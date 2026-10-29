"""
PagePublish — 第 5 页：视频发布

左右分栏布局：
  左侧：平台账号管理（4 个平台 Tab，每个平台可多账号并存）
  右侧：视频池 + 发布表单 + 发布按钮

数据流：
  管线完成烧录 → 调 VideoPool.add() → 用户点"最近完成"从池里选
  → 选账号 → 编辑标题/简介/封面/标签 → 点发布
"""

import os
import time
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QTimer, QDateTime
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QLabel,
    QProgressBar, QMessageBox, QFileDialog, QTabWidget,
    QListWidget, QListWidgetItem, QSplitter, QTextEdit,
    QDateTimeEdit, QSpinBox, QSizePolicy, QToolButton, QDialog,
)

from ..task_manager import TaskManager
from ..theme import PALETTE, STATUS_COLORS, build_global_qss

from core.publish import (
    AccountManager,
    VideoPool,
    PublishService,
    PlatformClientFactory,
    PLATFORMS,
    POOL_STATUS,
    VideoMeta,
)


class PagePublish(QWidget):
    """发布页主容器"""

    # 外部钩子：由管线调用，把视频塞进来
    sig_prefill_pool = Signal(int)  # pool_id

    # AUDIT-0010: worker thread -> main thread UI signals
    _sig_upload_progress = Signal(int, int)       # uploaded, total
    _sig_publish_done = Signal(bool, dict)        # ok, result_dict
    # AUDIT-0010: 账号探测 worker → 主线程
    _sig_probe_progress = Signal(int)             # 已探测数
    _sig_probe_done = Signal(str)                 # platform_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_pool_id: Optional[int] = None
        self._current_account_id: Optional[int] = None
        self._current_platform: str = "bilibili"
        self._build()

        # AUDIT-0010: wire worker->main UI signals
        self._sig_upload_progress.connect(self._on_upload_progress)
        self._sig_publish_done.connect(self._on_publish_done)
        # AUDIT-0010: 账号探测
        self._sig_probe_progress.connect(self._on_probe_progress)
        self._sig_probe_done.connect(self._on_probe_done)
        self.refresh_context()

    # ------------------------------------------------------------------
    # UI 搭建
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([380, 1000])
        root.addWidget(splitter)

    def _build_left(self) -> QWidget:
        """平台账号管理区"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("📱 平台账号")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PALETTE['text_primary']};")
        layout.addWidget(title)

        # 平台 Tab
        self._platform_tabs = QTabWidget()
        for pid, pinfo in PLATFORMS.items():
            tab = self._build_platform_tab(pid)
            self._platform_tabs.addTab(tab, pinfo["label"])
        self._platform_tabs.currentChanged.connect(self._on_platform_changed)
        layout.addWidget(self._platform_tabs, 1)

        return panel

    def _build_platform_tab(self, platform_id: str) -> QWidget:
        """单个平台的账号管理 Tab"""
        wrapper = QWidget()
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(6)

        # 账号列表
        self._acc_lists: Dict[str, QListWidget] = getattr(self, "_acc_lists", {})
        lw = QListWidget()
        lw.setSelectionMode(QListWidget.SingleSelection)
        lw.itemClicked.connect(lambda item: self._select_account(platform_id, item))
        self._acc_lists[platform_id] = lw
        lay.addWidget(lw, 1)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ 添加账号")
        btn_add.clicked.connect(lambda: self._add_account_dialog(platform_id))
        btn_probe = QPushButton("🔍 探测有效性")
        btn_probe.clicked.connect(lambda: self._probe_accounts(platform_id))
        btn_del = QPushButton("🗑 删除")
        btn_del.clicked.connect(lambda: self._delete_selected_account(platform_id))
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_probe)
        btn_row.addWidget(btn_del)
        lay.addLayout(btn_row)

        return wrapper

    def _build_right(self) -> QWidget:
        """视频池 + 发布表单"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ---- 视频池选择 ----
        pool_group = QGroupBox("🎬 选择视频")
        pool_lay = QHBoxLayout(pool_group)

        btn_recent = QPushButton("📅 最近 3 天完成")
        btn_recent.setObjectName("PrimaryBtn")
        btn_recent.clicked.connect(lambda: self._show_video_pool(recent=True))
        btn_all = QPushButton("📂 所有视频")
        btn_all.clicked.connect(lambda: self._show_video_pool(recent=False))
        self._pool_info = QLabel("点击按钮选择要发布的视频")
        self._pool_info.setStyleSheet(f"color: {PALETTE['text_muted']}; padding: 4px;")

        pool_lay.addWidget(btn_recent)
        pool_lay.addWidget(btn_all)
        pool_lay.addWidget(self._pool_info, 1)
        layout.addWidget(pool_group)

        # ---- 发布表单 ----
        form_splitter = QSplitter(Qt.Horizontal)
        form_splitter.addWidget(self._build_cover_panel())
        form_splitter.addWidget(self._build_meta_panel())
        form_splitter.setStretchFactor(0, 1)
        form_splitter.setStretchFactor(1, 3)
        form_splitter.setSizes([300, 700])
        layout.addWidget(form_splitter, 1)

        # ---- 发布按钮 + 进度 ----
        action_row = QHBoxLayout()
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        self._publish_btn = QPushButton("🚀 立即发布")
        self._publish_btn.setObjectName("PrimaryBtn")
        self._publish_btn.setMinimumHeight(40)
        self._publish_btn.clicked.connect(self._do_publish)

        action_row.addWidget(self._progress, 1)
        action_row.addWidget(self._publish_btn)
        layout.addLayout(action_row)
        layout.addWidget(self._status_label)

        return panel

    def _build_cover_panel(self) -> QWidget:
        """封面预览 + 上传"""
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        title = QLabel("🖼 封面")
        title.setStyleSheet(f"font-weight: bold; color: {PALETTE['text_primary']};")
        lay.addWidget(title)

        self._cover_label = QLabel("未选择视频")
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setMinimumHeight(240)
        self._cover_label.setStyleSheet(
            f"background: {PALETTE['bg_input']}; border: 1px dashed {PALETTE['border']}; "
            f"border-radius: 6px; color: {PALETTE['text_muted']};"
        )
        lay.addWidget(self._cover_label, 1)

        row = QHBoxLayout()
        btn_pick = QPushButton("📁 选择封面")
        btn_pick.clicked.connect(self._pick_cover_file)
        btn_clear = QPushButton("✖")
        btn_clear.setFixedWidth(32)
        btn_clear.clicked.connect(lambda: self._set_cover(""))
        row.addWidget(btn_pick, 1)
        row.addWidget(btn_clear)
        lay.addLayout(row)

        self._cover_path: str = ""

        return panel

    def _build_meta_panel(self) -> QWidget:
        """标题 / 简介 / 标签 / 定时 / 原创"""
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(8)

        # 标题
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("填写一个吸引人的标题（建议 15-30 字）")
        self._title_edit.setMaxLength(80)
        form.addRow("📌 标题", self._title_edit)

        # 简介
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("视频简介，补充标题没说清楚的细节...")
        self._desc_edit.setMaximumHeight(120)
        self._desc_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form.addRow("📝 简介", self._desc_edit)

        # 标签
        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("用逗号分隔，如：科技,学习,德语")
        form.addRow("🏷 标签", self._tags_edit)

        # 分区（B站特有，其他平台忽略）
        self._category_edit = QLineEdit()
        self._category_edit.setPlaceholderText("B站分区 id（可选，默认 17=生活）")
        self._category_edit.setMaximumWidth(150)
        form.addRow("📂 分区", self._category_edit)

        # 定时发布
        self._scheduled_check = QCheckBox("🕐 定时发布")
        self._scheduled_check.stateChanged.connect(self._on_scheduled_toggled)
        self._scheduled_dt = QDateTimeEdit()
        self._scheduled_dt.setCalendarPopup(True)
        self._scheduled_dt.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self._scheduled_dt.setEnabled(False)
        self._scheduled_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        form.addRow(self._scheduled_check, self._scheduled_dt)

        # 原创声明 + 评论/合拍
        opt_row = QHBoxLayout()
        self._original_check = QCheckBox("✅ 原创声明")
        self._original_check.setChecked(True)
        self._comment_check = QCheckBox("💬 允许评论")
        self._comment_check.setChecked(True)
        self._duet_check = QCheckBox("🎭 允许合拍（抖音）")
        self._duet_check.setChecked(True)
        opt_row.addWidget(self._original_check)
        opt_row.addWidget(self._comment_check)
        opt_row.addWidget(self._duet_check)
        opt_row.addStretch(1)
        form.addRow("", opt_row)

        lay.addLayout(form)

        # 视频信息只读展示
        info_group = QGroupBox("ℹ️ 视频信息（只读）")
        info_lay = QFormLayout(info_group)
        self._info_video = QLabel("-")
        self._info_duration = QLabel("-")
        self._info_size = QLabel("-")
        self._info_source = QLabel("-")
        info_lay.addRow("视频文件", self._info_video)
        info_lay.addRow("时长", self._info_duration)
        info_lay.addRow("大小", self._info_size)
        info_lay.addRow("来源", self._info_source)
        lay.addWidget(info_group)

        return panel

    # ------------------------------------------------------------------
    # 平台 Tab 切换
    # ------------------------------------------------------------------

    def _on_platform_changed(self, idx: int) -> None:
        self._current_platform = self._platform_tabs.tabText(idx)
        # 从 label 反推 id
        for pid, pinfo in PLATFORMS.items():
            if pinfo["label"] == self._current_platform:
                self._current_platform = pid
                break
        self._refresh_account_list(self._current_platform)

    # ------------------------------------------------------------------
    # 账号管理
    # ------------------------------------------------------------------

    def _refresh_account_list(self, platform: str) -> None:
        lw = self._acc_lists.get(platform)
        if not lw:
            return
        lw.clear()
        accs = AccountManager.list_accounts(platform=platform, only_active=False)
        if not accs:
            item = QListWidgetItem("（暂无账号，点下方按钮添加）")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            lw.addItem(item)
            return
        for acc in accs:
            nickname = acc.get("nickname") or "未命名"
            status = acc.get("check_status", 0)
            status_icon = {0: "❓", 1: "✅", 2: "❌"}.get(status, "❓")
            src = acc.get("cookie_src", "")
            active_icon = "" if acc.get("is_active") else " 🔕"
            text = f"{status_icon} {nickname}{active_icon}  ·  {src}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, acc["id"])
            lw.addItem(item)

    def _select_account(self, platform: str, item: QListWidgetItem) -> None:
        acc_id = item.data(Qt.UserRole)
        if acc_id is None:
            return
        self._current_account_id = acc_id
        acc = AccountManager.get_account(acc_id)
        if acc:
            self._set_status(f"已选中账号: {acc.get('nickname') or '未命名'}")
            # 如果选了账号但还没选视频，发布按钮禁用
            self._update_publish_btn()

    def _add_account_dialog(self, platform: str) -> None:
        """弹出添加账号对话框"""
        from PySide6.QtWidgets import QInputDialog, QTextEdit

        dlg = QDialog(self)
        dlg.setWindowTitle(f"添加 {PLATFORMS[platform]['label']} 账号")
        dlg.setMinimumSize(520, 420)
        lay = QVBoxLayout(dlg)

        # CDP 快捷提取
        btn_cdp = QPushButton("🌐 从浏览器实时拉取 Cookie（推荐）")
        btn_cdp.setObjectName("PrimaryBtn")
        cdp_result = QLabel("")
        cdp_result.setStyleSheet(f"color: {PALETTE['text_muted']};")

        def _do_cdp(browser: str):
            cookies = AccountManager.cdp_extract_cookies(platform, browser)
            if cookies:
                cdp_result.setText(f"✅ Cookie 已拉取到剪贴板下方，记得粘贴到输入框")
                cookie_edit.setPlainText(cookies)
            else:
                cdp_result.setText("❌ 拉取失败，请手动粘贴")

        btn_edge = QPushButton("Edge 浏览器")
        btn_chrome = QPushButton("Chrome 浏览器")
        btn_edge.clicked.connect(lambda: _do_cdp("edge"))
        btn_chrome.clicked.connect(lambda: _do_cdp("chrome"))

        row = QHBoxLayout()
        row.addWidget(btn_cdp)
        row.addWidget(btn_edge)
        row.addWidget(btn_chrome)
        lay.addLayout(row)
        lay.addWidget(cdp_result)

        lay.addWidget(QLabel(
            "🔑 Cookie 字符串（Netscape / Cookie header / JSON）\n"
            "或官方开放平台凭证 JSON（含 \"auth_mode\":\"open_api\"，由 scripts/publish_open_oauth.py 生成）:"
        ))
        cookie_edit = QTextEdit()
        cookie_edit.setPlaceholderText("粘贴 cookie，或粘贴开放平台凭证 JSON...")
        lay.addWidget(cookie_edit, 1)

        lay.addWidget(QLabel("👤 昵称（可选，手动填方便辨认）:"))
        nick_edit = QLineEdit()
        lay.addWidget(nick_edit)

        def _save():
            cookies = cookie_edit.toPlainText().strip()
            if not cookies:
                QMessageBox.warning(dlg, "缺少 Cookie", "请先粘贴 cookie")
                return
            AccountManager.add_account(
                platform=platform,
                cookies=cookies,
                nickname=nick_edit.text().strip(),
                cookie_src="cdp" if "cdp" in cdp_result.text().lower() else "manual",
            )
            self._refresh_account_list(platform)
            dlg.close()

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        btn_save = QPushButton("💾 保存")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.clicked.connect(_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.close)
        save_row.addWidget(btn_cancel)
        save_row.addWidget(btn_save)
        lay.addLayout(save_row)

        dlg.exec()

    def _probe_accounts(self, platform: str) -> None:
        accs = AccountManager.list_accounts(platform=platform, only_active=False)
        if not accs:
            QMessageBox.information(self, "无账号", "请先添加账号")
            return

        self._set_status(f"探测 {len(accs)} 个账号中...")
        self._progress.setVisible(True)
        self._progress.setMaximum(len(accs))
        self._progress.setValue(0)

        # 闭包把 platform 带进去，probe_done 时回传
        def _work(_plat=platform):
            for i, acc in enumerate(accs):
                try:
                    AccountManager.verify_account(acc["id"])
                except Exception:
                    pass
                # AUDIT-0010: worker 线程只能 emit，不能碰 UI
                self._sig_probe_progress.emit(i + 1)
            self._sig_probe_done.emit(_plat)

        spawn(target=_work, daemon=True).start()

    def _delete_selected_account(self, platform: str) -> None:
        lw = self._acc_lists.get(platform)
        if not lw:
            return
        item = lw.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一个账号")
            return
        acc_id = item.data(Qt.UserRole)
        if acc_id is None:
            return
        reply = QMessageBox.question(
            self, "删除账号", "确定要删除这个账号吗？（cookie 将一并清除）",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        AccountManager.delete_account(acc_id)
        self._refresh_account_list(platform)
        if self._current_account_id == acc_id:
            self._current_account_id = None
            self._update_publish_btn()

    # ------------------------------------------------------------------
    # 视频池 & 表单填值
    # ------------------------------------------------------------------

    def refresh_context(self) -> None:
        """被 Tab 切换触发"""
        if hasattr(self, "_platform_tabs"):
            idx = self._platform_tabs.currentIndex()
            platform_label = self._platform_tabs.tabText(idx)
            for pid, pinfo in PLATFORMS.items():
                if pinfo["label"] == platform_label:
                    self._refresh_account_list(pid)
                    break

    def _show_video_pool(self, recent: bool = True) -> None:
        """弹出视频池列表，选中后自动填表单"""
        items = VideoPool.list_recent(hours=72) if recent else VideoPool.list_all()
        if not items:
            self._pool_info.setText("（暂无视频，请先在下载页烧录完成）")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("选择要发布的视频")
        dlg.setMinimumSize(720, 520)
        lay = QVBoxLayout(dlg)

        search = QLineEdit()
        search.setPlaceholderText("🔍 搜索标题或源 URL...")
        lay.addWidget(search)

        lw = QListWidget()
        for it in items:
            title = it.get("title_translated") or it.get("title_original") or os.path.basename(it["final_video_path"])
            src_tag = "全自动" if it.get("pipeline_source") == "auto" else "手动"
            pub_tag = POOL_STATUS.get(it.get("publish_status", 0), "?")
            ts = it.get("create_ts", 0)
            t_str = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
            text = f"[{src_tag}] {title}  ·  {t_str}  ·  {pub_tag}"
            li = QListWidgetItem(text)
            li.setData(Qt.UserRole, it["id"])
            lw.addItem(li)
        lay.addWidget(lw, 1)

        def _pick():
            item = lw.currentItem()
            if not item:
                return
            pool_id = item.data(Qt.UserRole)
            self._prefill_from_pool(pool_id)
            dlg.close()

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_ok = QPushButton("✅ 填入表单")
        btn_ok.setObjectName("PrimaryBtn")
        btn_ok.clicked.connect(_pick)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.close)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        lw.itemDoubleClicked.connect(lambda _i: _pick())
        dlg.exec()

    def _prefill_from_pool(self, pool_id: int) -> None:
        """把池里的视频信息填入右侧表单"""
        item = VideoPool.get(pool_id)
        if not item:
            return
        self._current_pool_id = pool_id

        # 标题
        self._title_edit.setText(item.get("title_translated") or item.get("title_original") or "")

        # 简介（翻译版优先）
        desc = item.get("desc_translated") or item.get("desc_original") or ""
        self._desc_edit.setPlainText(desc)

        # 标签（从 category 兜底，实际通常由用户手动填）
        self._tags_edit.setText("")

        # 封面（自动加载）
        cover = item.get("cover_path") or ""
        if cover and os.path.exists(cover):
            self._set_cover(cover)
        else:
            # 尝试自动从 output 目录找同名 jpg
            video_dir = os.path.dirname(item["final_video_path"])
            base = os.path.splitext(os.path.basename(item["final_video_path"]))[0]
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                cand = os.path.join(video_dir, base + ext)
                if os.path.exists(cand):
                    self._set_cover(cand)
                    break

        # 只读信息
        fp = item["final_video_path"]
        self._info_video.setText(os.path.basename(fp))
        size_mb = os.path.getsize(fp) / 1024 / 1024 if os.path.exists(fp) else 0
        self._info_size.setText(f"{size_mb:.1f} MB")
        dur = item.get("duration_sec", 0) or 0
        if dur > 0:
            m, s = divmod(dur, 60)
            self._info_duration.setText(f"{m}:{s:02d}")
        else:
            self._info_duration.setText("(未知)")
        src_tag = "全自动流水线" if item.get("pipeline_source") == "auto" else "手动操作"
        self._info_source.setText(f"{src_tag} · 创建于 {time.strftime('%m-%d %H:%M', time.localtime(item.get('create_ts', 0)))}")

        self._pool_info.setText(f"✅ 已选: {os.path.basename(fp)}")
        self._update_publish_btn()

    def _set_cover(self, path: str) -> None:
        self._cover_path = path
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                scaled = pix.scaled(
                    self._cover_label.width() or 280,
                    self._cover_label.height() or 240,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                self._cover_label.setPixmap(scaled)
                return
        self._cover_label.clear()
        self._cover_label.setText("未选择视频")

    def _pick_cover_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if path:
            self._set_cover(path)

    def _on_scheduled_toggled(self, state: int) -> None:
        self._scheduled_dt.setEnabled(state == Qt.Checked)

    # ------------------------------------------------------------------
    # 发布按钮
    # ------------------------------------------------------------------

    def _update_publish_btn(self) -> None:
        can_publish = self._current_pool_id is not None and self._current_account_id is not None
        self._publish_btn.setEnabled(can_publish)
        if not can_publish:
            tips = []
            if self._current_pool_id is None:
                tips.append("选择视频")
            if self._current_account_id is None:
                tips.append("选择账号")
            self._publish_btn.setText(f"🚀 请先 {' / '.join(tips)}")
        else:
            self._publish_btn.setText("🚀 立即发布")

    def _set_status(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _do_publish(self) -> None:
        if not self._current_pool_id or not self._current_account_id:
            QMessageBox.warning(self, "未就绪", "请先选择视频和账号")
            return
        if not self._title_edit.text().strip():
            QMessageBox.warning(self, "缺少标题", "标题不能为空")
            return

        # 组装 VideoMeta
        meta = VideoMeta(
            title=self._title_edit.text().strip(),
            description=self._desc_edit.toPlainText().strip(),
            tags=[t.strip() for t in self._tags_edit.text().split(",") if t.strip()],
            category=self._category_edit.text().strip(),
            cover_path=self._cover_path,
            scheduled_ts=(
                int(self._scheduled_dt.dateTime().toSecsSinceEpoch())
                if self._scheduled_check.isChecked() else None
            ),
            original_declaration=self._original_check.isChecked(),
            allow_comment=self._comment_check.isChecked(),
            allow_duet=self._duet_check.isChecked(),
        )

        self._publish_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._set_status("⏳ 上传中...")

        def _on_progress(uploaded: int, total: int) -> None:
            # AUDIT-0010: callback runs in worker thread, emit only
            self._sig_upload_progress.emit(uploaded, total)

        def _work():
            try:
                result = PublishService.publish(
                    pool_id=self._current_pool_id,
                    account_id=self._current_account_id,
                    meta=meta,
                    on_progress=_on_progress,
                )
                # AUDIT-0010: UI updates must happen in main thread
                self._sig_publish_done.emit(bool(result.get('ok')), dict(result))
            except Exception as e:
                import traceback
                self._sig_publish_done.emit(False, {
                    'error': f'{e}\n{traceback.format_exc()}',
                    'remote_id': '', 'remote_url': '',
                })

        spawn(target=_work, daemon=True).start()


    # ================================================================
    # AUDIT-0010: Main-thread slots (worker emit -> UI ops happen here)
    # ================================================================
    def _on_upload_progress(self, uploaded: int, total: int) -> None:
        """Main thread slot: progress callback from worker"""
        if total > 0:
            self._progress.setValue(int(uploaded / total * 100))

    def _on_probe_progress(self, count: int) -> None:
        """Main thread slot: 账号探测进度"""
        self._progress.setValue(count)

    def _on_probe_done(self, platform: str) -> None:
        """Main thread slot: 账号探测完成"""
        self._progress.setVisible(False)
        self._set_status("✅ 探测完成")
        self._refresh_account_list(platform)

    def _on_publish_done(self, ok: bool, result: dict) -> None:
        """Main thread slot: worker finished -> update UI + show dialog"""
        self._progress.setVisible(False)
        rid = result.get('remote_id', '')
        rurl = result.get('remote_url', '-')
        err = result.get('error', '')
        if ok:
            self._set_status(f'OK publish id={rid}')
            QMessageBox.information(
                self, 'Publish OK',
                f'Platform: {self._current_platform}\nID: {rid}\nURL: {rurl}',
            )
        else:
            self._set_status(f'FAIL publish: {err}')
            QMessageBox.critical(self, 'Publish FAIL', f'Error:\n{err}')
        self._update_publish_btn()
