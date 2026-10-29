"""
VideoCrawler — PySide6 GUI 入口

启动方式 1（开发）: python main_gui.py
启动方式 2（打包）: dist/VideoCrawler/VideoCrawler.exe

打包的 exe 默认从 dist/_internal 加载模块。
开发模式下，在 exe 同目录放 source_path.txt 指向源项目根目录，
exe 就会从源项目 .py 加载 → 改源码重启即生效，无需重新打包。
"""

import sys
import os

# ============================================================
# 开发模式：让 frozen exe 从源项目 .py 加载
# ============================================================
def _setup_dev_mode() -> None:
    if not getattr(sys, "frozen", False):
        return

    src_dir: str = ""

    # 优先级 1: 环境变量
    src_dir = os.environ.get("VIDEO_CRAWLER_SOURCE", "").strip()

    # 优先级 2: exe 同目录的 source_path.txt
    if not src_dir:
        exe_dir = os.path.dirname(sys.executable)
        pointer = os.path.join(exe_dir, "source_path.txt")
        if os.path.isfile(pointer):
            try:
                src_dir = open(pointer, encoding="utf-8").read().strip()
            except Exception:
                pass

    if src_dir and os.path.isdir(src_dir):
        src_dir = os.path.abspath(src_dir)

        # 清掉 PyInstaller 预装的项目模块（让 import 重新找源项目）
        prefixes = ("core.", "utils.", "gui.", "resources.")
        for k in list(sys.modules.keys()):
            if k == "core" or k == "utils" or k == "gui" or k == "resources":
                del sys.modules[k]
            elif any(k.startswith(p) for p in prefixes):
                del sys.modules[k]

        # 源项目插到 sys.path 最前
        sys.path.insert(0, src_dir)

        # 写标记，方便 force_restart 知道源项目在哪
        os.environ["_VC_DEV_SOURCE"] = src_dir


_setup_dev_mode()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from utils.app_initializer import initialize_app
from gui.main_window import MainWindow
from gui.log_bridge import LogBridge


def main() -> int:
    initialize_app()

    app = QApplication(sys.argv)
    app.setApplicationName("VideoCrawler")
    app.setOrganizationName("VideoCrawler")

    default_font = QFont("Microsoft YaHei", 9)
    app.setFont(default_font)

    bridge = LogBridge.instance()
    bridge.install_sink()

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
