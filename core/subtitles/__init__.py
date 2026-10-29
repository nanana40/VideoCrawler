from __future__ import annotations
"""
core/subtitles/ — 字幕处理子系统（AUDIT-0016 拆分自 core/subtitle_processor.py）

原 4075 行单文件拆为 8 个职责单一的子模块：
  models.py          — SubtitleSegment / SubtitleSentence / SubtitleResult 数据模型
  sentence_merger.py — SentenceMerger 句子合并与切分
  asr.py             — SpeechRecognizer 语音识别（whisper）
  translator.py      — SubtitleTranslator 翻译
  writer.py          — SRTWriter SRT 字幕写入
  quality_gate.py    — SubtitleQualityGate 质量门控
  embedder.py        — VideoSubtitleEmbedder 字幕烧录
  processor.py       — SubtitleProcessor 编排器

外部 import 路径保持不变：from core.subtitle_processor import X
（subtitle_processor.py 现为 re-export 门面）
"""

# Re-export all classes from sub-modules
from .models import SubtitleSegment, SubtitleSentence, SubtitleResult
from .sentence_merger import SentenceMerger
from .asr import SpeechRecognizer
from .translator import SubtitleTranslator
from .writer import SRTWriter
from .quality_gate import SubtitleQualityGate
from .embedder import VideoSubtitleEmbedder
from .processor import SubtitleProcessor, process_video_subtitle

__all__ = [
    "SubtitleSegment", "SubtitleSentence", "SubtitleResult",
    "SentenceMerger", "SpeechRecognizer", "SubtitleTranslator",
    "SRTWriter", "SubtitleQualityGate", "VideoSubtitleEmbedder",
    "SubtitleProcessor", "process_video_subtitle",
]
