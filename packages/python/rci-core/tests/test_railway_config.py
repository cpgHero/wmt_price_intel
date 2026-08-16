from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_railway_services_use_pinned_dockerfiles_and_health_checks() -> None:
    expected = {
        "web": ("apps/web/Dockerfile", "/health"),
        "api": ("apps/api/Dockerfile", "/health/ready"),
        "worker": ("apps/worker/Dockerfile", "/health/ready"),
        "scheduler": ("apps/scheduler/Dockerfile", "/health/ready"),
    }
    for service, (dockerfile, healthcheck) in expected.items():
        config = json.loads((REPOSITORY_ROOT / f"infra/railway/{service}.json").read_text())
        assert config["$schema"] == "https://railway.com/railway.schema.json"
        assert config["build"]["builder"] == "DOCKERFILE"
        assert config["build"]["dockerfilePath"] == dockerfile
        assert (REPOSITORY_ROOT / dockerfile).is_file()
        assert config["deploy"]["healthcheckPath"] == healthcheck
        assert config["deploy"]["restartPolicyType"] == "ON_FAILURE"


def test_only_api_owns_the_railway_migration_predeploy() -> None:
    configs = {
        service: json.loads((REPOSITORY_ROOT / f"infra/railway/{service}.json").read_text())
        for service in ("web", "api", "worker", "scheduler")
    }
    assert configs["api"]["deploy"]["preDeployCommand"] == (
        "alembic -c database/alembic.ini upgrade head"
    )
    assert all(
        "preDeployCommand" not in configs[service]["deploy"]
        for service in ("web", "worker", "scheduler")
    )
    assert configs["worker"]["deploy"]["overlapSeconds"] == 0
    assert configs["worker"]["deploy"]["drainingSeconds"] >= 60


def test_production_images_drop_root_and_pin_runtimes() -> None:
    dockerfiles = {
        name: (REPOSITORY_ROOT / f"apps/{name}/Dockerfile").read_text()
        for name in ("web", "api", "worker", "scheduler")
    }
    assert "FROM node:24.18.0-slim" in dockerfiles["web"]
    assert "USER nextjs" in dockerfiles["web"]
    for service in ("api", "worker", "scheduler"):
        assert "FROM python:3.14.6-slim" in dockerfiles[service]
        assert "USER rci" in dockerfiles[service]


def test_report_catalog_is_packaged_and_watched_by_runtime_consumers() -> None:
    api_dockerfile = (REPOSITORY_ROOT / "apps/api/Dockerfile").read_text()
    assert "COPY --chown=rci:rci report-blueprints report-blueprints" in api_dockerfile

    for service in ("api", "worker", "scheduler"):
        config = json.loads((REPOSITORY_ROOT / f"infra/railway/{service}.json").read_text())
        watch_patterns = set(config["build"]["watchPatterns"])
        assert "/product-packs/**" in watch_patterns
        assert "/report-blueprints/**" in watch_patterns


def test_governed_agent_package_and_prompts_are_in_runtime_build_contexts() -> None:
    api_dockerfile = (REPOSITORY_ROOT / "apps/api/Dockerfile").read_text()
    assert "packages/python/rci-agents/pyproject.toml" in api_dockerfile
    assert "COPY --chown=rci:rci agent-prompts agent-prompts" in api_dockerfile
    for service in ("api", "worker"):
        config = json.loads((REPOSITORY_ROOT / f"infra/railway/{service}.json").read_text())
        assert "/agent-prompts/**" in set(config["build"]["watchPatterns"])
