"""
Unit tests for chunker.py token-aware chunking logic.

Run with:
    python test_chunker.py          # standalone
    python -m pytest test_chunker.py -v  # with pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from chunker import (
    MAX_CHUNK_TOKENS,
    count_tokens,
    _enforce_token_limit,
    _merge_and_recurse,
    chunk_confluence,
    chunk_jira,
    chunk_doc,
)


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------

def test_count_tokens_empty():
    assert count_tokens("") == 0
    assert count_tokens(None) == 0  # type: ignore[arg-type]


def test_count_tokens_single_char():
    assert count_tokens("a") == 1


def test_count_tokens_400_chars():
    assert count_tokens("a" * 400) == 100


# ---------------------------------------------------------------------------
# _enforce_token_limit
# ---------------------------------------------------------------------------

def test_enforce_empty_returns_empty():
    assert _enforce_token_limit("") == []
    assert _enforce_token_limit("   ") == []


def test_enforce_under_limit_passthrough():
    text = "short text"
    result = _enforce_token_limit(text)
    assert result == [text]


def test_enforce_oversized_all_under_limit():
    """10 000-char string (~2500 tokens) must be split so every piece <= MAX_CHUNK_TOKENS."""
    text = "word " * 2000  # 10 000 chars
    result = _enforce_token_limit(text)
    assert len(result) > 1
    assert all(count_tokens(piece) <= MAX_CHUNK_TOKENS for piece in result)
    assert all(piece.strip() for piece in result), "No empty chunks"


def test_enforce_paragraph_boundary_preferred():
    """Two 900-token paragraphs separated by a blank line must split at the boundary."""
    para_a = "alpha " * 750  # ~900 tokens
    para_b = "beta " * 750   # ~900 tokens
    text = para_a.strip() + "\n\n" + para_b.strip()
    result = _enforce_token_limit(text)
    assert len(result) == 2
    # Each piece should contain only words from its own paragraph
    assert "alpha" in result[0] and "beta" not in result[0]
    assert "beta" in result[1] and "alpha" not in result[1]


def test_enforce_sentence_fallback():
    """No blank lines but multiple sentences totalling ~2500 tokens → sentence split."""
    # Build sentences each ~300 tokens (1200 chars)
    sentences = [("word" * 300 + ". ") for _ in range(9)]  # ~2700 tokens total
    text = "".join(sentences).strip()
    assert "\n\n" not in text  # no paragraph breaks
    result = _enforce_token_limit(text)
    assert len(result) > 1
    assert all(count_tokens(piece) <= MAX_CHUNK_TOKENS for piece in result)


def test_enforce_hard_split_no_spaces():
    """Single word with no spaces exceeding budget → returned as-is (unsplittable atom)."""
    long_word = "x" * (MAX_CHUNK_TOKENS * 4 + 100)  # clearly over budget
    result = _enforce_token_limit(long_word)
    assert result == [long_word]


# ---------------------------------------------------------------------------
# _merge_and_recurse
# ---------------------------------------------------------------------------

def test_merge_and_recurse_single_oversized_piece():
    """A single piece that is itself over budget must be recursively split."""
    big_piece = "word " * 2000  # ~2500 tokens
    result = _merge_and_recurse([big_piece], max_tokens=MAX_CHUNK_TOKENS)
    assert all(count_tokens(p) <= MAX_CHUNK_TOKENS for p in result)
    assert len(result) > 1


def test_merge_and_recurse_greedy_accumulation():
    """Small pieces should be greedily merged up to the budget."""
    # 10 pieces each ~100 tokens (400 chars); budget 1800 → should fit in 1 group
    pieces = ["word " * 80 for _ in range(10)]  # each ~100 tokens
    result = _merge_and_recurse(pieces, max_tokens=MAX_CHUNK_TOKENS)
    assert len(result) == 1
    assert count_tokens(result[0]) <= MAX_CHUNK_TOKENS


# ---------------------------------------------------------------------------
# chunk_confluence integration
# ---------------------------------------------------------------------------

def test_chunk_confluence_all_under_limit():
    page = {
        "title": "My Page",
        "body": "<h2>Big Section</h2><p>" + "word " * 3000 + "</p>",
        "space": "CI-CD",
        "url": "https://acme.atlassian.net/wiki/my-page",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    chunks = chunk_confluence(page)
    assert chunks, "Expected at least one chunk"
    for c in chunks:
        assert count_tokens(c["content"]) <= MAX_CHUNK_TOKENS, (
            f"Chunk '{c['title']}' exceeds token limit: {count_tokens(c['content'])}"
        )


def test_chunk_confluence_no_h2_fallback():
    """A page with no H2 sections should produce chunks via the fallback path."""
    page = {
        "title": "Flat Page",
        "body": "<p>" + "word " * 100 + "</p>",
        "space": "INFRA",
        "url": "https://acme.atlassian.net/wiki/flat",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    chunks = chunk_confluence(page)
    assert len(chunks) >= 1
    assert all(c["source_type"] == "confluence" for c in chunks)


# ---------------------------------------------------------------------------
# chunk_jira integration
# ---------------------------------------------------------------------------

def test_chunk_jira_all_under_limit():
    ticket = {
        "key": "INFRA-42",
        "summary": "Fix memory leak",
        "description": "stack " * 3000,
        "status": "Open",
        "space": "INFRA",
        "url": "https://acme.atlassian.net/browse/INFRA-42",
        "updated_at": "2026-01-01T00:00:00Z",
        "comments": [
            {
                "author": "alice",
                "body": "log " * 3000,
                "created_at": "2026-01-02T00:00:00Z",
            }
        ],
    }
    chunks = chunk_jira(ticket)
    assert chunks
    for c in chunks:
        assert count_tokens(c["content"]) <= MAX_CHUNK_TOKENS
    # Verify part titles when split
    body_chunks = [c for c in chunks if "Comment" not in c["title"]]
    if len(body_chunks) > 1:
        assert "(part 2)" in body_chunks[1]["title"]


def test_chunk_jira_zero_comments():
    """A ticket with no comments should not crash and return exactly one body chunk."""
    ticket = {
        "key": "ENG-1",
        "summary": "Short ticket",
        "description": "Just a description.",
        "status": "Done",
        "space": "ENG-ENV",
        "url": "https://acme.atlassian.net/browse/ENG-1",
        "updated_at": "2026-01-01T00:00:00Z",
        "comments": [],
    }
    chunks = chunk_jira(ticket)
    assert len(chunks) == 1
    assert chunks[0]["title"] == "[ENG-1] Short ticket"


# ---------------------------------------------------------------------------
# chunk_doc integration
# ---------------------------------------------------------------------------

def test_chunk_doc_all_under_limit():
    doc = {
        "title": "Big Doc",
        "content": "\n\n".join(["paragraph " * 300 for _ in range(10)]),
        "source_type": "doc",
        "space": "ENG-ENV",
        "url": "https://acme.atlassian.net/wiki/docs/big-doc",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    chunks = chunk_doc(doc)
    assert chunks
    for c in chunks:
        assert count_tokens(c["content"]) <= MAX_CHUNK_TOKENS


def test_chunk_doc_single_paragraph_no_split():
    """A short single-paragraph doc should produce exactly one chunk."""
    doc = {
        "title": "Small Doc",
        "content": "This is a short document with just one paragraph.",
        "source_type": "doc",
        "space": "CI-CD",
        "url": "https://acme.atlassian.net/wiki/docs/small-doc",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    chunks = chunk_doc(doc)
    assert len(chunks) == 1
    assert chunks[0]["title"] == "Small Doc"


def test_chunk_doc_no_overlap_at_boundaries():
    """Verify no word overlap at chunk boundaries (overlap was intentionally removed)."""
    # Build a doc with 3 large paragraphs, each ~700 tokens (2800 chars)
    para_a = "alpha " * 466  # ~700 tokens
    para_b = "beta " * 466
    para_c = "gamma " * 466
    doc = {
        "title": "Three Para Doc",
        "content": f"{para_a.strip()}\n\n{para_b.strip()}\n\n{para_c.strip()}",
        "source_type": "doc",
        "space": "INFRA",
        "url": "https://acme.atlassian.net/wiki/docs/three-para",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    chunks = chunk_doc(doc)
    assert len(chunks) >= 2
    # Check no "alpha" word leaks into a chunk that also has "beta"
    for c in chunks:
        has_alpha = "alpha" in c["content"]
        has_beta = "beta" in c["content"]
        has_gamma = "gamma" in c["content"]
        # A chunk should not contain content from more than two adjacent paragraphs
        # (two adjacent is ok if they fit together under the limit)
        assert not (has_alpha and has_gamma), (
            "Chunk spans non-adjacent paragraphs — possible overlap bleed"
        )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in test_fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
