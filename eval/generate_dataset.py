#!/usr/bin/env python3
"""
Generate golden QA datasets for RAG evaluation.

Pulls documents from mock-apis (Confluence + Jira), strips HTML,
then uses Gemini Flash to generate question/answer pairs per document.

Usage:
    python generate_dataset.py [--mock-apis-url http://localhost:8081]
                               [--pairs-per-doc 2]
                               [--out-dir datasets/]

Output:
    datasets/golden_CI-CD.json
    datasets/golden_INFRA.json
    datasets/golden_ENG-ENV.json

Each record:
    {
        "question":     str,
        "ground_truth": str,
        "source_title": str,   # for retrieval eval matching
        "source_type":  str,   # "confluence" | "jira"
        "space":        str
    }
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    sys.exit("GEMINI_API_KEY not set — check .env")

# ---------------------------------------------------------------------------
# Space config: which parent IDs to scrape and which Jira projects to use
# ---------------------------------------------------------------------------

SPACES = [
    {
        "space":           "CI-CD",
        "confluence_parents": [10001, 10002, 10003],
        "jira_project":    "CICD",
    },
    {
        "space":           "INFRA",
        "confluence_parents": [20001, 20002],
        "jira_project":    "INFRA",
    },
    {
        "space":           "ENG-ENV",
        "confluence_parents": [30001],
        "jira_project":    "ENGENV",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()


def fetch_confluence_pages(base_url: str, parent_ids: list[int]) -> list[dict]:
    pages = []
    with httpx.Client(base_url=base_url, timeout=10) as client:
        for pid in parent_ids:
            resp = client.get(
                "/wiki/rest/api/content",
                params={"ancestor": pid, "expand": "body.storage,version,space", "limit": 50},
            )
            resp.raise_for_status()
            for p in resp.json().get("results", []):
                body_html = p.get("body", {}).get("storage", {}).get("value", "")
                pages.append({
                    "title":      p["title"],
                    "space":      p["space"]["key"],
                    "text":       strip_html(body_html),
                    "source_type": "confluence",
                })
    return pages


def fetch_jira_issues(base_url: str, project: str, max_results: int = 50) -> list[dict]:
    issues = []
    with httpx.Client(base_url=base_url, timeout=10) as client:
        resp = client.get(
            "/rest/api/2/search",
            params={"jql": f"project={project} ORDER BY id ASC", "maxResults": max_results},
        )
        resp.raise_for_status()
        for iss in resp.json().get("issues", []):
            fields = iss["fields"]
            text = f"{fields['summary']}\n\n{fields.get('description', '')}"
            comments = fields.get("comment", {}).get("comments", [])
            for c in comments:
                text += f"\n\nComment by {c['author']['displayName']}: {c['body']}"
            # derive space from project key
            space_map = {"CICD": "CI-CD", "INFRA": "INFRA", "ENGENV": "ENG-ENV"}
            space = space_map.get(project, project)
            issues.append({
                "title":      f"{iss['key']}: {fields['summary']}",
                "space":      space,
                "text":       text.strip(),
                "source_type": "jira",
            })
    return issues


# ---------------------------------------------------------------------------
# QA generation via Gemini Flash
# ---------------------------------------------------------------------------

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

QA_PROMPT = """\
You are creating evaluation data for a RAG system.

Given the document below, generate {n} question-answer pairs.
Rules:
- Questions must be answerable from the document alone.
- Answers must be factually grounded in the document (no speculation).
- Questions should be realistic internal engineering questions.
- Keep answers concise (1-3 sentences).

Output ONLY valid JSON — a list of objects, each with "question" and "answer" keys.
No markdown fences, no explanation.

Document title: {title}
Document text:
{text}
"""


def generate_qa_pairs(title: str, text: str, n: int = 2) -> list[dict]:
    if not text.strip():
        return []

    prompt = QA_PROMPT.format(n=n, title=title, text=text[:3000])

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }

    for attempt in range(3):
        try:
            resp = httpx.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            pairs = json.loads(raw)
            return [
                {"question": p["question"], "ground_truth": p["answer"]}
                for p in pairs
                if "question" in p and "answer" in p
            ]
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  [WARN] failed to generate QA for '{title}': {e}", file=sys.stderr)
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate golden QA datasets")
    parser.add_argument("--mock-apis-url", default="http://localhost:8081")
    parser.add_argument("--pairs-per-doc", type=int, default=2,
                        help="QA pairs to generate per document")
    parser.add_argument("--out-dir", default=str(Path(__file__).parent / "datasets"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for space_cfg in SPACES:
        space = space_cfg["space"]
        print(f"\n=== {space} ===")

        docs: list[dict] = []

        # Fetch Confluence pages
        try:
            pages = fetch_confluence_pages(args.mock_apis_url, space_cfg["confluence_parents"])
            print(f"  Confluence pages: {len(pages)}")
            docs.extend(pages)
        except Exception as e:
            print(f"  [ERROR] Confluence fetch failed: {e}", file=sys.stderr)

        # Fetch Jira issues
        try:
            issues = fetch_jira_issues(args.mock_apis_url, space_cfg["jira_project"])
            print(f"  Jira issues: {len(issues)}")
            docs.extend(issues)
        except Exception as e:
            print(f"  [ERROR] Jira fetch failed: {e}", file=sys.stderr)

        if not docs:
            print(f"  [WARN] no documents found for {space}, skipping")
            continue

        records: list[dict] = []
        for doc in docs:
            pairs = generate_qa_pairs(doc["title"], doc["text"], n=args.pairs_per_doc)
            for pair in pairs:
                records.append({
                    "question":     pair["question"],
                    "ground_truth": pair["ground_truth"],
                    "source_title": doc["title"],
                    "source_type":  doc["source_type"],
                    "space":        space,
                })
            # Stay within Gemini free-tier rate limits
            time.sleep(0.5)

        out_path = out_dir / f"golden_{space}.json"
        out_path.write_text(json.dumps(records, indent=2))
        print(f"  Wrote {len(records)} QA pairs → {out_path}")


if __name__ == "__main__":
    main()
