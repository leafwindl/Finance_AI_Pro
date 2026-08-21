"""
端口注册表 — 线程安全的内存存储

内部结构:
  - _allocations: dict[int, AllocationRecord]   端口 → 记录
  - _agent_index: dict[str, int]                agent_name → 端口

后台清理:
  - _sweep_worker 定期扫描，释放超过 MAX_IDLE_SECONDS 无心跳的端口
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("port_manager.registry")


@dataclass
class AllocationRecord:
    """单条端口分配记录"""
    port: int
    agent_name: str
    agent_type: str
    token_hash: str                      # SHA256(token)，非明文存储
    allocated_at: float                  # time.time()
    last_heartbeat: float                # time.time()
    status: str = "active"               # active | released | expired
    metadata: dict = field(default_factory=dict)

    @property
    def seconds_since_heartbeat(self) -> float:
        return time.time() - self.last_heartbeat

    @property
    def is_expired(self, max_idle: float) -> bool:
        return self.seconds_since_heartbeat > max_idle

    def to_dict(self) -> dict:
        """转为 PortInfo 兼容的字典"""
        return {
            "port": self.port,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "allocated_at": datetime.fromtimestamp(
                self.allocated_at, tz=timezone.utc
            ).isoformat(),
            "last_heartbeat": datetime.fromtimestamp(
                self.last_heartbeat, tz=timezone.utc
            ).isoformat(),
            "status": self.status,
            "metadata": self.metadata,
        }


class PortRegistry:
    """线程安全 + 异步后台清理的端口注册表"""

    MAX_IDLE_SECONDS = 120        # 超过此时间无心跳 → 自动释放
    SWEEP_INTERVAL = 30           # 清理任务间隔（秒）

    def __init__(self, pool_start: int = 8101, pool_end: int = 8120):
        self._lock = threading.Lock()
        self._allocations: dict[int, AllocationRecord] = {}
        self._agent_index: dict[str, int] = {}
        self._pool = range(pool_start, pool_end + 1)
        self._sweep_task: Optional[asyncio.Task] = None
        self._running = False

    # ================================================================
    # 基本 CRUD
    # ================================================================
    def allocate(self, record: AllocationRecord) -> bool:
        """分配端口，返回 True 表示成功"""
        with self._lock:
            if record.port in self._allocations:
                return False
            if record.agent_name in self._agent_index:
                return False
            self._allocations[record.port] = record
            self._agent_index[record.agent_name] = record.port
        logger.info("端口 %d 分配给 %s", record.port, record.agent_name)
        return True

    def release(self, port: int) -> Optional[AllocationRecord]:
        """释放端口，返回被释放的记录"""
        with self._lock:
            record = self._allocations.pop(port, None)
            if record:
                self._agent_index.pop(record.agent_name, None)
                logger.info("端口 %d 已释放 (agent=%s)", port, record.agent_name)
        return record

    def heartbeat(self, port: int) -> bool:
        """更新心跳时间，返回 True 表示端口存在"""
        with self._lock:
            record = self._allocations.get(port)
            if record is None:
                return False
            record.last_heartbeat = time.time()
            record.status = "active"
        return True

    # ================================================================
    # 查询
    # ================================================================
    def find_by_agent(self, agent_name: str) -> Optional[AllocationRecord]:
        """按智能体名称查找"""
        with self._lock:
            port = self._agent_index.get(agent_name)
            return self._allocations.get(port) if port else None

    def find_by_port(self, port: int) -> Optional[AllocationRecord]:
        """按端口号查找"""
        with self._lock:
            return self._allocations.get(port)

    def find_available_port(self) -> Optional[int]:
        """在端口池范围内找第一个未被占用的端口"""
        with self._lock:
            for port in self._pool:
                if port not in self._allocations:
                    return port
        return None

    def list_all(self, status_filter: Optional[str] = None) -> list[dict]:
        """列出所有端口分配记录"""
        with self._lock:
            records = list(self._allocations.values())
            if status_filter and status_filter != "all":
                records = [r for r in records if r.status == status_filter]
            return [r.to_dict() for r in records]

    # ================================================================
    # 统计
    # ================================================================
    @property
    def pool_range(self) -> tuple[int, int]:
        return (self._pool.start, self._pool.stop - 1)

    @property
    def usage_stats(self) -> dict:
        with self._lock:
            used = len(self._allocations)
            total = len(self._pool)
            return {
                "pool_start": self._pool.start,
                "pool_end": self._pool.stop - 1,
                "total_ports": total,
                "used_ports": used,
                "available_ports": total - used,
            }

    # ================================================================
    # 后台清理任务
    # ================================================================
    async def start_sweep_worker(self):
        """启动后台清理协程"""
        if self._running:
            return
        self._running = True
        self._sweep_task = asyncio.create_task(self._sweep_loop())
        logger.info("端口清理任务已启动 (sweep_interval=%ds, max_idle=%ds)",
                     self.SWEEP_INTERVAL, self.MAX_IDLE_SECONDS)

    async def stop_sweep_worker(self):
        """停止后台清理协程"""
        self._running = False
        if self._sweep_task:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
            self._sweep_task = None
            logger.info("端口清理任务已停止")

    async def _sweep_loop(self):
        """清理循环 — 释放超时端口"""
        while self._running:
            await asyncio.sleep(self.SWEEP_INTERVAL)
            expired_ports = []
            with self._lock:
                for port, record in list(self._allocations.items()):
                    if record.is_expired(self.MAX_IDLE_SECONDS):
                        expired_ports.append(port)

            for port in expired_ports:
                with self._lock:
                    record = self._allocations.pop(port, None)
                    if record:
                        self._agent_index.pop(record.agent_name, None)
                        logger.warning(
                            "端口 %d 租约过期，已自动释放 (agent=%s, idle=%.0fs)",
                            port, record.agent_name, record.seconds_since_heartbeat,
                        )
