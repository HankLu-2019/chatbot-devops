import { NextRequest, NextResponse } from "next/server";
import { TEAMS } from "@/lib/teams";
import { genai } from "@/lib/gemini";
import {
  DbRow,
  embedQuery,
  hybridSearch,
  rerank,
  assembleByBudget,
  makeSnippet,
} from "@/lib/rag";

// Map space values (e.g. "CI-CD") to human-readable team labels (e.g. "CI/CD")
const SPACE_LABEL_MAP = new Map(TEAMS.map((t) => [t.space, t.label]));

// ---------------------------------------------------------------------------
// Types (chat-specific)
// ---------------------------------------------------------------------------
interface Message {
  role: "user" | "assistant";
  content: string;
}

interface RequestBody {
  message: string;
  history?: Message[];
  space?: string;
  include_contexts?: boolean;
}

interface Source {
  title: string;
  url: string;
  source_type: string;
  snippet: string;
}

// ---------------------------------------------------------------------------
// Step 1 — Query rewriting (chat-specific: uses conversation history)
// ---------------------------------------------------------------------------
async function rewriteQuery(
  message: string,
  history: Message[],
): Promise<string> {
  if (!history || history.length === 0) {
    return message;
  }

  const recentHistory = history.slice(-6);
  const historyText = recentHistory
    .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
    .join("\n");

  const prompt = `Given the following conversation history, rewrite the last user message as a standalone, self-contained search query. Output ONLY the rewritten query — no explanation, no quotes.

Conversation history:
${historyText}

Last user message: ${message}

Standalone search query:`;

  const response = await openai.chat.completions.create({
    model: CHAT_MODEL,
    messages: [{ role: "user", content: prompt }],
    temperature: 0,
  });
  const rewritten = response.choices[0].message.content?.trim();
  return rewritten || message;
}

// ---------------------------------------------------------------------------
// Step 6 helpers — build chat session
// ---------------------------------------------------------------------------
function buildChatSession(
  contextRows: DbRow[],
  history: Message[],
  isGlobal: boolean,
) {
  const contextText = contextRows
    .map((r, i) => {
      const teamLabel = SPACE_LABEL_MAP.get(r.space) ?? r.space;
      const teamPrefix = isGlobal && teamLabel ? `[Team: ${teamLabel}] ` : "";
      return `[${i + 1}] ${teamPrefix}Source: ${r.title} (${r.url})\n${r.content}`;
    })
    .join("\n\n---\n\n");

  const attributionInstruction = isGlobal
    ? "\nFor each source you cite, name the owning team explicitly in your answer (e.g., 'according to the CI/CD team\u2019s pipeline guide\u2026')."
    : "";

  const systemPrompt = `You are an internal knowledge assistant for Acme Engineering.
Answer based ONLY on the provided context. Cite the source URL for every claim.
If you cannot answer from the context, say so clearly.${attributionInstruction}

Context:
${contextText}`;

  const model = genai.getGenerativeModel({
    model: "gemini-2.5-flash",
    systemInstruction: systemPrompt,
  });

  const historyForGemini = (history ?? []).map((m) => ({
    role: m.role === "user" ? "user" : "model",
    parts: [{ text: m.content }],
  }));

  return model.startChat({ history: historyForGemini });
}

// ---------------------------------------------------------------------------
// Step 6a — Generate answer (non-streaming)
// ---------------------------------------------------------------------------
async function generateAnswer(
  query: string,
  contextRows: DbRow[],
  history: Message[],
  isGlobal = false,
): Promise<string> {
  const chat = buildChatSession(contextRows, history, isGlobal);
  const result = await chat.sendMessage(query);
  return result.response.text();
}

// ---------------------------------------------------------------------------
// Step 6b — Generate answer (streaming)
// ---------------------------------------------------------------------------
async function* generateAnswerStream(
  query: string,
  contextRows: DbRow[],
  history: Message[],
  isGlobal = false,
): AsyncGenerator<string> {
  const chat = buildChatSession(contextRows, history, isGlobal);
  const result = await chat.sendMessageStream(query);
  for await (const chunk of result.stream) {
    const text = chunk.text();
    if (text) yield text;
  }
}

// ---------------------------------------------------------------------------
// Source builder helper
// ---------------------------------------------------------------------------
function buildSources(topRows: DbRow[]): Source[] {
  const seenUrls = new Set<string>();
  const sources: Source[] = [];
  for (const row of topRows) {
    if (row.url && !seenUrls.has(row.url)) {
      seenUrls.add(row.url);
      sources.push({
        title: row.title,
        url: row.url,
        source_type: row.source_type,
        snippet: makeSnippet(row.content),
      });
    }
  }
  return sources;
}

// ---------------------------------------------------------------------------
// SSE encoder helper
// ---------------------------------------------------------------------------
const enc = new TextEncoder();
function sseEvent(data: object): Uint8Array {
  return enc.encode(`data: ${JSON.stringify(data)}\n\n`);
}

// ---------------------------------------------------------------------------
// Shared pipeline (steps 1–5)
// ---------------------------------------------------------------------------
async function runPipeline(
  message: string,
  history: Message[],
  space: string | undefined,
): Promise<{ topRows: DbRow[]; isGlobal: boolean } | { noInfo: true }> {
  const rewrittenQuery = await rewriteQuery(message, history);
  const embedding = await embedQuery(rewrittenQuery);
  const searchRows = await hybridSearch(rewrittenQuery, embedding, space);

  if (searchRows.length === 0) return { noInfo: true };

  const { rows: rerankedRows, scores } = await rerank(
    rewrittenQuery,
    searchRows,
  );
  const topRows = assembleByBudget(rerankedRows, scores);

  if (topRows.length === 0) return { noInfo: true };

  const isGlobal = typeof space !== "string" || space.length === 0;
  return { topRows, isGlobal };
}

// ---------------------------------------------------------------------------
// POST /api/chat
// ---------------------------------------------------------------------------
export async function POST(req: NextRequest): Promise<Response> {
  let body: RequestBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { message, history = [], space, include_contexts = false } = body;

  if (!message || typeof message !== "string" || !message.trim()) {
    return NextResponse.json({ error: "message is required" }, { status: 400 });
  }

  const wantsSSE = req.headers.get("Accept") === "text/event-stream";

  // ---------------------------------------------------------------------------
  // SSE streaming path
  // ---------------------------------------------------------------------------
  if (wantsSSE) {
    const stream = new ReadableStream({
      async start(controller) {
        try {
          const result = await runPipeline(message, history, space);

          if ("noInfo" in result) {
            controller.enqueue(
              sseEvent({
                type: "done",
                answer: "I don't have information about this.",
                sources: [],
              }),
            );
            controller.close();
            return;
          }

          const { topRows, isGlobal } = result;
          const sources = buildSources(topRows);

          for await (const text of generateAnswerStream(
            message,
            topRows,
            history,
            isGlobal,
          )) {
            controller.enqueue(sseEvent({ type: "token", text }));
          }

          controller.enqueue(sseEvent({ type: "done", sources }));
          controller.close();
        } catch (err) {
          console.error("SSE stream error:", err);
          try {
            controller.enqueue(
              sseEvent({ type: "error", message: String(err) }),
            );
            controller.close();
          } catch {
            // controller may already be closed
          }
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Non-streaming path (unchanged)
  // ---------------------------------------------------------------------------
  try {
    const result = await runPipeline(message, history, space);

    if ("noInfo" in result) {
      return NextResponse.json({
        answer: "I don't have information about this.",
        sources: [],
      });
    }

    const { topRows, isGlobal } = result;
    const answer = await generateAnswer(message, topRows, history, isGlobal);
    const sources = buildSources(topRows);

    const responseBody: Record<string, unknown> = { answer, sources };
    if (include_contexts) {
      responseBody.contexts = topRows.map((r) => r.content);
    }
    return NextResponse.json(responseBody);
  } catch (err) {
    console.error("Chat API error:", err);
    return NextResponse.json(
      { error: "Internal server error", detail: String(err) },
      { status: 500 },
    );
  }
}
