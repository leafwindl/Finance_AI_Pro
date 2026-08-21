"""Mock Agent — 回显 SSE 事件，用于前端联调测试"""
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import asyncio, json, uvicorn, sys

app = FastAPI()


class TextAttachment(BaseModel):
    file_id: str = ""
    filename: str = ""
    content_type: str = "text/plain"
    text: str = ""


class ChatRequest(BaseModel):
    request_id: str = Field(default="r1", min_length=1, max_length=128)
    thread_id: str = Field(default="t1", min_length=1, max_length=128)
    user_id: str = Field(default="u1", min_length=1, max_length=128)
    query: str = Field(default="你好", min_length=1, max_length=5000)
    attachments: list[TextAttachment] = Field(default_factory=list)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/agent/chat")
async def chat(req: ChatRequest):
    async def generate():
        yield f"event: progress\ndata: {json.dumps({'request_id': req.request_id, 'node': 'mock', 'message': '正在处理...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.5)
        answer = f"已收到：{req.query[:50]}。这是 Mock Agent 回复，用于开发调试。"
        yield f"event: delta\ndata: {json.dumps({'request_id': req.request_id, 'text': answer}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.3)
        yield f"event: completed\ndata: {json.dumps({'request_id': req.request_id, 'thread_id': req.thread_id, 'answer': answer, 'metadata': {}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8101
    uvicorn.run(app, host="127.0.0.1", port=port)
