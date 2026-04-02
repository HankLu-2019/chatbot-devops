FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY ingest.py chunker.py ./

# data/ is mounted at runtime via docker-compose volume
CMD ["python", "ingest.py"]
