"""
统一 LLM 工厂 — 所有智能体通过此函数获取模型实例。

用法:
    from models import get_llm
    llm = get_llm()
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import httpx

load_dotenv()


def get_llm():
    """创建 DeepSeek 模型实例（临时切换：Ollama -> DeepSeek API）"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 不存在，请检查 .env")

    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
        timeout=180,
http_client=httpx.Client(trust_env=False),
    )
