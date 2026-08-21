"""文档解析模块 — 多格式文件 → 纯文本。"""

from parser.loader import load_document, RawDocument
from parser.cleaner import clean_text
from parser.parsers import parse_file, get_parser, supported_formats
from parser.parsers.base import BaseParser, ParsedDocument

__all__ = [
    "load_document",
    "RawDocument",
    "clean_text",
    "parse_file",
    "get_parser",
    "supported_formats",
    "BaseParser",
    "ParsedDocument",
]
