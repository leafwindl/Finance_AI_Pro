# Finance AI 知识库（检索模块）

证券交易智能体知识库系统 —— 文档解析 → LLM 分类 → PG+ES+Neo4j 入库 → 智能检索。

## ⚠️ 重要：本仓库不包含模型，向量检索默认不可用

**向量检索模型（约 1.2GB）未随代码上传**。克隆后必须自行下载模型，否则：
- 向量检索（语义相似度）**无法运行**
- `/api/v1/search` 的 `vector_score` 恒为 `null`、`trace.vector_count` 为 0

**如何启用向量检索**（见下方"环境准备"第 3 步）：从 ModelScope 下载 `BAAI/bge-large-zh-v1.5`，在 `.env` 设置 `EMBEDDING_MODEL` 指向本地路径，然后重建知识库。

## 架构

```
Finance_AI_KnowledgeBase
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  parser  │ → │classifier│ → │  writer  │ → │ searcher │
│  解析模块  │   │  分类模块  │   │  写入模块 │   │  检索模块 │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
 txt/pdf/docx   LLM分段+分类   向量化→PG+ES   Neo4j→ES→PG
  →纯文本       KB01~KB06      Neo4j图谱      三段式管线
```

## 模块说明

| 模块 | 作用 |
|---|---|
| `parser/` | 文档解析：txt/pdf/docx → 纯文本 |
| `classifier/` | LLM 分段 + 六库分类 → 知识点 chunk |
| `writer/` | 入库：向量化 → PG（元数据）+ ES（正文+向量）+ Neo4j（图谱） |
| `searcher/` | **检索核心**：Neo4j 扩展 → ES 混合(BM25+向量) → PG 溯源 |
| `services/` | 上述模块的 HTTP 服务封装 |
| `scripts/` | 重建知识库、建图谱、top-k 测试等工具 |

## 检索接口（智能体用）

| 接口 | 说明 |
|---|---|
| `POST /api/v1/search` | 稳定检索接口（推荐） |
| `POST /search` | 旧版多模式检索（不推荐新接入） |
| `GET /health` / `/readiness` | 存活/就绪检查 |

响应字段：`content`（正文）、`score`（RRF 融合分）、`bm25_score`（字面分）、`vector_score`（语义分，需模型）、`metadata`（溯源）。

## 配置文件说明（.env.example / .gitignore）

### `.env.example` —— 环境变量模板
- **是什么**：一份"配置清单模板"，列出程序需要的所有配置项（数据库连接、模型路径、API key 等），值都是占位符（`your_api_key_here`、`你的路径`）。
- **怎么用**：复制一份改名为 `.env`，再填你自己的实际值：
  ```bash
  cp .env.example .env    # Windows: copy .env.example .env
  ```
- **为什么要有它**：`.env`（真实配置）含密码/key/绝对路径，**不能提交**；`.env.example`（模板）可以提交，队友照它配自己的 `.env`。
- **当前模板默认值**：模型=本地 bge 路径（需自行下载）、`ENABLE_VECTOR_SEARCH=true`、`ENABLE_NEO4J=true`。

### `.gitignore` —— 提交忽略规则
- **是什么**：告诉 git **哪些文件/目录不提交**到仓库。
- **当前已忽略**：`.env`（密钥）、`models/`（1.2GB 模型）、`output/`（生成产物）、`__pycache__/`、`.pytest_cache/`、`_backup_*/`、`.claude/`、`一键启动知识库.bat` 等。
- **为什么要有它**：防止把大文件（模型）、密钥（.env）、临时产物误传上 GitHub —— 会导致仓库臃肿、密钥泄露、队友无法使用。

> ⚠️ 若你看到的仓库里出现 `models/`、`.env` 等文件，说明 `.gitignore` 未生效，请检查是否已把 `.gitignore` 提交到仓库根目录。

## 环境准备（克隆后必做）

### 1. 依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 `.env`
复制 `.env.example` 为 `.env`（本仓库未含 `.env`，需自建），填入三库连接、模型路径。

### 3. 向量模型（关键！）
```bash
# 从 ModelScope 下载 BAAI/bge-large-zh-v1.5（1024 维），放到任意目录
# 然后 .env 设置：
#   EMBEDDING_MODEL=/你的路径/models/bge-large-zh-v1.5
#   ENABLE_VECTOR_SEARCH=true
```

### 4. 三数据库（Docker）
```bash
docker compose up -d   # 启动 PG(5432) / ES(9200) / Neo4j(7687)
```

### 5. ES 中文分词插件（首次）
```bash
docker exec <es容器> bin/elasticsearch-plugin install analysis-smartcn
docker restart <es容器>
```

### 6. Neo4j 图谱（可选，但建议）
```bash
python scripts/build_neo4j_graph.py   # 从 ES 切片建图谱（无 LLM）
```
不建图谱：检索仍可用，但 `expanded_keywords` 为空、无关键词扩展。

## 使用

```bash
# 重建知识库（PG + ES + 向量）
python scripts/rebuild_knowledge_base.py --source "你的知识源目录"

# 建图谱
python scripts/build_neo4j_graph.py

# 启动检索服务
python -m uvicorn searcher.kb_search_server:app --host 127.0.0.1 --port 8002

# 测试
python scripts/topk_eval.py "证券投资基金法" --top-k 5 --similarity
```

## 测试

```bash
python -m pytest tests -q
```

## 已知说明

- **向量检索依赖本地模型**，未上传；不下载则语义检索不可用（见顶部警告）。
- **`finetune-text2vec-base-chinese/` 目录说明**：这是**写入模块同学使用的 embedding 模型目录**（text2vec 系，保留供参考）。⚠️ 注意它**不完整** —— `model.safetensors` 只是 134 字节的 Git LFS 指针，**权重未下载、无法加载**，**不能用于向量化**。实际运行的向量模型是 `BAAI/bge-large-zh-v1.5`（需自行下载）。统一知识库时请理解：写入侧参照的是 text2vec，检索侧实际用的是 bge，二者在 `.env` 的 `EMBEDDING_MODEL` 指定。
- **Neo4j 是外部服务**，需 Docker 启动 + 建图谱；挂了检索会降级（不报错，只是无扩展词）。
- **ES 需 smartcn 插件**，否则 rebuild 重建索引会失败。
- 检索无鉴权，生产环境请自行加鉴权。
