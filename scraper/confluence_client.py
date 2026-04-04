"""
Confluence API client.
"""

from datetime import datetime, timezone

from base_client import BaseClient


class ConfluenceClient(BaseClient):
    def get_pages_by_parent(
        self,
        parent_id: int,
        modified_since: datetime | None = None,
    ) -> list[dict]:
        """
        Returns pages as dicts compatible with chunker.chunk_confluence():
          {title, body (HTML), space, url, updated_at}

        API: GET /wiki/rest/api/content
             ?ancestor={parent_id}
             &expand=body.storage,version,space
             &limit=50&start=0

        If modified_since: filters pages where updated_at >= modified_since
        (client-side filter since mock API may not support date filter).
        """
        params = {
            "ancestor": parent_id,
            "expand": "body.storage,version,space",
        }
        raw_pages = self.paginate(
            "/wiki/rest/api/content",
            params,
            result_key="results",
        )

        pages: list[dict] = []
        for p in raw_pages:
            updated_at_raw = (
                p.get("version", {}).get("when")
                or p.get("updated_at")
                or ""
            )
            updated_at: datetime | None = None
            if updated_at_raw:
                try:
                    updated_at = datetime.fromisoformat(
                        updated_at_raw.replace("Z", "+00:00")
                    )
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    updated_at = None

            if modified_since is not None and updated_at is not None:
                if updated_at < modified_since:
                    continue

            # Extract HTML body from nested structure
            body_html = (
                p.get("body", {})
                .get("storage", {})
                .get("value", "")
            )

            space_key = (
                p.get("space", {}).get("key", "")
                if isinstance(p.get("space"), dict)
                else p.get("space", "")
            )

            # Build a base URL from the client base_url if links not present
            links = p.get("_links", {})
            page_url = links.get("webui", "") or links.get("self", "")
            if page_url and not page_url.startswith("http"):
                page_url = self.base_url + page_url

            pages.append({
                "title": p.get("title", ""),
                "body": body_html,
                "space": space_key,
                "url": page_url,
                "updated_at": updated_at.isoformat() if updated_at else None,
            })

        return pages
