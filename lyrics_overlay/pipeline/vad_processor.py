"""
语音活动检测处理器
使用 Silero VAD 对音频流进行实时语音分段。
"""
import threading
import logging
import queue

import numpy as np
import torch

from config import Config
from lyrics_overlay.core.models import AudioSegment

logger = logging.getLogger(__name__)


class VADProcessor:
    """Silero VAD 语音分段处理器

    从 audio_queue 读取音频块，用 VADIterator 进行流式语音检测，
    在检测到静音时输出完整的 AudioSegment 到 segment_queue。
    """

    def __init__(
        self,
        config: Config,
        audio_queue: queue.Queue,
        segment_queue: queue.Queue,
    ):
        self._config = config
        self._audio_queue = audio_queue
        self._segment_queue = segment_queue

        self._running = False
        self._thread: threading.Thread | None = None

        # VAD 模型（延迟加载）
        self._model = None
        self._vad_iterator = None

        # 缓冲区
        self._speech_buffer: list[np.ndarray] = []
        self._speech_start_time: float | None = None
        self._total_buffered_ms = 0

        # 静音计时
        self._silence_ms = 0
        self._block_ms = config.block_duration_ms

    def start(self) -> None:
        if self._running:
            return
        self._load_model()
        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop, daemon=True, name="VADProcessor"
        )
        self._thread.start()
        logger.info("VADProcessor 启动")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("VADProcessor 已停止")

    def _load_model(self) -> None:
        """加载 Silero VAD 模型"""
        logger.info("正在加载 Silero VAD 模型...")
        self._model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            trust_repo=True,
        )
        (_, _, _, VADIterator, _) = utils
        self._vad_iterator = VADIterator(
            self._model,
            threshold=self._config.vad_speech_threshold,
            sampling_rate=self._config.sample_rate,
        )
        logger.info("Silero VAD 模型加载完成")

    def _process_loop(self) -> None:
        """VAD 处理主循环"""
        while self._running:
            try:
                audio_chunk, timestamp = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                # 超时没有数据，检查是否需要强制切段
                if (self._speech_buffer and
                        self._total_buffered_ms >= self._config.vad_silence_threshold_ms):
                    self._force_flush()
                continue

            # 转换为 float32 且确保是 1D
            chunk = np.asarray(audio_chunk, dtype=np.float32).flatten()
            if len(chunk) == 0:
                continue

            # 送入 Silero VADIterator
            speech_dict = self._vad_iterator(chunk, return_seconds=True)

            if speech_dict:
                if 'start' in speech_dict:
                    # 语音开始
                    self._speech_start_time = timestamp
                    self._speech_buffer = [chunk]
                    self._total_buffered_ms = self._block_ms
                    self._silence_ms = 0

                elif 'end' in speech_dict and self._speech_buffer:
                    # 语音结束 → 输出完整段
                    self._speech_buffer.append(chunk)
                    self._output_segment()

            elif self._speech_buffer:
                # 当前在语音中，追加数据
                self._speech_buffer.append(chunk)
                self._total_buffered_ms += self._block_ms
                self._silence_ms += self._block_ms

                # 静音超时 → 句子结束
                if self._silence_ms >= self._config.vad_silence_threshold_ms:
                    self._output_segment()

                # 最大缓冲保护 → 强制切段
                elif self._total_buffered_ms >= self._config.vad_max_buffer_ms:
                    logger.warning("达到最大缓冲 %dms，强制切段",
                                   self._config.vad_max_buffer_ms)
                    self._output_segment()

    def _output_segment(self) -> None:
        """将当前缓冲输出为 AudioSegment"""
        if not self._speech_buffer:
            return

        audio = np.concatenate(self._speech_buffer)
        total_ms = len(audio) / self._config.sample_rate * 1000

        # 太短的段丢弃（噪音）
        if total_ms < self._config.vad_min_speech_ms:
            logger.debug("丢弃过短语音段 %.0fms", total_ms)
            self._reset_buffer()
            return

        segment = AudioSegment(
            audio=audio,
            sample_rate=self._config.sample_rate,
            start_time=self._speech_start_time or 0.0,
            duration=total_ms / 1000.0,
        )
        try:
            self._segment_queue.put_nowait(segment)
            logger.debug("输出语音段: %.1fs", segment.duration)
        except queue.Full:
            logger.warning("语音段队列已满，丢弃一段")

        self._reset_buffer()

    def _force_flush(self) -> None:
        """强制输出当前缓冲（用于关闭/暂停时）"""
        if self._speech_buffer:
            self._vad_iterator.reset_states()
            self._output_segment()

    def _reset_buffer(self) -> None:
        self._speech_buffer = []
        self._speech_start_time = None
        self._total_buffered_ms = 0
        self._silence_ms = 0