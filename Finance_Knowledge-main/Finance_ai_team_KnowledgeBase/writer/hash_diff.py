#!/usr/bin/env python3
"""
知识库单文件同步工具 — 以 PostgreSQL 为唯一状态源。

工作流:
  1. 解析 Markdown 文件，提取 record_id 和 SHA256
  2. 查询 PostgreSQL 是否已有该 record_id
  3. 比对规则:
     - record_id 不存在 → 调用 kb_ingest.py 入库 → PG 验证 → set_flag(True)
     - record_id 存在、hash 相同 → 跳过（无变更）
     - record_id 存在、hash 不同 → 先入库 → PG 验证 → 删旧记录 → set_flag(True)
  4. 入库验证: kb_ingest.py 内部写 PG/ES 后各自查询确认，run.py 再独立查 PG 二次验证
  5. 通知 updater: 入库成功后设置 needs_graphrag_rebuild = True

用法:
    python run.py xxx.md      # 指定文件
    python run.py             # 使用 .env 中的 INPUT_FILE
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys

# ============================================================
# 路径 & 环境
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 使 services 子模块可导入
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
KB_INGEST_DIR = os.path.join(SCRIPT_DIR, "..", "kb-ingest-pges")
ENV_FILE = os.path.join(KB_INGEST_DIR, ".env")
KB_INGEST_PY = os.path.join(KB_INGEST_DIR, "kb_ingest.py")

# 加载 kb-ingest-pges 的 .env 配置（必须在 import services 之前，确保 PG 连接参数就绪）
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
except ImportError:
    print("[WARN] 未安装 python-dotenv，无法读取 .env，将使用默认值。"
          " 请执行: pip install python-dotenv", file=sys.stderr)

# .env 加载完毕后才能导入 status_manager（其模块级变量依赖 os.getenv）
from writer.status_manager import set_flag

# ============================================================
# 配置 — 从 .env 读取
# ============================================================

INPUT_FILE = os.getenv("INPUT_FILE", "")

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DBNAME = os.getenv("PG_DBNAME", "knowledge_base")
PG_USER = os.getenv("PG_USER", "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# rag_service 的 PG 数据库名（与 knowledge_base 在同一 PG 实例，不同 database）
PG_RAG_DBNAME = os.getenv("PG_RAG_DBNAME", "rag_service")


# ============================================================
# 1. 文件读取 & 哈希计算
# ============================================================

def read_file(path: str) -> str:
    """读取文件，统一换行符为 \n。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def compute_sha256(text: str) -> str:
    """计算文本的 SHA256 哈希值。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================
# 2. 元数据提取（轻量版，无需 LLM / 向量化）
# ============================================================

def extract_metadata(text: str) -> dict:
    """从 Markdown 文档登记信息表格中提取元数据。

    返回 {"title": str, "meta_fields": {key: value, ...}}
    record_id 位于 meta_fields 中。
    """
    meta_fields: dict[str, str] = {}

    # 标题
    title = ""
    m = re.search(r"^#\s+(.*)", text, flags=re.MULTILINE)
    if m:
        title = m.group(1).strip()

    # 文档登记信息表格
    m = re.search(
        r"^##\s+文档登记信息.*?\n(.*?)(?=^##\s|\Z)",
        text, flags=re.MULTILINE | re.DOTALL,
    )
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line.startswith("|") or not line.endswith("|"):
                continue
            if re.match(r"^\|[\s\-:]+\|", line):  # 跳过分隔行
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 2 or cols[0] in ("元数据字段", "字段"):
                continue
            key = re.sub(r"[（(].*", "", cols[0]).strip()
            val = re.sub(r"[（(].*", "", cols[1]).strip()
            if key:
                meta_fields[key] = val

    return {"title": title, "meta_fields": meta_fields}


# ============================================================
# 3. PostgreSQL 查询 & 删除
# ============================================================

def _pg_connect():
    """建立 PG 连接（autocommit 模式）。"""
    import psycopg2
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
        user=PG_USER, password=PG_PASSWORD,
    )
    conn.autocommit = True
    return conn


def resolve_schema(kb_code: str) -> str:
    """根据 kb_code 前缀匹配 PG 中已有的 schema。

    - PG 连接失败 → 致命错误，退出
    - 未匹配到 schema → 警告后返回 prefix（可能为新 kb_code 首次入库）
    - 匹配成功 → 返回完整 schema 名
    """
    if not kb_code:
        return "public"
    prefix = kb_code.split("-")[0].strip()
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE %s ORDER BY schema_name LIMIT 1",
            (prefix + "%",),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"[ERROR] PG 连接失败，无法解析 schema（kb_code={kb_code}）: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  [WARN] 未匹配到 kb_code={kb_code} 对应的 schema，将使用前缀 '{prefix}'", file=sys.stderr)
    return prefix


def query_by_record_id(schema: str, record_id: str) -> dict | None:
    """按 record_id 查询 documents 表，返回 {doc_hash, title, ...} 或 None。

    如果 schema 或表不存在，返回 None（视为新文档）。
    """
    from psycopg2 import OperationalError, ProgrammingError
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(
            f'SELECT doc_hash, title, source_file, meta_fields '
            f'FROM "{schema}".documents '
            f"WHERE meta_fields->>'record_id' = %s",
            (record_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {
                "doc_hash": row[0],
                "title": row[1],
                "source_file": row[2],
                "meta_fields": row[3],
            }
        return None
    except (OperationalError, ProgrammingError):
        # schema 或表不存在 → 视为新文档
        return None
    except Exception as e:
        print(f"  [WARN] PG 查询异常: {e}")
        return None


def delete_by_record_id(schema: str, record_id: str) -> int:
    """按 record_id 删除旧记录，返回删除行数。"""
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(
            f'DELETE FROM "{schema}".documents '
            f"WHERE meta_fields->>'record_id' = %s",
            (record_id,),
        )
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return deleted
    except Exception as e:
        print(f"  [ERROR] PG 删除失败: {e}")
        return 0


def delete_by_doc_hash(schema: str, doc_hash: str) -> int:
    """按 doc_hash 精确删除单条记录（用于覆盖入库后清理旧记录）。

    与 delete_by_record_id 不同：只删指定 doc_hash 的记录，
    不会误删同 record_id 的新记录。
    """
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(
            f'DELETE FROM "{schema}".documents WHERE doc_hash = %s',
            (doc_hash,),
        )
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return deleted
    except Exception as e:
        print(f"  [ERROR] PG 删除(doc_hash) 失败: {e}")
        return 0


# ============================================================
# 4. 清理 rag_service chunk_mapping + 调用 kb_ingest.py 入库
# ============================================================

def delete_mapping_by_record_id(record_id: str) -> int:
    """按 record_id 清理 rag_service.chunk_mapping 中的过期映射。

    文档重新入库后 doc_hash 会变化，旧的 chunk_mapping 指向无效的 ES 文档 ID，
    必须清理掉才能让 rag_service 的 ensure_mapping_for_record() 触发自动重建。

    返回删除行数。
    """
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_RAG_DBNAME,
            user=PG_USER, password=PG_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM chunk_mapping WHERE es_record_id = %s",
            (record_id,),
        )
        deleted = cur.rowcount
        cur.close()
        conn.close()
        return deleted
    except Exception as e:
        print(f"  [WARN] chunk_mapping 清理异常: {e}")
        return 0


def call_ingest(file_path: str) -> bool:
    """调用 kb_ingest.py 执行 PG + ES 双写入库。

    kb_ingest.py 内部会：解析元数据 → 分块 → 向量化 → 写 PG → 写 ES。
    返回 True 表示子进程成功退出。
    """
    cmd = [
        sys.executable, KB_INGEST_PY, file_path,
        "--pg-write", "--es-write",
    ]
    print(f"  执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # 打印子进程输出
    stdout = result.stdout.strip()
    if stdout:
        for line in stdout.splitlines():
            print(f"  [ingest] {line}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"  [ERROR] kb_ingest.py 失败:", file=sys.stderr)
            for line in stderr.splitlines():
                print(f"    {line}", file=sys.stderr)
        return False
    return True


# ============================================================
# 5. 入口
# ============================================================

def main():
    # ---- 获取输入文件 ----
    input_file = None
    # CLI 位置参数优先
    for arg in sys.argv[1:]:
        if not arg.startswith("-") and arg.endswith(".md"):
            input_file = arg
            break
    # 回退到 .env 的 INPUT_FILE
    if not input_file:
        input_file = INPUT_FILE

    if not input_file:
        print("用法: python run.py <文件路径.md>")
        print("      或在 .env 中设置 INPUT_FILE=")
        sys.exit(1)

    input_file = os.path.abspath(input_file)
    if not os.path.isfile(input_file):
        print(f"[ERROR] 文件不存在: {input_file}")
        sys.exit(1)

    # ================================================================
    # Step 1: 解析文件
    # ================================================================
    print("=" * 60)
    print(f"  文件: {input_file}")
    print("=" * 60)

    text = read_file(input_file)
    doc_hash = compute_sha256(text)
    metadata = extract_metadata(text)

    record_id = metadata["meta_fields"].get("record_id", "")
    kb_code = metadata["meta_fields"].get("kb_code", "")
    title = metadata["title"]

    if not record_id:
        print("[ERROR] 未能从文档中提取到 record_id，请检查文档登记信息表格。")
        sys.exit(1)

    print(f"  record_id : {record_id}")
    print(f"  kb_code   : {kb_code}")
    print(f"  title     : {title}")
    print(f"  SHA256    : {doc_hash}")
    print(f"  (前16位)  : {doc_hash[:16]}...")

    # ================================================================
    # Step 2: 解析 PG schema，查询是否已有该 record_id
    # ================================================================
    schema = resolve_schema(kb_code)
    print(f"\n  PG schema : {schema}")

    existing = query_by_record_id(schema, record_id)

    # ================================================================
    # Step 3: 三分支判断
    # ================================================================
    if existing is None:
        # ---- 分支1: record_id 不存在 → 新文档，直接入库 ----
        print(f"\n  [分支1] record_id 不在 PG 中 → 新文档，开始入库...")
        success = call_ingest(input_file)
        if not success:
            print(f"\n  ❌ 入库失败，请检查上方错误信息")
            sys.exit(1)

        # 二次验证：确认 PG 中已有该 record_id
        confirmed = query_by_record_id(schema, record_id)
        if confirmed is None:
            print(f"\n  ❌ 入库后验证失败：PG 中未查询到 record_id={record_id}")
            sys.exit(1)

        print(f"\n  ✅ 入库成功（新增），PG 验证通过")
        if not set_flag(True):
            print(f"  [WARN] needs_graphrag_rebuild 标记更新失败，请检查 PG 连接")
        else:
            print(f"  needs_graphrag_rebuild → True（等待 updater 定时更新 Neo4j）")

    elif existing["doc_hash"] == doc_hash:
        # ---- 分支2: record_id 存在 && hash 相同 → 跳过 ----
        print(f"\n  [分支2] record_id 已存在，哈希值相同 → 跳过")
        print(f"    PG 中 hash: {existing['doc_hash'][:16]}...")
        print(f"    文件 hash  : {doc_hash[:16]}...")
        print(f"\n  ✅ 无变更，无需操作")

    else:
        # ---- 分支3: record_id 存在 && hash 不同 → 覆盖入库 ----
        old_doc_hash = existing["doc_hash"]
        print(f"\n  [分支3] record_id 已存在，哈希值不同 → 覆盖入库")
        print(f"    PG 中旧 hash: {old_doc_hash[:16]}...")
        print(f"    文件新 hash  : {doc_hash[:16]}...")

        # 3a: 先写入新数据（旧数据保留，防止写入失败数据丢失）
        print(f"\n  开始入库新数据...")
        success = call_ingest(input_file)
        if not success:
            print(f"\n  ❌ 入库失败（旧数据未受影响）")
            sys.exit(1)

        # 二次验证：确认 PG 中已有新的 record_id
        confirmed = query_by_record_id(schema, record_id)
        if confirmed is None:
            print(f"\n  ❌ 入库后验证失败：PG 中未查询到 record_id={record_id}")
            sys.exit(1)

        print(f"  PG 验证通过（新 hash: {confirmed['doc_hash'][:16]}...）")

        # 3b: 新数据已确认，安全删除旧记录（按旧的 doc_hash 精确删除）
        deleted = delete_by_doc_hash(schema, old_doc_hash)
        print(f"  已清理旧记录: {deleted} 行（doc_hash={old_doc_hash[:16]}...）")

        # 3c: 清理 rag_service 的过期 chunk_mapping
        mapping_deleted = delete_mapping_by_record_id(record_id)
        if mapping_deleted > 0:
            print(f"  已清理过期 mapping: {mapping_deleted} 行")

        print(f"\n  ✅ 覆盖入库成功")
        if not set_flag(True):
            print(f"  [WARN] needs_graphrag_rebuild 标记更新失败，请检查 PG 连接")
        else:
            print(f"  needs_graphrag_rebuild → True（等待 updater 定时更新 Neo4j）")

    print("")


if __name__ == "__main__":
    main()
