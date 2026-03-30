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

function sourceChipStyle(type: string): { bg: string; color: string; label: string } {
  switch (type) {
    case "confluence":
      return { bg: "#e8f0fe", color: "#1a73e8", label: "Confluence" };
    case "jira":
      return { bg: "#e8f0fe", color: "#5f35ae", label: "Jira" };
    case "doc":
      return { bg: "#e6f4ea", color: "#1e8e3e", label: "Doc" };
    default:
      return { bg: "#f1f3f4", color: "#5f6368", label: type };
  }
}

// ---------------------------------------------------------------------------
// Avatar
// ---------------------------------------------------------------------------
function AsstAvatar() {
  return (
    <div style={{
      width: 32, height: 32,
      borderRadius: "50%",
      background: "var(--blue)",
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
    }}>
      {/* Simple sparkle/AI icon */}
      <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
        <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source chips
// ---------------------------------------------------------------------------
function SourceChips({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: "12px", display: "flex", flexWrap: "wrap" as const, gap: "6px" }}>
      {sources.map((s, i) => {
        const chip = sourceChipStyle(s.source_type);
        return (
          <a
            key={i}
            href={s.url}
            target="_blank"
            rel="noopener noreferrer"
            title={s.title}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              padding: "3px 10px 3px 6px",
              borderRadius: "12px",
              background: chip.bg,
              textDecoration: "none",
              transition: "filter 0.15s",
              maxWidth: "260px",
            }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.filter = "brightness(0.95)"}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.filter = "none"}
          >
            <span style={{
              fontFamily: "var(--sans)",
              fontSize: "11px",
              fontWeight: 600,
              color: chip.color,
              background: chip.color + "18",
              borderRadius: "6px",
              padding: "0 5px",
              lineHeight: "18px",
              flexShrink: 0,
            }}>
              {chip.label}
            </span>
            <span style={{
              fontFamily: "var(--sans)",
              fontSize: "12px",
              color: "var(--text-2)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap" as const,
            }}>
              {s.title}
            </span>
          </a>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message rows
// ---------------------------------------------------------------------------
function UserMessage({ content }: { content: string }) {
  return (
    <div className="msg-enter" style={{ display: "flex", justifyContent: "flex-end" }}>
      <div style={{
        maxWidth: "72%",
        background: "var(--blue)",
        color: "#fff",
        borderRadius: "18px 18px 4px 18px",
        padding: "10px 16px",
        fontFamily: "var(--sans)",
        fontSize: "14px",
        lineHeight: "1.55",
        boxShadow: "var(--shadow-1)",
        wordBreak: "break-word",
        whiteSpace: "pre-wrap",
      }}>
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({
  content, sources, noInfo,
}: {
  content: string; sources?: Source[]; noInfo?: boolean;
}) {
  return (
    <div className="msg-enter" style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
      <AsstAvatar />
      <div style={{
        maxWidth: "78%",
        background: "var(--surface)",
        borderRadius: "4px 18px 18px 18px",
        padding: "12px 16px",
        boxShadow: "var(--shadow-1)",
        border: "1px solid var(--border)",
      }}>
        <p style={{
          margin: 0,
          fontFamily: "var(--sans)",
          fontSize: "14px",
          lineHeight: "1.6",
          color: noInfo ? "var(--text-3)" : "var(--text-1)",
          fontStyle: noInfo ? "italic" : "normal",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}>
          {content}
        </p>
        {!noInfo && sources && sources.length > 0 && (
          <>
            <div style={{ height: "1px", background: "var(--border)", margin: "10px 0" }} />
            <div style={{
              fontFamily: "var(--sans)",
              fontSize: "11px",
              fontWeight: 500,
              color: "var(--text-3)",
              textTransform: "uppercase" as const,
              letterSpacing: "0.06em",
              marginBottom: "6px",
            }}>
              Sources
            </div>
            <SourceChips sources={sources} />
          </>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
      <AsstAvatar />
      <div style={{
        background: "var(--surface)",
        borderRadius: "4px 18px 18px 18px",
        padding: "14px 18px",
        boxShadow: "var(--shadow-1)",
        border: "1px solid var(--border)",
      }}>
        <div className="dot-pulse" style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          <span /><span /><span />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
const STARTER_QUESTIONS = [
  "How do I deploy to production?",
  "My pod is OOMKilled, what should I do?",
  "How do I rollback a bad deployment?",
  "Why am I getting 401 errors after token rotation?",
  "How do I check logs for a specific pod?",
];

function EmptyState({ onSelect, questions }: { onSelect: (q: string) => void; questions: string[] }) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column" as const,
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      gap: "32px",
      padding: "2rem",
    }}>
      {/* Logo block */}
      <div style={{ textAlign: "center" as const }}>
        <div style={{
          width: 56, height: 56,
          borderRadius: "50%",
          background: "var(--blue)",
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 16px",
          boxShadow: "0 2px 8px rgba(26,115,232,0.35)",
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
            <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
          </svg>
        </div>
        <h2 style={{
          margin: "0 0 6px",
          fontFamily: "var(--sans)",
          fontSize: "20px",
          fontWeight: 400,
          color: "var(--text-1)",
          letterSpacing: "-0.01em",
        }}>
          How can I help?
        </h2>
        <p style={{
          margin: 0,
          fontFamily: "var(--sans)",
          fontSize: "13px",
          color: "var(--text-2)",
          maxWidth: "340px",
        }}>
          Search across Confluence pages, Jira tickets, and internal runbooks.
        </p>
      </div>

      {/* Suggestion cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "8px",
        width: "100%",
        maxWidth: "540px",
      }}>
        {questions.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: "12px 14px",
              fontFamily: "var(--sans)",
              fontSize: "13px",
              color: "var(--text-2)",
              cursor: "pointer",
              textAlign: "left" as const,
              lineHeight: "1.4",
              transition: "border-color 0.15s, box-shadow 0.15s, color 0.15s",
            }}
            onMouseEnter={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "var(--blue)";
              el.style.color = "var(--blue)";
              el.style.boxShadow = "var(--shadow-1)";
            }}
            onMouseLeave={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "var(--border)";
              el.style.color = "var(--text-2)";
              el.style.boxShadow = "none";
            }}
          >
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
interface ChatUIProps {
  space?: string;
  title?: string;
  exampleQuestions?: string[];
}

export default function ChatUI({ space, title, exampleQuestions }: ChatUIProps = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const displayTitle = title ?? "Acme Engineering Assistant";
  const displayQuestions =
    exampleQuestions && exampleQuestions.length > 0 ? exampleQuestions : STARTER_QUESTIONS;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function buildHistory() {
    return messages.slice(-10).map((m) => ({ role: m.role, content: m.content }));
  }

  function resetConversation() {
    if (loading) return;
    setMessages([]);
    setInput("");
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
        body: JSON.stringify({ message: text.trim(), history: buildHistory(), space }),
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
        { id: generateId(), role: "assistant", content: `Something went wrong: ${String(err)}`, noInfo: true },
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

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  }

  const canSend = !loading && input.trim().length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--bg)" }}>

      {/* App bar */}
      <div style={{
        flexShrink: 0,
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        padding: "0 24px",
        height: "56px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        boxShadow: "0 1px 3px rgba(60,64,67,0.08)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{
            width: 32, height: 32,
            borderRadius: "50%",
            background: "var(--blue)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: "var(--sans)", fontSize: "15px", fontWeight: 500, color: "var(--text-1)", lineHeight: 1.2 }}>
              {displayTitle}
            </div>
            <div style={{ fontFamily: "var(--sans)", fontSize: "11px", color: "var(--text-3)", lineHeight: 1 }}>
              Powered by RAG · Confluence · Jira · Runbooks
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            onClick={resetConversation}
            disabled={loading}
            title="New conversation"
            style={{
              fontFamily: "var(--sans)",
              fontSize: "12px",
              color: loading ? "var(--text-3)" : "var(--text-2)",
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: "12px",
              padding: "2px 10px",
              cursor: loading ? "default" : "pointer",
              transition: "border-color 0.15s, color 0.15s",
            }}
            onMouseEnter={e => {
              if (!loading) {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--blue)";
                (e.currentTarget as HTMLElement).style.color = "var(--blue)";
              }
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--border)";
              (e.currentTarget as HTMLElement).style.color = loading ? "var(--text-3)" : "var(--text-2)";
            }}
          >
            New conversation
          </button>
          <div style={{
            fontFamily: "var(--mono)",
            fontSize: "11px",
            color: "var(--text-3)",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: "12px",
            padding: "2px 10px",
          }}>
            internal · confidential
          </div>
        </div>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: "auto",
        padding: "24px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        maxWidth: "820px",
        width: "100%",
        margin: "0 auto",
        alignSelf: "center",
        boxSizing: "border-box",
      }}>
        {messages.length === 0 ? (
          <EmptyState onSelect={sendMessage} questions={displayQuestions} />
        ) : (
          messages.map((msg) =>
            msg.role === "user" ? (
              <UserMessage key={msg.id} content={msg.content} />
            ) : (
              <AssistantMessage
                key={msg.id}
                content={msg.content}
                sources={msg.sources}
                noInfo={msg.noInfo}
              />
            )
          )
        )}

        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{
        flexShrink: 0,
        background: "var(--surface)",
        borderTop: "1px solid var(--border)",
        padding: "12px 24px 16px",
      }}>
        <form
          onSubmit={handleSubmit}
          style={{
            maxWidth: "820px",
            margin: "0 auto",
            display: "flex",
            alignItems: "flex-end",
            gap: "8px",
            background: "var(--surface)",
            border: "1px solid var(--border-hi)",
            borderRadius: "24px",
            padding: "8px 8px 8px 18px",
            boxShadow: "var(--shadow-1)",
            transition: "box-shadow 0.2s, border-color 0.2s",
          }}
          onFocus={e => {
            e.currentTarget.style.borderColor = "var(--blue)";
            e.currentTarget.style.boxShadow = "0 1px 3px rgba(26,115,232,0.15), 0 0 0 2px rgba(26,115,232,0.10)";
          }}
          onBlur={e => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) {
              e.currentTarget.style.borderColor = "var(--border-hi)";
              e.currentTarget.style.boxShadow = "var(--shadow-1)";
            }
          }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask about deployments, incidents, runbooks…"
            rows={1}
            disabled={loading}
            style={{
              flex: 1,
              resize: "none",
              border: "none",
              outline: "none",
              background: "transparent",
              fontFamily: "var(--sans)",
              fontSize: "14px",
              color: "var(--text-1)",
              lineHeight: "1.5",
              padding: "4px 0",
              overflowY: "hidden",
              caretColor: "var(--blue)",
            }}
          />

          {/* Send button */}
          <button
            type="submit"
            disabled={!canSend}
            style={{
              width: 36, height: 36,
              borderRadius: "50%",
              background: canSend ? "var(--blue)" : "var(--surface-2)",
              border: "none",
              cursor: canSend ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              transition: "background 0.15s",
            }}
            onMouseEnter={e => {
              if (canSend) (e.currentTarget as HTMLElement).style.background = "var(--blue-dark)";
            }}
            onMouseLeave={e => {
              if (canSend) (e.currentTarget as HTMLElement).style.background = "var(--blue)";
            }}
          >
            {loading ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="var(--text-3)" strokeWidth="2.5" />
                <path d="M12 3a9 9 0 019 9" stroke="var(--text-2)" strokeWidth="2.5" strokeLinecap="round"
                  style={{ animation: "spin 0.8s linear infinite", transformOrigin: "center" }} />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={canSend ? "white" : "var(--text-3)"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            )}
          </button>
        </form>

        <p style={{
          textAlign: "center" as const,
          margin: "8px 0 0",
          fontFamily: "var(--sans)",
          fontSize: "11px",
          color: "var(--text-3)",
        }}>
          Press Enter to send · Shift+Enter for a new line · Internal use only
        </p>
      </div>
    </div>
  );
}
