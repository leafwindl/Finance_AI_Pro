"""
端口管理模块 — 统一错误码枚举

设计原则:
  - 0 表示成功
  - 1xxx 参数校验错误
  - 2xxx 端口资源错误
  - 3xxx Agent 管理错误
  - 4xxx 鉴权错误
  - 5xxx 系统内部错误
  - 6xxx 生命周期错误
"""

from enum import Enum


class ErrorCode(Enum):
    """统一错误码，每个变体为 (code, message)"""

    # ---- 成功 ----
    SUCCESS = (0, "操作成功")

    # ---- 参数校验 (1001-1099) ----
    INVALID_REQUEST = (1001, "请求参数校验失败")
    AGENT_NAME_REQUIRED = (1002, "智能体名称缺失或为空")
    AGENT_ID_INVALID = (1003, "Agent ID 无效，合法值: agent1~agent4")
    PORT_OUT_OF_RANGE = (1004, "请求端口超出允许范围")
    INVALID_AGENT_TYPE = (1005, "智能体类型不在允许列表中")
    MISSING_REQUIRED_FIELD = (1006, "必填字段缺失")
    HEARTBEAT_INTERVAL_TOO_SHORT = (1007, "心跳间隔过短，至少需要 5 秒")

    # ---- 端口资源 (2001-2099) ----
    PORT_ALREADY_ASSIGNED = (2001, "该智能体已有端口分配，不可重复申请")
    PORT_ALREADY_IN_USE = (2002, "该端口已被占用")
    PORT_CONFLICT = (2003, "端口与已分配给其他 Agent 的端口冲突")
    PORT_NOT_FOUND = (2004, "指定端口未在注册表中找到")
    PORT_POOL_EXHAUSTED = (2005, "端口池已耗尽，无可分配端口")

    # ---- Agent 管理 (3001-3099) ----
    AGENT_NOT_FOUND = (3001, "Agent 未注册，请先申请端口")
    AGENT_ALREADY_REGISTERED = (3002, "Agent 已注册端口，请先释放后再申请")
    AGENT_NOT_OWNER = (3003, "智能体不是该端口的持有者")
    AGENT_DISCONNECTED = (3004, "Agent 心跳超时，连接已断开")

    # ---- 鉴权 (4001-4099) ----
    AUTHENTICATION_FAILED = (4001, "身份验证失败，Agent Token 无效")
    PERMISSION_DENIED = (4002, "无权限操作该端口资源")

    # ---- 系统内部 (5001-5099) ----
    INTERNAL_ERROR = (5001, "端口管理服务内部错误")
    REGISTRY_CORRUPTED = (5002, "端口注册表数据异常")
    PERSISTENCE_FAILED = (5003, "持久化失败")

    # ---- 生命周期 (6001-6099) ----
    PORT_LEASE_EXPIRED = (6001, "端口租约已过期，请重新申请")

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def error_response(code: ErrorCode, data=None) -> dict:
    """快捷构造错误响应字典"""
    return {"code": code.code, "message": code.message, "data": data}


def success_response(data=None) -> dict:
    """快捷构造成功响应字典"""
    return {"code": ErrorCode.SUCCESS.code, "message": ErrorCode.SUCCESS.message, "data": data}
