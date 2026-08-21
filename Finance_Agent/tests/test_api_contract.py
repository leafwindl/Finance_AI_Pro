"""
API 契约测试 + Agent 端集成测试

修复记录 (2026-07-29):
  1. sys.path 按测试隔离，解决 agent1/agent3 同名 graph/ 包冲突
  2. agent2: modular_agent → agents.agent2 包导入
  3. agent3: src.graph → agents.agent3 包导入
  4. 新增 PortAgentClient 集成测试 (httpx 0.28+ ASGITransport)
"""
import sys
from pathlib import Path
from contextlib import contextmanager

import pytest
import httpx


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
_AGENTS = _SRC / "agents"

# Agent 1/2/3 统一从 src/ 层按 agents.<agent> 包导入。
_AGENT1_PATH = str(_AGENTS / "agent1")
_SRC_PATH = str(_SRC)  # src/ 目录 (agents 包的父级)
# agent4 需要 agent4/ 在 sys.path 顶层 (内部用 from modules.xxx)
_AGENT4_PATH = str(_AGENTS / "agent4")


@contextmanager
def _syspath(*paths: str):
    """临时注入 sys.path，退出时自动清理"""
    added = [p for p in paths if p not in sys.path]
    for p in added:
        sys.path.insert(0, p)
    try:
        yield
    finally:
        for p in added:
            sys.path.remove(p)


# ============================================================
# Agent1 — 需求评审（包导入）
# ============================================================
class TestAgent1:
    """② 需求评审智能体"""

    def test_state_definition(self):
        with _syspath(_SRC_PATH):
            from agents.agent1.state import RequirementState
            assert RequirementState is not None

    def test_graph_builds(self):
        with _syspath(_SRC_PATH):
            from agents.agent1.graph.workflow import build_graph
            app = build_graph()
            assert app is not None


# ============================================================
# Agent2 — 需求分析 (relative import, 包导入 agents.agent2)
# ============================================================
class TestAgent2:
    """⑦ 需求AI测试分析智能体"""

    def test_state_definition(self):
        with _syspath(_SRC_PATH):
            from agents.agent2.core.state import AgentState
            assert AgentState is not None

    def test_graph_builds(self):
        with _syspath(_SRC_PATH):
            from agents.agent2.core.graph import agent_graph
            assert agent_graph is not None
            assert agent_graph.name == "HybridRetrievalAgent"


# ============================================================
# Agent3 — 用例评审 (relative import, 包导入 agents.agent3)
# ============================================================
class TestAgent3:
    """⑩ 测试用例评审智能体"""

    def test_state_definition(self):
        with _syspath(_SRC_PATH):
            from agents.agent3.graph.state import ReviewState
            assert ReviewState is not None

    def test_graph_builds(self):
        with _syspath(_SRC_PATH):
            from agents.agent3.graph.workflow import build_graph
            graph = build_graph()
            assert graph is not None


# ============================================================
# Agent4 — 步骤生成 (flat import: modules.xxx)
# ============================================================
class TestAgent4:
    """⑬ 测试步骤生成智能体"""

    def test_state_definition(self):
        with _syspath(_AGENT4_PATH):
            from modules.state.state_def import WorkflowState
            assert WorkflowState is not None

    def test_graph_builds(self):
        with _syspath(_AGENT4_PATH):
            from modules.workflow.graph import build_workflow_graph
            graph = build_workflow_graph()
            assert graph is not None


# ============================================================
# 全流程编排器
# ============================================================
class TestPipeline:
    """全流程编排器"""

    def test_full_pipeline_class(self):
        # FullPipeline 内部用到所有 agent 的路径，全部注入
        with _syspath(_AGENT1_PATH, _SRC_PATH, _AGENT4_PATH):
            from src.pipeline.orchestrator import FullPipeline, PipelineResult
            pipeline = FullPipeline()
            assert pipeline is not None
            result = PipelineResult()
            assert isinstance(result.errors, list)


# ============================================================
# PortAgentClient 集成测试 (httpx 0.28+ ASGITransport)
# ============================================================
class TestPortAgentClientIntegration:
    """PortAgentClient 集成测试"""

    @pytest.fixture
    def manager_app(self):
        """构建测试用 FastAPI 应用 (内存端口池)"""
        from fastapi import FastAPI
        from src.port_manager.registry import PortRegistry
        from src.port_manager.allocator import PortAllocator
        from src.port_manager.manager import PortManager
        from src.port_manager.router import init_router, router

        app = FastAPI()
        registry = PortRegistry(pool_start=8101, pool_end=8105)
        allocator = PortAllocator(registry, preferred_ranges={
            "agent1": (8101, 8102),
            "agent2": (8200, 8201),
            "agent3": (8300, 8301),
            "agent4": (8400, 8401),
        })
        mgr = PortManager(registry, allocator, heartbeat_interval=30, lease_duration=300)
        init_router(mgr)
        app.include_router(router)
        return app

    TOKEN = "agent1-port-token"

    @pytest.mark.asyncio
    async def test_agent_client_can_acquire_and_release(self, manager_app):
        """申请 → 心跳 → 查询 → 释放 全流程 (httpx 0.28+ 兼容)"""
        transport = httpx.ASGITransport(app=manager_app)
        base_url = "http://testserver"

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            # ---- 申请 ----
            r = await client.post("/v1/port/apply", json={
                "agent_name": "agent1",
                "agent_type": "requirement_review",
                "token": self.TOKEN,
                "metadata": {"pid": 99999, "host": "127.0.0.1"},
            })
            assert r.status_code == 200
            d = r.json()
            assert d["code"] == 0
            port = d["data"]["assigned_port"]
            assert 8101 <= port <= 8105

            # ---- 心跳 ----
            r = await client.post("/v1/port/heartbeat", json={
                "agent_name": "agent1", "port": port,
                "token": self.TOKEN, "status": {"running": True},
            })
            assert r.json()["code"] == 0

            # ---- 查询 ----
            r = await client.post("/v1/port/query", json={"agent_name": "agent1"})
            assert r.json()["code"] == 0

            # ---- 释放 ----
            r = await client.post("/v1/port/release", json={
                "agent_name": "agent1", "port": port, "token": self.TOKEN,
            })
            assert r.json()["code"] == 0

    @pytest.mark.asyncio
    async def test_reapply_rejected(self, manager_app):
        """重复申请 → 3002 AGENT_ALREADY_REGISTERED"""
        transport = httpx.ASGITransport(app=manager_app)
        base_url = "http://testserver"
        agent2_token = "agent2-port-token"

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            r = await client.post("/v1/port/apply", json={
                "agent_name": "agent2", "agent_type": "requirement_analysis",
                "token": agent2_token,
            })
            assert r.json()["code"] == 0
            port = r.json()["data"]["assigned_port"]

            r = await client.post("/v1/port/apply", json={
                "agent_name": "agent2", "agent_type": "requirement_analysis",
                "token": agent2_token,
            })
            # 失败时 router 抛 HTTPException，body 为 {"detail": {"code": ..., "message": ...}}
            assert r.status_code == 409
            assert r.json()["detail"]["code"] == 3002

            await client.post("/v1/port/release", json={
                "agent_name": "agent2", "port": port, "token": agent2_token,
            })

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, manager_app):
        """无效 token → 401 AUTHENTICATION_FAILED"""
        transport = httpx.ASGITransport(app=manager_app)
        base_url = "http://testserver"

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            r = await client.post("/v1/port/apply", json={
                "agent_name": "agent3", "agent_type": "case_review",
                "token": "wrong-token",
            })
            assert r.status_code == 401
            assert r.json()["detail"]["code"] == 4001

    @pytest.mark.asyncio
    async def test_pool_info(self, manager_app):
        """GET /v1/port/pool"""
        transport = httpx.ASGITransport(app=manager_app)
        base_url = "http://testserver"

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            r = await client.get("/v1/port/pool")
            d = r.json()
            assert d["code"] == 0
            assert d["data"]["total_ports"] > 0

    @pytest.mark.asyncio
    async def test_list_active(self, manager_app):
        """GET /v1/port/list?status=active"""
        transport = httpx.ASGITransport(app=manager_app)
        base_url = "http://testserver"

        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            # 先申请一个端口
            r = await client.post("/v1/port/apply", json={
                "agent_name": "agent1", "agent_type": "requirement_review",
                "token": self.TOKEN,
            })
            port = r.json()["data"]["assigned_port"]

            r = await client.get("/v1/port/list?status=active")
            d = r.json()
            assert d["code"] == 0
            assert d["data"]["used_ports"] >= 1

            await client.post("/v1/port/release", json={
                "agent_name": "agent1", "port": port, "token": self.TOKEN,
            })
