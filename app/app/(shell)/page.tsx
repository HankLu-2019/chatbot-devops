"use client";

import Link from "next/link";
import { TEAMS } from "@/lib/teams";

export default function HomePage() {
  return (
    <div style={{
      flex: 1,
      overflowY: "auto",
      background: "var(--bg)",
      padding: "48px 24px 64px",
    }}>
      <div style={{ maxWidth: "720px", margin: "0 auto" }}>

        {/* Hero */}
        <div style={{ marginBottom: "48px" }}>
          <div style={{
            width: 52,
            height: 52,
            borderRadius: "50%",
            background: "var(--blue)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "20px",
            boxShadow: "0 2px 8px rgba(26,115,232,0.30)",
          }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
            </svg>
          </div>
          <h1 style={{
            margin: "0 0 10px",
            fontFamily: "var(--sans)",
            fontSize: "26px",
            fontWeight: 500,
            color: "var(--text-1)",
            letterSpacing: "-0.02em",
          }}>
            Acme Engineering Assistant
          </h1>
          <p style={{
            margin: 0,
            fontFamily: "var(--sans)",
            fontSize: "15px",
            color: "var(--text-2)",
            lineHeight: "1.6",
            maxWidth: "560px",
          }}>
            An AI-powered knowledge assistant that searches across your team&apos;s
            Confluence pages, Jira tickets, and internal runbooks to give you
            cited, accurate answers in seconds.
          </p>
        </div>

        {/* What is this */}
        <section style={{ marginBottom: "40px" }}>
          <SectionHeading>What this tool does</SectionHeading>
          <div style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "20px 24px",
          }}>
            <InfoRow icon="🔍" title="Hybrid search">
              Combines full-text and semantic search across your team&apos;s indexed
              documents for the most relevant results.
            </InfoRow>
            <InfoRow icon="📎" title="Cited sources">
              Every answer links back to the original Confluence page, Jira ticket,
              or runbook so you can verify and dive deeper.
            </InfoRow>
            <InfoRow icon="💬" title="Conversational">
              Ask follow-up questions — the assistant remembers the context of your
              conversation within a session.
            </InfoRow>
            <InfoRow icon="🏢" title="Team-scoped" last>
              Each team page searches only that team&apos;s knowledge, keeping answers
              focused and relevant.
            </InfoRow>
          </div>
        </section>

        {/* Getting started */}
        <section style={{ marginBottom: "48px" }}>
          <SectionHeading>Getting started</SectionHeading>
          <div style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "20px 24px",
            display: "flex",
            flexDirection: "column" as const,
            gap: "14px",
          }}>
            <Tip number={1} title="Ask specific questions">
              &ldquo;How do I configure autoscaling for service X?&rdquo; works better than
              &ldquo;autoscaling&rdquo;. The more context you give, the better the answer.
            </Tip>
            <Tip number={2} title="Use your team's page">
              Navigate to your team&apos;s page using the sidebar. Answers will be scoped
              to your team&apos;s indexed knowledge, not the entire corpus.
            </Tip>
            <Tip number={3} title="Check the sources">
              Source chips appear below each answer. Click them to open the original
              document and verify the information is still current.
            </Tip>
            <Tip number={4} title="&ldquo;I don&apos;t have information about this&rdquo;">
              This means the answer wasn&apos;t found in the indexed content. The document
              may not be indexed yet — ask your team lead to add it to the ingestion pipeline.
            </Tip>
            <Tip number={5} title="Start fresh for a new topic" last>
              Reload the page to clear conversation history when switching to an
              unrelated question. This improves answer quality.
            </Tip>
          </div>
        </section>

        {/* Team cards */}
        <section>
          <SectionHeading>Choose your team</SectionHeading>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: "12px",
          }}>
            {TEAMS.map((team) => (
              <Link
                key={team.slug}
                href={`/${team.slug}`}
                style={{
                  display: "block",
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  padding: "18px 20px",
                  textDecoration: "none",
                  transition: "border-color 0.15s, box-shadow 0.15s",
                }}
                onMouseEnter={(e) => {
                  const el = e.currentTarget as HTMLElement;
                  el.style.borderColor = "var(--blue)";
                  el.style.boxShadow = "var(--shadow-1)";
                }}
                onMouseLeave={(e) => {
                  const el = e.currentTarget as HTMLElement;
                  el.style.borderColor = "var(--border)";
                  el.style.boxShadow = "none";
                }}
              >
                <div style={{
                  fontFamily: "var(--sans)",
                  fontSize: "14px",
                  fontWeight: 500,
                  color: "var(--text-1)",
                  marginBottom: "4px",
                }}>
                  {team.label}
                </div>
                <div style={{
                  fontFamily: "var(--sans)",
                  fontSize: "12px",
                  color: "var(--text-2)",
                  lineHeight: "1.45",
                  marginBottom: "14px",
                }}>
                  {team.description}
                </div>
                <div style={{
                  fontFamily: "var(--sans)",
                  fontSize: "12px",
                  color: "var(--blue)",
                  fontWeight: 500,
                }}>
                  Open chat →
                </div>
              </Link>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      margin: "0 0 12px",
      fontFamily: "var(--sans)",
      fontSize: "13px",
      fontWeight: 600,
      color: "var(--text-3)",
      textTransform: "uppercase" as const,
      letterSpacing: "0.06em",
    }}>
      {children}
    </h2>
  );
}

function InfoRow({
  icon,
  title,
  children,
  last,
}: {
  icon: string;
  title: string;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <div style={{
      display: "flex",
      gap: "14px",
      paddingBottom: last ? 0 : "14px",
      marginBottom: last ? 0 : "14px",
      borderBottom: last ? "none" : "1px solid var(--border)",
    }}>
      <span style={{ fontSize: "16px", flexShrink: 0, lineHeight: 1.5 }}>{icon}</span>
      <div>
        <div style={{
          fontFamily: "var(--sans)",
          fontSize: "13px",
          fontWeight: 500,
          color: "var(--text-1)",
          marginBottom: "2px",
        }}>
          {title}
        </div>
        <div style={{
          fontFamily: "var(--sans)",
          fontSize: "13px",
          color: "var(--text-2)",
          lineHeight: "1.5",
        }}>
          {children}
        </div>
      </div>
    </div>
  );
}

function Tip({
  number,
  title,
  children,
  last,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <div style={{
      display: "flex",
      gap: "14px",
      paddingBottom: last ? 0 : "14px",
      borderBottom: last ? "none" : "1px solid var(--border)",
    }}>
      <div style={{
        width: 22,
        height: 22,
        borderRadius: "50%",
        background: "var(--blue)",
        color: "white",
        fontFamily: "var(--sans)",
        fontSize: "11px",
        fontWeight: 600,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        marginTop: "1px",
      }}>
        {number}
      </div>
      <div>
        <div style={{
          fontFamily: "var(--sans)",
          fontSize: "13px",
          fontWeight: 500,
          color: "var(--text-1)",
          marginBottom: "2px",
        }}>
          {title}
        </div>
        <div style={{
          fontFamily: "var(--sans)",
          fontSize: "13px",
          color: "var(--text-2)",
          lineHeight: "1.5",
        }}>
          {children}
        </div>
      </div>
    </div>
  );
}
