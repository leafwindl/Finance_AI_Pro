"""
端口管理 API 路由

挂载到主 FastAPI 应用: app.include_router(router)

端点列表:
    POST   /v1/port/apply       — 智能体申请端口
    POST   /v1/port/release     — 智能体释放端口
    POST   /v1/port/heartbeat   — 智能体发送心跳
    POST   /v1/port/query       — 查询端口状态
    GET    /v1/port/query/{agent_name} — 按智能体查询
    GET    /v1/port/list        — 列出所有端口分配
    GET    /v1/port/pool        — 查看端口池配置
"""

import logging
from fastapi import APIRouter, HTTPException

from src.port_manager.error_codes import ErrorCode
from src.port_manager.models import (
    PortApplyRequest,
    PortReleaseRequest,
    HeartbeatRequest,
    PortQueryRequest,
    UnifiedResponse,
)

logger = logging.getLogger("port_manager.router")

router = APIRouter(prefix="/v1/port", tags=["端口管理"])

# 由 server.py 启动时注入
_port_manager = None


def init_router(manager):
    """依赖注入: server.py 启动时调用，绑定 PortManager 实例"""
    global _port_manager
    _port_manager = manager


def _get_manager():
    if _port_manager is None:
        raise HTTPException(status_code=500, detail="端口管理服务未初始化")
    return _port_manager


def _respond(code: ErrorCode, data=None) -> UnifiedResponse:
    """构造统一响应"""
    return UnifiedResponse(code=code.code, message=code.message, data=data)


def _http_status(code: ErrorCode) -> int:
    """根据业务错误码映射 HTTP 状态码"""
    if code == ErrorCode.SUCCESS:
        return 200
    if code.code < 2000:
        return 400                     # 参数错误 → 400
    if code.code < 3000:
        return 409                     # 端口资源冲突 → 409
    if code.code < 4000:
        # Agent 管理: 未找到 → 404, 冲突/归属 → 409
        if code == ErrorCode.AGENT_NOT_FOUND:
            return 404
        if code == ErrorCode.AGENT_DISCONNECTED:
            return 410                 # Gone
        return 409
    if code.code < 5000:
        return 401                     # 鉴权失败 → 401
    return 500                         # 系统错误 → 500


# ================================================================
# 端点
# ================================================================

@router.post("/apply", summary="智能体申请端口")
async def apply_port(req: PortApplyRequest) -> UnifiedResponse:
    """
    智能体申请端口。

    每个 Agent (agent1~agent4) 可调用此接口获取一个外部端口。
    成功返回分配的端口号、租约时长和建议心跳间隔。

    示例请求:
    ```json
    {"agent_name":"agent1","agent_type":"requirement_review","token":"agent1-port-token"}
    ```
    """
    mgr = _get_manager()
    code, data = mgr.apply(req)
    if code != ErrorCode.SUCCESS:
        raise HTTPException(
            status_code=_http_status(code),
            detail={"code": code.code, "message": code.message},
        )
    return _respond(code, data.model_dump() if data else None)


@router.post("/release", summary="智能体释放端口")
async def release_port(req: PortReleaseRequest) -> UnifiedResponse:
    """
    智能体释放已分配的端口。

    示例请求:
    ```json
    {"agent_name":"agent1","port":8101,"token":"agent1-port-token"}
    ```
    """
    mgr = _get_manager()
    code, data = mgr.release(req)
    if code != ErrorCode.SUCCESS:
        raise HTTPException(
            status_code=_http_status(code),
            detail={"code": code.code, "message": code.message},
        )
    return _respond(code, data)


@router.post("/heartbeat", summary="智能体发送心跳")
async def send_heartbeat(req: HeartbeatRequest) -> UnifiedResponse:
    """
    智能体定期发送心跳以维持端口租约，建议按 heartbeat_interval 间隔发送。

    示例请求:
    ```json
    {"agent_name":"agent1","port":8101,"token":"agent1-port-token","status":{"running":true}}
    ```
    """
    mgr = _get_manager()
    code, data = mgr.heartbeat(req)
    if code != ErrorCode.SUCCESS:
        raise HTTPException(
            status_code=_http_status(code),
            detail={"code": code.code, "message": code.message},
        )
    return _respond(code, data)


@router.post("/query", summary="条件查询端口状态")
async def query_ports(req: PortQueryRequest) -> UnifiedResponse:
    """
    按条件查询端口分配状态。支持按 agent_name、port、status 筛选。

    示例请求:
    ```json
    {"status":"active"}
    ```
    """
    mgr = _get_manager()
    code, data = mgr.query(req)
    return _respond(code, data.model_dump() if data else None)


@router.get("/query/{agent_name}", summary="按智能体查询端口")
async def query_agent_port(agent_name: str) -> UnifiedResponse:
    """
    查询指定智能体的端口分配情况。

    示例: `GET /v1/port/query/agent1`
    """
    mgr = _get_manager()
    code, data = mgr.query_agent(agent_name)
    if code != ErrorCode.SUCCESS:
        raise HTTPException(
            status_code=_http_status(code),
            detail={"code": code.code, "message": code.message},
        )
    return _respond(code, data.model_dump() if data else None)


@router.get("/list", summary="列出所有端口分配")
async def list_all_ports(status: str = "all") -> UnifiedResponse:
    """
    列出所有端口分配记录。

    可选查询参数:
    - `status`: active | released | expired | all（默认 all）

    示例: `GET /v1/port/list?status=active`
    """
    mgr = _get_manager()
    req = PortQueryRequest(status=status)
    code, data = mgr.query(req)
    return _respond(code, data.model_dump() if data else None)


@router.get("/pool", summary="查看端口池配置")
async def port_pool_info() -> UnifiedResponse:
    """查看端口池配置信息：范围、使用率、各 Agent 偏好范围。"""
    mgr = _get_manager()
    info = mgr.get_pool_info()
    return _respond(ErrorCode.SUCCESS, info.model_dump())
