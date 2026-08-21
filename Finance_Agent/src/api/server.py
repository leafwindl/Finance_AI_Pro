"""
FastAPI 统一 API 服务 — Gateway SSE 标准

启动: python -m src.api.server
访问: http://localhost:8000/docs
"""
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# Windows 兼容：agent5 多轮记忆（psycopg AsyncConnection / PostgresSaver）
# 只支持 SelectorEventLoop，而 Windows 默认（及 uvicorn>=0.51 硬编码）是
# ProactorEventLoop。必须在模块导入期设置策略（用 `python -m src.api.server`
# 启动时先于 uvicorn.run 生效），且下方 uvicorn.run 需传 loop="none" 让
# uvicorn 不创建自己的事件循环工厂，否则策略会被无视。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 让 5 个 Agent 保持原版导入路径
sys.path.append(str(_PROJECT_ROOT / "agents" / "agent1"))
sys.path.append(str(_PROJECT_ROOT / "agents" / "agent2"))
sys.path.append(str(_PROJECT_ROOT / "agents" / "agent3"))
sys.path.append(str(_PROJECT_ROOT / "agents" / "agent4"))
sys.path.append(str(_PROJECT_ROOT / "agents" / "agent5"))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Literal
from contextlib import asynccontextmanager
import uvicorn
import httpx

from src.config.settings import load_dotenv_on_startup, settings
load_dotenv_on_startup()

logger = logging.getLogger("uvicorn.error")


# ============================================================
# 端口管理子系统初始化
# ============================================================
def _parse_range(s: str) -> tuple[int, int]:
    """解析 "8101-8199" 格式的范围字符串"""
    parts = s.strip().split("-")
    return int(parts[0]), int(parts[1])


_port_registry = None
_port_manager = None

if settings.PORT_MANAGER_ENABLED:
    from src.port_manager import (
        PortRegistry, PortAllocator, PortManager,
        init_router, router as port_router,
    )

    _port_registry = PortRegistry(
        pool_start=settings.PORT_POOL_START,
        pool_end=settings.PORT_POOL_END,
    )
    _port_registry.MAX_IDLE_SECONDS = settings.PORT_LEASE_DURATION
    _port_registry.SWEEP_INTERVAL = settings.PORT_SWEEP_INTERVAL

    _port_allocator = PortAllocator(
        _port_registry,
        preferred_ranges={
            "agent1": _parse_range(settings.PORT_AGENT1_RANGE),
            "agent2": _parse_range(settings.PORT_AGENT2_RANGE),
            "agent3": _parse_range(settings.PORT_AGENT3_RANGE),
            "agent4": _parse_range(settings.PORT_AGENT4_RANGE),
        },
    )
    _port_manager = PortManager(
        _port_registry,
        _port_allocator,
        heartbeat_interval=settings.PORT_HEARTBEAT_INTERVAL,
        lease_duration=settings.PORT_LEASE_DURATION,
    )
    init_router(_port_manager)
    logger.info(
        "端口管理已启用: pool=%d-%d",
        settings.PORT_POOL_START, settings.PORT_POOL_END,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时开启端口清理，关闭时停止"""
    if _port_registry is not None:
        await _port_registry.start_sweep_worker()
    yield
    if _port_registry is not None:
        await _port_registry.stop_sweep_worker()


app = FastAPI(
    title="智能测试全流程平台",
    description="4 个 AI 智能体协作：需求评审 → 需求分析 → 用例评审 → 步骤生成",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册端口管理路由
if settings.PORT_MANAGER_ENABLED:
    app.include_router(port_router)

SSE_RESPONSES = {
    200: {
        "description": "Server-Sent Events stream",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


# ============================================================
# 请求模型
# ============================================================
class TextAttachment(BaseModel):
    file_id: str = ""
    filename: str = ""
    content_type: str = "text/plain"
    text: str = Field(default="", max_length=200_000)


class InternalChatRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(default="default", min_length=1, max_length=128)
    agent_id: Literal[
        "requirement-pre-review",
        "ai-test-analysis",
        "accounting-expert",
        "business-analyst",
        "ai-assistant",
    ]
    query: str = Field(min_length=1, max_length=5000)
    attachments: list[TextAttachment] = Field(default_factory=list, max_length=5)


class InternalApprovalRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    agent_id: Literal["requirement-pre-review"]
    approval_id: str = Field(min_length=1, max_length=128)
    decision: Literal["approve", "reject", "revise"]
    reason: str = Field(default="", max_length=500)


_pending_approvals: dict[str, dict] = {}


# ============================================================
# SSE 工具函数
# ============================================================
def _event_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _execution_error(exc: Exception) -> tuple[str, str, bool]:
    detail = str(exc).lower()
    if "knowledge_base_unavailable" in detail:
        return "knowledge_base_unavailable", "知识库检索服务暂不可用", True
    if "authentication" in detail or "error code: 401" in detail:
        return "model_authentication_failed", "大模型鉴权失败，请检查 Agent 配置", False
    if any(text in detail for text in (
        "server disconnected", "empty reply", "connection refused",
        "connecterror", "remoteprotocolerror",
    )):
        return "model_connection_lost", "远程 Ollama 连接已断开，请检查 SSH 隧道和 Ollama 服务", True
    return "agent_execution_failed", "智能体执行失败", True


def _query_with_attachments(query: str, attachments: list[TextAttachment]) -> str:
    parts = [query]
    for a in attachments:
        if a.text.strip():
            parts.append(f"附件《{a.filename}》内容：\n{a.text.strip()}")
    return "\n\n".join(parts)


# ============================================================
# 可选 API Token 鉴权（2026-08-07 新增，修复安全审查发现#7）
#   - 未配置 AGENT_API_TOKEN 时放行（本地/内网向后兼容）
#   - 配置后要求请求带 X-Agent-Token header，否则 401
# ============================================================
def _require_agent_token(request: Request) -> None:
    expected = os.environ.get("AGENT_API_TOKEN", "").strip()
    if not expected:
        return  # 未配置 → 放行
    provided = request.headers.get("X-Agent-Token", "")
    if provided != expected:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_agent_token", "message": "Agent API Token 无效"},
        )


# ============================================================
# 各 Agent 节点进度映射
# ============================================================
REVIEW_NODE_PROGRESS = {
    "requirement_parser":      "正在解析需求内容...",
    "keyword_extractor":       "正在提取需求关键词...",
    "kb_router":               "正在路由知识库查询...",
    "knowledge_retrieval":     "正在检索行业知识库...",
    "six_points_eval":         "正在进行六维完整性评估...",
    "risk_assessment":         "正在分析业务与合规风险...",
    "report_generator":        "正在生成预评审报告...",
    "extract_info":            "正在进行风险预评估与需求分析...",
    "generate_confirmation":   "正在生成确认总结...",
    "recognize_intent":        "正在理解回复意图...",
    "extract_modifications":   "正在提取修改内容...",
    "generate_reconfirmation": "正在重新确认需求...",
    "generate_spec":           "正在生成规范需求报告...",
}

ANALYSIS_NODE_PROGRESS = {
    "extract_keywords": "正在分析需求，提取关键词...",
    "retrieve_all":     "正在检索知识库...",
    "rag_response":     "正在生成测试分析报告...",
    "chat_response":    "正在生成回复...",
}

CASE_REVIEW_NODE_PROGRESS = {
    "keyword":              "正在提取三维检索关键词...",
    "retrieval_merge":      "检索结果汇聚完成",
    "review_generate":      "正在执行18项检查清单评审...",
    "score":                "报告生成中...",
}

STEP_GEN_NODE_PROGRESS = {
    "extract_keyword_node":     "正在提取测试关键词...",
    "kb_route_node":            "正在路由知识库...",
    "knowledge_retrieve_node":  "正在检索测试相关知识...",
    "llm_gen_json_node":        "正在生成测试步骤...",
    "json_to_python_node":      "正在解析结果...",
    "gen_markdown_node":        "正在生成步骤文档...",
}

ASSISTANT_NODE_PROGRESS = {
    "intent_recognition": "正在理解你的意图...",
    "kb_retrieve":        "正在检索知识库...",
    "answer_generate":    "正在生成回答...",
    "transfer_agent":     "正在确认跳转...",
}


# ============================================================
# 4 个 SSE 流式生成器（调原版 Agent 代码）
# ============================================================
async def _stream_requirement_review(state: dict, req: InternalChatRequest):
    """② 需求评审 — 原版 Agent(1)"""
    try:
        from src.agents.agent1.graph.workflow import build_graph as build_review_graph
        app = build_review_graph()
        final_state = dict(state)
        # LangGraph updates are emitted after a node finishes. Send the first
        # stage immediately, then announce the next stage after each update so
        # the UI reflects what is actually running instead of appearing stuck.
        yield _event_sse("progress", {
            "request_id": req.request_id,
            "node": "requirement_parser",
            "message": REVIEW_NODE_PROGRESS["requirement_parser"],
        })
        next_node = {
            "requirement_parser": "keyword_extractor",
            "keyword_extractor": "kb_router",
            "kb_router": "knowledge_retrieval",
            "knowledge_retrieval": "six_points_eval",
            "six_points_eval": "risk_assessment",
            "risk_assessment": "report_generator",
        }
        config = {"configurable": {"thread_id": req.thread_id}}
        async for chunk in app.astream(state, config=config, stream_mode="updates"):
            node_name = next(iter(chunk))
            node_update = chunk[node_name]
            if isinstance(node_update, dict):
                final_state.update(node_update)
            upcoming = next_node.get(node_name)
            msg = REVIEW_NODE_PROGRESS.get(upcoming) if upcoming else None
            if msg:
                yield _event_sse("progress", {
                    "request_id": req.request_id, "node": upcoming, "message": msg,
                })

        answer = final_state.get("final_output", "") or "（未生成回复）"
        yield _event_sse("delta", {"request_id": req.request_id, "text": answer})
        approval_id = f"approval_{uuid.uuid4().hex}"
        _pending_approvals[req.thread_id] = {
            "approval_id": approval_id,
            "user_id": req.user_id,
            "agent_id": req.agent_id,
            "answer": answer,
        }
        yield _event_sse("approval_required", {
            "request_id": req.request_id,
            "thread_id": req.thread_id,
            "approval_id": approval_id,
            "answer": answer,
            "options": ["approve", "reject", "revise"],
        })
    except Exception as exc:
        logger.exception("requirement_review 执行失败")
        code, message, retryable = _execution_error(exc)
        yield _event_sse("error", {
            "request_id": req.request_id, "code": code, "message": message,
            "retryable": retryable,
        })


async def _stream_requirement_analysis(state: dict, req: InternalChatRequest):
    """⑦ 需求分析 — 原版 Requirements Test Analysis"""
    from src.agents.agent2.core.graph import agent_graph as analysis_graph
    from src.agents.agent2.loader import default_loader

    default_loader.load()
    final_state = dict(state)
    try:
        async for event in analysis_graph.astream_events(
            state,
            config={"configurable": {"user_id": req.user_id, "thread_id": req.thread_id}},
            version="v2",
        ):
            etype = event.get("event", "")
            name = event.get("name", "")
            if etype == "on_chain_start" and name in ANALYSIS_NODE_PROGRESS:
                yield _event_sse("progress", {
                    "request_id": req.request_id, "node": name,
                    "message": ANALYSIS_NODE_PROGRESS[name],
                })
            if etype == "on_chain_end" and name in ANALYSIS_NODE_PROGRESS:
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    final_state.update(output)

        # `aggregated_context` 是提供给模型的知识库检索原文，不是六维报告。
        # Agent 2 的最终报告由 rag_response/chat_response 写入最后一条 AI 消息。
        answer = ""
        messages = final_state.get("messages") or []
        if messages:
            content = getattr(messages[-1], "content", "")
            if isinstance(content, str):
                answer = content
            elif isinstance(content, list):
                answer = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )
            else:
                answer = str(content)
        answer = answer or "（未生成六维测试分析报告）"
        yield _event_sse("delta", {"request_id": req.request_id, "text": answer})
        yield _event_sse("completed", {
            "request_id": req.request_id, "thread_id": req.thread_id,
            "answer": answer, "metadata": {},
        })
    except Exception as exc:
        logger.exception("requirement_analysis 执行失败")
        code, message, retryable = _execution_error(exc)
        yield _event_sse("error", {
            "request_id": req.request_id, "code": code, "message": message,
            "retryable": retryable,
        })


async def _stream_test_case_review(state: dict, req: InternalChatRequest):
    """⑩ 用例评审 — 原版 Intelligent Test Case Review Agent(8)"""
    from src.agents.agent3.graph.workflow import build_graph as build_case_graph

    # 原版用同步 graph.stream()，这里用 astream
    graph = build_case_graph()
    final_state = dict(state)
    seen_retrieval = False

    try:
        yield _event_sse("progress", {
            "request_id": req.request_id, "node": "keyword",
            "message": CASE_REVIEW_NODE_PROGRESS["keyword"],
        })
        async for chunk in graph.astream(state, stream_mode="updates"):
            node_name = next(iter(chunk))
            node_update = chunk[node_name]
            if isinstance(node_update, dict):
                final_state.update(node_update)

            if node_name in ("standard_retrieval", "spec_retrieval", "history_retrieval"):
                if seen_retrieval:
                    continue
                seen_retrieval = True
                yield _event_sse("progress", {
                    "request_id": req.request_id, "node": "retrieval",
                    "message": "正在并行检索三维知识库...",
                })
            else:
                msg = CASE_REVIEW_NODE_PROGRESS.get(node_name)
                if msg:
                    yield _event_sse("progress", {
                        "request_id": req.request_id, "node": node_name, "message": msg,
                    })

        report = final_state.get("report_text", "") or "（未生成报告）"
        checklist = final_state.get("checklist", [])
        passed = sum(1 for c in checklist if c.get("passed"))
        pass_flag = final_state.get("pass_flag", False)
        yield _event_sse("delta", {"request_id": req.request_id, "text": report})
        yield _event_sse("completed", {
            "request_id": req.request_id, "thread_id": req.thread_id,
            "answer": report,
            "metadata": {
                "pass_flag": pass_flag,
                "coverage": f"{passed}/{len(checklist)}",
                "checklist": checklist,
            },
        })
    except Exception as exc:
        logger.exception("test_case_review 执行失败")
        code, message, retryable = _execution_error(exc)
        yield _event_sse("error", {
            "request_id": req.request_id, "code": code, "message": message,
            "retryable": retryable,
        })


async def _stream_test_step_generator(state: dict, req: InternalChatRequest):
    """⑬ 步骤生成 — 原版 Agent_4-main(1)"""
    from modules.workflow.graph import build_workflow_graph

    graph = build_workflow_graph()
    final_state = dict(state)

    try:
        yield _event_sse("progress", {
            "request_id": req.request_id, "node": "extract_keyword_node",
            "message": STEP_GEN_NODE_PROGRESS["extract_keyword_node"],
        })
        async for chunk in graph.astream(state, stream_mode="updates"):
            node_name = next(iter(chunk))
            node_update = chunk[node_name]
            if isinstance(node_update, dict):
                final_state.update(node_update)
            msg = STEP_GEN_NODE_PROGRESS.get(node_name)
            if msg:
                yield _event_sse("progress", {
                    "request_id": req.request_id, "node": node_name, "message": msg,
                })

        if final_state.get("is_success") != 1:
            yield _event_sse("error", {
                "request_id": req.request_id,
                "code": "agent_result_invalid",
                "message": final_state.get("error_msg") or "智能体返回无效结果",
                "retryable": False,
            })
            return

        answer = final_state.get("output_text", "") or "（未生成回复）"
        data = final_state.get("parse_data") or []
        yield _event_sse("delta", {"request_id": req.request_id, "text": answer})
        yield _event_sse("completed", {
            "request_id": req.request_id, "thread_id": req.thread_id,
            "answer": answer,
            "metadata": {
                "retrieval_count": len(final_state.get("rag_docs") or []),
                "steps": data,
            },
        })
    except Exception as exc:
        logger.exception("test_step_generator 执行失败")
        code, message, retryable = _execution_error(exc)
        yield _event_sse("error", {
            "request_id": req.request_id, "code": code, "message": message,
            "retryable": retryable,
        })


async def _stream_ai_assistant(state: dict, req: InternalChatRequest):
    """⑤ 智能对话助手 — 通用对话 + 知识库问答 + 文档问答 + 转交

    多轮记忆：PostgresSaver（AsyncPostgresSaver，首次请求惰性挂载），
    按 thread_id（= conversation_id）隔离会话；挂载失败自动降级单轮。
    图为异步节点，用 astream 逐节点输出。
    """
    import src.agents.agent5.core.graph as agent5_graph

    # 首次请求惰性挂载 PostgresSaver（幂等；失败保持单轮）
    await agent5_graph.attach_checkpointer()
    assistant_graph = agent5_graph.assistant_graph

    final_state = dict(state)
    # thread_id 作为记忆 key（同一会话共享，不同会话独立）
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        async for chunk in assistant_graph.astream(state, config=config, stream_mode="updates"):
            node_name = next(iter(chunk))
            node_update = chunk[node_name]
            if isinstance(node_update, dict):
                final_state.update(node_update)
            msg = ASSISTANT_NODE_PROGRESS.get(node_name)
            if msg:
                yield _event_sse("progress", {
                    "request_id": req.request_id, "node": node_name, "message": msg,
                })

        answer = final_state.get("answer", "") or "（未生成回答）"
        yield _event_sse("delta", {"request_id": req.request_id, "text": answer})
        intent = final_state.get("intent", "")
        metadata: dict = {"intent": intent}
        # 跳转调度（2026-08-20）：transfer_confirm 且目标已锁定 → 带 transfer 指令（前端据此跳页）
        if intent == "transfer_confirm" and final_state.get("transfer_target"):
            metadata["transfer"] = {
                "target": final_state.get("transfer_target"),
                "query": final_state.get("transfer_query", ""),
            }
        yield _event_sse("completed", {
            "request_id": req.request_id, "thread_id": req.thread_id,
            "answer": answer,
            "metadata": metadata,
        })
    except Exception as exc:
        logger.exception("ai_assistant 执行失败")
        code, message, retryable = _execution_error(exc)
        yield _event_sse("error", {
            "request_id": req.request_id, "code": code, "message": message,
            "retryable": retryable,
        })


# ============================================================
# API 路由
# ============================================================
@app.get("/")
async def root():
    return {"service": "智能测试全流程平台", "agents": 5, "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent_id": "full-pipeline-platform"}


@app.get("/readiness")
async def readiness():
    checks = {
        "model": "unconfigured",
        "knowledge-base": "unconfigured",
    }
    # 模型检查：本项目模型统一走 DeepSeek 云端 API（.env DEEPSEEK_API_KEY），
    # 配置了即视为 ok；未配置时回退检查 Ollama（向后兼容旧部署）。
    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        checks["model"] = "ok"
    else:
        model_base_url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if model_base_url:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(f"{model_base_url}/api/tags")
                checks["model"] = "ok" if response.is_success else "unavailable"
            except httpx.HTTPError:
                checks["model"] = "unavailable"
    kb_base_url = os.getenv("KB_BASE_URL", "").rstrip("/")
    if kb_base_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{kb_base_url}/health")
            checks["knowledge-base"] = "ok" if response.is_success else "unavailable"
        except httpx.HTTPError:
            checks["knowledge-base"] = "unavailable"
    ready = checks["model"] == "ok" and checks["knowledge-base"] == "ok"
    return {"status": "ok" if ready else "degraded", "checks": checks}


@app.post(
    "/v1/agent/chat",
    summary="Gateway 统一 SSE 智能体接口",
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
    dependencies=[Depends(_require_agent_token)],
)
async def gateway_chat(req: InternalChatRequest) -> StreamingResponse:
    """
    Gateway 统一入口 — 根据显式 agent_id 精确路由到对应 Agent。

    SSE 事件: progress → delta → completed / error
    """
    query = _query_with_attachments(req.query, req.attachments)
    # agent1/agent5 通过 file_content 单独携带附件文本，此处用未拼附件的原始 query，
    # 避免同一批附件全文被塞进输入两遍（审计报告中严重度第 3 项）
    raw_query = req.query
    ROUTE_MAP = {
        "requirement-pre-review": ("agent1", _stream_requirement_review),
        "ai-test-analysis": ("agent2", _stream_requirement_analysis),
        "accounting-expert": ("agent3", _stream_test_case_review),
        "business-analyst": ("agent4", _stream_test_step_generator),
        "ai-assistant": ("agent5", _stream_ai_assistant),
    }
    agent_type, stream_fn = ROUTE_MAP[req.agent_id]

    logger.info(
        "[Gateway] thread=%s agent_id=%s → agent=%s",
        req.thread_id,
        req.agent_id,
        agent_type,
    )

    # 构建各 Agent 的初始 state
    if agent_type == "agent1":
        # 原始 query + 附件文本进 file_content（requirement_parser 等节点会读取该字段拼进 prompt，
        # 与 agent1 自身 /review 入口的取法一致；不再把附件拼进 requirement_input，避免重复）
        file_texts = [a.text.strip() for a in req.attachments if a.text.strip()]
        file_content = "\n\n".join(file_texts)
        file_name = req.attachments[0].filename if req.attachments else ""
        state = {
            "requirement_input": raw_query,
            "file_content": file_content,
            "file_name": file_name,
        }
    elif agent_type == "agent2":
        from langchain_core.messages import HumanMessage
        state = {"messages": [HumanMessage(content=query)]}
    elif agent_type == "agent3":
        state = {"query": query}
    elif agent_type == "agent4":
        state = {
            "query": query, "test_case": None, "doc_content": "",
            "kb_keywords": {}, "kb_task_list": [], "rag_docs": [],
            "llm_json_raw": "", "parse_data": None,
            "is_success": 0, "output_text": "",
            "error_msg": "", "progress_msg": "",
        }
    elif agent_type == "agent5":
        from langchain_core.messages import HumanMessage
        # 原始 query + 附件文本进 file_content（文档问答/意图路由用，route 依赖 file_content 判 doc_qa/transfer；
        # 不再把附件拼进 query/messages，避免重复）
        file_texts = [a.text.strip() for a in req.attachments if a.text.strip()]
        state = {
            "messages": [HumanMessage(content=raw_query)],
            "query": raw_query,
            "file_content": "\n\n".join(file_texts),
            "file_name": req.attachments[0].filename if req.attachments else "",
            "intent": "",
            "retrieval_context": "",
            "pending_transfer_target": "",
            "transfer_target": "",
            "transfer_query": "",
            "answer": "",
        }
    else:
        raise HTTPException(status_code=400, detail=f"无法路由: {agent_type}")

    return StreamingResponse(
        stream_fn(state, req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/v1/agent/approve", summary="处理 Gateway 转发的审批决策",
          dependencies=[Depends(_require_agent_token)])
async def approve_agent(req: InternalApprovalRequest):
    pending = _pending_approvals.get(req.thread_id)
    if pending is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "approval_not_pending", "message": "当前没有待处理审批"},
        )
    if (
        pending["approval_id"] != req.approval_id
        or pending["user_id"] != req.user_id
        or pending["agent_id"] != req.agent_id
    ):
        raise HTTPException(status_code=403, detail="审批信息与待处理状态不匹配")

    _pending_approvals.pop(req.thread_id, None)
    return {
        "ok": True,
        "thread_id": req.thread_id,
        "approval_id": req.approval_id,
        "decision": req.decision,
    }


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    uvicorn.run(
        "src.api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        # 不干预事件循环工厂：Windows 上用导入期设置的 Selector 策略，
        # macOS/Linux 默认策略本身就是 Selector，行为不变。
        loop="none",
    )
