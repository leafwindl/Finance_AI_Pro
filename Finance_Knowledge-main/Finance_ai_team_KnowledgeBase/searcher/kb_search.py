#!/usr/bin/env python3
"""
知识库统一检索模块 — kb_search.py
========================================
实现三段式检索管线：Neo4j 图谱关键词扩展 → ES BM25+向量混合检索 → PG 元数据溯源。

使用现有基础设施：
    - db_conn.py  → 三库连接（PG / ES / Neo4j）
    - utils.py    → BGE-large-zh-v1.5 向量化

用法（在项目根目录下运行）：
    python -m src.kb_search "创业板买入权限"            # 默认三段式管线
    python -m src.kb_search "权限" --mode es            # 仅 ES 检索
    python -m src.kb_search "委托" --mode pg            # 仅 PG 搜索
    python -m src.kb_search "风控" --mode neo4j         # 仅 Neo4j 图谱检索
    python -m src.kb_search "权限" --expand-k 5 --top-k 10
"""

import sys
import json
import logging
import argparse
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from searcher.db_conn import (
    get_pg_conn,
    get_es_client,
    get_neo4j_driver,
    list_all_es_indexes,
    route_es_index,
)
from shared.embedding import text_to_vector

# ---------- 日志 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kb_search")

# ---------- ES 索引名（与 sync_pipeline.py 保持一致） ----------
ES_INDEX_NAME = "kb_chunks"

# 多样性控制：最终每个章节只保留 1 个最高分 chunk，防止标题加权后重复章节霸屏
MAX_CHUNKS_PER_DOC = 1
NEO4J_CORE_TERM_LIMIT = 3

# 查询中的功能词和提问套话不应进入 Neo4j 实体扩展。
_QUERY_FUNCTION_WORDS = {
    "请", "帮我", "我", "想", "查询", "查找", "了解", "说明", "介绍",
    "是否", "能否", "可以", "如何", "怎么", "为什么", "哪些", "哪个",
    "什么", "哪里", "以及", "和", "与", "或", "的", "了", "着", "在",
    "对", "从", "到", "为", "被", "让", "吗", "呢", "吧", "啊", "呀",
}

# ---------- 所有 Neo4j 实体类型（与 entity_extractor.py 保持一致） ----------
_ALL_ENTITY_TYPES = [
    "TestCase", "BusinessRule", "Requirement", "Defect",
    "Module", "Account", "Security", "ErrorCode",
    "Permission", "OfficialRule",
]


def _load_jieba():
    """延迟加载 jieba 分词器。"""
    try:
        import jieba
        return jieba
    except ImportError:
        logger.error(
            "缺少 jieba 依赖，请执行: pip install jieba\n"
            "亦可屏蔽 Neo4j 扩展直接检索: python -m src.kb_search \"查询\" --mode es"
        )
        raise


def _kb_of_name(name: str) -> str:
    """从实体/模块名提取 KB0N 前缀；不是 KB0N 开头返回空串。"""
    name = name or ""
    if name[:2] == "KB" and len(name) >= 4 and name[2:4].isdigit():
        return name[:4]
    return ""


def _seed_match_score(query_text: str, name: str) -> int:
    """种子名与查询的最长公共子串长度（越大 = 匹配证据越强）。"""
    name = name or ""
    best = 0
    q = len(query_text)
    for i in range(q):
        for j in range(q, i, -1):
            if j - i <= best:
                break
            if query_text[i:j] in name:
                best = j - i
                break
    return best


def _extract_core_keywords(query_text: str, limit: int = NEO4J_CORE_TERM_LIMIT) -> List[str]:
    """提取并排序查询核心词，只保留适合图谱扩展的名词和动词。

    名词优先于动词；更长的业务术语、编号和靠前的词优先。这里只做轻量
    规则排序，不引入额外模型，避免为了扩展关键词增加一次模型调用。
    """
    try:
        import jieba.posseg as posseg
    except ImportError:
        return []

    candidates: Dict[str, float] = {}
    for position, item in enumerate(posseg.lcut(query_text)):
        term = item.word.strip()
        flag = (item.flag or "").lower()
        if not term or term in _QUERY_FUNCTION_WORDS:
            continue
        is_code = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{1,}", term))
        is_noun = flag.startswith("n")
        is_verb = flag.startswith("v")
        if not (is_code or is_noun or is_verb):
            continue
        if len(term) < 2 and not is_code:
            continue

        score = 4.0 if is_code else (3.0 if is_noun else 2.0)
        score += min(len(term), 8) * 0.12
        score += max(0.0, 0.3 - position * 0.01)
        candidates[term] = max(candidates.get(term, 0.0), score)

    ranked = sorted(candidates, key=lambda term: (-candidates[term], term))
    return ranked[:max(1, limit)]


def expand_keywords_neo4j(query_text: str, top_k: int = 3) -> dict:
    """
    在图谱中查找与查询相关的实体，沿关联边扩展相邻实体名作为扩展关键词。

    流程：
        1. jieba 词性分词，只保留排序后的核心名词/动词匹配实体 name/description
        2. 匹配到的实体作为"种子节点"，并通过 PART_OF 定位其所属知识库(KB0N)
        3. 按"种子名与查询的最长匹配"判定查询所属知识库，只保留同库种子
        4. 沿种子节点的一跳关联边（任意方向）收集同库、且非文档名的相邻实体
        5. 去重后返回 top_k 个扩展关键词

    参数:
        query_text (str): 原始查询文本。
        top_k      (int): 最多返回的关键词数量。

    返回:
        dict: {
            "keywords": ["扩展词1", ...],
            "seed_entities": [{...}, ...],
            "related_entities": [{...}, ...],
            "error": ""
        }
    """
    result = {
        "keywords": [],
        "seed_entities": [],
        "related_entities": [],
        "error": "",
    }

    try:
        core_limit = max(1, min(NEO4J_CORE_TERM_LIMIT, top_k))
        core_keywords = _extract_core_keywords(query_text, limit=core_limit)
    except Exception as e:
        result["error"] = f"核心词提取失败: {e}"
        return result
    result["core_keywords"] = core_keywords
    if not core_keywords:
        result["error"] = "未提取到可用于 Neo4j 扩展的核心词"
        return result

    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            seeds: List[dict] = []
            for token in core_keywords:
                cypher_parts = []
                for etype in _ALL_ENTITY_TYPES:
                    cypher_parts.append(
                        f"MATCH (e:{etype}) "
                        f"WHERE e.name CONTAINS $token OR coalesce(e.description, '') CONTAINS $token "
                        f"OPTIONAL MATCH (e)-[:PART_OF]->(m:Module) "
                        f"RETURN e.name AS name, e.id AS id, labels(e)[0] AS type, "
                        f"       coalesce(e.description, '') AS description, "
                        f"       coalesce(m.name, '') AS module_name "
                        f"LIMIT 3"
                    )
                full_cypher = "\nUNION\n".join(cypher_parts)
                r = session.run(full_cypher, token=token)
                for rec in r:
                    d = dict(rec)
                    d["kb_code"] = (_kb_of_name(d.get("module_name", ""))
                                    or _kb_of_name(d.get("name", "")))
                    seeds.append(d)

            if not seeds:
                return result

            # 判定查询所属知识库：取"种子名与查询最长匹配"得分最高的 KB
            kb_score: dict[str, int] = {}
            for s in seeds:
                kb = s.get("kb_code", "")
                if not kb:
                    continue
                score = _seed_match_score(query_text, s.get("name", ""))
                kb_score[kb] = kb_score.get(kb, 0) + score
            target_kb = max(kb_score, key=kb_score.get) if kb_score else ""
            if not target_kb:
                result["error"] = "无法判定查询所属知识库，跳过扩展"
                return result

            # 只保留同库种子
            seed_entities = [s for s in seeds if s.get("kb_code") == target_kb]
            if not seed_entities:
                return result
            result["seed_entities"] = seed_entities[:top_k * 3]

            # 沿种子一跳扩展，只收同库、非文档名实体
            seed_names = list({s["name"] for s in seed_entities})
            related_cypher = (
                "MATCH (a)-[r]-(b) "
                "WHERE a.name IN $names AND b.name IS NOT NULL "
                "OPTIONAL MATCH (b)-[:PART_OF]->(m:Module) "
                "RETURN DISTINCT b.name AS name, labels(b)[0] AS type, "
                "       coalesce(m.name, '') AS module_name "
                "LIMIT $limit"
            )
            r2 = session.run(related_cypher, names=seed_names, limit=top_k * 20)
            related: List[dict] = []
            for rec in r2:
                d = dict(rec)
                if d.get("type") == "Module":
                    continue  # 文档名不当扩展关键词
                if _kb_of_name(d.get("module_name", "")) != target_kb:
                    continue  # 只留同知识库实体
                related.append(d)

            result["related_entities"] = related[:top_k * 3]

            keywords = []
            kw_seen: Set[str] = set()
            for item in related:
                name = item["name"].strip()
                if not name or name.lower() == query_text.lower():
                    continue
                if _is_noise_keyword(name):
                    continue
                if name not in kw_seen:
                    kw_seen.add(name)
                    keywords.append(name)

            result["keywords"] = keywords[:top_k]

    except Exception as e:
        result["error"] = f"Neo4j 查询失败: {e}"
        logger.warning("Neo4j 关键词扩展失败: %s", e)

    return result


def _query_tokens(query_text: str) -> List[str]:
    """返回用于 BM25 词项加权的核心词，不包含功能词。"""
    return _extract_core_keywords(query_text, limit=NEO4J_CORE_TERM_LIMIT)


# 扩展关键词噪声：文档模板文本 / 文档名，不应当作关键词
_NOISE_KW = [
    "适用边界", "整合审核状态", "文档登记信息", "核验要求", "来源说明",
    "官方法规", "交易所规则", "功能说明", "模块说明", "业务规则",
    "需求评审案例", "测试用例", "缺陷", "规范", "模板", "章节",
]
_NOISE_RE = None


def _is_noise_keyword(name: str) -> bool:
    """判断扩展词是否是文档模板噪声（文档名/适用边界等）。"""
    global _NOISE_RE
    if _NOISE_RE is None:
        import re as _re
        _NOISE_RE = _re.compile("|".join(map(_re.escape, _NOISE_KW)))
    if _NOISE_RE.search(name):
        return True
    # 文档编号样式（KB01-01 / REG-ZJQ- / 官方法规02 等）
    if len(name) > 20 and (name.startswith("KB0") or name.startswith("REG-ZJQ")
                           or "：" in name or "：" in name):
        return True
    return False


def search_es_bm25(
    query_text: str,
    expanded_keywords: List[str],
    top_k: int = 10,
    *,
    index_name: str = ES_INDEX_NAME,
    kb_code: str = "",
) -> List[dict]:
    """ES BM25 全文检索：jieba 分词多词召回 + 标题/章节加权，任意关键词命中即入选。

    结构演进：
      ① 最初   must(整句 match)：整句黑盒打分，无通道
      ② 上一版 must(整句) + should(多词) + minimum_should_match 60%：5 词查询要命中
                ≥3 词才进结果，BM25 常凑不满 top_k（实测 4/5）
      ③ 现在   「扁平 should + minimum_should_match=1」+ 标题/章节加权：
                - 正文：整句 boost 1.6 / jieba 词 1.0 / Neo4j 扩展词 0.8
                - 标题：整句 boost 2.0 / 词 1.5（温和档，避免同文档多 chunk 霸屏）
                - 章节：整句 boost 1.5 / 词 1.0
    (标题加权会让同文档所有 chunk 同分升高 → 配合 limit_chunks_per_doc 每篇文章只保留 1 个最高分 chunk)
    任意一个关键词命中即召回，BM25 累加打分让多命中文档 + 标题命中文档自然靠前。
    """
    es = get_es_client()
    try:
        # 用 jieba 把查询切成多个关键词（长度>=2），避免整句当一个 match 导致切词不准
        toks = _query_tokens(query_text)
        # 正文通道（历史沿用）
        content_clauses = (
            [{"match": {"content": {"query": query_text, "boost": 1.6}}}]
            + [{"match": {"content": {"query": t, "boost": 1.0}}} for t in toks]
            + [{"match": {"content": {"query": kw, "boost": 0.8}}} for kw in expanded_keywords]
        )
        # 标题通道：标题=文档身份，命中即强相关（温和档，避免同文档多 chunk 霸屏）
        title_clauses = (
            [{"match": {"title": {"query": query_text, "boost": 2.0}}}]
            + [{"match": {"title": {"query": t, "boost": 1.5}}} for t in toks]
        )
        # 章节通道
        heading_clauses = (
            [{"match": {"heading": {"query": query_text, "boost": 1.5}}}]
            + [{"match": {"heading": {"query": t, "boost": 1.0}}} for t in toks]
        )
        should_clauses = content_clauses + title_clauses + heading_clauses
        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1,
                }
            },
            "_source": {"excludes": ["embedding"]},
        }
        resp = es.search(index=index_name, body=body)
        hits: List[dict] = []
        for h in resp["hits"]["hits"]:
            src = h["_source"]
            hits.append({
                "score": h["_score"],
                "chunk_id": src.get("chunk_id", ""),
                "doc_id": src.get("doc_id", ""),
                "title": src.get("title", ""),
                "heading": src.get("heading", "") or src.get("title", ""),
                "content": src.get("content", ""),
                "source_file": src.get("source_file", ""),
                "content_hash": src.get("content_hash", ""),
                "kb_code": kb_code or src.get("meta_fields", {}).get("kb_code", ""),
            })
        return hits
    except Exception as e:
        logger.error("ES BM25 检索失败: %s", e)
        return []


def search_es_vector(
    query_text: str,
    expanded_keywords: List[str],
    top_k: int = 10,
    *,
    index_name: str = ES_INDEX_NAME,
    kb_code: str = "",
) -> List[dict]:
    """ES 向量相似度检索：将查询文本向量化后，用 cosineSimilarity 检索。"""
    es = get_es_client()
    try:
        combined = query_text
        if expanded_keywords:
            combined = query_text + " " + " ".join(expanded_keywords)
        query_vec = text_to_vector(combined)
        body = {
            "size": top_k,
            # 相似度下限：score = cosine+1，min_score=1.3 即 cosine≥0.3。
            # 无意义/无关查询不再返回"最近邻凑数"结果（此前垃圾查询也能命中任意文档）。
            "min_score": 1.3,
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": query_vec.tolist()},
                    },
                }
            },
            "_source": {"excludes": ["embedding"]},
        }
        resp = es.search(index=index_name, body=body)
        hits: List[dict] = []
        for h in resp["hits"]["hits"]:
            src = h["_source"]
            hits.append({
                "score": h["_score"],
                "chunk_id": src.get("chunk_id", ""),
                "doc_id": src.get("doc_id", ""),
                "title": src.get("title", ""),
                "heading": src.get("heading", "") or src.get("title", ""),
                "content": src.get("content", ""),
                "source_file": src.get("source_file", ""),
                "content_hash": src.get("content_hash", ""),
                "kb_code": kb_code or src.get("meta_fields", {}).get("kb_code", ""),
            })
        return hits
    except Exception as e:
        logger.error("ES 向量检索失败: %s", e)
        return []


def merge_deduplicate_es_hits(bm25_hits: List[dict], vector_hits: List[dict]) -> List[dict]:
    """融合 BM25 和向量两份检索结果，按 chunk_id 去重。

    不再直接比较两种分数（BM25 无上限、向量只有 0~2，比大小会让 BM25 高分
    盖掉语义命中），而是用 Reciprocal Rank Fusion（RRF）按"排名"融合：
        RRF = Σ 1/(K + rank)，K 取 60
    某条只在其中一份里出现，就只加那一份的项。融合分越大 = 综合越相关。
    同时保留每条的原始分：bm25_score（BM25 原始分）/ vector_score（向量原始分）。
    """
    K = 60
    rrf: Dict[str, float] = {}
    combined: Dict[str, dict] = {}
    bm25_raw: Dict[str, float] = {}
    vector_raw: Dict[str, float] = {}
    for source_tag, hits in [("bm25", bm25_hits), ("vector", vector_hits)]:
        for rank, h in enumerate(hits, 1):
            cid = h.get("chunk_id", "")
            if not cid:
                continue
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K + rank)
            if source_tag == "bm25":
                bm25_raw[cid] = h["score"]
            else:
                vector_raw[cid] = h["score"]
            if cid not in combined:
                combined[cid] = {**h, "source": source_tag}
            elif source_tag == "bm25":
                # 两份都命中同一块时，保留 BM25 的数据，来源标记为融合
                combined[cid] = {**h, "source": "bm25+vector"}
    out: List[dict] = []
    for cid, score in rrf.items():
        item = dict(combined[cid])
        item["score"] = score            # 融合分，用于排序
        item["bm25_score"] = bm25_raw.get(cid)   # 原始 BM25 分（可能为 None）
        item["vector_score"] = vector_raw.get(cid)  # 原始向量分（可能为 None）
        out.append(item)
    return sorted(out, key=lambda x: x["score"], reverse=True)


def normalize_title_key(title: str) -> str:
    """标准化标题，用于按文章去重（过滤同一标题的重复 chunk）。"""
    t = (title or "").strip().lower()
    t = re.sub(r"[\s　]+", "", t)
    t = re.sub(r"[：:，。！？、（）()\-\[\]【】/\\]+", "", t)
    return t


def section_key(hit: dict) -> str:
    """章节级去重 key：同一文档同一章节只保留最高分 chunk。"""
    doc_id = (hit.get("doc_id") or "").strip()
    heading = normalize_title_key(hit.get("heading", "") or hit.get("title", ""))
    if doc_id and heading:
        return f"section:{doc_id}|{heading}"
    if doc_id:
        return f"doc:{doc_id}"
    if heading:
        return f"title:{heading}"
    return f"chunk:{hit.get('chunk_id', '')}"


def limit_chunks_per_doc(hits: List[dict], max_per_doc: int = MAX_CHUNKS_PER_DOC) -> List[dict]:
    """章节级去重：每个章节最多保留 max_per_doc 个最高分 chunk（默认 1 个）。

    标题加权后，同一章节的多个 chunk 可能获得相同标题加分，因此按
    doc_id + heading 聚合，只保留同一章节得分最高的 chunk。
    """
    if max_per_doc <= 1:
        best_by_article: Dict[str, dict] = {}
        for h in hits:
            key = section_key(h)
            current = best_by_article.get(key)
            if current is None or h.get("score", 0.0) > current.get("score", 0.0):
                best_by_article[key] = h
        return sorted(best_by_article.values(), key=lambda x: x.get("score", 0.0), reverse=True)

    seen: Dict[str, int] = {}
    out: List[dict] = []
    for h in hits:
        key = section_key(h)
        if seen.get(key, 0) >= max_per_doc:
            continue
        seen[key] = seen.get(key, 0) + 1
        out.append(h)
    return out


def lookup_pg_by_chunk_ids(chunk_ids: List[str]) -> Dict[str, dict]:
    """根据 chunk_id 列表，在 PG 的 kb_documents 表中查询对应文档元数据。"""
    if not chunk_ids:
        return {}
    conn = get_pg_conn()
    cursor = conn.cursor()
    results: Dict[str, dict] = {}
    try:
        cursor.execute(
            "SELECT chunk_id, doc_id, title, source_file, content, version, updated_at "
            "FROM kb_documents WHERE chunk_id = ANY(%s)",
            (chunk_ids,),
        )
        for chunk_id, doc_id, title, source_file, content, version, updated_at in cursor.fetchall():
            results[chunk_id] = {
                "chunk_id": chunk_id, "doc_id": doc_id, "title": title,
                "source_file": source_file, "content_preview": (content or "")[:200],
                "version": version, "updated_at": str(updated_at) if updated_at else "",
            }
    except Exception as e:
        logger.error("PG 溯源查询失败: %s", e)
    finally:
        cursor.close()
    return results


def run_pipeline(
    query_text: str,
    top_k: int = 10,
    expand_k: int = 3,
    skip_neo4j: bool = False,
    kb_codes: Optional[List[str]] = None,
) -> dict:
    """完整三段式检索管线。"""
    result = {"query": query_text, "neo4j_expansion": {}, "es_results": {}, "merged_hits": [], "pg_metadata": {}}

    neo4j_enabled = os.getenv("ENABLE_NEO4J", "false").lower() == "true"
    if not skip_neo4j and neo4j_enabled:
        print(f"  [Stage 1/3] Neo4j 关键词扩展 (top {expand_k}) ...", file=sys.stderr)
        expansion = expand_keywords_neo4j(query_text, top_k=expand_k)
        result["neo4j_expansion"] = expansion
        keywords = expansion.get("keywords", [])
        if expansion.get("error"):
            print(f"    Warning: {expansion['error']}", file=sys.stderr)
    else:
        keywords = []
        result["neo4j_expansion"] = {"keywords": [], "error": "skipped"}

    print(f"  [Stage 2/3] ES 混合检索 (原词 + {len(keywords)} 扩展词) ...", file=sys.stderr)
    requested_codes = list(dict.fromkeys(kb_codes or []))
    targets = (
        [(route_es_index(code), code) for code in requested_codes]
        if requested_codes
        else [(list_all_es_indexes(), "")]
    )
    bm25_hits: List[dict] = []
    vector_hits: List[dict] = []
    vector_enabled = os.getenv("ENABLE_VECTOR_SEARCH", "false").lower() == "true"
    # 文章级去重后仍要尽量填满 top_k，所以内部候选池要大于最终返回数。
    candidate_k = max(top_k * 3, top_k + 10)
    for index_name, kb_code in targets:
        bm25_hits.extend(
            search_es_bm25(
                query_text, keywords, top_k=candidate_k,
                index_name=index_name, kb_code=kb_code,
            )
        )
        if vector_enabled:
            vector_hits.extend(
                search_es_vector(
                    query_text, keywords, top_k=candidate_k,
                    index_name=index_name, kb_code=kb_code,
                )
            )
    merged = merge_deduplicate_es_hits(bm25_hits, vector_hits)
    merged = limit_chunks_per_doc(merged, max_per_doc=MAX_CHUNKS_PER_DOC)
    result["es_results"] = {"bm25_count": len(bm25_hits), "vector_count": len(vector_hits), "merged_count": len(merged)}
    result["merged_hits"] = merged[:top_k]

    print(f"  [Stage 3/3] PG 溯源 (共 {len(merged)} 个唯一切片) ...", file=sys.stderr)
    chunk_ids = list({h["chunk_id"] for h in merged if h.get("chunk_id")})
    if chunk_ids:
        result["pg_metadata"] = lookup_pg_by_chunk_ids(chunk_ids)
    return result


def search_es_standalone(query_text: str, top_k: int = 10) -> dict:
    """独立 ES 模式。"""
    candidate_k = max(top_k * 3, top_k + 10)
    bm25 = search_es_bm25(query_text, [], top_k=candidate_k)
    vec = search_es_vector(query_text, [], top_k=candidate_k)
    merged = merge_deduplicate_es_hits(bm25, vec)
    merged = limit_chunks_per_doc(merged, max_per_doc=MAX_CHUNKS_PER_DOC)
    for h in merged:
        h["text_preview"] = (h.get("content", "") or "")[:150]
    return {"source": "ES", "method": "BM25 + Vector", "total": len(merged), "bm25_hits": len(bm25), "vector_hits": len(vec), "hits": merged[:top_k]}


def search_pg_standalone(query_text: str, top_k: int = 10) -> dict:
    """独立 PG 模式。"""
    conn = get_pg_conn()
    cursor = conn.cursor()
    hits: List[dict] = []
    try:
        cursor.execute(
            "SELECT chunk_id, doc_id, title, content, source_file, version, updated_at "
            "FROM kb_documents WHERE title ILIKE %s OR content ILIKE %s "
            "ORDER BY char_length(title) LIMIT %s",
            (f"%{query_text}%", f"%{query_text}%", top_k),
        )
        for chunk_id, doc_id, title, content, source_file, version, updated_at in cursor.fetchall():
            hits.append({
                "chunk_id": chunk_id, "doc_id": doc_id, "title": title,
                "content_preview": (content or "")[:200], "source_file": source_file,
                "version": version, "updated_at": str(updated_at) if updated_at else "",
            })
    except Exception as e:
        logger.error("PG 独立检索失败: %s", e)
    finally:
        cursor.close()
    return {"source": "PG", "method": "SQL ILIKE", "total": len(hits), "hits": hits}


def search_neo4j_standalone(query_text: str, top_k: int = 10) -> dict:
    """独立 Neo4j 模式。"""
    export = {"source": "Neo4j", "method": "Cypher CONTAINS", "total": 0, "hits": []}
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            all_hits: List[dict] = []
            for etype in _ALL_ENTITY_TYPES:
                r = session.run(
                    f"MATCH (e:{etype}) WHERE e.name CONTAINS $q OR coalesce(e.description, '') CONTAINS $q "
                    f"RETURN e.id AS id, e.name AS name, labels(e)[0] AS entity_type, "
                    f"coalesce(e.description, '') AS description LIMIT $k",
                    q=query_text, k=top_k,
                )
                for rec in r:
                    d = dict(rec)
                    all_hits.append({
                        "id": d.get("id", ""), "name": d.get("name", ""),
                        "entity_type": d.get("entity_type", ""),
                        "description": (d.get("description", "") or "")[:200],
                    })
            seen = set()
            unique = []
            for h in all_hits:
                k = f"{h['id']}|{h['entity_type']}"
                if k not in seen:
                    seen.add(k)
                    unique.append(h)
            export["total"] = len(unique)
            export["hits"] = sorted(unique, key=lambda x: len(x["name"]))[:top_k]
    except Exception as e:
        export["error"] = str(e)
    return export


def main() -> None:
    p = argparse.ArgumentParser(description="知识库统一检索（Neo4j 图谱扩展 → ES 混合 → PG 溯源）")
    p.add_argument("query", nargs="+", help="查询文本")
    p.add_argument("--mode", "-m", choices=["pipe", "es", "pg", "neo4j"], default="pipe")
    p.add_argument("--top-k", "-k", type=int, default=10)
    p.add_argument("--expand-k", "-e", type=int, default=3)
    p.add_argument("--skip-neo4j", action="store_true")
    p.add_argument("--json", "-j", action="store_true")
    args = p.parse_args()
    query_text = " ".join(args.query)

    if args.mode == "pipe":
        result = run_pipeline(query_text, top_k=args.top_k, expand_k=args.expand_k, skip_neo4j=args.skip_neo4j)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_pipeline_summary(result, args.top_k)
    elif args.mode == "es":
        _print_standalone_summary(search_es_standalone(query_text, top_k=args.top_k))
    elif args.mode == "pg":
        _print_standalone_summary(search_pg_standalone(query_text, top_k=args.top_k))
    elif args.mode == "neo4j":
        _print_standalone_summary(search_neo4j_standalone(query_text, top_k=args.top_k))


def _print_pipeline_summary(result: dict, top_k: int) -> None:
    exp = result["neo4j_expansion"]
    es = result["es_results"]
    pg = result["pg_metadata"]
    print("=" * 70)
    print("  检索管线结果")
    print("=" * 70)
    print(f"\n[Stage 1] Neo4j 扩展词: {exp.get('keywords', [])}")
    if exp.get("error") and not exp.get("keywords"):
        print(f"  Warning: {exp['error']}")
    print(f"\n[Stage 2] ES: BM25={es.get('bm25_count',0)} | Vector={es.get('vector_count',0)} | Merged={es.get('merged_count',0)}")
    for i, h in enumerate(result.get("merged_hits", [])[:top_k], 1):
        print(f"  #{i} [{h.get('source','?')}] score={h['score']:.4f} [{h.get('heading','')}] {h.get('doc_id','')}")
        text = (h.get("content", "") or "")[:80].replace("\n", " ")
        if text:
            print(f"       {text}...")
    print(f"\n[Stage 3] PG 溯源: {len(pg)} 个文档")
    for chunk_id, doc in list(pg.items())[:5]:
        print(f"  {doc.get('chunk_id', '?')[:50]}...")
        print(f"    -> doc_id={doc.get('doc_id','?')} source={doc.get('source_file','?')} v{doc.get('version','?')}")
    print()


def _print_standalone_summary(result: dict) -> None:
    source = result["source"]
    method = result["method"]
    total = result["total"]
    hits = result.get("hits", [])
    error = result.get("error", "")
    print(f"\n{'='*70}")
    print(f"  [{source}] {method}  (共 {total} 条命中)")
    if error:
        print(f"  错误: {error}")
    print(f"{'='*70}")
    if not hits:
        print("  (无结果)")
        return
    for i, h in enumerate(hits, 1):
        print(f"\n  #{i}")
        if source == "ES":
            print(f"    score={h.get('score',0):.4f} source={h.get('source','?')} heading={h.get('heading','')}")
            text = h.get("text_preview", "") or (h.get("content", "") or "")[:100]
        else:
            text = h.get("content_preview", "") or (h.get("description", "") or "")[:100]
        if source == "Neo4j":
            print(f"    [{h.get('entity_type','?')}] {h.get('name','')} (id={h.get('id','')})")
        else:
            print(f"    title={h.get('title','')} doc_id={h.get('doc_id','')}")
        if text:
            print(f"    {text.replace(chr(10), ' ')}...")
    print()


if __name__ == "__main__":
    main()
