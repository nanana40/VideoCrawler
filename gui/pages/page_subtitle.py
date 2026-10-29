"""
PageSubtitle — 第 3 页：字幕参数 + 可视化预览 + 生成成品

左侧：视频预览 + 字幕叠加（可拖拽）
右侧：字幕参数面板（字号/颜色/位置/双语/输出类型）

输出：
  - MP4 硬烧录（字幕烧进画面，兼容所有播放器）
  - MKV 封装（视频+音频+字幕多条轨道，剪辑软件可编辑）
  - 或两者都输出
"""

import os
import re
import json
import subprocess
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox, QLabel,
    QProgressBar, QMessageBox, QFileDialog, QSplitter, QColorDialog,
    QRadioButton, QButtonGroup, QDoubleSpinBox, QSizePolicy,
)

from ..widgets.video_preview import VideoPreview
from ..task_manager import TaskManager
from ..theme import PALETTE


class PageSubtitle(QWidget):
    """字幕参数选择 + 预览 + 输出"""

    _sig_render_done = Signal(list)
    _sig_render_failed = Signal(str)
    _sig_finished = Signal()
    _sig_progress = Signal(int, str)  # (百分比, 描述)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        TaskManager.instance().register_observer(self._on_running_changed)
        QTimer.singleShot(150, self.refresh_context)

        self._sig_render_done.connect(self._on_render_done)
        self._sig_render_failed.connect(self._on_render_failed_slot)
        self._sig_finished.connect(self._on_finished)
        self._sig_progress.connect(self._on_progress)

        # ★ 加载上次保存的字幕样式参数
        self._load_style_config()

    def _on_running_changed(self, running: bool) -> None:
        self._render_btn.setEnabled(not running)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([860, 420])
        root.addWidget(splitter)

    def _build_left(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self._video_preview = VideoPreview()
        self._video_preview.setMinimumHeight(400)
        self._video_preview.player_error.connect(lambda m: self._log(f"播放器错误: {m}", "ERROR"))
        self._video_preview.player_status.connect(lambda s: None)  # 静默状态变化
        self._video_preview.canvas.pos_changed.connect(self._save_style_config)  # ★ 拖拽结束自动保存
        layout.addWidget(self._video_preview, 1)

        hint = QLabel("💡 提示：可直接在画面中拖拽字幕框调整位置；右侧参数实时生效。")
        hint.setStyleSheet(f"color: {PALETTE['text_secondary']}; padding: 4px 8px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---- 文件来源 ----
        file_group = QGroupBox("📂 文件来源")
        file_layout = QFormLayout(file_group)
        self._video_path_edit = QLineEdit()
        self._video_path_edit.setReadOnly(True)
        file_layout.addRow("视频文件:", self._video_path_edit)

        browse_row = QHBoxLayout()
        browse_video = QPushButton("📂 选择视频")
        browse_video.clicked.connect(self._pick_video)
        browse_srt = QPushButton("📂 选择 SRT")
        browse_srt.clicked.connect(self._pick_srt)
        browse_row.addWidget(browse_video)
        browse_row.addWidget(browse_srt)
        browse_row.addStretch(1)
        file_layout.addRow("", browse_row)

        self._srt_path_edit = QLineEdit()
        self._srt_path_edit.setReadOnly(True)
        file_layout.addRow("SRT 字幕:", self._srt_path_edit)

        layout.addWidget(file_group)

        # ---- 字幕参数 ----
        style_group = QGroupBox("🎨 字幕样式参数")
        style_form = QFormLayout(style_group)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 120)
        self._font_size.setValue(36)
        self._font_size.valueChanged.connect(self._apply_params_preview)
        style_form.addRow("字号 (px):", self._font_size)

        self._primary_color = "#FFFFFF"
        self._primary_btn = QPushButton("白色 ▤")
        self._primary_btn.clicked.connect(lambda: self._pick_color("_primary_color", self._primary_btn))
        style_form.addRow("主文字颜色:", self._primary_btn)

        self._outline_color = "#000000"
        self._outline_btn = QPushButton("黑色 ▤")
        self._outline_btn.clicked.connect(lambda: self._pick_color("_outline_color", self._outline_btn))
        style_form.addRow("描边颜色:", self._outline_btn)

        self._bilingual_check = QCheckBox("双语显示（原语言 + 译文）")
        self._bilingual_check.setChecked(False)
        self._bilingual_check.toggled.connect(self._apply_params_preview)
        style_form.addRow("", self._bilingual_check)

        self._bilingual_pos = QComboBox()
        self._bilingual_pos.addItem("原语言在上，译文在下", "src_top")
        self._bilingual_pos.addItem("原语言在下，译文在上", "src_bottom")
        self._bilingual_pos.currentIndexChanged.connect(self._apply_params_preview)
        style_form.addRow("双语相对位置:", self._bilingual_pos)

        self._secondary_scale = QDoubleSpinBox()
        self._secondary_scale.setRange(0.50, 1.00)
        self._secondary_scale.setSingleStep(0.05)
        self._secondary_scale.setValue(0.85)
        self._secondary_scale.setDecimals(2)
        self._secondary_scale.setSuffix(" ×主字号")
        self._secondary_scale.valueChanged.connect(self._apply_params_preview)
        style_form.addRow("译文字号比例:", self._secondary_scale)

        self._margin_v = QSpinBox()
        self._margin_v.setRange(0, 200)
        self._margin_v.setValue(16)
        self._margin_v.setSuffix(" px")
        self._margin_v.valueChanged.connect(self._apply_params_preview)
        style_form.addRow("底部边距:", self._margin_v)

        # ---- 底部黑框（pad 向下扩边的纯黑字幕条） ----
        self._bar_enabled = QCheckBox("启用底部黑框（从视频底边向下扩展画布，字幕放入新黑条，不遮挡原画面）")
        self._bar_enabled.setChecked(False)
        self._bar_enabled.toggled.connect(self._apply_params_preview)
        style_form.addRow("", self._bar_enabled)

        self._bar_height = QSpinBox()
        self._bar_height.setRange(20, 200)
        self._bar_height.setValue(48)
        self._bar_height.setSuffix(" px")
        self._bar_height.setToolTip("从视频底部向下接出的黑条高度（1080p 基准像素）")
        self._bar_height.valueChanged.connect(self._apply_params_preview)
        style_form.addRow("黑条扩展高度:", self._bar_height)

        self._bar_opacity_label = QLabel("黑框透明度:")
        self._bar_opacity = QSpinBox()
        self._bar_opacity.setRange(0, 100)
        self._bar_opacity.setValue(100)
        self._bar_opacity.setSuffix(" %")
        # ★ pad 扩边的黑条是纯黑不透明的新画布区域，透明度无意义；控件仅保留以兼容旧配置
        self._bar_opacity.setEnabled(False)
        self._bar_opacity_label.setEnabled(False)
        self._bar_opacity.setToolTip("扩边黑条固定为纯黑不透明区域，不支持调节透明度")
        style_form.addRow(self._bar_opacity_label, self._bar_opacity)

        layout.addWidget(style_group)

        # ---- 输出类型 ----
        out_group = QGroupBox("📦 输出类型")
        out_layout = QVBoxLayout(out_group)

        self._out_mp4 = QCheckBox("🎬 硬烧录 MP4（字幕嵌入画面，兼容所有播放器）")
        self._out_mp4.setChecked(True)
        out_layout.addWidget(self._out_mp4)

        self._out_mkv = QCheckBox("📁 MKV 多路封装（视频/音频/字幕分离轨道，剪辑软件可编辑）")
        self._out_mkv.setChecked(False)
        out_layout.addWidget(self._out_mkv)

        layout.addWidget(out_group)

        layout.addStretch(1)

        # ---- 重置位置 ----
        self._reset_pos_btn = QPushButton("↺ 重置字幕位置")
        self._reset_pos_btn.setCursor(Qt.PointingHandCursor)
        self._reset_pos_btn.clicked.connect(lambda: self._video_preview.canvas.reset_pos_to_default())
        layout.addWidget(self._reset_pos_btn)

        # ---- 保存设置 ----
        self._save_style_btn = QPushButton("💾 保存设置")
        self._save_style_btn.setCursor(Qt.PointingHandCursor)
        self._save_style_btn.clicked.connect(self._save_style_config)
        layout.addWidget(self._save_style_btn)

        # ---- 开始制作 ----
        self._render_btn = QPushButton("▶ 开始制作成品")
        self._render_btn.setCursor(Qt.PointingHandCursor)
        self._render_btn.setObjectName("PrimaryBtn")
        self._render_btn.clicked.connect(self._on_render)
        layout.addWidget(self._render_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFormat("%p%")
        self._progress.hide()

        self._progress_label = QLabel()
        self._progress_label.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        self._progress_label.hide()
        layout.addWidget(self._progress_label)
        layout.addWidget(self._progress)

        return panel

    # ------------------------------------------------------------------
    # 颜色选择器
    # ------------------------------------------------------------------
    def _pick_color(self, attr_name: str, btn: QPushButton) -> None:
        current = getattr(self, attr_name, "#FFFFFF")
        color = QColorDialog.getColor(QColor(current), self, "选择颜色")
        if not color.isValid():
            return
        hex_str = color.name().upper()
        setattr(self, attr_name, hex_str)
        short = hex_str.lstrip("#")
        btn.setText(f"#{short[:6]} ▤")
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {hex_str}; color: {'#000000' if color.lightness() > 128 else '#FFFFFF'}; padding: 4px; }}"
        )
        self._apply_params_preview()

    # ------------------------------------------------------------------
    # 继承上下文
    # ------------------------------------------------------------------
    def refresh_context(self) -> None:
        """从全局 TaskManager.context 同步视频/字幕状态（切 tab 时自动调用）"""
        ctx = TaskManager.instance().context
        video_path = ctx.video_path
        srt_path = ctx.srt_path
        cur_video = self._video_path_edit.text()
        cur_srt = self._srt_path_edit.text()

        if video_path and os.path.exists(video_path) and video_path != cur_video:
            self._video_path_edit.setText(video_path)
            self._video_preview.set_video(video_path)
            self._log(f"📥 已加载视频: {os.path.basename(video_path)}", "INFO")

        if srt_path and os.path.exists(srt_path) and srt_path != cur_srt:
            self._srt_path_edit.setText(srt_path)
            self._load_srt_preview(srt_path)
        elif ctx.asr_items and not cur_srt:
            self._preview_subtitle_items(ctx.asr_items)

    def _pick_video(self) -> None:
        start = os.path.dirname(self._video_path_edit.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", start,
            "视频 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v);;All (*)",
        )
        if path:
            self._video_path_edit.setText(path)
            self._video_preview.set_video(path)
            TaskManager.instance().context.video_path = path
            self._log(f"📥 已导入视频: {os.path.basename(path)}", "INFO")

    def _pick_srt(self) -> None:
        start = os.path.dirname(self._video_path_edit.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", start,
            "字幕 (*.srt *.vtt *.ass *.ssa);;SRT (*.srt);;VTT (*.vtt);;All (*)",
        )
        if path:
            self._srt_path_edit.setText(path)
            self._load_srt_preview(path)
            TaskManager.instance().context.srt_path = path

    def _load_srt_preview(self, srt_path: str) -> None:
        try:
            from utils.srt_parser import parse_subtitle_file, normalize_subtitle_items
            raw = parse_subtitle_file(srt_path)
            items = normalize_subtitle_items(raw)
            self._preview_subtitle_items(items)
            self._log(f"📥 已加载字幕: {len(items)} 条", "INFO")
        except Exception as e:
            self._log(f"解析字幕失败: {e}", "ERROR")

    def _preview_subtitle_items(self, items: List[Dict[str, Any]]) -> None:
        from utils.srt_parser import normalize_subtitle_items
        normalized = normalize_subtitle_items(items)
        self._video_preview.set_subtitle_items(normalized)
        self._apply_params_preview()

    # ------------------------------------------------------------------
    # 参数实时应用（预览）
    # ------------------------------------------------------------------
    def _apply_params_preview(self) -> None:
        canvas = self._video_preview.canvas
        # 字号
        canvas.set_font_size(self._font_size.value())
        # 主文字颜色
        canvas.set_primary_color(self._primary_color)
        # 描边颜色
        canvas.set_outline_color(self._outline_color)
        # 双语开关 + 双语位置 + 译文字号比例
        canvas.set_bilingual(self._bilingual_check.isChecked())
        canvas.set_bilingual_pos(self._bilingual_pos.currentData())
        canvas.set_bilingual_scale(self._secondary_scale.value())
        # 底部边距
        canvas.set_margin_v(self._margin_v.value())
        canvas.set_show_src(True)
        # ★ 黑框参数
        canvas.set_bg_bar(
            enabled=self._bar_enabled.isChecked(),
            height=self._bar_height.value(),
            opacity_pct=self._bar_opacity.value(),
        )

    # ------------------------------------------------------------------
    # 开始制作
    # ------------------------------------------------------------------
    def _on_render(self) -> None:
        video_path = self._video_path_edit.text().strip()
        srt_path = self._srt_path_edit.text().strip()

        if not video_path or not os.path.exists(video_path):
            QMessageBox.warning(self, "文件缺失", "请先加载视频文件（从上一页继承或手动选择）。")
            return
        if not srt_path or not os.path.exists(srt_path):
            QMessageBox.warning(self, "字幕缺失", "请先加载 SRT 字幕文件。")
            return

        want_mp4 = self._out_mp4.isChecked()
        want_mkv = self._out_mkv.isChecked()

        if not want_mp4 and not want_mkv:
            QMessageBox.warning(self, "未选择输出", "请至少勾选一种输出类型。")
            return

        if TaskManager.instance().is_running():
            QMessageBox.warning(self, "任务进行中", "当前已有任务在执行。")
            return

        font_size = self._font_size.value()
        margin_v = self._margin_v.value()

        self._log(
            f"▶ 开始制作: video={os.path.basename(video_path)}, srt={os.path.basename(srt_path)}, "
            f"out={'+'.join(filter(None, ['MP4' if want_mp4 else '', 'MKV' if want_mkv else '']))}, "
            f"font={font_size}px",
            "INFO",
        )

        self._set_running(True)
        self._show_progress(True)

        def _run():
            try:
                outputs = []
                if want_mp4:
                    out_mp4 = self._do_burn_mp4(video_path, srt_path, font_size, margin_v)
                    if out_mp4:
                        outputs.append(out_mp4)
                if want_mkv:
                    out_mkv = self._do_mux_mkv(video_path, srt_path)
                    if out_mkv:
                        outputs.append(out_mkv)

                if outputs:
                    self._sig_render_done.emit(outputs)
                else:
                    self._log("未生成任何文件，请查看错误日志", "ERROR")
            except Exception as e:
                import traceback
                self._log(f"制作异常: {e}\n{traceback.format_exc()}", "ERROR")
            finally:
                self._sig_finished.emit()

        spawn(target=_run, daemon=True).start()

    def _do_burn_mp4(self, video_path: str, srt_path: str, font_size: int, margin_v: int) -> Optional[str]:
        from core.subtitle_render import burn_mp4

        base, _ = os.path.splitext(os.path.basename(video_path))
        self._log(f"🎬 开始硬烧录 MP4 → {base}_已完成.mp4", "INFO")

        # ★ 从 GUI 控件快照所有参数（包括双语 + 译文字号比例 + 黑框 + 自由定位）
        bilingual = self._bilingual_check.isChecked()
        bilingual_pos = self._bilingual_pos.currentData()  # "src_top" | "src_bottom"
        secondary_scale = float(self._secondary_scale.value())
        bar_enabled = self._bar_enabled.isChecked()
        bar_height = self._bar_height.value() if bar_enabled else 0
        bar_opacity = self._bar_opacity.value() if bar_enabled else 0

        # ★ 从 Canvas 读取字幕自由定位坐标（视频像素）
        canvas = self._video_preview.canvas
        pos_x, pos_y = canvas.get_pos()

        return burn_mp4(
            video_path,
            srt_path,
            font_size=font_size,
            margin_v=margin_v,
            primary_color=self._primary_color,
            outline_color=self._outline_color,
            progress_cb=lambda pct, desc: self._sig_progress.emit(pct, desc),
            bilingual=bilingual,
            bilingual_pos=bilingual_pos,
            secondary_scale=secondary_scale,
            bar_enabled=bar_enabled,
            bar_height=bar_height,
            bar_opacity_pct=bar_opacity,
            pos_x=pos_x,
            pos_y=pos_y,
        )

    def _do_mux_mkv(self, video_path: str, srt_path: str) -> Optional[str]:
        """MKV 多路封装：视频流 + 音频流 + 字幕文件"""
        try:
            ffmpeg = "ffmpeg"
            try:
                from utils.path_helper import get_ffmpeg_path
                p = get_ffmpeg_path()
                if p:
                    ffmpeg = str(p)
            except Exception:
                pass

            dir_name = os.path.dirname(video_path)
            base, _ = os.path.splitext(os.path.basename(video_path))
            out_path = os.path.join(dir_name, f"{base}_封装.mkv")

            self._log(f"📁 开始 MKV 多路封装 → {os.path.basename(out_path)}", "INFO")

            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
                "-i", srt_path,
                "-c", "copy",
                "-c:s", "mov_text",
                "-metadata:s:s:0", "language=chi",
                "-metadata:s:s:0", "title=中文字幕",
                "-map", "0:v?",
                "-map", "0:a?",
                "-map", "1:0",
                out_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, encoding="utf-8", errors="replace",
                timeout=1800,
            )

            if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                self._log(f"✅ MKV 封装完成: {out_path}", "SUCCESS")
                return out_path

            err_tail = (result.stderr or "")[-500:]
            self._log(f"MKV 封装失败: {err_tail}", "ERROR")
            return None
        except subprocess.TimeoutExpired:
            self._log("MKV 封装超时（>30分钟）", "ERROR")
            return None
        except Exception as e:
            self._log(f"MKV 封装异常: {e}", "ERROR")
            return None

    # ------------------------------------------------------------------
    # 制作完成 → 询问打开文件夹 & 进入下一步 & 是否发布
    # ------------------------------------------------------------------
    def _on_render_done(self, outputs: List[str]) -> None:
        ctx = TaskManager.instance().context
        ctx.final_video_path = outputs[0] if outputs else ""

        folder = os.path.dirname(outputs[0]) if outputs else ""
        file_list = "\n".join(f"  • {os.path.basename(p)}" for p in outputs)

        reply = QMessageBox.question(
            self, "制作完成",
            f"✅ 已生成 {len(outputs)} 个成品：\n{file_list}\n\n"
            f"所在目录：{folder}\n\n"
            "[是] = 打开文件夹 + 进入文案生成\n"
            "[否] = 仅打开文件夹\n"
            "[取消] = 仅跳转下一步",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )

        if reply in (QMessageBox.Yes, QMessageBox.No):
            try:
                os.startfile(folder)  # type: ignore[attr-defined]
            except Exception:
                pass

        if reply != QMessageBox.No:
            mw = self.window()
            if hasattr(mw, "switch_to_tab"):
                mw.switch_to_tab(3)

        # ---- 入视频候选池 + 询问是否立即发布 ----
        self._manual_post_render_hook(outputs)

    def _manual_post_render_hook(self, outputs: List[str]) -> None:
        """手动烧录完成后：入候选池 → 可选直接跳到发布页"""
        try:
            from core.publish.pool import VideoPool
            from loguru import logger

            final_video = outputs[0] if outputs else ""
            if not final_video or not os.path.exists(final_video):
                return

            ctx = TaskManager.instance().context

            # 收集可用元数据
            source_url = ""
            try:
                # 尝试从下载页拿 source_url
                mw = self.window()
                dl_page = getattr(mw, "page_download", None)
                if dl_page and hasattr(dl_page, "_current_url"):
                    source_url = getattr(dl_page, "_current_url", "") or ""
            except Exception:
                pass

            cover_path = ""
            try:
                base = os.path.splitext(os.path.basename(final_video))[0]
                d = os.path.dirname(final_video)
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    cand = os.path.join(d, base + ext)
                    if os.path.exists(cand):
                        cover_path = cand
                        break
            except Exception:
                pass

            pool_id = VideoPool.add(
                final_video_path=final_video,
                source_url=source_url,
                video_id=ctx.video_id,
                cover_path=cover_path,
                srt_path=ctx.srt_path or "",
                title_original="",   # 手动模式让用户自己填
                title_translated="",
                desc_original="",
                desc_translated="",
                lang=ctx.language,
                pipeline_source="manual",
            )
            if pool_id:
                logger.info(f"[PageSubtitle] 入池成功: pool_id={pool_id} (manual)")

                # 询问是否立即去发布页
                reply2 = QMessageBox.question(
                    self, "是否发布",
                    f"✅ 视频已加入发布候选池。\n\n是否立即跳到「视频发布」页面设置平台账号并发布？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply2 == QMessageBox.Yes:
                    mw = self.window()
                    if hasattr(mw, "switch_to_tab"):
                        mw.switch_to_tab(4)
                    # 发布页还没加载 pool_id，等 tab 切过去后用 timer 触发 prefill
                    if hasattr(mw, "page_publish") and pool_id:
                        QTimer.singleShot(300, lambda: self._publish_prefill(mw, pool_id))

        except Exception as e:
            import traceback
            from loguru import logger
            logger.warning(f"[PageSubtitle] 入池/发布询问异常（不影响主流程）: {e}\n{traceback.format_exc()}")

    def _publish_prefill(self, mw, pool_id: int) -> None:
        """切到发布页后自动填入刚烧录完的视频"""
        try:
            pub_page = getattr(mw, "page_publish", None)
            if pub_page and hasattr(pub_page, "_prefill_from_pool"):
                pub_page._prefill_from_pool(pool_id)
        except Exception:
            pass

    def _on_render_failed_slot(self, msg: str) -> None:
        QMessageBox.critical(self, "制作失败", msg)

    def _on_finished(self) -> None:
        self._set_running(False)
        self._show_progress(False)

    def _on_progress(self, pct: int, desc: str) -> None:
        self._progress.setValue(pct)
        self._progress_label.setText(desc)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "INFO") -> None:
        from loguru import logger
        logger.log(level.upper(), msg)

    def _set_running(self, running: bool) -> None:
        TaskManager.instance().set_running(running)
        self._render_btn.setEnabled(not running)

    def _show_progress(self, show: bool) -> None:
        self._progress.setVisible(show)
        self._progress_label.setVisible(show)
        if show:
            self._progress.setValue(0)
            self._progress_label.setText("")

    # ------------------------------------------------------------------
    # 字幕样式配置持久化
    # ------------------------------------------------------------------
    def _save_style_config(self) -> None:
        """把当前字幕样式参数保存到 config.yaml 的 subtitle_style section"""
        try:
            from utils.config_loader import save_subsection
            # ★ 从 Canvas 读当前自由定位
            pos_x, pos_y = self._video_preview.canvas.get_pos()
            data = {
                "font_size": self._font_size.value(),
                "primary_color": self._primary_color,
                "outline_color": self._outline_color,
                "bilingual": self._bilingual_check.isChecked(),
                "bilingual_pos": self._bilingual_pos.currentData(),
                "secondary_scale": float(self._secondary_scale.value()),
                "margin_v": self._margin_v.value(),
                "bar_enabled": self._bar_enabled.isChecked(),
                "bar_height": self._bar_height.value(),
                "bar_opacity_pct": self._bar_opacity.value(),
                "out_mp4": self._out_mp4.isChecked(),
                "out_mkv": self._out_mkv.isChecked(),
                "pos_x": pos_x,
                "pos_y": pos_y,
            }
            save_subsection("subtitle_style", data)
            self._log("💾 字幕样式设置已保存", "SUCCESS")
        except Exception as e:
            self._log(f"保存字幕样式失败: {e}", "ERROR")

    def _load_style_config(self) -> None:
        """从 config.yaml 读取上次保存的字幕样式参数并应用到 UI 控件"""
        try:
            from utils.config_loader import load_config
            cfg = load_config()
            data = cfg.get("subtitle_style", {})
            if not data:
                return

            # 字号
            if "font_size" in data:
                self._font_size.setValue(int(data["font_size"]))
            # 主文字颜色
            if "primary_color" in data:
                self._primary_color = str(data["primary_color"])
                c = QColor(self._primary_color)
                short = self._primary_color.lstrip("#")
                self._primary_btn.setText(f"#{short[:6]} ▤")
                self._primary_btn.setStyleSheet(
                    f"QPushButton {{ background-color: {self._primary_color}; "
                    f"color: {'#000000' if c.lightness() > 128 else '#FFFFFF'}; padding: 4px; }}"
                )
            # 描边颜色
            if "outline_color" in data:
                self._outline_color = str(data["outline_color"])
                c = QColor(self._outline_color)
                short = self._outline_color.lstrip("#")
                self._outline_btn.setText(f"#{short[:6]} ▤")
                self._outline_btn.setStyleSheet(
                    f"QPushButton {{ background-color: {self._outline_color}; "
                    f"color: {'#000000' if c.lightness() > 128 else '#FFFFFF'}; padding: 4px; }}"
                )
            # 双语
            if "bilingual" in data:
                self._bilingual_check.setChecked(bool(data["bilingual"]))
            # 双语位置
            if "bilingual_pos" in data:
                idx = self._bilingual_pos.findData(str(data["bilingual_pos"]))
                if idx >= 0:
                    self._bilingual_pos.setCurrentIndex(idx)
            # 译文字号比例
            if "secondary_scale" in data:
                self._secondary_scale.setValue(float(data["secondary_scale"]))
            # 底部边距
            if "margin_v" in data:
                self._margin_v.setValue(int(data["margin_v"]))
            # 黑框
            if "bar_enabled" in data:
                self._bar_enabled.setChecked(bool(data["bar_enabled"]))
            if "bar_height" in data:
                self._bar_height.setValue(int(data["bar_height"]))
            if "bar_opacity_pct" in data:
                self._bar_opacity.setValue(int(data["bar_opacity_pct"]))
            # 输出类型
            if "out_mp4" in data:
                self._out_mp4.setChecked(bool(data["out_mp4"]))
            if "out_mkv" in data:
                self._out_mkv.setChecked(bool(data["out_mkv"]))

            # 应用到 Canvas 预览
            self._apply_params_preview()

            # ★ 自由定位 pos_x/pos_y（需要 Canvas 初始化后再设）
            if "pos_x" in data and "pos_y" in data:
                self._video_preview.canvas.set_pos(int(data["pos_x"]), int(data["pos_y"]))

            self._log("📥 已加载上次保存的字幕样式设置", "INFO")
        except Exception as e:
            self._log(f"加载字幕样式失败（使用默认值）: {e}", "WARNING")
