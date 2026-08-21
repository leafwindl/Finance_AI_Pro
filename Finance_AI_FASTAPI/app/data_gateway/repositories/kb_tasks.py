from __future__ import annotations

import json

import asyncpg


async def create_task(
    pool: asyncpg.Pool,
    *,
    task_id: str,
    file_id: str,
    user_id: str,
    filename: str,
    kb_code: str = "",
) -> None:
    """创建任务。kb_code 人工指定时传 KB01~06；自动分类时留空（由后台分类）。"""
    await pool.execute(
        """
        INSERT INTO kb_ingest_tasks (
            task_id, file_id, user_id, filename, status, stage, percent, kb_code
        ) VALUES ($1,$2,$3,$4,'processing','saved',10,$5)
        """,
        task_id,
        file_id,
        user_id,
        filename,
        kb_code or None,
    )


async def get_task(
    pool: asyncpg.Pool, *, task_id: str
) -> dict | None:
    """按 task_id 取任务（含 user_id 属主字段），路由层再按属主做 404/403 判断。"""
    row = await pool.fetchrow(
        """
        SELECT task_id, file_id, user_id, filename, status, stage, percent, kb_code,
               total_chunks, doc_id, error_code, error_message, created_at,
               blocks, kb_distribution
        FROM kb_ingest_tasks
        WHERE task_id=$1
        """,
        task_id,
    )
    return dict(row) if row else None


async def mark_ingesting(pool: asyncpg.Pool, *, task_id: str) -> None:
    await pool.execute(
        """
        UPDATE kb_ingest_tasks
        SET stage='ingesting', percent=90, updated_at=NOW()
        WHERE task_id=$1
        """,
        task_id,
    )


async def mark_completed(
    pool: asyncpg.Pool,
    *,
    task_id: str,
    blocks: list[dict],
    kb_distribution: dict,
    total_chunks: int,
    kb_code: str | None = None,
    doc_id: str | None = None,
) -> None:
    """标记完成。自动分类时为块级多库（blocks + kb_distribution）；
    人工指定单库时同时保留 kb_code/doc_id 便于回滚。"""
    await pool.execute(
        """
        UPDATE kb_ingest_tasks
        SET status='completed', stage='ingesting', percent=100,
            blocks=$2, kb_distribution=$3, total_chunks=$4,
            kb_code=COALESCE($5, kb_code), doc_id=COALESCE($6, doc_id),
            updated_at=NOW()
        WHERE task_id=$1
        """,
        task_id,
        json.dumps(blocks, ensure_ascii=False),
        json.dumps(kb_distribution, ensure_ascii=False),
        total_chunks,
        kb_code,
        doc_id,
    )


async def mark_failed(
    pool: asyncpg.Pool, *, task_id: str, error_code: str, error_message: str
) -> None:
    await pool.execute(
        """
        UPDATE kb_ingest_tasks
        SET status='failed', error_code=$2, error_message=$3, updated_at=NOW()
        WHERE task_id=$1
        """,
        task_id,
        error_code,
        error_message,
    )


async def mark_rolled_back(pool: asyncpg.Pool, *, task_id: str) -> None:
    await pool.execute(
        """
        UPDATE kb_ingest_tasks
        SET status='rolled_back', updated_at=NOW()
        WHERE task_id=$1
        """,
        task_id,
    )
