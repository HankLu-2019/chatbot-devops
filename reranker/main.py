"""
Reranker sidecar service.

Provides a FastAPI endpoint that accepts a query and a list of text chunks,
scores them with a cross-encoder model, and returns them sorted by relevance.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import CrossEncoder


# ---------------------------------------------------------------------------
# Model — loaded once at startup
# ---------------------------------------------------------------------------

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_model: CrossEncoder | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the cross-encoder model on startup."""
    global _model
    print(f"Loading cross-encoder model: {MODEL_NAME} ...")
    _model = CrossEncoder(MODEL_NAME)
    print("Model loaded.")
    yield
    # (no teardown needed)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Acme Reranker Service",
    description="Cross-encoder reranking for RAG pipelines",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class Chunk(BaseModel):
    id: int
    text: str


class RerankRequest(BaseModel):
    query: str
    chunks: list[Chunk]


class RankedChunk(BaseModel):
    chunk_id: int
    score: float
    text: str


class RerankResponse(BaseModel):
    results: list[RankedChunk]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    """Returns 200 OK when the service is ready."""
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/rerank", response_model=RerankResponse, summary="Rerank chunks by relevance to query")
def rerank(request: RerankRequest) -> Any:
    """
    Accept a query and a list of text chunks.
    Score each chunk against the query using the cross-encoder.
    Return the chunks sorted by score descending.
    """
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    if not request.chunks:
        return RerankResponse(results=[])

    # Build (query, passage) pairs for the cross-encoder
    pairs = [(request.query, chunk.text) for chunk in request.chunks]

    # Predict returns a numpy array of floats
    scores: list[float] = _model.predict(pairs).tolist()

    # Zip with original chunk metadata and sort by score descending
    ranked = sorted(
        zip(request.chunks, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    results = [
        RankedChunk(chunk_id=chunk.id, score=round(float(score), 4), text=chunk.text)
        for chunk, score in ranked
    ]

    return RerankResponse(results=results)
