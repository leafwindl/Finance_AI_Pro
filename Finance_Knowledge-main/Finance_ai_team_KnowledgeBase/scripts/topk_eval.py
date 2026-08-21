#!/usr/bin/env python3
"""top-k 检索测试 + 查询词↔扩展关键词相似度评估脚本 — topk_eval.py

用途：
    1. top-k 测试：同一个 query 用不同 top_k 检索，对比返回条数与 score 分布。
    2. 相似度判断：把「你输入的 query」和「系统输出的扩展关键词 / 命中内容」
       各自向量化，算余弦相似度，量化"是否相关"。

用法（在项目根目录下运行）：
    python scripts/topk_eval.py "创业板买入权限校验"                     # 只跑 top_k=5,10,20
    python scripts/topk_eval.py "创业板买入权限校验" --top-k 1,3,5,10    # 自定义 top_k 列表
    python scripts/topk_eval.py "权限校验" --similarity                  # 额外计算 query↔关键词余弦相似度
    python scripts/topk_eval.py "权限校验" --expand-k 5 --similarity     # 更多扩展关键词
    python scripts/topk_eval.py "权限校验" --api http://127.0.0.1:8002   # 指定 API 地址

相似度参考口径（text2vec / bge 中文模型，余弦 0~1）：
    >= 0.70  高度相关；  0.50~0.70  相关；  0.35~0.50  弱相关；  <0.35  基本无关。
    注意：这只是粗粒度经验值，实际可用你的正/负例对标校准。

说明：
    - 需要 requests：pip install requests
    - --similarity 需要加载本地微调向量模型 finetune-text2vec-base-chinese/merged
      （首次加载较慢，约几十秒）
    - 若 trace.expanded_keywords 为空，说明检索服务里 ENABLE_NEO4J=false，
      此时改用「query ↔ 各命中结果的 heading/content」看相似度。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

API_BASE = "http://127.0.0.1:8002"
SEARCH_URL = f"{API_BASE}/api/v1/search"


def call_search(query: str, top_k: int, expand_k: int, api: str) -> dict:
    """调用 /api/v1/search 稳定契约接口。"""
    resp = requests.post(
        f"{api}/api/v1/search",
        json={"query": query, "top_k": top_k, "expand_k": expand_k, "kb_codes": []},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


def cosine_sim(vec_a, vec_b) -> float:
    """余弦相似度。"""
    import numpy as np

    a, b = np.asarray(vec_a, dtype="float32"), np.asarray(vec_b, dtype="float32")
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def load_embedding() -> "callable":
    """延迟加载向量模型，返回 text_to_vector 函数。"""
    from searcher.utils import text_to_vector

    return text_to_vector


def print_topk_row(top_k: int, data: dict) -> None:
    """打印一次 top_k 检索的概要。"""
    results = data.get("results", [])
    trace = data.get("trace", {})
    scores = [r.get("score", 0) for r in results]
    best = max(scores) if scores else 0.0
    worst = min(scores) if scores else 0.0
    print(f"  top_k={top_k:<3} 实际返回={len(results):<3} "
          f"score 范围=[{worst:.3f} ~ {best:.3f}] "
          f"BM25命中={trace.get('bm25_count', '-')} 向量命中={trace.get('vector_count', '-')}")
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        print(f"    #{i:<2} score={r.get('score', 0):.4f}  "
              f"[{meta.get('kb_code', '')}] {meta.get('title', '')} :: "
              f"{r.get('content', '')[:40].replace(chr(10), ' ')}")


def main() -> None:
    p = argparse.ArgumentParser(description="top-k 测试 + 查询↔关键词相似度评估")
    p.add_argument("query", help="要检索的查询文本")
    p.add_argument("--top-k", default="5,10,20", help="逗号分隔的 top_k 列表，默认 5,10,20")
    p.add_argument("--expand-k", type=int, default=3, help="Neo4j 扩展关键词数量，默认 3")
    p.add_argument("--similarity", action="store_true", help="计算 query 与扩展关键词/命中的余弦相似度")
    p.add_argument("--api", default=API_BASE, help=f"检索 API 地址，默认 {API_BASE}")
    p.add_argument("--json", action="store_true", help="导出原始 JSON 到 topk_eval_result.json")
    args = p.parse_args()

    print("=" * 70)
    print(f"  检索测试 query = {args.query!r}")
    print("=" * 70)

    topk_values = [int(x.strip()) for x in args.top_k.split(",") if x.strip()]
    first = call_search(args.query, max(topk_values), args.expand_k, args.api)

    # ---------- 1) top-k 对比 ----------
    print("\n[1] top-k 结果对比")
    for tk in topk_values:
        data = first if tk == max(topk_values) else call_search(args.query, tk, args.expand_k, args.api)
        print_topk_row(tk, data)

    # ---------- 2) 相似度判断 ----------
    trace = first.get("trace", {})
    keywords = trace.get("expanded_keywords", []) or []
    print("\n[2] 扩展关键词（来自 Neo4j 图谱）: ", keywords if keywords else "（空 —— 服务端 ENABLE_NEO4J=false）")

    if args.similarity:
        print("\n[3] query ↔ 关键词/命中 余弦相似度（加载向量模型，请稍候...）")
        text_to_vector = load_embedding()
        qvec = text_to_vector(args.query)

        print("  --- query ↔ 扩展关键词 ---")
        if keywords:
            for kw in keywords:
                kv = text_to_vector(kw)
                print(f"    query={args.query!r}  vs  关键词={kw!r:>10}  相似度={cosine_sim(qvec, kv):.4f}")
        else:
            print("    无扩展关键词，跳过")

        print("  --- query ↔ 命中内容（前 5 条） ---")
        for i, r in enumerate(first.get("results", [])[:5], 1):
            content = (r.get("content", "") or "").strip()
            cv = text_to_vector(content[:300])
            print(f"    #{i:<2} score={r.get('score', 0):.4f}  "
                  f"query↔内容 相似度={cosine_sim(qvec, cv):.4f}  "
                  f"标题={r.get('metadata', {}).get('title', '')}")

        print("\n  参考：>=0.70 高度相关 | 0.50~0.70 相关 | 0.35~0.50 弱相关 | <0.35 无关")

    if args.json:
        with open(PROJECT_ROOT / "topk_eval_result.json", "w", encoding="utf-8") as f:
            json.dump({"query": args.query, "top_k": topk_values, "expand_k": args.expand_k,
                       "full_response": first}, f, ensure_ascii=False, indent=2)
        print(f"\n完整响应已导出 → topk_eval_result.json")


if __name__ == "__main__":
    main()
