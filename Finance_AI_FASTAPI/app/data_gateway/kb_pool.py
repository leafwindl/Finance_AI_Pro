import asyncio

import asyncpg
from app.core.config import Settings

# 知识库元数据库（knowledge_base）专用连接池，与业务库（knowledge_agent）分离。
_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_kb_pool() -> asyncpg.Pool:
    """返回知识库库全局连接池，首次调用时自动初始化。"""
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is not None:
            return _pool
        settings = Settings()
        _pool = await asyncpg.create_pool(
            host=settings.kb_db_host,
            port=settings.kb_db_port,
            database=settings.kb_db_name,
            user=settings.kb_db_user,
            password=settings.kb_db_password,
            min_size=settings.kb_db_pool_min_size,
            max_size=settings.kb_db_pool_max_size,
        )
    return _pool


async def close_kb_pool() -> None:
    """关闭知识库库连接池（应用关闭时调用）。"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None