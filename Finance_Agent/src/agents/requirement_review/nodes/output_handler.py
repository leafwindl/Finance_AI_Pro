"""输出处理 — 设置最终输出文本"""
from ..state import RequirementState


def set_clarification_output(state: RequirementState) -> dict:
    """信息不完整时输出追问话术"""
    clarification = state.get("clarification_question", "请补充以下信息...")
    print("[输出] 追问话术")
    return {"final_output": clarification}


def set_confirmation_output(state: RequirementState) -> dict:
    """重新展示确认话术"""
    summary = state.get("confirmation_summary", "")
    print("[输出] 重新展示确认话术")
    return {"final_output": summary}
