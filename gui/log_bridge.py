"""
loguru → PySide6 信号桥接器

核心思路：loguru.logger.add(sink=callable) 接受任意 callable。
单参数 sink 会收到 loguru 的 Message 对象，Message.record 是原始 record dict。
我们解析 record，然后 emit 一个 Qt 信号，任何 QWidget 都可以 connect 它来实时追加日志。
同时维护一个环形缓冲，供新创建的完整日志窗口回放历史，避免"打开后只有零星几条"。
"""

from typing import Dict, Any, List
from collections import deque
from PySide6.QtCore import QObject, Signal

from .theme import PALETTE


class LogBridge(QObject):
    """loguru → Qt 信号桥（单例）"""

    log_received = Signal(dict)

    _instance: "LogBridge | None" = None

    MAX_HISTORY = 5000  # 最多缓冲 5000 条

    @classmethod
    def instance(cls) -> "LogBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent: "QObject | None" = None) -> None:
        super().__init__(parent)
        self._history: deque[dict] = deque(maxlen=self.MAX_HISTORY)

    def history(self) -> List[dict]:
        """返回当前缓冲的全部历史日志（新到旧）"""
        return list(self._history)

    def install_sink(self) -> None:
        """向 loguru 注册一个 sink，把每条日志桥到 Qt 信号"""
        from loguru import logger

        if hasattr(self, "_sink_id"):
            return

        def _sink(msg) -> None:
            try:
                entry = self._parse_record(msg.record)
                self._history.append(entry)
                self.log_received.emit(entry)
            except Exception:
                # AUDIT-0036: 至少 warning 一下，不然解析失败会静默丢日志
                logger.opt(colors=True).debug(f"<yellow>LogBridge sink 解析异常：{msg}</yellow>")

        # AUDIT-0036: 改 enqueue=True，sink 在独立队列线程执行，不拖慢 worker 线程
        self._sink_id = logger.add(_sink, level="DEBUG", enqueue=True)

    def uninstall_sink(self) -> None:
        from loguru import logger
        if hasattr(self, "_sink_id"):
            try:
                logger.remove(self._sink_id)
            except Exception:
                pass
            del self._sink_id

    @staticmethod
    def _parse_record(record: Dict[str, Any]) -> Dict[str, Any]:
        """把 loguru 的 record dict 解析成 UI 用的结构化 dict"""
        # level 是 RecordLevel 对象，有 .name / .no / .icon 属性
        level_obj = record.get("level")
        level = getattr(level_obj, "name", "INFO") if level_obj else "INFO"

        time_obj = record.get("time")
        time_str = time_obj.strftime("%H:%M:%S") if time_obj else "--:--:--"

        extra = record.get("extra", {}) or {}
        tag = extra.get("tag", "-") if isinstance(extra, dict) else "-"

        msg = record.get("message", "") or ""

        color_map = {
            "DEBUG": PALETTE["log_debug"],
            "INFO": PALETTE["log_info"],
            "SUCCESS": PALETTE["success"],
            "WARNING": PALETTE["log_warn"],
            "ERROR": PALETTE["log_error"],
            "CRITICAL": PALETTE["log_critical"],
        }
        color = color_map.get(level, PALETTE["log_info"])

        return {
            "time": time_str,
            "level": level,
            "tag": tag,
            "message": msg,
            "color": color,
        }
