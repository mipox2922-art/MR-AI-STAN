-- SQLite upgrade reference for the MR AI command-center truth model.
-- The app runs idempotent upgrades in backend/app/migrations.py on startup.
-- Run this manual SQL only when applying a one-time migration to an older DB.
ALTER TABLE conversations ADD COLUMN session_id VARCHAR(100);
-- Existing tasks lack reliable authorship. Preserve that uncertainty rather than inventing Boss as the source.
ALTER TABLE tasks ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'unknown';
ALTER TABLE tasks ADD COLUMN requested_by VARCHAR(100);
ALTER TABLE tasks ADD COLUMN approved_by INTEGER;
ALTER TABLE tasks ADD COLUMN approved_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS ix_conversations_user_session ON conversations (user_id, session_id);

CREATE TABLE IF NOT EXISTS task_steps (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 1,
  title VARCHAR(255) NOT NULL,
  state VARCHAR(20) NOT NULL DEFAULT 'pending',
  evidence TEXT,
  verified_at TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_state_snapshots (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE,
  state VARCHAR(20) NOT NULL DEFAULT 'IDLE',
  reason_safe VARCHAR(500),
  request_id VARCHAR(100),
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_error_logs (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  component VARCHAR(100) NOT NULL,
  code VARCHAR(100) NOT NULL,
  message_safe VARCHAR(500) NOT NULL,
  created_at TIMESTAMP
);

UPDATE tasks SET status = 'WAITING_FOR_VERIFICATION', progress = 0
WHERE UPPER(status) IN ('COMPLETED', 'DONE')
AND NOT EXISTS (
  SELECT 1 FROM task_steps s
  WHERE s.task_id = tasks.id
    AND LOWER(s.state) = 'verified'
    AND LENGTH(TRIM(COALESCE(s.evidence, ''))) > 0
);
