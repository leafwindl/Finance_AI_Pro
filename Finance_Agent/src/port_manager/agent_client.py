"""
Agent 端端口管理客户端 — 封装申请/心跳/释放的通用逻辑

每个 Agent 在自己的进程中引用此模块，统一处理端口生命周期。

用法示例::

    from src.port_manager.agent_client import PortAgentClient

    client = PortAgentClient(
        agent_name="agent1",
        token="agent1-port-token",
        manager_url="http://localhost:8000",
    )

    # 启动时申请端口
    port = await client.acquire()
    print(f"分配端口: {port}")

    # 关闭时释放端口
    await client.release()
"""

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("port_manager.agent_client")


class PortAgentClient:
    """Agent 端端口管理客户端

    封装了申请、心跳、释放的完整生命周期。
    """

    def __init__(
        self,
        agent_name: str,
        token: str,
        manager_url: str = "http://localhost:8000",
        heartbeat_interval: int = 30,
    ):
        """
        Args:
            agent_name: 智能体标识 (agent1~agent4)
            token: Agent 身份令牌
            manager_url: 端口管理器地址（默认 http://localhost:8000）
            heartbeat_interval: 心跳间隔（秒）
        """
        self.agent_name = agent_name
        self.token = token
        self.manager_url = manager_url.rstrip("/")
        self.heartbeat_interval = heartbeat_interval
        self._port: Optional[int] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def port(self) -> Optional[int]:
        """已分配的端口号，未申请时返回 None"""
        return self._port

    @property
    def is_connected(self) -> bool:
        return self._port is not None and self._running

    async def acquire(self, preferred_port: Optional[int] = None) -> int:
        """
        申请端口并启动后台心跳任务。

        Args:
            preferred_port: 可选的首选端口号

        Returns:
            分配的端口号

        Raises:
            RuntimeError: 申请失败时抛出
        """
        from src.port_manager.models import AGENT_TYPE_MAP

        agent_type = AGENT_TYPE_MAP.get(self.agent_name)
        if agent_type is None:
            raise RuntimeError(f"无效的 agent_name: {self.agent_name}")

        body = {
            "agent_name": self.agent_name,
            "agent_type": agent_type.value,
            "token": self.token,
            "metadata": {
                "pid": os.getpid(),
                "host": "127.0.0.1",
            },
        }
        if preferred_port is not None:
            body["requested_port"] = preferred_port

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{self.manager_url}/v1/port/apply", json=body)
                data = resp.json()

            if data["code"] != 0:
                raise RuntimeError(
                    f"[{self.agent_name}] 端口申请失败: [{data['code']}] {data['message']}"
                )

            self._port = data["data"]["assigned_port"]
            lease = data["data"]["lease_timeout_seconds"]
            interval = data["data"]["heartbeat_interval"]
            self.heartbeat_interval = interval

            logger.info(
                "[%s] 端口 %d 申请成功 (lease=%ds, heartbeat=%ds)",
                self.agent_name, self._port, lease, interval,
            )
        except httpx.HTTPError as e:
            raise RuntimeError(f"[{self.agent_name}] 无法连接端口管理器: {e}") from e

        # 启动后台心跳任务
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return self._port

    async def release(self) -> bool:
        """
        释放端口并停止心跳。

        Returns:
            True 表示释放成功，False 表示失败
        """
        # 先停止心跳
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._port is None:
            return False

        body = {
            "agent_name": self.agent_name,
            "port": self._port,
            "token": self.token,
        }
        success = False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.manager_url}/v1/port/release", json=body
                )
                data = resp.json()
                success = data["code"] == 0
                if success:
                    logger.info("[%s] 端口 %d 已释放", self.agent_name, self._port)
                else:
                    logger.warning(
                        "[%s] 端口释放异常: [%d] %s",
                        self.agent_name, data["code"], data["message"],
                    )
        except httpx.HTTPError as e:
            logger.warning("[%s] 端口释放请求失败: %s", self.agent_name, e)
        finally:
            self._port = None

        return success

    async def _heartbeat_loop(self):
        """后台心跳循环"""
        fail_count = 0
        while self._running and self._port is not None:
            await asyncio.sleep(self.heartbeat_interval)
            if not self._running:
                break

            body = {
                "agent_name": self.agent_name,
                "port": self._port,
                "token": self.token,
                "status": {
                    "pid": os.getpid(),
                    "running": True,
                    "fail_count": fail_count,
                },
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{self.manager_url}/v1/port/heartbeat", json=body
                    )
                    data = resp.json()
                    if data["code"] == 0:
                        fail_count = 0
                    else:
                        fail_count += 1
                        logger.warning(
                            "[%s] 心跳被拒绝: [%d] %s",
                            self.agent_name, data["code"], data["message"],
                        )
            except Exception as e:
                fail_count += 1
                logger.warning("[%s] 心跳发送失败 (累计 %d 次): %s",
                               self.agent_name, fail_count, e)

            if fail_count >= 5:
                logger.error("[%s] 连续 %d 次心跳失败，连接可能已断开",
                             self.agent_name, fail_count)
