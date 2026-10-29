"""
翻译引擎模块（统一改用 Gemini 直接翻译）

历史说明：
    本模块曾实现 DeepL > Azure > 火山(Volc) > 腾讯 > LLM 兜底 的多引擎故障转移链，
    以及 googletrans / MyMemory / Lingva / Google 等兜底方案。
    现已按需求彻底移除（视频元数据与字幕翻译一律直接走 Gemini）。

当前职责：
    1. 提供 `merge_texts` / `split_translated` 批量字幕行打包/拆回工具（无副作用）。
    2. 提供 `TranslationEngine` 统一入口，内部直接调用 GeminiTranscriber.translate_texts。
       Gemini 不可用时返回原文，并在日志提示检查 gemini.api_key 配置。
"""

from typing import Dict, Any

from utils.logger import get_translate_logger

logger = get_translate_logger()

SPLIT_MARKER = "|||SPLIT|||"


# =====================================================================
# 批量文本合并 / 拆分工具（Gemini 翻译复用）
# =====================================================================

def merge_texts(texts: list, max_chars: int) -> list:
    """将多条短文本按字符上限打包，用 SPLIT_MARKER 拼接

    Args:
        texts: 待合并的原文列表
        max_chars: 单批最大字符数（含 SPLIT_MARKER 开销）

    Returns:
        合并后的批次列表，每批是一个拼接好的长字符串
    """
    batches = []
    cur_parts: list = []
    cur_len = 0
    sep_len = len(SPLIT_MARKER)

    for t in texts:
        if len(t) >= max_chars:
            if cur_parts:
                batches.append(SPLIT_MARKER.join(cur_parts))
                cur_parts = []
                cur_len = 0
            batches.append(t)
            continue

        need = len(t) + (sep_len if cur_parts else 0)
        if cur_len + need > max_chars:
            if cur_parts:
                batches.append(SPLIT_MARKER.join(cur_parts))
            cur_parts = [t]
            cur_len = len(t)
        else:
            cur_parts.append(t)
            cur_len += need

    if cur_parts:
        batches.append(SPLIT_MARKER.join(cur_parts))

    return batches


def split_translated(batch: str, expected_count: int) -> list:
    """将合并翻译后的长文本精准拆回 N 条（按 SPLIT_MARKER 拆分）"""
    if not batch:
        return [""] * expected_count

    if SPLIT_MARKER in batch:
        parts = batch.split(SPLIT_MARKER)
        parts = [p.strip() for p in parts]
        if len(parts) >= expected_count:
            return parts[:expected_count]
        while len(parts) < expected_count:
            parts.append("")
        return parts

    # 无 SPLIT_MARKER：均匀切分兜底
    total = len(batch)
    per = total // expected_count if expected_count else total
    result = []
    for i in range(expected_count):
        start = i * per
        end = start + per if i < expected_count - 1 else total
        result.append(batch[start:end].strip())
    return result


# =====================================================================
# TranslationEngine —— 统一翻译入口（仅 Gemini）
# =====================================================================

class TranslationEngine:
    """翻译引擎：统一走 Gemini 直接翻译

    使用：
        engine = TranslationEngine.from_config()
        results = engine.translate(["Hello", "World"], source_lang="en", target_lang="zh-CN")
    """

    def __init__(self, gemini_transcriber=None):
        self._gemini = gemini_transcriber

    # ---------- 构造：从 config.yaml 加载 ----------

    @classmethod
    def from_config(cls) -> "TranslationEngine":
        try:
            from core.gemini_engine import get_gemini_transcriber
            transcriber = get_gemini_transcriber()
        except Exception as e:
            logger.error(f"[TranslationEngine] Gemini 初始化失败: {e}")
            transcriber = None

        if transcriber is not None:
            if transcriber.is_available:
                logger.info("[TranslationEngine] 已启用 Gemini 直接翻译")
            else:
                logger.warning(
                    "[TranslationEngine] Gemini 未启用或 api_key 未配置，"
                    "翻译将返回原文，请在 config.yaml 配置 gemini.api_key"
                )

        return cls(gemini_transcriber=transcriber)

    # ---------- 翻译入口 ----------

    def translate(
        self,
        texts,
        source_lang: str = "auto",
        target_lang: str = "zh-CN",
    ):
        """翻译一批文本（仅 Gemini）

        Args:
            texts: 原文列表
            source_lang: 源语言代码
            target_lang: 目标语言代码

        Returns:
            译文列表（长度与 texts 相同）。Gemini 不可用或失败时对应项返回原文。
        """
        texts = list(texts or [])
        if not texts:
            return []

        if self._gemini is None or not self._gemini.is_available:
            logger.error("[TranslationEngine] Gemini 不可用，翻译返回原文，请检查 gemini.api_key")
            return list(texts)

        try:
            return self._gemini.translate_texts(
                texts, source_lang=source_lang, target_lang=target_lang
            )
        except Exception as e:
            logger.error(f"[TranslationEngine] Gemini 翻译异常，返回原文: {e}")
            return list(texts)

    # ---------- 诊断 ----------

    def get_status(self) -> Dict[str, Any]:
        """返回翻译引擎实时状态（供日志/诊断）"""
        available = self._gemini is not None and self._gemini.is_available
        return {
            "Gemini": {
                "enabled": bool(self._gemini and getattr(self._gemini, "_enabled", False)),
                "available": available,
                "api_key_configured": bool(self._gemini and self._gemini._api_key),
            }
        }