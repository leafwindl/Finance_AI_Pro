"""步骤1: 问题分类器 — 判断业务相关 vs 闲聊"""
from ..state import RequirementState
from ..prompts import QUESTION_CLASSIFIER_INSTRUCTION
from src.models import get_llm


def classify_question(state: RequirementState) -> dict:
    user_input = state.get("user_input", "")
    llm = get_llm()
    prompt = f"{QUESTION_CLASSIFIER_INSTRUCTION}\n\n用户输入: {user_input}\n输出分类 (1或2):"
    response = llm.invoke(prompt)
    is_business = "1" in response.content.strip()
    label = "业务相关" if is_business else "闲聊"
    print(f"[路由] 问题分类 → {label}")
    return {"is_business": is_business}
