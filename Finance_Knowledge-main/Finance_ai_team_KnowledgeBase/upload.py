#!/usr/bin/env python
"""知识库文档上传脚本。

用法:
    # 上传单个文件（全流程：parse → classify）
    python upload.py document.txt
    python upload.py report.pdf
    python upload.py manual.docx

    # 上传多个文件
    python upload.py a.txt b.pdf c.docx

    # 上传整个目录
    python upload.py --dir ./docs

    # 只解析不分类
    python upload.py document.txt --parse-only

    # 试运行（不写文件）
    python upload.py document.txt --dry-run

    # HTTP 模式（服务已部署时）
    python upload.py document.txt --mode http --url http://localhost:8003
"""

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).parent


def _run_subprocess(cmd: list[str]) -> tuple[bool, str]:
    """运行子进程，返回 (成功, 输出)。"""
    import subprocess, os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            cmd, cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
        )
        out = result.stdout.decode("utf-8", errors="replace")
        err = result.stderr.decode("utf-8", errors="replace")
        output = out + err
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


def run_cli_parse(file_path: str) -> bool:
    """调用 CLI 解析单文件。"""
    ok, out = _run_subprocess(
        [sys.executable, "main.py", "parse", "-f", str(file_path), "--force"]
    )
    if out:
        print(out)
    return ok


def run_cli_classify(file_path: str, dry_run: bool = False) -> bool:
    """调用 CLI 分类单文件。"""
    cmd = [sys.executable, "main.py", "classify", "-f", str(file_path), "--force"]
    if dry_run:
        cmd.append("--dry-run")
    ok, out = _run_subprocess(cmd)
    if out:
        print(out)
    return ok


def upload_http(file_path: str, base_url: str) -> Optional[dict]:
    """通过 HTTP API 上传文件并返回 chunk 列表。"""
    import requests

    url = f"{base_url.rstrip('/')}/ingest"
    with open(file_path, "rb") as f:
        resp = requests.post(url, files={"file": f}, timeout=300)

    if resp.status_code != 200:
        print(f"上传失败: HTTP {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        return None

    return resp.json()


def copy_to_input(file_path: str) -> str:
    """将文件复制到 input/ 目录，返回新路径。"""
    input_dir = PROJECT_DIR / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    src = Path(file_path)
    dst = input_dir / src.name
    shutil.copy2(src, dst)
    return str(dst)


def print_summary(file_name: str, elapsed: float, result: Optional[dict] = None):
    """打印处理结果摘要。"""
    print(f"\n{'='*60}")
    print(f"文件: {file_name}")
    print(f"耗时: {elapsed:.1f}s")
    if result:
        chunks = result.get("chunks", [])
        stats = result.get("stats", {})
        review = result.get("review_count", 0)
        print(f"知识块: {len(chunks)} 个")
        print(f"KB 分布: {stats}")
        if review:
            print(f"待复核: {review} 个 ⚠️")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="知识库文档上传脚本")
    parser.add_argument("files", nargs="*", help="要上传的文件路径（支持 txt/pdf/docx）")
    parser.add_argument("--dir", type=str, help="上传整个目录")
    parser.add_argument("--mode", choices=["cli", "http"], default="cli",
                        help="cli=本地命令行 | http=远程服务")
    parser.add_argument("--url", type=str, default="http://localhost:8003",
                        help="HTTP 模式的服务地址")
    parser.add_argument("--parse-only", action="store_true",
                        help="只解析不分类")
    parser.add_argument("--dry-run", action="store_true",
                        help="试运行（不写文件）")
    parser.add_argument("--force", action="store_true",
                        help="强制重新处理所有文件")
    args = parser.parse_args()

    # 收集文件
    files: list[str] = list(args.files)
    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"错误: 目录不存在: {args.dir}", file=sys.stderr)
            sys.exit(1)
        for ext in [".txt", ".pdf", ".docx", ".md", ".csv", ".text", ".log"]:
            files.extend(str(p) for p in dir_path.glob(f"*{ext}"))
        files = sorted(set(files))

    if not files:
        print("请指定要上传的文件（或使用 --dir 指定目录）")
        print("示例: python upload.py document.txt")
        sys.exit(1)

    # ── 统计跳过/新增 ──
    new_files = []
    skipped_files = []
    input_dir = PROJECT_DIR / "input"
    parse_force_flag = args.force

    for f in files:
        src = Path(f)
        if not src.exists():
            print(f"SKIP {src.name} (文件不存在)")
            continue

        dest = input_dir / src.name
        # 判断是否已处理过：input/parsed/knowledge 三者都比较修改时间
        parsed_file = PROJECT_DIR / "output/parsed" / f"{src.stem}.{src.suffix.lstrip('.')}.txt"
        knowledge_index = PROJECT_DIR / "output/knowledge" / "index.json"

        already_parsed = parsed_file.exists() and parsed_file.stat().st_mtime >= src.stat().st_mtime
        already_classified = knowledge_index.exists() and knowledge_index.stat().st_mtime >= src.stat().st_mtime

        if already_parsed and already_classified and not parse_force_flag:
            skipped_files.append(src.name)
        else:
            new_files.append(src)

    if skipped_files:
        print(f"跳过 {len(skipped_files)} 个已处理文件 (使用 --force 强制重处理)")
        for name in skipped_files:
            print(f"  SKIP {name}")
    if not new_files:
        print("所有文件已处理，无需操作")
        return

    print(f"\n处理 {len(new_files)} 个文件" +
          (" [试运行]" if args.dry_run else ""))

    # ── 步骤1: 复制到 input/ ──
    print(f"\n--- 复制到 input/ ---")
    for src_path in new_files:
        copy_to_input(str(src_path))
        print(f"  {src_path.name} -> input/")

    # ── 步骤1→2: 批量解析 ──
    if not args.parse_only:
        print(f"\n--- 批量解析 ---")
        _run_subprocess(
            [sys.executable, "main.py", "parse",
             "--force" if parse_force_flag else ""]
        )
        # 过滤掉 --force 导致的空字符串
        cmd = [sys.executable, "main.py", "parse"]
        if parse_force_flag:
            cmd.append("--force")
        ok, out = _run_subprocess(cmd)
        print(out)
        if not ok:
            print("部分文件解析失败")

    if args.parse_only:
        print(f"\n解析产物: {PROJECT_DIR / 'parsed'}")
        return

    # ── 步骤3→4: 批量分类 ──
    print(f"\n--- 批量分类 ---")
    cmd = [sys.executable, "main.py", "classify"]
    if parse_force_flag:
        cmd.append("--force")
    if args.dry_run:
        cmd.append("--dry-run")
    ok, out = _run_subprocess(cmd)
    print(out)

    # ── 最终摘要 ──
    print(f"\n{'='*60}")
    if not args.dry_run and ok:
        print(f"解析产物: {PROJECT_DIR / 'output/parsed'}")
        print(f"知识chunk: {PROJECT_DIR / 'output/knowledge'}")
        print(f"查看待复核: python main.py review")
    elif args.dry_run:
        print("试运行完成（未写入文件）")


if __name__ == "__main__":
    main()
