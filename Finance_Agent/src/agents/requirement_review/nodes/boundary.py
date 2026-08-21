"""步骤2: 边界回复 — 闲聊时礼貌拒绝并引导业务"""
from ..state import RequirementState
from ..prompts import BOUNDARY_REPLY_SYSTEM_PROMPT
from src.models import get_llm


def boundary_reply(state: RequirementState) -> dict:
    user_input = state.get("user_input", "")
    llm = get_llm()
    prompt = BOUNDARY_REPLY_SYSTEM_PROMPT.format(user_input=user_input)
    response = llm.invoke(prompt)
    print("[边界] 输出闲聊拒绝回复")
    return {"final_output": response.content}
