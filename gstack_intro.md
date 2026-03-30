# gstack — Headless Browser QA Skill for Claude Code

## Introduction

`gstack` is a persistent headless Chromium browser skill for Claude Code, designed for fast QA testing, visual dogfooding, and deployment verification. It wraps a compiled `browse` binary that starts once (~3s) and stays alive between commands (~100–200ms per call), making it practical for multi-step test flows without the overhead of relaunching a browser each time.

The skill follows the **"Boil the Lake"** principle: when AI makes the marginal cost of thoroughness near-zero, always do the complete thing.

---

## Core Capabilities

| Category | What It Does |
|----------|-------------|
| **Navigation** | `goto`, `reload`, `back`, `forward` |
| **Reading** | `text`, `html`, `links`, `forms`, `accessibility tree` |
| **Interaction** | `click`, `fill`, `select`, `upload`, `press`, `hover` |
| **Assertions** | `is visible/enabled/checked/focused/editable` |
| **Visual** | `screenshot`, `responsive` (mobile/tablet/desktop), `pdf` |
| **Inspection** | `console`, `network`, `storage`, `cookies`, `attrs`, `css` |
| **Diffing** | `snapshot -D` (what changed after an action), `diff url1 url2` |
| **Tabs/Frames** | multi-tab management, iframe context switching |
| **Auth** | `cookie-import-browser` — import real browser cookies |

---

## Key Workflow: Snapshot → Interact → Diff

```bash
$B goto https://app.example.com
$B snapshot -i          # list all interactive elements with @e refs
$B fill @e2 "user@example.com"
$B click @e5            # submit
$B snapshot -D          # see exactly what changed on the page
$B console              # check for JS errors
$B screenshot /tmp/result.png
```

The `snapshot` system is the primary lens: it returns an accessibility tree with `@e` refs you can use directly in `click`, `fill`, `hover`, etc. — no CSS selector guessing needed.

---

## Common Use Cases

- **QA a user flow** (login, signup, checkout) end-to-end
- **Verify a deployment** — check prod loads, no JS errors, key elements present
- **Dogfood a new feature** — annotated screenshots (`snapshot -a`) for bug reports
- **Responsive layout checks** — one command generates mobile/tablet/desktop screenshots
- **Form validation testing** — submit empty, check errors appear, fill, resubmit
- **Authenticated testing** — import cookies from your real browser

---

## Proactive Skill Suggestions

When `proactive` mode is on, gstack auto-suggests adjacent skills:
- `/qa` — full QA pass
- `/design-review` — visual audit
- `/investigate` — debugging
- `/ship` — shipping workflow
- `/careful` / `/guard` — production safety

---

## Setup

gstack needs a one-time build of the `browse` binary:
```bash
cd ~/.claude/skills/gstack && ./setup
```
Requires `bun` (installed automatically if missing). After setup, the binary lives at `~/.claude/skills/gstack/browse/dist/browse`.
