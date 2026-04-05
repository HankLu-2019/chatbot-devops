---
date: 2026-03-30
topic: conversation-history
---

# Conversation History (Multi-Turn)

## Problem Frame

Users need to ask follow-up questions in the same session without re-stating context ("what about INFRA instead?" after asking a CI/CD question). The core multi-turn capability is already implemented — history is sent to the API, query rewriting uses prior context, and Gemini receives the full prior conversation. The remaining gap is UX: users currently have to refresh the page to start a fresh conversation.

## Requirements

- R1. Conversation history is session-only — stored in React component state (in-memory). History is cleared automatically when the user refreshes the page or navigates away. No persistence to localStorage or a backend.
- R2. A "New conversation" button appears in the app bar. Clicking it resets the chat to the empty state (clears all messages).
- R3. History sent to the API is capped at the last 10 messages (5 user + 5 assistant turns) to bound cost and latency as sessions grow long.

## Success Criteria

- A follow-up question like "what about INFRA?" after a CI/CD answer correctly resolves the reference and returns an INFRA-scoped result.
- Clicking "New conversation" clears the chat and returns to the empty state.
- After a page refresh, the chat starts fresh with no prior messages.

## Scope Boundaries

- No server-side history storage.
- No conversation export or copy feature.
- The history cap (R3) applies silently — no UI indicator of truncation.

## Next Steps
→ `/ce:plan` for structured implementation planning
