"""
文件归档模块（升级版）

目录结构升级：output/<language>/<category>/<channel>/<video_id>/

职责：
    1. 按 语言/分类/频道主 三级自动创建目录
    2. 标准化视频/字幕命名（video_id_title.ext）
    3. 频道名 sanitize（中文/标点/uax9 空格 → _）
    4. 提供 organize_file(): 下载完成后把临时文件搬到正确归档目录
"""

import os
import shutil
import re
from typing import Optional, Dict, Any

from utils.enums import LanguageType, VideoCategory
from utils.path_helper import get_output_dir
from utils.logger import get_crawler_logger


logger = get_crawler_logger()


def _sanitize(name: str, max_len: int = 60) -> str:
    if not name:
        return ""
    s = str(name)
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\t', ',', ';']:
        s = s.replace(ch, " ")
    # 连续空格 → 单 _
    s = re.sub(r"\s+", "_", s).strip("_")
    if not s:
        return ""
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


class FileSorter:
    """文件归档器（支持 language/category/channel 三级目录）"""

    def __init__(self) -> None:
        self._output_dir = get_output_dir()
        logger.info("文件归档器初始化完成")

    def get_output_root(self) -> str:
        """只读返回归档根目录（output 绝对路径）。

        供需要 output 根但又不该直接摸私有 `_output_dir` 的调用方使用。
        """
        return str(self._output_dir)

    # ------------------------------------------------------------------
    # 目录
    # ------------------------------------------------------------------
    def get_video_dir(
        self,
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        video_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> str:
        """
        构造视频存储目录:
            output/<language>/<category>/<channel>/<video_id>/
            其中 category/channel/video_id 可省略
        """
        parts = [self._output_dir]
        if language:
            parts.append(language.value)
        if category:
            parts.append(category.value)
        if channel:
            c = _sanitize(channel)
            if c:
                parts.append(c)
        if video_id:
            parts.append(video_id)
        dir_path = os.path.join(*parts)
        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def get_subtitle_dir(
        self,
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        video_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> str:
        """字幕文件存放在视频目录下（而非单独 subtitles/ 子目录）。"""
        return self.get_video_dir(language, category, video_id, channel)

    # ------------------------------------------------------------------
    # 文件名
    # ------------------------------------------------------------------
    def generate_video_filename(
        self,
        video_id: str,
        title: str,
        ext: str = "mp4",
    ) -> str:
        safe_title = _sanitize(title or "", max_len=50)
        return f"{video_id}_{safe_title}.{ext}"

    def generate_subtitle_filename(
        self,
        video_id: str,
        target_lang: str = "zh-CN",
        ext: str = "srt",
    ) -> str:
        return f"{video_id}_{target_lang}.{ext}"

    # ------------------------------------------------------------------
    # 归档
    # ------------------------------------------------------------------
    def organize_file(
        self,
        src_path: str,
        video_id: str,
        title: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        channel: Optional[str] = None,
        target_name: Optional[str] = None,
    ) -> str:
        """
        把 src_path 复制/移动到正确的归档目录，返回归档后路径。
        如果 src_path 已经在目标位置，就原样返回。

        Args:
            target_name: 直接指定文件名（例如烧录成品的 <id>_已完成.mp4）。
                         None → 用 generate_video_filename / generate_subtitle_filename 自动拼。
        """
        if not src_path or not os.path.exists(src_path):
            return src_path or ""

        ext = os.path.splitext(src_path)[1].lstrip(".").lower()

        # 根据扩展名判断是视频还是字幕
        subtitle_exts = {"srt", "vtt", "ass", "ssa", "sub"}
        if ext in subtitle_exts:
            target_dir = self.get_subtitle_dir(language, category, video_id, channel)
            if target_name:
                fname = target_name
            else:
                # 从原文件名解析 target_lang（如 abc_de.srt）
                base = os.path.splitext(os.path.basename(src_path))[0]
                lang_hint = "zh-CN"
                for known in ("zh-CN", "zh_CN", "en", "de", "fr", "es", "it", "pt", "ru",
                              "ja", "ko", "ar", "nl", "sv", "no", "da", "fi", "pl", "tr"):
                    if base.endswith(f"_{known}"):
                        lang_hint = known.replace("_", "-")
                        break
                fname = self.generate_subtitle_filename(video_id, lang_hint, ext)
        else:
            target_dir = self.get_video_dir(language, category, video_id, channel)
            fname = target_name or self.generate_video_filename(video_id, title, ext)

        dst = os.path.join(target_dir, fname)

        # 同源
        if os.path.abspath(src_path) == os.path.abspath(dst):
            return dst

        try:
            os.makedirs(target_dir, exist_ok=True)
            if os.path.abspath(os.path.dirname(src_path)) == os.path.abspath(target_dir):
                # 同目录只需重命名
                os.replace(src_path, dst)
            else:
                shutil.move(src_path, dst)
            logger.info(f"已归档: {os.path.basename(dst)} → {target_dir}")
            return dst
        except Exception as e:
            logger.error(f"归档失败: {e}")
            # 失败兜底：copy 不 move
            try:
                shutil.copy2(src_path, dst)
                return dst
            except Exception:
                return src_path

    # --- 兼容旧 API（内部走 organize_file） ---
    def move_video(
        self, source_path: str, video_id: str, title: str,
        language: Optional[LanguageType], category: Optional[VideoCategory],
        ext: str = "mp4", channel: Optional[str] = None,
    ) -> str:
        return self.organize_file(
            source_path, video_id, title, language, category, channel,
            target_name=self.generate_video_filename(video_id, title, ext),
        )

    def move_subtitle(
        self, source_path: str, video_id: str,
        language: Optional[LanguageType], category: Optional[VideoCategory],
        target_lang: str = "zh-CN", channel: Optional[str] = None,
    ) -> str:
        ext = os.path.splitext(source_path)[1].lstrip(".") or "srt"
        return self.organize_file(
            source_path, video_id, "", language, category, channel,
            target_name=self.generate_subtitle_filename(video_id, target_lang, ext),
        )

    # --- 兼容旧 API: 只拿路径，不动文件 ---
    def get_video_path(
        self, video_id: str, title: str,
        language: Optional[LanguageType], category: Optional[VideoCategory],
        ext: str = "mp4", channel: Optional[str] = None,
    ) -> str:
        target_dir = self.get_video_dir(language, category, video_id, channel)
        return os.path.join(target_dir, self.generate_video_filename(video_id, title, ext))

    def get_subtitle_path(
        self, video_id: str,
        language: Optional[LanguageType], category: Optional[VideoCategory],
        target_lang: str = "zh-CN", ext: str = "srt", channel: Optional[str] = None,
    ) -> str:
        target_dir = self.get_subtitle_dir(language, category, video_id, channel)
        return os.path.join(target_dir, self.generate_subtitle_filename(video_id, target_lang, ext))

    def ensure_dirs(self) -> None:
        for lang in LanguageType:
            for cat in VideoCategory:
                self.get_video_dir(lang, cat)
        logger.info("所有归档目录已创建")


# ---- 便捷函数 ----
_file_sorter: Optional[FileSorter] = None


def get_file_sorter() -> FileSorter:
    global _file_sorter
    if _file_sorter is None:
        _file_sorter = FileSorter()
    return _file_sorter


def get_video_path(*a, **kw) -> str:
    return get_file_sorter().get_video_path(*a, **kw)


def get_subtitle_path(*a, **kw) -> str:
    return get_file_sorter().get_subtitle_path(*a, **kw)


def init_file_sorter() -> None:
    global _file_sorter
    _file_sorter = FileSorter()
    _file_sorter.ensure_dirs()
