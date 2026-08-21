"""
LLM 配置模块

统一管理所有节点使用的 LLM 实例。
使用 langchain_ollama 的 ChatOllama 通过 Cloudflare Tunnel 连接 qwen3:32b-q8_0。
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import httpx

load_dotenv()

# ================================================================
# 基础 LLM (用于普通文本生成)
# ================================================================
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise ValueError("DEEPSEEK_API_KEY 不存在，请检查 .env")

llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    api_key=api_key,
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
http_client=httpx.Client(trust_env=False),
)

# ================================================================
# 带结构化输出的 LLM (用于 JSON 提取)
#   使用 .with_structured_output() 方法强制输出符合 schema 的 JSON
# ================================================================

# 也可以用同一个 llm 实例在不同节点中调用 .with_structured_output(),
# 这里保留一个基础实例供普通调用使用。
