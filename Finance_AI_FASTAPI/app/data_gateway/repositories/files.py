from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg


async def create_file_record(
    pool: asyncpg.Pool,
    *,
    file_id: str,
    user_id: str,
    filename: str,
    content_type: str,
    extension: str,
    size_bytes: int,
    storage_path: str,
    ttl_seconds: int,
) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    await pool.execute(
        """
        INSERT INTO uploaded_files (
            file_id, user_id, filename, content_type, extension,
            size_bytes, storage_path, status, expires_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,'ready',$8)
        """,
        file_id,
        user_id,
        filename,
        content_type,
        extension,
        size_bytes,
        storage_path,
        expires_at,
    )


async def get_owned_ready_files(
    pool: asyncpg.Pool, *, user_id: str, file_ids: list[str]
) -> list[dict]:
    if not file_ids:
        return []
    rows = await pool.fetch(
        """
        SELECT file_id, filename, content_type, extension, size_bytes, storage_path
        FROM uploaded_files
        WHERE user_id=$1
          AND file_id=ANY($2::varchar[])
          AND status='ready'
          AND expires_at > NOW()
        """,
        user_id,
        file_ids,
    )
    by_id = {row["file_id"]: dict(row) for row in rows}
    return [by_id[file_id] for file_id in file_ids if file_id in by_id]
