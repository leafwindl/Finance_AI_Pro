"""知识检索 LangGraph 节点。"""

import asyncio

from modules.rag.service import search_knowledge_base
from modules.state.state_def import WorkflowState


async def _search_one(task: dict) -> list[str]:
    """单任务检索，返回格式化片段列表；失败降级为空（保持原串行语义）。"""
    if not task.get("need_search"):
        return []
    query = str(task.get("query") or "").strip()
    kb_codes = task.get("kb_codes") or []
    if not query or not kb_codes:
        return []
    try:
        results = await search_knowledge_base(query, kb_codes, top_k=6)
    except Exception as exc:
        # KB 检索失败 → 降级为空结果继续（agent4 有 query 兜底，空检索也能出步骤）
        print(f"[知识检索] [警告] KB 检索失败，降级为空: {exc}")
        return []
    parts: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue  # 非 dict 项跳过，避免 AttributeError
        content = str(item.get("content") or "").strip()
        metadata = item.get("metadata") or {}
        if content:
            title = metadata.get("title") or metadata.get("heading") or "未知来源"
            parts.append(f"【{title}】\n{content}")
    return parts


async def knowledge_retrieve_node(state: WorkflowState) -> WorkflowState:
    tasks = state.get("kb_task_list", [])
    # 并行检索所有 KB 任务（gather 保持顺序，结果与串行一致）
    results = await asyncio.gather(*(_search_one(t) for t in tasks))
    all_rag_docs: list[str] = []
    for parts in results:
        all_rag_docs.extend(parts)
    return {"rag_docs": all_rag_docs, "progress_msg": "知识检索中..."}
