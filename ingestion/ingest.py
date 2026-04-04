#!/usr/bin/env python3
"""
Main ingestion script.

Loads Confluence pages, Jira tickets, and plain-text docs, chunks them,
embeds them with Gemini, and upserts into PostgreSQL (ParadeDB).

Usage:
    pip install -r requirements.txt
    python ingest.py
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from google import genai
from google.genai import types as genai_types

from chunker import chunk_confluence, chunk_jira, chunk_doc

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ragdb",
)

_REPO_ROOT = Path(__file__).parent.parent
# When running in Docker the volume is mounted at /data; honour that if present.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(_REPO_ROOT / "data")))

# Gemini embed API rate limit is 1500 RPM (free tier); add a small delay to be safe
EMBED_DELAY_SECONDS = 0.05

# ---------------------------------------------------------------------------
# Gemini setup (new google-genai SDK)
# ---------------------------------------------------------------------------

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


def embed_text(text: str) -> list[float]:
    """Embed a single text string using Gemini text-embedding-004."""
    result = gemini_client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config={"output_dimensionality": EMBED_DIM},
    )
    embedding = result.embeddings[0].values
    if len(embedding) != EMBED_DIM:
        raise ValueError(f"Expected {EMBED_DIM}-dim embedding, got {len(embedding)}")
    return list(embedding)


def embed_batch(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    """
    Embed a list of texts in batches, returning a list of embedding vectors.
    Adds a small sleep between calls to respect rate limits.
    """
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        print(f"  Embedding texts {i + 1}–{i + len(batch)} of {len(texts)} ...", flush=True)
        for text in batch:
            emb = embed_text(text)
            embeddings.append(emb)
            time.sleep(EMBED_DELAY_SECONDS)
    return embeddings


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def get_existing_hashes(conn) -> set[str]:
    """Return the set of content_hash values already in the database."""
    with conn.cursor() as cur:
        cur.execute("SELECT content_hash FROM documents WHERE content_hash IS NOT NULL")
        return {row[0] for row in cur.fetchall()}


def insert_chunk(conn, chunk: dict, embedding: list[float]) -> None:
    """Insert one chunk + its embedding into the documents table."""
    sql = """
        INSERT INTO documents
            (content, title, source_type, space, ticket_id, status, url, updated_at, content_hash, embedding)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (content_hash) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            chunk.get("content"),
            chunk.get("title"),
            chunk.get("source_type"),
            chunk.get("space"),
            chunk.get("ticket_id"),
            chunk.get("status"),
            chunk.get("url"),
            chunk.get("updated_at"),
            chunk.get("content_hash"),
            embedding,
        ))


# ---------------------------------------------------------------------------
# Config loading (scraper/config.yml is SSOT for space names)
# ---------------------------------------------------------------------------

def _load_spaces_from_config() -> list[str]:
    """Return list of space values from scraper/config.yml, or [] if unavailable."""
    if not _YAML_AVAILABLE:
        return []
    config_path = _REPO_ROOT / "scraper" / "config.yml"
    if not config_path.exists():
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        spaces = [team["space"] for team in cfg.get("teams", []) if "space" in team]
        print(f"Config: loaded {len(spaces)} spaces from scraper/config.yml: {spaces}")
        return spaces
    except Exception as exc:
        print(f"WARNING: could not parse scraper/config.yml: {exc}", file=sys.stderr)
        return []


# Map doc filename prefixes to team space values (hardcoded fallback)
_DOC_SPACE_MAP_DEFAULT = {
    "cicd-": "CI-CD",
    "ci-cd-": "CI-CD",
    "infra-": "INFRA",
    "infrastructure-": "INFRA",
    "runbook-": "INFRA",
    "eng-env-": "ENG-ENV",
    "onboarding-": "ENG-ENV",
}

def _build_doc_space_map() -> dict[str, str]:
    """
    Build DOC_SPACE_MAP from config.yml if available; fall back to hardcoded map.
    Config spaces produce prefix entries: 'ci-cd-' → 'CI-CD', etc.
    Always merges with the hardcoded map so existing prefixes still work.
    """
    space_map = dict(_DOC_SPACE_MAP_DEFAULT)
    spaces = _load_spaces_from_config()
    for space in spaces:
        prefix = space.lower().rstrip("-") + "-"
        if prefix not in space_map:
            space_map[prefix] = space
    return space_map

DOC_SPACE_MAP = _build_doc_space_map()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_confluence_chunks() -> tuple[list[dict], list[Path]]:
    """
    Scan data/<SPACE>/confluence_*.json files (skipping .tmp).
    Returns (chunks, processed_files).
    Falls back to legacy data/confluence/pages.json if it exists.
    """
    chunks: list[dict] = []
    processed_files: list[Path] = []
    total_pages = 0

    # New per-team folder structure
    for json_file in sorted(DATA_DIR.glob("*/confluence_*.json")):
        if json_file.suffix == ".tmp" or json_file.name.endswith(".tmp"):
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                pages = json.load(f)
            file_chunks = []
            for page in pages:
                file_chunks.extend(chunk_confluence(page))
            chunks.extend(file_chunks)
            total_pages += len(pages)
            processed_files.append(json_file)
            print(f"  Confluence {json_file}: {len(pages)} pages → {len(file_chunks)} chunks")
        except Exception as exc:
            print(f"  WARNING: could not load {json_file}: {exc}", file=sys.stderr)

    # Legacy fallback
    legacy_path = DATA_DIR / "confluence" / "pages.json"
    if legacy_path.exists() and legacy_path not in processed_files:
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                pages = json.load(f)
            legacy_chunks = []
            for page in pages:
                legacy_chunks.extend(chunk_confluence(page))
            chunks.extend(legacy_chunks)
            total_pages += len(pages)
            # Legacy file is not auto-deleted (manually managed)
            print(f"  Confluence (legacy) {legacy_path}: {len(pages)} pages → {len(legacy_chunks)} chunks")
        except Exception as exc:
            print(f"  WARNING: could not load legacy {legacy_path}: {exc}", file=sys.stderr)

    print(f"Confluence total: {total_pages} pages → {len(chunks)} chunks")
    return chunks, processed_files


def load_jira_chunks() -> tuple[list[dict], list[Path]]:
    """
    Scan data/<SPACE>/jira_*.json files (skipping .tmp).
    Returns (chunks, processed_files).
    Falls back to legacy data/jira/tickets.json if it exists.
    """
    chunks: list[dict] = []
    processed_files: list[Path] = []
    total_tickets = 0

    # New per-team folder structure
    for json_file in sorted(DATA_DIR.glob("*/jira_*.json")):
        if json_file.suffix == ".tmp" or json_file.name.endswith(".tmp"):
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                tickets = json.load(f)
            file_chunks = []
            for ticket in tickets:
                file_chunks.extend(chunk_jira(ticket))
            chunks.extend(file_chunks)
            total_tickets += len(tickets)
            processed_files.append(json_file)
            print(f"  Jira {json_file}: {len(tickets)} tickets → {len(file_chunks)} chunks")
        except Exception as exc:
            print(f"  WARNING: could not load {json_file}: {exc}", file=sys.stderr)

    # Legacy fallback
    legacy_path = DATA_DIR / "jira" / "tickets.json"
    if legacy_path.exists() and legacy_path not in processed_files:
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                tickets = json.load(f)
            legacy_chunks = []
            for ticket in tickets:
                legacy_chunks.extend(chunk_jira(ticket))
            chunks.extend(legacy_chunks)
            total_tickets += len(tickets)
            print(f"  Jira (legacy) {legacy_path}: {len(tickets)} tickets → {len(legacy_chunks)} chunks")
        except Exception as exc:
            print(f"  WARNING: could not load legacy {legacy_path}: {exc}", file=sys.stderr)

    print(f"Jira total: {total_tickets} tickets → {len(chunks)} chunks")
    return chunks, processed_files


def _infer_doc_space(stem: str) -> str:
    """Infer team space from a doc filename stem."""
    lower = stem.lower()
    for prefix, space in DOC_SPACE_MAP.items():
        if lower.startswith(prefix):
            return space
    return ""


def load_doc_chunks() -> list[dict]:
    docs_dir = DATA_DIR / "docs"
    chunks = []
    doc_count = 0
    for txt_path in sorted(docs_dir.glob("*.txt")):
        content = txt_path.read_text(encoding="utf-8")
        doc = {
            "title":       txt_path.stem.replace("-", " ").title(),
            "content":     content,
            "source_type": "doc",
            "space":       _infer_doc_space(txt_path.stem),
            "url":         f"https://acme.atlassian.net/wiki/docs/{txt_path.stem}",
            "updated_at":  datetime.now(tz=timezone.utc).isoformat(),
        }
        doc_chunks = chunk_doc(doc)
        chunks.extend(doc_chunks)
        doc_count += 1
    print(f"Docs: {doc_count} files → {len(chunks)} chunks")
    return chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def clean_documents(conn) -> None:
    """Delete all rows from the documents table (used before a full re-ingest)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM documents")
    conn.commit()
    print("Cleaned: all existing documents deleted.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Acme RAG Ingestion Pipeline")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete all existing documents before ingesting (full re-ingest). "
             "Use this after chunking logic changes that alter content_hash values.",
    )
    args = parser.parse_args()

    print("=== Acme RAG Ingestion Pipeline ===\n")

    # 1. Load all chunks
    all_chunks: list[dict] = []
    confluence_chunks, confluence_files = load_confluence_chunks()
    jira_chunks, jira_files = load_jira_chunks()
    doc_chunks = load_doc_chunks()

    all_chunks.extend(confluence_chunks)
    all_chunks.extend(jira_chunks)
    all_chunks.extend(doc_chunks)

    processed_files = confluence_files + jira_files

    if not all_chunks and not processed_files:
        print("No new data files found. Nothing to ingest.")
        return

    print(f"\nTotal chunks to process: {len(all_chunks)}\n")

    # 2. Connect to DB; optionally wipe before re-ingesting
    print("Connecting to database ...")
    conn = get_connection()
    if args.clean:
        clean_documents(conn)
    existing_hashes = get_existing_hashes(conn)
    print(f"Found {len(existing_hashes)} existing chunks in DB.\n")

    # 3. Filter out duplicates
    new_chunks = [c for c in all_chunks if c["content_hash"] not in existing_hashes]
    print(f"New chunks to embed and insert: {len(new_chunks)}")

    if not new_chunks:
        print("Nothing to do. All chunks already ingested.")
        conn.close()
        return

    # 4. Embed new chunks
    print("\nEmbedding new chunks ...")
    texts = [c["content"] for c in new_chunks]
    embeddings = embed_batch(texts)

    # 5. Insert into DB
    print("\nInserting into database ...")
    inserted = 0
    skipped = 0
    for chunk, embedding in zip(new_chunks, embeddings):
        try:
            insert_chunk(conn, chunk, embedding)
            inserted += 1
        except Exception as exc:
            print(f"  WARNING: failed to insert chunk '{chunk.get('title', '?')}': {exc}", file=sys.stderr)
            skipped += 1

    conn.commit()
    conn.close()

    print(f"\n=== Done ===")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (errors): {skipped}")
    print(f"  Already existed: {len(all_chunks) - len(new_chunks)}")

    # Delete processed scraper-output files now that DB commit succeeded
    if processed_files:
        print(f"\nCleaning up {len(processed_files)} processed file(s):")
        for f in processed_files:
            try:
                f.unlink()
                print(f"  Deleted: {f}")
            except Exception as exc:
                print(f"  WARNING: could not delete {f}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
