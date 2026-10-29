"""
Dailymotion 视频爬虫

支持搜索、频道视频获取，集成语言过滤功能。
"""

import re
import json
from typing import Optional, Dict, List, Any

from core.spiders.base_spider import VideoSpider
from utils.enums import LanguageType


class DailymotionSpider(VideoSpider):
    """
    Dailymotion 视频爬虫
    
    功能：
        - 搜索视频（使用官方 API）
        - 获取单个视频详情
        - 获取频道视频列表
        - 语言过滤
    """
    
    def __init__(self, **kwargs) -> None:
        """初始化 Dailymotion 爬虫"""
        super().__init__(**kwargs)
        self._custom_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.dailymotion.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        self._api_base = "https://api.dailymotion.com/videos"
        self._logger.info("Dailymotion 爬虫初始化完成")
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索 Dailymotion 视频（使用官方 API）
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"Dailymotion 搜索: {query}")
        
        videos = []
        
        try:
            page = 1
            while page <= max_pages:
                params = {
                    "search": query,
                    "limit": 10,
                    "page": page,
                }
                
                url = f"{self._api_base}"
                self._logger.info(f"爬取第 {page}/{max_pages} 页: {url}")
                
                try:
                    # AUDIT-0022: 走 engine.request（curl_cffi + 重试），替换裸 std_requests
                    text = self._engine.request(url, headers=self._custom_headers, params=params, timeout=10)
                    if not text:
                        break
                    data = json.loads(text)
                    items = data.get("list", [])
                    
                    if not items:
                        self._logger.info("当前页无视频，可能已到达最后一页")
                        break
                    
                    for item in items:
                        video = {
                            "title": item.get("title"),
                            "source_url": "https://www.dailymotion.com/video/" + item.get("id", ""),
                            "description": item.get("description"),
                            "thumbnail": item.get("thumbnail_url"),
                            "duration": item.get("duration"),
                            "author": item.get("owner"),
                            "views": item.get("views"),
                            "published_at": item.get("created_time"),
                        }
                        
                        filtered = {k: v for k, v in video.items() if v}
                        if filtered:
                            videos.append(filtered)
                    
                    if not data.get("has_more", False):
                        break
                    
                    page += 1
                    
                except json.JSONDecodeError:
                    self._logger.error("解析 JSON 失败")
                    break
                
                except Exception as e:
                    self._logger.error(f"API 请求失败: {e}")
                    break
            
            if filter_languages:
                videos = self._filter_by_language(videos, filter_languages)
            
            if self._result_buffer:
                self._result_buffer.add_batch(videos)
                self._result_buffer.flush()
            
            self._logger.info(f"Dailymotion 搜索完成，获取 {len(videos)} 个视频")
            
        except Exception as e:
            self._logger.error(f"Dailymotion 搜索异常: {e}")
        
        return videos
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个 Dailymotion 视频详情
        
        Args:
            video_url: 视频 URL
        
        Returns:
            视频详情字典
        """
        self._logger.info(f"获取 Dailymotion 视频详情: {video_url}")
        
        video_id = self._extract_video_id(video_url)
        if not video_id:
            return None
        
        try:
            params = {
                "fields": "id,title,description,duration,views,created_time,thumbnail_480_url,owner.name",
            }
            
            url = f"{self._api_base}/{video_id}?" + "&".join([f"{k}={v}" for k, v in params.items()])
            html = self._engine.get(url, headers=self._custom_headers)
            
            if html is None:
                self._logger.error(f"获取视频页面失败: {video_url}")
                return None
            
            data = json.loads(html)
            video_info = {
                "title": data.get("title"),
                "source_url": video_url,
                "description": data.get("description"),
                "thumbnail": data.get("thumbnail_480_url"),
                "duration": data.get("duration"),
                "author": data.get("owner", {}).get("name"),
                "views": data.get("views"),
                "published_at": data.get("created_time"),
            }
            
            return self._normalize_video_info(video_info)
        
        except json.JSONDecodeError:
            self._logger.error("解析视频详情 JSON 失败")
            return None
        except Exception as e:
            self._logger.error(f"获取视频详情失败: {e}")
            return None
    
    def get_channel_videos(
        self,
        channel_url: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 Dailymotion 频道视频列表
        
        Args:
            channel_url: 频道 URL
            max_pages: 最大页数
            filter_languages: 语言白名单
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"获取 Dailymotion 频道视频: {channel_url}")
        
        return []
    
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        解析 Dailymotion 页面 HTML
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表
        """
        videos = []
        
        try:
            data = json.loads(html)
            items = data.get("list", [])
            
            for item in items:
                video = {
                    "title": item.get("title"),
                    "source_url": "https://www.dailymotion.com/video/" + item.get("id", ""),
                    "description": item.get("description"),
                    "thumbnail": item.get("thumbnail_480_url"),
                    "duration": item.get("duration"),
                    "author": item.get("owner", {}).get("name"),
                    "views": item.get("views"),
                    "published_at": item.get("created_time"),
                }
                
                filtered = {k: v for k, v in video.items() if v}
                if filtered:
                    videos.append(filtered)
        
        except json.JSONDecodeError:
            pass
        
        return videos
    
    def _build_search_url(self, query: str, page: int = 1) -> str:
        """构建 Dailymotion 搜索 URL"""
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        return f"https://www.dailymotion.com/search/{encoded_query}"
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """从 URL 中提取 Dailymotion 视频 ID"""
        match = re.match(r'.*dailymotion\.com/video/([^/]+)', url)
        if match:
            return match.group(1)
        
        return None
