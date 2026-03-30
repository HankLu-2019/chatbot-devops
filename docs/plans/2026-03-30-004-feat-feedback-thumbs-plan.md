---
title: "feat: Add thumbs up/down feedback with DB persistence"
type: feat
status: active
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-feedback-thumbs-requirements.md
---

# feat: Add Feedback Thumbs (DB-Persisted)

## Overview

Add thumbs up/down icons to every assistant answer bubble. Votes persist to a new `feedback` table in PostgreSQL via a new `POST /api/feedback` endpoint. Feedback is anonymous, locked after first vote, and silent on failure.

## Problem Frame

There is no quality signal on answers today. Thumbs feedback allows identification of knowledge gaps per team space and retrieval quality issues over time (see origin: `docs/brainstorms/2026-03-30-feedback-thumbs-requirements.md`).

## Requirements Trace

- R1. Thumbs appear below every assistant answer, after sources
- R2. Subtle icon-only display; slightly more prominent on hover
- R3. Clicking locks selection (filled active, other dims); no re-vote
- R4. Hidden on "I don't have information about this." answers
- R5. Votes persist to `feedback` table in PostgreSQL
- R6. Row stores: `id`, `created_at`, `space`, `question`, `vote`
- R7. `POST /api/feedback` endpoint; silent failure on frontend
- R8. `feedback` table added to `schema.sql`

## Scope Boundaries

- No analytics dashboard
- No vote retraction
- No user identity stored
- Frontend errors are silently swallowed

## Context & Research

### Relevant Code and Patterns

- `app/components/ChatUI.tsx:149` — `AssistantMessage` renders answer + sources; thumbs go below sources section
- `app/components/ChatUI.tsx:18` — `Message` interface — add `question?: string` to associate the user's question with each assistant message (needed when submitting feedback)
- `app/components/ChatUI.tsx:348` — `sendMessage` creates the assistant `Message` — store `question: text.trim()` on the assistant message object
- `app/components/ChatUI.tsx:29` — `NO_INFO_ANSWER` constant — already used to set `noInfo` flag; R4 hides thumbs when `noInfo === true`
- `app/app/api/chat/route.ts` — existing API route pattern; `POST /api/feedback` follows the same shape
- `app/lib/db.ts` — `pool` import pattern for DB queries
- `schema.sql` — uses `CREATE TABLE IF NOT EXISTS`; add `feedback` table there

### Resolved Questions

- **How does the frontend know the `question` for an assistant message?** Store `question: string` on the assistant `Message` object at creation time in `sendMessage`. The question is the `text` parameter passed to `sendMessage`.
- **Where does `space` come from on the frontend?** `ChatUI` already receives `space` as a prop. Pass it through when submitting feedback.

## Key Technical Decisions

- **`question` on assistant `Message`**: Store the original user question on the assistant message object when it's created. This avoids state-scanning logic to find the preceding user message and is safe even if messages are re-ordered.
- **Fire-and-forget `fetch` for feedback**: `POST /api/feedback` is called without `await` in the vote handler. Errors are caught and suppressed. This keeps the UI interaction instant.
- **`schema.sql` for migration**: No migration runner exists. The `feedback` table is added to `schema.sql` with `CREATE TABLE IF NOT EXISTS`. Existing deployments require a one-time manual `docker compose exec paradedb psql ... -c "CREATE TABLE IF NOT EXISTS feedback ..."` or a full DB re-init.

## Implementation Units

- [ ] **Unit 1: Add `feedback` table to `schema.sql`**

**Goal:** Define the `feedback` table so it is created on next DB init.

**Requirements:** R5, R6, R8

**Dependencies:** None

**Files:**
- Modify: `schema.sql`

**Approach:**
- Append after the existing index definitions:
  ```sql
  CREATE TABLE IF NOT EXISTS feedback (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    space      TEXT,
    question   TEXT NOT NULL,
    vote       TEXT NOT NULL CHECK (vote IN ('up', 'down'))
  );
  ```

**Test expectation: none** — DDL-only change; verified by inspecting the table after DB init.

**Verification:** `\dt` in psql shows `feedback` table; `\d feedback` shows correct columns and constraint.

---

- [ ] **Unit 2: Create `POST /api/feedback` endpoint**

**Goal:** Accept a vote payload and insert a row into `feedback`.

**Requirements:** R5, R6, R7

**Dependencies:** Unit 1

**Files:**
- Create: `app/app/api/feedback/route.ts`
- Test: none (fire-and-forget endpoint; verified via DB inspection)

**Approach:**
- Parse JSON body: `{ space?: string, question: string, vote: 'up' | 'down' }` (ignore `messageId` — not stored)
- Validate `vote` is `'up'` or `'down'`; return 400 on invalid input
- `INSERT INTO feedback (space, question, vote) VALUES ($1, $2, $3)`
- Return `200 OK` on success; return `500` on DB error (frontend silently swallows non-200)
- Import `pool` from `@/lib/db`

**Patterns to follow:** `app/app/api/chat/route.ts` — same `NextRequest`/`NextResponse` pattern, same `pool.connect()` / `client.release()` pattern.

**Test scenarios:**
- Happy path: valid `{ space: 'CI-CD', question: 'How do I deploy?', vote: 'up' }` → 200; row appears in DB
- Happy path: `space` is `null`/omitted (global search) → 200; row inserted with `space = null`
- Error path: `vote` value outside `('up', 'down')` → 400
- Error path: missing `question` field → 400
- Integration: row in `feedback` table has correct `space`, `question`, `vote` after a successful call

**Verification:** `curl -X POST /api/feedback` with valid body returns 200; `SELECT * FROM feedback` shows the row.

---

- [ ] **Unit 3: Add thumbs UI to `AssistantMessage`**

**Goal:** Thumbs icons appear below assistant answers; clicking submits a vote and locks the selection.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Unit 2

**Files:**
- Modify: `app/components/ChatUI.tsx`

**Approach:**
- Add `question?: string` to `Message` interface
- In `sendMessage`, set `question: text.trim()` on the assistant message object when creating it
- Add `vote: 'up' | 'down' | null` to `AssistantMessage` props (controlled from parent via `onVote` callback), or use local `useState` in `AssistantMessage`
  - **Prefer local state**: `const [vote, setVote] = useState<'up'|'down'|null>(null)`. Avoids threading vote state through the message list.
- Add a thumbs row below the sources divider in `AssistantMessage`, hidden when `noInfo === true`
- Two icon buttons: thumbs-up SVG and thumbs-down SVG
- Hover: slightly increase opacity or show color
- On click: set local `vote` state; fire `fetch('/api/feedback', { method: 'POST', ... })` without await; catch and swallow errors
- When `vote !== null`: disable both buttons; active thumb fills with `var(--green)` (up) or `var(--red)` (down); inactive thumb dims to `var(--text-3)`
- `space` and `question` passed as props from the parent message object

**Patterns to follow:**
- Send button SVG icon style in `ChatUI.tsx:546` for consistent icon sizing
- Hover state pattern using `onMouseEnter`/`onMouseLeave` inline styles

**Test scenarios:**
- Happy path: thumbs-up and thumbs-down icons visible below a normal assistant answer
- Happy path: icons not visible when `noInfo === true`
- Happy path: clicking thumbs-up fills it green, dims thumbs-down, disables both
- Happy path: clicking thumbs-down fills it red, dims thumbs-up, disables both
- Edge case: clicking the already-selected thumb (after a vote) does nothing (buttons disabled)
- Integration: clicking a thumb fires a POST to `/api/feedback` with correct `space`, `question`, `vote`
- Error path: `/api/feedback` returns 500 — no UI error shown; thumb stays in selected state

**Verification:** Thumb selection visible on click; DB row inserted; no errors on re-click or API failure.

## System-Wide Impact

- **Interaction graph:** `AssistantMessage` gains a local vote state and a fire-and-forget fetch. No parent state change.
- **Error propagation:** Feedback failures are caught and swallowed — they do not propagate to the UI or affect the message state.
- **Unchanged invariants:** Answer text, sources, and the RAG pipeline are unaffected. `Message` type gains an optional `question` field — existing message creation sites that don't set it are unaffected.
- **API surface parity:** `POST /api/feedback` is a new endpoint; `POST /api/chat` is unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `feedback` table not created on existing deployments | Document the one-time `CREATE TABLE IF NOT EXISTS feedback (...)` command in operational notes |
| Large `question` text in DB | `question TEXT NOT NULL` has no length limit; acceptable for this use case |
| Anonymous votes make abuse detection impossible | Acceptable — internal tool with no external access |

## Documentation / Operational Notes

- **Existing deployments**: The `feedback` table will not be auto-created because `schema.sql` only runs on a fresh DB init. Run the DDL from Unit 1 manually against the running ParadeDB container:
  ```
  docker compose exec paradedb psql -U postgres -d ragdb -c "CREATE TABLE IF NOT EXISTS feedback (...)"
  ```
- **Querying feedback**: `SELECT space, vote, COUNT(*) FROM feedback GROUP BY space, vote ORDER BY space;`

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-30-feedback-thumbs-requirements.md](../brainstorms/2026-03-30-feedback-thumbs-requirements.md)
- Related code: `app/components/ChatUI.tsx:149` (AssistantMessage), `app/app/api/chat/route.ts` (API pattern), `schema.sql`, `app/lib/db.ts`
