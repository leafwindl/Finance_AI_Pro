#!/usr/bin/env python3
"""
neo4j_relink.py — 补全 chunk → Entity 的 HAS_ENTITY 关系

读取所有 Document 的 Entity 列表，为每个 chunk 建立 HAS_ENTITY 链接。
不调用 LLM，只补关系。

用法:
  python neo4j_relink.py
  python neo4j_relink.py --dry-run
"""

import hashlib
import json
import os
import sys
import urllib.request

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

DRY_RUN = "--dry-run" in sys.argv


def main():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:

        # 获取每个 Document 的 chunk 列表和 entity 列表
        r = session.run("""
            MATCH (d:__Document__)-[:PART_OF]-(c:__Chunk__)
            OPTIONAL MATCH (c)-[:HAS_ENTITY]->(e:__Entity__)
            RETURN d.id AS doc_id, d.title AS title,
                   collect(DISTINCT c.id) AS chunk_ids,
                   collect(DISTINCT e.name) AS entity_names
        """)

        docs = [(row['doc_id'], row['title'], row['chunk_ids'],
                 [n for n in row['entity_names'] if n]) for row in r]

        total_linked = 0
        total_chunks = 0

        for doc_id, title, chunk_ids, entity_names in docs:
            if not entity_names:
                print(f"  SKIP (0 entities): {title[:50]}")
                continue

            chunk_count = len(chunk_ids)
            total_chunks += chunk_count

            if DRY_RUN:
                print(f"  {title[:50]}: {chunk_count} chunks, {len(entity_names)} entities")
                continue

            # 为每个 chunk 建 HAS_ENTITY
            for cid in chunk_ids:
                result = session.run("""
                    MATCH (c:__Chunk__ {id: $id})
                    MATCH (e:__Entity__) WHERE e.name IN $names
                    MERGE (c)-[:HAS_ENTITY]->(e)
                    RETURN count(e) AS cnt
                """, id=cid, names=entity_names)
                linked = result.single()['cnt']
                total_linked += linked

            print(f"  {title[:50]}: {chunk_count} chunks x {len(entity_names)} entities")

        if not DRY_RUN:
            print(f"\nDone: {total_linked} HAS_ENTITY links across {total_chunks} chunks")
        else:
            print(f"\n[DRY-RUN] {len(docs)} docs, {total_chunks} chunks would be linked")

    driver.close()


if __name__ == "__main__":
    main()
