"""证券知识库文档解析模块 — 主入口。

四步流程:
  1. 上传文件 (input/)
  2. parse: 多格式 → 纯文本 (parsed/)
  3. classify: LLM 分段+分类 (knowledge/)
  4. 按 KB 聚合输出

用法:
    python main.py parse                        # 解析 input/ → parsed/
    python main.py classify                     # 分类 parsed/ → knowledge/
    python main.py orchestrate                  # 一键全流程
    python upload.py document.txt               # 上传脚本
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Union

import yaml

from shared.file_utils import ensure_output_dir, write_text_file
from shared.logger import setup_logger


def load_config(config_path: Union[str, Path]) -> dict:
    """加载 YAML 配置文件。"""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if config is None:
        config = {}
    return config


def main():
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="证券知识库文档解析模块",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 步骤 1→2：解析文档 → 结构化 Markdown
  python main.py parse                             # 批量解析 input/ → parsed/
  python main.py parse -f document.txt             # 解析单个文件
  python main.py parse -f report.pdf               # 支持 txt/pdf/docx
  python main.py parse --force                     # 强制重新解析

  # 步骤 3→4：分类 + 聚类 → 按 KB 输出 chunk
  python main.py classify                          # 批量分类 parsed/
  python main.py classify -f parsed/doc.txt        # 分类单个文件
  python main.py classify --dry-run                # 试运行（只预览不写文件）

  # 一键全流程：解析 + 分类
  python main.py orchestrate                       # 全流程
  python main.py orchestrate -f document.txt       # 单文件全流程
  python main.py orchestrate --dry-run             # 试运行

  # 查看待复核 chunk
  python main.py review
        """,
    )
    parser.add_argument(
        "command", nargs="?", default="parse",
        choices=["parse", "classify", "orchestrate", "review"],
        help="parse | classify | orchestrate | review",
    )
    parser.add_argument(
        "-f", "--file", type=str, default=None,
        help="指定单个文件",
    )
    parser.add_argument(
        "-i", "--input-dir", type=str, default="input",
        help="原始文件目录（默认: input）",
    )
    parser.add_argument(
        "--parsed-dir", type=str, default="output/parsed",
        help="解析产物目录（默认: output/parsed）",
    )
    parser.add_argument(
        "--classified-dir", type=str, default="output/classified",
        help="分类中间产物目录（默认: output/classified）",
    )
    parser.add_argument(
        "--knowledge-dir", type=str, default="output/knowledge",
        help="知识库 chunk 目录（默认: output/knowledge）",
    )
    parser.add_argument(
        "-c", "--config", type=str, default="config.yaml",
        help="配置文件路径",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    parser.add_argument("--log-file", type=str, default=None, help="日志文件路径")
    parser.add_argument("--force", action="store_true", help="强制重新处理")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写文件")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=log_level, log_file=args.log_file)

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "orchestrate":
            _cmd_orchestrate(args, config)
        elif args.command == "classify":
            _cmd_classify(args, config)
        elif args.command == "review":
            _cmd_review(args)
        elif args.file:
            _cmd_parse_single(args, config)
        else:
            _cmd_parse_batch(args, config)
    except Exception as e:
        logging.getLogger("knowledge_parser").error("执行出错: %s", e, exc_info=True)
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# 步骤 1→2: 解析
# ═══════════════════════════════════════════════════════════════

def _cmd_parse_single(args, config):
    """文件 → 纯文本，不做结构分析。"""
    from parser.parsers import parse_file

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"错误: 文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"解析: {input_path.name} ({input_path.suffix}) → 纯文本")
    parsed = parse_file(input_path)

    parsed_dir = Path(args.parsed_dir)
    ensure_output_dir(parsed_dir)
    safe_ext = input_path.suffix.lstrip(".")
    output_path = parsed_dir / f"{input_path.stem}.{safe_ext}.txt"
    write_text_file(output_path, parsed.content, encoding="utf-8")
    print(f"完成 -> {output_path} ({len(parsed.content)} 字符, {parsed.source_format})")


def _cmd_parse_batch(args, config):
    """批量 input/ → parsed/。"""
    from parser.parsers import parse_file, supported_formats

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"错误: 输入目录不存在: {input_dir}", file=sys.stderr)
        sys.exit(1)

    extensions = supported_formats()
    files = []
    for ext in extensions:
        files.extend(input_dir.glob(f"*{ext}"))
    files = sorted(set(files))

    if not files:
        print(f"在 {input_dir} 中未找到支持的文件（支持: {extensions}）")
        sys.exit(0)

    parsed_dir = Path(args.parsed_dir)
    ensure_output_dir(parsed_dir)

    success_count = 0
    for i, fp in enumerate(files, 1):
        safe_ext = fp.suffix.lstrip(".")
        output_path = parsed_dir / f"{fp.stem}.{safe_ext}.txt"
        if not args.force and output_path.exists() and output_path.stat().st_mtime >= fp.stat().st_mtime:
            print(f"[{i}/{len(files)}] SKIP {fp.name}")
            success_count += 1
            continue

        print(f"[{i}/{len(files)}] {fp.name} ({fp.suffix})")
        try:
            parsed = parse_file(fp)
            write_text_file(output_path, parsed.content, encoding="utf-8")
            print(f"  -> {output_path} ({len(parsed.content)} 字符)")
            success_count += 1
        except Exception as e:
            print(f"  FAIL: {e}")

    print(f"\n批量解析完成: {success_count}/{len(files)} -> {parsed_dir}/")


# ═══════════════════════════════════════════════════════════════
# 步骤 3→4: 分类
# ═══════════════════════════════════════════════════════════════

def _cmd_classify(args, config):
    """纯文本 → LLM 分段+分类 → knowledge/。"""
    from classifier.segmenter import LLMSegmenter
    from classifier.aggregator import Aggregator

    llm_cfg = config.get("extensions", {})
    api_key = llm_cfg.get("llm_api_key", "")
    if not api_key:
        print("错误: 未配置 LLM API Key")
        sys.exit(1)

    segmenter = LLMSegmenter(
        api_key=api_key,
        model=llm_cfg.get("llm_model", "deepseek-chat"),
        endpoint=llm_cfg.get("llm_endpoint", "https://api.deepseek.com/v1/chat/completions"),
        max_retries=llm_cfg.get("llm_max_retries", 2),
    )
    if not segmenter.ping():
        print("警告: LLM API 连通性检查失败")

    if args.file:
        text_files = [Path(args.file)]
    else:
        parsed_dir = Path(args.parsed_dir)
        text_files = sorted(list(parsed_dir.glob("*.txt")) + list(parsed_dir.glob("*.md")))
        if not text_files:
            print(f"在 {args.parsed_dir}/ 中未找到文件，请先运行 parse")
            sys.exit(0)

    knowledge_dir = Path(args.knowledge_dir)
    index_file = knowledge_dir / "index.json"
    skip_existing = not args.force and index_file.exists()
    pending = text_files if not skip_existing else [
        fp for fp in text_files
        if not (index_file.stat().st_mtime >= fp.stat().st_mtime)
    ]
    skipped = len(text_files) - len(pending)

    print(f"LLM 分段 + 分类: {len(text_files)} 个文件" + (f" (跳过 {skipped} 个)" if skipped else ""))
    if args.dry_run:
        print("[DRY RUN] 只预览，不写文件\n")

    agg = Aggregator(output_dir=str(knowledge_dir)) if not args.dry_run else None
    if not pending and not args.dry_run:
        print("所有文件已是最新")
        sys.exit(0)

    total_chunks = 0
    for i, fp in enumerate(pending, 1):
        print(f"\n{'='*50}")
        print(f"[{i}/{len(pending)}] {fp.name}")

        text = fp.read_text(encoding="utf-8")
        if not text.strip():
            print("  文件为空，跳过")
            continue

        print(f"  文本长度: {len(text)} 字符")
        segments = segmenter.segment(text, source_name=fp.stem)

        if not segments:
            print("  未提取到知识点")
            continue

        # 过滤掉无 KB 的片段
        valid_segments = [s for s in segments if s.primary_kb]
        skipped = len(segments) - len(valid_segments)
        if skipped:
            print(f"  过滤 {skipped} 个无效片段（无 KB 归属）")

        print(f"  提取 {len(valid_segments)} 个知识点:")
        for seg in valid_segments:
            sub = f" {seg.sub_category}" if seg.sub_category else ""
            print(f"  [{seg.primary_kb}{sub}] ({seg.confidence:.0%}) {seg.title[:40]}")

        if not args.dry_run:
            blocks, classifications = _segments_to_blocks(valid_segments, fp.name)
            file_chunks = agg.process_file(blocks, classifications, fp.name, markdown=text)
            total_chunks += len(file_chunks)

            # ── 在纯文本文件末尾追加分类备注 ──
            _append_classification_note(fp, valid_segments)

            # ── 保存分类中间结果到 classified/ ──
            _save_classified(args, fp, valid_segments, file_chunks)

    if not args.dry_run:
        agg.finalize()

    print(f"\n{'='*50}")
    if args.dry_run:
        print("试运行完成（未写入文件）")
    else:
        print(f"完成: {total_chunks} chunks → {args.knowledge_dir}/")


def _segments_to_blocks(segments, source_file: str):
    """LLM 分段结果 → aggregator 兼容格式。"""
    from classifier.models import H2Block, ClassifyResult

    blocks = []
    classifications = []
    for i, seg in enumerate(segments):
        blocks.append(H2Block(
            index=i, h1=source_file, h2_title=seg.title,
            content_preview=seg.content[:300], source_file=source_file,
            confidence="original", identified_refs=[],
            h3_children=[seg.title], h3_contents=[seg.content],
        ))
        classifications.append(ClassifyResult(
            index=i, primary_kb=seg.primary_kb, sub_category=seg.sub_category,
            secondary_kb=seg.secondary_kb, confidence=seg.confidence,
            keywords=seg.keywords, needs_review=seg.needs_review,
            method="llm", legal_ref=seg.legal_ref,
        ))
    return blocks, classifications


def _append_classification_note(parsed_file: Path, segments):
    """在纯文本文件末尾追加分类结果备注。"""
    from collections import Counter

    if not segments:
        return

    kb_counts = Counter(seg.primary_kb for seg in segments)
    kb_summary = "、".join(f"{kb}({cnt}条)" for kb, cnt in sorted(kb_counts.items()))
    note = (
        f"\n\n---\n"
        f"# 知识库分类备注\n"
        f"# 分类时间: {_now()}\n"
        f"# 提取知识点: {len(segments)} 条\n"
        f"# 归属知识库: {kb_summary}\n"
    )
    with open(parsed_file, "a", encoding="utf-8") as f:
        f.write(note)


def _save_classified(args, parsed_file: Path, segments, chunks):
    """保存分类中间结果到 classified/ 目录。"""
    import json as _json
    classified_dir = Path(args.classified_dir)
    ensure_output_dir(classified_dir)

    data = {
        "source": parsed_file.name,
        "segments": [
            {
                "title": s.title,
                "content": s.content[:200],
                "primary_kb": s.primary_kb,
                "sub_category": s.sub_category,
                "confidence": s.confidence,
                "needs_review": s.needs_review,
            }
            for s in segments
        ],
        "chunks": [{"chunk_id": c.chunk_id, "kb_id": c.kb_id} for c in chunks],
    }
    out_path = classified_dir / f"{parsed_file.stem}_classification.json"
    out_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════
# 全流程 + 审核
# ═══════════════════════════════════════════════════════════════

def _cmd_orchestrate(args, config):
    """一键全流程：parse + classify。"""
    from parser.parsers import parse_file

    print("=" * 50)
    print("阶段 1/2：文件 → 纯文本")
    print("=" * 50)

    if args.file:
        input_path = Path(args.file)
        parsed = parse_file(input_path)
        parsed_dir = Path(args.parsed_dir)
        ensure_output_dir(parsed_dir)
        safe_ext = input_path.suffix.lstrip(".")
        output_path = parsed_dir / f"{input_path.stem}.{safe_ext}.txt"
        write_text_file(output_path, parsed.content, encoding="utf-8")
        print(f"解析完成 -> {output_path} ({len(parsed.content)} 字符)")
    else:
        _cmd_parse_batch(args, config)

    print(f"\n{'='*50}")
    print("阶段 2/2：LLM 分段 + 分类")
    print("=" * 50)

    if args.file:
        args.file = str(Path(args.parsed_dir) / f"{Path(args.file).stem}.txt")
    _cmd_classify(args, config)


def _cmd_review(args):
    """列出所有待复核 chunk。"""
    index_file = Path(args.knowledge_dir) / "index.json"
    if not index_file.exists():
        print("未找到 index.json，请先运行 python main.py orchestrate")
        sys.exit(0)

    index = json.loads(index_file.read_text(encoding="utf-8"))
    chunks = index.get("chunks", [])
    review = [c for c in chunks if c.get("needs_review")]
    if not review:
        print("没有待复核的 chunk。")
        sys.exit(0)

    print(f"待复核 chunk: {len(review)}/{len(chunks)}\n")
    for c in review:
        kb = c.get("kb_id", "?")
        fn = c.get("source", "?")
        h2 = c.get("h2", "")[:60]
        conf = c.get("confidence", 0)
        print(f"  [{kb}] {c['chunk_id']} | src={fn} | conf={conf:.0%}")
        print(f"       {h2}")
        print()


if __name__ == "__main__":
    main()
