"""
多语种视频爬虫主程序

统一入口，负责初始化所有模块、启动调度器和WebUI。

启动命令：
    python main.py [--crawl] [--download] [--translate] [--webui]

功能模块：
    1. 爬虫模块（crawler）
    2. 下载模块（download）
    3. 分类模块（classify）
    4. 字幕翻译模块（subtitle_trans）
    5. 任务调度模块（task_scheduler）
    6. 文件归档模块（file_sort）
    7. WebUI 模块（webui）
"""

import sys
import os
import signal
import argparse
from typing import Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from utils.path_helper import clear_tmp_dir, get_db_path, APP_ROOT
from utils.logger import init_logger, get_crawler_logger
from utils.config_loader import load_config


logger = get_crawler_logger()


def init_environment() -> None:
    """初始化运行环境"""
    logger.info(f"项目根目录: {APP_ROOT}")
    
    clear_tmp_dir()
    logger.info("临时目录已清理")


def init_database() -> None:
    """初始化数据库"""
    from utils.db_manager import init_database, init_buffer_pool
    
    db_path = get_db_path()
    logger.info(f"数据库路径: {db_path}")
    
    init_buffer_pool()
    init_database()
    logger.info("数据库初始化完成")


def init_modules() -> None:
    """初始化所有核心模块"""
    from utils.queue_manager import init_queue_manager
    from utils.file_sort import init_file_sorter
    from utils.crypto_util import init_crypto_util
    
    init_queue_manager()
    logger.info("队列管理器初始化完成")
    
    init_file_sorter()
    logger.info("文件归档器初始化完成")
    
    init_crypto_util()
    logger.info("加密工具初始化完成")


def start_scheduler() -> None:
    """启动任务调度器"""
    from core.task_scheduler import init_scheduler, start_scheduler
    
    init_scheduler()
    start_scheduler()
    logger.info("任务调度器启动完成")


def start_webui() -> None:
    """启动 WebUI"""
    try:
        from webui.app import launch
        
        logger.info("启动 WebUI...")
        launch()
    except ImportError:
        logger.warning("WebUI 模块未安装，跳过启动")
    except Exception as e:
        logger.error(f"启动 WebUI 失败: {e}")


def run_crawler(query: str = "") -> None:
    """运行爬虫"""
    from core.crawler import MultiLangVideoCrawler
    
    crawler = MultiLangVideoCrawler()
    
    if query:
        logger.info(f"开始搜索: {query}")
        crawler.search_all(query, max_pages=3)
    else:
        logger.info("执行定时爬取任务")
        crawler.execute_scheduled_crawl()


def run_downloader(auto_subtitle: bool = True) -> None:
    """运行下载器"""
    from core.download import get_download_pool, DownloadResult
    from utils.db_manager import get_undownloaded_videos, update_video_downloaded, get_buffer_pool
    from utils.enums import LanguageType, VideoCategory
    
    download_pool = get_download_pool()
    
    videos = get_undownloaded_videos()
    logger.info(f"找到 {len(videos)} 个未下载视频")
    
    if not videos:
        logger.info("没有未下载的视频")
        return
    
    videos_to_download = []
    for video in videos:
        video_id = str(video["id"])
        source_url = video["source_url"]
        title = video.get("title", "")
        lang_code = video.get("lang")
        category_str = video.get("category")
        
        language = LanguageType.from_code(lang_code) if lang_code else None
        category = VideoCategory.from_code(category_str) if category_str else None
        
        videos_to_download.append({
            "video_id": video_id,
            "url": source_url,
            "title": title,
            "language": language,
            "category": category,
        })
        
        logger.info(f"添加下载任务: {video_id} -> {language.display_name if language else 'unknown'} / {category.display_name if category else 'unknown'}")
    
    download_pool.download_batch(videos_to_download)
    results = download_pool.wait_all()
    
    successful_count = 0
    failed_count = 0
    
    for result in results:
        if result.success:
            successful_count += 1
            for video in videos:
                if str(video["id"]) == result.video_id:
                    update_video_downloaded(video["id"], result.file_path)
                    logger.info(f"视频下载完成并更新状态: {result.video_id}")
                    
                    if auto_subtitle:
                        logger.info(f"自动处理字幕: {result.video_id}")
                        run_subtitle_processor(result.video_id, result.file_path)
                    break
        else:
            failed_count += 1
            logger.error(f"视频下载失败: {result.video_id}, error={result.error_message}")
    
    get_buffer_pool().flush()
    logger.info(f"下载任务完成，成功: {successful_count}，失败: {failed_count}")


def run_subtitle_processor(video_id: str, video_path: str) -> None:
    """运行字幕处理器"""
    from core.subtitle_processor import process_video_subtitle
    from utils.db_manager import get_video_info, get_buffer_pool
    
    try:
        video_info = get_video_info(video_id)
        if not video_info:
            logger.warning(f"未找到视频信息: {video_id}")
            return
        
        lang_code = video_info.get("lang")
        category_str = video_info.get("category")
        
        from utils.enums import LanguageType, VideoCategory
        language = LanguageType.from_code(lang_code) if lang_code else None
        category = VideoCategory.from_code(category_str) if category_str else None
        
        result = process_video_subtitle(
            video_id=video_id,
            video_path=video_path,
            language=language,
            category=category,
            source_lang=lang_code if lang_code else "auto",
            target_lang="zh-CN"
        )
        
        if result.success:
            logger.info(f"字幕处理成功: {video_id}")
            logger.info(f"  字幕文件: {result.subtitle_path}")
            logger.info(f"  嵌入字幕视频: {result.embedded_video_path}")
        else:
            logger.error(f"字幕处理失败: {video_id}, error={result.error_message}")
        
        get_buffer_pool().flush()
        
    except Exception as e:
        logger.error(f"字幕处理异常: {video_id}, error={e}")
        import traceback
        traceback.print_exc()


def run_translator() -> None:
    """运行翻译器"""
    from core.subtitle_trans import get_subtitle_translator
    from utils.db_manager import get_db_connection
    
    translator = get_subtitle_translator()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT video_id, file_path FROM video_info WHERE status = 3 AND subtitle_task_id IS NULL LIMIT 5"
        )
        
        for row in cursor.fetchall():
            video_id = row["video_id"]
            file_path = row["file_path"]
            
            logger.info(f"提交翻译任务: {video_id}")
            task_id = translator.submit_translation(video_id, file_path)
            
            if task_id:
                cursor.execute(
                    "UPDATE video_info SET subtitle_task_id = ? WHERE video_id = ?",
                    (task_id, video_id)
                )
        
        conn.commit()
        logger.info("翻译任务提交完成")
        
    finally:
        cursor.close()
        conn.close()


def signal_handler(signum: int, frame) -> None:
    """信号处理函数（优雅退出）"""
    logger.info(f"收到信号 {signum}，正在关闭服务...")
    
    from core.task_scheduler import stop_scheduler
    
    stop_scheduler()
    logger.info("服务已关闭")
    sys.exit(0)


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(description="多语种视频爬虫主程序")
    parser.add_argument("--crawl", action="store_true", help="运行爬虫")
    parser.add_argument("--download", action="store_true", help="运行下载器")
    parser.add_argument("--translate", action="store_true", help="运行翻译器")
    parser.add_argument("--webui", action="store_true", help="启动 WebUI")
    parser.add_argument("--query", type=str, default="", help="搜索关键词")
    parser.add_argument("--all", action="store_true", help="启动所有模块")
    
    args = parser.parse_args()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 60)
    logger.info("多语种视频爬虫启动")
    logger.info("=" * 60)
    
    init_logger()
    init_environment()
    init_database()
    init_modules()
    start_scheduler()
    
    if args.all:
        args.crawl = True
        args.download = True
        args.translate = True
        args.webui = True
    
    if args.crawl:
        run_crawler(args.query)
    
    if args.download:
        run_downloader()
    
    if args.translate:
        run_translator()
    
    if args.webui:
        start_webui()
    else:
        logger.info("WebUI 未启动，按 Ctrl+C 退出")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
