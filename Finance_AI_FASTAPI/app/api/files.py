from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.data_gateway.pool import get_pool
from app.data_gateway.repositories.files import create_file_record
from app.knowledge_gateway.extraction import IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/api/v1", tags=["files"])


class FileUploadResponse(BaseModel):
    file_id: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=1)
    status: Literal["ready"] = "ready"


@router.post("/files/upload", status_code=201)
async def upload_file(
    user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
    agent_id: str = Form(default=""),
    settings: Settings = Depends(get_settings),
    pool=Depends(get_pool),
) -> FileUploadResponse:
    del agent_id  # 文件归用户所有，不绑定某个 Agent。
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(400, detail=f"不支持的文件类型，仅允许: {allowed}")

    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = f"file_{uuid.uuid4().hex}"
    storage_path = (upload_dir / f"{file_id}{extension}").resolve()
    if upload_dir not in storage_path.parents:
        raise HTTPException(400, detail="非法文件路径")

    # 契约 §5.1：图片单张 ≤5 MB，普通文件 ≤10 MB
    is_image = extension in IMAGE_EXTENSIONS
    max_bytes = settings.upload_image_max_bytes if is_image else settings.upload_max_bytes
    limit_mb = max_bytes // (1024 * 1024)

    size = 0
    try:
        with storage_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        400, detail=f"{'图片' if is_image else '文件'}超过 {limit_mb} MB 限制"
                    )
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, detail="文件不能为空")

        await create_file_record(
            pool,
            file_id=file_id,
            user_id=user["user_id"],
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            extension=extension,
            size_bytes=size,
            storage_path=str(storage_path),
            ttl_seconds=settings.upload_ttl_seconds,
        )
    except Exception:
        if storage_path.exists():
            storage_path.unlink()
        raise
    finally:
        await file.close()

    return FileUploadResponse(
        file_id=file_id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size=size,
        status="ready",
    )
