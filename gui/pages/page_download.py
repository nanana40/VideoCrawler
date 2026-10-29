"""
PageDownload — 第 1 页：搜索与下载

两种模式：
  [单视频] 按 URL / VideoID 精准下载
  [热门/关键词] 按语言/关键词/时长过滤批量爬取 + 下载

查重：在 output 目录里已存在 → 弹窗让用户选择
      （停止下载 / 覆盖文件 / 创建新文件加后缀）
"""

import os
import re
import time
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from utils.youtube_url import build_watch_url  # AUDIT-0051
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QLabel, QProgressBar, QMessageBox,
    QTextEdit, QTabWidget,
)

from ..task_manager import TaskManager
from ..auto_pipeline import AutoPipelineManager, AutoJob
from ..theme import PALETTE


class PageDownload(QWidget):
    """搜索与下载页"""

    request_next_page = Signal()
    download_finished = Signal(str)

    # 跨线程 UI 操作信号（后台线程 emit，主线程 slot 执行）
    _sig_test_finished = Signal(bool, str)
    _sig_download_success = Signal(str, str, str, dict)
    _sig_download_failed = Signal(str)
    _sig_batch_finished = Signal(str, str)
    _sig_thread_finished = Signal()
    # 元数据获取完成（title, description, duration, channel, language）
    _sig_meta_ready = Signal(dict)
    # 翻译完成（title_zh, desc_zh）
    _sig_translation_done = Signal(str, str)
    # 封面处理：原版下载完成 (本地 jpg 路径) + AI 翻译完成 (输出图片路径)
    _sig_cover_orig_ready = Signal(str)
    _sig_cover_ai_ready = Signal(str)
    # AUDIT-0032: 封面管线 worker 线程状态文本 → 主线程刷新 QLabel
    _sig_cover_status = Signal(str)
    # 全自动流水线队列变化（worker 线程 emit，主线程槽刷新标签）
    _sig_queue_changed = Signal(int)
    # 全自动流水线阶段文本（worker 线程 emit → 主线程刷新标签）
    _sig_pipeline_text = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._running_thread: Optional[threading.Thread] = None
        self._last_meta: Dict[str, Any] = {}   # 最近一次获取的元数据
        self._cover_ai_temp_path: Optional[str] = None  # 获取信息阶段 AI 翻译封面 tempfile
        self._pending_count = 0                 # 排队中数量
        self._phase_text = ""                   # 当前处理阶段
        self._setup_ui()

        TaskManager.instance().register_observer(self._on_running_changed)

        AutoPipelineManager.instance().add_status_observer(self._on_pipeline_status)
        AutoPipelineManager.instance().add_text_observer(self._on_pipeline_text)
        self._sig_queue_changed.connect(self._update_queue_label)
        self._sig_pipeline_text.connect(self._update_pipeline_text)

        self._sig_test_finished.connect(self._on_test_finished)
        self._sig_download_success.connect(self._on_download_success)
        self._sig_download_failed.connect(self._on_download_failed)
        self._sig_batch_finished.connect(self._on_batch_finished)
        self._sig_thread_finished.connect(self._hide_progress)
        self._sig_meta_ready.connect(self._on_meta_ready)
        self._sig_translation_done.connect(self._on_translation_done)
        self._sig_cover_orig_ready.connect(self._on_cover_orig_ready)
        self._sig_cover_ai_ready.connect(self._on_cover_ai_ready)
        # AUDIT-0032: 主线程槽直接 QLabel.setText
        self._sig_cover_status.connect(self._cover_ai.setText)

    def _on_running_changed(self, running: bool) -> None:
        """全局 running 状态变化回调 —— 只刷 UI，不调 set_running 避免循环"""
        if hasattr(self, "_start_btn"):
            self._start_btn.setEnabled(not running)
        if hasattr(self, "_test_btn"):
            self._test_btn.setEnabled(not running)
        if hasattr(self, "_batch_start_btn"):
            self._batch_start_btn.setEnabled(not running)
        if hasattr(self, "_fetch_meta_btn"):
            self._fetch_meta_btn.setEnabled(not running)

    def _on_test_finished(self, ok: bool, msg: str) -> None:
        """主线程槽：测试连接结束"""
        self._test_btn.setEnabled(True)
        self._test_btn.setText("🔌 测试连接")

    def _on_download_success(self, fp: str, lang: str, vid: str, meta: dict) -> None:
        """主线程槽：下载成功"""
        self._set_running(False)
        # 如果用户没提前点"获取信息"，则用下载时解析到的元数据填充面板
        if meta and not self._last_meta:
            self._on_meta_ready(meta)
        self._on_single_downloaded(fp, lang, vid)

    def _on_download_failed(self, err: str) -> None:
        """主线程槽：下载失败"""
        self._set_running(False)

    def _on_batch_finished(self, video_path: str, language_code: str) -> None:
        """主线程槽：批量下载结束"""
        self._set_running(False)
        if video_path:
            self._on_single_downloaded(video_path, language_code, "")

    def _hide_progress(self) -> None:
        if hasattr(self, "_progress"):
            self._progress.setVisible(False)
        if hasattr(self, "_batch_progress"):
            self._batch_progress.setVisible(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        lang_options = self._build_lang_options()
        quality_presets = [
            # ★ 最高清=None → 由 download.py 统一决定（单一来源，避免不同步）
            ("🎬 最高清 (默认，≤2160p)", None),
            ("4K (≤2160p)", "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"),
            ("1440p (≤1440p)", "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best"),
            ("1080p (≤1080p)", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"),
            ("720p (≤720p)", "bestvideo[height<=720]+bestaudio/best[height<=720]/best"),
            ("480p (≤480p)", "bestvideo[height<=480]+bestaudio/best[height<=480]/best"),
            ("360p (≤360p)", "bestvideo[height<=360]+bestaudio/best[height<=360]/best"),
            ("📱 低流量 (≤360p 单文件)", "best[height<=360]"),
        ]
        self._quality_presets = quality_presets

        self._sub_tabs = QTabWidget()
        self._sub_tabs.setDocumentMode(True)
        root.addWidget(self._sub_tabs)

        self._build_single_tab(lang_options)
        self._build_batch_tab(lang_options)
        self._sub_tabs.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # 单视频 Tab：输入 + 视频信息展示 + 封面处理
    # ------------------------------------------------------------------
    def _build_single_tab(self, lang_options: List[tuple]) -> None:
        tab = QWidget()
        main = QHBoxLayout(tab)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(16)

        # ========== 左栏：表单 / 视频信息 / 下载 ==========
        form_w = QWidget()
        form_lay = QVBoxLayout(form_w)
        form_lay.setContentsMargins(0, 0, 0, 0)
        form_lay.setSpacing(12)

        # ---- 单视频下载 ----
        self._single_panel = QGroupBox("🎯 单视频下载")
        single_form = QFormLayout(self._single_panel)
        url_row = QHBoxLayout()
        self._single_url = QLineEdit()
        self._single_url.setPlaceholderText(
            "粘贴视频链接（YouTube / TikTok / 抖音），或 11 位 YouTube Video ID，"
            "例如 https://www.youtube.com/watch?v=xxxxxxxxx"
        )
        url_row.addWidget(self._single_url, 1)
        self._fetch_meta_btn = QPushButton("🔍 获取信息")
        self._fetch_meta_btn.setCursor(Qt.PointingHandCursor)
        self._fetch_meta_btn.setToolTip("提取标题、简介、时长并自动翻译")
        self._fetch_meta_btn.clicked.connect(self._on_fetch_metadata)
        url_row.addWidget(self._fetch_meta_btn)
        url_wrap = QWidget()
        url_wrap.setLayout(url_row)
        single_form.addRow("📎 URL / Video ID:", url_wrap)

        self._single_lang = QComboBox()
        self._single_lang.addItem("自动检测", "auto")
        for code, name in lang_options:
            self._single_lang.addItem(name, code)
        self._single_lang.setCurrentIndex(0)

        self._quality_combo = QComboBox()
        for label, val in self._quality_presets:
            self._quality_combo.addItem(label, val)
        self._quality_combo.setCurrentIndex(0)

        self._single_category = QComboBox()
        self._single_category.addItem("📂 其他", "other")
        self._single_category.addItem("📰 新闻", "news")
        self._single_category.addItem("🎓 教育", "education")
        self._single_category.addItem("💡 科技", "technology")
        self._single_category.addItem("🔬 科普", "science")
        self._single_category.addItem("🎬 娱乐", "entertainment")
        self._single_category.addItem("📅 日常", "daily")
        self._single_category.setCurrentIndex(0)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(4)
        opts_row.addWidget(QLabel("🗣 语言:"))
        opts_row.addWidget(self._single_lang)
        opts_row.addSpacing(8)
        opts_row.addWidget(QLabel("🎞 画质:"))
        opts_row.addWidget(self._quality_combo)
        opts_row.addSpacing(8)
        opts_row.addWidget(QLabel("🏷 分类:"))
        opts_row.addWidget(self._single_category)
        opts_row.addStretch(1)
        opts_wrap = QWidget()
        opts_wrap.setLayout(opts_row)
        single_form.addRow("", opts_wrap)
        form_lay.addWidget(self._single_panel)

        # ---- 全自动模式 + 队列状态 ----
        auto_row = QHBoxLayout()
        self._auto_check = QCheckBox("⚡ 全自动（下载 → 识别 → 烧录 → 文案，自动排队）")
        self._auto_check.setChecked(True)
        self._auto_check.setToolTip(
            "开启后，点击「开始下载」即进入全自动流水线，中间无需再确认。\n"
            "页面立即释放，可继续录入下一个视频排队处理。\n\n"
            "关闭后，走原有分步流程（每步确认）。"
        )
        auto_row.addWidget(self._auto_check)
        auto_row.addStretch(1)
        self._queue_label = QLabel("队列: 0")
        self._queue_label.setStyleSheet(f"color: {PALETTE['accent']}; font-weight: bold; font-size: 13px; padding: 0 8px;")
        auto_row.addWidget(self._queue_label)
        auto_wrap = QWidget()
        auto_wrap.setLayout(auto_row)
        form_lay.addWidget(auto_wrap)

        # ---- 视频信息展示面板（标题/简介/时长 + 翻译） ----
        self._meta_panel = QGroupBox("📋 视频信息")
        self._meta_panel.setVisible(False)
        meta_layout = QVBoxLayout(self._meta_panel)
        meta_layout.setSpacing(6)

        meta_head = QHBoxLayout()
        self._meta_duration = QLabel("⏱ 时长：-")
        self._meta_duration.setStyleSheet(f"color: {PALETTE['accent']}; font-weight: bold;")
        self._meta_channel = QLabel("📺 频道：-")
        self._meta_channel.setStyleSheet(f"color: {PALETTE['text_secondary']};")
        meta_head.addWidget(self._meta_duration)
        meta_head.addStretch(1)
        meta_head.addWidget(self._meta_channel)
        meta_layout.addLayout(meta_head)

        # 双栏：左=原文，右=中文翻译（保持信息完整、布局紧凑，复制可用 Ctrl+C）
        cols = QHBoxLayout()
        cols.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.addWidget(QLabel("🎬 标题（原文）"))
        self._meta_title = QTextEdit()
        self._meta_title.setReadOnly(True)
        self._meta_title.setMaximumHeight(56)
        left_col.addWidget(self._meta_title)
        left_col.addWidget(QLabel("📝 简介（原文）"))
        self._meta_desc = QTextEdit()
        self._meta_desc.setReadOnly(True)
        self._meta_desc.setMaximumHeight(120)
        left_col.addWidget(self._meta_desc)
        left_w = QWidget()
        left_w.setLayout(left_col)
        meta_left_w = QWidget()
        meta_left_w.setLayout(left_col)
        cols.addWidget(meta_left_w, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.addWidget(QLabel("🇨🇳 标题（中文翻译）"))
        self._meta_title_zh = QTextEdit()
        self._meta_title_zh.setReadOnly(True)
        self._meta_title_zh.setMaximumHeight(56)
        right_col.addWidget(self._meta_title_zh)
        right_col.addWidget(QLabel("🇨🇳 简介（中文翻译）"))
        self._meta_desc_zh = QTextEdit()
        self._meta_desc_zh.setReadOnly(True)
        self._meta_desc_zh.setMaximumHeight(120)
        right_col.addWidget(self._meta_desc_zh)
        meta_right_w = QWidget()
        meta_right_w.setLayout(right_col)
        cols.addWidget(meta_right_w, 1)

        meta_layout.addLayout(cols)
        form_lay.addWidget(self._meta_panel)

        # ---- 动作区 ----
        action_row = QHBoxLayout()
        self._test_btn = QPushButton("🔌 测试连接")
        self._test_btn.setCursor(Qt.PointingHandCursor)
        self._test_btn.clicked.connect(self._on_test_connection)
        action_row.addWidget(self._test_btn)

        action_row.addStretch(1)

        self._start_btn = QPushButton("▶ 开始下载")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setObjectName("PrimaryBtn")
        self._start_btn.clicked.connect(self._on_start_download)
        action_row.addWidget(self._start_btn)
        form_lay.addLayout(action_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        form_lay.addWidget(self._progress)

        self._result_label = QLabel("")
        self._result_label.setStyleSheet(f"color: {PALETTE['text_secondary']}; padding: 8px;")
        self._result_label.setWordWrap(True)
        form_lay.addWidget(self._result_label)

        form_lay.addStretch(1)

        # ========== 右栏：封面预览（上=原版，下=AI 翻译版）==========
        cover_w = QWidget()
        rl = QVBoxLayout(cover_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)

        # ---- 原封面 ----
        orig_box = QGroupBox("🖼 原始封面")
        orig_lay = QVBoxLayout(orig_box)
        orig_lay.setContentsMargins(8, 18, 8, 8)
        self._cover_orig = QLabel("点击「🔍 获取信息」后自动下载封面")
        self._cover_orig.setAlignment(Qt.AlignCenter)
        self._cover_orig.setMinimumHeight(180)
        self._cover_orig.setWordWrap(True)
        self._cover_orig.setStyleSheet(
            f"color: {PALETTE['text_muted']}; border: 1px dashed {PALETTE['border']};"
            " border-radius: 6px; padding: 20px;"
        )
        orig_lay.addWidget(self._cover_orig)
        rl.addWidget(orig_box, 1)

        # ---- AI 翻译封面 ----
        ai_box = QGroupBox("✨ AI 翻译封面（Gemini）")
        ai_lay = QVBoxLayout(ai_box)
        ai_lay.setContentsMargins(8, 18, 8, 8)
        self._cover_ai = QLabel("获取封面后自动调用 Gemini 翻译文字")
        self._cover_ai.setAlignment(Qt.AlignCenter)
        self._cover_ai.setMinimumHeight(180)
        self._cover_ai.setWordWrap(True)
        self._cover_ai.setStyleSheet(
            f"color: {PALETTE['text_muted']}; border: 1px dashed {PALETTE['border']};"
            " border-radius: 6px; padding: 20px;"
        )
        ai_lay.addWidget(self._cover_ai)
        rl.addWidget(ai_box, 1)

        # 组合左右栏进主 HBox
        main.addWidget(form_w, 3)
        main.addWidget(cover_w, 2)

        self._sub_tabs.addTab(tab, "🎯 单视频")

    # ------------------------------------------------------------------
    # 热门 / 关键词批量 Tab
    # ------------------------------------------------------------------
    def _build_batch_tab(self, lang_options: List[tuple]) -> None:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        self._batch_panel = QGroupBox("🔥 热门 / 关键词批量下载")
        batch_form = QFormLayout(self._batch_panel)

        self._keyword = QLineEdit()
        self._keyword.setPlaceholderText("搜索关键词，例如 'WELT news'（留空则按语言热门）")
        batch_form.addRow("🔑 关键词:", self._keyword)

        self._batch_lang = QComboBox()
        for code, name in lang_options:
            self._batch_lang.addItem(name, code)
        self._batch_lang.setCurrentIndex(0)
        batch_form.addRow("🌍 语言:", self._batch_lang)

        self._batch_count = QSpinBox()
        self._batch_count.setRange(1, 50)
        self._batch_count.setValue(5)
        self._batch_count.setSuffix(" 条")
        batch_form.addRow("📦 下载数量:", self._batch_count)

        self._min_dur = QSpinBox()
        self._min_dur.setRange(0, 3600)
        self._min_dur.setValue(60)
        self._min_dur.setSuffix(" 秒")
        self._max_dur = QSpinBox()
        self._max_dur.setRange(0, 7200)
        self._max_dur.setValue(900)
        self._max_dur.setSuffix(" 秒")
        dur_row = QHBoxLayout()
        dur_row.addWidget(self._min_dur)
        dur_row.addWidget(QLabel("~"))
        dur_row.addWidget(self._max_dur)
        dur_wrap = QWidget()
        dur_wrap.setLayout(dur_row)
        batch_form.addRow("⏱ 时长范围:", dur_wrap)

        self._batch_quality = QComboBox()
        for label, val in self._quality_presets[:6]:
            self._batch_quality.addItem(label, val)
        self._batch_quality.setCurrentIndex(0)
        batch_form.addRow("🎞 清晰度:", self._batch_quality)

        self._batch_category = QComboBox()
        self._batch_category.addItem("📂 其他", "other")
        self._batch_category.addItem("📰 新闻", "news")
        self._batch_category.addItem("🎓 教育", "education")
        self._batch_category.addItem("💡 科技", "technology")
        self._batch_category.addItem("🔬 科普", "science")
        self._batch_category.addItem("🎬 娱乐", "entertainment")
        self._batch_category.addItem("📅 日常", "daily")
        self._batch_category.setCurrentIndex(0)
        batch_form.addRow("🏷 分类:", self._batch_category)
        lay.addWidget(self._batch_panel)

        batch_action_row = QHBoxLayout()
        batch_action_row.addStretch(1)
        self._batch_start_btn = QPushButton("▶ 开始批量下载")
        self._batch_start_btn.setCursor(Qt.PointingHandCursor)
        self._batch_start_btn.setObjectName("PrimaryBtn")
        self._batch_start_btn.clicked.connect(self._on_start_batch)
        batch_action_row.addWidget(self._batch_start_btn)
        lay.addLayout(batch_action_row)

        self._batch_progress = QProgressBar()
        self._batch_progress.setRange(0, 0)
        self._batch_progress.hide()
        lay.addWidget(self._batch_progress)

        lay.addStretch(1)
        self._sub_tabs.addTab(tab, "🔥 热门 / 关键词批量")

    # ------------------------------------------------------------------
    # 元数据获取 + 翻译
    # ------------------------------------------------------------------
    def _on_fetch_metadata(self) -> None:
        """点击"获取信息"：提取视频标题/简介/时长并翻译"""
        url_raw = self._single_url.text().strip()
        if not url_raw:
            QMessageBox.warning(self, "参数缺失", "请输入视频链接（YouTube / TikTok / 抖音）或 11 位 YouTube Video ID。")
            return

        video_id = self._parse_video_id(url_raw)
        if not video_id:
            QMessageBox.critical(self, "解析失败", "无法解析出有效的视频 ID（YouTube 需 11 位 ID；TikTok/抖音需完整链接）。")
            return

        self._maybe_tiktok_cookie_guide(url_raw)

        url = url_raw if url_raw.startswith("http") else build_watch_url(video_id)
        self._fetch_meta_btn.setEnabled(False)
        self._fetch_meta_btn.setText("获取中...")
        self._meta_panel.setVisible(True)
        self._meta_title.setPlainText("正在获取视频信息...")
        self._meta_title_zh.clear()
        self._meta_desc.clear()
        self._meta_desc_zh.clear()
        self._meta_duration.setText("⏱ 时长：-")
        self._meta_channel.setText("📺 频道：-")

        def _run():
            try:
                from core.download import VideoDownloader
                dl = VideoDownloader()
                meta = dl.get_video_metadata(url, video_id)
                self._sig_meta_ready.emit(meta)
            except Exception as e:
                self._log(f"获取元数据失败: {e}", "ERROR")
                self._sig_meta_ready.emit({})

        spawn(target=_run, daemon=True).start()

    def _on_meta_ready(self, meta: Dict[str, Any]) -> None:
        """主线程槽：元数据获取完成 → 自动识别语言/分类 → 翻译标题+简介"""
        self._fetch_meta_btn.setEnabled(True)
        self._fetch_meta_btn.setText("🔍 获取信息")

        if not meta:
            self._meta_title.setPlainText("❌ 获取视频信息失败，请检查网络或 URL。")
            return

        self._last_meta = meta
        title = meta.get("title", "")
        desc = meta.get("description", "")
        duration = float(meta.get("duration") or 0)
        channel = meta.get("channel", "")

        # ---------- 展示原文 ----------
        self._meta_title.setPlainText(title)
        self._meta_desc.setPlainText(desc)
        self._meta_duration.setText(f"⏱ 时长：{self._fmt_duration(duration)}")
        self._meta_channel.setText(f"📺 频道：{channel or '-'}")
        self._meta_title_zh.setPlainText("翻译中...")
        self._meta_desc_zh.setPlainText("翻译中...")

        # ---------- 自动识别语言 ----------
        from utils.language_check import detect_language_from_info
        from utils.enums import LanguageType
        detected_lt: LanguageType = detect_language_from_info(meta)
        detected_lang = detected_lt.value  # 如 "de", "en"
        # 把 UI 下拉切到识别到的语言（找不到匹配项则保留"自动检测"）
        idx = self._single_lang.findData(detected_lang)
        if idx >= 0:
            self._single_lang.setCurrentIndex(idx)
            self._log(f"🗣 自动识别源语言：{detected_lt.display_name} ({detected_lang})", "INFO")
        else:
            self._log(f"🗣 自动识别源语言：{detected_lt.display_name}（未在下拉中找到匹配项，保留默认）", "INFO")

        # ---------- 自动识别分类 ----------
        from core.classify import classify_video
        from utils.enums import VideoCategory
        detected_cat: VideoCategory = classify_video(title, desc)
        cat_code = detected_cat.value  # 如 "entertainment"
        idx = self._single_category.findData(cat_code)
        if idx >= 0:
            self._single_category.setCurrentIndex(idx)
            self._log(f"🏷 自动识别分类：{detected_cat.display_name}", "INFO")

        # ---------- 翻译：标题和简介分别独立调用，各自完整翻译 ----------
        def _translate() -> None:
            try:
                from core.translation_engine import TranslationEngine
                engine = TranslationEngine.from_config()

                # ① 标题（短文本，独立翻译，避免和长简介一起错位）
                title_zh = ""
                if title.strip():
                    try:
                        results = engine.translate([title], source_lang=detected_lang, target_lang="zh-CN")
                        title_zh = results[0] if results else ""
                    except Exception as _e:
                        self._log(f"标题翻译失败: {_e}", "ERROR")
                        title_zh = ""

                # ② 简介（可能很长，独立翻译 → _translate_batch 会按行分块完整处理）
                desc_zh = ""
                if desc.strip():
                    try:
                        results = engine.translate([desc], source_lang=detected_lang, target_lang="zh-CN")
                        desc_zh = results[0] if results else ""
                    except Exception as _e:
                        self._log(f"简介翻译失败: {_e}", "ERROR")
                        desc_zh = ""

                self._sig_translation_done.emit(title_zh, desc_zh)
            except Exception as e:
                self._log(f"翻译初始化失败: {e}", "ERROR")
                self._sig_translation_done.emit("", "")

        spawn(target=_translate, daemon=True).start()

        # ---------- 封面管线：下载 thumbnail_url → AI 翻译 → 展示 ----------
        thumb_url = meta.get("thumbnail_url")
        if thumb_url:
            self._cover_orig.setText("⏳ 下载封面中...")
            self._cover_ai.setText("等待原版封面完成后自动处理...")
            spawn(self._run_cover_pipeline, thumb_url, daemon=True).start()
        else:
            self._log("⚠ 视频无封面缩略图 URL，跳过封面管线", "WARNING")

    def _on_translation_done(self, title_zh: str, desc_zh: str) -> None:
        """主线程槽：翻译完成"""
        self._meta_title_zh.setPlainText(title_zh or "（翻译失败）")
        self._meta_desc_zh.setPlainText(desc_zh or "（翻译失败）")

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        if seconds <= 0:
            return "-"
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:d}:{s:02d}"

    # ------------------------------------------------------------------
    # 动作槽
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "INFO") -> None:
        from loguru import logger
        logger.log(level.upper(), msg)

    def _on_test_connection(self) -> None:
        """测试 yt-dlp / 网络连通性"""
        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")

        def _run():
            try:
                import yt_dlp
                self._log(f"yt-dlp 版本: {yt_dlp.version.__version__}", "INFO")

                import requests
                r = requests.head("https://www.youtube.com", timeout=10, allow_redirects=True)
                self._log(f"YouTube 连通性: HTTP {r.status_code}", "SUCCESS")
                self._sig_test_finished.emit(True, "HTTP " + str(r.status_code))
            except Exception as e:
                self._log(f"连接测试失败: {e}", "ERROR")
                self._sig_test_finished.emit(False, str(e))

        spawn(target=_run, daemon=True).start()

    def _maybe_tiktok_cookie_guide(self, raw_url: str) -> None:
        """TikTok/抖音 链接：首次提示导出 Cookie，并检查 cookie 是否缺失/过旧"""
        try:
            from utils.video_url import detect_video_site
            if detect_video_site(raw_url) != "tiktok":
                return

            from utils.path_helper import get_cookies_file_path
            cookie_file = get_cookies_file_path()
            if not cookie_file.exists():
                self._log(f"⚠ 未找到 cookie 文件：{cookie_file}", "WARNING")
            else:
                age_days = int((time.time() - cookie_file.stat().st_mtime) / 86400)
                if age_days >= 14:
                    self._log(f"⚠ cookie 已 {age_days} 天未更新，解析失败时请重新导出", "WARNING")

            from gui.onboarding import maybe_show_guide
            maybe_show_guide(
                self, "tiktok_cookie",
                actions=[("📂 打开 cookies 存放位置", self._open_cookie_folder)],
            )
        except Exception as e:
            self._log(f"TikTok Cookie 引导弹出失败: {e}", "WARNING")

    def _open_cookie_folder(self) -> None:
        """打开 cookies 文件所在目录"""
        try:
            from utils.path_helper import get_data_dir
            os.startfile(str(get_data_dir()))  # type: ignore[attr-defined]
        except Exception as e:
            self._log(f"打开目录失败: {e}", "ERROR")

    def _on_start_download(self) -> None:
        self._maybe_tiktok_cookie_guide(self._single_url.text().strip())
        if self._auto_check.isChecked():
            self._auto_enqueue()
            return

        if TaskManager.instance().is_running():
            QMessageBox.warning(self, "任务进行中", "当前已有任务在执行，请先等待或强制结束。")
            return

        self._start_single()

    def _on_start_batch(self) -> None:
        if TaskManager.instance().is_running():
            QMessageBox.warning(self, "任务进行中", "当前已有任务在执行，请先等待或强制结束。")
            return

        self._start_batch()

    # ------------------------------------------------------------------
    # 单视频下载
    # ------------------------------------------------------------------
    def _start_single(self) -> None:
        url_raw = self._single_url.text().strip()
        if not url_raw:
            QMessageBox.warning(self, "参数缺失", "请输入视频链接（YouTube / TikTok / 抖音）或 11 位 YouTube Video ID。")
            return

        video_id = self._parse_video_id(url_raw)
        if not video_id:
            QMessageBox.critical(self, "解析失败", "无法从输入中解析出有效的视频 ID（YouTube 需 11 位 ID；TikTok/抖音需完整链接）。")
            return

        url = url_raw if url_raw.startswith("http") else build_watch_url(video_id)
        language_code = self._single_lang.currentData()

        # 查重
        existing = self._find_existing_video(video_id)
        if existing:
            choice = QMessageBox.question(
                self, "视频已存在",
                f"output 目录已存在该视频：\n{existing}\n\n"
                "如何处理？\n[是] = 创建新文件（加后缀 _new）\n"
                "[否] = 停止下载\n[取消] = 覆盖原文件",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if choice == QMessageBox.No:
                self._log(f"用户决定跳过（已存在）: {video_id}", "WARNING")
                self._offer_next_step(existing, language_code, video_id)
                return
            elif choice == QMessageBox.Cancel:
                self._do_single_download(url, video_id, language_code, overwrite=True)
                return
            else:
                self._do_single_download(url, video_id, language_code, overwrite=False, suffix="_new")
                return

        self._do_single_download(url, video_id, language_code)

    def _do_single_download(
        self, url: str, video_id: str, language_code: str,
        overwrite: bool = False, suffix: str = "",
        category_code: Optional[str] = None,
    ) -> None:
        quality = self._quality_combo.currentData()
        cat_code = category_code or self._single_category.currentData()
        self._set_running(True)
        self._show_progress(True)
        self._log(f"▶ 开始下载单视频: {url}  清晰度={quality}  分类={cat_code}", "INFO")

        def _run():
            try:
                from core.download import VideoDownloader
                from utils.enums import LanguageType, VideoCategory

                downloader = VideoDownloader()
                lang_obj = None
                if language_code and language_code != "auto":
                    try:
                        lang_obj = LanguageType(language_code)
                    except Exception:
                        lang_obj = None

                cat_obj = None
                if cat_code and cat_code != "other":
                    try:
                        cat_obj = VideoCategory(cat_code)
                    except Exception:
                        cat_obj = None

                result = downloader.download_video(
                    url=url,
                    video_id=video_id,
                    language=lang_obj,
                    category=cat_obj,
                    format_selector=quality,
                    overwrite=overwrite or bool(suffix),  # suffix 模式也跳过查重，否则会被拦截
                )

                fp = result.file_path or result.local_path or ""
                if fp and not getattr(result, 'skipped', False):
                    if suffix and fp and overwrite is False:
                        base, ext = os.path.splitext(fp)
                        new_fp = base + suffix + ext
                        try:
                            import shutil
                            if os.path.exists(new_fp):
                                os.remove(new_fp)
                            shutil.copy2(fp, new_fp)
                            fp = new_fp
                            self._log(f"已创建副本: {new_fp}", "SUCCESS")
                        except Exception as e:
                            self._log(f"创建副本失败: {e}", "ERROR")

                    self._log(f"✅ 下载成功: {fp}", "SUCCESS")
                    meta = {
                        "title": getattr(result, "title", "") or "",
                        "description": getattr(result, "description", "") or "",
                        "duration": getattr(result, "duration", 0) or 0,
                        "channel": getattr(result, "channel", "") or "",
                        "language": language_code or "auto",
                        "thumbnail_url": getattr(result, "thumbnail_url", None),
                    }
                    self._sig_download_success.emit(fp, language_code, video_id, meta)
                else:
                    err = result.error_message or "未知错误"
                    self._log(f"❌ 下载失败: {err}", "ERROR")
                    self._sig_download_failed.emit(err)
            except Exception as e:
                self._log(f"下载异常: {e}", "ERROR")
                self._sig_download_failed.emit(str(e))
            finally:
                self._sig_thread_finished.emit()

        self._running_thread = spawn(target=_run, daemon=True)
        TaskManager.instance().register_thread(self._running_thread)
        self._running_thread.start()

    # ------------------------------------------------------------------
    # 全自动流水线（排队）
    # ------------------------------------------------------------------
    def _auto_enqueue(self) -> None:
        """全自动模式入队：解析 URL → 快照各页默认参数 → 前置确认 → 加入队列"""
        url_raw = self._single_url.text().strip()
        if not url_raw:
            QMessageBox.warning(self, "参数缺失", "请输入视频链接（YouTube / TikTok / 抖音）或 11 位 YouTube Video ID。")
            return

        video_id = self._parse_video_id(url_raw)
        if not video_id:
            QMessageBox.critical(self, "解析失败", "无法从输入中解析出有效的视频 ID（YouTube 需 11 位 ID；TikTok/抖音需完整链接）。")
            return

        url = url_raw if url_raw.startswith("http") else build_watch_url(video_id)

        job = self._build_auto_job(url, video_id)

        # 前置确认：请用户检查默认参数是否正确
        reply = QMessageBox.question(
            self, "⚡ 全自动流程 - 请检查默认参数",
            "将以以下参数对该视频执行全自动处理"
            "（下载 → 识别 → 烧录 → 文案），无需再确认：\n\n"
            + self._format_job_summary(job) +
            "\n[是] = 参数正确，加入队列开始\n[否] = 取消本次下载",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._log(f"用户取消全自动下载: {video_id}", "INFO")
            return

        AutoPipelineManager.instance().enqueue(job)
        self._log(f"⚡ 已加入全自动队列：{video_id}，处理中请留意下方进度", "SUCCESS")
        app = AutoPipelineManager.instance()
        if app.is_busy():
            self._phase_text = "正在处理中…"
        self._pending_count = app.queue_size()
        self._refresh_queue_label()

    def _build_auto_job(self, url: str, video_id: str) -> AutoJob:
        """从当前各页控件快照一份自动任务参数"""
        mw = self.window()
        rec = getattr(mw, "page_recognize", None)
        sub = getattr(mw, "page_subtitle", None)
        wrt = getattr(mw, "page_writer", None)

        # ---- 识别页参数 ----
        target_lang = "zh-CN"
        proofread = False
        if rec is not None:
            tc = getattr(rec, "_tgt_lang", None)
            if tc is not None:
                target_lang = tc.currentData() or "zh-CN"
            pc = getattr(rec, "_proofread_check", None)
            if pc is not None:
                proofread = bool(pc.isChecked())

        # ---- 字幕页参数 ----
        font_size = 12
        margin_v = 16
        primary_color = "#FFFFFF"
        outline_color = "#000000"
        bilingual = True
        bilingual_pos = "src_top"
        secondary_scale = 0.85
        if sub is not None:
            fs = getattr(sub, "_font_size", None)
            if fs is not None:
                font_size = int(fs.value())
            mv = getattr(sub, "_margin_v", None)
            if mv is not None:
                margin_v = int(mv.value())
            primary_color = getattr(sub, "_primary_color", "#FFFFFF") or "#FFFFFF"
            outline_color = getattr(sub, "_outline_color", "#000000") or "#000000"
            # ★ 双语参数
            bc = getattr(sub, "_bilingual_check", None)
            if bc is not None:
                bilingual = bool(bc.isChecked())
            bp = getattr(sub, "_bilingual_pos", None)
            if bp is not None:
                bilingual_pos = bp.currentData() or "src_top"
            # ★ 译文字号比例（从字幕页新控件读取）
            ss = getattr(sub, "_secondary_scale", None)
            if ss is not None:
                secondary_scale = float(ss.value())

        # ---- 文案页参数 ----
        platform = "xiaohongshu"
        style = "oral"
        analyze = True
        if wrt is not None:
            pl = getattr(wrt, "_platform", None)
            if pl is not None:
                platform = pl.currentData() or "xiaohongshu"
            exam = getattr(wrt, "_style_exam", None)
            if exam is not None and exam.isChecked():
                style = "exam"
            ac = getattr(wrt, "_analyze_check", None)
            if ac is not None:
                analyze = bool(ac.isChecked())

        return AutoJob(
            url=url,
            video_id=video_id,
            language=self._single_lang.currentData() or "auto",
            # None → 由 download.py 统一决定（单一来源）
            quality=self._quality_combo.currentData(),
            category=self._single_category.currentData() or "other",
            target_lang=target_lang,
            proofread=proofread,
            font_size=font_size,
            margin_v=margin_v,
            primary_color=primary_color,
            outline_color=outline_color,
            bilingual=bilingual,
            bilingual_pos=bilingual_pos,
            secondary_scale=secondary_scale,
            platform=platform,
            style=style,
            analyze=analyze,
        )

    @staticmethod
    def _format_job_summary(job: AutoJob) -> str:
        lang_display = job.language if job.language != "auto" else "自动检测"
        return (
            f"🎯 视频 ID：{job.video_id}\n"
            f"🗣  源语言：{lang_display}\n"
            f"🎞  清晰度：{job.quality}\n"
            f"🏷  分类：{job.category or 'other'}\n"
            f"🎯 目标语言：{job.target_lang}\n"
            f"🔍 AI 校对：{'开' if job.proofread else '关'}\n"
            f"🎨 字幕字号：{job.font_size}px   底部边距：{job.margin_v}px\n"
            f"📝 文案平台：{job.platform}   风格：{job.style}   深度分析：{'开' if job.analyze else '关'}\n"
        )

    def _on_pipeline_status(self, size: int) -> None:
        """AutoPipelineManager 队列变化回调（worker 线程）→ 信号转主线程"""
        self._sig_queue_changed.emit(size)

    def _on_pipeline_text(self, text: str) -> None:
        """AutoPipelineManager 阶段文本回调（worker 线程）→ 信号转主线程"""
        self._sig_pipeline_text.emit(text)

    def _update_queue_label(self, size: int) -> None:
        self._pending_count = size
        self._refresh_queue_label()

    def _update_pipeline_text(self, text: str) -> None:
        self._phase_text = text
        self._refresh_queue_label()

    def _refresh_queue_label(self) -> None:
        if not hasattr(self, "_queue_label"):
            return
        busy = AutoPipelineManager.instance().is_busy()
        parts = [f"队列: {self._pending_count}"]
        if self._phase_text:
            parts.append(self._phase_text)
        label = " | ".join(parts)
        self._queue_label.setText(label)
        self._queue_label.setStyleSheet(
            f"color: {PALETTE['accent']}; font-weight: bold; font-size: 13px; padding: 0 8px;"
            if not busy else
            f"color: {PALETTE['success']}; font-weight: bold; font-size: 13px; padding: 0 8px;"
        )

    # ------------------------------------------------------------------
    # 批量下载
    # ------------------------------------------------------------------
    def _start_batch(self) -> None:
        keyword = self._keyword.text().strip()
        language_code = self._batch_lang.currentData()
        category_code = self._batch_category.currentData()
        count = self._batch_count.value()
        min_dur = self._min_dur.value()
        max_dur = self._max_dur.value()

        self._set_running(True)
        self._show_progress(True)
        self._log(
            f"▶ 开始批量爬取: keyword='{keyword or '(语言热门)'}', lang={language_code}, "
            f"category={category_code}, count={count}, dur={min_dur}~{max_dur}s",
            "INFO",
        )

        def _run():
            video_path = ""
            try:
                from core.pipeline import PipelineConfig, run_pipeline

                cfg = PipelineConfig()
                cfg.search_mode = PipelineConfig.SEARCH_MODE_KEYWORD if keyword else PipelineConfig.SEARCH_MODE_LANGUAGE
                cfg.search_keyword = keyword
                cfg.language = language_code
                cfg.category_default = category_code
                cfg.video_count = count
                cfg.min_duration = min_dur
                cfg.max_duration = max_dur
                cfg.analyze_content = False

                result = run_pipeline(cfg)
                self._log(
                    f"✅ 批量完成: 爬取 {result.crawled} / 下载 {result.downloaded} / 字幕 {result.subtitled}",
                    "SUCCESS",
                )

                downloaded = result.downloaded_videos or []
                for v in downloaded:
                    p = v.get("local_video_path") or v.get("local_path") or v.get("file_path") or ""
                    if p and os.path.exists(p):
                        video_path = p
                        break
            except Exception as e:
                self._log(f"批量任务异常: {e}", "ERROR")
            finally:
                self._sig_thread_finished.emit()
                self._sig_batch_finished.emit(video_path, language_code)

        self._running_thread = spawn(target=_run, daemon=True)
        TaskManager.instance().register_thread(self._running_thread)
        self._running_thread.start()

    # ------------------------------------------------------------------
    # 下载完成后 — 给出结果，询问是否进入下一步
    # ------------------------------------------------------------------
    def _on_single_downloaded(self, video_path: str, language_code: str, video_id: str) -> None:
        tm = TaskManager.instance()
        ctx = tm.context
        ctx.video_path = video_path
        ctx.video_id = video_id
        ctx.language = language_code

        self._set_running(False)

        # 启动封面中文化处理（后台线程，不阻塞 UI）
        self._start_cover_analysis(video_path)

        folder = os.path.dirname(video_path)
        reply = QMessageBox.question(
            self, "下载完成",
            f"✅ 视频已保存：\n{video_path}\n\n"
            f"所在目录：{folder}\n\n"
            "打开文件夹？并进入下一步【语音识别与翻译】？\n"
            "[是] = 打开文件夹并跳转\n[否] = 仅跳转\n[取消] = 仅打开文件夹",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )

        if reply in (QMessageBox.Yes, QMessageBox.Cancel):
            try:
                os.startfile(folder)  # type: ignore[attr-defined]
            except Exception:
                pass

        if reply != QMessageBox.Cancel:
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            mw = self.window()
            if hasattr(mw, "switch_to_tab"):
                mw.switch_to_tab(1)

    def _offer_next_step(self, video_path: str, language_code: str, video_id: str) -> None:
        """跳过下载但已有文件时也允许进入下一步"""
        tm = TaskManager.instance()
        tm.context.video_path = video_path
        tm.context.video_id = video_id
        tm.context.language = language_code
        self._on_single_downloaded(video_path, language_code, video_id)

    # ------------------------------------------------------------------
    # 封面管线：下载/定位 → AI 翻译 → 展示
    # ------------------------------------------------------------------
    def _run_cover_pipeline(self, input_ref: str) -> None:
        """
        统一封面管线 — 同时支持 URL（远程下载）和本地文件路径两种输入。
        worker 线程中串行执行：下载(如果需要) → emit orig → localize → emit ai

        临时文件管理：
        - 原始封面（远程下载或本地副本）在 AI 处理完成后统一清理
        - AI 翻译封面保留在 _cover_ai_temp_path，供下载完成后迁移到目标文件夹
        """
        import tempfile
        import requests

        orig_temp: Optional[str] = None   # 远程下载的原始封面 tempfile，用完就删

        # Step 1: 拿本地文件路径
        local_path: str
        if input_ref.startswith(("http://", "https://")):
            # 远程 URL — 下载到临时文件
            try:
                self._log(f"📥 下载封面: {input_ref[:80]}...", "INFO")
                r = requests.get(input_ref, timeout=20, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/124.0.0.0 Safari/537.36",
                })
                r.raise_for_status()
                suffix = ".jpg"
                ctype = r.headers.get("Content-Type", "")
                if "png" in ctype:
                    suffix = ".png"
                elif "webp" in ctype:
                    suffix = ".webp"
                tmp_fd, local_path = tempfile.mkstemp(prefix="cover_orig_", suffix=suffix)
                with os.fdopen(tmp_fd, "wb") as fh:
                    fh.write(r.content)
                orig_temp = local_path   # ★ 登记，finally 里清理
                self._log(f"✅ 封面已下载到临时文件", "SUCCESS")
            except Exception as e:
                self._log(f"❌ 封面下载失败: {e}", "ERROR")
                return
        else:
            # 本地路径 — 直接用（不由我们创建，不负责清理）
            local_path = input_ref
            if not os.path.exists(local_path):
                self._log(f"❌ 封面文件不存在: {local_path}", "ERROR")
                return

        if not os.path.exists(local_path):
            self._log(f"❌ 封面文件不存在: {local_path}", "ERROR")
            return

        try:
            # Step 2: emit 原版封面（供 UI 预览）
            self._sig_cover_orig_ready.emit(local_path)

            # Step 3: AI 翻译（把图里的文字变成目标语言，其他不动）
            self._sig_cover_status.emit("⏳ AI 翻译处理中...")
            self._log(f"🖼 调用 Gemini 做封面中文化: {os.path.basename(local_path)}", "INFO")
            from core.gemini_engine import get_gemini_transcriber
            transcriber = get_gemini_transcriber()
            _summary, out_path = transcriber.localize_image_zh(local_path)
            if out_path and os.path.exists(out_path):
                self._cover_ai_temp_path = out_path  # 记录下来，下载完后复制到目标文件夹
                self._sig_cover_ai_ready.emit(out_path)
                self._log(f"✅ AI 翻译封面已输出: {os.path.basename(out_path)}", "SUCCESS")
            else:
                self._log("⚠ Gemini 返回了封面处理结果但路径无效", "WARNING")
                self._sig_cover_status.emit("⚠ AI 未返回有效图片")
        except Exception as e:
            import traceback
            self._log(f"❌ 封面 AI 处理失败: {e}\n{traceback.format_exc()}", "ERROR")
            self._sig_cover_status.emit(f"❌ AI 处理失败")
        finally:
            # ★ 清理：原始封面 tempfile（远程下载的那个）用完就删
            if orig_temp and os.path.exists(orig_temp):
                try:
                    os.remove(orig_temp)
                    self._log(f"🧹 原始封面临时文件已清理: {os.path.basename(orig_temp)}", "DEBUG")
                except OSError as e:
                    self._log(f"⚠ 清理原始封面 tempfile 失败: {e}", "WARNING")

    def _on_cover_orig_ready(self, path: str) -> None:
        """主线程槽：原版封面下载完成 → 加载展示"""
        from PySide6.QtGui import QPixmap
        pm = QPixmap(path)
        if pm.isNull():
            self._cover_orig.setText("⚠ 封面图片加载失败")
            return
        box_h = self._cover_orig.height() if self._cover_orig.height() > 100 else 220
        self._cover_orig.setPixmap(pm.scaledToHeight(box_h, Qt.SmoothTransformation))
        self._cover_orig.setStyleSheet("")  # 清除虚线框

    def _on_cover_ai_ready(self, path: str) -> None:
        """主线程槽：AI 翻译封面处理完成 → 加载展示"""
        from PySide6.QtGui import QPixmap
        pm = QPixmap(path)
        if pm.isNull():
            self._cover_ai.setText("⚠ AI 封面图片加载失败")
            return
        box_h = self._cover_ai.height() if self._cover_ai.height() > 100 else 220
        self._cover_ai.setPixmap(pm.scaledToHeight(box_h, Qt.SmoothTransformation))
        self._cover_ai.setStyleSheet("")  # 清除虚线框

    def _start_cover_analysis(self, video_path: str) -> None:
        """
        下载完成后整合封面管线：
        - 原版封面：yt-dlp 的 write_thumbnail 已保存到文件夹 → 刷新 UI 展示
        - AI 翻译封面：
            a) 如果获取信息阶段已有 tempfile → shutil.copy 到目标文件夹
            b) 否则（兜底：用户跳过获取信息直接下载）→ 找文件夹 jpg 跑 AI → 保存
        """
        folder = os.path.dirname(video_path)

        # --- 1. 刷新原版封面 UI（从 yt-dlp 产物加载）---
        orig_cover = self._find_folder_cover(folder)
        if orig_cover:
            self._sig_cover_orig_ready.emit(orig_cover)
            self._log(f"🖼 原封面已加载: {os.path.basename(orig_cover)}", "INFO")

        # --- 2. AI 翻译封面保存 ---
        import shutil
        dest_ai = os.path.join(folder, "cover_zh.jpg")

        def _cleanup_temp(temp_path: str, label: str = "AI 封面") -> None:
            """复制成功后删除源 tempfile（存在即删，不存在忽略，失败仅警告）"""
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    self._log(f"🧹 {label} 临时文件已清理: {os.path.basename(temp_path)}", "DEBUG")
                except OSError as e:
                    self._log(f"⚠ 删除 {label} tempfile 失败: {e}", "WARNING")

        if self._cover_ai_temp_path and os.path.exists(self._cover_ai_temp_path):
            # 主路径：获取信息阶段已生成 AI 封面 → 复制到目标文件夹 + 清理源 tempfile
            try:
                shutil.copy2(self._cover_ai_temp_path, dest_ai)
                self._log(f"✅ AI 翻译封面已保存: {dest_ai}", "SUCCESS")
                _cleanup_temp(self._cover_ai_temp_path, "AI 封面")
                self._cover_ai_temp_path = None
            except Exception as e:
                self._log(f"❌ AI 封面复制失败: {e}", "ERROR")
        else:
            # 兜底路径：用户跳过获取信息直接下载 → 现场跑 AI → 复制到目标文件夹 + 清理源
            if orig_cover:
                self._log(f"⚠ 无预生成 AI 封面，从文件夹 jpg 现场处理: {os.path.basename(orig_cover)}", "WARNING")
                def _run():
                    try:
                        from core.gemini_engine import get_gemini_transcriber
                        _summary, out_path = get_gemini_transcriber().localize_image_zh(orig_cover)
                        if out_path and os.path.exists(out_path):
                            try:
                                shutil.copy2(out_path, dest_ai)
                                self._sig_cover_ai_ready.emit(out_path)
                                self._log(f"✅ AI 翻译封面已保存（兜底）: {dest_ai}", "SUCCESS")
                                # ★ 清理兜底 AI 封面源文件
                                _cleanup_temp(out_path, "兜底 AI 封面")
                            except Exception as e2:
                                self._log(f"❌ 兜底 AI 封面复制失败: {e2}", "ERROR")
                        else:
                            self._log("⚠ 兜底：Gemini 未返回有效 AI 封面", "WARNING")
                    except Exception as e:
                        self._log(f"❌ 兜底 AI 处理失败: {e}", "ERROR")
                spawn(target=_run, daemon=True).start()
            else:
                self._log("⚠ 目标文件夹无原封面 jpg，跳过 AI 封面保存", "WARNING")

    def _find_folder_cover(self, folder: str) -> Optional[str]:
        """在视频输出文件夹里找 yt-dlp 保存的封面（jpg/png/webp）"""
        try:
            for fn in os.listdir(folder):
                if fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    fp = os.path.join(folder, fn)
                    # 跳过我们自己生成的 cover_zh
                    if fn.lower().startswith("cover_zh"):
                        continue
                    return fp
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_video_id(raw: str) -> str:
        import re
        s = raw.strip()

        # TikTok / 抖音：数字 id（短链会跟随一次重定向）
        from utils.video_url import detect_video_site, resolve_tiktok_id
        if detect_video_site(s) == "tiktok":
            return resolve_tiktok_id(s) or ""

        m = re.match(r"^([a-zA-Z0-9_-]{11})$", s)
        if m:
            return m.group(1)
        patterns = [
            r"[?&]v=([a-zA-Z0-9_-]{11})",
            r"youtu\.be/([a-zA-Z0-9_-]{11})",
            r"/shorts/([a-zA-Z0-9_-]{11})",
            r"/embed/([a-zA-Z0-9_-]{11})",
        ]
        for p in patterns:
            m = re.search(p, s)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def _find_existing_video(video_id: str) -> str:
        from utils.path_helper import get_output_dir
        import glob
        root = str(get_output_dir())
        if not os.path.isdir(root):
            return ""
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if fn.endswith(".mp4") and video_id in fn:
                    return os.path.join(dirpath, fn)
        return ""

    @staticmethod
    def _build_lang_options() -> List[tuple]:
        from utils.enums import LanguageType
        return [(m.value, f"{m.display_name} ({m.value})") for m in LanguageType]

    def _set_running(self, running: bool) -> None:
        tm = TaskManager.instance()
        tm.set_running(running)
        if hasattr(self, "_start_btn"):
            self._start_btn.setEnabled(not running)
        if hasattr(self, "_test_btn"):
            self._test_btn.setEnabled(not running)
        if hasattr(self, "_batch_start_btn"):
            self._batch_start_btn.setEnabled(not running)
        if hasattr(self, "_fetch_meta_btn"):
            self._fetch_meta_btn.setEnabled(not running)

    def _show_progress(self, show: bool) -> None:
        if getattr(self, "_progress", None) is not None:
            self._progress.setVisible(show)
        if getattr(self, "_batch_progress", None) is not None:
            self._batch_progress.setVisible(show)
