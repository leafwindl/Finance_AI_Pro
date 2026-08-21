"""步骤10: 意图识别 — 判断用户是确认/修改/澄清"""
from ..state import RequirementState
from ..prompts import INTENT_RECOGNITION_SYSTEM_PROMPT
from src.models import get_llm


def recognize_intent(state: RequirementState) -> dict:
    user_input = state.get("user_input", "")
    llm = get_llm()
    prompt = INTENT_RECOGNITION_SYSTEM_PROMPT.format(user_input=user_input)
    response = llm.invoke(prompt)
    intent = response.content.strip().upper()

    valid = ["CONFIRM", "MODIFY", "CLARIFY"]
    if intent not in valid:
        intent = "CLARIFY"

    print(f"[意图识别] → {intent}")
    return {"recognized_intent": intent}
