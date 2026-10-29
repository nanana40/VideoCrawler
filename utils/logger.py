"""
日志模块：基于 Loguru 封装的分文件日志系统

功能特性：
    1. 按 LogTag 枚举分文件输出日志（crawler/download/translate/error）
    2. 支持日志滚动（按大小 10MB / 保留 7 天 / zip 压缩）
    3. 统一日志格式（时间戳/级别/标签/消息）
    4. 日志路径通过 path_helper 获取，自动适配开发/打包环境
    5. 提供便捷的 logger 实例获取函数
    6. 支持自定义日志级别
"""

import sys
from typing import Optional
from loguru import logger

from .enums import LogTag
from .path_helper import get_log_file, get_config_path
from . import config_loader


# =====================================================
# 日志格式定义
# =====================================================

# 控制台输出格式
_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "<level>{level: <8}</level> "
    "<cyan>[{extra[tag]}]</cyan> "
    "<level>{message}</level>"
)

# 文件输出格式（更详细，含进程/线程信息）
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "[{extra[tag]}] | "
    "{process.name}({process.id}) | "
    "{thread.name}({thread.id}) | "
    "{message}"
)

# 日志滚动配置（10MB / 保留 7 天 / zip 压缩）
_ROTATION_CONFIG = {
    "rotation": "10 MB",
    "retention": "7 days",
    "compression": "zip",
}


# =====================================================
# 日志标签映射（LogTag -> 文件名）
# =====================================================

def _get_log_file_path(tag: LogTag) -> str:
    """根据日志标签获取日志文件路径

    Args:
        tag: 日志标签枚举

    Returns:
        日志文件绝对路径字符串
    """
    return str(get_log_file(tag.value))


# =====================================================
# Logger 封装类
# =====================================================

class VideoCrawlerLogger:
    """视频爬虫项目日志封装类

    提供按模块分文件记录日志的能力，每个模块对应一个 LogTag，
    日志自动输出到对应文件和控制台。
    """

    def __init__(self, tag: LogTag) -> None:
        """初始化日志记录器

        Args:
            tag: 日志标签，决定日志输出到哪个文件
        """
        self._tag = tag
        self._logger = logger.bind(tag=tag.display_name)

    def debug(self, message: str, *args: object, **kwargs: object) -> None:
        """记录 DEBUG 级别日志

        Args:
            message: 日志消息（支持格式化）
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: object, **kwargs: object) -> None:
        """记录 INFO 级别日志

        Args:
            message: 日志消息（支持格式化）
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: object, **kwargs: object) -> None:
        """记录 WARNING 级别日志

        Args:
            message: 日志消息（支持格式化）
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: object, **kwargs: object) -> None:
        """记录 ERROR 级别日志

        Args:
            message: 日志消息（支持格式化）
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self._logger.error(message, *args, **kwargs)

    def critical(self, message: str, *args: object, **kwargs: object) -> None:
        """记录 CRITICAL 级别日志

        Args:
            message: 日志消息（支持格式化）
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self._logger.critical(message, *args, **kwargs)

    def exception(self, message: str, *args: object, exc_info: bool = True, **kwargs: object) -> None:
        """记录异常日志（自动包含堆栈信息）

        Args:
            message: 日志消息
            *args: 格式化参数
            exc_info: 是否包含异常信息，默认为 True
            **kwargs: 额外参数
        """
        self._logger.exception(message, *args, exc_info=exc_info, **kwargs)

    @property
    def tag(self) -> LogTag:
        """获取当前日志标签"""
        return self._tag


# =====================================================
# 全局日志记录器缓存
# =====================================================

_logger_instances: dict[LogTag, VideoCrawlerLogger] = {}


# =====================================================
# 日志初始化与获取函数
# =====================================================

def get_logger(tag: LogTag) -> VideoCrawlerLogger:
    """获取指定标签的日志记录器

    单例模式，同一标签只创建一个实例。

    Args:
        tag: 日志标签枚举

    Returns:
        VideoCrawlerLogger 实例
    """
    if tag not in _logger_instances:
        _logger_instances[tag] = VideoCrawlerLogger(tag)
    return _logger_instances[tag]


def get_crawler_logger() -> VideoCrawlerLogger:
    """获取爬虫模块日志记录器

    Returns:
        crawler 标签的 VideoCrawlerLogger 实例
    """
    return get_logger(LogTag.CRAWLER)


def get_download_logger() -> VideoCrawlerLogger:
    """获取下载模块日志记录器

    Returns:
        download 标签的 VideoCrawlerLogger 实例
    """
    return get_logger(LogTag.DOWNLOAD)


def get_translate_logger() -> VideoCrawlerLogger:
    """获取翻译模块日志记录器

    Returns:
        translate 标签的 VideoCrawlerLogger 实例
    """
    return get_logger(LogTag.TRANSLATE)


def get_error_logger() -> VideoCrawlerLogger:
    """获取错误日志记录器

    Returns:
        error 标签的 VideoCrawlerLogger 实例
    """
    return get_logger(LogTag.ERROR)


# =====================================================
# 日志系统初始化
# =====================================================

def init_logger(log_level: Optional[str] = None) -> None:
    """初始化日志系统

    配置 Loguru 的 sink，设置分文件输出和控制台输出。
    应在程序启动时调用一次。

    Args:
        log_level: 日志级别（DEBUG/INFO/WARNING/ERROR），
                   若为 None 则从配置文件读取
    """
    # 获取日志级别
    if log_level is None:
        try:
            config = config_loader.load_config()
            log_level = config.get("log", {}).get("log_level", "INFO")
        except Exception:
            log_level = "INFO"

    # 移除默认的控制台 sink
    logger.remove()

    def _ensure_tag(record: dict) -> bool:
        """给没 .bind(tag=...) 的日志补默认 tag='-'，避免 KeyError 炸 handler"""
        if "tag" not in record["extra"]:
            record["extra"]["tag"] = "-"
        return True

    # 配置控制台输出（所有级别）
    # PyInstaller --windowed / console=False 打包后 sys.stdout/sys.stderr 为 None，
    # loguru 直接 add(None, ...) 会抛 TypeError。此处做 None 防御。
    _console_sink = sys.stdout if sys.stdout is not None else (
        sys.__stdout__ if hasattr(sys, "__stdout__") and sys.__stdout__ is not None else None
    )
    if _console_sink is not None:
        logger.add(
            _console_sink,
            format=_CONSOLE_FORMAT,
            level=log_level,
            colorize=True,
            enqueue=True,
            filter=_ensure_tag,
        )

    # 配置各模块日志文件输出
    for tag in LogTag:
        logger.add(
            _get_log_file_path(tag),
            format=_FILE_FORMAT,
            level=log_level,
            colorize=False,
            enqueue=True,
            **_ROTATION_CONFIG,
            filter=lambda record, tag=tag: record["extra"].get("tag") == tag.display_name,
        )

    # 兜底 sink：把没 .bind(tag=...) 的模块日志也写到 crawler.log
    # （比如 publish 模块用 from loguru import logger 没 bind tag）
    _KNOWN_TAGS = {t.display_name for t in LogTag}

    def _fallback_filter(record: dict) -> bool:
        tag = record.get("extra", {}).get("tag")
        return tag not in _KNOWN_TAGS

    logger.add(
        _get_log_file_path(LogTag.CRAWLER),
        format=_FILE_FORMAT,
        level=log_level,
        colorize=False,
        enqueue=True,
        **_ROTATION_CONFIG,
        filter=_fallback_filter,
    )


# =====================================================
# 全局便捷函数（向后兼容/快速使用）
# =====================================================

def log_crawler(message: str, level: str = "INFO") -> None:
    """便捷函数：记录爬虫模块日志

    Args:
        message: 日志消息
        level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    """
    _log_by_level(get_crawler_logger(), message, level)


def log_download(message: str, level: str = "INFO") -> None:
    """便捷函数：记录下载模块日志

    Args:
        message: 日志消息
        level: 日志级别
    """
    _log_by_level(get_download_logger(), message, level)


def log_translate(message: str, level: str = "INFO") -> None:
    """便捷函数：记录翻译模块日志

    Args:
        message: 日志消息
        level: 日志级别
    """
    _log_by_level(get_translate_logger(), message, level)


def log_error(message: str, level: str = "ERROR") -> None:
    """便捷函数：记录错误日志

    Args:
        message: 日志消息
        level: 日志级别
    """
    _log_by_level(get_error_logger(), message, level)


def _log_by_level(logger_inst: VideoCrawlerLogger, message: str, level: str) -> None:
    """根据级别调用对应的日志方法

    Args:
        logger_inst: 日志记录器实例
        message: 日志消息
        level: 日志级别
    """
    level = level.upper()
    if level == "DEBUG":
        logger_inst.debug(message)
    elif level == "INFO":
        logger_inst.info(message)
    elif level == "WARNING":
        logger_inst.warning(message)
    elif level == "ERROR":
        logger_inst.error(message)
    elif level == "CRITICAL":
        logger_inst.critical(message)
    else:
        logger_inst.info(message)
