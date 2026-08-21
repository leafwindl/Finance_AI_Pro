"""步骤2: 知识库路由 — 按 kb_keywords 精准备库（v2 新版）"""
from ..state import WorkflowState

ALL_KB_CODES = ["KB01", "KB04", "KB05", "KB06"]


def kb_route_node(state: WorkflowState) -> dict:
    kb_keywords = state.get("kb_keywords", {})
    query = state.get("query", "")

    task_list = []
    for kb_code in ALL_KB_CODES:
        keywords = kb_keywords.get(kb_code, [])
        valid_keywords = [kw.strip() for kw in keywords if kw and kw.strip()]
        if valid_keywords:
            task_list.append({
                "kb_codes": [kb_code],
                "query": " ".join(valid_keywords),
                "need_search": True,
            })

    # 兜底：没有任何库命中时，全量搜索
    if not task_list:
        task_list.append({
            "kb_codes": ALL_KB_CODES,
            "query": query,
            "need_search": bool(query.strip()),
        })

    return {"kb_task_list": task_list}
