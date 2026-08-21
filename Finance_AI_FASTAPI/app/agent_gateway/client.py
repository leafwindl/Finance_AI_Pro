from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError
from app.agent_gateway.registry import AgentDefinition
from app.agent_gateway.sse import parse_sse


def agent_headers(settings: Settings) -> dict[str, str]:
    """构造调用 Agent 平台的请求头。

    契约 §1：Agent 侧配置 AGENT_API_TOKEN 后，请求必须带 X-Agent-Token。
    Gateway 与 Agent 共用同一环境变量，未配置时不发送（向后兼容）。
    """
    headers: dict[str, str] = {}
    token = settings.agent_api_token.strip()
    if token:
        headers["X-Agent-Token"] = token
    return headers


class AgentClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream(
        self, agent: AgentDefinition, payload: dict
    ) -> AsyncIterator[tuple[str, dict]]:
        timeout = httpx.Timeout(
            connect=self.settings.agent_connect_timeout_seconds,
            read=self.settings.agent_read_timeout_seconds,
            write=30.0,
            pool=self.settings.agent_connect_timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{agent.base_url}/v1/agent/chat",
                    json=payload,
                    headers=agent_headers(self.settings),
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise UpstreamServiceError(
                            "智能体服务请求失败",
                            code="agent_upstream_error",
                            status_code=502,
                        )
                    async for event in parse_sse(response.aiter_bytes()):
                        yield event
        except UpstreamServiceError:
            raise
        except httpx.TimeoutException as exc:
            raise UpstreamServiceError(
                "智能体响应超时",
                code="agent_timeout",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise UpstreamServiceError(
                "无法连接智能体服务",
                code="agent_unavailable",
                status_code=503,
            ) from exc
