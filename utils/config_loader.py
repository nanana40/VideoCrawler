"""
配置文件加载模块

负责加载 config.yaml 配置文件，提供全局配置访问能力。
配置路径通过 path_helper 获取，自动适配开发/打包环境。
"""

import yaml
from typing import Optional, Dict, Any

from .path_helper import get_config_path


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载配置文件

    Args:
        config_path: 配置文件路径，若为 None 则使用默认路径

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: YAML 解析错误
    """
    if config_path is None:
        config_path = str(get_config_path())

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"YAML 解析错误: {e}")
    except Exception as e:
        raise RuntimeError(f"加载配置文件失败: {e}")


def get_config_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """获取嵌套配置值

    Args:
        config: 配置字典
        key_path: 键路径，用点分隔，如 "crawler.request_delay"
        default: 默认值

    Returns:
        配置值，若路径不存在则返回默认值
    """
    keys = key_path.split(".")
    value = config
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default


def get_crawler_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取爬虫配置

    Args:
        config: 配置字典

    Returns:
        爬虫配置子字典
    """
    return config.get("crawler", {})


def get_download_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取下载配置

    Args:
        config: 配置字典

    Returns:
        下载配置子字典
    """
    return config.get("download", {})


def get_db_buffer_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取数据库缓冲配置

    Args:
        config: 配置字典

    Returns:
        数据库缓冲配置子字典
    """
    return config.get("db_buffer", {})


def get_subtitle_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取字幕翻译配置

    Args:
        config: 配置字典

    Returns:
        字幕翻译配置子字典
    """
    return config.get("subtitle", {})


def get_scheduler_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取调度器配置

    Args:
        config: 配置字典

    Returns:
        调度器配置子字典
    """
    return config.get("scheduler", {})


def get_log_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取日志配置

    Args:
        config: 配置字典

    Returns:
        日志配置子字典
    """
    return config.get("log", {})


def get_classify_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取 AI 分类配置

    Args:
        config: 配置字典

    Returns:
        AI 分类配置子字典
    """
    return config.get("classify", {})
