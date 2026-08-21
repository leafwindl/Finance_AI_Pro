"""步骤3: 知识检索"""
from ..state import WorkflowState
from src.knowledge.remote_kb import search_knowledge_base


async def knowledge_retrieve_node(state: WorkflowState) -> dict:
    all_rag_docs: list[str] = []
    for task in state.get("kb_task_list", []):
        if not task.get("need_search"):
            continue
        query = str(task.get("query") or "").strip()
        kb_codes = task.get("kb_codes") or []
        if not query or not kb_codes:
            continue
        try:
            results = await search_knowledge_base(query, kb_codes, top_k=6)
        except Exception as e:
            print(f"  [KB检索降级] {kb_codes}: {e}")
            all_rag_docs.append(f"【知识库暂不可用】将基于通用知识生成步骤")
            continue
        for item in results:
            content = str(item.get("content") or "").strip()
            metadata = item.get("metadata") or {}
            if content:
                title = metadata.get("title") or "未知来源"
                all_rag_docs.append(f"【{title}】\n{content}")

    return {"rag_docs": all_rag_docs, "progress_msg": "知识检索中..."}
