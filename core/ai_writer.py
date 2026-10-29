"""
AI 文案生成器

核心功能：
1. 调用外部 AI 服务生成高质量文案
2. 提供专业的提示词模板（可优化）
3. 支持社交媒体文案和分析报告生成
4. 支持最多8次重构尝试
5. 提供质量评估机制

提示词设计原则：
- 角色设定：专业英语学习导师
- 明确目标：生成具有高学习价值的内容
- 结构化输出：清晰的板块划分
- 深度分析：词汇、语法、语境多维度解析
"""

import json
import time
from typing import Optional, Dict, Any, List
from enum import auto
import sys as _sys
if _sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum as _Enum
    class StrEnum(str, _Enum):
        pass

from utils.logger import get_crawler_logger
from utils.config_loader import load_config


logger = get_crawler_logger()

# AUDIT-0050: 4 处重复 lang_names 抽成模块级常量
LANG_NAMES: Dict[str, str] = {
    "en": "英语", "de": "德语", "fr": "法语", "es": "西班牙语",
    "it": "意大利语", "pt": "葡萄牙语", "nl": "荷兰语",
    "zh": "中文", "ja": "日语", "ko": "韩语", "ru": "俄语",
}


class ContentType(StrEnum):
    """文案类型枚举"""
    XIAOHONGSHU_ORAL = auto()
    XIAOHONGSHU_EXAM = auto()
    WEIBO_ORAL = auto()
    WEIBO_EXAM = auto()
    ZHIHU_ORAL = auto()
    ZHIHU_EXAM = auto()
    ANALYSIS_REPORT = auto()
    # 语言学习分析报告（多语言，由 video_analyzer 调用）
    ORAL_ANALYSIS = auto()   # 口语学习分析
    EXAM_ANALYSIS = auto()   # 应试学习分析

    @property
    def display_name(self) -> str:
        names = {
            "xiaohongshu_oral": "小红书-口语学习",
            "xiaohongshu_exam": "小红书-应试学习",
            "weibo_oral": "微博-口语学习",
            "weibo_exam": "微博-应试学习",
            "zhihu_oral": "知乎-口语学习",
            "zhihu_exam": "知乎-应试学习",
            "analysis_report": "分析报告",
            "oral_analysis": "口语学习分析报告",
            "exam_analysis": "应试学习分析报告",
        }
        return names.get(self.value, self.value)


class AIWriterConfig:
    """AI 文案生成器配置

    双梯队降级链（2026-09-24 实测 ping 全量更新）：

        梯队 1 (Groq):  qwen/qwen3.8-27b → openai/gpt-oss-20b → openai/gpt-oss-120b
                        通过 /openai/v1/models 动态拉取（加 curl UA 绕过 Cloudflare）
                        2026-09-24 实测：你的 Groq Key 下只有 11 个模型，文本模型就这三个
                        旧的 llama-4-maverick/3.3-70b/deepseek-r1-distill 全部 404（Key 没权限）

        梯队 2 (GLM):   glm-5.3-flash → glm-5.3-flashx → glm-5.3 → glm-5.2 → glm-5.1 → glm-5 →
                        glm-5-turbo → glm-4.7 → glm-4.6 → glm-4.5 → glm-4.5-air
                        通过 /api/paas/v4/models 动态拉取到 11 个，全部 ping OK

    梯队 1 全部失败才走梯队 2。
    Gemini 梯队已停用（日配额有限），保留定义供未来恢复。
    """

    # ---------- Groq 梯队（2026-09-24 从 /openai/v1/models 动态拉取 + 加 curl UA 绕过 Cloudflare 全部 ping OK）----------
    # 顺序 = 速度优先（27b 最快）→ 质量兜底（120b 最大）
    # 旧版 GROQ_CHAIN（llama-4-maverick / 3.3-70b / deepseek-r1-distill）：这个 Key 下全部 404 无权限
    GROQ_CHAIN = [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ]

    # ---------- GLM 梯队（2026-09-23 从 /api/paas/v4/models 动态拉取 + 全部 ping OK）----------
    # 按速度/成本优先级：flash 快且便宜 → 标准 → 4.x 兜底
    GLM_CHAIN = [
        "glm-5.3-flash",
        "glm-5.3-flashx",
        "glm-5.3",
        "glm-5.2",
        "glm-5.1",
        "glm-5",
        "glm-5-turbo",
        "glm-4.7",
        "glm-4.6",
        "glm-4.5",
        "glm-4.5-air",
    ]

    # ---------- Gemini 梯队（已停用，保留定义）----------
    GEMINI_CHAIN = [
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
        "gemini-3.7-flash",
    ]

    RETRIES_PER_MODEL = 2  # 每个模型最多重试

    # Groq Cloudflare WAF 硬要求：Python urllib 默认 UA 会被直接 403:1010 拦截
    # 必须伪装成 curl 或浏览器；requests 默认 UA 也可能中招，统一用这个常量
    GROQ_USER_AGENT = "curl/8.7.1"

    def __init__(self) -> None:
        config = load_config()
        ai_config = config.get("ai_writer", {})

        # ---- Groq 梯队（主梯队）----
        groq_cfg = config.get("groq", {})
        self.groq_enabled: bool = bool(
            groq_cfg.get("enabled", False)
            and bool(groq_cfg.get("api_key", ""))
            and bool(groq_cfg.get("api_url", ""))
        )
        self.groq_api_url: str = str(groq_cfg.get("api_url", "")).strip()
        self.groq_api_key: str = str(groq_cfg.get("api_key", "")).strip()
        self.groq_timeout: int = int(groq_cfg.get("timeout", 120))

        # 组装 Groq 链：优先用 config.model_chain（用户 GUI 勾选），没有回退到旧逻辑
        raw_groq_chain = groq_cfg.get("model_chain")
        if isinstance(raw_groq_chain, list) and raw_groq_chain:
            self.groq_chain: List[str] = [str(m) for m in raw_groq_chain if m]
        else:
            self.groq_chain = []
            primary_groq = groq_cfg.get("model")
            if primary_groq:
                self.groq_chain.append(str(primary_groq))
            for m in self.GROQ_CHAIN:
                if m not in self.groq_chain:
                    self.groq_chain.append(m)

        # ---- GLM 梯队（备用梯队）----
        self.api_url = ai_config.get("api_url", "")
        self.api_key = ai_config.get("api_key", "")
        self.max_retries = ai_config.get("max_retries", 8)
        self.timeout = ai_config.get("timeout", 60)
        self.model = ai_config.get("model", "glm-4.7-flash")
        self.temperature = ai_config.get("temperature", 0.7)
        self.max_tokens = ai_config.get("max_tokens", 4000)
        self.enabled = ai_config.get("enabled", False)

        # GLM 链：优先用 config.model_chain
        raw_glm_chain = ai_config.get("model_chain")
        if isinstance(raw_glm_chain, list) and raw_glm_chain:
            self.glm_chain: List[str] = [str(m) for m in raw_glm_chain if m]
        else:
            self.glm_chain = []
            if self.model and self.model.startswith("glm"):
                self.glm_chain.append(self.model)
            for m in self.GLM_CHAIN:
                if m not in self.glm_chain:
                    self.glm_chain.append(m)

        # ---- Gemini 梯队（已停用）----
        gemini_cfg = config.get("gemini", {})
        self.gemini_enabled: bool = False
        self.gemini_api_key: str = str(gemini_cfg.get("api_key", "")).strip()
        self.gemini_proxy: str = str(gemini_cfg.get("proxy", "")).strip() or str(
            config.get("crawler", {}).get("proxy", "")
        ).strip()

        # Gemini 链：优先用 config.model_chain
        raw_gem_chain = gemini_cfg.get("model_chain")
        if isinstance(raw_gem_chain, list) and raw_gem_chain:
            self.gemini_chain: List[str] = [str(m) for m in raw_gem_chain if m]
        else:
            self.gemini_chain = []
            primary = gemini_cfg.get("model")
            if primary:
                self.gemini_chain.append(str(primary))
            for m in self.GEMINI_CHAIN:
                if m not in self.gemini_chain:
                    self.gemini_chain.append(m)


class AIWriter:
    """
    AI 文案生成器
    
    支持调用外部 AI 服务生成高质量的英语学习文案。
    如果本地代码生成的文案质量不达标，可以调用 AI 服务生成。
    """
    
    MAX_REWRITE_ATTEMPTS = 8
    
    def __init__(self) -> None:
        """初始化 AI 文案生成器"""
        self._config = AIWriterConfig()
        self._prompt_version = 1

        if self._config.groq_enabled:
            logger.info(
                f"AI 文案生成器 ✅ Groq 梯队可用 "
                f"({len(self._config.groq_chain)} 个模型): {self._config.groq_chain}"
            )
        else:
            logger.info("AI 文案生成器: Groq 梯队未启用")

        if self._config.api_url and self._config.api_key:
            logger.info(
                f"AI 文案生成器: GLM 梯队可用 "
                f"({len(self._config.glm_chain)} 个模型): {self._config.glm_chain}"
            )
        else:
            logger.info("AI 文案生成器: GLM 梯队未配置")

        if self._config.gemini_enabled:
            logger.info(
                f"AI 文案生成器: Gemini 梯队可用 "
                f"({len(self._config.gemini_chain)} 个模型): {self._config.gemini_chain}"
            )
        else:
            logger.info("AI 文案生成器: Gemini 梯队未启用")

        self._gemini_client = None
    
    def generate_content(
        self,
        subtitles: List[Dict[str, Any]],
        content_type: ContentType,
        max_attempts: int = MAX_REWRITE_ATTEMPTS,
        language: str = "en"
    ) -> str:
        """
        生成高质量文案

        Args:
            subtitles: 字幕列表，包含 text 和 translated_text
            content_type: 文案类型
            max_attempts: 最大重构尝试次数
            language: 视频源语言代码（en/de/fr/es/it/pt/nl/zh/ja/ko/ru 等），
                      仅对 ORAL_ANALYSIS/EXAM_ANALYSIS 生效，其他类型忽略此参数

        Returns:
            生成的文案内容（失败返回空字符串）
        """
        if not (self._config.groq_enabled or (self._config.enabled and self._config.api_url and self._config.api_key)):
            logger.warning("AI 文案生成器未启用：GLM / Groq 梯队均不可用")
            return ""

        subtitle_text = self._format_subtitles(subtitles)

        for attempt in range(1, max_attempts + 1):
            logger.info(f"AI 文案生成第 {attempt}/{max_attempts} 次尝试 (type={content_type.value}, lang={language})")

            try:
                prompt = self._build_prompt(subtitle_text, content_type, attempt, language=language)
                response = self._call_ai_api(prompt, language=language)

                if response:
                    quality_score = self._evaluate_quality(response, subtitles)
                    logger.info(f"第 {attempt} 次尝试质量评分: {quality_score}/10")

                    if quality_score >= 7:
                        logger.info(f"第 {attempt} 次尝试成功，质量达标")
                        return response
                    else:
                        logger.warning(f"第 {attempt} 次尝试质量不达标，继续优化提示词")

            except Exception as e:
                logger.error(f"第 {attempt} 次尝试失败: {e}")
                time.sleep(2)

        logger.warning(f"已尝试 {max_attempts} 次，使用最后一次生成的文案")
        try:
            prompt = self._build_prompt(subtitle_text, content_type, max_attempts, language=language)
            return self._call_ai_api(prompt, language=language) or ""
        except Exception as e:
            logger.error(f"最终尝试也失败: {e}")
            return ""
    
    def _format_subtitles(self, subtitles: List[Dict[str, Any]]) -> str:
        """格式化字幕文本供 AI 使用"""
        lines = []
        for i, sub in enumerate(subtitles[:50], 1):
            text = sub.get("text", "").strip()
            translated = sub.get("translated_text", "").strip()
            if text:
                lines.append(f"{i}. {text}")
                if translated:
                    lines.append(f"   翻译：{translated}")
                lines.append("")
        return "\n".join(lines)
    
    def _build_prompt(self, subtitle_text: str, content_type: ContentType, attempt: int, language: str = "en") -> str:
        """构建专业的提示词"""
        base_prompt = self._get_base_prompt(content_type, language=language)

        optimization_notes = self._get_optimization_notes(attempt)

        return f"""{base_prompt}

{optimization_notes}

视频字幕内容（请基于以下内容进行分析和创作）：

{subtitle_text}

请严格按照以上要求生成文案，确保内容具有真正的学习价值！"""

    def _get_base_prompt(self, content_type: ContentType, language: str = "en") -> str:
        """获取基础提示词"""
        prompts = {
            ContentType.XIAOHONGSHU_ORAL: self._get_xiaohongshu_oral_prompt(language),
            ContentType.XIAOHONGSHU_EXAM: self._get_xiaohongshu_exam_prompt(language),
            ContentType.WEIBO_ORAL: self._get_weibo_oral_prompt(language),
            ContentType.WEIBO_EXAM: self._get_weibo_exam_prompt(language),
            ContentType.ZHIHU_ORAL: self._get_zhihu_oral_prompt(language),
            ContentType.ZHIHU_EXAM: self._get_zhihu_exam_prompt(language),
            ContentType.ANALYSIS_REPORT: self._get_analysis_report_prompt(),
            ContentType.ORAL_ANALYSIS: self._get_oral_analysis_prompt(language),
            ContentType.EXAM_ANALYSIS: self._get_exam_analysis_prompt(language),
        }
        return prompts.get(content_type, self._get_default_prompt())
    
    def _get_lang_name(self, language: str) -> str:
        """语言代码转中文名"""
        return LANG_NAMES.get(language, "目标语言")

    def _get_xiaohongshu_oral_prompt(self, language: str = "en") -> str:
        """小红书口语学习风格提示词（多语言）"""
        lang_name = self._get_lang_name(language)
        return f"""你是一位专业的{lang_name}口语学习导师，擅长从真实视频中提炼有价值的语言知识点。

请根据提供的视频字幕，生成一篇适合在小红书发布的{lang_name}学习文案，要求：

【输出语言要求】
- 所有讲解、分析、感悟使用**中文**
- 所有例句必须保留**{lang_name}原文**，并附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【整体风格】
- 活泼亲切，使用emoji和话题标签
- 标题要吸引人，带话题感
- 内容结构清晰，分板块展示

【内容要求】
1. 高频口语表达深度解析（3-5个）
   - {lang_name}原句（摘自字幕）
   - 含义解释（中文）
   - 中{lang_name}表达差异对比
   - 语气和使用场景分析
   - 学习误区提示
   - 场景拓展和例句

2. 实用词汇学习（3-5个）
   - 常用搭配（{lang_name}给出）
   - 同义替换（{lang_name}给出）
   - 记忆技巧

3. 地道句型分析（2-3个）
   - 句型结构拆解
   - 真实学习感悟
   - 仿写练习建议

4. 短语动词（2-3个）
   - 含义和例句（{lang_name}原文）
   - 学习提示

【质量标准】
- 内容必须具有真正的学习价值，不能空洞
- 每个知识点都要有详细解析，不能简单罗列
- 学习感悟要真实具体，不能模板化
- 避免重复内容，每个板块内容不重叠
- 使用真实的例子，不要编造

【输出格式】
- 使用Markdown格式
- 每个板块要有清晰的标题
- 适当使用emoji增强可读性
- 末尾添加相关话题标签"""
    
    def _get_xiaohongshu_exam_prompt(self, language: str = "en") -> str:
        """小红书应试学习风格提示词（多语言）"""
        lang_name = self._get_lang_name(language)
        return f"""你是一位专业的{lang_name}考试辅导老师，擅长从真实视频中提炼对考试有用的语言知识点。

请根据提供的视频字幕，生成一篇适合在小红书发布的应试{lang_name}学习文案，要求：

【输出语言要求】
- 所有讲解、分析、感悟使用**中文**
- 所有例句必须保留**{lang_name}原文**，并附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【整体风格】
- 专业实用，使用emoji和话题标签
- 标题要突出干货价值
- 内容结构清晰，分板块展示

【内容要求】
1. 高级词汇深度解析（5-8个）
   - {lang_name}词汇（原文）
   - 常用搭配（至少3个，{lang_name}给出）
   - 同义替换（至少3个，{lang_name}给出）
   - 单词家族拓展
   - 记忆技巧

2. 长难句精准拆解（3-5个）
   - {lang_name}原句（摘自字幕）
   - 句子结构分析
   - 语法特征标注
   - 成分拆解
   - 学习感悟和考试要点

3. 高分搭配积累（5-8个）
   - 词块组合（{lang_name}给出）
   - 例句展示

4. 写作技巧总结（4-6条）
   - 词汇升级方法
   - 句式多样化技巧
   - 连接词使用
   - 避免中式{lang_name}

【质量标准】
- 内容必须对考试有直接帮助
- 词汇选择要符合考试高频词
- 长难句分析要有深度，不能泛泛而谈
- 学习建议要具体可操作
- 避免简单词汇和基础句型的重复分析

【输出格式】
- 使用Markdown格式
- 每个板块要有清晰的标题
- 适当使用emoji增强可读性
- 末尾添加相关话题标签"""
    
    def _get_weibo_oral_prompt(self, language: str = "en") -> str:
        """微博口语学习风格提示词（多语言）"""
        lang_name = self._get_lang_name(language)
        return f"""你是一位专业的{lang_name}口语学习导师。

请根据提供的视频字幕，生成一篇适合在微博发布的{lang_name}学习文案，要求：

【输出语言要求】
- 所有讲解使用**中文**
- 所有例句必须保留**{lang_name}原文**，并附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【整体风格】
- 简洁有力，适合移动端阅读
- 使用话题标签
- 每段不要太长

【内容要求】
1. 高频口语表达（5-8个）
   - {lang_name}表达 + 中文含义
   - 简短例句（{lang_name}原文）
   - 学习提示

2. 实用短语动词（3-5个）
   - {lang_name}短语 + 含义
   - 例句（{lang_name}原文）

3. 地道句型（2-3个）
   - {lang_name}句型 + 分析

【质量标准】
- 内容必须实用，不能空洞
- 每个表达都要有学习价值
- 语言简洁，避免冗长

【输出格式】
- 使用简洁的文本格式
- 适当使用emoji
- 末尾添加话题标签"""

    def _get_weibo_exam_prompt(self, language: str = "en") -> str:
        """微博应试学习风格提示词（多语言）"""
        lang_name = self._get_lang_name(language)
        return f"""你是一位专业的{lang_name}考试辅导老师。

请根据提供的视频字幕，生成一篇适合在微博发布的应试{lang_name}学习文案，要求：

【输出语言要求】
- 所有讲解使用**中文**
- 所有例句必须保留**{lang_name}原文**，并附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【整体风格】
- 干货满满，直接实用
- 使用话题标签
- 每段不要太长

【内容要求】
1. 高级词汇积累（5-8个）
   - {lang_name}词汇 + 搭配

2. 长难句拆解（2-3个）
   - {lang_name}原句 + 分析

3. 写作技巧（3-5条）

【质量标准】
- 内容必须对考试有直接帮助
- 词汇选择要符合考试高频词
- 技巧要具体可操作

【输出格式】
- 使用简洁的文本格式
- 适当使用emoji
- 末尾添加话题标签"""
    
    def _get_zhihu_oral_prompt(self, language: str = "en") -> str:
        """知乎口语学习风格提示词（多语言）"""
        lang_name = self._get_lang_name(language)
        return f"""你是一位专业的{lang_name}口语学习导师，擅长从真实视频中提炼有价值的语言知识点。

请根据提供的视频字幕，生成一篇适合在知乎发布的{lang_name}学习文章，要求：

【输出语言要求】
- 所有讲解、分析、感悟使用**中文**
- 所有例句必须保留**{lang_name}原文**，并附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【整体风格】
- 专业深度，逻辑清晰
- 适合深度阅读
- 使用Markdown格式

【内容要求】
1. 高频口语表达深度解析（5-8个）
   - {lang_name}原句（摘自字幕）+ 含义和用法详解
   - 中{lang_name}表达差异对比分析
   - 语气辨析
   - 学习误区和常见错误
   - 场景拓展和使用建议

2. 核心词汇解析（3-5个）
   - {lang_name}词汇 + 详细释义
   - 记忆技巧
   - 常见搭配（{lang_name}给出）

3. 短语动词学习（3-5个）
   - {lang_name}短语 + 含义和例句
   - 学习提示

4. 实用句型分析（2-3个）
   - {lang_name}句型结构分析
   - 学习感悟
   - 仿写练习

5. 总结
   - 学习方法建议
   - 实践建议

【质量标准】
- 内容必须具有真正的学习价值
- 分析要有深度，不能简单罗列
- 语言要专业但易懂
- 学习建议要具体可操作

【输出格式】
- 使用Markdown格式
- 使用合适的标题层级
- 结构清晰，逻辑严谨"""

    def _get_zhihu_exam_prompt(self, language: str = "en") -> str:
        """知乎应试学习风格提示词（多语言）"""
        lang_name = self._get_lang_name(language)
        return f"""你是一位专业的{lang_name}考试辅导老师，擅长从真实视频中提炼对考试有用的语言知识点。

请根据提供的视频字幕，生成一篇适合在知乎发布的应试{lang_name}学习文章，要求：

【输出语言要求】
- 所有讲解、分析、感悟使用**中文**
- 所有例句必须保留**{lang_name}原文**，并附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【整体风格】
- 专业深度，逻辑清晰
- 适合深度阅读
- 使用Markdown格式

【内容要求】
1. 高级词汇深度解析（5-8个）
   - {lang_name}词汇 + 详细释义
   - 常用搭配（至少5个，{lang_name}给出）
   - 同义替换（至少3个，{lang_name}给出）
   - 单词家族拓展
   - 记忆技巧
   - 考试应用场景

2. 长难句深度分析（3-5个）
   - {lang_name}完整原文和中文翻译
   - 句子类型判断
   - 语法特征分析
   - 结构拆解（成分分析）
   - 学习感悟和考试要点
   - 仿写练习建议

3. 写作技巧总结（6-8条）
   - 词汇升级方法
   - 句式多样化技巧
   - 连接词使用策略
   - 避免中式{lang_name}的方法
   - 段落结构优化
   - 论证方法建议

4. 总结
   - 学习路径建议
   - 备考策略

【质量标准】
- 内容必须对考试有直接帮助
- 词汇选择要符合考试高频词
- 长难句分析要有深度，不能泛泛而谈
- 学习建议要具体可操作
- 避免简单词汇和基础句型的重复分析

【输出格式】
- 使用Markdown格式
- 使用合适的标题层级
- 结构清晰，逻辑严谨"""
    
    def _get_analysis_report_prompt(self) -> str:
        """分析报告提示词"""
        return """你是一位专业的英语语言分析专家。

请根据提供的视频字幕，生成一份详细的英语学习分析报告，要求：

【内容要求】
1. 高级词汇分析（5-8个）
   - 词汇 + 释义 + 例句
   - 常用搭配
   - 同义替换

2. 复杂句式分析（3-5个）
   - 原文 + 翻译
   - 句子类型
   - 语法特征
   - 结构拆解

3. 长难句深度分析（2-3个）
   - 完整分析

4. 书面表达推荐
   - 口语词替换为正式表达
   - 例句对比

5. 学习建议

【质量标准】
- 分析要有深度
- 内容要有学习价值
- 结构清晰

【输出格式】
- 使用Markdown格式"""
    
    def _get_system_message(self, language: str) -> str:
        """根据视频源语言返回对应的 system message（避免对德语/法语视频仍自称英语导师）"""
        lang_name = LANG_NAMES.get(language, "外语")
        return (
            f"你是一位专业的{lang_name}语言学习导师，擅长从真实视频字幕中提炼有价值的语言知识点。"
            f"你的讲解使用中文，但所有例句必须保留{lang_name}原文，并附上中文翻译。"
            f"你深刻理解{lang_name}的口语表达、语法特征和文化背景，能给出有深度的学习建议。"
        )

    def _get_oral_analysis_prompt(self, language: str) -> str:
        """口语学习分析报告 prompt（多语言）"""
        lang_name = LANG_NAMES.get(language, "目标语言")

        return f"""你是一位专业的{lang_name}口语学习专家。请根据提供的视频字幕，生成一份针对口语学习者的深度分析报告。

【输出语言要求】
- 所有讲解、分析、感悟、技巧一律使用**中文**
- 所有例句必须保留**{lang_name}原文**，并在下一行附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【内容要求】（每个板块都要基于字幕中的真实例句）

### 一、口语表达精华（5-8个）
针对每个表达：
- **{lang_name}原句**：摘自字幕的真实句子
- **中文翻译**：准确自然的中文
- **口语特征**：为什么这是地道口语（如：缩略、省略、语气词、习惯表达、文化背景）
- **学习感悟**：与中国学习者母语表达的差异、容易踩的坑、可迁移到哪些场景

### 二、语气词与填充词分析（3-5个）
- **{lang_name}原句**：含语气词的真实句子
- **中文翻译**
- **功能分析**：该语气词在对话中的作用（犹豫、强调、转折、应答等）
- **使用建议**：什么场合用、频率如何、中国学习者容易误用的地方

### 三、地道表达 vs 教科书表达（3-5组对比）
- **{lang_name}口语表达**（来自字幕）
- **{lang_name}教科书表达**（你给出的正式等价说法）
- **中文翻译**
- **差异分析**：为什么口语会这样变形（节奏、连读、弱化、文化习惯）

### 四、长难口语段拆解（1-2个）
选一段较长的口语（3句以上连续）：
- **{lang_name}原文**
- **中文翻译**
- **口语逻辑**：这段话是怎么展开的（开场→铺垫→核心→收尾）
- **可借鉴的口语框架**：学习者可以怎么套用这种结构

### 五、口语学习建议
基于本次视频的内容，给出 3-5 条具体可操作的建议：
- 不是泛泛而谈的"多听多说"
- 必须结合视频中的具体例子
- 至少包含 1 条中国学习者常犯的错误纠正

【质量标准】
- 每个分析点必须有真实的字幕例句支撑，禁止编造
- 学习感悟要深入，避免"这个表达很有用"这类空洞话
- 对比中国学习者的母语习惯，体现跨语言视角
- 总字数 1500-2500 字

【输出格式】
- 使用 Markdown 格式
- 原文例句用引用块（>）或粗体突出
- 中文翻译紧跟其后，用 *斜体* 标注"""

    def _get_exam_analysis_prompt(self, language: str) -> str:
        """应试学习分析报告 prompt（多语言）"""
        lang_name = LANG_NAMES.get(language, "目标语言")

        return f"""你是一位专业的{lang_name}应试学习专家，熟悉各级别语言考试（如{lang_name}专四专八、歌德证书、DELF/DALF、DELE等）的考点。请根据提供的视频字幕，生成一份针对应试学习者的深度分析报告。

【输出语言要求】
- 所有讲解、分析、感悟、技巧一律使用**中文**
- 所有例句必须保留**{lang_name}原文**，并在下一行附上**中文翻译**
- 严禁将原文翻译成英文或其他语言

【内容要求】（每个板块都要基于字幕中的真实例句）

### 一、高级词汇分析（5-8个）
针对每个词汇：
- **{lang_name}词汇**：原文出现的词
- **词性 + 中文释义**
- **{lang_name}例句**（摘自字幕）
- **中文翻译**
- **常用搭配**（2-3个，用{lang_name}给出）
- **同义替换**（2-3个{lang_name}同义词，标注细微差异）
- **考试应用**：该词在写作/阅读/翻译中如何拿高分

### 二、复杂句式分析（3-5个）
针对每个句式：
- **{lang_name}原句**（摘自字幕）
- **中文翻译**
- **句子类型**（主从复合句、倒装、虚拟、被动等）
- **语法特征**：核心语法点是什么
- **结构拆解**：主句/从句/修饰关系
- **考试应用**：如何在写作中模仿这种句式

### 三、长难句深度分析（2-3个）
选最复杂的句子：
- **{lang_name}原句**
- **中文翻译**
- **语法树拆解**：逐层分析句子结构
- **翻译难点**：中国学习者容易翻译错的地方
- **学习感悟**：理解这类句子的关键是什么

### 四、书面表达升级（3-5组对比）
- **{lang_name}口语表达**（来自字幕）
- **{lang_name}书面/高级表达**（你给出的等价正式说法）
- **中文翻译**
- **升级分析**：为什么书面要这样写（用词、句式、语气）

### 五、写作技巧总结
基于本次视频，给出 3-5 条针对{lang_name}写作的技巧：
- 必须用{lang_name}词汇和句式作示例（严禁出现英文示例）
- 每条技巧结合视频中的具体例子
- 至少包含 1 条"中国学习者常犯的母语负迁移错误"

### 六、考试应用建议
- 这些词汇/句式适用于哪些考试题型
- 如何在作文/翻译中主动运用

【质量标准】
- 每个分析点必须有真实的字幕例句支撑，禁止编造
- 语法分析要有深度，不能只贴标签
- 同义替换要标注细微差异，不能简单罗列
- 总字数 1500-2500 字

【输出格式】
- 使用 Markdown 格式
- 原文例句用引用块（>）或粗体突出
- 中文翻译紧跟其后，用 *斜体* 标注"""

    def _get_default_prompt(self) -> str:
        """默认提示词"""
        return """你是一位专业的英语学习导师。

请根据提供的视频字幕，生成一篇高质量的英语学习文案。

要求：
1. 内容具有真正的学习价值
2. 分析要有深度
3. 结构清晰
4. 使用Markdown格式"""
    
    def _get_optimization_notes(self, attempt: int) -> str:
        """获取优化提示词（根据尝试次数逐步优化）"""
        notes = [
            "",
            "【优化提示】请确保每个知识点都有详细解析，不要简单罗列词汇。",
            "【优化提示】请增加词汇的搭配和例句，提供更多学习价值。",
            "【优化提示】请增加语法分析的深度，提供结构拆解和学习感悟。",
            "【优化提示】请确保内容不重复，每个板块有独特的知识点。",
            "【优化提示】请提供真实的学习感悟，避免模板化的表述。",
            "【优化提示】请增加更多实用的学习技巧和记忆方法。",
            "【优化提示】请确保所有内容都对学习者有实际帮助，避免空洞内容。",
        ]
        if attempt > len(notes):
            return notes[-1]
        return notes[attempt - 1]
    
    def _call_ai_api(self, prompt: str, language: str = "en") -> Optional[str]:
        """双梯队链式降级调用

        梯队 1: Groq  (qwen/qwen3.8-27b → gpt-oss-20b → gpt-oss-120b)
        梯队 2: GLM   (glm-5.3-flash → glm-5.3-flashx → glm-5.3 → glm-5.x → glm-4.x)
        （Gemini 梯队已停用）

        每个模型内部做 2 次指数退避重试（针对 503/429/overloaded/timeout）。
        梯队 1 全部失败才走梯队 2。
        """
        import random

        system_msg = self._get_system_message(language)

        # ---------- 梯队 1: Groq ----------
        if self._config.groq_enabled:
            result = self._call_chain(
                provider="Groq",
                chain=self._config.groq_chain,
                invoker=lambda model: self._call_openai_compat(
                    model, system_msg, prompt,
                    base_url=self._config.groq_api_url,
                    api_key=self._config.groq_api_key,
                    timeout=self._config.groq_timeout,
                ),
            )
            if result:
                return result
            logger.warning("Groq 梯队全部失败，降级到 GLM 梯队")

        # ---------- 梯队 2: GLM ----------
        if self._config.api_url and self._config.api_key:
            result = self._call_chain(
                provider="GLM",
                chain=self._config.glm_chain,
                invoker=lambda model: self._call_openai_compat(
                    model, system_msg, prompt,
                ),
            )
            if result:
                return result

        logger.error("所有 AI 梯队均无可用模型 / 调用失败")
        return None

    # ---------------------------------------------------------------
    # 链式降级调度器
    # ---------------------------------------------------------------

    def _call_chain(self, provider: str, chain: List[str], invoker) -> Optional[str]:
        """在给定模型链上依次尝试，每个模型带内部重试"""
        import random

        for model in chain:
            last_err: Optional[str] = None
            for attempt in range(1, self._config.RETRIES_PER_MODEL + 1):
                try:
                    result = invoker(model)
                    if result:
                        logger.info(f"[{provider}] {model} ✅ 调用成功")
                        return result
                    logger.warning(f"[{provider}] {model} 返回空结果")
                    last_err = "empty response"
                except Exception as e:
                    last_err = str(e)
                    msg = last_err
                    is_retryable = any(
                        code in msg
                        for code in ("503", "500", "429", "UNAVAILABLE", "overloaded", "timeout")
                    )
                    if is_retryable and attempt < self._config.RETRIES_PER_MODEL:
                        backoff = min(2 ** (attempt - 1), 16) + random.uniform(0, 1.5)
                        logger.warning(
                            f"[{provider}] {model} API 失败 "
                            f"(retry {attempt}/{self._config.RETRIES_PER_MODEL}): "
                            f"{msg[:100]} — {backoff:.1f}s 后重试"
                        )
                        time.sleep(backoff)
                        continue
                    # 不可重试 / 已用尽 → 切下一个模型
                    break

            logger.warning(
                f"[{provider}] {model} 全部重试失败 ({last_err}) → 降级"
            )

        return None

    # ---------------------------------------------------------------
    # Gemini 调用
    # ---------------------------------------------------------------
    # AUDIT-0049: Gemini 梯队已硬停用（gemini_enabled=False），
    # _get_gemini_client / _call_gemini 无调用方，保留待恢复时启用。

    def _get_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client
        import os

        proxy = self._config.gemini_proxy
        if proxy:
            os.environ.setdefault("HTTPS_PROXY", proxy)
            os.environ.setdefault("HTTP_PROXY", proxy)
        try:
            import google.genai as genai
        except ImportError as e:
            raise RuntimeError(f"google-genai 未安装: {e}")
        self._gemini_client = genai.Client(api_key=self._config.gemini_api_key)
        return self._gemini_client

    def _call_gemini(self, model: str, system_msg: str, prompt: str) -> str:
        """用 google-genai SDK 纯文本调用"""
        client = self._get_gemini_client()

        try:
            import google.genai.types as types
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_msg,
                    temperature=self._config.temperature,
                    max_output_tokens=self._config.max_tokens,
                ),
            )
        except TypeError:
            # 旧版 SDK 不接受 config 参数，降级调用
            response = client.models.generate_content(
                model=model,
                contents=[system_msg, prompt],
            )

        text = getattr(response, "text", None) or ""
        text = text.strip()
        if not text:
            raise RuntimeError("Gemini 返回空 text")
        return text

    # ---------------------------------------------------------------
    # OpenAI 兼容调用 (glm)
    # ---------------------------------------------------------------

    def _call_openai_compat(
        self,
        model: str,
        system_msg: str,
        prompt: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        """调用 OpenAI 兼容接口（Groq / 智谱 GLM 等都用）

        Args:
            model: 模型名
            system_msg: system prompt
            prompt: user prompt
            base_url: 接口地址，None → 用 config.api_url
            api_key: API key，None → 用 config.api_key
            timeout: 超时秒数，None → 用 config.timeout
        """
        import requests as std_requests

        url = base_url if base_url else self._config.api_url
        key = api_key if api_key else self._config.api_key
        t = timeout if timeout else self._config.timeout

        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        # Groq Cloudflare WAF 硬拦截：requests 默认 UA 会直接 403:1010
        # 伪装成 curl；智谱 GLM 也无妨（不会因为 UA 报错）
        if url and "groq.com" in url:
            headers["User-Agent"] = AIWriterConfig.GROQ_USER_AGENT

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }

        response = std_requests.post(
            url,
            headers=headers,
            json=data,
            timeout=t,
        )
        response.raise_for_status()
        result = response.json()

        if "choices" in result and result["choices"]:
            return (result["choices"][0]["message"]["content"] or "").strip()
        if "content" in result:
            return (result["content"] or "").strip()

        raise RuntimeError(f"API 返回格式异常: {result}")
    
    def _evaluate_quality(self, content: str, subtitles: List[Dict[str, Any]]) -> int:
        """评估文案质量（1-10分）"""
        score = 0

        if len(content) > 500:
            score += 2
        elif len(content) > 200:
            score += 1

        sections = ["##", "###", "一、", "二、", "三、", "四、", "五、", "六、"]
        section_count = sum(1 for s in sections if s in content)
        if section_count >= 3:
            score += 2
        elif section_count >= 2:
            score += 1

        if "搭配" in content or "collocation" in content.lower():
            score += 1

        if "同义" in content or "synonym" in content.lower():
            score += 1

        if "分析" in content or "analysis" in content.lower():
            score += 1

        if "学习感悟" in content or "感悟" in content:
            score += 1

        if "记忆" in content or "memory" in content.lower():
            score += 1

        # 口语分析报告常见关键词（弥补口语类报告不含"同义/记忆"导致的评分偏低）
        if "口语" in content:
            score += 1
        if "语气" in content:
            score += 1
        if "地道" in content:
            score += 1
        if "场景" in content:
            score += 1
        # 应试分析报告常见关键词
        if "语法" in content:
            score += 1
        if "句式" in content or "句型" in content:
            score += 1
        if "翻译" in content:
            score += 1
        if "建议" in content:
            score += 1

        return min(score, 10)


def get_ai_writer() -> AIWriter:
    """获取 AI 文案生成器单例"""
    global _ai_writer_instance
    if _ai_writer_instance is None:
        _ai_writer_instance = AIWriter()
    return _ai_writer_instance


_ai_writer_instance: Optional[AIWriter] = None