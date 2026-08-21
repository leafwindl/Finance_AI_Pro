"""接入服务 — FastAPI

知识库系统的统一数据入口。接收文件上传，调度解析+分类服务，
返回可直接入库的结构化 chunk。

支持两种部署模式（环境变量 INGEST_MODE 控制）：
  - "direct"：同进程直接调用（开发/单机）
  - "http" ：通过 HTTP 调用独立服务（生产/微服务）

API:
    POST /ingest        — 单文件接入
    POST /ingest/batch  — 批量接入
    GET  /health        — 健康检查
"""

import os
import time
import traceback

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from shared.models import ChunkItem

app = FastAPI(
    title="知识库接入服务",
    description="文件上传 → 解析 → 分类 → 结构化 chunk 输出",
    version="1.0.0",
)

INGEST_MODE = os.getenv("INGEST_MODE", "direct")

# HTTP 模式下的下游服务地址
PARSE_SERVICE_URL = os.getenv("PARSE_SERVICE_URL", "http://parse-service:8001")
CLASSIFY_SERVICE_URL = os.getenv("CLASSIFY_SERVICE_URL", "http://classify-service:8002")


@app.get("/health")
async def health():
    ok = True
    parse_status = "unknown"
    classify_status = "unknown"

    if INGEST_MODE == "http":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{PARSE_SERVICE_URL}/health")
                parse_status = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            parse_status = str(e)
            ok = False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{CLASSIFY_SERVICE_URL}/health")
                classify_status = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            classify_status = str(e)
            ok = False

    return {
        "status": "ok" if ok else "degraded",
        "mode": INGEST_MODE,
        "parse_service": parse_status,
        "classify_service": classify_status,
    }


@app.post("/ingest")
async def ingest_single(file: UploadFile = File(...)):
    """接入单个文件，返回可直接入库的 chunk 列表。

    请求示例：
        curl -F "file=@report.txt" http://localhost:8003/ingest

    响应示例：
        {
          "success": true,
          "chunks": [{ "kb_id": "KB01", "content": "...", ... }],
          "stats": {"KB01": 2, "KB04": 1},
          "review_count": 0
        }
    """
    t0 = time.time()

    # ── 阶段1: 解析 ──
    t1 = time.time()
    try:
        if INGEST_MODE == "http":
            cleaned = await _parse_via_http(file)
        else:
            cleaned = await _parse_direct(file)
    except Exception as e:
        raise HTTPException(500, f"解析失败: {str(e)}")
    parse_ms = int((time.time() - t1) * 1000)

    # ── 阶段2: 分类 ──
    t2 = time.time()
    try:
        if INGEST_MODE == "http":
            classify_result = await _classify_via_http(cleaned)
        else:
            classify_result = _classify_direct(cleaned)
    except Exception as e:
        raise HTTPException(500, f"分类失败: {str(e)}")
    classify_ms = int((time.time() - t2) * 1000)

    total_ms = int((time.time() - t0) * 1000)

    return {
        "success": True,
        "total_ms": total_ms,
        "parse_ms": parse_ms,
        "classify_ms": classify_ms,
        "chunks": classify_result.get("chunks", []),
        "stats": classify_result.get("stats", {}),
        "review_count": classify_result.get("review_count", 0),
        "source_filename": file.filename,
    }


@app.post("/ingest/batch")
async def ingest_batch(files: list[UploadFile] = File(...)):
    """批量接入多个文件。"""
    results = []
    errors = []
    for f in files:
        try:
            if INGEST_MODE == "http":
                cleaned = await _parse_via_http(f)
                classify_result = await _classify_via_http(cleaned)
            else:
                cleaned = await _parse_direct(f)
                classify_result = _classify_direct(cleaned)

            results.append({
                "source": f.filename,
                "chunks": classify_result.get("chunks", []),
                "stats": classify_result.get("stats", {}),
                "review_count": classify_result.get("review_count", 0),
            })
        except Exception as e:
            errors.append({"source": f.filename, "error": str(e)})

    return {
        "total": len(files),
        "success": len(results),
        "errors": len(errors),
        "results": results,
        "error_details": errors,
    }


# ═══════════════════════════════════════════════════════════════
# Direct 模式 — 同进程调用
# ═══════════════════════════════════════════════════════════════

async def _parse_direct(file: UploadFile) -> dict:
    """直接调用解析器。"""
    from pathlib import Path
    from tempfile import NamedTemporaryFile
    from parser.parsers import parse_file

    content_bytes = await file.read()
    ext = Path(file.filename).suffix if file.filename else ".txt"
    with NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content_bytes)
        tmp_path = Path(tmp.name)

    try:
        result = parse_file(tmp_path)
        return {
            "content": result.content,
            "source_filename": result.source_filename,
            "source_type": result.source_type,
            "encoding": result.encoding,
            "content_hash": result.content_hash,
            "metadata": result.metadata,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def _classify_direct(cleaned: dict) -> dict:
    """直接调用分类流水线。"""
    # from services.classify_service.main import _run_pipeline

    chunks, stats, review_count = _run_pipeline(
        content=cleaned["content"],
        source_filename=cleaned["source_filename"],
        source_type=cleaned.get("source_type", "txt"),
    )

    return {
        "chunks": [c.__dict__ for c in chunks],
        "stats": stats,
        "review_count": review_count,
    }


# ═══════════════════════════════════════════════════════════════
# HTTP 模式 — 调用独立微服务
# ═══════════════════════════════════════════════════════════════

async def _parse_via_http(file: UploadFile) -> dict:
    """通过 HTTP 调用 parse-service。"""
    import httpx

    content_bytes = await file.read()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{PARSE_SERVICE_URL}/parse",
            files={"file": (file.filename, content_bytes)},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"解析服务返回失败")
        return data["data"]


async def _classify_via_http(cleaned: dict) -> dict:
    """通过 HTTP 调用 classify-service。"""
    import httpx

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{CLASSIFY_SERVICE_URL}/classify",
            json=cleaned,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"分类服务返回失败")
        return data["data"]
