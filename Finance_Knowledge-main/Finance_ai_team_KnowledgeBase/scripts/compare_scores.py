#!/usr/bin/env python3
"""演示：同一查询下，BM25 分 vs ES 向量分 vs 模型余弦相似度 三者对比。"""

import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("EMBEDDING_MODEL", str(PROJECT_ROOT / "models/bge-large-zh-v1.5"))

from elasticsearch import Elasticsearch
from searcher.utils import text_to_vector

API = "http://127.0.0.1:8002/api/v1/search"
ES_INDEX = "knowledge_chunks_kb04,knowledge_chunks_kb01,knowledge_chunks_kb05,knowledge_chunks_kb06,knowledge_chunks_kb02,knowledge_chunks_kb03"


def cosine(a, b):
    import numpy as np
    a, b = np.asarray(a, dtype="float32"), np.asarray(b, dtype="float32")
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "多次输错密码账户会怎样"
    print(f"查询：{query}\n")

    # 1) 管线返回的合并分（max(bm25, vector)）
    d = requests.post(API, json={"query": query, "top_k": 5, "expand_k": 3, "kb_codes": []}, timeout=120).json()
    merged = {h["metadata"]["chunk_id"]: h for h in d["results"]}

    # 2) 纯 ES 向量检索分（cosineSimilarity + 1.0，范围 0~2）
    qvec = text_to_vector(query).tolist()
    es = Elasticsearch(["http://localhost:9200"], request_timeout=30)
    vresp = es.search(
        index=ES_INDEX,
        query={"script_score": {"query": {"match_all": {}},
               "script": {"source": "cosineSimilarity(params.q,'embedding') + 1.0", "params": {"q": qvec}}}},
        size=5, _source=["chunk_id", "content", "kb_code"],
    )

    # 3) 模型余弦相似度（纯 0~1）
    seen = {}
    for h in merged.values():
        seen[h["metadata"]["chunk_id"]] = cosine(qvec, text_to_vector(h["content"][:300]).tolist())

    print(f"{'排序':<4}{'管线合并分':<12}{'ES向量分(0~2)':<14}{'模型余弦(0~1)':<14}  内容预览")
    print("-" * 90)
    for i, h in enumerate(vresp["hits"]["hits"], 1):
        src = h["_source"]
        cid = src["chunk_id"]
        esv = h["_score"]
        cos = seen.get(cid, 0)
        mscore = merged.get(cid, {}).get("score", 0)
        prev = src.get("content", "")[:36].replace("\n", " ")
        print(f"#{i:<3}{mscore:<12.3f}{esv:<14.3f}{cos:<14.3f}  {prev}")
    print("\n说明：管线合并分 = max(bm25, 向量分)，所以经常被 BM25 主导；后两列才是纯向量算的。")


if __name__ == "__main__":
    main()
