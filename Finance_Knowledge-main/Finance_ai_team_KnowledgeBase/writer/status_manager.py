"""
status_manager.py
=================
GraphRAG 重建标记状态管理模块。

管理 `knowledge_base.sys_config.rebuild_flags.needs_graphrag_rebuild` 字段，
在三路任务（ES / PostgreSQL / Neo4j）全部完成后统一判断和更新。

规则:
  情况1: 当前 FALSE + 三路成功 → UPDATE 为 TRUE
  情况2: 当前 TRUE  + 三路成功 → 保持 TRUE（不重复修改）
  情况3: 任一路失败            → 不修改

用法:
  from services.status_manager import check_and_update_graphrag_flag
  result = check_and_update_graphrag_flag(es_ok=True, pg_ok=True, neo4j_ok=True)
"""

from __future__ import annotations

import os
import time
import urllib.request
import json
from datetime import datetime

import psycopg2

# ============================================================
# 配置 — 从环境变量读取
# ============================================================

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DBNAME = os.getenv("PG_DBNAME", "knowledge_base")
PG_USER = os.getenv("PG_USER", "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
RAGRAG_API_URL = os.getenv("RAGRAG_API_URL", "http://127.0.0.1:8201")


# ============================================================
# 底层 PG 操作
# ============================================================

def _pg_connect():
    """连接 knowledge_base 数据库。"""
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
        user=PG_USER, password=PG_PASSWORD,
    )


def get_flag() -> bool | None:
    """读取 needs_graphrag_rebuild 当前值。

    返回 True / False / None（表不存在或无数据时）。
    """
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute("SELECT needs_graphrag_rebuild FROM sys_config.rebuild_flags")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row is not None:
            return row[0]
        return None
    except Exception as e:
        print(f"  [WARN] 读取 rebuild_flags 失败: {e}")
        return None


def set_flag(value: bool) -> bool:
    """设置 needs_graphrag_rebuild 为指定值。

    返回 True 表示写入成功。
    """
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE sys_config.rebuild_flags SET needs_graphrag_rebuild = %s",
            (value,),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"  [ERROR] 更新 rebuild_flags 失败: {e}")
        return False


# ============================================================
# Neo4j 任务轮询
# ============================================================

def poll_neo4j_task(task_id: int, timeout_seconds: int = 300) -> tuple[bool, dict | None]:
    """轮询 rag_service 任务直到完成或超时。

    Args:
        task_id: rag_service 返回的任务 ID
        timeout_seconds: 最大等待秒数

    Returns:
        (success: bool, task_result: dict | None)
    """
    if task_id <= 0:
        return False, None

    start = time.time()
    url = f"{RAGRAG_API_URL}/api/graphrag/status/{task_id}"

    while (time.time() - start) < timeout_seconds:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            status = data.get("status", "unknown")

            if status == "completed":
                return True, data
            elif status == "failed":
                return False, data
            # else: pending / running → continue polling
        except Exception as e:
            print(f"  [WARN] Neo4j 任务轮询异常: {e}")

        time.sleep(5)

    # Timeout
    print(f"  [WARN] Neo4j 任务 {task_id} 在 {timeout_seconds}s 内未完成")
    return False, None


# ============================================================
# 核心判断逻辑
# ============================================================

def check_and_update_graphrag_flag(
    es_ok: bool = False,
    pg_ok: bool = False,
    neo4j_ok: bool = False,
) -> dict | None:
    """三路任务完成后，统一判断和更新 needs_graphrag_rebuild 标记。

    Args:
        es_ok: Elasticsearch 更新是否成功
        pg_ok: PostgreSQL 更新是否成功
        neo4j_ok: Neo4j 知识图谱更新是否成功

    Returns:
        {
            "all_completed": bool,      # 三路是否全部成功
            "before": True|False|None,  # 修改前标记值
            "after": True|False|None,   # 修改后标记值
            "action": "updated"|"kept"|"skipped"|"error",
            "task_status": {"postgres": pg_ok, "es": es_ok, "neo4j": neo4j_ok},
            "timestamp": str,
        }
        三路未全部成功时返回 None。
    """
    # ---- 日志头 ----
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 55}")
    print(f"  [GraphRAG Flag] 状态检查")
    print(f"  {'─' * 45}")
    print(f"  task_status:")
    print(f"    postgres = {pg_ok}")
    print(f"    es       = {es_ok}")
    print(f"    neo4j    = {neo4j_ok}")
    print(f"  {'─' * 45}")

    # ---- 三路未全部成功 → 不修改 ----
    all_ok = es_ok and pg_ok and neo4j_ok
    if not all_ok:
        print(f"  all_completed = FALSE → 不修改标记")
        print(f"{'=' * 55}")
        return {
            "all_completed": False,
            "before": None,
            "after": None,
            "action": "skipped",
            "task_status": {"postgres": pg_ok, "es": es_ok, "neo4j": neo4j_ok},
            "timestamp": timestamp,
        }

    # ---- 三路全部成功 → 检查并更新标记 ----
    print(f"  all_completed = TRUE")
    before = get_flag()
    print(f"  needs_graphrag_rebuild (before): {before}")

    if before is None:
        print(f"  [ERROR] 无法读取标记值，跳过更新")
        print(f"{'=' * 55}")
        return {
            "all_completed": True,
            "before": None, "after": None,
            "action": "error",
            "task_status": {"postgres": pg_ok, "es": es_ok, "neo4j": neo4j_ok},
            "timestamp": timestamp,
        }

    if before is False:
        # 情况1: FALSE → TRUE
        ok = set_flag(True)
        after = get_flag()
        print(f"  needs_graphrag_rebuild (after):  {after}")
        action = "updated" if ok and after is True else "error"
        print(f"  操作: FALSE → TRUE  ({action})")
        print(f"{'=' * 55}")
        return {
            "all_completed": True,
            "before": False, "after": after,
            "action": action,
            "task_status": {"postgres": pg_ok, "es": es_ok, "neo4j": neo4j_ok},
            "timestamp": timestamp,
        }
    else:
        # 情况2: TRUE → 保持 TRUE
        print(f"  needs_graphrag_rebuild (after):  {before} (already TRUE)")
        print(f"  操作: 保持 TRUE，不重复修改")
        print(f"{'=' * 55}")
        return {
            "all_completed": True,
            "before": True, "after": True,
            "action": "kept",
            "task_status": {"postgres": pg_ok, "es": es_ok, "neo4j": neo4j_ok},
            "timestamp": timestamp,
        }
