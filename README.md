# Acme Engineering RAG Chatbot

A production-quality Retrieval-Augmented Generation chatbot for Acme Engineering's internal knowledge base.

- **Storage & Search**: ParadeDB (PostgreSQL + pgvector + pg_search)
- **Embeddings & Generation**: Google Gemini (`gemini-embedding-001` + `gemini-2.5-flash`)
- **Retrieval**: Hybrid BM25 + vector search with Reciprocal Rank Fusion (RRF)
- **Reranking**: Cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
- **Frontend**: Next.js 15 + Tailwind CSS

## Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 20+
- A `GEMINI_API_KEY` in `.env` (already present)

## Quick Start

### 1. Start ParadeDB

```bash
docker compose up -d
```

Wait for the health check to pass:

```bash
docker compose ps   # status should be "healthy"
```

The `schema.sql` is auto-applied on first start. It creates the `documents` table, HNSW vector index, and BM25 full-text index.

### 2. Ingest data

```bash
cd ingestion
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ingest.py
```

This will:
1. Load Confluence pages, Jira tickets, and plain-text docs from `data/`
2. Chunk them with structure-aware splitting
3. Embed each chunk with Gemini `gemini-embedding-001` (768 dims via `output_dimensionality`)
4. Insert into ParadeDB, skipping any chunks already present (idempotent)

Re-running `ingest.py` is safe — existing chunks are detected by content hash and skipped.

### 3. Start the reranker sidecar

In a separate terminal:

```bash
cd reranker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

The reranker loads `cross-encoder/ms-marco-MiniLM-L-6-v2` on startup (~50MB, ~5s).

Health check: `curl http://localhost:8000/health`

### 4. Start the Next.js app

```bash
cd app
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Architecture

```
Browser
  │
  └─► Next.js App (port 3000)
        │
        ├─► POST /api/chat
        │     1. Rewrite query (gemini-2.5-flash)
        │     2. Embed query (gemini-embedding-001, 768 dims)
        │     3. Hybrid search: BM25 (pg_search) + vector (pgvector) with RRF
        │     4. Rerank top-30 → top-6 (cross-encoder sidecar)
        │     5. Score threshold filter (< 0.3 → "I don't have info")
        │     6. Generate answer (Gemini Flash, context-grounded)
        │
        ├─► ParadeDB / PostgreSQL (port 5432)
        │     - pgvector: HNSW index on embedding column (768 dims, cosine)
        │     - pg_search: BM25 index on title + content (en_stem tokenizer)
        │
        └─► Reranker Sidecar (port 8000)
              - FastAPI + sentence-transformers
              - POST /rerank: cross-encoder scoring
```

## Data Sources

| Source | Location | Count |
|--------|----------|-------|
| Confluence pages (ENG space) | `data/confluence/pages.json` | 10 pages |
| Jira tickets | `data/jira/tickets.json` | 15 tickets |
| Internal docs | `data/docs/*.txt` | 3 files |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | (required) | Google Gemini API key |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/ragdb` | PostgreSQL connection string |
| `RERANKER_URL` | `http://localhost:8000` | Reranker sidecar base URL |

## Demo Questions

The following questions are answerable from the ingested data:

1. **"How do I deploy to production?"** → ENG-001 (Kubernetes Deployment Guide), runbook-payment-service.txt
2. **"My pod is OOMKilled, what should I do?"** → ENG-002 (OOMKilled Troubleshooting), ENG-42 (Jira ticket with real fix)
3. **"How do I rollback a bad deployment?"** → ENG-001, ENG-084 (Jira ticket with step-by-step rollback)
4. **"Why am I getting 401 errors after token rotation?"** → ENG-004 (API Authentication Setup), ENG-55 (Jira ticket with root cause)
5. **"How do I check logs for a specific pod?"** → ENG-010 (Monitoring Guide), ENG-129 (Jira ticket with kubectl commands)

## Project Structure

```
RAG_Chatbot/
├── docker-compose.yml          # ParadeDB container
├── .env                        # GEMINI_API_KEY (not committed)
├── .gitignore
├── schema.sql                  # Table + index definitions
├── data/
│   ├── confluence/pages.json   # 10 Confluence pages
│   ├── jira/tickets.json       # 15 Jira tickets
│   └── docs/*.txt              # 3 internal docs
├── ingestion/
│   ├── requirements.txt
│   ├── ingest.py               # Main ingestion pipeline
│   └── chunker.py              # Structure-aware chunking
├── reranker/
│   ├── requirements.txt
│   └── main.py                 # FastAPI cross-encoder service
└── app/                        # Next.js frontend + API
    ├── package.json
    ├── next.config.js
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx
    │   └── api/chat/route.ts   # RAG pipeline endpoint
    ├── components/
    │   └── ChatUI.tsx
    └── lib/
        └── db.ts
```

## Notes

- The reranker is optional — if it is unreachable, the app falls back to the top-6 results by RRF score.
- Ingestion is idempotent: content is hashed (SHA-256 of normalised text) and duplicate chunks are skipped.
- The BM25 index uses the `en_stem` tokenizer for English language stemming.
- The HNSW index uses cosine distance (`vector_cosine_ops`) with m=16, ef_construction=64.
