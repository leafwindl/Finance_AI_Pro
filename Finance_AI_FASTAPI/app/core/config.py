from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # 四个 LangGraph Agent 由同一个 Agent Platform 承载。
    agent_platform_url: str = "http://127.0.0.1:8101"
    agent_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    # 预评审报告生成是单个 LLM 长任务（数分钟无中间事件），
    # 默认读超时放宽到 300s，避免长报告被网关误判为超时。
    agent_read_timeout_seconds: float = Field(default=300.0, gt=0, le=600)
    # 契约 §1：Agent 侧配置 AGENT_API_TOKEN 后要求请求带 X-Agent-Token。
    # Gateway 与 Agent 共用同一环境变量；留空则不发送（向后兼容）。
    agent_api_token: str = ""

    # 业务数据库 knowledge_agent
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "knowledge_agent"
    db_user: str = "postgres"
    db_password: str = ""
    migrations_dir: str = "database"

    # 登录 Session
    session_ttl_seconds: int = Field(default=604800, ge=300, le=2592000)
    session_cookie_secure: bool = False
    session_cookie_name: str = "session_id"

    # 文件上传
    upload_dir: str = "./data/uploads"
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    # 契约 §5.1：图片单张 ≤5 MB（小于普通文件 10MB，控制 OCR 成本）
    upload_image_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    upload_ttl_seconds: int = Field(default=86400, ge=300, le=2592000)
    extracted_text_max_chars: int = Field(default=200_000, ge=1000, le=1_000_000)
    request_attachments_max_chars: int = Field(
        default=400_000, ge=1000, le=2_000_000
    )

    # 图片 OCR（契约 §5.1 要求的 Gateway .env 开关）
    # easyocr=本地识别（默认）；none=禁用 OCR（图片不提取文本、不阻塞聊天）；
    # mineru / paddle 为预留的在线/替代引擎，接入后启用。
    ocr_provider: str = "easyocr"
    # 在线 OCR 引擎的 API Key（easyocr 无需）
    ocr_api_key: str = ""
    # OCR 识别超时（在线引擎使用；easyocr 为本地同步调用，忽略此值）
    ocr_timeout_seconds: float = Field(default=60.0, gt=0, le=600)

    # 知识库入库（V1）
    kb_ingest_url: str = "http://127.0.0.1:8200"
    kb_internal_token: str = ""
    kb_sources_dir: str = "./data/kb_sources"

    # 远程六库分类模型（V2 自动分类）
    # 本地不可直连服务器 8000，需 scripts/classify_tunnel.py 建 SSH 隧道后经本地端口访问。
    kb_classify_url: str = "http://127.0.0.1:8001"
    # 分类超时（批量分类一个块约需若干秒，放宽）
    kb_classify_timeout_seconds: float = Field(default=120.0, gt=1, le=600)

    # 知识库入库（V1）
    kb_ingest_url: str = "http://127.0.0.1:8200"
    kb_internal_token: str = ""
    kb_sources_dir: str = "./data/kb_sources"

    # 知识库业务库（knowledge_base；list_kbs / list_documents / content 使用）
    kb_db_host: str = "localhost"
    kb_db_port: int = 5432
    kb_db_name: str = "knowledge_base"
    kb_db_user: str = "postgres"
    kb_db_password: str = ""
    kb_db_pool_min_size: int = 1
    kb_db_pool_max_size: int = 5

    # Neo4j（知识图谱 /graph、/subgraph 使用；懒连接，未启动时不影响网关启动）
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    neo4j_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

@lru_cache
def get_settings() -> Settings:
    return Settings()
