"""
模型管理器
负责首次运行时下载模型、检查缓存、报告状态。
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelManager:
    """管理本地模型的下载与缓存"""

    def __init__(self, models_dir: Path):
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)

    def ensure_whisper_model(self, model_size: str) -> Path:
        """确保 Whisper 模型已下载，返回缓存路径"""
        model_dir = self._models_dir / f"faster-whisper-{model_size}"
        if model_dir.exists():
            logger.info("Whisper 模型已缓存: %s", model_dir)
            return model_dir

        logger.info("首次运行，下载 Whisper %s 模型...", model_size)
        logger.info("（约 1.5GB，仅首次需要）")
        return self._models_dir  # faster-whisper 会自动管理缓存

    def check_dependencies(self) -> list[str]:
        """检查关键依赖是否就绪，返回缺失项列表"""
        missing = []
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            missing.append("sounddevice")
        try:
            import pycaw  # noqa: F401
        except ImportError:
            missing.append("pycaw")
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            missing.append("faster-whisper")
        try:
            import torch  # noqa: F401
        except ImportError:
            missing.append("torch")
        try:
            import transformers  # noqa: F401
        except ImportError:
            missing.append("transformers")
        try:
            from PySide6.QtWidgets import QApplication  # noqa: F401
        except ImportError:
            missing.append("PySide6")
        return missing