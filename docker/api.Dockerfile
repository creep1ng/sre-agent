# Digest verified against Docker Hub on 2026-09-08. Keep the tag for
# recognition and the digest for repeatable builds.
FROM rust:1.98.1-slim-bookworm@sha256:ff521445a372125ed4f76e1453a1f8098f2d05332d1601d30db1c1f62757e730 AS rust-toolchain

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS python-base

ARG SRE_AGENT_APPLICATION_VERSION=""
ARG SRE_AGENT_CONTRACT_VERSION=""
ARG SRE_AGENT_BUILD_REVISION=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}" \
    SRE_AGENT_APPLICATION_VERSION=${SRE_AGENT_APPLICATION_VERSION} \
    SRE_AGENT_CONTRACT_VERSION=${SRE_AGENT_CONTRACT_VERSION} \
    SRE_AGENT_BUILD_REVISION=${SRE_AGENT_BUILD_REVISION}

WORKDIR /app

FROM python-base AS base

ENV CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH="/usr/local/cargo/bin:${PATH}"
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
COPY rust ./rust
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

# uv is build-only. The runtime stage receives only the locked virtual
# environment and application sources, never the quality-tool dependency group.
ARG UV_VERSION=0.8.14
RUN pip install --no-cache-dir "uv==${UV_VERSION}" \
    && uv sync --locked --no-dev

FROM base AS runtime-dependencies

FROM runtime-dependencies AS checks

RUN apt-get update \
    && apt-get install --no-install-recommends -y git shellcheck \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --locked --extra dev

COPY tests ./tests
COPY scripts ./scripts
COPY schemas ./schemas
COPY public ./public
COPY styles ./styles
COPY agent ./agent
COPY docs ./docs
COPY .github ./.github
COPY docker ./docker
COPY .dockerignore compose.yaml README.md .importlinter playwright.config.js playwright.production.config.js ./

USER 65532:65532
CMD ["sh", "-c", "python scripts/assert_test_database_isolated.py && shellcheck docker/harness-entrypoint.sh scripts/worktree-compose && ruff check --no-cache . && ruff format --check --no-cache . && uv lock --check --no-cache && lint-imports --no-cache && mypy --cache-dir=/tmp/mypy src/sre_agent/incident/persistence.py src/sre_agent/incident/runtime.py src/sre_agent/governance/dto.py src/sre_agent/governance/authorization.py && pytest && alembic check"]

FROM python-base AS runtime

COPY --from=runtime-dependencies /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY --from=runtime-dependencies /app/src ./src
COPY agent/workflows ./agent/workflows

USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "sre_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
