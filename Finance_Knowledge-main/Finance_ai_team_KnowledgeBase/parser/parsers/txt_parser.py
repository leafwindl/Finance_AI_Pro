"""TXT 文件解析器。

复用现有 loader.py（编码检测）+ cleaner.py（文本清洗）。
"""

from pathlib import Path
from typing import Optional

from parser.parsers.base import BaseParser, ParsedDocument
from parser.loader import detect_encoding
from parser.cleaner import clean_text


class TxtParser(BaseParser):
    """解析 .txt / .text / .md 文件。"""

    FORMAT = "txt"
    SUPPORTED_EXTENSIONS = [".txt", ".text", ".md", ".csv", ".log"]
    SUPPORTED_MIMETYPES = ["text/plain", "text/markdown", "text/csv"]

    def __init__(
        self,
        fallback_encodings: Optional[list[str]] = None,
        sample_bytes: int = 65536,
    ):
        self.fallback_encodings = fallback_encodings or [
            "utf-8", "gbk", "gb18030", "gb2312",
        ]
        self.sample_bytes = sample_bytes

    def parse(self, file_path: Path) -> ParsedDocument:
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        raw_bytes = file_path.read_bytes()
        if not raw_bytes:
            return ParsedDocument(
                content="",
                source_path=str(file_path),
                source_format="txt",
                content_hash="",
            )

        # 编码检测
        encoding = detect_encoding(raw_bytes, self.fallback_encodings, self.sample_bytes)

        # 解码
        try:
            content = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            content = raw_bytes.decode(encoding, errors="replace")

        # 统一换行符
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        # 文本清洗
        cleaned = clean_text(
            content,
            max_consecutive_blank_lines=2,
            remove_page_numbers=True,
        )

        return ParsedDocument(
            content=cleaned,
            source_path=str(file_path),
            source_format="txt",
            encoding=encoding,
            content_hash=self._compute_hash(cleaned),
            metadata={"original_length": len(content), "cleaned_length": len(cleaned)},
        )
