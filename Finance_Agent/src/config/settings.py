"""
全局配置 — 从 .env 加载
"""
import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


def load_dotenv_on_startup():
    """项目启动时加载 .env"""
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH, override=True)


class Settings:
    """全局配置"""

    # ===== 项目路径 =====
    PROJECT_ROOT: Path = _PROJECT_ROOT
    DOCS_DIR: Path = _PROJECT_ROOT / "docs"
    CHROMA_DIR: Path = _PROJECT_ROOT / "chroma_db"
    KB_CACHE_DIR: Path = _PROJECT_ROOT / "knowledge_base" / ".cache"

    # ===== Ollama (Cloudflare Tunnel) =====
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:32b-q8_0")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))

    # ===== 远程知识库 =====
    KB_BASE_URL: str = os.getenv("KB_BASE_URL", "")
    KB_TIMEOUT_SECONDS: float = float(os.getenv("KB_TIMEOUT_SECONDS", "30"))

    # ===== Embedding =====
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "dashscope")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v1")
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

    # ===== 降级 =====
    ALLOW_LOCAL_KB_FALLBACK: bool = (
        os.getenv("ALLOW_LOCAL_KB_FALLBACK", "false").lower() == "true"
    )

    # ===== API =====
    API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("API_PORT", "8101"))
    API_RELOAD: bool = os.getenv("API_RELOAD", "false").lower() == "true"

    # ===== 端口管理 =====
    PORT_POOL_START: int = int(os.getenv("PORT_POOL_START", "8101"))
    PORT_POOL_END: int = int(os.getenv("PORT_POOL_END", "8500"))
    PORT_AGENT1_RANGE: str = os.getenv("PORT_AGENT1_RANGE", "8101-8199")
    PORT_AGENT2_RANGE: str = os.getenv("PORT_AGENT2_RANGE", "8200-8299")
    PORT_AGENT3_RANGE: str = os.getenv("PORT_AGENT3_RANGE", "8300-8399")
    PORT_AGENT4_RANGE: str = os.getenv("PORT_AGENT4_RANGE", "8400-8499")
    PORT_HEARTBEAT_INTERVAL: int = int(os.getenv("PORT_HEARTBEAT_INTERVAL", "30"))
    PORT_LEASE_DURATION: int = int(os.getenv("PORT_LEASE_DURATION", "300"))
    PORT_SWEEP_INTERVAL: int = int(os.getenv("PORT_SWEEP_INTERVAL", "30"))
    PORT_MANAGER_ENABLED: bool = (
        os.getenv("PORT_MANAGER_ENABLED", "true").lower() == "true"
    )


settings = Settings()
