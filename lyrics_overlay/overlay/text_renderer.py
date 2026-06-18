"""
歌词文字渲染器
使用 QPainter 在透明窗口上绘制带描边和阴影的歌词。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QPainter, QFont, QPen, QColor, QPainterPath, )
from lyrics_overlay.overlay.themes import Theme


class TextRenderer:
    """歌词绘制工具"""

    def __init__(self, theme: Theme):
        self.theme = theme
        self._main_font = QFont(theme.font_family, theme.font_size)
        self._sub_font = QFont(theme.font_family, theme.translation_font_size)

    def paint(
        self,
        painter: QPainter,
        widget_width: int,
        widget_height: int,
        original_text: str,
        translated_text: str = "",
        opacity: float = 1.0,
    ) -> None:
        """在 painter 上绘制歌词

        Args:
            painter: QPainter 实例
            widget_width: 窗口宽度
            widget_height: 窗口高度
            original_text: 原文（中文或外文）
            translated_text: 翻译文本（为空时不绘制）
            opacity: 整体透明度 0.0~1.0
        """
        if not original_text:
            return

        painter.setOpacity(opacity)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # 计算绘制区域
        text_rect = painter.viewport()

        has_translation = bool(translated_text)
        if has_translation:
            # 双行模式：原文在上，翻译在下
            main_y = text_rect.height() * 0.35
            sub_y = text_rect.height() * 0.72
        else:
            # 单行居中
            main_y = text_rect.height() * 0.5

        # ── 绘制原文 ──
        self._draw_text_line(
            painter, original_text, self._main_font,
            self.theme.text_color, main_y, is_main=True,
        )

        # ── 绘制翻译 ──
        if has_translation:
            self._draw_text_line(
                painter, translated_text, self._sub_font,
                self.theme.translation_color, sub_y, is_main=False,
            )

    def _draw_text_line(
        self,
        painter: QPainter,
        text: str,
        font: QFont,
        color: QColor,
        y_center: float,
        is_main: bool,
    ) -> None:
        """绘制单行文字（含描边 + 阴影）"""
        painter.setFont(font)

        # 水平居中
        text_width = painter.fontMetrics().horizontalAdvance(text)
        x = (painter.viewport().width() - text_width) / 2

        # 1. 阴影
        shadow_path = QPainterPath()
        shadow_path.addText(
            x + self.theme.shadow_offset[0],
            y_center + self.theme.shadow_offset[1],
            font, text,
        )
        painter.fillPath(shadow_path, self.theme.shadow_color)

        # 2. 描边
        stroke_path = QPainterPath()
        stroke_path.addText(x, y_center, font, text)
        pen = QPen(self.theme.stroke_color, self.theme.stroke_width)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(stroke_path)

        # 3. 填充文字
        painter.setPen(Qt.NoPen)
        fill_path = QPainterPath()
        fill_path.addText(x, y_center, font, text)
        painter.fillPath(fill_path, color)