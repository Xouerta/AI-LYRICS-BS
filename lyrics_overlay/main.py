"""
Lyrics Overlay — 本地 AI 歌词识别与悬浮字幕
程序入口
"""
import sys
import signal
import logging

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction

from config import Config
from lyrics_overlay.utils.logger import setup_logging
from lyrics_overlay.utils.model_manager import ModelManager
from lyrics_overlay.core.orchestrator import Orchestrator
from lyrics_overlay.core.models import AppState
from lyrics_overlay.overlay.lyrics_window import LyricsWindow
from lyrics_overlay.overlay.themes import BUILTIN_THEMES

logger = logging.getLogger(__name__)


class LyricsApp:
    """应用主控制器"""

    def __init__(self):
        self.config = Config()
        self.orchestrator = Orchestrator(self.config)

        # Qt 应用
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # UI 组件
        self._lyrics_window: LyricsWindow | None = None
        self._tray_icon: QSystemTrayIcon | None = None
        self._current_theme_idx = 0

    def run(self) -> int:
        """启动应用，返回退出码"""
        # 1. 初始化日志
        setup_logging(level=logging.DEBUG)

        # 2. 依赖检查
        self._check_dependencies()

        # 3. 创建 UI
        self._setup_ui()

        # 4. 启动管线
        self.orchestrator.start()

        # 5. 进入 Qt 事件循环
        logger.info("=" * 40)
        logger.info("Lyrics Overlay 已启动")
        logger.info("右键系统托盘图标操作")
        logger.info("=" * 40)

        return self._app.exec()

    def _check_dependencies(self) -> None:
        """检查依赖和系统兼容性"""
        manager = ModelManager(self.config.models_dir)
        missing = manager.check_dependencies()
        if missing:
            logger.error("缺少依赖: %s", missing)
            logger.error("请执行: pip install -r requirements.txt")
            sys.exit(1)

        if sys.platform != "win32" and sys.platform != "cygwin":
            logger.warning(
                "当前仅在 Windows 上完整支持。macOS/Linux 需要额外配置音频回路。"
            )

    def _setup_ui(self) -> None:
        """创建悬浮窗口和系统托盘"""
        # ── 悬浮歌词窗口 ──
        theme = BUILTIN_THEMES[self._current_theme_idx]
        self._lyrics_window = LyricsWindow(
            display_queue=self.orchestrator.display_queue,
            theme=theme,
            width=self.config.window_width,
            height=self.config.window_height,
        )

        # ── 系统托盘图标 ──
        self._tray_icon = QSystemTrayIcon(self._app)
        # 尝试加载图标（没有则用系统默认）
        icon_path = self.config.project_root / "icon.png"
        if icon_path.exists():
            self._tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self._tray_icon.setIcon(self._app.style().standardIcon(
                self._app.style().SP_MediaPlay
            ))
        self._tray_icon.setToolTip("歌词悬浮窗 - 运行中")

        # 右键菜单
        menu = QMenu()

        # 切换主题子菜单
        theme_menu = QMenu("切换主题")
        for i, t in enumerate(BUILTIN_THEMES):
            action = theme_menu.addAction(t.name)
            action.setData(i)
            action.triggered.connect(self._on_theme_change)
        menu.addMenu(theme_menu)

        menu.addSeparator()

        # 暂停/恢复
        pause_action = QAction("暂停识别")
        pause_action.triggered.connect(self._on_pause)
        menu.addAction(pause_action)

        # 拖拽模式
        drag_action = QAction("切换拖拽模式")
        drag_action.triggered.connect(self._on_toggle_drag)
        menu.addAction(drag_action)

        menu.addSeparator()

        # 退出
        exit_action = QAction("退出")
        exit_action.triggered.connect(self._on_exit)
        menu.addAction(exit_action)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.show()

    def _on_theme_change(self) -> None:
        """切换主题"""
        action = self._app.sender()
        if action:
            idx = action.data()
            if 0 <= idx < len(BUILTIN_THEMES):
                self._current_theme_idx = idx
                self._lyrics_window.set_theme(BUILTIN_THEMES[idx])
                logger.info("主题切换: %s", BUILTIN_THEMES[idx].name)

    def _on_pause(self) -> None:
        """暂停/恢复识别"""
        state = self.orchestrator.get_state()
        if state == AppState.RUNNING:
            self.orchestrator.stop()
            self._lyrics_window._current_original = "已暂停"
            self._lyrics_window._current_translated = ""
            self._lyrics_window.update()
            logger.info("用户暂停识别")
        else:
            self.orchestrator.start()
            self._lyrics_window._current_original = "等待识别..."
            self._lyrics_window._current_translated = ""
            self._lyrics_window.update()
            logger.info("用户恢复识别")

    def _on_toggle_drag(self) -> None:
        """切换拖拽模式"""
        # 简单切换：当前窗口标志含 TransparentForInput 则去掉
        flags = self._lyrics_window.windowFlags()
        if flags & Qt.WindowTransparentForInput:
            self._lyrics_window.enable_drag(True)
            self._tray_icon.showMessage("歌词悬浮窗", "拖拽模式已开启，拖动窗口调整位置")
        else:
            self._lyrics_window.enable_drag(False)
            self._tray_icon.showMessage("歌词悬浮窗", "拖拽模式已关闭，鼠标可穿透")

    def _on_exit(self) -> None:
        """退出应用"""
        logger.info("用户请求退出")
        self.orchestrator.stop()
        self._tray_icon.hide()
        self._app.quit()


def main():
    app = LyricsApp()
    # 注册信号处理（Ctrl+C 优雅退出）
    signal.signal(signal.SIGINT, lambda *a: app._app.quit())
    return app.run()


if __name__ == "__main__":
    sys.exit(main())