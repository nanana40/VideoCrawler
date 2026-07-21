"""
Vimeo 视频爬虫

支持搜索、频道视频获取，集成语言过滤功能。
"""

import re
import json
import requests as std_requests
from typing import Optional, Dict, List, Any

from core.spiders.base_spider import VideoSpider
from utils.enums import LanguageType


class VimeoSpider(VideoSpider):
    """
    Vimeo 视频爬虫
    
    功能：
        - 搜索视频（使用 API 方式）
        - 获取单个视频详情
        - 获取频道视频列表
        - 语言过滤
    """
    
    def __init__(self, **kwargs) -> None:
        """初始化 Vimeo 爬虫"""
        super().__init__(**kwargs)
        self._custom_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://vimeo.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._api_base = "https://vimeo.com/api/v2"
        self._logger.info("Vimeo 爬虫初始化完成")
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索 Vimeo 视频（使用频道 API 方式）
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"Vimeo 搜索: {query}")
        
        videos = []
        
        available_channels = ['music', 'travel', 'food', 'german', 'spanish', 'technology']
        
        query_lower = query.lower()
        target_channels = available_channels
        
        if 'deutsch' in query_lower or 'german' in query_lower:
            target_channels = ['german', 'music', 'technology']
        elif 'français' in query_lower or 'french' in query_lower:
            target_channels = ['travel', 'food', 'music']
        elif 'español' in query_lower or 'spanish' in query_lower:
            target_channels = ['spanish', 'travel', 'music']
        
        try:
            for channel_name in target_channels[:2]:
                api_url = f"{self._api_base}/channel/{channel_name}/videos.json"
                self._logger.info(f"获取频道视频: {channel_name}")
                
                self._engine._add_delay()
                response = std_requests.get(api_url, headers=self._custom_headers, timeout=10)
                
                if response.status_code != 200:
                    continue
                
                try:
                    items = response.json()
                except json.JSONDecodeError:
                    continue
                
                if not items:
                    continue
                
                for item in items[:10]:
                    video = {
                        "title": item.get("title"),
                        "source_url": item.get("url"),
                        "description": item.get("description"),
                        "thumbnail": item.get("thumbnail_large"),
                        "duration": item.get("duration"),
                        "author": item.get("user_name"),
                        "views": item.get("stats_number_of_plays"),
                        "published_at": item.get("upload_date"),
                    }
                    
                    filtered = {k: v for k, v in video.items() if v}
                    if filtered:
                        videos.append(filtered)
            
            if filter_languages:
                videos = self._filter_by_language(videos, filter_languages, threshold=0.1)
            
            if self._result_buffer:
                self._result_buffer.add_batch(videos)
                self._result_buffer.flush()
            
            self._logger.info(f"Vimeo 搜索完成，获取 {len(videos)} 个视频")
            
        except Exception as e:
            self._logger.error(f"Vimeo 搜索异常: {e}")
        
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
            filter_languages=filter_languages,
            headers=self._custom_headers
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
            videos = self._parse_vimeo_search_data(html)
            
            if not videos:
                videos = self._parse_video_cards(html)
            
            if not videos:
                videos = self._parse_with_regex(html)
        
        except Exception as e:
            self._logger.error(f"Vimeo 页面解析失败: {e}")
        
        return videos
    
    def _parse_vimeo_search_data(self, html: str) -> List[Dict[str, Any]]:
        """解析 Vimeo 搜索页面数据（现代页面结构）"""
        videos = []
        
        vimeo_data_match = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', html, re.DOTALL)
        if vimeo_data_match:
            try:
                app_data = json.loads(vimeo_data_match.group(1))
                videos.extend(self._extract_from_next_data(app_data))
            except json.JSONDecodeError:
                pass
        
        return videos
    
    def _extract_from_next_data(self, app_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Next.js 数据中提取视频信息"""
        videos = []
        
        try:
            props = app_data.get("props", {})
            page_props = props.get("pageProps", {})
            
            search_data = page_props.get("searchResults")
            if search_data:
                results = search_data.get("data", [])
                for result in results:
                    if result.get("type") == "video":
                        video = {
                            "title": result.get("name"),
                            "source_url": "https://vimeo.com/" + str(result.get("id", "")),
                            "description": result.get("description"),
                            "thumbnail": result.get("pictures", {}).get("sizes", [{}])[-1].get("link"),
                            "duration": result.get("duration"),
                            "author": result.get("user", {}).get("name"),
                            "views": result.get("stats", {}).get("plays"),
                            "published_at": result.get("created_time"),
                        }
                        
                        filtered = {k: v for k, v in video.items() if v}
                        if filtered:
                            videos.append(filtered)
            
            entities = page_props.get("entities", {})
            if entities:
                for entity_id, entity in entities.items():
                    if entity.get("type") == "video":
                        video = {
                            "title": entity.get("name"),
                            "source_url": "https://vimeo.com/" + str(entity.get("id", "")),
                            "description": entity.get("description"),
                            "thumbnail": entity.get("pictures", {}).get("sizes", [{}])[-1].get("link"),
                            "duration": entity.get("duration"),
                            "author": entity.get("user", {}).get("name"),
                            "views": entity.get("stats", {}).get("plays"),
                            "published_at": entity.get("created_time"),
                        }
                        
                        filtered = {k: v for k, v in video.items() if v}
                        if filtered:
                            videos.append(filtered)
        
        except Exception as e:
            self._logger.debug(f"解析 Vimeo Next.js 数据失败: {e}")
        
        return videos
    
    def _parse_video_cards(self, html: str) -> List[Dict[str, Any]]:
        """解析视频卡片（现代 Vimeo 页面）"""
        videos = []
        
        card_pattern = r'<div[^>]*class="[^"]*video-card[^"]*"[^>]*>(.*?)</div>'
        cards = re.findall(card_pattern, html, re.DOTALL)
        
        for card in cards:
            video = {}
            
            title_match = re.search(r'<h[234]\s[^>]*>([^<]+)</h[234]>', card)
            if title_match:
                video["title"] = title_match.group(1).strip()
            
            link_match = re.search(r'<a\s+href="([^"]+)"[^>]*>', card)
            if link_match:
                href = link_match.group(1)
                if href.startswith("/"):
                    video["source_url"] = "https://vimeo.com" + href
                else:
                    video["source_url"] = href
            
            thumbnail_match = re.search(r'<img[^>]*src="([^"]+\.jpg[^"]*)"', card)
            if thumbnail_match:
                video["thumbnail"] = thumbnail_match.group(1)
            
            if video.get("title") and video.get("source_url"):
                videos.append(video)
        
        return videos
    
    def _parse_with_regex(self, html: str) -> List[Dict[str, Any]]:
        """使用正则表达式提取视频信息"""
        videos = []
        
        video_links = re.findall(r'href="(/video/[^"]+)"', html)
        title_tags = re.findall(r'<h[234][^>]*>([^<]+)</h[234]>', html)
        
        for i, link in enumerate(video_links):
            if link.startswith("/video/"):
                video = {
                    "title": title_tags[i] if i < len(title_tags) else "",
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
        
        vimeo_data_match = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', html, re.DOTALL)
        if vimeo_data_match:
            try:
                app_data = json.loads(vimeo_data_match.group(1))
                props = app_data.get("props", {}).get("pageProps", {})
                entities = props.get("entities", {})
                for entity in entities.values():
                    if entity.get("type") == "video":
                        video_info["duration"] = entity.get("duration")
                        video_info["views"] = entity.get("stats", {}).get("plays")
                        video_info["author"] = entity.get("user", {}).get("name")
                        video_info["thumbnail"] = entity.get("pictures", {}).get("sizes", [{}])[-1].get("link")
                        break
            except json.JSONDecodeError:
                pass
        
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
