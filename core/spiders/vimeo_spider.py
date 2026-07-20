"""
Vimeo 视频爬虫

支持搜索、频道视频获取，集成语言过滤功能。
"""

import re
import json
from typing import Optional, Dict, List, Any

from core.spiders.base_spider import VideoSpider
from utils.enums import LanguageType


class VimeoSpider(VideoSpider):
    """
    Vimeo 视频爬虫
    
    功能：
        - 搜索视频
        - 获取单个视频详情
        - 获取频道视频列表
        - 语言过滤
    """
    
    def __init__(self, **kwargs) -> None:
        """初始化 Vimeo 爬虫"""
        super().__init__(**kwargs)
        self._logger.info("Vimeo 爬虫初始化完成")
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索 Vimeo 视频
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"Vimeo 搜索: {query}")
        
        def pagination_strategy(base_url: str, page: int) -> str:
            return f"{base_url}&page={page}"
        
        base_url = self._build_search_url(query)
        
        videos = self.crawl_with_pagination(
            base_url=base_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages
        )
        
        self._logger.info(f"Vimeo 搜索完成，获取 {len(videos)} 个视频")
        return videos
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个 Vimeo 视频详情
        
        Args:
            video_url: 视频 URL
        
        Returns:
            视频详情字典
        """
        self._logger.info(f"获取 Vimeo 视频详情: {video_url}")
        
        html = self._engine.get(video_url)
        if html is None:
            self._logger.error(f"获取视频页面失败: {video_url}")
            return None
        
        video_info = self._parse_video_page(html, video_url)
        if video_info:
            return self._normalize_video_info(video_info)
        
        return None
    
    def get_channel_videos(
        self,
        channel_url: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 Vimeo 频道视频列表
        
        Args:
            channel_url: 频道 URL
            max_pages: 最大页数
            filter_languages: 语言白名单
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"获取 Vimeo 频道视频: {channel_url}")
        
        def pagination_strategy(base_url: str, page: int) -> str:
            return f"{base_url}?page={page}"
        
        videos = self.crawl_with_pagination(
            base_url=channel_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages
        )
        
        self._logger.info(f"频道视频获取完成，获取 {len(videos)} 个视频")
        return videos
    
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        解析 Vimeo 页面 HTML
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表
        """
        videos = []
        
        try:
            # 提取 JSON-LD 数据
            json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            if json_ld_match:
                try:
                    data = json.loads(json_ld_match.group(1))
                    if isinstance(data, list):
                        data = data[0]
                    
                    if data.get("@type") == "ItemList":
                        for item in data.get("itemListElement", []):
                            video = self._parse_json_ld_item(item)
                            if video:
                                videos.append(video)
                except json.JSONDecodeError:
                    pass
            
            # 提取 Vimeo 内部数据
            vimeo_data_match = re.search(r'window\.playerConfig\s*=\s*({.*?});', html, re.DOTALL)
            if vimeo_data_match:
                try:
                    vimeo_data = json.loads(vimeo_data_match.group(1))
                    video = self._parse_player_config(vimeo_data)
                    if video:
                        videos.append(video)
                except json.JSONDecodeError:
                    pass
            
            # 使用正则提取视频信息
            if not videos:
                videos = self._parse_with_regex(html)
        
        except Exception as e:
            self._logger.error(f"Vimeo 页面解析失败: {e}")
        
        return videos
    
    def _parse_json_ld_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析 JSON-LD 列表项"""
        if item.get("@type") != "VideoObject":
            return None
        
        video = {
            "title": item.get("name"),
            "source_url": item.get("url"),
            "description": item.get("description"),
            "thumbnail": item.get("thumbnailUrl"),
            "duration": item.get("duration"),
            "author": item.get("author", {}).get("name"),
            "views": item.get("interactionCount"),
            "published_at": item.get("datePublished"),
        }
        
        return {k: v for k, v in video.items() if v}
    
    def _parse_player_config(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析播放器配置"""
        try:
            video = {
                "title": config.get("video", {}).get("title"),
                "source_url": config.get("video", {}).get("url"),
                "description": config.get("video", {}).get("description"),
                "thumbnail": config.get("video", {}).get("thumbnail"),
                "duration": config.get("video", {}).get("duration"),
                "author": config.get("video", {}).get("owner", {}).get("name"),
                "views": config.get("video", {}).get("stats", {}).get("plays"),
            }
            
            return {k: v for k, v in video.items() if v}
        except Exception:
            return None
    
    def _parse_with_regex(self, html: str) -> List[Dict[str, Any]]:
        """使用正则表达式提取视频信息"""
        videos = []
        
        video_pattern = r'<a\s+href="(/[^"]+)"\s+class="[^"]*video-link[^"]*"[^>]*>'
        title_pattern = r'<h[234]\s+class="[^"]*video-title[^"]*"[^>]*>([^<]+)</h[234]>'
        
        links = re.findall(video_pattern, html)
        titles = re.findall(title_pattern, html)
        
        for i, link in enumerate(links):
            video = {
                "title": titles[i] if i < len(titles) else "",
                "source_url": "https://vimeo.com" + link,
            }
            
            if video["title"] or video["source_url"]:
                videos.append(video)
        
        return videos
    
    def _parse_video_page(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """解析视频详情页面"""
        video_info = {}
        
        title_match = re.search(r'<title>(.*?)\s*\|.*?Vimeo</title>', html)
        if title_match:
            video_info["title"] = title_match.group(1)
        
        desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if desc_match:
            video_info["description"] = desc_match.group(1)
        
        duration_match = re.search(r'"duration":\s*(\d+)', html)
        if duration_match:
            video_info["duration"] = int(duration_match.group(1))
        
        views_match = re.search(r'"plays":\s*(\d+)', html)
        if views_match:
            video_info["views"] = int(views_match.group(1))
        
        author_match = re.search(r'"name":\s*"([^"]+)"', html)
        if author_match:
            video_info["author"] = author_match.group(1)
        
        video_info["source_url"] = url
        
        return video_info if video_info else None
    
    def _build_search_url(self, query: str, page: int = 1) -> str:
        """构建 Vimeo 搜索 URL"""
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        return f"https://vimeo.com/search?q={encoded_query}"
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """从 URL 中提取 Vimeo 视频 ID"""
        match = re.match(r'.*vimeo\.com/(\d+)', url)
        if match:
            return match.group(1)
        
        return None