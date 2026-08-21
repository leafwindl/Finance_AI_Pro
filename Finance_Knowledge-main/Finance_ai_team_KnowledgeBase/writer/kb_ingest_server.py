#!/usr/bin/env python3
"""
kb_ingest_server.py — 知识库入库 HTTP API 服务

启动后接受 POST /ingest 请求，传入 Markdown → 自动入库 PG + ES。

用法：
  python kb_ingest_server.py                        # 默认 0.0.0.0:8200
  python kb_ingest_server.py --port 9000            # 指定端口
  python kb_ingest_server.py --host 127.0.0.1       # 仅本机访问

API 文档：
  启动后浏览器打开 http://<IP>:<PORT>/docs 查看中文 Swagger 交互文档。
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
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

# 导入公共模块
from kb_common import (
    read_file, compute_sha256, extract_meta, extract_meta_via_llm,
    get_file_info, build_metadata, strip_markdown, split_by_h2
)

# ===========================================================================
# 配置 —— 从 .env 读取，换环境只需改 .env 文件
# ===========================================================================

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
    """三态缓存：成功返回模型；失败缓存并返回 False（无向量模式，不崩溃）。"""
    global _embedding_model, _embedding_model_name
    if _embedding_model is not None and _embedding_model_name == model_name:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  警告：未安装 sentence-transformers，跳过向量化")
        _embedding_model, _embedding_model_name = False, model_name
        return False
    try:
        print(f"  加载嵌入模型：{model_name} ...")
        _embedding_model = SentenceTransformer(model_name)
    except Exception as exc:
        print(f"  警告：嵌入模型加载失败，跳过向量化（无向量模式不受影响）: {exc}")
        _embedding_model = False
    _embedding_model_name = model_name
    return _embedding_model


def embed_chunks(chunks: List[Dict], model_name: str) -> List[Dict]:
    """为每个 chunk 生成向量嵌入，原地添加 vector 字段。模型不可用时跳过（无向量模式）。"""
    if not chunks:
        return chunks
    model = _get_embedding_model(model_name)
    if not model:
        return chunks
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
# 6. PostgreSQL 写入
# ===========================================================================

def _pg_connect(host, port, dbname, user, password):
    try:
        import psycopg2
    except ImportError:
        sys.exit("错误：需要 psycopg2。请执行：pip install psycopg2-binary")
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def write_to_postgres(data: Dict, host: str, port: int, dbname: str,
                      user: str, password: str, schema: str = "public") -> bool:
    """将文档 chunks 幂等写入现有 public.kb_documents 表。

    该项目的真实 PG 契约是一行一个 chunk，主键为 chunk_id。
    为避免误改现有库，这里不创建 schema/table，也不写 documents 表。
    """
    meta = data["metadata"]
    doc_hash = data["doc_hash"]
    chunks = data.get("chunks", [])
    kb_code = str(meta.get("meta_fields", {}).get("kb_code", "")).strip().upper()
    if not kb_code:
        match = re.search(r"KB\d+", str(meta.get("source_file", "")), re.IGNORECASE)
        kb_code = match.group(0).upper() if match else "KB01"

    conn = _pg_connect(host, port, dbname, user, password)
    cur = conn.cursor()
    try:
        for index, chunk in enumerate(chunks):
            chunk_id = f"{doc_hash}_{index:04d}"
            cur.execute(
                """
                INSERT INTO public.kb_documents
                    (chunk_id, doc_id, kb_code, title, heading, source_file,
                     content, version, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW())
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id,
                    kb_code = EXCLUDED.kb_code,
                    title = EXCLUDED.title,
                    heading = EXCLUDED.heading,
                    source_file = EXCLUDED.source_file,
                    content = EXCLUDED.content,
                    version = public.kb_documents.version + 1,
                    updated_at = NOW()
                """,
                (
                    chunk_id,
                    doc_hash,
                    kb_code,
                    meta.get("title", ""),
                    chunk.get("heading", ""),
                    meta.get("source_file", ""),
                    chunk.get("content", ""),
                ),
            )
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()


def resolve_schema_for_kb(kb_code: str, host: str, port: int, dbname: str,
                          user: str, password: str) -> str:
    """根据 kb_code 前缀匹配 PG 中已有的 schema，未找到则回退为前缀本身。

    - PG 连接失败 → 返回 prefix（后续 CREATE SCHEMA IF NOT EXISTS 会兜底）
    - 未匹配到 → 返回 prefix（新 kb_code 首次入库的正常情况）
    """
    prefix = kb_code.split("-")[0].strip()  # "KB01-02" → "KB01"
    try:
        conn = _pg_connect(host, port, dbname, user, password)
        cur = conn.cursor()
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE %s "
            "ORDER BY schema_name LIMIT 1",
            (prefix + "%",)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"  [WARN] PG 连接失败，使用前缀 '{prefix}' 作为 schema（后续 CREATE SCHEMA 将自动创建）: {e}")
        return prefix

    print(f"  [INFO] 未匹配到 kb_code={kb_code} 对应的 schema，使用前缀 '{prefix}'")
    return prefix


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


def _ensure_es_index(es_host: str, es_index: str, vector_dim: int = 1024,
                     es_user: str = "", es_password: str = ""):
    """确保 ES 索引存在且 mapping 正确：dense_vector + IK 中文分词。"""
    if es_index in _es_indexes_ensured:
        return

    base = es_host.rstrip("/")
    idx_url = f"{base}/{es_index}"

    # 1) 检查索引是否已存在
    status, _ = _es_request(idx_url, "HEAD", es_user=es_user, es_password=es_password)
    if status == 200:
        _es_indexes_ensured.add(es_index)
        return

    # 2) 构建 mapping：尝试 IK，失败回退 standard
    for analyzer in ("ik_max_word", "standard"):
        mapping = {
            "settings": {
                "number_of_shards": 1,
                # 本机为单节点 ES（dify 集群），副本分片无法分配会一直 yellow
                "number_of_replicas": 0,
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
                    "embedding": {
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
        # 400 + analyzer 错误 → 回退 standard 重试
        if status == 400 and analyzer == "ik_max_word" and "analyzer" in str(resp).lower():
            print(f"  ES IK 分词器不可用，回退 standard")
            continue
        # 其他错误直接打印
        print(f"  ES 索引创建失败 ({status}): {resp}")
        break


def write_to_elasticsearch(data: Dict, es_host: str, es_index: str,
                           es_user: str = "", es_password: str = "") -> int:
    """将 chunks 幂等写入已有的 knowledge_chunks_kbXX 索引。

    本函数不会创建索引。向量只有在输入 chunk 明确提供 embedding 时才写入；
    本轮默认关闭向量，因此不会向现有 mapping 写入不兼容的 vector 字段。
    """
    import base64
    import urllib.request
    import urllib.error

    doc_hash = data["doc_hash"]
    meta = data["metadata"]
    chunks = data["chunks"]

    # 构建 _bulk 请求体
    lines: List[str] = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_hash}_{i:04d}"
        action = json.dumps({"index": {"_index": es_index, "_id": chunk_id}},
                            ensure_ascii=False)
        kb_code = str(meta.get("meta_fields", {}).get("kb_code", "")).strip().upper()
        if not kb_code:
            match = re.search(r"KB\d+", str(meta.get("source_file", "")), re.IGNORECASE)
            kb_code = match.group(0).upper() if match else "KB01"
        doc = {
            "chunk_id": chunk_id,
            "doc_id": doc_hash,
            "kb_code": kb_code,
            "title": meta.get("title", ""),
            "heading": chunk.get("heading", ""),
            "content": chunk.get("content", ""),
            "source_file": meta.get("source_file", ""),
            "meta_fields": meta.get("meta_fields", {}),
            "source_h1": meta.get("title", ""),
            "source_h2": chunk.get("heading", ""),
            "source_h3": "",
            "sub_category": "",
            "needs_review": False,
            "confidence": "rule_fallback",
            "version": 1,
        }
        if "embedding" in chunk:
            doc["embedding"] = chunk["embedding"]
        elif "vector" in chunk:
            doc["embedding"] = chunk["vector"]
        lines.append(action + "\n" + json.dumps(doc, ensure_ascii=False))

    body = "\n".join(lines) + "\n"
    # refresh=wait_for：写完后立即可搜索
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
# 8b. Gateway 契约：块级入库 / 删除（/ingest/chunks、/ingest/delete）
# ===========================================================================

def _gateway_payload_to_data(kb_code: str, doc_id: str, title: str,
                             source_file: str, chunks: List[Dict]) -> Dict:
    """把 Gateway KBClient 契约 payload 适配为 write_to_postgres /
    write_to_elasticsearch 期望的 data 形状。

    doc_hash 传 Gateway 的 doc_id → chunk_id 自动生成为 f"{doc_id}_{i:04d}"，
    与现网 public.kb_documents 存量数据格式一致。
    """
    return {
        "doc_hash": doc_id,
        "metadata": {
            "title": title,
            "source_file": source_file,
            "meta_fields": {"kb_code": kb_code},
        },
        "chunks": [
            {"heading": str(c.get("heading") or ""), "content": str(c.get("content") or "")}
            for c in chunks
        ],
    }


def _es_index_for_kb(kb_code: str) -> str:
    """按 kb_code 前缀路由 ES 索引，与 searcher.route_es_index 规则一致。"""
    return f"{ES_INDEX}_{kb_code.split('-')[0].strip().lower()}"


def ingest_chunks_from_gateway(payload: Dict) -> Dict:
    """处理 Gateway 的 /ingest/chunks 契约：写 PG public.kb_documents + ES 路由索引。

    - PG 是权威存储，失败即整体失败（success=false）
    - ES 尽力而为（fail-soft）：失败不阻塞上传，success=true + warning，
      数据可用回填脚本补进 ES；重复入库幂等（PG ON CONFLICT / ES _id=chunk_id）
    """
    kb_code = str(payload.get("kb_code", "")).strip().upper()
    doc_id = str(payload.get("doc_id", "")).strip()
    chunks = payload.get("chunks") or []
    if not kb_code or not doc_id or not chunks:
        return {"success": False, "error": "kb_code/doc_id/chunks 不能为空"}

    data = _gateway_payload_to_data(
        kb_code, doc_id, str(payload.get("title", "")),
        str(payload.get("source_file", "")), chunks,
    )

    # 向量模式：用嵌入模型为每个 chunk 生成向量（write_to_elasticsearch 会映射为 embedding 字段）；
    # 模型不可用时降级为无向量写入（fail-soft，不影响入库）
    vector_dim = 1024
    if os.getenv("ENABLE_VECTOR_SEARCH", "false").lower() == "true":
        model = _get_embedding_model(EMBEDDING_MODEL)
        if model:
            for chunk in data["chunks"]:
                chunk["vector"] = model.encode(
                    chunk["content"], normalize_embeddings=True
                ).tolist()
            try:
                vector_dim = model.get_embedding_dimension()
            except AttributeError:  # 兼容旧版 sentence-transformers
                vector_dim = model.get_sentence_embedding_dimension()

    try:
        write_to_postgres(data, PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD, schema="public")
    except Exception as exc:
        return {"success": False, "error": f"PG 写入失败: {exc}"}

    es_index = _es_index_for_kb(kb_code)
    es_count, warning = 0, None
    try:
        _ensure_es_index(ES_HOST, es_index, vector_dim=vector_dim,
                         es_user=ES_USER, es_password=ES_PASSWORD)
        es_count = write_to_elasticsearch(data, ES_HOST, es_index, ES_USER, ES_PASSWORD)
    except Exception as exc:
        warning = f"ES 写入失败: {exc}"
    if es_count == 0 and warning is None:
        warning = "ES 写入 0 块（详见服务日志）"

    result = {
        "success": True,
        "doc_id": doc_id,
        "title": data["metadata"]["title"],
        "kb_code": kb_code,
        "chunk_count": len(chunks),
        "pg_schema": "public",
        "es_index": es_index,
        "es_chunks_written": es_count,
    }
    if warning:
        result["warning"] = warning
    return result


def delete_chunks_for_gateway(payload: Dict) -> Dict:
    """处理 Gateway 的 /ingest/delete 契约：同时删 PG 与 ES。

    deleted_chunks 取 PG 行数（Gateway rollback 汇总的就是该字段）；
    ES 按 kb_code 路由索引 delete_by_query，索引不存在（404）视为 0 条。
    """
    doc_id = str(payload.get("doc_id", "")).strip()
    kb_code = str(payload.get("kb_code", "")).strip().upper()
    if not doc_id or not kb_code:
        return {"success": False, "error": "doc_id/kb_code 不能为空"}

    try:
        conn = _pg_connect(PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD)
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM public.kb_documents WHERE doc_id = %s AND kb_code = %s",
            (doc_id, kb_code),
        )
        pg_deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        return {"success": False, "error": f"PG 删除失败: {exc}"}

    es_deleted, warning = 0, None
    index = _es_index_for_kb(kb_code)
    try:
        status, resp = _es_request(
            f"{ES_HOST.rstrip('/')}/{index}/_delete_by_query?refresh=true", "POST",
            json.dumps({"query": {"term": {"doc_id": doc_id}}}),
            es_user=ES_USER, es_password=ES_PASSWORD, timeout=30,
        )
        if status == 200:
            es_deleted = resp.get("deleted", 0)
        elif status != 404:  # 404 = index_not_found，视为 0 条已删
            warning = f"ES 删除异常({status}): {resp}"
    except Exception as exc:
        warning = f"ES 删除失败: {exc}"

    result = {
        "success": True,
        "doc_id": doc_id,
        "kb_code": kb_code,
        "deleted_chunks": pg_deleted,
        "es_deleted": es_deleted,
    }
    if warning:
        result["warning"] = warning
    return result


# ===========================================================================
# 9. 核心处理函数（CLI 和 API 共用）
# ===========================================================================

def process_one_document(file_path=None, content=None, file_name=None,
                         use_llm=False, no_embed=False,
                         pg_write=True, es_write=True,
                         pg_config=None, es_config=None):
    """处理单个文档（路径或内容二选一），写入 PG + ES，返回结果 dict。

    参数：
      file_path   — md 文件路径
      content     — md 文本内容（与 file_path 二选一，需同时传 file_name）
      file_name   — content 模式下用作输出文件名
      use_llm     — 是否用 DeepSeek 提取元数据
      pg_write    — 是否写入 PG
      es_write    — 是否写入 ES
      pg_config   — dict: {host, port, dbname, user, password}
      es_config   — dict: {host, user, password}

    返回：
      {
        "success": bool,
        "doc_hash": "...",
        "title": "...",
        "kb_code": "KB01" or None,
        "chunk_count": 8,
        "vector_dim": 768 or None,
        "pg_schema": "KB01_系统业务知识库" or None,
        "es_index": "knowledge_chunks_kb01" or None,
        "es_chunks_written": 8 or None,
      }
      失败时返回 {"success": False, "error": "原因"}
    """
    import tempfile

    result = {"success": False}

    # 输入校验
    if file_path and content:
        result["error"] = "file_path 和 content 只能传一个"
        return result
    if not file_path and not content:
        result["error"] = "file_path 或 content 必须传一个"
        return result

    # content 模式：写入临时文件
    tmp_file = None
    if content:
        if not file_name:
            file_name = "untitled.md"
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp_file.write(content.replace("\r\n", "\n").replace("\r", "\n"))
        tmp_file.close()
        file_path = tmp_file.name

    try:
        if not os.path.isfile(file_path):
            result["error"] = f"文件不存在 — {file_path}"
            return result

        stem = Path(file_path).stem
        vector_enabled = os.getenv("ENABLE_VECTOR_SEARCH", "false").lower() == "true"
        embed_model = None if (no_embed or not vector_enabled) else EMBEDDING_MODEL
        data = build_output(file_path, embedding_model=embed_model, use_llm=use_llm)
        if content and file_name:
            # content 模式使用临时文件完成复用处理，但对外元数据必须保留调用方文件名。
            data["metadata"]["source_file"] = Path(file_name).name

        # 根据 kb_code 路由
        kb_code = data["metadata"].get("meta_fields", {}).get("kb_code", "")
        # The verified runtime contract stores chunk rows in public.kb_documents.
        # Keep the response aligned with the table actually used by the writer.
        pg_schema = "public"

        if kb_code:
            es_suffix = kb_code.split("-")[0].strip().lower()
            es_index = f"{ES_INDEX}_{es_suffix}"
        else:
            es_index = ES_INDEX

        doc_hash = data["doc_hash"]
        chunk_count = len(data["chunks"])
        pg_verified = True
        es_verified = True

        # PG 写入
        if pg_write and pg_config:
            write_to_postgres(
                data, pg_config["host"], pg_config["port"],
                pg_config["dbname"], pg_config["user"], pg_config["password"],
                schema=pg_schema,
            )
            pg_verified = _verify_pg_write(
                pg_config["host"], pg_config["port"],
                pg_config["dbname"], pg_config["user"], pg_config["password"],
                doc_hash, chunk_count,
            )

        # ES 写入
        es_count = 0
        if es_write and es_config:
            es_count = write_to_elasticsearch(
                data, es_config["host"], es_index,
                es_config.get("user", ""), es_config.get("password", ""),
            )
            if es_count > 0:
                es_verified = _verify_es_write(
                    es_config["host"], es_index,
                    es_config.get("user", ""), es_config.get("password", ""),
                    doc_hash, chunk_count,
                ) == chunk_count

        vector_dim = None
        if data["chunks"] and "vector" in data["chunks"][0]:
            vector_dim = len(data["chunks"][0]["vector"])

        result = {
            "success": pg_verified and es_verified,
            "doc_hash": data["doc_hash"],
            "title": data["metadata"].get("title", ""),
            "kb_code": kb_code or None,
            "chunk_count": len(data["chunks"]),
            "vector_dim": vector_dim,
            "pg_schema": pg_schema if (pg_write and pg_config) else None,
            "es_index": es_index if (es_write and es_config) else None,
            "es_chunks_written": es_count if (es_write and es_config) else None,
        }
        return result

    finally:
        if tmp_file:
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass


# ===========================================================================
# 10. FastAPI 服务
# ===========================================================================

def _build_pg_config():
    return {
        "host": PG_HOST, "port": PG_PORT, "dbname": PG_DBNAME,
        "user": PG_USER, "password": PG_PASSWORD,
    }


def _build_es_config():
    return {
        "host": ES_HOST, "user": ES_USER, "password": ES_PASSWORD,
    }


def create_app():
    """创建 FastAPI 应用。"""
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    class IngestRequest(BaseModel):
        file_path: str = Field(
            default="",
            description="服务器上 md 文件的路径，如 ../KB01_系统业务知识库/xxx.md（与 content 二选一）",
            examples=["../KB01_系统业务知识库/KB01-01_系统概览01_模拟证券交易系统.md"],
        )
        content: str = Field(
            default="",
            description="直接传入 Markdown 文本内容（与 file_path 二选一，需同时传 file_name）",
            examples=["# 文档标题\n\n## 文档登记信息\n\n| 字段 | 值 |\n|------|------|\n| kb_code | KB01 |\n\n## 正文\n\n这是一段 Markdown 内容。"],
        )
        file_name: str = Field(
            default="",
            description="来源文件名，仅在 content 模式下使用；为空时使用 untitled.md",
            examples=["my_document.md"],
        )
        use_llm: bool = Field(
            default=False,
            description="是否用 DeepSeek 大模型智能提取元数据",
        )


    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(app):
        # 仅向量模式开启时才预加载模型；无向量模式下不触发联网加载
        if os.getenv("ENABLE_VECTOR_SEARCH", "false").lower() == "true":
            _get_embedding_model(EMBEDDING_MODEL)
        yield

    app = FastAPI(
        title="知识库入库 API",
        description="将 Markdown 文档自动分块、向量化，写入 PostgreSQL 和 Elasticsearch。传入文件路径或文本内容即可完成入库。",
        version="1.0",
        lifespan=_lifespan,
    )

    @app.post(
        "/ingest",
        summary="单文档入库",
        description="接收一个 Markdown 文档（路径或内容），完成：元数据提取 → SHA256 哈希 → 二级标题分块 → 向量化 → 写入 PG + ES。支持 file_path 和 content 两种模式，只能二选一。",
    )
    def ingest(req: IngestRequest):
        pg_cfg = _build_pg_config()
        es_cfg = _build_es_config()

        if req.file_path and req.content:
            return {"success": False, "error": "file_path 和 content 只能传一个"}
        if not req.file_path and not req.content:
            return {"success": False, "error": "file_path 或 content 必须传一个"}

        kwargs = dict(
            use_llm=req.use_llm,
            pg_write=True,
            es_write=True,
            pg_config=pg_cfg,
            es_config=es_cfg,
        )
        if req.content:
            kwargs["content"] = req.content
            kwargs["file_name"] = req.file_name or "untitled.md"
        else:
            kwargs["file_path"] = req.file_path

        return process_one_document(**kwargs)

    class GatewayChunk(BaseModel):
        heading: str = ""
        content: str = ""

    class IngestChunksRequest(BaseModel):
        kb_code: str
        doc_id: str
        title: str = ""
        source_file: str = ""
        chunks: List[GatewayChunk]

    class IngestDeleteRequest(BaseModel):
        doc_id: str
        kb_code: str

    @app.post(
        "/ingest/chunks",
        summary="Gateway 契约：块级入库（PG public.kb_documents + ES 路由索引）",
        description="对齐 Finance_AI_FASTAPI KBClient.ingest_chunks 契约：kb_code/doc_id/title/source_file/chunks。"
                    "chunk_id 生成为 {doc_id}_{i:04d}；重复入库幂等。ES 写入失败不阻塞（fail-soft）。",
    )
    def ingest_chunks(req: IngestChunksRequest):
        return ingest_chunks_from_gateway(req.model_dump())

    @app.post(
        "/ingest/delete",
        summary="Gateway 契约：按 doc_id 删除（PG + ES）",
        description="对齐 Finance_AI_FASTAPI KBClient.ingest_delete 契约：同时删 PG 行与 ES 文档。",
    )
    def ingest_delete(req: IngestDeleteRequest):
        return delete_chunks_for_gateway(req.model_dump())

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app

# ===========================================================================
# 10. 写入后验证
# ===========================================================================

def _verify_pg_write(host: str, port: int, dbname: str, user: str, password: str,
                     doc_id: str, expected_count: int) -> bool:
    """查询现有 public.kb_documents，确认本次 doc_id 的 chunks 已写入。"""
    try:
        conn = _pg_connect(host, port, dbname, user, password)
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM public.kb_documents WHERE doc_id = %s",
            (doc_id,),
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        return bool(row and row[0] == expected_count)
    except Exception as e:
        print(f"  [WARN] PG 验证查询异常: {e}")
        return False


def _verify_es_write(es_host: str, es_index: str, es_user: str, es_password: str,
                     doc_hash: str, expected_count: int) -> int:
    """查询 ES 确认本次 doc_id 的 chunk 数，返回实际文档数。"""
    import base64, urllib.request, urllib.error
    body = json.dumps({
        "query": {"term": {"doc_id": doc_hash}}
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
# 11. 入口
# ===========================================================================

def main():
    p = argparse.ArgumentParser(description="知识库入库 HTTP API 服务")
    p.add_argument("--embedding-model", default=EMBEDDING_MODEL,
                   help=f"向量模型名称（默认 {EMBEDDING_MODEL}）")
    p.add_argument("--host", default="0.0.0.0", help="监听 IP（默认 0.0.0.0）")
    p.add_argument("--port", type=int, default=8200, help="监听端口（默认 8200）")
    args = p.parse_args()

    import uvicorn
    if os.getenv("ENABLE_VECTOR_SEARCH", "false").lower() == "true":
        print(f"加载嵌入模型：{args.embedding_model}")
        _get_embedding_model(args.embedding_model)
    print(f"启动 API 服务 → http://{args.host}:{args.port}/docs")
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
