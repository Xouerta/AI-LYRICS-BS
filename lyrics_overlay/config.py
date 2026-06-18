"""
全局配置中心
所有可调参数集中在此，支持从字典/环境变量覆盖。
"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # ── 项目路径 ──
    project_root: Path = field(default_factory=lambda: Path(__file__).parent)
    models_dir: Path = field(default_factory=lambda: Path(__file__).parent / "models")

    # ── 音频捕获 ──
    sample_rate: int = 16000          # 16kHz 单声道，Whisper 要求
    block_duration_ms: int = 30       # sounddevice 每次读取 30ms
    audio_channels: int = 1           # 单声道
    # WASAPI loopback 设备名（None = 自动查找默认回路设备）
    loopback_device: str | None = None

    # ── 会话监控 ──
    session_poll_interval: float = 0.5       # pycaw 轮询间隔（秒）
    # 目标进程名（小写），可运行时修改
    target_process_names: list[str] = field(default_factory=lambda: [
        "cloudmusic.exe",
        "qqmusic.exe",
        "spotify.exe",
        "music-ui.exe",     # 网易云 UWP
    ])

    # ── VAD 语音活动检测 ──
    vad_silence_threshold_ms: int = 800      # 静音多久判定句子结束
    vad_min_speech_ms: int = 300             # 最短有效语音（过滤短噪音）
    vad_max_buffer_ms: int = 15000           # 最大缓冲（防止 OOM，15 秒强制切）
    vad_speech_threshold: float = 0.5        # Silero 语音概率阈值

    # ── Whisper 语音识别 ──
    whisper_model_size: str = "medium"       # tiny/small/medium/large-v3
    whisper_compute_type: str = "int8"       # CPU: int8; GPU: float16
    whisper_device: str = "cpu"              # "cpu" | "cuda"
    whisper_beam_size: int = 5               # 束搜索宽度
    whisper_language: str | None = None      # None = 自动检测; "zh"/"en"/"ja"

    # ── 翻译 ──
    translation_enabled: bool = True
    nllb_model: str = "facebook/nllb-200-distilled-600M"
    # NLLB 语言代码映射
    lang_code_map: dict = field(default_factory=lambda: {
        "en": {"src": "eng_Latn", "tgt": "zho_Hans"},
        "ja": {"src": "jpn_Jpan", "tgt": "zho_Hans"},
    })

    # ── 字幕显示 ──
    font_name: str = "Microsoft YaHei"       # 中文字体
    font_size: int = 36
    window_width: int = 900
    window_height: int = 130
    # 窗口位置：None = 自动居中底部
    window_x: int | None = None
    window_y: int | None = None
    display_poll_interval: int = 80          # UI 轮询间隔（ms）
    lyrics_fade_duration: int = 300          # 歌词淡入动画（ms）

    def __post_init__(self):
        self.models_dir.mkdir(parents=True, exist_ok=True)