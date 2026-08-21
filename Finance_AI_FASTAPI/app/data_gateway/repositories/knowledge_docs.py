from __future__ import annotations

from typing import Any

import asyncpg

# 知识库编号 → 名称（与 Finance_Knowledge-main 目录 / 契约一致）
KB_NAMES: dict[str, str] = {
    "KB01": "系统业务知识库",
    "KB02": "法规与合规规则库",
    "KB03": "历史需求与评审案例库",
    "KB04": "标准测试用例库",
    "KB05": "历史缺陷与测试经验库",
    "KB06": "测试规范与模板库",
}


def kb_name_for(kb_code: str) -> str:
    return KB_NAMES.get(kb_code, kb_code)


def _heading_key(text: str) -> str:
    """标题去重键：前 6 字符（如 KB01-01 编号前缀）相同即视为同一标题。"""
    stripped = text.strip()
    return stripped[:6] if len(stripped) >= 6 else stripped


async def list_kbs(kb_pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """返回有文档的知识库清单（编号、名称、文档数）。"""
    rows = await kb_pool.fetch(
        """
        SELECT kb_code, COUNT(DISTINCT doc_id) AS document_count
        FROM kb_documents
        GROUP BY kb_code
        ORDER BY kb_code
        """
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        kb_code = row["kb_code"]
        result.append(
            {
                "kb_code": kb_code,
                "kb_name": kb_name_for(kb_code),
                "document_count": row["document_count"],
            }
        )
    return result


async def list_documents_by_kb(
    kb_pool: asyncpg.Pool, kb_code: str
) -> dict[str, Any] | None:
    """返回某知识库下的文件列表；知识库不存在（无任何文档）时返回 None。"""
    rows = await kb_pool.fetch(
        """
        SELECT doc_id, MIN(title) AS title, MIN(source_file) AS source_file,
               COUNT(*) AS chunk_count, MAX(version) AS version
        FROM kb_documents
        WHERE kb_code = $1
        GROUP BY doc_id
        ORDER BY MIN(title)
        """,
        kb_code,
    )
    if not rows:
        return None
    documents = [
        {
            "doc_id": row["doc_id"],
            "title": row["title"],
            "source_file": row["source_file"],
            "chunk_count": row["chunk_count"],
            "version": row["version"],
        }
        for row in rows
    ]
    return {
        "kb_code": kb_code,
        "kb_name": kb_name_for(kb_code),
        "documents": documents,
    }


async def get_document_content(
    kb_pool: asyncpg.Pool, doc_id: str
) -> dict[str, Any] | None:
    """按 doc_id 聚合全部 chunk，还原为 markdown 内容；文档不存在时返回 None。"""
    meta = await kb_pool.fetchrow(
        """
        SELECT doc_id, MIN(title) AS title, MIN(source_file) AS source_file,
               MIN(kb_code) AS kb_code, MIN(version) AS version, COUNT(*) AS chunk_count
        FROM kb_documents
        WHERE doc_id = $1
        GROUP BY doc_id
        """,
        doc_id,
    )
    if meta is None:
        return None
    chunks = await kb_pool.fetch(
        """
        SELECT heading, content
        FROM kb_documents
        WHERE doc_id = $1
        ORDER BY chunk_id
        """,
        doc_id,
    )

    title = meta["title"] or doc_id
    title_key = _heading_key(title)
    parts = [f"# {title}"]
    for chunk in chunks:
        heading = (chunk["heading"] or "").strip()
        content = (chunk["content"] or "").strip()
        # 跳过与文档标题重复的标题（如源文档首行一级标题与文件名仅编号一致）
        if heading and _heading_key(heading) != title_key:
            parts.append(f"## {heading}")
        if content:
            parts.append(content)
    content_markdown = "\n\n".join(parts)

    return {
        "doc_id": doc_id,
        "title": title,
        "source_file": meta["source_file"],
        "kb_code": meta["kb_code"],
        "content_markdown": content_markdown,
        "chunk_count": meta["chunk_count"],
        "chars": len(content_markdown),
    }