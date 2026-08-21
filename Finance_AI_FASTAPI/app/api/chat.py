from __future__ import annotations

import asyncio
from typing import Annotated
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.data_gateway.pool import get_pool
from app.core.exceptions import UpstreamServiceError
from app.data_gateway.repositories.conversations import (
    create_conversation,
    get_owned_conversation,
    insert_assistant_message,
    insert_user_message,
    mark_request_failed,
)
from app.data_gateway.repositories.files import get_owned_ready_files
from app.data_gateway.repositories.reviews import create_pending_review, decide_review
from app.schemas.chat import ApprovalRequest, ChatRequest, WorkflowRequest
from app.agent_gateway.client import AgentClient, agent_headers
from app.agent_gateway.registry import build_registry
from app.knowledge_gateway.extraction import FileTextError, extract_text
from app.agent_gateway.sse import encode_sse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.get("/agents", summary="智能体能力清单")
async def list_agents(
    user: Annotated[dict, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    del user
    return {
        "agents": [
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "enabled": agent.enabled,
                "stateful": agent.stateful,
            }
            for agent in build_registry(settings).values()
        ]
    }


@router.post("/chat/approve", summary="审批决策")
async def approve_message(
    payload: ApprovalRequest,
    user: Annotated[dict, Depends(get_current_user)],
    pool=Depends(get_pool),
) -> dict:
    conversation = await get_owned_conversation(
        pool, payload.conversation_id, user["user_id"]
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    settings = get_settings()
    registry = build_registry(settings)
    agent = registry.get(conversation["agent_id"])
    if not agent or not agent.enabled or not agent.stateful:
        raise HTTPException(status_code=409, detail="当前智能体不支持审批")

    request_id = f"req_{uuid.uuid4().hex}"
    # Agent Platform 的待审批状态保存在进程内存中，平台重启后历史审批会丢失。
    # 平台返回 409（当前没有待处理审批）时降级为仅落库决策：
    # DB 中仍为 pending 的审批记录允许直接记录决策，避免历史待审批永远无法处理。
    try:
        headers = agent_headers(settings)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{agent.base_url}/v1/agent/approve",
                json={
                    "request_id": request_id,
                    "thread_id": payload.conversation_id,
                    "user_id": user["user_id"],
                    "agent_id": conversation["agent_id"],
                    "approval_id": payload.approval_id,
                    "decision": payload.decision,
                    "reason": payload.reason,
                },
                headers=headers,
            )
            if response.status_code != 409:
                response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="审批服务暂不可用") from exc

    saved = await decide_review(
        pool,
        conversation_id=payload.conversation_id,
        approval_id=payload.approval_id,
        decision=payload.decision,
        reason=payload.reason,
    )
    if not saved:
        raise HTTPException(status_code=409, detail="审批记录不存在或已经处理")

    return {"ok": True, "decision": payload.decision}


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "统一 progress/delta/completed/error SSE 事件流",
            "content": {
                "text/event-stream": {"schema": {"type": "string"}},
            },
        }
    },
)
async def send_chat_message(
    payload: ChatRequest,
    user: Annotated[dict, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> StreamingResponse:
    registry = build_registry(settings)
    agent = registry.get(payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=400, detail="未知的智能体")
    if not agent.enabled:
        # 契约 §2：结构化错误统一走 {"error": {code,message,retryable}}，
        # 由 UpstreamServiceError 全局 handler 格式化，不再塞进 detail。
        raise UpstreamServiceError(
            f"{agent.name}尚未接入",
            code="agent_unavailable",
            status_code=503,
        )

    conversation_id = payload.conversation_id
    if conversation_id:
        conversation = await get_owned_conversation(
            pool, conversation_id, user["user_id"]
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        if conversation["agent_id"] != payload.agent_id:
            raise HTTPException(status_code=409, detail="会话与智能体不匹配")
    files = await get_owned_ready_files(
        pool, user_id=user["user_id"], file_ids=payload.file_ids
    )
    if len(files) != len(payload.file_ids):
        raise HTTPException(status_code=404, detail="附件不存在、已过期或无权访问")

    attachments = []
    total_chars = 0
    for item in files:
        try:
            text, ocr_failed = await asyncio.to_thread(
                extract_text,
                item["storage_path"],
                item["extension"],
                settings.extracted_text_max_chars,
            )
        except FileTextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        total_chars += len(text)
        if total_chars > settings.request_attachments_max_chars:
            raise HTTPException(status_code=400, detail="附件提取文本总长度超过限制")
        attachment = {
            "file_id": item["file_id"],
            "filename": item["filename"],
            "content_type": item["content_type"],
            "text": text,
        }
        # 契约 §5.1：OCR 失败 → text 为空 + metadata.ocr_failed=true，不阻塞聊天
        if ocr_failed:
            attachment["metadata"] = {"ocr_failed": True}
        attachments.append(attachment)

    # 文件归属和文本解析全部成功后再创建会话，避免非法附件请求留下空会话。
    if conversation_id is None:
        conversation_id = f"conv_{uuid.uuid4().hex}"
        await create_conversation(
            pool,
            conversation_id=conversation_id,
            user_id=user["user_id"],
            agent_id=payload.agent_id,
            title=payload.query[:100],
        )

    request_id = f"req_{uuid.uuid4().hex}"
    user_message_id = await insert_user_message(
        pool,
        conversation_id=conversation_id,
        content=payload.query,
        request_id=request_id,
        client_message_id=payload.client_message_id,
    )
    if user_message_id is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "message_duplicate",
                "message": "该消息已提交，请勿重复发送",
                "retryable": False,
            },
        )

    agent_payload = {
        "request_id": request_id,
        "thread_id": conversation_id,
        "user_id": user["user_id"],
        "agent_id": payload.agent_id,
        "query": payload.query,
        "attachments": attachments,
    }
    client = AgentClient(settings)

    async def generate():
        # 发送初始 progress 事件，确保浏览器立即开始处理 SSE 流
        yield encode_sse(
            "progress",
            {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "node": "init",
                "message": "正在处理...",
            },
        )
        full_answer = ""
        completed = False
        try:
            async for event, data in client.stream(agent, agent_payload):
                if event == "progress":
                    yield encode_sse(
                        "progress",
                        {
                            "request_id": request_id,
                            "conversation_id": conversation_id,
                            "node": str(data.get("node") or "agent"),
                            "message": str(data.get("message") or "正在处理..."),
                        },
                    )
                elif event == "approval_required":
                    answer = str(data.get("answer") or full_answer)
                    if answer:
                        message_id = await insert_assistant_message(
                            pool,
                            conversation_id=conversation_id,
                            content=answer,
                            request_id=request_id,
                        )
                        if payload.agent_id == "requirement-pre-review":
                            await create_pending_review(
                                pool,
                                conversation_id=conversation_id,
                                report_message_id=message_id,
                                approval_id=str(data.get("approval_id") or ""),
                                report_content=answer,
                            )
                    else:
                        message_id = None
                    completed = True
                    # 契约 §6.1：approval_required.answer 是最终权威文本，
                    # 无论报告是否已通过 delta 流式发送都必须带上，前端据此取报告正文。
                    yield encode_sse(
                        "approval_required",
                        {
                            "request_id": request_id,
                            "conversation_id": conversation_id,
                            "message_id": str(message_id) if message_id else "",
                            "approval_id": str(data.get("approval_id") or ""),
                            "answer": answer,
                            "options": data.get("options") or ["approve", "reject", "revise"],
                        },
                    )
                    # 契约 §6.1：一次请求只能出现一个终止事件；
                    # approval_required 后直接结束，不再转发 Agent 后续事件。
                    return
                elif event == "delta":
                    text = str(data.get("text") or "")
                    if text:
                        full_answer += text
                        # 将大段文本拆分为逐字小块发送，实现打字机效果
                        chunk_size = 3
                        for i in range(0, len(text), chunk_size):
                            chunk = text[i : i + chunk_size]
                            yield encode_sse(
                                "delta",
                                {
                                    "request_id": request_id,
                                    "conversation_id": conversation_id,
                                    "text": chunk,
                                },
                            )
                            if len(text) > 60 and i + chunk_size < len(text):
                                await asyncio.sleep(0.02)
                elif event == "error":
                    code = str(data.get("code") or "agent_execution_failed")
                    await mark_request_failed(
                        pool, request_id=request_id, error_code=code
                    )
                    yield encode_sse(
                        "error",
                        {
                            "request_id": request_id,
                            "conversation_id": conversation_id,
                            "code": code,
                            "message": str(data.get("message") or "智能体执行失败"),
                            "retryable": bool(data.get("retryable", True)),
                        },
                    )
                    return
                elif event == "completed":
                    answer = str(data.get("answer") or full_answer)
                    metadata = data.get("metadata")
                    if not isinstance(metadata, dict):
                        metadata = {}
                    if not answer:
                        raise UpstreamServiceError(
                            "智能体未返回答案", code="agent_invalid_response"
                        )
                    if not full_answer:
                        full_answer = answer
                        yield encode_sse(
                            "delta",
                            {
                                "request_id": request_id,
                                "conversation_id": conversation_id,
                                "text": answer,
                            },
                        )
                    message_id = await insert_assistant_message(
                        pool,
                        conversation_id=conversation_id,
                        content=answer,
                        request_id=request_id,
                        metadata=metadata,
                    )
                    completed = True
                    yield encode_sse(
                        "completed",
                        {
                            "request_id": request_id,
                            "conversation_id": conversation_id,
                            "message_id": message_id,
                            "answer": answer,
                            "metadata": metadata,
                        },
                    )
                    return

            if not completed:
                raise UpstreamServiceError(
                    "智能体响应意外中断", code="agent_stream_incomplete"
                )
        except asyncio.CancelledError:
            await mark_request_failed(
                pool, request_id=request_id, error_code="client_disconnected"
            )
            raise
        except UpstreamServiceError as exc:
            await mark_request_failed(
                pool, request_id=request_id, error_code=exc.code
            )
            yield encode_sse(
                "error",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                },
            )
        except Exception:
            await mark_request_failed(
                pool, request_id=request_id, error_code="gateway_stream_error"
            )
            yield encode_sse(
                "error",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "code": "gateway_stream_error",
                    "message": "网关处理智能体响应失败",
                    "retryable": True,
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/test-cases/review", response_class=StreamingResponse, tags=["test-cases"])
async def review_test_case(
    payload: WorkflowRequest,
    user: Annotated[dict, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> StreamingResponse:
    """测试用例评审专用入口，固定路由到 Agent 3。"""
    return await send_chat_message(
        ChatRequest(
            query=payload.query,
            agent_id="accounting-expert",
            client_message_id=payload.client_message_id,
        ),
        user,
        settings,
        pool,
    )


@router.post("/test-cases/generate-steps", response_class=StreamingResponse, tags=["test-cases"])
async def generate_test_case_steps(
    payload: WorkflowRequest,
    user: Annotated[dict, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> StreamingResponse:
    """测试步骤生成专用入口，固定路由到 Agent 4。"""
    return await send_chat_message(
        ChatRequest(
            query=payload.query,
            agent_id="business-analyst",
            client_message_id=payload.client_message_id,
        ),
        user,
        settings,
        pool,
    )
