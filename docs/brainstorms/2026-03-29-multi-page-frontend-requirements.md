---
date: 2026-03-29
topic: multi-page-frontend
---

# Multi-Page Frontend with Team-Scoped Knowledge

## Problem Frame

The current frontend is a single page with one chat UI that searches all documents
globally. As more engineering teams onboard their knowledge, users need a way to get
focused answers scoped to their team's content, and new users need guidance on how to
use the tool effectively.

## User Flow

```
Home (/)
  │  Sidebar always visible
  ├─► /cicd       — CI/CD team chat (scoped to CI/CD space)
  ├─► /infra      — Infrastructure team chat (scoped to infra space)
  └─► /eng-env    — Engineer Environment chat (scoped to eng-env space)
        (more teams added via config file)
```

## Requirements

**Navigation**
- R1. A persistent left sidebar is present on all pages, listing Home and all configured team pages.
- R2. The active page is visually highlighted in the sidebar.
- R3. Each sidebar entry shows the team name and a short description.

**Home Page (`/`)**
- R4. Home page is informational only — no chat interface.
- R5. Home page includes a section explaining what the tool is: what knowledge it has (Confluence, Jira, runbooks), how RAG works at a high level, and what kinds of questions it answers well.
- R6. Home page includes an onboarding guide: how to write good questions, what sources look like, what "I don't have information about this" means, and how to get help if results are poor.
- R7. Home page links to each team page (e.g. cards or a list).

**Team Chat Pages**
- R8. Each team page has a full chat UI (reusing the existing `ChatUI` component).
- R9. Each team page passes a `space` filter to the API so the chat only searches that team's documents.
- R10. Each team page shows team-specific starter/example questions in the empty state.
- R11. The page title and app bar reflect the team name (e.g. "CI/CD Assistant").

**API**
- R12. The `/api/chat` endpoint accepts an optional `space` filter parameter. When provided, the hybrid search is restricted to documents where `space = <value>`. When absent, behavior is unchanged (searches all documents).

**Team Configuration**
- R13. A single config file (e.g. `lib/teams.ts`) defines all teams with: name, URL slug, description, space filter value, and example questions.
- R14. Adding a new team requires only adding one entry to the config file — no other code changes.
- R15. Initial teams: CI/CD (`/cicd`), Infrastructure (`/infra`), Engineer Environment (`/eng-env`).

## Success Criteria

- A new team can be onboarded by editing one config file with no code changes.
- Users on a team page only receive answers from that team's knowledge.
- A new engineer can understand what the tool does and how to use it from the home page alone.

## Scope Boundaries

- No admin UI for team management — config file only.
- No cross-team / universal chat — the home page is navigation-only.
- No team-specific visual theming — same UI design for all team pages, different content.
- No authentication or per-team access control.
- No collapsible sidebar (keep it simple for now).

## Key Decisions

- **Sidebar over top navbar**: Chosen for scalability — a sidebar handles many teams without overflowing, and leaves the full width for the chat.
- **`space` column for filtering**: Already exists in the schema, no migration needed.
- **Config-driven teams**: Single source of truth; zero code changes to add a team once the pattern is in place.
- **Home page is navigation-only**: Avoids confusion between "ask everything" and "ask my team" — users are routed to a scoped context immediately.

## Dependencies / Assumptions

- The `space` column in the `documents` table is already populated for ingested content, or will be populated by the ingestion pipeline when teams onboard.
- The ingestion pipeline sets `space` values that match the slugs/filters defined in the teams config.

## Outstanding Questions

### Resolve Before Planning
_(none)_

### Deferred to Planning
- [Technical] What `space` values are currently in the DB for the three initial teams? Verify against the ingestion config before writing SQL filter.
- [Technical] Should the sidebar be collapsible on smaller screens, or just always visible?
- [Technical] Should the `space` filter be sent as a JSON body field (alongside `message` and `history`) or as a query param on the API route?

## Next Steps
→ `/ce:plan` for structured implementation planning
