# Acme Engineering RAG Chatbot

A production-quality Retrieval-Augmented Generation chatbot for Acme Engineering's internal knowledge base. Each engineering team gets its own page with knowledge scoped to their domain.

- **Storage & Search**: ParadeDB (PostgreSQL + pgvector + pg_search)
- **Embeddings & Generation**: Google Gemini (`gemini-embedding-001` + `gemini-2.5-flash`)
- **Retrieval**: Hybrid BM25 + vector search with Reciprocal Rank Fusion (RRF), team-scoped by `space`
- **Reranking**: Cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
- **Frontend**: Next.js 15 App Router + Tailwind CSS, multi-page with persistent sidebar

## Prerequisites

- Docker & Docker Compose
- A `GEMINI_API_KEY` (that's it — no local Python or Node required)

## Quick Start

### 1. Set your API key

```bash
cp .env.example .env
# then edit .env and add your GEMINI_API_KEY
```

### 2. Start all services

```bash
docker compose up -d
```

This starts ParadeDB, the reranker, and the Next.js app. Wait for everything to be healthy:

```bash
docker compose ps   # all services should show "healthy" or "running"
```

The `schema.sql` is auto-applied on first start (documents table + HNSW + BM25 indexes).

### 3. Ingest data

```bash
docker compose --profile ingest run --rm ingestion
```

This will:
1. Load Confluence pages, Jira tickets, and plain-text docs from `data/`
2. Chunk them with structure-aware splitting, tagging each chunk with its team `space`
3. Embed each chunk with Gemini `gemini-embedding-001` (768 dims)
4. Insert into ParadeDB, skipping chunks already present (idempotent)

Re-running is safe — existing chunks are detected by content hash and skipped.

### 4. Open the app

[http://localhost:3000](http://localhost:3000)

---

**Local dev** (optional, if you want hot-reload for the frontend):

```bash
cd app && npm install && npm run dev
```

Set `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ragdb` and `RERANKER_URL=http://localhost:8000` in `app/.env.local`.

## Architecture

```
Browser
  │
  └─► Next.js App (port 3000)
        │
        ├─► / (home)               — team directory, links to each team page
        ├─► /cicd                  — CI/CD team, space=CI-CD
        ├─► /infra                 — Infrastructure team, space=INFRA
        └─► /eng-env               — Eng Environment team, space=ENG-ENV
              │
              └─► POST /api/chat?space=<SPACE>
                    1. Rewrite query (gemini-2.5-flash)
                    2. Embed query (gemini-embedding-001, 768 dims)
                    3. Hybrid search: BM25 (pg_search) + vector (pgvector) with RRF
                       └─ filtered to the team's space (B-tree index on `space` column)
                    4. Rerank top-30 → top-6 (cross-encoder sidecar)
                    5. Score threshold filter (< 0.3 → "I don't have info")
                    6. Generate answer (Gemini Flash, context-grounded)

        ├─► ParadeDB / PostgreSQL (port 5432)
        │     - pgvector: HNSW index on embedding column (768 dims, cosine)
        │     - pg_search: BM25 index on title + content (en_stem tokenizer)
        │     - B-tree index on `space` column for team-scoped retrieval
        │
        └─► Reranker Sidecar (port 8000)
              - FastAPI + sentence-transformers
              - POST /rerank: cross-encoder scoring
```

## Team Pages

Each team page is independently scoped — queries only retrieve documents tagged with that team's space. Adding a new team requires editing one file.

| Route | Team | Space | Description |
|-------|------|-------|-------------|
| `/cicd` | CI/CD | `CI-CD` | Pipelines, builds, deployments, release processes |
| `/infra` | Infrastructure | `INFRA` | Kubernetes, networking, cloud resources, monitoring |
| `/eng-env` | Eng Environment | `ENG-ENV` | Local dev setup, tooling, onboarding, access |

### Adding a new team

1. Edit `app/lib/teams.ts` — add an entry to the `TEAMS` array with `slug`, `label`, `description`, `space`, and `exampleQuestions`
2. Tag your data with the new `space` value in `data/confluence/pages.json`, `data/jira/tickets.json`, or add docs to `data/docs/` with the space prefix
3. Re-run ingestion: `docker compose --profile ingest run --rm ingestion`

That's it. The new route (`/<slug>`), sidebar link, and scoped retrieval are all automatic.

## Data Sources

| Source | Location | Spaces |
|--------|----------|--------|
| Confluence pages | `data/confluence/pages.json` | CI-CD, INFRA, ENG-ENV |
| Jira tickets | `data/jira/tickets.json` | CI-CD, INFRA, ENG-ENV |
| Internal docs | `data/docs/*.txt` | CI-CD, INFRA, ENG-ENV |

Space tagging for docs is automatic: `ingest.py` infers the space from the filename prefix (`cicd-*` → `CI-CD`, `infra-*` → `INFRA`, `eng-env-*` → `ENG-ENV`). Override with the `DOC_SPACE_MAP` dict in `ingest.py`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | (required) | Google Gemini API key |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/ragdb` | PostgreSQL connection string |
| `RERANKER_URL` | `http://localhost:8000` | Reranker sidecar base URL |

## Project Structure

```
RAG_Chatbot/
├── docker-compose.yml
├── schema.sql                      # Table + index definitions (incl. space B-tree)
├── data/
│   ├── confluence/pages.json       # Confluence pages with space field
│   ├── jira/tickets.json           # Jira tickets with space field
│   └── docs/*.txt                  # Internal docs (filename prefix → space)
├── ingestion/
│   ├── ingest.py                   # Main pipeline: DOC_SPACE_MAP + _infer_doc_space()
│   └── chunker.py                  # Structure-aware chunking, preserves space field
├── reranker/
│   └── main.py                     # FastAPI cross-encoder service
└── app/
    ├── app/
    │   ├── (shell)/                # Layout shell (sidebar + nav)
    │   │   ├── layout.tsx
    │   │   ├── page.tsx            # Home: team directory
    │   │   └── [team]/page.tsx     # Dynamic team page
    │   └── api/chat/route.ts       # RAG pipeline, accepts ?space= param
    ├── components/
    │   ├── ChatUI.tsx              # Chat interface component
    │   └── Sidebar.tsx             # Persistent sidebar with active-state highlighting
    └── lib/
        ├── teams.ts                # Single source of truth for all team config
        └── db.ts                   # PostgreSQL client
```

## Notes

- The reranker is optional — if unreachable, the app falls back to the top-6 results by RRF score.
- Ingestion is idempotent: content is hashed (SHA-256 of normalised text) and duplicate chunks are skipped.
- The BM25 index uses the `en_stem` tokenizer for English language stemming.
- The HNSW index uses cosine distance (`vector_cosine_ops`) with m=16, ef_construction=64.
- Team isolation is enforced at the SQL level — the `space` filter is applied in the `WHERE` clause of both BM25 and vector searches.
