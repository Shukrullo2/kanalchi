FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libpq5 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" MEDIA_TMP_DIR=/var/tmp/media
RUN mkdir -p /var/tmp/media && useradd -m app && chown -R app:app /app /var/tmp/media
USER app
EXPOSE 8000
CMD ["uvicorn", "kanalchi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
