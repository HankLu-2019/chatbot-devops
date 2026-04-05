---
title: "feat: Add New Conversation button and history cap"
type: feat
status: completed
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-conversation-history-requirements.md
---

# feat: Add New Conversation Button and History Cap

## Overview

The multi-turn RAG pipeline is already fully functional — history is sent to the API, query rewriting uses prior context, and Gemini receives the conversation. Two small gaps remain: no way to reset the chat without refreshing, and no cap on history length for long sessions.

## Problem Frame

History is in-memory React state that disappears on refresh (correct by design). Users have no in-app way to start fresh, and very long sessions send unbounded history to Gemini on every turn (see origin: `docs/brainstorms/2026-03-30-conversation-history-requirements.md`).

## Requirements Trace

- R1. Session-only history — already implemented; no change needed
- R2. "New conversation" button in app bar clears all messages
- R3. History capped at last 10 messages sent to the API

## Scope Boundaries

- No server-side history storage
- No conversation export
- Cap is silent — no UI indicator

## Context & Research

### Relevant Code and Patterns

- `app/components/ChatUI.tsx:344` — `buildHistory()` returns `messages.map(...)` — needs a `slice(-10)` cap
- `app/components/ChatUI.tsx:330` — `const [messages, setMessages] = useState<Message[]>([])` — "New conversation" calls `setMessages([])`
- `app/components/ChatUI.tsx:409` — app bar section where the "New conversation" button should live (right side, next to "internal · confidential" badge)

## Key Technical Decisions

- **Cap in `buildHistory()`**: The cap belongs in `buildHistory()`, not in the state itself. State preserves the full visible conversation; only the payload sent to the API is trimmed. This avoids a jarring truncation of the on-screen chat.
- **"New conversation" resets state only**: Calls `setMessages([])` and `setInput("")`. No API call, no navigation.

## Implementation Units

- [x] **Unit 1: Cap history at 10 messages in `buildHistory()`**

**Goal:** Limit the history array sent to `/api/chat` to the last 10 messages.

**Requirements:** R3

**Dependencies:** None

**Files:**
- Modify: `app/components/ChatUI.tsx`

**Approach:**
- In `buildHistory()`, change `messages.map(...)` to `messages.slice(-10).map(...)`
- The visible message list in the UI is unchanged — only the API payload is capped

**Test scenarios:**
- Happy path: after 4 turns (8 messages), all 8 are sent in history
- Edge case: after 6 turns (12 messages), only the last 10 are sent
- Edge case: `buildHistory()` called with 0 messages returns `[]`

**Verification:** A fetch payload inspection (browser devtools Network tab) shows `history.length <= 10` even in long sessions.

---

- [x] **Unit 2: Add "New conversation" button to app bar**

**Goal:** Clicking the button resets the chat to empty state without a page reload.

**Requirements:** R2

**Dependencies:** Unit 1

**Files:**
- Modify: `app/components/ChatUI.tsx`

**Approach:**
- Add a button in the app bar (right side, before the "internal · confidential" badge) labelled "New conversation" or showing a reset icon
- `onClick`: call `setMessages([])` and `setInput("")`
- Disable the button while `loading` is true (prevents clearing during an in-flight request)
- Style consistently with the app bar's existing icon/badge style — small, unobtrusive

**Patterns to follow:** App bar layout in `ChatUI.tsx:409` — the existing badge uses `var(--mono)` font, `var(--surface-2)` background, `var(--border)` border.

**Test scenarios:**
- Happy path: button visible in app bar on all chat pages (team pages and `/search`)
- Happy path: clicking with messages present returns to empty state (example questions shown)
- Happy path: clicking with 0 messages has no visible effect (already empty)
- Edge case: button is disabled/non-interactive while a response is loading
- Happy path: after clearing, a new question submits successfully

**Verification:** Clicking "New conversation" mid-conversation shows the empty state with example questions.

## System-Wide Impact

- **Unchanged invariants:** The API contract, session behavior, and team-scoped vs. global search are all unaffected.
- **State lifecycle:** `setMessages([])` is the only state mutation — no risk of stale closures or partial resets since `loading` is guarded.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Accidental clear during in-flight request | Button disabled while `loading === true` |
| `buildHistory()` cap discards early context in a long helpful session | Cap is 10 messages (5 turns) — sufficient context for any realistic follow-up chain; cost/latency benefit justifies it |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-30-conversation-history-requirements.md](../brainstorms/2026-03-30-conversation-history-requirements.md)
- Related code: `app/components/ChatUI.tsx:330` (state), `app/components/ChatUI.tsx:344` (buildHistory), `app/components/ChatUI.tsx:409` (app bar)
