FROM ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc AS uv

FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

# procps supplies /bin/ps, which orchestration/process_control.py requires to
# read owned-process identity; python:3.13-slim does not ship it.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend
COPY demo/taskmaster ./demo/taskmaster

RUN uv sync --frozen --no-dev --no-editable \
    && groupadd --gid 10001 graphene \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin graphene

USER 10001:10001
EXPOSE 8080

CMD ["uvicorn", "graphene.orchestration.cloud:create_cloud_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
