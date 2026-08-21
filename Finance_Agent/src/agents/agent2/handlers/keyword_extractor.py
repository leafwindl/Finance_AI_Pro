"""
关键词提取 — LLM 结构化输出

输入: user_query → LLM → 手动解析 JSON
输出: biz_keywords, test_keywords, regulatory_keywords

注：qwen3 可能不支持 tool_choice，
    因此不走 with_structured_output，改为普通调用 + JSON 解析。
"""

import json
import os
import re
from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..core.state import AgentState

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "keyword_extract.txt"

# JSON Schema 作为 prompt 后缀，让 LLM 按格式输出 JSON
_JSON_INSTRUCTION = """

请严格按照以下 JSON 格式输出，不要包含 Markdown 标记：
{
  "biz_keywords": "...",
  "test_keywords": "...",
  "regulatory_keywords": "..."
}"""


class KeywordExtractor:
    """LLM 关键词提取器：分析用户输入，提取业务/测试/法规三类关键词。"""

    def __init__(self) -> None:
        self._system_prompt: str = (
            _PROMPT_PATH.read_text(encoding="utf-8") + _JSON_INSTRUCTION
        )

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

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从 LLM 回复中提取 JSON 对象。"""
        # 去掉可能的 Markdown 代码块标记
        cleaned = re.sub(r'```(?:json)?\s*', '', text)
        cleaned = cleaned.replace('```', '')
        # 尝试找到 JSON 对象的起止位置
        start = cleaned.find('{')
        end = cleaned.rfind('}') + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    async def extract(
        self, state: AgentState, *, config: RunnableConfig
    ) -> dict:
        """图节点：LLM 提取关键词 → JSON 解析。"""
        model_name = config.get("configurable", {}).get(
            "extract_model", "ollama/qwen3:32b-q8_0"
        )
        provider, model_id = model_name.split("/", maxsplit=1)
        # 临时切换：ollama 分支改调 DeepSeek API（验证后 restore 还原）
        if provider == "ollama":
            from langchain_openai import ChatOpenAI
            import httpx
            model = ChatOpenAI(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
                http_client=httpx.Client(trust_env=False),
            )
        else:
            model = init_chat_model(model_id, model_provider=provider)

        user_query = self._extract_last_user_query(state)
        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_query),
        ]
        response = await model.ainvoke(messages, config)
        content = response.content
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        parsed = self._parse_json(str(content))

        return {
            "biz_keywords": parsed.get("biz_keywords", ""),
            "test_keywords": parsed.get("test_keywords", ""),
            "regulatory_keywords": parsed.get("regulatory_keywords", ""),
        }


# 模块级默认实例
default_extractor = KeywordExtractor()
