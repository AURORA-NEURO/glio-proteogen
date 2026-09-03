"""Readiness coverage for every mounted fitted research profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters import api as api_module
from glio_proteogen.adapters import research_readiness as readiness_module
from glio_proteogen.adapters.research_readiness import (
    RESEARCH_PROFILE_ROUTES,
    RESEARCH_READINESS_CHECKS,
    ResearchReadinessCheck,
    ResearchReadinessError,
    ensure_research_profiles_ready,
)
from glio_proteogen.deployment import DeploymentSettings, create_deployment_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

HTTP_OK = 200


def _recording_check(
    lane_id: str,
    calls: list[str],
    *,
    failure: str | None = None,
) -> Callable[[], None]:
    def check() -> None:
        calls.append(lane_id)
        if failure is not None:
            raise RuntimeError(failure)

    return check


def test_registry_covers_every_mounted_research_profile_route(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(
            database_path=tmp_path / "profile-inventory" / "events.sqlite3",
            environment="test",
        )
    )
    mounted_profile_routes: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        path = getattr(route, "path", None)
        if isinstance(path, str) and "/research/" in path and path.endswith("/profile"):
            mounted_profile_routes.add(path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(original_router.routes)

    assert set(RESEARCH_PROFILE_ROUTES) == mounted_profile_routes
    assert len(RESEARCH_PROFILE_ROUTES) == len(set(RESEARCH_PROFILE_ROUTES))
    assert len(RESEARCH_READINESS_CHECKS) < len(RESEARCH_PROFILE_ROUTES)


def test_registry_runs_every_check_before_reporting_a_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    checks = (
        ResearchReadinessCheck(
            lane_id="first-lane",
            profile_routes=("/v1/research/first/profile",),
            check=_recording_check("first-lane", calls),
        ),
        ResearchReadinessCheck(
            lane_id="failed-lane",
            profile_routes=("/v1/research/failed/profile",),
            check=_recording_check(
                "failed-lane",
                calls,
                failure="private fitted-artifact path and exception text",
            ),
        ),
        ResearchReadinessCheck(
            lane_id="last-lane",
            profile_routes=("/v1/research/last/profile",),
            check=_recording_check("last-lane", calls),
        ),
    )
    monkeypatch.setattr(readiness_module, "RESEARCH_READINESS_CHECKS", checks)

    with pytest.raises(ResearchReadinessError) as raised:
        ensure_research_profiles_ready()

    assert calls == ["first-lane", "failed-lane", "last-lane"]
    assert raised.value.lane_id == "failed-lane"
    assert str(raised.value) == "research lane is not ready: failed-lane"
    assert "private fitted-artifact" not in str(raised.value)


def test_successful_profile_checks_do_not_change_readyz_chain_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        readiness_module,
        "RESEARCH_READINESS_CHECKS",
        (
            ResearchReadinessCheck(
                lane_id="successful-lane",
                profile_routes=("/v1/research/successful/profile",),
                check=_recording_check("successful-lane", calls),
            ),
        ),
    )
    app = create_deployment_app(
        DeploymentSettings(
            database_path=tmp_path / "successful-readiness" / "events.sqlite3",
            environment="test",
        )
    )

    with TestClient(app) as client:
        checked = client.get("/readyz")
        monkeypatch.setattr(api_module, "ensure_research_profiles_ready", lambda: None)
        original = client.get("/readyz")

    assert calls == ["successful-lane"]
    assert checked.status_code == HTTP_OK
    assert checked.json() == original.json()
    assert checked.json()["valid"] is True
