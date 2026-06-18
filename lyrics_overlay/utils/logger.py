"""
统一日志模块
控制台输出 + 可选文件日志，全项目共用一个 logger 配置。
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(
    level: int = logging.INFO,
    log_file: str | None = "lyrics_overlay.log",
    max_bytes: int = 5 * 1024 * 1024,  # 5MB
    backup_count: int = 3,
) -> None:
    """初始化全局日志配置，只调用一次。

    格式: [时间] [级别] [模块名] 消息内容
    """
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # 文件 handler（可关闭）
    if log_file:
        log_path = Path(log_file)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)  # 文件保留更详细
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # 降低第三方库日志噪音
    for noisy in ["comtypes", "PIL", "urllib3"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)