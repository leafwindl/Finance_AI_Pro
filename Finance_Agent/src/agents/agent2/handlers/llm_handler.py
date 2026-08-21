"""LLM 调用模块 — RAG 六维分析 + 闲聊"""

import os
from pathlib import Path
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from ..core.state import AgentState

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class LLMHandler:
    """LLM 处理器：加载 prompt 模板，提供 RAG / 闲聊两个图节点。"""

    def __init__(self) -> None:
        self._rag_prompt: str = (
            _PROMPTS_DIR / "rag_prompt.txt"
        ).read_text(encoding="utf-8")
        self._chat_prompt: str = (
            _PROMPTS_DIR / "chat_prompt.txt"
        ).read_text(encoding="utf-8")

    # ---- 模型工厂 ----
    @staticmethod
    def load_model(fully_specified_name: str) -> BaseChatModel:
        """从 'provider/model' 字符串创建 chat model 实例。

        对于 ollama provider，显式传入 OLLAMA_BASE_URL 环境变量，
        避免默认连接 localhost:11434。
        """
        if "/" in fully_specified_name:
            provider, model = fully_specified_name.split("/", maxsplit=1)
        else:
            provider, model = "", fully_specified_name

        if provider == "ollama":
            # 临时切换：Ollama -> DeepSeek API（验证后 restore 还原）
            from langchain_openai import ChatOpenAI
            import httpx
            return ChatOpenAI(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
                http_client=httpx.Client(trust_env=False),
            )

        return init_chat_model(model, model_provider=provider)

    # ---- 辅助 ----
    @staticmethod
    def _format_doc(doc) -> str:
        meta = doc.metadata or {}
        src = meta.get("source", meta.get("record_id", "unknown"))
        return f"--- 文档来源: {src} ---\n{doc.page_content}"

    @staticmethod
    def _format_docs(docs: list) -> str:
        if not docs:
            return "（无相关文档）"
        return "\n\n".join(LLMHandler._format_doc(d) for d in docs)

    @staticmethod
    def _extract_last_user_query(state: AgentState) -> str:
        msgs = state.get("messages", [])
        user_msgs = [m for m in msgs if isinstance(m, HumanMessage)]
        if not user_msgs:
            return ""
        content = user_msgs[-1].content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    # ---- 图节点 ----
    async def rag_response(
        self, state: AgentState, *, config: RunnableConfig
    ) -> dict:
        """步骤7: RAG 六维分析节点（上下文 = 聚合结果 + 用户问题）。"""
        model_name = config.get("configurable", {}).get(
            "response_model", "ollama/qwen3:32b-q8_0"
        )
        model = self.load_model(model_name)
        aggregated = state.get("aggregated_context", "") or "（无相关知识库文档）"
        user_query = self._extract_last_user_query(state)

        prompt = ChatPromptTemplate.from_messages([("system", self._rag_prompt)])
        prompt_value = await prompt.ainvoke(
            {"aggregated_context": aggregated, "user_query": user_query}, config
        )
        response = await model.ainvoke(prompt_value, config)
        return {"messages": [response]}

    async def chat_response(
        self, state: AgentState, *, config: RunnableConfig
    ) -> dict:
        """步骤5: 闲聊节点（all_query 不为空时走这里，不经过检索）。"""
        model_name = config.get("configurable", {}).get(
            "response_model", "ollama/qwen3:32b-q8_0"
        )
        model = self.load_model(model_name)
        user_query = state.get("all_query") or self._extract_last_user_query(state)

        prompt = ChatPromptTemplate.from_messages([("system", self._chat_prompt)])
        prompt_value = await prompt.ainvoke({"user_query": user_query}, config)
        response = await model.ainvoke(prompt_value, config)
        return {"messages": [response]}


# 模块级默认实例
default_llm = LLMHandler()
