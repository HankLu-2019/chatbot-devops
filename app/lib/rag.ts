/**
 * RAG pipeline — shared search functions.
 *
 * Extracted from api/chat/route.ts so both the chat route and the
 * Jenkins debug agent can call the same hybrid search pipeline.
 *
 * Public surface:
 *   searchKnowledgeBase(query, spaces?) → KbResult[]   ← agent tool use
 *   embedQuery, hybridSearch, rerank, filterByThreshold ← chat route internals
 */

import pool from "@/lib/db";

const GEMINI_API_KEY = process.env.GEMINI_API_KEY!;
const EMBED_MODEL = "gemini-embedding-001";
const EMBED_DIM = 768;
const RERANKER_URL = process.env.RERANKER_URL || "http://localhost:8000";
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
  rrf_score: number;
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
// Step 2 — Hybrid search with RRF (BM25 + vector)
// ---------------------------------------------------------------------------

export async function hybridSearch(
  query: string,
  embedding: number[],
  space?: string
): Promise<DbRow[]> {
  const vectorLiteral = `[${embedding.join(",")}]`;
  const useSpaceFilter = typeof space === "string" && space.length > 0;

  // space is always passed as a positional parameter ($3), never interpolated.
  const sqlWithSpace = `
    WITH bm25_results AS (
      SELECT id,
             paradedb.score(id) AS bm25_score,
             ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS bm25_rank
      FROM documents
      WHERE documents @@@ paradedb.parse($1)
        AND space = $3
      LIMIT 50
    ),
    vector_results AS (
      SELECT id,
             1 - (embedding <=> $2::vector) AS vec_score,
             ROW_NUMBER() OVER (ORDER BY embedding <=> $2::vector) AS vec_rank
      FROM documents
      WHERE space = $3
      ORDER BY embedding <=> $2::vector
      LIMIT 50
    ),
    rrf AS (
      SELECT COALESCE(b.id, v.id) AS id,
             COALESCE(1.0 / (60 + b.bm25_rank), 0) +
             COALESCE(1.0 / (60 + v.vec_rank), 0) AS rrf_score
      FROM bm25_results b
      FULL JOIN vector_results v ON b.id = v.id
    )
    SELECT d.id, d.title, d.content, d.url, d.source_type, d.space, r.rrf_score
    FROM rrf r
    JOIN documents d ON d.id = r.id
    ORDER BY r.rrf_score DESC
    LIMIT 30
  `;

  const sqlWithoutSpace = `
    WITH bm25_results AS (
      SELECT id,
             paradedb.score(id) AS bm25_score,
             ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS bm25_rank
      FROM documents
      WHERE documents @@@ paradedb.parse($1)
      LIMIT 50
    ),
    vector_results AS (
      SELECT id,
             1 - (embedding <=> $2::vector) AS vec_score,
             ROW_NUMBER() OVER (ORDER BY embedding <=> $2::vector) AS vec_rank
      FROM documents
      ORDER BY embedding <=> $2::vector
      LIMIT 50
    ),
    rrf AS (
      SELECT COALESCE(b.id, v.id) AS id,
             COALESCE(1.0 / (60 + b.bm25_rank), 0) +
             COALESCE(1.0 / (60 + v.vec_rank), 0) AS rrf_score
      FROM bm25_results b
      FULL JOIN vector_results v ON b.id = v.id
    )
    SELECT d.id, d.title, d.content, d.url, d.source_type, d.space, r.rrf_score
    FROM rrf r
    JOIN documents d ON d.id = r.id
    ORDER BY r.rrf_score DESC
    LIMIT 30
  `;

  const client = await pool.connect();
  try {
    const result = useSpaceFilter
      ? await client.query(sqlWithSpace, [query, vectorLiteral, space])
      : await client.query(sqlWithoutSpace, [query, vectorLiteral]);
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
// Step 4 — Score threshold filter
// ---------------------------------------------------------------------------

export function filterByThreshold(
  rows: DbRow[],
  scores: Map<number, number>
): DbRow[] {
  const hasCrossEncoderScores = [...scores.values()].some((s) => s !== 0);
  if (!hasCrossEncoderScores) {
    return rows.slice(0, 6);
  }
  return rows.filter((r) => (scores.get(r.id) ?? 0) >= RERANK_THRESHOLD).slice(0, 6);
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
  const topRows = filterByThreshold(rerankedRows, scores);

  return topRows.map((row) => ({
    url: row.url,
    title: row.title,
    snippet: makeSnippet(row.content),
    score: scores.get(row.id) ?? row.rrf_score,
    space: row.space,
  }));
}
