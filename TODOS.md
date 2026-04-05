# TODOS

## Sprint 1 follow-up

### ~~Add truncation indicator to Jenkins log tool responses~~ ✓ Done

**Implemented in `lib/jenkins.ts:160-164`** — appends `[Note: log truncated to last {N} lines. Full log was {M} lines — earlier context may have been omitted.]` when trimming occurs.

---

## Sprint 2 prerequisites

### ~~Onyx-inspired RAG improvements (scoring + context assembly)~~ ✓ Done

**Implemented in `lib/rag.ts`** — normalized alpha-blend scoring, time-decay on `updated_at`, token budget-driven `assembleByBudget` replacing `filterByThreshold`.

---

## Future: Onyx-inspired improvements (deferred)

### Token-aware chunking in ingestion

**What:** Subtract metadata/title token cost upfront before allocating content space in `ingestion/chunker.py`. Add a token budget check to avoid chunks silently exceeding `text-embedding-004`'s 2048-token input limit.
**Why:** Current chunker splits on structure (headers, paragraphs) but doesn't guard against embedding model window overflow. Large sections may be silently truncated by the embedding API.
**How:** Add `count_tokens(text)` estimate (len/4), enforce `MAX_CHUNK_TOKENS = 1800` per chunk, recursively split oversized chunks.
**Depends on:** Nothing — can be done any time before next ingestion run.

---

## Before connecting real Confluence/Jira APIs

### Confluence server-side date filtering

**What:** Pass `modified_since` as a server-side query param in `scraper/confluence_client.py` instead of fetching all pages and filtering client-side.
**Why:** Current implementation fetches ALL pages per parent_id every 6h run, then throws away pages older than 24h. For large spaces (500+ pages/parent), this is O(all pages) per incremental run instead of O(recent pages). Will be a bottleneck before real APIs are connected.
**How:** Real Confluence REST API supports `lastModified` param on `/wiki/rest/api/content`. Pass it when `modified_since` is set; keep client-side filter as a fallback for APIs that don't support it.
**Depends on:** Nothing. Safe to do any time before real Confluence is connected.

---

## Sprint 2 prerequisites

### ~~Extract RAG pipeline from chat/route.ts into lib/rag.ts~~ ✓ Done

**What:** Extract `hybridSearch()`, `embedQuery()`, `rerank()`, and `rewriteQuery()` from `app/api/chat/route.ts` into `app/lib/rag.ts` as callable, exported functions.
**Why:** Sprint 2 requires exposing `search_knowledge_base` as a Gemini function tool in the Jenkins debug agent. Today the RAG logic is ~400 lines of procedural code inline in the chat route — it can't be called as a module. This extraction is Sprint 2's biggest prerequisite.
**How:** Move functions to lib/rag.ts, re-import in chat/route.ts, expose as tool executor in jenkins-tools.ts.
**Context:** `app/api/chat/route.ts` lines ~60-300 contain hybridSearch (SQL), embedQuery (Gemini REST), rerank (cross-encoder sidecar call), rewriteQuery (Gemini). All need type exports for DiagnosisResult compatibility.
**Depends on:** Sprint 1 complete
