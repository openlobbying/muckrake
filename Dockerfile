# syntax=docker/dockerfile:1

# ---- Builder: resolve and install the environment with uv ----
FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

# plyvel (LevelDB) and pyicu (ICU) are sdist-only and compile from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    libleveldb-dev \
    libicu-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Keep the venv outside /app so a bind-mounted repo doesn't shadow it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependency layer: cached until pyproject.toml/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Project layer: muckrake itself (editable, pointing at /app/src).
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# ---- Runtime ----
FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libleveldb1d \
    libicu72 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Full repo: the CLI reads datasets/ and writes data/ relative to the repo root.
COPY . .
RUN mkdir -p data

EXPOSE 8000
CMD ["muckrake", "server", "--host", "0.0.0.0"]
