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

function sourcePrefix(type: string): string {
  switch (type) {
    case "confluence": return "cf";
    case "jira":       return "jr";
    case "doc":        return "doc";
    default:           return type.slice(0, 3);
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function UserLine({ content }: { content: string }) {
  return (
    <div className="msg-enter" style={{ paddingLeft: "0" }}>
      <div style={{
        display: "flex",
        gap: "0.5rem",
        alignItems: "flex-start",
      }}>
        <span style={{ color: "var(--amber)", flexShrink: 0, fontFamily: "var(--mono)", fontSize: "13px", marginTop: "1px" }}>
          &gt;
        </span>
        <span style={{
          color: "var(--amber)",
          fontFamily: "var(--mono)",
          fontSize: "13px",
          lineHeight: "1.6",
          wordBreak: "break-word",
        }}>
          {content}
        </span>
      </div>
    </div>
  );
}

function SourceTags({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{
      marginTop: "0.75rem",
      display: "flex",
      flexWrap: "wrap" as const,
      gap: "0.375rem",
      paddingLeft: "0.75rem",
    }}>
      {sources.map((s, i) => (
        <a
          key={i}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          title={s.title}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.25rem",
            fontFamily: "var(--mono)",
            fontSize: "11px",
            color: "var(--text-2)",
            border: "1px solid var(--border)",
            borderRadius: "2px",
            padding: "1px 6px",
            textDecoration: "none",
            transition: "color 0.15s, border-color 0.15s",
            maxWidth: "220px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap" as const,
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLElement).style.color = "var(--accent)";
            (e.currentTarget as HTMLElement).style.borderColor = "var(--accent-dim)";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLElement).style.color = "var(--text-2)";
            (e.currentTarget as HTMLElement).style.borderColor = "var(--border)";
          }}
        >
          <span style={{ color: "var(--accent)", opacity: 0.7 }}>[{sourcePrefix(s.source_type)}]</span>
          {s.title}
        </a>
      ))}
    </div>
  );
}

function AssistantBlock({
  content,
  sources,
  noInfo,
}: {
  content: string;
  sources?: Source[];
  noInfo?: boolean;
}) {
  return (
    <div className="msg-enter" style={{
      borderLeft: `2px solid ${noInfo ? "var(--text-3)" : "var(--accent)"}`,
      paddingLeft: "0.75rem",
      marginLeft: "1rem",
    }}>
      <p style={{
        fontFamily: noInfo ? "var(--mono)" : "var(--serif)",
        fontSize: noInfo ? "12px" : "14px",
        color: noInfo ? "var(--text-2)" : "var(--text-1)",
        lineHeight: "1.75",
        fontStyle: noInfo ? "italic" : "normal",
        margin: 0,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}>
        {content}
      </p>
      {!noInfo && sources && sources.length > 0 && (
        <SourceTags sources={sources} />
      )}
    </div>
  );
}

function ScanningIndicator() {
  return (
    <div style={{
      borderLeft: "2px solid var(--accent-dim)",
      paddingLeft: "0.75rem",
      marginLeft: "1rem",
      display: "flex",
      alignItems: "center",
      gap: "0.5rem",
    }}>
      <span style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--text-2)" }}>
        scanning knowledge base
      </span>
      <span style={{ display: "flex", gap: "3px", alignItems: "center" }}>
        <span className="scanning-dot" style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--accent)", display: "inline-block" }} />
        <span className="scanning-dot" style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--accent)", display: "inline-block" }} />
        <span className="scanning-dot" style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--accent)", display: "inline-block" }} />
      </span>
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

function EmptyState({ onSelect }: { onSelect: (q: string) => void }) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column" as const,
      alignItems: "flex-start",
      justifyContent: "center",
      height: "100%",
      padding: "2rem 0",
      gap: "2rem",
    }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
            ready
          </span>
          <span className="cursor-blink" />
        </div>
        <p style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--text-2)", margin: 0 }}>
          Query internal knowledge — Confluence, Jira, runbooks.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column" as const, gap: "0.375rem" }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: "10px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "0.25rem" }}>
          suggested queries
        </span>
        {STARTER_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--mono)",
              fontSize: "12px",
              color: "var(--text-2)",
              padding: "0",
              textAlign: "left",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              transition: "color 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-2)")}
          >
            <span style={{ color: "var(--text-3)" }}>//</span>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ChatUI
// ---------------------------------------------------------------------------
export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function buildHistory() {
    return messages.map((m) => ({ role: m.role, content: m.content }));
  }

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;

    const userMsg: Message = { id: generateId(), role: "user", content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text.trim(), history: buildHistory() }),
      });

      if (!res.ok) throw new Error(`API error ${res.status}`);

      const data = await res.json();
      const answer: string = data.answer || "No answer returned.";
      const sources: Source[] = data.sources || [];
      const noInfo = answer.includes(NO_INFO_ANSWER);

      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: "assistant", content: answer, sources, noInfo },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: "assistant", content: `error: ${String(err)}`, noInfo: true },
      ]);
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

  // Auto-resize textarea
  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative", zIndex: 1 }}>

      {/* Header */}
      <div style={{
        flexShrink: 0,
        borderBottom: "1px solid var(--border)",
        padding: "0.75rem 1.5rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--surface)",
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem" }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: "13px", color: "var(--accent)", fontWeight: 700, letterSpacing: "-0.02em" }}>
            acme<span style={{ color: "var(--text-2)" }}>/</span>kb
          </span>
          <span style={{ fontFamily: "var(--mono)", fontSize: "10px", color: "var(--text-3)", border: "1px solid var(--border)", padding: "1px 5px", borderRadius: "2px" }}>
            v1.0
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%",
            background: "var(--accent)",
            display: "inline-block",
            boxShadow: "0 0 6px var(--accent)",
          }} />
          <span style={{ fontFamily: "var(--mono)", fontSize: "10px", color: "var(--text-2)" }}>
            RAG · hybrid search
          </span>
        </div>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: "auto",
        padding: "1.5rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.25rem",
      }}>
        {messages.length === 0 && (
          <EmptyState onSelect={(q) => sendMessage(q)} />
        )}

        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserLine key={msg.id} content={msg.content} />
          ) : (
            <AssistantBlock
              key={msg.id}
              content={msg.content}
              sources={msg.sources}
              noInfo={msg.noInfo}
            />
          )
        )}

        {loading && <ScanningIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        flexShrink: 0,
        borderTop: "1px solid var(--border)",
        background: "var(--surface)",
        padding: "0.875rem 1.5rem",
      }}>
        <form onSubmit={handleSubmit} style={{ display: "flex", alignItems: "flex-end", gap: "0.75rem" }}>
          {/* Prompt glyph */}
          <span style={{
            fontFamily: "var(--mono)",
            fontSize: "13px",
            color: loading ? "var(--text-3)" : "var(--accent)",
            flexShrink: 0,
            paddingBottom: "2px",
            transition: "color 0.2s",
            userSelect: "none",
          }}>
            &gt;_
          </span>

          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="ask anything about deployments, incidents, runbooks…"
            rows={1}
            disabled={loading}
            style={{
              flex: 1,
              resize: "none",
              background: "transparent",
              border: "none",
              borderBottom: "1px solid var(--border-hi)",
              outline: "none",
              fontFamily: "var(--mono)",
              fontSize: "13px",
              color: "var(--text-1)",
              lineHeight: "1.6",
              padding: "2px 0 4px",
              overflowY: "hidden",
              caretColor: "var(--accent)",
            }}
          />

          <button
            type="submit"
            disabled={loading || !input.trim()}
            style={{
              flexShrink: 0,
              background: "none",
              border: "1px solid var(--border-hi)",
              borderRadius: "2px",
              padding: "3px 10px",
              fontFamily: "var(--mono)",
              fontSize: "11px",
              color: (!loading && input.trim()) ? "var(--accent)" : "var(--text-3)",
              cursor: (!loading && input.trim()) ? "pointer" : "not-allowed",
              transition: "color 0.15s, border-color 0.15s",
              letterSpacing: "0.05em",
            }}
            onMouseEnter={e => {
              if (!loading && input.trim()) {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)";
              }
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--border-hi)";
            }}
          >
            {loading ? "…" : "send"}
          </button>
        </form>

        <div style={{
          marginTop: "0.375rem",
          paddingLeft: "1.75rem",
          fontFamily: "var(--mono)",
          fontSize: "10px",
          color: "var(--text-3)",
        }}>
          ↵ send &nbsp;·&nbsp; shift+↵ newline
        </div>
      </div>
    </div>
  );
}
