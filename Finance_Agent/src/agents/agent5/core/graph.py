"""Agent ⑤ 智能对话助手 — LangGraph 图

拓扑:
  START → intent_recognition（意图识别）
      ├─ chat     → answer_generate（闲聊回答）→ END
      ├─ kb_query → kb_retrieve（知识库检索）→ answer_generate → END
      ├─ doc_qa   → answer_generate（文档回答）→ END
      └─ transfer → transfer_agent（转交）→ END
"""

import os
from langgraph.graph import StateGraph, START, END

# 多轮记忆（2026-08-10 恢复）：
#   使用 PostgresSaver（checkpointer）实现跨请求 + 跨重启的多轮记忆；
#   每个 thread_id（= Gateway conversation_id）独立记忆，多会话天然支持。
#   连接失败时降级为单轮对话（attach_checkpointer 捕获异常）。
from .state import AssistantState, AssistantInputState
from .handler import default_handler
from .checkpointer import build_checkpointer


# ================================================================
# 节点函数
# ================================================================
def intent_recognition(state: AssistantState) -> dict:
    """意图识别：规则 + LLM 兜底。"""
    intent = default_handler.recognize_intent(state)
    print(f"[agent5] 意图: {intent}")
    return {"intent": intent}


async def kb_retrieve(state: AssistantState, config=None) -> dict:
    """知识库检索：复用 agent2 的 _retrieve_remote 模式（KB REST）。"""
    import asyncio
    import httpx
    from langchain_core.documents import Document

    query = state.get("query", "")
    base_url = os.environ.get("KB_BASE_URL", "").rstrip("/")
    if not base_url:
        return {"retrieval_context": ""}

    timeout = float(os.environ.get("KB_TIMEOUT_SECONDS", "30"))
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
            response = await client.post(
                "/api/v1/search",
                json={"query": query, "kb_codes": ["KB01", "KB04", "KB05", "KB06"], "top_k": 5, "expand_k": 0},
            )
            response.raise_for_status()
            results = response.json().get("results") or []
    except Exception as exc:
        print(f"[agent5] KB 检索失败，降级为空: {exc}")
        results = []

    parts = []
    for r in results:
        if not isinstance(r, dict):
            continue
        content = r.get("content", "")
        if content:
            meta = r.get("metadata") or {}
            title = meta.get("title") or meta.get("heading") or "未知来源"
            parts.append(f"【{title}】\n{content}")
    return {"retrieval_context": "\n\n".join(parts)}


async def answer_generate(state: AssistantState) -> dict:
    """按意图生成回答。"""
    intent = state.get("intent", "chat")
    if intent == "kb_query":
        answer = await default_handler.kb_answer(state)
    elif intent == "doc_qa":
        answer = await default_handler.doc_answer(state)
    else:
        answer = await default_handler.chat_answer(state)
    return {"answer": answer}


async def transfer_agent(state: AssistantState) -> dict:
    """跳转调度（2026-08-20 改造：不再进程内代跑，改为生成跳转指令）。

    三意图：
      - transfer_propose：解析目标 + 记 pending，输出确认询问（两段确认①）
      - transfer_confirm：确认后生成跳转指令（server 侧 completed metadata 带 transfer）
      - transfer_cancel：取消跳转，清 pending
    """
    query = state.get("query", "")
    intent = state.get("intent", "")

    # ---- propose：解析目标，记 pending，询问确认 ----
    if intent == "transfer_propose":
        info = default_handler.resolve_transfer(state)
        print(f"[agent5] 提议跳转: {info['transfer_target']}")
        suffix = (
            ""
            if info["transfer_query"].strip()
            else "（未检测到需求内容，跳转后请在目标页面输入需求再提交）"
        )
        return {
            "pending_transfer_target": info["transfer_target"],
            "transfer_target": info["transfer_target"],
            "transfer_query": info["transfer_query"],
            "answer": f"我检测到你想调用智能体，将跳转到「{info['transfer_target']}」。确认吗？回复\"确认\"或\"确定\"即可，或直接告诉我其他需求。{suffix}",
        }

    # ---- confirm：确认跳转（有 pending 才生效） ----
    if intent == "transfer_confirm":
        pending = state.get("pending_transfer_target", "")
        if pending:
            print(f"[agent5] 确认跳转: {pending}")
            # transfer_query 可能合法为空（纯跳转指令 → 前端只跳页不自动发起），
            # 仅在字段缺失（None）时才回退到本轮 query
            transfer_query = state.get("transfer_query")
            if transfer_query is None:
                transfer_query = query
            return {
                "pending_transfer_target": "",
                "transfer_target": pending,
                "transfer_query": transfer_query,
                "answer": f"已确认，即将跳转到「{pending}」智能体处理。",
            }
        # 无 pending：回落普通对话
        return {"answer": "好的，请告诉我你想做什么。"}

    # ---- cancel：取消 ----
    if intent == "transfer_cancel":
        print("[agent5] 取消跳转")
        return {
            "pending_transfer_target": "",
            "answer": "好的，不跳转了。还有什么可以帮你？",
        }

    # 兜底
    return {"answer": "（未识别的调度意图）"}


# ================================================================
# 路由函数
# ================================================================
def route_after_intent(state: AssistantState) -> str:
    return state.get("intent", "chat")


# ================================================================
# 构建图（多轮记忆暂缓：无 checkpointer，单轮对话）
# ================================================================
_builder = StateGraph(AssistantState, input_schema=AssistantInputState)

_builder.add_node("intent_recognition", intent_recognition)
_builder.add_node("kb_retrieve", kb_retrieve)
_builder.add_node("answer_generate", answer_generate)
_builder.add_node("transfer_agent", transfer_agent)

_builder.add_edge(START, "intent_recognition")
_builder.add_conditional_edges(
    "intent_recognition", route_after_intent,
    {
        "chat": "answer_generate",
        "doc_qa": "answer_generate",
        "kb_query": "kb_retrieve",
        "transfer_propose": "transfer_agent",
        "transfer_confirm": "transfer_agent",
        "transfer_cancel": "transfer_agent",
    },
)
_builder.add_edge("kb_retrieve", "answer_generate")
_builder.add_edge("answer_generate", END)
_builder.add_edge("transfer_agent", END)

# 多轮记忆：PostgresSaver 惰性挂载。
# graph 先以无 checkpointer 编译（单轮兜底）；server 首次请求时
# attach_checkpointer() 异步构建并重新挂载（避免模块加载期事件循环问题）。
assistant_graph = _builder.compile()
assistant_graph.name = "IntelligentAssistant"

_attached = False


async def attach_checkpointer():
    """首次请求时挂载 PostgresSaver（幂等，失败静默降级单轮）。"""
    global _attached
    if _attached:
        return
    try:
        saver = await build_checkpointer()
        if saver is not None:
            globals()["assistant_graph"] = _builder.compile(checkpointer=saver)
        _attached = True
    except Exception as exc:
        print(f"[agent5] PostgresSaver 挂载失败，保持单轮对话: {exc}")
        _attached = True  # 不再重试（避免每次请求都尝试）
