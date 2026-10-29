"""
app/bootstrap.py — 应用启动装配

AUDIT-0040: 原 utils/app_initializer.py 反向 import core.task_scheduler，
打破了 utils→core 的分层方向。将装配入口下沉到 app/（入口层），
这里是唯一允许同时依赖 utils 和 core 的位置。

初始化顺序：
    1. 日志系统
    2. 旧数据迁移（打包版首次启动：程序目录 → 用户数据目录）
    3. 环境清理（临时目录）
    4. 路径工具初始化（确保工具在PATH中）
    5. 数据库初始化
    6. 核心模块初始化（队列、文件归档、加密）
    7. 任务调度器启动
"""

from utils.path_helper import clear_tmp_dir, ensure_tools_in_path
from utils.logger import init_logger, get_crawler_logger
from utils.db_manager import init_database, init_buffer_pool
from utils.queue_manager import init_queue_manager
from utils.file_sort import init_file_sorter
from utils.crypto_util import init_crypto_util
from core.task_scheduler import init_scheduler, start_scheduler
from app.data_migration import migrate_legacy_data

logger = get_crawler_logger()


def initialize_app() -> None:
    """
    统一初始化应用

    按正确顺序初始化所有模块。
    """
    logger.info("=" * 60)
    logger.info("开始初始化应用环境")
    logger.info("=" * 60)

    _step("初始化日志系统", _init_logger)
    _step("迁移旧数据到用户数据目录", migrate_legacy_data)
    _step("清理临时目录", _clear_temp_dir)
    _step("初始化路径工具", _init_path_tools)
    _step("初始化数据库", _init_database)
    _step("初始化核心模块", _init_core_modules)
    _step("启动任务调度器", _start_scheduler)

    logger.info("=" * 60)
    logger.info("应用初始化完成")
    logger.info("=" * 60)


def _step(name: str, func) -> None:
    """执行单个初始化步骤"""
    try:
        func()
        logger.info(f"✓ {name}")
    except Exception as e:
        logger.error(f"✗ {name} 失败: {e}")
        raise


def _init_logger() -> None:
    """初始化日志系统"""
    init_logger()


def _clear_temp_dir() -> None:
    """清理临时目录"""
    clear_tmp_dir()


def _init_path_tools() -> None:
    """初始化路径工具"""
    ensure_tools_in_path()


def _init_database() -> None:
    """初始化数据库"""
    init_buffer_pool()
    init_database()


def _init_core_modules() -> None:
    """初始化核心模块"""
    init_queue_manager()
    init_file_sorter()
    init_crypto_util()


def _start_scheduler() -> None:
    """启动任务调度器"""
    init_scheduler()
    start_scheduler()
