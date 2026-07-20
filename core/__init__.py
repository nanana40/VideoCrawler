"""
核心业务层模块

仅导入 utils 层，禁止反向导入
"""

from .crawler import (
    FingerprintCrawler,
    CrawlerAdapter,
    GenericCrawler,
    ResultBuffer,
    PaginationStrategy,
    create_fingerprint_crawler,
    create_crawler,
    create_result_buffer,
    init_crawler,
)

from .spiders import (
    VideoSpider,
    YoutubeSpider,
    VimeoSpider,
    DailymotionSpider,
    BilibiliSpider,
    create_spider,
)

__all__ = [
    "FingerprintCrawler",
    "CrawlerAdapter",
    "GenericCrawler",
    "ResultBuffer",
    "PaginationStrategy",
    "VideoSpider",
    "YoutubeSpider",
    "VimeoSpider",
    "DailymotionSpider",
    "BilibiliSpider",
    "create_fingerprint_crawler",
    "create_crawler",
    "create_result_buffer",
    "create_spider",
    "init_crawler",
]