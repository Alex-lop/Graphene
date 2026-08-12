FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend
COPY contracts ./contracts
COPY demo/fixture ./demo/fixture
COPY frontend ./frontend

RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 graphene \
    && chown -R graphene:graphene /app

USER graphene
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["sh", "-c", "exec uvicorn graphene.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
