"""
file_translation — 文件接收与解析

接收上游传过来的文件，解析为文本，供 agent 分析。
"""

from .parser import parse_file, parse_bytes

__all__ = ["parse_file", "parse_bytes"]
