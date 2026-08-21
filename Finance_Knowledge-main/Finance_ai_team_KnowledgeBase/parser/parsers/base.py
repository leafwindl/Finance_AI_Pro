"""解析器抽象基类。

所有格式解析器必须实现 parse()，返回 ParsedDocument。
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDocument:
    """解析器输出 — 清洗后的纯文本 + 来源信息。

    这是所有解析器的统一输出格式，分类模块只消费此结构。
    """

    content: str
    """清洗后的纯文本内容"""

    source_path: str
    """原始文件路径"""

    source_format: str
    """原始格式：txt | pdf | docx | html | image"""

    encoding: str = ""
    """文本编码（PDF/图片 OCR 填空）"""

    content_hash: str = ""
    """内容 SHA256 前 16 位，用于去重"""

    metadata: dict = field(default_factory=dict)
    """格式特有元数据，如 {"pages": 12, "author": "xxx"}"""


class BaseParser(ABC):
    """解析器基类 — 所有格式解析器继承此类。"""

    # 子类必须覆盖
    FORMAT: str = ""                       # 格式标识，如 "pdf"
    SUPPORTED_EXTENSIONS: list[str] = []   # 如 [".pdf"]
    SUPPORTED_MIMETYPES: list[str] = []    # 如 ["application/pdf"]

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        """解析文件，返回清洗后的文本。"""
        ...

    def _compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def supports(cls, path: Path) -> bool:
        """检测是否支持此文件。"""
        ext = path.suffix.lower()
        return ext in cls.SUPPORTED_EXTENSIONS
