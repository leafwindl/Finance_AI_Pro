"""文件读取与编码检测模块。

负责读取原始 txt 文件，自动检测文件编码，返回标准化的文档对象。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from shared.file_utils import read_file_bytes
from shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RawDocument:
    """原始文档对象，保存读取结果。"""

    filename: str
    """文件名称（不含路径）"""

    source_path: Path
    """原始文件路径"""

    encoding: str
    """检测到的文件编码"""

    content: str
    """文件正文内容"""

    raw_bytes: bytes = field(repr=False)
    """原始字节数据（调试用）"""


def detect_encoding(
    data: bytes,
    fallbacks: list[str],
    sample_bytes: int = 65536,
) -> str:
    """自动检测文本编码。

    依次尝试 fallback 列表中的编码，使用 strict 模式解码。
    返回第一个成功解码的编码名称。
    若全部失败，使用 utf-8 + replace 模式兜底。

    Args:
        data: 原始字节数据。
        fallbacks: 候选编码列表，按优先级排列。
        sample_bytes: 检测用的最大字节数（取文件前 N 字节）。

    Returns:
        检测到的编码名称（如 "utf-8", "gbk"）。
    """
    sample = data[:sample_bytes]

    for encoding in fallbacks:
        try:
            sample.decode(encoding)
            logger.debug("编码检测成功: %s", encoding)
            return encoding
        except (UnicodeDecodeError, LookupError) as e:
            logger.debug("编码 %s 解码失败: %s", encoding, e)
            continue

    # 兜底：utf-8 + replace
    logger.warning(
        "所有编码检测失败 (%s)，使用 utf-8 + replace 兜底",
        fallbacks,
    )
    return "utf-8"


def load_document(
    file_path: Union[str, Path],
    fallback_encodings: Optional[list[str]] = None,
    sample_bytes: int = 65536,
) -> RawDocument:
    """读取并解析单个 txt 文件。

    执行流程：
    1. 读取文件字节数据
    2. 自动检测编码
    3. 解码为文本内容
    4. 标准化换行符为 \\n
    5. 返回 RawDocument 对象

    Args:
        file_path: 文件路径。
        fallback_encodings: 候选编码列表，默认 ["utf-8", "gbk", "gb18030", "gb2312"]。
        sample_bytes: 编码检测采样字节数。

    Returns:
        RawDocument 对象，包含文件名、编码和文本内容。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
    """
    if fallback_encodings is None:
        fallback_encodings = ["utf-8", "gbk", "gb18030", "gb2312"]

    path = Path(file_path)
    logger.info("开始加载文件: %s", path)

    # 1. 读取字节
    data = read_file_bytes(path)
    logger.debug("读取字节数: %d", len(data))

    if len(data) == 0:
        logger.warning("文件为空: %s", path)
        return RawDocument(
            filename=path.name,
            source_path=path,
            encoding="utf-8",
            content="",
            raw_bytes=data,
        )

    # 2. 编码检测
    encoding = detect_encoding(data, fallback_encodings, sample_bytes)

    # 3. 解码
    try:
        content = data.decode(encoding)
    except UnicodeDecodeError:
        logger.warning(
            "编码 %s 解码失败，使用 replace 模式兜底", encoding
        )
        content = data.decode(encoding, errors="replace")

    # 4. 标准化换行符
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    logger.info("文件加载完成: %s (编码: %s, 长度: %d 字符)", path.name, encoding, len(content))

    return RawDocument(
        filename=path.name,
        source_path=path,
        encoding=encoding,
        content=content,
        raw_bytes=data,
    )
