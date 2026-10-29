"""
PageWriter — 第 4 页：文案生成

让用户选择：
  - 社交媒体平台（小红书 / 微博 / 知乎）
  - 文案风格（口语学习 / 应试学习）
  - 从字幕中选词、复制

调用 AIWriter 走 Groq → GLM 降级链。
"""

import os
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QComboBox, QLabel, QProgressBar, QMessageBox,
    QTextEdit, QRadioButton, QButtonGroup, QCheckBox,
)

from ..task_manager import TaskManager
from ..theme import PALETTE


class _SelectableTextEdit(QTextEdit):
    """可选词复制的文本框 — 重写 mouseReleaseEvent，方便用户选中好词好句"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(False)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        cursor = self.textCursor()
        if cursor.hasSelection():
            self.parent()._on_word_selected(cursor.selectedText())


class PageWriter(QWidget):
    """文案生成页"""

    _sig_gen_content = Signal(str)
    _sig_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_content: str = ""
        self._setup_ui()
        TaskManager.instance().register_observer(self._on_running_changed)
        QTimer.singleShot(150, self._inherit_context)

        self._sig_gen_content.connect(self._on_gen_content)
        self._sig_finished.connect(self._on_finished)

    def _on_running_changed(self, running: bool) -> None:
        self._gen_btn.setEnabled(not running)

    def _on_gen_content(self, content: str) -> None:
        self._current_content = content
        self._preview.setPlainText(content)

    def _on_finished(self) -> None:
        self._set_running(False)
        self._show_progress(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ---- 参数 ----
        param_group = QGroupBox("文案生成参数")
        form = QFormLayout(param_group)

        self._platform = QComboBox()
        self._platform.addItem("📕 小红书 (xiaohongshu)", "xiaohongshu")
        self._platform.addItem("📢 微博 (weibo)", "weibo")
        self._platform.addItem("💡 知乎 (zhihu)", "zhihu")
        self._platform.setCurrentIndex(0)
        form.addRow("社交媒体平台:", self._platform)

        style_row = QHBoxLayout()
        self._style_oral = QRadioButton("🗣 口语学习")
        self._style_exam = QRadioButton("📝 应试学习")
        self._style_both = QRadioButton("🗣 + 📝 两种都生成（推荐）")
        self._style_both.setChecked(True)
        self._style_bg = QButtonGroup(self)
        self._style_bg.addButton(self._style_oral, 0)
        self._style_bg.addButton(self._style_exam, 1)
        self._style_bg.addButton(self._style_both, 2)
        style_row.addWidget(self._style_oral)
        style_row.addWidget(self._style_exam)
        style_row.addWidget(self._style_both)
        style_row.addStretch(1)
        style_wrap = QWidget()
        style_wrap.setLayout(style_row)
        form.addRow("风格:", style_wrap)

        self._analyze_check = QCheckBox("启用视频分析（解析字幕内容 + 生成深度点评）")
        self._analyze_check.setChecked(True)
        form.addRow("", self._analyze_check)

        root.addWidget(param_group)

        # ---- 生成按钮 ----
        action_row = QHBoxLayout()
        action_row.addStretch(1)

        self._gen_btn = QPushButton("✨ 生成文案")
        self._gen_btn.setCursor(Qt.PointingHandCursor)
        self._gen_btn.setObjectName("PrimaryBtn")
        self._gen_btn.clicked.connect(self._on_generate)
        action_row.addWidget(self._gen_btn)
        root.addLayout(action_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        root.addWidget(self._progress)

        # ---- 预览 + 选词 ----
        preview_group = QGroupBox("📄 文案预览（选中文本即可复制）")
        preview_layout = QVBoxLayout(preview_group)

        self._preview = _SelectableTextEdit()
        self._preview.setFont(QFont("Microsoft YaHei", 11))
        self._preview.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['bg_input']}; color: {PALETTE['text_primary']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; padding: 12px; font-family: 'Microsoft YaHei'; }}"
        )
        self._preview.setPlaceholderText("点击「生成文案」后，结果将显示在这里。\n你可以直接用鼠标选中任何文字，按 Ctrl+C 复制。")
        preview_layout.addWidget(self._preview, 1)

        # 选中文本时自动复制
        hint_row = QHBoxLayout()
        self._selected_label = QLabel("✅ 选中任意文字后，将自动复制到剪贴板")
        self._selected_label.setStyleSheet(f"color: {PALETTE['text_secondary']};")
        hint_row.addWidget(self._selected_label)

        copy_btn = QPushButton("📋 复制全部")
        copy_btn.clicked.connect(self._copy_all)
        hint_row.addStretch(1)
        hint_row.addWidget(copy_btn)

        preview_layout.addLayout(hint_row)
        root.addWidget(preview_group, 1)

    # ------------------------------------------------------------------
    # 选词 → 自动复制
    # ------------------------------------------------------------------
    def _on_word_selected(self, text: str) -> None:
        if not text:
            return
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        cb.setText(text)
        self._selected_label.setText(f"📋 已复制: {text[:60]}{'...' if len(text) > 60 else ''}")

    def _copy_all(self) -> None:
        text = self._preview.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "暂无可复制的内容。")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self._selected_label.setText(f"📋 已复制全部 {len(text)} 字")
        QMessageBox.information(self, "已复制", "文案已复制到剪贴板！")

    # ------------------------------------------------------------------
    # 继承上下文
    # ------------------------------------------------------------------
    def _inherit_context(self) -> None:
        ctx = TaskManager.instance().context
        if ctx.video_path:
            self._log(f"📥 已加载视频上下文: {os.path.basename(ctx.video_path)}", "INFO")

    # ------------------------------------------------------------------
    # 生成文案
    # ------------------------------------------------------------------
    def _on_generate(self) -> None:
        ctx = TaskManager.instance().context
        platform = self._platform.currentData()
        do_analyze = self._analyze_check.isChecked()

        if self._style_both.isChecked():
            styles: List[str] = ["oral", "exam"]
        else:
            styles = ["oral"] if self._style_oral.isChecked() else ["exam"]

        if TaskManager.instance().is_running():
            QMessageBox.warning(self, "任务进行中", "当前已有任务在执行。")
            return

        self._log(
            f"▶ 开始生成文案: platform={platform}, styles={'+'.join(styles)}, "
            f"video={os.path.basename(ctx.video_path) if ctx.video_path else '(无视频上下文)'}",
            "INFO",
        )

        self._set_running(True)
        self._show_progress(True)
        self._preview.clear()

        def _run():
            all_content: List[str] = []
            for style in styles:
                try:
                    self._log(f"⏳ 正在生成 {style} 风格...", "INFO")
                    content = self._call_writer(platform, style, do_analyze)
                    if content:
                        all_content.append(content)
                    else:
                        self._log(f"{style} 风格返回空内容，跳过", "WARNING")
                except Exception as e:
                    import traceback
                    self._log(f"{style} 风格生成异常: {e}\n{traceback.format_exc()}", "ERROR")

            if all_content:
                combined = "\n\n" + "=" * 40 + "\n\n".join(all_content)
                self._sig_gen_content.emit(combined)
                self._log(f"✅ 全部完成，共 {len(styles)} 种风格，合计 {len(combined)} 字", "SUCCESS")
            else:
                self._log("所有风格均无有效内容", "WARNING")

            self._sig_finished.emit()

        spawn(target=_run, daemon=True).start()

    def _call_writer(self, platform: str, style: str, do_analyze: bool) -> str:
        ctx = TaskManager.instance().context

        subtitles: List[Dict[str, Any]] = []

        # ★ 优先路径 A：直接用 ctx.asr_items（含 source_text/target_text），
        # 绕过 SRT 文件序列化→解析这条容易把译文误识别为原文的链路
        if ctx.asr_items:
            for it in ctx.asr_items:
                src = it.get("source_text", "") or it.get("text", "")
                tgt = it.get("target_text", "") or it.get("translated_text", "")
                if src or tgt:
                    subtitles.append({"text": src, "translated_text": tgt})
            self._log(f"📝 从 ASR 素材直取：{len(subtitles)} 条", "INFO")

        # ★ 兜底路径 B：SRT 文件解析
        if not subtitles and ctx.srt_path and os.path.exists(ctx.srt_path):
            try:
                from utils.srt_parser import parse_subtitle_file, normalize_subtitle_items
                blocks = parse_subtitle_file(ctx.srt_path)
                blocks = normalize_subtitle_items(blocks)
                for b in blocks:
                    src = b.get("text", "")
                    tgt = b.get("translated_text", "")
                    if src or tgt:
                        subtitles.append({"text": src, "translated_text": tgt})
                self._log(f"📝 fallback 从字幕文件加载：{len(subtitles)} 条", "INFO")
            except Exception as e:
                self._log(f"解析字幕文件失败: {e}", "WARNING")

        if not subtitles:
            self._log("⚠ 没有可用字幕素材", "WARNING")
            return ""

        save_dir: Optional[str] = None
        if ctx.video_path and os.path.exists(ctx.video_path):
            save_dir = os.path.dirname(ctx.video_path)
        elif ctx.srt_path and os.path.exists(ctx.srt_path):
            save_dir = os.path.dirname(ctx.srt_path)

        ctx_id = ctx.video_id or (os.path.splitext(os.path.basename(ctx.video_path or ""))[0]
                                  if ctx.video_path else "")
        try:
            from core.copy_writer import generate_copy
            result = generate_copy(
                subtitles=subtitles,
                language=ctx.language,
                video_save_dir=save_dir,
                video_id=ctx_id,
                platform=platform,
                style=style,
                analyze=do_analyze,
            )
            if result:
                self._log(f"✅ 文案生成完成，共 {len(result)} 字", "SUCCESS")
            else:
                self._log("文案生成返回空内容", "WARNING")
            return result
        except Exception as e:
            import traceback
            self._log(f"生成异常: {e}\n{traceback.format_exc()}", "ERROR")
            return ""

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "INFO") -> None:
        from loguru import logger
        logger.log(level.upper(), msg)

    def _set_running(self, running: bool) -> None:
        TaskManager.instance().set_running(running)
        self._gen_btn.setEnabled(not running)

    def _show_progress(self, show: bool) -> None:
        self._progress.setVisible(show)
