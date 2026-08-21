#!/usr/bin/env python3
"""
kb_ingest_batch.py — 批量知识库入库

扫描文件夹内所有 .md，逐文件执行：元数据提取 → 哈希 → 分块 → 向量化 → PG + ES 双写

用法：
  python kb_ingest_batch.py                      # 使用 .env 中的 INPUT_DIR
  python kb_ingest_batch.py ./md_folder          # 命令行指定文件夹
  python kb_ingest_batch.py --pg-write           # 直写 PG
  python kb_ingest_batch.py --es-write           # 直写 ES
  python kb_ingest_batch.py --use-llm            # DeepSeek 提取元数据

输出：
  PG documents 表 — 按文件夹创建独立 schema，文档元数据入库
  ES 索引         — 按文件夹创建独立索引，分块 + 向量 + 全文

首次使用：
  1. 编辑 .env：数据库连接信息
  2. pip install sentence-transformers psycopg2-binary
  3. python kb_ingest_batch.py
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# 导入公共模块
from kb_common import (
    read_file, compute_sha256, extract_meta, extract_meta_via_llm,
    get_file_info, build_metadata, strip_markdown, split_by_h2
)

# ===========================================================================
# 配置 —— 从 .env 读取，换环境只需改 .env 文件
# ===========================================================================

# ---- 输入 ----
INPUT_DIR = os.getenv("INPUT_DIR", "")

# ---- 嵌入模型 ----
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")

# ---- DeepSeek API（用于 LLM 提取元数据） ----
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# ---- PostgreSQL（元数据入库） ----
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DBNAME = os.getenv("PG_DBNAME", "knowledge_base")
PG_USER = os.getenv("PG_USER", "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# ---- Elasticsearch（分块入库） ----
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "knowledge_chunks")
ES_USER = os.getenv("ES_USER", "")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")


# ===========================================================================
# 1. 本脚本特定的工具
# ===========================================================================
# 基础工具（read_file, compute_sha256）已从 kb_common 导入


# ===========================================================================
# 2. 元数据提取（已从 kb_common 导入）
# ===========================================================================
# extract_meta, extract_meta_via_llm, get_file_info, build_metadata 已从 kb_common 导入

# ===========================================================================
# 3. 纯文本提取（已从 kb_common 导入）
# ===========================================================================
# strip_markdown 已从 kb_common 导入

# ===========================================================================
# 4. 分块（已从 kb_common 导入）
# ===========================================================================
# split_by_h2 已从 kb_common 导入


# ===========================================================================
# 5. 向量化
# ===========================================================================

_embedding_model = None
_embedding_model_name = None


def _get_embedding_model(model_name: str):
    global _embedding_model, _embedding_model_name
    if _embedding_model is not None and _embedding_model_name == model_name:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("错误：向量化需要 sentence-transformers。请执行：pip install sentence-transformers")
    print(f"  加载嵌入模型：{model_name} ...")
    _embedding_model = SentenceTransformer(model_name)
    _embedding_model_name = model_name
    return _embedding_model


def embed_chunks(chunks: List[Dict], model_name: str) -> List[Dict]:
    """为每个 chunk 生成向量嵌入，原地添加 vector 字段。"""
    if not chunks:
        return chunks
    model = _get_embedding_model(model_name)
    texts = [c["content"] for c in chunks]
    print(f"  正在向量化 {len(texts)} 个块 ...")
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    for chunk, vec in zip(chunks, vectors):
        chunk["vector"] = vec.tolist()
    return chunks


# ===========================================================================
# 6. 构建 & 输出
# ===========================================================================

def build_output(input_path: str, embedding_model: Optional[str] = None,
                 use_llm: bool = False) -> Dict:
    text = read_file(input_path)
    return {
        "doc_hash": compute_sha256(text),
        "metadata": build_metadata(
            text, input_path, use_llm=use_llm,
            llm_api_key=DEEPSEEK_API_KEY,
            llm_base_url=DEEPSEEK_BASE_URL,
            llm_model=DEEPSEEK_MODEL
        ),
        "chunks": embed_chunks(split_by_h2(text), embedding_model) if embedding_model
                  else split_by_h2(text),
    }




# ===========================================================================
# 7. PostgreSQL 写入
# ===========================================================================

def _pg_connect(host, port, dbname, user, password):
    try:
        import psycopg2
    except ImportError:
        sys.exit("错误：需要 psycopg2。请执行：pip install psycopg2-binary")
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def write_to_postgres(data: Dict, host: str, port: int, dbname: str,
                      user: str, password: str, schema: str = "public") -> bool:
    """元数据写入 PG documents 表。PG 只存元数据，chunk 归 ES。"""
    from psycopg2 import sql as psql

    meta = data["metadata"]
    doc_hash = data["doc_hash"]
    meta_json = json.dumps(meta.get("meta_fields", {}), ensure_ascii=False)

    conn = _pg_connect(host, port, dbname, user, password)
    cur = conn.cursor()
    try:
        cur.execute(psql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(psql.Identifier(schema)))
        tbl = psql.SQL("{}.documents").format(psql.Identifier(schema))
        cur.execute(psql.SQL("""
            CREATE TABLE IF NOT EXISTS {} (
                doc_hash TEXT PRIMARY KEY, title TEXT, source_file TEXT,
                file_size_bytes BIGINT, file_created TIMESTAMPTZ,
                file_modified TIMESTAMPTZ, word_count INTEGER, char_count INTEGER,
                meta_fields JSONB, updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """).format(tbl))
        cur.execute(psql.SQL("""
            INSERT INTO {} (doc_hash, title, source_file, file_size_bytes,
                file_created, file_modified, word_count, char_count, meta_fields, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (doc_hash) DO UPDATE SET
                title=EXCLUDED.title, source_file=EXCLUDED.source_file,
                file_size_bytes=EXCLUDED.file_size_bytes,
                file_created=EXCLUDED.file_created,
                file_modified=EXCLUDED.file_modified,
                word_count=EXCLUDED.word_count, char_count=EXCLUDED.char_count,
                meta_fields=EXCLUDED.meta_fields,
                updated_at=NOW()
        """).format(tbl), (doc_hash, meta.get("title", ""), meta.get("source_file", ""),
              meta.get("file_size_bytes", 0), meta.get("file_created", ""),
              meta.get("file_modified", ""), meta.get("word_count", 0),
              meta.get("char_count", 0), meta_json))
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()


# ===========================================================================
# 8. Elasticsearch 写入
# ===========================================================================

_es_indexes_ensured: set = set()  # 已创建 mapping 的索引缓存


def _es_request(url: str, method: str = "GET", body: Optional[str] = None,
                es_user: str = "", es_password: str = "", timeout: int = 15):
    """发送 ES HTTP 请求，返回 (status_code, response_json_dict)。"""
    import base64
    import urllib.request
    import urllib.error

    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if es_user:
        cred = base64.b64encode(f"{es_user}:{es_password}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, json.loads(raw) if raw.strip() else {}


def _ensure_es_index(es_host: str, es_index: str, vector_dim: int = 768,
                     es_user: str = "", es_password: str = ""):
    """确保 ES 索引存在且 mapping 正确：dense_vector + IK 中文分词。"""
    if es_index in _es_indexes_ensured:
        return

    base = es_host.rstrip("/")
    idx_url = f"{base}/{es_index}"

    status, _ = _es_request(idx_url, "HEAD", es_user=es_user, es_password=es_password)
    if status == 200:
        _es_indexes_ensured.add(es_index)
        return

    for analyzer in ("ik_max_word", "standard"):
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
            },
            "mappings": {
                "properties": {
                    "doc_hash":       {"type": "keyword"},
                    "chunk_index":    {"type": "integer"},
                    "heading":        {"type": "text", "analyzer": analyzer,
                                       "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                    "content":        {"type": "text", "analyzer": analyzer},
                    "text":           {"type": "text", "analyzer": analyzer,
                                       "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                    "content_hash":   {"type": "keyword"},
                    "char_start":     {"type": "integer"},
                    "char_end":       {"type": "integer"},
                    "source_file":    {"type": "keyword"},
                    "title":          {"type": "text", "analyzer": analyzer,
                                       "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                    "meta_fields":    {"type": "object"},
                    "vector": {
                        "type": "dense_vector",
                        "dims": vector_dim,
                    },
                }
            },
        }
        status, resp = _es_request(idx_url, "PUT", json.dumps(mapping),
                                   es_user=es_user, es_password=es_password)
        if status == 200:
            _es_indexes_ensured.add(es_index)
            print(f"  ES 索引已创建: {es_index}  (analyzer={analyzer})")
            return
        if status == 400 and analyzer == "ik_max_word" and "analyzer" in str(resp).lower():
            print(f"  ES IK 分词器不可用，回退 standard")
            continue
        print(f"  ES 索引创建失败 ({status}): {resp}")
        break


def write_to_elasticsearch(data: Dict, es_host: str, es_index: str,
                           es_user: str = "", es_password: str = "") -> int:
    """chunk 写入 ES（_bulk API），_id = {doc_hash}_{chunk_index}，
    自动创建索引 mapping（dense_vector 768d + IK 中文分词），
    写入后立即 refresh。"""
    import base64
    import urllib.request
    import urllib.error

    doc_hash = data["doc_hash"]
    meta = data["metadata"]
    chunks = data["chunks"]

    vec_dim = 768
    if chunks and "vector" in chunks[0]:
        vec_dim = len(chunks[0]["vector"])

    _ensure_es_index(es_host, es_index, vector_dim=vec_dim,
                     es_user=es_user, es_password=es_password)

    lines: List[str] = []
    for i, chunk in enumerate(chunks):
        action = json.dumps({"index": {"_index": es_index, "_id": f"{doc_hash}_{i}"}},
                            ensure_ascii=False)
        doc = {
            "doc_hash": doc_hash, "chunk_index": i, "heading": chunk["heading"],
            "content": chunk["content"], "text": chunk["text"],
            "content_hash": chunk["hash"], "char_start": chunk["char_start"],
            "char_end": chunk["char_end"], "source_file": meta.get("source_file", ""),
            "title": meta.get("title", ""), "meta_fields": meta.get("meta_fields", {}),
        }
        if "vector" in chunk:
            doc["vector"] = chunk["vector"]
        lines.append(action + "\n" + json.dumps(doc, ensure_ascii=False))

    body = "\n".join(lines) + "\n"
    req = urllib.request.Request(
        f"{es_host.rstrip('/')}/_bulk?refresh=wait_for",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"}, method="POST",
    )
    if es_user:
        cred = base64.b64encode(f"{es_user}:{es_password}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ES 写入失败：{e.code} {e.reason}")
        return 0
    except Exception as e:
        print(f"  ES 连接失败：{e}")
        return 0

    if result.get("errors"):
        errors = [it for it in result.get("items", []) if "error" in it.get("index", {})]
        print(f"  ES 部分写入失败：{len(errors)}/{len(chunks)} 条")
        for err in errors[:3]:
            print(f"    {err['index'].get('_id')}: {err['index'].get('error', {}).get('reason')}")
    return len(chunks) - len(errors) if result.get("errors") else len(chunks)


# ===========================================================================
# 9. 写入后验证
# ===========================================================================

def _verify_pg_write(host: str, port: int, dbname: str, user: str, password: str,
                     schema: str, doc_hash: str) -> bool:
    """查询 PG 确认 doc_hash 已成功写入。"""
    try:
        conn = _pg_connect(host, port, dbname, user, password)
        cur = conn.cursor()
        from psycopg2 import sql as psql
        tbl = psql.SQL("{}.documents").format(psql.Identifier(schema))
        cur.execute(psql.SQL("SELECT 1 FROM {} WHERE doc_hash = %s").format(tbl), (doc_hash,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return row is not None
    except Exception as e:
        print(f"  [WARN] PG 验证查询异常: {e}")
        return False


def _verify_es_write(es_host: str, es_index: str, es_user: str, es_password: str,
                     doc_hash: str, expected_count: int) -> int:
    """查询 ES 确认 chunk 已成功写入，返回实际文档数。"""
    import base64, urllib.request, urllib.error
    body = json.dumps({
        "query": {"term": {"doc_hash": doc_hash}}
    })
    req = urllib.request.Request(
        f"{es_host.rstrip('/')}/{es_index}/_count",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    if es_user:
        cred = base64.b64encode(f"{es_user}:{es_password}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("count", 0)
    except Exception as e:
        print(f"  [WARN] ES 验证查询异常: {e}")
        return 0


# ===========================================================================
# 10. 入口
# ===========================================================================

def process_one_file(file_path: str, args, pg_conn: Dict, es_conn: Dict):
    """处理单个 md 文件：提取 → 分块 → 向量化 → PG + ES 双写"""
    stem = Path(file_path).stem
    print(f"\n{'='*60}")
    print(f"处理：{file_path}")
    embed_model = args.embedding_model
    data = build_output(file_path, embedding_model=embed_model, use_llm=args.use_llm)

    print(f"  标题：{data['metadata'].get('title', 'N/A')}")
    print(f"  文档哈希：{data['doc_hash']}")
    print(f"  元数据字段数：{len(data['metadata'].get('meta_fields', {}))}")
    print(f"  分块数：{len(data['chunks'])}")
    if any("vector" in c for c in data["chunks"]):
        print(f"  向量维度：{len(data['chunks'][0]['vector'])}")

    doc_hash = data["doc_hash"]
    chunk_count = len(data["chunks"])
    pg_ok = True
    es_ok = True

    # PG
    if args.pg_write:
        write_to_postgres(data, pg_conn["host"], pg_conn["port"], pg_conn["dbname"],
                          pg_conn["user"], pg_conn["password"], schema=pg_conn["schema"])
        # 验证 PG 写入
        pg_ok = _verify_pg_write(pg_conn["host"], pg_conn["port"], pg_conn["dbname"],
                                 pg_conn["user"], pg_conn["password"],
                                 pg_conn["schema"], doc_hash)
        if pg_ok:
            print(f"  PG(write)    → 已写入并验证 {pg_conn['dbname']}.{pg_conn['schema']}.documents")
        else:
            print(f"  PG(write)    → [ERROR] 写入后验证失败：未查询到 doc_hash={doc_hash[:16]}...")

    # ES
    if args.es_write:
        n = write_to_elasticsearch(data, es_conn["host"], es_conn["index"],
                                   es_conn["user"], es_conn["password"])
        # 验证 ES 写入
        written = _verify_es_write(es_conn["host"], es_conn["index"],
                                   es_conn["user"], es_conn["password"],
                                   doc_hash, chunk_count)
        if written == chunk_count:
            es_ok = True
            print(f"  ES(write)    → {n} chunks 已写入并验证 {es_conn['host']}/{es_conn['index']}")
        else:
            es_ok = False
            print(f"  ES(write)    → [ERROR] 写入后验证失败：期望 {chunk_count} chunks，实际查到 {written}")

    return pg_ok and es_ok


def main():
    p = argparse.ArgumentParser(description="批量 Markdown 元数据提取 + 哈希 + 分块 + 向量化 + 入库")
    p.add_argument("input_dir", nargs="?", default=None,
                   help="包含 md 文件的文件夹路径（留空则使用 .env 中的 INPUT_DIR）")
    p.add_argument("--embedding-model", default=EMBEDDING_MODEL,
                   help=f"向量模型（默认 {EMBEDDING_MODEL}）")
    p.add_argument("--use-llm", action="store_true",
                   help="用 DeepSeek 提取元数据（需先填 DEEPSEEK_API_KEY）")

    pg = p.add_argument_group("PostgreSQL — 写入元数据到 documents 表")
    pg.add_argument("--pg-write", action="store_true", help="启用直写 PG")
    pg.add_argument("--pg-host", default=PG_HOST, help=f"PG 主机（默认 {PG_HOST}）")
    pg.add_argument("--pg-port", type=int, default=PG_PORT, help=f"PG 端口（默认 {PG_PORT}）")
    pg.add_argument("--pg-dbname", default=PG_DBNAME, help=f"数据库名（默认 {PG_DBNAME}）")
    pg.add_argument("--pg-user", default=PG_USER, help=f"用户名（默认 {PG_USER}）")
    pg.add_argument("--pg-password", default=PG_PASSWORD, help="密码")

    es = p.add_argument_group("Elasticsearch — 写入分块（原文 + 纯文本 + 向量）")
    es.add_argument("--es-write", action="store_true", help="启用直写 ES")
    es.add_argument("--es-host", default=ES_HOST, help=f"ES 地址（默认 {ES_HOST}）")
    es.add_argument("--es-index", default=ES_INDEX, help=f"ES 索引名（默认 {ES_INDEX}）")
    es.add_argument("--es-user", default=ES_USER, help="ES 用户名")
    es.add_argument("--es-password", default=ES_PASSWORD, help="ES 密码")

    args = p.parse_args()

    # 输入：CLI 参数优先，否则用 .env 中的 INPUT_DIR
    input_dir = args.input_dir or INPUT_DIR
    if not input_dir:
        print("错误：请指定文件夹（命令行传入 或 在 .env 填写 INPUT_DIR）", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(input_dir):
        print(f"错误：文件夹不存在 — {input_dir}", file=sys.stderr)
        sys.exit(1)

    # 扫描所有 md 文件
    md_files = sorted(
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.endswith(".md")
    )
    if not md_files:
        print(f"错误：文件夹中没有 .md 文件 — {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    # 提取文件夹名作为子数据库标识
    folder_name = os.path.basename(os.path.normpath(input_dir.rstrip("/\\")))
    # PG schema：保留原始名称（支持中文），通过 psycopg2.sql.Identifier 安全引用
    pg_schema = folder_name.strip()
    # ES 索引后缀：只保留字母数字下划线，小写
    es_suffix = re.sub(r"[^a-zA-Z0-9]", "_", folder_name).strip("_").lower()
    if not es_suffix:
        es_suffix = hashlib.md5(folder_name.encode()).hexdigest()[:8]

    print(f"找到 {len(md_files)} 个 md 文件")
    print(f"PG schema: {pg_schema}  |  ES 索引: {args.es_index}_{es_suffix}")

    # 预加载嵌入模型（避免每个文件重复加载）
    _get_embedding_model(args.embedding_model)

    # 数据库连接参数
    pg_conn = {
        "host": args.pg_host, "port": args.pg_port, "dbname": args.pg_dbname,
        "user": args.pg_user, "password": args.pg_password,
        "schema": pg_schema,
    }
    es_conn = {
        "host": args.es_host, "index": f"{args.es_index}_{es_suffix}",
        "user": args.es_user, "password": args.es_password,
    }

    # 逐个处理
    success = fail = 0
    for file_path in md_files:
        try:
            if process_one_file(file_path, args, pg_conn, es_conn):
                success += 1
            else:
                fail += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            fail += 1

    print(f"\n{'='*60}")
    print(f"完成：成功 {success}，失败 {fail}，共 {len(md_files)} 个文件")


if __name__ == "__main__":
    main()
