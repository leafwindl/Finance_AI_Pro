"""聚合器。

按 KB 聚合分类后的 H2 块 → 库内排序 → H3 细切 chunk → 写入文件。
支持跨文件累积索引。
"""

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Union

from classifier.models import H2Block, ClassifyResult, Chunk, KBIndex

logger = logging.getLogger("knowledge_parser.orchestrate")

KB_NAMES = {
    "KB01": "系统业务知识库",
    "KB02": "法规与合规规则库",
    "KB03": "历史需求与评审案例库",
    "KB04": "标准测试用例库",
    "KB05": "历史缺陷与测试经验库",
    "KB06": "测试规范与模板库",
}


class Aggregator:
    """按 KB 聚合、排序、输出 chunk。支持跨文件累积。"""

    def __init__(
        self,
        output_dir: Union[str, Path] = "output/orchestrated",
        max_chunk_chars: int = 2000,
        min_chunk_chars: int = 100,
        write_review_copies: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.max_chunk_chars = max_chunk_chars
        self.min_chunk_chars = min_chunk_chars
        self.write_review_copies = write_review_copies
        self._global_counts: dict[str, int] = {}
        self._global_index: list[dict] = []
        self._total_review = 0
        self._total_chunks = 0
        self._processed_files: list[str] = []
        self._run_id = uuid.uuid4().hex[:8]

    def process_file(
        self,
        blocks: list[H2Block],
        results: list[ClassifyResult],
        source_file: str,
        markdown: str = "",
    ) -> list[Chunk]:
        """处理单个文件：建 chunk、按 KB 写文件（不写全局索引）。

        Args:
            blocks: 原始 H2 块列表
            results: LLM 分类结果
            source_file: 源文件名

        Returns:
            生成的 Chunk 列表
        """
        # 从 markdown 按 H2 提取各段内容（更完整，格式更好）
        h2_contents = _split_markdown_by_h2(markdown) if markdown else {}

        # 按 H3 切 chunk：H2 是分类单元，H3 是 chunk 单元
        chunks: list[Chunk] = []
        for block, result in zip(blocks, results):
            # 优先用 markdown 提取的完整内容
            full_content = h2_contents.get(block.h2_title, block.content_preview)
            if block.h3_children:
                for title, dom_content in zip(block.h3_children, block.h3_contents):
                    # H3 内容也优先用 markdown（从 H2 段中找对应 H3）
                    h3_content = dom_content or full_content
                    chunks.append(self._build_chunk(
                        block, result, source_file,
                        h3_title=title, h3_content=h3_content,
                    ))
            else:
                # 无 H3 → H2 整个作为 chunk
                chunks.append(self._build_chunk(
                    block, result, source_file, h3_content=full_content,
                ))

        # 按 KB 分组
        kb_groups: dict[str, list[Chunk]] = {}
        for c in chunks:
            kb_groups.setdefault(c.kb_id, []).append(c)

        for kb_id in sorted(kb_groups.keys()):
            group = kb_groups[kb_id]
            group.sort(key=self._sort_key)

            # 分配 chunk_id（全局递增）
            for c in group:
                self._global_counts.setdefault(c.kb_id, 0)
                self._global_counts[c.kb_id] += 1
                c.chunk_id = f"{c.kb_id}-{self._global_counts[c.kb_id]:03d}"

            # 写入 KB 目录（超长 chunk 自动拆分）
            kb_dir = self.output_dir / f"{kb_id}_{KB_NAMES.get(kb_id, kb_id)}"
            kb_dir.mkdir(parents=True, exist_ok=True)
            for c in group:
                for sub in self._split_large_chunk(c):
                    self._write_chunk(sub, kb_dir)

        # 处理 review 块
        for c in chunks:
            if c.needs_review and self.write_review_copies:
                self._total_review += 1
                review_dir = self.output_dir / "_review"
                review_dir.mkdir(parents=True, exist_ok=True)
                self._write_chunk(c, review_dir)

        # 累积索引
        for c in chunks:
            self._global_index.append({
                "chunk_id": c.chunk_id,
                "kb_id": c.kb_id,
                "source": c.source_file,
                "h2": c.source_h2,
                "confidence": c.confidence,
                "method": c.method,
                "needs_review": c.needs_review,
                "refs": c.refs,
            })

        self._total_chunks += len(chunks)
        self._processed_files.append(source_file)
        return chunks

    def finalize(self):
        """写入全局 index.json。在所有文件处理完成后调用。"""
        index = KBIndex(
            chunks=self._global_index,
            stats=self._global_counts,
            review_count=self._total_review,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            run_id=self._run_id,
            files_processed=self._processed_files,
        )
        index_file = self.output_dir / "index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            json.dumps(index.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "索引写入完成: %d chunks, %d KBs, %d review",
            self._total_chunks, len(self._global_counts), self._total_review,
        )

    def _build_chunk(
        self, block: H2Block, result: ClassifyResult, source_file: str,
        h3_title: str = "", h3_content: str = "",
    ) -> Chunk:
        """从 H2Block + ClassifyResult 构建 Chunk。"""
        return Chunk(
            kb_id=result.primary_kb,
            chunk_id="",  # process_file 中分配
            method=result.method,
            confidence=result.confidence,
            source_file=source_file,
            source_h1=block.h1,
            source_h2=block.h2_title,
            h3_title=h3_title,
            sub_category=result.sub_category,
            content=h3_content if h3_content else block.content_preview,
            refs={"secondary_kb": result.secondary_kb} if result.secondary_kb else {},
            needs_review=result.needs_review,
            legal_ref=result.legal_ref,
        )

    def _sort_key(self, chunk: Chunk) -> tuple:
        """库内排序键：文档编号 → 置信度降序。"""
        doc_id = ""
        m = re.search(r"(?:BIZ|REG|REQ|TC|DEF|STD)[-_]?GEM[-_]?\d+", chunk.source_h2)
        if not m:
            m = re.search(r"(?:BIZ|REG|REQ|TC|DEF|STD)[-_]?GEM[-_]?\d+", chunk.source_h1)
        if m:
            doc_id = m.group()
        nums = re.findall(r"\d+", doc_id)
        num = int(nums[0]) if nums else 0
        return (-chunk.confidence if chunk.method == "rule_fallback" else 0, num, doc_id)

    def _split_large_chunk(self, chunk: Chunk) -> list[Chunk]:
        """超长 chunk 按段落拆分。"""
        content = chunk.content
        if len(content) <= self.max_chunk_chars:
            return [chunk]

        # 按双换行（段落边界）拆分
        paragraphs = re.split(r"\n\n+", content)
        sub_chunks = []
        buffer = ""
        part = 0
        for para in paragraphs:
            if buffer and len(buffer) + len(para) > self.max_chunk_chars:
                sub_chunks.append(self._copy_chunk(chunk, buffer.strip(), part))
                buffer = para
                part += 1
            else:
                buffer += ("\n\n" if buffer else "") + para
        if buffer.strip():
            sub_chunks.append(self._copy_chunk(chunk, buffer.strip(), part))
        return sub_chunks or [chunk]

    def _copy_chunk(self, original: Chunk, content: str, part: int) -> Chunk:
        """复制 chunk 并替换内容。"""
        c = Chunk(
            kb_id=original.kb_id,
            chunk_id="",
            method=original.method,
            confidence=original.confidence,
            source_file=original.source_file,
            source_h1=original.source_h1,
            source_h2=original.source_h2,
            h3_title=f"{original.h3_title} (part {part+1})" if original.h3_title and part > 0 else original.h3_title,
            sub_category=original.sub_category,
            content=content,
            refs=original.refs,
            needs_review=original.needs_review,
            legal_ref=original.legal_ref,
        )
        return c

    def _write_chunk(self, chunk: Chunk, directory: Path):
        """写出单个 chunk 文件。"""
        filename = f"{chunk.chunk_id}.md"
        filepath = directory / filename

        lines = [
            "---",
            f"kb_id: {chunk.kb_id}",
            f"chunk_id: {chunk.chunk_id}",
            f"method: {chunk.method}",
            f"confidence: {chunk.confidence}",
            f"source_file: {chunk.source_file}",
            f"source_h1: {chunk.source_h1}",
            f"source_h2: {chunk.source_h2}",
        ]
        if chunk.h3_title:
            lines.append(f"source_h3: {chunk.h3_title}")
        if chunk.sub_category:
            lines.append(f"sub_category: {chunk.sub_category}")
        if chunk.legal_ref:
            lines.append(f"legal_ref: {chunk.legal_ref}")
        if chunk.refs:
            refs_str = json.dumps(chunk.refs, ensure_ascii=False)
            lines.append(f"refs: {refs_str}")
        lines.append(f"needs_review: {str(chunk.needs_review).lower()}")
        lines.append("---")
        lines.append("")
        lines.append(f"## {chunk.source_h2}")
        lines.append("")
        lines.append(chunk.content)

        filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _split_markdown_by_h2(markdown: str) -> dict[str, str]:
    """按 H2 标题将 markdown 拆分为 {h2_title: content} 字典。"""
    import re
    result = {}
    # 跳过 YAML frontmatter
    body = markdown
    if body.startswith("---"):
        end = body.find("---", 3)
        if end > 0:
            body = body[end + 3:]

    # 按 ## 分割
    parts = re.split(r"\n(?=## )", body.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 提取 H2 标题（第一行去掉 ## 前缀）
        lines = part.split("\n", 1)
        title = lines[0].lstrip("#").strip()
        content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        result[title] = content
    return result
