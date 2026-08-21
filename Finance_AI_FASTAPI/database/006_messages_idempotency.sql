-- 006_messages_idempotency.sql
-- user 消息幂等：同一会话内相同 client_message_id 只能插入一次

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_idempotent
    ON messages(conversation_id, client_message_id)
    WHERE role = 'user' AND client_message_id IS NOT NULL;
