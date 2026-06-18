"""
翻译模块
使用 NLLB-200 模型将英文/日语歌词翻译为中文。
"""
import logging
import threading
import queue
from typing import Optional

from transformers import pipeline

from config import Config
from lyrics_overlay.core.models import Transcript, LyricsLine

logger = logging.getLogger(__name__)


class Translator:
    """NLLB-200 歌词翻译封装

    从 transcript_queue 读取识别结果，
    对英文/日语文本进行中文翻译，输出 LyricsLine 到 display_queue。
    中文文本直接透传，不翻译。
    """

    def __init__(
        self,
        config: Config,
        transcript_queue: queue.Queue,
        display_queue: queue.Queue,
    ):
        self._config = config
        self._transcript_queue = transcript_queue
        self._display_queue = display_queue

        self._model = None
        self._tokenizer = None
        self._pipe = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        if self._config.translation_enabled:
            self._load_model()
        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop, daemon=True, name="Translator"
        )
        self._thread.start()
        logger.info("Translator 启动 | 翻译: %s",
                     "启用" if self._config.translation_enabled else "禁用")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Translator 已停止")

    def _load_model(self) -> None:
        """加载 NLLB-200 翻译模型"""
        model_name = self._config.nllb_model
        logger.info("正在加载翻译模型 (%s)...", model_name)
        try:
            self._pipe = pipeline(
                'translation',
                model=model_name,
                tokenizer=model_name,
                device=-1,  # CPU
            )
            logger.info("翻译模型加载完成")
        except Exception as e:
            logger.error("翻译模型加载失败: %s，翻译功能将禁用", e)
            self._config.translation_enabled = False

    def _process_loop(self) -> None:
        """翻译处理主循环"""
        while self._running:
            try:
                transcript: Transcript = self._transcript_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                lyrics = self._build_lyrics_line(transcript)
                try:
                    self._display_queue.put_nowait(lyrics)
                except queue.Full:
                    logger.warning("显示队列已满，丢弃一条")
            except Exception as e:
                logger.error("翻译异常: %s", e, exc_info=True)

    def _build_lyrics_line(self, transcript: Transcript) -> LyricsLine:
        """构建最终的歌词行（必要时翻译）"""
        lang = transcript.language
        original = transcript.text.strip()

        if not self._config.translation_enabled or lang not in ('en', 'ja'):
            # 中文或禁用翻译 → 直接输出原文
            return LyricsLine(
                original=original,
                translated="",
                is_translated=False,
                timestamp=transcript.confidence,  # 借用字段
            )

        # 需要翻译
        lang_config = self._config.lang_code_map.get(lang)
        if not lang_config or self._pipe is None:
            return LyricsLine(original=original, is_translated=False)

        try:
            result = self._pipe(
                original,
                src_lang=lang_config['src'],
                tgt_lang=lang_config['tgt'],
                max_length=128,
            )
            translated = result[0]['translation_text']
        except Exception as e:
            logger.warning("翻译失败 (%s→zh): %s", lang, e)
            translated = ""

        return LyricsLine(
            original=original,
            translated=translated,
            is_translated=True,
            timestamp=0.0,
        )