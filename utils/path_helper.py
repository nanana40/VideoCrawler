"""
全局路径工具模块
统一管理所有文件路径，自动适配开发环境与 Nuitka 打包后环境
所有业务代码禁止硬编码路径，统一通过本模块获取
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional


def _get_app_root() -> Path:
    """获取程序根目录（自动识别开发/打包环境）

    Nuitka 打包后 sys.frozen 为 True，
    onefile 模式下使用 sys._MEIPASS 临时解压目录，
    但业务数据文件应与 exe 同目录，因此统一取 exe/脚本所在目录
    """
    if getattr(sys, "frozen", False):
        # Nuitka / PyInstaller 打包环境
        return Path(sys.executable).parent
    # 开发环境：取当前文件的上两级目录（utils/path_helper.py -> 项目根）
    return Path(__file__).resolve().parent.parent


# 项目根目录（单例，全局唯一）
APP_ROOT: Path = _get_app_root()


def _ensure_dir(path: Path) -> Path:
    """确保目录存在，不存在则自动创建

    Args:
        path: 目录路径

    Returns:
        传入的路径（方便链式调用）
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


# =====================================================
# 核心目录路径
# =====================================================

def get_resources_dir() -> Path:
    """获取静态资源目录"""
    return _ensure_dir(APP_ROOT / "resources")


def get_bin_dir() -> Path:
    """获取外置二进制目录（ffmpeg/yt-dlp）"""
    return _ensure_dir(APP_ROOT / "bin")


def get_data_dir() -> Path:
    """获取数据目录（数据库等）"""
    return _ensure_dir(APP_ROOT / "data")


def get_tmp_dir() -> Path:
    """获取临时文件目录（运行时缓存，启动自动清理）"""
    return _ensure_dir(APP_ROOT / "tmp")


def get_output_dir() -> Path:
    """获取成品视频输出目录"""
    return _ensure_dir(APP_ROOT / "output")


def get_logs_dir() -> Path:
    """获取日志目录"""
    return _ensure_dir(APP_ROOT / "logs")


def get_translate_queue_dir() -> Path:
    """获取待翻译字幕中转目录"""
    return _ensure_dir(APP_ROOT / "translate_queue")


def get_finished_sub_dir() -> Path:
    """获取翻译完成字幕缓存目录"""
    return _ensure_dir(APP_ROOT / "finished_sub")


def get_tests_dir() -> Path:
    """获取单元测试目录"""
    return _ensure_dir(APP_ROOT / "tests")


# =====================================================
# 配置文件路径
# =====================================================

def get_config_path() -> Path:
    """获取明文业务配置文件路径（根目录 config.yaml）"""
    return APP_ROOT / "config.yaml"


def get_secret_config_path() -> Path:
    """获取加密密钥配置文件路径（api_secret.yaml.enc）"""
    return APP_ROOT / "api_secret.yaml.enc"


# =====================================================
# 数据库路径
# =====================================================

def get_db_path() -> Path:
    """获取 SQLite 数据库文件路径"""
    return get_data_dir() / "video_tasks.db"


def get_schema_path() -> Path:
    """获取建表 SQL 脚本路径"""
    return get_resources_dir() / "schema.sql"


# =====================================================
# 二进制工具路径
# =====================================================

def get_ffmpeg_path() -> Path:
    """获取 ffmpeg 可执行文件路径"""
    return get_bin_dir() / "ffmpeg.exe"


def get_ytdlp_path() -> Path:
    """获取 yt-dlp 可执行文件路径"""
    return get_bin_dir() / "yt-dlp.exe"


# =====================================================
# 日志文件路径
# =====================================================

def get_log_file(tag: str) -> Path:
    """根据日志标签获取对应日志文件路径

    Args:
        tag: 日志标签（crawler/download/translate/error）

    Returns:
        日志文件绝对路径
    """
    return get_logs_dir() / f"{tag}.log"


# =====================================================
# 临时文件工具
# =====================================================

def make_tmp_file(suffix: str = "", prefix: str = "tmp_") -> Path:
    """在 tmp 目录下创建唯一临时文件名（不实际创建文件）

    Args:
        suffix: 文件名后缀
        prefix: 文件名前缀

    Returns:
        临时文件路径
    """
    tmp_dir = get_tmp_dir()
    fd, path_str = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=str(tmp_dir))
    os.close(fd)
    return Path(path_str)


def clear_tmp_dir() -> None:
    """清理临时目录下的所有文件（程序启动时调用）"""
    tmp_dir = get_tmp_dir()
    if not tmp_dir.exists():
        return
    for item in tmp_dir.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item, ignore_errors=True)
        except OSError:
            # 单个文件删除失败不影响整体清理
            continue


# =====================================================
# 运行环境检测
# =====================================================

def is_frozen() -> bool:
    """是否为打包后的运行环境

    Returns:
        True 表示 Nuitka 打包环境，False 表示开发环境
    """
    return getattr(sys, "frozen", False)


def get_runtime_info() -> dict[str, object]:
    """获取当前运行环境信息（调试用）

    Returns:
        包含环境信息的字典
    """
    return {
        "frozen": is_frozen(),
        "app_root": str(APP_ROOT),
        "python_version": sys.version,
        "platform": sys.platform,
    }
