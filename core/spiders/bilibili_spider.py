"""
Bilibili 视频爬虫

支持搜索、频道视频获取，集成语言过滤功能。
"""

import re
import json
from typing import Optional, Dict, List, Any

from core.spiders.base_spider import VideoSpider
from utils.enums import LanguageType


class BilibiliSpider(VideoSpider):
    """
    Bilibili 视频爬虫
    
    功能：
        - 搜索视频
        - 获取单个视频详情
        - 获取频道视频列表
        - 语言过滤
    """
    
    def __init__(self, **kwargs) -> None:
        """初始化 Bilibili 爬虫"""
        super().__init__(**kwargs)
        self._custom_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.bilibili.com/",
            "Sec-Ch-Ua": '"Chromium";v="120", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        self._logger.info("Bilibili 爬虫初始化完成")
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索 Bilibili 视频
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"Bilibili 搜索: {query}")
        
        def pagination_strategy(base_url: str, page: int) -> str:
            return f"{base_url}&page={page}"
        
        base_url = self._build_search_url(query)
        
        videos = self.crawl_with_pagination(
            base_url=base_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages,
            headers=self._custom_headers
        )
        
        self._logger.info(f"Bilibili 搜索完成，获取 {len(videos)} 个视频")
        return videos
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个 Bilibili 视频详情
        
        Args:
            video_url: 视频 URL
        
        Returns:
            视频详情字典
        """
        self._logger.info(f"获取 Bilibili 视频详情: {video_url}")
        
        html = self._engine.get(video_url, headers=self._custom_headers)
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
        获取 Bilibili 频道视频列表
        
        Args:
            channel_url: 频道 URL
            max_pages: 最大页数
            filter_languages: 语言白名单
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"获取 Bilibili 频道视频: {channel_url}")
        
        def pagination_strategy(base_url: str, page: int) -> str:
            return f"{base_url}?page={page}"
        
        videos = self.crawl_with_pagination(
            base_url=channel_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages,
            headers=self._custom_headers
        )
        
        self._logger.info(f"频道视频获取完成，获取 {len(videos)} 个视频")
        return videos
    
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        解析 Bilibili 页面 HTML
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表
        """
        videos = []
        
        try:
            videos = self._parse_bili_api_data(html)
            
            if not videos:
                videos = self._parse_video_cards(html)
            
            if not videos:
                videos = self._parse_with_regex(html)
        
        except Exception as e:
            self._logger.error(f"Bilibili 页面解析失败: {e}")
        
        return videos
    
    def _parse_bili_api_data(self, html: str) -> List[Dict[str, Any]]:
        """解析 Bilibili API 数据（现代页面结构）"""
        videos = []
        
        bili_api_match = re.search(r'window\.__DATA__\s*=\s*({.*?});', html, re.DOTALL)
        if bili_api_match:
            try:
                api_data = json.loads(bili_api_match.group(1))
                videos.extend(self._extract_from_bili_data(api_data))
            except json.JSONDecodeError:
                pass
        
        bili_initial_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
        if bili_initial_match:
            try:
                initial_data = json.loads(bili_initial_match.group(1))
                videos.extend(self._extract_from_bili_initial(initial_data))
            except json.JSONDecodeError:
                pass
        
        return videos
    
    def _extract_from_bili_data(self, api_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Bilibili API 数据中提取视频信息"""
        videos = []
        
        try:
            pages = api_data.get("pages", {})
            for page_id, page_data in pages.items():
                if isinstance(page_data, dict):
                    items = page_data.get("items", [])
                    for item in items:
                        if isinstance(item, dict):
                            video = {
                                "title": item.get("title"),
                                "source_url": item.get("url"),
                                "description": item.get("desc"),
                                "thumbnail": item.get("pic"),
                                "duration": item.get("duration"),
                                "author": item.get("author"),
                                "views": item.get("play"),
                                "published_at": item.get("pubdate"),
                            }
                            
                            filtered = {k: v for k, v in video.items() if v}
                            if filtered:
                                videos.append(filtered)
        except Exception as e:
            self._logger.debug(f"解析 Bilibili API 数据失败: {e}")
        
        return videos
    
    def _extract_from_bili_initial(self, initial_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Bilibili 初始状态中提取视频信息"""
        videos = []
        
        try:
            search_result = initial_data.get("searchResult", {})
            videos_data = search_result.get("result", [])
            
            for video_data in videos_data:
                video = {
                    "title": video_data.get("title"),
                    "source_url": "https://www.bilibili.com/video/" + video_data.get("bvid", ""),
                    "description": video_data.get("desc"),
                    "thumbnail": video_data.get("pic"),
                    "duration": video_data.get("duration"),
                    "author": video_data.get("author"),
                    "views": video_data.get("play"),
                    "published_at": video_data.get("pubdate"),
                }
                
                filtered = {k: v for k, v in video.items() if v}
                if filtered:
                    videos.append(filtered)
        except Exception as e:
            self._logger.debug(f"解析 Bilibili 初始状态失败: {e}")
        
        return videos
    
    def _parse_video_cards(self, html: str) -> List[Dict[str, Any]]:
        """解析视频卡片（现代 Bilibili 页面）"""
        videos = []
        
        card_pattern = r'<div[^>]*class="[^"]*bili-video-card[^"]*"[^>]*>(.*?)</div>'
        cards = re.findall(card_pattern, html, re.DOTALL)
        
        for card in cards:
            video = {}
            
            title_match = re.search(r'title="([^"]+)"', card)
            if title_match:
                video["title"] = title_match.group(1).strip()
            
            link_match = re.search(r'href="([^"]+)"', card)
            if link_match:
                href = link_match.group(1)
                if href.startswith("/"):
                    video["source_url"] = "https://www.bilibili.com" + href
                else:
                    video["source_url"] = href
            
            thumbnail_match = re.search(r'src="([^"]+\.(jpg|png)[^"]*)"', card)
            if thumbnail_match:
                video["thumbnail"] = thumbnail_match.group(1)
            
            author_match = re.search(r'<span[^>]*class="[^"]*up-name[^"]*"[^>]*>([^<]+)</span>', card)
            if author_match:
                video["author"] = author_match.group(1).strip()
            
            view_match = re.search(r'<span[^>]*class="[^"]*play-num[^"]*"[^>]*>([^<]+)</span>', card)
            if view_match:
                video["views"] = view_match.group(1).strip()
            
            if video.get("title") and video.get("source_url"):
                videos.append(video)
        
        return videos
    
    def _parse_with_regex(self, html: str) -> List[Dict[str, Any]]:
        """使用正则表达式提取视频信息"""
        videos = []
        
        video_links = re.findall(r'href="(/video/[^"]+)"', html)
        title_tags = re.findall(r'title="([^"]+)"', html)
        
        video_titles = []
        for i, link in enumerate(video_links):
            if link.startswith("/video/"):
                title = ""
                if i < len(title_tags):
                    title = title_tags[i]
                
                video = {
                    "title": title,
                    "source_url": "https://www.bilibili.com" + link,
                }
                
                if video["title"] or video["source_url"]:
                    videos.append(video)
        
        return videos
    
    def _parse_video_page(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """解析视频详情页面"""
        video_info = {}
        
        title_match = re.search(r'<title>(.*?)\s*_\s*哔哩哔哩</title>', html)
        if title_match:
            video_info["title"] = title_match.group(1)
        
        desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if desc_match:
            video_info["description"] = desc_match.group(1)
        
        bili_api_match = re.search(r'window\.__DATA__\s*=\s*({.*?});', html, re.DOTALL)
        if bili_api_match:
            try:
                api_data = json.loads(bili_api_match.group(1))
                pages = api_data.get("pages", {})
                for page_data in pages.values():
                    if isinstance(page_data, dict):
                        video_info["duration"] = page_data.get("duration")
                        video_info["views"] = page_data.get("play")
                        video_info["author"] = page_data.get("author")
                        video_info["thumbnail"] = page_data.get("pic")
                        break
            except json.JSONDecodeError:
                pass
        
        video_info["source_url"] = url
        
        return video_info if video_info else None
    
    def _build_search_url(self, query: str, page: int = 1) -> str:
        """构建 Bilibili 搜索 URL"""
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        return f"https://search.bilibili.com/all?keyword={encoded_query}&page={page}"
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """从 URL 中提取 Bilibili 视频 ID"""
        match = re.match(r'.*bilibili\.com/video/(BV[^/]+)', url)
        if match:
            return match.group(1)
        
        match = re.match(r'.*bilibili\.com/video/av(\d+)', url)
        if match:
            return match.group(1)
        
        return None
