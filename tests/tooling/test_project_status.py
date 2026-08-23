"""Tests for reproducible project-status evidence."""

from pathlib import Path

from fastapi.testclient import TestClient
from tools.verify_project_status import (
    ARTIFACT_COMPLETE,
    CANONICAL_MODEL_COUNT,
    CANONICAL_MODEL_IDS,
    CONCRETE_IMPLEMENTATION_COMPLETE,
    MATRIX_TOTAL,
    _percent,
    build_report,
    verify,
)

from glio_proteogen.deployment import DeploymentSettings, create_deployment_app

HTTP_OK = 200


def test_project_status_reports_current_completion_estimates() -> None:
    report = verify()

    assert report["matrix_total"] == MATRIX_TOTAL
    assert report["concrete_implementation_complete"] == CONCRETE_IMPLEMENTATION_COMPLETE
    assert report["concrete_implementation_percent"] == _percent(CONCRETE_IMPLEMENTATION_COMPLETE)
    assert report["artifact_complete"] == ARTIFACT_COMPLETE
    assert report["artifact_percent"] == _percent(ARTIFACT_COMPLETE)
    assert report["canonical_model_count"] == CANONICAL_MODEL_COUNT
    assert report["missing_canonical_route_limits"] == []


def test_project_status_keeps_unresolved_abis_explicit() -> None:
    report = build_report()

    assert report["provisional_source_ids"] == [
        "M23_06",
        "M24_01",
        "M27_01",
        "M28_01",
        "M28_02",
        "M28_03",
        "M28_05",
        "M28_06",
        "M28_07",
        "M28_08",
    ]


def test_canonical_inventory_is_mounted_in_the_runtime_catalog(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        response = client.get("/v1/deployment/catalog")

    assert response.status_code == HTTP_OK
    catalog = response.json()
    assert catalog["unmounted_route_limit_prefixes"] == []
    mounted_ids = {module["module_id"] for module in catalog["modules"]}
    assert set(CANONICAL_MODEL_IDS) <= mounted_ids
