-- 009_kb_blocks.sql — 块级多库支持
-- 自动分类时：一篇文档切成多个块，每块独立分类入库（可能分到不同 KB）
--  - kb_code 允许为空（任务级不再强制单一 KB；各块分类结果在 blocks 里）
--  - blocks JSONB：[{heading, kb_code, doc_id, total_chunks}, ...]
--  - kb_distribution JSONB：{KB01: 2, KB04: 1, ...} 汇总，供前端展示

ALTER TABLE kb_ingest_tasks ALTER COLUMN kb_code DROP NOT NULL;

ALTER TABLE kb_ingest_tasks ADD COLUMN IF NOT EXISTS blocks JSONB;
ALTER TABLE kb_ingest_tasks ADD COLUMN IF NOT EXISTS kb_distribution JSONB;
