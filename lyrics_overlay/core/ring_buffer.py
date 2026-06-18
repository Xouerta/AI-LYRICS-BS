"""
线程安全的环形缓冲区
用于音频捕获回调与 VAD 处理器之间的低延迟数据传递。
相比 queue.Queue，避免了 Python 对象的装箱/拆箱开销。
"""
import threading
import numpy as np


class RingBuffer:
    """固定容量的环形缓冲区，线程安全。

    单生产者（audio callback）、单消费者（VAD processor）场景，
    写满时覆盖旧数据，读空时返回 None。
    """

    def __init__(self, capacity_frames: int, dtype=np.float32):
        """
        Args:
            capacity_frames: 缓冲区容量（帧数，非字节数）
            dtype: numpy 数据类型
        """
        self._capacity = capacity_frames
        self._buffer = np.zeros(capacity_frames, dtype=dtype)
        self._write_idx = 0
        self._read_idx = 0
        self._avail = 0              # 可读帧数（原子更新由锁保证）
        self._lock = threading.Lock()

    def write(self, data: np.ndarray) -> int:
        """写入音频数据。写满则覆盖旧数据。

        Returns:
            实际写入的帧数
        """
        n = len(data)
        if n == 0:
            return 0

        with self._lock:
            if n >= self._capacity:
                # 数据大于缓冲区，只保留最后 capacity 帧
                self._buffer[:] = data[-self._capacity:]
                self._write_idx = 0
                self._read_idx = 0
                self._avail = self._capacity
                return self._capacity

            # 分两段写入（处理回绕）
            space_to_end = self._capacity - self._write_idx
            if n <= space_to_end:
                self._buffer[self._write_idx:self._write_idx + n] = data
                self._write_idx = (self._write_idx + n) % self._capacity
            else:
                first_part = space_to_end
                self._buffer[self._write_idx:] = data[:first_part]
                remaining = n - first_part
                self._buffer[:remaining] = data[first_part:]
                self._write_idx = remaining

            # 更新可用量（可能覆盖未读数据）
            self._avail = min(self._avail + n, self._capacity)
            # 如果写指针追上读指针，读指针前移
            if self._avail == self._capacity:
                self._read_idx = self._write_idx

        return n

    def read(self, n_frames: int) -> np.ndarray | None:
        """读取 n_frames 帧音频数据。

        Returns:
            numpy array 或 None（数据不足时）
        """
        if n_frames <= 0:
            return np.array([], dtype=self._buffer.dtype)

        with self._lock:
            if self._avail < n_frames:
                return None

            result = np.empty(n_frames, dtype=self._buffer.dtype)
            space_to_end = self._capacity - self._read_idx
            if n_frames <= space_to_end:
                result[:] = self._buffer[self._read_idx:self._read_idx + n_frames]
            else:
                first_part = space_to_end
                result[:first_part] = self._buffer[self._read_idx:]
                remaining = n_frames - first_part
                result[first_part:] = self._buffer[:remaining]

            self._read_idx = (self._read_idx + n_frames) % self._capacity
            self._avail -= n_frames
            return result

    def read_all_available(self) -> np.ndarray:
        """一次性读取所有可用数据。

        Returns:
            numpy array（可能为空）
        """
        with self._lock:
            if self._avail == 0:
                return np.array([], dtype=self._buffer.dtype)
            result = self.read(self._avail)
            return result if result is not None else np.array([], dtype=self._buffer.dtype)

    def reset(self) -> None:
        """清空缓冲区"""
        with self._lock:
            self._write_idx = 0
            self._read_idx = 0
            self._avail = 0

    @property
    def available(self) -> int:
        with self._lock:
            return self._avail

    @property
    def capacity(self) -> int:
        return self._capacity