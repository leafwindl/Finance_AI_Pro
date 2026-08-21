#!/usr/bin/env python3
"""
txt_to_markdown.py — 将 TXT/文本文件按清洗+切块结果转为 Markdown

复用网页 V1 入库同一套逻辑（Finance_AI_FASTAPI/app/knowledge_gateway/）：
  文件 -> extraction.extract_text（编码识别 + 清洗）
       -> kb_ingest.chunk_document（标题/中文章节/编号切块 + 字数收敛）
       -> kb_ingest.chunks_to_markdown（heading 按层级转 #/##/###）

用法（在 Finance_AI_FASTAPI 目录下执行）：
  .venv\\Scripts\\python.exe scripts\\txt_to_markdown.py D:\\8.17update\\测试.txt
  .venv\\Scripts\\python.exe scripts\\txt_to_markdown.py input.txt --out output.md
  .venv\\Scripts\\python.exe scripts\\txt_to_markdown.py input.txt --show-chunks
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge_gateway.extraction import extract_text  # noqa: E402
from app.knowledge_gateway.kb_ingest import (  # noqa: E402
    chunk_document,
    chunk_to_markdown,
    chunks_to_markdown,
    split_document_by_level1,
    _split_by_heading,
)


def main() -> int:
    p = argparse.ArgumentParser(description="TXT -> 清洗 -> 切块 -> Markdown")
    p.add_argument("input", help="输入文件路径（.txt/.md 等）")
    p.add_argument("--out", "-o", help="输出单个 .md 文件路径；缺省打印到终端")
    p.add_argument("--split-dir", "-d", help="每个切块生成一个独立 .md 文件到该目录")
    p.add_argument("--by-h1", action="store_true", help="以一级标题为界切块（块内含二/三级标题）")
    p.add_argument("--max-chars", type=int, default=500, help="单块最大字符数（默认 500）")
    p.add_argument("--show-chunks", action="store_true", help="打印切块明细（heading/level/字数）")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"错误：文件不存在 {src}", file=sys.stderr)
        return 1

    text, _ = extract_text(str(src), src.suffix.lower(), 200_000)
    if not text.strip():
        print("错误：未提取到文本内容", file=sys.stderr)
        return 1

    raw_sections = _split_by_heading(text)
    if args.by_h1:
        chunks = split_document_by_level1(text, max_chars=args.max_chars)
    else:
        chunks = chunk_document(text, max_chars=args.max_chars)
    markdown = chunks_to_markdown(chunks)

    print(f"输入文件    : {src}")
    print(f"提取字符数  : {len(text)}")
    print(f"识别标题数  : {len(raw_sections)}")
    print(f"切块数      : {len(chunks)}")
    print("=" * 60)

    if args.show_chunks:
        for i, c in enumerate(chunks, 1):
            print(f"  [{i}] level={c.get('level', 0)} chars={len(c['content'])} "
                  f"heading={c['heading']!r}")

    if args.split_dir:
        out_dir = Path(args.split_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, ch in enumerate(chunks, 1):
            safe = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", ch["heading"]).strip("._ ") or f"chunk{i}"
            name = f"{i:03d}_{safe}.md"
            (out_dir / name).write_text(chunk_to_markdown(ch), encoding="utf-8")
        print(f"已生成 {len(chunks)} 个 Markdown 块 -> {out_dir}")
    elif args.out:
        out = Path(args.out)
        out.write_text(markdown, encoding="utf-8")
        print(f"已写入 Markdown : {out} ({len(markdown)} 字符)")
    else:
        print("--- 生成的 Markdown ---")
        print(markdown)

    if args.show_chunks:
        print("--- 切块明细 JSON ---")
        print(json.dumps(chunks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
