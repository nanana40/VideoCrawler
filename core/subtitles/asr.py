from __future__ import annotations
"""core/subtitles/asr.py — SpeechRecognizer"""

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
from core.subtitles.models import SubtitleSegment


logger = get_translate_logger()


@dataclass


class SpeechRecognizer:
    """
    语音识别器（ffmpeg 字幕提取 + faster-whisper ASR 回退）

    三级字幕提取策略：
        1. 读取视频同目录外挂字幕文件（yt-dlp 下载的 .srt/.vtt）
        2. 通过 ffmpeg 提取视频内嵌字幕轨道
        3. faster-whisper 本地 ASR 语音识别（当无可用字幕时的回退方案）
           使用本地 small 模型，无需网络，支持 99 种语言
    """

    # 类级模型缓存（避免重复加载模型，多个实例共享）
    _whisper_model: Optional[Any] = None
    _whisper_model_loaded: bool = False
    _whisper_load_error: Optional[str] = None

    def __init__(self) -> None:
        """初始化语音识别器"""
        self._ffmpeg_path = str(get_ffmpeg_path())
        self._ffprobe_path: Optional[str] = None
        self._ffmpeg_available: Optional[bool] = None
        self._force_asr: bool = self._read_force_asr()
        logger.info(
            f"语音识别器初始化完成（ffmpeg + faster-whisper 模式"
            f"{'，force_asr=ON（跳过YouTube字幕）' if self._force_asr else ''}）"
        )

    def _read_force_asr(self) -> bool:
        try:
            from utils.config_loader import load_config
            cfg = load_config()
            return bool(cfg.get("subtitle", {}).get("force_asr", False))
        except Exception:
            return False
    
    def _check_ffmpeg(self) -> bool:
        """
        检查 ffmpeg 是否可用（仅检查一次）
        
        Returns:
            ffmpeg 是否可用
        """
        if self._ffmpeg_available is not None:
            return self._ffmpeg_available
        
        ffprobe_path = self._ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
        if os.path.exists(ffprobe_path):
            self._ffprobe_path = ffprobe_path
            self._ffmpeg_available = True
            logger.info(f"ffprobe 可用: {ffprobe_path}")
            return True
        
        try:
            subprocess.run(
                ["ffprobe", "-version"],
                capture_output=True,
                timeout=5
            )
            self._ffprobe_path = "ffprobe"
            self._ffmpeg_available = True
            logger.info("系统 ffprobe 可用")
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        if os.path.exists(self._ffmpeg_path):
            self._ffprobe_path = ffprobe_path
            self._ffmpeg_available = True
            logger.info(f"ffprobe 可用: {ffprobe_path}")
            return True

        self._ffmpeg_available = False
        logger.warning("ffprobe/ffmpeg 不可用，将仅尝试外挂字幕文件")
        return False

    # 注：_get_video_duration 在本类稍后（约 :2603）有完整实现，此处的早期版本是死代码，已删除。

    def _compute_segments_coverage(
        self, segments: List, video_path: str
    ) -> float:
        """
        计算字幕覆盖率：字幕段累计覆盖时长 / 视频总时长
        返回 0.0 ~ 1.0，失败或无有效信息返回 1.0（视为有效，避免误降级）
        """
        if not segments:
            return 0.0
        video_dur = self._get_video_duration(video_path)
        if video_dur <= 1.0:  # 视频时长获取失败或太短
            return 1.0
        # 去重叠累计覆盖时长（简单合并重叠/相邻区间）
        intervals = sorted(
            [(max(0.0, float(s.start_time)), max(0.0, float(s.end_time)))
             for s in segments if hasattr(s, "start_time") and hasattr(s, "end_time")]
        )
        if not intervals:
            return 0.0
        merged = [list(intervals[0])]
        for start, end in intervals[1:]:
            prev_start, prev_end = merged[-1]
            # 间隔 < 200ms 视为连续（避免小间隙导致覆盖率被低估）
            if start <= prev_end + 0.2:
                merged[-1][1] = max(prev_end, end)
            else:
                merged.append([start, end])
        covered = sum(max(0.0, e - s) for s, e in merged)
        ratio = min(1.0, covered / video_dur) if video_dur > 0 else 0.0
        logger.info(
            f"字幕覆盖率检查: 覆盖={covered:.1f}s / 总时长={video_dur:.1f}s = {ratio:.1%}"
        )
        return ratio

    def _check_video_ready(self, video_path: str) -> Tuple[bool, str]:
        """
        预检查视频文件是否可用于字幕提取
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            (是否就绪, 错误信息)
        """
        if not video_path:
            return False, "视频路径为空"
        
        if not os.path.exists(video_path):
            return False, f"视频文件不存在: {video_path}"
        
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            return False, f"视频文件为空: {video_path}"
        
        logger.debug(f"视频文件检查通过: {video_path} ({file_size} bytes)")
        return True, ""
    
    def _extract_embedded_subtitles(
        self,
        video_path: str,
        language: Optional[str] = None
    ) -> List[SubtitleSegment]:
        """
        通过 ffmpeg 提取视频内嵌字幕轨道
        
        Args:
            video_path: 视频文件路径
            language: 语言代码
            
        Returns:
            字幕片段列表
        """
        if not self._check_ffmpeg():
            logger.info("ffprobe 不可用，跳过内嵌字幕提取")
            return []
        
        logger.info("尝试通过 ffmpeg 提取内嵌字幕轨道...")
        
        try:
            assert self._ffprobe_path is not None
            cmd = [
                self._ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "s",
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace", 
                timeout=10
            )
            
            import json as _json
            streams = _json.loads(result.stdout) if result.stdout else {}
            subtitle_streams = streams.get("streams", [])
            
            if not subtitle_streams:
                logger.info("视频无内嵌字幕轨道")
                return []
            
            logger.info(f"检测到 {len(subtitle_streams)} 条内嵌字幕轨道")
            
            srt_content = self._extract_subtitle_stream(video_path, len(subtitle_streams))
            if not srt_content:
                return []
            
            segments = self._parse_srt_content(srt_content)
            logger.info(f"内嵌字幕提取成功，共 {len(segments)} 个片段")
            return segments
            
        except Exception as e:
            logger.warning(f"ffmpeg 提取内嵌字幕失败: {e}")
            return []
    
    def _extract_subtitle_stream(
        self,
        video_path: str,
        stream_count: int
    ) -> str:
        """
        使用 ffmpeg 提取字幕轨道为 SRT 格式文本
        
        Args:
            video_path: 视频文件路径
            stream_count: 字幕轨道数量
            
        Returns:
            SRT 格式文本内容
        """
        codecs_to_try = ["srt", "subrip", "webvtt"]
        
        for stream_idx in range(stream_count):
            for codec in codecs_to_try:
                try:
                    cmd = [
                        self._ffmpeg_path,
                        "-i", video_path,
                        "-map", f"0:s:{stream_idx}",
                        "-vn",
                        "-c:s", codec,
                        "-f", "srt" if codec != "webvtt" else "webvtt",
                        "-"
                    ]

                    with FFMPEG_LOCK:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True, encoding="utf-8", errors="replace", 
                            timeout=30
                        )
                    
                    output_text = result.stdout.strip()
                    if output_text and len(output_text) > 20:
                        logger.info(
                            f"成功提取第 {stream_idx} 条字幕轨道"
                            f"（codec={codec}），长度 {len(output_text)}"
                        )
                        return output_text
                        
                except subprocess.TimeoutExpired:
                    logger.warning(f"提取第 {stream_idx} 条字幕轨道（codec={codec}）超时")
                    continue
                except Exception as e:
                    logger.warning(
                        f"提取第 {stream_idx} 条字幕轨道（codec={codec}）失败: {e}"
                    )
                    continue
        
        return ""
    
    def _parse_srt_content(self, srt_text: str) -> List[SubtitleSegment]:
        """
        解析字幕文本为字幕片段列表（兼容 SRT / VTT 格式）
        
        Args:
            srt_text: 字幕文本（SRT 或 VTT 格式）
            
        Returns:
            字幕片段列表
        """
        segments: List[SubtitleSegment] = []
        
        try:
            normalized = srt_text.replace("\r\n", "\n").replace("\r", "\n")
            
            if normalized.lstrip().startswith("WEBVTT"):
                logger.debug("检测到 VTT 格式字幕，使用 VTT 解析器")
                return self._parse_vtt_content(normalized)
            
            segments = self._parse_srt_format(normalized)
                    
        except Exception as e:
            logger.warning(f"字幕文本解析异常: {e}")
        
        return segments
    
    def _parse_srt_format(self, normalized: str) -> List[SubtitleSegment]:
        """
        解析 SRT 格式文本
        
        Args:
            normalized: 已归一化换行符的 SRT 文本
            
        Returns:
            字幕片段列表
        """
        import re
        
        segments: List[SubtitleSegment] = []
        
        pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2})[,.](\d{3}) --> (\d{2}:\d{2}:\d{2})[,.](\d{3})\n(.+?)\n\n"
        matches = re.findall(pattern, normalized, re.DOTALL)
        
        for match in matches:
            start_str = f"{match[1]},{match[2]}"
            end_str = f"{match[3]},{match[4]}"
            text = match[5].strip()
            
            start_time = self._srt_time_to_seconds(start_str)
            end_time = self._srt_time_to_seconds(end_str)
            
            if text:
                segments.append(SubtitleSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text=text
                ))
        
        if not segments:
            lines = normalized.strip().split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.isdigit():
                    i += 1
                    if i < len(lines):
                        time_line = lines[i].strip()
                        time_match = re.match(
                            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
                            time_line
                        )
                        if time_match:
                            start_h, start_m, start_s, start_ms = (
                                int(time_match.group(1)), int(time_match.group(2)),
                                int(time_match.group(3)), int(time_match.group(4))
                            )
                            end_h, end_m, end_s, end_ms = (
                                int(time_match.group(5)), int(time_match.group(6)),
                                int(time_match.group(7)), int(time_match.group(8))
                            )
                            start_time = (start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0)
                            end_time = (end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0)
                            
                            i += 1
                            text_lines = []
                            while i < len(lines) and lines[i].strip():
                                text_lines.append(lines[i].strip())
                                i += 1
                            
                            text = " ".join(text_lines)
                            if text:
                                segments.append(SubtitleSegment(
                                    start_time=start_time,
                                    end_time=end_time,
                                    text=text
                                ))
                i += 1
        
        return segments
    
    def _parse_vtt_content(self, normalized: str) -> List[SubtitleSegment]:
        """
        解析 VTT 格式文本（支持 YouTube 渐进式自动字幕）

        YouTube 自动生成的 VTT 字幕使用"渐进式"显示：
            - 每个时间段包含两行：旧行（继承上一帧）+ 新行（新增词）
            - 存在大量"过渡帧"（持续 0.01 秒），只有继承行
            - 如果直接合并所有行，会导致大量重复文本

        本方法检测渐进式模式并正确提取增量文本：
            - 渐进式模式（有 align:start position:0% 标记）：
              只取每个时间段的新增行（最后一行），跳过过渡帧
            - 传统模式：按原逻辑解析

        Args:
            normalized: 已归一化换行符的 VTT 文本

        Returns:
            字幕片段列表
        """
        import re

        segments: List[SubtitleSegment] = []

        lines = normalized.strip().split("\n")

        start_idx = 0
        for idx, line in enumerate(lines):
            if line.strip().startswith("WEBVTT"):
                start_idx = idx + 1
                break

        timestamp_pattern = re.compile(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
        )

        # 检测是否为 YouTube 渐进式自动字幕
        is_progressive = "align:start" in normalized and "position:0%" in normalized

        if is_progressive:
            segments = self._parse_progressive_vtt(lines, start_idx, timestamp_pattern)
        else:
            segments = self._parse_traditional_vtt(lines, start_idx, timestamp_pattern)

        logger.info(f"VTT 解析完成，共 {len(segments)} 个字幕片段（渐进式: {is_progressive}）")
        return segments

    def _parse_progressive_vtt(
        self,
        lines: List[str],
        start_idx: int,
        timestamp_pattern: re.Pattern
    ) -> List[SubtitleSegment]:
        """解析 YouTube 渐进式自动字幕

        渐进式字幕每个时间段有两行文本：
            行1 = 继承行（上一帧的新增行）
            行2 = 新增行（本帧新增的词，带词级时间戳）

        过渡帧（持续 < 0.1 秒）只有继承行 + 空行，需跳过。

        本方法只提取每个非过渡帧的"新增行"（最后一行），
        得到干净的增量文本，避免重复。

        Args:
            lines: VTT 文本行列表
            start_idx: 开始解析的行索引
            timestamp_pattern: 时间戳正则

        Returns:
            字幕片段列表（每个片段为增量文本）
        """
        segments: List[SubtitleSegment] = []

        idx = start_idx
        while idx < len(lines):
            line = lines[idx].strip()

            time_match = timestamp_pattern.match(line)
            if not time_match:
                idx += 1
                continue

            # 解析时间
            start_h, start_m, start_s, start_ms = (
                int(time_match.group(1)), int(time_match.group(2)),
                int(time_match.group(3)), int(time_match.group(4))
            )
            end_h, end_m, end_s, end_ms = (
                int(time_match.group(5)), int(time_match.group(6)),
                int(time_match.group(7)), int(time_match.group(8))
            )
            start_time = (start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0)
            end_time = (end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0)

            idx += 1

            # 收集本时间段的所有文本行
            # VTT 格式：时间戳 → 空行 → 文本行 → 空行
            # 需要跳过第一个空行，然后收集文本直到遇到下一个空行
            text_lines: List[str] = []
            
            # 跳过时间戳后面的空行
            while idx < len(lines) and lines[idx].strip() == "":
                idx += 1
            
            # 收集文本行（直到遇到空行或下一个时间戳）
            while idx < len(lines):
                peek = lines[idx].strip()
                if peek == "":
                    idx += 1  # 跳过文本后面的空行
                    break
                if timestamp_pattern.match(peek):
                    break
                text_lines.append(peek)
                idx += 1

            # 跳过过渡帧（持续时间 < 0.1 秒）
            if end_time - start_time < 0.1:
                continue

            # 渐进式字幕处理：
            # - 只有一行时：保留该行（第一帧或非渐进式单帧）
            # - 两行时：取最后一行（新增行）
            # - 多于两行时：取最后一行（新增行）
            if len(text_lines) == 1:
                # 只有一行（通常是第一帧），保留全部文本
                line_to_use = text_lines[0]
            elif len(text_lines) >= 2:
                # 多行：只取最后一行（新增行）
                line_to_use = text_lines[-1]
            else:
                continue

            clean_text = self._strip_vtt_tags(line_to_use).strip()

            # 清理非内容性标记（如 [musique], [music], [音乐] 等）
            clean_text = self._clean_non_content_markers(clean_text)

            if clean_text:
                segments.append(SubtitleSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text=clean_text
                ))

        return segments

    def _parse_traditional_vtt(
        self,
        lines: List[str],
        start_idx: int,
        timestamp_pattern: re.Pattern
    ) -> List[SubtitleSegment]:
        """解析传统 VTT 字幕（非渐进式）

        Args:
            lines: VTT 文本行列表
            start_idx: 开始解析的行索引
            timestamp_pattern: 时间戳正则

        Returns:
            字幕片段列表
        """
        segments: List[SubtitleSegment] = []

        idx = start_idx
        while idx < len(lines):
            line = lines[idx].strip()

            time_match = timestamp_pattern.match(line)
            if not time_match:
                idx += 1
                continue

            start_h, start_m, start_s, start_ms = (
                int(time_match.group(1)), int(time_match.group(2)),
                int(time_match.group(3)), int(time_match.group(4))
            )
            end_h, end_m, end_s, end_ms = (
                int(time_match.group(5)), int(time_match.group(6)),
                int(time_match.group(7)), int(time_match.group(8))
            )
            start_time = (start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0)
            end_time = (end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0)

            idx += 1

            text_lines: List[str] = []
            while idx < len(lines):
                peek = lines[idx].strip()
                if peek == "":
                    next_non_blank = self._find_next_non_blank(lines, idx + 1)
                    if next_non_blank == -1:
                        idx = len(lines)
                        break
                    if timestamp_pattern.match(lines[next_non_blank].strip()):
                        idx += 1
                        break
                    idx += 1
                    continue
                text_lines.append(peek)
                idx += 1

            raw_text = " ".join(text_lines)
            clean_text = self._strip_vtt_tags(raw_text)

            if clean_text:
                if segments and segments[-1].text == clean_text:
                    pass
                else:
                    segments.append(SubtitleSegment(
                        start_time=start_time,
                        end_time=end_time,
                        text=clean_text
                    ))

        return segments
    
    @staticmethod
    def _find_next_non_blank(lines: List[str], start: int) -> int:
        """
        查找下一个非空行的索引
        
        Args:
            lines: 行列表
            start: 起始索引
            
        Returns:
            非空行索引，未找到返回 -1
        """
        for i in range(start, len(lines)):
            if lines[i].strip() != "":
                return i
        return -1
    
    @staticmethod
    def _strip_vtt_tags(text: str) -> str:
        """
        移除 VTT 文本中的 HTML-like 标签
        
        Args:
            text: 含标签的 VTT 文本
            
        Returns:
            纯文本
        """
        import re
        
        clean = re.sub(r"<[^>]+>", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
    
    # 非内容性标记列表（多语言）
    _NON_CONTENT_MARKERS = [
        # 音乐/音效标记
        r"\[musique\]", r"\[music\]", r"\[音樂\]", r"\[音乐\]",
        r"\[musik\]", r"\[musica\]", r"\[musique\]",
        # 其他非内容标记
        r"\[rire\]", r"\[laughs?\]", r"\[笑\]", r"\[笑声\]",
        r"\[applause\]", r"\[掌声\]", r"\[鼓掌\]",
        r"\[sigh\]", r"\[叹息\]",
        # 通用方括号标记
        r"\[[a-zA-ZÀ-ÿ\u4e00-\u9fa5]{2,15}\]",
    ]

    @classmethod
    def _clean_non_content_markers(cls, text: str) -> str:
        """清除字幕中的非内容性标记（如 [musique], [music], [音乐] 等）
        
        这些标记由 YouTube 自动生成，表示背景音乐、音效等，
        不属于对话内容，应该从字幕中移除。
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        import re
        
        if not text:
            return text
        
        clean = text
        for pattern in cls._NON_CONTENT_MARKERS:
            clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
        
        # 清理因移除标记产生的多余空格
        clean = re.sub(r"\s+", " ", clean).strip()
        # 清理开头/结尾的标点
        clean = clean.strip(" ,.;:!?。，；：！？、")
        
        return clean
    
    @staticmethod
    def _srt_time_to_seconds(time_str: str) -> float:
        """
        将 SRT 时间字符串转换为秒
        
        Args:
            time_str: 时间字符串 (HH:MM:SS,mmm 或 HH:MM:SS.mmm)
            
        Returns:
            秒数
        """
        try:
            time_str = time_str.replace(",", ".")
            parts = time_str.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, IndexError):
            pass
        return 0.0
    
    def _load_external_subtitles(
        self,
        video_path: str,
        language: Optional[str] = None
    ) -> List[SubtitleSegment]:
        """
        从视频同目录加载外挂字幕文件
        
        优先加载指定语言的字幕文件，再尝试通用字幕文件和其他常用语言。
        
        Args:
            video_path: 视频文件路径
            language: 目标语言代码（如 'de', 'fr', 'es', 'en' 等）
            
        Returns:
            字幕片段列表
        """
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        
        subtitle_extensions = [".srt", ".vtt", ".ass", ".ssa"]
        
        lang_regions = {
            "de": ["de-DE"],
            "fr": ["fr-FR"],
            "es": ["es-ES"],
            "en": ["en-US", "en_GB"],
            "zh": ["zh-CN", "zh-TW"],
            "ja": ["ja-JP"],
            "ko": ["ko-KR"],
            "ru": ["ru-RU"],
            "it": ["it-IT"],
            "pt": ["pt-PT", "pt-BR"],
            "ar": ["ar-SA"],
            "hi": ["hi-IN"],
            "nl": ["nl-NL"],
            "sv": ["sv-SE"],
            "no": ["no-NO"],
            "da": ["da-DK"],
            "fi": ["fi-FI"],
            "pl": ["pl-PL"],
            "cs": ["cs-CZ"],
            "hu": ["hu-HU"],
            "ro": ["ro-RO"],
            "el": ["el-GR"],
            "tr": ["tr-TR"],
            "vi": ["vi-VN"],
            "th": ["th-TH"],
            "id": ["id-ID"],
            "ms": ["ms-MY"],
            "tl": ["tl-PH"],
        }
        
        candidate_files: List[str] = []
        
        priority_langs: List[str] = []
        if language:
            priority_langs.append(language)
            priority_langs.extend(lang_regions.get(language, []))
        
        priority_langs.append("en")
        priority_langs.extend(lang_regions.get("en", []))
        
        seen_langs = set(priority_langs)
        for lang_code, regions in lang_regions.items():
            if lang_code not in seen_langs:
                priority_langs.append(lang_code)
                priority_langs.extend(regions)
                seen_langs.add(lang_code)
        
        for ext in subtitle_extensions:
            candidate_files.append(os.path.join(video_dir, f"{video_name}{ext}"))
        
        for lang_code in priority_langs:
            for ext in subtitle_extensions:
                candidate_files.append(os.path.join(video_dir, f"{video_name}.{lang_code}{ext}"))
        
        if language and language != "en":
            logger.info(f"优先加载 {language} 语言的外挂字幕文件")
        
        for sub_path in candidate_files:
            if os.path.exists(sub_path):
                logger.info(f"找到外挂字幕文件: {sub_path}")
                try:
                    with open(sub_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    segments = self._parse_srt_content(content)
                    if segments:
                        logger.info(f"外挂字幕加载成功，共 {len(segments)} 个片段")
                        return segments
                except UnicodeDecodeError:
                    try:
                        with open(sub_path, "r", encoding="gbk") as f:
                            content = f.read()
                        segments = self._parse_srt_content(content)
                        if segments:
                            logger.info(f"外挂字幕加载成功（GBK编码），共 {len(segments)} 个片段")
                            return segments
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"读取外挂字幕文件失败 {sub_path}: {e}")
                    continue
        
        logger.info("未找到可用的外挂字幕文件")
        return []
    
    def recognize(
        self,
        video_path: str,
        language: Optional[str] = None
    ) -> List[SubtitleSegment]:
        """
        从视频中提取字幕（两套方案）

        方案A - 使用已有字幕（优先）：
            1. 读取视频同目录外挂字幕文件（yt-dlp 下载的 .srt/.vtt）
            2. 通过 ffmpeg 提取视频内嵌字幕轨道

        方案B - ASR 语音识别（回退）：
            3. 当方案A无可用字幕时，使用 faster-whisper 语音识别生成字幕

        Args:
            video_path: 视频文件路径
            language: 语言代码（可选）

        Returns:
            字幕片段列表

        Raises:
            FileNotFoundError: 视频文件不存在
            ValueError: 视频文件为空
            RuntimeError: 无可用字幕
        """
        is_ready, err_msg = self._check_video_ready(video_path)
        if not is_ready:
            logger.error(f"视频预检查失败: {err_msg}")
            if "不存在" in err_msg:
                raise FileNotFoundError(err_msg)
            elif "为空" in err_msg:
                raise ValueError(err_msg)
            else:
                raise RuntimeError(err_msg)
        
        # 覆盖率阈值：字幕覆盖时长/视频时长 低于该值视为"字幕不完整"，继续尝试后续方案
        MIN_COVERAGE_RATIO = 0.20  # 20%
        
        logger.info(f"开始处理视频字幕: {os.path.basename(video_path)}")

        if self._force_asr:
            # === force_asr: 跳过方案A，直接走 ASR ===
            logger.info("force_asr=ON，跳过 YouTube 外挂/内嵌字幕，直接 ASR 语音识别")
            asr_segments = self._generate_subtitles_via_asr(video_path, language)
            if asr_segments:
                coverage = self._compute_segments_coverage(asr_segments, video_path)
                logger.info(f"force_asr ASR 识别成功: {len(asr_segments)} 段（覆盖率 {coverage:.0%}）")
                return asr_segments
            logger.error("force_asr 模式下 ASR 识别失败，无可用字幕")
            raise RuntimeError("force_asr 模式下 ASR 识别失败")

        # === 正常模式：方案A → 方案B ===
        logger.info("字幕方案A：优先使用已下载/内嵌的字幕文件")

        # 方案A-第1级：外挂字幕（yt-dlp 下载的 .srt/.vtt）
        segments = self._load_external_subtitles(video_path, language=language)
        if segments:
            coverage = self._compute_segments_coverage(segments, video_path)
            if coverage >= MIN_COVERAGE_RATIO:
                logger.info(f"方案A命中 - 外挂字幕加载成功: {len(segments)} 段（覆盖率 {coverage:.0%}）")
                return segments
            logger.warning(
                f"外挂字幕覆盖率仅 {coverage:.0%}（<{MIN_COVERAGE_RATIO:.0%}），"
                f"视为不完整，继续尝试内嵌字幕和 ASR"
            )
            fallback_external = segments  # 保留，作为最后兜底
        else:
            fallback_external = []

        # 方案A-第2级：内嵌字幕（ffmpeg 提取视频内字幕轨道）
        logger.info("尝试提取内嵌字幕")
        segments = self._extract_embedded_subtitles(video_path, language)
        if segments:
            coverage = self._compute_segments_coverage(segments, video_path)
            if coverage >= MIN_COVERAGE_RATIO:
                logger.info(f"方案A命中 - 内嵌字幕提取成功: {len(segments)} 段（覆盖率 {coverage:.0%}）")
                return segments
            logger.warning(
                f"内嵌字幕覆盖率仅 {coverage:.0%}（<{MIN_COVERAGE_RATIO:.0%}），"
                f"视为不完整，继续尝试 ASR"
            )

        # 方案B：ASR 语音识别（无可用字幕或字幕不完整时启用）
        logger.info("启用方案B：ASR 语音识别（无可用/不完整外挂+内嵌时执行）")
        asr_segments = self._generate_subtitles_via_asr(video_path, language)
        if asr_segments:
            coverage = self._compute_segments_coverage(asr_segments, video_path)
            logger.info(f"方案B命中 - ASR 语音识别成功: {len(asr_segments)} 段（覆盖率 {coverage:.0%}）")
            return asr_segments

        # ASR 也失败/空：回退到方案A拿到的外挂/内嵌字幕（即使不完整也比完全没有好）
        if fallback_external:
            logger.warning(
                f"ASR 无结果，回退使用不完整的外挂字幕（{len(fallback_external)} 段）作为兜底"
            )
            return fallback_external
        if segments:
            logger.warning(
                f"ASR 无结果，回退使用不完整的内嵌字幕（{len(segments)} 段）作为兜底"
            )
            return segments

        # 全部失败
        logger.error(f"视频无可用字幕（方案A外挂+内嵌、方案B ASR均失败）: {video_path}")
        raise RuntimeError("视频无可用字幕（外挂字幕文件不存在且无内嵌字幕轨道，ASR识别也失败）")
    
    def _load_whisper_model(self) -> Optional[Any]:
        """
        加载 faster-whisper 模型（懒加载 + 类级缓存）

        使用 small 模型，本地推理，无需网络。
        模型文件存放在项目内部 models/asr/ 目录（通过 path_helper 获取）。
        首次加载需要几秒，后续从缓存读取。

        Returns:
            WhisperModel 实例，加载失败返回 None
        """
        # 已加载成功，直接返回缓存
        if SpeechRecognizer._whisper_model_loaded and SpeechRecognizer._whisper_model is not None:
            return SpeechRecognizer._whisper_model

        # 已确认加载失败，不再重复尝试
        if SpeechRecognizer._whisper_load_error is not None:
            return None

        try:
            from faster_whisper import WhisperModel

            model_dir = str(get_asr_model_dir())
            logger.info(f"加载 faster-whisper small 模型（本地推理）: {model_dir}")

            # device="cpu" 适合无 GPU 环境
            # compute_type="int8" 在 CPU 上性能最好（精度损失极小）
            # cpu_threads 可根据实际 CPU 核数调整
            SpeechRecognizer._whisper_model = WhisperModel(
                "small",
                device="cpu",
                compute_type="int8",
                download_root=model_dir,
                cpu_threads=os.cpu_count() or 4
            )
            SpeechRecognizer._whisper_model_loaded = True
            logger.info("faster-whisper small 模型加载成功")
            return SpeechRecognizer._whisper_model

        except ImportError:
            SpeechRecognizer._whisper_load_error = "faster-whisper 库未安装"
            logger.error(
                "ASR 识别失败：faster-whisper 库未安装，"
                "请执行: pip install faster-whisper"
            )
            return None
        except Exception as e:
            SpeechRecognizer._whisper_load_error = str(e)
            logger.error(f"faster-whisper 模型加载失败: {e}")
            logger.exception("模型加载详细堆栈:")
            return None

    def _generate_subtitles_via_asr(
        self,
        video_path: str,
        language: Optional[str] = None
    ) -> List[SubtitleSegment]:
        """
        通过 faster-whisper ASR 语音识别生成字幕（回退方案）

        使用本地 small 模型推理，无需网络，支持 99 种语言。
        内置 VAD（语音活动检测）智能分段，避免粗暴切句。
        识别失败时记录详细错误日志并返回空列表，由上层抛出异常使任务失败。
        不生成占位字幕。

        Args:
            video_path: 视频文件路径
            language: 语言代码（如 fr/de/es，ISO 639-1 格式）

        Returns:
            字幕片段列表，识别失败返回空列表 []
        """
        # 步骤1: 加载 faster-whisper 模型（带缓存）
        model = self._load_whisper_model()
        if model is None:
            logger.error(
                f"ASR 识别失败：faster-whisper 模型不可用（"
                f"错误: {SpeechRecognizer._whisper_load_error}），"
                f"视频={os.path.basename(video_path)}"
            )
            return []

        # 步骤2: 从视频提取音频为 WAV 格式
        audio_path = self._extract_audio_for_asr(video_path)
        if not audio_path:
            logger.error(
                f"ASR 识别失败：音频提取失败，"
                f"视频={os.path.basename(video_path)}"
            )
            return []

        try:
            # 步骤3: 调用 faster-whisper 进行识别
            # faster-whisper 自带 VAD 智能分段，无需手动切分
            # language 参数指定源语言提高准确率（None 时自动检测）
            whisper_lang = language if language else None

            def _run_asr(use_vad: bool, vad_threshold: float,
                         min_silence_ms: int, speech_pad_ms: int,
                         label: str) -> List[SubtitleSegment]:
                """封装一次 ASR 尝试，返回 SubtitleSegment 列表"""
                logger.info(
                    f"ASR 识别尝试 [{label}]: "
                    f"视频={os.path.basename(video_path)}, "
                    f"语言={whisper_lang or '自动检测'}, "
                    f"vad={use_vad}, threshold={vad_threshold}, "
                    f"min_silence={min_silence_ms}ms"
                )
                if use_vad:
                    seg_gen, run_info = model.transcribe(
                        audio_path,
                        beam_size=5,
                        language=whisper_lang,
                        vad_filter=True,
                        vad_parameters={
                            "threshold": vad_threshold,  # 默认0.5，降低后更容易识别歌曲人声
                            "min_silence_duration_ms": min_silence_ms,
                            "speech_pad_ms": speech_pad_ms,
                        }
                    )
                else:
                    seg_gen, run_info = model.transcribe(
                        audio_path,
                        beam_size=5,
                        language=whisper_lang,
                        vad_filter=False,
                        condition_on_previous_text=False,
                        no_speech_threshold=0.6,
                    )
                # 检测语言（仅第一次尝试会输出，后续尝试 info 仍可用）
                _detected_lang = run_info.language if run_info else "未知"
                _lang_prob = run_info.language_probability if run_info else 0.0
                logger.info(
                    f"ASR [{label}] 语言检测: {_detected_lang} (置信度: {_lang_prob:.2%})"
                )
                result: List[SubtitleSegment] = []
                for seg in seg_gen:
                    text = seg.text.strip()
                    if text:
                        result.append(SubtitleSegment(
                            start_time=float(seg.start),
                            end_time=float(seg.end),
                            text=text
                        ))
                        logger.debug(
                            f"ASR [{label}] [{seg.start:.1f}s-{seg.end:.1f}s]: {text[:60]}"
                        )
                return result

            # 第1次尝试：宽松 VAD（默认0.5降为0.35，歌曲背景下更容易通过）
            segments = _run_asr(
                use_vad=True,
                vad_threshold=0.35,
                min_silence_ms=300,
                speech_pad_ms=300,
                label="VAD-loose"
            )
            coverage = self._compute_segments_coverage(segments, video_path)
            MIN_ASR_COVERAGE = 0.20

            if segments and coverage >= MIN_ASR_COVERAGE:
                logger.info(
                    f"ASR 首次尝试成功: {len(segments)} 段，覆盖率 {coverage:.0%}（≥{MIN_ASR_COVERAGE:.0%}）"
                )
            else:
                # 第2次尝试：关闭 VAD（完全不静音过滤），针对音乐MV/visualizer等演唱人声场景
                logger.warning(
                    f"ASR 首次尝试覆盖率仅 {coverage:.0%}（<{MIN_ASR_COVERAGE:.0%}），"
                    f"启用无VAD重试（针对音乐/演唱类视频优化）"
                )
                segments_no_vad = _run_asr(
                    use_vad=False,
                    vad_threshold=0.0,
                    min_silence_ms=0,
                    speech_pad_ms=0,
                    label="NO-VAD"
                )
                cov_no_vad = self._compute_segments_coverage(
                    segments_no_vad, video_path
                )
                # 选覆盖率更高、且非空的那个；若覆盖率接近优先保留 VAD 版（静音过滤通常更干净）
                if segments_no_vad and cov_no_vad > max(coverage + 0.05, MIN_ASR_COVERAGE):
                    logger.info(
                        f"ASR 无VAD重试效果更好: "
                        f"{len(segments_no_vad)} 段，覆盖率 {cov_no_vad:.0%} > VAD版 {coverage:.0%}"
                    )
                    segments = segments_no_vad
                elif segments:
                    logger.info(
                        f"ASR 仍保留VAD版: {len(segments)} 段（覆盖率 {coverage:.0%}，"
                        f"无VAD版覆盖率 {cov_no_vad:.0%}未显著更高）"
                    )
                else:
                    segments = segments_no_vad
                    logger.info(
                        f"ASR 回退使用无VAD版: {len(segments)} 段，覆盖率 {cov_no_vad:.0%}"
                    )

            # 清理临时音频文件
            try:
                os.remove(audio_path)
            except Exception:
                pass

            if segments:
                final_cov = self._compute_segments_coverage(segments, video_path)
                logger.info(
                    f"ASR 语音识别完成，共 {len(segments)} 段，最终覆盖率 {final_cov:.0%}"
                )
                return segments
            else:
                logger.error(
                    f"ASR 识别失败：识别结果为空，"
                    f"视频={os.path.basename(video_path)}，"
                    f"语言={whisper_lang or '自动检测'}"
                )
                return []

        except Exception as e:
            logger.error(
                f"ASR 识别失败：语音识别异常，"
                f"视频={os.path.basename(video_path)}，"
                f"语言={language}，"
                f"错误类型={type(e).__name__}，"
                f"错误信息={e}"
            )
            logger.exception(f"ASR 详细异常堆栈: {e}")

            # 清理临时音频文件
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except Exception:
                pass

            return []
    
    def _extract_audio_for_asr(self, video_path: str) -> Optional[str]:
        """
        从视频提取音频为 ASR 可用的 WAV 格式（16kHz, 单声道, PCM）
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            临时 WAV 文件路径，失败返回 None
        """
        if not self._check_ffmpeg():
            logger.warning("ffmpeg 不可用，无法提取音频")
            return None
        
        try:
            tmp_dir = str(get_tmp_dir())
            os.makedirs(tmp_dir, exist_ok=True)
            audio_path = os.path.join(tmp_dir, f"asr_audio_{os.getpid()}_{id(self)}.wav")
            
            cmd = [
                self._ffmpeg_path,
                "-i", video_path,
                "-vn",  # 不处理视频流
                "-acodec", "pcm_s16le",  # PCM 16-bit 编码
                "-ar", "16000",  # 16kHz 采样率
                "-ac", "1",  # 单声道
                "-y",  # 覆盖输出
                audio_path
            ]
            
            logger.info(f"提取音频用于 ASR: {os.path.basename(video_path)}")
            with FFMPEG_LOCK:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=120  # 2分钟超时
                )
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1024:
                logger.info(f"音频提取成功: {os.path.getsize(audio_path)} bytes")
                return audio_path
            else:
                logger.warning("音频提取文件为空或不存在")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning("音频提取超时")
            return None
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            return None
    
    def _get_video_duration(self, video_path: str) -> float:
        """
        获取视频时长（秒）
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频时长（秒），失败返回0
        """
        if not self._check_ffmpeg():
            return 0.0
        
        try:
            assert self._ffprobe_path is not None
            cmd = [
                self._ffprobe_path,
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace", 
                timeout=10
            )
            
            duration = float(result.stdout.strip())
            logger.info(f"视频时长: {duration:.1f}秒")
            return duration
        except Exception:
            return 0.0
