"""
PageRecognize — 第 2 页：语音识别与翻译

流程：
  1. 用户拖入 / 选取音视频文件（或继承自上一页下载的视频）
  2. 选择源语言 / 目标语言
  3. 点击「开始识别」→ 调用 GeminiTranscriber（自动处理音频提取）
  4. 结果显示在预览文本框
  5. 用户确认后可生成 SRT 文件，询问是否进入下一步
"""

import os
import re
import json
import shutil
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLineEdit, QComboBox, QLabel, QProgressBar,
    QMessageBox, QFileDialog, QTextEdit, QCheckBox, QSplitter,
)

from ..task_manager import TaskManager
from ..theme import PALETTE


VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".ts"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
ALL_EXTS = VIDEO_EXTS | AUDIO_EXTS


class _DropZone(QLineEdit):
    """支持拖拽的文件路径输入框"""

    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setReadOnly(False)
        self.setPlaceholderText("📂 拖拽音视频文件到这里，或点击右侧「浏览」...")

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.splitext(path)[1].lower() in ALL_EXTS:
                self.setText(path)
                self.file_dropped.emit(path)
                e.acceptProposedAction()
                return


class PageRecognize(QWidget):
    """语音识别与翻译页"""

    _sig_recognize_done = Signal(list, str, str, str)
    _sig_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._current_result: Optional[List[Dict[str, Any]]] = None
        self._setup_ui()
        TaskManager.instance().register_observer(self._on_running_changed)
        self._sig_recognize_done.connect(self._on_recognize_done)
        self._sig_finished.connect(self._on_thread_finished)
        QTimer.singleShot(100, self._inherit_context)

    def _on_running_changed(self, running: bool) -> None:
        self._update_start_button()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ---- 文件选取 ----
        file_group = QGroupBox("音视频文件")
        file_layout = QHBoxLayout(file_group)
        self._path_edit = _DropZone()
        self._path_edit.file_dropped.connect(self._on_file_picked)
        file_layout.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("📂 浏览...")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(browse_btn)

        clear_btn = QPushButton("✖")
        clear_btn.setFixedWidth(32)
        clear_btn.clicked.connect(lambda: self._path_edit.clear())
        file_layout.addWidget(clear_btn)

        root.addWidget(file_group)

        # ---- 参数 ----
        param_group = QGroupBox("识别参数")
        form = QFormLayout(param_group)

        self._src_lang = QComboBox()
        self._src_lang.setEditable(True)
        for code, name in [
            ("auto", "自动检测"),
            ("en", "英语"), ("de", "德语"), ("fr", "法语"),
            ("es", "西班牙语"), ("ja", "日语"), ("ko", "韩语"),
            ("zh", "中文"), ("ru", "俄语"), ("it", "意大利语"),
            ("pt", "葡萄牙语"), ("ar", "阿拉伯语"),
        ]:
            self._src_lang.addItem(name, code)
        self._src_lang.setCurrentIndex(0)
        form.addRow("🗣 源语言:", self._src_lang)

        self._tgt_lang = QComboBox()
        self._tgt_lang.addItem("简体中文 (zh-CN)", "zh-CN")
        self._tgt_lang.addItem("英语 (en)", "en")
        self._tgt_lang.addItem("日语 (ja)", "ja")
        self._tgt_lang.setCurrentIndex(0)
        form.addRow("🎯 目标语言:", self._tgt_lang)

        self._proofread_check = QCheckBox("识别完成后进行 AI 辅助校对")
        self._proofread_check.setChecked(False)
        self._proofread_check.setToolTip(
            "Gemini 二次校对字幕：修正识别误差、润色翻译结果（约 +30% token 消耗）"
        )
        form.addRow("", self._proofread_check)

        root.addWidget(param_group)

        # ---- 动作 ----
        action_row = QHBoxLayout()
        action_row.addStretch(1)

        self._start_btn = QPushButton("▶ 开始识别 + 翻译")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setObjectName("PrimaryBtn")
        self._start_btn.clicked.connect(self._on_start_recognize)
        action_row.addWidget(self._start_btn)
        root.addLayout(action_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        root.addWidget(self._progress)

        # ---- 预览 ----
        preview_group = QGroupBox("识别结果预览")
        preview_layout = QVBoxLayout(preview_group)
        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setFontPointSize(10)
        preview_layout.addWidget(self._preview_text)
        root.addWidget(preview_group, 1)

        # ---- 确认区（默认隐藏）----
        self._confirm_widget = QWidget()
        confirm_layout = QHBoxLayout(self._confirm_widget)
        confirm_layout.setContentsMargins(0, 0, 0, 0)

        self._save_srt_btn = QPushButton("💾 保存 SRT 字幕")
        self._save_srt_btn.setCursor(Qt.PointingHandCursor)
        self._save_srt_btn.clicked.connect(self._on_save_srt)

        self._next_btn = QPushButton("➡ 下一步：字幕参数与预览")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setObjectName("PrimaryBtn")
        self._next_btn.clicked.connect(self._on_go_next)

        confirm_layout.addStretch(1)
        confirm_layout.addWidget(self._save_srt_btn)
        confirm_layout.addWidget(self._next_btn)
        self._confirm_widget.hide()
        root.addWidget(self._confirm_widget)

    # ------------------------------------------------------------------
    # 继承上一页上下文
    # ------------------------------------------------------------------
    def _inherit_context(self) -> None:
        ctx = TaskManager.instance().context
        if ctx.video_path and os.path.exists(ctx.video_path):
            self._path_edit.setText(ctx.video_path)
            self._on_file_picked(ctx.video_path)
            self._log(f"📥 已继承上一页文件: {ctx.video_path}", "INFO")
        if ctx.language:
            idx = self._src_lang.findData(ctx.language)
            if idx >= 0:
                self._src_lang.setCurrentIndex(idx)

    def _on_file_picked(self, path: str) -> None:
        if not path or not os.path.exists(path):
            self._log(f"文件不存在: {path}", "WARNING")
            self._path_edit.clear()
            self._update_start_button()
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in ALL_EXTS:
            self._log(f"不支持的文件格式: {ext}", "WARNING")
            self._update_start_button()
            return
        self._path_edit.setText(path)
        self._log(f"📂 已选择文件: {path}", "INFO")
        self._update_start_button()

    def _update_start_button(self) -> None:
        """根据文件 + running 状态刷新开始按钮"""
        has_file = bool(self._path_edit.text().strip()) and os.path.exists(self._path_edit.text().strip())
        not_running = not TaskManager.instance().is_running()
        self._start_btn.setEnabled(has_file and not_running)

    def _browse_file(self) -> None:
        start = os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音视频文件", start,
            "Media (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac);;All (*)",
        )
        if path:
            self._path_edit.setText(path)
            self._on_file_picked(path)

    # ------------------------------------------------------------------
    # 开始识别
    # ------------------------------------------------------------------
    def _on_start_recognize(self) -> None:
        path = self._path_edit.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "文件缺失", "请先选择有效的音视频文件。")
            return

        if TaskManager.instance().is_running():
            QMessageBox.warning(self, "任务进行中", "当前已有任务在执行。")
            return

        src = self._src_lang.currentData() or "auto"
        tgt = self._tgt_lang.currentData() or "zh-CN"
        proofread = self._proofread_check.isChecked()

        self._log(f"▶ 开始识别: {os.path.basename(path)}, src={src}, proofread={proofread}", "INFO")
        self._set_running(True)
        self._show_progress(True)
        self._preview_text.clear()
        self._confirm_widget.hide()

        def _run():
            try:
                # ------ Step 1: 本地 faster-whisper ASR ------
                self._log("🔊 步骤1: 本地 faster-whisper ASR（VAD 激进，时间戳精度高）...", "INFO")
                local_asr = []
                try:
                    from faster_whisper import WhisperModel
                    import os as _os

                    models_dir = _os.path.join(
                        _os.path.dirname(_os.path.abspath(__file__)),
                        "..", "..", "models"
                    )
                    models_dir = _os.path.normpath(models_dir)

                    self._log("  📦 加载 faster-whisper small 模型...", "INFO")
                    whisper_model = WhisperModel(
                        "small", device="auto", compute_type="auto",
                        download_root=models_dir,
                    )

                    whisper_lang = src if src and src != "auto" else None
                    seg_gen, info = whisper_model.transcribe(
                        path, beam_size=5, language=whisper_lang,
                        vad_filter=True,
                        vad_parameters={"min_silence_duration_ms": 500},
                    )
                    for seg in seg_gen:
                        local_asr.append({
                            "start_time": float(seg.start or 0),
                            "end_time": float(seg.end or 0),
                            "text": (seg.text or "").strip(),
                        })
                    self._log(f"  ✅ 本地 ASR 完成: {len(local_asr)} 段, "
                              f"语言={getattr(info, 'language', '?')}", "SUCCESS")
                except Exception as asr_err:
                    self._log(f"  ⚠️ 本地 ASR 失败（降级为纯 Gemini）: {asr_err}", "WARNING")

                # ------ Step 2: Gemini 识别 + 翻译 ------
                self._log("🧠 步骤2: 调用 Gemini", "INFO")

                from core.gemini_engine import GeminiTranscriber
                transcriber = GeminiTranscriber()

                asr_arg = local_asr if local_asr else None
                if asr_arg:
                    self._log(f"  📎 附带本地 ASR 参考 ({len(asr_arg)} 段) → 翻译+精炼", "INFO")
                else:
                    self._log("  ⚠️ 无 ASR 参考 → Gemini 独立识别", "WARNING")

                self._log("📤 上传文件到 Gemini...", "INFO")
                segments = transcriber.transcribe_and_translate(
                    path,
                    source_lang=src,
                    asr_segments=asr_arg,
                )

                if not segments:
                    self._log("Gemini 返回空结果", "ERROR")
                    return

                self._log(f"✅ Gemini 识别+翻译完成，共 {len(segments)} 条字幕", "SUCCESS")

                if proofread:
                    self._log("🔍 进行 AI 辅助校对（第二轮调用）...", "INFO")
                    try:
                        segments = transcriber.proofread_subtitles(
                            path, segments, source_lang=src,
                            asr_segments=local_asr if local_asr else None,
                        )
                        self._log("✅ 校对完成", "SUCCESS")
                    except Exception as e:
                        self._log(f"校对失败，保留原始结果: {e}", "WARNING")

                self._sig_recognize_done.emit(segments, path, src, tgt)

            except Exception as e:
                self._log(f"识别异常: {e}", "ERROR")
                import traceback
                self._log(traceback.format_exc(), "ERROR")
            finally:
                self._sig_finished.emit()

        spawn(target=_run, daemon=True).start()

    def _on_recognize_done(
        self, segments: List[Dict[str, Any]], source_path: str,
        src_lang: str, tgt_lang: str,
    ) -> None:
        self._current_result = segments

        ctx = TaskManager.instance().context
        ctx.video_path = source_path
        ctx.language = src_lang
        ctx.target_language = tgt_lang
        ctx.asr_items = segments

        lines = []
        for i, seg in enumerate(segments):
            start = seg.get("start_time", 0)
            end = seg.get("end_time", 0)
            src_txt = seg.get("source_text", "")
            tgt_txt = seg.get("target_text", "")
            lines.append(f"[{start:7.2f} → {end:7.2f}] {src_txt}")
            if tgt_txt:
                lines.append(f"                → {tgt_txt}")
        self._preview_text.setPlainText("\n".join(lines))

        self._confirm_widget.show()
        self._log(f"📋 识别结果已展示，共 {len(segments)} 条字幕。请确认是否满意。", "INFO")

    # ------------------------------------------------------------------
    # 保存 SRT
    # ------------------------------------------------------------------
    def _on_save_srt(self) -> None:
        if not self._current_result:
            return

        source_path = self._path_edit.text().strip()
        out_dir = os.path.dirname(source_path) if source_path else os.path.expanduser("~")
        base = os.path.splitext(os.path.basename(source_path))[0] if source_path else "subtitles"
        default_name = f"{base}_zh-CN.srt"
        default_path = os.path.join(out_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "保存 SRT 字幕", default_path, "SRT (*.srt)"
        )
        if not path:
            return

        try:
            self._write_srt(self._current_result, path)
            self._log(f"✅ SRT 已保存: {path}", "SUCCESS")

            ctx = TaskManager.instance().context
            ctx.srt_path = path

            QMessageBox.information(
                self, "保存成功",
                f"字幕已保存至：\n{path}\n\n打开所在文件夹？",
            )
            try:
                os.startfile(os.path.dirname(path))  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception as e:
            self._log(f"保存 SRT 失败: {e}", "ERROR")
            QMessageBox.critical(self, "保存失败", str(e))

    @staticmethod
    def _write_srt(segments: List[Dict[str, Any]], path: str) -> None:
        def fmt(t: float) -> str:
            t = max(0.0, float(t))
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int(round((t - int(t)) * 1000))
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        with open(path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start = fmt(seg.get("start_time", 0))
                end = fmt(seg.get("end_time", 0))
                src = seg.get("source_text", "").strip()
                tgt = seg.get("target_text", "").strip()
                if not src and not tgt:
                    continue
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                # ★ 双语输出：永远先写原文 (source_text)，后写译文 (target_text)
                # 即使 src == tgt 也强制写两行（播放器能正确渲染第二行作为译文）
                if src:
                    f.write(src + "\n")
                if tgt:
                    f.write(tgt + "\n")
                f.write("\n")

    # ------------------------------------------------------------------
    # 下一步
    # ------------------------------------------------------------------
    def _on_go_next(self) -> None:
        ctx = TaskManager.instance().context
        if not ctx.srt_path and self._current_result:
            # 自动保存到视频同目录
            source_path = self._path_edit.text().strip()
            if source_path:
                out_dir = os.path.dirname(source_path)
                base = os.path.splitext(os.path.basename(source_path))[0]
                auto_srt = os.path.join(out_dir, f"{base}_zh-CN.srt")
                try:
                    self._write_srt(self._current_result, auto_srt)
                    ctx.srt_path = auto_srt
                    self._log(f"📥 自动保存 SRT: {auto_srt}", "SUCCESS")
                except Exception as e:
                    self._log(f"自动保存失败: {e}", "WARNING")

        mw = self.window()
        if hasattr(mw, "switch_to_tab"):
            mw.switch_to_tab(2)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "INFO") -> None:
        from loguru import logger
        logger.log(level.upper(), msg)

    def _set_running(self, running: bool) -> None:
        TaskManager.instance().set_running(running)
        self._start_btn.setEnabled(not running)

    def _show_progress(self, show: bool) -> None:
        self._progress.setVisible(show)

    def _on_thread_finished(self) -> None:
        self._set_running(False)
        self._show_progress(False)
