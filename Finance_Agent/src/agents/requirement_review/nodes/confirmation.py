"""步骤8-9: 确认话术生成 — 首次确认 + 修改后重新确认"""
from ..state import RequirementState, merge_collected_info
from ..prompts import CONFIRMATION_SYSTEM_PROMPT, RECONFIRMATION_SYSTEM_PROMPT
from src.models import get_llm


def generate_confirmation(state: RequirementState) -> dict:
    """首次确认话术"""
    collected_info = state.get("collected_info", [])
    merged = merge_collected_info(collected_info)
    user_input = state.get("user_input", "")

    llm = get_llm()
    prompt = CONFIRMATION_SYSTEM_PROMPT.format(
        collected_info=merged, user_input=user_input
    )
    response = llm.invoke(prompt)

    print("[确认] 生成确认话术")
    return {
        "waiting_confirmation": True,
        "confirmation_summary": response.content,
        "final_output": response.content,
    }


def generate_reconfirmation(state: RequirementState) -> dict:
    """修改后重新确认"""
    collected_info = state.get("collected_info", [])
    merged = merge_collected_info(collected_info)
    user_input = state.get("user_input", "")
    modifications = state.get("modifications", [])

    llm = get_llm()
    prompt = RECONFIRMATION_SYSTEM_PROMPT.format(
        collected_info=merged,
        extracted_context=f"\n本次修改: {modifications}",
        user_input=user_input,
    )
    response = llm.invoke(prompt)

    print("[重新确认] 生成更新后的确认话术")
    return {
        "confirmation_summary": response.content,
        "final_output": response.content,
    }
