"""
data_gateway 数据库层完整测试脚本
===================================
直接测试 repository 层的所有 CRUD 函数，不依赖 HTTP / 前端。

配置数据库密码：
    修改项目根目录 .env 中的 DB_PASSWORD=你的密码
    当前配置：
      Host:     localhost:5432
      Database: knowledge_agent
      User:     postgres
      Password: postgres_word

前置条件：
    1. PostgreSQL 已启动，knowledge_agent 数据库已创建
    2. 迁移脚本已执行（表已建好）
       从项目根目录运行: uv run python -m scripts.apply_migrations

运行方式：
    python app/data_gateway/test_data_gateway.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在 sys.path 中，以便导入 app 模块
# 脚本位于 app/data_gateway/，需往上三级到项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 强制切换到项目根目录，否则 pydantic-settings 找不到 .env 文件
os.chdir(str(PROJECT_ROOT))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 测试数据（每次运行使用唯一 ID，避免与历史数据冲突）
# ============================================================
SUFFIX = uuid.uuid4().hex[:8]
TEST_USER_ID = f"test_user_{SUFFIX}"
TEST_CONV_ID = f"test_conv_{SUFFIX}"
TEST_FILE_ID = f"test_file_{SUFFIX}"
PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [OK] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  -- {detail}")


async def test_conversations(pool):
    """测试会话 CRUD"""
    from app.data_gateway.repositories.conversations import (
        create_conversation,
        get_owned_conversation,
        list_owned_conversations,
        delete_owned_conversation,
    )

    print("\n--- 会话 (conversations) 测试 ---")
    print("-" * 50)

    # --- 创建会话 ---
    conv = await create_conversation(
        pool,
        conversation_id=TEST_CONV_ID,
        user_id=TEST_USER_ID,
        agent_id="accounting-expert",
        title="测试会话标题",
    )
    check("创建会话返回 Record", conv is not None)
    check("会话 ID 正确", conv is not None and conv["conversation_id"] == TEST_CONV_ID,
          f"期望 {TEST_CONV_ID}, 实际 {conv}")
    check("会话归属用户正确", conv is not None and conv["user_id"] == TEST_USER_ID)
    check("agent_id 正确", conv is not None and conv["agent_id"] == "accounting-expert")
    check("title 正确", conv is not None and conv["title"] == "测试会话标题")
    check("created_at 已自动填充", conv is not None and conv["created_at"] is not None)

    # --- 查询单个会话 ---
    fetched = await get_owned_conversation(pool, TEST_CONV_ID, TEST_USER_ID)
    check("get_owned_conversation 查询到会话", fetched is not None)
    check("查询结果与创建一致", fetched is not None and fetched["conversation_id"] == conv["conversation_id"])

    # --- 所有权隔离：另一个用户查不到 ---
    other = await get_owned_conversation(pool, TEST_CONV_ID, "other_user_nonexistent")
    check("其他用户查不到该会话（所有权隔离）", other is None)

    # --- 列出会话 ---
    convs = await list_owned_conversations(pool, user_id=TEST_USER_ID, agent_id=None, limit=50)
    check("list_owned_conversations 返回列表", isinstance(convs, list))
    check("列表中包含刚创建的会话", any(c["conversation_id"] == TEST_CONV_ID for c in convs))

    # --- 按 agent_id 过滤 ---
    filtered = await list_owned_conversations(
        pool, user_id=TEST_USER_ID, agent_id="accounting-expert", limit=50
    )
    check("按 agent_id 过滤正确", all(c["agent_id"] == "accounting-expert" for c in filtered))

    # --- limit 限制 ---
    limited = await list_owned_conversations(pool, user_id=TEST_USER_ID, agent_id=None, limit=2)
    check("limit 参数生效", len(limited) <= 2)

    print(f"  -> 共 {len(convs)} 条会话记录（含历史数据）")


async def test_messages(pool):
    """测试消息 CRUD"""
    from app.data_gateway.repositories.conversations import (
        create_conversation,
        insert_user_message,
        insert_assistant_message,
        list_owned_messages,
        mark_request_failed,
    )

    print("\n--- 消息 (messages) 测试 ---")
    print("-" * 50)

    # 会话已在 test_conversations 中创建，此处的 create_conversation 调用
    # 可能因主键冲突而失败，忽略即可（幂等创建）
    import asyncpg
    try:
        await create_conversation(
            pool,
            conversation_id=TEST_CONV_ID,
            user_id=TEST_USER_ID,
            agent_id="accounting-expert",
            title="测试会话-消息测试",
        )
    except asyncpg.UniqueViolationError:
        pass  # 会话已存在，无需重复创建

    request_id = f"test_req_{SUFFIX}"
    client_msg_id = f"test_cmsg_{SUFFIX}"

    # --- 插入用户消息 ---
    msg_id = await insert_user_message(
        pool,
        conversation_id=TEST_CONV_ID,
        content="请问资产负债表怎么看？",
        request_id=request_id,
        client_message_id=client_msg_id,
    )
    check("插入用户消息返回 message_id", msg_id is not None and isinstance(msg_id, int))

    # --- 幂等性：重复插入同一 client_message_id 返回 None ---
    dup_id = await insert_user_message(
        pool,
        conversation_id=TEST_CONV_ID,
        content="重复消息内容",
        request_id="some_other_req",
        client_message_id=client_msg_id,
    )
    check("幂等性：重复 client_message_id 返回 None", dup_id is None,
          f"期望 None, 实际 {dup_id}")

    # --- 插入 AI 回复 ---
    ai_msg_id = await insert_assistant_message(
        pool,
        conversation_id=TEST_CONV_ID,
        content="资产负债表是反映企业在某一特定日期...",
        request_id=request_id,
        metadata={"source": "accounting-expert", "tokens": 150},
    )
    check("插入 AI 消息返回 message_id", ai_msg_id is not None and isinstance(ai_msg_id, int))

    # --- 查询消息列表 ---
    messages = await list_owned_messages(pool, user_id=TEST_USER_ID, conversation_id=TEST_CONV_ID)
    check("消息列表不为 None", messages is not None)
    if messages is not None:
        check("消息列表包含 2 条", len(messages) >= 2, f"实际 {len(messages)} 条")
        roles = [m["role"] for m in messages]
        check("包含 user 角色", "user" in roles)
        check("包含 assistant 角色", "assistant" in roles)
        # 验证 metadata 被正确解析为 dict
        ai_msg = next((m for m in messages if m["role"] == "assistant"), None)
        check("AI 消息 metadata 是 dict", ai_msg is not None and isinstance(ai_msg.get("metadata"), dict),
              f"类型: {type(ai_msg.get('metadata')) if ai_msg else 'N/A'}")

    # --- 所有权隔离：其他用户查不到消息 ---
    other_msgs = await list_owned_messages(pool, user_id="other_user_nonexistent", conversation_id=TEST_CONV_ID)
    check("其他用户查不到消息（所有权隔离）", other_msgs is None)

    # --- 标记请求失败 ---
    fail_req_id = f"test_fail_req_{SUFFIX}"
    fail_cmsg = f"test_fail_cmsg_{SUFFIX}"
    await insert_user_message(
        pool,
        conversation_id=TEST_CONV_ID,
        content="这条消息会失败",
        request_id=fail_req_id,
        client_message_id=fail_cmsg,
    )
    await mark_request_failed(pool, request_id=fail_req_id, error_code="test_error")
    fail_msgs = await list_owned_messages(pool, user_id=TEST_USER_ID, conversation_id=TEST_CONV_ID)
    if fail_msgs is not None:
        failed_msg = next(
            (m for m in fail_msgs if m.get("status") == "failed"), None
        )
        check("mark_request_failed 后消息状态变为 failed", failed_msg is not None)
        check("error_code 正确", failed_msg is not None and failed_msg.get("error_code") == "test_error")


async def test_files(pool):
    """测试文件元数据 CRUD"""
    from app.data_gateway.repositories.files import (
        create_file_record,
        get_owned_ready_files,
    )

    print("\n--- 文件 (files) 测试 ---")
    print("-" * 50)

    # --- 创建文件记录 ---
    await create_file_record(
        pool,
        file_id=TEST_FILE_ID,
        user_id=TEST_USER_ID,
        filename="测试报告.pdf",
        content_type="application/pdf",
        extension=".pdf",
        size_bytes=2048,
        storage_path=f"C:/temp/test_{SUFFIX}.pdf",
        ttl_seconds=86400,  # 1 天
    )

    # 验证记录存在
    files = await get_owned_ready_files(pool, user_id=TEST_USER_ID, file_ids=[TEST_FILE_ID])
    check("创建文件后可查询到", len(files) == 1, f"实际 {len(files)} 条")
    if files:
        f = files[0]
        check("文件 filename 正确", f["filename"] == "测试报告.pdf")
        check("文件 content_type 正确", f["content_type"] == "application/pdf")
        check("文件 extension 正确", f["extension"] == ".pdf")
        check("文件 size_bytes 正确", f["size_bytes"] == 2048)

    # --- 所有权隔离 ---
    other_files = await get_owned_ready_files(
        pool, user_id="other_user", file_ids=[TEST_FILE_ID]
    )
    check("其他用户查不到文件（所有权隔离）", len(other_files) == 0)

    # --- 空列表查询 ---
    empty = await get_owned_ready_files(pool, user_id=TEST_USER_ID, file_ids=[])
    check("空 file_ids 返回空列表", empty == [])

    # --- 不存在的文件 ID ---
    missing = await get_owned_ready_files(
        pool, user_id=TEST_USER_ID, file_ids=["nonexistent_file_99999"]
    )
    check("不存在的 file_id 不在结果中", missing == [])


async def test_edge_cases(pool):
    """边界情况测试"""
    from app.data_gateway.repositories.conversations import (
        create_conversation,
        insert_user_message,
        list_owned_messages,
        delete_owned_conversation,
    )

    print("\n--- 边界情况测试 ---")
    print("-" * 50)

    # --- 长文本消息 ---
    long_conv_id = f"test_long_{SUFFIX}"
    await create_conversation(
        pool, conversation_id=long_conv_id, user_id=TEST_USER_ID,
        agent_id="requirement-pre-review", title="长文本测试",
    )
    long_content = "这是一段很长的文本。" * 500  # 约 5000 字符
    msg_id = await insert_user_message(
        pool,
        conversation_id=long_conv_id,
        content=long_content,
        request_id=f"long_req_{SUFFIX}",
        client_message_id=f"long_cmsg_{SUFFIX}",
    )
    check("长文本消息插入成功", msg_id is not None)
    msgs = await list_owned_messages(pool, user_id=TEST_USER_ID, conversation_id=long_conv_id)
    if msgs:
        check("长文本消息内容完整", msgs[0]["content"] == long_content)

    # --- 特殊字符 ---
    special_conv_id = f"test_special_{SUFFIX}"
    await create_conversation(
        pool, conversation_id=special_conv_id, user_id=TEST_USER_ID,
        agent_id="business-analyst", title="特殊字符测试",
    )
    special_content = "单引号'双引号\"反斜杠\\换行\n制表\t中文汉字"
    msg_id2 = await insert_user_message(
        pool,
        conversation_id=special_conv_id,
        content=special_content,
        request_id=f"special_req_{SUFFIX}",
        client_message_id=f"special_cmsg_{SUFFIX}",
    )
    check("特殊字符消息插入成功", msg_id2 is not None)
    msgs2 = await list_owned_messages(pool, user_id=TEST_USER_ID, conversation_id=special_conv_id)
    if msgs2:
        check("特殊字符消息内容完整", msgs2[0]["content"] == special_content)

    # --- 删除不存在的会话 ---
    deleted = await delete_owned_conversation(
        pool, conversation_id="nonexistent_conv_999999", user_id=TEST_USER_ID
    )
    check("删除不存在的会话返回 False", deleted is False)

    # --- 查询不存在的会话的消息 ---
    empty_msgs = await list_owned_messages(
        pool, user_id=TEST_USER_ID, conversation_id="nonexistent_conv_999999"
    )
    check("查询不存在会话的消息返回 None", empty_msgs is None)

    # 清理辅助会话（直接用 pool 删，不需要走 repository）
    await pool.execute("DELETE FROM messages WHERE conversation_id = ANY($1::varchar[])",
                       [long_conv_id, special_conv_id])
    await pool.execute("DELETE FROM conversations WHERE conversation_id = ANY($1::varchar[])",
                       [long_conv_id, special_conv_id])


async def cleanup(pool):
    """清理本次测试产生的所有数据"""
    print("\n--- 清理测试数据 ---")
    print("-" * 50)

    # 删除消息（CASCADE 会自动删，显式删更安全）
    await pool.execute(
        "DELETE FROM messages WHERE conversation_id = $1",
        TEST_CONV_ID,
    )

    # 删除测试会话（含长文本/特殊字符的子会话）
    await pool.execute(
        "DELETE FROM conversations WHERE user_id = $1 AND conversation_id LIKE $2",
        TEST_USER_ID,
        f"test_%_{SUFFIX}",
    )

    # 删除文件记录
    await pool.execute(
        "DELETE FROM uploaded_files WHERE file_id = $1 AND user_id = $2",
        TEST_FILE_ID,
        TEST_USER_ID,
    )

    # 删除用户会话（如有）
    await pool.execute(
        "DELETE FROM user_sessions WHERE user_id = $1",
        TEST_USER_ID,
    )

    # 删除测试用户
    await pool.execute(
        "DELETE FROM users WHERE user_id = $1",
        TEST_USER_ID,
    )
    print(f"  已清理用户 {TEST_USER_ID} 及其关联数据")


async def main():
    global PASS, FAIL

    print("=" * 60)
    print("  data_gateway 数据库层完整测试")
    print("=" * 60)
    print(f"  测试 ID 后缀: {SUFFIX}")
    print(f"  工作目录: {os.getcwd()}")
    print(f"  .env 存在: {Path('.env').exists()}")
    print(f"  数据库: localhost:5432 / knowledge_agent / postgres")
    print()

    # ---- 连接数据库 ----
    from app.data_gateway.pool import get_pool, close_pool

    try:
        pool = await get_pool()
        # 验证连接
        version = await pool.fetchval("SELECT version()")
        print(f"  数据库连接成功 [OK]")
        print(f"  PostgreSQL: {version.split(',')[0]}")
    except Exception as e:
        print(f"\n[FAIL] 数据库连接失败: {e}")
        print("\n请检查：")
        print("  1. PostgreSQL 服务是否已启动？")
        print("  2. 项目根目录 .env 中 DB_PASSWORD 是否正确？")
        print("  3. knowledge_agent 数据库是否已创建？")
        print("  4. 迁移脚本是否已执行？")
        print("\n  当前配置见项目根目录 .env")
        return 1

    # ---- 创建测试用户（conversations 有外键引用 users）----
    import bcrypt
    hashed = bcrypt.hashpw(b"test_password_123", bcrypt.gensalt()).decode()
    try:
        await pool.execute(
            """
            INSERT INTO users (user_id, name, email, password)
            VALUES ($1, $2, $3, $4)
            """,
            TEST_USER_ID,
            f"测试用户_{SUFFIX}",
            f"test_{SUFFIX}@example.com",
            hashed,
        )
        print(f"  测试用户已创建: {TEST_USER_ID}")
    except Exception as e:
        print(f"\n[FAIL] 创建测试用户失败: {e}")
        return 1

    try:
        await test_conversations(pool)
        await test_messages(pool)
        await test_files(pool)
        await test_edge_cases(pool)
    finally:
        await cleanup(pool)
        await close_pool()

    # ---- 统计 ----
    total = PASS + FAIL
    print("\n" + "=" * 60)
    print(f"  测试结果: {PASS}/{total} 通过", end="")
    if FAIL > 0:
        print(f", {FAIL} 失败 [FAIL]")
    else:
        print(" [OK] 全部通过！")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
