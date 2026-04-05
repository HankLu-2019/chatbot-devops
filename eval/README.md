# RAG Evaluation Suite

End-to-end evaluation for the Acme RAG chatbot covering retrieval quality and generation quality.

## What's measured

| Layer      | Script              | Metrics                                                           |
| ---------- | ------------------- | ----------------------------------------------------------------- |
| Retrieval  | `eval_retrieval.py` | Recall@5, Recall@10, MRR@10                                       |
| Generation | `eval_rag.py`       | Faithfulness, Answer Relevancy, Context Precision, Context Recall |

## Prerequisites

- Python 3.11+
- `GEMINI_API_KEY` in root `.env`
- For retrieval eval: ParadeDB running (`docker-compose up paradedb`)
- For RAG eval: Full app stack running (`docker-compose up -d`)

## Setup

```bash
cd eval
pip install -r requirements.txt
```

## Step 1 — Generate golden dataset

Pulls documents from mock-apis and generates QA pairs with Gemini Flash.

```bash
# Requires mock-apis running on port 8081
docker-compose up mock-apis

python generate_dataset.py
# Optional flags:
#   --mock-apis-url http://localhost:8081   (default)
#   --pairs-per-doc 2                       (QA pairs per document)
#   --out-dir datasets/                     (output directory)
```

Output: `datasets/golden_CI-CD.json`, `datasets/golden_INFRA.json`, `datasets/golden_ENG-ENV.json`

Each record:

```json
{
  "question": "How does the canary deployment rollback work?",
  "ground_truth": "Rollback triggers automatically if error rate exceeds 1% during canary window.",
  "source_title": "Canary Deployment Runbook",
  "source_type": "confluence",
  "space": "CI-CD"
}
```

The golden datasets are committed to the repo after generation. Regenerate only when mock-apis data changes.

## Step 2 — Retrieval evaluation

Runs hybrid search (BM25 + vector, same SQL as the app) and measures whether the source document appears in the top-K results.

```bash
# Requires ParadeDB running and ingestion done
python eval_retrieval.py

# Options:
#   --space CI-CD        evaluate one space only
#   --top-k 10           (default)
#   --datasets-dir datasets/
```

Matching: a retrieved chunk is a hit if its `title` starts with or equals the golden record's `source_title` (chunker appends ` > Section` suffixes).

## Step 3 — RAG generation evaluation (RAGAS)

Calls the live chat API for each golden question, collects answer + retrieved contexts, and computes RAGAS metrics using Gemini Flash as the LLM judge.

```bash
# Requires full app stack: docker-compose up -d
python eval_rag.py

# Options:
#   --space CI-CD              evaluate one space only
#   --limit 5                  quick smoke test (5 questions per space)
#   --app-url http://localhost:3000
```

## Interpreting results

| Metric            | Target | Low score → action                                    |
| ----------------- | ------ | ----------------------------------------------------- |
| Recall@5          | ≥ 0.70 | Tune `SEARCH_ALPHA` or expand top-30 limit            |
| MRR@10            | ≥ 0.50 | Improve BM25 term matching (chunking quality)         |
| Faithfulness      | ≥ 0.80 | Tighten system prompt; reduce `MAX_CONTEXT_CHUNKS`    |
| Answer Relevancy  | ≥ 0.80 | Improve query rewriting prompt                        |
| Context Precision | ≥ 0.70 | Lower reranker threshold; reduce `MAX_CONTEXT_CHUNKS` |
| Context Recall    | ≥ 0.70 | Tune `SEARCH_ALPHA`, increase top-30 limit            |

## Results

Reports are saved to `results/` with timestamps:

```
results/
  retrieval_20260405_143022.md
  rag_20260405_143512.md
```
