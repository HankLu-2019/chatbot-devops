import { NextRequest, NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";
import pool from "@/lib/db";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const GEMINI_API_KEY = process.env.GEMINI_API_KEY!;
const EMBED_MODEL = "gemini-embedding-001";
const EMBED_DIM = 768;
const RERANKER_URL = process.env.RERANKER_URL || "http://localhost:8000";
const RERANK_THRESHOLD = 0.3;

const genai = new GoogleGenerativeAI(GEMINI_API_KEY);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Message {
  role: "user" | "assistant";
  content: string;
}

interface RequestBody {
  message: string;
  history?: Message[];
}

interface DbRow {
  id: number;
  title: string;
  content: string;
  url: string;
  source_type: string;
  rrf_score: number;
}

interface RankedChunk {
  chunk_id: number;
  score: number;
  text: string;
}

interface Source {
  title: string;
  url: string;
  source_type: string;
}

// ---------------------------------------------------------------------------
// Step 1 — Query rewriting
// ---------------------------------------------------------------------------
async function rewriteQuery(
  message: string,
  history: Message[]
): Promise<string> {
  if (!history || history.length === 0) {
    return message;
  }

  const recentHistory = history.slice(-6); // last 3 turns (user + assistant each)
  const historyText = recentHistory
    .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
    .join("\n");

  const prompt = `Given the following conversation history, rewrite the last user message as a standalone, self-contained search query. Output ONLY the rewritten query — no explanation, no quotes.

Conversation history:
${historyText}

Last user message: ${message}

Standalone search query:`;

  const model = genai.getGenerativeModel({ model: "gemini-2.5-flash" });
  const result = await model.generateContent(prompt);
  const rewritten = result.response.text().trim();
  return rewritten || message;
}

// ---------------------------------------------------------------------------
// Step 2 — Embed query via Gemini REST API
// ---------------------------------------------------------------------------
async function embedQuery(text: string): Promise<number[]> {
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
// Step 3 — Hybrid search with RRF (BM25 + vector)
// ---------------------------------------------------------------------------
async function hybridSearch(query: string, embedding: number[]): Promise<DbRow[]> {
  // Format the vector as a Postgres literal: '[0.1, 0.2, ...]'
  const vectorLiteral = `[${embedding.join(",")}]`;

  const sql = `
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
    SELECT d.id, d.title, d.content, d.url, d.source_type, r.rrf_score
    FROM rrf r
    JOIN documents d ON d.id = r.id
    ORDER BY r.rrf_score DESC
    LIMIT 30
  `;

  const client = await pool.connect();
  try {
    const result = await client.query(sql, [query, vectorLiteral]);
    return result.rows as DbRow[];
  } finally {
    client.release();
  }
}

// ---------------------------------------------------------------------------
// Step 4 — Reranker call (with RRF fallback)
// ---------------------------------------------------------------------------
async function rerank(
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
      // 3-second timeout
      signal: AbortSignal.timeout(3000),
    });

    if (!response.ok) {
      throw new Error(`Reranker returned ${response.status}`);
    }

    const data = await response.json();
    const results: RankedChunk[] = data.results;

    // Build score map and reorder rows by reranker rank
    for (const r of results) {
      scores.set(r.chunk_id, r.score);
    }

    const rerankedRows = results
      .map((r) => rows.find((row) => row.id === r.chunk_id)!)
      .filter(Boolean);

    return { rows: rerankedRows, scores };
  } catch (_err) {
    // Reranker unavailable — fall back to top 6 by RRF score
    console.warn("Reranker unavailable, falling back to RRF order");
    const fallbackRows = rows.slice(0, 6);
    for (const row of fallbackRows) {
      scores.set(row.id, 0); // no cross-encoder score available
    }
    return { rows: fallbackRows, scores };
  }
}

// ---------------------------------------------------------------------------
// Step 5 — Score threshold filter
// ---------------------------------------------------------------------------
function filterByThreshold(
  rows: DbRow[],
  scores: Map<number, number>
): DbRow[] {
  // Only apply threshold if we have real cross-encoder scores (not zeros from fallback)
  const hasCrossEncoderScores = [...scores.values()].some((s) => s !== 0);
  if (!hasCrossEncoderScores) {
    return rows.slice(0, 6);
  }
  return rows.filter((r) => (scores.get(r.id) ?? 0) >= RERANK_THRESHOLD).slice(0, 6);
}

// ---------------------------------------------------------------------------
// Step 6 — Generate answer with Gemini
// ---------------------------------------------------------------------------
async function generateAnswer(
  query: string,
  contextRows: DbRow[],
  history: Message[]
): Promise<string> {
  const contextText = contextRows
    .map(
      (r, i) =>
        `[${i + 1}] Source: ${r.title} (${r.url})\n${r.content}`
    )
    .join("\n\n---\n\n");

  const systemPrompt = `You are an internal knowledge assistant for Acme Engineering.
Answer based ONLY on the provided context. Cite the source URL for every claim.
If you cannot answer from the context, say so clearly.

Context:
${contextText}`;

  const model = genai.getGenerativeModel({
    model: "gemini-2.5-flash",
    systemInstruction: systemPrompt,
  });

  // Build chat history for multi-turn context
  const historyForGemini = (history ?? []).map((m) => ({
    role: m.role === "user" ? "user" : "model",
    parts: [{ text: m.content }],
  }));

  const chat = model.startChat({ history: historyForGemini });
  const result = await chat.sendMessage(query);
  return result.response.text();
}

// ---------------------------------------------------------------------------
// POST /api/chat
// ---------------------------------------------------------------------------
export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: RequestBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { message, history = [] } = body;

  if (!message || typeof message !== "string" || !message.trim()) {
    return NextResponse.json({ error: "message is required" }, { status: 400 });
  }

  try {
    // 1. Rewrite query for better retrieval (uses conversation context)
    const rewrittenQuery = await rewriteQuery(message, history);

    // 2. Embed the rewritten query
    const embedding = await embedQuery(rewrittenQuery);

    // 3. Hybrid search (BM25 + vector with RRF)
    const searchRows = await hybridSearch(rewrittenQuery, embedding);

    if (searchRows.length === 0) {
      return NextResponse.json({
        answer:
          "I don't have information about this.",
        sources: [],
      });
    }

    // 4. Rerank
    const { rows: rerankedRows, scores } = await rerank(rewrittenQuery, searchRows);

    // 5. Threshold filter
    const topRows = filterByThreshold(rerankedRows, scores);

    if (topRows.length === 0) {
      return NextResponse.json({
        answer:
          "I don't have information about this.",
        sources: [],
      });
    }

    // 6. Generate answer
    const answer = await generateAnswer(message, topRows, history);

    // Build deduplicated sources list
    const seenUrls = new Set<string>();
    const sources: Source[] = [];
    for (const row of topRows) {
      if (row.url && !seenUrls.has(row.url)) {
        seenUrls.add(row.url);
        sources.push({
          title: row.title,
          url: row.url,
          source_type: row.source_type,
        });
      }
    }

    return NextResponse.json({ answer, sources });
  } catch (err) {
    console.error("Chat API error:", err);
    return NextResponse.json(
      { error: "Internal server error", detail: String(err) },
      { status: 500 }
    );
  }
}
