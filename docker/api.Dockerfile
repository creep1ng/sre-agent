FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN pip install --no-cache-dir .

FROM base AS checks

COPY uv.lock ./
RUN apt-get update \
    && apt-get install --no-install-recommends -y shellcheck \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir ".[dev]" "uv==0.8.14"

COPY tests ./tests
COPY scripts ./scripts
COPY schemas ./schemas
COPY docker ./docker
COPY compose.yaml README.md ./

USER 65532:65532
CMD ["sh", "-c", "shellcheck docker/harness-entrypoint.sh scripts/worktree-compose && ruff check --no-cache . && ruff format --check --no-cache . && uv lock --check --no-cache && pytest && alembic check"]

FROM base AS runtime

USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "sre_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
