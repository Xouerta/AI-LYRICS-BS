"""
管线总调度器
负责创建所有队列、启动/停止各处理线程，协调整个数据管线。
"""
import queue
import logging

from config import Config
from lyrics_overlay.core.models import AppState
from lyrics_overlay.capture.session_monitor import SessionMonitor
from lyrics_overlay.capture.audio_capture import AudioCapture
from lyrics_overlay.pipeline.vad_processor import VADProcessor
from lyrics_overlay.pipeline.transcriber import Transcriber
from lyrics_overlay.pipeline.translator import Translator

logger = logging.getLogger(__name__)


class Orchestrator:
    """管线总调度

    管理五级队列：
        audio_capture → [audio_queue] → VAD
        → [segment_queue] → Transcriber
        → [transcript_queue] → Translator
        → [display_queue] → UI

    所有后台线程在此统一管理生命周期。
    """

    def __init__(self, config: Config):
        self._config = config
        self._state = AppState.IDLE

        # ── 线程安全队列 ──
        # maxsize 限制内存，防止下游处理慢时 OOM
        self.audio_queue: queue.Queue = queue.Queue(maxsize=200)
        self.segment_queue: queue.Queue = queue.Queue(maxsize=20)
        self.transcript_queue: queue.Queue = queue.Queue(maxsize=10)
        self.display_queue: queue.Queue = queue.Queue(maxsize=30)

        # ── 组件 ──
        self.session_monitor = SessionMonitor(
            target_process_names=config.target_process_names,
            poll_interval=config.session_poll_interval,
        )
        self.audio_capture = AudioCapture(config, self.audio_queue)
        self.vad_processor = VADProcessor(config, self.audio_queue, self.segment_queue)
        self.transcriber = Transcriber(config, self.segment_queue, self.transcript_queue)
        self.translator = Translator(config, self.transcript_queue, self.display_queue)

    def start(self) -> None:
        """启动整个管线"""
        if self._state == AppState.RUNNING:
            logger.warning("管线已在运行中")
            return

        logger.info("=" * 50)
        logger.info("管线启动中...")

        # 1. 音频会话监控先启动
        self.session_monitor.start()

        # 2. 将播放状态查询注入音频捕获
        self.audio_capture.set_playing_provider(
            self.session_monitor.is_target_playing
        )

        # 3. 按数据流方向启动各处理器
        self.audio_capture.start()
        self.vad_processor.start()
        self.transcriber.start()
        self.translator.start()

        self._state = AppState.RUNNING
        logger.info("管线已就绪，等待目标应用播放...")
        logger.info("=" * 50)

    def stop(self) -> None:
        """优雅停止管线（按数据流逆向关闭）"""
        if self._state != AppState.RUNNING:
            return

        logger.info("管线停止中...")
        self._state = AppState.STOPPING

        # 逆向关闭：先断源头，再清下游
        self.audio_capture.stop()
        self.vad_processor.stop()
        self.transcriber.stop()
        self.translator.stop()
        self.session_monitor.stop()

        # 清空所有队列
        for q in [self.audio_queue, self.segment_queue,
                  self.transcript_queue, self.display_queue]:
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

        self._state = AppState.IDLE
        logger.info("管线已完全停止")

    def get_state(self) -> AppState:
        return self._state