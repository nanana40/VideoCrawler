from __future__ import annotations
"""core/subtitles/translator.py — SubtitleTranslator"""

"""
字幕处理模块

实现视频字幕的自动提取、翻译和嵌入功能。

功能特性：
    1. 字幕文件提取（外挂字幕 + ffmpeg 内嵌字幕）
    2. 字幕翻译（API + 本地）
    3. 字幕嵌入（ffmpeg）
    4. 自带字幕检测
    5. 双语/纯汉语字幕处理
"""

import os
import re
import subprocess
import json
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from utils.enums import LanguageType, VideoCategory, TaskStatus
from utils.logger import get_translate_logger
from utils.path_helper import get_ffmpeg_path, get_tmp_dir, get_finished_sub_dir, get_asr_model_dir
from utils.file_sort import get_file_sorter
from utils.resource_locks import FFMPEG_LOCK
from core.subtitles.models import SubtitleSentence


logger = get_translate_logger()


@dataclass


class SubtitleTranslator:
    """字幕翻译器（统一走 Gemini 直接翻译）

    已彻底移除 DeepL / Azure / 火山 / 腾讯 / googletrans / MyMemory / Lingva / LLM 等
    旧翻译链路，仅通过 TranslationEngine（内部封装 GeminiTranscriber.translate_texts）
    进行翻译。Gemini 不可用或调用失败时对应句子返回原文，并在日志提示检查 gemini.api_key。
    """

    def __init__(self) -> None:
        # 统一翻译引擎（仅 Gemini）
        try:
            from core.translation_engine import TranslationEngine
            self._translation_engine = TranslationEngine.from_config()
        except Exception as e:
            logger.error(f"[SubtitleTranslator] TranslationEngine 初始化失败: {e}")
            self._translation_engine = None

        self._translate_cache: Dict[str, str] = {}
        self._cache_max_size: int = 2000
        self._cache_hits: int = 0

    # ---------- 翻译缓存 ----------

    @staticmethod
    def _build_cache_key(text: str, source_lang: str, target_lang: str) -> str:
        return f"{source_lang}|{target_lang}|{text}"

    def _get_cached_translation(self, text, source_lang, target_lang):
        key = self._build_cache_key(text, source_lang, target_lang)
        if text and key in self._translate_cache:
            self._cache_hits += 1
            return self._translate_cache[key]
        return None

    def _set_cached_translation(self, text, source_lang, target_lang, translation) -> None:
        if not text:
            return
        key = self._build_cache_key(text, source_lang, target_lang)
        self._translate_cache[key] = translation
        if len(self._translate_cache) > self._cache_max_size:
            oldest = list(self._translate_cache.keys())[:self._cache_max_size // 2]
            for k in oldest:
                self._translate_cache.pop(k, None)

    # ---------- 翻译 ----------

    def translate_segments(
        self, segments, source_lang: str = "auto", target_lang: str = "zh-CN",
    ):
        """翻译片段列表（别名，统一走 translate_sentences）"""
        return self.translate_sentences(
            list(segments), source_lang=source_lang, target_lang=target_lang,
        )

    def translate_sentences(
        self,
        sentences: List[SubtitleSentence],
        source_lang: str = "auto",
        target_lang: str = "zh-CN",
    ) -> List[SubtitleSentence]:
        """翻译合并后的完整句子（统一走 Gemini 直接翻译）

        步骤：
            1. 缓存命中检查：相同原文直接使用缓存
            2. TranslationEngine.translate()（内部仅用 Gemini）批量翻译

        Gemini 不可用或调用失败时，对应句子返回原文。
        """
        if not sentences:
            return sentences

        # 缓存命中
        cache_hit_count = 0
        for s in sentences:
            cached = self._get_cached_translation(s.text, source_lang, target_lang)
            if cached is not None:
                s.translated_text = cached
                cache_hit_count += 1
        if cache_hit_count > 0:
            logger.info(f"[Gemini翻译] 缓存命中 {cache_hit_count} 句")

        uncached_indices = [i for i, s in enumerate(sentences) if s.translated_text is None]
        if not uncached_indices:
            logger.info("[Gemini翻译] 所有句子均命中缓存，翻译完成")
            return sentences

        if self._translation_engine is None:
            logger.error("[Gemini翻译] TranslationEngine 未初始化，无法翻译（返回原文）")
            return sentences

        uncached_texts = [sentences[i].text for i in uncached_indices]
        logger.info(
            f"[Gemini翻译] 翻译 {len(uncached_indices)} 句（缓存命中 {cache_hit_count} 句已跳过）"
        )

        results = self._translation_engine.translate(
            uncached_texts, source_lang=source_lang, target_lang=target_lang,
        )

        success_count = 0
        for i, sent_idx in enumerate(uncached_indices):
            translated = results[i] if i < len(results) else ""
            sentences[sent_idx].translated_text = translated
            if translated and translated.strip():
                success_count += 1
                if translated != sentences[sent_idx].text:
                    self._set_cached_translation(
                        sentences[sent_idx].text, source_lang, target_lang, translated,
                    )

        logger.info(
            f"[Gemini翻译] 完成: {success_count}/{len(uncached_indices)} 句成功"
            f"（缓存命中 {cache_hit_count} 句）"
        )
        return sentences
