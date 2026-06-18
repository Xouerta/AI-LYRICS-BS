"""
桌面悬浮歌词窗口
PySide6 透明置顶无边框窗口，模拟 QQ 音乐歌词显示效果。
"""
import queue
import logging

from PySide6.QtCore import (
    Qt, QTimer, QPoint, QRect, )
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QApplication

from lyrics_overlay.core.models import LyricsLine
from lyrics_overlay.overlay.themes import Theme, create_default_theme
from lyrics_overlay.overlay.text_renderer import TextRenderer

logger = logging.getLogger(__name__)


class LyricsWindow(QWidget):
    """桌面悬浮歌词窗口

    特性：
    - 透明背景 + 鼠标穿透
    - 始终置顶
    - 无边框、无任务栏图标
    - 支持拖拽移动位置
    - 淡入动画
    """

    def __init__(
        self,
        display_queue: queue.Queue,
        theme: Theme | None = None,
        width: int = 900,
        height: int = 130,
    ):
        super().__init__()
        self._display_queue = display_queue
        self._theme = theme or create_default_theme()
        self._renderer = TextRenderer(self._theme)

        # 当前显示的歌词
        self._current_original = "等待识别..."
        self._current_translated = ""
        self._opacity = 1.0

        # 拖拽
        self._dragging = False
        self._drag_offset = QPoint()

        self._setup_window(width, height)
        self._setup_timer()

    def _setup_window(self, width: int, height: int) -> None:
        """配置窗口属性"""
        self.setWindowTitle("LyricsOverlay")
        self.setFixedSize(width, height)

        # 窗口标志：置顶 + 无边框 + 工具窗口（不显示在任务栏）
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowTransparentForInput  # 鼠标穿透
        )
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 定位到屏幕底部居中
        self._center_at_bottom()

        self.show()

    def _center_at_bottom(self) -> None:
        """将窗口定位到主屏幕底部居中"""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom: QRect = screen.availableGeometry()
            x = (screen_geom.width() - self.width()) // 2 + screen_geom.x()
            y = screen_geom.height() - self.height() - 60 + screen_geom.y()
            self.move(x, y)

    def _setup_timer(self) -> None:
        """设置轮询定时器"""
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_display_queue)
        self._poll_timer.start(80)  # 每 80ms 检查一次

    def _poll_display_queue(self) -> None:
        """轮询显示队列，更新歌词"""
        try:
            while True:
                lyrics: LyricsLine = self._display_queue.get_nowait()
                self._update_lyrics(lyrics)
        except queue.Empty:
            pass

    def _update_lyrics(self, lyrics: LyricsLine) -> None:
        """更新歌词内容并触发重绘"""
        old_text = self._current_original

        if lyrics.is_translated:
            self._current_original = lyrics.original
            self._current_translated = lyrics.translated
        else:
            self._current_original = lyrics.original
            self._current_translated = ""

        if old_text != self._current_original:
            logger.debug("歌词更新: %s", self._current_original[:40])
            # 简单淡入效果：透明度降为 0 再恢复
            self._opacity = 0.0
            self.update()

            # 300ms 后恢复
            QTimer.singleShot(50, lambda: self._fade_in())

    def _fade_in(self) -> None:
        """淡入动画"""
        self._opacity = min(self._opacity + 0.15, 1.0)
        self.update()
        if self._opacity < 1.0:
            QTimer.singleShot(30, self._fade_in)

    def set_theme(self, theme: Theme) -> None:
        """切换主题"""
        self._theme = theme
        self._renderer = TextRenderer(theme)
        self.update()

    # ── 鼠标拖拽（需要穿透时暂时取消） ──

    def enable_drag(self, enabled: bool) -> None:
        """启用/禁用窗口拖拽"""
        if enabled:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowTransparentForInput)
            self.setAttribute(Qt.WA_TranslucentBackground)
            # 重新显示以应用标志
            self.hide()
            self.show()
        else:
            self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
            self.hide()
            self.show()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False

    # ── 绘制 ──

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # 填充透明背景
        painter.fillRect(self.rect(), self._theme.background_color)

        self._renderer.paint(
            painter,
            self.width(),
            self.height(),
            self._current_original,
            self._current_translated,
            self._opacity,
        )