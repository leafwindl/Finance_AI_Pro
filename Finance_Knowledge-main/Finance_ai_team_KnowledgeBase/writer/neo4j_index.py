#!/usr/bin/env python3
"""
neo4j_index.py — ES chunks → Neo4j 基础节点导入

从 ES 读取所有 new_data_chunks 分块，在 Neo4j 中创建：
  __Document__ 节点（按 doc_hash 去重）
  __Chunk__ 节点（每 chunk 一个）
  PART_OF 关系（Chunk → Document）

用法:
  python neo4j_index.py
  python neo4j_index.py --dry-run    # 预览不动数据库
"""

import hashlib
import json
import os
import sys
import urllib.request

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX_PREFIX = os.getenv("ES_INDEX", "knowledge_chunks")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

DRY_RUN = "--dry-run" in sys.argv


def es_scroll(index: str):
    """遍历 ES 索引所有文档"""
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


def chunk_id(doc_hash: str, index: int) -> str:
    return hashlib.md5(f"{doc_hash}_{index}".encode()).hexdigest()


def document_id(doc_hash: str) -> str:
    return doc_hash


def main():
    # ---- 发现索引 ----
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
                "es_id": hit["_id"],
                "doc_hash": src.get("doc_hash", ""),
                "chunk_index": src.get("chunk_index", 0),
                "heading": src.get("heading", ""),
                "text": src.get("text", ""),
                "content": src.get("content", ""),
                "title": src.get("title", ""),
                "source_file": src.get("source_file", ""),
            })
        print(f"  {idx_name}: {len(hits)} chunks")

    # ---- 按文档分组 ----
    docs = {}
    for c in all_chunks:
        dh = c["doc_hash"]
        if dh not in docs:
            docs[dh] = {
                "doc_hash": dh,
                "title": c["title"],
                "source_file": c["source_file"],
                "chunks": [],
            }
        docs[dh]["chunks"].append(c)

    print(f"\nDocuments: {len(docs)}, Chunks: {len(all_chunks)}")

    if DRY_RUN:
        print("[DRY-RUN] 不写入数据库，预览前 5 个文档:")
        for dh, doc in list(docs.items())[:5]:
            print(f"  {doc['title'][:50]}  ({len(doc['chunks'])} chunks)")
        return

    # ---- 写入 Neo4j ----
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    doc_count, chunk_count = 0, 0
    with driver.session(database=NEO4J_DATABASE) as session:
        for dh, doc in docs.items():
            did = document_id(dh)

            # CREATE __Document__
            session.run("""
                MERGE (d:__Document__ {id: $id})
                ON CREATE SET d.title = $title, d.raw_content = ''
            """, id=did, title=doc["title"])

            # CREATE chunks + PART_OF
            for c in doc["chunks"]:
                cid = chunk_id(dh, c["chunk_index"])
                n_tokens = len(c["text"]) // 2  # rough token count
                session.run("""
                    MERGE (ch:__Chunk__ {id: $id})
                    ON CREATE SET ch.n_tokens = $n_tokens, ch.text = $text
                    ON MATCH SET ch.text = CASE
                        WHEN ch.text IS NULL OR size(ch.text) < size($text)
                        THEN $text ELSE ch.text END
                """, id=cid, n_tokens=n_tokens, text=c["text"])

                session.run("""
                    MATCH (ch:__Chunk__ {id: $chunk_id})
                    MATCH (d:__Document__ {id: $doc_id})
                    MERGE (ch)-[:PART_OF]->(d)
                """, chunk_id=cid, doc_id=did)

                chunk_count += 1

            doc_count += 1
            if doc_count % 10 == 0:
                print(f"  {doc_count}/{len(docs)} documents...")

    driver.close()
    print(f"\nDone: {doc_count} documents, {chunk_count} chunks")


if __name__ == "__main__":
    main()
