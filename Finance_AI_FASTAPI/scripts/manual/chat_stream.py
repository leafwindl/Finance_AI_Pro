"""使用已有测试账号手工查看 Gateway 的统一 SSE 聊天流。"""

import asyncio
import os
import uuid

import httpx


async def main() -> None:
    base_url = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
    username = os.environ.get("MANUAL_TEST_USER", "").strip()
    password = os.environ.get("MANUAL_TEST_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("请设置 MANUAL_TEST_USER 和 MANUAL_TEST_PASSWORD")

    async with httpx.AsyncClient(base_url=base_url, timeout=180) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"name": username, "password": password},
        )
        login.raise_for_status()

        async with client.stream(
            "POST",
            "/api/v1/chat",
            json={
                "query": "请简要介绍当前智能体的能力",
                "conversation_id": None,
                "agent_id": "requirement-pre-review",
                "file_ids": [],
                "client_message_id": f"manual_{uuid.uuid4().hex}",
            },
        ) as response:
            print("status", response.status_code)
            async for line in response.aiter_lines():
                print(line)


if __name__ == "__main__":
    asyncio.run(main())
