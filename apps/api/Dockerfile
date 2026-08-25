FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.14.6-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system rci && useradd --system --gid rci --home-dir /app rci \
    && chown rci:rci /app

COPY --chown=rci:rci pyproject.toml uv.lock ./
COPY --chown=rci:rci apps/api/pyproject.toml apps/api/pyproject.toml
COPY --chown=rci:rci apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY --chown=rci:rci apps/scheduler/pyproject.toml apps/scheduler/pyproject.toml
COPY --chown=rci:rci packages/python/rci-core/pyproject.toml packages/python/rci-core/pyproject.toml
COPY --chown=rci:rci packages/python/rci-agents/pyproject.toml packages/python/rci-agents/pyproject.toml
COPY --chown=rci:rci packages/python/rci-analytics/pyproject.toml packages/python/rci-analytics/pyproject.toml
COPY --chown=rci:rci packages/python/rci-automation/pyproject.toml packages/python/rci-automation/pyproject.toml
COPY --chown=rci:rci packages/python/rci-contracts/pyproject.toml packages/python/rci-contracts/pyproject.toml
COPY --chown=rci:rci packages/python/rci-collections/pyproject.toml packages/python/rci-collections/pyproject.toml
COPY --chown=rci:rci packages/python/rci-db/pyproject.toml packages/python/rci-db/pyproject.toml
COPY --chown=rci:rci packages/python/rci-locations/pyproject.toml packages/python/rci-locations/pyproject.toml
COPY --chown=rci:rci packages/python/rci-providers/pyproject.toml packages/python/rci-providers/pyproject.toml
COPY --chown=rci:rci packages/python/rci-products/pyproject.toml packages/python/rci-products/pyproject.toml
COPY --chown=rci:rci packages/python/rci-retailer-packs/pyproject.toml packages/python/rci-retailer-packs/pyproject.toml
COPY --chown=rci:rci packages/python/rci-results/pyproject.toml packages/python/rci-results/pyproject.toml
COPY --chown=rci:rci packages/python/rci-studies/pyproject.toml packages/python/rci-studies/pyproject.toml
USER rci
RUN uv sync --frozen --no-dev --package rci-api --no-install-workspace

COPY --chown=rci:rci apps/api apps/api
COPY --chown=rci:rci packages/python packages/python
COPY --chown=rci:rci config config
COPY --chown=rci:rci database database
COPY --chown=rci:rci fixtures/location_master fixtures/location_master
COPY --chown=rci:rci product-packs product-packs
COPY --chown=rci:rci retailer-packs retailer-packs
COPY --chown=rci:rci brand-foundations brand-foundations
COPY --chown=rci:rci agent-prompts agent-prompts
COPY --chown=rci:rci report-blueprints report-blueprints
COPY --chown=rci:rci schemas schemas
COPY --chown=rci:rci scripts/build_live_matching_v2_queue.py scripts/build_live_matching_v2_queue.py
COPY --chown=rci:rci scripts/audit_matching_v2_evidence_gaps.py scripts/audit_matching_v2_evidence_gaps.py
COPY --chown=rci:rci scripts/plan_spring_valley_location_panel.py scripts/plan_spring_valley_location_panel.py
RUN uv sync --frozen --no-dev --package rci-api

EXPOSE 8000
CMD ["python", "-m", "rci_api"]
