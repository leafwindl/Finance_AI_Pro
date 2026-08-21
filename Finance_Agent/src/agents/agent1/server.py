"""
需求预评审智能体 - FastAPI 接口 (流水线版本)

重构说明:
    从"多轮对话 SSE 流式接口"改为"单次请求 → 完整报告返回"。
    删除了会话管理、SSE流式、对话接口等，
    改为单次 POST → 流水线自动执行 → 返回完整预评审报告。

启动方式:
    python server.py

接口:
    POST /v1/agent/review   Gateway 统一内部接口 (单次报告生成)
    POST /review            生成预评审报告 (同步)
    POST /review/async      生成预评审报告 (异步, 返回 task_id)
    GET  /review/status/{task_id}  查询异步任务状态
    GET  /health            进程存活检查
"""

import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graph.workflow import build_graph
from utils.file_reader import extract_text

agent_app = build_graph()
logger = logging.getLogger("uvicorn.error")

# 简单的内存异步任务存储 (生产环境可替换为 Redis/数据库)
_task_store: dict[str, dict] = {}


# ================================================================
# 节点 → 进度消息 (用于 SSE 场景, 保留以备扩展)
# ================================================================
NODE_PROGRESS_MESSAGES: dict[str, str] = {
    "requirement_parser":    "正在理解需求并结构化分析...",
    "keyword_extractor":     "正在提取多领域关键词...",
    "kb_router":             "正在路由知识库查询...",
    "knowledge_retrieval":   "正在检索证券行业知识库...",
    "six_points_eval":       "正在生成六大要点评估...",
    "risk_assessment":       "正在进行全面风险评估...",
    "report_generator":      "正在生成预评审报告...",
}


# ================================================================
# 请求 / 响应模型
# ================================================================

class TextAttachment(BaseModel):
    file_id: str = ""
    filename: str = ""
    content_type: str = "text/plain"
    text: str = Field(default="", max_length=200_000)


class ReviewRequest(BaseModel):
    """预评审请求"""
    request_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        min_length=1, max_length=128,
        description="请求ID，用于追踪"
    )
    thread_id: str = Field(
        default="",
        min_length=0, max_length=128,
        description="会话ID，可选"
    )
    user_id: str = Field(
        default="",
        min_length=0, max_length=128,
        description="用户ID，可选"
    )
    query: str = Field(
        min_length=1, max_length=10000,
        description="完整的需求描述文本"
    )
    attachments: list[TextAttachment] = Field(
        default_factory=list, max_length=5,
        description="附件列表（文本内容）"
    )


class RiskItem(BaseModel):
    """风险项"""
    risk: str = ""
    severity: str = ""
    source: str = ""
    mitigation: str = ""


class RiskAnalysis(BaseModel):
    """风险评估结果"""
    tech_risks: list[RiskItem] = Field(default_factory=list)
    business_risks: list[RiskItem] = Field(default_factory=list)
    compliance_risks: list[RiskItem] = Field(default_factory=list)
    data_risks: list[RiskItem] = Field(default_factory=list)
    overall_risk_level: str = ""
    risk_summary: str = ""
    key_concerns: list[str] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    """预评审报告响应"""
    request_id: str = ""
    report: str = Field(description="完整的预评审报告 (Markdown 格式)")
    # 摘要信息
    completeness_score: float = 0.0
    overall_risk_level: str = ""
    total_risks_identified: int = 0
    missing_items_count: int = 0
    # 结构化风险详情
    risk_analysis: Optional[RiskAnalysis] = None


class AsyncTaskResponse(BaseModel):
    """异步任务响应"""
    task_id: str
    status: str = "processing"  # processing / completed / failed
    message: str = "任务已提交，正在执行预评审流程..."


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    status: str  # processing / completed / failed
    result: Optional[ReviewResponse] = None
    error: Optional[str] = None


# ================================================================
# FastAPI 应用
# ================================================================

@asynccontextmanager
async def lifespan(_: FastAPI):
    """配置检查点存储器。"""
    global agent_app
    database_url = os.environ.get("LANGGRAPH_DATABASE_URL", "").strip()
    if database_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
            await checkpointer.setup()
            agent_app = build_graph(checkpointer=checkpointer)
            yield
    else:
        from langgraph.checkpoint.memory import MemorySaver

        agent_app = build_graph(checkpointer=MemorySaver())
        yield


app = FastAPI(
    title="证券需求预评审智能体",
    description="基于 LangGraph 的自动化需求预评审报告生成 API (流水线版本)",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================
# 核心: 执行预评审流水线
# ================================================================

async def _run_review_pipeline(req: ReviewRequest) -> ReviewResponse:
    """执行完整的预评审流水线并返回结构化响应。"""
    # 处理附件
    file_content = "\n\n".join(
        attachment.text.strip()
        for attachment in req.attachments
        if attachment.text.strip()
    )
    file_name = ", ".join(
        attachment.filename for attachment in req.attachments if attachment.filename
    )

    # 构造初始状态
    state = {
        "requirement_input": req.query,
        "file_content": file_content,
        "file_name": file_name,
    }

    logger.info(
        "[预评审] 开始执行 - request_id=%s, 需求长度=%d, 附件数=%d",
        req.request_id, len(req.query), len(req.attachments),
    )

    # 执行流水线
    config = {"configurable": {"thread_id": req.thread_id or req.request_id}}
    result = await agent_app.ainvoke(state, config=config)

    # 提取结果
    final_report = result.get("final_report", result.get("final_output", ""))
    risk_analysis = result.get("risk_analysis", {}) or {}
    six_points = result.get("six_points", {}) or {}
    requirement_analysis = result.get("requirement_analysis", {}) or {}

    # 计算统计信息
    parse_score = requirement_analysis.get("completeness_score", 0)
    six_score = six_points.get("completeness_score", 0)
    completeness_score = round(parse_score * 0.4 + six_score * 0.6, 1)

    all_risks = (
        risk_analysis.get("tech_risks", [])
        + risk_analysis.get("business_risks", [])
        + risk_analysis.get("compliance_risks", [])
        + risk_analysis.get("data_risks", [])
    )
    total_risks = len(all_risks)
    missing_count = len(six_points.get("missing_items", []))

    # 构造风险分析响应
    risk_resp = RiskAnalysis(
        tech_risks=[RiskItem(**r) for r in risk_analysis.get("tech_risks", [])],
        business_risks=[RiskItem(**r) for r in risk_analysis.get("business_risks", [])],
        compliance_risks=[RiskItem(**r) for r in risk_analysis.get("compliance_risks", [])],
        data_risks=[RiskItem(**r) for r in risk_analysis.get("data_risks", [])],
        overall_risk_level=risk_analysis.get("overall_risk_level", "未评估"),
        risk_summary=risk_analysis.get("risk_summary", ""),
        key_concerns=risk_analysis.get("key_concerns", []),
    )

    logger.info(
        "[预评审] 完成 - request_id=%s, 完整度=%.1f%%, 风险等级=%s, 风险数=%d",
        req.request_id, completeness_score,
        risk_analysis.get("overall_risk_level", "N/A"), total_risks,
    )

    return ReviewResponse(
        request_id=req.request_id,
        report=final_report,
        completeness_score=completeness_score,
        overall_risk_level=risk_analysis.get("overall_risk_level", "未评估"),
        total_risks_identified=total_risks,
        missing_items_count=missing_count,
        risk_analysis=risk_resp,
    )


# ================================================================
# 接口
# ================================================================

@app.get("/health", summary="进程存活检查")
async def health() -> dict:
    return {"status": "ok", "agent_id": "requirement-pre-review", "version": "2.0.0"}


@app.post(
    "/v1/agent/review",
    response_model=ReviewResponse,
    summary="统一内部智能体接口 - 生成预评审报告",
)
async def unified_review(req: ReviewRequest) -> ReviewResponse:
    """
    统一内部接口: 接收需求描述，自动执行完整预评审流程，返回结构化报告。

    与旧版 /v1/agent/chat 的区别:
        - 不再进行多轮对话
        - 不返回 SSE 流
        - 一次性返回完整预评审报告
    """
    try:
        return await _run_review_pipeline(req)
    except Exception as exc:
        logger.exception("[预评审] 执行失败")
        detail = str(exc).lower()
        if "knowledge_base_unavailable" in detail:
            raise HTTPException(
                status_code=503,
                detail="知识库检索服务暂不可用，请稍后重试",
            )
        if "authentication" in detail or "error code: 401" in detail:
            raise HTTPException(
                status_code=500,
                detail="大模型鉴权失败，请检查 Agent 配置",
            )
        raise HTTPException(
            status_code=500,
            detail=f"预评审执行失败: {str(exc)}",
        )


@app.post(
    "/review",
    response_model=ReviewResponse,
    summary="生成预评审报告 (同步)",
)
async def review_sync(req: ReviewRequest) -> ReviewResponse:
    """
    同步接口: 提交需求描述，等待完整预评审报告返回。

    适用于: 后端服务间调用、CLI 工具集成
    注意: 执行时间可能较长 (30-120秒)，取决于 LLM 响应速度和知识库检索时间
    """
    return await _run_review_pipeline(req)


@app.post(
    "/review/async",
    response_model=AsyncTaskResponse,
    summary="生成预评审报告 (异步)",
)
async def review_async(
    req: ReviewRequest,
    background_tasks: BackgroundTasks,
) -> AsyncTaskResponse:
    """
    异步接口: 提交需求描述后立即返回 task_id，
    通过 GET /review/status/{task_id} 查询结果。

    适用于: 前端页面调用，避免长时间等待
    """
    task_id = uuid.uuid4().hex[:16]
    _task_store[task_id] = {"status": "processing", "result": None, "error": None}

    async def _process():
        try:
            result = await _run_review_pipeline(req)
            _task_store[task_id] = {
                "status": "completed",
                "result": result,
                "error": None,
            }
        except Exception as exc:
            logger.exception("[异步预评审] 任务失败 - task_id=%s", task_id)
            _task_store[task_id] = {
                "status": "failed",
                "result": None,
                "error": str(exc),
            }

    background_tasks.add_task(_process)

    return AsyncTaskResponse(
        task_id=task_id,
        status="processing",
        message="任务已提交，正在执行预评审流程...",
    )


@app.get(
    "/review/status/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询异步任务状态",
)
async def review_status(task_id: str) -> TaskStatusResponse:
    """
    查询异步预评审任务的状态和结果。

    status 可能的值:
        - processing: 正在执行中
        - completed: 已完成, result 字段包含报告
        - failed: 执行失败, error 字段包含错误信息
    """
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        result=task.get("result"),
        error=task.get("error"),
    )


# ================================================================
# 文件上传接口 (兼容旧版)
# ================================================================

@app.post(
    "/review/file",
    response_model=ReviewResponse,
    summary="带文件上传的预评审报告生成",
)
async def review_with_file(
    message: str = Form(default="", description="需求描述文本（可与文件互补）"),
    file: UploadFile | None = File(default=None, description="需求文档"),
    request_id: str = Form(default=""),
) -> ReviewResponse:
    """
    带文件上传的同步预评审接口。

    支持格式: .txt .md .pdf .docx .xlsx

    使用方式 (multipart/form-data):
        form.append("message", "请帮我评审这个需求");
        form.append("file", fileInput.files[0]);
    """
    # 处理文件
    attachment_text = ""
    attachment_filename = ""
    if file and file.filename:
        file_bytes = await file.read()
        attachment_filename = file.filename
        attachment_text = extract_text(file_bytes, file.filename)
        logger.info("[文件上传] 解析完成: %s (%d bytes -> %d 字符)",
                     file.filename, len(file_bytes), len(attachment_text))

    # 组装请求
    req = ReviewRequest(
        request_id=request_id or uuid.uuid4().hex[:12],
        query=message.strip() or "请根据上传的需求文档进行预评审",
    )
    if attachment_text:
        req.attachments.append(TextAttachment(
            filename=attachment_filename,
            text=attachment_text,
        ))

    return await _run_review_pipeline(req)


# ================================================================
# 启动
# ================================================================

if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":
        import asyncio

        config = uvicorn.Config(
            app,
            host=os.environ.get("AGENT_HOST", "127.0.0.1"),
            port=int(os.environ.get("AGENT_PORT", "8101")),
        )
        server = uvicorn.Server(config)
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
    else:
        uvicorn.run(
            app,
            host=os.environ.get("AGENT_HOST", "127.0.0.1"),
            port=int(os.environ.get("AGENT_PORT", "8101")),
        )
