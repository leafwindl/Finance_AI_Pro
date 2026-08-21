"""Agent ⑤ 多轮记忆 — PostgresSaver 连接封装

将对话记忆持久化到 PostgreSQL（复用 docker-compose 的 postgres:16 容器），
实现跨请求 + 跨重启的多轮记忆（每个 thread_id 独立）。

依赖：langgraph-checkpoint-postgres（requirements.txt 已声明 psycopg[binary]）
配置（Finance_Agent/.env）：
  AGENT5_DB_DSN  （可选）形如 postgresql://postgres:finance_ai_dev@127.0.0.1:5432/knowledge_agent
  不配置时回退默认本地 DSN（与 docker-compose 默认值一致）。

使用官方 AsyncPostgresSaver（langgraph.checkpoint.postgres.aio），适配 agent5
的异步节点图（astream）。连接为常驻 AsyncConnection（server 生命周期内有效）。
"""

import os

# 默认连接串：与仓库 docker-compose.yml 的 postgres 服务一致
_DEFAULT_DSN = (
    "postgresql://postgres:finance_ai_dev@127.0.0.1:5432/knowledge_agent"
)


def _dsn() -> str:
    return os.getenv("AGENT5_DB_DSN", "").strip() or _DEFAULT_DSN


async def build_checkpointer():
    """异步构建官方 AsyncPostgresSaver 实例（惰性建表）。

    连接为常驻 AsyncConnection；返回 AsyncPostgresSaver。
    失败时由调用方捕获并降级为单轮对话。
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import AsyncConnection

    conn = await AsyncConnection.connect(
        _dsn(), autocommit=True, prepare_threshold=0,
    )
    saver = AsyncPostgresSaver(conn)
    await saver.setup()  # 幂等建表（checkpoints / checkpoint_writes 等）
    return saver
