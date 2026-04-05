"""
Shared HTTP base client with retry and pagination.
Uses urllib.request from stdlib (no requests library dependency).
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class BaseClient:
    def __init__(
        self,
        base_url: str,
        delay: float = 0.5,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET with retry on 429/5xx. Raises on 4xx (except 429)."""
        url = self.base_url + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as e:
                status = e.code
                if status == 429 or status >= 500:
                    last_exc = e
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                # 4xx other than 429 — raise immediately
                raise
            except urllib.error.URLError as e:
                last_exc = e
                time.sleep(self.retry_delay * (attempt + 1))
                continue

        raise RuntimeError(
            f"GET {url} failed after {self.max_retries} retries"
        ) from last_exc

    def paginate(self, path: str, params: dict, result_key: str, limit: int = 50) -> list[dict]:
        """Fetch all pages of results using start/limit pagination.

        result_key is the JSON key containing the results list.
        Stops when the returned page is empty or fewer items than limit.
        """
        all_results: list[dict] = []
        start = int(params.get("start", 0))
        page_params = {**params, "limit": limit, "start": start}

        while True:
            data = self.get(path, page_params)
            items = data.get(result_key, [])
            all_results.extend(items)

            if self.delay > 0:
                time.sleep(self.delay)

            if len(items) < limit:
                break

            start += limit
            page_params = {**page_params, "start": start}

        return all_results
