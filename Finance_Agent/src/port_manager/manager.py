"""
端口管理器 — 编排申请/释放/心跳/查询生命周期

职责:
  - 鉴权校验（token 验证）
  - 业务规则校验（重复申请、归属校验等）
  - 调用注册中心和分配器完成实际操作
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from src.port_manager.registry import PortRegistry, AllocationRecord
from src.port_manager.allocator import PortAllocator
from src.port_manager.error_codes import ErrorCode
from src.port_manager.models import (
    PortApplyRequest,
    PortAssignData,
    PortReleaseRequest,
    HeartbeatRequest,
    PortQueryRequest,
    PortQueryData,
    PortInfo,
    PoolInfo,
    VALID_AGENT_IDS,
    AGENT_TYPE_MAP,
)

logger = logging.getLogger("port_manager.manager")

# 简单 token 映射表（生产环境建议改用数据库或外部配置）
_DEFAULT_TOKENS: dict[str, str] = {
    "agent1": "agent1-port-token",
    "agent2": "agent2-port-token",
    "agent3": "agent3-port-token",
    "agent4": "agent4-port-token",
}


class PortManager:
    """端口生命周期管理器"""

    DEFAULT_HEARTBEAT_INTERVAL = 30    # 建议心跳间隔（秒）
    DEFAULT_LEASE_DURATION = 300       # 租约时长（秒），5 分钟

    def __init__(
        self,
        registry: PortRegistry,
        allocator: PortAllocator,
        agent_tokens: Optional[dict[str, str]] = None,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        lease_duration: int = DEFAULT_LEASE_DURATION,
    ):
        self._registry = registry
        self._allocator = allocator
        self._tokens = agent_tokens or _DEFAULT_TOKENS
        self.heartbeat_interval = heartbeat_interval
        self.lease_duration = lease_duration

    # ================================================================
    # 申请端口
    # ================================================================
    def apply(self, req: PortApplyRequest) -> tuple[ErrorCode, Optional[PortAssignData]]:
        """
        智能体申请端口。

        流程:
          1. 鉴权
          2. 检查是否已有分配
          3. 分配端口
          4. 写入注册表
        """
        # 1. 鉴权
        if not self._authenticate(req.agent_name, req.token):
            logger.warning("申请拒绝: %s 鉴权失败", req.agent_name)
            return ErrorCode.AUTHENTICATION_FAILED, None

        # 2. 检查是否已注册
        existing = self._registry.find_by_agent(req.agent_name)
        if existing:
            logger.warning("申请拒绝: %s 已有端口 %d", req.agent_name, existing.port)
            return ErrorCode.AGENT_ALREADY_REGISTERED, None

        # 3. 分配端口
        port = self._allocator.allocate_for(req.agent_name, req.requested_port)
        if port is None:
            if req.requested_port is not None:
                return ErrorCode.PORT_CONFLICT, None
            return ErrorCode.PORT_POOL_EXHAUSTED, None

        # 4. 写入注册表
        now = time.time()
        record = AllocationRecord(
            port=port,
            agent_name=req.agent_name,
            agent_type=req.agent_type.value,
            token_hash=self._hash(req.token),
            allocated_at=now,
            last_heartbeat=now,
            status="active",
            metadata=req.metadata,
        )
        if not self._registry.allocate(record):
            logger.error("分配写入失败: %s → 端口 %d（并发冲突）", req.agent_name, port)
            return ErrorCode.PORT_CONFLICT, None

        logger.info("端口分配成功: %s → %d (type=%s)", req.agent_name, port, req.agent_type.value)
        data = PortAssignData(
            agent_name=req.agent_name,
            agent_type=req.agent_type.value,
            assigned_port=port,
            allocated_at=datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            lease_timeout_seconds=self.lease_duration,
            heartbeat_interval=self.heartbeat_interval,
        )
        return ErrorCode.SUCCESS, data

    # ================================================================
    # 释放端口
    # ================================================================
    def release(self, req: PortReleaseRequest) -> tuple[ErrorCode, Optional[dict]]:
        """智能体释放端口"""
        # 鉴权
        if not self._authenticate(req.agent_name, req.token):
            return ErrorCode.AUTHENTICATION_FAILED, None

        # 校验端口归属
        record = self._registry.find_by_port(req.port)
        if not record:
            return ErrorCode.PORT_NOT_FOUND, None
        if record.agent_name != req.agent_name:
            logger.warning("释放拒绝: %s 不是端口 %d 的持有者 (实际持有者: %s)",
                           req.agent_name, req.port, record.agent_name)
            return ErrorCode.AGENT_NOT_OWNER, None

        self._registry.release(req.port)
        logger.info("端口释放成功: %s 释放 %d", req.agent_name, req.port)
        return ErrorCode.SUCCESS, {"released_port": req.port, "agent_name": req.agent_name}

    # ================================================================
    # 心跳
    # ================================================================
    def heartbeat(self, req: HeartbeatRequest) -> tuple[ErrorCode, Optional[dict]]:
        """智能体发送心跳以维持租约"""
        # 鉴权
        if not self._authenticate(req.agent_name, req.token):
            return ErrorCode.AUTHENTICATION_FAILED, None

        # 校验端口归属
        record = self._registry.find_by_port(req.port)
        if not record:
            return ErrorCode.PORT_NOT_FOUND, None
        if record.agent_name != req.agent_name:
            return ErrorCode.AGENT_NOT_OWNER, None

        ok = self._registry.heartbeat(req.port)
        if not ok:
            return ErrorCode.PORT_NOT_FOUND, None

        return ErrorCode.SUCCESS, {
            "port": req.port,
            "agent_name": req.agent_name,
            "heartbeat_received": True,
            "next_heartbeat_in": self.heartbeat_interval,
        }

    # ================================================================
    # 查询端口
    # ================================================================
    def query(self, req: PortQueryRequest) -> tuple[ErrorCode, Optional[PortQueryData]]:
        """按条件查询端口分配状态"""
        records = self._registry.list_all(status_filter=req.status)
        stats = self._registry.usage_stats

        # 按条件筛选
        if req.agent_name:
            records = [r for r in records if r["agent_name"] == req.agent_name]
        if req.port is not None:
            records = [r for r in records if r["port"] == req.port]

        # 转换为 PortInfo 列表
        allocations = [PortInfo(**r) for r in records]

        data = PortQueryData(
            total_ports=stats["total_ports"],
            used_ports=stats["used_ports"],
            available_ports=stats["available_ports"],
            allocations=allocations,
        )
        return ErrorCode.SUCCESS, data

    def query_agent(self, agent_name: str) -> tuple[ErrorCode, Optional[PortInfo]]:
        """按智能体名称查询"""
        record = self._registry.find_by_agent(agent_name)
        if not record:
            return ErrorCode.AGENT_NOT_FOUND, None
        return ErrorCode.SUCCESS, PortInfo(**record.to_dict())

    def get_pool_info(self) -> PoolInfo:
        """获取端口池配置信息"""
        stats = self._registry.usage_stats
        return PoolInfo(
            pool_start=stats["pool_start"],
            pool_end=stats["pool_end"],
            total_ports=stats["total_ports"],
            used_ports=stats["used_ports"],
            available_ports=stats["available_ports"],
            preferred_ranges=self._allocator.preferred_ranges,
        )

    # ================================================================
    # 辅助方法
    # ================================================================
    def _authenticate(self, agent_name: str, token: str) -> bool:
        """验证 Agent Token"""
        expected = self._tokens.get(agent_name)
        if expected is None:
            return False
        return token == expected

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
