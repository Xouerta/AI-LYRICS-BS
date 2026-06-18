"""
数据模型
定义管线中流转的所有数据结构，使用 dataclass 保证类型清晰。
"""
from dataclasses import dataclass, field
from enum import Enum, auto
import numpy as np


class AppState(Enum):
    """应用/管线整体状态"""
    IDLE = auto()       # 未启动
    RUNNING = auto()    # 运行中
    PAUSED = auto()     # 暂停（目标应用无声）
    STOPPING = auto()   # 正在关闭
    ERROR = auto()      # 出错


class Lang(Enum):
    """识别的语言类型"""
    ZH = "zh"
    EN = "en"
    JA = "ja"
    UNKNOWN = "unknown"

    def needs_translation(self) -> bool:
        """是否需要翻译成中文"""
        return self in (Lang.EN, Lang.JA)


@dataclass
class AudioSegment:
    """一段有效的语音片段（VAD 切分后的输出）"""
    audio: np.ndarray           # 原始音频数据 (float32, 16kHz mono)
    sample_rate: int = 16000
    start_time: float = 0.0     # 相对捕获开始的时间偏移（秒）
    duration: float = 0.0       # 时长（秒）

    def __post_init__(self):
        if self.audio.ndim != 1:
            raise ValueError("AudioSegment 音频必须是 1D numpy array")
        if self.duration == 0.0:
            self.duration = len(self.audio) / self.sample_rate


@dataclass
class Transcript:
    """Whisper 识别结果"""
    text: str                           # 识别文本
    language: str                       # 检测到的语言代码 "zh"/"en"/"ja"
    language_probability: float = 1.0   # 语言置信度
    confidence: float = 0.0             # 平均置信度
    segments: list = field(default_factory=list)  # 原始 segment 列表


@dataclass
class LyricsLine:
    """最终显示的单行歌词"""
    original: str           # 原文
    translated: str = ""    # 中文翻译（如果需要）
    is_translated: bool = False
    timestamp: float = 0.0  # 接收时间戳