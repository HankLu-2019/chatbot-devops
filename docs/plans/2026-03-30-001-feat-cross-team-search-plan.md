---
title: "feat: Add cross-team global search page"
type: feat
status: completed
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-cross-team-search-requirements.md
---

# feat: Add Cross-Team Global Search Page

## Overview

Add a dedicated `/search` page that queries across all team spaces with no filter, plus a "Search All Teams" sidebar entry. The system prompt for global search mandates team attribution in the answer prose so users know which team owns each cited source.

## Problem Frame

Users who don't know which team owns the answer currently have to guess a team page first. A `/search` page removes that friction and surfaces cross-boundary answers (see origin: `docs/brainstorms/2026-03-30-cross-team-search-requirements.md`).

## Requirements Trace

- R1. New `/search` route, full chat layout (sidebar + main area)
- R2. Sidebar "Search All Teams" link with divider, highlights active on `/search`
- R3. Queries on `/search` use no `space` filter
- R4. System prompt mandates team name attribution in prose for every source
- R5. Source chips unchanged — no team badge on chips
- R6. Cross-team example questions in empty state; clicking submits immediately

## Scope Boundaries

- No new API endpoint — reuses `/api/chat` without `space` param
- No source chip team badges
- Team pages behavior unchanged

## Context & Research

### Relevant Code and Patterns

- `app/app/(shell)/[team]/page.tsx` — pattern to follow for the new `/search` page (server component, passes props to `<ChatUI>`)
- `app/components/ChatUI.tsx` — accepts `space?: string`, `title?: string`, `exampleQuestions?: string[]`; omitting `space` already triggers global search in `route.ts`
- `app/components/Sidebar.tsx` — `NavItem` component with `active` prop; `usePathname()` for active detection; "Teams" section label pattern to follow for divider
- `app/app/api/chat/route.ts:118` — `hybridSearch()` already branches on `space` presence; no code change needed there
- `app/app/api/chat/route.ts:266` — `generateAnswer()` `systemPrompt` — needs a second variant for global search with team attribution instruction
- `app/lib/teams.ts` — `TEAMS` array with `space` and `label` fields; import in `route.ts` to build `space → label` lookup at request time
- `schema.sql` — `documents.space TEXT` column already exists and is indexed; SQL `SELECT` just needs `d.space` added

### Resolved Deferred Questions

- **Space → label mapping**: Build `Map<string, string>` from `TEAMS` at module level in `route.ts` — e.g. `CI-CD → CI/CD`, `INFRA → Infrastructure`. No data duplication.
- **SQL SELECT**: Add `d.space` to the SELECT in both `sqlWithSpace` and `sqlWithoutSpace`. Update `DbRow` interface to include `space: string`.

## Key Technical Decisions

- **Single system prompt variant**: Pass team labels into the context block already sent to Gemini. Add a one-line instruction to the global-search system prompt: "For each source cited, mention the owning team by name." Team labels come from the `space → label` map applied to each `DbRow.space`. No separate generation call.
- **Static page, not dynamic route**: `/search` is a fixed route at `app/app/(shell)/search/page.tsx`, not a dynamic segment, so it doesn't conflict with `[team]` and needs no `generateStaticParams` guard.

## Implementation Units

- [x] **Unit 1: Add `space` to SQL SELECT and `DbRow` type**

**Goal:** `DbRow` carries the team space so the API can include team labels in Gemini's context.

**Requirements:** R3, R4

**Dependencies:** None

**Files:**
- Modify: `app/app/api/chat/route.ts`

**Approach:**
- Add `space: string` to the `DbRow` interface
- Add `d.space` to the SELECT clause in both `sqlWithSpace` and `sqlWithoutSpace` CTE final selects
- No change to query parameters or indexes

**Test scenarios:**
- Happy path: a query with no `space` param returns `DbRow[]` where each row has a `space` value matching the chunk's team
- Happy path: a query with `space='CI-CD'` still returns rows all having `space='CI-CD'`

**Verification:** Running a test query against the DB returns rows with a populated `space` field.

---

- [x] **Unit 2: Build space→label map and update global-search system prompt**

**Goal:** When `space` is absent (global search), Gemini is instructed to name the owning team in prose for every cited source.

**Requirements:** R4, R5

**Dependencies:** Unit 1

**Files:**
- Modify: `app/app/api/chat/route.ts`
- Modify: `app/lib/teams.ts` (no change needed — read-only import)

**Approach:**
- At module level in `route.ts`, build `const SPACE_LABEL_MAP: Map<string, string>` from `TEAMS` (import from `@/lib/teams`)
- In `generateAnswer`, accept an optional `isGlobal: boolean` parameter
- When `isGlobal`, augment each context block with the team label: prepend `[Team: ${SPACE_LABEL_MAP.get(row.space) ?? row.space}]` to each source block
- Add one instruction line to the system prompt: `"For each source you cite, name the owning team explicitly in your answer (e.g., 'according to the CI/CD team's pipeline guide…')."`
- When `isGlobal` is false (team page), system prompt is unchanged

**Test scenarios:**
- Happy path: global query returns answer text containing a team name from `TEAMS` (e.g. "CI/CD" or "Infrastructure")
- Happy path: team-scoped query system prompt does not contain the team attribution instruction
- Edge case: `DbRow.space` value not in `SPACE_LABEL_MAP` falls back to raw space string (e.g. `"CI-CD"`)

**Verification:** A cross-team question returns an answer that mentions at least one team name in the prose.

---

- [x] **Unit 3: Create `/search` static page**

**Goal:** New route at `/search` renders `<ChatUI>` with no space, global title, and cross-team example questions.

**Requirements:** R1, R6

**Dependencies:** Unit 2

**Files:**
- Create: `app/app/(shell)/search/page.tsx`

**Approach:**
- Server component, identical structure to `[team]/page.tsx`
- No `space` prop passed to `<ChatUI>` (omitted = global search)
- `title="Search All Teams"`
- `exampleQuestions` set to the 4 cross-team questions from the requirements doc
- Export `metadata` with title `"Search All Teams — Acme Engineering"`

**Patterns to follow:** `app/app/(shell)/[team]/page.tsx`

**Test scenarios:**
- Happy path: `/search` loads with 200 status, no console errors
- Happy path: empty state shows correct description and 4 example questions
- Happy path: clicking an example question submits it and returns an answer
- Integration: answer text contains a team name attribution (validates R4 end-to-end)
- Edge case: `/search` does not 404 when the `[team]` dynamic segment exists alongside it

**Verification:** Page loads, example questions are clickable, answers reference team names in prose.

---

- [x] **Unit 4: Add "Search All Teams" sidebar link**

**Goal:** Sidebar shows a visually separated "Search All Teams" entry that highlights when on `/search`.

**Requirements:** R2

**Dependencies:** Unit 3

**Files:**
- Modify: `app/components/Sidebar.tsx`

**Approach:**
- After the Teams section, add a divider (`<div style={{ height: '1px', background: 'var(--border)', margin: '4px 8px' }} />`)
- Add a `NavItem` with `href="/search"`, `label="Search All Teams"`, `description="Ask across all knowledge bases"`, `active={pathname === '/search'}`

**Patterns to follow:** Existing `NavItem` usage and "Teams" section label pattern in `Sidebar.tsx`

**Test scenarios:**
- Happy path: sidebar renders "Search All Teams" link on all pages
- Happy path: link is active (blue left border) when pathname is `/search`
- Happy path: link is inactive on team pages and home
- Happy path: clicking navigates to `/search`

**Verification:** Sidebar shows the new link; active state highlights correctly on `/search`.

## System-Wide Impact

- **Unchanged invariants:** All three team pages (`/cicd`, `/infra`, `/eng-env`) and the home page (`/`) are unaffected. The `/api/chat` endpoint contract is unchanged — `space` remains optional.
- **API surface parity:** The `isGlobal` flag in `generateAnswer` is an internal signal, not an API contract change.
- **Error propagation:** If `SPACE_LABEL_MAP` lookup misses a space value, the fallback to raw space string is safe.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Gemini may not consistently follow the team attribution instruction | Instruction is explicit in system prompt; cross-team example questions during QA will verify |
| `/search` route conflicts with `[team]` dynamic segment | Static segments take priority over dynamic segments in Next.js App Router — no conflict |
| `d.space` NULL for legacy chunks ingested before the space column was populated | Schema has `space TEXT` (nullable); `SPACE_LABEL_MAP.get(undefined)` returns `undefined`, falls back to raw space string |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-30-cross-team-search-requirements.md](../brainstorms/2026-03-30-cross-team-search-requirements.md)
- Related code: `app/app/(shell)/[team]/page.tsx`, `app/components/Sidebar.tsx`, `app/app/api/chat/route.ts:266`
