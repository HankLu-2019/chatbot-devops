"""
Structure-aware chunking for Confluence pages, Jira tickets, and plain-text docs.
"""

import hashlib
import re
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Remove HTML tags and return plain text."""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=" ")


def content_hash(text: str) -> str:
    """
    Stable SHA-256 hash of normalised content.
    Normalisation: strip HTML tags, lowercase, collapse whitespace.
    """
    plain = strip_html(text)
    normalised = " ".join(plain.lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _word_count(text: str) -> int:
    return len(text.split())


def _split_into_token_chunks(text: str, max_words: int = 400, overlap_words: int = 50) -> list[str]:
    """
    Split a block of text into overlapping chunks of at most *max_words* words.
    Each successive chunk starts *overlap_words* words before the previous chunk ended.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words  # slide back for overlap
    return chunks


# ---------------------------------------------------------------------------
# Confluence chunking
# ---------------------------------------------------------------------------

def chunk_confluence(page: dict) -> list[dict]:
    """
    Parse the page body by H2 sections and return one chunk per section.
    Each chunk is prefixed with  "{title} > {heading}".

    Returns a list of chunk dicts with keys:
      content, title, source_type, space, url, updated_at, content_hash
    """
    title = page["title"]
    body_html = page.get("body", "")
    soup = BeautifulSoup(body_html, "html.parser")

    # Collect (heading_text, body_text) pairs split by <h2> tags
    sections: list[tuple[str, str]] = []
    current_heading = "Introduction"
    current_parts: list[str] = []

    for element in soup.children:
        tag_name = getattr(element, "name", None)
        if tag_name in ("h1",):
            # Skip the top-level H1 — we'll use the page title
            continue
        if tag_name == "h2":
            if current_parts:
                sections.append((current_heading, " ".join(current_parts).strip()))
                current_parts = []
            current_heading = element.get_text(separator=" ").strip()
        else:
            text = element.get_text(separator=" ").strip() if hasattr(element, "get_text") else str(element).strip()
            if text:
                current_parts.append(text)

    # Flush the last section
    if current_parts:
        sections.append((current_heading, " ".join(current_parts).strip()))

    # If the page has no H2 sections, treat the whole body as one chunk
    if not sections:
        plain = strip_html(body_html)
        sections = [("Full Content", plain)]

    chunks: list[dict] = []
    for heading, body_text in sections:
        prefix = f"{title} > {heading}\n\n"
        full_text = prefix + body_text

        # Split oversized sections into overlapping sub-chunks
        if _word_count(full_text) > 400:
            sub_texts = _split_into_token_chunks(full_text, max_words=400, overlap_words=50)
        else:
            sub_texts = [full_text]

        for sub in sub_texts:
            chunks.append({
                "content":      sub,
                "title":        f"{title} > {heading}",
                "source_type":  "confluence",
                "space":        page.get("space", ""),
                "url":          page.get("url", ""),
                "updated_at":   page.get("updated_at"),
                "content_hash": content_hash(sub),
            })

    return chunks


# ---------------------------------------------------------------------------
# Jira chunking
# ---------------------------------------------------------------------------

def chunk_jira(ticket: dict) -> list[dict]:
    """
    Produce one chunk for the main ticket body (summary + description) and
    one chunk per comment.

    Returns a list of chunk dicts with keys:
      content, title, source_type, ticket_id, status, url, updated_at, content_hash
    """
    key = ticket["key"]
    summary = ticket.get("summary", "")
    description = ticket.get("description", "")
    status = ticket.get("status", "")
    url = ticket.get("url", "")
    updated_at = ticket.get("updated_at")

    space = ticket.get("space", "")
    chunks: list[dict] = []

    # Main body chunk
    body_text = f"{summary}\n\n{description}".strip()
    chunks.append({
        "content":      body_text,
        "title":        f"[{key}] {summary}",
        "source_type":  "jira",
        "space":        space,
        "ticket_id":    key,
        "status":       status,
        "url":          url,
        "updated_at":   updated_at,
        "content_hash": content_hash(body_text),
    })

    # One chunk per comment
    for comment in ticket.get("comments", []):
        comment_body = comment.get("body", "").strip()
        author = comment.get("author", "unknown")
        comment_text = f"Comment on [{key}] {summary}:\n\n{comment_body}"
        chunks.append({
            "content":      comment_text,
            "title":        f"[{key}] Comment by {author}",
            "source_type":  "jira",
            "space":        space,
            "ticket_id":    key,
            "status":       status,
            "url":          url,
            "updated_at":   comment.get("created_at", updated_at),
            "content_hash": content_hash(comment_text),
        })

    return chunks


# ---------------------------------------------------------------------------
# Plain-text doc chunking
# ---------------------------------------------------------------------------

def chunk_doc(doc: dict) -> list[dict]:
    """
    Split plain text by blank-line-separated paragraphs, then group paragraphs
    into chunks of at most 400 words with 50-word overlap.

    *doc* must have keys: title, content, source_type, url, updated_at

    Returns a list of chunk dicts.
    """
    title = doc["title"]
    raw_text = doc.get("content", "")

    # Split on one or more blank lines
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]

    # Group paragraphs greedily until we would exceed 400 words
    groups: list[str] = []
    current_words: list[str] = []
    for para in paragraphs:
        para_words = para.split()
        if current_words and len(current_words) + len(para_words) > 400:
            groups.append(" ".join(current_words))
            # Overlap: carry forward last 50 words
            current_words = current_words[-50:] + para_words
        else:
            current_words.extend(para_words)
    if current_words:
        groups.append(" ".join(current_words))

    chunks: list[dict] = []
    for i, group_text in enumerate(groups):
        chunk_title = title if len(groups) == 1 else f"{title} (part {i + 1})"
        chunks.append({
            "content":      group_text,
            "title":        chunk_title,
            "source_type":  doc.get("source_type", "doc"),
            "space":        doc.get("space", ""),
            "url":          doc.get("url", ""),
            "updated_at":   doc.get("updated_at"),
            "content_hash": content_hash(group_text),
        })

    return chunks
