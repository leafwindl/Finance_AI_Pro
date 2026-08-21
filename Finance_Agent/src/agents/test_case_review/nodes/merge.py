"""步骤6: 知识库结果汇聚"""
from ..state import ReviewState


def merge_retrieval(state: ReviewState) -> dict:
    retrieval_context = {
        "standard": state.get("standard_context", "") or "（未检索）",
        "spec": state.get("spec_context", "") or "（未检索）",
        "history": state.get("history_context", "") or "（未检索）",
    }
    return {"retrieval_context": retrieval_context}
