FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM python:3.13-slim

# COMPATIBILITY ONLY: this image serves the mutable legacy HTTP demo. It is not
# the authoritative v2 CLI/viewer path and cannot run v2 fixed tests on Linux.
LABEL org.opencontainers.image.description="Graphene legacy HTTP compatibility demo; not authoritative v2 execution"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git procps \
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
ENV GRAPHENE_ENTRYPOINT_MODE="legacy-http-compatibility" \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Compatibility entry point. The served page repeats this warning persistently.
CMD ["sh", "-c", "echo 'LEGACY HTTP COMPATIBILITY DEMO — NOT AUTHORITATIVE V2' >&2; exec uvicorn graphene.legacy_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
