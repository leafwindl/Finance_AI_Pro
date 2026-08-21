#!/usr/bin/env python3
"""
kb_common.py — 知识库入库公共模块

供 kb_ingest.py / kb_ingest_batch.py / kb_ingest_server.py 共用的工具函数。
包括：文件读取、哈希计算、元数据提取、Markdown 清洗、文档分块等。

这个模块本身不依赖任何脚本特定的配置，所有配置由调用者传入。
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ===========================================================================
# 1. 基础工具
# ===========================================================================

def read_file(path: str) -> str:
    """读取文件，自动规范化换行符为 \\n。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def compute_sha256(text: str) -> str:
    """计算文本的 SHA256 哈希值。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# 2. 元数据提取
# ===========================================================================

def extract_meta(text: str) -> Dict:
    """从 # 标题和 ## 文档登记信息 表格中提取元数据。
    
    Returns:
        {"title": "文档标题", "meta_fields": {"字段1": "值1", ...}}
    """
    # 标题
    title = ""
    m = re.search(r"^#\s+(.*)", text, flags=re.MULTILINE)
    if m:
        title = m.group(1).strip()

    # 登记表格 → meta_fields
    meta_fields: Dict[str, str] = {}
    m = re.search(r"^##\s+文档登记信息.*?\n(.*?)(?=^##\s|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line.startswith("|") or not line.endswith("|"):
                continue
            if re.match(r"^\|[\s\-:]+\|", line):  # 跳过分隔行
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 2 or cols[0] in ("元数据字段", "字段"):
                continue
            key = re.sub(r"[（(].*", "", cols[0]).strip()
            val = re.sub(r"[（(].*", "", cols[1]).strip()
            if key:
                meta_fields[key] = val

    return {"title": title, "meta_fields": meta_fields}


def extract_meta_via_llm(text: str, api_key: str, base_url: str, model: str) -> Optional[Dict]:
    """用 LLM（如 DeepSeek）智能提取元数据（备选方案，适合非标准格式的文档）。
    
    Args:
        text: 文档内容
        api_key: LLM API Key
        base_url: LLM API Base URL
        model: LLM 模型名称
    
    Returns:
        {"title": "...", "meta_fields": {...}, "summary": "..."} 或 None
    """
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        print("  LLM 模式需要 openai 库，请执行：pip install openai")
        return None

    prompt = (
        "从以下 Markdown 文档提取元数据，返回纯 JSON（一行，不要 markdown 代码块）。\n"
        '格式：{"title":"...","meta_fields":{"kb_code":"KB03",...},"summary":"..."}\n'
        "规则：title 取第一个 # 标题；meta_fields 取登记表格全部字段，键值只留英文/数字部分；summary 用中文一句话概括。\n"
        "文档内容："
    )
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt + "\n\n" + text}],
            temperature=0.0, max_tokens=1024,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"  LLM 提取失败（回退正则）：{e}")
        return None


def get_file_info(path: str) -> Dict:
    """获取文件的基本信息（名称、大小、创建/修改时间）。"""
    stat = os.stat(path)
    return {
        "source_file": os.path.basename(path),
        "file_size_bytes": stat.st_size,
        "file_created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
        "file_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def build_metadata(text: str, file_path: str, use_llm: bool = False,
                   llm_api_key: str = "", llm_base_url: str = "", llm_model: str = "") -> Dict:
    """构建文档的元数据（包括文件信息、标题、字段等）。
    
    Args:
        text: 文档内容
        file_path: 文件路径
        use_llm: 是否使用 LLM 提取
        llm_api_key: LLM API Key（use_llm=True 时需要）
        llm_base_url: LLM API Base URL（use_llm=True 时需要）
        llm_model: LLM 模型名称（use_llm=True 时需要）
    
    Returns:
        包含 title、source_file、file_size_bytes、file_created、file_modified、
        meta_fields、summary、word_count、char_count 的字典
    """
    file_info = get_file_info(file_path)

    if use_llm:
        llm_result = extract_meta_via_llm(text, llm_api_key, llm_base_url, llm_model)
        if llm_result:
            return {
                "title": llm_result.get("title") or file_info["source_file"],
                **file_info,
                "meta_fields": llm_result.get("meta_fields", {}),
                "summary": llm_result.get("summary", ""),
                "word_count": len(text.split()),
                "char_count": len(text),
            }

    extracted = extract_meta(text)
    return {
        "title": extracted["title"] or file_info["source_file"],
        **file_info,
        "meta_fields": extracted["meta_fields"],
        "summary": "",
        "word_count": len(text.split()),
        "char_count": len(text),
    }


# ===========================================================================
# 3. 纯文本提取（Markdown 清洗）
# ===========================================================================

def strip_markdown(md: str) -> str:
    """去除 Markdown 语法标记，保留纯文本供 BM25 全文索引。
    
    处理项目：图片、链接、行内代码、加粗、斜体、删除线、标题、引用、列表、
    水平线、脚注、HTML 标签、表格。
    """
    text = md
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)   # 图片
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)     # 链接
    text = re.sub(r"`([^`]+)`", r"\1", text)                 # 行内代码
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)             # 加粗（非贪婪，兼容内含 * 的情况）
    text = re.sub(r"\*(.+?)\*", r"\1", text)                 # 斜体
    text = re.sub(r"~~(.+?)~~", r"\1", text)                 # 删除线
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # 标题标记
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)    # 引用
    text = re.sub(r"^(\s*)([-*+]|\d+\.)\s+", r"\1", text, flags=re.MULTILINE)  # 列表标记
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)  # 水平线
    text = re.sub(r"\[\^[^\]]+\]", "", text)                 # 脚注引用
    text = re.sub(r"<[^>]+>", "", text)                      # HTML
    # 表格：保留单元格内容
    lines = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.match(r"^[\s\-:]+$", c) for c in cells):
                continue
            lines.append(" ".join(c for c in cells if c))
        else:
            lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ===========================================================================
# 4. 分块（基础实现 + 智能分块）
# ===========================================================================

def _split_by_h2_impl(text: str) -> List[Dict]:
    """【内部函数】按 ## 二级标题切分文档的基础实现。
    
    避免在 split_by_h2() 和 split_chunks_smart() 之间产生循环调用。
    """
    title_match = re.search(r"^#\s+.*\n+", text, flags=re.MULTILINE)
    if not title_match:
        return [{
            "heading": "引言", "content": text, "text": strip_markdown(text),
            "char_start": 0, "char_end": len(text), "hash": compute_sha256(text),
        }]

    preamble_end = title_match.end()
    parts = re.split(r"(?=^##\s)", text[preamble_end:], flags=re.MULTILINE)
    chunks: List[Dict] = []
    cursor = preamble_end

    for raw_part in parts:
        part = raw_part.strip()
        if not part:
            cursor += len(raw_part)
            continue
        heading_line = part.split("\n")[0].removeprefix("## ").strip() if part.startswith("## ") else "引言"
        chunk_content = part
        chunks.append({
            "heading": heading_line,
            "content": chunk_content,
            "text": strip_markdown(chunk_content),
            "char_start": cursor,
            "char_end": cursor + len(raw_part),
            "hash": compute_sha256(chunk_content),
        })
        cursor += len(raw_part)

    return chunks


def split_by_h2(text: str) -> List[Dict]:
    """按 ## 二级标题切分文档，返回每块的 heading/content/text/hash/偏移量。
    
    【改进版】现已集成智能分块算法（支持大小限制和边界感知），
    对调用方完全透明，保持向后兼容。
    
    如需精细控制分块参数，请直接调用 split_chunks_smart()。
    
    Returns:
        [
            {
                "heading": "小节标题",
                "content": "原始内容",
                "text": "纯文本内容",
                "char_start": 起始位置,
                "char_end": 结束位置,
                "hash": "SHA256 哈希"
            },
            ...
        ]
    """
    # 使用智能分块算法（保持向后兼容）
    return split_chunks_smart(text, min_chunk_size=100, max_chunk_size=2000)


def split_txt_paragraphs(text: str) -> List[Dict]:
    """按空行切分 TXT：每个连续非空段落独立成为一个 chunk。

    TXT 没有可靠的 H2/H3 结构，因此不使用 Markdown 的大小合并策略，
    也不丢弃短段落，确保段落正文可以完整落盘和追溯。
    """
    if not text or not text.strip():
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: List[Dict] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", normalized, flags=re.DOTALL):
        content = match.group(0).strip()
        if not content:
            continue
        start = match.start() + (len(match.group(0)) - len(match.group(0).lstrip()))
        end = start + len(content)
        chunks.append({
            "heading": "TXT 段落",
            "content": content,
            "text": strip_markdown(content),
            "char_start": start,
            "char_end": end,
            "hash": compute_sha256(content),
        })
    return chunks


def split_chunks_smart(
    text: str,
    min_chunk_size: int = 100,
    max_chunk_size: int = 2000,
    prefer_h2_boundary: bool = True,
) -> List[Dict]:
    """智能分块算法 v1：支持大小限制和边界感知的分割。
    
    分块策略：
    1. 首先按 H2 标题分块（尊重文档结构）
    2. 对超大块（> max_chunk_size）按 H3 或段落进一步细分
    3. 对超小块（< min_chunk_size）尝试与相邻块合并
    4. 检测块的完整性（跳过只有标题没内容的块）
    5. 优先在段落边界（空行）切分，避免在中间断句
    
    Args:
        text: 文档内容
        min_chunk_size: 最小块大小（字符数）
        max_chunk_size: 最大块大小（字符数）
        prefer_h2_boundary: 是否优先保留 H2 边界（True 时尽量按 H2 切，H3 只在必要时才用）
    
    Returns:
        List of chunk dicts with: heading, content, text, char_start, char_end, hash, size_info
    """
    if not text.strip():
        return []
    
    # 第一步：按 H2 标题初始分块（使用内部实现避免循环）
    h2_chunks = _split_by_h2_impl(text)
    
    # 第二步：处理超大和超小块
    result_chunks = []
    
    for i, h2_chunk in enumerate(h2_chunks):
        content = h2_chunk["content"]
        content_len = len(content)
        
        # 跳过过小的块（只有标题或极其简短）
        if content_len < 20:
            continue
        
        # 如果块大小合理，直接添加
        if min_chunk_size <= content_len <= max_chunk_size:
            result_chunks.append(h2_chunk)
            continue
        
        # 超大块需要细分
        if content_len > max_chunk_size:
            # 尝试按 H3 再分割
            sub_chunks = _split_large_chunk_by_h3(content, h2_chunk["heading"], min_chunk_size, max_chunk_size)
            if len(sub_chunks) > 1:
                # H3 分割成功，添加所有子块
                for sub_chunk in sub_chunks:
                    sub_chunk["char_start"] = h2_chunk["char_start"] + sub_chunk.get("_offset", 0)
                    sub_chunk["char_end"] = sub_chunk["char_start"] + len(sub_chunk["content"])
                    if "_offset" in sub_chunk:
                        del sub_chunk["_offset"]
                    result_chunks.append(sub_chunk)
            else:
                # H3 分割失败或无 H3，则按段落分割
                para_chunks = _split_by_paragraphs(
                    content, h2_chunk["heading"], min_chunk_size, max_chunk_size
                )
                for para_chunk in para_chunks:
                    para_chunk["char_start"] = h2_chunk["char_start"] + para_chunk.get("_offset", 0)
                    para_chunk["char_end"] = para_chunk["char_start"] + len(para_chunk["content"])
                    if "_offset" in para_chunk:
                        del para_chunk["_offset"]
                    result_chunks.append(para_chunk)
            continue
        
        # 超小块无法独立存在，标记但保留（后续可选合并）
        # 暂不做处理，保留原样
        result_chunks.append(h2_chunk)
    
    # 第三步：尝试合并相邻的超小块
    merged_chunks = _merge_small_chunks(result_chunks, min_chunk_size)
    
    return merged_chunks


def _split_large_chunk_by_h3(
    content: str,
    parent_heading: str,
    min_size: int,
    max_size: int,
) -> List[Dict]:
    """将超大块按 H3 标题进一步分割。
    
    Returns:
        分割后的块列表，若无 H3 或分割失败则返回空列表
    """
    # 寻找 H3 标题
    h3_pattern = r"(?=^###\s)"
    if not re.search(h3_pattern, content, flags=re.MULTILINE):
        return []  # 无 H3，返回空
    
    # 按 H3 分割
    h3_parts = re.split(h3_pattern, content, flags=re.MULTILINE)
    chunks = []
    offset = 0
    
    for i, part in enumerate(h3_parts):
        if not part.strip():
            offset += len(part)
            continue
        
        # 提取 H3 标题
        h3_match = re.match(r"^###\s+(.+?)$", part, flags=re.MULTILINE)
        h3_title = h3_match.group(1).strip() if h3_match else ""
        heading = f"{parent_heading} > {h3_title}" if h3_title else parent_heading
        
        # 检查子块大小
        if len(part) < 20:  # 过小，跳过
            offset += len(part)
            continue
        
        chunks.append({
            "heading": heading,
            "content": part,
            "text": strip_markdown(part),
            "hash": compute_sha256(part),
            "_offset": offset,
        })
        offset += len(part)
    
    return chunks


def _split_by_paragraphs(
    content: str,
    parent_heading: str,
    min_size: int,
    max_size: int,
) -> List[Dict]:
    """按段落（双换行）分割超大块。
    
    策略：
    1. 按双换行分割段落
    2. 在保持块大小合理的情况下，尽量合并相邻段落
    3. 单个段落超过 max_size 时，按句子进一步分割
    """
    # 按双换行分割段落
    paragraphs = re.split(r"\n\n+", content.strip())
    
    chunks = []
    current_chunk_content = ""
    offset = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            offset += len(para) + 2  # 包括分隔符
            continue
        
        # 单个段落过小，跳过
        if len(para) < 20:
            offset += len(para) + 2
            continue
        
        # 单个段落超大，按句子分割
        if len(para) > max_size:
            # 先保存当前块
            if current_chunk_content.strip():
                chunks.append({
                    "heading": parent_heading,
                    "content": current_chunk_content.strip(),
                    "text": strip_markdown(current_chunk_content),
                    "hash": compute_sha256(current_chunk_content),
                    "_offset": offset - len(current_chunk_content),
                })
            
            # 对大段落按句子分割
            sentences = re.split(r"(?<=[。！？；])\s+", para)
            sentence_chunk = ""
            for sent in sentences:
                if len(sentence_chunk) + len(sent) < max_size:
                    sentence_chunk += sent + " "
                else:
                    if sentence_chunk.strip():
                        chunks.append({
                            "heading": parent_heading,
                            "content": sentence_chunk.strip(),
                            "text": strip_markdown(sentence_chunk),
                            "hash": compute_sha256(sentence_chunk),
                            "_offset": offset,
                        })
                        offset += len(sentence_chunk)
                    sentence_chunk = sent + " "
            
            if sentence_chunk.strip():
                chunks.append({
                    "heading": parent_heading,
                    "content": sentence_chunk.strip(),
                    "text": strip_markdown(sentence_chunk),
                    "hash": compute_sha256(sentence_chunk),
                    "_offset": offset,
                })
                offset += len(sentence_chunk)
            
            current_chunk_content = ""
            offset += 2  # 段落分隔符
            continue
        
        # 尝试合并段落到当前块
        combined = current_chunk_content + "\n\n" + para if current_chunk_content else para
        if len(combined) <= max_size:
            current_chunk_content = combined
        else:
            # 当前块已满，保存并开始新块
            if current_chunk_content.strip():
                chunks.append({
                    "heading": parent_heading,
                    "content": current_chunk_content.strip(),
                    "text": strip_markdown(current_chunk_content),
                    "hash": compute_sha256(current_chunk_content),
                    "_offset": offset - len(current_chunk_content),
                })
            current_chunk_content = para
        
        offset += len(para) + 2
    
    # 保存最后一个块
    if current_chunk_content.strip():
        chunks.append({
            "heading": parent_heading,
            "content": current_chunk_content.strip(),
            "text": strip_markdown(current_chunk_content),
            "hash": compute_sha256(current_chunk_content),
            "_offset": offset - len(current_chunk_content),
        })
    
    return chunks if chunks else []


def _merge_small_chunks(chunks: List[Dict], min_size: int) -> List[Dict]:
    """合并相邻的超小块。
    
    策略：
    - 如果块 < min_size，尝试与下一个块合并
    - 如果合并后仍 < min_size，继续合并下一个
    """
    if not chunks:
        return []
    
    merged = []
    i = 0
    
    while i < len(chunks):
        current = chunks[i].copy()
        
        # 如果当前块过小，尝试合并
        if len(current["content"]) < min_size and i + 1 < len(chunks):
            j = i + 1
            combined_content = current["content"]
            
            # 尽量合并多个小块
            while j < len(chunks) and len(combined_content) < min_size:
                next_chunk = chunks[j]
                combined_content += "\n\n" + next_chunk["content"]
                j += 1
            
            # 生成合并后的块
            current["content"] = combined_content.strip()
            current["text"] = strip_markdown(combined_content)
            current["hash"] = compute_sha256(combined_content)
            current["char_end"] = current["char_start"] + len(combined_content)
            
            i = j
        else:
            i += 1
        
        merged.append(current)
    
    return merged
