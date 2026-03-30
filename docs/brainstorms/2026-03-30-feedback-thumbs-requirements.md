---
date: 2026-03-30
topic: feedback-thumbs
---

# Feedback / Thumbs Up-Down

## Problem Frame

There is currently no signal on answer quality. Thumbs feedback gives a lightweight way to identify which questions produce bad answers, which teams have knowledge gaps, and which retrieval patterns should be improved.

## Requirements

**UI**
- R1. A thumbs up / thumbs down pair appears at the bottom of every assistant message bubble, below the sources section.
- R2. The thumbs are subtle (icon-only, no label) until interacted with. On hover, they become slightly more prominent.
- R3. After clicking a thumb, the selected thumb fills/highlights in the active color; the other dims. The selection is locked — the user cannot change their vote.
- R4. Feedback is not shown on "I don't have information about this." answers — those are already a known signal and don't benefit from thumbs.

**Data**
- R5. Votes are persisted to a `feedback` table in the existing PostgreSQL database. No separate service is required.
- R6. Each row stores: `id`, `created_at`, `space` (team space or null for global search), `question` (the user's original message), `vote` (`up` or `down`).
- R7. A new `POST /api/feedback` endpoint accepts `{ messageId, space, question, vote }` and inserts a row. It responds with `200 OK` on success; on failure the frontend silently swallows the error (feedback loss is acceptable over disrupting the user).

**Schema**
- R8. A new migration adds the `feedback` table:
  ```sql
  CREATE TABLE IF NOT EXISTS feedback (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    space      TEXT,
    question   TEXT NOT NULL,
    vote       TEXT NOT NULL CHECK (vote IN ('up', 'down'))
  );
  ```

## Success Criteria

- Clicking a thumb immediately highlights the selection and fires a request to `/api/feedback`.
- A row appears in the `feedback` table with the correct space, question, and vote.
- Clicking the already-selected thumb does nothing (locked after first vote).
- "I don't have info" answers show no thumbs.

## Scope Boundaries

- No feedback analytics dashboard or reporting UI.
- No ability to change or retract a vote.
- No user identity stored — votes are anonymous.
- Feedback failures are silent; they do not surface errors to the user.

## Key Decisions

- **Persist to DB over console log:** Enables future analysis of which team spaces produce low-quality answers; low carrying cost given the existing DB.
- **Lock after first vote:** Simpler state management; prevents accidental double-votes.

## Dependencies / Assumptions

- The `schema.sql` (or a new migration file) must be applied before the feature is usable. Ingestion is unaffected.

## Next Steps
→ `/ce:plan` for structured implementation planning
