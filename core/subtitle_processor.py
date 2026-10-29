"""
core/subtitle_processor.py — AUDIT-0016 重构为门面

原 4075 行单文件已拆为 core/subtitles/ 子包，
本文件仅做 re-export，保持外部 import 路径兼容。

新代码建议直接从 core.subtitles 导入：
  from core.subtitles import SubtitleProcessor
"""

from core.subtitles import *  # noqa: F401,F403
from core.subtitles import (
    SubtitleSegment, SubtitleSentence, SubtitleResult,
    SentenceMerger, SpeechRecognizer, SubtitleTranslator,
    SRTWriter, SubtitleQualityGate, VideoSubtitleEmbedder,
    SubtitleProcessor,
)

# 为向后兼容显式导出全部公共符号
__all__ = [
    "SubtitleSegment", "SubtitleSentence", "SubtitleResult",
    "SentenceMerger", "SpeechRecognizer", "SubtitleTranslator",
    "SRTWriter", "SubtitleQualityGate", "VideoSubtitleEmbedder",
    "SubtitleProcessor",
]

# 便捷函数（原模块级快捷入口）
from core.subtitles.processor import process_video_subtitle  # noqa: E402
