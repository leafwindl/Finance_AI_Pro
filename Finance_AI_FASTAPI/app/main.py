import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import httpx

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.files import router as files_router
from app.api.knowledge import router as knowledge_router
from app.core.config import get_settings
from app.data_gateway.pool import get_pool, close_pool
from app.core.exceptions import ClientError, UpstreamServiceError
from app.knowledge_gateway.kb_ingest import router as kb_ingest_router
from app.schemas.chat import HealthResponse
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await get_pool()
    except Exception:
        logger.exception(
            "database initialization failed; readiness will remain unavailable"
        )
    yield
    await close_pool()

app = FastAPI(
    title="Finance AI API",
    version="0.1.0",
    description="Vue、LangGraph Agent 与业务数据库之间的统一网关",
    lifespan=lifespan,
)
app.include_router(chat_router)
app.include_router(files_router)
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(kb_ingest_router)
app.include_router(knowledge_router)

@app.middleware("http")
async def log_http_request(request: Request, call_next):
    request_id = uuid4().hex[:8]
    request.state.request_id = request_id
    started_at = perf_counter()

    logger.info(
        "[request:%s] --> %s %s",
        request_id,
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - started_at) * 1000
        logger.exception(
            "[request:%s] !! unhandled error duration_ms=%.1f",
            request_id,
            duration_ms,
        )
        raise

    duration_ms = (perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "[request:%s] <-- %s %s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/v1/readiness", tags=["system"])
async def readiness_check() -> JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {}
    ready = True
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        ready = False

    timeout = httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0)
    agent_url = settings.agent_platform_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{agent_url}/health")
        agent_ready = response.is_success
    except httpx.HTTPError:
        agent_ready = False
    checks["agent"] = "ok" if agent_ready else "unavailable"
    ready = ready and agent_ready

    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "degraded", "checks": checks},
    )


@app.exception_handler(UpstreamServiceError)
async def handle_upstream_service_error(
    request: Request,
    exc: UpstreamServiceError,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(
        "[request:%s] upstream error code=%s status=%s message=%s",
        request_id,
        exc.code,
        exc.status_code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        },
    )


@app.exception_handler(ClientError)
async def handle_client_error(
    request: Request,
    exc: ClientError,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(
        "[request:%s] client error code=%s status=%s message=%s",
        request_id,
        exc.code,
        exc.status_code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        },
    )
