from __future__ import annotations

import json
from typing import Any

import asyncpg


async def get_owned_conversation(
    pool: asyncpg.Pool, conversation_id: str, user_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT conversation_id, user_id, agent_id, title, created_at, updated_at
        FROM conversations
        WHERE conversation_id=$1 AND user_id=$2
        """,
        conversation_id,
        user_id,
    )


async def create_conversation(
    pool: asyncpg.Pool,
    *,
    conversation_id: str,
    user_id: str,
    agent_id: str,
    title: str,
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        INSERT INTO conversations (conversation_id, user_id, agent_id, title)
        VALUES ($1, $2, $3, $4)
        RETURNING conversation_id, user_id, agent_id, title, created_at, updated_at
        """,
        conversation_id,
        user_id,
        agent_id,
        title,
    )


async def list_owned_conversations(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    agent_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT c.conversation_id, c.agent_id, c.title, c.created_at, c.updated_at,
               review.decision AS review_decision,
               review.decided_at AS review_decided_at
        FROM conversations c
        LEFT JOIN LATERAL (
            SELECT decision, decided_at
            FROM requirement_review_records
            WHERE conversation_id=c.conversation_id
            ORDER BY created_at DESC, review_id DESC
            LIMIT 1
        ) review ON TRUE
        WHERE c.user_id=$1 AND ($2::text IS NULL OR c.agent_id=$2)
        ORDER BY c.updated_at DESC
        LIMIT $3
        """,
        user_id,
        agent_id,
        limit,
    )
    return [dict(row) for row in rows]


async def list_owned_messages(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    conversation_id: str,
) -> list[dict[str, Any]] | None:
    owned = await get_owned_conversation(pool, conversation_id, user_id)
    if owned is None:
        return None
    rows = await pool.fetch(
        """
        SELECT m.message_id, m.role, m.content, m.status, m.error_code, m.metadata,
               m.created_at, r.approval_id, r.decision AS review_decision,
               r.rejection_reason, r.decided_at
        FROM messages m
        LEFT JOIN requirement_review_records r ON r.report_message_id=m.message_id
        WHERE m.conversation_id=$1
        ORDER BY m.created_at ASC, m.message_id ASC
        """,
        conversation_id,
    )
    messages = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("metadata"), str):
            try:
                item["metadata"] = json.loads(item["metadata"])
            except json.JSONDecodeError:
                item["metadata"] = {}
        messages.append(item)
    return messages


async def insert_user_message(
    pool: asyncpg.Pool,
    *,
    conversation_id: str,
    content: str,
    request_id: str,
    client_message_id: str,
) -> int | None:
    row = await pool.fetchrow(
        """
        INSERT INTO messages (
            conversation_id, role, content, request_id, client_message_id, status, metadata
        )
        VALUES ($1, 'user', $2, $3, $4, 'completed', '{}'::jsonb)
        ON CONFLICT (conversation_id, client_message_id)
            WHERE role='user' AND client_message_id IS NOT NULL
        DO NOTHING
        RETURNING message_id
        """,
        conversation_id,
        content,
        request_id,
        client_message_id,
    )
    return row["message_id"] if row else None


async def insert_assistant_message(
    pool: asyncpg.Pool,
    *,
    conversation_id: str,
    content: str,
    request_id: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    row = await pool.fetchrow(
        """
        INSERT INTO messages (
            conversation_id, role, content, request_id, status, metadata
        )
        VALUES ($1, 'assistant', $2, $3, 'completed', $4::jsonb)
        RETURNING message_id
        """,
        conversation_id,
        content,
        request_id,
        json.dumps(metadata or {}, ensure_ascii=False),
    )
    return row["message_id"]


async def mark_request_failed(
    pool: asyncpg.Pool, *, request_id: str, error_code: str
) -> None:
    await pool.execute(
        """
        UPDATE messages
        SET status='failed', error_code=$2,
            metadata=metadata || '{"request_failed": true}'::jsonb
        WHERE request_id=$1 AND role='user'
        """,
        request_id,
        error_code,
    )


async def delete_owned_conversation(
    pool: asyncpg.Pool, *, conversation_id: str, user_id: str
) -> bool:
    result = await pool.execute(
        "DELETE FROM conversations WHERE conversation_id=$1 AND user_id=$2",
        conversation_id,
        user_id,
    )
    return result == "DELETE 1"
