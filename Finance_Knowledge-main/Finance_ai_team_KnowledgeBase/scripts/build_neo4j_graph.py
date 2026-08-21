#!/usr/bin/env python3
"""从现有知识库(ES knowledge_chunks_kb*)构建 Neo4j 实体关系图 — build_neo4j_graph.py

无 LLM 方式：基于切片标题/内容规则抽取实体节点（错误码/测试用例/缺陷/规则/模块），
并建立 PART_OF、RELATED_TO 关系。让 searcher 的 Neo4j 关键词扩展(expand_keywords_neo4j)能命中。

用法（项目根目录）:
    python scripts/build_neo4j_graph.py            # 全量重建图谱
    python scripts/build_neo4j_graph.py --dry-run  # 只预览不写库
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DRY_RUN = "--dry-run" in sys.argv

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# 与 searcher/kb_search.py 的 _ALL_ENTITY_TYPES 保持一致
LABELS = ["TestCase", "BusinessRule", "Requirement", "Defect", "Module",
          "Account", "Security", "ErrorCode", "Permission", "OfficialRule"]

# 泛化/字段标签，不作为实体（否则扩展词全是"建议""案例"这类噪声）
NOISE_NAMES = {
    "建议", "案例", "症状", "步骤", "预期结果", "前置条件", "概述", "字段",
    "请求示例", "请求体", "成功响应", "常见失败", "返回字段", "接口列表",
    "核心原则", "错误码速查", "端口分配策略", "端口池信息", "查询端口",
    "接口列表", "统一响应格式", "完整接入示例", "租约与心跳", "发送心跳",
    "申请端口", "释放端口", "全部列表", "条件查询", "按智能体名称查询",
}


# ---------- ES 读取 ----------
def es_client():
    from elasticsearch import Elasticsearch
    return Elasticsearch([ES_HOST], request_timeout=30)


def read_all_chunks():
    """遍历 knowledge_chunks_kb* 索引取全部切片。"""
    es = es_client()
    indices = es.indices.get(index="knowledge_chunks*", allow_no_indices=True)
    chunks = []
    for index in sorted(indices):
        resp = es.search(index=index, query={"match_all": {}}, size=1000,
                         _source=["chunk_id", "title", "heading", "content", "kb_code", "doc_id"])
        for h in resp["hits"]["hits"]:
            chunks.append(h["_source"])
    return chunks


# ---------- 无 LLM 实体抽取 ----------
def doc_type_label(content: str, kb_code: str) -> str | None:
    """从文档元数据 doc_type（知识类型）推断主实体标签；找不到则按 kb_code 兜底。"""
    m = re.search(r"doc_type（知识类型）\s*\|\s*([a-z_]+)", content)
    if m:
        t = m.group(1)
        if "error_code" in t:
            return "ErrorCode"
        if "test_case" in t:
            return "TestCase"
        if "defect" in t:
            return "Defect"
        # 规范/标准/规则/指南 优先于 requirement（requirement_review_standard 是规范不是需求案例）
        if ("standard" in t or "spec" in t or "norm" in t or "guide" in t
                or "rule" in t or "regulation" in t or "official" in t or "guide" in t):
            return "OfficialRule"
        if "review_case" in t or "requirement" in t:
            return "Requirement"
        return "BusinessRule"
    return {
        "KB02": "OfficialRule", "KB03": "Requirement",
        "KB04": "TestCase", "KB05": "Defect", "KB06": "OfficialRule",
    }.get(kb_code)


def extract_entities(chunk: dict) -> list[dict]:
    """按规则从单个切片抽取实体。返回 [{label, name, description}, ...]"""
    title = chunk.get("title", "").strip()
    heading = chunk.get("heading", "").strip()
    content = chunk.get("content", "") or ""
    kb_code = chunk.get("kb_code", "")
    entities: list[dict] = []

    def add(label, name, desc):
        name = re.sub(r"\s+", " ", name).strip(" #-*|`：:，。").strip()
        name = re.sub(r"^(?:案例|建议|症状|步骤|预期结果|前置条件)\s*[：:]?\s*$", "", name).strip()
        if len(name) < 2 or name in NOISE_NAMES:
            return
        if any(name.startswith(p) for p in ("请求示例", "请求体", "成功响应", "常见失败", "返回字段", "接口列表")):
            return
        entities.append({"label": label, "name": name, "description": (desc or "").strip()[:300]})

    # 0) 文档主实体：按 doc_type 归类（文档标题作为该类型的实体）
    doc_label = doc_type_label(content, kb_code)
    if doc_label and title:
        add(doc_label, title, f"{doc_label} 文档：{title}")

    # 1) 错误码：ERR_XXX 格式（最终版）+ 数字码（旧版）
    for m in re.finditer(r"\|\s*`?([A-Z][A-Z0-9_]{3,})`?\s*\|\s*([^|\n]+?)\s*\|", content):
        code, desc = m.group(1), m.group(2).strip()
        add("ErrorCode", f"{code} {desc}", f"错误码 {code}：{desc}")
    for m in re.finditer(r"\|\s*(\d{3,5})\s*\|\s*([^|\n]+?)\s*\|", content):
        code, desc = m.group(1), m.group(2).strip()
        add("ErrorCode", f"{code} {desc}", f"错误码 {code}：{desc}")

    # 2) 测试用例：用例ID / 标题 / 用例N：标题
    for m in re.finditer(r"用例ID\s*[：:]\s*([^\n]+)", content):
        add("TestCase", m.group(1).strip(), f"测试用例：{m.group(1).strip()}")
    for m in re.finditer(r"标题\s*[：:]\s*([^\n]+)", content):
        add("TestCase", m.group(1).strip(), f"测试用例：{m.group(1).strip()}")
    for m in re.finditer(r"用例\s*(\d+)\s*[：:]\s*([^\n#]+)", content):
        add("TestCase", f"用例{m.group(1)} {m.group(2).strip()}", f"{heading}：{m.group(2).strip()}")

    # 3) 缺陷模式：## N. 名称（缺陷库旧格式）+ 缺陷标题：xxx（最终版）
    for m in re.finditer(r"缺陷标题\s*[：:]\s*([^\n]+)", content):
        add("Defect", m.group(1).strip(), f"缺陷案例：{m.group(1).strip()}")
    if kb_code == "KB05":
        for m in re.finditer(r"^#{2,3}\s+\d+[.、]\s*([^\n#]+)", content, re.M):
            add("Defect", m.group(1).strip(), f"缺陷模式：{m.group(1).strip()}")

    # 4) 评审规范章节：## 一、覆盖完整性（规范库旧格式）
    if kb_code == "KB06":
        for m in re.finditer(r"^#{2,3}\s+[一二三四五六七八九十]+、\s*([^\n#]+)", content, re.M):
            add("OfficialRule", m.group(1).strip(), f"评审规范：{m.group(1).strip()}")

    # 5) 业务规则：**先申请，后使用** 等加粗条款
    for m in re.finditer(r"\*\*([^*\n]{2,30}?)\*\*", content):
        add("BusinessRule", m.group(1).strip(), f"{heading} 中的规则：{m.group(1).strip()}")

    # 6) 章节标题本身作为实体（去重由 Cypher MERGE 保证）
    if heading and heading != title and len(heading) >= 3:
        add("Requirement", heading, f"{title} 的章节：{heading}")

    return entities


# ---------- Neo4j 写入 ----------
def build(chunks: list[dict]) -> dict:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    stats = {"modules": 0, "entities": 0, "part_of": 0, "related_to": 0}
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            if not DRY_RUN:
                session.run("MATCH (n) DETACH DELETE n")
                print("已清空旧图谱")

            # 按文档分组
            by_doc: dict[str, list[dict]] = defaultdict(list)
            for c in chunks:
                by_doc[c.get("title", "") or "未命名文档"].append(c)

            # 文档内实体（用于去重：同一实体只建一次 PART_OF）
            doc_entities: dict[str, dict] = {}  # (label,name) -> entity

            def merge_entity(session, ent, module_id):
                key = (ent["label"], ent["name"])
                if key in doc_entities:
                    return False
                doc_entities[key] = ent
                session.run(
                    f"MERGE (e:{ent['label']} {{name: $name, id: $id}}) "
                    "SET e.description = $desc, e.type = $label",
                    name=ent["name"], id=f"{ent['label']}::{ent['name']}",
                    desc=ent["description"], label=ent["label"],
                )
                session.run(
                    "MATCH (e {id: $eid}), (m:Module {id: $mid}) "
                    "MERGE (e)-[:PART_OF]->(m)",
                    eid=f"{ent['label']}::{ent['name']}", mid=module_id,
                )
                return True

            for title, doc_chunks in by_doc.items():
                module_name = re.sub(r"\s+", " ", title).strip()
                module_id = f"mod::{module_name}"
                if not DRY_RUN:
                    session.run(
                        "MERGE (m:Module {name: $name, id: $id, type: 'Module'}) "
                        "SET m.description = $desc",
                        name=module_name, id=module_id, desc=f"文档模块：{module_name}",
                    )
                stats["modules"] += 1

                # 第一遍：合并实体 + 建 PART_OF
                for chunk in doc_chunks:
                    for ent in extract_entities(chunk):
                        if not DRY_RUN:
                            merge_entity(session, ent, module_id)
                        stats["entities"] += 1
                        stats["part_of"] += 1

                # 第二遍：同一切片内共现的实体建 RELATED_TO（更贴近语义，图也清爽）
                seen_pairs = set()
                for chunk in doc_chunks:
                    in_chunk = []
                    for ent in extract_entities(chunk):
                        if ent["name"] == module_name:
                            continue
                        if (ent["label"], ent["name"]) in doc_entities and \
                           not any(x["name"] == ent["name"] for x in in_chunk):
                            in_chunk.append(ent)
                    for i in range(len(in_chunk)):
                        for j in range(i + 1, len(in_chunk)):
                            a, b = in_chunk[i], in_chunk[j]
                            if a["name"] == b["name"]:
                                continue
                            pair = tuple(sorted((a["name"], b["name"])))
                            if pair in seen_pairs:
                                continue
                            seen_pairs.add(pair)
                            if not DRY_RUN:
                                session.run(
                                    "MATCH (a {name: $a}), (b {name: $b}) "
                                    "WHERE labels(a)[0] <> 'Module' AND labels(b)[0] <> 'Module' "
                                    "MERGE (a)-[:RELATED_TO]->(b)",
                                    a=a["name"], b=b["name"],
                                )
                            stats["related_to"] += 1

            # 建约束/索引（可选，加速）
            if not DRY_RUN:
                for label in LABELS:
                    try:
                        session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.name)")
                    except Exception:
                        pass
    finally:
        driver.close()
    return stats


def main() -> None:
    print(f"读取 ES chunks（{ES_HOST}）...")
    chunks = read_all_chunks()
    print(f"共 {len(chunks)} 个切片\n")

    if not chunks:
        print("没有可用的切片，先跑 scripts/rebuild_knowledge_base.py")
        sys.exit(1)

    stats = build(chunks)
    print(f"{'预览' if DRY_RUN else '写入'}完成：")
    print(f"  Module 文档节点 : {stats['modules']}")
    print(f"  实体节点        : {stats['entities']}")
    print(f"  PART_OF 关系    : {stats['part_of']}")
    print(f"  RELATED_TO 关系 : {stats['related_to']}")

    if DRY_RUN:
        print("\n(未写库。去掉 --dry-run 执行正式写入)")


if __name__ == "__main__":
    main()
