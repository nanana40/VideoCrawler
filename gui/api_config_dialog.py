"""
API 与 Cookie 管理对话框（架构 v2）

四个 Tab：
  Tab 1: 🔑 API Key & 提供商管理   — 配置所有 provider（内置 + 用户自定义）
  Tab 2: 🍪 Cookie                — 下载用 Cookie（TikTok / 抖音 / YouTube 通用）
  Tab 3: 🎬 视频/音频处理          — 展示多模态模型（动态扫描 + 连通性 + 用户勾选）
  Tab 4: 📝 文字处理               — 展示文本模型（同上）

核心：不再硬编码任何模型清单。所有模型列表 = 从用户填入 API Key 的 provider
动态扫描 /models 端点 → 自动连通性测试 → 启发式能力打标 → 按 Tab 展示。
"""

from __future__ import annotations

import copy
import os
import time
import webbrowser
from typing import Dict, List, Any, Optional, Tuple

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QListWidget, QListWidgetItem, QPushButton,
    QDialogButtonBox, QMessageBox, QGroupBox, QComboBox, QTextEdit,
    QScrollArea, QSizePolicy, QFrame, QFileDialog,
)

from core.model_registry import (
    ModelRegistry, ProviderSpec, ModelInfo, BUILTIN_PROVIDERS,
)
from utils.config_loader import load_config
from utils.crypto_util import load_secret_config, save_secret_config
from utils.path_helper import get_config_path, get_cookies_file_path, get_data_dir

from .theme import PALETTE, STATUS_COLORS, tag_background as _tag_bg


# ---------------------------------------------------------------------------
# Tab 1: 提供商管理
# ---------------------------------------------------------------------------

class _ProviderRow(QFrame):
    """单个 provider 在 Tab 1 里的一行卡片"""

    edit_requested = Signal(str)   # provider_id
    delete_requested = Signal(str)

    def __init__(self, spec: ProviderSpec, parent=None) -> None:
        super().__init__(parent)
        self.spec_id = spec.id
        self._build(spec)

    def _build(self, spec: ProviderSpec) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("ProviderRow")

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)

        # 左侧：图标 + 名称 + 启用开关
        icon_label = QLabel(spec.icon)
        icon_label.setStyleSheet(f"font-size: 20px; color: {PALETTE['text_primary']};")
        icon_label.setFixedWidth(30)
        row.addWidget(icon_label)

        info_col = QVBoxLayout()
        name_row = QHBoxLayout()
        name_label = QLabel(f"<b>{spec.name}</b>")
        if spec.is_builtin:
            tag = QLabel("内置")
            tag.setStyleSheet(
                f"background: {_tag_bg(PALETTE['accent'])}; color: {PALETTE['accent']};"
                f" padding: 1px 6px; border-radius: 3px; font-size: 10px;"
            )
            name_row.addWidget(name_label)
            name_row.addWidget(tag)
        else:
            name_row.addWidget(name_label)
        name_row.addStretch(1)

        self.enable_cb = QCheckBox("启用")
        self.enable_cb.setChecked(spec.enabled)
        self.enable_cb.setStyleSheet(f"color: {PALETTE['text_secondary']};")
        name_row.addWidget(self.enable_cb)

        info_col.addLayout(name_row)

        detail = f"{spec.protocol}"
        if spec.base_url:
            detail += f"  ·  {spec.base_url}"
        if spec.api_key:
            masked = spec.api_key[:4] + "..." + spec.api_key[-4:] if len(spec.api_key) > 10 else "已填"
            detail += f"  ·  API Key: {masked}"
        else:
            detail += "  ·  ⚠️ 未填 API Key"
        detail_label = QLabel(detail)
        detail_label.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
        detail_label.setWordWrap(True)
        info_col.addWidget(detail_label)

        row.addLayout(info_col, 1)

        # 右侧：编辑/删除按钮
        btn_col = QVBoxLayout()
        btn_edit = QPushButton("✎")
        btn_edit.setFixedSize(28, 28)
        btn_edit.setToolTip("编辑此提供商")
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(spec.id))
        btn_col.addWidget(btn_edit)

        if not spec.is_builtin:
            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(28, 28)
            btn_del.setToolTip("删除此自定义提供商")
            btn_del.clicked.connect(lambda: self.delete_requested.emit(spec.id))
            btn_col.addWidget(btn_del)

        row.addLayout(btn_col)


class _ProviderEditDialog(QDialog):
    """编辑 / 新建一个 provider（内置只读部分字段）"""

    def __init__(self, spec: Optional[ProviderSpec] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑提供商" if spec else "添加自定义提供商")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._spec = copy.deepcopy(spec) if spec else None

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_edit = QLineEdit(spec.name if spec else "")
        self.name_edit.setPlaceholderText("显示名，如 '我的自建 API'")
        form.addRow("名称:", self.name_edit)

        self.id_edit = QLineEdit(spec.id if spec else "")
        self.id_edit.setPlaceholderText("唯一 ID，如 custom_1（字母+下划线）")
        if spec and spec.is_builtin:
            self.id_edit.setEnabled(False)
        form.addRow("ID:", self.id_edit)

        self.icon_edit = QLineEdit(spec.icon if spec else "🤖")
        self.icon_edit.setMaximumWidth(40)
        form.addRow("图标:", self.icon_edit)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems([
            "openai_chat_completions",   # 多数兼容
            "gemini_generate_content",  # Google Gemini 原生
        ])
        idx = self.protocol_combo.findText(spec.protocol if spec else "openai_chat_completions")
        if idx >= 0:
            self.protocol_combo.setCurrentIndex(idx)
        if spec and spec.is_builtin:
            self.protocol_combo.setEnabled(False)
        form.addRow("协议:", self.protocol_combo)

        self.url_edit = QLineEdit(spec.base_url if spec else "")
        self.url_edit.setPlaceholderText("https://api.example.com/v1")
        if spec and spec.is_builtin:
            self.url_edit.setReadOnly(True)
            self.url_edit.setStyleSheet(f"color: {PALETTE['text_muted']};")
        form.addRow("Base URL:", self.url_edit)

        self.key_edit = QLineEdit(spec.api_key if spec else "")
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("在此粘贴 API Key")
        form.addRow("API Key:", self.key_edit)

        self.ua_edit = QLineEdit(spec.user_agent or "" if spec else "")
        self.ua_edit.setPlaceholderText("可选：覆盖 User-Agent（Groq 等 Cloudflare WAF 需要）")
        form.addRow("User-Agent:", self.ua_edit)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        pid = self.id_edit.text().strip()
        if not name or not pid:
            QMessageBox.warning(self, "信息缺失", "名称和 ID 必填")
            return
        if not self._spec:
            self._spec = ProviderSpec(
                id=pid, name=name, protocol=self.protocol_combo.currentText(),
                base_url=self.url_edit.text().strip(),
                api_key=self.key_edit.text().strip(),
                enabled=True,
                icon=self.icon_edit.text().strip() or "🤖",
                user_agent=self.ua_edit.text().strip() or None,
            )
        else:
            self._spec.name = name
            self._spec.base_url = self.url_edit.text().strip()
            self._spec.api_key = self.key_edit.text().strip()
            self._spec.enabled = True  # 编辑时自动启用
            self._spec.icon = self.icon_edit.text().strip() or self._spec.icon
            ua = self.ua_edit.text().strip()
            self._spec.user_agent = ua or None
        self.accept()

    def get_spec(self) -> Optional[ProviderSpec]:
        return self._spec


class _YouTubeKeySection(QGroupBox):
    """Tab 1 顶部的 YouTube Data API Key 区域（搜索功能用，独立于 LLM provider）

    密钥保存在加密配置 api_secret.yaml.enc 的 youtube_api_key 字段，
    由 core/spiders/youtube_api_client.py 读取。
    """

    DOCS_URL = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"

    def __init__(self) -> None:
        super().__init__("🌐 YouTube 数据 API（按语言搜索视频时使用）")
        self._build()
        self._reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        tip = QLabel(
            "仅「按语言自动搜索」需要；不填不影响手动粘贴链接下载。"
            "获取：Google Cloud Console → 启用 YouTube Data API v3 → 创建 API 密钥。"
            "（填完请点右侧「💾 保存」）"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(tip)

        row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("AIza...（留空表示不使用）")
        row.addWidget(self.key_edit, 1)

        btn_show = QPushButton("👁")
        btn_show.setCheckable(True)
        btn_show.setToolTip("显示 / 隐藏 Key")
        btn_show.setFixedWidth(36)
        btn_show.toggled.connect(
            lambda on: self.key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(btn_show)

        btn_save = QPushButton("💾 保存")
        btn_save.clicked.connect(self._on_save)
        row.addWidget(btn_save)

        btn_open = QPushButton("🔗 获取页面")
        btn_open.setToolTip("在浏览器打开 Google Cloud 的 YouTube Data API 页面")
        btn_open.clicked.connect(lambda: webbrowser.open(self.DOCS_URL))
        row.addWidget(btn_open)
        layout.addLayout(row)

        self.status = QLabel("")
        layout.addWidget(self.status)

    def _reload(self) -> None:
        key = ""
        try:
            key = str((load_secret_config() or {}).get("youtube_api_key") or "")
        except Exception:
            key = ""
        self.key_edit.setText(key)
        self._set_status(bool(key))

    def _set_status(self, configured: bool, saved: bool = False) -> None:
        if configured:
            self.status.setText(
                "✅ 已配置（修改后下次搜索生效）" if saved else "✅ 已配置"
            )
            self.status.setStyleSheet(f"color: {STATUS_COLORS['ok']};")
        else:
            self.status.setText("⚠️ 未配置 —— 无法按语言自动搜索，手动链接下载不受影响")
            self.status.setStyleSheet(f"color: {STATUS_COLORS['warn']};")

    def _on_save(self) -> None:
        key = self.key_edit.text().strip()
        try:
            secret = load_secret_config() or {}
            secret["youtube_api_key"] = key
            save_secret_config(secret)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法写入加密配置：\n{e}")
            return
        self._set_status(bool(key), saved=True)


class _ProviderTab(QWidget):
    """Tab 1: 提供商列表 + 编辑"""

    providers_changed = Signal()

    def __init__(self, registry: ModelRegistry) -> None:
        super().__init__()
        self.registry = registry
        self._build()
        self.registry.models_discovered.connect(self._on_discovered)

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            "📋 配置所有 LLM 提供商。内置 3 个（Gemini / Groq / GLM）字段不可改协议/URL，"
            "只需填 API Key。下方可添加任意自定义提供商。"
        )
        header.setWordWrap(True)
        header.setStyleSheet(f"color: {PALETTE['text_muted']}; padding:4px 2px 10px 2px;")
        layout.addWidget(header)

        # YouTube Data API Key（搜索功能用，非 LLM provider）
        layout.addWidget(_YouTubeKeySection())

        # 滚动区放 provider 卡片
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(6)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ 添加自定义提供商")
        btn_add.clicked.connect(self._on_add_custom)
        btn_test_all = QPushButton("🔌 扫描全部已启用")
        btn_test_all.clicked.connect(self._on_scan_all)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_test_all)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        # 先同步启用状态
        for i in range(self._container_layout.count()):
            row = self._container_layout.itemAt(i).widget()
            if isinstance(row, _ProviderRow):
                spec = self.registry.get_provider(row.spec_id)
                if spec and row.enable_cb.isChecked() != spec.enabled:
                    spec.enabled = row.enable_cb.isChecked()

        # 清理
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        specs = self.registry.list_providers()
        if not specs:
            empty = QLabel("⚠️ 未配置任何提供商。点击下方按钮添加。")
            empty.setStyleSheet(f"color: {PALETTE['text_muted']}; padding:20px;")
            self._container_layout.addWidget(empty)
        for spec in specs:
            row = _ProviderRow(spec)
            row.enable_cb.toggled.connect(lambda checked, pid=spec.id: self._on_enable_changed(pid, checked))
            row.edit_requested.connect(self._on_edit)
            row.delete_requested.connect(self._on_delete)
            self._container_layout.addWidget(row)
        self._container_layout.addStretch(1)

    def _on_enable_changed(self, pid: str, checked: bool) -> None:
        spec = self.registry.get_provider(pid)
        if spec:
            spec.enabled = checked
            self.providers_changed.emit()

    def _on_add_custom(self) -> None:
        dlg = _ProviderEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.get_spec():
            spec = dlg.get_spec()
            if spec and not spec.id.startswith("builtin_"):
                spec.is_builtin = False
                self.registry.upsert_provider(spec)
                self._refresh()
                self.providers_changed.emit()

    def _on_edit(self, pid: str) -> None:
        spec = self.registry.get_provider(pid)
        if not spec:
            return
        dlg = _ProviderEditDialog(spec, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.get_spec():
            updated = dlg.get_spec()
            updated.is_builtin = spec.is_builtin
            self.registry.upsert_provider(updated)
            self._refresh()
            self.providers_changed.emit()

    def _on_delete(self, pid: str) -> None:
        spec = self.registry.get_provider(pid)
        if spec and spec.is_builtin:
            return
        confirm = QMessageBox.question(
            self, "删除",
            f"确认删除自定义提供商 '{spec.name}'？\n关联的所有模型勾选会一起清除。"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.registry.remove_provider(pid)
            self._refresh()
            self.providers_changed.emit()

    def _on_scan_all(self) -> None:
        self.registry.discover_all_enabled()
        QMessageBox.information(
            self, "扫描已触发",
            "正在后台扫描所有已启用提供商的可用模型...\n完成后 Tab 2/3 会自动刷新。"
        )

    def _on_discovered(self, provider_id: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Tab 2 & 3: 按功能分组的模型选择（视频/音频 & 文字）
# ---------------------------------------------------------------------------

class _ModelRow(QFrame):
    """Tab 2/3 里单个模型的一行卡片"""

    toggled = Signal(str, bool)   # (model_name, checked)
    skip_toggled = Signal(str, bool)  # (model_name, skip)

    def __init__(self, spec: ProviderSpec, mi: ModelInfo, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.mi = mi
        self.spec = spec
        self._checked = checked
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("ModelRow")
        self._build()

    def _build(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)

        # 连通性 emoji（左边）— 只用 PALETTE 的低饱和状态色
        ok = self.mi.ok
        ok_color = {
            True:  PALETTE['success'],
            False: PALETTE['fail'],
            None:  PALETTE['text_muted'],
        }.get(ok, PALETTE['text_muted'])
        ok_label = QLabel(emoji if (emoji := self.mi.status_emoji()) else "⏳")
        ok_label.setStyleSheet(f"color:{ok_color};font-size:16px;min-width:22px;")
        ok_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(ok_label)

        # 勾选框
        self.cb = QCheckBox()
        self.cb.setChecked(self._checked)
        self.cb.stateChanged.connect(
            lambda s: self.toggled.emit(self.mi.name, s == Qt.CheckState.Checked.value)
        )
        row.addWidget(self.cb)

        # 跳过探测勾选框（🚫）
        self.cb_skip = QCheckBox()
        self.cb_skip.setChecked(self.mi.skip_probe)
        self.cb_skip.setToolTip("勾选后跳过该模型的连通性探测，节省时间")
        if self.mi.skip_probe:
            self.cb_skip.setStyleSheet(f"color:{PALETTE['text_muted']};")
        self.cb_skip.stateChanged.connect(
            lambda s: self.skip_toggled.emit(self.mi.name, s == Qt.CheckState.Checked.value)
        )
        row.addWidget(self.cb_skip)

        # provider 图标 + 名称 + 模型名
        info_col = QVBoxLayout()
        first_row = QHBoxLayout()
        icon = QLabel(self.spec.icon)
        icon.setStyleSheet(f"font-size:14px; color: {PALETTE['text_primary']};")
        icon.setFixedWidth(22)
        first_row.addWidget(icon)

        # provider 名 — 用内联 span 保持低饱和
        prov_fg = PALETTE['text_muted']
        prov_label = QLabel(
            f"<span style='color:{prov_fg};font-size:11px'>{self.spec.name}</span>"
        )
        first_row.addWidget(prov_label)
        first_row.addStretch(1)

        # 模型名 — 唯一稍亮的主视觉元素
        self.model_label = QLabel(f"<b>{self.mi.name}</b>")
        self.model_label.setStyleSheet(f"color: {PALETTE['text_primary']};")
        first_row.addWidget(self.model_label)

        # 能力标签 — 全部降饱和
        cap_colors = {
            "video":      PALETTE['cap_video'],
            "audio":      PALETTE['cap_audio'],
            "multimodal": PALETTE['cap_multimodal'],
            "text":       PALETTE['cap_text'],
            "vision":     PALETTE['cap_vision'],
            "tts":        PALETTE['cap_tts'],
            "image":      PALETTE['cap_image'],
        }
        cap_labels = {
            "video": "视频", "audio": "音频", "multimodal": "多模态",
            "text": "文本", "vision": "视觉", "tts": "TTS", "image": "生图",
        }
        for cap in sorted(self.mi.capabilities):
            if cap in ("text",):
                continue
            fg = cap_colors.get(cap, PALETTE['text_muted'])
            lbl = cap_labels.get(cap, cap)
            tag = QLabel(f" {lbl} ")
            tag.setStyleSheet(
                f"background: {_tag_bg(fg)}; color: {fg};"
                f" padding: 1px 6px; border-radius: 3px; font-size: 10px;"
            )
            first_row.addWidget(tag)
        first_row.addStretch(1)

        info_col.addLayout(first_row)

        # 连通性详情 — 一律用 muted 灰，不再跟 ok_color 饱和红
        if self.mi.ok_message:
            status_label = QLabel(self.mi.ok_message)
            status_label.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
            status_label.setWordWrap(True)
            info_col.addWidget(status_label)

        row.addLayout(info_col, 1)

    def set_ok(self, ok: Optional[bool], msg: str) -> None:
        self.mi.ok = ok
        self.mi.ok_message = msg
        # 重建（简化起见：用 tooltip 显示详情）
        if msg:
            self.setToolTip(f"{self.mi.name}\n{msg}")

    def is_checked(self) -> bool:
        return self.cb.isChecked()

    def set_checked(self, checked: bool) -> None:
        self.cb.blockSignals(True)
        self.cb.setChecked(checked)
        self.cb.blockSignals(False)


class _FunctionTab(QWidget):
    """Tab 2 / Tab 3：按 capability 过滤的模型列表"""

    def __init__(self, registry: ModelRegistry, capability: str, title: str, description: str, parent=None) -> None:
        super().__init__(parent)
        self.registry = registry
        self.capability = capability
        self.title = title
        self.description = description
        self._row_by_key: Dict[tuple, _ModelRow] = {}   # (provider_id, model_name) → row

        self._build()
        self._connect_signals()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        desc = QLabel(self.title + "\n" + self.description)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {PALETTE['text_muted']}; padding:4px 2px 10px 2px;")
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(4)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        self.btn_retest = QPushButton("🔌 重新测试连通性")
        self.btn_retest.clicked.connect(self._on_retest)
        self.btn_scan = QPushButton("🔄 重新扫描全部")
        self.btn_scan.clicked.connect(self._on_rescan)
        self.btn_checked_label = QLabel("")
        self.btn_checked_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        btn_row.addWidget(self.btn_retest)
        btn_row.addWidget(self.btn_scan)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_checked_label)
        layout.addLayout(btn_row)

        self._refresh()

    def _connect_signals(self) -> None:
        self.registry.models_discovered.connect(self._on_discovered)
        self.registry.connectivity_changed.connect(self._on_connectivity_changed)

    def _refresh(self) -> None:
        # 先保存当前勾选状态
        prev_checked: Dict[tuple, bool] = {
            k: row.is_checked() for k, row in self._row_by_key.items()
        }

        # 清理
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row_by_key.clear()

        models = self.registry.get_models_for_capability(self.capability)
        if not models:
            # 看一眼是不是根本没启用 provider
            any_enabled = any(s.enabled and s.api_key for s in self.registry.list_providers())
            if not any_enabled:
                empty = QLabel(
                    "⚠️ 还没配置任何已启用的 API Key。\n"
                    "请到第一个 Tab「🔑 API Key & 提供商管理」里配置。"
                )
            else:
                empty = QLabel(
                    "⚠️ 已配置 API Key，但扫描还没跑或没发现匹配的模型。\n"
                    "点击下方「🔄 重新扫描全部」触发。"
                )
            empty.setStyleSheet(f"color: {PALETTE['text_muted']}; padding:20px;")
            self._container_layout.addWidget(empty)
            self._update_checked_label()
            return

        function_name = "video" if self.capability in ("video", "audio", "multimodal") else "text"
        checked_entries = self.registry.get_function_models(function_name)
        checked_set: set = {(e.get("provider", ""), e.get("model", "")) for e in checked_entries}

        for mi in models:
            spec = self.registry.get_provider(mi.provider_id)
            if not spec:
                continue
            key = (mi.provider_id, mi.name)
            default_checked = prev_checked.get(key) if key in prev_checked else (key in checked_set)
            row = _ModelRow(spec, mi, checked=default_checked)
            row.toggled.connect(lambda mname, checked, pid=mi.provider_id: self._on_row_toggled(pid, mname, checked))
            row.skip_toggled.connect(lambda mname, skip, pid=mi.provider_id: self.registry.set_skip_probe(pid, mname, skip))
            self._container_layout.addWidget(row)
            self._row_by_key[key] = row

        self._container_layout.addStretch(1)
        self._update_checked_label()

    def _on_row_toggled(self, provider_id: str, model_name: str, checked: bool) -> None:
        function_name = "video" if self.capability in ("video", "audio", "multimodal") else "text"
        entries = self.registry.get_function_models(function_name)
        key = {"provider": provider_id, "model": model_name}
        if checked:
            if key not in entries:
                entries.append(key)
        else:
            entries = [e for e in entries if e != key]
        self.registry.set_function_models(function_name, entries)
        self._update_checked_label()

    def _update_checked_label(self) -> None:
        function_name = "video" if self.capability in ("video", "audio", "multimodal") else "text"
        count = len(self.registry.get_function_models(function_name))
        total = len(self._row_by_key)
        self.btn_checked_label.setText(f"✅ 已选 {count} / {total}")

    def _on_discovered(self, provider_id: str) -> None:
        self._refresh()

    def _on_connectivity_changed(self, provider_id: str, model_name: str, ok, msg: str) -> None:
        row = self._row_by_key.get((provider_id, model_name))
        if row:
            row.set_ok(ok, msg)

    def _on_retest(self) -> None:
        # 只测当前 Tab 里出现的模型，排除 skip_probe
        targets: List[Tuple[str, str]] = []
        for (pid, mname), row in self._row_by_key.items():
            if not row.mi.skip_probe:
                targets.append((pid, mname))
        if not targets:
            QMessageBox.information(self, "提示", "当前没有可测试的模型（全部已勾选跳过探测）。")
            return
        self.btn_retest.setEnabled(False)
        from utils.thread_spawn import spawn  # AUDIT-0033
        def _run():
            for pid, mname in targets:
                self.registry.test_model(pid, mname)
            import PySide6.QtCore as qtc
            qtc.QMetaObject.invokeMethod(self.btn_retest, "setEnabled", qtc.Qt.ConnectionType.QueuedConnection,
                                         qtc.Q_ARG(bool, True))
        spawn(_run, name="api_retest").start()

    def _on_rescan(self) -> None:
        self.registry.discover_all_enabled()


class _CookieTab(QWidget):
    """Tab 2：下载用 Cookie（TikTok / 抖音 / YouTube 通用）

    内容保存到数据目录的 data/browser_cookies.txt，
    由 VideoDownloader 与 TiktokSpider 自动读取，保存后立即生效。
    """

    def __init__(self) -> None:
        super().__init__()
        self._loaded_text = ""
        self._build()
        self._reload()

    # ---- UI ----
    def _build(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            "Cookie 是平台登录态凭证：TikTok / 抖音必须提供才能解析下载；"
            "YouTube 遇到风控时也会用到。内容只保存在本机，不会上传。"
        )
        header.setWordWrap(True)
        header.setStyleSheet(f"color: {PALETTE['text_muted']}; padding:4px 2px 10px 2px;")
        layout.addWidget(header)

        box = QGroupBox("🍪 下载 Cookie（Netscape 格式）")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)

        tip = QLabel(
            "用浏览器扩展 Cookie-Editor / Get cookies.txt LOCALLY 导出后粘贴到下面。"
            "抖音需包含 s_v_web_id 与 ttwid，TikTok 需包含 ttwid / msToken。"
            "保存后立即生效，无需重启。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {PALETTE['text_muted']};")
        v.addWidget(tip)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText(
            "# Netscape HTTP Cookie File\n"
            ".tiktok.com\tTRUE\t/\tTRUE\t1793334770\tttwid\t...\n"
            ".douyin.com\tTRUE\t/\tFALSE\t1793334770\ts_v_web_id\t..."
        )
        self.editor.setMinimumHeight(240)
        v.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 保存并生效")
        btn_save.clicked.connect(lambda: self.save(silent=False))
        btn_import = QPushButton("📂 从文件导入")
        btn_import.setToolTip("选择一个已导出的 cookies.txt，把内容读进来")
        btn_import.clicked.connect(self._on_import)
        btn_guide = QPushButton("📖 获取与维护教程")
        btn_guide.clicked.connect(self._on_guide)
        btn_dir = QPushButton("📂 打开存放目录")
        btn_dir.setToolTip("打开 browser_cookies.txt 所在的数据目录")
        btn_dir.clicked.connect(self._on_open_dir)
        for b in (btn_save, btn_import, btn_guide, btn_dir):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        layout.addWidget(box)

        note = QLabel(
            "说明：发布账号的 Cookie（B站 / 抖音 / 小红书 / 快手）不在这里配置，"
            "每个账号一份，请到「⑤ 视频发布」页 → 添加账号。"
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {PALETTE['text_muted']}; padding:8px 2px;")
        layout.addWidget(note)
        layout.addStretch(1)

    # ---- 读写 ----
    def _reload(self) -> None:
        content = ""
        try:
            path = get_cookies_file_path()
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""
        self._loaded_text = content
        self.editor.setPlainText(content)
        self._refresh_status()

    @staticmethod
    def _count_entries(text: str) -> int:
        """统计合法 Cookie 行（每行 7 列、Tab 分隔；跳过纯注释行）"""
        return sum(
            1 for ln in text.splitlines()
            if ln.count("\t") >= 6 and ln.strip() and not ln.lstrip().startswith("# ")
        )

    def _refresh_status(self) -> None:
        text = self._loaded_text
        count = self._count_entries(text)
        path = get_cookies_file_path()
        if not path.exists() or count == 0:
            self.status.setText(f"⚠️ 未配置 —— TikTok / 抖音 无法下载。保存后写入 {path}")
            self.status.setStyleSheet(f"color: {STATUS_COLORS['warn']};")
            return

        has_tt = "tiktok.com" in text or "douyin.com" in text
        try:
            age_days = int((time.time() - path.stat().st_mtime) / 86400)
        except Exception:
            age_days = 0
        parts = [f"✅ 已配置 {count} 条 Cookie"]
        parts.append("含 TikTok/抖音域" if has_tt else "未包含 TikTok/抖音域")
        if age_days >= 14:
            parts.append(f"已 {age_days} 天未更新，解析失败时请重新导出")
        parts.append(str(path))
        self.status.setText("　·　".join(parts))
        self.status.setStyleSheet(
            f"color: {STATUS_COLORS['warn'] if (age_days >= 14 or not has_tt) else STATUS_COLORS['ok']};"
        )

    def save(self, silent: bool = True) -> bool:
        """把编辑框内容写入 browser_cookies.txt（空内容表示清除）"""
        text = self.editor.toPlainText().strip()
        if text and self._count_entries(text) == 0:
            if not silent:
                QMessageBox.warning(
                    self, "格式不对",
                    "没有识别到任何一行合法 Cookie（每行 7 列、Tab 分隔）。\n"
                    "请确认导出的是 Netscape 格式，而不是 JSON。",
                )
            return False

        path = get_cookies_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if text:
                if not text.endswith("\n"):
                    text += "\n"
                path.write_text(text, encoding="utf-8")
            elif path.exists():
                path.unlink()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法写入：\n{path}\n{e}")
            return False

        self._loaded_text = text
        self._refresh_status()
        if not silent:
            QMessageBox.information(self, "已保存", "✅ Cookie 已保存并立即生效。")
        return True

    def save_if_dirty(self) -> bool:
        """底部「保存」按钮调用：内容有改动才写盘，避免误覆盖"""
        if self.editor.toPlainText().strip() == self._loaded_text.strip():
            return True
        return self.save(silent=True)

    # ---- 按钮 ----
    def _on_import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择 cookies 文件", "", "Cookie 文件 (*.txt);;所有文件 (*.*)"
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"{filename}\n{e}")
            return
        if self._count_entries(content) == 0:
            QMessageBox.warning(
                self, "格式不对",
                "该文件里没有合法的 Netscape Cookie 行。\n"
                "请用 Cookie-Editor 的 Export（不是 JSON 导出）。",
            )
            return
        self.editor.setPlainText(content)
        self.status.setText("已读入文件，点「💾 保存并生效」写入")
        self.status.setStyleSheet(f"color: {STATUS_COLORS['warn']};")

    def _on_guide(self) -> None:
        from .onboarding import show_guide
        show_guide(self, "tiktok_cookie")

    def _on_open_dir(self) -> None:
        try:
            os.startfile(str(get_data_dir()))  # type: ignore[attr-defined]
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))


# ---------------------------------------------------------------------------
# ApiConfigDialog — 主对话框（4 个 Tab）
# ---------------------------------------------------------------------------

class ApiConfigDialog(QDialog):
    """API 与 Cookie 管理主对话框"""

    config_saved = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🔧 API 与 Cookie 管理")
        self.setMinimumSize(720, 720)
        self.resize(820, 820)

        self.registry = ModelRegistry.instance()
        self.registry.load_from_config()

        self.tabs = QTabWidget()
        self._tab_providers = _ProviderTab(self.registry)
        self._tab_cookie = _CookieTab()
        self._tab_video = _FunctionTab(
            self.registry,
            capability="video",
            title="🎬 视频/音频处理",
            description="所有原生支持 video/audio modality 的模型（供视频下载 → 语音识别 → 翻译 使用）",
        )
        self._tab_text = _FunctionTab(
            self.registry,
            capability="text",
            title="📝 文字处理",
            description="所有支持文本对话的模型（供翻译 / 文案生成 使用）",
        )

        self.tabs.addTab(self._tab_providers, "🔑 API Key & 提供商")
        self.tabs.addTab(self._tab_cookie, "🍪 Cookie")
        self.tabs.addTab(self._tab_video, "🎬 视频/音频处理")
        self.tabs.addTab(self._tab_text, "📝 文字处理")

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Save).setText("💾 保存并触发扫描")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(button_box)

        self._apply_style()

    def _apply_style(self) -> None:
        """统一应用低饱和深色调色板 — 所有硬编码颜色取 PALETTE"""
        P = PALETTE
        self.setStyleSheet(f"""
            /* ===== 最外层：对话框 + 所有直接子 widget ===== */
            QDialog {{
                background: {P['bg_dialog']};
                color: {P['text_primary']};
            }}
            /* 关键：给 QWidget 也设深色背景，解决滚动区/容器白底漏出 */
            QWidget {{
                background: transparent;
                color: {P['text_primary']};
            }}
            QLabel {{
                color: {P['text_primary']};
                background: transparent;
            }}
            QFrame {{
                background: transparent;
            }}

            /* ===== 输入控件 ===== */
            QLineEdit, QComboBox, QTextEdit {{
                background: {P['bg_input']};
                color: {P['text_primary']};
                border: 1px solid {P['border']};
                border-radius: 4px;
                padding: 5px 8px;
                selection-background-color: {P['bg_selected']};
                selection-color: {P['text_primary']};
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border-color: {P['accent']};
            }}
            QLineEdit[readOnly="true"] {{
                background: {P['bg_card']};
                color: {P['text_muted']};
            }}

            /* ===== Tab ===== */
            QTabWidget::pane {{
                border: 1px solid {P['border']};
                background: {P['bg_dialog']};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {P['bg_card']};
                color: {P['text_secondary']};
                padding: 6px 14px;
                border: 1px solid {P['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {P['bg_dialog']};
                color: {P['text_primary']};
                border-bottom: 2px solid {P['accent']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {P['text_primary']};
                background: {P['bg_hover']};
            }}

            /* ===== 按钮 ===== */
            QPushButton {{
                background: {P['bg_card']};
                color: {P['text_primary']};
                border: 1px solid {P['border']};
                padding: 5px 12px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background: {P['bg_hover']};
                border-color: {P['accent']};
            }}
            QPushButton:pressed {{
                background: {P['bg_selected']};
            }}
            QPushButton:disabled {{
                background: {P['bg_input']};
                color: {P['text_muted']};
            }}

            /* ===== Checkbox：深色版，选中色和 accent 统一 ===== */
            QCheckBox {{
                color: {P['text_primary']};
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {P['border']};
                border-radius: 3px;
                background: {P['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {P['accent']};
                border-color: {P['accent']};
                image: none;
            }}

            /* ===== 滚动条：深色，解决白白条漏出 ===== */
            QScrollArea {{
                border: none;
                background: {P['bg_dialog']};
            }}
            QScrollBar:vertical {{
                background: {P['bg_dialog']};
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {P['scroll']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {P['bg_selected']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: {P['bg_dialog']};
                height: 10px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {P['scroll']};
                border-radius: 4px;
                min-width: 30px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}

            /* ===== 卡片 ===== */
            #ProviderRow, #ModelRow {{
                background: {P['bg_card']};
                border: 1px solid {P['border']};
                border-radius: 5px;
            }}

            /* ===== QMessageBox 覆盖（避免系统默认白） ===== */
            QMessageBox {{
                background: {P['bg_dialog']};
                color: {P['text_primary']};
            }}
            QMessageBox QLabel {{
                color: {P['text_primary']};
            }}
        """)

    def _collect_provider_states(self) -> None:
        """Tab 1 的启用 checkbox 变更同步回 registry"""
        for i in range(self._tab_providers._container_layout.count()):
            row = self._tab_providers._container_layout.itemAt(i).widget()
            if isinstance(row, _ProviderRow):
                spec = self.registry.get_provider(row.spec_id)
                if spec:
                    spec.enabled = row.enable_cb.isChecked()

    def _on_save(self) -> None:
        self._collect_provider_states()
        # Cookie 编辑框有改动时一并落盘（格式不对则跳过，不阻塞其他配置保存）
        try:
            self._tab_cookie.save_if_dirty()
        except Exception:
            pass
        cfg = self.registry.save_to_config()
        try:
            import yaml
            path = get_config_path()
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 config.yaml 失败:\n{e}")
            return

        # 保存后立刻触发扫描（会自动扫所有 enabled provider + 连通性测试）
        self.registry.discover_all_enabled()

        self.config_saved.emit()
        QMessageBox.information(
            self, "已保存",
            "✅ 配置已写入 config.yaml\n"
            "🔍 正在后台扫描所有已启用提供商的可用模型并测试连通性...\n"
            "完成后 Tab 2/3 会自动刷新。"
        )
        self.accept()


# ---------------------------------------------------------------------------
# 启动入口（供 main_window.py 调用）
# ---------------------------------------------------------------------------

def run_startup_connectivity_check() -> None:
    """启动全局连通性后台检查（在 MainWindow 初始化完成后调用）"""
    registry = ModelRegistry.instance()
    registry.load_from_config()
    # 先确保所有 provider 的 enabled 状态正确
    registry.discover_all_enabled()
