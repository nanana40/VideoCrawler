"""
视频网站爬虫基类

所有视频网站爬虫的统一接口，提供搜索和视频解析功能。
"""

import re
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod

from core.crawler import CrawlerAdapter, FingerprintCrawler, PaginationStrategy
from utils.enums import LanguageType


class VideoSpider(CrawlerAdapter, ABC):
    """
    视频网站爬虫基类
    
    定义视频网站爬虫的标准接口：
        - search() - 搜索视频
        - get_video_info() - 获取单个视频详情
        - get_channel_videos() - 获取频道视频
    """
    
    def __init__(
        self,
        engine: Optional[FingerprintCrawler] = None,
        buffer_size: int = 100,
        enable_buffer: bool = True
    ) -> None:
        """初始化视频爬虫
        
        Args:
            engine: 指纹爬虫引擎
            buffer_size: 结果缓冲区大小
            enable_buffer: 是否启用结果缓冲
        """
        super().__init__(engine, buffer_size, enable_buffer)
        
        # 视频信息字段映射
        self._field_mapping = {
            "title": ["title", "name", "videoTitle", "video_title"],
            "source_url": ["url", "videoUrl", "video_url", "source_url", "link"],
            "description": ["description", "desc", "videoDescription", "video_desc"],
            "thumbnail": ["thumbnail", "thumb", "thumbnailUrl", "thumb_url"],
            "duration": ["duration", "length", "videoDuration", "duration_sec"],
            "author": ["author", "channel", "channelName", "uploader"],
            "views": ["views", "viewCount", "view_count", "play_count"],
            "published_at": ["publishedAt", "published_at", "uploadDate", "upload_date"],
        }
    
    @abstractmethod
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索视频
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        pass
    
    @abstractmethod
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个视频详情
        
        Args:
            video_url: 视频 URL
        
        Returns:
            视频详情字典
        """
        pass
    
    @abstractmethod
    def get_channel_videos(
        self,
        channel_url: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取频道视频列表
        
        Args:
            channel_url: 频道 URL
            max_pages: 最大页数
            filter_languages: 语言白名单
        
        Returns:
            视频信息列表
        """
        pass
    
    def _build_search_url(self, query: str, page: int = 1) -> str:
        """构建搜索 URL（默认实现）
        
        Args:
            query: 搜索关键词
            page: 页码
        
        Returns:
            搜索 URL
        """
        raise NotImplementedError("子类必须实现 _build_search_url 方法")
    
    def _normalize_video_info(self, video: Dict[str, Any]) -> Dict[str, Any]:
        """标准化视频信息字段
        
        将不同网站返回的不同字段名统一为标准字段。
        
        Args:
            video: 原始视频信息字典
        
        Returns:
            标准化后的视频信息字典
        """
        normalized = {}
        
        for standard_field, possible_fields in self._field_mapping.items():
            for field in possible_fields:
                if field in video and video[field]:
                    normalized[standard_field] = video[field]
                    break
        
        # 如果没有找到标准字段，保留原始字段
        if not normalized:
            normalized = video
        
        # 标准化时长格式
        if "duration" in normalized:
            normalized["duration"] = self._normalize_duration(normalized["duration"])
        
        # 标准化播放量格式
        if "views" in normalized:
            normalized["views"] = self._normalize_views(normalized["views"])
        
        return normalized
    
    def _normalize_duration(self, duration: Any) -> str:
        """标准化时长格式
        
        将各种时长格式转换为统一的 HH:MM:SS 格式。
        
        Args:
            duration: 原始时长（字符串或数字）
        
        Returns:
            标准化后的时长字符串
        """
        if isinstance(duration, int):
            # 秒数转换为 HH:MM:SS
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60
            
            if hours > 0:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{minutes:02d}:{seconds:02d}"
        
        duration_str = str(duration)
        
        # 匹配常见的时长格式
        patterns = [
            r"(\d+):(\d+):(\d+)",        # HH:MM:SS
            r"(\d+):(\d+)",              # MM:SS
            r"PT(\d+)H(\d+)M(\d+)S",     # ISO 8601
            r"PT(\d+)M(\d+)S",           # ISO 8601
            r"PT(\d+)S",                 # ISO 8601
        ]
        
        for pattern in patterns:
            match = re.match(pattern, duration_str)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    return f"{int(groups[0]):02d}:{int(groups[1]):02d}:{int(groups[2]):02d}"
                elif len(groups) == 2:
                    return f"{int(groups[0]):02d}:{int(groups[1]):02d}"
                elif len(groups) == 1:
                    return f"00:{int(groups[0]):02d}"
        
        return duration_str
    
    def _normalize_views(self, views: Any) -> int:
        """标准化播放量格式
        
        将字符串格式的播放量转换为整数。
        
        Args:
            views: 原始播放量（字符串或数字）
        
        Returns:
            标准化后的播放量整数
        """
        if isinstance(views, int):
            return views
        
        views_str = str(views).strip()
        
        # 匹配带单位的播放量格式
        match = re.match(r"([\d,]+)\s*(K|M|B)", views_str, re.IGNORECASE)
        if match:
            num = float(match.group(1).replace(",", ""))
            unit = match.group(2).upper()
            
            if unit == "K":
                return int(num * 1000)
            elif unit == "M":
                return int(num * 1000000)
            elif unit == "B":
                return int(num * 1000000000)
        
        # 纯数字格式
        try:
            return int(re.sub(r"[,\\s]", "", views_str))
        except ValueError:
            return 0
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """从 URL 中提取视频 ID
        
        Args:
            url: 视频 URL
        
        Returns:
            视频 ID，如果无法提取返回 None
        """
        raise NotImplementedError("子类必须实现 _extract_video_id 方法")
    
    @property
    def site_name(self) -> str:
        """获取网站名称"""
        return self.__class__.__name__.replace("Spider", "")