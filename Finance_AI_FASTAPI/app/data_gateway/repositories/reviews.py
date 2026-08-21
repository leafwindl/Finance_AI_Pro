from __future__ import annotations

import asyncpg


async def create_pending_review(
    pool: asyncpg.Pool,
    *,
    conversation_id: str,
    report_message_id: int,
    approval_id: str,
    report_content: str,
) -> None:
    await pool.execute(
        """
        INSERT INTO requirement_review_records (
            conversation_id, report_message_id, approval_id, report_content
        ) VALUES ($1, $2, $3, $4)
        ON CONFLICT (conversation_id, approval_id) DO UPDATE SET
            report_message_id=EXCLUDED.report_message_id,
            report_content=EXCLUDED.report_content,
            updated_at=NOW()
        """,
        conversation_id,
        report_message_id,
        approval_id,
        report_content,
    )


async def decide_review(
    pool: asyncpg.Pool,
    *,
    conversation_id: str,
    approval_id: str,
    decision: str,
    reason: str,
) -> bool:
    result = await pool.execute(
        """
        UPDATE requirement_review_records
        SET decision=$3, rejection_reason=$4, decided_at=NOW(), updated_at=NOW()
        WHERE conversation_id=$1 AND approval_id=$2 AND decision='pending'
        """,
        conversation_id,
        approval_id,
        decision,
        reason if decision == "reject" else "",
    )
    return result == "UPDATE 1"
