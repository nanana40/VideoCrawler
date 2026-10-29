"""
theme.py — VideoCrawler 统一设计系统 (UICraft extract)

所有 GUI 颜色、QSS 必须从这里取。目的：
  1. 消除 178 处硬编码 hex
  2. 全局一致的深色低饱和视觉
  3. Windows 原生控件白底漏出彻底消失
  4. 改一处换全应用

调色板设计：
  - 三层背景（对话框 / 卡片 / 输入框）形成深度层次
  - 三级文字（primary / secondary / muted）控制视觉权重
  - 状态色只表达状态（点缀），不抢主视觉
  - 唯一 accent 蓝 #4e8cff，替代 GitHub 霓虹 #58a6ff
  - 失败红从 #f85149 → #c97878（降饱和）
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# PALETTE — 全局唯一色值来源，改这里 = 改全应用
# ---------------------------------------------------------------------------

PALETTE = {
    # --- 背景层：从深到浅形成层次 ---
    "bg_window":   "#1c2333",   # 主窗口 / 对话框最外层
    "bg_dialog":   "#1c2333",   # ← 兼容别名
    "bg_card":     "#232b3d",   # 卡片 / Tab pane / 分组框
    "bg_input":    "#1a2130",   # 输入框 / 列表框 / 下拉
    "bg_hover":    "#2a3348",   # hover / 鼠标悬停
    "bg_pressed":  "#353f58",   # 按下瞬间
    "bg_selected": "#2e3a54",   # 选中 / 焦点态
    "bg_header":   "#182032",   # 顶栏 / 分组标题区

    # --- 文字层：三级灰度控制视觉权重 ---
    "text_primary":   "#d4d9e5",   # 主视觉（模型名 / 按钮文字 / tab 标题）
    "text_secondary": "#8892a6",   # 次文字（provider 名 / 描述 / 按钮副标题）
    "text_muted":     "#5e6677",   # 最灰（详细错误 / 辅助信息 / placeholder）
    "text_on_accent": "#ffffff",   # accent 按钮上的白色文字

    # --- 状态色：只表达状态，降饱和 ---
    "accent":  "#4e8cff",   # 选中 / 重点 / 链接（替代 GitHub 霓虹蓝）
    "success": "#52b788",   # ✅ 连通 / 运行中
    "warn":    "#c2a15b",   # ⚠️ 警告
    "fail":    "#c97878",   # ❌ 失败（降饱和红，不再刺眼）

    # --- 能力标签（全部降饱和，作为元数据不抢） ---
    "cap_video":      "#b08848",
    "cap_audio":      "#8f7cc4",
    "cap_multimodal": "#8f7cc4",
    "cap_text":       "#4e8cff",
    "cap_vision":     "#b08848",
    "cap_tts":        "#5da87a",
    "cap_image":      "#b97a95",

    # --- 边框 / 分隔 / 滚动条 ---
    "border":     "#2d3750",
    "divider":    "#2d3750",
    "scroll":     "#2d3750",
    "scroll_hover": "#3f4a66",

    # --- 日志等级（log_bridge 对齐 dark） ---
    "log_debug": "#5e6677",
    "log_info":  "#d4d9e5",
    "log_warn":  "#c2a15b",
    "log_error": "#c97878",
    "log_critical": "#c97878",
}

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def tag_background(foreground: str, alpha: float = 0.18) -> str:
    """把 hex 颜色转成带 alpha 的 rgba，用作能力标签的半透明底色"""
    r = int(foreground[1:3], 16)
    g = int(foreground[3:5], 16)
    b = int(foreground[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# GLOBAL_QSS — 整个应用的全局样式表
# 由 main_window.setStyleSheet(GLOBAL_QSS) 应用，级联覆盖所有子组件
# 子组件如需局部覆盖，用更高 specificity 的选择器或 inline setStyleSheet
# ---------------------------------------------------------------------------

def build_global_qss() -> str:
    P = PALETTE
    return f"""
    /* =========================================================
       根容器：覆盖所有 Windows 默认白底
       ========================================================= */
    QMainWindow, QDialog, QWidget {{
        background: {P['bg_window']};
        color: {P['text_primary']};
    }}

    /* =========================================================
       滚动条：所有滚动组件统一深色滚动条（覆盖 Windows 默认）
       ========================================================= */
    QScrollBar:vertical {{
        background: {P['bg_window']};
        width: 10px;
        margin: 2px 2px 2px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {P['scroll']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {P['scroll_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background: {P['bg_window']};
        height: 10px;
        margin: 0 2px 2px 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {P['scroll']};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {P['scroll_hover']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
        background: none;
    }}

    /* =========================================================
       输入控件
       ========================================================= */
    QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox {{
        background: {P['bg_input']};
        color: {P['text_primary']};
        border: 1px solid {P['border']};
        border-radius: 4px;
        padding: 5px 8px;
        selection-background-color: {P['bg_selected']};
        selection-color: {P['text_primary']};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {P['accent']};
    }}
    QLineEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
        background: {P['bg_card']};
        color: {P['text_muted']};
    }}

    /* QComboBox 下拉弹出列表 */
    QComboBox QAbstractItemView {{
        background: {P['bg_card']};
        color: {P['text_primary']};
        border: 1px solid {P['border']};
        selection-background-color: {P['bg_selected']};
        selection-color: {P['text_primary']};
        outline: none;
    }}

    /* =========================================================
       Tab（主窗口多页面切换）
       ========================================================= */
    QTabWidget::pane {{
        border: 1px solid {P['border']};
        background: {P['bg_window']};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {P['bg_card']};
        color: {P['text_secondary']};
        padding: 8px 16px;
        border: 1px solid {P['border']};
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {P['bg_window']};
        color: {P['text_primary']};
        border-bottom: 2px solid {P['accent']};
    }}
    QTabBar::tab:hover:!selected {{
        color: {P['text_primary']};
        background: {P['bg_hover']};
    }}

    /* =========================================================
       按钮
       ========================================================= */
    QPushButton {{
        background: {P['bg_card']};
        color: {P['text_primary']};
        border: 1px solid {P['border']};
        padding: 6px 14px;
        border-radius: 5px;
    }}
    QPushButton:hover {{
        background: {P['bg_hover']};
        border-color: {P['accent']};
    }}
    QPushButton:pressed {{
        background: {P['bg_pressed']};
    }}
    QPushButton:disabled {{
        background: {P['bg_input']};
        color: {P['text_muted']};
        border-color: {P['border']};
    }}
    /* 主操作按钮（通过 objectName="PrimaryBtn" 指定）*/
    QPushButton#PrimaryBtn {{
        background: {P['accent']};
        color: {P['text_on_accent']};
        border-color: {P['accent']};
    }}
    QPushButton#PrimaryBtn:hover {{
        background: #3d7ce8;
        border-color: #3d7ce8;
    }}
    /* 危险按钮 */
    QPushButton#DangerBtn {{
        background: {P['fail']};
        color: white;
        border-color: {P['fail']};
    }}
    QPushButton#DangerBtn:hover {{
        background: #b86868;
    }}

    /* =========================================================
       Checkbox / Radio（深色版）
       ========================================================= */
    QCheckBox, QRadioButton {{
        color: {P['text_primary']};
        spacing: 8px;
        background: transparent;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {P['border']};
        border-radius: 3px;
        background: {P['bg_input']};
    }}
    QCheckBox::indicator:checked {{
        background: {P['accent']};
        border-color: {P['accent']};
    }}
    QRadioButton::indicator {{
        border-radius: 8px;
    }}
    QRadioButton::indicator:checked {{
        background: {P['accent']};
        border-color: {P['accent']};
    }}

    /* =========================================================
       GroupBox / 分组
       ========================================================= */
    QGroupBox {{
        border: 1px solid {P['border']};
        border-radius: 6px;
        margin-top: 14px;
        padding-top: 10px;
        background: {P['bg_card']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
        color: {P['text_primary']};
    }}

    /* =========================================================
       QListWidget / QTreeWidget / QTableWidget
       ========================================================= */
    QListWidget, QTreeWidget, QTableWidget {{
        background: {P['bg_card']};
        color: {P['text_primary']};
        border: 1px solid {P['border']};
        border-radius: 4px;
        outline: none;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
        background: {P['bg_selected']};
        color: {P['text_primary']};
    }}
    QTableWidget {{
        gridline-color: {P['border']};
    }}
    QHeaderView::section {{
        background: {P['bg_header']};
        color: {P['text_primary']};
        border: none;
        border-right: 1px solid {P['border']};
        border-bottom: 1px solid {P['border']};
        padding: 6px 10px;
    }}

    /* =========================================================
       QProgressBar
       ========================================================= */
    QProgressBar {{
        background: {P['bg_input']};
        border: 1px solid {P['border']};
        border-radius: 4px;
        text-align: center;
        color: {P['text_primary']};
    }}
    QProgressBar::chunk {{
        background: {P['accent']};
        border-radius: 3px;
    }}

    /* =========================================================
       QStatusBar（主窗口底部状态栏）
       ========================================================= */
    QStatusBar {{
        background: {P['bg_header']};
        color: {P['text_secondary']};
        border-top: 1px solid {P['border']};
    }}

    /* =========================================================
       QMenuBar / QMenu（顶部菜单栏）
       ========================================================= */
    QMenuBar {{
        background: {P['bg_header']};
        color: {P['text_primary']};
        border-bottom: 1px solid {P['border']};
        padding: 2px;
    }}
    QMenuBar::item:selected {{
        background: {P['bg_selected']};
    }}
    QMenu {{
        background: {P['bg_card']};
        color: {P['text_primary']};
        border: 1px solid {P['border']};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 20px;
        border-radius: 3px;
    }}
    QMenu::item:selected {{
        background: {P['bg_selected']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {P['border']};
        margin: 4px 8px;
    }}

    /* =========================================================
       QMessageBox（覆盖系统默认白底）
       ========================================================= */
    QMessageBox {{
        background: {P['bg_window']};
        color: {P['text_primary']};
    }}
    QMessageBox QLabel {{
        color: {P['text_primary']};
    }}
    QMessageBox QPushButton {{
        min-width: 80px;
    }}
    QMessageBox QPushButton#PrimaryBtn {{
        background: {P['accent']};
        color: white;
        border-color: {P['accent']};
    }}

    /* =========================================================
       QToolBar（顶部工具栏）
       ========================================================= */
    QToolBar {{
        background: {P['bg_header']};
        border-bottom: 1px solid {P['border']};
        spacing: 4px;
        padding: 4px;
    }}
    QToolBar QToolButton {{
        background: transparent;
        color: {P['text_primary']};
        border: none;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    QToolBar QToolButton:hover {{
        background: {P['bg_hover']};
    }}

    /* =========================================================
       Slider / 滑块
       ========================================================= */
    QSlider::groove:horizontal {{
        background: {P['bg_input']};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {P['accent']};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    QSlider::handle:horizontal:hover {{
        background: #3d7ce8;
    }}

    /* =========================================================
       分隔线
       ========================================================= */
    QFrame[frameShape="4"], QFrame[frameShape="5"] {{
        color: {P['border']};
        background: {P['border']};
        max-height: 1px;
        max-width: 1px;
    }}
    """


# ---------------------------------------------------------------------------
# 主窗口状态色映射（供 main_window.py status_label 使用）
# ---------------------------------------------------------------------------

STATUS_COLORS = {
    "running": PALETTE["success"],
    "stopped": PALETTE["text_muted"],
    "error": PALETTE["fail"],
    "warn": PALETTE["warn"],
    "ok": PALETTE["success"],
}
