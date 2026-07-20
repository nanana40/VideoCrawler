"""
YouTube 视频爬虫

支持搜索、频道视频获取，集成语言过滤功能。
"""

import re
import json
from typing import Optional, Dict, List, Any

from core.spiders.base_spider import VideoSpider
from utils.enums import LanguageType


class YoutubeSpider(VideoSpider):
    """
    YouTube 视频爬虫
    
    功能：
        - 搜索视频
        - 获取单个视频详情
        - 获取频道视频列表
        - 语言过滤
    """
    
    def __init__(self, **kwargs) -> None:
        """初始化 YouTube 爬虫"""
        super().__init__(**kwargs)
        self._logger.info("YouTube 爬虫初始化完成")
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索 YouTube 视频
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"YouTube 搜索: {query}")
        
        def pagination_strategy(base_url: str, page: int) -> str:
            if page == 1:
                return base_url
            # YouTube 使用 pageToken 进行分页，这里简化为 URL 参数
            return f"{base_url}&page={page}"
        
        base_url = self._build_search_url(query)
        
        videos = self.crawl_with_pagination(
            base_url=base_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages
        )
        
        self._logger.info(f"YouTube 搜索完成，获取 {len(videos)} 个视频")
        return videos
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个 YouTube 视频详情
        
        Args:
            video_url: 视频 URL
        
        Returns:
            视频详情字典
        """
        self._logger.info(f"获取 YouTube 视频详情: {video_url}")
        
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
        获取 YouTube 频道视频列表
        
        Args:
            channel_url: 频道 URL
            max_pages: 最大页数
            filter_languages: 语言白名单
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"获取 YouTube 频道视频: {channel_url}")
        
        # YouTube 频道视频页面格式
        videos_url = channel_url.rstrip("/") + "/videos"
        
        def pagination_strategy(base_url: str, page: int) -> str:
            if page == 1:
                return base_url
            return f"{base_url}?page={page}"
        
        videos = self.crawl_with_pagination(
            base_url=videos_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages
        )
        
        self._logger.info(f"频道视频获取完成，获取 {len(videos)} 个视频")
        return videos
    
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        解析 YouTube 页面 HTML
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表
        """
        videos = []
        
        try:
            # 提取页面中的 JSON-LD 数据
            json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            if json_ld_match:
                try:
                    data = json.loads(json_ld_match.group(1))
                    if isinstance(data, list):
                        data = data[0]
                    
                    if "@type" in data:
                        if data["@type"] == "ItemList":
                            for item in data.get("itemListElement", []):
                                video = self._parse_json_ld_item(item)
                                if video:
                                    videos.append(video)
                        elif data["@type"] == "VideoObject":
                            video = self._parse_video_object(data)
                            if video:
                                videos.append(video)
                except json.JSONDecodeError:
                    pass
            
            # 提取 YouTube 内部数据
            yt_data_match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
            if yt_data_match:
                try:
                    yt_data = json.loads(yt_data_match.group(1))
                    videos.extend(self._parse_yt_initial_data(yt_data))
                except json.JSONDecodeError:
                    pass
            
            # 使用正则提取视频信息
            if not videos:
                videos = self._parse_with_regex(html)
        
        except Exception as e:
            self._logger.error(f"YouTube 页面解析失败: {e}")
        
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
    
    def _parse_video_object(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析单个 VideoObject"""
        video = {
            "title": data.get("name"),
            "source_url": data.get("url"),
            "description": data.get("description"),
            "thumbnail": data.get("thumbnailUrl"),
            "duration": data.get("duration"),
            "author": data.get("author", {}).get("name"),
            "views": data.get("interactionCount"),
            "published_at": data.get("datePublished"),
        }
        
        return {k: v for k, v in video.items() if v}
    
    def _parse_yt_initial_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 YouTube 内部数据"""
        videos = []
        
        try:
            contents = data.get("contents", {})
            two_column_search_results = contents.get("twoColumnSearchResultsRenderer", {})
            primary_contents = two_column_search_results.get("primaryContents", {})
            section_list = primary_contents.get("sectionListRenderer", {})
            contents_list = section_list.get("contents", [])
            
            for section in contents_list:
                item_section = section.get("itemSectionRenderer", {})
                video_items = item_section.get("contents", [])
                
                for item in video_items:
                    video_renderer = item.get("videoRenderer")
                    if video_renderer:
                        video = self._parse_video_renderer(video_renderer)
                        if video:
                            videos.append(video)
        except Exception as e:
            self._logger.debug(f"解析 YouTube 内部数据失败: {e}")
        
        return videos
    
    def _parse_video_renderer(self, renderer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析视频渲染器数据"""
        try:
            video = {
                "title": renderer.get("title", {}).get("runs", [{}])[0].get("text"),
                "source_url": "https://www.youtube.com/watch?v=" + renderer.get("videoId", ""),
                "description": renderer.get("descriptionSnippet", {}).get("runs", [{}])[0].get("text"),
                "thumbnail": renderer.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url"),
                "duration": renderer.get("lengthText", {}).get("simpleText"),
                "author": renderer.get("ownerText", {}).get("runs", [{}])[0].get("text"),
                "views": renderer.get("viewCountText", {}).get("simpleText"),
                "published_at": renderer.get("publishedTimeText", {}).get("simpleText"),
            }
            
            return {k: v for k, v in video.items() if v}
        except Exception:
            return None
    
    def _parse_with_regex(self, html: str) -> List[Dict[str, Any]]:
        """使用正则表达式提取视频信息"""
        videos = []
        
        # 提取视频链接
        video_pattern = r'<a\s+href="(/watch\?v=[^"]+)"[^>]*>'
        title_pattern = r'<a\s+href="/watch\?v=[^"]+"[^>]*>([^<]+)</a>'
        
        links = re.findall(video_pattern, html)
        titles = re.findall(title_pattern, html)
        
        for i, link in enumerate(links):
            video = {
                "title": titles[i] if i < len(titles) else "",
                "source_url": "https://www.youtube.com" + link,
            }
            
            if video["title"] or video["source_url"]:
                videos.append(video)
        
        return videos
    
    def _parse_video_page(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """解析视频详情页面"""
        video_info = {}
        
        # 提取标题
        title_match = re.search(r'<title>(.*?)\s*-\s*YouTube</title>', html)
        if title_match:
            video_info["title"] = title_match.group(1)
        
        # 提取描述
        desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if desc_match:
            video_info["description"] = desc_match.group(1)
        
        # 提取时长
        duration_match = re.search(r'"lengthSeconds":"(\d+)"', html)
        if duration_match:
            video_info["duration"] = int(duration_match.group(1))
        
        # 提取播放量
        views_match = re.search(r'"viewCount":"([^"]+)"', html)
        if views_match:
            video_info["views"] = views_match.group(1)
        
        # 提取作者
        author_match = re.search(r'"author":"([^"]+)"', html)
        if author_match:
            video_info["author"] = author_match.group(1)
        
        video_info["source_url"] = url
        
        return video_info if video_info else None
    
    def _build_search_url(self, query: str, page: int = 1) -> str:
        """构建 YouTube 搜索 URL"""
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        return f"https://www.youtube.com/results?search_query={encoded_query}&page={page}"
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """从 URL 中提取 YouTube 视频 ID"""
        match = re.match(r'.*youtube\.com/watch\?v=([^&]+)', url)
        if match:
            return match.group(1)
        
        match = re.match(r'.*youtube\.com/embed/([^/]+)', url)
        if match:
            return match.group(1)
        
        return None