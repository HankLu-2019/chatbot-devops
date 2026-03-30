"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { TEAMS } from "@/lib/teams";

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <nav style={{
      width: "240px",
      flexShrink: 0,
      height: "100%",
      background: "var(--surface)",
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      overflowY: "auto",
    }}>
      {/* Brand */}
      <div style={{
        padding: "20px 20px 16px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        flexShrink: 0,
      }}>
        <div style={{
          width: 28,
          height: 28,
          borderRadius: "50%",
          background: "var(--blue)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="white">
            <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
          </svg>
        </div>
        <span style={{
          fontFamily: "var(--sans)",
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--text-1)",
          letterSpacing: "-0.01em",
        }}>
          Acme Knowledge
        </span>
      </div>

      {/* Nav items */}
      <div style={{ padding: "8px 0", flex: 1 }}>
        <NavItem href="/" label="Home" description="Overview & getting started" active={pathname === "/"} />

        <div style={{
          padding: "8px 16px 4px",
          fontFamily: "var(--sans)",
          fontSize: "10px",
          fontWeight: 600,
          color: "var(--text-3)",
          textTransform: "uppercase" as const,
          letterSpacing: "0.08em",
        }}>
          Teams
        </div>

        {TEAMS.map((team) => (
          <NavItem
            key={team.slug}
            href={`/${team.slug}`}
            label={team.label}
            description={team.description}
            active={pathname === `/${team.slug}`}
          />
        ))}

        <div style={{
          height: "1px",
          background: "var(--border)",
          margin: "4px 8px",
        }} />

        <NavItem
          href="/search"
          label="Search All Teams"
          description="Ask across all knowledge bases"
          active={pathname === "/search"}
        />
      </div>

      {/* Footer */}
      <div style={{
        padding: "12px 16px",
        borderTop: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        <span style={{
          fontFamily: "var(--mono)",
          fontSize: "10px",
          color: "var(--text-3)",
        }}>
          internal · confidential
        </span>
      </div>
    </nav>
  );
}

function NavItem({
  href,
  label,
  description,
  active,
}: {
  href: string;
  label: string;
  description: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      style={{
        display: "block",
        padding: "8px 16px 8px 12px",
        margin: "1px 8px",
        borderRadius: "6px",
        borderLeft: active ? "3px solid var(--blue)" : "3px solid transparent",
        background: active ? "var(--blue-light, rgba(26,115,232,0.08))" : "transparent",
        textDecoration: "none",
        transition: "background 0.12s",
      }}
      onMouseEnter={(e) => {
        if (!active) (e.currentTarget as HTMLElement).style.background = "var(--surface-2)";
      }}
      onMouseLeave={(e) => {
        if (!active) (e.currentTarget as HTMLElement).style.background = "transparent";
      }}
    >
      <div style={{
        fontFamily: "var(--sans)",
        fontSize: "13px",
        fontWeight: active ? 500 : 400,
        color: active ? "var(--blue)" : "var(--text-1)",
        lineHeight: 1.3,
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "var(--sans)",
        fontSize: "11px",
        color: "var(--text-3)",
        lineHeight: 1.3,
        marginTop: "1px",
      }}>
        {description}
      </div>
    </Link>
  );
}
