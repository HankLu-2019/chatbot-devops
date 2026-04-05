/**
 * RAG pipeline — shared search functions.
 *
 * Extracted from api/chat/route.ts so both the chat route and the
 * Jenkins debug agent can call the same hybrid search pipeline.
 *
 * Public surface:
 *   searchKnowledgeBase(query, spaces?) → KbResult[]   ← agent tool use
 *   embedQuery, hybridSearch, rerank, assembleByBudget ← chat route internals
 */

import pool from "@/lib/db";

const GEMINI_API_KEY = process.env.GEMINI_API_KEY!;
const EMBED_MODEL = "gemini-embedding-001";
const EMBED_DIM = 768;
const RERANKER_URL = process.env.RERANKER_URL || "http://localhost:8000";

/**
 * Alpha blend weight for hybrid search score fusion.
 * 0 = keyword-only (BM25), 1 = vector-only, 0.7 = favor semantic.
 * Replaces Reciprocal Rank Fusion — normalized scores give magnitude info RRF discards.
 */
export const SEARCH_ALPHA = 0.7;

/**
 * Time-decay rate applied per day of document age.
 * score *= exp(-DECAY_RATE * days_old)
 * At 0.003: ~50% penalty after 231 days. Stale KB pages rank lower automatically.
 */
export const DECAY_RATE_PER_DAY = 0.003;

/**
 * Token budget for context assembly (rough: 4 chars ≈ 1 token).
 * Replaces hard RERANK_THRESHOLD cutoff — adapts to actual content size.
 */
export const MAX_CONTEXT_TOKENS = 6_000;

/** Hard cap on chunks regardless of token budget. */
export const MAX_CONTEXT_CHUNKS = 8;

/** @deprecated Use assembleByBudget instead. */
export const RERANK_THRESHOLD = 0.3;

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface DbRow {
  id: number;
  title: string;
  content: string;
  url: string;
  source_type: string;
  space: string;
  /** Hybrid score (normalized alpha-blend + time-decay). Field kept as rrf_score for query compat. */
  rrf_score: number;
  updated_at: Date | null;
}

export interface RankedChunk {
  chunk_id: number;
  score: number;
  text: string;
}

/** Result shape returned to callers (agents, chat route). */
export interface KbResult {
  url: string;
  title: string;
  snippet: string;
  score: number;
  space: string;
}

// ---------------------------------------------------------------------------
// Step 1 — Embed query via Gemini REST API
// ---------------------------------------------------------------------------

export async function embedQuery(text: string): Promise<number[]> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${EMBED_MODEL}:embedContent?key=${GEMINI_API_KEY}`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: `models/${EMBED_MODEL}`,
      content: { parts: [{ text }] },
      outputDimensionality: EMBED_DIM,
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Gemini embed API error: ${response.status} ${err}`);
  }

  const data = await response.json();
  const embedding: number[] = data?.embedding?.values;

  if (!embedding || embedding.length !== EMBED_DIM) {
    throw new Error(
      `Unexpected embedding dimension: ${embedding?.length} (expected ${EMBED_DIM})`
    );
  }

  return embedding;
}

// ---------------------------------------------------------------------------
// Step 2 — Hybrid search: normalized alpha-blend + time-decay
//
// Scoring pipeline (per document):
//
//   BM25 candidates ──┐
//                     ├─► min-max normalize ──► alpha-blend ──► time-decay ──► rank
//   Vector candidates ─┘
//
//   hybrid_score = (1 - α) * bm25_norm + α * vec_norm
//   final_score  = hybrid_score * exp(-λ * days_old)
//
//   α = SEARCH_ALPHA (0.7 — favor semantic)
//   λ = DECAY_RATE_PER_DAY (0.003 — ~50% penalty at 231 days)
//
// Replaces Reciprocal Rank Fusion. Normalized scores carry magnitude
// information RRF discards (RRF only uses rank position).
// ---------------------------------------------------------------------------

// Shared SQL fragment for score fusion — used in both space-filtered and global queries.
// Alpha and decay rate are TypeScript constants (numbers), never user input — safe to interpolate.
function fusionSQL(spaceFilter: boolean): string {
  const whereSpace = spaceFilter ? "AND space = $3" : "";
  const fromSpace  = spaceFilter ? "WHERE space = $3" : "";

  return `
    WITH bm25_raw AS (
      SELECT id, paradedb.score(id) AS s
      FROM documents
      WHERE documents @@@ paradedb.parse($1) ${whereSpace}
      LIMIT 50
    ),
    bm25_norm AS (
      SELECT id,
        CASE WHEN MAX(s) OVER() = MIN(s) OVER() THEN 0.5
             ELSE (s - MIN(s) OVER()) / (MAX(s) OVER() - MIN(s) OVER())
        END AS score_n
      FROM bm25_raw
    ),
    vec_raw AS (
      SELECT id, 1 - (embedding <=> $2::vector) AS s
      FROM documents ${fromSpace}
      ORDER BY embedding <=> $2::vector
      LIMIT 50
    ),
    vec_norm AS (
      SELECT id,
        CASE WHEN MAX(s) OVER() = MIN(s) OVER() THEN 0.5
             ELSE (s - MIN(s) OVER()) / (MAX(s) OVER() - MIN(s) OVER())
        END AS score_n
      FROM vec_raw
    ),
    fused AS (
      SELECT COALESCE(b.id, v.id) AS id,
             ${1 - SEARCH_ALPHA} * COALESCE(b.score_n, 0) +
             ${SEARCH_ALPHA}     * COALESCE(v.score_n, 0) AS hybrid_score
      FROM bm25_norm b
      FULL JOIN vec_norm v ON b.id = v.id
    )
    SELECT d.id, d.title, d.content, d.url, d.source_type, d.space, d.updated_at,
           f.hybrid_score * EXP(
             ${-DECAY_RATE_PER_DAY} * GREATEST(0, COALESCE(
               EXTRACT(EPOCH FROM (NOW() - d.updated_at)) / 86400.0, 0
             ))
           ) AS rrf_score
    FROM fused f
    JOIN documents d ON d.id = f.id
    ORDER BY rrf_score DESC
    LIMIT 30
  `;
}

export async function hybridSearch(
  query: string,
  embedding: number[],
  space?: string
): Promise<DbRow[]> {
  const vectorLiteral = `[${embedding.join(",")}]`;
  const useSpaceFilter = typeof space === "string" && space.length > 0;

  const client = await pool.connect();
  try {
    const result = useSpaceFilter
      ? await client.query(fusionSQL(true),  [query, vectorLiteral, space])
      : await client.query(fusionSQL(false), [query, vectorLiteral]);
    return result.rows as DbRow[];
  } finally {
    client.release();
  }
}

// ---------------------------------------------------------------------------
// Step 3 — Reranker call (with RRF fallback)
// ---------------------------------------------------------------------------

export async function rerank(
  query: string,
  rows: DbRow[]
): Promise<{ rows: DbRow[]; scores: Map<number, number> }> {
  const chunks = rows.map((r) => ({ id: r.id, text: r.content }));
  const scores = new Map<number, number>();

  try {
    const response = await fetch(`${RERANKER_URL}/rerank`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, chunks }),
      signal: AbortSignal.timeout(3000),
    });

    if (!response.ok) {
      throw new Error(`Reranker returned ${response.status}`);
    }

    const data = await response.json();
    const results: RankedChunk[] = data.results;

    for (const r of results) {
      scores.set(r.chunk_id, r.score);
    }

    const rerankedRows = results
      .map((r) => rows.find((row) => row.id === r.chunk_id)!)
      .filter(Boolean);

    return { rows: rerankedRows, scores };
  } catch (_err) {
    console.warn("Reranker unavailable, falling back to RRF order");
    const fallbackRows = rows.slice(0, 6);
    for (const row of fallbackRows) {
      scores.set(row.id, 0);
    }
    return { rows: fallbackRows, scores };
  }
}

// ---------------------------------------------------------------------------
// Step 4 — Context assembly: token budget-driven, replaces hard threshold
//
// Instead of a fixed RERANK_THRESHOLD cutoff, greedily accumulate chunks by
// cross-encoder score until the token budget is exhausted. This adapts to
// actual content size and model context window rather than a magic number.
//
//   Input (sorted by cross-encoder score, highest first):
//     [chunk_A: 0.82, 1200 tok] → include (running: 1200)
//     [chunk_B: 0.74,  900 tok] → include (running: 2100)
//     [chunk_C: 0.61, 3200 tok] → include (running: 5300)
//     [chunk_D: 0.55,  900 tok] → STOP — would exceed MAX_CONTEXT_TOKENS
//
// Token estimate: length / 4 (rough approximation, safe for English/code).
// Hard floor: always returns at least 1 chunk if available (ignores budget).
// ---------------------------------------------------------------------------

export function assembleByBudget(
  rows: DbRow[],
  scores: Map<number, number>,
  maxTokens = MAX_CONTEXT_TOKENS,
  maxChunks = MAX_CONTEXT_CHUNKS
): DbRow[] {
  const hasCrossEncoderScores = [...scores.values()].some((s) => s !== 0);
  if (!hasCrossEncoderScores) {
    return rows.slice(0, maxChunks);
  }

  const sorted = [...rows].sort(
    (a, b) => (scores.get(b.id) ?? 0) - (scores.get(a.id) ?? 0)
  );

  const result: DbRow[] = [];
  let tokenCount = 0;

  for (const row of sorted) {
    const rowTokens = Math.ceil(row.content.length / 4);
    const wouldExceedBudget = tokenCount + rowTokens > maxTokens;

    // Always include the first chunk (floor), then respect budget.
    if (result.length > 0 && wouldExceedBudget) break;

    result.push(row);
    tokenCount += rowTokens;

    if (result.length >= maxChunks) break;
  }

  return result;
}

/** @deprecated Use assembleByBudget instead. Kept for external callers. */
export function filterByThreshold(
  rows: DbRow[],
  scores: Map<number, number>
): DbRow[] {
  return assembleByBudget(rows, scores);
}

// ---------------------------------------------------------------------------
// Snippet helper
// ---------------------------------------------------------------------------

export function makeSnippet(content: string): string {
  const raw = (content ?? "").slice(0, 220);
  if (raw.length < 220) return raw;
  const lastSpace = raw.lastIndexOf(" ", 200);
  return lastSpace > 0 ? raw.slice(0, lastSpace) : raw.slice(0, 200);
}

// ---------------------------------------------------------------------------
// searchKnowledgeBase — callable interface for agent tools
//
// Runs embed → hybrid search → rerank → threshold filter.
// spaces: optional list of space keys (e.g. ["CI-CD", "INFRA"]).
//         If a single space is provided it is used as a filter.
//         If empty/omitted, searches all spaces.
//         If multiple, searches all (cross-space filter is not supported in the
//         current schema — the single-space filter is the safe path).
// ---------------------------------------------------------------------------

export async function searchKnowledgeBase(
  query: string,
  spaces?: string[]
): Promise<KbResult[]> {
  const space =
    Array.isArray(spaces) && spaces.length === 1 ? spaces[0] : undefined;

  const embedding = await embedQuery(query);
  const rows = await hybridSearch(query, embedding, space);

  if (rows.length === 0) return [];

  const { rows: rerankedRows, scores } = await rerank(query, rows);
  const topRows = assembleByBudget(rerankedRows, scores, MAX_CONTEXT_TOKENS, 6);

  return topRows.map((row) => ({
    url: row.url,
    title: row.title,
    snippet: makeSnippet(row.content),
    score: scores.get(row.id) ?? row.rrf_score,
    space: row.space,
  }));
}
