#!/usr/bin/env python3
"""
Neo4j 知识图谱定时更新器 — 独立于 run.py 运行。

设计思路:
  run.py 入库（PG + ES）成功后，将 needs_graphrag_rebuild 标记置为 True。
  updater.py 由系统计划任务每天凌晨 2 点调用，发现标记为 True 就执行图谱更新。

工作流:
  1. 查询 sys_config.rebuild_flags.needs_graphrag_rebuild
  2. False → 无需更新，直接退出
  3. True  → POST /api/graphrag/update 触发图谱更新
           → 轮询 /api/graphrag/status/{task_id} 直到完成
           → 成功后 set_flag(False) 重置标记

用法:
    python updater.py           # 一次性执行，由计划任务每天凌晨 2 点调用

计划任务配置见本文件末尾的 main() 注释。
"""

import os
import sys
import time
import requests

# 使 services 子模块可导入
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# 加载 .env 配置（优先于代码默认值）
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
except ImportError:
    print("[WARN] 未安装 python-dotenv，无法读取 .env，将使用默认值。"
          " 请执行: pip install python-dotenv", file=sys.stderr)

from writer.status_manager import get_flag, set_flag, poll_neo4j_task

# ============================================================
# 配置 — 从 .env 读取（默认值仅作 fallback）
# ============================================================

RAGRAG_API_URL = os.getenv("RAGRAG_API_URL", "http://127.0.0.1:8201")


# ============================================================
# 核心逻辑
# ============================================================

def trigger_graph_update() -> int | None:
    """调用 rag_service API 触发全局 Neo4j 知识图谱更新。

    不传 record_id：由 rag_service 端自行判断哪些文档需要增量更新。

    Returns:
        task_id (int) — 成功时返回任务 ID，失败返回 None。
    """
    url = f"{RAGRAG_API_URL}/api/graphrag/update"
    print(f"  POST {url}")

    try:
        resp = requests.post(url, json={}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            task_id = data.get("task_id")
            print(f"  ✅ GraphRAG 任务已提交 (task_id={task_id})")
            return task_id
        elif resp.status_code == 409:
            print(f"  ⚠️ 已有正在执行的任务，跳过重复提交")
            # 尝试获取已有任务 ID 并等待其完成
            return _get_running_task_id()
        else:
            print(f"  [ERROR] GraphRAG 返回异常: HTTP {resp.status_code}")
            if resp.text:
                print(f"    {resp.text[:200]}")
            return None
    except requests.ConnectionError:
        print(f"  [ERROR] GraphRAG 服务未启动 ({RAGRAG_API_URL})")
        return None
    except requests.Timeout:
        print(f"  [ERROR] GraphRAG 请求超时")
        return None
    except Exception as e:
        print(f"  [ERROR] GraphRAG 触发异常: {e}")
        return None


def _get_running_task_id() -> int | None:
    """查询当前正在执行的 graphrag 任务 ID。"""
    try:
        resp = requests.get(f"{RAGRAG_API_URL}/api/graphrag/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            tasks = data.get("running_tasks", [])
            if tasks:
                task_id = tasks[0].get("id")
                print(f"  复用正在执行的任务 (task_id={task_id})")
                return task_id
    except Exception:
        pass
    return None


def run_once() -> bool:
    """执行一次检查：读标记 → 更新图谱 → 重置标记。

    Returns:
        True   — 执行了更新（或无需更新）
        False  — 更新失败
    """
    print("=" * 55)
    print(f"  [Updater] 检查时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # ---- Step 1: 读标记 ----
    flag = get_flag()
    print(f"  needs_graphrag_rebuild = {flag}")

    if flag is None:
        print(f"  [ERROR] 无法读取标记值，可能是表不存在或 PG 连接失败")
        print("=" * 55)
        return False

    if flag is False:
        print(f"  无需更新，退出")
        print("=" * 55)
        return True

    # ---- Step 2: 标记为 True → 触发更新 ----
    print(f"\n  开始触发 Neo4j 知识图谱更新...")
    task_id = trigger_graph_update()

    if task_id is None:
        print(f"\n  [ERROR] 无法触发图谱更新")
        print("=" * 55)
        return False

    # ---- Step 3: 轮询等待完成 ----
    print(f"\n  等待 Neo4j 任务完成 (task_id={task_id})...")
    success, result = poll_neo4j_task(task_id)

    if success:
        entities = result.get("entities_added", "?") if result else "?"
        relations = result.get("relations_added", "?") if result else "?"
        print(f"  ✅ Neo4j 图谱更新完成 (+{entities}e, +{relations}r)")

        # ---- Step 4: 重置标记 ----
        print(f"\n  重置 needs_graphrag_rebuild → False ...")
        ok = set_flag(False)
        if ok:
            print(f"  ✅ 标记已重置")
        else:
            print(f"  [ERROR] 标记重置失败")
            print("=" * 55)
            return False
    else:
        if result:
            print(f"  ❌ Neo4j 图谱更新失败: {result.get('error_message', '')}")
        else:
            print(f"  ⚠️ Neo4j 图谱更新超时")
        print(f"\n  标记保持 True，下次再试")
        print("=" * 55)
        return False

    print("=" * 55)
    return True


# ============================================================
# 入口
# ============================================================

def main():
    """一次性执行，由系统计划任务每天凌晨 2 点调用。

    Windows 计划任务（管理员 PowerShell）:
        $action = New-ScheduledTaskAction -Execute "python" `
            -Argument "D:/github_project/Finance_KnowledgeBase/neo4j_updater/updater.py"
        $trigger = New-ScheduledTaskTrigger -Daily -At 02:00
        Register-ScheduledTask -TaskName "GraphRAG-Updater" -Action $action -Trigger $trigger

    Linux cron:
        0 2 * * * cd /path/to/Finance_KnowledgeBase/neo4j_updater && python updater.py >> updater.log 2>&1
    """
    success = run_once()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
