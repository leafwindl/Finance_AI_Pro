from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import ClientError, UpstreamServiceError
from app.data_gateway.pool import get_pool
from app.data_gateway.repositories import kb_tasks
from app.knowledge_gateway.extraction import FileTextError, extract_text
from app.knowledge_gateway.kb_client import KBClient

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

KB_CODES = {f"KB{i:02d}" for i in range(1, 7)}  # KB01 ~ KB06
KB_INGEST_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


# ---------------------------------------------------------------------------
# 切块（近似 classifier/prompts.py 的分段规则：100-500 字、标题/编号作边界）
# ---------------------------------------------------------------------------

def _heading_level(line: str) -> int:
    """识别一行是否为标题，返回层级（0 表示非标题）。

    无模型规则，兼容 Markdown 标题 + 中文章节/编号：
      # / ## / ###           -> 1 / 2 / 3
      第一章 / 1. / 一、       -> 1 / 2 / 2
      （一） / 1.1 / 1.1.1    -> 3
      规则编号：/ 用例编号：   -> 1
    """
    line = line.strip()
    if not line:
        return 0
    m = re.match(r"^(#{1,6})\s+", line)
    if m:
        return len(m.group(1))
    if re.match(r"^第[0-9一二三四五六七八九十百千零]+[章节篇卷部分]", line):
        return 1
    if re.match(r"^\d+\.\d+\.\d+", line):
        return 3
    if re.match(r"^\d+\.\d+", line):
        return 2
    if re.match(r"^[一二三四五六七八九十]+、", line):
        return 2
    if re.match(r"^[（(][一二三四五六七八九十]+[）)]", line):
        return 3
    if re.match(r"^\d+[.．、]", line):
        return 2
    if re.match(r"^(规则编号|用例编号|缺陷编号|需求编号|错误码)[:：]", line):
        return 1
    return 0


def _split_by_heading(text: str) -> list[tuple[str, str, int]]:
    """按标题切分为 [(heading, content, level)]。

    同时识别 Markdown 标题与中文章节/编号；无标题时整篇视为 ("文档", text, 0)。
    """
    sections: list[tuple[str, str, int]] = []
    heading = "文档"
    level = 0
    buf: list[str] = []
    for line in text.splitlines():
        lv = _heading_level(line)
        if lv:
            if buf:
                sections.append((heading, "\n".join(buf).strip(), level))
            heading = line.strip()
            level = lv
            buf = []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip(), level))
    return [(h, c, l) for h, c, l in sections if c.strip()]


def _split_long(content: str, max_chars: int) -> list[str]:
    """超长段落按空行/字数拆分，每段尽量 ≤ max_chars。"""
    if len(content) <= max_chars:
        return [content]
    paragraphs = re.split(r"\n\s*\n", content)
    pieces: list[str] = []
    buf = ""
    for para in paragraphs:
        if buf and len(buf) + len(para) > max_chars:
            pieces.append(buf.strip())
            buf = para
        else:
            buf = (buf + "\n\n" + para) if buf else para
        while len(buf) > max_chars:
            pieces.append(buf[:max_chars].strip())
            buf = buf[max_chars:]
    if buf.strip():
        pieces.append(buf.strip())
    return pieces


def _merge_short(chunks: list[dict], min_chars: int) -> list[dict]:
    """相邻同标题短块（< min_chars）合并。"""
    merged: list[dict] = []
    for ch in chunks:
        if (
            merged
            and ch["heading"] == merged[-1]["heading"]
            and len(merged[-1]["content"]) < min_chars
        ):
            merged[-1]["content"] = merged[-1]["content"] + "\n\n" + ch["content"]
        else:
            merged.append(dict(ch))
    return merged


def chunk_document(text: str, max_chars: int = 500, min_chars: int = 100) -> list[dict]:
    """切块：按标题切 → 超长按段落拆 → 短块合并。"""
    chunks: list[dict] = []
    for heading, content, level in _split_by_heading(text):
        for piece in _split_long(content, max_chars):
            chunks.append({"heading": heading, "content": piece, "level": level})
    return _merge_short(chunks, min_chars)


def split_document_by_level1(text: str, max_chars: int = 2000) -> list[dict]:
    """以一级标题（# / 第一章 等，level 1）为界切分文档。

    每个一级标题及其下全部内容（二/三级标题自动转 markdown）为一个块；
    无一级标题时整篇为一块（heading='文档'）。
    """
    sections: list[tuple[str, str, int]] = []
    heading = "文档"
    level = 0
    buf: list[str] = []
    for line in text.splitlines():
        lv = _heading_level(line)
        if lv == 1:
            if buf:
                sections.append((heading, "\n".join(buf).strip(), level))
            heading = re.sub(r"^#{1,6}\s*", "", line).strip()
            level = 1
            buf = []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip(), level))

    chunks: list[dict] = []
    for h, c, l in sections:
        if not c.strip():
            continue
        md_content = "\n".join(
            line
            if re.match(r"^#{1,6}\s+", line)          # 本身已是 markdown 标题 -> 保留
            else f"{'#' * lv} {line}"
            if (lv := _heading_level(line)) >= 2       # 中文编号标题 -> 转 markdown
            else line
            for line in c.splitlines()
        )
        for piece in _split_long(md_content, max_chars):
            chunks.append({"heading": h, "content": piece, "level": l or 1})
    return chunks


def chunk_to_markdown(chunk: dict) -> str:
    """单个切块转为一个 Markdown 文件内容：heading 按层级转 #/##/### + 正文。"""
    level = chunk.get("level", 0) or 0
    prefix = "#" * min(max(level, 1), 4)
    return f"{prefix} {chunk['heading']}\n\n{chunk['content'].strip()}\n"


def chunks_to_markdown(chunks: list[dict]) -> str:
    """将切块结果转为 Markdown 文本：heading 按层级转 #/##/###，content 为正文。

    每个 chunk 输出为一个 Markdown 小节，可写为单个 .md 文件。
    """
    parts = [chunk_to_markdown(ch) for ch in chunks]
    return "\n".join(parts).strip() + "\n"


# ---------------------------------------------------------------------------
# 后台入库任务
# ---------------------------------------------------------------------------

async def _classify_blocks(settings: Settings, md_blocks: list[str]) -> list[str]:
    """调本地分类隧道 -> 远程六库模型分类，返回每块的 kb_code。

    依赖 scripts/classify_tunnel.py 建立的本地端口（默认 8001）转发到服务器 127.0.0.1:8000。
    OUT_OF_SCOPE / UNCLASSIFIED 等原样返回，由调用方决定跳过。
    """
    if not md_blocks:
        return []
    timeout = httpx.Timeout(
        connect=10.0, read=settings.kb_classify_timeout_seconds, write=30.0, pool=10.0
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.kb_classify_url.rstrip('/')}/classify_batch",
                json={"texts": md_blocks},
            )
            if resp.status_code >= 400:
                raise UpstreamServiceError(
                    "分类服务返回错误", code="classify_unavailable", status_code=502
                )
            data = resp.json()
    except UpstreamServiceError:
        raise
    except httpx.TimeoutException as exc:
        raise UpstreamServiceError(
            "分类服务超时", code="classify_unavailable", status_code=504
        ) from exc
    except httpx.RequestError as exc:
        raise UpstreamServiceError(
            "无法连接分类服务（请先启动 SSH 隧道 scripts/classify_tunnel.py）",
            code="classify_unavailable",
            status_code=503,
        ) from exc

    if not isinstance(data, list):
        raise UpstreamServiceError(
            "分类服务返回格式异常", code="classify_unavailable", status_code=502
        )
    return [d.get("kb_code", "") if isinstance(d, dict) else "" for d in data]


async def _run_ingest(
    pool,
    settings: Settings,
    task_id: str,
    file_path: str,
    extension: str,
    kb_code: str,
    filename: str,
) -> None:
    try:
        await kb_tasks.mark_ingesting(pool, task_id=task_id)
        text, _ = await asyncio.to_thread(
            extract_text, file_path, extension, settings.extracted_text_max_chars
        )
        blocks = split_document_by_level1(text, max_chars=2000)
        if not blocks:
            raise FileTextError("文件中没有可切分的文本")

        md_blocks = [chunk_to_markdown(b) for b in blocks]
        if kb_code:
            # 人工指定：整篇所有块归同一库（V1 行为）
            classifications = [kb_code] * len(blocks)
        else:
            # 自动分类：块级多库
            classifications = await _classify_blocks(settings, md_blocks)

        ingested: list[dict] = []
        skipped = 0
        for block, kb in zip(blocks, classifications):
            if kb not in KB_CODES:
                skipped += 1
                continue
            block_doc_id = hashlib.sha256(
                chunk_to_markdown(block).encode("utf-8")
            ).hexdigest()[:24]
            result = await KBClient(settings).ingest_chunks(
                kb_code=kb,
                doc_id=block_doc_id,
                title=block["heading"],
                source_file=filename,
                chunks=[{"heading": block["heading"], "content": block["content"]}],
            )
            if not result.get("success"):
                raise UpstreamServiceError(
                    f"入库失败: {result.get('error', '未知错误')}",
                    code="ingest_unavailable",
                )
            ingested.append({
                "heading": block["heading"],
                "kb_code": kb,
                "doc_id": block_doc_id,
            })

        if not ingested:
            raise UpstreamServiceError(
                "没有可入库的知识块（全部 OUT_OF_SCOPE 或分类失败）",
                code="ingest_unavailable",
            )

        distribution: dict[str, int] = {}
        for item in ingested:
            distribution[item["kb_code"]] = distribution.get(item["kb_code"], 0) + 1

        single_kb = next(iter(distribution)) if len(distribution) == 1 else None
        single_doc = ingested[0]["doc_id"] if len(distribution) == 1 else None

        await kb_tasks.mark_completed(
            pool,
            task_id=task_id,
            blocks=ingested,
            kb_distribution=distribution,
            total_chunks=len(ingested),
            kb_code=single_kb,
            doc_id=single_doc,
        )
    except UpstreamServiceError as exc:
        await kb_tasks.mark_failed(
            pool, task_id=task_id, error_code=exc.code, error_message=exc.message
        )
    except FileTextError as exc:
        await kb_tasks.mark_failed(
            pool, task_id=task_id, error_code="extract_failed", error_message=str(exc)
        )
    except Exception as exc:  # 兜底：任何异常都标记 failed，不吞掉
        await kb_tasks.mark_failed(
            pool, task_id=task_id, error_code="ingest_failed", error_message=str(exc)
        )


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@router.post("/knowledge/upload", status_code=202)
async def upload_knowledge(
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
    kb_code: str = Form(""),
    settings: Settings = Depends(get_settings),
    pool=Depends(get_pool),
):
    kb_code = kb_code.strip().upper()
    if kb_code and kb_code not in KB_CODES:
        raise ClientError("kb_code 必须为 KB01~KB06", code="invalid_kb_code")
    # 空 kb_code → 全自动分类（后台任务调远程模型按块分类入库）

    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in KB_INGEST_EXTENSIONS:
        raise ClientError(
            "不支持的文件类型，仅允许: .md, .txt, .pdf, .docx",
            code="unsupported_file_type",
        )

    kb_dir = Path(settings.kb_sources_dir).resolve()
    kb_dir.mkdir(parents=True, exist_ok=True)
    file_id = f"file_{uuid.uuid4().hex}"
    storage_path = (kb_dir / f"{file_id}{extension}").resolve()
    if kb_dir not in storage_path.parents:
        raise ClientError("非法文件路径", code="invalid_request")

    size = 0
    try:
        with storage_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    raise ClientError("文件超过 10 MB 限制", code="file_too_large")
                output.write(chunk)
        if size == 0:
            raise ClientError("文件不能为空", code="empty_file")
    except Exception:
        if storage_path.exists():
            storage_path.unlink()
        raise
    finally:
        await file.close()

    task_id = f"kb_{uuid.uuid4().hex[:12]}"
    await kb_tasks.create_task(
        pool,
        task_id=task_id,
        file_id=file_id,
        user_id=user["user_id"],
        filename=filename,
        kb_code=kb_code,
    )

    background_tasks.add_task(
        _run_ingest,
        pool,
        settings,
        task_id,
        str(storage_path),
        extension,
        kb_code,
        filename,
    )

    return {
        "task_id": task_id,
        "file_id": file_id,
        "filename": filename,
        "status": "processing",
    }


@router.get("/knowledge/tasks/{task_id}")
async def get_knowledge_task(
    task_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    pool=Depends(get_pool),
):
    task = await kb_tasks.get_task(pool, task_id=task_id)
    if not task:
        raise ClientError("任务不存在", status_code=404, code="task_not_found")
    if task["user_id"] != user["user_id"]:
        raise ClientError("无权访问该任务", status_code=403, code="permission_denied")

    resp: dict = {
        "task_id": task["task_id"],
        "filename": task["filename"],
        "status": task["status"],
        "progress": {"stage": task["stage"], "percent": task["percent"]},
        "created_at": task["created_at"],
    }
    if task["status"] == "completed":
        dist = json.loads(task["kb_distribution"]) if task["kb_distribution"] else {}
        blocks = json.loads(task["blocks"]) if task["blocks"] else []
        resp["result"] = {
            "kb_distribution": dist,
            "total_chunks": task["total_chunks"],
            "blocks": blocks,
        }
        if task["kb_code"]:
            resp["result"]["kb_code"] = task["kb_code"]
            resp["result"]["doc_id"] = task["doc_id"]
    if task["status"] == "failed":
        resp["error"] = {
            "code": task["error_code"],
            "message": task["error_message"],
            "retryable": True,
        }
    return resp


@router.post("/knowledge/tasks/{task_id}/rollback")
async def rollback_knowledge_task(
    task_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
    pool=Depends(get_pool),
):
    task = await kb_tasks.get_task(pool, task_id=task_id)
    if not task:
        raise ClientError("任务不存在", status_code=404, code="task_not_found")
    if task["user_id"] != user["user_id"]:
        raise ClientError("无权访问该任务", status_code=403, code="permission_denied")
    if task["status"] != "completed":
        raise ClientError(
            "任务不在 completed 状态，无法回滚",
            status_code=409,
            code="task_not_rollbackable",
        )

    # 块级多库：按 blocks 逐块删除；无 blocks（单库/旧任务）按单 doc_id 删除
    deleted = 0
    if task["blocks"]:
        blocks = json.loads(task["blocks"])
        for b in blocks:
            r = await KBClient(settings).ingest_delete(
                doc_id=b["doc_id"], kb_code=b["kb_code"]
            )
            deleted += r.get("deleted_chunks", 0)
    else:
        r = await KBClient(settings).ingest_delete(
            doc_id=task["doc_id"], kb_code=task["kb_code"]
        )
        deleted = r.get("deleted_chunks", 0)

    await kb_tasks.mark_rolled_back(pool, task_id=task_id)

    return {
        "task_id": task_id,
        "status": "rolled_back",
        "deleted_chunks": deleted,
    }
