import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import httpx

# 加载环境变量
load_dotenv()


def get_llm(temperature: float | None = None, model: str | None = None, max_tokens: int | None = None):
    """创建 DeepSeek LLM 实例（临时切换：Ollama -> DeepSeek API）。

    Args:
        temperature: 温度值 (0~1)，不传则用默认值 0.7
        model: 模型名，不传则用 DEEPSEEK_MODEL
        max_tokens: 输出上限，防截断并限死最坏耗时（默认 1024，步骤生成 6 步够用）
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 不存在，请检查 .env")

    return ChatOpenAI(
        model=model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=temperature if temperature is not None else float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
        max_tokens=max_tokens if max_tokens is not None else 1024,
        timeout=180,
http_client=httpx.Client(trust_env=False),
    )


# 默认全局实例（向后兼容已有代码）
llm = get_llm()

# 兼容旧函数名
get_deepseek_llm = get_llm
