"""
Mock Confluence + Jira API server.

Confluence endpoints:
  GET /wiki/rest/api/content
      ?ancestor={parent_id}&expand=body.storage,version,space
      &limit={limit}&start={start}

Jira endpoints:
  GET /rest/api/2/search
      ?jql={jql}&maxResults={max}&startAt={start}

Seeded with realistic fake data for all 3 spaces (CI-CD, INFRA, ENG-ENV).
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Confluence + Jira API")

# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)


def _ts(days_ago: float = 0, hours_ago: float = 0) -> str:
    dt = _NOW - timedelta(days=days_ago, hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_page(
    page_id: int,
    parent_id: int,
    title: str,
    space_key: str,
    body_html: str,
    days_ago: float = 2.0,
) -> dict:
    return {
        "id": str(page_id),
        "title": title,
        "type": "page",
        "space": {"key": space_key, "name": space_key},
        "version": {"when": _ts(days_ago=days_ago)},
        "body": {"storage": {"value": body_html}},
        "_links": {"webui": f"/wiki/spaces/{space_key}/pages/{page_id}"},
        "_parent_id": parent_id,
    }


def _make_issue(
    key: str,
    project: str,
    summary: str,
    description: str,
    status: str,
    days_ago: float = 2.0,
    comments: list[dict] | None = None,
) -> dict:
    num = int(key.split("-")[1])
    return {
        "id": str(10000 + num),
        "key": key,
        "fields": {
            "summary": summary,
            "description": description,
            "status": {"name": status},
            "updated": _ts(days_ago=days_ago),
            "comment": {
                "comments": comments or [],
            },
        },
        "_links": {"webui": f"/browse/{key}"},
    }


def _comment(author: str, body: str, hours_ago: float = 12.0) -> dict:
    return {
        "author": {"displayName": author},
        "body": body,
        "created": _ts(hours_ago=hours_ago),
    }


# ---------------------------------------------------------------------------
# Seed: Confluence pages
# ---------------------------------------------------------------------------

_CICD_BODY_1 = """
<h2>Overview</h2>
<p>This page describes the CI/CD pipeline for the main application service.</p>
<h2>Build Steps</h2>
<p>The pipeline runs lint, unit tests, integration tests, and Docker build.</p>
<h2>Deployment</h2>
<p>Deploys to Kubernetes via Helm. Uses ArgoCD for GitOps sync.</p>
"""

_CICD_BODY_2 = """
<h2>Overview</h2>
<p>Jenkins job configuration for nightly regression builds.</p>
<h2>Schedule</h2>
<p>Runs every night at 02:00 UTC. Notifies Slack on failure.</p>
"""

_CICD_BODY_3 = """
<h2>Overview</h2>
<p>Documentation for the release branching strategy used by all services.</p>
<h2>Branch Naming</h2>
<p>Release branches follow the pattern: release/YYYY-MM-DD-v{version}.</p>
<h2>Hotfix Policy</h2>
<p>Hotfixes cherry-picked from main, tagged with -hotfix suffix.</p>
"""

_CICD_BODY_4 = """
<h2>Secrets Management</h2>
<p>All CI secrets stored in Vault. Injected via Vault Agent Sidecar.</p>
<h2>Rotation Policy</h2>
<p>Secrets rotate every 90 days automatically via Vault TTL policies.</p>
"""

_CICD_BODY_5 = """
<h2>Canary Deployments</h2>
<p>We use Argo Rollouts for canary releases. 10% traffic for 15 minutes before full rollout.</p>
<h2>Rollback</h2>
<p>Automated rollback if error rate exceeds 1% during canary window.</p>
"""

_INFRA_BODY_1 = """
<h2>Cluster Architecture</h2>
<p>Production Kubernetes cluster runs on EKS 1.28. Three availability zones.</p>
<h2>Node Groups</h2>
<p>General workloads: m5.xlarge. GPU workloads: g4dn.xlarge. Spot instances for batch jobs.</p>
"""

_INFRA_BODY_2 = """
<h2>Networking Overview</h2>
<p>VPC spans three AZs. Public subnets for load balancers, private for pods.</p>
<h2>Ingress</h2>
<p>AWS ALB Ingress Controller. TLS terminated at the load balancer.</p>
"""

_INFRA_BODY_3 = """
<h2>Monitoring Stack</h2>
<p>Prometheus + Grafana for metrics. Loki for logs. PagerDuty for alerts.</p>
<h2>SLOs</h2>
<p>99.9% availability for production APIs. 99.5% for staging.</p>
"""

_ENGENV_BODY_1 = """
<h2>Local Setup</h2>
<p>Install: Docker Desktop, nvm, pyenv, direnv. Clone repos with clone-all.sh script.</p>
<h2>First Run</h2>
<p>Run make setup from repo root. This installs all dependencies and configures git hooks.</p>
<h2>IDE Setup</h2>
<p>VSCode with recommended extensions: ESLint, Prettier, Python, Ruff, Docker.</p>
"""

_ENGENV_BODY_2 = """
<h2>Python Tooling</h2>
<p>We use uv for package management. pyproject.toml defines all dependencies.</p>
<h2>Node Tooling</h2>
<p>Node 20 LTS via nvm. Package manager: npm (not yarn or pnpm).</p>
"""

_ENGENV_BODY_3 = """
<h2>Git Hooks</h2>
<p>Pre-commit hooks: ruff lint, mypy type check, ESLint, Prettier format check.</p>
<h2>Commit Convention</h2>
<p>Conventional commits: feat/fix/chore/docs/refactor. No emoji in commit messages.</p>
"""

_CONFLUENCE_PAGES: list[dict] = [
    # parent 10001 — CI/CD
    _make_page(101, 10001, "CI/CD Pipeline Overview", "CI-CD", _CICD_BODY_1, days_ago=1.0),
    _make_page(102, 10001, "Jenkins Nightly Jobs", "CI-CD", _CICD_BODY_2, days_ago=3.0),
    _make_page(103, 10001, "Release Branching Strategy", "CI-CD", _CICD_BODY_3, days_ago=0.5),
    _make_page(104, 10001, "Secrets Management in CI", "CI-CD", _CICD_BODY_4, days_ago=5.0),
    _make_page(105, 10001, "Canary Deployment Runbook", "CI-CD", _CICD_BODY_5, days_ago=0.2),
    # parent 10002 — CI/CD
    _make_page(111, 10002, "Docker Build Optimizations", "CI-CD", _CICD_BODY_1, days_ago=2.0),
    _make_page(112, 10002, "Pipeline Metrics Dashboard", "CI-CD", _CICD_BODY_2, days_ago=4.0),
    _make_page(113, 10002, "Test Parallelization Guide", "CI-CD", _CICD_BODY_3, days_ago=1.5),
    _make_page(114, 10002, "Artifact Registry Policy", "CI-CD", _CICD_BODY_4, days_ago=6.0),
    _make_page(115, 10002, "Rollback Procedures", "CI-CD", _CICD_BODY_5, days_ago=0.1),
    # parent 10003 — CI/CD
    _make_page(121, 10003, "GitHub Actions Workflows", "CI-CD", _CICD_BODY_1, days_ago=0.8),
    _make_page(122, 10003, "Build Cache Strategy", "CI-CD", _CICD_BODY_2, days_ago=7.0),
    _make_page(123, 10003, "Dependency Scanning", "CI-CD", _CICD_BODY_3, days_ago=2.5),
    _make_page(124, 10003, "SBOM Generation", "CI-CD", _CICD_BODY_4, days_ago=3.5),
    _make_page(125, 10003, "Smoke Test Framework", "CI-CD", _CICD_BODY_5, days_ago=0.3),
    # parent 20001 — INFRA
    _make_page(201, 20001, "Kubernetes Cluster Architecture", "INFRA", _INFRA_BODY_1, days_ago=1.0),
    _make_page(202, 20001, "Networking Overview", "INFRA", _INFRA_BODY_2, days_ago=0.5),
    _make_page(203, 20001, "Monitoring and Alerting", "INFRA", _INFRA_BODY_3, days_ago=2.0),
    _make_page(204, 20001, "Node Autoscaling Policy", "INFRA", _INFRA_BODY_1, days_ago=4.0),
    _make_page(205, 20001, "Storage Classes Reference", "INFRA", _INFRA_BODY_2, days_ago=0.2),
    # parent 20002 — INFRA
    _make_page(211, 20002, "Load Balancer Configuration", "INFRA", _INFRA_BODY_2, days_ago=1.5),
    _make_page(212, 20002, "DNS and Service Discovery", "INFRA", _INFRA_BODY_3, days_ago=3.0),
    _make_page(213, 20002, "Certificate Management", "INFRA", _INFRA_BODY_1, days_ago=0.4),
    _make_page(214, 20002, "VPC Peering Runbook", "INFRA", _INFRA_BODY_2, days_ago=5.0),
    _make_page(215, 20002, "Firewall Rules Reference", "INFRA", _INFRA_BODY_3, days_ago=0.6),
    # parent 30001 — ENG-ENV
    _make_page(301, 30001, "Developer Environment Setup", "ENG-ENV", _ENGENV_BODY_1, days_ago=1.0),
    _make_page(302, 30001, "Python Tooling Guide", "ENG-ENV", _ENGENV_BODY_2, days_ago=0.3),
    _make_page(303, 30001, "Git Hooks and Conventions", "ENG-ENV", _ENGENV_BODY_3, days_ago=2.0),
    _make_page(304, 30001, "VSCode Remote Dev Setup", "ENG-ENV", _ENGENV_BODY_1, days_ago=4.0),
    _make_page(305, 30001, "Debugging Guide", "ENG-ENV", _ENGENV_BODY_2, days_ago=0.1),
]

# ---------------------------------------------------------------------------
# Seed: Jira issues
# ---------------------------------------------------------------------------

_JIRA_ISSUES: list[dict] = []

# CICD project — 20 issues
_cicd_data = [
    (1, "Set up GitHub Actions for main service", "Configure CI pipeline with lint, test, build stages.", "Done", 10.0),
    (2, "Add Docker layer caching to build pipeline", "Implement BuildKit cache mounts to speed up builds.", "Done", 8.0),
    (3, "Nightly regression test flakiness", "Tests failing intermittently on concurrent DB access.", "In Progress", 0.5),
    (4, "Implement canary deployment for API service", "Use Argo Rollouts for 10% canary traffic split.", "Done", 5.0),
    (5, "Vault integration for CI secrets", "Replace hardcoded secrets with Vault dynamic credentials.", "Done", 7.0),
    (6, "Pipeline failure notifications to Slack", "Add Slack webhook for build failures and recoveries.", "Done", 6.0),
    (7, "SBOM generation on every release build", "Integrate Syft for software bill of materials.", "In Progress", 0.8),
    (8, "Dependency vulnerability scanning", "Add Trivy scan step before Docker push.", "In Progress", 0.3),
    (9, "Release branch automation script", "Automate release/YYYY-MM-DD-vX branch creation.", "To Do", 1.0),
    (10, "Improve test parallelization", "Shard pytest runs across 4 workers in CI.", "Done", 4.0),
    (11, "Build artifact retention policy", "ECR lifecycle policy: keep last 30 images per service.", "Done", 9.0),
    (12, "Multi-arch Docker builds (arm64 + amd64)", "Use docker buildx for cross-platform images.", "In Progress", 0.2),
    (13, "Cache pip dependencies in CI", "Use actions/cache for pip wheels.", "Done", 11.0),
    (14, "GitHub OIDC auth for AWS", "Replace long-lived AWS keys with OIDC federation.", "Done", 3.0),
    (15, "Smoke tests post-deploy", "Run curl-based smoke tests against staging after deploy.", "In Progress", 0.6),
    (16, "Rollback automation on error spike", "Auto-rollback if p99 latency > 500ms post-deploy.", "To Do", 1.5),
    (17, "Hotfix pipeline documentation", "Document cherry-pick + tag process for hotfixes.", "To Do", 2.0),
    (18, "Performance benchmark in CI", "Add k6 load test with baseline comparison.", "To Do", 0.4),
    (19, "Slack deploy notifications", "Post deploy summary (version, env, duration) to #deploys.", "Done", 12.0),
    (20, "Fix flaky integration test: test_db_connection", "Race condition in teardown causing port conflicts.", "In Progress", 0.1),
]

for _num, _summary, _desc, _status, _days in _cicd_data:
    _key = f"CICD-{_num}"
    _comments = [
        _comment("alice", f"Working on {_summary}. ETA tomorrow.", hours_ago=_days * 24 * 0.5),
    ]
    if _num % 3 == 0:
        _comments.append(_comment("bob", "Reviewed and approved the approach.", hours_ago=_days * 24 * 0.3))
    _JIRA_ISSUES.append(_make_issue(_key, "CICD", _summary, _desc, _status, days_ago=_days, comments=_comments))

# INFRA project — 15 issues
_infra_data = [
    (1, "EKS 1.28 upgrade planning", "Evaluate breaking changes and update node AMIs.", "Done", 14.0),
    (2, "ALB Ingress Controller upgrade to v2.7", "Test new features: grpc routing, mTLS.", "Done", 10.0),
    (3, "Node autoscaler tuning for burst workloads", "Reduce scale-out delay from 3m to 1m.", "In Progress", 0.5),
    (4, "Spot instance interruption handling", "Implement graceful shutdown on SIGTERM from spot.", "Done", 7.0),
    (5, "VPC peering with data warehouse VPC", "Add routes and SG rules for DW subnet access.", "In Progress", 0.3),
    (6, "Prometheus storage expansion", "Increase PVC from 100Gi to 500Gi for 90-day retention.", "Done", 5.0),
    (7, "Grafana dashboard for deployment frequency", "DORA metrics: deployment frequency, lead time.", "To Do", 1.0),
    (8, "Certificate rotation automation", "Cert-manager + Let's Encrypt wildcard cert renewal.", "Done", 8.0),
    (9, "Network policy audit", "Review all NetworkPolicy resources for least privilege.", "In Progress", 0.7),
    (10, "GPU node pool setup for ML workloads", "Add g4dn.xlarge Spot node group with GPU operator.", "In Progress", 0.2),
    (11, "Loki retention policy (30 days)", "Configure Loki ruler for log retention and deletion.", "Done", 9.0),
    (12, "PagerDuty escalation policy update", "Add new on-call rotation for infra team.", "Done", 6.0),
    (13, "S3 bucket versioning audit", "Enable versioning on all prod buckets.", "Done", 11.0),
    (14, "DNS failover for primary region outage", "Route53 health checks and failover routing policy.", "To Do", 2.0),
    (15, "Cost optimization: right-size over-provisioned nodes", "Analyze VPA recommendations and resize.", "In Progress", 0.4),
]

for _num, _summary, _desc, _status, _days in _infra_data:
    _key = f"INFRA-{_num}"
    _comments = [
        _comment("charlie", f"Starting investigation on {_summary}.", hours_ago=_days * 24 * 0.6),
    ]
    if _num % 2 == 0:
        _comments.append(_comment("diana", "Verified fix in staging. Ready for prod.", hours_ago=_days * 24 * 0.2))
    _JIRA_ISSUES.append(_make_issue(_key, "INFRA", _summary, _desc, _status, days_ago=_days, comments=_comments))

# ENGENV project — 12 issues
_engenv_data = [
    (1, "Update Python version to 3.12", "Update pyproject.toml and CI matrix to Python 3.12.", "Done", 12.0),
    (2, "Migrate to uv from pip+virtualenv", "Replace requirements.txt workflow with uv lockfile.", "Done", 8.0),
    (3, "Add ruff formatter to pre-commit hooks", "Replace black+isort with ruff format in .pre-commit-config.yaml.", "Done", 5.0),
    (4, "mypy strict mode for core modules", "Enable strict mypy checks for lib/ and api/ modules.", "In Progress", 0.6),
    (5, "VSCode devcontainer setup", "Create .devcontainer/devcontainer.json for consistent env.", "In Progress", 0.3),
    (6, "Node 20 LTS upgrade", "Update .nvmrc and Dockerfile FROM node:20-alpine.", "Done", 6.0),
    (7, "Document onboarding script", "Write step-by-step setup guide for new engineers.", "To Do", 1.0),
    (8, "Git large file tracking policy", "Block commits of >1MB binary files via pre-commit.", "Done", 9.0),
    (9, "Debugging guide for remote containers", "Document VSCode attach to running Docker container.", "To Do", 0.5),
    (10, "Homebrew bundle for macOS setup", "Create Brewfile with all required tools.", "In Progress", 0.2),
    (11, "ESLint upgrade to v9 flat config", "Migrate from .eslintrc to eslint.config.js format.", "In Progress", 0.4),
    (12, "Prettier config standardization", "Unify .prettierrc across all repos in the monorepo.", "To Do", 1.5),
]

for _num, _summary, _desc, _status, _days in _engenv_data:
    _key = f"ENGENV-{_num}"
    _comments = [
        _comment("eve", f"PR open for {_summary}. Please review.", hours_ago=_days * 24 * 0.4),
    ]
    if _num % 4 == 0:
        _comments.append(_comment("frank", "LGTM. Merging tomorrow.", hours_ago=_days * 24 * 0.1))
    _JIRA_ISSUES.append(_make_issue(_key, "ENGENV", _summary, _desc, _status, days_ago=_days, comments=_comments))


# ---------------------------------------------------------------------------
# Confluence endpoint
# ---------------------------------------------------------------------------

@app.get("/wiki/rest/api/content")
def get_confluence_content(
    ancestor: int | None = Query(default=None),
    expand: str = Query(default=""),
    limit: int = Query(default=50),
    start: int = Query(default=0),
) -> Any:
    if ancestor is None:
        return JSONResponse({"results": [], "size": 0})

    matching = [p for p in _CONFLUENCE_PAGES if p["_parent_id"] == ancestor]
    page_slice = matching[start: start + limit]

    # Strip internal _parent_id before returning
    results = []
    for p in page_slice:
        clean = {k: v for k, v in p.items() if k != "_parent_id"}
        results.append(clean)

    return JSONResponse({
        "results": results,
        "start": start,
        "limit": limit,
        "size": len(results),
    })


# ---------------------------------------------------------------------------
# Jira search endpoint
# ---------------------------------------------------------------------------

def _parse_jql(jql: str) -> dict:
    """Parse simple JQL into filter criteria."""
    criteria: dict = {}

    # project=X or project = X
    m = re.search(r"project\s*=\s*(\w[\w-]*)", jql, re.IGNORECASE)
    if m:
        criteria["project"] = m.group(1).upper()

    # id > N
    m = re.search(r"\bid\s*>\s*(\d+)", jql, re.IGNORECASE)
    if m:
        criteria["id_gt"] = int(m.group(1))

    # updated >= "YYYY-MM-DD HH:MM"
    m = re.search(r'updated\s*>=\s*["\']?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})["\']?', jql, re.IGNORECASE)
    if m:
        raw = m.group(1).replace(" ", "T")
        try:
            criteria["updated_since"] = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # ORDER BY id DESC/ASC
    m = re.search(r"order by\s+id\s+(asc|desc)", jql, re.IGNORECASE)
    if m:
        criteria["order"] = m.group(1).lower()
    else:
        criteria["order"] = "asc"

    return criteria


@app.get("/rest/api/2/search")
def jira_search(
    jql: str = Query(default=""),
    maxResults: int = Query(default=50),
    startAt: int = Query(default=0),
) -> Any:
    criteria = _parse_jql(jql)
    project = criteria.get("project")
    id_gt = criteria.get("id_gt")
    updated_since = criteria.get("updated_since")
    order = criteria.get("order", "asc")

    matching = []
    for issue in _JIRA_ISSUES:
        # Filter by project
        if project and not issue["key"].startswith(project + "-"):
            continue

        # Filter by id > N
        if id_gt is not None:
            num = int(issue["key"].split("-")[1])
            if num <= id_gt:
                continue

        # Filter by updated >= date
        if updated_since is not None:
            updated_raw = issue["fields"]["updated"]
            try:
                updated_dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                if updated_dt < updated_since:
                    continue
            except ValueError:
                pass

        matching.append(issue)

    # Sort
    def _issue_num(iss: dict) -> int:
        return int(iss["key"].split("-")[1])

    matching.sort(key=_issue_num, reverse=(order == "desc"))

    total = len(matching)
    page = matching[startAt: startAt + maxResults]

    return JSONResponse({
        "issues": page,
        "total": total,
        "maxResults": maxResults,
        "startAt": startAt,
    })


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> Any:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
