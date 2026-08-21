#!/usr/bin/env python3
"""检查 top-k 排序是否正确 — check_topk.py

用法（项目根目录）：
    py scripts/check_topk.py "账号被锁定" "登录功能标准用例"
    py scripts/check_topk.py "账号被锁定" "登录功能标准用例" --top-k 10
    py scripts/check_topk.py "权限" "常见缺陷模式" --top-k 3
    py scripts/check_topk.py "端口池" "端口管理接口文档" --top-k 1,3,5,10

它做什么：
    检索后，看"你认为正确的文档"排在第几名，并给出判定：
        ✅ 第1名      = 完美
        ✅ 前3名      = 好
        ⚠️ 前10名     = 一般（排太靠后）
        ❌ 不在top-k  = 检索有问题（查询歧义 / 库里没这内容 / 索引没同步）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

API = "http://127.0.0.1:8002/api/v1/search"


def search(query: str, top_k: int) -> list[dict]:
    d = requests.post(
        API,
        json={"query": query, "top_k": top_k, "expand_k": 3, "kb_codes": []},
        timeout=120,
    ).json()
    return d["results"]


def find_rank(results: list[dict], answer: str) -> int | None:
    """在结果里找标题包含 answer 的那条，返回它的排名(1-based)，找不到返回 None。"""
    for i, h in enumerate(results, 1):
        title = h["metadata"].get("title", "")
        if answer and answer in title:
            return i
    return None


def verdict(rank: int | None, top_k: int) -> str:
    if rank is None:
        return "❌ 不在 top-k 内"
    if rank == 1:
        return "✅ 第1名，完美"
    if rank <= 3:
        return f"✅ 前3名（第{rank}名），好"
    if rank <= top_k:
        return f"⚠️ 前{top_k}名（第{rank}名），偏靠后，一般"
    return "❌ 不在 top-k 内"


def main() -> None:
    p = argparse.ArgumentParser(description="检查 top-k 排序是否正确")
    p.add_argument("query", help="查询词")
    p.add_argument("answer", help="你认为正确答案的文档标题（子串即可，如 登录功能标准用例）")
    p.add_argument("--top-k", default="1,3,5,10", help="逗号分隔，检查哪几个 k，默认 1,3,5,10")
    args = p.parse_args()

    topk_list = [int(x) for x in args.top_k.split(",") if x.strip()]
    print(f"查询：{args.query!r}\n正确答案应为文档：「{args.answer}」\n")

    for k in sorted(set(topk_list)):
        results = search(args.query, k)
        rank = find_rank(results, args.answer)
        print(f"  top-{k:<3} 实际返回{len(results):<3}  ->  {verdict(rank, k)}")

        if rank is not None and rank <= k:
            h = results[rank - 1]
            print(f"         [第{rank}名] score={h['score']:.3f} {h['metadata'].get('kb_code')} :: {h['content'][:40]!r}")


if __name__ == "__main__":
    main()
