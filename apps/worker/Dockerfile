FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.14.6-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --system rci && useradd --system --gid rci --home-dir /app rci \
    && chown rci:rci /app
COPY --chown=rci:rci . .
USER rci
RUN uv sync --frozen --no-dev --package rci-worker
EXPOSE 8080
CMD ["rci-worker"]
