# 知识图谱接口契约

> 版本：v1.0
> 状态：已实现
> 公共前缀：`/api/v1`

知识图谱页的接口事实来源：Vue → FastAPI Gateway → Neo4j / PostgreSQL(knowledge_base)。

```text
Browser / Vue (/knowledge-graph)
  -> FastAPI Gateway /api/v1/knowledge/*
     -> Neo4j（图谱：知识库→文件 节点/关系）
     -> knowledge_base PostgreSQL（文件列表 / 文档内容）
```

浏览器不能直连 Neo4j 或知识库库。鉴权使用与现有 Gateway 一致的 HttpOnly Session Cookie（`credentials: 'include'`）。

## 图模型（Neo4j）

```
(KnowledgeBase {kb_code, kb_name}) -[:CONTAINS]-> (Document {doc_id, title, source_file, kb_code})
```

- 共 6 个知识库节点（KB01~KB06）与 80+ 文档节点。
- `doc_id` 与 PG `knowledge_base.kb_documents` 同源（`sha256(相对路径)[:24]`），保证图上点得开文档内容。
- 数据由 `Finance_AI_KnowledgeBase/scripts/seed_kb_graph.py` 幂等灌入（MERGE + 唯一约束）。

## 通用约定

- 所有端点需要登录，Session 缺失返回 `401 {"detail":"未登录"}`。
- 普通响应与错误为 UTF-8 JSON；错误格式沿用 `gateway-api.md`：
  - 业务性错误：`4xx {"detail":"..."}`
  - 上游不可用：`503 {"error":{"code":"...","message":"...","retryable":true}}`
- 节点 id 使用 `kb__<kb_code>` / `doc__<doc_id>` 前缀保证全局唯一。

## 1. 全图谱

```http
GET /api/v1/knowledge/graph
```

读取知识库→文件两级全图，供前端关系图谱组件（vue-force-graph）渲染。

成功响应 `200`：

```json
{
  "nodes": [
    {
      "id": "kb__KB01",
      "type": "kb",
      "kb_code": "KB01",
      "label": "系统业务知识库",
      "count": 46
    },
    {
      "id": "doc__a1b2c3d4e5f60718293a4b5c",
      "type": "doc",
      "doc_id": "a1b2c3d4e5f60718293a4b5c",
      "kb_code": "KB01",
      "label": "系统概览",
      "source_file": "KB01_系统业务知识库/系统概览.md"
    }
  ],
  "links": [
    { "source": "kb__KB01", "target": "doc__a1b2c3d4e5f60718293a4b5c", "type": "CONTAINS" }
  ],
  "meta": {
    "total_nodes": 95,
    "total_links": 89,
    "refreshed_at": "2026-08-19T09:00:00+08:00"
  }
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `nodes[].type` | `kb` 知识库节点 / `doc` 文档节点 |
| `nodes[].count` | 仅 kb 节点；该知识库下的文档数 |
| `links[].source/target` | 节点 id（对应 `nodes[].id`） |
| `meta.refreshed_at` | 图谱生成时间（UTC ISO 8601） |

Neo4j 不可达 → `503`：

```json
{
  "error": {
    "code": "knowledge_graph_unavailable",
    "message": "知识图谱服务暂不可用，请确认 Neo4j 已启动",
    "retryable": true
  }
}
```

## 2. 知识库清单

```http
GET /api/v1/knowledge/kbs
```

知识库清单（按 PG `kb_documents` 统计，返回存在文档的库）。成功响应 `200`：

```json
{
  "kbs": [
    { "kb_code": "KB01", "kb_name": "系统业务知识库", "document_count": 46 }
  ]
}
```

## 3. 知识库下的文件列表

```http
GET /api/v1/knowledge/kbs/{kb_code}/documents
```

`kb_code` 为 `KB01`~`KB06`。成功响应 `200`：

```json
{
  "kb_code": "KB01",
  "kb_name": "系统业务知识库",
  "documents": [
    {
      "doc_id": "a1b2c3d4e5f60718293a4b5c",
      "title": "系统概览",
      "source_file": "KB01_系统业务知识库/系统概览.md",
      "chunk_count": 8,
      "version": 1
    }
  ]
}
```

知识库不存在（无任何文档）→ `404 {"detail":"知识库不存在"}`。

## 4. 文档内容

```http
GET /api/v1/knowledge/documents/{doc_id}/content
```

按 `doc_id` 聚合其全部 chunk、按 `chunk_id` 顺序拼接为 markdown（`# 标题` + 每块 `## heading` + 正文）。
成功响应 `200`：

```json
{
  "doc_id": "a1b2c3d4e5f60718293a4b5c",
  "title": "系统概览",
  "source_file": "KB01_系统业务知识库/系统概览.md",
  "kb_code": "KB01",
  "content_markdown": "# 系统概览\n\n## 系统定位\n...",
  "chunk_count": 8,
  "chars": 18452
}
```

`chars` 为 `content_markdown` 的字符数，用于前端展示篇幅。文档不存在 → `404 {"detail":"文档不存在"}`。

## 4.1 文档子图（分块与实体）

```http
GET /api/v1/knowledge/documents/{doc_id}/subgraph
```

返回该文档的「分块 → 实体」子图，前端点击文件节点时按需展开。
为控制渲染规模：每分块最多返回 5 个关联实体（HAS_ENTITY），每实体最多 3 条关联边（RELATED，按 weight 降序）。
成功响应 `200`：

```json
{
  "doc_id": "a1b2c3d4e5f60718293a4b5c",
  "title": "KB01-01 系统概览",
  "kb_code": "KB01",
  "nodes": [
    { "id": "chunk__a1b2c3d4e5f60718293a4b5c_0000", "type": "chunk", "chunk_id": "...",
      "doc_id": "a1b2c3d4e5f60718293a4b5c", "kb_code": "KB01",
      "label": "系统定位", "text": "分块正文...", "n_tokens": 120 },
    { "id": "entity__登录", "type": "entity", "name": "登录", "entity_type": "MODULE",
      "kb_code": "KB01", "doc_id": "a1b2c3d4e5f60718293a4b5c",
      "label": "登录", "description": "用户登录模块" }
  ],
  "links": [
    { "source": "chunk__..._0000", "target": "doc__a1b2c3d4e5f60718293a4b5c", "type": "PART_OF" },
    { "source": "chunk__..._0000", "target": "entity__登录", "type": "HAS_ENTITY" },
    { "source": "entity__登录", "target": "entity__会话", "type": "RELATED", "weight": 1.5 }
  ],
  "meta": { "total_nodes": 81, "total_links": 153 }
}
```

- `RELATED` 的目标实体可能属于其他文档，节点会一并返回（`doc_id` 为 `null`），避免边悬空。
- 文档不存在（Neo4j 中无该文档节点且无分块）→ `404 {"detail":"文档不存在"}`。
- Neo4j 不可达 → `503 {"error":{"code":"knowledge_graph_unavailable",...}}`。

## 5. 错误码汇总

| 状态码 | code | 含义 |
|---|---:|---|---|
| `401` | — | 未登录或 Session 过期 |
| `404` | — | 知识库/文档不存在 |
| `503` | `knowledge_graph_unavailable` | Neo4j 不可达（图谱接口） |
| `503` | `knowledge_docs_unavailable` | PostgreSQL(knowledge_base) 不可达（清单/列表/内容接口） |

## 6. Gateway 新增配置项（`.env`）

```dotenv
# 知识图谱（Neo4j）——密码与 docker-compose.yml 的 NEO4J_AUTH 一致
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=finance_ai_dev
NEO4J_DATABASE=neo4j
NEO4J_CONNECT_TIMEOUT_SECONDS=5

# 知识库元数据库 knowledge_base（与业务库 knowledge_agent 分离）
KB_DB_HOST=localhost
KB_DB_PORT=5432
KB_DB_NAME=knowledge_base
KB_DB_USER=postgres
KB_DB_PASSWORD=<knowledge_base 库口令>
KB_DB_POOL_MIN_SIZE=1
KB_DB_POOL_MAX_SIZE=5
```