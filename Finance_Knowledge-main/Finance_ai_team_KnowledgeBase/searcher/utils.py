"""
工具函数模块 — utils.py
==============================
提供 Markdown 切片、SHA256 哈希计算、文本向量化三个核心工具。

Markdown 切片策略：
    - 以一级标题（"# " 开头）为分割边界。
    - 文档中第一个 "#" 之前的内容（如 YAML frontmatter 或导言）作为"文档前言"切片。
    - 每个切片保留其原始标题行，方便下游按标题检索。

哈希策略：
    - 对切片文本计算 SHA256，用于检测内容是否变更（增量更新）。
"""
from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from typing import List, Tuple

from shared.embedding import (
    batch_text_to_vectors,
    get_embedding_model as _get_embedding_model,
    text_to_vector,
)
from shared.hash_utils import compute_chunk_hashes, sha256_hash

_project_root = Path(__file__).resolve().parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

logger = logging.getLogger(__name__)

# ============================================================
#  Markdown 切片
# ============================================================

def slice_markdown(markdown_text: str, source_file: str = "") -> List[dict]:
    """
    按一级标题（'# ' 开头）将 Markdown 文本切分为多个逻辑块。

    参数:
        markdown_text (str): 原始 Markdown 全文。
        source_file  (str): 来源文件名，用于生成切片 ID 的前缀。

    返回:
        List[dict]: 每个元素包含:
            - chunk_id   (str) : 切片唯一标识，格式 "文件名#标题文本"
            - title      (str) : 该切片的一级标题（若无则为 "文档前言"）
            - content    (str) : 切片完整文本（含标题行）
            - start_line (int) : 切片在原文中的起始行号（1-based）
    """
    if not markdown_text.strip():
        logger.warning("输入文本为空，跳过切片")
        return []

    lines = markdown_text.split("\n")
    chunks: List[dict] = []

    # 第一步：找到所有一级标题的位置
    heading_positions: List[Tuple[int, str]] = []  # [(行号, 标题文本), ...]
    for idx, line in enumerate(lines):
        stripped = line.strip()
        # 仅匹配 "# xxx"，不匹配 "## xxx"、"### xxx" 等更深层级
        if re.match(r"^# [^#]", stripped):
            heading_positions.append((idx, stripped[2:].strip()))

    # 第二步：如果没有一级标题，整篇文档作为一个切片
    if not heading_positions:
        chunks.append({
            "chunk_id": f"{source_file}#文档前言",
            "title": "文档前言",
            "content": markdown_text.strip(),
            "start_line": 1,
        })
        return chunks

    # 第三步：处理第一个 "#" 之前的前言部分
    first_heading_line = heading_positions[0][0]
    if first_heading_line > 0:
        preamble = "\n".join(lines[:first_heading_line]).strip()
        if preamble:
            chunks.append({
                "chunk_id": f"{source_file}#文档前言",
                "title": "文档前言",
                "content": preamble,
                "start_line": 1,
            })

    # 第四步：以每个一级标题为起点，截取到下一个一级标题（或文档末尾）
    for i, (start_idx, heading_title) in enumerate(heading_positions):
        # 当前切片的起始行
        start_line = start_idx + 1  # 转为 1-based

        # 当前切片的结束行：下一个一级标题的前一行，或文档末尾
        if i + 1 < len(heading_positions):
            end_idx = heading_positions[i + 1][0]
        else:
            end_idx = len(lines)

        # 提取切片文本
        chunk_lines = lines[start_idx:end_idx]
        chunk_text = "\n".join(chunk_lines).strip()

        if not chunk_text:
            continue  # 跳过空切片

        # 构造切片 ID：文件名 + 标题
        safe_title = re.sub(r"[^\w一-鿿\-]+", "_", heading_title).strip("_")
        chunk_id = f"{source_file}#{safe_title}" if source_file else safe_title

        chunks.append({
            "chunk_id": chunk_id,
            "title": heading_title,
            "content": chunk_text,
            "start_line": start_line,
        })

    logger.info("文件 [%s] 切片完成，共 %d 个切片", source_file or "未知", len(chunks))
    return chunks


