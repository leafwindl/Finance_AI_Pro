#!/usr/bin/env python3
"""
kb_classify_remote.py — 本地 TXT -> 切块 -> markdown -> 远程六库分类 -> 打印 kb_code

流程（本地处理结构，SSH 借道服务器模型，不改服务器任何代码）：
  1. 本地读取 TXT -> 清洗提取文本
  2. 本地切块（默认以一级标题为界 --by-h1），每块转 markdown（模型要的 text 结构）
  3. 通过 SSH 在服务器本机调用 127.0.0.1:8000/classify_batch（模型推理）
  4. 打印每块的 kb_code / doc_type / confidence

运行：用【系统 python】（已装 paramiko，无需装依赖）：
  python scripts/kb_classify_remote.py D:\\8.17update\\测试.txt
  python scripts/kb_classify_remote.py input.txt --by-h1
  python scripts/kb_classify_remote.py input.txt --ssh-pass '<密码>'

注意：切块逻辑与 app/knowledge_gateway/kb_ingest.py 保持一致（内联避免 fastapi 依赖）。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出避免中文/符号打印失败
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REMOTE_HOST = "172.22.121.55"
REMOTE_SSH_PORT = 50009
REMOTE_USER = "root"
CLASSIFY_URL = "http://127.0.0.1:8000/classify_batch"


# ============================================================
# 切块逻辑（与 kb_ingest.py 一致，纯函数，无第三方依赖）
# ============================================================

def _heading_level(line: str) -> int:
    line = line.strip()
    if not line:
        return 0
    m = re.match(r"^(#{1,6})\s+", line)
    if m:
        return len(m.group(1))
    if re.match(r"^第[0-9一二三四五六七八九十百千零]+[章节篇卷部分]", line):
        return 1
    if re.match(r"^\d+\.\d+\.\d+", line):
        return 3
    if re.match(r"^\d+\.\d+", line):
        return 2
    if re.match(r"^[一二三四五六七八九十]+、", line):
        return 2
    if re.match(r"^[（(][一二三四五六七八九十]+[）)]", line):
        return 3
    if re.match(r"^\d+[.．、]", line):
        return 2
    if re.match(r"^(规则编号|用例编号|缺陷编号|需求编号|错误码)[:：]", line):
        return 1
    return 0


def split_document_by_level1(text: str, max_chars: int = 2000) -> list[dict]:
    """以一级标题为界切块；块内二/三级标题转 markdown。"""
    sections: list[tuple[str, str, int]] = []
    heading = "文档"
    level = 0
    buf: list[str] = []
    for line in text.splitlines():
        lv = _heading_level(line)
        if lv == 1:
            if buf:
                sections.append((heading, "\n".join(buf).strip(), level))
            heading = re.sub(r"^#{1,6}\s*", "", line).strip()
            level = 1
            buf = []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip(), level))

    chunks: list[dict] = []
    for h, c, l in sections:
        if not c.strip():
            continue
        md_content = "\n".join(
            line if re.match(r"^#{1,6}\s+", line)
            else f"{'#' * lv} {line}" if (lv := _heading_level(line)) >= 2
            else line
            for line in c.splitlines()
        )
        for piece in _split_long(md_content, max_chars):
            chunks.append({"heading": h, "content": piece, "level": l or 1})
    return chunks


def _split_long(content: str, max_chars: int) -> list[str]:
    if len(content) <= max_chars:
        return [content]
    paragraphs = re.split(r"\n\s*\n", content)
    pieces: list[str] = []
    buf = ""
    for para in paragraphs:
        if buf and len(buf) + len(para) > max_chars:
            pieces.append(buf.strip())
            buf = para
        else:
            buf = (buf + "\n\n" + para) if buf else para
        while len(buf) > max_chars:
            pieces.append(buf[:max_chars].strip())
            buf = buf[max_chars:]
    if buf.strip():
        pieces.append(buf.strip())
    return pieces


def chunk_to_markdown(chunk: dict) -> str:
    level = chunk.get("level", 0) or 0
    prefix = "#" * min(max(level, 1), 4)
    return f"{prefix} {chunk['heading']}\n\n{chunk['content'].strip()}\n"


def extract_text_local(path: str, max_chars: int = 200000) -> str:
    """本地读取 TXT/MD：编码识别 + 统一换行 + 清洗（简化版，与 extraction 一致）。"""
    raw = Path(path).read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:max_chars]


# ============================================================
# SSH 调用远程模型
# ============================================================

def classify_batch_via_ssh(texts: list[str], ssh_pass: str) -> list:
    import paramiko

    payload = json.dumps({"texts": texts}, ensure_ascii=False)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        REMOTE_HOST, port=REMOTE_SSH_PORT, username=REMOTE_USER,
        password=ssh_pass, timeout=20,
    )
    cmd = (
        f"curl -s -X POST {CLASSIFY_URL} "
        "-H 'Content-Type: application/json' --data-binary @-"
    )
    stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
    stdin.write(payload)
    stdin.channel.shutdown_write()
    raw = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    client.close()
    if err.strip():
        print("[ssh stderr]", err[:300])
    try:
        return json.loads(raw)
    except Exception:
        return [{"raw": raw[:500], "parse_error": True}] * len(texts)


KB_CODES = {f"KB{i:02d}" for i in range(1, 7)}


def ingest_results(
    chunks: list[dict],
    results: list,
    ingest_url: str,
    source_file: str,
) -> tuple[int, int]:
    """按分类结果入库：kb_code ∈ KB01~06 写 ES+PG，其余（OUT_OF_SCOPE 等）跳过。

    返回 (已入库数, 跳过数)。
    """
    import hashlib
    import urllib.error
    import urllib.request

    ingested = 0
    skipped = 0
    for i, (ch, res) in enumerate(zip(chunks, results), 1):
        kb = (res or {}).get("kb_code", "") if isinstance(res, dict) else ""
        if kb not in KB_CODES:
            print(f"[{i}] {ch['heading']!r} -> {kb or '解析失败'}  跳过（不入库）")
            skipped += 1
            continue

        doc_id = hashlib.sha256(chunk_to_markdown(ch).encode("utf-8")).hexdigest()[:24]
        payload = {
            "kb_code": kb,
            "doc_id": doc_id,
            "title": ch["heading"],
            "source_file": source_file,
            "chunks": [{"heading": ch["heading"], "content": ch["content"]}],
        }
        url = f"{ingest_url.rstrip('/')}/ingest/chunks"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                rj = json.loads(r.read().decode("utf-8"))
            if rj.get("success"):
                print(
                    f"[{i}] {ch['heading']!r} -> {kb}  已入库 doc_id={doc_id} "
                    f"total_chunks={rj.get('total_chunks')}"
                )
                ingested += 1
            else:
                print(f"[{i}] {ch['heading']!r} -> {kb}  入库失败: {rj.get('error')}")
        except Exception as e:
            print(f"[{i}] {ch['heading']!r} -> {kb}  入库异常: {type(e).__name__}: {e}")
    return ingested, skipped


def main() -> int:
    p = argparse.ArgumentParser(description="本地切块 -> 远程分类 -> 按 kb_code 入库")
    p.add_argument("input", help="输入 TXT/MD 文件")
    p.add_argument("--by-h1", action="store_true", help="以一级标题为界切块（推荐）")
    p.add_argument("--max-chars", type=int, default=2000, help="单块最大字符数")
    p.add_argument("--ssh-pass", default="", help="服务器 SSH 密码（或环境变量 REMOTE_SSH_PASS）")
    p.add_argument("--ingest-url", default="http://127.0.0.1:8200",
                   help="本地 KB 入库服务地址（默认 http://127.0.0.1:8200）")
    p.add_argument("--no-ingest", action="store_true", help="只分类不入库")
    args = p.parse_args()

    ssh_pass = args.ssh_pass or __import__("os").environ.get("REMOTE_SSH_PASS", "")
    if not ssh_pass:
        print("错误：请用 --ssh-pass 或环境变量 REMOTE_SSH_PASS 提供服务器密码", file=sys.stderr)
        return 1

    src = Path(args.input)
    if not src.exists():
        print(f"错误：文件不存在 {src}", file=sys.stderr)
        return 1

    text = extract_text_local(str(src))
    chunks = split_document_by_level1(text, max_chars=args.max_chars) if args.by_h1 else []
    if not chunks:
        # 非 --by-h1 时也用一级标题切分兜底（保持简单）
        chunks = split_document_by_level1(text, max_chars=args.max_chars)

    if not chunks:
        print("未切出任何块", file=sys.stderr)
        return 1

    md_blocks = [chunk_to_markdown(c) for c in chunks]
    print(f"切块数: {len(chunks)}  →  调远程分类模型 …\n")

    results = classify_batch_via_ssh(md_blocks, ssh_pass)

    print("=" * 60)
    for i, (ch, res) in enumerate(zip(chunks, results), 1):
        if not isinstance(res, dict):
            print(f"[{i}] {ch['heading']}  (解析失败)")
            continue
        kb = res.get("kb_code", "?")
        dt = res.get("doc_type", "")
        conf = res.get("confidence", 0)
        review = "  ⚠需复核" if res.get("review_required") else ""
        print(f"[{i}] heading={ch['heading']!r}  ->  {kb} / {dt} / {conf}{review}")
    print("=" * 60)

    if args.no_ingest:
        return 0

    print(f"\n入库服务: {args.ingest_url}  （源文件: {src.name}）")
    ingested, skipped = ingest_results(chunks, results, args.ingest_url, src.name)
    print(f"汇总：已入库 {ingested} 块，跳过 {skipped} 块（OUT_OF_SCOPE 等）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
