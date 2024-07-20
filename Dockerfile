FROM python:3.11.9-slim AS base

RUN pip install poetry==1.8.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY citibank ./citibank
COPY pyproject.toml poetry.lock README.md ./

RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --without dev

FROM python:3.11.9-slim AS runtime

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
apt-get install -y chromium && \
apt-get clean && \
rm -rf /var/lib/apt/lists/*

COPY --from=base ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY citibank ./citibank

CMD ["python", "-m", "citibank.main"]
