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
from enum import StrEnum, auto

from utils.logger import get_crawler_logger
from utils.config_loader import load_config


logger = get_crawler_logger()


class ContentType(StrEnum):
    """文案类型枚举"""
    XIAOHONGSHU_ORAL = auto()
    XIAOHONGSHU_EXAM = auto()
    WEIBO_ORAL = auto()
    WEIBO_EXAM = auto()
    ZHIHU_ORAL = auto()
    ZHIHU_EXAM = auto()
    ANALYSIS_REPORT = auto()
    
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
        }
        return names.get(self.value, self.value)


class AIWriterConfig:
    """AI 文案生成器配置"""
    
    def __init__(self) -> None:
        config = load_config()
        ai_config = config.get("ai_writer", {})
        self.api_url = ai_config.get("api_url", "")
        self.api_key = ai_config.get("api_key", "")
        self.max_retries = ai_config.get("max_retries", 8)
        self.timeout = ai_config.get("timeout", 60)
        self.model = ai_config.get("model", "gpt-4o")
        self.temperature = ai_config.get("temperature", 0.7)
        self.max_tokens = ai_config.get("max_tokens", 4000)
        self.enabled = ai_config.get("enabled", False)


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
        logger.info(f"AI 文案生成器初始化完成，API: {'已配置' if self._config.api_url else '未配置'}")
    
    def generate_content(
        self,
        subtitles: List[Dict[str, Any]],
        content_type: ContentType,
        max_attempts: int = MAX_REWRITE_ATTEMPTS
    ) -> str:
        """
        生成高质量文案
        
        Args:
            subtitles: 字幕列表，包含 text 和 translated_text
            content_type: 文案类型
            max_attempts: 最大重构尝试次数
            
        Returns:
            生成的文案内容
        """
        if not self._config.enabled or not self._config.api_url:
            logger.warning("AI 文案生成器未启用或未配置 API")
            return ""
        
        subtitle_text = self._format_subtitles(subtitles)
        
        for attempt in range(1, max_attempts + 1):
            logger.info(f"AI 文案生成第 {attempt}/{max_attempts} 次尝试")
            
            try:
                prompt = self._build_prompt(subtitle_text, content_type, attempt)
                response = self._call_ai_api(prompt)
                
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
            prompt = self._build_prompt(subtitle_text, content_type, max_attempts)
            return self._call_ai_api(prompt) or ""
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
    
    def _build_prompt(self, subtitle_text: str, content_type: ContentType, attempt: int) -> str:
        """构建专业的提示词"""
        base_prompt = self._get_base_prompt(content_type)
        
        optimization_notes = self._get_optimization_notes(attempt)
        
        return f"""{base_prompt}

{optimization_notes}

视频字幕内容（请基于以下内容进行分析和创作）：

{subtitle_text}

请严格按照以上要求生成文案，确保内容具有真正的学习价值！"""
    
    def _get_base_prompt(self, content_type: ContentType) -> str:
        """获取基础提示词"""
        prompts = {
            ContentType.XIAOHONGSHU_ORAL: self._get_xiaohongshu_oral_prompt(),
            ContentType.XIAOHONGSHU_EXAM: self._get_xiaohongshu_exam_prompt(),
            ContentType.WEIBO_ORAL: self._get_weibo_oral_prompt(),
            ContentType.WEIBO_EXAM: self._get_weibo_exam_prompt(),
            ContentType.ZHIHU_ORAL: self._get_zhihu_oral_prompt(),
            ContentType.ZHIHU_EXAM: self._get_zhihu_exam_prompt(),
            ContentType.ANALYSIS_REPORT: self._get_analysis_report_prompt(),
        }
        return prompts.get(content_type, self._get_default_prompt())
    
    def _get_xiaohongshu_oral_prompt(self) -> str:
        """小红书口语学习风格提示词"""
        return """你是一位专业的英语口语学习导师，擅长从真实视频中提炼有价值的语言知识点。

请根据提供的视频字幕，生成一篇适合在小红书发布的英语学习文案，要求：

【整体风格】
- 活泼亲切，使用emoji和话题标签
- 标题要吸引人，带话题感
- 内容结构清晰，分板块展示

【内容要求】
1. 高频口语表达深度解析（3-5个）
   - 含义解释（中文）
   - 中英表达差异对比
   - 语气和使用场景分析
   - 学习误区提示
   - 场景拓展和例句

2. 实用词汇学习（3-5个）
   - 常用搭配
   - 同义替换
   - 记忆技巧

3. 地道句型分析（2-3个）
   - 句型结构拆解
   - 真实学习感悟
   - 仿写练习建议

4. 短语动词（2-3个）
   - 含义和例句
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
    
    def _get_xiaohongshu_exam_prompt(self) -> str:
        """小红书应试学习风格提示词"""
        return """你是一位专业的英语考试辅导老师，擅长从真实视频中提炼对考试有用的语言知识点。

请根据提供的视频字幕，生成一篇适合在小红书发布的应试英语学习文案，要求：

【整体风格】
- 专业实用，使用emoji和话题标签
- 标题要突出干货价值
- 内容结构清晰，分板块展示

【内容要求】
1. 高级词汇深度解析（5-8个）
   - 常用搭配（至少3个）
   - 同义替换（至少3个）
   - 单词家族拓展
   - 记忆技巧

2. 长难句精准拆解（3-5个）
   - 句子结构分析
   - 语法特征标注
   - 成分拆解
   - 学习感悟和考试要点

3. 高分搭配积累（5-8个）
   - 词块组合
   - 例句展示

4. 写作技巧总结（4-6条）
   - 词汇升级方法
   - 句式多样化技巧
   - 连接词使用
   - 避免中式英语

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
    
    def _get_weibo_oral_prompt(self) -> str:
        """微博口语学习风格提示词"""
        return """你是一位专业的英语口语学习导师。

请根据提供的视频字幕，生成一篇适合在微博发布的英语学习文案，要求：

【整体风格】
- 简洁有力，适合移动端阅读
- 使用话题标签
- 每段不要太长

【内容要求】
1. 高频口语表达（5-8个）
   - 表达 + 含义
   - 简短例句
   - 学习提示

2. 实用短语动词（3-5个）
   - 短语 + 含义
   - 例句

3. 地道句型（2-3个）
   - 句型 + 分析

【质量标准】
- 内容必须实用，不能空洞
- 每个表达都要有学习价值
- 语言简洁，避免冗长

【输出格式】
- 使用简洁的文本格式
- 适当使用emoji
- 末尾添加话题标签"""
    
    def _get_weibo_exam_prompt(self) -> str:
        """微博应试学习风格提示词"""
        return """你是一位专业的英语考试辅导老师。

请根据提供的视频字幕，生成一篇适合在微博发布的应试英语学习文案，要求：

【整体风格】
- 干货满满，直接实用
- 使用话题标签
- 每段不要太长

【内容要求】
1. 高级词汇积累（5-8个）
   - 词汇 + 搭配

2. 长难句拆解（2-3个）
   - 句子 + 分析

3. 写作技巧（3-5条）

【质量标准】
- 内容必须对考试有直接帮助
- 词汇选择要符合考试高频词
- 技巧要具体可操作

【输出格式】
- 使用简洁的文本格式
- 适当使用emoji
- 末尾添加话题标签"""
    
    def _get_zhihu_oral_prompt(self) -> str:
        """知乎口语学习风格提示词"""
        return """你是一位专业的英语口语学习导师，擅长从真实视频中提炼有价值的语言知识点。

请根据提供的视频字幕，生成一篇适合在知乎发布的英语学习文章，要求：

【整体风格】
- 专业深度，逻辑清晰
- 适合深度阅读
- 使用Markdown格式

【内容要求】
1. 高频口语表达深度解析（5-8个）
   - 含义和用法详解
   - 中英表达差异对比分析
   - 语气辨析
   - 学习误区和常见错误
   - 场景拓展和使用建议

2. 核心词汇解析（3-5个）
   - 详细释义
   - 记忆技巧
   - 常见搭配

3. 短语动词学习（3-5个）
   - 含义和例句
   - 学习提示

4. 实用句型分析（2-3个）
   - 句型结构分析
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
    
    def _get_zhihu_exam_prompt(self) -> str:
        """知乎应试学习风格提示词"""
        return """你是一位专业的英语考试辅导老师，擅长从真实视频中提炼对考试有用的语言知识点。

请根据提供的视频字幕，生成一篇适合在知乎发布的应试英语学习文章，要求：

【整体风格】
- 专业深度，逻辑清晰
- 适合深度阅读
- 使用Markdown格式

【内容要求】
1. 高级词汇深度解析（5-8个）
   - 详细释义
   - 常用搭配（至少5个）
   - 同义替换（至少3个）
   - 单词家族拓展
   - 记忆技巧
   - 考试应用场景

2. 长难句深度分析（3-5个）
   - 完整原文和翻译
   - 句子类型判断
   - 语法特征分析
   - 结构拆解（成分分析）
   - 学习感悟和考试要点
   - 仿写练习建议

3. 写作技巧总结（6-8条）
   - 词汇升级方法
   - 句式多样化技巧
   - 连接词使用策略
   - 避免中式英语的方法
   - 段落结构优化
   - 论证方法建议

4. 总结
   - 学习路径建议
   - 备考策略

【质量标准】
- 内容必须对考试有直接帮助
- 词汇选择要符合考试高频词（雅思/托福/四六级）
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
    
    def _call_ai_api(self, prompt: str) -> Optional[str]:
        """调用 AI API"""
        try:
            import requests as std_requests
            
            headers = {
                "Content-Type": "application/json",
            }
            
            if self._config.api_key:
                headers["Authorization"] = f"Bearer {self._config.api_key}"
            
            data = {
                "model": self._config.model,
                "messages": [
                    {"role": "system", "content": "你是一位专业的英语学习导师，擅长从真实视频中提炼有价值的语言知识点。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": self._config.temperature,
                "max_tokens": self._config.max_tokens,
            }
            
            response = std_requests.post(
                self._config.api_url,
                headers=headers,
                json=data,
                timeout=self._config.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"].strip()
            
            if "content" in result:
                return result["content"].strip()
            
            logger.warning(f"AI API 返回格式异常: {result}")
            return None
            
        except Exception as e:
            logger.error(f"调用 AI API 失败: {e}")
            return None
    
    def _evaluate_quality(self, content: str, subtitles: List[Dict[str, Any]]) -> int:
        """评估文案质量（1-10分）"""
        score = 0
        
        if len(content) > 500:
            score += 2
        elif len(content) > 200:
            score += 1
        
        sections = ["##", "###", "一、", "二、", "三、", "四、", "五、"]
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
        
        return min(score, 10)


def get_ai_writer() -> AIWriter:
    """获取 AI 文案生成器单例"""
    global _ai_writer_instance
    if _ai_writer_instance is None:
        _ai_writer_instance = AIWriter()
    return _ai_writer_instance


_ai_writer_instance: Optional[AIWriter] = None