# data_gateway — 数据库端接口（人员B 负责）
#
# 职责：PostgreSQL 数据持久化（连接池 + CRUD + 迁移）
# 文件：
#   pool.py                 — asyncpg 连接池管理
#   repositories/
#     conversations.py      — 会话/消息 CRUD
#     files.py              — 文件记录 CRUD
# 迁移脚本：
#   scripts/apply_migrations.py — SQL 迁移执行器
