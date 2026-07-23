"""
视频下载模块

封装 yt-dlp 下载逻辑，支持多线程下载、进度回调、失败重试。

功能特性：
    1. yt-dlp 下载封装
    2. 外置 bin 路径适配
    3. 下载进度回调
    4. 多线程下载池
    5. 下载失败重试逻辑
    6. 按语言/分类自动存储到对应目录
"""

import os
import time
import threading
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass

from utils.enums import TaskStatus, LanguageType, VideoCategory
from utils.logger import get_download_logger
from utils.path_helper import get_ytdlp_path, get_output_dir, get_tmp_dir
from utils.config_loader import get_download_config, load_config
from utils.file_sort import get_file_sorter


logger = get_download_logger()


@dataclass
class DownloadProgress:
    """下载进度信息"""
    video_id: str
    url: str
    title: str
    downloaded_bytes: int
    total_bytes: int
    progress: float
    speed: float
    eta: float
    status: str


@dataclass
class DownloadResult:
    """下载结果"""
    video_id: str
    url: str
    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None


class VideoDownloader:
    """
    视频下载器
    
    封装 yt-dlp 下载逻辑，支持进度回调和失败重试。
    """
    
    def __init__(self) -> None:
        """初始化视频下载器"""
        config = get_download_config(load_config())
        self._max_threads = config.get("max_download_thread", 3)
        self._ytdlp_path = get_ytdlp_path()
        self._output_dir = get_output_dir()
        self._tmp_dir = get_tmp_dir()
        self._downloading = set()
        self._lock = threading.Lock()
        logger.info("视频下载器初始化完成")
    
    def download_video(
        self,
        url: str,
        video_id: str,
        title: str = "",
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        max_retries: int = 3,
        min_duration: float = 90.0,
        max_duration: float = 600.0
    ) -> DownloadResult:
        """
        下载单个视频
        
        Args:
            url: 视频 URL
            video_id: 视频 ID
            title: 视频标题（用于生成文件名）
            language: 语言类型（用于自动选择存储目录）
            category: 视频分类（用于自动选择存储目录）
            output_path: 输出路径（可选，如果提供则覆盖语言/分类目录）
            progress_callback: 进度回调函数
            max_retries: 最大重试次数
            min_duration: 最小视频时长（秒），默认90秒（1分30秒）
            max_duration: 最大视频时长（秒），默认300秒（5分钟）
            
        Returns:
            DownloadResult 下载结果
        """
        if output_path is None and (language or category):
            file_sorter = get_file_sorter()
            output_path = file_sorter.get_video_dir(language, category, video_id)
            logger.info(f"自动选择输出目录: {output_path}")
        
        with self._lock:
            if video_id in self._downloading:
                logger.warning(f"视频 {video_id} 正在下载中，跳过")
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    success=False,
                    error_message="视频正在下载中"
                )
            self._downloading.add(video_id)
        
        try:
            for attempt in range(max_retries):
                try:
                    return self._do_download(url, video_id, title, output_path, progress_callback, min_duration, max_duration)
                except Exception as e:
                    logger.warning(f"下载失败 (尝试 {attempt + 1}/{max_retries}): {video_id}, error={e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            
            return DownloadResult(
                video_id=video_id,
                url=url,
                success=False,
                error_message=f"下载失败，已达最大重试次数 {max_retries}"
            )
            
        finally:
            with self._lock:
                self._downloading.discard(video_id)
    
    def _do_download(
        self,
        url: str,
        video_id: str,
        title: str = "",
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        min_duration: float = 90.0,
        max_duration: float = 600.0
    ) -> DownloadResult:
        """执行实际下载操作"""
        import yt_dlp
        
        if output_path is None:
            output_path = self._output_dir
        
        os.makedirs(output_path, exist_ok=True)
        
        file_sorter = get_file_sorter()
        filename = file_sorter.generate_video_filename(video_id, title)
        
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(output_path, filename),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_with_newline": False,
            "writesubtitles": True,
            "subtitleslangs": ["en", "en-US"],
            "writeautomaticsub": True,
            "embed_subtitles": True,
        }
        
        if self._ytdlp_path and os.path.exists(self._ytdlp_path):
            ydl_opts["external_downloader"] = self._ytdlp_path
        
        def progress_hook(d: Dict[str, Any]) -> None:
            if progress_callback and d.get("status") in ["downloading", "finished"]:
                progress = DownloadProgress(
                    video_id=video_id,
                    url=url,
                    title=d.get("info_dict", {}).get("title", title),
                    downloaded_bytes=d.get("downloaded_bytes", 0),
                    total_bytes=d.get("total_bytes", 0),
                    progress=d.get("_percent_str", "0%").strip("%"),
                    speed=d.get("_speed_str", "0 B/s"),
                    eta=d.get("_eta_str", "00:00"),
                    status=d.get("status", "")
                )
                progress_callback(progress)
        
        ydl_opts["progress_hooks"] = [progress_hook]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            duration = info.get("duration", 0)
            if duration < min_duration:
                logger.warning(f"视频时长 {duration:.2f} 秒小于最小要求 {min_duration:.2f} 秒，跳过下载")
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    success=False,
                    error_message=f"视频时长不足，仅 {duration:.2f} 秒，要求至少 {min_duration:.2f} 秒"
                )
            
            if duration > max_duration:
                logger.warning(f"视频时长 {duration:.2f} 秒大于最大要求 {max_duration:.2f} 秒，跳过下载")
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    success=False,
                    error_message=f"视频时长过长，达 {duration:.2f} 秒，要求不超过 {max_duration:.2f} 秒"
                )
            
            info = ydl.extract_info(url, download=True)
            
            file_path = ydl.prepare_filename(info)
            duration = info.get("duration")
            
            logger.info(f"视频下载完成: {file_path}，时长: {duration:.2f}秒")
            
            return DownloadResult(
                video_id=video_id,
                url=url,
                success=True,
                file_path=file_path,
                duration=duration
            )
    
    def download_batch(
        self,
        videos: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> List[DownloadResult]:
        """
        批量下载视频（单线程）
        
        Args:
            videos: 视频列表，每个视频包含 url、video_id、title、language、category 字段
            progress_callback: 进度回调函数
            
        Returns:
            下载结果列表
        """
        results = []
        for video in videos:
            language = video.get("language")
            category = video.get("category")
            
            if isinstance(language, str):
                language = LanguageType.from_code(language)
            if isinstance(category, str):
                category = VideoCategory.from_code(category)
            
            result = self.download_video(
                url=video.get("url", ""),
                video_id=video.get("video_id", ""),
                title=video.get("title", ""),
                language=language,
                category=category,
                progress_callback=progress_callback
            )
            results.append(result)
        return results


class DownloadPool:
    """
    多线程下载池
    
    管理多个并发下载任务，控制并发数。
    """
    
    def __init__(self, max_threads: Optional[int] = None) -> None:
        """
        初始化下载池
        
        Args:
            max_threads: 最大并发线程数
        """
        if max_threads is None:
            config = get_download_config(load_config())
            max_threads = config.get("max_download_thread", 3)
        
        self._max_threads = max_threads
        self._downloader = VideoDownloader()
        self._threads: List[threading.Thread] = []
        self._results: List[DownloadResult] = []
        self._lock = threading.Lock()
        logger.info(f"下载池初始化完成，最大并发数: {max_threads}")
    
    def download(
        self,
        url: str,
        video_id: str,
        title: str = "",
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> None:
        """
        提交下载任务（阻塞直到有可用线程）
        
        Args:
            url: 视频 URL
            video_id: 视频 ID
            title: 视频标题（用于生成文件名）
            language: 语言类型（用于自动选择存储目录）
            category: 视频分类（用于自动选择存储目录）
            output_path: 输出路径
            progress_callback: 进度回调
        """
        while len(self._threads) >= self._max_threads:
            self._cleanup_finished()
            time.sleep(0.1)
        
        thread = threading.Thread(
            target=self._download_worker,
            args=(url, video_id, title, language, category, output_path, progress_callback),
            daemon=True
        )
        thread.start()
        self._threads.append(thread)
    
    def download_batch(
        self,
        videos: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> None:
        """
        批量提交下载任务（非阻塞）
        
        Args:
            videos: 视频列表，每个视频包含 url、video_id、title、language、category 字段
            progress_callback: 进度回调函数
        """
        for video in videos:
            language = video.get("language")
            category = video.get("category")
            
            if isinstance(language, str):
                language = LanguageType.from_code(language)
            if isinstance(category, str):
                category = VideoCategory.from_code(category)
            
            self.download(
                url=video.get("url", ""),
                video_id=video.get("video_id", ""),
                title=video.get("title", ""),
                language=language,
                category=category,
                progress_callback=progress_callback
            )
    
    def _download_worker(
        self,
        url: str,
        video_id: str,
        title: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        output_path: Optional[str],
        progress_callback: Optional[Callable[[DownloadProgress], None]]
    ) -> None:
        """下载工作线程"""
        result = self._downloader.download_video(
            url=url,
            video_id=video_id,
            title=title,
            language=language,
            category=category,
            output_path=output_path,
            progress_callback=progress_callback
        )
        with self._lock:
            self._results.append(result)
    
    def _cleanup_finished(self) -> None:
        """清理已完成的线程"""
        self._threads = [t for t in self._threads if t.is_alive()]
    
    def wait_all(self) -> List[DownloadResult]:
        """等待所有下载任务完成并返回结果"""
        while self._threads:
            self._cleanup_finished()
            time.sleep(0.5)
        
        results = self._results[:]
        self._results.clear()
        return results
    
    def clear(self) -> None:
        """清空下载池状态（线程和结果）"""
        self._threads.clear()
        self._results.clear()
    
    def is_busy(self) -> bool:
        """检查是否有正在进行的下载任务"""
        self._cleanup_finished()
        return len(self._threads) > 0
    
    def get_progress(self) -> Dict[str, Any]:
        """获取下载池进度"""
        self._cleanup_finished()
        return {
            "active_threads": len(self._threads),
            "completed_tasks": len(self._results),
            "max_threads": self._max_threads,
        }


# 便捷函数
_download_pool: Optional[DownloadPool] = None


def get_download_pool() -> DownloadPool:
    """获取下载池实例（单例）"""
    global _download_pool
    if _download_pool is None:
        _download_pool = DownloadPool()
    return _download_pool


def download_video(
    url: str,
    video_id: str,
    title: str = "",
    language: Optional[LanguageType] = None,
    category: Optional[VideoCategory] = None,
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    min_duration: float = 90.0,
    max_duration: float = 300.0
) -> DownloadResult:
    """
    便捷函数：下载单个视频
    
    Args:
        url: 视频 URL
        video_id: 视频 ID
        title: 视频标题（用于生成文件名）
        language: 语言类型（用于自动选择存储目录）
        category: 视频分类（用于自动选择存储目录）
        output_path: 输出路径
        progress_callback: 进度回调
        min_duration: 最小视频时长（秒），默认90秒（1分30秒）
        max_duration: 最大视频时长（秒），默认300秒（5分钟）
        
    Returns:
        DownloadResult 下载结果
    """
    downloader = VideoDownloader()
    return downloader.download_video(url, video_id, title, language, category, output_path, progress_callback, min_duration=min_duration, max_duration=max_duration)


def init_download_pool(max_threads: Optional[int] = None) -> None:
    """
    初始化下载池
    
    Args:
        max_threads: 最大并发线程数
    """
    global _download_pool
    _download_pool = DownloadPool(max_threads)
