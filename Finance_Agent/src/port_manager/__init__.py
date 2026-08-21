"""
端口管理模块 (Port Manager)

提供统一的端口申请、分配、释放、心跳和查询能力。

核心组件:
  - ErrorCode:  统一错误码枚举
  - PortRegistry: 线程安全的内存注册表
  - PortAllocator: 范围优先的端口分配器
  - PortManager: 端口生命周期管理器
  - PortAgentClient: Agent 端客户端（申请/心跳/释放封装）

快速使用::

    # --- 服务端（集成到主 API） ---
    from src.port_manager import (
        PortRegistry, PortAllocator, PortManager, init_router, router,
    )
    registry = PortRegistry(pool_start=8101, pool_end=8500)
    allocator = PortAllocator(registry)
    manager = PortManager(registry, allocator)
    init_router(manager)
    app.include_router(router)

    # --- 客户端（各 Agent 进程中使用） ---
    from src.port_manager import PortAgentClient
    client = PortAgentClient("agent1", "agent1-port-token")
    port = await client.acquire()
    # ... 运行 Agent 服务 ...
    await client.release()
"""

from src.port_manager.error_codes import ErrorCode, error_response, success_response
from src.port_manager.models import (
    UnifiedResponse,
    PortApplyRequest,
    PortAssignData,
    PortReleaseRequest,
    HeartbeatRequest,
    PortQueryRequest,
    PortQueryData,
    PortInfo,
    PoolInfo,
    AgentType,
    VALID_AGENT_IDS,
    AGENT_TYPE_MAP,
)
from src.port_manager.registry import PortRegistry, AllocationRecord
from src.port_manager.allocator import PortAllocator
from src.port_manager.manager import PortManager
from src.port_manager.agent_client import PortAgentClient
from src.port_manager.router import router, init_router

__all__ = [
    # Error codes
    "ErrorCode",
    "error_response",
    "success_response",
    # Models
    "UnifiedResponse",
    "PortApplyRequest",
    "PortAssignData",
    "PortReleaseRequest",
    "HeartbeatRequest",
    "PortQueryRequest",
    "PortQueryData",
    "PortInfo",
    "PoolInfo",
    "AgentType",
    "VALID_AGENT_IDS",
    "AGENT_TYPE_MAP",
    # Core
    "PortRegistry",
    "AllocationRecord",
    "PortAllocator",
    "PortManager",
    # Client
    "PortAgentClient",
    # Router
    "router",
    "init_router",
]
