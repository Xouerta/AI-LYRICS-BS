"""
会话监控模块
使用 Windows Core Audio API (via pycaw) 检测目标应用的音频播放状态。

工作原理：
  1. 每 500ms 枚举系统所有音频会话
  2. 按进程名匹配目标应用（如 cloudmusic.exe, qqmusic.exe）
  3. 检查会话是否处于 Active 状态 & 未被静音
  4. 将结果通过线程安全属性暴露给其他模块
"""
import time
import threading
import logging
from typing import Optional, List

from pycaw.pycaw import AudioUtilities
from comtypes import COMError

logger = logging.getLogger(__name__)


class SessionMonitor:
    """目标应用音频会话状态监控器

    通过轮询 Windows Audio Session API 检测指定进程是否正在播放音频。
    运行在独立的后台守护线程中，不阻塞主线程。

    Usage:
        monitor = SessionMonitor(["cloudmusic.exe", "qqmusic.exe"])
        monitor.start()

        # 在音频捕获线程中轮询
        while True:
            if monitor.is_target_playing:
                process_audio()
    """

    # AudioSessionState 枚举值 (来自 Windows SDK)
    AUDIO_SESSION_STATE_INACTIVE = 0
    AUDIO_SESSION_STATE_ACTIVE = 1
    AUDIO_SESSION_STATE_EXPIRED = 2

    def __init__(
        self,
        target_process_names: List[str],
        poll_interval: float = 0.5,
    ):
        """
        Args:
            target_process_names: 目标进程名列表（大小写不敏感）
                示例: ["cloudmusic.exe", "qqmusic.exe", "spotify.exe"]
            poll_interval: 轮询间隔（秒），默认 500ms
        """
        self._target_names = set(name.lower().strip() for name in target_process_names)
        self._poll_interval = poll_interval

        # 线程安全的状态缓存
        self._lock = threading.Lock()
        self._is_playing = False
        self._active_process: Optional[str] = None

        # 线程控制
        self._running = False
        self._thread: Optional[threading.Thread] = None

        if not self._target_names:
            logger.warning("SessionMonitor 初始化时未指定任何目标进程")

    # ── 线程安全属性 ──────────────────────────────

    @property
    def is_target_playing(self) -> bool:
        """目标应用是否正在播放音频（可从任意线程安全读取）"""
        with self._lock:
            return self._is_playing

    @property
    def active_process(self) -> Optional[str]:
        """当前活跃的目标进程名（如 'cloudmusic.exe'），无则为 None"""
        with self._lock:
            return self._active_process

    # ── 生命周期 ──────────────────────────────────

    def start(self) -> None:
        """启动后台监控线程（幂等，重复调用安全）"""
        if self._running:
            logger.debug("SessionMonitor 已在运行，跳过重复启动")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="SessionMonitor",
        )
        self._thread.start()
        logger.info(
            "SessionMonitor 已启动 | 目标进程: %s | 轮询间隔: %.0fms",
            list(self._target_names),
            self._poll_interval * 1000,
        )

    def stop(self) -> None:
        """停止监控线程，等待最多 2 秒"""
        if not self._running:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            self._is_playing = False
            self._active_process = None

        logger.info("SessionMonitor 已停止")

    # ── 内部轮询逻辑 ──────────────────────────────

    def _poll_loop(self) -> None:
        """后台轮询主循环"""
        consecutive_errors = 0

        while self._running:
            try:
                playing, process_name = self._check_sessions()
                with self._lock:
                    # 状态变化时输出日志
                    if playing != self._is_playing:
                        logger.info(
                            "播放状态变化: %s → %s (%s)",
                            "播放中" if self._is_playing else "未播放",
                            "播放中" if playing else "未播放",
                            process_name or "无",
                        )
                    self._is_playing = playing
                    self._active_process = process_name

                consecutive_errors = 0  # 成功则重置错误计数

            except Exception:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.warning(
                        "轮询音频会话时出错 (第 %d 次)", consecutive_errors, exc_info=True
                    )
                else:
                    # 避免日志洪水
                    logger.debug(
                        "轮询音频会话持续出错 (第 %d 次)", consecutive_errors
                    )

                with self._lock:
                    self._is_playing = False
                    self._active_process = None

                # 错误时稍长等待，避免 busy-loop
                time.sleep(min(self._poll_interval * 2, 2.0))
                continue

            time.sleep(self._poll_interval)

    def _check_sessions(self) -> tuple[bool, Optional[str]]:
        """检查所有音频会话，查找目标进程

        Returns:
            (是否播放中, 匹配到的进程名或 None)
        """
        try:
            sessions = AudioUtilities.GetAllSessions()
        except COMError as e:
            logger.debug("获取音频会话列表失败 (COM 错误): %s", e)
            return False, None

        for session in sessions:
            # 跳过无进程的系统音频会话（如系统提示音）
            if session.Process is None:
                continue

            # 获取进程名
            try:
                process_name = session.Process.name().lower()
            except (COMError, AttributeError, OSError):
                continue

            if process_name not in self._target_names:
                continue

            # ── 找到目标进程，检查其播放状态 ──

            # 第一层：检查会话状态 (Active/Inactive/Expired)
            try:
                state = session._ctl.GetState()
                if state != self.AUDIO_SESSION_STATE_ACTIVE:
                    logger.debug("%s 音频会话状态: %d (非活跃)", process_name, state)
                    continue
            except Exception as state_error:
                # 部分 COM 接口可能不暴露 GetState
                # 退而求其次：只要会话存在就认为可能播放
                logger.debug(
                    "无法获取 %s 会话状态 (%s)，按 Active 处理",
                    process_name,
                    state_error,
                )

            # 第二层：检查是否静音
            try:
                if session.SimpleAudioVolume.GetMute():
                    logger.debug("%s 音频会话已静音，跳过", process_name)
                    return False, process_name
            except Exception:
                # 无法获取静音状态，忽略此检查
                pass

            # 通过所有检查 → 目标正在播放
            return True, process_name

        # 未找到任何活跃的目标会话
        return False, None