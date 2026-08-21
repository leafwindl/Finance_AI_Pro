#!/usr/bin/env python3
"""
neo4j_extract.py — 新知识图谱实体关系抽取

跳过 rag_service 内部管线，直接：
  1. 读 new_data_chunks_kb* 的 ES 分块
  2. 按 Document 合并文本
  3. 调用 DeepSeek LLM 抽取实体关系
  4. 写入 Neo4j newdata 数据库

用法:
  python neo4j_extract.py                  # 全量处理
  python neo4j_extract.py --limit 5        # 只处理前 5 个文档
  python neo4j_extract.py --dry-run        # 预览不动数据库
"""

import hashlib
import json
import os
import sys
import time
import urllib.request

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX_PREFIX = "new_data_chunks"
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")

DRY_RUN = "--dry-run" in sys.argv
LIMIT = None
for arg in sys.argv:
    if arg.startswith("--limit="):
        LIMIT = int(arg.split("=")[1])

EXTRACTION_PROMPT = """从以下文本中提取所有关键实体和它们之间的关系。

返回纯 JSON（不要 markdown 代码块）:
{{
  "entities": [
    {{"name": "实体名称", "type": "ENTITY_TYPE", "description": "详细描述"}}
  ],
  "relations": [
    {{"source": "源实体名称", "target": "目标实体名称", "description": "关系描述"}}
  ]
}}

文本:
{text}"""


def es_scroll(index: str):
    url = f"{ES_HOST}/{index}/_search?scroll=5m"
    body = json.dumps({"size": 200, "query": {"match_all": {}}, "_source": True}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

    all_hits = []
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    scroll_id = data["_scroll_id"]
    hits = data["hits"]["hits"]
    all_hits.extend(hits)

    while hits:
        url2 = f"{ES_HOST}/_search/scroll"
        body2 = json.dumps({"scroll": "5m", "scroll_id": scroll_id}).encode()
        req2 = urllib.request.Request(url2, data=body2, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req2, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        scroll_id = data.get("_scroll_id", scroll_id)
        hits = data["hits"]["hits"]
        all_hits.extend(hits)

    return all_hits


def call_llm(text: str):
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=180.0)
    t0 = time.time()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}],
        temperature=0.1,
    )
    elapsed_ms = int((time.time() - t0) * 1000)

    content = response.choices[0].message.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    data = json.loads(content)
    return data, elapsed_ms, response.model


def _do_update(tx, chunk_id, source_record_id, entities, relations):
    tx.run("""
        MATCH (c:__Chunk__ {id: $id})-[r:HAS_ENTITY]->(:__Entity__)
        DELETE r
    """, id=chunk_id)

    for i, ent in enumerate(entities):
        name = ent['name'].strip()
        etype = ent['type'].strip().upper()
        description = ent.get('description', '').strip()
        entity_id = hashlib.md5(f"{name}:{etype}".encode('utf-8')).hexdigest()

        tx.run("""
            MERGE (e:__Entity__ {name: $name})
            ON CREATE SET e.id=$entity_id, e.type=$type, e.description=$description,
                e.human_readable_id=$hid, e.text_unit_ids=[$chunk_id],
                e.source_record_id=$source_record_id
            ON MATCH SET e.description=CASE
                WHEN e.description IS NULL OR size(e.description)<size($description)
                THEN $description ELSE e.description END,
                e.text_unit_ids=CASE
                WHEN $chunk_id IN e.text_unit_ids THEN e.text_unit_ids
                ELSE e.text_unit_ids+$chunk_id END,
                e.type=CASE WHEN e.type IS NULL THEN $type ELSE e.type END,
                e.source_record_id=CASE
                WHEN e.source_record_id IS NULL THEN $source_record_id
                WHEN $source_record_id IN split(coalesce(e.source_record_id,''),',')
                THEN e.source_record_id
                ELSE e.source_record_id+','+$source_record_id END
        """, name=name, type=etype, entity_id=entity_id, description=description,
            hid=str(i), chunk_id=chunk_id, source_record_id=source_record_id)

    if entities:
        tx.run("""
            MATCH (c:__Chunk__ {id: $id})
            MATCH (e:__Entity__) WHERE e.name IN $names
            MERGE (c)-[:HAS_ENTITY]->(e)
        """, id=chunk_id, names=[e['name'] for e in entities])

    for j, rel in enumerate(relations):
        source = rel['source'].strip()
        target = rel['target'].strip()
        if source == target:
            continue
        desc = rel.get('description', '').strip()
        rel_id = hashlib.md5(f"{source}->{target}:{j}".encode('utf-8')).hexdigest()

        tx.run("""
            MATCH (e1:__Entity__ {name: $s}), (e2:__Entity__ {name: $t})
            MERGE (e1)-[r:RELATED]->(e2)
            ON CREATE SET r.id=$rid, r.description=$desc, r.human_readable_id=$hid,
                r.text_unit_ids=[$chunk_id], r.weight=1.0, r.rank=$rank,
                r.source_record_id=$source_record_id
            ON MATCH SET r.description=CASE
                WHEN r.description IS NULL OR size(r.description)<size($desc)
                THEN $desc ELSE r.description END,
                r.weight=coalesce(r.weight,1.0)+0.5,
                r.source_record_id=CASE
                WHEN r.source_record_id IS NULL THEN $source_record_id
                WHEN $source_record_id IN split(coalesce(r.source_record_id,''),',')
                THEN r.source_record_id
                ELSE r.source_record_id+','+$source_record_id END
        """, s=source, t=target, rid=rel_id, desc=desc, hid=str(j),
            chunk_id=chunk_id, rank=100+j, source_record_id=source_record_id)


def main():
    # ---- 发现新数据 ES 索引 ----
    url = f"{ES_HOST}/_cat/indices/{ES_INDEX_PREFIX}*?format=json&h=index"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        all_indices = json.loads(resp.read().decode())
    indices = [i["index"] for i in all_indices if i["index"].startswith(ES_INDEX_PREFIX)]
    print(f"ES indices: {indices}")

    # ---- 读取所有 chunks ----
    all_chunks = []
    for idx_name in indices:
        hits = es_scroll(idx_name)
        for hit in hits:
            src = hit["_source"]
            all_chunks.append({
                "es_index": idx_name,
                "doc_hash": src.get("doc_hash", ""),
                "chunk_index": src.get("chunk_index", 0),
                "heading": src.get("heading", ""),
                "content": src.get("content", ""),
                "title": src.get("title", ""),
                "source_file": src.get("source_file", ""),
                "record_id": src.get("meta_fields", {}).get("record_id", ""),
            })
        print(f"  {idx_name}: {len(hits)} chunks")

    # ---- 按文档分组，合并文本 ----
    docs = {}
    for c in all_chunks:
        dh = c["doc_hash"]
        if dh not in docs:
            docs[dh] = {"doc_hash": dh, "title": c["title"],
                        "record_id": c["record_id"], "chunks": []}
        docs[dh]["chunks"].append(c)

    for doc in docs.values():
        doc["chunks"].sort(key=lambda x: x["chunk_index"])
        doc["merged_text"] = "\n\n".join(c["content"] for c in doc["chunks"])

    doc_list = list(docs.values())
    if LIMIT:
        doc_list = doc_list[:LIMIT]

    print(f"\nDocuments: {len(doc_list)} (total: {len(docs)})")
    print(f"LLM: {LLM_MODEL}")
    print(f"Neo4j: {NEO4J_DATABASE}")

    if DRY_RUN:
        print("\n[DRY-RUN] 预览前 3 个文档:")
        for doc in doc_list[:3]:
            print(f"\n  {doc['title'][:60]}")
            print(f"  record_id: {doc['record_id']}")
            print(f"  chunks: {len(doc['chunks'])}")
            print(f"  text length: {len(doc['merged_text'])} chars")
        return

    # ---- LLM 抽取 + Neo4j 写入 ----
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    total_e, total_r = 0, 0
    for i, doc in enumerate(doc_list):
        record_id = doc["record_id"]
        title = doc["title"]
        text = doc["merged_text"]

        # chunk_id = md5(doc_hash + chunk_index) — matches neo4j_index.py
        first_chunk_id = hashlib.md5(
            f"{doc['doc_hash']}_0".encode()
        ).hexdigest()

        print(f"\n[{i+1}/{len(doc_list)}] {title[:60]}")
        print(f"  record_id: {record_id}")

        # LLM
        try:
            data, llm_ms, model = call_llm(text)
            entities = data.get("entities", [])
            relations = data.get("relations", [])
            print(f"  LLM: {llm_ms}ms, {len(entities)} entities, {len(relations)} relations")
        except Exception as e:
            print(f"  LLM ERROR: {e}")
            continue

        # Neo4j — link all chunks to extracted entities
        try:
            entity_names = [e['name'] for e in entities]
            with driver.session(database=NEO4J_DATABASE) as session:
                # 用第一个 chunk 创建 Entity + RELATED
                first_chunk_id = hashlib.md5(
                    f"{doc['doc_hash']}_0".encode()
                ).hexdigest()
                session.execute_write(
                    _do_update, first_chunk_id, record_id, entities, relations
                )

                # 其余每个 chunk 都建 HAS_ENTITY
                for ci in range(len(doc["chunks"])):
                    cid = hashlib.md5(
                        f"{doc['doc_hash']}_{ci}".encode()
                    ).hexdigest()
                    if cid == first_chunk_id:
                        continue  # already done
                    if entity_names:
                        session.run("""
                            MATCH (c:__Chunk__ {id: $id})
                            MATCH (e:__Entity__) WHERE e.name IN $names
                            MERGE (c)-[:HAS_ENTITY]->(e)
                        """, id=cid, names=entity_names)

            total_e += len(entities)
            total_r += len(relations)
            print(f"  Neo4j: OK (+{len(entities)}e, +{len(relations)}r, {len(doc['chunks'])} chunks linked)")
        except Exception as e:
            print(f"  Neo4j ERROR: {e}")

    driver.close()
    print(f"\nDone: {total_e} entities, {total_r} relations")


if __name__ == "__main__":
    main()
