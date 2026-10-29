"""
全局日志面板（精简版）

右侧常驻的只是一个"小窗口"：显示最新一条日志 + 累计条数 + 打开完整日志窗口按钮。
点击「查看全部日志」才弹出独立的 GlobalLogWindow，展示完整历史日志。
两个控件都订阅 LogBridge，完整窗口从创建起就持续累积，因此随时打开都能看到全部内容。
"""

from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel,
)

from .log_bridge import LogBridge
from .theme import PALETTE


class GlobalLogWindow(QWidget):
    """独立完整日志窗口（点击「查看全部日志」打开）"""

    MAX_BLOCKS = 5000

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📋 全局日志（完整）")
        self.resize(760, 520)
        self.setMinimumSize(420, 300)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.NoWrap)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setStyleSheet(
            f"QTextEdit {{ background-color: {PALETTE['bg_input']}; color: {PALETTE['text_primary']}; border: 1px solid {PALETTE['border']}; }}"
        )

        self._auto_scroll = True
        self._scroll_btn = QPushButton("📜 自动滚动: 开")
        self._scroll_btn.setCheckable(True)
        self._scroll_btn.setChecked(True)
        self._scroll_btn.clicked.connect(self._toggle_scroll)

        self._clear_btn = QPushButton("🗑 清空")
        self._clear_btn.clicked.connect(self._text.clear)

        self._count_label = QLabel("0 条")
        self._count_label.setStyleSheet(f"color: {PALETTE['text_secondary']};")

        header = QHBoxLayout()
        header.addWidget(QLabel("📋 全局日志"))
        header.addStretch(1)
        header.addWidget(self._count_label)
        header.addWidget(self._scroll_btn)
        header.addWidget(self._clear_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addLayout(header)
        root.addWidget(self._text, 1)

        self._log_count = 0

        bridge = LogBridge.instance()
        # 先回放已有历史缓冲（5000 条以内），再订阅新信号
        self._replay_history(bridge.history())
        bridge.log_received.connect(self._on_log_received)

    def _replay_history(self, history) -> None:
        """把桥接器已缓冲的历史日志一次性灌进文本框"""
        if not history:
            return
        # 回放时用一次性追加（避免每条都触发额外的光标移动）
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.beginEditBlock()
        for entry in history:
            ts = entry.get("time", "--:--:--")
            lvl = entry.get("level", "INFO")
            tag = entry.get("tag", "-")
            msg = entry.get("message", "")
            color_hex = entry.get("color", PALETTE["log_info"])
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color_hex))
            cursor.insertText(f"[{ts}] [{lvl}] [{tag}] ", fmt)
            msg_fmt = QTextCharFormat()
            msg_fmt.setForeground(QColor(color_hex))
            msg_fmt.setFontWeight(QFont.Normal)
            cursor.insertText(msg + "\n", msg_fmt)
        cursor.endEditBlock()
        self._text.setTextCursor(cursor)
        self._log_count = len(history)
        self._count_label.setText(f"{self._log_count} 条")
        if self._auto_scroll:
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())
        self._trim_if_needed()

    def _toggle_scroll(self) -> None:
        self._auto_scroll = self._scroll_btn.isChecked()
        self._scroll_btn.setText(
            "📜 自动滚动: 开" if self._auto_scroll else "📜 自动滚动: 关"
        )

    def _on_log_received(self, entry: dict) -> None:
        ts = entry.get("time", "--:--:--")
        lvl = entry.get("level", "INFO")
        tag = entry.get("tag", "-")
        msg = entry.get("message", "")
        color_hex = entry.get("color", PALETTE["log_info"])

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(f"[{ts}] [{lvl}] [{tag}] ", fmt)
        msg_fmt = QTextCharFormat()
        msg_fmt.setForeground(QColor(color_hex))
        msg_fmt.setFontWeight(QFont.Normal)
        cursor.insertText(msg + "\n", msg_fmt)
        self._text.setTextCursor(cursor)

        self._log_count += 1
        self._count_label.setText(f"{self._log_count} 条")

        if self._auto_scroll:
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())

        self._trim_if_needed()

    def _trim_if_needed(self) -> None:
        doc = self._text.document()
        if doc.blockCount() > self.MAX_BLOCKS:
            cursor = self._text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            for _ in range(doc.blockCount() - self.MAX_BLOCKS):
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()


class GlobalLogPanel(QWidget):
    """右侧常驻的紧凑日志小窗口：最新一条 + 计数 + 「查看全部」按钮"""

    DEFAULT_HEIGHT = 96

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setMaximumHeight(self.DEFAULT_HEIGHT)
        self.setFixedHeight(self.DEFAULT_HEIGHT)

        # 最新消息标签（单行，超宽自动裁剪）
        self._latest = QLabel("尚无日志")
        self._latest.setWordWrap(False)
        self._latest.setFont(QFont("Consolas", 9))
        self._latest.setStyleSheet(
            f"color: {PALETTE['text_primary']}; background-color: {PALETTE['bg_input']}; border: 1px solid {PALETTE['border']};"
            "border-radius: 4px; padding: 4px 6px;"
        )

        self._count_label = QLabel("0 条")
        self._count_label.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px;")

        self._open_btn = QPushButton("↗ 查看全部日志")
        self._open_btn.setToolTip("打开独立完整日志窗口")
        self._open_btn.clicked.connect(self._toggle_full_window)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(QLabel("📋 日志"))
        header.addStretch(1)
        header.addWidget(self._count_label)
        header.addWidget(self._open_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        root.addLayout(header)
        root.addWidget(self._latest, 1)

        self._log_count = 0
        self._full_window: Optional[GlobalLogWindow] = None

        bridge = LogBridge.instance()
        bridge.log_received.connect(self._on_log_received)

    def _on_log_received(self, entry: dict) -> None:
        ts = entry.get("time", "--:--:--")
        lvl = entry.get("level", "INFO")
        msg = entry.get("message", "")
        self._latest.setText(f"[{ts}] [{lvl}] {msg}")
        self._log_count += 1
        self._count_label.setText(f"{self._log_count} 条")

    def _toggle_full_window(self) -> None:
        if self._full_window is None:
            self._full_window = GlobalLogWindow()
        if self._full_window.isVisible():
            self._full_window.hide()
        else:
            self._full_window.showNormal()
            self._full_window.raise_()
            self._full_window.activateWindow()

    def closeEvent(self, event) -> None:
        # 关掉主面板时若完整窗口还开着则一并关闭
        if self._full_window is not None:
            self._full_window.close()
        super().closeEvent(event)