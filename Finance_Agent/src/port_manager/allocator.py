"""
端口分配策略 — 范围优先 + 共享池溢出

每个 Agent 有「偏好范围」(preferred range)，优先在该范围内分配。
偏好范围内分配完毕时，从全局端口池扫描溢出分配。

默认范围规划:
    Agent        偏好范围          说明
    agent1       8101-8199        需求评审
    agent2       8200-8299        需求分析
    agent3       8300-8399        用例评审
    agent4       8400-8499        步骤生成
"""

import logging
from typing import Optional

logger = logging.getLogger("port_manager.allocator")


class PortAllocator:
    """端口分配器 — 范围优先 + 全局池兜底"""

    def __init__(
        self,
        registry,
        preferred_ranges: dict[str, tuple[int, int]] | None = None,
    ):
        """
        Args:
            registry: PortRegistry 实例
            preferred_ranges: agent_name → (start, end) 偏好范围映射
        """
        self._registry = registry
        self._preferred = preferred_ranges or {
            "agent1": (8101, 8199),
            "agent2": (8200, 8299),
            "agent3": (8300, 8399),
            "agent4": (8400, 8499),
        }

    def allocate_for(
        self, agent_name: str, preferred_port: Optional[int] = None
    ) -> Optional[int]:
        """
        为 agent 分配端口。

        优先级:
          1. preferred_port 指定且在池范围内且未被占用 → 直接分配
          2. agent 的偏好范围内找第一个空闲端口
          3. 全局端口池扫描（兜底）
          4. 全部耗尽 → 返回 None
        """
        pool_start, pool_end = self._registry.pool_range

        # 1. 用户指定端口
        if preferred_port is not None:
            if pool_start <= preferred_port <= pool_end:
                if not self._registry.find_by_port(preferred_port):
                    return preferred_port
                logger.warning("指定端口 %d 已被占用", preferred_port)
            else:
                logger.warning("指定端口 %d 超出池范围 [%d, %d]",
                               preferred_port, pool_start, pool_end)
            return None  # 指定端口不可用，不降级

        # 2. 偏好范围
        preferred_range = self._preferred.get(agent_name)
        if preferred_range:
            start, end = preferred_range
            for port in range(start, end + 1):
                if not self._registry.find_by_port(port):
                    return port
            logger.info("偏好范围 %d-%d 已满，尝试全局扫描", start, end)

        # 3. 全局端口池扫描
        return self._registry.find_available_port()

    @property
    def preferred_ranges(self) -> dict[str, str]:
        """返回偏好范围的可读描述"""
        return {
            name: f"{start}-{end}"
            for name, (start, end) in self._preferred.items()
        }
