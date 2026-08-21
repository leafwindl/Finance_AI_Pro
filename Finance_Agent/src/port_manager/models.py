"""
端口管理模块 — 统一请求/响应 Pydantic 模型

所有外层响应均遵循 {code, message, data} 结构。
"""

from enum import Enum
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


# ================================================================
# 智能体类型枚举
# ================================================================
class AgentType(str, Enum):
    """智能体类型 — 与主流程 4 个 Agent 一一对应（port_manager 已过时，不含 agent5）"""
    REQUIREMENT_REVIEW = "requirement_review"        # 需求评审
    REQUIREMENT_ANALYSIS = "requirement_analysis"    # 需求分析
    CASE_REVIEW = "case_review"                      # 用例评审
    STEP_GENERATION = "step_generation"              # 步骤生成


# Agent 名称 → 类型 映射
AGENT_TYPE_MAP: dict[str, AgentType] = {
    "agent1": AgentType.REQUIREMENT_REVIEW,
    "agent2": AgentType.REQUIREMENT_ANALYSIS,
    "agent3": AgentType.CASE_REVIEW,
    "agent4": AgentType.STEP_GENERATION,
}

VALID_AGENT_IDS = frozenset(AGENT_TYPE_MAP.keys())


# ================================================================
# 统一响应包裹
# ================================================================
class UnifiedResponse(BaseModel, Generic[T]):
    """统一外层响应包裹 — 所有 API 端点均返回此结构"""
    code: int = Field(default=0, description="业务错误码，0 表示成功")
    message: str = Field(default="success", description="人类可读的消息")
    data: Optional[T] = Field(default=None, description="响应数据载荷")


# ================================================================
# 端口申请 — 请求/响应
# ================================================================
class PortApplyRequest(BaseModel):
    """智能体申请端口的标准请求"""
    agent_name: str = Field(
        default=...,
        min_length=1,
        max_length=32,
        description="智能体标识: agent1 | agent2 | agent3 | agent4",
    )
    agent_type: AgentType = Field(
        default=...,
        description="智能体类型",
    )
    requested_port: Optional[int] = Field(
        default=None,
        ge=1024,
        le=65535,
        description="首选端口号，留空则由系统自动分配",
    )
    token: str = Field(
        default=...,
        min_length=1,
        max_length=256,
        description="Agent 身份令牌",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="附加元数据（如 Agent 版本、主机信息）",
    )

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        if v.lower() not in VALID_AGENT_IDS:
            raise ValueError(f"agent_name 必须为 {set(VALID_AGENT_IDS)}")
        return v.lower()


class PortAssignData(BaseModel):
    """端口分配成功的响应数据"""
    agent_name: str = Field(description="智能体标识")
    agent_type: str = Field(description="智能体类型")
    assigned_port: int = Field(description="分配的端口号")
    allocated_at: str = Field(description="分配时间（ISO 8601）")
    lease_timeout_seconds: int = Field(description="租约超时（秒）")
    heartbeat_interval: int = Field(description="建议心跳间隔（秒）")


# ================================================================
# 端口释放 — 请求
# ================================================================
class PortReleaseRequest(BaseModel):
    """智能体释放端口的请求"""
    agent_name: str = Field(
        default=...,
        min_length=1,
        max_length=32,
        description="智能体标识",
    )
    port: int = Field(default=..., ge=1024, le=65535, description="要释放的端口号")
    token: str = Field(default=..., min_length=1, max_length=256, description="Agent 身份令牌")

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        if v.lower() not in VALID_AGENT_IDS:
            raise ValueError(f"agent_name 必须为 {set(VALID_AGENT_IDS)}")
        return v.lower()


# ================================================================
# 心跳 — 请求
# ================================================================
class HeartbeatRequest(BaseModel):
    """智能体发送心跳的请求"""
    agent_name: str = Field(default=..., description="智能体标识")
    port: int = Field(default=..., ge=1024, le=65535, description="已分配的端口号")
    token: str = Field(default=..., min_length=1, max_length=256, description="Agent 身份令牌")
    status: dict = Field(default_factory=dict, description="当前 Agent 运行状态摘要")

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        if v.lower() not in VALID_AGENT_IDS:
            raise ValueError(f"agent_name 必须为 {set(VALID_AGENT_IDS)}")
        return v.lower()


# ================================================================
# 端口查询 — 请求/响应
# ================================================================
class PortQueryRequest(BaseModel):
    """端口查询筛选条件"""
    agent_name: Optional[str] = Field(default=None, description="按智能体名称筛选")
    port: Optional[int] = Field(default=None, ge=1024, le=65535, description="按端口号筛选")
    status: Optional[str] = Field(
        default=None,
        pattern=r"^(active|released|expired|all)$",
        description="按状态筛选: active | released | expired | all",
    )


class PortInfo(BaseModel):
    """单个端口占用信息"""
    port: int
    agent_name: str
    agent_type: str
    allocated_at: str           # ISO 8601
    last_heartbeat: str         # ISO 8601
    status: str                 # active | released | expired
    metadata: dict = Field(default_factory=dict)


class PortQueryData(BaseModel):
    """端口查询响应数据"""
    total_ports: int = Field(description="端口池总端口数")
    used_ports: int = Field(description="已占用端口数")
    available_ports: int = Field(description="可用端口数")
    allocations: list[PortInfo] = Field(default_factory=list, description="端口分配列表")


# ================================================================
# 端口池信息
# ================================================================
class PoolInfo(BaseModel):
    """端口池配置信息"""
    pool_start: int
    pool_end: int
    total_ports: int
    used_ports: int
    available_ports: int
    preferred_ranges: dict[str, str]
