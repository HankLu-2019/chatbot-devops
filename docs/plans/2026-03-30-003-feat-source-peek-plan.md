---
title: "feat: Add source peek panel with snippet and original link"
type: feat
status: completed
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-source-peek-requirements.md
---

# feat: Add Source Peek Panel

## Overview

Source chips currently link to external URLs. A click-to-expand peek panel shows a ~200-character text snippet from the retrieved chunk (acting as an abstract), plus a "View original →" link. The chip gains a separate ↗ icon for direct URL navigation.

## Problem Frame

Users want to verify why a source was cited without navigating away. The retrieved chunk content is already available in the API pipeline — it just needs to be surfaced in the response and rendered in the UI (see origin: `docs/brainstorms/2026-03-30-source-peek-requirements.md`).

## Requirements Trace

- R1. Click chip → toggle peek panel; only one open at a time
- R2. Chip gains a ↗ icon for direct URL open, separate from toggle click target
- R3. Panel shows ~200-char snippet trimmed to word boundary
- R4. Panel has "View original →" link
- R5. Snippet styled as body copy
- R6. API returns `snippet` field per source; derived from existing retrieved data

## Scope Boundaries

- No LLM summaries — verbatim excerpt only
- No copy/share actions
- No changes to retrieval ranking

## Context & Research

### Relevant Code and Patterns

- `app/app/api/chat/route.ts:354` — source assembly loop builds `sources: Source[]`; each `row` has `.content` available at this point — add `snippet: row.content.slice(0, …).trimEnd()`
- `app/app/api/chat/route.ts:33` — `Source` interface: `{ title, url, source_type }` — add `snippet: string`
- `app/components/ChatUI.tsx:8` — `Source` interface — must be updated to match
- `app/components/ChatUI.tsx:67` — `SourceChips` component — split into two click targets per chip; add expand state
- `app/components/ChatUI.tsx:149` — `AssistantMessage` passes `sources` to `SourceChips`

## Key Technical Decisions

- **Snippet trim at word boundary**: `content.slice(0, 220)` then trim back to the last space to avoid mid-word cuts. Cap at 200 visible characters after trim. Simple string operation — no library needed.
- **`openChipIndex: number | null` state in `SourceChips`**: Track which chip is expanded using a local `useState` in `SourceChips`. Opening chip N sets state to N; clicking again (same chip) sets to null. This is isolated to the chip row and does not affect parent state.
- **Two click targets per chip**: The main chip area (title text) toggles the panel. A small `<a>` with the ↗ icon handles URL navigation. The icon `stopPropagation` prevents the toggle from firing on icon click.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification.*

```
Source chip row (before):
  [Confluence badge] [title text (links to URL)]

Source chip row (after):
  [Confluence badge] [title text (toggles panel)] [↗ icon (links to URL)]
  └─ peek panel (conditional):
       │ "To deploy to production, open ArgoCD and..."
       │ [View original →]
```

`SourceChips` state:
- `openIndex: number | null` — which chip's panel is expanded
- Chip click → `setOpenIndex(i === openIndex ? null : i)`
- Icon click → `e.stopPropagation()` then navigate

## Implementation Units

- [x] **Unit 1: Add `snippet` to API response**

**Goal:** API returns a `snippet` field per source containing the first ~200 characters of chunk content, trimmed to a word boundary.

**Requirements:** R6

**Dependencies:** None

**Files:**
- Modify: `app/app/api/chat/route.ts`

**Approach:**
- Add `snippet: string` to the `Source` interface in `route.ts`
- In the source assembly loop (after `filterByThreshold`): compute `snippet` by slicing `row.content` to at most 220 chars, then trimming back to the last space before position 200 to avoid mid-word cuts. If content is shorter than 200 chars, use it as-is.
- Include `snippet` in the `sources.push({...})` call

**Test scenarios:**
- Happy path: API response `sources[0].snippet` is a non-empty string ≤ 200 characters
- Edge case: chunk content shorter than 200 chars — snippet equals full content
- Edge case: chunk content with no spaces in first 220 chars — truncate at 200 without word-boundary trim (degenerate case)
- Happy path: `snippet` ends on a complete word (no mid-word cut for typical content)

**Verification:** API response includes `snippet` for each source; `snippet.length <= 200`.

---

- [x] **Unit 2: Update `Source` type and `SourceChips` component**

**Goal:** `SourceChips` renders a clickable chip that toggles a peek panel, with a separate ↗ icon for URL navigation.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** Unit 1

**Files:**
- Modify: `app/components/ChatUI.tsx`

**Approach:**
- Add `snippet: string` to the `Source` interface in `ChatUI.tsx`
- Add `useState<number | null>(null)` (`openIndex`) to `SourceChips`
- Restructure each chip: wrap in a container `<div>` with `position: relative`. Inner layout: `[badge] [title area — onClick toggles] [↗ icon — onClick stopPropagation + navigates]`
- The title area is a `<button>` (keyboard accessible) styled to look like the current chip, minus the `href`
- The ↗ icon is a small `<a>` with `href={s.url}` and `target="_blank"`
- Below the chip row, when `openIndex === i`, render the peek panel: a `<div>` with snippet text and "View original →" link
- Snippet text: `var(--sans)` font, `var(--text-2)` color, `font-size: 12px`, `line-height: 1.5`
- Panel background: `var(--surface-2)`, `border: 1px solid var(--border)`, `border-radius: var(--radius)`, `padding: 10px 12px`, `margin-top: 6px`

**Patterns to follow:** Existing chip style in `SourceChips` (`ChatUI.tsx:67`); hover state pattern using inline `onMouseEnter`/`onMouseLeave`.

**Test scenarios:**
- Happy path: clicking a chip expands a panel with non-empty snippet text
- Happy path: clicking the same chip again collapses the panel
- Happy path: clicking chip B while chip A is open collapses A and expands B
- Happy path: clicking the ↗ icon opens URL in new tab without toggling the panel
- Happy path: "View original →" link opens the same URL in a new tab
- Edge case: source with empty `snippet` still renders the panel (no crash); shows empty or falls back gracefully
- Accessibility: chip toggle is a `<button>` element (keyboard-navigable with Tab + Enter)

**Verification:** Click expand → snippet visible; click same → collapsed; ↗ opens URL; no JS errors on interaction.

## System-Wide Impact

- **Unchanged invariants:** `AssistantMessage`, answer rendering, and the API response shape are backward-compatible — `snippet` is additive. Existing `Source` consumers that ignore extra fields are unaffected.
- **State lifecycle:** `openIndex` is local to `SourceChips` — no shared state risk.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Snippet with HTML/special characters rendered as text | `snippet` is rendered as React text node, not `dangerouslySetInnerHTML` — no XSS risk |
| `row.content` NULL in database | Add null guard: `(row.content ?? '').slice(0, 220)` |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-30-source-peek-requirements.md](../brainstorms/2026-03-30-source-peek-requirements.md)
- Related code: `app/app/api/chat/route.ts:33` (Source interface), `app/app/api/chat/route.ts:354` (source assembly), `app/components/ChatUI.tsx:67` (SourceChips)
