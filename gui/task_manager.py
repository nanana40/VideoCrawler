"""
全局任务管理器

职责：
  1. 标记当前是否有任务在跑（GUI 按钮禁用/启用）
  2. 强制结束：杀掉后台线程 + 清理 tmp 残留
  3. 强制重启：先强制结束 → 清 __pycache__ → importlib.reload → 重新 initialize_app
  4. 跨模块的“脏”状态传递（上一页的文件路径 → 下一页继承）
"""

import os
import sys
import time
import shutil
import threading
import importlib
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field


@dataclass
class SharedContext:
    """跨页面共享的上下文（pipeline 各阶段的产物）"""
    video_path: str = ""          # 下载好的视频文件绝对路径
    video_id: str = ""            # YouTube video id
    language: str = ""            # 源语言
    target_language: str = "zh-CN"
    srt_path: str = ""            # ASR 生成的 SRT 文件
    asr_items: List[Dict] = field(default_factory=list)  # 字幕条目（用于预览）
    final_video_path: str = ""    # 烧录/封装好的成品视频
    custom_audio_path: str = ""   # 用户上传的纯音频文件


class TaskManager:
    """全局单例任务管理器"""

    _instance: Optional["TaskManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._running: bool = False
        self._running_lock = threading.Lock()
        self._threads: List[threading.Thread] = []
        self._threads_lock = threading.Lock()
        self._observers: List[Callable[[bool], None]] = []
        self._observers_lock = threading.Lock()
        self.context = SharedContext()
        self._tmp_files: List[str] = []  # 运行期间产生的临时文件
        self._tmp_dirs: List[str] = []

    @classmethod
    def instance(cls) -> "TaskManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ---------- running 状态 ----------
    def is_running(self) -> bool:
        with self._running_lock:
            return self._running

    def set_running(self, running: bool) -> None:
        with self._running_lock:
            self._running = running
        self._notify_observers(running)

    def register_observer(self, observer: Callable[[bool], None]) -> None:
        """注册 running 状态变化回调（force_stop / set_running 时自动通知）"""
        with self._observers_lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def unregister_observer(self, observer: Callable[[bool], None]) -> None:
        with self._observers_lock:
            if observer in self._observers:
                self._observers.remove(observer)

    def _notify_observers(self, running: bool) -> None:
        with self._observers_lock:
            observers = list(self._observers)
        for cb in observers:
            try:
                cb(running)
            except Exception:
                pass

    def register_thread(self, t: threading.Thread) -> None:
        with self._threads_lock:
            self._threads.append(t)

    def spawn(
        self,
        target: Callable[..., Any],
        *args,
        name: Optional[str] = None,
        daemon: bool = True,
        **kwargs,
    ) -> threading.Thread:
        """AUDIT-0033: 线程创建工厂 — 创建 + 自动 register_thread

        用法:
            t = TaskManager.instance().spawn(_work, arg1, name="download")
            t.start()
        """
        from utils.thread_spawn import spawn as _spawn
        t = _spawn(target, *args, name=name, daemon=daemon, **kwargs)
        self.register_thread(t)
        return t

    def register_tmp_file(self, path: str) -> None:
        self._tmp_files.append(path)

    def register_tmp_dir(self, path: str) -> None:
        self._tmp_dirs.append(path)

    # ---------- 强制结束 ----------
    def force_stop(self, log_fn: Optional[Callable[[str, str], None]] = None) -> str:
        """杀掉所有后台线程 + 清理临时残留。返回执行报告"""
        log = lambda lvl, msg: (log_fn(lvl, msg) if log_fn else None)

        lines: List[str] = []
        lines.append("=== 强制结束任务 ===")

        # 1. 标记停止
        self.set_running(False)

        # 2. 等待后台线程自然结束（最多 5 秒）
        with self._threads_lock:
            threads = list(self._threads)
            self._threads.clear()

        for t in threads:
            if t.is_alive():
                t.join(timeout=5.0)
                if t.is_alive():
                    lines.append(f"  ⚠️ 线程 {t.name} 未在 5s 内退出")
                else:
                    lines.append(f"  ✅ 线程 {t.name} 已退出")

        # 3. 清理 tmp 文件
        cleaned_files = 0
        for f in self._tmp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    cleaned_files += 1
            except Exception:
                pass
        self._tmp_files.clear()

        cleaned_dirs = 0
        for d in self._tmp_dirs:
            try:
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
                    cleaned_dirs += 1
            except Exception:
                pass
        self._tmp_dirs.clear()

        lines.append(f"  🧹 清理临时文件: {cleaned_files} 个")
        lines.append(f"  🧹 清理临时目录: {cleaned_dirs} 个")

        lines.append("=== 强制结束完成 ===")
        report = "\n".join(lines)
        log("WARNING", report)
        return report

    # ---------- 强制重启 ----------
    def force_restart(self, log_fn: Optional[Callable[[str, str], None]] = None) -> None:
        """
        彻底重启进程：force_stop → 清 __pycache__ → 启动新进程 → 当前进程退出。

        不使用 importlib.reload（它对类引用、单例、闭包等场景不可靠）。
        新进程从磁盘重新 import 所有 .py，源码改动 100% 生效。
        """
        import subprocess

        log = lambda lvl, msg: (log_fn(lvl, msg) if log_fn else None)

        # 1. 先停干净
        self.force_stop(log_fn)
        log("INFO", "=== 强制重启：清理缓存 + 启动新进程 ===")

        # 2. 清 __pycache__（源项目 + _MEIPASS 兜底）
        cache_count = 0
        roots: List[str] = []
        dev_src = os.environ.get("_VC_DEV_SOURCE", "").strip()
        if dev_src:
            roots.append(dev_src)
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and meipass not in roots:
            roots.append(meipass)

        for root in roots:
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                if "__pycache__" in dirnames:
                    p = os.path.join(dirpath, "__pycache__")
                    try:
                        shutil.rmtree(p, ignore_errors=True)
                        cache_count += 1
                    except Exception:
                        pass
                    dirnames.remove("__pycache__")
                for fn in filenames:
                    if fn.endswith(".pyc"):
                        try:
                            os.remove(os.path.join(dirpath, fn))
                        except Exception:
                            pass
        log("INFO", f"  ✅ 清理 __pycache__: {cache_count} 个")

        # 3. 构建新进程命令
        if getattr(sys, "frozen", False):
            # PyInstaller exe：启动自己
            new_cmd = [sys.executable]
        else:
            # 开发模式：python main_gui.py
            new_cmd = [sys.executable, os.path.abspath(sys.argv[0])]

        # 4. 启动新进程（独立进程组，不随当前进程退出）
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        try:
            subprocess.Popen(
                new_cmd,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            log("SUCCESS", "  ✅ 新进程已启动，当前进程即将退出")
        except Exception as e:
            log("ERROR", f"  ❌ 启动新进程失败: {e}")
            return

        # 5. 当前进程退出（Qt 正常关闭）
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.quit()
        else:
            sys.exit(0)
