"""
视频网站爬虫模块

提供多种主流外网视频网站的爬虫实现，支持语言过滤。

支持的网站：
    - YouTube
    - Vimeo
    - Dailymotion
    - Bilibili

使用方式：
    from core.spiders import YoutubeSpider
    
    spider = YoutubeSpider()
    videos = spider.search("python tutorial", max_pages=5)
    
    # 语言过滤
    from utils.enums import LanguageType
    videos = spider.search(
        "python tutorial",
        filter_languages=[LanguageType.ENGLISH, LanguageType.GERMAN]
    )
"""

from .base_spider import VideoSpider
from .youtube_spider import YoutubeSpider
from .vimeo_spider import VimeoSpider
from .dailymotion_spider import DailymotionSpider
from .bilibili_spider import BilibiliSpider

__all__ = [
    "VideoSpider",
    "YoutubeSpider",
    "VimeoSpider",
    "DailymotionSpider",
    "BilibiliSpider",
]


def create_spider(spider_type: str, **kwargs):
    """创建视频网站爬虫
    
    Args:
        spider_type: 爬虫类型（youtube/vimeo/dailymotion/bilibili）
        **kwargs: 其他参数
    
    Returns:
        VideoSpider 实例
    """
    spider_map = {
        "youtube": YoutubeSpider,
        "vimeo": VimeoSpider,
        "dailymotion": DailymotionSpider,
        "bilibili": BilibiliSpider,
    }
    
    spider_class = spider_map.get(spider_type.lower())
    if spider_class is None:
        raise ValueError(f"未知的爬虫类型: {spider_type}")
    
    return spider_class(**kwargs)