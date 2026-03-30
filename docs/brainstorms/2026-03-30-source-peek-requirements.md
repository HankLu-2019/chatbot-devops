---
date: 2026-03-30
topic: source-peek
---

# Source Peek (Inline Preview)

## Problem Frame

Source chips currently show only a title and link to an external URL. Users who want to verify why a source was cited must leave the page. A peek panel lets users quickly confirm relevance in-context, then follow the link only if they want the full document.

## Requirements

**Chip Interaction**
- R1. Clicking a source chip toggles an expandable peek panel inline below the chip row. Clicking the chip again collapses it. Only one panel can be open at a time — opening a second chip collapses any previously open panel.
- R2. The chip gains a small external-link icon (↗) that opens the source URL in a new tab. The icon is always visible; it is separate from the click target that toggles the panel (R1).

**Peek Panel Content**
- R3. The panel shows a short text snippet from the retrieved chunk — approximately the first 200 characters — as an abstract of the source content.
- R4. Below the snippet, a "View original →" link opens the full source URL in a new tab.
- R5. The snippet text is styled as body copy (not monospace), clearly distinct from the answer text above.

**Data**
- R6. The API response includes a `snippet` field per source: the first ~200 characters of the chunk's content, trimmed to the nearest word boundary. This is derived from data already retrieved in the pipeline — no additional database query is needed.

## Success Criteria

- Clicking a source chip expands a panel with a readable text snippet and a working "View original" link.
- The external-link icon on the chip opens the URL directly without toggling the panel.
- Closing one panel and opening another works without visual glitches.

## Scope Boundaries

- No LLM-generated summaries — the snippet is a verbatim excerpt from the chunk.
- No "copy" or "share" actions on the panel.
- No changes to how sources are ranked or selected.

## Key Decisions

- **Click-to-expand over hover tooltip:** More accessible, works on touch, and gives users control over when to see the preview.
- **~200-char snippet over full chunk:** Acts as an abstract; enough for relevance verification without overwhelming the chat UI.

## Next Steps
→ `/ce:plan` for structured implementation planning
