"""
Acme RAG Scraper

Run modes:
  python scraper.py          # single run then exit
  python scraper.py --loop   # run every N hours (docker service mode)

Algorithm:
  For each team in config:
    1. Incremental: fetch Confluence pages and Jira issues modified in last 24h
    2. Gap check: if latest_issue_number > state.max_issue_number, fetch gap
    3. Backfill: if source is new, fetch backfill_batch_size items from cursor

  Dump results to data/<SPACE>/confluence_<ts>.json.tmp -> .json
                               jira_<ts>.json.tmp -> .json

  On startup: clean up orphaned .tmp files older than 1 hour.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

# Allow running from scraper/ directory
sys.path.insert(0, str(Path(__file__).parent))

import state as state_mod
from confluence_client import ConfluenceClient
from jira_client import JiraClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config.yml"
_STATE_PATH = Path(__file__).parent / "scraper_state.json"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: str | Path = _CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# File output helpers
# ---------------------------------------------------------------------------

def dump_json(items: list[dict], path_prefix: str) -> None:
    """Write items as JSON. Writes .tmp then renames to .json. Skips if empty."""
    if not items:
        return
    tmp_path = path_prefix + ".tmp"
    final_path = path_prefix + ".json"
    p = Path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, default=str)
    os.replace(tmp_path, final_path)
    log.info("Wrote %d items to %s", len(items), final_path)


def cleanup_orphaned_tmp(data_dir: str | Path, max_age_seconds: int = 3600) -> None:
    """Delete *.tmp files in data_dir older than max_age_seconds."""
    data_path = Path(data_dir)
    if not data_path.exists():
        return
    now = time.time()
    for tmp_file in data_path.rglob("*.tmp"):
        try:
            age = now - tmp_file.stat().st_mtime
            if age > max_age_seconds:
                tmp_file.unlink()
                log.info("Cleaned up orphaned tmp file: %s", tmp_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Scrape helpers — Confluence
# ---------------------------------------------------------------------------

def scrape_confluence_incremental(
    client: ConfluenceClient,
    parent_id: int,
    since: datetime,
    space: str,
) -> list[dict]:
    """Fetch pages modified since `since`, inject `space` field."""
    pages = client.get_pages_by_parent(parent_id, modified_since=since)
    for p in pages:
        p.setdefault("space", space)
    return pages


def scrape_confluence_backfill(
    client: ConfluenceClient,
    parent_id: int,
    batch_size: int,
    cursor_page: int,
) -> tuple[list[dict], int | None]:
    """
    Fetch a batch of pages starting at cursor_page (0-indexed page number).
    Returns (pages, next_cursor). next_cursor is None when no more pages.
    """
    # Use paginate internally but only fetch one batch worth
    params = {
        "ancestor": parent_id,
        "expand": "body.storage,version,space",
        "start": cursor_page * batch_size,
    }
    raw = client.get("/wiki/rest/api/content", {**params, "limit": batch_size})
    items = raw.get("results", [])

    pages: list[dict] = []
    for p in items:
        updated_at_raw = (
            p.get("version", {}).get("when") or p.get("updated_at") or ""
        )
        body_html = (
            p.get("body", {}).get("storage", {}).get("value", "")
        )
        space_key = (
            p.get("space", {}).get("key", "")
            if isinstance(p.get("space"), dict)
            else p.get("space", "")
        )
        links = p.get("_links", {})
        page_url = links.get("webui", "") or links.get("self", "")
        if page_url and not page_url.startswith("http"):
            page_url = client.base_url + page_url

        pages.append({
            "title": p.get("title", ""),
            "body": body_html,
            "space": space_key,
            "url": page_url,
            "updated_at": updated_at_raw,
        })

    next_cursor = cursor_page + 1 if len(items) >= batch_size else None
    return pages, next_cursor


# ---------------------------------------------------------------------------
# Scrape helpers — Jira
# ---------------------------------------------------------------------------

def scrape_jira_incremental(
    client: JiraClient,
    project: str,
    since: datetime,
    space: str,
) -> list[dict]:
    """Fetch issues updated since `since`."""
    result = client.search_issues(project, updated_since=since)
    issues = result["issues"]
    for i in issues:
        i["space"] = space
    return issues


def scrape_jira_gap(
    client: JiraClient,
    project: str,
    from_id: int,
    to_id: int,
    space: str,
) -> list[dict]:
    """Fetch issues with issue number in (from_id, to_id]."""
    all_issues: list[dict] = []
    start_at = 0
    batch = 50
    while True:
        result = client.search_issues(
            project,
            min_issue_number=from_id,
            max_results=batch,
            start_at=start_at,
        )
        issues = result["issues"]
        # Filter to ids <= to_id
        for i in issues:
            m = re.search(r"-(\d+)$", i.get("key", ""))
            num = int(m.group(1)) if m else 0
            if num <= to_id:
                i["space"] = space
                all_issues.append(i)
        if len(issues) < batch:
            break
        # Check if all remaining are past to_id
        if issues and issues[-1]:
            m = re.search(r"-(\d+)$", issues[-1].get("key", ""))
            if m and int(m.group(1)) >= to_id:
                break
        start_at += batch
    return all_issues


def scrape_jira_backfill(
    client: JiraClient,
    project: str,
    batch_size: int,
    cursor: int,
    space: str,
) -> tuple[list[dict], int | None]:
    """
    Fetch batch_size issues starting after `cursor` (issue number).
    Returns (issues, next_cursor). next_cursor is None when no more pages.
    """
    result = client.search_issues(
        project,
        min_issue_number=cursor,
        max_results=batch_size,
        start_at=0,
    )
    issues = result["issues"]
    for i in issues:
        i["space"] = space

    if not issues or len(issues) < batch_size:
        next_cursor = None
    else:
        last_key = issues[-1].get("key", "")
        m = re.search(r"-(\d+)$", last_key)
        next_cursor = int(m.group(1)) if m else None

    return issues, next_cursor


# ---------------------------------------------------------------------------
# Main run cycle
# ---------------------------------------------------------------------------

def run_once(
    config: dict,
    state: dict,
    confluence_client: ConfluenceClient,
    jira_client: JiraClient,
    data_dir: str | Path,
) -> dict:
    """One full scrape cycle. Returns updated state."""
    settings = config.get("settings", {})
    look_back_hours: int = int(settings.get("look_back_hours", 24))
    run_interval_hours: int = int(settings.get("run_interval_hours", 6))
    backfill_batch_size: int = int(settings.get("backfill_batch_size", 50))

    # If backfill_total_estimated and backfill_days are both set, compute
    # batch_size to spread the full backfill evenly across backfill_days.
    # runs_per_day = 24 / run_interval_hours; computed size overrides explicit setting.
    backfill_total_estimated = settings.get("backfill_total_estimated")
    backfill_days = settings.get("backfill_days")
    if backfill_total_estimated and backfill_days:
        import math
        runs_per_day = 24 / run_interval_hours
        computed = math.ceil(int(backfill_total_estimated) / (int(backfill_days) * runs_per_day))
        backfill_batch_size = max(computed, 1)
        log.info(
            "backfill_batch_size computed from backfill_total_estimated=%s / backfill_days=%s "
            "(%.1f runs/day) = %d items/run",
            backfill_total_estimated, backfill_days, runs_per_day, backfill_batch_size,
        )

    now = datetime.now(timezone.utc)
    incremental_since = now - timedelta(hours=look_back_hours)
    ts = now.strftime("%Y%m%dT%H%M%S")

    for team in config.get("teams", []):
        space: str = team["space"]
        team_data_dir = Path(data_dir) / space
        team_data_dir.mkdir(parents=True, exist_ok=True)

        # ---- Confluence ----
        confluence_pages: list[dict] = []
        for parent_id in team.get("confluence", {}).get("parent_ids", []):
            pid = int(parent_id)
            pid_str = str(pid)
            is_new = state_mod.is_new_confluence_source(state, pid)

            # Incremental
            since = incremental_since if not is_new else datetime.fromtimestamp(0, tz=timezone.utc)
            pages = scrape_confluence_incremental(confluence_client, pid, since, space)
            confluence_pages.extend(pages)
            log.info("Confluence parent=%s incremental: %d pages", pid, len(pages))

            # Backfill
            if is_new or not state["confluence"].get(pid_str, {}).get("backfill_done"):
                cursor = state.get("confluence", {}).get(pid_str, {}).get("backfill_cursor", 0) or 0
                bf_pages, next_cursor = scrape_confluence_backfill(
                    confluence_client, pid, backfill_batch_size, cursor
                )
                confluence_pages.extend(bf_pages)
                log.info("Confluence parent=%s backfill cursor=%s: %d pages", pid, cursor, len(bf_pages))

                # Update state
                state.setdefault("confluence", {}).setdefault(pid_str, {})
                state["confluence"][pid_str]["backfill_cursor"] = next_cursor
                state["confluence"][pid_str]["backfill_done"] = next_cursor is None
            else:
                state.setdefault("confluence", {}).setdefault(pid_str, {})

            state["confluence"][pid_str]["last_fetched"] = now.isoformat()

        if confluence_pages:
            dump_json(confluence_pages, str(team_data_dir / f"confluence_{ts}"))

        # ---- Jira ----
        for project in team.get("jira", {}).get("projects", []):
            jira_issues: list[dict] = []
            is_new = state_mod.is_new_jira_source(state, project)

            # Incremental
            since = incremental_since if not is_new else datetime.fromtimestamp(0, tz=timezone.utc)
            inc_issues = scrape_jira_incremental(jira_client, project, since, space)
            jira_issues.extend(inc_issues)
            log.info("Jira project=%s incremental: %d issues", project, len(inc_issues))

            # Gap check
            latest_num = jira_client.get_latest_issue_number(project)
            known_max = state_mod.get_jira_max_issue_number(state, project)
            if latest_num > known_max and known_max > 0:
                gap_issues = scrape_jira_gap(jira_client, project, known_max, latest_num, space)
                jira_issues.extend(gap_issues)
                log.info("Jira project=%s gap %d->%d: %d issues", project, known_max, latest_num, len(gap_issues))

            # Backfill
            state.setdefault("jira", {}).setdefault(project, {})
            proj_state = state["jira"][project]
            if is_new or proj_state.get("backfill_cursor") is not None:
                cursor = state_mod.get_backfill_cursor(state, project)
                if cursor is None:
                    cursor = 0
                bf_issues, next_cursor = scrape_jira_backfill(
                    jira_client, project, backfill_batch_size, cursor, space
                )
                jira_issues.extend(bf_issues)
                log.info("Jira project=%s backfill cursor=%s: %d issues", project, cursor, len(bf_issues))
                proj_state["backfill_cursor"] = next_cursor

            # Update state
            proj_state["last_fetched"] = now.isoformat()
            if latest_num > known_max:
                proj_state["max_issue_number"] = latest_num

            if jira_issues:
                dump_json(jira_issues, str(team_data_dir / f"jira_{ts}"))

    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Acme RAG Scraper")
    parser.add_argument("--loop", action="store_true", help="Run continuously every N hours")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", str(Path(__file__).parent.parent / "data")), help="Output data directory")
    parser.add_argument("--config", default=str(_CONFIG_PATH), help="Config YAML path")
    parser.add_argument("--state", default=str(_STATE_PATH), help="State JSON path")
    parser.add_argument("--mock-api-url", default=None, help="Base URL for Confluence+Jira API (overrides env vars)")
    args = parser.parse_args()

    config = load_config(args.config)
    settings = config.get("settings", {})
    delay = float(settings.get("request_delay_seconds", 0.5))
    max_retries = int(settings.get("max_retries", 3))
    retry_delay = float(settings.get("retry_delay_seconds", 2.0))
    run_interval_hours = int(settings.get("run_interval_hours", 6))

    # Resolve API URLs: CLI flag > env vars > localhost fallback
    default_url = "http://localhost:8081"
    confluence_url = args.mock_api_url or os.environ.get("CONFLUENCE_URL", default_url)
    jira_url = args.mock_api_url or os.environ.get("JIRA_URL", default_url)

    confluence_client = ConfluenceClient(
        base_url=confluence_url,
        delay=delay,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )
    jira_client = JiraClient(
        base_url=jira_url,
        delay=delay,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )

    cleanup_orphaned_tmp(args.data_dir)

    if args.loop:
        while True:
            st = state_mod.load(args.state)
            st = run_once(config, st, confluence_client, jira_client, args.data_dir)
            state_mod.save(st, args.state)
            log.info("Sleeping %d hours until next run", run_interval_hours)
            time.sleep(run_interval_hours * 3600)
    else:
        st = state_mod.load(args.state)
        st = run_once(config, st, confluence_client, jira_client, args.data_dir)
        state_mod.save(st, args.state)


if __name__ == "__main__":
    main()
