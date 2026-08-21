from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

_driver: AsyncDriver | None = None
_driver_lock = asyncio.Lock()


async def get_driver() -> AsyncDriver:
    """返回全局 Neo4j 驱动，首次调用时惰性创建。

    惰性创建保证 Neo4j 未启动时 Gateway 依然可以正常启动；
    只有真正请求图谱接口时才尝试连接并向上层抛出连接异常。
    """
    global _driver
    if _driver is not None:
        return _driver
    async with _driver_lock:
        if _driver is not None:
            return _driver
        settings = get_settings()
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=settings.neo4j_connect_timeout_seconds,
        )
    return _driver


async def close_driver() -> None:
    """关闭全局驱动（应用关闭时调用）。"""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def fetch_graph(driver: AsyncDriver) -> dict[str, Any]:
    """读取完整的「知识库 → 文件」两级图谱，组装成前端 force-graph 数据。

    节点 id 统一使用 ``kb__<code>`` / ``doc__<doc_id>`` 前缀保证全局唯一。
    """
    settings = get_settings()
    db = settings.neo4j_database
    async with driver.session(database=db) as session:
        # 1) 每个知识库及文档数（OPTIONAL MATCH 保证 0 文档的库也出现在图里）
        kb_rows = await session.run(
            """
            MATCH (kb:KnowledgeBase)
            OPTIONAL MATCH (kb)-[:CONTAINS]->(d:Document)
            RETURN kb.kb_code AS kb_code, kb.kb_name AS kb_name, count(d) AS count
            ORDER BY kb.kb_code
            """
        )
        kbs = [record async for record in kb_rows]

        # 2) 每个文档及其所属知识库
        doc_rows = await session.run(
            """
            MATCH (kb:KnowledgeBase)-[:CONTAINS]->(d:Document)
            RETURN kb.kb_code AS kb_code,
                   d.doc_id AS doc_id, d.title AS title, d.source_file AS source_file
            ORDER BY kb.kb_code, d.title
            """
        )
        docs = [record async for record in doc_rows]

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    kb_names: dict[str, str] = {}

    for row in kbs:
        kb_code = row["kb_code"]
        kb_name = row["kb_name"] or kb_code
        kb_names[kb_code] = kb_name
        nodes.append(
            {
                "id": f"kb__{kb_code}",
                "type": "kb",
                "kb_code": kb_code,
                "label": kb_name,
                "count": row["count"],
            }
        )

    for row in docs:
        kb_code = row["kb_code"]
        doc_id = row["doc_id"]
        nodes.append(
            {
                "id": f"doc__{doc_id}",
                "type": "doc",
                "doc_id": doc_id,
                "kb_code": kb_code,
                "label": row["title"] or doc_id,
                "source_file": row["source_file"],
            }
        )
        links.append(
            {
                "source": f"kb__{kb_code}",
                "target": f"doc__{doc_id}",
                "type": "CONTAINS",
            }
        )

    return {
        "nodes": nodes,
        "links": links,
        "meta": {
            "total_nodes": len(nodes),
            "total_links": len(links),
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


async def fetch_document_subgraph(driver: AsyncDriver, doc_id: str) -> dict[str, Any] | None:
    """读取某文档的「分块 → 实体」子图，供前端点击文件时动态展开。

    节点 id 与全图保持一致：``doc__<doc_id>`` / ``chunk__<chunk_id>`` / ``entity__<name>``。
    文档不存在（无分块且无对应 Document 节点）时返回 None。
    """
    settings = get_settings()
    db = settings.neo4j_database
    async with driver.session(database=db) as session:
        kb_rows = await session.run(
            """
            MATCH (kb:KnowledgeBase)-[:CONTAINS]->(d:Document {doc_id: $doc_id})
            RETURN kb.kb_code AS kb_code, d.title AS title
            """,
            doc_id=doc_id,
        )
        kb_records = [record async for record in kb_rows]

        chunk_rows = await session.run(
            """
            MATCH (d:__Document__ {id: $doc_id})<-[:PART_OF]-(c:__Chunk__)
            RETURN c.id AS chunk_id, c.heading AS heading, c.text AS text,
                   c.n_tokens AS n_tokens
            ORDER BY c.id
            """,
            doc_id=doc_id,
        )
        chunks = [record async for record in chunk_rows]

        entity_rows = await session.run(
            """
            MATCH (d:__Document__ {id: $doc_id})<-[:PART_OF]-(c:__Chunk__)
                  -[:HAS_ENTITY]->(e:__Entity__)
            WITH c, collect(DISTINCT e)[..5] AS ents
            UNWIND ents AS e
            RETURN DISTINCT c.id AS chunk_id, e.name AS name, e.type AS type,
                   e.description AS description
            """,
            doc_id=doc_id,
        )
        entities = [record async for record in entity_rows]

        relation_rows = await session.run(
            """
            MATCH (d:__Document__ {id: $doc_id})<-[:PART_OF]-(c:__Chunk__)
                  -[:HAS_ENTITY]->(e:__Entity__)-[r:RELATED]->(e2:__Entity__)
            WITH e, e2, coalesce(r.weight, 1.0) AS w
            ORDER BY w DESC
            WITH e, collect(DISTINCT {t: e2.name, tt: e2.type, td: e2.description, w: w})[..3] AS targets
            UNWIND targets AS t
            RETURN e.name AS source, e.type AS source_type,
                   e.description AS source_description,
                   t.t AS target, t.tt AS target_type,
                   t.td AS target_description, t.w AS weight
            """,
            doc_id=doc_id,
        )
        relations = [record async for record in relation_rows]

    if not chunks and not kb_records:
        return None

    kb_code = kb_records[0]["kb_code"] if kb_records else None
    doc_title = kb_records[0]["title"] if kb_records else None

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    doc_node_id = f"doc__{doc_id}"

    for row in chunks:
        chunk_id = row["chunk_id"]
        nodes.append(
            {
                "id": f"chunk__{chunk_id}",
                "type": "chunk",
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "kb_code": kb_code,
                "label": row["heading"] or f"分块 {chunk_id[:6]}",
                "text": row["text"] or "",
                "n_tokens": row["n_tokens"] or 0,
            }
        )
        links.append(
            {"source": f"chunk__{chunk_id}", "target": doc_node_id, "type": "PART_OF"}
        )

    seen_entities: dict[str, dict[str, Any]] = {}
    entity_links: set[tuple[str, str]] = set()
    for row in entities:
        name = row["name"]
        chunk_id = row["chunk_id"]
        if name not in seen_entities:
            seen_entities[name] = {
                "id": f"entity__{name}",
                "type": "entity",
                "name": name,
                "entity_type": row["type"],
                "kb_code": kb_code,
                "doc_id": doc_id,
                "label": name,
                "description": row["description"] or "",
            }
        pair = (f"chunk__{chunk_id}", f"entity__{name}")
        if pair not in entity_links:
            entity_links.add(pair)
            links.append(
                {"source": pair[0], "target": pair[1], "type": "HAS_ENTITY"}
            )
    nodes.extend(seen_entities.values())

    for row in relations:
        source = row["source"]
        target = row["target"]
        # 边的两端都可能不在 chunk 的 top5 实体集合中：一并带入图，避免边悬空
        if source not in seen_entities:
            seen_entities[source] = {
                "id": f"entity__{source}",
                "type": "entity",
                "name": source,
                "entity_type": row["source_type"],
                "kb_code": kb_code,
                "doc_id": doc_id,
                "label": source,
                "description": row["source_description"] or "",
            }
        if target not in seen_entities:
            seen_entities[target] = {
                "id": f"entity__{target}",
                "type": "entity",
                "name": target,
                "entity_type": row["target_type"],
                "kb_code": kb_code,
                "doc_id": None,
                "label": target,
                "description": row["target_description"] or "",
            }
        pair = (f"entity__{source}", f"entity__{target}")
        if pair not in entity_links:
            entity_links.add(pair)
            links.append(
                {
                    "source": pair[0],
                    "target": pair[1],
                    "type": "RELATED",
                    "weight": row["weight"],
                }
            )

    node_ids = {n["id"] for n in nodes}
    nodes.extend(
        node for node in seen_entities.values() if node["id"] not in node_ids
    )

    return {
        "doc_id": doc_id,
        "title": doc_title,
        "kb_code": kb_code,
        "nodes": nodes,
        "links": links,
        "meta": {
            "total_nodes": len(nodes),
            "total_links": len(links),
        },
    }