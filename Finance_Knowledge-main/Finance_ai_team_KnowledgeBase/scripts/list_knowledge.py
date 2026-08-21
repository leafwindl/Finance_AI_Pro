#!/usr/bin/env python3
"""浏览知识库内容 — list_knowledge.py

列出当前知识库里所有文档、各自的知识库编码、切片数，以及每个切片的标题和内容预览。

用法（项目根目录）：
    py scripts/list_knowledge.py              # 全部列出
    py scripts/list_knowledge.py --kb KB01    # 只看某个知识库
    py scripts/list_knowledge.py --detail     # 每个切片展开看内容
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    p = argparse.ArgumentParser(description="浏览知识库内容")
    p.add_argument("--kb", help="只看某个知识库，如 KB01")
    p.add_argument("--detail", action="store_true", help="展开每个切片的内容预览")
    args = p.parse_args()

    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"), port=int(os.getenv("PG_PORT", "5432")),
        dbname=os.getenv("PG_DBNAME", "knowledge_base"),
        user=os.getenv("PG_USER", "postgres"), password=os.getenv("PG_PASSWORD", ""),
    )
    cur = conn.cursor()

    sql = ("SELECT kb_code, title, source_file, chunk_id, heading, content, version "
           "FROM kb_documents")
    params = []
    if args.kb:
        sql += " WHERE kb_code = %s"
        params.append(args.kb)
    sql += " ORDER BY kb_code, doc_id, chunk_id"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("知识库是空的。先跑 scripts/rebuild_knowledge_base.py 导入。")
        return

    # 按文档分组统计
    docs: dict[tuple, dict] = {}
    for kb_code, title, source_file, chunk_id, heading, content, version in rows:
        key = (kb_code, title, source_file)
        docs.setdefault(key, {"chunks": []})["chunks"].append(
            (chunk_id, heading, content, version)
        )

    print(f"知识库共 {len(docs)} 篇文档 / {len(rows)} 个切片\n")
    for (kb_code, title, source_file), info in sorted(docs.items()):
        print(f"[{kb_code}] 《{title}》   ({len(info['chunks'])} 切片)  来源: {source_file}")
        if args.detail:
            for chunk_id, heading, content, version in info["chunks"]:
                preview = (content or "").replace("\n", " ")[:70]
                print(f"     - {heading!r}: {preview}...")
        print()


if __name__ == "__main__":
    main()
