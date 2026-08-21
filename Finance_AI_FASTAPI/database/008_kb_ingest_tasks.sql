-- 008_kb_ingest_tasks.sql
-- 知识库入库任务表（V1：上传即触发，人工选 KB）

CREATE TABLE IF NOT EXISTS kb_ingest_tasks (
    task_id          VARCHAR(64) PRIMARY KEY,
    file_id          VARCHAR(64) NOT NULL,
    user_id          VARCHAR(32) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    filename         VARCHAR(256) NOT NULL,
    status           VARCHAR(16)  NOT NULL DEFAULT 'processing',  -- processing/completed/failed/rolled_back
    stage            VARCHAR(16)  NOT NULL DEFAULT 'saved',       -- saved/ingesting
    percent          INTEGER      NOT NULL DEFAULT 10,
    kb_code          VARCHAR(8)   NOT NULL,                       -- KB01~KB06
    total_chunks     INTEGER,
    doc_id           VARCHAR(128),
    error_code       VARCHAR(64),
    error_message    TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ
);

CREATE INDEX idx_kb_tasks_user ON kb_ingest_tasks(user_id);
CREATE INDEX idx_kb_tasks_status ON kb_ingest_tasks(status);
