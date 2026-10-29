from __future__ import annotations
"""core/subtitles/embedder.py — VideoSubtitleEmbedder"""

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

from utils.enums import LanguageType, VideoCategory, TaskStatus
from utils.logger import get_translate_logger
from utils.path_helper import get_ffmpeg_path, get_tmp_dir, get_finished_sub_dir, get_asr_model_dir
from utils.file_sort import get_file_sorter
from utils.resource_locks import FFMPEG_LOCK


logger = get_translate_logger()


class VideoSubtitleEmbedder:
    """
    视频字幕嵌入器
    
    使用 ffmpeg 将字幕嵌入视频。
    """
    
    def __init__(self) -> None:
        """初始化视频字幕嵌入器"""
        ffmpeg_path = get_ffmpeg_path()
        if not os.path.exists(str(ffmpeg_path)):
            ffmpeg_path = ffmpeg_path.parent / "ffmpeg" / "bin" / "ffmpeg.exe"
        
        self._ffmpeg_path = str(ffmpeg_path)
        
        if os.path.exists(self._ffmpeg_path):
            logger.info(f"视频字幕嵌入器初始化完成，ffmpeg路径: {self._ffmpeg_path}")
        else:
            logger.warning(f"ffmpeg 未找到，将跳过字幕嵌入，仅生成字幕文件")
    
    def _has_embedded_subtitle(self, video_path: str) -> bool:
        """
        检测视频是否自带字幕轨道或外挂字幕文件
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            True 表示有自带字幕（内嵌或外挂）
        """
        if self._has_external_subtitle(video_path):
            return True
            
        try:
            cmd = [self._ffmpeg_path or "ffmpeg", "-i", video_path]
            result = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            
            stderr = result.stderr
            
            import re
            subtitle_pattern = re.compile(r"Stream #\d+:\d+.*Subtitle:", re.IGNORECASE)
            
            if subtitle_pattern.search(stderr):
                logger.info("视频自带内嵌字幕轨道")
                return True
            
            logger.info("视频未检测到字幕轨道")
            return False
            
        except Exception as e:
            logger.warning(f"检测自带字幕失败: {e}")
            return False
    
    def _has_external_subtitle(self, video_path: str) -> bool:
        """
        检测视频同目录下是否有外挂字幕文件
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            True 表示有外挂字幕文件
        """
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        
        subtitle_extensions = [".srt", ".vtt", ".ass", ".ssa", ".sub"]
        
        for ext in subtitle_extensions:
            subtitle_path = os.path.join(video_dir, f"{video_name}{ext}")
            if os.path.exists(subtitle_path):
                logger.info(f"视频同目录下有外挂字幕文件: {subtitle_path}")
                return True
                
            for lang in ["en", "en-US", "en_GB"]:
                subtitle_path = os.path.join(video_dir, f"{video_name}.{lang}{ext}")
                if os.path.exists(subtitle_path):
                    logger.info(f"视频同目录下有外挂字幕文件: {subtitle_path}")
                    return True
        
        return False
    
    def _get_video_dimensions(self, video_path: str) -> Tuple[int, int]:
        """
        获取视频分辨率
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            (宽度, 高度)
        """
        try:
            import json
            
            # 使用 ffprobe 获取视频分辨率（比 cv2 更可靠，无需额外依赖）
            ffprobe_path = self._ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
            if not os.path.exists(ffprobe_path):
                ffprobe_path = "ffprobe"
            
            cmd = [
                ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                video_path
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace", 
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        width = stream.get("width", 0)
                        height = stream.get("height", 0)
                        if width > 0 and height > 0:
                            return width, height
            
            logger.warning("ffprobe 未找到视频流，使用默认分辨率")
            return 1920, 1080
            
        except Exception as e:
            logger.warning(f"获取视频分辨率失败: {e}")
            return 1920, 1080

    @staticmethod
    def _cleanup_partial(path: str) -> None:
        """删除 ffmpeg 中断后留下的半成品文件"""
        try:
            if path and os.path.exists(path):
                size = os.path.getsize(path)
                os.remove(path)
                logger.debug(f"已清理半成品文件: {path} ({size} bytes)")
        except Exception as e:
            logger.warning(f"清理半成品文件失败: {e}")

    @staticmethod
    def _kill_orphan_ffmpeg() -> None:
        """Windows 上强制杀掉所有残留的 ffmpeg.exe 进程（taskkill /T /F）"""
        if os.name != "nt":
            return
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", "ffmpeg.exe"],
                capture_output=True, timeout=10
            )
        except Exception:
            pass

    def _verify_mp4_integrity(self, path: str) -> bool:
        """用 ffprobe 检查 MP4 是否有 moov atom（文件完整性）"""
        if not path or not os.path.exists(path):
            return False
        try:
            ffprobe = self._ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
            if not os.path.exists(ffprobe):
                ffprobe = "ffprobe"
            result = subprocess.run(
                [ffprobe, "-v", "error", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",  timeout=30
            )
            if result.returncode != 0:
                err = (result.stderr or "").lower()
                if "moov" in err or "invalid data" in err:
                    return False
                logger.debug(f"ffprobe 警告但可打开: {result.stderr[:200]}")
            return True
        except Exception as e:
            logger.warning(f"完整性校验异常: {e}")
            return False

    def _probe_duration(self, video_path: str) -> Optional[float]:
        """获取视频时长（秒），用于动态计算超时"""
        try:
            ffprobe = self._ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
            if not os.path.exists(ffprobe):
                ffprobe = "ffprobe"
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",  timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass
        return None

    
    
    
    def _generate_subtitle_style(self, video_path: str, has_original: bool) -> str:
        """
        生成字幕样式
        
        Args:
            video_path: 视频文件路径
            has_original: 是否有原字幕
            
        Returns:
            ASS 样式字符串
        """
        width, height = self._get_video_dimensions(video_path)
        
        font_size = 8
        margin_bottom = height // 15
        
        if has_original:
            y_position = margin_bottom
        else:
            y_position = height - margin_bottom - font_size - 10
        
        style = f"""\
[Script Info]
Title: Generated Subtitle
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,10,10,{y_position},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        return style
    
    def _convert_srt_to_ass(
        self,
        srt_path: str,
        video_path: str,
        has_original: bool
    ) -> str:
        """
        将 SRT 转换为 ASS 格式，添加样式
        
        Args:
            srt_path: SRT 文件路径
            video_path: 视频文件路径
            has_original: 是否有原字幕
            
        Returns:
            ASS 文件路径
        """
        ass_path = srt_path.replace(".srt", ".ass")
        
        style = self._generate_subtitle_style(video_path, has_original)
        
        with open(srt_path, "r", encoding="utf-8") as srt_file:
            srt_content = srt_file.read()
        
        ass_lines = [style]
        
        srt_pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)\n\n"
        matches = re.findall(srt_pattern, srt_content, re.DOTALL)
        
        for match in matches:
            _, start, end, text = match
            start = start.replace(",", ".")
            end = end.replace(",", ".")
            text = text.replace("\n", "\\N").strip()
            
            ass_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        
        with open(ass_path, "w", encoding="utf-8") as ass_file:
            ass_file.write("\n".join(ass_lines))
        
        logger.info(f"ASS 文件已生成: {ass_path}")
        return ass_path
    
    def embed_subtitle(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: Optional[str] = None,
        has_original_subtitle: bool = False
    ) -> str:
        """
        将字幕嵌入视频（底部黑色区域方案）
        
        在视频下方添加一块黑色区域，将字幕限制在该区域内，
        避免遮挡视频主内容。
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_path: 输出视频路径（可选）
            has_original_subtitle: 是否有原字幕
            
        Returns:
            输出视频路径（如果ffmpeg不可用，返回原视频路径）
        """
        if not os.path.exists(self._ffmpeg_path):
            logger.warning("ffmpeg 不可用，跳过字幕嵌入")
            return video_path
        
        if not os.path.exists(subtitle_path):
            logger.warning(f"字幕文件不存在: {subtitle_path}")
            return video_path
        
        if output_path is None:
            dir_name = os.path.dirname(video_path)
            base_name = os.path.basename(video_path)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(dir_name, f"{name}_已完成{ext}")
        
        try:
            orig_width, orig_height = self._get_video_dimensions(video_path)

            # 自动缩放：低分辨率视频先放大到合理尺寸
            # 判断标准：高度 < 720p 或宽度 < 720p
            target_height = orig_height
            target_width = orig_width
            needs_scale = False

            # 如果是竖屏视频（高度 > 宽度），以宽度为基准缩放
            if orig_height > orig_width:
                if orig_height < 720:
                    scale_factor = 720 / orig_height
                    target_height = 720
                    target_width = int(orig_width * scale_factor)
                    needs_scale = True
            # 横屏视频以高度为基准
            else:
                if orig_height < 480:
                    scale_factor = 480 / orig_height
                    target_height = 480
                    target_width = int(orig_width * scale_factor)
                    needs_scale = True

            # 确保偶数分辨率
            target_width += target_width % 2
            target_height += target_height % 2

            if needs_scale:
                logger.info(
                    f"低分辨率视频缩放: {orig_width}x{orig_height} → {target_width}x{target_height}"
                )

            # 计算字幕区域（基于缩放后的分辨率）
            # 黑色区域高度：视频画面高度的 10%，确保双语文本自动换行后不溢出
            subtitle_area_height = max(int(target_height * 0.10), 80)

            # 字体大小：强制固定 16px，不随分辨率变化
            font_size = 8

            # MarginV：字幕距底部（区域高度的 15%，底部留呼吸空间）
            margin_v = max(6, int(subtitle_area_height * 0.15))

            # MarginL/R：字幕水平内边距（区域宽度的 2%，避免贴边）
            margin_h = max(16, int(target_width * 0.02))

            logger.info(
                f"字幕嵌入配置: orig={orig_width}x{orig_height}, "
                f"target={target_width}x{target_height}, "
                f"subtitle_area={subtitle_area_height}px({subtitle_area_height/target_height:.0%}), "
                f"font_size={font_size}, scale={needs_scale}"
            )

            # Windows 路径转义
            escaped_path = subtitle_path.replace("\\", "/")
            special_chars = [":", "'", "[", "]", "(", ")", "{", "}", ",", ";", "&"]
            for char in special_chars:
                escaped_path = escaped_path.replace(char, f"\\{char}")

            style = (
                f"FontName=Microsoft YaHei,FontSize={font_size},"
                f"PrimaryColour=&H00FFFFFF,SecondaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,BackColour=&H80000000,"
                f"Bold=1,Alignment=2,"
                f"MarginL={margin_h},MarginR={margin_h},MarginV={margin_v},"
                f"Outline=2,Shadow=1,Spacing=0.4"
            )

            new_height = target_height + subtitle_area_height

            # 构建滤镜链
            filters = []

            if needs_scale:
                # 先 scale 到目标分辨率
                filters.append(f"scale={target_width}:{target_height}")

            # 再 pad 添加底部黑色区域
            filters.append(f"pad={target_width}:{new_height}:0:0:black")

            # 最后嵌入字幕
            filters.append(f"subtitles='{escaped_path}':force_style='{style}'")

            vf_chain = ",".join(filters)

            cmd = [
                self._ffmpeg_path,
                "-y",
                "-i", video_path,
                "-vf", vf_chain,
                "-c:a", "aac",
                "-b:a", "192k",
                "-c:v", "libx264",
                "-crf", "20",
                "-preset", "medium",
                "-movflags", "+faststart",
                output_path
            ]

            logger.info(f"ffmpeg 滤镜链: {vf_chain}")

            timeout_sec = max(600, int(orig_duration * 4 if (orig_duration := self._probe_duration(video_path)) else 600))

            with FFMPEG_LOCK:
                proc = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                try:
                    _, stderr = proc.communicate(timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.communicate(timeout=5)
                    except Exception:
                        pass
                    self._kill_orphan_ffmpeg()
                    self._cleanup_partial(output_path)
                    logger.error(f"ffmpeg 字幕嵌入超时（>{timeout_sec}s），已清理半成品: {output_path}")
                    return video_path

            if proc.returncode != 0:
                self._cleanup_partial(output_path)
                logger.error(f"ffmpeg 嵌入字幕失败 (code={proc.returncode}): {stderr[-500:]}")
                raise RuntimeError(f"ffmpeg error: {stderr[-300:]}")

            if not self._verify_mp4_integrity(output_path):
                self._cleanup_partial(output_path)
                logger.error(f"ffmpeg 输出文件完整性校验失败（moov atom 缺失或损坏）: {output_path}")
                return video_path

            logger.info(f"字幕已嵌入视频: {output_path}")
            return output_path

        except Exception as e:
            self._cleanup_partial(output_path)
            logger.error(f"ffmpeg 命令执行失败: {e}")
            return video_path
