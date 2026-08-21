"""步骤6: 知识库结果汇聚节点"""
from typing import Dict, Any

from ..graph.state import ReviewState


def merge_retrieval(state: ReviewState) -> Dict[str, Any]:
    """
    对应 Dify: 三个 Knowledge Retrieval 结果汇总
    输入: standard_context, spec_context, history_context
    输出: retrieval_context
    """
    retrieval_context = {
        "standard": state.get("standard_context", "") or "（未检索）",
        "spec": state.get("spec_context", "") or "（未检索）",
        "history": state.get("history_context", "") or "（未检索）",
    }

    return {"retrieval_context": retrieval_context}
