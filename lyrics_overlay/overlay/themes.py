"""
字幕主题定义
预设多种显示风格，可运行时切换。
"""
from dataclasses import dataclass
from PySide6.QtGui import QColor, QFont


@dataclass
class Theme:
    name: str
    # 文字
    font_family: str
    font_size: int
    text_color: QColor
    # 描边
    stroke_color: QColor
    stroke_width: int
    # 阴影
    shadow_color: QColor
    shadow_offset: tuple[int, int]
    # 翻译文字（如果有）
    translation_font_size: int
    translation_color: QColor
    # 背景
    background_color: QColor  # 透明窗口底色（alpha 可设 0）


def create_default_theme() -> Theme:
    """QQ 音乐风格默认主题"""
    return Theme(
        name="默认 (QQ音乐风格)",
        font_family="Microsoft YaHei",
        font_size=36,
        text_color=QColor(255, 255, 255, 240),
        stroke_color=QColor(40, 40, 40, 200),
        stroke_width=3,
        shadow_color=QColor(0, 0, 0, 100),
        shadow_offset=(2, 2),
        translation_font_size=20,
        translation_color=QColor(200, 200, 200, 220),
        background_color=QColor(0, 0, 0, 0),
    )


def create_karaoke_theme() -> Theme:
    """卡拉 OK 风格"""
    return Theme(
        name="卡拉OK",
        font_family="Microsoft YaHei",
        font_size=42,
        text_color=QColor(255, 255, 100, 255),
        stroke_color=QColor(0, 0, 0, 220),
        stroke_width=4,
        shadow_color=QColor(0, 0, 0, 120),
        shadow_offset=(3, 3),
        translation_font_size=24,
        translation_color=QColor(255, 255, 255, 200),
        background_color=QColor(0, 0, 0, 0),
    )


def create_minimal_theme() -> Theme:
    """极简白字"""
    return Theme(
        name="极简",
        font_family="Microsoft YaHei",
        font_size=32,
        text_color=QColor(255, 255, 255, 230),
        stroke_color=QColor(0, 0, 0, 180),
        stroke_width=2,
        shadow_color=QColor(0, 0, 0, 60),
        shadow_offset=(1, 1),
        translation_font_size=18,
        translation_color=QColor(180, 180, 180, 200),
        background_color=QColor(0, 0, 0, 0),
    )


BUILTIN_THEMES = [
    create_default_theme(),
    create_karaoke_theme(),
    create_minimal_theme(),
]