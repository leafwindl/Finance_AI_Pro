from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
import httpx

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.agent_gateway.client import agent_headers
from app.data_gateway.pool import get_pool
from app.data_gateway.repositories.conversations import (
    delete_owned_conversation,
    get_owned_conversation,
    list_owned_conversations,
    list_owned_messages,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    user: Annotated[dict, Depends(get_current_user)],
    agent_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    pool=Depends(get_pool),
) -> dict:
    conversations = await list_owned_conversations(
        pool, user_id=user["user_id"], agent_id=agent_id, limit=limit
    )
    return {"conversations": conversations}


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    pool=Depends(get_pool),
) -> dict:
    messages = await list_owned_messages(
        pool, user_id=user["user_id"], conversation_id=conversation_id
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"messages": messages}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> dict:
    conversation = await get_owned_conversation(
        pool, conversation_id, user["user_id"]
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    deleted = await delete_owned_conversation(
        pool, conversation_id=conversation_id, user_id=user["user_id"]
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")

    if conversation["agent_id"] == "requirement-pre-review":
        # 契约 §7：尽力请求 Agent 清理该会话的待审批状态（POST /chat/reset），
        # 避免已删除会话仍可被审批。失败不影响删除结果。
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{settings.agent_platform_url.rstrip('/')}/chat/reset",
                    json={"session_id": conversation_id},
                    headers=agent_headers(settings),
                )
        except httpx.HTTPError:
            pass
    return {"ok": True}
