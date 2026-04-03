# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A RAG (Retrieval-Augmented Generation) chatbot for Acme Engineering's internal knowledge base. It provides team-scoped Q&A over Confluence pages, Jira tickets, and internal docs using hybrid search (BM25 + vector) with cross-encoder reranking.

## Commands

### Frontend (Next.js, run from `app/`)

```bash
npm run dev        # Dev server with hot-reload at http://localhost:3000
npm run build      # Build standalone production bundle
npm run lint       # ESLint on TypeScript/React code
```

### docker-compose (run from repo root)

```bash
docker-compose up -d                                           # Start all services
docker-compose --profile ingest run --rm ingestion            # Run ingestion pipeline
docker-compose logs <paradedb|reranker|app>                   # View service logs
docker-compose ps                                              # Check health status
docker-compose down -v                                         # Stop + wipe DB volumes
```

### Local Development (without Docker for app)

```bash
# Start DB + reranker only via Docker
docker-compose up paradedb reranker

# Run app with hot-reload
cd app && npm run dev

# Run ingestion (one-time or on data changes)
cd ingestion && pip install -r requirements.txt && python ingest.py
```

## Architecture

### Services

| Service | Port | Tech |
|---------|------|------|
| Next.js app | 3000 | Next.js 15, TypeScript, Tailwind CSS 4 |
| ParadeDB | 5432 | PostgreSQL 17 + pgvector + pg_search (BM25) |
| Reranker | 8000 | FastAPI + `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Ingestion | — | Python 3.11, one-shot Docker container |

### RAG Request Flow (`app/app/api/chat/route.ts`)

1. Query rewriting — Gemini Flash converts multi-turn history to standalone query
2. Embedding — `gemini-embedding-001` produces 768-dim vector
3. Hybrid search — BM25 (`pg_search`) + vector (`pgvector`) fused with RRF, top-30 results
4. Reranking — cross-encoder sidecar scores top-30, returns top-6
5. Threshold filter — scores below 0.3 trigger "I don't have information" response
6. Generation — Gemini Flash generates answer streamed via SSE
7. Response — answer + source citations (URL + snippet)

All search is **space-scoped**: each team page passes `?space=<TEAM_SPACE>` to the API.

### Team Routing

Routes are statically generated from `app/lib/teams.ts`:

| Route | Space | Data |
|-------|-------|------|
| `/cicd` | `CI-CD` | CI/CD pipelines, deployments |
| `/infra` | `INFRA` | Kubernetes, networking |
| `/eng-env` | `ENG-ENV` | Dev setup, tooling |
| `/search` | all | Cross-team global search |

To add a team: add an entry to `TEAMS` in `app/lib/teams.ts` and tag data with the space value.

### Key Files

- `app/app/api/chat/route.ts` — Entire RAG pipeline (embed → search → rerank → generate → stream)
- `app/app/api/feedback/route.ts` — Thumbs up/down persistence to DB
- `app/components/ChatUI.tsx` — Chat interface (streaming, feedback, source peek)
- `app/components/Sidebar.tsx` — Persistent nav with team links
- `app/lib/teams.ts` — Team config; edit this to add/remove teams
- `app/lib/db.ts` — PostgreSQL connection pool (pg package)
- `ingestion/ingest.py` — Ingestion orchestrator (load → dedupe → embed → insert)
- `ingestion/chunker.py` — Structure-aware chunking per source type
- `reranker/main.py` — FastAPI endpoint: `POST /rerank`, `GET /health`
- `schema.sql` — DB schema (applied automatically on ParadeDB startup)

### Database Schema

Two tables: `documents` (content, embedding, space, source_url, content_hash) and `feedback` (message_id, thumbs direction, team). Ingestion is idempotent via `content_hash` deduplication.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Google Gemini API key — required for embeddings and generation |
| `DATABASE_URL` | PostgreSQL connection string (default: `postgresql://postgres:postgres@localhost:5432/ragdb`) |
| `RERANKER_URL` | Reranker service URL (default: `http://localhost:8000`) |

Set these in root `.env` (for docker-compose) and `app/.env.local` (for local dev).

## No Test Suite

There are no automated tests. QA is done manually using gstack (see `.claude/qa-reports/`). The `/cso` security audit findings are in `.claude/security-reports/`.

## Key Points
- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.