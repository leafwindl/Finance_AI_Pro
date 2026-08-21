"""步骤4-5: RAG分析回复 + 闲聊回复"""
import json
from ..state import AgentState
from ..prompts import RAG_RESPONSE_PROMPT, CHAT_RESPONSE_PROMPT
from src.models import get_llm


async def rag_response(state: AgentState) -> dict:
    messages = state.get("messages", [])
    input_text = messages[-1].content if messages else ""
    aggregated = state.get("aggregated_context", "")

    llm = get_llm()
    prompt = RAG_RESPONSE_PROMPT.format(
        input_text=input_text, aggregated_context=aggregated
    )
    response = llm.invoke(prompt)

    print(f"[RAG分析] 生成报告: {len(response.content)} 字符")
    # 将结果作为 aggregated_context 返回给调用方
    return {"aggregated_context": response.content}


async def chat_response(state: AgentState) -> dict:
    llm = get_llm()
    prompt = CHAT_RESPONSE_PROMPT
    response = llm.invoke(prompt)
    print("[闲聊回复] 无有效关键词")
    return {"aggregated_context": response.content}
