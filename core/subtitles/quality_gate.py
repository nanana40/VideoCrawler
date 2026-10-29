from __future__ import annotations
"""core/subtitles/quality_gate.py — SubtitleQualityGate"""

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


class SubtitleQualityGate:
    """字幕质量关卡（仅保留文本质量过滤）

    已彻底移除旧的 LLM 对齐校对 / DeepL 兜底翻译等非 Gemini 校对方案，
    只保留「垃圾翻译过滤」（回显原文 / 过短 / 无中文字符）。
    字幕翻译与校对统一走 Gemini：翻译在 translation_engine（Gemini），
    校对在 gemini_engine.proofread_subtitles。
    """

    def __init__(self) -> None:
        pass

    def run(
        self,
        sentences: List[SubtitleSentence],
        source_lang: str = "auto",
        target_lang: str = "zh-CN",
        enabled: bool = True,
    ) -> List[SubtitleSentence]:
        """执行文本质量过滤

        Args:
            sentences: 待校验的句子列表
            source_lang: 源语言代码（保留签名，当前仅用于日志）
            target_lang: 目标语言代码
            enabled: 总开关。False 则原样透传上游结果。

        Returns:
            过滤后的句子列表（translated_text 可能被置 None）
        """
        if not sentences:
            return sentences
        if not enabled:
            logger.info(f"字幕质量关卡: 全部跳过（信任上游产出）— {len(sentences)} 句原样透传")
            return sentences

        garbage_count = self._filter_garbage(sentences)
        if garbage_count > 0:
            logger.warning(f"字幕质量关卡（垃圾过滤）清理 {garbage_count} 句无效翻译")
        final_cn = sum(1 for s in sentences if s.translated_text)
        logger.info(f"字幕质量关卡完成: {len(sentences)} 句, 有效中文翻译 {final_cn} 句")
        return sentences

    # ========== 垃圾翻译过滤 ==========

    @staticmethod
    def _filter_garbage(sentences: List[SubtitleSentence]) -> int:
        """过滤垃圾翻译：回显原文、过短、无中文字符等"""
        count = 0
        for s in sentences:
            t = (s.translated_text or "").strip()
            o = s.text.strip()
            if not t or len(t) < 2:
                if s.translated_text:
                    s.translated_text = None
                    count += 1
                continue
            if t == o:
                s.translated_text = None
                count += 1
                continue
            cn = sum(1 for c in t if '一' <= c <= '鿿')
            es_like = sum(
                1 for c in t
                if 'a' <= c.lower() <= 'z' or c in 'ñáéíóúü¿¡'
            )
            # 翻译是中文但完全没有中文字符 → 垃圾
            if cn == 0 and es_like > 3 and '一' <= o[0] <= '鿿':
                s.translated_text = None
                count += 1
        return count
        return None
