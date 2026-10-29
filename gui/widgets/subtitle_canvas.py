"""
SubtitleCanvas — 视频上字幕预览覆盖层（独立顶级窗口）

设计说明：
    QVideoWidget 在 Windows 上使用独立的底层窗口句柄（HWND）直接渲染视频帧，
    会盖住叠加在它上面的所有子 widget 的绘制内容（Qt Multimedia 经典问题）。
    因此 SubtitleCanvas 必须作为**独立顶级窗口**存在，拥有自己的 HWND，
    才能保证字幕渲染在视频帧之上。

职责：
    1. 独立顶级窗口（Frameless + Tool + 透明背景）
    2. 跟随播放进度渲染当前活跃字幕
    3. 字幕样式完全对齐 libass 渲染行为（与 ffmpeg burn 结果 1:1）
    4. 外部通过 sync_geometry() 把它定位到视频画面的屏幕坐标位置

对齐 libass 行为清单：
    - Alignment=2：底部居中
    - MarginL=MarginR=32（固定水平边距）
    - MarginV：用户设的底部边距
    - 字体：Microsoft YaHei, Bold=1
    - 描边：2px，颜色 outline_color
    - 主色：primary_color
    - 双语：src_top 时原文主字号上 + 译文 secondary 下，同主色同描边
    - 硬折行：按像素宽度逐字符折行（支持中文无空格）
    - 无背景框、无边框、无序号角标（烧录里也没有）
"""

from typing import List, Dict, Optional

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QSize
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainterPath,
)
from PySide6.QtWidgets import QWidget, QSizePolicy


# 对齐 libass Style 行里的固定值
MARGIN_X = 32          # MarginL = MarginR = 32（和 ASS Style 一致）
OUTLINE_WIDTH = 2      # Outline=2（和 ASS Style 一致）
LINE_SPACING_PX = 4    # 双行间额外间距（libass 里是自动行距，这里微调）
SECONDARY_COLOR_FACTOR = 1.15   # 译文颜色变亮系数（复刻 ASS lighter(115)）
SECONDARY_OUTLINE_MINUS = 1     # 译文描边减细值（复刻 ASS \bord N-1）


class SubtitleCanvas(QWidget):
    """覆盖在视频帧上的字幕预览画布（独立顶级窗口），渲染行为对齐 libass。"""

    subtitle_moved = Signal(int, QPoint)       # 旧签名，保留兼容
    pos_changed = Signal()                      # ★ 拖拽结束时 emit，page_subtitle 自动保存
    layout_changed = Signal()                   # ★ 黑条开关/高度或视频比例变化时 emit，驱动 overlay 重新拟合

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        # 作为顶级窗口：parent=None + 设置 WindowFlags
        if parent is None:
            super().__init__(
                None,
                Qt.FramelessWindowHint
                | Qt.Tool
                | Qt.NoDropShadowWindowHint,
            )
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        else:
            super().__init__(parent)

        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._subtitle_items: List[Dict] = []
        self._current_time: float = 0.0

        # ---- 视频宽高比（ffprobe 探测后传入） ----
        # 只存比例用于算 PlayResX，scale 和所有像素值都基于 1080p 固定基准
        self._video_res_x: int = 1920
        self._video_res_y: int = 1080

        # ---- 样式属性（全部基于 1080p 像素值，和 ASS 基准一致） ----
        self._font_size: int = 36              # 主字号 (1080p 像素，固定基准)
        self._primary_color: QColor = QColor(255, 255, 255)
        self._outline_color: QColor = QColor(0, 0, 0)
        self._margin_v: int = 16               # 底部边距 (1080p 像素)
        self._bilingual: bool = True
        self._bilingual_pos: str = "src_top"   # "src_top" | "src_bottom"
        self._bilingual_scale: float = 0.85
        self._show_src: bool = True

        # ---- 底部黑框（字幕条） ----
        self._bar_enabled: bool = False
        self._bar_height: int = 48             # 1080p 像素
        self._bar_opacity_pct: int = 70        # 0-100%

        # ---- 字幕自由定位（基准坐标系，和 ASS Dialogue \pos 一致） ----
        # PlayResX = round(1080 * video_w / video_h)，PlayResY = basis_h = 1080(+黑条高)
        # pos_x 默认 = PlayResX/2（水平居中），pos_y 默认 = 1080 - margin_v（贴视频底）
        self._pos_x: int = 960      # 默认：PlayResX/2（16:9 视频 PlayResX=1920，居中=960）
        self._pos_y: int = 1064     # 默认：1080 - margin_v（1080 - 16 = 1064）
        self._drag_pos_anchor_x: int = 0  # 拖拽起始时鼠标相对于字幕块中心 X 的偏移（1080p 像素）
        self._drag_pos_anchor_y: int = 0  # 拖拽起始时鼠标相对于字幕块底部 Y 的偏移（1080p 像素）
        self._drag_active: bool = False

    # ------------------------------------------------------------------
    # 外部驱动：定位 / 显示 / 隐藏
    # ------------------------------------------------------------------
    def sync_geometry(self, screen_rect: QRect) -> None:
        """把 canvas 顶级窗口移动到指定屏幕坐标区域（必须和 QVideoWidget 完全重合）。"""
        if screen_rect.isNull():
            return
        self.setGeometry(screen_rect)
        self.update()

    def sync_visible(self, visible: bool) -> None:
        if visible:
            self.show()
            self.raise_()
        else:
            self.hide()

    # ------------------------------------------------------------------
    # 样式 setter（page_subtitle 参数面板实时调用）
    # ------------------------------------------------------------------
    def set_font_size(self, px: int) -> None:
        self._font_size = max(8, min(120, int(px)))
        self.update()

    def set_primary_color(self, color: QColor | str) -> None:
        c = QColor(color) if isinstance(color, str) else color
        if c.isValid():
            self._primary_color = c
            self.update()

    def set_outline_color(self, color: QColor | str) -> None:
        c = QColor(color) if isinstance(color, str) else color
        if c.isValid():
            self._outline_color = c
            self.update()

    def set_margin_v(self, px: int) -> None:
        self._margin_v = max(0, min(200, int(px)))
        self._sync_pos_from_margin()  # ★ margin_v 变化时同步 pos_y（仅未手动拖拽过时）

    def set_bilingual(self, on: bool) -> None:
        self._bilingual = bool(on)
        self.update()

    def set_bilingual_pos(self, pos: str) -> None:
        self._bilingual_pos = pos if pos in ("src_top", "src_bottom") else "src_top"
        self.update()

    def set_bilingual_scale(self, scale: float) -> None:
        self._bilingual_scale = max(0.5, min(1.0, float(scale)))
        self.update()

    def set_show_src(self, on: bool) -> None:
        self._show_src = bool(on)
        self.update()

    def _play_res_x(self) -> int:
        """ASS PlayResX：按视频宽高比算，保持形状对齐。视频部分基准高固定 1080。"""
        return max(1, round(1080 * self._video_res_x / max(1, self._video_res_y)))

    def play_res_x(self) -> int:
        """公开访问：ASS PlayResX（供 _OverlayStack 拟合布局用）。"""
        return self._play_res_x()

    def basis_height(self) -> int:
        """ASS 总坐标系高度 PlayResY。

        pad 扩边模型：视频原画面占 0..1080（完整保留），启用黑条时总高 = 1080 + 黑条高，
        黑条是从视频底边向下接出的新区（1080..basis_h），不遮挡视频内容。
        """
        return 1080 + (self._bar_height if self._bar_enabled else 0)

    def video_area_bottom_screen(self) -> int:
        """屏幕像素：视频区底边（= 黑条顶边）。视频占 Canvas 总高的 1080/basis_h。"""
        canvas_h = self.height()
        if canvas_h <= 0:
            return 0
        return int(canvas_h * 1080.0 / max(1, self.basis_height()))

    def _default_pos_y(self) -> int:
        """默认字幕纵向锚点（基准像素）。

        黑条开启：字幕块垂直居中于黑条新区（\an2 锚点是块底，故还要上补半块高）；
        黑条关闭：1080 - margin_v 贴视频底边。
        """
        if self._bar_enabled:
            return int(1080 + self._bar_height / 2.0 + self._subtitle_block_height_basis() / 2.0)
        return 1080 - self._margin_v

    def set_video_resolution(self, width: int, height: int) -> None:
        """设置视频宽高比（ffprobe 探测后调用）。仅用于算 PlayResX。"""
        w = max(1, int(width))
        h = max(1, int(height))
        changed = w != self._video_res_x or h != self._video_res_y
        if changed:
            self._video_res_x = w
            self._video_res_y = h
            # ★ 如果用户没手动拖过字幕，用新的 PlayResX/2 居中 + 默认纵向位置
            if not getattr(self, "_pos_set_by_user", False):
                self._pos_x = self._play_res_x() // 2
                self._pos_y = self._default_pos_y()
            self.update()
            self.layout_changed.emit()  # ★ 宽高比变化，overlay 需重新拟合

    def _sync_pos_from_margin(self) -> None:
        """把当前 margin_v 同步到 pos_y（只在用户没手动拖拽过时生效）。"""
        if not getattr(self, "_pos_set_by_user", False):
            self._pos_y = self._default_pos_y()
            self.update()

    def get_pos(self) -> tuple:
        """获取当前字幕定位锚点（视频像素），供烧录时读取。"""
        return self._pos_x, self._pos_y

    def set_pos(self, pos_x: int, pos_y: int) -> None:
        """外部设置字幕定位锚点（基准坐标），加载配置时用。"""
        prx = self._play_res_x()
        self._pos_x = max(0, min(prx, int(pos_x)))
        self._pos_y = max(0, min(self.basis_height(), int(pos_y)))
        self._pos_set_by_user = True
        self.update()

    def reset_pos_to_default(self) -> None:
        """重置到默认位置（水平居中；黑条开启时落在黑条新区中心，否则 margin_v 贴视频底）。"""
        self._pos_x = self._play_res_x() // 2
        self._pos_y = self._default_pos_y()
        self._pos_set_by_user = False
        self.update()

    def set_bg_bar(self, *, enabled: bool = False, height: int = 48, opacity_pct: int = 70) -> None:
        """设置底部黑框（pad 向下扩边的纯黑字幕条）参数。

        Args:
            enabled: 是否启用（启用后总坐标系高度 = 1080 + height）
            height: 黑条高度（1080p 基准像素，从视频底边向下接出）
            opacity_pct: 保留兼容字段；pad 扩边固定纯黑不透明，不再生效
        """
        changed = False
        if bool(enabled) != self._bar_enabled:
            self._bar_enabled = bool(enabled)
            changed = True
        h = max(20, min(200, int(height)))
        if h != self._bar_height:
            self._bar_height = h
            changed = True
        op = max(0, min(100, int(opacity_pct)))
        if op != self._bar_opacity_pct:
            self._bar_opacity_pct = op
            changed = True
        if changed:
            # ★ 用户没手动拖过字幕时，让字幕自动跟随：
            # 启用 → 字幕块落在黑条新区垂直中心；关闭 → 恢复 margin_v 贴视频底
            if not getattr(self, "_pos_set_by_user", False):
                self._pos_x = self._play_res_x() // 2
                self._pos_y = self._default_pos_y()
            self.update()
            self.layout_changed.emit()  # ★ 总宽高比变化，overlay 立即重新拟合

    # ------------------------------------------------------------------
    # 烧录时从 Canvas 读取的"有效样式"（libass 对齐）
    # ------------------------------------------------------------------
    def get_alignment(self) -> int:
        """libass 九宫格 Alignment 值。当前固定 2=底部居中，后续可扩展拖拽改 alignment。"""
        return 2

    def get_margin_v(self) -> int:
        """当前底部边距 (px)。拖拽后会更新。"""
        return self._margin_v

    def get_effective_outline_width(self, is_secondary: bool = False) -> int:
        """当前有效描边宽度 (px)，区分主/译文行。"""
        if is_secondary:
            return max(1, OUTLINE_WIDTH - SECONDARY_OUTLINE_MINUS)
        return OUTLINE_WIDTH

    # ------------------------------------------------------------------
    # 字幕数据 API
    # ------------------------------------------------------------------
    def set_subtitle_items(self, items: List[Dict]) -> None:
        self._subtitle_items = list(items)
        self._current_time = 0.0
        self.update()

    def subtitle_items(self) -> List[Dict]:
        return self._subtitle_items

    def set_current_time(self, t: float) -> None:
        if abs(t - self._current_time) < 0.05 and self._current_time >= 0:
            return
        self._current_time = t
        self.update()

    # ------------------------------------------------------------------
    # 鼠标事件（自由拖拽字幕位置 — XY 双向）
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """点击字幕区域开始双向拖拽（X 水平 + Y 垂直）。"""
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        scale_x = self.width() / max(1, self._play_res_x())
        scale_y = self._current_scale()

        # 字幕块在屏幕里的位置（底部中心）
        anchor_x_screen = int(self._pos_x * scale_x)
        anchor_y_screen = int(self._pos_y * scale_y)
        block_h_screen = self._subtitle_block_height()
        block_w_screen = self._estimate_block_width()
        hit_left = anchor_x_screen - block_w_screen // 2
        hit_right = anchor_x_screen + block_w_screen // 2
        hit_top = anchor_y_screen - block_h_screen
        hit_bottom = anchor_y_screen

        mouse_x = int(event.position().x())
        mouse_y = int(event.position().y())
        if hit_left <= mouse_x <= hit_right and hit_top <= mouse_y <= hit_bottom:
            self._drag_active = True
            # ★ 记录鼠标相对于字幕块锚点的偏移（1080p 基准像素）
            self._drag_pos_anchor_x = int((mouse_x - anchor_x_screen) / scale_x)
            self._drag_pos_anchor_y = int((mouse_y - anchor_y_screen) / scale_y)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scale_x = self.width() / max(1, self._play_res_x())
        scale_y = self._current_scale()

        if getattr(self, "_drag_active", False):
            # ★ 鼠标位置反算回 1080p 基准像素，减去起始偏移得到新的 pos
            mouse_x_video = int(event.position().x() / scale_x)
            mouse_y_video = int(event.position().y() / scale_y)
            new_x = mouse_x_video - self._drag_pos_anchor_x
            new_y = mouse_y_video - self._drag_pos_anchor_y
            # ★ 边界 clamp（在 PlayResX × basis_h 总坐标系范围内）
            self._pos_x = max(0, min(self._play_res_x(), new_x))
            self._pos_y = max(0, min(self.basis_height(), new_y))
            self.update()
            event.accept()
            return

        # hover 光标
        anchor_x_screen = int(self._pos_x * scale_x)
        anchor_y_screen = int(self._pos_y * scale_y)
        block_h_screen = self._subtitle_block_height()
        block_w_screen = self._estimate_block_width()
        hit_left = anchor_x_screen - block_w_screen // 2
        hit_right = anchor_x_screen + block_w_screen // 2
        hit_top = anchor_y_screen - block_h_screen
        hit_bottom = anchor_y_screen
        mouse_x = int(event.position().x())
        mouse_y = int(event.position().y())
        if hit_left <= mouse_x <= hit_right and hit_top <= mouse_y <= hit_bottom:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and getattr(self, "_drag_active", False):
            self._drag_active = False
            self._pos_set_by_user = True  # ★ 标记用户手动拖过，后续分辨率/margin_v 变化不再自动覆盖
            self.setCursor(Qt.OpenHandCursor)
            self.update()
            self.pos_changed.emit()  # ★ 通知外层保存当前位置
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _estimate_block_width(self) -> int:
        """估算字幕块屏幕像素宽度（用于 hit-test）。取所有行里最长的。"""
        scale = self._current_scale()
        font = QFont("Microsoft YaHei")
        font.setPixelSize(max(4, int(self._font_size * scale)))
        font.setBold(True)
        fm = QFontMetrics(font)

        max_w = 0
        for item in self._subtitle_items:
            src = (item.get("text") or "").strip()
            tgt = (item.get("translated_text") or "").strip()
            max_w = max(max_w, fm.horizontalAdvance(src))
            if self._bilingual:
                sub_font = QFont("Microsoft YaHei")
                sub_font.setPixelSize(max(4, int(self._font_size * self._bilingual_scale * scale)))
                sub_fm = QFontMetrics(sub_font)
                max_w = max(max_w, sub_fm.horizontalAdvance(tgt))
        # 加一点余量（描边 + 宽松）
        return max_w + 20

    def _subtitle_top_y(self, canvas_h: int) -> int:
        """字幕块顶部屏幕像素 Y。基于 _pos_y（底部锚点）往上推 block 高度。"""
        scale = self._current_scale()
        anchor_y_screen = int(self._pos_y * scale)
        block_h = self._subtitle_block_height()
        return anchor_y_screen - block_h

    def _subtitle_block_height_basis(self) -> int:
        """字幕块高度（1080p 基准像素）：主行 + 可能的译行 + 行距。"""
        font = QFont("Microsoft YaHei")
        font.setPixelSize(max(4, int(self._font_size)))
        font.setBold(True)
        h = QFontMetrics(font).height()
        if self._bilingual:
            sub_font = QFont("Microsoft YaHei")
            sub_font.setPixelSize(max(4, int(self._font_size * self._bilingual_scale)))
            sub_font.setBold(True)
            h += LINE_SPACING_PX + QFontMetrics(sub_font).height()
        return h

    def _subtitle_block_height(self) -> int:
        """字幕块高度（Canvas 屏幕像素）。"""
        return max(1, int(self._subtitle_block_height_basis() * self._current_scale()))

    def _current_scale(self) -> float:
        """基准坐标系 → Canvas 屏幕像素的换算系数。

        scale = canvas_height / basis_height
        basis_height 无黑条时为 1080，启用黑条时为 1080 + 黑条高（与 ASS PlayResY 一致）。
        用户设的所有像素值（font_size、margin_v、pos）都在该基准坐标系下，
        渲染时乘 scale 得到屏幕像素，和 libass 的脚本坐标缩放完全对齐。
        """
        canvas_h = self.height()
        if canvas_h <= 0:
            return 1.0
        return canvas_h / float(self.basis_height())

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        if self.windowFlags() & Qt.FramelessWindowHint:
            painter.fillRect(self.rect(), Qt.transparent)

        # ★ 底部黑条（字幕条）独立于字幕绘制——任何时候只要启用就显示
        self._draw_bg_bar(painter)

        active_idx = self._active_index()

        if active_idx >= 0:
            self._draw_active(painter, self._subtitle_items[active_idx])

        painter.end()

    def _draw_bg_bar(self, painter: QPainter) -> None:
        """画底部扩边黑条（对应 ffmpeg pad 接出的新区）。

        pad 语义：视频原画面完整保留在 Canvas 上方（占总高 1080/basis_h），
        黑条是从视频底边【向下】接出的纯黑新区域（video_bottom..canvas_h），
        绝不向上侵入/遮挡视频内容。
        """
        if not self._bar_enabled:
            return
        canvas_w = self.width()
        canvas_h = self.height()
        if canvas_w <= 0 or canvas_h <= 0:
            return
        bar_top = self.video_area_bottom_screen()
        if bar_top >= canvas_h:
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0)))  # pad 扩边固定纯黑不透明
        painter.drawRect(0, bar_top, canvas_w, canvas_h - bar_top)

    def _active_index(self) -> int:
        if self._current_time < 0:
            return -1
        for i, item in enumerate(self._subtitle_items):
            s = item.get("start_time", 0.0)
            e = item.get("end_time", 0.0)
            if s <= self._current_time <= e:
                return i
        return -1

    # ------------------------------------------------------------------
    # libass 对齐绘制核心
    # ------------------------------------------------------------------

    def _wrap_by_width(self, fm: QFontMetrics, text: str, max_width: int) -> List[str]:
        """按像素宽度逐字符硬折行（支持中文无空格场景）。

        libass 会在 PlayResX 宽度内自动折行，实现类似行为。
        """
        if not text:
            return []
        lines: List[str] = []
        current = ""
        for ch in text:
            trial = current + ch
            # 跳过：单个字符就超宽（极端情况）
            if fm.horizontalAdvance(trial) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
        return lines

    def _draw_outlined_text(
        self,
        painter: QPainter,
        center_x: int,
        baseline_y: int,
        line: str,
        font: QFont,
        primary: QColor,
        outline: QColor,
        outline_width: int,
    ) -> None:
        """画一行带描边的居中文字（模拟 libass Alignment=2 + Center）。

        用 QPainterPath 先画描边色粗 pen，再画主色填充。
        libass Outline=2 对应 Qt 这里的 outline_width=2（Qt pen width 直接用，不乘 2）。
        """
        if not line:
            return
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(line)
        x = center_x - text_w // 2
        path = QPainterPath()
        path.addText(x, baseline_y, font, line)

        # 描边（先画粗的 outline 色）
        if outline_width > 0:
            painter.setPen(QPen(outline, outline_width * 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)

        # 主色填充
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(primary))
        painter.drawPath(path)

    def _draw_active(self, painter: QPainter, item: Dict) -> None:
        """渲染当前活跃字幕（对齐 libass 行为）。

        所有用户设的像素值（font_size, margin_v, MARGIN_X, OUTLINE_WIDTH 等）
        都是相对于视频原生分辨率的，这里统一乘以 scale 转成 Canvas 屏幕像素。
        """
        canvas_w = self.width()
        canvas_h = self.height()
        if canvas_w <= 0 or canvas_h <= 0:
            return

        # ★ scale：基准坐标系 → Canvas 屏幕像素
        # scale_x 用 PlayResX（按视频宽高比算），scale_y 用总坐标系高 basis_h（=PlayResY）
        scale_x = canvas_w / max(1, self._play_res_x())
        scale_y = canvas_h / float(self.basis_height())
        scale = scale_y  # 字号/垂直用高度 scale 做主导（fit 后二者相等）

        # ---- 主字体（和 ASS Style 一致，字号乘 scale） ----
        font_px = max(4, int(self._font_size * scale))
        font = QFont("Microsoft YaHei")
        font.setPixelSize(font_px)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # ---- 译文字体（secondary_scale，同样乘 scale） ----
        sub_font: Optional[QFont] = None
        sub_fm: Optional[QFontMetrics] = None
        if self._bilingual:
            sub_px = max(4, int(self._font_size * self._bilingual_scale * scale))
            sub_font = QFont("Microsoft YaHei")
            sub_font.setPixelSize(sub_px)
            sub_font.setBold(True)
            sub_fm = QFontMetrics(sub_font)

        # ---- 文字来源 ----
        src_text = (item.get("text") or "").strip()
        tgt_text = (item.get("translated_text") or "").strip()

        # ---- 边距和位置（全部乘 scale） ----
        # ★ 自由定位：bottom_y / center_x 从 _pos_x/_pos_y（视频像素锚点）换算
        bottom_y = int(self._pos_y * scale)
        center_x = int(self._pos_x * scale_x)
        margin_x_screen = int(MARGIN_X * scale_x)
        outline_w_screen = max(1, int(OUTLINE_WIDTH * scale))
        line_spacing_screen = int(LINE_SPACING_PX * scale)
        available_w = canvas_w - margin_x_screen * 2  # libass 水平方向 MarginL+MarginR

        lines: List[tuple] = []  # (text, font, fm, is_secondary)

        if self._bilingual and sub_font and sub_fm and tgt_text and src_text:
            src_lines = self._wrap_by_width(fm, src_text, available_w)
            tgt_lines = self._wrap_by_width(sub_fm, tgt_text, available_w)

            if self._bilingual_pos == "src_top":
                for ln in src_lines:
                    lines.append((ln, font, fm, False))
                lines.append(("", None, None, False))  # 间隔
                for ln in tgt_lines:
                    lines.append((ln, sub_font, sub_fm, True))
            else:
                for ln in tgt_lines:
                    lines.append((ln, font, fm, False))
                lines.append(("", None, None, False))  # 间隔
                for ln in src_lines:
                    lines.append((ln, sub_font, sub_fm, True))
        elif src_text:
            lines = [(ln, font, fm, False) for ln in self._wrap_by_width(fm, src_text, available_w)]

        # ---- 从底部往上画 ----
        total_h = 0
        for i, (_, _, lfm, _) in enumerate(lines):
            if lfm is None:
                total_h += line_spacing_screen
            else:
                total_h += lfm.height()

        cur_y = bottom_y - (total_h - lines[-1][2].height() if lines and lines[-1][2] else 0)

        # 注：底部黑条已在 paintEvent 的 _draw_bg_bar 里独立绘制（字幕下层）

        for i, (ln, lfont, lfm, is_sec) in enumerate(lines):
            if lfont is None or lfm is None:
                cur_y += line_spacing_screen
                continue
            # ★ 译文行：颜色变淡 + 描边更细（复刻 ASS Dialogue 里的 \c + \bord 覆盖）
            draw_color = self._primary_color.lighter(SECONDARY_COLOR_FACTOR * 100) if is_sec else self._primary_color
            draw_outline_w = max(1, int((OUTLINE_WIDTH - SECONDARY_OUTLINE_MINUS) * scale)) if is_sec else outline_w_screen
            baseline = cur_y + lfm.ascent()
            self._draw_outlined_text(
                painter, center_x, baseline, ln, lfont,
                draw_color, self._outline_color, draw_outline_w,
            )
            cur_y += lfm.height()
