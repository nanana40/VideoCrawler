"""
Gemini 多模态全托管引擎

直接把视频（本地文件或 YouTube URL）喂给 Gemini，一步完成 ASR + 翻译 + 时间戳对齐。
返回已带翻译和时间戳的字幕 dict 列表，可直接在 SubtitleProcessor 里转成 SubtitleSentence。

使用方式：
    config.yaml 里设置 gemini.enabled: true + gemini.api_key
    SubtitleProcessor.process_video() 会自动走这个路径，跳过本地 ASR + 翻译引擎链路。

免费层额度（2026-08）：
    Gemini 2.5 Flash / 3.6 Flash — 输入输出 token 全免费
    限制：15 RPM / 1,500 RPD / 1M TPM
    视频：≤20GB，≤2 小时（默认）/ ≤6 小时（低分辨率）
    YouTube URL：原生支持，Gemini 服务端下载处理
"""
# AUDIT-0015: 原 2166 行单类拆成 4 个 mixin（core/gemini/ 包），本文件仅为门面

from __future__ import annotations

import os
import time
from typing import List, Optional, Dict, Any

from utils.logger import get_translate_logger

# --- 从 gemini._helpers re-export 模块级辅助函数 ---
from .gemini._helpers import (
    _wrap_text,
    _is_429,
    _extract_retry_delay,
    _parse_duration,
    _apply_unit,
    _walk_for_retry_delay,
    _extract_exhausted_model,
    _today_end_epoch,
    _is_model_exhausted,
    _mark_model_exhausted,
    _is_quota_exhausted,
)

# --- 可选的免费图生图 provider ---
try:
    from core.image_provider import try_inpaint_translate as _try_inpaint
except Exception:  # pragma: no cover — import 失败不影响主流程
    _try_inpaint = None

# --- 导入 mixin（从 core/gemini 包）---
from .gemini import ImageMixin, JsonMixin, TranslateMixin, AsrMixin

logger = get_translate_logger()


# ============================================================
# 主类：多继承所有 mixin + 类常量 + 骨架方法
# ============================================================
class GeminiTranscriber(ImageMixin, JsonMixin, TranslateMixin, AsrMixin):
    """Gemini 全托管 ASR + 翻译 + 时间戳引擎"""
    MODEL_DEFAULT = "gemini-3-flash-preview"

    # 实测（2026-09-23 更新）纯音频输入 + generateContent ping：
    #   ✅ gemini-3-flash-preview       视频+音频都可用（唯一视频输入模型；今天 ping 稳定 OK）
    #   ⚠️ gemini-3.1-flash-lite       音频可用（今天 Google 对本 Key 返回 503，之前长期稳定）
    #   ⚠️ gemini-3.1-flash-lite-preview 音频可用（同上）
    #   ⚠️ gemini-3.7-flash            音频可用（同上）
    #   ⚠️ gemini-3.8-flash            新模型，暂未验证 audio modality（今天也 503）
    #   ❌ gemini-3.5/3.6-flash        响应 JSON 结构异常
    #   ❌ gemini-2.5/2.0 全系列       404 已下线
    #   ❌ gemini-pro-latest            429 配额耗尽
    # 顺序 = 按"文本 ping + modality 支持"双重优先级排序：
    MODEL_CHAIN = [
        "gemini-3-flash-preview",           # 首选：唯一支持 video + 今天唯一 ping OK
        "gemini-3.1-flash-lite",            # 降级：之前最稳定的音频模型
        "gemini-3.1-flash-lite-preview",    # 降级
        "gemini-3.7-flash",                 # 兜底
    ]

    # 每个模型最多重试次数（仅用于 503/连接错误 等瞬时故障；429 不做内部重试，直接降级）
    RETRIES_PER_MODEL = 2

    # 文件上传最大重试次数（网络抖动时恢复；SDK 内部 tenacity 已经消耗 N 次，
    # 外层需要比 UPLOAD_RETRIES 给足余量，因为 VPN RST 后每次 SDK 内部 retry 都会秒挂）
    UPLOAD_RETRIES = 5

    PROMPT_TEMPLATE = """你是一名专业的视频字幕处理专家。请对输入的**音频轨**（视频提取出的音轨）完成以下工作：

1. 语音识别（ASR）：逐句转写音频中的人声内容，保留完整时间戳
2. 翻译：将转写结果翻译成**简体中文**
3. 分句：按自然语义分句，每句中文翻译**不超过 18 个汉字**（硬上限），如需拆分长句请合理断句
4. 输出：严格按以下 JSON 数组格式输出，不要输出任何解释文本、不要加 markdown 代码块标记

时间戳格式：start_time 和 end_time 用**秒**（浮点数，如 12.345）

**⚠️ 输出要求（必须严格遵守）**：
- 原文语言：{source_lang}（如果是 auto 请自动识别）
- 目标语言：简体中文
- source_text = **原始语言的原文**（保持原语言，不要翻译成中文！）
- target_text = **简体中文译文**
- 每一条字幕必须同时包含 source_text 和 target_text，不能只有一个
- 原文是什么语言，source_text 就是什么语言，不要把原文也翻译成中文

示例（德语视频）：
```json
[
  {{"start_time": 0.0, "end_time": 3.5, "source_text": "Hallo Welt", "target_text": "你好世界"}},
  {{"start_time": 3.5, "end_time": 7.0, "source_text": "Ich liebe dich", "target_text": "我爱你"}}
]
```

如果原文是问句（?），翻译也应保留问句语气
数字、人名、专业术语必须准确翻译
跳过纯音乐/无人声段落
只输出 JSON 数组，不要输出任何其他内容"""

    PROOFREAD_PROMPT = """你是一名专业的视频字幕校对专家。请同时利用**视频画面中已烧录的字幕**和**视频音轨**进行三重审核：

## 你的输入
- 一个已烧录字幕的视频文件（底部/顶部会看到已有的字幕画面）
- 下方附了一段"当前字幕列表"（文本形式，便于你快速比对）

## 你的任务
1. **完整听音**：从头至尾重新听一遍视频，ASR 识别所有有台词的片段——不管画面上有没有字幕
2. **画面读字幕**：读取画面中已烧录的字幕文本和它们大致出现的时间段
3. **对比审核**，找出以下三类问题：
   - ✅ **缺漏**：有明确人声但画面上没有字幕的时间段（这是最关键的！）
   - ✅ **错配**：画面上的字幕时间戳和实际说话时间对不上
   - ✅ **翻译硬伤**：中文字幕和实际说的内容不符、明显机器翻译腔、人名/数字翻译错
4. **输出修正后的完整字幕列表**——不管原有字幕对不对，都输出你认为最准确的版本

## 校对原则
- 缺漏是最严重的问题，宁可"多加"也不要漏掉任何一句有人声的台词
- 时间戳精度到 0.1 秒即可，允许 ±0.5s 误差
- 每句中文翻译不超过 18 字（硬上限），长句合理拆分
- 跳过纯音乐、无人声、黑屏片段
- 如果"当前字幕列表"里某一句是对的，直接沿用即可

## 当前字幕列表（供你快速参考）
{existing_srt}

**⚠️ 输出要求（必须严格遵守）**：
- source_text = **原始语言的原文**（保持原语言，不要翻译成中文！）
- target_text = **简体中文译文**
- 每一条字幕必须同时包含 source_text 和 target_text，不能只有一个
- 原文是什么语言，source_text 就是什么语言

示例（德语视频）：
```json
[
  {{"start_time": 0.0, "end_time": 3.5, "source_text": "Hallo Welt", "target_text": "你好世界"}}
]
```

只输出 JSON 数组，不要 markdown 代码块、不要解释文字"""

    PROMPT_WITH_ASR_REF = """你是一名专业的字幕处理专家。请对输入的**音频轨**完成以下工作：

## 核心优势——下方附有本地 ASR 识别结果（faster-whisper，VAD 激进不容易漏，时间戳精度更高）
{asr_reference}

## 你的任务（对照 ASR 做翻译+分句，而非从零开始做 ASR）
1. **对照 ASR 结果听音轨**：听音频确认 ASR 每段的实际说话内容，纠正 ASR 可能的误识别
2. **翻译**：将每段源文翻译成**简体中文**
3. **分句**：按自然语义分句，每句中文翻译**不超过 18 个汉字**（硬上限）
4. **时间戳**：优先沿用 ASR 提供的时间戳（精度更高），允许 ±0.3s 微调
5. **缺漏检查**：
   - 如果 ASR 有某段但你听音没听到 → 保留 ASR（VAD 比你更激进）
   - 如果你听到了 ASR 没覆盖的人声 → **必须新增**这段（这是最关键的补漏！）
   - 宁可"多加"也不要漏掉任何一句有人声的台词

## 原文语言：{source_lang}（auto 请自行确认）
## 目标语言：简体中文

**⚠️ 输出要求（必须严格遵守）**：
- source_text = **原始语言的原文**（保持原语言，不要翻译成中文！）
- target_text = **简体中文译文**
- 每一条字幕必须同时包含 source_text 和 target_text，不能只有一个
- 原文是什么语言，source_text 就是什么语言，不要把原文也翻译成中文

示例（德语视频）：
```json
[
  {{"start_time": 0.0, "end_time": 3.5, "source_text": "Jeder Baum ist tot.", "target_text": "每棵树都死了"}},
  {{"start_time": 3.5, "end_time": 6.0, "source_text": "Der lebendige Teil ist winzig.", "target_text": "活的部分微乎其微"}}
]
```

只输出 JSON 数组，不要 markdown 代码块、不要解释文字"""

    PROOFREAD_WITH_ASR_REF = """你是一名专业的视频字幕校对专家。请同时利用**视频音轨**、**已烧录字幕画面**和**本地 ASR 参考**进行三重审核：

## 你的三重输入
1. 一个已烧录字幕的视频文件（底部/顶部会看到已有的字幕画面）
2. "当前字幕列表"（画面中烧录的字幕文本）
3. **"本地 ASR 参考"**（faster-whisper 独立识别结果，VAD 更激进，时间戳精度更高）

## 当前字幕列表（画面中已烧录）
{existing_srt}

## 本地 ASR 参考（更完整的时间戳覆盖，作为补漏依据）
{asr_reference}

## 你的任务
1. **完整听音**：从头至尾听一遍视频
2. **读取画面字幕**：对照"当前字幕列表"
3. **对照 ASR 参考**：检查 ASR 有但当前字幕漏掉的段落
4. **找出并修复三类问题**：
   - 🔴 **缺漏**：有明确人声但画面没字幕（优先对照 ASR 参考补！）
   - 🔴 **漏时段**：ASR 有覆盖但当前字幕没有的时间段
   - 🟡 **错配**：画面字幕时间戳和实际说话对不上
   - 🟡 **翻译硬伤**：中文和实际内容不符、机器翻译腔、人名/数字错

## 校对原则
- 缺漏是最严重的问题，**宁可多加也不要漏掉任何一句有人声的台词**
- 本地 ASR 参考里的段落 → 必须全部覆盖（除非确认是纯音乐）
- 时间戳精度到 0.1 秒，允许 ±0.5s 误差
- 每句中文翻译不超过 18 字（硬上限），长句合理拆分
- 如果"当前字幕列表"某句完全正确，直接沿用

**⚠️ 输出要求（必须严格遵守）**：
- source_text = **原始语言的原文**（保持原语言，不要翻译成中文！）
- target_text = **简体中文译文**
- 每一条字幕必须同时包含 source_text 和 target_text，不能只有一个
- 原文是什么语言，source_text 就是什么语言

示例（德语视频）：
```json
[
  {{"start_time": 0.0, "end_time": 3.5, "source_text": "Jeder Baum ist tot.", "target_text": "每棵树都死了"}},
  {{"start_time": 3.5, "end_time": 6.0, "source_text": "Der lebendige Teil ist winzig.", "target_text": "活的部分微乎其微"}}
]
```

只输出 JSON 数组，不要 markdown 代码块、不要解释文字"""

    # 多模态幻觉黑名单 — 训练数据中 YouTube/视频平台 UI 元素容易被误识别为封面文字
    _HALLUCINATION_BLOCKLIST = (
        "立即观看", "精彩内容", "探索更多", "视频预览", "点击播放", "点击订阅",
        "订阅", "点赞", "分享", "下载", "收藏", "关注", "评论", "播放列表",
        "加入列表", "稍后观看", "推荐", "观看更多", "限时优惠", "免费试看",
        "立即体验", "立即下载", "马上行动", "点击了解更多", "立即加入",
        "subscribe", "watch now", "watch more", "preview", "play now",
        "subscribe now", "like", "share", "subscribe to",
    )

    def __init__(self) -> None:
        cfg = self._load_config()
        self._enabled: bool = bool(cfg.get("enabled", False))
        self._api_key: str = str(cfg.get("api_key", "")).strip()
        self._model: str = str(cfg.get("model", self.MODEL_DEFAULT))
        self._proxy: str = str(cfg.get("proxy", "")).strip() or self._read_crawler_proxy()
        self._use_youtube_url: bool = bool(cfg.get("use_youtube_url", True))
        self._use_audio_only: bool = bool(cfg.get("use_audio_only", True))
        self._client = None
        self._file_ref = None

        # ---- 模型链：优先用 config 的 model_chain（用户在 GUI 勾选），没有回退到硬编码 ----
        raw_chain = cfg.get("model_chain")
        if isinstance(raw_chain, list) and raw_chain:
            self._model_chain: List[str] = [str(m) for m in raw_chain if m]
        else:
            # 旧配置兼容：用单 model 字段 + 默认链补齐
            self._model_chain = list(GeminiTranscriber.MODEL_CHAIN)
            if self._model and self._model not in self._model_chain:
                self._model_chain.insert(0, self._model)

        if self._enabled:
            mode = "纯音频" if self._use_audio_only else "视频+音频"
            logger.info(
                f"[Gemini] 全托管引擎已启用: model_chain={self._model_chain}, "
                f"proxy={'已配置' if self._proxy else '无'}, "
                f"use_youtube_url={self._use_youtube_url}, mode={mode}"
            )
        else:
            logger.info("[Gemini] 全托管引擎未启用")

    # ---------------------------------------------------------------
    # 配置读取
    # ---------------------------------------------------------------

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        try:
            from utils.config_loader import load_config
            cfg = load_config()
            return cfg.get("gemini", {})
        except Exception:
            return {}

    @staticmethod
    def _read_crawler_proxy() -> str:
        try:
            from utils.config_loader import load_config
            cfg = load_config()
            return str(cfg.get("crawler", {}).get("proxy", "")).strip()
        except Exception:
            return ""

    @property
    def is_available(self) -> bool:
        if not self._enabled:
            return False
        if not self._api_key:
            logger.error("[Gemini] api_key 未配置")
            return False
        return True

    # ---------------------------------------------------------------
    # 代理 + 客户端初始化
    # ---------------------------------------------------------------

    def _apply_proxy(self) -> None:
        if not self._proxy:
            return
        os.environ.setdefault("HTTPS_PROXY", self._proxy)
        os.environ.setdefault("HTTP_PROXY", self._proxy)
        os.environ.setdefault("ALL_PROXY", self._proxy)
        logger.info(f"[Gemini] 已设置代理: {self._proxy}")

    def _get_client(self):
        if self._client is not None:
            return self._client
        self._apply_proxy()
        try:
            import google.genai as genai
            from google.genai import types
            import httpx
        except ImportError:
            raise RuntimeError(
                "google-genai 未安装。运行: pip install google-genai"
            )
        # httpx timeout: connect 30s, read 600s (10min), write 60s
        # 视频/音频输入时 generate_content 可能需要 1-3 分钟服务端处理
        # 600s read 给足余量，不设无限避免极端网络故障时进程卡死
        client_args = {
            "timeout": httpx.Timeout(
                connect=30.0, read=600.0, write=60.0, pool=60.0
            ),
        }
        client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(client_args=client_args),
        )
        logger.info(
            f"[Gemini] SDK 客户端初始化成功 (model={self._model}, "
            f"httpx read_timeout=600s)"
        )
        self._client = client
        return client

    # ---------------------------------------------------------------
    # 连接池重建（VPN 重连 / 网络切换后必须调用）
    # ---------------------------------------------------------------

    def _reset_client(self):
        """关闭旧 httpx 连接池、重建新客户端

        VPN TUN 网卡切换节点/重连会强制 RST 所有已建立的 TCP 连接，
        但 httpx 连接池不知道这件事，里面的 socket 变成"僵尸"。
        所有后续请求都会秒挂 WinError 10054，必须重建客户端才能恢复。
        """
        if self._client is not None:
            try:
                self._client.close()
                logger.info("[Gemini] 已关闭旧 httpx 连接池")
            except Exception:
                pass
            self._client = None
        return self._get_client()

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        """判断是否为'连接类错误'（需要重建连接池才能恢复）

        与 503/429 等服务端错误不同——后者连接本身没问题，
        只是服务端暂时不可用；连接类错误意味着 TCP 层已经断了。
        """
        # 关键词匹配（覆盖 httpx / httpcore / socket / Windows error）
        CONNECTION_KEYWORDS = (
            "WinError 10054", "WinError 10053", "WinError 10049",
            "WinError 10060",
            "Connection reset", "Connection aborted", "Connection refused",
            "ConnectionResetError", "ConnectionAbortedError",
            "RemoteDisconnected", "BrokenPipeError", "ProtocolError",
            "ConnectError", "ConnectTimeout", "TransportError", "ReadError",
            "ECONNRESET", "ECONNABORTED", "EPIPE",
        )
        msg = str(exc)
        if any(kw in msg for kw in CONNECTION_KEYWORDS):
            return True
        # 也检查 exception 类型（更精确）
        try:
            import httpx
            if isinstance(exc, (
                httpx.ConnectError, httpx.ConnectTimeout,
                httpx.WriteError, httpx.ReadError, httpx.PoolTimeout,
            )):
                return True
        except ImportError:
            pass
        try:
            import httpcore
            if isinstance(exc, (
                httpcore.ConnectError, httpcore.ReadError,
                httpcore.WriteError, httpcore.PoolTimeout,
            )):
                return True
        except ImportError:
            pass
        # OSError 是所有 socket 错误的基类
        if isinstance(exc, OSError):
            return True
        return False

    # ---------------------------------------------------------------
    # Prompt 日志（调 AI 前把提示词打印出来，方便排查双语等问题）
    # ---------------------------------------------------------------

    _PROMPT_LOG_MAX = 4000  # 单条 prompt 最长打印 4000 字符，过长截断

    def _log_prompt(self, label: str, prompt: Any) -> None:
        """把 prompt 打到日志里。label 用来区分场景（ASR/翻译/封面/校对）。

        截断策略: 完整 prompt 太冗长影响排查效率，保留头尾各一半 + 中间省略号。
        """
        if prompt is None:
            logger.info(f"[Gemini 📝 Prompt—{label}] (空)")
            return
        text = str(prompt)
        max_len = self._PROMPT_LOG_MAX
        if len(text) <= max_len:
            logger.info(f"[Gemini 📝 Prompt—{label}] ({len(text)} chars)\n{text}")
        else:
            half = max_len // 2
            logger.info(
                f"[Gemini 📝 Prompt—{label}] ({len(text)} chars, 截断至 {max_len})\n"
                f"----- HEAD ({half} chars) -----\n{text[:half]}\n"
                f"... ({len(text) - max_len} chars omitted) ...\n"
                f"----- TAIL ({half} chars) -----\n{text[-half:]}"
            )


_transcriber: Optional[GeminiTranscriber] = None


def get_gemini_transcriber() -> GeminiTranscriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = GeminiTranscriber()
    return _transcriber


__all__ = ['GeminiTranscriber', 'get_gemini_transcriber']
