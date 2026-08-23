"""Static checks for the production container security and health contract."""

from __future__ import annotations

from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_runs_nonroot_and_checks_storage_readiness() -> None:
    dockerfile = (_REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "USER glio" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/readyz" in dockerfile
    assert "/livez" not in dockerfile.split("HEALTHCHECK", 1)[1]


def test_compose_is_readonly_and_healthchecks_storage_readiness() -> None:
    compose = (_REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "glio-proteogen-data:/data/glio-proteogen" in compose
    assert "/readyz" in compose
    assert "/livez" not in compose.split("healthcheck:", 1)[1]
