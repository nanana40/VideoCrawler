from __future__ import annotations
"""core/subtitles/writer.py — SRTWriter"""

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
from core.subtitles.models import SubtitleSegment, SubtitleSentence


logger = get_translate_logger()


@dataclass


class SRTWriter:
    """
    SRT字幕写入器
    
    将字幕片段写入 SRT 格式文件。
    """
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """将秒转换为 SRT 时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        msecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{msecs:03d}"
    
    @staticmethod
    def write(
        segments: List[SubtitleSegment],
        output_path: str,
        bilingual: bool = True
    ) -> str:
        """
        写入 SRT 文件
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
            bilingual: 是否写入双语字幕
            
        Returns:
            输出文件路径
        """
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, 1):
                start = SRTWriter._format_time(segment.start_time)
                end = SRTWriter._format_time(segment.end_time)
                
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                
                if bilingual and segment.translated_text:
                    f.write(f"{segment.text}\n")
                    f.write(f"{segment.translated_text}\n")
                elif segment.translated_text:
                    f.write(f"{segment.translated_text}\n")
                else:
                    f.write(f"{segment.text}\n")
                
                f.write("\n")
        
        logger.info(f"SRT 文件已写入: {output_path}")
        return output_path

    @staticmethod
    def _wrap_cjk(text: str, max_per_line: int = 18, hard_limit: int = 22) -> str:
        """CJK 文本按字符数自动换行，每行 18 字左右，绝不超过 hard_limit

        Args:
            text: 原始文本
            max_per_line: 理想每行最大字符数（默认 18）
            hard_limit: 硬上限（默认 22）

        Returns:
            带换行的文本
        """
        if not text or len(text) <= max_per_line:
            return text
        lines = []
        i = 0
        n = len(text)
        while i < n:
            # 剩余文本
            remaining = text[i:]
            if len(remaining) <= max_per_line:
                lines.append(remaining.strip())
                break
            # 理想位置
            ideal_end = i + max_per_line
            # 在 [ideal_end - hard_limit + max_per_line, ideal_end] 范围内找标点断点
            search_start = max(ideal_end - (hard_limit - max_per_line), i + 1)
            chunk = text[search_start:ideal_end + 1]
            cut_offset = -1
            # 优先在理想位置之前找标点（更早断，不超过 max_per_line 太多）
            for sep in ["。", "！", "？", "，", "；", "：", ",", ".", "!", "?", ";"]:
                try:
                    pos = chunk.rindex(sep)
                    if pos >= 0:
                        cut_offset = pos + 1
                        break
                except ValueError:
                    continue
            if cut_offset < 0:
                # 无标点，硬切 max_per_line（不超 hard_limit）
                chunk_end = min(i + hard_limit, n)
                # 如果连这个 chunk 都超过 hard_limit，硬切到 hard_limit
                actual_end = i + min(max_per_line, hard_limit)
                # 如果硬切位置刚好卡在字中间，再往前退一点找最近的空格
                lines.append(text[i:actual_end].strip())
                i = actual_end
            else:
                cut_abs = search_start + cut_offset
                lines.append(text[i:cut_abs].strip())
                i = cut_abs
        return "\n".join(lines)

    @staticmethod
    def _translate_is_garbage(trans: str, original: str) -> bool:
        """判断翻译是否无效（回显原文、过短、全是标点等）"""
        if not trans or len(trans.strip()) < 2:
            return True
        t = trans.strip()
        o = original.strip()
        if t == o:
            return True
        # 中文翻译必须含中文字符
        if any('\u4e00' <= c <= '\u9fff' for c in o):
            pass
        # 简单检查：如果原文是西语，但"翻译"里中文字符很少
        es_chars = sum(1 for c in t if 'a' <= c.lower() <= 'z' or c in 'ñáéíóúü¿¡')
        cn_chars = sum(1 for c in t if '\u4e00' <= c <= '\u9fff')
        if o and cn_chars > 0 and es_chars > 0:
            # 混合文本没问题
            return False
        if cn_chars == 0 and '\u4e00' <= o[0] <= '\u9fff':
            return True
        return False

    @staticmethod
    def write_sentences(
        sentences: List[SubtitleSentence],
        output_path: str,
        bilingual: bool = True
    ) -> str:
        """按完整句子写入 SRT 文件（每次显示一句完整句子）

        合并后的句子作为一条字幕显示，时间轴覆盖整句，
        避免 YouTube 原始分段在句子中间切换显示。
        自动对 CJK 文本做换行，防止单行过长溢出字幕区域。
        翻译质量校验：回显原文 / 过短 / 无中文字符 → 跳过翻译行。
        """
        written_cn = 0
        skipped_cn = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for i, sentence in enumerate(sentences, 1):
                start = SRTWriter._format_time(sentence.start_time)
                end = SRTWriter._format_time(sentence.end_time)

                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")

                orig_text = sentence.text.strip()
                trans_text = (sentence.translated_text or "").strip()

                trans_garbage = SRTWriter._translate_is_garbage(trans_text, orig_text)

                if bilingual and trans_text and not trans_garbage:
                    f.write(f"{orig_text}\n")
                    f.write(f"{SRTWriter._wrap_cjk(trans_text)}\n")
                    written_cn += 1
                else:
                    if trans_text and trans_garbage:
                        skipped_cn += 1
                    f.write(f"{SRTWriter._wrap_cjk(orig_text, 36)}\n")

                f.write("\n")

        logger.info(
            f"句子级 SRT 文件已写入: {output_path}（共 {len(sentences)} 句，"
            f"含中文翻译 {written_cn}，跳过垃圾翻译 {skipped_cn}）"
        )
        return output_path
