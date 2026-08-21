-- 需求预评审报告及人工审批结果

CREATE TABLE IF NOT EXISTS requirement_review_records (
    review_id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    report_message_id INTEGER NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    approval_id VARCHAR(128) NOT NULL,
    report_content TEXT NOT NULL,
    decision VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (decision IN ('pending', 'approve', 'reject', 'revise')),
    rejection_reason VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, approval_id),
    UNIQUE (report_message_id)
);

CREATE INDEX IF NOT EXISTS idx_requirement_reviews_conversation
    ON requirement_review_records(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requirement_reviews_decision
    ON requirement_review_records(decision);
