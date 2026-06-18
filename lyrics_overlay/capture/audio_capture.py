"""
音频捕获模块
使用 sounddevice 通过 WASAPI loopback 捕获系统音频输出。
"""
import threading
import logging
import queue
import time

import numpy as np
import sounddevice as sd
from sounddevice import CallbackFlags

from config import Config

logger = logging.getLogger(__name__)


class AudioCapture:
    """系统音频回路捕获器

    在独立线程中运行 sounddevice InputStream，
    通过 WASAPI loopback 抓取系统混音输出。
    同时接受外部信号（SessionMonitor.is_target_playing）控制是否发放数据。
    """

    def __init__(self, config: Config, audio_queue: queue.Queue):
        """
        Args:
            config: 全局配置
            audio_queue: 输出队列，放入 (numpy_array, timestamp) 元组
        """
        self._config = config
        self._audio_queue = audio_queue
        self._stream: sd.InputStream | None = None
        self._running = False
        self._thread: threading.Thread | None = None

        # 外部注入：由 Orchestrator 设置
        self._is_playing_provider: callable = lambda: True
        # 时间戳跟踪
        self._block_samples = int(config.sample_rate * config.block_duration_ms / 1000)
        self._blocks_captured = 0

    def set_playing_provider(self, provider: callable) -> None:
        """设置目标应用播放状态查询回调"""
        self._is_playing_provider = provider

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="AudioCapture"
        )
        self._thread.start()
        logger.info("AudioCapture 启动 | sample_rate=%d | block=%dms",
                     self._config.sample_rate, self._config.block_duration_ms)

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("AudioCapture 已停止")

    def _capture_loop(self) -> None:
        """音频采集主循环（阻塞式读取）"""
        try:
            device = self._find_loopback_device()
            logger.info("使用回路设备: %s", device)

            self._stream = sd.InputStream(
                device=device,
                channels=self._config.audio_channels,
                samplerate=self._config.sample_rate,
                blocksize=self._block_samples,
                dtype='float32',
                latency='low',
            )
            self._stream.start()

            while self._running:
                # 阻塞读取一个音频块
                indata, _ = self._stream.read(self._block_samples)
                indata = indata.flatten()

                # 只在目标应用播放时才分发数据
                if self._is_playing_provider():
                    timestamp = self._blocks_captured * (
                        self._config.block_duration_ms / 1000.0
                    )
                    try:
                        self._audio_queue.put_nowait((indata.copy(), timestamp))
                    except queue.Full:
                        # 队列满了说明下游处理不过来，丢弃旧数据
                        logger.debug("音频队列已满，丢弃一帧")
                        try:
                            self._audio_queue.get_nowait()  # 丢弃最旧
                            self._audio_queue.put_nowait((indata.copy(), timestamp))
                        except queue.Empty:
                            pass

                self._blocks_captured += 1

        except sd.PortAudioError as e:
            logger.error("音频设备错误: %s", e)
        except Exception as e:
            logger.error("捕获循环异常: %s", e, exc_info=True)
        finally:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None

    def _find_loopback_device(self) -> int | None:
        """查找 WASAPI 回路设备"""
        if self._config.loopback_device:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if self._config.loopback_device in dev['name']:
                    return i
        # 自动查找
        try:
            # WASAPI loopback 设备名通常包含 "Loopback" 或为默认输出设备
            host_api = sd.query_hostapis()
            for api in host_api:
                if 'WASAPI' in api['name']:
                    default_output = api['default_output_device']
                    if default_output is not None:
                        return default_output
        except Exception:
            pass
        return sd.default.device[0]  # 回退到系统默认