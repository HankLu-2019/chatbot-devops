"use client";

import { useState, useRef, useEffect, FormEvent } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Source {
  title: string;
  url: string;
  source_type: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  noInfo?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function generateId(): string {
  return Math.random().toString(36).slice(2, 10);
}

const NO_INFO_ANSWER = "I don't have information about this.";

function sourceTypeLabel(type: string): string {
  switch (type) {
    case "confluence":
      return "Confluence";
    case "jira":
      return "Jira";
    case "doc":
      return "Doc";
    default:
      return type;
  }
}

function sourceTypeBadgeColor(type: string): string {
  switch (type) {
    case "confluence":
      return "bg-blue-100 text-blue-700";
    case "jira":
      return "bg-purple-100 text-purple-700";
    case "doc":
      return "bg-green-100 text-green-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed shadow-sm">
        {content}
      </div>
    </div>
  );
}

function SourcesPanel({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <p className="text-xs font-medium text-gray-400 mb-2 uppercase tracking-wide">
        Sources
      </p>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, i) => (
          <a
            key={i}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 hover:border-indigo-300 hover:text-indigo-700 transition-colors"
          >
            <span
              className={`inline-block rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${sourceTypeBadgeColor(
                source.source_type
              )}`}
            >
              {sourceTypeLabel(source.source_type)}
            </span>
            <span className="truncate max-w-[200px]">{source.title}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function AssistantBubble({
  content,
  sources,
  noInfo,
}: {
  content: string;
  sources?: Source[];
  noInfo?: boolean;
}) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%]">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-xs select-none mt-0.5">
            A
          </div>
          <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 text-sm shadow-sm border border-gray-100 flex-1">
            {noInfo ? (
              <p className="text-gray-400 italic">{content}</p>
            ) : (
              <p className="text-gray-800 leading-relaxed whitespace-pre-wrap">
                {content}
              </p>
            )}
            {!noInfo && sources && sources.length > 0 && (
              <SourcesPanel sources={sources} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-xs select-none">
          A
        </div>
        <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100">
          <div className="flex gap-1.5 items-center h-4">
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
          </div>
        </div>
      </div>
    </div>
  );
}

const STARTER_QUESTIONS = [
  "How do I deploy to production?",
  "My pod is OOMKilled, what should I do?",
  "How do I rollback a bad deployment?",
  "Why am I getting 401 errors after token rotation?",
  "How do I check logs for a specific pod?",
];

// ---------------------------------------------------------------------------
// Main ChatUI component
// ---------------------------------------------------------------------------
export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Build history array for the API (exclude the in-progress assistant msg)
  function buildHistory(): { role: "user" | "assistant"; content: string }[] {
    return messages.map((m) => ({ role: m.role, content: m.content }));
  }

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;

    const userMsg: Message = {
      id: generateId(),
      role: "user",
      content: text.trim(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const history = buildHistory();
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text.trim(), history }),
      });

      if (!res.ok) {
        throw new Error(`API error ${res.status}`);
      }

      const data = await res.json();
      const answer: string = data.answer || "No answer returned.";
      const sources: Source[] = data.sources || [];
      const noInfo = answer.includes(NO_INFO_ANSWER);

      const assistantMsg: Message = {
        id: generateId(),
        role: "assistant",
        content: answer,
        sources,
        noInfo,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: Message = {
        id: generateId(),
        role: "assistant",
        content: `Sorry, something went wrong: ${String(err)}`,
        noInfo: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-6 pb-16">
            <div>
              <h2 className="text-2xl font-semibold text-gray-700 mb-2">
                How can I help?
              </h2>
              <p className="text-sm text-gray-400 max-w-sm">
                Ask anything about Acme's internal docs, runbooks, Confluence
                pages, or Jira tickets.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {STARTER_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50 transition-colors text-left shadow-sm"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserBubble key={msg.id} content={msg.content} />
          ) : (
            <AssistantBubble
              key={msg.id}
              content={msg.content}
              sources={msg.sources}
              noInfo={msg.noInfo}
            />
          )
        )}

        {loading && <TypingIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3">
        <form
          onSubmit={handleSubmit}
          className="flex gap-2 items-end max-w-3xl mx-auto"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about deployments, OOM errors, runbooks..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent transition-all leading-relaxed"
            style={{ maxHeight: "120px", overflowY: "auto" }}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex-shrink-0 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <svg
                className="w-4 h-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            ) : (
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
            )}
          </button>
        </form>
        <p className="text-center text-xs text-gray-400 mt-2">
          Press Enter to send &middot; Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
