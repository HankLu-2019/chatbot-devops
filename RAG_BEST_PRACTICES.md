# RAG Pipeline Best Practices

Stack: PostgreSQL (pgvector + pg_search) · BM25 · Reranker · Next.js frontend
Data sources: Confluence · Jira · Docs
Scale: ~200MB raw text (~50k–100k chunks)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [pg_search & BM25](#pg_search--bm25)
3. [Hybrid Search with RRF](#hybrid-search-with-rrf)
4. [Chunk Quality](#chunk-quality)
5. [Embedding Model](#embedding-model)
6. [Reranker](#reranker)
7. [Conversation Context & Query Rewriting](#conversation-context--query-rewriting)
8. [Full Pipeline](#full-pipeline)
9. [Priority Order](#priority-order)

---

## Architecture Overview

```
Query
  ├── embed (+ HyDE) ──────────→ pgvector search   (top 50)
  ├── tokenize ─────────────────→ pg_search BM25    (top 50)
  └── RRF merge ────────────────→ top 30 candidates
                                      ↓
                               Reranker → top 6
                                      ↓
                               LLM generation
                                      ↓
                           Answer + source citations
```

All retrieval (vector + BM25 + RRF) runs in a **single PostgreSQL query**.
No Elasticsearch. No external services. No sync pipelines.

---

## pg_search & BM25

### What it is

`pg_search` is a PostgreSQL extension by [ParadeDB](https://paradedb.com).
It brings real **BM25 scoring** natively into Postgres, built on Tantivy (Rust, same ideas as Lucene).

Standard `tsvector`/`tsquery` uses tf-idf without length normalization. `pg_search` gives you proper BM25.

### BM25 scoring formula

```
score(D, Q) = Σ IDF(qi) × f(qi,D) × (k1+1)
                          ─────────────────────────────────
                          f(qi,D) + k1 × (1 - b + b×|D|/avgdl)
```

- **IDF** — rare terms score higher
- **f(qi, D)** — term frequency in document
- **|D| / avgdl** — length normalization
- **k1=1.2, b=0.75** — default tuning params

### Setup

```bash
# Docker: both pgvector and pg_search pre-installed
docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres paradedb/paradedb:latest
```

```sql
CREATE EXTENSION pg_search;
CREATE EXTENSION vector;

CREATE TABLE documents (
  id          SERIAL PRIMARY KEY,
  content     TEXT,
  title       TEXT,
  source_type TEXT,        -- 'confluence' | 'jira' | 'jira_comment' | 'doc'
  space       TEXT,
  ticket_id   TEXT,
  status      TEXT,
  url         TEXT,
  updated_at  TIMESTAMPTZ,
  content_hash TEXT,       -- for deduplication
  parent_id   INT,         -- for hierarchical chunking
  embedding   vector(1536)
);

-- Vector index
CREATE INDEX ON documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- BM25 index
CALL paradedb.create_bm25(
  index_name  => 'documents_bm25',
  table_name  => 'documents',
  key_field   => 'id',
  text_fields => paradedb.field('title',   tokenizer => paradedb.tokenizer('en_stem'))
              || paradedb.field('content', tokenizer => paradedb.tokenizer('en_stem'))
);
```

### Query types

```sql
-- Basic BM25
SELECT id, title, paradedb.score(id)
FROM   documents.search('content:kubernetes deploy')
ORDER  BY paradedb.score(id) DESC LIMIT 50;

-- Fuzzy (handles typos)
FROM documents.search(
  query => paradedb.fuzzy_term(field => 'content', value => 'kuberntes', distance => 1)
)

-- Phrase search
FROM documents.search('content:"out of memory error"')

-- Boolean
FROM documents.search(
  query => paradedb.boolean(
    must     => ARRAY[paradedb.term(field => 'content', value => 'kubernetes')],
    should   => ARRAY[paradedb.term(field => 'title',   value => 'deploy')],
    must_not => ARRAY[paradedb.term(field => 'content', value => 'deprecated')]
  )
)

-- Pre-filter by metadata (runs inside the index, very fast)
FROM documents.search(
  query  => paradedb.term(field => 'content', value => 'onboarding'),
  filter => paradedb.term(field => 'source_type', value => 'confluence')
          AND paradedb.term(field => 'space', value => 'engineering')
)
```

### pg_search vs alternatives

| | `tsvector` (built-in) | Elasticsearch | `pg_search` |
|---|---|---|---|
| Scoring | tf-idf | BM25 | BM25 |
| Setup | zero | separate cluster | extension only |
| Sync needed | no | yes | no |
| Hybrid with pgvector | manual | no | single SQL query |
| Fuzzy search | limited | yes | yes |
| Operational cost | zero | high | zero |

> **Limit:** not distributed. Fine up to ~50M documents on a single Postgres instance.
> At 200MB (~100k chunks) this is far more than sufficient.

---

## Hybrid Search with RRF

Reciprocal Rank Fusion (RRF) merges BM25 and vector rankings without needing to normalize scores.

```
RRF score = 1/(k + bm25_rank) + 1/(k + vector_rank)    k=60 (standard)
```

```sql
WITH bm25_results AS (
  SELECT id,
         paradedb.score(id) AS bm25_score,
         ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS bm25_rank
  FROM   documents.search('content:kubernetes deployment error')
  LIMIT  50
),
vector_results AS (
  SELECT id,
         1 - (embedding <=> $1::vector) AS vec_score,
         ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS vec_rank
  FROM   documents
  ORDER  BY embedding <=> $1::vector
  LIMIT  50
),
rrf AS (
  SELECT
    COALESCE(b.id, v.id) AS id,
    COALESCE(1.0 / (60 + b.bm25_rank), 0) +
    COALESCE(1.0 / (60 + v.vec_rank),  0) AS rrf_score
  FROM      bm25_results b
  FULL JOIN vector_results v ON b.id = v.id
)
SELECT d.id, d.title, d.content, d.url, d.source_type, r.rrf_score
FROM   rrf r
JOIN   documents d ON d.id = r.id
ORDER  BY r.rrf_score DESC
LIMIT  30;  -- feed top 30 into reranker
```

---

## Chunk Quality

> **Most important lever.** Bad chunks cannot be rescued by any downstream component.

### The wrong way

```python
# ❌ Fixed-size chunking: splits mid-sentence, loses context
chunks = [text[i:i+500] for i in range(0, len(text), 500)]
```

### Confluence pages — structure-aware chunking

```python
from bs4 import BeautifulSoup

def chunk_confluence(page):
    soup = BeautifulSoup(page.body, 'html.parser')
    chunks = []
    current_section = {"heading": page.title, "content": []}

    for element in soup.find_all(['h1','h2','h3','p','li','code']):
        if element.name in ['h1','h2','h3']:
            if current_section["content"]:
                chunks.append(build_chunk(page, current_section))
            current_section = {"heading": element.get_text(), "content": []}
        else:
            current_section["content"].append(element.get_text())

    if current_section["content"]:
        chunks.append(build_chunk(page, current_section))
    return chunks

def build_chunk(page, section):
    # Prepend title + heading → chunk is self-contained when retrieved alone
    text = f"{page.title} > {section['heading']}\n\n"
    text += "\n".join(section["content"])
    return {
        "content": text,
        "title": page.title,
        "heading": section["heading"],
        "url": page.url,
        "source_type": "confluence",
        "space": page.space
    }
```

**Key rule:** prepend `title > heading` to every chunk so it's self-contained when retrieved.

### Jira tickets — fields separately

```python
def chunk_jira(ticket):
    chunks = []

    # Summary + description = core meaning
    if ticket.description:
        chunks.append({
            "content": f"{ticket.summary}\n\n{ticket.description}",
            "title": ticket.summary,
            "source_type": "jira",
            "ticket_id": ticket.key,
            "ticket_type": ticket.issue_type,
            "status": ticket.status,
            "url": ticket.url
        })

    # Each comment separately — comments often contain the fix
    for comment in ticket.comments:
        chunks.append({
            "content": f"Comment on [{ticket.key}] {ticket.summary}:\n\n{comment.body}",
            "title": ticket.summary,
            "source_type": "jira_comment",
            "ticket_id": ticket.key,
            "author": comment.author,
            "url": ticket.url
        })

    return chunks
```

### Hierarchical chunking (best quality)

Store two levels: small children for precision retrieval, large parents for LLM context.

```python
def hierarchical_chunk(page):
    parents = split_by_section(page)      # ~1000 tokens each

    for parent in parents:
        parent_id = save_to_db(parent)
        sub_chunks = split_by_paragraph(parent.content)  # ~200 tokens each
        for child in sub_chunks:
            child["parent_id"] = parent_id
            save_to_db(child)

# At query time: retrieve children, send parents to LLM
child_chunks = vector_search(query, limit=5)
parent_ids   = [c.parent_id for c in child_chunks]
context      = fetch_parents(parent_ids)   # richer context for generation
```

### Deduplication

```python
import hashlib

def get_or_create_embedding(chunk, db, embed_fn):
    content_hash = hashlib.sha256(chunk['embedding_input'].encode()).hexdigest()
    existing = db.query(
        "SELECT embedding FROM documents WHERE content_hash = $1", content_hash
    )
    if existing:
        return existing.embedding          # skip API call
    return embed_fn(chunk['embedding_input'])
```

---

## Embedding Model

### Model comparison

| Model | Dims | Quality | Cost | Deployment |
|-------|------|---------|------|------------|
| `text-embedding-3-small` | 1536 | good | $0.02/1M tokens | OpenAI API |
| `text-embedding-3-large` | 3072 | best OpenAI | $0.13/1M tokens | OpenAI API |
| `BGE-large-en-v1.5` | 1024 | near large | free | local |
| `BGE-m3` | 1024 | multilingual | free | local |
| `nomic-embed-text` | 768 | good | free | local, fast |

**Recommendation:** `text-embedding-3-small` for most cases. The jump to `large` rarely justifies 6x cost at 200MB scale.

### Enrich what you embed

```python
def prepare_for_embedding(chunk):
    # Embed enriched text, store original for display
    return f"""
Title: {chunk['title']}
Section: {chunk.get('heading', '')}
Source: {chunk['source_type']} | {chunk.get('space', chunk.get('ticket_id', ''))}

{chunk['content']}
    """.strip()

chunk['embedding_input'] = prepare_for_embedding(chunk)
chunk['display_content'] = chunk['content']   # shown to user
```

### HyDE — biggest free quality boost

Short queries (5–15 words) vs long chunks (200–500 words) = embedding mismatch.
Fix: ask LLM to write a hypothetical answer, embed *that* instead.

```python
async def embed_query_with_hyde(query: str, llm) -> list[float]:
    hypothetical = await llm.complete(
        f"Write a short passage that would answer this question:\n{query}"
    )
    return await embed(hypothetical)
```

Consistently improves recall by **10–20%** with zero infra changes.

---

## Reranker

### Why it matters

```
Query: "how do I fix OOM kill in kubernetes pod"

Vector search #1:  "Kubernetes memory management overview"  ← topically similar
Reranker #1:       "Set memory limits to prevent OOMKilled" ← actually answers it
```

### Model options

```python
# Option A: Local cross-encoder (free, good, runs on CPU)
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank(query, chunks, top_k=8):
    pairs  = [(query, c['content']) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [c for c, _ in ranked[:top_k]]
```

```python
# Option B: BGE reranker (free, strongest open-source)
reranker = CrossEncoder('BAAI/bge-reranker-large')
```

```python
# Option C: Cohere Rerank API (best quality, paid)
import cohere
co = cohere.Client(api_key)

def rerank(query, chunks, top_k=8):
    results = co.rerank(
        query=query,
        documents=[c['content'] for c in chunks],
        top_n=top_k,
        model='rerank-english-v3.0'
    )
    return [chunks[r.index] for r in results.results]
```

**Start with** `cross-encoder/ms-marco-MiniLM-L-6-v2`. Upgrade to Cohere or BGE-large if quality is lacking.

### Candidate window sizing

```python
retrieval_k = 30   # fetch from hybrid search
rerank_top_k = 6   # reranker selects best for LLM

# Too few → reranker can't rescue bad retrieval
# Too many → slow, diminishing returns
```

### Score threshold — prevent hallucination

```python
def rerank_with_threshold(query, chunks, threshold=0.3):
    scores = reranker.predict([(query, c['content']) for c in chunks])
    good   = [c for c, s in zip(chunks, scores) if s > threshold]

    if not good:
        return None   # signal "no relevant info found"
    return good[:6]
```

If nothing scores above threshold → return "I don't have information about this" rather than hallucinating.

---

## Conversation Context & Query Rewriting

> **Required for chatbots.** Every query arrives with history — ignoring it breaks multi-turn conversations.

### The problem

```
Turn 1: "How do I deploy to production?"
Turn 2: "What about rollbacks?"   ← standalone search finds nothing useful
```

"What about rollbacks?" has no meaning without turn 1. Embedding it directly retrieves garbage.

### Solution: rewrite before embedding

Before HyDE, pass the raw query + recent history to the LLM and ask it to produce a self-contained search query. This runs in parallel with or replaces HyDE.

```python
REWRITE_PROMPT = """You are rewriting a chat message into a standalone search query.
Given the conversation history and the latest message, write a single search query
that captures the full intent. Output only the query, nothing else.

History:
{history}

Latest message: {query}
Standalone query:"""

async def rewrite_query(query: str, history: list[dict]) -> str:
    if not history:
        return query   # first turn — no rewriting needed

    # Only use last 3 turns to keep context tight
    recent = history[-3:]
    formatted = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}" for m in recent
    )
    rewritten = await llm.complete(
        REWRITE_PROMPT.format(history=formatted, query=query),
        max_tokens=100   # short output — just a query
    )
    return rewritten.strip()
```

### Where it fits in the pipeline

```
User message
    ↓
rewrite_query(message, history)   ← NEW: runs first
    ↓
embed_query_with_hyde(rewritten)
    ↓
hybrid_search(...)
    ...
```

### What to include in history

- Last **3 turns** (user + assistant pairs) is usually enough — more adds noise
- Include assistant answers, not just user messages — the answer establishes what was already covered
- Strip citations and source blocks from assistant turns before passing to rewriter

### Storing conversation history

```python
# Minimal in-memory structure per session
history = [
    {"role": "user",      "content": "How do I deploy to production?"},
    {"role": "assistant", "content": "You deploy via the CI pipeline..."},
    {"role": "user",      "content": "What about rollbacks?"},
]

# After generating an answer, append before responding:
history.append({"role": "assistant", "content": answer})
```

For persistent sessions (page reload, multi-device), store history in a `sessions` table keyed by session ID and load the last N turns on each request.

---

## Full Pipeline

```python
async def rag_query(query: str, filters: dict = None):
    # 1. Embed query with HyDE
    query_embedding = await embed_query_with_hyde(query, llm)

    # 2. Hybrid search → RRF merge → top 30
    candidates = await hybrid_search(
        query=query,
        embedding=query_embedding,
        filters=filters,        # e.g. {"source_type": "confluence"}
        limit=30
    )

    # 3. Rerank → top 6, with hallucination guard
    reranked = rerank_with_threshold(query, candidates, threshold=0.3)
    if not reranked:
        return {"answer": "I don't have information about this.", "sources": []}

    # 4. Fetch parent chunks for richer LLM context (hierarchical)
    context = fetch_parent_chunks(reranked)

    # 5. Generate with citations
    return await generate_with_citations(query, context)
```

### Storage sizing at 200MB

| Component | Size |
|-----------|------|
| Raw text | 200MB |
| After chunking (~100k chunks) | ~200MB |
| BM25 index | ~400–600MB |
| pgvector (1536-dim × 100k) | ~600MB |
| **Total Postgres storage** | **~1.5–2GB** |

A `$20/month` Postgres instance handles this with room to spare.

---

## Priority Order

Do these in order — each one builds on the previous.

| # | Action | Why |
|---|--------|-----|
| 1 | **Fix chunking** (structure-aware for Confluence/Jira) | Bad chunks can't be rescued downstream |
| 2 | **Add metadata to every chunk** (source, space, ticket_id) | Enables filtering before search |
| 3 | **Implement HyDE** on query embedding | +10–20% recall, zero infra cost |
| 4 | **Add score threshold** in reranker | Stops hallucination at the gate |
| 5 | **Hierarchical chunking** (parent/child) | Best retrieval quality |
| 6 | **Tune reranker model** (BGE-large or Cohere) | Only after 1–5 are solid |
| 7 | **Add RAG evaluation** (Ragas / LLM-as-judge) | Know what's actually broken |

### Evaluation metrics to track

- **Retrieval recall** — are the right chunks being fetched?
- **Answer faithfulness** — is the answer grounded in retrieved context?
- **Answer relevance** — does the answer address the question?

Tools: [Ragas](https://docs.ragas.io), [ARES](https://github.com/stanford-futuredata/ARES), or LLM-as-judge with GPT-4o.

---

## Next.js Frontend Checklist

- [ ] Use **Vercel AI SDK** `useChat` hook — handles streaming, loading, errors
- [ ] Show **sources panel** alongside every answer — users need to verify
- [ ] Add **👍 / 👎 feedback** per answer — cheapest eval signal available
- [ ] Show **suggested questions** on empty state
- [ ] Scope filter UI — let users narrow to Confluence / Jira / Docs
