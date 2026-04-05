"""
Jira API client.
"""

import re
from datetime import datetime, timezone

from base_client import BaseClient


class JiraClient(BaseClient):
    def search_issues(
        self,
        project: str,
        updated_since: datetime | None = None,
        min_issue_number: int | None = None,
        max_results: int = 50,
        start_at: int = 0,
    ) -> dict:
        """
        JQL search. Returns {'issues': [...], 'total': int}

        API: GET /rest/api/2/search
             ?jql=project={project} ORDER BY id ASC
             &maxResults={max_results}&startAt={start_at}

        Builds JQL:
        - If updated_since: project=X AND updated >= "YYYY-MM-DD HH:MM"
        - If min_issue_number: project=X AND id > {min_issue_number}
        - Both can combine

        Returns issues as dicts for chunker.chunk_jira():
          {key, summary, description, status, space, url, updated_at,
           comments: [{author, body, created_at}]}
        """
        clauses = [f"project={project}"]
        if updated_since is not None:
            ts = updated_since.strftime("%Y-%m-%d %H:%M")
            clauses.append(f'updated >= "{ts}"')
        if min_issue_number is not None:
            clauses.append(f"id > {min_issue_number}")
        jql = " AND ".join(clauses) + " ORDER BY id ASC"

        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }
        data = self.get("/rest/api/2/search", params)

        issues: list[dict] = []
        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            key = issue.get("key", "")

            updated_raw = fields.get("updated") or fields.get("updated_at") or ""
            updated_at: str | None = None
            if updated_raw:
                try:
                    dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    updated_at = dt.isoformat()
                except ValueError:
                    updated_at = updated_raw

            status = (
                fields.get("status", {}).get("name", "")
                if isinstance(fields.get("status"), dict)
                else fields.get("status", "")
            )

            # Build URL
            links = issue.get("_links", {})
            issue_url = links.get("webui", "") or links.get("self", "")
            if issue_url and not issue_url.startswith("http"):
                issue_url = self.base_url + issue_url

            # Parse comments
            raw_comments = (
                fields.get("comment", {}).get("comments", [])
                if isinstance(fields.get("comment"), dict)
                else fields.get("comments", [])
            )
            comments: list[dict] = []
            for c in raw_comments:
                author_raw = c.get("author", {})
                author = (
                    author_raw.get("displayName", "unknown")
                    if isinstance(author_raw, dict)
                    else str(author_raw)
                )
                created_raw = c.get("created", "") or c.get("created_at", "")
                comments.append({
                    "author": author,
                    "body": c.get("body", ""),
                    "created_at": created_raw,
                })

            issues.append({
                "key": key,
                "summary": fields.get("summary", ""),
                "description": fields.get("description", "") or "",
                "status": status,
                "space": project,
                "url": issue_url,
                "updated_at": updated_at,
                "comments": comments,
            })

        return {
            "issues": issues,
            "total": data.get("total", len(issues)),
        }

    def get_latest_issue_number(self, project: str) -> int:
        """Fetch the highest issue number in this project (ORDER BY id DESC LIMIT 1)."""
        jql = f"project={project} ORDER BY id DESC"
        params = {"jql": jql, "maxResults": 1, "startAt": 0}
        data = self.get("/rest/api/2/search", params)
        issues = data.get("issues", [])
        if not issues:
            return 0
        key = issues[0].get("key", "")
        # Extract numeric part: e.g. "CICD-42" -> 42
        match = re.search(r"-(\d+)$", key)
        if match:
            return int(match.group(1))
        return 0
