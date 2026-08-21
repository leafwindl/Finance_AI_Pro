"""Agent ⑤ 智能对话助手 — 全局状态定义

多轮对话记忆（messages 用 add_messages 追加）+ 意图识别结果 + 上下文。
"""

from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class AssistantInputState(TypedDict):
    """输入状态：多轮对话 messages + 当前输入。"""
    messages: Annotated[Sequence[AnyMessage], add_messages]
    query: str                       # 当前用户问题
    file_content: str                # 上传文件提取的文本（文档问答用）
    file_name: str                   # 上传文件名


class AssistantState(AssistantInputState, total=False):
    """全局状态：输入 + 意图 + 上下文 + 输出。"""

    # ===== 输入 =====
    query: str                       # 当前用户问题
    file_content: str                # 上传文件提取的文本（文档问答用）
    file_name: str                   # 上传文件名

    # ===== 意图识别 =====
    intent: str                      # chat / kb_query / doc_qa / transfer_propose / transfer_confirm / transfer_cancel

    # ===== 知识库检索 =====
    retrieval_context: str           # 检索结果拼好的文本

    # ===== 跳转调度（2026-08-20 改造：transfer 改为前端跳转模式） =====
    pending_transfer_target: str     # 两段确认①的待确认目标（跨轮状态，checkpointer 保存）
    transfer_target: str             # 目标 agent_id（requirement-pre-review 等）
    transfer_query: str              # 跳转携带的内容（用户原话/附件拼接）

    # ===== 输出 =====
    answer: str                      # 最终回答
