#!/usr/bin/env python3
"""
Retrieval evaluation: Recall@5, Recall@10, MRR@10.

For each question in the golden datasets, embeds the question with Gemini,
runs the same hybrid search SQL as the app (BM25 + vector, alpha-blend + decay),
and checks whether the source document appears in the top-K results.

Matching: a result is considered correct if its title equals the source_title
recorded in the golden dataset (exact or prefix match).

Usage:
    python eval_retrieval.py [--datasets-dir datasets/] [--top-k 10]

Outputs:
    - Markdown table to stdout
    - results/retrieval_<timestamp>.md
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from tabulate import tabulate

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    sys.exit("GEMINI_API_KEY not set")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ragdb",
)

# Must match app/lib/rag.ts constants
SEARCH_ALPHA = 0.7
DECAY_RATE_PER_DAY = 0.003
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
EMBED_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{EMBED_MODEL}:embedContent"
)

# ---------------------------------------------------------------------------
# Hybrid search SQL (mirrors app/lib/rag.ts fusionSQL)
# ---------------------------------------------------------------------------

_ALPHA_VEC  = SEARCH_ALPHA
_ALPHA_BM25 = 1.0 - SEARCH_ALPHA

FUSION_SQL = f"""
WITH bm25_raw AS (
  SELECT id, paradedb.score(id) AS s
  FROM documents
  WHERE documents @@@ paradedb.parse($1)
  LIMIT 50
),
bm25_norm AS (
  SELECT id,
    CASE WHEN MAX(s) OVER() = MIN(s) OVER() THEN 0.5
         ELSE (s - MIN(s) OVER()) / (MAX(s) OVER() - MIN(s) OVER())
    END AS score_n
  FROM bm25_raw
),
vec_raw AS (
  SELECT id, 1 - (embedding <=> $2::vector) AS s
  FROM documents
  ORDER BY embedding <=> $2::vector
  LIMIT 50
),
vec_norm AS (
  SELECT id,
    CASE WHEN MAX(s) OVER() = MIN(s) OVER() THEN 0.5
         ELSE (s - MIN(s) OVER()) / (MAX(s) OVER() - MIN(s) OVER())
    END AS score_n
  FROM vec_raw
),
fused AS (
  SELECT COALESCE(b.id, v.id) AS id,
         {_ALPHA_BM25} * COALESCE(b.score_n, 0) +
         {_ALPHA_VEC}  * COALESCE(v.score_n, 0) AS hybrid_score
  FROM bm25_norm b
  FULL JOIN vec_norm v ON b.id = v.id
)
SELECT d.id, d.title, d.url,
       f.hybrid_score * EXP(
         {-DECAY_RATE_PER_DAY} * GREATEST(0, COALESCE(
           EXTRACT(EPOCH FROM (NOW() - d.updated_at)) / 86400.0, 0
         ))
       ) AS score
FROM fused f
JOIN documents d ON d.id = f.id
ORDER BY score DESC
LIMIT 30
"""

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_query(text: str) -> list[float]:
    resp = httpx.post(
        EMBED_URL,
        params={"key": GEMINI_API_KEY},
        json={
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        },
        timeout=15,
    )
    resp.raise_for_status()
    values = resp.json()["embedding"]["values"]
    if len(values) != EMBED_DIM:
        raise ValueError(f"Unexpected embedding dim: {len(values)}")
    return values


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def hybrid_search(cur, query: str, embedding: list[float]) -> list[dict]:
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    cur.execute(FUSION_SQL, (query, vec_str))
    rows = cur.fetchall()
    return [{"id": r[0], "title": r[1], "url": r[2], "score": float(r[3])} for r in rows]


def is_match(result_title: str, source_title: str) -> bool:
    """True if result_title matches source_title (by prefix — chunker appends ' > Section')."""
    rt = result_title.lower()
    st = source_title.lower()
    return rt == st or rt.startswith(st) or st.startswith(rt)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def recall_at_k(ranked: list[dict], source_title: str, k: int) -> float:
    for r in ranked[:k]:
        if is_match(r["title"], source_title):
            return 1.0
    return 0.0


def reciprocal_rank(ranked: list[dict], source_title: str, k: int = 10) -> float:
    for i, r in enumerate(ranked[:k], start=1):
        if is_match(r["title"], source_title):
            return 1.0 / i
    return 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval evaluation")
    parser.add_argument("--datasets-dir", default=str(Path(__file__).parent / "datasets"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--space", help="Evaluate a single space only")
    args = parser.parse_args()

    datasets_dir = Path(args.datasets_dir)
    dataset_files = sorted(datasets_dir.glob("golden_*.json"))
    if not dataset_files:
        sys.exit(f"No golden datasets found in {datasets_dir}. Run generate_dataset.py first.")

    if args.space:
        dataset_files = [f for f in dataset_files if args.space in f.name]

    # Connect to DB
    try:
        conn = psycopg2.connect(DATABASE_URL)
        register_vector(conn)
        cur = conn.cursor()
    except Exception as e:
        sys.exit(f"DB connection failed: {e}\nIs ParadeDB running? docker-compose up paradedb")

    results_by_space: dict[str, dict] = {}

    for dataset_file in dataset_files:
        space = dataset_file.stem.replace("golden_", "")
        records = json.loads(dataset_file.read_text())
        if not records:
            print(f"[WARN] {dataset_file.name} is empty, skipping")
            continue

        print(f"\nEvaluating retrieval for {space} ({len(records)} questions)...")

        r5_scores, r10_scores, rr_scores = [], [], []

        for i, rec in enumerate(records):
            q = rec["question"]
            src_title = rec["source_title"]

            try:
                embedding = embed_query(q)
                time.sleep(0.1)  # rate limit
            except Exception as e:
                print(f"  [WARN] embed failed for q{i}: {e}", file=sys.stderr)
                continue

            ranked = hybrid_search(cur, q, embedding)

            r5  = recall_at_k(ranked, src_title, 5)
            r10 = recall_at_k(ranked, src_title, 10)
            rr  = reciprocal_rank(ranked, src_title, 10)

            r5_scores.append(r5)
            r10_scores.append(r10)
            rr_scores.append(rr)

            print(f"  [{i+1:2d}/{len(records)}] R@5={r5:.0f} R@10={r10:.0f} RR={rr:.3f}  {q[:60]}")

        if not r5_scores:
            continue

        results_by_space[space] = {
            "recall@5":  sum(r5_scores)  / len(r5_scores),
            "recall@10": sum(r10_scores) / len(r10_scores),
            "mrr@10":    sum(rr_scores)  / len(rr_scores),
            "n":         len(r5_scores),
        }

    cur.close()
    conn.close()

    if not results_by_space:
        sys.exit("No results computed.")

    # ---------------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------------
    rows = [
        [space, f"{v['recall@5']:.3f}", f"{v['recall@10']:.3f}", f"{v['mrr@10']:.3f}", v["n"]]
        for space, v in results_by_space.items()
    ]
    # Macro averages
    all_vals = list(results_by_space.values())
    rows.append([
        "**MACRO AVG**",
        f"{sum(v['recall@5']  for v in all_vals) / len(all_vals):.3f}",
        f"{sum(v['recall@10'] for v in all_vals) / len(all_vals):.3f}",
        f"{sum(v['mrr@10']    for v in all_vals) / len(all_vals):.3f}",
        sum(v['n'] for v in all_vals),
    ])

    headers = ["Space", "Recall@5", "Recall@10", "MRR@10", "N"]
    table_md = tabulate(rows, headers=headers, tablefmt="github")

    report = f"""# Retrieval Evaluation

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Metrics

{table_md}

## Interpretation

- **Recall@K**: fraction of questions where the source document appears in top-K results.
- **MRR@10**: Mean Reciprocal Rank — rewards higher-ranked correct results.
- Target: Recall@5 ≥ 0.70, MRR@10 ≥ 0.50 for a well-tuned hybrid search.
"""

    print("\n" + table_md)

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"retrieval_{ts}.md"
    out_path.write_text(report)
    print(f"\nReport saved → {out_path}")


if __name__ == "__main__":
    main()
