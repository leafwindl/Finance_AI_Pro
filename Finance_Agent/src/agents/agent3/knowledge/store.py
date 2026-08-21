# src/knowledge/store.py
"""
ChromaDB 向量存储 — 三维知识库的构建与检索。

三个 Collection：
  kb_history_defects  — 历史缺陷与经验
  kb_standard_cases   — 标准测试用例参考
  kb_test_specs       — ISTQB 测试规范与模板

用法：
  from src.knowledge.store import build_collections
  from src.knowledge.store import (retrieve_history_defects,
                                    retrieve_standard_cases,
                                    retrieve_test_specs)
"""
import os
import re
from typing import Optional

import chromadb
from chromadb.config import Settings

# ---- 项目根目录 ----
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- ChromaDB 持久化目录 ----
_DEFAULT_PERSIST_DIR = os.path.join(_PROJECT_DIR, "chroma_db")

# ---- 三个知识库目录 ----
_KB_DIRS = {
    "kb_history_defects": os.path.join(_PROJECT_DIR, "docs", "history_defects"),
    "kb_standard_cases": os.path.join(_PROJECT_DIR, "docs", "standard_cases"),
    "kb_test_specs": os.path.join(_PROJECT_DIR, "docs", "test_specs"),
}

# ---- 全局客户端（惰性初始化） ----
_client: Optional[chromadb.PersistentClient] = None


def _get_client() -> chromadb.PersistentClient:
    """获取或创建 ChromaDB 持久化客户端"""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=_DEFAULT_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


# ==========================================
# 文档加载
# ==========================================
def _load_docs_from_dir(dir_path: str) -> list[dict]:
    """从目录加载所有 .md（或 .txt）文件，返回 [{"id":..., "content":...}]"""
    docs = []
    if not os.path.isdir(dir_path):
        return docs
    for fname in sorted(os.listdir(dir_path)):
        if not fname.endswith((".md", ".txt")):
            continue
        fpath = os.path.join(dir_path, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception:
            content = ""
        if not content:
            continue
        doc_id = os.path.splitext(fname)[0]
        docs.append({"id": doc_id, "content": content, "source": fname})
    return docs


# ==========================================
# 知识库构建
# ==========================================
def build_collections(persist_dir: Optional[str] = None) -> None:
    """
    扫描 docs/ 下三个子目录，为每个目录构建 ChromaDB collection。
    若 collection 已存在则先删除重建（幂等操作）。
    """
    if persist_dir:
        global _DEFAULT_PERSIST_DIR, _client
        _DEFAULT_PERSIST_DIR = persist_dir
        _client = None  # 强制重建客户端

    client = _get_client()
    total = 0

    for coll_name, dir_path in _KB_DIRS.items():
        docs = _load_docs_from_dir(dir_path)
        if not docs:
            print(f"  [WARN] {coll_name}: 目录为空或无 .md 文件，跳过")
            continue

        # 删除已有 collection（幂等重建）
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass

        coll = client.create_collection(
            name=coll_name,
            metadata={"description": f"知识库: {coll_name}"},
        )

        ids = [d["id"] for d in docs]
        documents = [d["content"] for d in docs]
        metadatas = [{"source": d["source"]} for d in docs]

        coll.add(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  [OK] {coll_name}: 已加载 {len(docs)} 篇文档")
        total += len(docs)

    print(f"\n知识库构建完成！共 {total} 篇文档，3 个 Collection。")


# ==========================================
# 检索接口
# ==========================================
def _retrieve_from_collection(
    coll_name: str,
    query: str,
    top_k: int = 8,
) -> str:
    """
    从指定 collection 检索与 query 最相关的文档。
    返回拼接的上下文字符串，若失败返回空字符串提示。
    """
    if not query or not query.strip():
        return "（未提供检索关键词）"

    client = _get_client()

    try:
        coll = client.get_collection(coll_name)
    except Exception:
        return f"（知识库 '{coll_name}' 尚未构建，请先运行 python -m src.knowledge.builder）"

    if coll.count() == 0:
        return f"（知识库 '{coll_name}' 为空）"

    try:
        results = coll.query(
            query_texts=[query.strip()],
            n_results=min(top_k, coll.count()),
        )
    except Exception as e:
        return f"（检索失败: {str(e)}）"

    docs = results.get("documents", [[]])[0]
    if not docs:
        return "（知识库未检索到相关内容）"

    parts = [f"\n【{coll_name} 检索结果】"]
    for i, doc in enumerate(docs, 1):
        # 截断过长文档，保留核心内容
        if len(doc) > 2000:
            doc = doc[:2000] + "\n...(内容过长，已截断)"
        parts.append(f"--- 片段 {i} ---\n{doc}")
    return "\n".join(parts)


def retrieve_history_defects(query: str, top_k: int = 8) -> str:
    """检索历史缺陷与经验知识库"""
    print(f"  检索历史缺陷与经验... (query: {query[:80]}...)")
    result = _retrieve_from_collection("kb_history_defects", query, top_k)
    hit_count = result.count("片段 ")
    print(f"    命中 {hit_count} 条")
    return result


def retrieve_standard_cases(query: str, top_k: int = 8) -> str:
    """检索标准测试用例知识库"""
    print(f"  检索标准测试用例... (query: {query[:80]}...)")
    result = _retrieve_from_collection("kb_standard_cases", query, top_k)
    hit_count = result.count("片段 ")
    print(f"    命中 {hit_count} 条")
    return result


def retrieve_test_specs(query: str, top_k: int = 8) -> str:
    """检索测试规范与模板知识库"""
    print(f"  检索测试规范与模板... (query: {query[:80]}...)")
    result = _retrieve_from_collection("kb_test_specs", query, top_k)
    hit_count = result.count("片段 ")
    print(f"    命中 {hit_count} 条")
    return result
