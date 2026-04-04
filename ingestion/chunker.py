"""
Structure-aware chunking for Confluence pages, Jira tickets, and plain-text docs.
"""

import hashlib
import re
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Token-budget constants
# ---------------------------------------------------------------------------

# gemini-embedding-001 accepts up to 2048 tokens. Target 1800 to leave headroom
# for any metadata the embedding API may prepend internally.
MAX_CHUNK_TOKENS: int = 1800

# 1 token ≈ 4 characters (GPT-style BPE heuristic). For technical content
# (code, URLs, version strings), tokens are shorter per character, so this
# heuristic over-estimates token count — the safe direction for a size guard.
_CHARS_PER_TOKEN: float = 4.0


def count_tokens(text: str) -> int:
    """Estimate token count via the len/4 character heuristic."""
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _split_on_paragraphs(text: str) -> list[str]:
    """Split on blank-line boundaries. Returns [] if no boundary found."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts if len(parts) > 1 else []


def _split_on_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation followed by whitespace.
    Returns [] if no sentence boundary is found.
    Note: intentionally simple regex — fragile on version strings like
    'v1.28.3. See docs', but sentence splitting is the last resort before
    hard word split, so occasional mis-splits are acceptable."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return parts if len(parts) > 1 else []


def _merge_and_recurse(pieces: list[str], max_tokens: int) -> list[str]:
    """Greedily accumulate pieces into groups within max_tokens, then
    recursively enforce the limit on any group that still overflows."""
    groups: list[str] = []
    current_parts: list[str] = []
    current_tokens: int = 0

    for piece in pieces:
        piece_tokens = count_tokens(piece)
        # 1-token cost for the "\n\n" separator (2 chars / 4 chars-per-token ≈ 1)
        sep_cost = 1 if current_parts else 0
        if current_parts and current_tokens + sep_cost + piece_tokens > max_tokens:
            groups.append("\n\n".join(current_parts))
            current_parts = [piece]
            current_tokens = piece_tokens
        else:
            current_parts.append(piece)
            current_tokens += sep_cost + piece_tokens

    if current_parts:
        groups.append("\n\n".join(current_parts))

    result: list[str] = []
    for g in groups:
        result.extend(_enforce_token_limit(g, max_tokens))
    return result


def _enforce_token_limit(text: str, max_tokens: int = MAX_CHUNK_TOKENS) -> list[str]:
    """Recursively split text until every piece is within max_tokens.

    Split priority:
      1. Blank-line paragraph boundaries
      2. Sentence-ending punctuation boundaries
      3. Hard word-boundary split (last resort)

    Edge cases:
      - Empty/whitespace input      → []
      - Single unsplittable word    → returned as-is (can't split further)
      - Already within budget       → [text]
    """
    text = text.strip()
    if not text:
        return []
    if count_tokens(text) <= max_tokens:
        return [text]

    paragraphs = _split_on_paragraphs(text)
    if paragraphs:
        return _merge_and_recurse(paragraphs, max_tokens)

    sentences = _split_on_sentences(text)
    if sentences:
        return _merge_and_recurse(sentences, max_tokens)

    # Hard word-boundary split
    words = text.split()
    if len(words) <= 1:
        return [text]  # unsplittable atom (e.g. very long URL)
    mid = len(words) // 2
    return (
        _enforce_token_limit(" ".join(words[:mid]), max_tokens)
        + _enforce_token_limit(" ".join(words[mid:]), max_tokens)
    )


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

    NOTE: Superseded by _enforce_token_limit + _merge_and_recurse for all internal
    call sites. Retained here for any external callers. Do not use in new code.
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
        # Prefix is included in full_text so _enforce_token_limit counts it in
        # the budget automatically — no separate prefix math needed.
        full_text = f"{title} > {heading}\n\n{body_text}"
        sub_texts = _enforce_token_limit(full_text)

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

def _jira_parts(text: str, base_title: str, fixed_fields: dict) -> list[dict]:
    """Split text via _enforce_token_limit and return chunk dicts for one Jira item.

    *fixed_fields* must contain: source_type, space, ticket_id, status, url, updated_at.
    """
    parts = _enforce_token_limit(text)
    return [
        {
            "content":      part,
            "title":        base_title if len(parts) == 1 else f"{base_title} (part {i + 1})",
            "content_hash": content_hash(part),
            **fixed_fields,
        }
        for i, part in enumerate(parts)
    ]


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
    base_fields = {
        "source_type": "jira",
        "space":       space,
        "ticket_id":   key,
        "status":      status,
        "url":         url,
    }
    chunks: list[dict] = []

    # Main body chunk — split if description is oversized (e.g. pasted stack traces)
    body_text = f"{summary}\n\n{description}".strip()
    chunks.extend(_jira_parts(body_text, f"[{key}] {summary}", {**base_fields, "updated_at": updated_at}))

    # One chunk per comment — guard against oversized comment bodies
    for comment in ticket.get("comments", []):
        comment_body = comment.get("body", "").strip()
        author = comment.get("author", "unknown")
        comment_text = f"Comment on [{key}] {summary}:\n\n{comment_body}"
        chunks.extend(_jira_parts(
            comment_text,
            f"[{key}] Comment by {author}",
            {**base_fields, "updated_at": comment.get("created_at", updated_at)},
        ))

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

    # Group paragraphs up to MAX_CHUNK_TOKENS per group, recursively splitting
    # any single paragraph that exceeds the budget on its own.
    # Note: no word overlap between groups — overlap at ingestion time creates
    # duplicate embeddings in the vector store. Context continuity is handled
    # at retrieval time by assembleByBudget in lib/rag.ts.
    safe_groups = _merge_and_recurse(paragraphs, MAX_CHUNK_TOKENS)

    chunks: list[dict] = []
    for i, group_text in enumerate(safe_groups):
        chunk_title = title if len(safe_groups) == 1 else f"{title} (part {i + 1})"
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
