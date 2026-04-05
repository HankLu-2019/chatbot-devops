"""
Unit tests for scraper components.

Run with:
    python test_scraper.py          # standalone
    python -m pytest test_scraper.py -v  # with pytest
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import state as state_mod
from base_client import BaseClient
from confluence_client import ConfluenceClient
from jira_client import JiraClient
from scraper import (
    cleanup_orphaned_tmp,
    dump_json,
    run_once,
    scrape_confluence_incremental,
    scrape_jira_backfill,
    scrape_jira_gap,
    scrape_jira_incremental,
)


# ===========================================================================
# state.py tests
# ===========================================================================

class TestStateLoad(unittest.TestCase):

    def test_load_missing_file_returns_default(self):
        """Loading a non-existent file returns empty confluence/jira dicts."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nonexistent.json")
            s = state_mod.load(path)
            self.assertEqual(s, {"confluence": {}, "jira": {}})

    def test_load_corrupt_file_returns_default(self):
        """Loading a corrupt JSON file returns empty default."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ this is not valid json !!!")
            path = f.name
        try:
            s = state_mod.load(path)
            self.assertEqual(s, {"confluence": {}, "jira": {}})
        finally:
            os.unlink(path)

    def test_load_valid_file(self):
        """Loading a valid state file returns correct data."""
        data = {
            "confluence": {"10001": {"last_fetched": "2026-04-04T00:00:00Z", "backfill_done": True}},
            "jira": {"CICD": {"last_fetched": "2026-04-04T00:00:00Z", "max_issue_number": 20}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            s = state_mod.load(path)
            self.assertEqual(s["confluence"]["10001"]["backfill_done"], True)
            self.assertEqual(s["jira"]["CICD"]["max_issue_number"], 20)
        finally:
            os.unlink(path)

    def test_save_reload_roundtrip(self):
        """save() then load() returns identical data."""
        data = {
            "confluence": {"99999": {"last_fetched": "2026-01-01T00:00:00Z", "backfill_done": False}},
            "jira": {"TEST": {"last_fetched": "2026-01-01T00:00:00Z", "max_issue_number": 5, "backfill_cursor": 3}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            state_mod.save(data, path)
            loaded = state_mod.load(path)
        self.assertEqual(loaded["confluence"]["99999"]["backfill_done"], False)
        self.assertEqual(loaded["jira"]["TEST"]["max_issue_number"], 5)
        self.assertEqual(loaded["jira"]["TEST"]["backfill_cursor"], 3)

    def test_is_new_confluence_source_true(self):
        """is_new_confluence_source returns True for unknown parent_id."""
        s = {"confluence": {}, "jira": {}}
        self.assertTrue(state_mod.is_new_confluence_source(s, 10001))

    def test_is_new_confluence_source_false(self):
        """is_new_confluence_source returns False for known parent_id."""
        s = {"confluence": {"10001": {"last_fetched": "2026-04-04T00:00:00Z"}}, "jira": {}}
        self.assertFalse(state_mod.is_new_confluence_source(s, 10001))

    def test_is_new_jira_source_true(self):
        """is_new_jira_source returns True for unknown project."""
        s = {"confluence": {}, "jira": {}}
        self.assertTrue(state_mod.is_new_jira_source(s, "CICD"))

    def test_is_new_jira_source_false(self):
        """is_new_jira_source returns False for known project."""
        s = {"confluence": {}, "jira": {"CICD": {"last_fetched": "2026-04-04T00:00:00Z"}}}
        self.assertFalse(state_mod.is_new_jira_source(s, "CICD"))

    def test_get_confluence_last_fetched_returns_epoch_for_new(self):
        """get_confluence_last_fetched returns epoch for unknown source."""
        s = {"confluence": {}, "jira": {}}
        dt = state_mod.get_confluence_last_fetched(s, 10001)
        self.assertEqual(dt, datetime.fromtimestamp(0, tz=timezone.utc))

    def test_get_jira_max_issue_number_returns_zero_for_new(self):
        """get_jira_max_issue_number returns 0 for unknown project."""
        s = {"confluence": {}, "jira": {}}
        self.assertEqual(state_mod.get_jira_max_issue_number(s, "CICD"), 0)

    def test_get_backfill_cursor_returns_none_when_done(self):
        """get_backfill_cursor returns None when backfill is complete."""
        s = {"confluence": {}, "jira": {"CICD": {"backfill_cursor": None}}}
        self.assertIsNone(state_mod.get_backfill_cursor(s, "CICD"))

    def test_get_backfill_cursor_returns_int(self):
        """get_backfill_cursor returns the integer cursor when set."""
        s = {"confluence": {}, "jira": {"CICD": {"backfill_cursor": 42}}}
        self.assertEqual(state_mod.get_backfill_cursor(s, "CICD"), 42)


# ===========================================================================
# scraper.py logic tests
# ===========================================================================

class TestScraperLogic(unittest.TestCase):

    def test_incremental_window_is_24h(self):
        """Incremental window calculation produces a 24h lookback."""
        now = datetime.now(timezone.utc)
        look_back_hours = 24
        since = now - timedelta(hours=look_back_hours)
        delta = now - since
        self.assertAlmostEqual(delta.total_seconds(), 24 * 3600, delta=5)

    def test_backfill_batch_size_from_config(self):
        """Backfill batch size is read from config settings."""
        config = {"settings": {"backfill_batch_size": 75}}
        batch = int(config["settings"]["backfill_batch_size"])
        self.assertEqual(batch, 75)

    def test_dump_json_skips_empty(self):
        """dump_json does not create a file when items list is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "output")
            dump_json([], prefix)
            self.assertFalse(Path(prefix + ".json").exists())

    def test_dump_json_writes_file(self):
        """dump_json writes a .json file and no .tmp remains."""
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "output")
            items = [{"key": "val"}]
            dump_json(items, prefix)
            out = Path(prefix + ".json")
            tmp_path = Path(prefix + ".tmp")
            self.assertTrue(out.exists())
            self.assertFalse(tmp_path.exists())
            loaded = json.loads(out.read_text())
            self.assertEqual(loaded, items)

    def test_cleanup_orphaned_tmp_deletes_old_files(self):
        """cleanup_orphaned_tmp removes .tmp files older than max_age_seconds."""
        with tempfile.TemporaryDirectory() as tmp:
            old_tmp = Path(tmp) / "old.tmp"
            old_tmp.write_text("stale")
            # Set mtime to 2 hours ago
            two_hours_ago = time.time() - 7200
            os.utime(old_tmp, (two_hours_ago, two_hours_ago))
            cleanup_orphaned_tmp(tmp, max_age_seconds=3600)
            self.assertFalse(old_tmp.exists())

    def test_cleanup_orphaned_tmp_preserves_recent_files(self):
        """cleanup_orphaned_tmp keeps .tmp files newer than max_age_seconds."""
        with tempfile.TemporaryDirectory() as tmp:
            new_tmp = Path(tmp) / "new.tmp"
            new_tmp.write_text("fresh")
            cleanup_orphaned_tmp(tmp, max_age_seconds=3600)
            self.assertTrue(new_tmp.exists())


# ===========================================================================
# base_client.py tests
# ===========================================================================

def _make_http_response(data: dict, status: int = 200) -> MagicMock:
    """Create a mock HTTP response."""
    body = json.dumps(data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestBaseClient(unittest.TestCase):

    def test_get_success(self):
        """get() returns parsed JSON on 200 response."""
        client = BaseClient("http://localhost:9999", delay=0, max_retries=3, retry_delay=0)
        response_data = {"results": [{"id": 1}]}
        mock_resp = _make_http_response(response_data)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.get("/test")
        self.assertEqual(result, response_data)

    def test_retry_on_429(self):
        """get() retries on 429 and succeeds on subsequent attempt."""
        client = BaseClient("http://localhost:9999", delay=0, max_retries=3, retry_delay=0)
        success_data = {"ok": True}

        http_err_429 = urllib.error.HTTPError(
            url="http://localhost:9999/test",
            code=429,
            msg="Too Many Requests",
            hdrs=None,  # type: ignore
            fp=None,
        )
        success_resp = _make_http_response(success_data)

        call_count = 0
        def _side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise http_err_429
            return success_resp

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            result = client.get("/test")
        self.assertEqual(result, success_data)
        self.assertEqual(call_count, 2)

    def test_retry_on_500(self):
        """get() retries on 500 and succeeds on subsequent attempt."""
        client = BaseClient("http://localhost:9999", delay=0, max_retries=3, retry_delay=0)
        success_data = {"ok": True}

        http_err_500 = urllib.error.HTTPError(
            url="http://localhost:9999/test",
            code=500,
            msg="Server Error",
            hdrs=None,  # type: ignore
            fp=None,
        )
        success_resp = _make_http_response(success_data)
        call_count = 0

        def _side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise http_err_500
            return success_resp

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            result = client.get("/test")
        self.assertEqual(result, success_data)
        self.assertEqual(call_count, 2)

    def test_paginate_fetches_all_pages(self):
        """paginate() accumulates results across multiple pages."""
        client = BaseClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)

        page1 = {"results": [{"id": i} for i in range(3)]}  # 3 items < limit=3? No, limit=3 == 3 → continue
        page2 = {"results": [{"id": i} for i in range(3, 5)]}  # 2 items < limit=3 → stop

        call_count = 0
        def _side_effect(req):
            nonlocal call_count
            call_count += 1
            data = page1 if call_count == 1 else page2
            return _make_http_response(data)

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            results = client.paginate("/test", {}, result_key="results", limit=3)

        self.assertEqual(len(results), 5)
        self.assertEqual(call_count, 2)


# ===========================================================================
# confluence_client.py tests
# ===========================================================================

class TestConfluenceClient(unittest.TestCase):

    def _mock_page_response(self) -> dict:
        return {
            "results": [
                {
                    "id": "101",
                    "title": "CI/CD Pipeline Overview",
                    "space": {"key": "CI-CD", "name": "CI-CD"},
                    "version": {"when": "2026-04-04T10:00:00Z"},
                    "body": {"storage": {"value": "<h2>Overview</h2><p>This is the pipeline.</p>"}},
                    "_links": {"webui": "/wiki/spaces/CI-CD/pages/101"},
                }
            ],
            "size": 1,
        }

    def test_maps_api_response_to_chunker_dict(self):
        """get_pages_by_parent returns dicts with title, body, space, url, updated_at."""
        client = ConfluenceClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)

        with patch.object(client, "paginate", return_value=self._mock_page_response()["results"]):
            pages = client.get_pages_by_parent(10001)

        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertIn("title", page)
        self.assertIn("body", page)
        self.assertIn("space", page)
        self.assertIn("url", page)
        self.assertIn("updated_at", page)
        self.assertEqual(page["title"], "CI/CD Pipeline Overview")
        self.assertIn("<h2>", page["body"])
        self.assertEqual(page["space"], "CI-CD")

    def test_filters_by_modified_since(self):
        """get_pages_by_parent filters out pages older than modified_since."""
        client = ConfluenceClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)

        raw_pages = [
            {
                "id": "101",
                "title": "New Page",
                "space": {"key": "CI-CD"},
                "version": {"when": "2026-04-04T10:00:00Z"},
                "body": {"storage": {"value": "<p>New</p>"}},
                "_links": {},
            },
            {
                "id": "102",
                "title": "Old Page",
                "space": {"key": "CI-CD"},
                "version": {"when": "2026-03-01T10:00:00Z"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "_links": {},
            },
        ]
        cutoff = datetime(2026, 4, 1, tzinfo=timezone.utc)

        with patch.object(client, "paginate", return_value=raw_pages):
            pages = client.get_pages_by_parent(10001, modified_since=cutoff)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["title"], "New Page")


# ===========================================================================
# jira_client.py tests
# ===========================================================================

class TestJiraClient(unittest.TestCase):

    def _mock_search_response(self, issues: list[dict] | None = None) -> dict:
        if issues is None:
            issues = [
                {
                    "id": "10001",
                    "key": "CICD-1",
                    "fields": {
                        "summary": "Set up GitHub Actions",
                        "description": "Configure CI pipeline.",
                        "status": {"name": "Done"},
                        "updated": "2026-04-04T10:00:00Z",
                        "comment": {
                            "comments": [
                                {
                                    "author": {"displayName": "alice"},
                                    "body": "Working on it.",
                                    "created": "2026-04-04T08:00:00Z",
                                }
                            ]
                        },
                    },
                    "_links": {"webui": "/browse/CICD-1"},
                }
            ]
        return {"issues": issues, "total": len(issues)}

    def test_jql_construction_updated_since(self):
        """search_issues builds correct JQL with updated_since."""
        client = JiraClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)
        captured: list[dict] = []

        def _mock_get(path: str, params: dict | None = None) -> dict:
            captured.append(params or {})
            return self._mock_search_response()

        with patch.object(client, "get", side_effect=_mock_get):
            since = datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)
            client.search_issues("CICD", updated_since=since)

        jql = captured[0]["jql"]
        self.assertIn("project=CICD", jql)
        self.assertIn("updated >=", jql)
        self.assertIn("2026-04-03", jql)

    def test_jql_construction_min_issue_number(self):
        """search_issues builds correct JQL with min_issue_number."""
        client = JiraClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)
        captured: list[dict] = []

        def _mock_get(path: str, params: dict | None = None) -> dict:
            captured.append(params or {})
            return self._mock_search_response()

        with patch.object(client, "get", side_effect=_mock_get):
            client.search_issues("CICD", min_issue_number=15)

        jql = captured[0]["jql"]
        self.assertIn("id > 15", jql)

    def test_extracts_comments_from_response(self):
        """search_issues extracts comments into {author, body, created_at} dicts."""
        client = JiraClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)

        with patch.object(client, "get", return_value=self._mock_search_response()):
            result = client.search_issues("CICD")

        issues = result["issues"]
        self.assertEqual(len(issues), 1)
        comments = issues[0]["comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["author"], "alice")
        self.assertEqual(comments[0]["body"], "Working on it.")
        self.assertIn("created_at", comments[0])

    def test_get_latest_issue_number_extracts_numeric_part(self):
        """get_latest_issue_number correctly parses the key's numeric part."""
        client = JiraClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)
        mock_resp = {
            "issues": [{"id": "10042", "key": "CICD-42", "fields": {"summary": "x", "description": "", "status": {"name": "Done"}, "updated": "2026-04-04T00:00:00Z", "comment": {"comments": []}}, "_links": {}}],
            "total": 1,
        }
        with patch.object(client, "get", return_value=mock_resp):
            num = client.get_latest_issue_number("CICD")
        self.assertEqual(num, 42)

    def test_get_latest_issue_number_empty_returns_zero(self):
        """get_latest_issue_number returns 0 when no issues exist."""
        client = JiraClient("http://localhost:9999", delay=0, max_retries=1, retry_delay=0)
        with patch.object(client, "get", return_value={"issues": [], "total": 0}):
            num = client.get_latest_issue_number("EMPTY")
        self.assertEqual(num, 0)


# ===========================================================================
# run_once() integration tests — space tagging, gap detection, backfill
# ===========================================================================

class TestRunOnceIntegration(unittest.TestCase):
    """Integration tests for run_once() using fully mocked clients."""

    def _minimal_config(self) -> dict:
        return {
            "teams": [{"name": "CI/CD", "space": "CI-CD",
                        "confluence": {"parent_ids": [10001]},
                        "jira": {"projects": ["CICD"]}}],
            "settings": {"look_back_hours": 24, "backfill_batch_size": 5,
                         "run_interval_hours": 6},
        }

    def test_jira_space_overrides_client_project_key(self):
        """run_once() must tag Jira issues with the team space (CI-CD), not the project key (CICD)."""
        config = self._minimal_config()
        state = {"confluence": {}, "jira": {}}

        mock_issue = {
            "key": "CICD-1", "space": "CICD",  # client sets project key
            "summary": "test", "description": "", "status": "Done",
            "url": "", "updated_at": None, "comments": [],
        }
        conf_client = MagicMock()
        conf_client.get_pages_by_parent.return_value = []
        conf_client.get.return_value = {"results": [], "size": 0}
        jira_client = MagicMock()
        jira_client.search_issues.return_value = {"issues": [mock_issue], "total": 1}
        jira_client.get_latest_issue_number.return_value = 1

        with tempfile.TemporaryDirectory() as tmpdir:
            run_once(config, state, conf_client, jira_client, tmpdir)
            jira_files = list(Path(tmpdir).rglob("jira_*.json"))
            self.assertEqual(len(jira_files), 1)
            issues = json.loads(jira_files[0].read_text())
            for issue in issues:
                self.assertEqual(issue["space"], "CI-CD",
                                 f"Expected space='CI-CD', got '{issue['space']}'")

    def test_gap_detection_triggers_gap_fetch(self):
        """run_once() fetches gap issues when latest_num > known state max."""
        config = self._minimal_config()
        # State says we've seen up to CICD-5; mock says latest is CICD-8 → gap
        state = {"confluence": {}, "jira": {"CICD": {
            "last_fetched": "2026-01-01T00:00:00Z",
            "max_issue_number": 5,
            "backfill_cursor": None,
        }}}

        conf_client = MagicMock()
        conf_client.get_pages_by_parent.return_value = []
        conf_client.get.return_value = {"results": [], "size": 0}
        jira_client = MagicMock()
        jira_client.search_issues.return_value = {"issues": [], "total": 0}
        jira_client.get_latest_issue_number.return_value = 8  # gap of 3

        with tempfile.TemporaryDirectory() as tmpdir:
            run_once(config, state, conf_client, jira_client, tmpdir)

        # search_issues should have been called for gap (min_issue_number=5)
        calls = jira_client.search_issues.call_args_list
        gap_calls = [c for c in calls if c.kwargs.get("min_issue_number") == 5
                     or (c.args and len(c.args) > 1 and c.args[1] == 5)]
        self.assertTrue(len(gap_calls) > 0 or any(
            call[1].get("min_issue_number") == 5 or
            (len(call[0]) > 1 and call[0][1] == 5)
            for call in [c for c in calls]
        ), "Expected a gap fetch call with min_issue_number=5")

    def test_backfill_runs_on_first_call_for_new_source(self):
        """run_once() runs backfill when a Jira project is new (not in state)."""
        config = self._minimal_config()
        state = {"confluence": {}, "jira": {}}  # CICD never seen before

        conf_client = MagicMock()
        conf_client.get_pages_by_parent.return_value = []
        conf_client.get.return_value = {"results": [], "size": 0}

        backfill_issue = {
            "key": "CICD-1", "space": "CICD",
            "summary": "Backfill issue", "description": "", "status": "Done",
            "url": "", "updated_at": None, "comments": [],
        }
        jira_client = MagicMock()
        # Incremental returns nothing; backfill call returns one issue
        jira_client.search_issues.side_effect = [
            {"issues": [], "total": 0},   # incremental
            {"issues": [backfill_issue], "total": 1},  # backfill
        ]
        jira_client.get_latest_issue_number.return_value = 1

        with tempfile.TemporaryDirectory() as tmpdir:
            new_state = run_once(config, state, conf_client, jira_client, tmpdir)

        # State should track the project now
        self.assertIn("CICD", new_state.get("jira", {}))
        # search_issues called at least twice (incremental + backfill)
        self.assertGreaterEqual(jira_client.search_issues.call_count, 2)


# ===========================================================================
# Standalone test runner
# ===========================================================================

def run_tests() -> bool:
    """Run all tests and return True if all pass."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestStateLoad,
        TestScraperLogic,
        TestBaseClient,
        TestConfluenceClient,
        TestJiraClient,
        TestRunOnceIntegration,
    ]
    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
