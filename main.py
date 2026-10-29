"""
多语种视频爬虫主程序（CLI 模式）

启动命令：
    python main.py --full              # 完整流水线：爬取 → 下载 → 字幕 → 分析
    python main.py --full --reset-db   # 完整流水线 + 启动前清空数据库
    python main.py --query "AI news"  # 指定搜索关键词

GUI 入口：python main_gui.py

功能模块：
    1. 爬虫模块（crawler）
    2. 下载模块（download）
    3. 字幕处理模块（subtitle_processor）
    4. 内容分析模块（video_analyzer, social_media_formatter）
    5. 任务调度模块（task_scheduler）
"""

import sys
import os
import signal
import argparse

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from utils.app_initializer import initialize_app
from utils.logger import get_crawler_logger
from utils.db_manager import _get_connection, get_buffer_pool
from core.pipeline import PipelineConfig, run_pipeline

logger = get_crawler_logger()


def reset_database() -> None:
    """清空所有视频和翻译记录"""
    try:
        conn = _get_connection()
        with conn:
            conn.execute("DELETE FROM video_info")
            conn.execute("DELETE FROM translate_task")
        get_buffer_pool().flush_now()
        logger.info("数据库已清空")
    except Exception as e:
        logger.error(f"清空数据库失败: {e}")
        raise


def run_full_pipeline(query: str = "") -> None:
    """运行完整流水线：爬取 → 下载 → 字幕 → 分析"""
    config = PipelineConfig()
    if query:
        logger.info(f"搜索关键词: {query}")
    result = run_pipeline(config)
    logger.info(
        f"流程完成 - 爬取: {result.crawled}, 下载: {result.downloaded}, "
        f"字幕: {result.subtitled}, 分析: {result.analyzed}"
    )


def signal_handler(signum: int, frame) -> None:
    """信号处理函数（优雅退出）"""
    logger.info(f"收到信号 {signum}，正在关闭服务...")
    from core.task_scheduler import stop_scheduler
    stop_scheduler()
    logger.info("服务已关闭")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="多语种视频爬虫主程序")
    parser.add_argument(
        "--full", action="store_true",
        help="运行完整流水线（爬取→下载→字幕→分析）"
    )
    parser.add_argument("--query", type=str, default="", help="搜索关键词")
    parser.add_argument(
        "--reset-db", action="store_true",
        help="启动前清空数据库（生产环境初始化用）"
    )

    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("多语种视频爬虫启动")
    logger.info("=" * 60)

    initialize_app()

    if args.reset_db:
        logger.warning("⚠  --reset-db 已指定，正在清空数据库...")
        reset_database()

    if args.full:
        run_full_pipeline(args.query)

    if not args.full:
        parser.print_help()
        logger.info("未指定任何操作，退出")
        return

    logger.info("所有任务完成，按 Ctrl+C 退出")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
