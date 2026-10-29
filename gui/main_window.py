"""
MainWindow — 主窗口

布局：
    ┌──────────────────────────────────────────────────┐
    │ 菜单栏： 文件 | 工具 | API/模型管理 | 帮助       │
    ├──────────────────────────────────┬───────────────┤
    │                                  │               │
    │  QTabWidget (4 页)              │ 全局日志面板   │
    │   1. 搜索与下载                 │   (右侧常驻)   │
    │   2. 语音识别与翻译             │               │
    │   3. 字幕参数 + 预览            │               │
    │   4. 文案生成                   │               │
    │                                  │               │
    ├──────────────────────────────────┴───────────────┤
    │  状态栏：任务状态 + 强制结束 + 强制重启          │
    └──────────────────────────────────────────────────┘
"""

import os
import sys
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from typing import Optional

from loguru import logger

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QStatusBar, QPushButton, QLabel, QMessageBox, QFileDialog,
)

from .global_log_panel import GlobalLogPanel
from .task_manager import TaskManager, SharedContext
from .log_bridge import LogBridge
from .api_config_dialog import ApiConfigDialog
from .onboarding import maybe_show_guide, reset_onboarding, show_guide
from .theme import PALETTE, STATUS_COLORS, build_global_qss
from utils.config_loader import load_config


class MainWindow(QMainWindow):
    """VideoCrawler 主窗口"""

    _sig_log_report = Signal(str, str)  # (level, report_str)

    def __init__(self) -> None:
        super().__init__()
        self._sig_log_report.connect(lambda msg, lvl: self._log(msg, lvl))

        self.setWindowTitle("VideoCrawler — 视频下载 & 字幕 & 文案 一体化工作台")
        self.resize(1480, 900)
        self.setMinimumSize(1100, 680)

        self._build_menu_bar()
        self._build_central()
        self._build_status_bar()

        self._init_pages()

        self._setup_stylesheet()

        # 启动后后台自动测试所有已配置模型的连通性（不阻塞 UI）
        self._startup_connectivity_check()

        # ── 嵌 FastAPI + MQTT bridge (GUI 进程里) ──
        self._mqtt_info: dict = {}  # 远程设备信息 (device_id / qr_url / connected)
        try:
            from .web_host import get_host
            self._web_host = get_host()
            info = self._web_host.start_all()
            self._web_lan = info["lan"]
            self._web_key = info["api_key"]
            self._mqtt_info = info.get("mqtt", {})
            logger.info(f"🌐 远程接口 → {self._web_lan}")
            if self._mqtt_info.get("ok"):
                logger.info(f"📡 MQTT 设备 → {self._mqtt_info.get('device_id')}")
            else:
                logger.info(f"📡 MQTT bridge 未就绪: {self._mqtt_info.get('msg','')}")
        except Exception as e:
            self._web_host = None
            logger.warning(f"🌐 远程接口启动失败 (不影响 GUI): {e}")

        # 首次运行且没配 Key → 弹出配置引导（延迟到窗口显示后，避免遮挡启动）
        QTimer.singleShot(1500, self._maybe_first_run_guide)

    # ------------------------------------------------------------------
    # 菜单栏
    # ------------------------------------------------------------------
    def _build_menu_bar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&文件")
        act_open_output = QAction("📂 打开输出目录", self)
        act_open_output.triggered.connect(self._open_output_dir)
        file_menu.addAction(act_open_output)

        act_exit = QAction("退出", self)
        act_exit.setShortcut(QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        tool_menu = mb.addMenu("&工具")

        act_api = QAction("🔧 API 与 Cookie 管理...", self)
        act_api.triggered.connect(self._open_api_config)
        tool_menu.addAction(act_api)

        tool_menu.addSeparator()

        act_stop = QAction("⏹ 强制结束任务", self)
        act_stop.triggered.connect(self._force_stop)
        tool_menu.addAction(act_stop)

        act_restart = QAction("🔄 强制重启 (热刷新)", self)
        act_restart.triggered.connect(self._force_restart)
        tool_menu.addAction(act_restart)

        tool_menu.addSeparator()

        act_link = QAction("📱 启动远程联动 (手机控制电脑)", self)
        act_link.triggered.connect(self._start_remote_linkage)
        tool_menu.addAction(act_link)

        act_remote = QAction("📱 远程连接信息 (扫码控制)", self)
        act_remote.triggered.connect(self._show_remote_info)
        tool_menu.addAction(act_remote)

        help_menu = mb.addMenu("&帮助")

        guide_menu = help_menu.addMenu("📖 新手引导")
        for key, label in (
            ("api_key", "🔑 配置 API Key"),
            ("mobile_remote", "📱 手机远程遥控"),
            ("publish", "🚀 从成品到发布"),
            ("tiktok_cookie", "🎵 TikTok / 抖音 Cookie"),
        ):
            act_guide = QAction(label, self)
            act_guide.triggered.connect(lambda _=False, k=key: show_guide(self, k))
            guide_menu.addAction(act_guide)
        guide_menu.addSeparator()
        act_reset_guide = QAction("♻️ 重置全部引导（重新弹出）", self)
        act_reset_guide.triggered.connect(self._reset_onboarding)
        guide_menu.addAction(act_reset_guide)

        act_about = QAction("关于 VideoCrawler", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # ------------------------------------------------------------------
    # 中央区：TabWidget 占满，LogPanel 浮动在 wrapper 右上角
    # ------------------------------------------------------------------
    def _build_central(self) -> None:
        from PySide6.QtCore import QEvent

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(False)

        # 用子类化 wrapper 重写 resizeEvent —— 比 eventFilter 更干净
        class _FloatWrapper(QWidget):
            def __init__(self, parent: Optional[QWidget] = None, on_resize=None):
                super().__init__(parent)
                self._on_resize = on_resize
            def resizeEvent(self, _e):
                super().resizeEvent(_e)
                if self._on_resize:
                    self._on_resize()

        wrapper = _FloatWrapper(on_resize=self._reposition_log_panel)
        lay = QHBoxLayout(wrapper)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._tabs, 1)

        # 浮动日志面板：不进 layout，用 absolute positioning 叠在右上角
        self._log_panel = GlobalLogPanel(parent=wrapper)
        self._log_panel.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self.setCentralWidget(wrapper)
        # 初始位置（等 wrapper 有 size 后再调一次）
        wrapper.show()
        QTimer.singleShot(0, self._reposition_log_panel)

    def _reposition_log_panel(self) -> None:
        """把浮动日志面板贴到主区域右上角"""
        wrapper = self.centralWidget()
        panel = getattr(self, "_log_panel", None)
        if not wrapper or not panel:
            return
        margin = 10
        pw = panel.width() or panel.sizeHint().width() or 320
        ph = panel.height() or panel.sizeHint().height() or 96
        panel.setGeometry(wrapper.width() - pw - margin, margin, pw, ph)
        panel.raise_()

    def _init_pages(self) -> None:
        from .pages.page_download import PageDownload
        from .pages.page_recognize import PageRecognize
        from .pages.page_subtitle import PageSubtitle
        from .pages.page_writer import PageWriter
        from .pages.page_publish import PagePublish

        self.page_download = PageDownload(self)
        self.page_recognize = PageRecognize(self)
        self.page_subtitle = PageSubtitle(self)
        self.page_writer = PageWriter(self)
        self.page_publish = PagePublish(self)

        self._tabs.addTab(self.page_download, "① 搜索与下载")
        self._tabs.addTab(self.page_recognize, "② 语音识别与翻译")
        self._tabs.addTab(self.page_subtitle, "③ 字幕参数与预览")
        self._tabs.addTab(self.page_writer, "④ 文案生成")
        self._tabs.addTab(self.page_publish, "⑤ 视频发布")

        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        tab = self._tabs.widget(index)
        refresh = getattr(tab, "refresh_context", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

        # 第一次进入「⑤ 视频发布」时，介绍账号导入与风险
        if index == 4:
            try:
                maybe_show_guide(self, "publish")
            except Exception as e:
                logger.warning(f"发布引导弹出失败: {e}")

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet(f"padding: 0 12px; color: {STATUS_COLORS['ok']};")
        sb.addWidget(self._status_label, 1)

        self._stop_btn = QPushButton("⏹ 强制结束任务")
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.clicked.connect(self._force_stop)
        sb.addPermanentWidget(self._stop_btn)

        self._restart_btn = QPushButton("🔄 强制重启")
        self._restart_btn.setCursor(Qt.PointingHandCursor)
        self._restart_btn.setObjectName("DangerBtn")
        self._restart_btn.clicked.connect(self._force_restart)
        sb.addPermanentWidget(self._restart_btn)

        # 一键启动远程联动按钮 (保证常开: 点击后自动切换 LAN 监听 + 确认 bridge 在线)
        self._remote_btn = QPushButton("📱 远程联动")
        self._remote_btn.setCursor(Qt.PointingHandCursor)
        self._remote_btn.clicked.connect(self._start_remote_linkage)
        sb.addPermanentWidget(self._remote_btn)

        # MQTT 远程连接状态指示器 (可点击)
        self._mqtt_label = QLabel("📡 远程: —")
        self._mqtt_label.setStyleSheet(f"padding: 0 12px; color: {STATUS_COLORS['ok']};")
        self._mqtt_label.setCursor(Qt.PointingHandCursor)
        self._mqtt_label.mousePressEvent = lambda _e: self._show_remote_info()
        sb.addPermanentWidget(self._mqtt_label)
        # 定时刷新连接状态 (10s)
        self._mqtt_timer = QTimer(self)
        self._mqtt_timer.timeout.connect(self._refresh_mqtt_status)
        self._mqtt_timer.start(10000)
        self._refresh_mqtt_status()

        tm = TaskManager.instance()
        tm.register_observer(self._update_status_running)
        self._update_status_running(tm.is_running())

    def _update_status_running(self, running: bool) -> None:
        if running:
            self._status_label.setText("⚙️ 正在执行任务...")
            self._status_label.setStyleSheet(f"padding: 0 12px; color: {STATUS_COLORS['warn']};")
        else:
            self._status_label.setText("就绪")
            self._status_label.setStyleSheet(f"padding: 0 12px; color: {STATUS_COLORS['ok']};")

    # ------------------------------------------------------------------
    # 菜单 / 按钮动作
    # ------------------------------------------------------------------
    def _open_output_dir(self) -> None:
        from utils.path_helper import get_output_dir
        output = str(get_output_dir())
        if not os.path.exists(output):
            os.makedirs(output, exist_ok=True)
        try:
            os.startfile(output)  # type: ignore[attr-defined]
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开目录:\n{e}")

    def _open_api_config(self) -> None:
        if not getattr(self, "_skip_api_guide", False):
            try:
                maybe_show_guide(self, "api_key")
            except Exception as e:
                logger.warning(f"API 引导弹出失败: {e}")
        dlg = ApiConfigDialog(self)
        dlg.config_saved.connect(lambda: self._log("配置已保存，部分模块需重启生效", "WARNING"))
        dlg.exec()

    # ---- 新手引导 ----
    def _maybe_first_run_guide(self) -> None:
        """首次运行且未配置任何 API Key 时，引导用户去填写"""
        try:
            if self._api_key_configured():
                return
            maybe_show_guide(
                self, "api_key",
                actions=[("🔧 现在去填写", self._open_api_config_skip_guide)],
            )
        except Exception as e:
            logger.warning(f"首次引导弹出失败: {e}")

    @staticmethod
    def _api_key_configured() -> bool:
        """是否已配置任意 LLM Key（新 providers[] 结构或旧 gemini 字段）"""
        try:
            cfg = load_config()
        except Exception:
            return False
        for prov in cfg.get("providers") or []:
            if str((prov or {}).get("api_key") or "").strip():
                return True
        return bool(str((cfg.get("gemini") or {}).get("api_key") or "").strip())

    def _open_api_config_skip_guide(self) -> None:
        """从引导里点「现在去填写」时直接打开配置，避免再次弹引导"""
        self._skip_api_guide = True
        try:
            self._open_api_config()
        finally:
            self._skip_api_guide = False

    def _reset_onboarding(self) -> None:
        reset_onboarding()
        self._log("已重置新手引导：下次打开对应功能会重新提示", "INFO")

    def _startup_connectivity_check(self) -> None:
        """启动后后台触发全局模型连通性检查（非阻塞）"""
        try:
            from .api_config_dialog import run_startup_connectivity_check
            run_startup_connectivity_check()
            self._log("正在后台检查各 API 模型连通性（打开「API/模型管理」查看结果）...", "INFO")
        except Exception as e:
            self._log(f"启动连通性检查失败: {e}", "WARNING")

    def _force_stop(self) -> None:
        tm = TaskManager.instance()
        reply = QMessageBox.question(
            self, "强制结束",
            "确定要强制结束当前所有后台任务并清理临时文件吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        def _run():
            report = tm.force_stop(log_fn=lambda lvl, msg: self._log(msg, lvl))
            self._sig_log_report.emit(report, "WARNING")

        spawn(target=_run, daemon=True).start()

    def _force_restart(self) -> None:
        reply = QMessageBox.warning(
            self, "强制重启",
            "这将结束所有后台任务、清理缓存并重新启动程序。\n"
            "（源码改动将在新进程中 100% 生效）\n\n确定继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # force_restart 内部会：force_stop → 清 __pycache__ → 启动新进程 → app.quit()
        # 必须在主线程调（因为 app.quit() 只能在主线程）
        TaskManager.instance().force_restart(
            log_fn=lambda lvl, msg: self._log(msg, lvl)
        )

    def _show_about(self) -> None:
        QMessageBox.information(
            self, "关于 VideoCrawler",
            "VideoCrawler v2.0 — PySide6 GUI 版\n\n"
            "一体化视频下载、字幕识别、字幕烧录、文案生成工作台。\n"
            "基于 YouTube + Gemini + Groq + GLM 多模型协作。",
        )

    # ------------------------------------------------------------------
    # MQTT 远程连接
    # ------------------------------------------------------------------

    def _start_remote_linkage(self) -> None:
        """一键启动远程联动: 确保服务在线 (LAN 可达 + bridge 在线) 后弹出扫码面板"""
        try:
            if getattr(self, "_web_host", None) is None:
                # GUI 启动时远程接口初始化失败过 → 这里补一次
                from .web_host import get_host
                self._web_host = get_host()
                self._web_host.start_all()
            info = self._web_host.ensure_remote_service()
            for act in info.get("actions", []):
                self._log(f"📡 远程联动: {act}", "INFO")
            if not info.get("bridge_ok"):
                QMessageBox.warning(
                    self, "远程联动",
                    "MQTT bridge 未能上线 (broker.emqx.io 可能不可达)。\n"
                    "请检查电脑网络后重试。",
                )
                return
        except Exception as e:
            QMessageBox.warning(self, "远程联动", f"启动失败: {e}")
            return
        self._show_remote_info()

    def _refresh_mqtt_status(self) -> None:
        """刷新状态栏 MQTT 连接状态 (10s 定时)"""
        try:
            from web.mqtt_bridge import get_bridge
            bridge = get_bridge()
            if bridge is None:
                self._mqtt_label.setText("📡 远程: 未启动")
                self._mqtt_label.setStyleSheet(
                    f"padding: 0 12px; color: {STATUS_COLORS['muted'] if 'muted' in STATUS_COLORS else '#8892a6'};"
                )
                return
            if bridge._connected:
                self._mqtt_label.setText("📡 远程: 在线")
                self._mqtt_label.setStyleSheet(
                    f"padding: 0 12px; color: {STATUS_COLORS['ok']};"
                )
            else:
                self._mqtt_label.setText("📡 远程: 重连中...")
                self._mqtt_label.setStyleSheet(
                    f"padding: 0 12px; color: {STATUS_COLORS['warn']};"
                )
        except Exception:
            self._mqtt_label.setText("📡 远程: —")

    def _show_remote_info(self) -> None:
        """弹出远程连接信息对话框 (二维码 + device_id + 链接)"""
        try:
            maybe_show_guide(self, "mobile_remote")
        except Exception as e:
            logger.warning(f"远程引导弹出失败: {e}")
        from PySide6.QtGui import QPixmap, QPainter, QColor
        from PySide6.QtCore import Qt, QByteArray
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
        import pyqrcode
        import io

        # 先刷新一次 mqtt_info
        self._refresh_mqtt_status()
        try:
            from web.mqtt_bridge import get_bridge
            bridge = get_bridge()
        except Exception:
            bridge = None

        dlg = QDialog(self)
        dlg.setWindowTitle("📱 远程连接信息")
        dlg.setMinimumWidth(420)

        lay = QVBoxLayout(dlg)

        # --- 设备状态 ---
        status_text = "未知"
        color = "#8892a6"
        if bridge is None:
            status_text = "MQTT bridge 未启动"
            color = "#c97878"
        elif bridge._connected:
            status_text = f"🟢 已连接 broker.emqx.io:1883"
            color = "#5da87a"
        else:
            status_text = "🟡 重连中 (自动)"
            color = "#b08848"

        status_lbl = QLabel(f"<span style='color:{color}'>{status_text}</span>")
        status_lbl.setStyleSheet("font-size: 13px;")
        lay.addWidget(status_lbl)

        if bridge:
            # --- 设备信息 ---
            info_html = (
                f"<div style='font-size:12px; line-height:1.9; color:#8892a6; padding:8px 0'>"
                f"<b style='color:#d4d9e5'>Device ID:</b> <span style='color:#4e8cff'>{bridge.device_id}</span><br>"
                f"<b style='color:#d4d9e5'>Token:</b> <code style='color:#8892a6; font-size:11px'>{bridge.token[:8]}...{bridge.token[-4:]}</code><br>"
                f"<b style='color:#d4d9e5'>Cmd Topic:</b> <code style='color:#8892a6; font-size:11px'>{bridge.topic_cmd}</code><br>"
                f"<b style='color:#d4d9e5'>Log Topic:</b> <code style='color:#8892a6; font-size:11px'>{bridge.topic_log}</code>"
                f"</div>"
            )
            lay.addWidget(QLabel(info_html))

            # --- 二维码 (公网模式优先, 局域网兜底, 始终可生成) ---
            urls = bridge.get_qr_urls()
            mode_text = ("🌐 公网模式 · 手机任意网络可用" if urls["mode"] == "public"
                         else "📶 局域网模式 · 手机需与电脑同一 WiFi")
            # 注意: pyqrcode 的 png() 只支持 module_color/background (RGBA 元组),
            # 不支持 dark/light 关键字 (传了会 TypeError)
            pix = None
            try:
                qr = pyqrcode.create(urls["url"])
                buf = io.BytesIO()
                qr.png(buf, scale=8,
                       module_color=(15, 20, 32, 255),    # #0f1420
                       background=(212, 217, 229, 255))   # #d4d9e5
                pix = QPixmap()
                pix.loadFromData(buf.getvalue(), "PNG")
                pix = pix.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception as e:
                # 二维码渲染失败不阻断面板, 链接仍可复制使用
                self._log(f"二维码渲染失败 (链接仍可复制使用): {e}", "WARNING")
            if pix is not None:
                img_lbl = QLabel()
                img_lbl.setPixmap(pix)
                img_lbl.setAlignment(Qt.AlignCenter)
                lay.addWidget(img_lbl)

            mode_lbl = QLabel(f"<span style='color:#5da87a'>{mode_text}</span>")
            mode_lbl.setStyleSheet("font-size:12px;")
            mode_lbl.setAlignment(Qt.AlignCenter)
            lay.addWidget(mode_lbl)

            hint = QLabel(
                "📱 扫码打开控制面板 → 浏览器菜单「添加到主屏幕」→ 下次点图标一键直达\n"
                "<span style='color:#8892a6; font-size:11px'>"
                "局域网模式下换 WiFi 需重新扫码；如需任意网络控制, 把 mobile.html 部署到静态托管并设 VC_MQTT_WEB_URL</span>"
            )
            hint.setStyleSheet("font-size:12px; color:#8892a6; padding:8px; background:#1a2130; border-radius:6px;")
            hint.setWordWrap(True)
            lay.addWidget(hint)

            # 完整链接 (可复制)
            url_edit = QLabel(f"<code style='color:#4e8cff; font-size:11px; word-break:break-all'>{urls['url']}</code>")
            url_edit.setStyleSheet("padding:6px; background:#0f1420; border-radius:4px;")
            url_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
            url_edit.setWordWrap(True)
            lay.addWidget(url_edit)

            # 公网模式下附局域网备选地址 (同 WiFi 更快)
            if urls["public"]:
                lan_row = QLabel(
                    f"<span style='color:#8892a6; font-size:11px'>局域网备选 (同一 WiFi 更快):</span> "
                    f"<code style='color:#4e8cff; font-size:11px'>{urls['lan']}</code>"
                )
                lan_row.setTextInteractionFlags(Qt.TextSelectableByMouse)
                lan_row.setWordWrap(True)
                lay.addWidget(lan_row)

        # --- 按钮 ---
        btn_row = QHBoxLayout()

        refresh_btn = QPushButton("🔄 刷新状态")
        refresh_btn.clicked.connect(lambda: (self._refresh_mqtt_status(), dlg.close(), self._show_remote_info()))
        btn_row.addWidget(refresh_btn)

        copy_btn = QPushButton("📋 复制 Device ID")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(bridge.device_id if bridge else ""))
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)

        lay.addLayout(btn_row)
        dlg.exec()

    def _copy_to_clipboard(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        if text:
            QApplication.clipboard().setText(text)
            self._log(f"📋 已复制到剪贴板: {text}", "INFO")

    # ------------------------------------------------------------------
    # 日志 & 跳转
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "INFO") -> None:
        from loguru import logger
        logger.log(level.upper(), msg)

    def switch_to_tab(self, index: int) -> None:
        self._tabs.setCurrentIndex(index)

    def context(self) -> SharedContext:
        return TaskManager.instance().context

    # ------------------------------------------------------------------
    # 样式
    # ------------------------------------------------------------------
    def _setup_stylesheet(self) -> None:
        """应用 UICraft 全局设计系统（单一数据源：theme.build_global_qss）"""
        self.setStyleSheet(build_global_qss())

    # ------------------------------------------------------------------
    # AUDIT-0011: 关窗清理钩子
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        """关窗时清理后台线程 / 流水线 / 临时文件，避免 ffmpeg/浏览器残留"""
        try:
            # 0. 停内嵌的 uvicorn
            try:
                if getattr(self, "_web_host", None):
                    self._web_host.stop_all()
            except Exception:
                pass

            # 1. 停自动流水线 worker + 清空队列
            try:
                from .auto_pipeline import AutoPipelineManager
                AutoPipelineManager.instance().stop()
            except Exception:
                pass

            # 2. 强制结束所有已登记的后台线程 + 清理临时文件
            try:
                TaskManager.instance().force_stop()
            except Exception:
                pass

            # 3. 关闭数据库连接（WAL checkpoint）
            try:
                from utils.db_manager import shutdown_db
                shutdown_db()
            except Exception:
                pass
        finally:
            event.accept()
