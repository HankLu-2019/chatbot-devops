---
title: "feat: Multi-Page Team-Scoped Frontend"
type: feat
status: active
date: 2026-03-29
origin: docs/brainstorms/2026-03-29-multi-page-frontend-requirements.md
deepened: 2026-03-29
---

# feat: Multi-Page Team-Scoped Frontend

## Overview

The RAG chatbot is a single page today. This plan expands it into a multi-page
Next.js app with a persistent sidebar, a home/landing page, and team-specific chat
pages that scope their knowledge search to a team's documents via an optional `space`
filter on the API. Adding a new team requires only one config file edit.

## Problem Frame

Engineers across CI/CD, Infrastructure, and Engineering Environment teams need focused
answers from their own knowledge base rather than a global corpus. New users need a
landing page to understand what the tool does and how to use it effectively before
diving into a chat. The system must make onboarding new teams low-friction.

See origin: `docs/brainstorms/2026-03-29-multi-page-frontend-requirements.md`

## Requirements Trace

- R1–R3. Persistent sidebar visible on all pages; active page highlighted; team name + description shown.
- R4–R7. Home page is informational only — explains the tool, provides onboarding guide, links to team pages. No chat.
- R8–R11. Each team page has a full chat UI scoped to that team's `space` value; team-specific starter questions; team name in app bar.
- R12. `/api/chat` accepts optional `space` filter; when provided, restricts hybrid search to `WHERE space = <value>`.
- R13–R15. Single `lib/teams.ts` config drives all pages; adding one entry onboards a new team with no other code changes. Initial teams: CI/CD, Infrastructure, Engineer Environment.

## Scope Boundaries

- No admin UI — config file only.
- No universal/cross-team chat on any page.
- No per-team visual theming — same design tokens, different content.
- No authentication or access control.
- No sidebar collapse behavior.
- No data migration or re-ingestion — space filter is plumbed now; actual data must be re-ingested with per-team space values separately (see Dependencies).

## Context & Research

### Relevant Code and Patterns

- `app/app/layout.tsx` — bare `<html><body>{children}</body></html>`; needs no change (shell layout goes inside a route group)
- `app/app/page.tsx` — current single page wrapping `ChatUI` in a `height:100vh` `<main>`; will be replaced by home landing page under `(shell)/`
- `app/components/ChatUI.tsx` — ~587-line client component; currently accepts no props; starter questions are hardcoded as `STARTER_QUESTIONS` const; app bar title is hardcoded
- `app/app/api/chat/route.ts` — `POST` handler; `hybridSearch(query, embedding)` runs a raw SQL CTE; `RequestBody = { message, history? }`; space filter must be threaded through here
- `app/lib/db.ts` — `pg` Pool singleton; new `lib/teams.ts` follows this module pattern
- **Styling convention**: all UI uses inline `style` props with CSS custom properties (`var(--blue)`, `var(--surface)`, `var(--border)`, etc.) defined in `globals.css`; zero Tailwind utility classes in tsx files; new components must follow this pattern

### Institutional Learnings

- No `docs/solutions/` exists yet. First solved problems from this work are good candidates to seed it.

### External References

- Next.js 15 App Router route groups: `(groupName)/` directories create shared layouts without affecting URL paths — the standard pattern for adding a persistent shell.
- `usePathname()` from `next/navigation` is the correct hook for active-route detection in App Router client components.

## Key Technical Decisions

- **Route group `(shell)/` for the sidebar shell**: A route group layout wraps all user-facing pages (home + team pages) with the sidebar without affecting URLs. The existing root `layout.tsx` stays untouched. This is the idiomatic App Router approach and avoids duplicating the sidebar in every page.

- **Dynamic route `(shell)/[team]/page.tsx` for team pages**: A single dynamic page file looks up the team from `TEAMS` config by slug. Adding a team = one config entry, zero new page files. Satisfies R14. An unknown slug returns a 404 via `notFound()`.

- **`lib/teams.ts` as single source of truth**: Defines `Team` interface and `TEAMS` array (slug, label, space, description, exampleQuestions). Both the sidebar and each team page import from here. This is the only place to edit when onboarding a new team.

- **`space` as optional JSON body field on the API**: Consistent with the existing `{ message, history }` body shape. Server-side only — the client passes what the page config dictates. When absent, behavior is unchanged (searches all documents).

- **Space filter values**: Use `"CI-CD"`, `"INFRA"`, `"ENG-ENV"` as the canonical values in `lib/teams.ts`. These match what the ingestion pipeline should set when teams re-ingest their content. (See Dependencies — current data all has `space = "ENG"` and filtering won't be meaningful until re-ingestion.)

- **ChatUI space prop**: `ChatUI` receives an optional `space?: string` prop and threads it into the fetch body. Team-specific `exampleQuestions` replace the current hardcoded `STARTER_QUESTIONS`. The app bar title becomes a prop (`title?: string`) to show the team name.

- **BM25 + space equality filter — preferred approach is in-CTE filtering**: Apply `AND space = $3` inside both `bm25_results` and `vector_results` CTEs so filtering happens before the 30-row RRF window is built. A post-CTE outer `WHERE` filter is NOT acceptable — filtering after RRF ranking means the 30-row window may contain very few team-specific docs, producing poor results regardless of threshold. If ParadeDB v0.22+ does not support `AND space = $3` directly alongside `@@@`, the fallback is a `WHERE space = $3` row filter applied inside the `bm25_results` CTE wrapping (before results leave the CTE), not after. Resolve the exact syntax during implementation, but the requirement is: space filter applied inside both CTEs before ranking.

- **`space` must always be passed as a positional SQL parameter**: When `space` is present, pass it as `$3` in the parameterized query. **Never interpolate the space value directly into the SQL string** (e.g., via template literals) — that path introduces SQL injection even though the value comes from page config, since the API endpoint is unauthenticated and `space` is user-controlled in the request body. Validate server-side: `typeof space === "string" && space.length > 0` (handles both `undefined` and runtime `null`).

- **Space-scoping is a UX filter, not a data boundary**: There is no authentication on `/api/chat`. Any caller can POST `{ space: "INFRA" }` regardless of which page they came from. This is a deliberate choice given the no-auth scope boundary. Future engineers must not assume team pages provide data isolation — they provide scoped UX only.

## Open Questions

### Resolved During Planning

- **Should space be a query param or body field?** Body field — consistent with existing `{ message, history }` shape. (see origin: Key Decisions)
- **Static or dynamic team routes?** Dynamic `[team]/page.tsx` — zero new files per team, satisfies R14.
- **Route groups vs top-level layout change?** Route group `(shell)/` — clean, idiomatic, non-destructive to root layout.

### Deferred to Implementation

- **ParadeDB BM25 + equality filter exact syntax**: Verify whether `WHERE (documents @@@ paradedb.parse($1)) AND space = $3` works, or whether `paradedb.boolean` wrapping is required. The requirement is in-CTE filtering (see Key Technical Decisions). Check ParadeDB v0.22+ docs during implementation.
- **`notFound()` vs redirect for unknown team slugs**: Default to 404 via `notFound()`; implement a custom `not-found.tsx` matching app design tokens if time allows.
- **Sidebar width on narrow screens**: 240px is planned; decide at implementation if a media query breakpoint is needed for laptop-width screens.
- **B-tree index on `documents(space)`**: The schema has no index on the `space` column. For current document volumes this is likely acceptable, but a `CREATE INDEX ON documents(space)` should be added to `schema.sql` before traffic scales. Defer to implementation — add the index to schema.sql as part of this work.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not
> implementation specification. The implementing agent should treat it as context, not
> code to reproduce.*

**Component and route tree:**

```
RootLayout  app/app/layout.tsx  (unchanged — <html><body>)
  └── ShellLayout  app/app/(shell)/layout.tsx  (NEW)
        ├── Sidebar  app/components/Sidebar.tsx  (NEW)
        │     └── reads TEAMS from app/lib/teams.ts
        └── <main>  (children slot)
              ├── HomePage  app/app/(shell)/page.tsx  (REPLACE existing page.tsx)
              │     └── static content: tool description + onboarding guide + team links
              └── TeamPage  app/app/(shell)/[team]/page.tsx  (NEW, async)
                    │   Next.js 15: params is a Promise — must await params
                    └── looks up Team by slug → ChatUI(space, title, exampleQuestions)
                          └── POST /api/chat  { message, history, space? }
                                └── hybridSearch(query, embedding, space?)
                                      └── ... WHERE space = $3 (when provided)
```

**Data flow for `space` filter:**

```
lib/teams.ts  →  [team]/page.tsx  →  ChatUI prop  →  fetch body  →
  route.ts RequestBody  →  hybridSearch(q, emb, space)  →
  SQL CTE: bm25_results + vector_results filtered by space  →
  rerank → generate answer
```

## Implementation Units

```mermaid
TB
graph TB
  U1[Unit 1: lib/teams.ts config] --> U2[Unit 2: ChatUI space prop]
  U1 --> U3[Unit 3: API space filter]
  U1 --> U4[Unit 4: Sidebar + shell layout]
  U2 --> U6[Unit 6: Team chat pages]
  U4 --> U5[Unit 5: Home landing page]
  U4 --> U6
```

---

- [ ] **Unit 1: Teams config (`lib/teams.ts`)**

**Goal:** Define the `Team` interface and `TEAMS` array as the single source of truth for all team pages, sidebar nav, and API space values.

**Requirements:** R13, R14, R15

**Dependencies:** None

**Files:**
- Create: `app/lib/teams.ts`

**Approach:**
- `Team` interface: `slug` (URL segment), `label` (display name), `description` (sidebar subtitle), `space` (value sent as API filter), `exampleQuestions` (string array for empty-state chips)
- `TEAMS` array: three entries — CI/CD (slug `cicd`, space `"CI-CD"`), Infrastructure (slug `infra`, space `"INFRA"`), Engineer Environment (slug `eng-env`, space `"ENG-ENV"`)
- Each team should have 4–5 example questions relevant to that domain
- Export both the interface and the array; also export a helper `getTeamBySlug(slug: string): Team | undefined`

**Patterns to follow:**
- `app/lib/db.ts` — simple module export, no class wrappers

**Test scenarios:**
- Happy path: `TEAMS` has exactly 3 entries; each has non-empty slug, label, space, description, and at least 3 exampleQuestions
- Edge case: `getTeamBySlug("cicd")` returns the CI/CD team; `getTeamBySlug("unknown")` returns `undefined`
- Edge case: all slugs are unique across the TEAMS array

**Verification:**
- TypeScript compiles without errors; `getTeamBySlug` returns the correct team for each slug

---

- [ ] **Unit 2: ChatUI — add `space`, `title`, and `exampleQuestions` props**

**Goal:** Make `ChatUI` configurable per-team so each team page can pass its own scope, title, and starter questions.

**Requirements:** R8, R9, R10, R11

**Dependencies:** Unit 1

**Files:**
- Modify: `app/components/ChatUI.tsx`

**Approach:**
- Add props: `space?: string`, `title?: string`, `exampleQuestions?: string[]`
- Thread `space` into the `fetch("/api/chat", ...)` body: `body: JSON.stringify({ message, history, space })`
- **`EmptyState` must be updated (required structural change):** `EmptyState` at line ~229 currently has signature `{ onSelect: (q: string) => void }` and reads `STARTER_QUESTIONS` from module scope. Add a `questions: string[]` prop to `EmptyState` and render from that prop. The fallback logic lives in `ChatUI`: pass `exampleQuestions && exampleQuestions.length > 0 ? exampleQuestions : STARTER_QUESTIONS` as the `questions` prop — `EmptyState` itself never needs to handle an empty array. This is a required structural change — all other chat logic, source chips, and typing indicator are unchanged.
- Replace hardcoded app bar title `"Acme Engineering Assistant"` with `title ?? "Acme Engineering Assistant"`

**Patterns to follow:**
- Existing `ChatUI.tsx` inline style conventions — no new CSS classes

**Test scenarios:**
- Happy path: when `space="CI-CD"` is passed, the fetch body includes `{ ..., space: "CI-CD" }`
- Happy path: when no `space` prop is given, fetch body omits `space` (or sends `undefined`), preserving current behavior
- Happy path: when `exampleQuestions` prop is provided, `EmptyState` renders those questions instead of `STARTER_QUESTIONS`
- Happy path: when `title="CI/CD Assistant"` is passed, the app bar shows "CI/CD Assistant"
- Edge case: when `exampleQuestions` is an empty array, `ChatUI` falls back to `STARTER_QUESTIONS` before passing to `EmptyState` (fallback logic is in ChatUI, not EmptyState)
- Regression: `ChatUI` rendered with no props behaves identically to before this change

**Verification:**
- ChatUI renders with no props — behavior identical to before (no regression)
- ChatUI renders with all three props — title, questions, and space prop are reflected correctly

---

- [ ] **Unit 3: API — optional `space` filter on `/api/chat`**

**Goal:** Allow the hybrid search to be restricted to a specific team's documents by accepting an optional `space` parameter.

**Requirements:** R12

**Dependencies:** Unit 1 (space values are defined there, but this unit only needs the concept)

**Files:**
- Modify: `app/app/api/chat/route.ts`
- Modify: `schema.sql` (add B-tree index on `space` column)

**Approach:**
- Extend `RequestBody` to include `space?: string`
- Extract `space` from the destructured body alongside `message` and `history`
- Pass `space` to `hybridSearch`; update its signature to `hybridSearch(query, embedding, space?: string)`
- When `space` is provided and non-empty, use a separate SQL string with in-CTE filters; `$3` = space value. Do NOT add a post-CTE outer `WHERE` (see Key Technical Decisions — this is a retrieval quality risk).
- When `space` is absent, empty string, or `null` (runtime JSON), use the existing SQL string unchanged. Validate with `typeof space === "string" && space.length > 0` before branching.
- Use two distinct SQL strings (one with filter, one without) rather than a single string with `OR $3 IS NULL` — two strings are more auditable and avoids subtle query plan differences.
- `space` must always be passed as positional parameter `$3`, never string-interpolated.

**Patterns to follow:**
- Existing `hybridSearch` SQL CTE structure in `route.ts`

**Technical design note (directional):**

```
-- When space is provided:
bm25_results AS (
  SELECT id, paradedb.score(id) AS bm25_score, ROW_NUMBER() ...
  FROM documents
  WHERE documents @@@ paradedb.parse($1)
    AND space = $3          -- added
  LIMIT 50
),
vector_results AS (
  SELECT id, 1 - (embedding <=> $2::vector) AS vec_score, ROW_NUMBER() ...
  FROM documents
  WHERE space = $3          -- added
  ORDER BY embedding <=> $2::vector
  LIMIT 50
),
...
```

**Important implementation notes for the space filter SQL:**

1. `bm25_results` already has `WHERE documents @@@ paradedb.parse($1)` — add `AND space = $3` to this clause.
2. `vector_results` has **no existing `WHERE` clause** — add `WHERE space = $3` as a new clause before `ORDER BY`. Do NOT write `AND space = $3` (no prior WHERE to AND onto).
3. Before committing to the two-SQL-strings approach, test `WHERE (documents @@@ paradedb.parse($1)) AND space = $3` against the live DB. ParadeDB may error if the planner tries to push the `space` predicate into the BM25 executor since `space` is not in the BM25 index. If this happens, the fallback is to apply space filtering as a post-BM25 `WHERE` on the `bm25_results` outer query — but not as a post-CTE outer filter (retrieval quality risk). Add `CREATE INDEX ON documents(space)` to `schema.sql` in this unit as well.

**Test scenarios:**
- Happy path: `POST /api/chat` with `{ message: "...", space: "CI-CD" }` restricts retrieved docs to `space = "CI-CD"`
- Happy path: `POST /api/chat` with `{ message: "..." }` (no space) returns results from all documents — existing behavior unchanged
- Edge case: `space: ""` (empty string) is treated as no filter — searches all documents
- Error path: `space` field present but SQL filter returns zero rows → returns `"I don't have information about this."` (existing no-results path)

**Verification:**
- TypeScript compiles; `RequestBody` type updated
- Existing request body `{ message, history }` with no `space` continues to work correctly

---

- [ ] **Unit 4: Sidebar component + shell layout**

**Goal:** Add a persistent left sidebar to all user-facing pages via a Next.js App Router route group layout.

**Requirements:** R1, R2, R3

**Dependencies:** Unit 1

**Files:**
- Create: `app/components/Sidebar.tsx`
- Create: `app/app/(shell)/layout.tsx`
- Delete or move: `app/app/page.tsx` → `app/app/(shell)/page.tsx` (handled in Unit 5; this unit creates the shell directory and layout)

**Approach:**

*Sidebar component (`components/Sidebar.tsx`):*
- `"use client"` — needs `usePathname()` for active-state detection
- Renders a vertical nav: a "Home" link at the top, then one link per entry in `TEAMS`
- Each nav item shows `team.label` (primary) and `team.description` (secondary, smaller text)
- Active item: compare `usePathname()` to `/` (home) or `/${team.slug}` (team pages); highlight with `var(--blue)` text and a left accent border or background
- Width: 240px, background `var(--surface)`, right border `1px solid var(--border)`
- Use Next.js `<Link>` for navigation

*Shell layout (`(shell)/layout.tsx`):*
- Server component (no `"use client"`)
- Flex row: `<Sidebar />` at 240px, `<main style={{ flex: 1, overflow: "hidden" }}>` for children
- Height: `height: "100vh"` on the outer flex container
- The `ChatUI` component's root div uses `height: "100%"` and its message list uses `flex: 1; overflow-y: auto`. The overflow chain must be: `100vh` outer → `flex: 1; overflow: hidden` main → `height: 100%` ChatUI root → `flex: 1; overflow-y: auto` message list. Any break in this chain causes unbounded growth. Remove the `height: "100vh"` wrapper from the existing `app/app/page.tsx` render — that is now provided by the shell layout.

*ChatUI app bar with sidebar:* `ChatUI` currently has a 56px internal app bar (title + "internal · confidential" badge). With a sidebar present, this bar is still useful as a per-page identity element showing the team name. Keep it. It spans the `<main>` area only (not the sidebar), which is the correct behavior. No change needed to the app bar component itself beyond the `title` prop added in Unit 2.

**Note on intermediate state:** After creating `(shell)/layout.tsx` (Unit 4) but before creating `(shell)/page.tsx` and deleting the old `page.tsx` (Unit 5), the old `page.tsx` at `app/app/page.tsx` is still the route handler for `/`. It will render without the sidebar shell since it is not inside the route group. Do not test or run `next dev` between Unit 4 and Unit 5 — the app will appear visually broken at this midpoint.

**Patterns to follow:**
- Inline style props with CSS custom properties (see ChatUI.tsx for color/shadow tokens)
- `usePathname` pattern from `next/navigation`

**Test scenarios:**
- Happy path: sidebar renders "Home" link and all 3 team links
- Happy path: on `/`, the "Home" nav item is visually active
- Happy path: on `/cicd`, the "CI/CD" nav item is visually active and "Home" is not
- Happy path: sidebar is present on both home page and team pages (rendered by the layout)
- Happy path: clicking a sidebar link navigates to the correct URL

**Verification:**
- Sidebar visible at 240px on left; main content occupies remaining width; no horizontal scroll
- Chat message list scrolls correctly within the viewport (overflow chain intact); no unbounded content growth

---

- [ ] **Unit 5: Home landing page**

**Goal:** Replace the current single-page ChatUI with an informational home page that explains the tool, provides an onboarding guide, and links to team pages.

**Requirements:** R4, R5, R6, R7

**Dependencies:** Unit 4 (shell layout must exist first), Unit 1

**Files:**
- Create: `app/app/(shell)/page.tsx`  ← replaces the top-level `app/app/page.tsx`
- Delete: `app/app/page.tsx` (or its content becomes the new `(shell)/page.tsx`)

**Approach:**
- Server component — no interactivity needed
- Two main sections:
  1. **What is this tool** — short description of the RAG chatbot: what knowledge it searches (Confluence pages, Jira tickets, runbooks), how sources are cited, what kinds of questions work well
  2. **Getting started guide** — numbered or bulleted tips: how to write good questions, what the source chips mean, what "I don't have information about this" means, who to contact if results are poor
- Below the two sections: a grid of team cards, one per entry in `TEAMS`, each showing `team.label`, `team.description`, and a "Go to [team] chat →" link to `/${team.slug}`
- Use existing CSS design tokens; center content with `maxWidth: 720px, margin: "0 auto"`; comfortable vertical padding
- **Tailwind preflight is active** via `globals.css` `@import "tailwindcss"`. It resets margins, padding, and list styles on semantic elements (`<h2>`, `<ul>`, `<a>`, etc.). Explicitly set `margin`, `padding`, and `listStyle` via inline styles on any semantic elements used — do not assume browser defaults will apply.
- The current `page.tsx` has a `maxWidth: 860px` centering wrapper around `ChatUI`. That wrapper is not needed in the shell (ChatUI handles its own `maxWidth: 820px` centering internally). Do not carry this wrapper into the shell's `<main>` — it is a page-level concern that becomes redundant once the shell layout controls the container.

**Patterns to follow:**
- Inline style props; CSS custom properties from `globals.css`
- EmptyState section in `ChatUI.tsx` for card/button styling patterns

**Test scenarios:**
- Happy path: page renders both the "what is this" section and the "getting started" section
- Happy path: team cards render one per TEAMS entry; each links to correct `/${team.slug}` URL
- Happy path: no chat input or ChatUI component is present on the page

**Verification:**
- `/` renders home content without a chat interface; team links navigate to the correct pages

---

- [ ] **Unit 6: Team chat pages (dynamic route)**

**Goal:** Implement the per-team chat pages using a single dynamic route that looks up the team config by slug and renders a scoped ChatUI.

**Requirements:** R8, R9, R10, R11, R14

**Dependencies:** Unit 4 (shell layout), Unit 2 (ChatUI props)

**Files:**
- Create: `app/app/(shell)/[team]/page.tsx`

**Approach:**
- Server component: receives `params: { team: string }` from Next.js
- Look up team: `const teamConfig = getTeamBySlug(params.team)`
- If `teamConfig` is `undefined`, call `notFound()` (triggers Next.js 404 page)
- **Next.js 15 requires `params` to be awaited**: the page must be `async` and destructure `params` via `await`. The correct pattern is `async function TeamPage({ params }: { params: Promise<{ team: string }> })` with `const { team } = await params`. Synchronous access to `params.team` will produce `undefined` at runtime, causing every valid slug to hit `notFound()`.
- Otherwise render `<ChatUI space={teamConfig.space} title={teamConfig.label + " Assistant"} exampleQuestions={teamConfig.exampleQuestions} />`
- Export `generateStaticParams()` returning `TEAMS.map(t => ({ team: t.slug }))` — this is required, not optional. Team slugs are known at build time from config; static pre-rendering is the correct choice and avoids an unnecessary dynamic render on first visit.
- Export `export const metadata` or use `generateMetadata` to set a per-page `<title>` (e.g., `"CI/CD Assistant — Acme Engineering"`). The root `layout.tsx` has a static title; team pages must override it.

**Patterns to follow:**
- `notFound()` import from `next/navigation`
- Existing `page.tsx` pattern (server component, simple render)

**Test scenarios:**
- Happy path: `/cicd` renders ChatUI with `space="CI-CD"`, title "CI/CD Assistant", and CI/CD example questions
- Happy path: `/infra` renders ChatUI with `space="INFRA"` and infra example questions
- Happy path: `/eng-env` renders ChatUI with `space="ENG-ENV"` and eng-env example questions
- Error path: `/unknown-team` renders a 404 (not a crash or blank page)
- Integration: a question asked on `/cicd` page sends `{ ..., space: "CI-CD" }` to `/api/chat`

**Verification:**
- All three team URLs render chat UIs; unknown slugs return 404; each chat sends correct space in API request

---

## System-Wide Impact

- **Interaction graph:** `(shell)/layout.tsx` wraps all user-facing pages. The root `layout.tsx` is untouched. No middleware, observers, or callbacks affected.
- **Error propagation:** Unknown team slugs call `notFound()` — handled by Next.js error boundary; no unhandled exceptions. API `space` filter failure (bad SQL) surfaces through the existing `catch` block in `POST /api/chat`.
- **State lifecycle risks:** `ChatUI` state (messages, loading) is local to each page mount. Navigating between team pages resets the chat — intentional, since different spaces are different conversations. No shared state to clean up.
- **API surface parity:** The `space` field is additive and optional. Existing callers sending `{ message, history }` continue to work unchanged. The `RequestBody` type change is backward-compatible.
- **Integration coverage:** The critical cross-layer scenario is: team page → `space` prop → ChatUI fetch body → API `space` filter → SQL in-CTE `WHERE space = $3`. This chain can only be verified end-to-end after Units 2, 3, and 6 are all complete — it is a post-Unit-6 integration verification step, not an intermediate one.
- **Unchanged invariants:** The hybrid search (BM25 + vector + RRF + reranker) pipeline is unchanged in structure; the space filter is additive. The existing `/api/chat` request/response contract (`{ answer, sources }`) is unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Current data has `space = "ENG"` for all Confluence docs; Jira/docs have no `space` value. Team pages will return **no results** for scoped queries until re-ingestion. | Do not expose team pages to users before re-ingestion, or add a visible "knowledge not yet loaded" notice per team page. Plan ingestion pipeline work concurrently — it is a prerequisite for team scoping to deliver any value. |
| ParadeDB `paradedb.parse($1) AND space = $3` exact syntax may vary. | Resolve during implementation by testing against the running DB. The requirement is in-CTE filtering — the exact operator form is an implementation detail. Post-CTE fallback is not acceptable (retrieval quality risk). |
| No B-tree index on `documents(space)` in schema.sql. | Add `CREATE INDEX ON documents(space)` to `schema.sql` during implementation. Low-effort, prevents sequential scans as document count grows. |
| SQL injection via space value if ever string-interpolated. | `space` must always be `$3` positional parameter. Validated server-side before SQL branch. Never template-literal-interpolated. |
| Replacing `app/app/page.tsx` with `(shell)/page.tsx` must be done carefully — both cannot coexist as route handlers for `/`. | Delete the old `page.tsx` when creating `(shell)/page.tsx`. The move is atomic; Next.js will resolve `/` to `(shell)/page.tsx` once the old file is removed. |
| `ChatUI.tsx` is 587 lines and has hardcoded constants. Adding props without regression requires care. | All prop additions are additive with defaults (`?? STARTER_QUESTIONS`, `?? "Acme Engineering Assistant"`). Existing render path (no props) is exercised by: render ChatUI with no props, verify it matches pre-change behavior. |

## Documentation / Operational Notes

- Update `README.md` to describe the multi-page structure and the team onboarding process (edit `lib/teams.ts`, re-ingest with matching `space` value).
- The ingestion pipeline (`ingestion/`) must be updated separately to set `space` values per team on ingested documents. This is out of scope for this plan but is a prerequisite for team filtering to be meaningful.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-29-multi-page-frontend-requirements.md](../brainstorms/2026-03-29-multi-page-frontend-requirements.md)
- Related code: `app/components/ChatUI.tsx`, `app/app/api/chat/route.ts`, `app/lib/db.ts`, `app/app/layout.tsx`, `schema.sql`
- Next.js 15 App Router route groups: https://nextjs.org/docs/app/building-your-application/routing/route-groups
