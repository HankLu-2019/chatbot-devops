"""
Scraper state management.

State file (scraper_state.json) schema:
{
  "confluence": {
    "<parent_id>": {
      "last_fetched": "2026-04-04T00:00:00Z",  # ISO UTC
      "backfill_done": true                      # true once cursor reaches end
    }
  },
  "jira": {
    "<project_key>": {
      "last_fetched": "2026-04-04T00:00:00Z",
      "max_issue_number": 1523,                  # highest issue number seen
      "backfill_cursor": null                    # null = done, int = resume from
    }
  }
}
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_STATE: dict = {"confluence": {}, "jira": {}}


def load(path: str) -> dict:
    """Load JSON state file. Returns empty default structure if missing or corrupt."""
    p = Path(path)
    if not p.exists():
        return {"confluence": {}, "jira": {}}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"confluence": {}, "jira": {}}
        data.setdefault("confluence", {})
        data.setdefault("jira", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"confluence": {}, "jira": {}}


def save(state: dict, path: str) -> None:
    """Atomic write: write to .tmp then rename to path."""
    p = Path(path)
    tmp = Path(str(path) + ".tmp")
    p.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, p)


def is_new_confluence_source(state: dict, parent_id: int) -> bool:
    """Return True if this parent_id has never been scraped."""
    return str(parent_id) not in state.get("confluence", {})


def is_new_jira_source(state: dict, project: str) -> bool:
    """Return True if this project has never been scraped."""
    return project not in state.get("jira", {})


def get_confluence_last_fetched(state: dict, parent_id: int) -> datetime:
    """Return last_fetched datetime for a parent_id, or epoch if never fetched."""
    entry = state.get("confluence", {}).get(str(parent_id), {})
    raw = entry.get("last_fetched")
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def get_jira_last_fetched(state: dict, project: str) -> datetime:
    """Return last_fetched datetime for a project, or epoch if never fetched."""
    entry = state.get("jira", {}).get(project, {})
    raw = entry.get("last_fetched")
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def get_jira_max_issue_number(state: dict, project: str) -> int:
    """Return the highest issue number seen for a project, or 0 if none."""
    entry = state.get("jira", {}).get(project, {})
    return int(entry.get("max_issue_number", 0))


def get_backfill_cursor(state: dict, project: str) -> int | None:
    """Return the backfill cursor (issue number) for a Jira project, or None if done."""
    entry = state.get("jira", {}).get(project, {})
    cursor = entry.get("backfill_cursor")
    return int(cursor) if cursor is not None else None
