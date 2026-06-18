"""
语音识别模块
使用 faster-whisper 进行本地语音转文字。
"""
import logging
import threading
import queue
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from config import Config
from lyrics_overlay.core.models import AudioSegment, Transcript

logger = logging.getLogger(__name__)


class Transcriber:
    """faster-whisper 语音识别封装

    在独立线程中从 segment_queue 读取语音段，
    使用本地 Whisper 模型进行识别，输出 Transcript 到 transcript_queue。
    """

    def __init__(
        self,
        config: Config,
        segment_queue: queue.Queue,
        transcript_queue: queue.Queue,
    ):
        self._config = config
        self._segment_queue = segment_queue
        self._transcript_queue = transcript_queue

        self._model: Optional[WhisperModel] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._load_model()
        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop, daemon=True, name="Transcriber"
        )
        self._thread.start()
        logger.info("Transcriber 启动 | 模型: %s | 设备: %s",
                     self._config.whisper_model_size, self._config.whisper_device)

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("Transcriber 已停止")

    def _load_model(self) -> None:
        """加载 faster-whisper 模型"""
        logger.info("正在加载 Whisper 模型 (%s)...", self._config.whisper_model_size)
        self._model = WhisperModel(
            self._config.whisper_model_size,
            device=self._config.whisper_device,
            compute_type=self._config.whisper_compute_type,
            download_root=str(self._config.models_dir),
        )
        logger.info("Whisper 模型加载完成")

    def _process_loop(self) -> None:
        """识别处理主循环"""
        while self._running:
            try:
                segment: AudioSegment = self._segment_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                transcript = self._transcribe(segment)
                if transcript and transcript.text.strip():
                    try:
                        self._transcript_queue.put_nowait(transcript)
                        logger.info("识别结果 [%s]: %s",
                                     transcript.language, transcript.text[:60])
                    except queue.Full:
                        logger.warning("识别结果队列已满，丢弃一条")
                else:
                    logger.debug("空识别结果，丢弃")

            except Exception as e:
                logger.error("识别异常: %s", e, exc_info=True)

    def _transcribe(self, segment: AudioSegment) -> Optional[Transcript]:
        """对单个语音段进行识别"""
        if self._model is None:
            return None

        # faster-whisper 需要 float32 数组
        audio = segment.audio.astype(np.float32)

        segments, info = self._model.transcribe(
            audio,
            language=self._config.whisper_language,
            beam_size=self._config.whisper_beam_size,
            vad_filter=False,           # 我们已自己做 VAD
            without_timestamps=True,    # 歌词场景不需要逐字时间戳
        )

        # 合并所有 segment 文本
        texts = [seg.text.strip() for seg in segments]
        full_text = ''.join(texts)

        # 计算平均置信度
        confidences = []
        raw_segments = list(self._model.transcribe(
            audio,
            language=self._config.whisper_language,
            beam_size=self._config.whisper_beam_size,
            vad_filter=False,
            without_timestamps=False,
        )[0])
        for seg in raw_segments:
            if hasattr(seg, 'avg_logprob') and seg.avg_logprob is not None:
                confidences.append(np.exp(seg.avg_logprob))

        avg_confidence = float(np.mean(confidences)) if confidences else 0.0

        return Transcript(
            text=full_text,
            language=info.language,
            language_probability=info.language_probability,
            confidence=avg_confidence,
            segments=[],  # 歌词场景暂不保留逐段信息
        )