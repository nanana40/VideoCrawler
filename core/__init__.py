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

from .pipeline import (
    PipelineConfig,
    PipelineResult,
    PipelineRunner,
    get_pipeline_runner,
    run_pipeline,
    run_pipeline_async,
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
    "PipelineConfig",
    "PipelineResult",
    "PipelineRunner",
    "create_fingerprint_crawler",
    "create_crawler",
    "create_result_buffer",
    "create_spider",
    "init_crawler",
    "get_pipeline_runner",
    "run_pipeline",
    "run_pipeline_async",
]