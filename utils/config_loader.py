"""
配置文件加载模块

负责加载 config.yaml 配置文件，提供全局配置访问能力。
配置路径通过 path_helper 获取，自动适配开发/打包环境。
当 config.yaml 不存在时，自动写入一份带默认值的模板文件。
"""

import os
import yaml
from typing import Optional, Dict, Any

from .path_helper import get_config_path


DEFAULT_CONFIG: Dict[str, Any] = {
    "crawler": {
        "enable_tls_finger": True,
        "request_delay": 2.0,
        "max_crawl_page": 10,
        "ua_pool": [],
        "proxy": "",
    },
    "tiktok_safety": {
        "cookies_from_browser": "chrome",
        "request_delay_min": 3.0,
        "request_delay_max": 5.0,
        "daily_cap_enabled": True,
        "daily_cap": 50,
        "cookie_expire_threshold": 3,
    },
    "download": {"max_download_thread": 3},
    "db_buffer": {"batch_write_size": 50, "flush_interval": 3},
    "subtitle": {
        "mode": "api",
        "api_url": "http://127.0.0.1:7861/api/subtitle",
        "ping_interval": 30,
        "max_concurrent_task": 2,
        "max_task_timeout": 600,
        "file_stable_wait": 2,
        "max_file_wait": 15,
        "target_lang": "zh-CN",
        "sub_format": "srt",
        "force_asr": True,
    },
    "scheduler": {
        "enable_memory_warn": True,
        "memory_threshold_mb": 2048,
        "auto_clear_expire_days": 30,
    },
    "log": {"log_level": "INFO"},
    "classify": {"api_url": "", "cache_ttl": 86400},
    "gemini": {
        "enabled": True,
        "api_key": "",
        "model": "gemini-3-flash-preview",
        "proxy": "",
        "use_youtube_url": False,
        "use_audio_only": True,
        "proofread": False,
    },
    "ai_writer": {
        "enabled": True,
        "api_url": "",
        "api_key": "",
        "max_retries": 8,
        "timeout": 180,
        "model": "",
        "temperature": 0.3,
        "max_tokens": 8000,
    },
    "groq": {
        "enabled": False,
        "api_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_key": "",
        "model": "llama-4-maverick-17b-128e-instruct",
        "timeout": 120,
    },
}


def _write_default(path: str) -> None:
    """将默认配置写入指定路径（含父目录）"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, sort_keys=False)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载配置文件

    若文件不存在则自动生成一份带默认值的模板再加载。

    Args:
        config_path: 配置文件路径，若为 None 则使用默认路径

    Returns:
        配置字典

    Raises:
        yaml.YAMLError: YAML 解析错误
    """
    if config_path is None:
        config_path = str(get_config_path())

    if not os.path.exists(config_path):
        _write_default(config_path)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        _write_default(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"YAML 解析错误: {e}")
    except Exception as e:
        raise RuntimeError(f"加载配置文件失败: {e}")


def save_config(config: Dict[str, Any], config_path: Optional[str] = None) -> None:
    """保存配置字典到 config.yaml（覆盖写入）。

    Args:
        config: 配置字典（完整结构）
        config_path: 配置文件路径，若为 None 则使用默认路径
    """
    if config_path is None:
        config_path = str(get_config_path())
    os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)


def save_subsection(section: str, data: Dict[str, Any], config_path: Optional[str] = None) -> None:
    """只更新配置的某个 section，其他 section 不动。

    Args:
        section: 顶层 section 名（如 "subtitle_style"）
        data: 该 section 的数据字典
        config_path: 配置文件路径，若为 None 则使用默认路径
    """
    cfg = load_config(config_path)
    cfg[section] = data
    save_config(cfg, config_path)


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
