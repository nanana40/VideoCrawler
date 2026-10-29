"""PyInstaller runtime hook — 设置 UTF-8 编码环境"""
import os
import sys

# 强制 UTF-8 输出，避免 Windows 控制台 GBK 编码导致 emoji 崩溃
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

# 修复 PyInstaller frozen 环境下的 stdout/stderr
if getattr(sys, "frozen", False):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
