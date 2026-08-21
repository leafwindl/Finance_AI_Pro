from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError


def kb_headers(settings: Settings) -> dict[str, str]:
    """构造调用 KB 入库服务的请求头。

    沿袭 AGENT_API_TOKEN 模式：KB 侧配置 KB_INTERNAL_TOKEN 后请求须带 X-Agent-Token，
    未配置时不发送（向后兼容）。
    """
    headers: dict[str, str] = {}
    token = settings.kb_internal_token.strip()
    if token:
        headers["X-Agent-Token"] = token
    return headers


class KBClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ingest_chunks(
        self,
        *,
        kb_code: str,
        doc_id: str,
        title: str,
        source_file: str,
        chunks: list[dict],
    ) -> dict:
        return await self._post(
            "/ingest/chunks",
            {
                "kb_code": kb_code,
                "doc_id": doc_id,
                "title": title,
                "source_file": source_file,
                "chunks": chunks,
            },
        )

    async def ingest_delete(self, *, doc_id: str, kb_code: str) -> dict:
        return await self._post(
            "/ingest/delete", {"doc_id": doc_id, "kb_code": kb_code}
        )

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.settings.kb_ingest_url.rstrip('/')}{path}"
        timeout = httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url, json=payload, headers=kb_headers(self.settings)
                )
                if response.status_code >= 400:
                    raise UpstreamServiceError(
                        "知识库入库服务请求失败",
                        code="ingest_unavailable",
                        status_code=502,
                    )
                return response.json()
        except UpstreamServiceError:
            raise
        except httpx.TimeoutException as exc:
            raise UpstreamServiceError(
                "知识库入库服务响应超时",
                code="ingest_unavailable",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise UpstreamServiceError(
                "无法连接知识库入库服务",
                code="ingest_unavailable",
                status_code=503,
            ) from exc
