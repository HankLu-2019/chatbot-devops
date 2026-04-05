#!/usr/bin/env python3
"""
RAG generation evaluation using RAGAS.

Metrics computed:
  - Faithfulness       — is the answer grounded in retrieved contexts? (hallucination detector)
  - Answer Relevancy   — does the answer address the question?
  - Context Precision  — are retrieved chunks relevant to the query?
  - Context Recall     — do retrieved chunks contain enough information to answer?

Requires:
  - App running at http://localhost:3000
  - GEMINI_API_KEY in .env
  - Golden datasets in datasets/ (run generate_dataset.py first)

Usage:
    python eval_rag.py [--app-url http://localhost:3000] [--space CI-CD]

Output:
    results/rag_<timestamp>.md
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from tabulate import tabulate

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    sys.exit("GEMINI_API_KEY not set")

# ---------------------------------------------------------------------------
# RAGAS + LangChain Gemini setup
# ---------------------------------------------------------------------------

try:
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    from ragas import evaluate, EvaluationDataset, SingleTurnSample
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
except ImportError as e:
    sys.exit(
        f"Missing dependency: {e}\n"
        "Run: pip install -r requirements.txt"
    )

os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

_llm = LangchainLLMWrapper(
    ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GEMINI_API_KEY)
)
_embeddings = LangchainEmbeddingsWrapper(
    GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=GEMINI_API_KEY,
    )
)

METRICS = [
    Faithfulness(llm=_llm),
    AnswerRelevancy(llm=_llm, embeddings=_embeddings),
    ContextPrecision(llm=_llm),
    ContextRecall(llm=_llm),
]


# ---------------------------------------------------------------------------
# Call chat API
# ---------------------------------------------------------------------------

def call_chat_api(app_url: str, question: str, space: str | None) -> dict:
    """POST to /api/chat with include_contexts=true. Returns {answer, contexts}."""
    payload: dict = {"message": question, "include_contexts": True}
    if space:
        payload["space"] = space

    resp = httpx.post(
        f"{app_url}/api/chat",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "answer":   data.get("answer", ""),
        "contexts": data.get("contexts", []),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RAGAS evaluation for RAG pipeline")
    parser.add_argument("--app-url", default="http://localhost:3000")
    parser.add_argument("--datasets-dir", default=str(Path(__file__).parent / "datasets"))
    parser.add_argument("--space", help="Evaluate a single space only")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max questions per space (0 = all, useful for smoke tests)")
    args = parser.parse_args()

    # Health check
    try:
        httpx.get(f"{args.app_url}/api/chat", timeout=5)
    except httpx.ConnectError:
        sys.exit(
            f"Cannot reach app at {args.app_url}\n"
            "Start with: docker-compose up -d app  OR  cd app && npm run dev"
        )

    datasets_dir = Path(args.datasets_dir)
    dataset_files = sorted(datasets_dir.glob("golden_*.json"))
    if not dataset_files:
        sys.exit(f"No golden datasets in {datasets_dir}. Run generate_dataset.py first.")

    if args.space:
        dataset_files = [f for f in dataset_files if args.space in f.name]

    results_by_space: dict[str, dict] = {}

    for dataset_file in dataset_files:
        space = dataset_file.stem.replace("golden_", "")
        records = json.loads(dataset_file.read_text())
        if not records:
            print(f"[WARN] {dataset_file.name} is empty, skipping")
            continue

        if args.limit:
            records = records[: args.limit]

        print(f"\n=== {space} ({len(records)} questions) ===")

        samples: list[SingleTurnSample] = []

        for i, rec in enumerate(records):
            q = rec["question"]
            gt = rec["ground_truth"]
            print(f"  [{i+1:2d}/{len(records)}] {q[:70]}")

            try:
                result = call_chat_api(args.app_url, q, space)
                answer = result["answer"]
                contexts = result["contexts"]

                if not answer or not contexts:
                    print(f"    [WARN] empty answer or contexts, skipping")
                    continue

                samples.append(
                    SingleTurnSample(
                        user_input=q,
                        response=answer,
                        retrieved_contexts=contexts,
                        reference=gt,
                    )
                )
                time.sleep(0.3)  # rate limit buffer
            except Exception as e:
                print(f"    [ERROR] {e}", file=sys.stderr)

        if not samples:
            print(f"  [WARN] no valid samples for {space}")
            continue

        print(f"\n  Running RAGAS on {len(samples)} samples...")
        dataset = EvaluationDataset(samples=samples)
        try:
            result = evaluate(dataset=dataset, metrics=METRICS)
            scores = result.to_pandas()
        except Exception as e:
            print(f"  [ERROR] RAGAS evaluation failed: {e}", file=sys.stderr)
            continue

        metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
        space_scores: dict[str, float] = {}
        for col in metric_names:
            if col in scores.columns:
                space_scores[col] = float(scores[col].mean())

        results_by_space[space] = {**space_scores, "n": len(samples)}
        print(f"  Scores: {space_scores}")

    if not results_by_space:
        sys.exit("No results computed.")

    # ---------------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------------
    metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

    rows = []
    for space, v in results_by_space.items():
        rows.append([
            space,
            f"{v.get('faithfulness', float('nan')):.3f}",
            f"{v.get('answer_relevancy', float('nan')):.3f}",
            f"{v.get('context_precision', float('nan')):.3f}",
            f"{v.get('context_recall', float('nan')):.3f}",
            v["n"],
        ])

    # Macro averages (only over spaces that have the metric)
    def _avg(key: str) -> str:
        vals = [v[key] for v in results_by_space.values() if key in v]
        return f"{sum(vals)/len(vals):.3f}" if vals else "N/A"

    rows.append([
        "**MACRO AVG**",
        _avg("faithfulness"),
        _avg("answer_relevancy"),
        _avg("context_precision"),
        _avg("context_recall"),
        sum(v["n"] for v in results_by_space.values()),
    ])

    headers = ["Space", "Faithfulness", "Ans.Relevancy", "Ctx.Precision", "Ctx.Recall", "N"]
    table_md = tabulate(rows, headers=headers, tablefmt="github")

    report = f"""# RAG Generation Evaluation (RAGAS)

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Metrics

{table_md}

## Interpretation

| Metric | What it measures | Target |
|--------|-----------------|--------|
| Faithfulness | Answer is grounded in retrieved contexts — no hallucination | ≥ 0.80 |
| Answer Relevancy | Answer addresses the question | ≥ 0.80 |
| Context Precision | Retrieved chunks are relevant to the query | ≥ 0.70 |
| Context Recall | Retrieved chunks contain enough info to answer | ≥ 0.70 |

All scores are on [0, 1]. Higher is better.

## Actions on low scores

- **Low Faithfulness** → LLM is hallucinating; tighten the system prompt or reduce context size.
- **Low Answer Relevancy** → Query rewriting or generation prompt needs improvement.
- **Low Context Precision** → Reranker threshold too permissive; tune `RERANK_THRESHOLD` or `MAX_CONTEXT_CHUNKS`.
- **Low Context Recall** → Retrieval is missing relevant docs; tune `SEARCH_ALPHA`, `DECAY_RATE_PER_DAY`, or top-30 limit.
"""

    print("\n" + table_md)

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"rag_{ts}.md"
    out_path.write_text(report)
    print(f"\nReport saved → {out_path}")


if __name__ == "__main__":
    main()
