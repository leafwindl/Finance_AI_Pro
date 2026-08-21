"""Agent ⑤ 智能对话助手 — LLM 处理器

意图识别（规则 + LLM 兜底）+ 对话回答 + 知识库问答回答 + 文档问答回答。
复用 agent2 的 DeepSeek 接入模式（ChatOpenAI + trust_env=False）。
"""

import os
import re
import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from .state import AssistantState


class AssistantHandler:
    """对话助手 LLM 处理器。"""

    # ---- 模型 ----
    @staticmethod
    def load_model() -> ChatOpenAI:
        return ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
            timeout=180,
            http_client=httpx.Client(trust_env=False),
        )

    # ---- 辅助：无（agent5 直接用 state.get("query")，不再需要消息提取） ----

    # ---- 意图识别 ----
    @staticmethod
    def recognize_intent(state: AssistantState) -> str:
        """规则优先判断意图（2026-08-20 升级：支持跳转调度两段确认）。

        返回意图：
          - chat / kb_query / doc_qa：原有三类
          - transfer_propose：检测到调度意图，先确认
          - transfer_confirm：用户确认跳转（结合 pending_transfer_target）
          - transfer_cancel：用户取消/否认
        """
        query = state.get("query", "")
        file_content = state.get("file_content", "")
        pending_target = state.get("pending_transfer_target", "")

        # 规则 0：上轮 propose 过 + 本轮确认/否认 → confirm / cancel
        if pending_target:
            if any(k in query for k in ["确认", "确定", "可以", "好的", "好", "行", "没问题",
                                        "去吧", "跳转", "转交", "是的", "对", "就这样",
                                        "ok", "OK", "Ok", "嗯"]):
                return "transfer_confirm"
            if any(k in query for k in ["不用", "取消", "算了", "不要", "不是", "等等",
                                        "再看看", "不跳", "不转"]):
                return "transfer_cancel"

        # 规则 1：有文件 + 明确转交意图 → transfer_propose（跳转确认）
        if file_content:
            if any(k in query for k in ["帮我评审", "预评审", "分析这份", "评审这份"]):
                return "transfer_propose"
            return "doc_qa"

        # 规则 2：涉及"我"的自我指涉 → chat（如"我叫什么"、"我说了什么"）
        if any(k in query for k in ["我叫", "我的名字", "我说过", "刚才"]):
            return "chat"

        # 规则 2.5：无文件 + 明确调度意图 → transfer_propose
        transfer_keywords = [
            "预评审", "需求评审", "建需求", "新建需求",
            "六维", "分析需求", "测试分析",
            "用例评审", "评审用例",
            "步骤生成", "生成步骤", "测试步骤",
        ]
        if any(k in query for k in transfer_keywords):
            return "transfer_propose"

        # 规则 3：无文件 + 明确问业务/知识 → kb_query
        kb_keywords = ["知识库", "查一下", "规范", "流程", "合规", "缺陷", "标准测试用例", "怎么测", "如何测试"]
        if any(k in query for k in kb_keywords):
            return "kb_query"

        # 规则 4：默认闲聊
        return "chat"

    # ---- 跳转调度：意图 → 目标 agent + 携带内容 ----
    @staticmethod
    def _is_pure_transfer_command(query: str) -> bool:
        """判断是否只有跳转指令、没有实际需求/用例内容。

        纯指令时 transfer_query 置空 → 前端只跳目标页不自动发起，
        由用户在工作台粘贴真实需求后手动提交。
        """
        residue = query
        # 长词在前，避免被短词先吃掉（如"用例评审"被"评审"截断）
        for kw in [
            "跳转", "转交", "需求预评审", "需求评审", "预评审", "建需求", "新建需求",
            "六维分析", "六维", "分析需求", "测试分析", "用例评审", "评审用例",
            "步骤生成", "生成步骤", "测试步骤", "评审这份", "这份文档",
            "帮我", "请", "智能体", "可以吗", "确认", "一下", "评审", "文档",
        ]:
            residue = residue.replace(kw, "")
        residue = re.sub(r"[\s，。！？、：；,.!?:;\"'（）()【】\[\]]", "", residue)
        return len(residue.strip()) < 4

    @staticmethod
    def resolve_transfer(state: AssistantState) -> dict:
        """根据用户话术解析跳转目标与内容（返回 {"transfer_target", "transfer_query", "answer"}）。

        关键词映射（定案 §7）：
          预评审/需求评审/建需求/新建需求 → requirement-pre-review
          六维/分析需求/测试分析            → ai-test-analysis
          用例评审/评审用例                → accounting-expert
          步骤生成/生成步骤/测试步骤        → business-analyst
        """
        query = state.get("query", "")
        file_content = state.get("file_content", "")
        # 有附件带附件文本；纯跳转指令不携带内容（前端只跳页不自动发起）
        if file_content and file_content.strip():
            transfer_query = file_content
        elif AssistantHandler._is_pure_transfer_command(query):
            transfer_query = ""
        else:
            transfer_query = query

        target = "requirement-pre-review"
        if any(k in query for k in ["六维", "分析需求", "测试分析"]):
            target = "ai-test-analysis"
        elif any(k in query for k in ["用例评审", "评审用例"]):
            target = "accounting-expert"
        elif any(k in query for k in ["步骤生成", "生成步骤", "测试步骤"]):
            target = "business-analyst"

        return {
            "transfer_target": target,
            "transfer_query": transfer_query,
            "answer": f"好的，我将为你跳转到「{target}」智能体，携带你的输入继续处理。请确认后开始。",
        }

    # ---- 各意图的回答 ----
    @staticmethod
    def _history_messages(state: AssistantState, limit: int = 8):
        """取最近 N 条历史消息（含当次）作为上下文。"""
        msgs = state.get("messages", [])
        return msgs[-limit:] if msgs else []

    @staticmethod
    async def chat_answer(state: AssistantState) -> str:
        """闲聊：直接回答（带历史上下文）。"""
        model = AssistantHandler.load_model()
        history = AssistantHandler._history_messages(state)
        messages = [
            SystemMessage(content=(
                "你是证券测试领域的智能对话助手，回答简洁、友好、准确。"
                "如果用户问的是闲聊话题，直接友好回答；"
                "如果是测试/证券相关的问题，给出专业解答。"
                "请记住对话历史中的用户信息（如名字、提到过的内容）。"
            )),
            *history,
        ]
        resp = await model.ainvoke(messages)
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    @staticmethod
    async def kb_answer(state: AssistantState) -> str:
        """知识库问答：基于检索上下文回答（带历史）。"""
        model = AssistantHandler.load_model()
        query = state.get("query", "")
        context = state.get("retrieval_context", "") or "（无相关知识库内容）"
        history = AssistantHandler._history_messages(state, limit=6)
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "你是证券测试领域的智能问答助手。请基于以下知识库内容回答用户问题。\n"
                "如果知识库内容不足以回答，请如实说明并给出你的专业建议。\n"
                "可结合对话历史理解用户意图。\n\n"
                "知识库内容：\n{context}"
            )),
            *[(m.type, m.content) for m in history],
            ("user", "{query}"),
        ])
        resp = await model.ainvoke(prompt.format_messages(context=context[:8000], query=query))
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    @staticmethod
    async def doc_answer(state: AssistantState) -> str:
        """文档问答：基于上传文件内容回答。"""
        model = AssistantHandler.load_model()
        query = state.get("query", "")
        file_content = state.get("file_content", "")[:8000]  # 截断防超长
        file_name = state.get("file_name", "")
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "你是文档问答助手。请基于用户上传的文档内容回答。\n"
                "文档《{file_name}》内容：\n{file_content}\n\n"
                "回答要求：准确引用文档内容，文档中没有的不要编造。"
            )),
            ("user", "{query}"),
        ])
        resp = await model.ainvoke(prompt.format_messages(file_name=file_name, file_content=file_content, query=query))
        return resp.content if isinstance(resp.content, str) else str(resp.content)


# 模块级默认实例
default_handler = AssistantHandler()
