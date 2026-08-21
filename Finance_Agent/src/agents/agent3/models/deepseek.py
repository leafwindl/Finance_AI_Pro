import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import httpx

load_dotenv()


def create_deepseek():
    """创建 DeepSeek 模型实例（评审任务=确定性判断，低温 0.2 更稳定可复现；max_tokens 2048 防截断+限死耗时）"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 不存在，请检查 .env")

    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.2,
        max_tokens=2048,
        timeout=180,
http_client=httpx.Client(trust_env=False),
    )
