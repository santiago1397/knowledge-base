-- Knowledge Base schema. Run once against the `knowledge_base` database.
-- Requires: CREATE EXTENSION IF NOT EXISTS vector;  (pgvector)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS courses (
    id         SERIAL PRIMARY KEY,
    slug       TEXT UNIQUE NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lessons (
    id              SERIAL PRIMARY KEY,
    course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    code            TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    duration        TEXT NOT NULL DEFAULT '',
    source_url      TEXT NOT NULL DEFAULT '',
    video_url       TEXT NOT NULL DEFAULT '',
    video_file      TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    key_points      JSONB NOT NULL DEFAULT '[]',
    tags            JSONB NOT NULL DEFAULT '[]',
    content_md      TEXT NOT NULL DEFAULT '',
    transcript      JSONB NOT NULL DEFAULT '[]',
    transcript_text TEXT NOT NULL DEFAULT '',
    module_order    INTEGER NOT NULL DEFAULT 0,   -- course module order (0 = ungrouped)
    module_title    TEXT NOT NULL DEFAULT '',
    lesson_order    INTEGER NOT NULL DEFAULT 0,   -- position within the course (links.md order)
    UNIQUE (course_id, code)
);

-- Idempotent upgrade for a DB created before module grouping existed.
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS module_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS module_title TEXT NOT NULL DEFAULT '';
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS lesson_order INTEGER NOT NULL DEFAULT 0;

-- bge-small-en-v1.5 => 384 dimensions
CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    course_id   INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    lesson_code TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    source      TEXT NOT NULL,            -- summary | transcript | content
    start_time  REAL,                     -- video deep-link (nullable)
    text        TEXT NOT NULL,
    embedding   vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_course_idx ON chunks (course_id);

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-user daily question count (rate limit).
CREATE TABLE IF NOT EXISTS user_usage (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day       DATE NOT NULL,
    questions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

-- Global daily MiniMax token spend (kill-switch).
CREATE TABLE IF NOT EXISTS usage_daily (
    day         DATE PRIMARY KEY,
    tokens_used BIGINT NOT NULL DEFAULT 0
);
