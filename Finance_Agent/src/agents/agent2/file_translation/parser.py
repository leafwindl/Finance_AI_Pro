"""
文件解析器 — 将各种格式的文件内容提取为纯文本。
"""

import os
from pathlib import Path

# 支持的文件类型
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".txt": "纯文本",
    ".md": "Markdown",
    ".py": "Python",
    ".json": "JSON",
    ".csv": "CSV",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".log": "日志",
    ".sql": "SQL",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class FileParseError(Exception):
    """文件解析异常。"""
    pass


def parse_bytes(filename: str, content: bytes) -> str:
    """从内存中的字节内容解析文本。

    Args:
        filename: 原始文件名（用于判断类型）
        content: 文件字节内容

    Returns:
        解析后的纯文本字符串
    """
    ext = Path(filename).suffix.lower()

    if len(content) > MAX_FILE_SIZE:
        raise FileParseError(f"文件过大，上限 {MAX_FILE_SIZE // 1024 // 1024}MB")

    if ext not in SUPPORTED_EXTENSIONS:
        raise FileParseError(
            f"不支持的文件类型: {ext}，支持: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # 尝试 UTF-8，失败则用 GBK
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    raise FileParseError(f"无法解码文件: {filename}")


def parse_file(file_path: str) -> str:
    """从磁盘路径读取文件并解析为文本。

    Args:
        file_path: 文件路径

    Returns:
        解析后的纯文本字符串
    """
    if not os.path.isfile(file_path):
        raise FileParseError(f"文件不存在: {file_path}")

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        content = f.read()

    return parse_bytes(filename, content)
