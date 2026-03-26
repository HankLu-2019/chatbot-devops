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
    embedding     vector(768)
);

-- HNSW index for vector similarity search
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx
    ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- BM25 full-text index via ParadeDB pg_search (v0.22+ syntax)
CREATE INDEX IF NOT EXISTS documents_bm25_idx
    ON documents USING bm25 (id, title, content)
    WITH (key_field = 'id');
