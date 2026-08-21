"""日志记录模块。

提供统一的日志配置，支持控制台和文件输出。
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

# 日志格式
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "knowledge_parser",
    level: int = logging.INFO,
    log_file: Optional[Union[str, Path]] = None,
) -> logging.Logger:
    """创建并配置日志记录器。

    Args:
        name: 日志记录器名称。
        level: 日志级别。
        log_file: 日志文件路径（可选，为 None 时仅输出到控制台）。

    Returns:
        配置好的 Logger 实例。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件 handler（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "knowledge_parser") -> logging.Logger:
    """获取已有的 Logger 实例，不存在则创建默认的。

    Args:
        name: 日志记录器名称。

    Returns:
        Logger 实例。
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger = setup_logger(name)
    return logger
