.PHONY: bootstrap check check-python check-typescript dev down

bootstrap:
	uv sync --all-packages --all-groups
	pnpm install --frozen-lockfile
	pnpm --filter @rci/web exec playwright install chromium

check: check-python check-typescript

check-python:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy apps packages/python
	uv run pytest
	uv run alembic -c database/alembic.ini upgrade head --sql

check-typescript:
	pnpm contracts:check
	pnpm format:check
	pnpm lint
	pnpm typecheck
	pnpm test
	pnpm build
	pnpm test:e2e

dev:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down
