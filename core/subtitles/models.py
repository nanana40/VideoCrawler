"""core/subtitles/models.py — SubtitleSegment, SubtitleSentence, SubtitleResult

字幕处理模块

实现视频字幕的自动提取、翻译和嵌入功能。

功能特性：
    1. 字幕文件提取（外挂字幕 + ffmpeg 内嵌字幕）
    2. 字幕翻译（API + 本地）
    3. 字幕嵌入（ffmpeg）
    4. 自带字幕检测
    5. 双语/纯汉语字幕处理
"""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass

from utils.logger import get_translate_logger


logger = get_translate_logger()


@dataclass


class SubtitleSegment:
    """字幕片段"""
    start_time: float
    end_time: float
    text: str
    translated_text: Optional[str] = None


@dataclass
class SubtitleSentence:
    """字幕完整句子（由多个相邻片段合并而成）

    一个句子对应一个完整的语义单元（以句号/问号/感叹号结尾），
    可能由 1~N 个原始 SubtitleSegment 合并而来。

    Attributes:
        start_time: 句子起始时间（= 第一个片段的 start_time）
        end_time: 句子结束时间（= 最后一个片段的 end_time）
        text: 合并后的完整原文
        translated_text: 整句翻译结果
        source_segments: 构成该句子的原始片段引用列表
    """
    start_time: float
    end_time: float
    text: str
    translated_text: Optional[str] = None
    source_segments: List[SubtitleSegment] = None


@dataclass
class SubtitleResult:
    """字幕处理结果"""
    video_id: str
    video_path: str
    success: bool
    subtitle_path: Optional[str] = None
    embedded_video_path: Optional[str] = None
    error_message: Optional[str] = None
    has_original_subtitle: bool = False
