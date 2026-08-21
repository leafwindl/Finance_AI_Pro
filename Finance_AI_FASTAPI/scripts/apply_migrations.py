"""Apply bundled SQL migrations using the Gateway .env connection."""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from app.core.config import get_settings


MIGRATIONS = (
    "001_initial_schema.sql",
    "004_auto_update_timestamp.sql",
    "005_sessions_uploads.sql",
    "006_messages_idempotency.sql",
    "007_requirement_review_records.sql",
    "008_kb_ingest_tasks.sql",
    "009_kb_blocks.sql",
)


async def main() -> None:
    settings = get_settings()
    backend_dir = Path(__file__).resolve().parents[1]
    configured_dir = Path(settings.migrations_dir).expanduser()
    database_dir = (
        configured_dir.resolve()
        if configured_dir.is_absolute()
        else (backend_dir / configured_dir).resolve()
    )
    missing = [name for name in MIGRATIONS if not (database_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "数据库迁移目录不可用："
            f"{database_dir}；缺少文件：{', '.join(missing)}。"
            "请设置 MIGRATIONS_DIR 指向包含迁移 SQL 的目录。"
        )

    connection = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )
    try:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(128) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for filename in MIGRATIONS:
            applied = await connection.fetchval(
                "SELECT 1 FROM schema_migrations WHERE version=$1", filename
            )
            if applied:
                print(f"skip {filename}")
                continue
            sql = (database_dir / filename).read_text(encoding="utf-8-sig")
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES($1)", filename
                )
            print(f"applied {filename}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
