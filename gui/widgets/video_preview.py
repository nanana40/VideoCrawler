"""
VideoPreview — 视频播放器 + 字幕画布 组合控件

职责：
    1. 叠加 QVideoWidget（底层视频） + SubtitleCanvas（独立顶级窗口字幕覆盖层）
    2. 提供播放 / 暂停 / 进度条 / 时间显示 一体化面板
    3. 将播放进度实时同步给 SubtitleCanvas，驱动字幕高亮
    4. _OverlayStack 负责把 canvas 顶级窗口精确定位到视频画面的屏幕坐标
"""

from typing import List, Dict, Optional

from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QRect, QPoint, QSize
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QStackedLayout,
    QSizePolicy,
)

from .subtitle_canvas import SubtitleCanvas
from ..theme import PALETTE


def _probe_video_resolution(video_path: str) -> tuple:
    """轻量封装：探测视频原生分辨率 (width, height)。失败返回 (1920, 1080)。"""
    try:
        from core.subtitle_render import _probe_video_resolution as _probe
        return _probe(video_path)
    except Exception:
        return 1920, 1080


def _fmt_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    s = ms // 1000
    m = s // 60
    s = s % 60
    h = m // 60
    m = m % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class VideoPreview(QWidget):
    """视频播放器 + 字幕覆盖层 + 控制栏。"""

    position_changed = Signal(int)
    duration_changed = Signal(int)
    player_error = Signal(str)
    player_status = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._video_widget = QVideoWidget(self)
        self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._player.setVideoOutput(self._video_widget)

        # canvas 作为独立顶级窗口创建（parent=None），拥有独立 HWND，不会被视频帧盖住
        self.canvas = SubtitleCanvas(parent=None)

        self._overlay = _OverlayStack(self._video_widget, self.canvas)

        # ★ 黑条开关/高度或视频宽高比变化时，overlay 立即按「视频 + 向下扩边黑条」总比例重新拟合
        self.canvas.layout_changed.connect(self._overlay.relayout)

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedWidth(44)
        self._btn_play.setCursor(Qt.PointingHandCursor)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setTracking(False)
        self._slider.setCursor(Qt.PointingHandCursor)

        self._label_cur = QLabel("0:00")
        self._label_dur = QLabel("0:00")
        for lbl in (self._label_cur, self._label_dur):
            lbl.setFixedWidth(56)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color: {PALETTE['text_secondary']};")

        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(4, 2, 4, 6)
        ctrl.setSpacing(6)
        ctrl.addWidget(self._btn_play)
        ctrl.addWidget(self._label_cur)
        ctrl.addWidget(self._slider, 1)
        ctrl.addWidget(self._label_dur)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._overlay, 1)
        root.addLayout(ctrl)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._btn_play.clicked.connect(self.toggle_play)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderReleased.connect(self._on_slider_released)

        self._slider_dragging = False
        self._last_pos_ms = 0

        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def set_video(self, path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(path))
        self._tick.start()

        # ★ 探测视频原生分辨率，传给 Canvas 做 scale 换算
        res_x, res_y = _probe_video_resolution(path)
        self.canvas.set_video_resolution(res_x, res_y)

        # 加载视频后立刻同步 canvas 位置并显示
        self._overlay.sync_canvas()

        # ★ 启动位置保活 timer（每 200ms 重新定位 + raise）
        # QVideoWidget 的 HWND 有时会触发 Canvas 窗口层级变化
        if not hasattr(self, "_keepalive"):
            self._keepalive = QTimer(self)
            self._keepalive.setInterval(200)
            self._keepalive.timeout.connect(self._overlay.sync_canvas)
        self._keepalive.start()

    def set_subtitle_items(self, items: List[Dict]) -> None:
        self.canvas.set_subtitle_items(items)
        self._overlay.sync_canvas()

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def seek(self, ms: int) -> None:
        self._player.setPosition(max(0, ms))

    def position_ms(self) -> int:
        return self._player.position()

    def duration_ms(self) -> int:
        return self._player.duration()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._overlay.sync_canvas()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.canvas.sync_visible(False)

    def closeEvent(self, event) -> None:
        self._tick.stop()
        if hasattr(self, "_keepalive"):
            self._keepalive.stop()
        self._player.stop()
        self.canvas.hide()
        self.canvas.close()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # 内部槽
    # ------------------------------------------------------------------
    def _on_position_changed(self, pos: int) -> None:
        self._last_pos_ms = pos
        if not self._slider_dragging:
            self._slider.blockSignals(True)
            self._slider.setValue(pos)
            self._slider.blockSignals(False)
        self._label_cur.setText(_fmt_time(pos))
        self.canvas.set_current_time(pos / 1000.0)
        self.position_changed.emit(pos)

    def _on_duration_changed(self, dur: int) -> None:
        self._slider.setRange(0, dur)
        self._label_dur.setText(_fmt_time(dur))
        self.duration_changed.emit(dur)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._btn_play.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_error(self, err, msg: str) -> None:
        self.player_error.emit(msg or f"播放器错误: {err}")

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        self.player_status.emit(str(status))

    def _on_slider_moved(self, val: int) -> None:
        self._slider_dragging = True
        self._label_cur.setText(_fmt_time(val))
        self.canvas.set_current_time(val / 1000.0)

    def _on_slider_released(self) -> None:
        self.seek(self._slider.value())
        self._slider_dragging = False

    def _on_tick(self) -> None:
        if self._slider_dragging:
            return
        cur = self._player.position()
        if abs(cur - self._last_pos_ms) > 50:
            self.canvas.set_current_time(cur / 1000.0)
            self._last_pos_ms = cur


class _OverlayStack(QWidget):
    """把「视频区 + 底部扩边黑条」作为一个整体按总宽高比拟合到自身区域，
    并把 SubtitleCanvas（顶级窗口）同步到相同屏幕区域。

    布局模型（pad 扩边）：
        总区宽高比 = PlayResX : basis_h，其中 basis_h = 1080（+黑条高度）
        ┌──────────────┐  ← 总区顶
        │              │
        │  QVideoWidget │  高度 = 总区高 × 1080/basis_h，宽高比恰好等于原视频宽高比
        │  （原视频帧）  │  → 视频帧无 letterbox 精确填满，原画面完整不被遮挡
        ├──────────────┤  ← 视频底边（= Canvas 黑条顶边）
        │  纯黑字幕条    │  高度 = 总区高 × bh/basis_h（Canvas 绘制），字幕落在此区
        └──────────────┘  ← 总区底
        Canvas 覆盖整个总区：视频部分透明（看见下层视频），黑条部分画纯黑 + 字幕。

    为什么不把 canvas 作为子 widget？
        QVideoWidget 在 Windows 上使用独立 HWND 渲染视频帧，会盖住所有子 widget 的绘制。
        所以 canvas 必须是独立顶级窗口，拥有自己的 HWND。
    """

    def __init__(self, video: QVideoWidget, canvas: SubtitleCanvas, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video = video
        self._canvas = canvas
        self._video.setParent(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.relayout()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.relayout()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.relayout()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._canvas.sync_visible(False)

    def sync_canvas(self) -> None:
        """保活定时器（200ms）调用：等价于 relayout，兜底修正窗口层级/位置。"""
        self.relayout()

    def relayout(self) -> None:
        """按「视频 + 底部扩边黑条」总宽高比重新拟合视频控件与 Canvas 几何。"""
        if not self.isVisible():
            self._canvas.sync_visible(False)
            return

        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return

        prx = max(1, self._canvas.play_res_x())
        basis_h = max(1080, self._canvas.basis_height())
        total_aspect = prx / float(basis_h)

        # contain 拟合：总区完整落在 self.rect() 内，居中
        if W / float(H) > total_aspect:
            total_h = H
            total_w = max(1, int(round(H * total_aspect)))
        else:
            total_w = W
            total_h = max(1, int(round(W / total_aspect)))

        x0 = (W - total_w) // 2
        y0 = (H - total_h) // 2

        # 视频控件只占上方 1080/basis_h；其自身宽高比 = total_w / video_h = 原视频宽高比
        video_h = int(round(total_h * 1080.0 / basis_h))
        video_geo = QRect(x0, y0, total_w, video_h)
        if self._video.geometry() != video_geo:
            self._video.setGeometry(video_geo)

        # Canvas 覆盖整个总区（视频 + 黑条）
        screen_rect = QRect(self.mapToGlobal(QPoint(x0, y0)), QSize(total_w, total_h))
        self._canvas.sync_geometry(screen_rect)
        self._canvas.sync_visible(True)
        self._canvas.raise_()   # ★ 确保 Canvas 窗口始终在 QVideoWidget 之上
