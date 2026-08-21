"""根据提取到的关键词，只路由到命中关键词的知识库。"""

from modules.state.state_def import WorkflowState

# 所有知识库编码（用于兜底全量搜索）
ALL_KB_CODES = ["KB01", "KB04", "KB05", "KB06"]


def kb_route_node(state: WorkflowState) -> WorkflowState:
    kb_keywords = state.get("kb_keywords", {})

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

    return {"kb_task_list": task_list}
