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
    """获取程序安装根目录（只读：bin/models/tools 等，自动识别开发/打包环境）

    打包环境下：返回 exe 所在目录（安装目录，普通用户通常无写权限）
    开发环境：返回项目根目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_resource_root() -> Path:
    """获取只读资源根目录

    PyInstaller onedir 模式下，spec 里声明的 datas 会被放到
    sys._MEIPASS（即 _internal/），需要从这里读取 schema.sql 等只读资源。
    其他情况（开发环境或 Nuitka）与 APP_ROOT 相同。
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# 程序根（只读：bin/models/tools；打包后为 exe 所在安装目录）
APP_ROOT: Path = _get_app_root()

# 只读资源根（schema.sql、Python 模块等 PyInstaller 打包进去的静态资源）
RESOURCE_ROOT: Path = _get_resource_root()


def _get_data_root() -> Path:
    """获取用户数据根目录（可写，自动识别开发/打包环境）

    优先级：
        1. 环境变量 VC_DATA_ROOT（测试/便携模式可指定）
        2. 打包后：%LOCALAPPDATA%\\VideoCrawler（普通用户必可写）
        3. 开发环境：项目根目录（与旧版行为一致，零迁移成本）
    """
    env = os.environ.get("VC_DATA_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else (Path.home() / "AppData" / "Local")
        return root / "VideoCrawler"
    return Path(__file__).resolve().parent.parent


def _ensure_dir(path: Path) -> Path:
    """确保目录存在，不存在则自动创建

    Args:
        path: 目录路径

    Returns:
        传入的路径（方便链式调用）
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


# 用户数据根（可写：config、数据库、logs、output、tmp、加密盐等）
APP_DATA_ROOT: Path = _ensure_dir(_get_data_root())


# =====================================================
# 核心目录路径
# =====================================================

def get_resources_dir() -> Path:
    """获取只读静态资源目录（schema.sql 等）"""
    return RESOURCE_ROOT / "resources"


def get_bin_dir() -> Path:
    """获取外置二进制目录（ffmpeg/yt-dlp）"""
    return _ensure_dir(APP_ROOT / "bin")


def get_data_dir() -> Path:
    """获取数据目录（数据库等）"""
    return _ensure_dir(APP_DATA_ROOT / "data")


def get_cookies_file_path() -> Path:
    """获取手动导出的 cookies 文件路径（Netscape 格式）。

    当 Edge/Chrome 等浏览器使用 v20 加密（yt-dlp 暂不支持）或运行时锁文件时，
    用户可手动导出 cookies 文件放到此路径，覆盖自动探测。
    """
    return get_data_dir() / "browser_cookies.txt"


def get_tmp_dir() -> Path:
    """获取临时文件目录（运行时缓存，启动自动清理）"""
    return _ensure_dir(APP_DATA_ROOT / "tmp")


def get_output_dir() -> Path:
    """获取成品视频输出目录"""
    return _ensure_dir(APP_DATA_ROOT / "output")


def get_logs_dir() -> Path:
    """获取日志目录"""
    return _ensure_dir(APP_DATA_ROOT / "logs")


def get_translate_queue_dir() -> Path:
    """获取待翻译字幕中转目录"""
    return _ensure_dir(APP_DATA_ROOT / "translate_queue")


def get_finished_sub_dir() -> Path:
    """获取翻译完成字幕缓存目录"""
    return _ensure_dir(APP_DATA_ROOT / "finished_sub")


def get_tests_dir() -> Path:
    """获取单元测试目录"""
    return _ensure_dir(APP_ROOT / "tests")


def get_models_dir() -> Path:
    """获取模型文件存放目录（ASR 模型等）"""
    return _ensure_dir(APP_ROOT / "models")


def get_asr_model_dir() -> Path:
    """获取 ASR 语音识别模型存放目录（faster-whisper 模型）"""
    return _ensure_dir(APP_ROOT / "models" / "asr")


# =====================================================
# 配置文件路径
# =====================================================

def get_config_path() -> Path:
    """获取明文业务配置文件路径（用户数据目录 config.yaml）"""
    return APP_DATA_ROOT / "config.yaml"


def get_secret_config_path() -> Path:
    """获取加密密钥配置文件路径（api_secret.yaml.enc）"""
    return APP_DATA_ROOT / "api_secret.yaml.enc"


def get_crypto_salt_path() -> Path:
    """获取本地加密盐文件路径（必须与 api_secret.yaml.enc 同目录）"""
    return APP_DATA_ROOT / ".crypto_salt"


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
    """获取 ffmpeg 可执行文件路径
    
    查找顺序：
        1. bin/ffmpeg.exe
        2. bin/ffmpeg/bin/ffmpeg.exe
        3. bin/ffmpeg-*/bin/ffmpeg.exe
    """
    bin_dir = get_bin_dir()
    
    # 1. 直接在 bin 目录下
    direct_path = bin_dir / "ffmpeg.exe"
    if direct_path.exists():
        return direct_path
    
    # 2. bin/ffmpeg/bin/ffmpeg.exe
    nested_path = bin_dir / "ffmpeg" / "bin" / "ffmpeg.exe"
    if nested_path.exists():
        return nested_path
    
    # 3. bin/ffmpeg-*/bin/ffmpeg.exe（通配符匹配）
    if bin_dir.exists():
        for item in bin_dir.iterdir():
            if item.is_dir() and item.name.startswith("ffmpeg"):
                candidate = item / "bin" / "ffmpeg.exe"
                if candidate.exists():
                    return candidate
    
    # 默认返回直接路径（兼容旧逻辑）
    return direct_path


def get_ytdlp_path() -> Path:
    """获取 yt-dlp 可执行文件路径
    
    查找顺序：
        1. bin/yt-dlp.exe
        2. 系统 PATH 中的 yt-dlp
    """
    import shutil
    
    bin_dir = get_bin_dir()
    direct_path = bin_dir / "yt-dlp.exe"
    if direct_path.exists():
        return direct_path
    
    path_found = shutil.which('yt-dlp')
    if path_found:
        return Path(path_found)
    
    return direct_path


def get_node_path() -> Path:
    """获取 Node.js 可执行文件路径

    查找顺序：
        1. 系统 PATH 中的 node（ensure_tools_in_path 注入的便携版优先）
        2. bin/nodejs/node.exe（便携版）
        3. tools/nodejs/node.exe（备用位置）
    找不到时返回一个假设的路径（exists() 会是 False），调用方自行判空。
    """
    import shutil

    which = shutil.which("node")
    if which:
        return Path(which)

    candidates = [
        APP_ROOT / "bin" / "nodejs" / "node.exe",
        APP_ROOT / "bin" / "nodejs" / "node",
        APP_ROOT / "tools" / "nodejs" / "node.exe",
        APP_ROOT / "tools" / "nodejs" / "node",
    ]
    for c in candidates:
        if c.exists():
            return c

    return candidates[0]


def ensure_tools_in_path() -> None:
    """将 ffmpeg、yt-dlp、nodejs、deno 所在目录添加到系统 PATH
    
    确保 Whisper、yt-dlp 等工具能找到 ffmpeg / JS runtime。
    """
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path.exists():
        ffmpeg_dir = str(ffmpeg_path.parent)
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    # Node.js (yt-dlp 首选 JS runtime) — 便携版放在 Vc/bin/nodejs
    node_dir = APP_ROOT / "bin" / "nodejs"
    if node_dir.exists():
        node_str = str(node_dir)
        if node_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = node_str + os.pathsep + os.environ.get("PATH", "")

    # Deno (yt-dlp JS runtime) — 放在项目 Vc/tools/deno
    deno_dir = APP_ROOT / "tools" / "deno"
    if deno_dir.exists():
        deno_str = str(deno_dir)
        if deno_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = deno_str + os.pathsep + os.environ.get("PATH", "")


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
        "data_root": str(APP_DATA_ROOT),
        "resource_root": str(RESOURCE_ROOT),
        "meipass": getattr(sys, "_MEIPASS", None),
        "executable": sys.executable,
        "python_version": sys.version,
        "platform": sys.platform,
    }
