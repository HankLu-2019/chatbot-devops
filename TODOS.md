# TODOS

## Sprint 1 follow-up

### ~~Add truncation indicator to Jenkins log tool responses~~ ✓ Done
**Implemented in `lib/jenkins.ts:160-164`** — appends `[Note: log truncated to last {N} lines. Full log was {M} lines — earlier context may have been omitted.]` when trimming occurs.

---

## Sprint 2 prerequisites

### ~~Extract RAG pipeline from chat/route.ts into lib/rag.ts~~ ✓ Done
**What:** Extract `hybridSearch()`, `embedQuery()`, `rerank()`, and `rewriteQuery()` from `app/api/chat/route.ts` into `app/lib/rag.ts` as callable, exported functions.
**Why:** Sprint 2 requires exposing `search_knowledge_base` as a Gemini function tool in the Jenkins debug agent. Today the RAG logic is ~400 lines of procedural code inline in the chat route — it can't be called as a module. This extraction is Sprint 2's biggest prerequisite.
**How:** Move functions to lib/rag.ts, re-import in chat/route.ts, expose as tool executor in jenkins-tools.ts.
**Context:** `app/api/chat/route.ts` lines ~60-300 contain hybridSearch (SQL), embedQuery (Gemini REST), rerank (cross-encoder sidecar call), rewriteQuery (Gemini). All need type exports for DiagnosisResult compatibility.
**Depends on:** Sprint 1 complete
