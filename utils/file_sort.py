"""
文件归档模块

自动分层文件夹管理、标准化视频/字幕命名。

功能特性：
    1. 按语言/分类自动创建目录结构
    2. 标准化视频/字幕命名
    3. 文件移动和重命名
    4. 目录结构管理
"""

import os
import shutil
from typing import Optional, Dict, Any

from utils.enums import LanguageType, VideoCategory
from utils.path_helper import get_output_dir
from utils.logger import get_crawler_logger


logger = get_crawler_logger()


class FileSorter:
    """
    文件归档器
    
    管理视频和字幕文件的存储结构。
    """
    
    def __init__(self) -> None:
        """初始化文件归档器"""
        self._output_dir = get_output_dir()
        logger.info("文件归档器初始化完成")
    
    def get_video_dir(
        self,
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        video_id: Optional[str] = None
    ) -> str:
        """
        获取视频存储目录
        
        Args:
            language: 语言类型
            category: 视频分类
            video_id: 视频 ID（如果提供，会为每个视频创建独立文件夹）
            
        Returns:
            目录路径
        """
        parts = [self._output_dir]
        
        if language:
            parts.append(language.value)
        if category:
            parts.append(category.value)
        if video_id:
            parts.append(video_id)
        
        dir_path = os.path.join(*parts)
        os.makedirs(dir_path, exist_ok=True)
        
        return dir_path
    
    def get_subtitle_dir(
        self,
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        video_id: Optional[str] = None
    ) -> str:
        """
        获取字幕存储目录
        
        Args:
            language: 语言类型
            category: 视频分类
            video_id: 视频 ID（如果提供，会为每个视频创建独立文件夹）
            
        Returns:
            目录路径
        """
        video_dir = self.get_video_dir(language, category, video_id)
        sub_dir = os.path.join(video_dir, "subtitles")
        os.makedirs(sub_dir, exist_ok=True)
        return sub_dir
    
    def generate_video_filename(
        self,
        video_id: str,
        title: str,
        ext: str = "mp4"
    ) -> str:
        """
        生成标准化的视频文件名
        
        Args:
            video_id: 视频 ID
            title: 视频标题
            ext: 文件扩展名
            
        Returns:
            文件名
        """
        safe_title = self._sanitize_filename(title)
        return f"{video_id}_{safe_title[:50]}.{ext}"
    
    def generate_subtitle_filename(
        self,
        video_id: str,
        target_lang: str = "zh-CN",
        ext: str = "srt"
    ) -> str:
        """
        生成标准化的字幕文件名
        
        Args:
            video_id: 视频 ID
            target_lang: 目标语言
            ext: 文件扩展名
            
        Returns:
            文件名
        """
        return f"{video_id}_{target_lang}.{ext}"
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        illegal_chars = '\\/:*?"<>| '
        for char in illegal_chars:
            filename = filename.replace(char, "_")
        return filename.strip()
    
    def move_video(
        self,
        source_path: str,
        video_id: str,
        title: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        ext: str = "mp4"
    ) -> str:
        """
        移动视频文件到归档目录
        
        Args:
            source_path: 源文件路径
            video_id: 视频 ID
            title: 视频标题
            language: 语言类型
            category: 视频分类
            ext: 文件扩展名
            
        Returns:
            新文件路径
        """
        target_dir = self.get_video_dir(language, category)
        new_filename = self.generate_video_filename(video_id, title, ext)
        new_path = os.path.join(target_dir, new_filename)
        
        try:
            shutil.move(source_path, new_path)
            logger.info(f"视频文件已移动: {new_path}")
            return new_path
        except Exception as e:
            logger.error(f"移动视频文件失败: {e}")
            return source_path
    
    def move_subtitle(
        self,
        source_path: str,
        video_id: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        target_lang: str = "zh-CN"
    ) -> str:
        """
        移动字幕文件到归档目录
        
        Args:
            source_path: 源文件路径
            video_id: 视频 ID
            language: 语言类型
            category: 视频分类
            target_lang: 目标语言
            
        Returns:
            新文件路径
        """
        target_dir = self.get_subtitle_dir(language, category)
        ext = os.path.splitext(source_path)[1].lstrip(".") or "srt"
        new_filename = self.generate_subtitle_filename(video_id, target_lang, ext)
        new_path = os.path.join(target_dir, new_filename)
        
        try:
            shutil.move(source_path, new_path)
            logger.info(f"字幕文件已移动: {new_path}")
            return new_path
        except Exception as e:
            logger.error(f"移动字幕文件失败: {e}")
            return source_path
    
    def get_video_path(
        self,
        video_id: str,
        title: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        ext: str = "mp4"
    ) -> str:
        """
        获取视频文件的归档路径（不移动文件）
        
        Args:
            video_id: 视频 ID
            title: 视频标题
            language: 语言类型
            category: 视频分类
            ext: 文件扩展名
            
        Returns:
            文件路径
        """
        target_dir = self.get_video_dir(language, category)
        filename = self.generate_video_filename(video_id, title, ext)
        return os.path.join(target_dir, filename)
    
    def get_subtitle_path(
        self,
        video_id: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        target_lang: str = "zh-CN",
        ext: str = "srt"
    ) -> str:
        """
        获取字幕文件的归档路径（不移动文件）
        
        Args:
            video_id: 视频 ID
            language: 语言类型
            category: 视频分类
            target_lang: 目标语言
            ext: 文件扩展名
            
        Returns:
            文件路径
        """
        target_dir = self.get_subtitle_dir(language, category)
        filename = self.generate_subtitle_filename(video_id, target_lang, ext)
        return os.path.join(target_dir, filename)
    
    def ensure_dirs(self) -> None:
        """确保所有必要的目录存在"""
        for lang in LanguageType:
            for cat in VideoCategory:
                self.get_video_dir(lang, cat)
                self.get_subtitle_dir(lang, cat)
        logger.info("所有归档目录已创建")


# 便捷函数
_file_sorter: Optional[FileSorter] = None


def get_file_sorter() -> FileSorter:
    """获取文件归档器实例（单例）"""
    global _file_sorter
    if _file_sorter is None:
        _file_sorter = FileSorter()
    return _file_sorter


def get_video_path(
    video_id: str,
    title: str,
    language: Optional[LanguageType],
    category: Optional[VideoCategory],
    ext: str = "mp4"
) -> str:
    """
    便捷函数：获取视频文件路径
    
    Args:
        video_id: 视频 ID
        title: 视频标题
        language: 语言类型
        category: 视频分类
        ext: 文件扩展名
        
    Returns:
        文件路径
    """
    return get_file_sorter().get_video_path(video_id, title, language, category, ext)


def get_subtitle_path(
    video_id: str,
    language: Optional[LanguageType],
    category: Optional[VideoCategory],
    target_lang: str = "zh-CN",
    ext: str = "srt"
) -> str:
    """
    便捷函数：获取字幕文件路径
    
    Args:
        video_id: 视频 ID
        language: 语言类型
        category: 视频分类
        target_lang: 目标语言
        ext: 文件扩展名
        
    Returns:
        文件路径
    """
    return get_file_sorter().get_subtitle_path(video_id, language, category, target_lang, ext)


def init_file_sorter() -> None:
    """初始化文件归档器"""
    global _file_sorter
    _file_sorter = FileSorter()
    _file_sorter.ensure_dirs()
