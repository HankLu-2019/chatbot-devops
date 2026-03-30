---
date: 2026-03-30
topic: cross-team-search
---

# Cross-Team Search

## Problem Frame

Users often don't know which team owns the answer to their question (e.g. "why is my deploy slow?" spans CI/CD and Infrastructure). The current app forces users to pick a team page before asking, which loses answers that live across boundaries. A global search mode lets users ask without pre-selecting a team.

## User Flow

```mermaid
flowchart TB
    A[User opens app] --> B{Knows which team?}
    B -- Yes --> C[Navigate to team page\n/cicd, /infra, /eng-env]
    B -- No --> D[Click 'Search All Teams'\nin sidebar]
    D --> E[/search page\nwith cross-team examples]
    E --> F[User types question]
    F --> G[Answer returned\nwith team attribution\nin prose]
    G --> H{Follow-up?}
    H -- Yes --> F
    H -- No --> I[Done]
```

## Requirements

**Routing & Navigation**
- R1. A new `/search` route renders a full chat page identical in layout to team pages (sidebar + main chat area).
- R2. The sidebar shows a "Search All Teams" link, visually separated from the three team links (e.g. a divider above it). It highlights as active when on `/search`.

**Search Behavior**
- R3. Queries on `/search` retrieve from all team spaces with no space filter applied.
- R4. The system prompt for global search mandates that the model name the owning team in the answer prose for every source cited (e.g. "according to the CI/CD team's pipeline guide…"). This is required, not best-effort. *(Depends on schema/mapping questions in Outstanding Questions.)*
- R5. Source chips below the answer still render as on team pages — no additional team badge on the chip itself. The mandatory prose attribution (R4) is the only team signal.

**Empty State**
- R6. Before the first message, the page shows a short description ("Ask anything across all three engineering knowledge bases") and 3–4 clickable example questions that span multiple teams. Clicking an example question populates the input and submits the query immediately.

**Example questions (starting set):**
- "Why is my deploy slow?"
- "How does a change go from PR to production?"
- "What should I check when something is broken in staging?"
- "Who handles VPN access versus Kubernetes access?"

## Success Criteria

- A question whose answer spans two team spaces returns a coherent single answer with prose attribution to both teams.
- The "Search All Teams" sidebar link is immediately findable and highlights correctly on `/search`.
- Clicking an example question submits it and returns an answer (no errors, no empty state).
- Team pages are unaffected — their space-scoped behavior is unchanged.

## Scope Boundaries

- No changes to team page behavior or the existing scoped query path. The global search reuses the existing `/api/chat` endpoint with no `space` parameter — it does not require a new endpoint.
- No UI grouping of sources by team — attribution lives in prose only.
- No search history persistence across sessions.

## Key Decisions

- **Dedicated `/search` page over home-page toggle:** Cleaner separation; keeps the home page as a directory rather than a chat interface.
- **Prose attribution over source chip badges:** Feels more natural in a conversational answer; chip badges would add rendering complexity for marginal gain.

## Outstanding Questions

### Deferred to Planning
- [Affects R4][Technical] The `space` value (e.g. `CI-CD`) needs to map to a human-readable team label for the system prompt. Confirm the mapping is derivable from `lib/teams.ts` at build/request time without duplicating data.
- [Affects R3][Technical] The SQL `SELECT` likely needs to include the `space` column so the API can pass team labels into Gemini's context. Verify schema and query changes needed.

## Next Steps
→ `/ce:plan` for structured implementation planning
