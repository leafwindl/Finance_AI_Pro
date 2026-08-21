"""文本清洗模块。

负责对原始文本进行标准化清洗：
- 空白处理（多余空行、连续空格）
- 特殊字符处理（制表符、不可见字符）
- 页眉页脚处理（页码、重复标题）
"""

import logging
import re
from typing import Optional

from shared.logger import get_logger

logger = get_logger(__name__)

# 默认页眉页脚正则模式
DEFAULT_HEADER_FOOTER_PATTERNS: list[str] = [
    r"^第\s*\d+\s*页\s*$",                      # 第1页
    r"^第\s*\d+\s*页\s*/\s*共\s*\d+\s*页\s*$",  # 第1页/共10页
    r"^\d+\s*/\s*\d+\s*$",                      # 1/10
    r"^［\d+］$",                                 # ［1］
    r"^\[\d+\]$",                                 # [1]
]

# 不可见字符正则（保留常用空白）
_INVISIBLE_CHARS_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​‌‍‎‏"
    r"﻿⁠⁡⁢⁣⁤]"
)


def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """将字符串模式列表编译为正则对象列表。"""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error as e:
            logger.warning("无效的正则表达式 '%s': %s", p, e)
    return compiled


def _remove_invisible_chars(line: str) -> str:
    """移除行内的不可见/控制字符（保留换行符和常见空白）。"""
    return _INVISIBLE_CHARS_PATTERN.sub("", line)


def _is_header_footer_line(
    line: str,
    compiled_patterns: list[re.Pattern],
) -> bool:
    """判断一行是否匹配页眉页脚模式。"""
    stripped = line.strip()
    if not stripped:
        return False
    for pattern in compiled_patterns:
        if pattern.search(stripped):
            return True
    return False


def _detect_repeated_title(
    lines: list[str],
    threshold: float = 0.3,
    min_occurrences: int = 3,
) -> set[str]:
    """检测并返回重复出现的疑似页眉标题行。

    如果某非空行在文档中重复出现次数超过阈值比例，则判定为页眉重复标题。

    Args:
        lines: 所有行（已拆分）。
        threshold: 出现比例阈值（默认 0.3，即超过 30% 的页都可能出现）。
        min_occurrences: 最少出现次数。

    Returns:
        疑似重复标题行的集合。
    """
    from collections import Counter

    # 统计非空、非纯数字行的出现次数
    non_empty_lines = [
        line.strip()
        for line in lines
        if line.strip() and not re.match(r"^\s*\d+\s*$", line.strip())
    ]
    counter = Counter(non_empty_lines)

    total_estimated_pages = max(len(lines) // 40, 1)  # 估算页数（每页约40行）
    repeated = set()
    for text, count in counter.items():
        # 长度合理（10-60字符，可能是标题）
        if 10 <= len(text) <= 60:
            if count >= min_occurrences and count / max(total_estimated_pages, 1) >= threshold:
                repeated.add(text)
                logger.debug("检测到重复标题: '%s' (出现 %d 次)", text, count)

    return repeated


def clean_text(
    content: str,
    max_consecutive_blank_lines: int = 2,
    remove_page_numbers: bool = True,
    remove_repeated_title: bool = True,
    tab_to_spaces: int = 4,
    header_footer_patterns: Optional[list[str]] = None,
) -> str:
    """清洗文本内容。

    执行以下清洗步骤：
    1. 移除不可见/控制字符
    2. 制表符替换为空格
    3. 移除页眉页脚行（页码、重复标题等）
    4. 合并连续空行到指定上限
    5. 去除首尾空白

    Args:
        content: 原始文本内容。
        max_consecutive_blank_lines: 最多连续空行数。
        remove_page_numbers: 是否移除页码。
        remove_repeated_title: 是否检测并移除重复标题。
        tab_to_spaces: 制表符替换为空格数。
        header_footer_patterns: 额外的页眉页脚正则模式。

    Returns:
        清洗后的文本内容。
    """
    logger.info("开始文本清洗 (长度: %d 字符)", len(content))

    # 编译页眉页脚模式
    patterns = list(DEFAULT_HEADER_FOOTER_PATTERNS)
    if header_footer_patterns:
        patterns.extend(header_footer_patterns)
    compiled_patterns = _compile_patterns(patterns) if remove_page_numbers else []

    lines = content.split("\n")
    original_line_count = len(lines)

    # 第一遍：检测重复标题（需在移除前完成）
    repeated_titles: set[str] = set()
    if remove_repeated_title:
        repeated_titles = _detect_repeated_title(lines)

    # 第二遍：逐行清洗
    cleaned_lines: list[str] = []
    consecutive_blank = 0

    for line in lines:
        # 1. 移除不可见字符
        line = _remove_invisible_chars(line)

        # 2. 制表符替换
        if tab_to_spaces > 0:
            line = line.replace("\t", " " * tab_to_spaces)

        # 3. 移除页眉页脚
        if remove_page_numbers and _is_header_footer_line(line, compiled_patterns):
            logger.debug("移除页眉页脚行: '%s'", line.strip())
            continue

        # 4. 移除重复标题
        if remove_repeated_title and line.strip() in repeated_titles:
            logger.debug("移除重复标题行: '%s'", line.strip())
            continue

        # 5. 处理空行
        stripped = line.strip()
        if not stripped:
            consecutive_blank += 1
            if consecutive_blank <= max_consecutive_blank_lines:
                cleaned_lines.append("")
            continue

        consecutive_blank = 0
        cleaned_lines.append(line)

    # 去除首尾空行
    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()

    result = "\n".join(cleaned_lines)
    logger.info(
        "文本清洗完成: %d 行 → %d 行 (%d → %d 字符)",
        original_line_count,
        len(cleaned_lines),
        len(content),
        len(result),
    )
    return result
