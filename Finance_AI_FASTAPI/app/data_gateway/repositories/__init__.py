# data_gateway.repositories — 数据访问层（人员B 负责）
#
# 所有查询必须带 user_id 所有权条件。
# 不使用 ORM，全部为 asyncpg 原生 SQL。
