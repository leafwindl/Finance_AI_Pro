"""解析器注册表 — 根据文件扩展名自动选择解析器。"""

from pathlib import Path
from typing import Optional, Union

from parser.parsers.base import BaseParser, ParsedDocument
from parser.parsers.txt_parser import TxtParser
from parser.parsers.pdf_parser import PdfParser
from parser.parsers.docx_parser import DocxParser

# 已注册的解析器（按优先级排序）
_PARSERS: list[BaseParser] = [
    TxtParser(),
    PdfParser(),
    DocxParser(),
]


def get_parser(file_path: Union[str, Path]) -> Optional[BaseParser]:
    """根据文件扩展名获取解析器。"""
    path = Path(file_path)
    for parser in _PARSERS:
        if parser.supports(path):
            return parser
    return None


def parse_file(file_path: Union[str, Path]) -> ParsedDocument:
    """统一入口：自动选择解析器并解析文件。

    Raises:
        ValueError: 不支持的文件格式或无匹配解析器
        RuntimeError: 解析过程出错
    """
    path = Path(file_path)
    parser = get_parser(path)
    if parser is None:
        ext = path.suffix or "(无扩展名)"
        supported = []
        for p in _PARSERS:
            supported.extend(p.SUPPORTED_EXTENSIONS)
        raise ValueError(
            f"不支持的文件格式: {ext}（文件: {path.name}）\n"
            f"当前支持: {supported}"
        )
    return parser.parse(path)


def supported_formats() -> list[str]:
    """返回所有支持的文件扩展名。"""
    exts = []
    for p in _PARSERS:
        exts.extend(p.SUPPORTED_EXTENSIONS)
    return sorted(set(exts))
