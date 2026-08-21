#!/usr/bin/env python3
"""
Finance AI KnowledgeBase — 统一入口
=====================================
四阶段流水线：解析 → 分类 → 写入 → 检索

用法:
    # 全流程：文件 → 知识入库
    python main.py pipeline -f document.pdf

    # 分步执行
    python main.py parse -f document.pdf           # 步骤1: 解析文档
    python main.py classify                        # 步骤2: LLM分段+分类
    python main.py ingest --dir output/knowledge   # 步骤3: 写入PG+ES
    python main.py search "创业板买入权限"          # 步骤4: 检索知识

    # 启动服务
    python main.py serve parse --port 8001          # 解析服务
    python main.py serve classify --port 8002       # 分类服务
    python main.py serve ingest --port 8200         # 入库服务
    python main.py serve search --port 8002         # 检索服务
"""

import argparse
import sys
import os
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


def cmd_parse(args):
    """解析文档：多格式 → 纯文本。"""
    from parser.parsers import parse_file, supported_formats
    from shared.file_utils import ensure_output_dir, write_text_file

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"错误: 文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"解析: {input_path.name} ({input_path.suffix})")
    parsed = parse_file(input_path)

    output_dir = Path(args.output or "output/parsed")
    ensure_output_dir(output_dir)
    safe_ext = input_path.suffix.lstrip(".")
    output_path = output_dir / f"{input_path.stem}.{safe_ext}.txt"
    write_text_file(output_path, parsed.content, encoding="utf-8")
    print(f"完成 -> {output_path} ({len(parsed.content)} 字符)")


def cmd_classify(args):
    """LLM分段+分类：纯文本 → KB chunk。"""
    from classifier.segmenter import LLMSegmenter
    from classifier.aggregator import Aggregator
    import yaml

    # 加载配置
    config_path = Path(args.config or "config.yaml")
    config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    llm_cfg = config.get("extensions", {})
    api_key = llm_cfg.get("llm_api_key", "") or os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("错误: 未配置 LLM API Key（请在 config.yaml 或 .env 中设置）", file=sys.stderr)
        sys.exit(1)

    segmenter = LLMSegmenter(
        api_key=api_key,
        model=llm_cfg.get("llm_model", "deepseek-chat"),
        endpoint=llm_cfg.get("llm_endpoint", "https://api.deepseek.com/v1/chat/completions"),
    )

    parsed_dir = Path(args.parsed or "output/parsed")
    text_files = sorted(list(parsed_dir.glob("*.txt")) + list(parsed_dir.glob("*.md")))
    if not text_files:
        print(f"在 {parsed_dir} 中未找到文件，请先运行 parse", file=sys.stderr)
        sys.exit(1)

    knowledge_dir = Path(args.output or "output/knowledge")
    agg = Aggregator(output_dir=str(knowledge_dir))

    total_chunks = 0
    for i, fp in enumerate(text_files, 1):
        print(f"\n[{i}/{len(text_files)}] {fp.name}")
        text = fp.read_text(encoding="utf-8")
        if not text.strip():
            continue

        segments = segmenter.segment(text, source_name=fp.stem)
        valid = [s for s in segments if s.primary_kb]
        print(f"  提取 {len(valid)} 个知识点")

        if valid:
            from classifier.models import H2Block, ClassifyResult
            blocks, classifications = [], []
            for j, seg in enumerate(valid):
                blocks.append(H2Block(
                    index=j, h1=fp.name, h2_title=seg.title,
                    content_preview=seg.content[:300], source_file=fp.name,
                    h3_children=[seg.title], h3_contents=[seg.content],
                ))
                classifications.append(ClassifyResult(
                    index=j, primary_kb=seg.primary_kb,
                    sub_category=seg.sub_category,
                    secondary_kb=seg.secondary_kb,
                    confidence=seg.confidence, keywords=seg.keywords,
                    needs_review=seg.needs_review, method="llm",
                    legal_ref=seg.legal_ref,
                ))
            chunks = agg.process_file(blocks, classifications, fp.name, markdown=text)
            total_chunks += len(chunks)

    agg.finalize()
    print(f"\n完成: {total_chunks} chunks -> {knowledge_dir}/")


def cmd_txt_pipeline(args):
    """TXT：解析/清洗 → 段落 chunk → LLM 分类 → Markdown → 可选入库。"""
    writer_dir = str(PROJECT_ROOT / "writer")
    if writer_dir not in sys.path:
        sys.path.insert(0, writer_dir)
    from parser.parsers import parse_file
    from writer.kb_common import split_txt_paragraphs
    from classifier.segmenter import LLMSegmenter
    from classifier.aggregator import Aggregator
    from classifier.models import H2Block, ClassifyResult
    from writer.kb_ingest import build_output, write_to_postgres, write_to_elasticsearch
    import re

    input_path = Path(args.file)
    if input_path.suffix.lower() not in {".txt", ".text"}:
        raise ValueError("txt-pipeline 只接受 .txt 或 .text 文件")
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    parsed = parse_file(input_path)
    chunks = split_txt_paragraphs(parsed.content)
    if not chunks:
        raise ValueError("清洗后没有可处理的 TXT 段落")

    config = {}
    config_path = Path(args.config)
    if config_path.exists():
        import yaml
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    llm_cfg = config.get("extensions", {})
    api_key = "" if args.no_llm else (llm_cfg.get("llm_api_key", "") or os.getenv("LLM_API_KEY", "")
                                      or os.getenv("DEEPSEEK_API_KEY", ""))
    segmenter = LLMSegmenter(
        api_key=api_key,
        model=llm_cfg.get("llm_model", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
        endpoint=llm_cfg.get("llm_endpoint", os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions")),
    )

    output_dir = Path(args.output)
    aggregator = Aggregator(
        output_dir=output_dir, max_chunk_chars=10**9, min_chunk_chars=0,
        write_review_copies=False,
    )
    blocks, results = [], []
    for index, chunk in enumerate(chunks):
        title = f"TXT段落-{index + 1:04d}"
        classified = segmenter.classify_chunk(chunk["content"], f"{input_path.name}#{index + 1}")
        blocks.append(H2Block(
            index=index, h1=input_path.name, h2_title=title,
            content_preview=chunk["content"][:300], source_file=input_path.name,
            h3_children=[title], h3_contents=[chunk["content"]],
        ))
        results.append(ClassifyResult(
            index=index, primary_kb=classified.primary_kb or "KB01",
            sub_category=classified.sub_category, secondary_kb=classified.secondary_kb,
            confidence=classified.confidence, keywords=classified.keywords,
            needs_review=classified.needs_review, method="llm" if api_key else "rule_fallback",
            legal_ref=classified.legal_ref,
        ))

    aggregator.process_file(blocks, results, input_path.name,
                            markdown="\n\n".join(
                                f"## TXT段落-{i + 1:04d}\n\n{c['content']}"
                                for i, c in enumerate(chunks)))
    aggregator.finalize()

    md_files = sorted(output_dir.glob("**/*.md"))
    embedding_model = "" if args.no_embedding else (args.embedding_model or os.getenv("EMBEDDING_MODEL", ""))
    embedded = 0
    for fp in md_files:
        try:
            data = build_output(str(fp), embedding_model=embedding_model or None, use_llm=False)
        except (OSError, ImportError) as exc:
            if args.write_pg or args.write_es:
                raise RuntimeError(f"Embedding 模型加载失败，已阻止入库: {exc}") from exc
            print(f"Embedding 跳过（模型不可用）: {exc}")
            data = build_output(str(fp), embedding_model=None, use_llm=False)
        if data["chunks"] and "vector" in data["chunks"][0]:
            embedded += len(data["chunks"])
        if args.write_pg:
            kb_match = re.search(r"KB\d+", fp.parent.name)
            schema = f"{kb_match.group()}_{fp.parent.name}" if kb_match else "public"
            write_to_postgres(data, schema=schema, **_txt_pg_config())
        if args.write_es:
            kb_match = re.search(r"KB\d+", fp.parent.name)
            index_name = f"{os.getenv('ES_INDEX', 'knowledge_chunks')}_{kb_match.group().lower()}" if kb_match else os.getenv("ES_INDEX", "knowledge_chunks")
            write_to_elasticsearch(data, os.getenv("ES_HOST", "http://localhost:9200"),
                                   index_name, os.getenv("ES_USER", ""), os.getenv("ES_PASSWORD", ""))

    print(f"TXT 完成: 清洗后 {len(parsed.content)} 字符，{len(chunks)} 段落，{len(md_files)} 个 Markdown 文件")
    print(f"Embedding: {embedded}/{len(md_files)} 个 chunk 已生成")
    print(f"输出目录: {output_dir}")
    print(f"数据库写入: PG={'是' if args.write_pg else '否'}，ES={'是' if args.write_es else '否'}")


def _txt_pg_config():
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": os.getenv("PG_DBNAME", "knowledge_base"),
        "user": os.getenv("PG_USER", ""),
        "password": os.getenv("PG_PASSWORD", ""),
    }


def cmd_ingest(args):
    """写入PG+ES：Markdown → 元数据+分块+向量 → 双写。"""
    from writer.kb_ingest import build_output, write_to_postgres, write_to_elasticsearch

    input_path = Path(args.file or args.dir)
    if not input_path.exists():
        print(f"错误: 路径不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    if input_path.is_dir():
        md_files = sorted(input_path.glob("**/*.md"))
    else:
        md_files = [input_path]

    print(f"入库 {len(md_files)} 个文件")

    pg_config = {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": os.getenv("PG_DBNAME", "knowledge_base"),
        "user": os.getenv("PG_USER", ""),
        "password": os.getenv("PG_PASSWORD", ""),
    }
    es_config = {
        "host": os.getenv("ES_HOST", "http://localhost:9200"),
        "user": os.getenv("ES_USER", ""),
        "password": os.getenv("ES_PASSWORD", ""),
    }
    es_index = os.getenv("ES_INDEX", "knowledge_chunks")

    import re
    from pathlib import Path as _Path

    for i, fp in enumerate(md_files, 1):
        fp = _Path(fp)
        print(f"\n[{i}/{len(md_files)}] {fp.name}")

        # 从文件名提取 kb_code 用于路由
        kb_match = re.search(r"KB\d+", fp.stem)
        kb_code = kb_match.group() if kb_match else ""

        data = build_output(str(fp), embedding_model=os.getenv("EMBEDDING_MODEL"),
                           use_llm=bool(os.getenv("DEEPSEEK_API_KEY")))

        print(f"  标题: {data['metadata'].get('title', 'N/A')}")
        print(f"  分块: {len(data['chunks'])} 个")

        if args.pg:
            schema = f"{kb_code}_{fp.parent.name}" if kb_code else "public"
            write_to_postgres(data, schema=schema, **{k: v for k, v in pg_config.items()})
            print(f"  PG -> {pg_config['dbname']}.{schema}.documents")

        if args.es:
            idx = f"{es_index}_{kb_code.lower()}" if kb_code else es_index
            n = write_to_elasticsearch(data, es_config["host"], idx,
                                      es_config["user"], es_config["password"])
            print(f"  ES -> {es_config['host']}/{idx} ({n} chunks)")

    print(f"\n入库完成: {len(md_files)} 个文件")


def cmd_search(args):
    """检索知识：Neo4j扩展 → ES混合 → PG溯源。"""
    query = " ".join(args.query)
    top_k = args.top_k or 10

    from searcher.kb_search import run_pipeline

    result = run_pipeline(query, top_k=top_k, expand_k=args.expand_k or 3,
                         skip_neo4j=args.skip_neo4j)

    print(f"\n{'='*60}")
    print(f"  检索: {query}")
    print(f"{'='*60}")

    expansion = result.get("neo4j_expansion", {})
    keywords = expansion.get("keywords", [])
    if keywords:
        print(f"\n  [扩展词] {', '.join(keywords)}")

    es = result.get("es_results", {})
    print(f"\n  [ES] BM25={es.get('bm25_count', 0)} | Vector={es.get('vector_count', 0)} | "
          f"合并={es.get('merged_count', 0)}")

    hits = result.get("merged_hits", [])
    if not hits:
        print("\n  (无结果)")
        return

    print(f"\n  [结果] 共 {len(hits)} 条:\n")
    for i, h in enumerate(hits[:top_k], 1):
        score = h.get("score", 0)
        heading = h.get("heading", "")[:50]
        content = (h.get("content", "") or "")[:100].replace("\n", " ")
        print(f"  #{i} [{h.get('source', '?')}] score={score:.4f}")
        print(f"      {heading}")
        print(f"      {content}...")
        print()


def cmd_serve(args):
    """启动微服务。"""
    import uvicorn

    if args.service == "parse":
        from services.parse_service import app
    elif args.service == "classify":
        from services.classify_service import app
    elif args.service == "ingest":
        from writer.kb_ingest_server import create_app
        app = create_app()
    elif args.service == "search":
        from searcher.kb_search_server import app
    else:
        print(f"未知服务: {args.service}", file=sys.stderr)
        sys.exit(1)

    host = args.host or "0.0.0.0"
    port = args.port or 8000
    print(f"启动 {args.service} 服务 -> http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")


def cmd_pipeline(args):
    """全流程：解析 → 分类 → 写入。"""
    print("=" * 60)
    print("  阶段 1/3: 文档解析")
    print("=" * 60)
    cmd_parse(args)

    print(f"\n{'='*60}")
    print("  阶段 2/3: LLM 分类")
    print("=" * 60)
    # 将解析产物路径传给分类
    args.parsed = args.output or "output/parsed"
    cmd_classify(args)

    print(f"\n{'='*60}")
    print("  阶段 3/3: 知识入库")
    print("=" * 60)
    args.file = None
    args.dir = args.output or "output/knowledge"
    args.pg = True
    args.es = True
    cmd_ingest(args)

    print(f"\n{'='*60}")
    print("  全流程完成!")
    print(f"  解析产物: output/parsed/")
    print(f"  知识chunk: output/knowledge/")
    print(f"  数据库: PG + ES")
    print(f"{'='*60}")


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Finance AI KnowledgeBase — 证券知识库系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py pipeline -f document.pdf       # 一键全流程
  python main.py parse -f report.pdf            # 解析文档
  python main.py classify                       # LLM分类
  python main.py ingest --dir output/knowledge  # 入库PG+ES
  python main.py search "权限校验 E403"          # 检索知识
  python main.py serve search --port 8002       # 启动检索API
        """,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── parse ──
    p_parse = sub.add_parser("parse", help="解析文档 → 纯文本")
    p_parse.add_argument("-f", "--file", required=True)
    p_parse.add_argument("-o", "--output", default="output/parsed")

    # ── classify ──
    p_cls = sub.add_parser("classify", help="LLM分段+分类 → KB chunk")
    p_cls.add_argument("-c", "--config", default="config.yaml")
    p_cls.add_argument("--parsed", default="output/parsed")
    p_cls.add_argument("-o", "--output", default="output/knowledge")

    # ── txt-pipeline ──
    p_txt = sub.add_parser("txt-pipeline", help="TXT段落切分+分类+Markdown，可选入库")
    p_txt.add_argument("-f", "--file", required=True)
    p_txt.add_argument("-o", "--output", default="output/txt_knowledge")
    p_txt.add_argument("-c", "--config", default="config.yaml")
    p_txt.add_argument("--embedding-model", default="")
    p_txt.add_argument("--no-llm", action="store_true", help="跳过网络调用，使用规则分类降级")
    p_txt.add_argument("--no-embedding", action="store_true", help="跳过本地向量模型，仅验证文本流程")
    p_txt.add_argument("--write-pg", action="store_true", help="显式启用 PostgreSQL 写入")
    p_txt.add_argument("--write-es", action="store_true", help="显式启用 Elasticsearch 写入")

    # ── ingest ──
    p_ing = sub.add_parser("ingest", help="写入PG+ES")
    p_ing.add_argument("-f", "--file")
    p_ing.add_argument("--dir")
    p_ing.add_argument("--pg", action="store_true", default=True)
    p_ing.add_argument("--es", action="store_true", default=True)

    # ── search ──
    p_srch = sub.add_parser("search", help="检索知识")
    p_srch.add_argument("query", nargs="+")
    p_srch.add_argument("-k", "--top-k", type=int, default=10)
    p_srch.add_argument("-e", "--expand-k", type=int, default=3)
    p_srch.add_argument("--skip-neo4j", action="store_true")

    # ── serve ──
    p_srv = sub.add_parser("serve", help="启动微服务")
    p_srv.add_argument("service", choices=["parse", "classify", "ingest", "search"])
    p_srv.add_argument("--host", default="0.0.0.0")
    p_srv.add_argument("--port", type=int)

    # ── pipeline ──
    p_pl = sub.add_parser("pipeline", help="全流程：解析+分类+入库")
    p_pl.add_argument("-f", "--file", required=True)
    p_pl.add_argument("-o", "--output", default="output")
    p_pl.add_argument("-c", "--config", default="config.yaml")
    p_pl.add_argument("--pg", action="store_true", default=True)
    p_pl.add_argument("--es", action="store_true", default=True)

    args = parser.parse_args()

    if args.command == "parse":
        cmd_parse(args)
    elif args.command == "classify":
        cmd_classify(args)
    elif args.command == "txt-pipeline":
        cmd_txt_pipeline(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "pipeline":
        cmd_pipeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
