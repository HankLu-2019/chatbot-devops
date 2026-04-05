-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

-- Main documents table
CREATE TABLE IF NOT EXISTS documents (
    id            SERIAL PRIMARY KEY,
    content       TEXT,
    title         TEXT,
    source_type   TEXT,
    space         TEXT,
    ticket_id     TEXT,
    status        TEXT,
    url           TEXT,
    updated_at    TIMESTAMPTZ,
    content_hash  TEXT UNIQUE,
    parent_id     INT REFERENCES documents(id),
    embedding     vector(1536)
);

-- HNSW index for vector similarity search
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx
    ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- BM25 full-text index via ParadeDB pg_search (v0.22+ syntax)
CREATE INDEX IF NOT EXISTS documents_bm25_idx
    ON documents USING bm25 (id, title, content)
    WITH (key_field = 'id');

-- B-tree index on space column for team-scoped filtering
CREATE INDEX IF NOT EXISTS documents_space_idx
    ON documents (space);

-- Feedback table for thumbs up/down votes
CREATE TABLE IF NOT EXISTS feedback (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    space      TEXT,
    question   TEXT NOT NULL,
    vote       TEXT NOT NULL CHECK (vote IN ('up', 'down'))
);

-- Index for Panel 6 "Recent Feedback" query: ORDER BY created_at DESC LIMIT 20
CREATE INDEX IF NOT EXISTS feedback_created_at_idx ON feedback (created_at DESC);
