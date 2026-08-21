from __future__ import annotations

import json
import logging
import os
from typing import AsyncGenerator

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from modules.api.file_parser import extract_text_from_file
from modules.workflow.graph import build_workflow_graph

app = FastAPI(title="测试步骤生成工作流 API", version="2.0.0")
graph = build_workflow_graph()
logger = logging.getLogger("uvicorn.error")

SSE_RESPONSES = {
    200: {
        "description": "Server-Sent Events stream",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


class TextAttachment(BaseModel):
    file_id: str
    filename: str
    content_type: str = "text/plain"
    text: str = Field(default="", max_length=200_000)


class InternalChatRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    test_case: dict = Field(..., max_length=50000)  # 唯一输入
    attachments: list[TextAttachment] = Field(default_factory=list, max_length=5)


def initial_state(doc_content: str = "", test_case: dict | None = None) -> dict:
    return {
        "test_case": test_case,
        "doc_content": doc_content,
        "keywords": [],
        "kb_keywords": {},
        "kb_task_list": [],
        "rag_docs": [],
        "llm_json_raw": "",
        "parse_data": None,
        "is_success": 0,
        "output_text": "",
        "error_msg": "",
        "progress_msg": "",
    }


def event_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def execution_error(exc: Exception) -> tuple[str, str, bool]:
    detail = str(exc).lower()
    if "knowledge_base_unavailable" in detail:
        return "knowledge_base_unavailable", "知识库检索服务暂不可用", True
    if "authentication" in detail or "error code: 401" in detail:
        return "model_authentication_failed", "大模型鉴权失败，请检查 Agent 配置", False
    return "agent_execution_failed", "智能体执行失败", True


async def run_updates(state: dict) -> AsyncGenerator[tuple[str, dict, dict], None]:
    final_state: dict = {}
    async for chunk in graph.astream(state, stream_mode="updates"):
        for node_name, state_data in chunk.items():
            if isinstance(state_data, dict):
                final_state.update(state_data)
                yield node_name, state_data, final_state


@app.get("/health", summary="进程存活检查")
async def health() -> dict:
    return {"status": "ok", "agent_id": "business-analyst"}


@app.post(
    "/v1/agent/chat",
    summary="统一内部智能体接口",
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def unified_chat(req: InternalChatRequest) -> StreamingResponse:
    doc_content = "\n\n".join(
        f"附件《{item.filename}》：\n{item.text.strip()}"
        for item in req.attachments
        if item.text.strip()
    )

    async def generate():
        final_state: dict = {}
        try:
            async for node_name, update, current in run_updates(
                initial_state(doc_content, req.test_case)
            ):
                final_state = current
                progress = update.get("progress_msg", "")
                if progress:
                    yield event_sse(
                        "progress",
                        {
                            "request_id": req.request_id,
                            "node": node_name,
                            "message": progress,
                        },
                    )
        except Exception as exc:
            logger.exception("Agent 4 execution failed")
            code, message, retryable = execution_error(exc)
            yield event_sse(
                "error",
                {
                    "request_id": req.request_id,
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                },
            )
            return

        answer = final_state.get("output_text", "") or "（未生成回复）"
        if final_state.get("is_success") != 1:
            yield event_sse(
                "error",
                {
                    "request_id": req.request_id,
                    "code": "agent_result_invalid",
                    "message": final_state.get("error_msg") or answer,
                    "retryable": False,
                },
            )
            return

        yield event_sse("delta", {"request_id": req.request_id, "text": answer})
        yield event_sse(
            "completed",
            {
                "request_id": req.request_id,
                "thread_id": req.thread_id,
                "answer": answer,
                "metadata": {
                    "retrieval_count": len(final_state.get("rag_docs") or []),
                    "steps": final_state.get("parse_data") or [],
                },
            },
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post(
    "/api/generate_test_step/stream",
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
    deprecated=True,
)
async def generate_test_step_stream(
    test_case: str = Form(...),
    doc: UploadFile | None = File(default=None),
) -> StreamingResponse:
    doc_content = await extract_text_from_file(doc) if doc else ""
    parsed_test_case = json.loads(test_case) if test_case else None

    async def generate():
        final_state: dict = {}
        try:
            async for _, update, current in run_updates(initial_state(doc_content, parsed_test_case)):
                final_state = current
                progress = update.get("progress_msg", "")
                if progress:
                    yield f"data: {json.dumps({'type': 'progress', 'content': progress}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            final_state = {
                "is_success": 0,
                "output_text": "",
                "parse_data": None,
                "error_msg": str(exc),
            }

        finish_data = {
            "type": "finish",
            "is_success": final_state.get("is_success", 0),
            "result_text": final_state.get("output_text", ""),
            "raw_parse_data": final_state.get("parse_data"),
            "error_msg": final_state.get("error_msg", ""),
        }
        yield f"data: {json.dumps(finish_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        "modules.api.api_server:app",
        host=os.environ.get("AGENT_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENT_PORT", "8104")),
        reload=True,
    )
