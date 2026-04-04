# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A RAG (Retrieval-Augmented Generation) chatbot for Acme Engineering's internal knowledge base. It provides team-scoped Q&A over Confluence pages, Jira tickets, and internal docs using hybrid search (BM25 + vector) with cross-encoder reranking.

## new feature, function implementation

always use skill to do it, from requirement discuss, plan, plan review, coding, review, qa, etc, make throughly check make sure all changes are fully filled, and make code commit at last, ask users need to push or not.

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

| Service      | Port | Tech                                                 |
| ------------ | ---- | ---------------------------------------------------- |
| Next.js app  | 3000 | Next.js 15, TypeScript, Tailwind CSS 4               |
| ParadeDB     | 5432 | PostgreSQL 17 + pgvector + pg_search (BM25)          |
| Reranker     | 8000 | FastAPI + `cross-encoder/ms-marco-MiniLM-L-6-v2`     |
| Mock Jenkins | 8080 | FastAPI mock CI/CD server                            |
| Mock APIs    | 8081 | FastAPI mock Confluence + Jira server                |
| Grafana      | 3001 | Grafana 11.6.0 feedback dashboard (anonymous viewer) |
| Ingestion    | —    | Python 3.11, one-shot Docker container               |
| Scraper      | —    | Python 3.11, runs every 6h in Docker (`--loop` mode) |

### RAG Request Flow (`app/app/api/chat/route.ts`)

1. Query rewriting — Gemini Flash converts multi-turn history to standalone query
2. Embedding — `gemini-embedding-001` produces 768-dim vector
3. Hybrid search — BM25 (`pg_search`) + vector (`pgvector`), min-max normalized and alpha-blended (`SEARCH_ALPHA=0.7`), with time-decay on `updated_at`; top-30 results
4. Reranking — cross-encoder sidecar scores top-30, returns top-N
5. Context assembly — token budget (6000 tok) greedily accumulates chunks by cross-encoder score; hard cap 8 chunks
6. Generation — Gemini Flash generates answer streamed via SSE
7. Response — answer + source citations (URL + snippet)

All search is **space-scoped**: each team page passes `?space=<TEAM_SPACE>` to the API.

### Team Routing

Routes are statically generated from `app/lib/teams.ts`:

| Route      | Space     | Data                         |
| ---------- | --------- | ---------------------------- |
| `/cicd`    | `CI-CD`   | CI/CD pipelines, deployments |
| `/infra`   | `INFRA`   | Kubernetes, networking       |
| `/eng-env` | `ENG-ENV` | Dev setup, tooling           |
| `/search`  | all       | Cross-team global search     |

To add a team: add an entry to `TEAMS` in `app/lib/teams.ts` and tag data with the space value.

### Key Files

- `app/app/api/chat/route.ts` — Chat pipeline (rewrite → embed → search → rerank → assemble → generate → stream)
- `app/lib/rag.ts` — Shared RAG functions: `hybridSearch` (alpha-blend + decay), `assembleByBudget`, `searchKnowledgeBase`
- `app/app/api/feedback/route.ts` — Thumbs up/down persistence to DB
- `app/components/ChatUI.tsx` — Chat interface (streaming, feedback, source peek)
- `app/components/Sidebar.tsx` — Persistent nav with team links
- `app/lib/teams.ts` — Team config; edit this to add/remove teams
- `app/lib/db.ts` — PostgreSQL connection pool (pg package)
- `ingestion/ingest.py` — Ingestion orchestrator (load → dedupe → embed → insert); scans `data/<SPACE>/confluence_*.json` and `jira_*.json`, deletes after commit
- `ingestion/chunker.py` — Structure-aware chunking per source type
- `reranker/main.py` — FastAPI endpoint: `POST /rerank`, `GET /health`
- `schema.sql` — DB schema (applied automatically on ParadeDB startup)
- `scraper/config.yml` — SSOT for teams: spaces, Confluence parent IDs, Jira project keys, scraper settings
- `scraper/scraper.py` — Scraper orchestrator: incremental (24h look-back) + gap check + backfill per team
- `scraper/state.py` — Atomic JSON state tracking `last_fetched`, `max_issue_number`, `backfill_cursor`
- `scraper/confluence_client.py` — Confluence REST client (parent-scoped, modified_since filter)
- `scraper/jira_client.py` — Jira REST client (JQL builder, gap detection, comment extraction)
- `mock-apis/server.py` — Combined Confluence + Jira FastAPI mock on port 8081
- `grafana/provisioning/` — Grafana datasource + dashboard provisioning (auto-loaded on start)

### Database Schema

Two tables: `documents` (content, embedding, space, source_url, content_hash) and `feedback` (message_id, thumbs direction, team). Ingestion is idempotent via `content_hash` deduplication.

### Data Scraping Pipeline

The scraper runs every 6h and writes per-team JSON files to `data/<SPACE>/`. Ingestion consumes and deletes them.

- **Incremental:** fetches pages/issues modified in last 24h per run
- **Gap check:** detects missed Jira tickets by comparing `state.max_issue_number` vs latest
- **Backfill:** new sources fetched in batches (`backfill_batch_size=50`/run) over multiple runs
- **Atomic writes:** `.tmp` → `.json` rename prevents ingestor from reading partial files
- **SSOT:** `scraper/config.yml` defines all teams; both scraper and ingestor read it

To add a team: add an entry to `scraper/config.yml` with `space`, `confluence.parent_ids`, and `jira.projects`.

## Environment Variables

| Variable         | Purpose                                                                                       |
| ---------------- | --------------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY` | Google Gemini API key — required for embeddings and generation                                |
| `DATABASE_URL`   | PostgreSQL connection string (default: `postgresql://postgres:postgres@localhost:5432/ragdb`) |
| `RERANKER_URL`   | Reranker service URL (default: `http://localhost:8000`)                                       |

Set these in root `.env` (for docker-compose) and `app/.env.local` (for local dev).

## Testing

- **Scraper unit tests:** `cd scraper && python test_scraper.py` (29 tests)
- **Scraper E2E QA:** start mock-apis on port 8082, run `python /tmp/qa_scraper.py`
- **App QA:** done manually using gstack (see `.claude/qa-reports/`)
- **Security audit:** findings in `.claude/security-reports/`

## Key Points

- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.
