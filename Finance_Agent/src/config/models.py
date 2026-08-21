"""
LLM 模型配置字典
"""
import os

# 可用的 LLM 模型及其参数
LLM_CONFIGS = {
    "deepseek-v4-flash": {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.7")),
        "provider": "deepseek",
    },
}

DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
