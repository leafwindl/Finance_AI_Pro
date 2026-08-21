"""解析服务 — FastAPI

接收文件上传，自动检测格式并提取纯文本。

API:
    POST /parse         — 单文件解析
    POST /parse/batch   — 批量解析
    GET  /health        — 健康检查
"""

import time
import traceback
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from shared.models import CleanedText
from parser.parsers import parse_file, supported_formats

app = FastAPI(
    title="知识库解析服务",
    description="多格式文档 → 清洗后纯文本",
    version="1.0.0",
)

# 与底层解析器注册表保持一致，避免解析器支持但 HTTP 白名单拒绝。
SUPPORTED_FORMATS = supported_formats()


@app.get("/health")
async def health():
    return {"status": "ok", "supported_formats": SUPPORTED_FORMATS}


@app.post("/parse", response_model=dict)
async def parse_single(file: UploadFile = File(...)):
    """解析单个文件，返回清洗后的文本。

    Args:
        file: 上传的文件（multipart/form-data）

    Returns:
        CleanedText 的 JSON 序列化结果
    """
    if not file.filename:
        raise HTTPException(400, "文件名为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"不支持的文件格式: {ext}，支持: {SUPPORTED_FORMATS}")

    t0 = time.time()
    try:
        # 保存上传文件到临时目录
        content_bytes = await file.read()
        with NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content_bytes)
            tmp_path = Path(tmp.name)

        # 调用解析器
        result = parse_file(tmp_path)

        # 清理临时文件
        tmp_path.unlink(missing_ok=True)

        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "success": True,
            "elapsed_ms": elapsed_ms,
            "data": _cleaned_text_to_dict(result),
        }

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"解析失败: {str(e)}")


@app.post("/parse/batch", response_model=dict)
async def parse_batch(files: list[UploadFile] = File(...)):
    """批量解析多个文件。

    Args:
        files: 上传的文件列表

    Returns:
        每个文件的解析结果列表
    """
    results = []
    errors = []
    for f in files:
        try:
            content_bytes = await f.read()
            ext = Path(f.filename).suffix.lower() if f.filename else ".txt"
            if ext not in SUPPORTED_FORMATS:
                errors.append({
                    "filename": f.filename,
                    "error": f"不支持的文件格式: {ext}，支持: {SUPPORTED_FORMATS}",
                })
                continue
            with NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content_bytes)
                tmp_path = Path(tmp.name)

            result = parse_file(tmp_path)
            tmp_path.unlink(missing_ok=True)
            results.append(_cleaned_text_to_dict(result))

        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})

    return {
        "total": len(files),
        "success": len(results),
        "errors": len(errors),
        "results": results,
        "error_details": errors,
    }


def _cleaned_text_to_dict(ct: CleanedText) -> dict:
    return {
        "content": ct.content,
        "source_filename": getattr(ct, "source_filename", getattr(ct, "source_path", "")),
        "source_type": getattr(ct, "source_type", getattr(ct, "source_format", "")),
        "encoding": getattr(ct, "encoding", ""),
        "content_hash": getattr(ct, "content_hash", ""),
        "metadata": getattr(ct, "metadata", {}),
    }
