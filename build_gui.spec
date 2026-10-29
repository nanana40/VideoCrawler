# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — VideoCrawler GUI 版

入口：main_gui.py（PySide6 桌面应用）
输出：dist_gui/VideoCrawler/VideoCrawler.exe  （目录模式，双击运行）
"""
import os, sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all

block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH))

# ============================================================
# hiddenimports
# ============================================================
hiddenimports = []

# 项目内部模块
for pkg in ["core", "utils", "gui"]:
    pkg_dir = os.path.join(PROJECT_ROOT, pkg)
    if os.path.isdir(pkg_dir):
        hiddenimports.extend(collect_submodules(pkg))

# PySide6 — collect_all 一网打尽（hiddenimports + datas）
pyside6_datas, pyside6_bins, pyside6_hidden = collect_all("PySide6")
hiddenimports.extend(pyside6_hidden)

# 第三方关键依赖
hiddenimports += [
    "faster_whisper", "faster_whisper.transcribe", "faster_whisper.tokenizer",
    "faster_whisper.vad", "ctranslate2", "onnxruntime", "av",
    "google.genai", "google.genai.types", "google.genai.client",
    "curl_cffi", "yt_dlp", "yt_dlp.extractor", "yt_dlp.downloader",
    "apsw", "apscheduler", "apscheduler.schedulers", "apscheduler.triggers",
    "watchdog", "watchdog.observers",
    "loguru", "pydantic", "cryptography", "requests",
    "PIL", "yaml", "lxml", "bs4", "rich",
    "huggingface_hub", "tokenizers",
]
hiddenimports = list(dict.fromkeys(hiddenimports))

# ============================================================
# datas
# ============================================================
datas = []

# 项目内部模块
for d in ["core", "utils", "gui", "resources"]:
    src = os.path.join(PROJECT_ROOT, d)
    if os.path.isdir(src):
        datas.append((src, d))

# PySide6 资源（collect_all 提供）
datas.extend(pyside6_datas)

# yt-dlp 数据
try:
    import yt_dlp as _y
    _y_dir = os.path.dirname(_y.__file__)
    for sub in ["js", "extractor", "downloader"]:
        p = os.path.join(_y_dir, sub)
        if os.path.isdir(p):
            datas.append((p, f"yt_dlp/{sub}"))
except ImportError:
    pass

# ctranslate2 / onnxruntime / faster-whisper 的 .dll/.pyd
for mod_name in ["faster_whisper", "ctranslate2", "onnxruntime"]:
    try:
        mod = __import__(mod_name)
        mod_dir = os.path.dirname(mod.__file__)
        for root, dirs, files in os.walk(mod_dir):
            for f in files:
                if f.endswith((".json", ".bin", ".pb", ".task", ".dll", ".pyd", ".so")):
                    src = os.path.join(root, f)
                    rel = os.path.relpath(os.path.dirname(src), mod_dir)
                    if rel == ".":
                        rel = ""
                    datas.append((src, f"{mod_name}/{rel}"))
    except ImportError:
        pass

# ============================================================
# binaries
# ============================================================
binaries = list(pyside6_bins)

# ============================================================
# excludes — 大幅减小体积
# ============================================================
excludes = [
    # GUI 不需要的 WebUI 栈
    "gradio", "gradio_client", "hf_gradio", "safehttpx",
    "uvicorn", "fastapi", "starlette", "pydantic_settings",
    # 竞品 GUI 框架（PySide6 已选定）
    "PyQt5", "PyQt6", "PySide2",
    # 重量级 ML 框架（faster-whisper 用 ctranslate2 就够了）
    "torch", "torchvision", "torchaudio",
    "tensorflow", "keras",
    "matplotlib", "scipy", "sklearn", "seaborn", "pandas",
    # 各种测试 / 文档工具
    "unittest", "doctest", "pydoc", "test", "tests", "lib2to3",
    "sphinx", "docutils", "pytest",
    # 其他不需要的
    "tkinter", "IDLE", "xmlrpc", "pipes",
]

# ============================================================
# Analysis
# ============================================================
a = Analysis(
    [os.path.join(PROJECT_ROOT, "main_gui.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(PROJECT_ROOT, "runtime_hook.py")],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoCrawler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # ← GUI 版不弹黑窗口（双击启动无控制台）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VideoCrawler",
)
