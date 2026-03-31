---
title: "Security Audit: 4 MEDIUM findings — no auth, no rate limit, Docker root, unpinned Python deps"
date: 2026-03-31
category: security-issues
module: api-security
problem_type: security_issue
component: authentication
symptoms:
  - "POST /api/chat and /api/feedback are fully public with no auth token or session check"
  - "No per-IP rate limiting on /api/chat; each request fires 3 Gemini API calls, enabling cost amplification"
  - "All three Dockerfiles (app, reranker, ingestion) run container processes as root — no USER directive"
  - "reranker/requirements.txt and ingestion/requirements.txt have no version pins and no lockfile"
  - "Any unauthenticated network client can query the internal knowledge base or exhaust Gemini quota"
root_cause: missing_permission
resolution_type: config_change
severity: medium
related_components:
  - tooling
  - development_workflow
tags:
  - rate-limiting
  - docker-hardening
  - least-privilege
  - dependency-pinning
  - api-authentication
  - next-js-middleware
  - uv-lockfile
  - security-audit
---

# Security Audit: 4 MEDIUM findings — no auth, no rate limit, Docker root, unpinned Python deps

## Problem

A /cso security audit of the RAG Chatbot identified four MEDIUM vulnerabilities: unauthenticated access to the internal knowledge base API, no rate limiting on LLM-backed endpoints (enabling Gemini API cost amplification), all container processes running as root, and Python service dependencies with no version pins or lockfiles. None are individually critical, but together they represent a weak security baseline for a prototype heading toward internal production use.

## Symptoms

- `POST /api/chat` and `POST /api/feedback` accept requests from any client on the network without any credential or token check
- Each chat request triggers 3 Gemini API calls (query rewrite → embed → generate) with no throttle per IP or user
- Running `docker inspect <app|reranker|ingestion>` shows all processes as UID 0 (root)
- `cat reranker/requirements.txt` and `cat ingestion/requirements.txt` show bare package names with no `==x.y.z` version specifiers; no `uv.lock` or equivalent lockfile in either directory
- An automated script hitting `/api/chat` at high frequency would exhaust Gemini quota with no built-in defense

## What Didn't Work

N/A — these are audit findings, not a debugging session. All four issues were identified through static analysis and code review during the first `/cso` run (2026-03-31).

The existing design choice to omit authentication was documented in `docs/plans/2026-03-29-001-feat-multi-page-team-frontend-plan.md` as "deliberate given the no-auth scope boundary." This is the correct way to track design decisions, but it means the gap was known and deferred rather than addressed.

## Solution

### Finding 1: Add Rate Limiting (create `app/middleware.ts`)

Create a Next.js middleware file at `app/middleware.ts` (same level as `next.config.js`) that intercepts all `/api/*` requests:

```typescript
import { NextResponse, NextRequest } from "next/server";

const counts = new Map<string, { count: number; reset: number }>();
const LIMIT = 30;      // requests per minute per IP
const WINDOW = 60_000; // 1 minute in ms

export function middleware(req: NextRequest) {
  if (!req.nextUrl.pathname.startsWith("/api/")) return;
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "unknown";
  const now = Date.now();
  const entry = counts.get(ip);
  if (!entry || entry.reset < now) {
    counts.set(ip, { count: 1, reset: now + WINDOW });
  } else if (entry.count >= LIMIT) {
    return NextResponse.json(
      { error: "Rate limit exceeded. Please wait a moment." },
      { status: 429 }
    );
  } else {
    entry.count++;
  }
}

export const config = { matcher: "/api/:path*" };
```

> **Multi-instance caveat:** This in-memory Map is process-local. For multi-container or serverless deployments, replace with `@upstash/ratelimit` (Redis-backed). Single-container docker-compose setup is safe with the in-memory approach.

---

### Finding 2: Fix Dockerfile Root User

**`app/Dockerfile`** — `node:20-alpine` ships a built-in `node` user, use it in the runner stage:

```dockerfile
# Stage 3 runner — add before EXPOSE 3000:
USER node
EXPOSE 3000
```

**`reranker/Dockerfile`** — `python:3.11-slim` has no non-root user by default:

```dockerfile
# Add before CMD:
RUN adduser --disabled-password --gecos '' appuser
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`ingestion/Dockerfile`** — same pattern, plus chown since `/app` is owned by root at build time:

```dockerfile
# Add before CMD:
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser
CMD ["python", "ingest.py"]
```

The `/data` volume is already mounted `:ro` in `docker-compose.yml`, so the non-root user has no write-permission issue with the data directory.

---

### Finding 3: Pin Python Dependencies with uv Lockfiles

Since `uv` is already installed in both Dockerfiles, generate lockfiles locally and commit them:

```bash
uv pip compile reranker/requirements.txt  -o reranker/requirements.lock
uv pip compile ingestion/requirements.txt -o ingestion/requirements.lock
git add reranker/requirements.lock ingestion/requirements.lock
git commit -m "fix(security): pin Python dependencies with uv lockfiles"
```

Update each Dockerfile to install from the lockfile instead of the loose requirements:

```dockerfile
# reranker/Dockerfile — replace existing pip install:
COPY requirements.txt requirements.lock .
RUN uv pip install --system --no-cache -r requirements.lock
```

```dockerfile
# ingestion/Dockerfile — same:
COPY requirements.txt requirements.lock .
RUN uv pip install --system --no-cache -r requirements.lock
```

**Ongoing:** Re-run `uv pip compile requirements.txt -o requirements.lock` whenever adding or upgrading a dependency. Add `pip-audit` to CI once a CI pipeline exists.

---

### Finding 4: Add Authentication (extend `app/middleware.ts`)

Combine with the rate limiting middleware above. Add a shared-secret header check:

```typescript
// Extend the middleware() function from Finding 1:
export function middleware(req: NextRequest) {
  if (!req.nextUrl.pathname.startsWith("/api/")) return;

  // Rate limiting (Finding 1)
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "unknown";
  const now = Date.now();
  const entry = counts.get(ip);
  if (!entry || entry.reset < now) {
    counts.set(ip, { count: 1, reset: now + WINDOW });
  } else if (entry.count >= LIMIT) {
    return NextResponse.json({ error: "Rate limit exceeded." }, { status: 429 });
  } else {
    entry.count++;
  }

  // Auth check (Finding 4)
  const token    = req.headers.get("x-internal-token");
  const expected = process.env.INTERNAL_TOKEN;
  if (expected && token !== expected) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}
```

Add to `.env` and `docker-compose.yml`:
```
INTERNAL_TOKEN=<random-32-char-string>  # generate with: openssl rand -hex 16
```

Frontend API calls in `ChatUI.tsx` must include the header:
```typescript
headers: {
  "Content-Type": "application/json",
  "Accept": "text/event-stream",
  "X-Internal-Token": process.env.NEXT_PUBLIC_INTERNAL_TOKEN ?? "",
},
```

> **Proper long-term fix:** Deploy behind a network-level SSO proxy (Cloudflare Access, nginx + company LDAP, Tailscale funnel, etc.). The app does not need to own auth if the network layer handles it — the shared secret is a backstop while the network posture is being established.

## Why This Works

- **Rate limiting:** Next.js middleware runs at the Edge before any route handler or Gemini call is made. A per-IP sliding window counter intercepts abusive traffic before any API spend occurs. Cap of 30 req/min means at most 90 Gemini calls/min per IP, not unbounded.

- **Non-root containers:** Docker runs the process as the UID specified by `USER`. If an attacker achieves RCE inside the container (e.g., via a malicious dependency), they operate as an unprivileged user without write access to system paths, preventing privilege escalation within the container and reducing container-escape risk.

- **Locked Python deps:** `uv pip compile` resolves the full dependency graph at a known point in time and records exact versions plus content hashes. `uv pip install -r requirements.lock` reproduces that exact environment on every build. A compromised new version of `fastapi`, `sentence-transformers`, or `google-genai` cannot silently enter the container.

- **Shared secret auth:** The `X-Internal-Token` header check happens in middleware before any route handler processes input. An attacker without the secret receives a 401 before the application spends any compute or Gemini API quota. The `if (expected && ...)` guard means the check is opt-in: if `INTERNAL_TOKEN` is not set in the environment, the middleware passes through (preserving the current no-auth behavior for local dev without the env var).

## Prevention

- **Rate limiting:** Default to rate-limited middleware on any LLM-backed API endpoint from day one. The cost per API call makes unbounded access a financial risk, not just a load risk. For serverless or multi-instance deployments, treat in-memory state as non-durable — use a distributed counter (Redis / `@upstash/ratelimit`) from the start.

- **Container hardening:** Add `USER` directive as a required line in every Dockerfile. Add `hadolint` to CI to flag missing USER, `ADD` instead of `COPY`, and unpinned base image tags. Make it a build gate, not a reminder.

- **Dependency pinning:** Treat lockfiles as required artifacts for all package managers — `package-lock.json` (already committed), `uv.lock` (missing, fix above). Run `npm audit` and `pip-audit` in every CI build. Automate lockfile updates with Dependabot or Renovate so pinning doesn't mean stale deps.

- **Authentication for internal tools:** "It's internal" is not an access control mechanism — it's a deployment assumption. Even for internal tools, layer access controls: network (VPN/SSO proxy) + application (shared secret or JWT) + audit logging. Start with the shared secret pattern above; migrate to SSO when the team scales.

- **Audit cadence:** Schedule a full `/cso` audit whenever a major dependency, infrastructure change, or new data source is added. The first audit (this document) establishes the baseline; future audits track the trend.

## Related Issues

- `/cso` audit report: `.gstack/security-reports/2026-03-31T16-30-41Z.json`
- Auth design decision (acknowledged as deferred): `docs/plans/2026-03-29-001-feat-multi-page-team-frontend-plan.md` lines 41, 83
- `RAG_BEST_PRACTICES.md` — Docker operational notes (no security hardening yet; candidate for additive guidance once Dockerfiles are hardened)
