"use client";

import { useState } from "react";
import type { DiagnosisResult } from "@/lib/jenkins-tools";

type UIState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "result"; data: DiagnosisResult }
  | { phase: "error"; message: string };

export default function JenkinsDebugUI() {
  const [jobUrl, setJobUrl] = useState("");
  const [state, setState] = useState<UIState>({ phase: "idle" });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = jobUrl.trim();
    if (!trimmed) return;

    setState({ phase: "loading" });

    try {
      const res = await fetch("/api/jenkins-debug", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobUrl: trimmed }),
      });

      const data = await res.json();

      if (!res.ok) {
        setState({ phase: "error", message: data.error ?? `Server error ${res.status}` });
        return;
      }

      setState({ phase: "result", data });
    } catch (err) {
      setState({
        phase: "error",
        message: err instanceof Error ? err.message : "Network error",
      });
    }
  }

  return (
    <div style={{
      flex: 1,
      overflowY: "auto",
      background: "var(--bg)",
      padding: "48px 24px 64px",
    }}>
      <div style={{ maxWidth: "760px", margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: "32px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: "8px",
              background: "var(--blue)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}>
              {/* Wrench icon */}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
              </svg>
            </div>
            <h1 style={{
              fontFamily: "var(--sans)",
              fontSize: "22px",
              fontWeight: 600,
              color: "var(--text-1)",
              margin: 0,
            }}>
              Jenkins Debugger
            </h1>
          </div>
          <p style={{
            fontFamily: "var(--sans)",
            fontSize: "14px",
            color: "var(--text-2)",
            margin: 0,
            lineHeight: 1.6,
          }}>
            Paste a Jenkins build URL and the agent will diagnose why it failed —
            root cause and suggested fix in under 60 seconds.
          </p>
        </div>

        {/* URL input form */}
        <form onSubmit={handleSubmit} style={{ marginBottom: "32px" }}>
          <label style={{
            display: "block",
            fontFamily: "var(--sans)",
            fontSize: "12px",
            fontWeight: 600,
            color: "var(--text-2)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            marginBottom: "8px",
          }}>
            Jenkins Build URL
          </label>
          <div style={{ display: "flex", gap: "10px" }}>
            <input
              type="url"
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              placeholder="http://localhost:8080/job/payment-service/123"
              disabled={state.phase === "loading"}
              style={{
                flex: 1,
                padding: "10px 14px",
                fontFamily: "var(--mono)",
                fontSize: "13px",
                color: "var(--text-1)",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                outline: "none",
                opacity: state.phase === "loading" ? 0.6 : 1,
              }}
            />
            <button
              type="submit"
              disabled={state.phase === "loading" || !jobUrl.trim()}
              style={{
                padding: "10px 20px",
                fontFamily: "var(--sans)",
                fontSize: "13px",
                fontWeight: 500,
                color: "white",
                background: state.phase === "loading" || !jobUrl.trim()
                  ? "var(--text-3)"
                  : "var(--blue)",
                border: "none",
                borderRadius: "8px",
                cursor: state.phase === "loading" || !jobUrl.trim() ? "not-allowed" : "pointer",
                whiteSpace: "nowrap",
                transition: "background 0.15s",
              }}
            >
              {state.phase === "loading" ? "Diagnosing…" : "Diagnose"}
            </button>
          </div>

          {/* Example links */}
          <div style={{
            marginTop: "10px",
            display: "flex",
            flexWrap: "wrap",
            gap: "8px",
          }}>
            <span style={{ fontFamily: "var(--sans)", fontSize: "11px", color: "var(--text-3)" }}>
              Try:
            </span>
            {[
              { label: "ECR auth failure", url: "http://localhost:8080/job/payment-service/123" },
              { label: "Disk space", url: "http://localhost:8080/job/payment-service/125" },
              { label: "HTTP 403", url: "http://localhost:8080/job/api-gateway/88" },
              { label: "GitLab access", url: "http://localhost:8080/job/gitlab-sync/42" },
              { label: "No baseline", url: "http://localhost:8080/job/new-service/1" },
            ].map((ex) => (
              <button
                key={ex.url}
                type="button"
                onClick={() => setJobUrl(ex.url)}
                style={{
                  padding: "2px 8px",
                  fontFamily: "var(--mono)",
                  fontSize: "11px",
                  color: "var(--blue)",
                  background: "transparent",
                  border: "1px solid var(--blue)",
                  borderRadius: "4px",
                  cursor: "pointer",
                  opacity: 0.8,
                }}
              >
                {ex.label}
              </button>
            ))}
          </div>
        </form>

        {/* Loading state */}
        {state.phase === "loading" && (
          <div style={{
            padding: "32px",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "12px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "16px",
          }}>
            <Spinner />
            <div style={{ textAlign: "center" }}>
              <p style={{
                fontFamily: "var(--sans)",
                fontSize: "14px",
                fontWeight: 500,
                color: "var(--text-1)",
                margin: "0 0 4px",
              }}>
                Analyzing build failure…
              </p>
              <p style={{
                fontFamily: "var(--sans)",
                fontSize: "12px",
                color: "var(--text-3)",
                margin: 0,
              }}>
                Fetching logs, comparing with last successful build. Up to 60s.
              </p>
            </div>
          </div>
        )}

        {/* Error state */}
        {state.phase === "error" && (
          <div style={{
            padding: "20px 24px",
            background: "rgba(234,67,53,0.06)",
            border: "1px solid rgba(234,67,53,0.25)",
            borderRadius: "12px",
          }}>
            <p style={{
              fontFamily: "var(--sans)",
              fontSize: "13px",
              fontWeight: 600,
              color: "#d93025",
              margin: "0 0 6px",
            }}>
              Error
            </p>
            <p style={{
              fontFamily: "var(--mono)",
              fontSize: "12px",
              color: "var(--text-1)",
              margin: 0,
              lineHeight: 1.6,
              whiteSpace: "pre-wrap",
            }}>
              {state.message}
            </p>
          </div>
        )}

        {/* Result state */}
        {state.phase === "result" && <DiagnosisCard result={state.data} />}

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DiagnosisCard({ result }: { result: DiagnosisResult }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>

      {/* Partial warning */}
      {result.partial && (
        <div style={{
          padding: "12px 16px",
          background: "rgba(251,188,4,0.1)",
          border: "1px solid rgba(251,188,4,0.4)",
          borderRadius: "8px",
          fontFamily: "var(--sans)",
          fontSize: "12px",
          color: "#b8860b",
        }}>
          Partial analysis — max depth reached. Results below may be incomplete.
        </div>
      )}

      {/* Meta row */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
        {result.buildNumber > 0 && (
          <Chip label={`Build #${result.buildNumber}`} color="var(--text-2)" />
        )}
        {result.failedStage && (
          <Chip label={`Failed at: ${result.failedStage}`} color="#d93025" bg="rgba(234,67,53,0.08)" />
        )}
        <Chip label={`${result.turnsUsed} tool calls`} color="var(--text-3)" />
      </div>

      {/* Analysis block */}
      <div style={{
        padding: "24px",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
      }}>
        <p style={{
          fontFamily: "var(--sans)",
          fontSize: "12px",
          fontWeight: 600,
          color: "var(--text-3)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          margin: "0 0 12px",
        }}>
          Diagnosis
        </p>
        <div style={{
          fontFamily: "var(--sans)",
          fontSize: "14px",
          color: "var(--text-1)",
          lineHeight: 1.7,
          whiteSpace: "pre-wrap",
        }}>
          {formatAnalysis(result.analysis)}
        </div>
      </div>

      {/* Job URL */}
      <p style={{
        fontFamily: "var(--mono)",
        fontSize: "11px",
        color: "var(--text-3)",
        margin: 0,
      }}>
        {result.jobUrl}
      </p>

    </div>
  );
}

function Chip({
  label,
  color,
  bg,
}: {
  label: string;
  color: string;
  bg?: string;
}) {
  return (
    <span style={{
      display: "inline-block",
      padding: "3px 10px",
      fontFamily: "var(--sans)",
      fontSize: "11px",
      fontWeight: 500,
      color,
      background: bg ?? "var(--surface)",
      border: `1px solid ${bg ? "transparent" : "var(--border)"}`,
      borderRadius: "20px",
    }}>
      {label}
    </span>
  );
}

function Spinner() {
  return (
    <div style={{
      width: 32,
      height: 32,
      borderRadius: "50%",
      border: "3px solid var(--border)",
      borderTopColor: "var(--blue)",
      animation: "spin 0.8s linear infinite",
    }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/** Highlight ROOT CAUSE / FIX labels in the analysis text. */
function formatAnalysis(text: string): React.ReactNode {
  if (!text) return null;
  const lines = text.split("\n");
  return lines.map((line, i) => {
    const isRootCause = line.startsWith("ROOT CAUSE:");
    const isFix = line.startsWith("FIX:");
    if (isRootCause || isFix) {
      const [label, ...rest] = line.split(":");
      return (
        <div key={i} style={{ marginBottom: "8px" }}>
          <span style={{
            fontWeight: 600,
            color: isRootCause ? "#d93025" : "var(--blue)",
          }}>
            {label}:
          </span>
          {rest.join(":")}
        </div>
      );
    }
    return (
      <span key={i}>
        {line}
        {i < lines.length - 1 ? "\n" : ""}
      </span>
    );
  });
}
