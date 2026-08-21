#!/usr/bin/env python3
"""Rebuild the development knowledge base from Markdown source documents."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from elasticsearch import Elasticsearch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# ---------- 向量模型（延迟加载，为向量检索写入 embedding 字段） ----------
_embedding_model = None


def get_embedding_model():
    """加载 EMBEDDING_MODEL 指定的向量模型；失败时返回 None 并跳过向量写入。"""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
    print(f"加载向量模型：{model_name} ...")
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(model_name)
        dim_method = getattr(_embedding_model, "get_embedding_dimension", None) or _embedding_model.get_sentence_embedding_dimension
        print(f"  向量维度：{dim_method()}")
    except Exception as exc:
        print(f"  警告：向量模型加载失败，跳过 embedding 写入（{exc}）")
        _embedding_model = False  # False 表示加载失败，不再重试
    return _embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本转向量（L2 归一化）。模型不可用时返回空列表。"""
    model = get_embedding_model()
    if not model:
        return []
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


KB_BY_DIRECTORY = {
    "history_defects": "KB05",
    "standard_cases": "KB04",
    "test_specs": "KB06",
}
ALL_KB_CODES = tuple(f"KB{number:02d}" for number in range(1, 7))


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split Markdown by headings while preserving heading text."""
    chunks: list[tuple[str, str]] = []
    current_heading = "文档前言"
    current_lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if match and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append((current_heading, content))
            current_lines = []
        if match:
            current_heading = match.group(1).strip()
        current_lines.append(line)
    content = "\n".join(current_lines).strip()
    if content:
        chunks.append((current_heading, content))
    return chunks


def kb_code_for(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root)
    if relative.name == "端口管理接口文档.md":
        return "KB01"
    first_part = relative.parts[0] if relative.parts else ""
    # 新目录结构：KB01_系统业务知识库 / KB02_法规... 直接取 KB0N 前缀
    match = re.match(r"^(KB\d+)", first_part)
    if match:
        return match.group(1).upper()
    return KB_BY_DIRECTORY.get(first_part, "KB01")


def pg_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=int(os.getenv("PG_PORT", "5432")),
        dbname=os.getenv("PG_DBNAME", "knowledge_base"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


def es_client() -> Elasticsearch:
    return Elasticsearch(os.getenv("ES_HOST", "http://127.0.0.1:9200"))


def reset_storage(connection, elasticsearch: Elasticsearch) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS sys_config CASCADE")
        cursor.execute("DROP TABLE IF EXISTS public.kb_documents")
        cursor.execute("CREATE SCHEMA sys_config")
        cursor.execute(
            """
            CREATE TABLE sys_config.kb_registry (
                kb_code TEXT PRIMARY KEY,
                schema_name TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE public.kb_documents (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                kb_code TEXT NOT NULL,
                title TEXT NOT NULL,
                heading TEXT NOT NULL,
                source_file TEXT NOT NULL,
                content TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for kb_code in ALL_KB_CODES:
            cursor.execute(
                "INSERT INTO sys_config.kb_registry(kb_code, schema_name) VALUES(%s, 'public')",
                (kb_code,),
            )
    connection.commit()

    for index in elasticsearch.indices.get(index="knowledge_chunks*", allow_no_indices=True):
        elasticsearch.indices.delete(index=index)


def ensure_index(elasticsearch: Elasticsearch, index: str, vector_dim: int = 768) -> None:
    elasticsearch.indices.create(
        index=index,
        mappings={
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "kb_code": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "smartcn", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                "heading": {"type": "text", "analyzer": "smartcn", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                "content": {"type": "text", "analyzer": "smartcn"},
                "source_file": {"type": "keyword"},
                "meta_fields": {"type": "object"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": vector_dim,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        },
    )


def rebuild(source_root: Path) -> tuple[int, int]:
    files = sorted(
        f for f in source_root.rglob("*.md")
        if not f.relative_to(source_root).parts
        or not f.relative_to(source_root).parts[0].startswith("00_")
    )
    if not files:
        raise FileNotFoundError(f"未找到 Markdown 知识源：{source_root}")

    connection = pg_connection()
    elasticsearch = es_client()
    try:
        reset_storage(connection, elasticsearch)
        vector_dim = 768
        embedding_model = get_embedding_model()
        if embedding_model:
            dim_method = getattr(embedding_model, "get_embedding_dimension", None) or embedding_model.get_sentence_embedding_dimension
            vector_dim = dim_method()
        indices = {
            code: f"knowledge_chunks_{code.lower()}"
            for code in ALL_KB_CODES
        }
        for index in indices.values():
            ensure_index(elasticsearch, index, vector_dim=vector_dim)

        chunk_count = 0
        seen_content: set[str] = set()  # 去重：相同内容只录入一次
        with connection.cursor() as cursor:
            for path in files:
                text = path.read_text(encoding="utf-8")
                kb_code = kb_code_for(path, source_root)
                doc_id = hashlib.sha256(str(path.relative_to(source_root)).encode()).hexdigest()[:24]
                chunks = list(chunk_markdown(text))
                vectors = embed_texts([content for _, content in chunks])
                for position, ((heading, content), vector) in enumerate(zip(chunks, vectors)):
                    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if content_hash in seen_content:
                        continue  # 跳过重复内容（多个文档共用的通用章节只留第一份）
                    seen_content.add(content_hash)
                    chunk_id = f"{doc_id}_{position:04d}"
                    cursor.execute(
                        """
                        INSERT INTO public.kb_documents(
                            chunk_id, doc_id, kb_code, title, heading, source_file, content
                        ) VALUES(%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chunk_id,
                            doc_id,
                            kb_code,
                            path.stem,
                            heading,
                            str(path.relative_to(source_root)),
                            content,
                        ),
                    )
                    document = {
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "kb_code": kb_code,
                        "title": path.stem,
                        "heading": heading,
                        "content": content,
                        "source_file": str(path.relative_to(source_root)),
                        "meta_fields": {"kb_code": kb_code},
                    }
                    if vector:
                        document["embedding"] = vector
                    elasticsearch.index(
                        index=indices[kb_code],
                        id=chunk_id,
                        document=document,
                    )
                    chunk_count += 1
        connection.commit()
        for index in indices.values():
            elasticsearch.indices.refresh(index=index)
        return len(files), chunk_count
    finally:
        connection.close()
        elasticsearch.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT.parent / "Finance_Agent" / "docs",
    )
    args = parser.parse_args()
    file_count, chunk_count = rebuild(args.source.resolve())
    print(f"知识库重建完成：{file_count} 个文档，{chunk_count} 个切片")


if __name__ == "__main__":
    main()
