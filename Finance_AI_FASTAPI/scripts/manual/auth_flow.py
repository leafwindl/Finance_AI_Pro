"""手工验证注册、当前用户和退出流程。"""

import asyncio
import os
import uuid

import httpx


async def main() -> None:
    base_url = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
    suffix = uuid.uuid4().hex[:8]
    name = f"manual_{suffix}"
    email = f"{name}@example.com"

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        register = await client.post(
            "/api/v1/auth/register",
            json={"name": name, "email": email, "password": "123456"},
        )
        print("register", register.status_code, register.text)

        current_user = await client.get("/api/v1/auth/me")
        print("me", current_user.status_code, current_user.text)

        logout = await client.post("/api/v1/auth/logout")
        print("logout", logout.status_code, logout.text)

        after_logout = await client.get("/api/v1/auth/me")
        print("me-after-logout", after_logout.status_code, after_logout.text)


if __name__ == "__main__":
    asyncio.run(main())
