#!/usr/bin/env python3
"""
Main ingestion script.

Loads Confluence pages, Jira tickets, and plain-text docs, chunks them,
embeds them with Gemini, and upserts into PostgreSQL (ParadeDB).

Usage:
    pip install -r requirements.txt
    python ingest.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from openai import OpenAI

from chunker import chunk_confluence, chunk_jira, chunk_doc

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ragdb",
)

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# OpenAI setup
# ---------------------------------------------------------------------------

openai_client = OpenAI(api_key=OPENAI_API_KEY)


def embed_text(text: str) -> list[float]:
    """Embed a single text string using OpenAI text-embedding-3-small."""
    result = openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=text,
        dimensions=EMBED_DIM,
    )
    embedding = result.data[0].embedding
    if len(embedding) != EMBED_DIM:
        raise ValueError(f"Expected {EMBED_DIM}-dim embedding, got {len(embedding)}")
    return embedding


def embed_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """
    Embed a list of texts in batches, returning a list of embedding vectors.
    """
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        print(f"  Embedding texts {i + 1}–{i + len(batch)} of {len(texts)} ...", flush=True)
        result = openai_client.embeddings.create(
            model=EMBED_MODEL,
            input=batch,
            dimensions=EMBED_DIM,
        )
        for item in result.data:
            embeddings.append(item.embedding)
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
# Data loading
# ---------------------------------------------------------------------------

def load_confluence_chunks() -> list[dict]:
    path = DATA_DIR / "confluence" / "pages.json"
    with open(path, "r", encoding="utf-8") as f:
        pages = json.load(f)
    chunks = []
    for page in pages:
        chunks.extend(chunk_confluence(page))
    print(f"Confluence: {len(pages)} pages → {len(chunks)} chunks")
    return chunks


def load_jira_chunks() -> list[dict]:
    path = DATA_DIR / "jira" / "tickets.json"
    with open(path, "r", encoding="utf-8") as f:
        tickets = json.load(f)
    chunks = []
    for ticket in tickets:
        chunks.extend(chunk_jira(ticket))
    print(f"Jira: {len(tickets)} tickets → {len(chunks)} chunks")
    return chunks


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

def main() -> None:
    print("=== Acme RAG Ingestion Pipeline ===\n")

    # 1. Load all chunks
    all_chunks: list[dict] = []
    all_chunks.extend(load_confluence_chunks())
    all_chunks.extend(load_jira_chunks())
    all_chunks.extend(load_doc_chunks())
    print(f"\nTotal chunks to process: {len(all_chunks)}\n")

    # 2. Connect to DB and find already-ingested hashes
    print("Connecting to database ...")
    conn = get_connection()
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


if __name__ == "__main__":
    main()
