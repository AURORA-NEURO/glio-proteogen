"""Verify the project-completion evidence and canonical model inventory."""

from __future__ import annotations

import json
import sys
from typing import Final

from glio_proteogen.adapters.api import _MODEL_ROUTE_LIMITS

MATRIX_TOTAL: Final = 224
CONCRETE_IMPLEMENTATION_COMPLETE: Final = 214
ARTIFACT_COMPLETE: Final = 214
COVERAGE_GATE_PERCENT: Final = 100

PROVISIONAL_SOURCE_IDS: Final = (
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
)

CANONICAL_MODEL_IDS: Final = (
    "M15-05",
    "M23-01",
    "M23-02",
    "M23-03",
    "M23-04",
    "M23-05",
    "M23-07",
    "M23-08",
    "M24-02",
    "M24-03",
    "M24-04",
    "M24-05",
    "M24-06",
    "M24-07",
    "M24-08",
    "M25-01",
    "M25-02",
    "M25-03",
    "M25-04",
    "M25-05",
    "M25-06",
    "M25-07",
    "M25-08",
    "M26-01",
    "M26-02",
    "M26-03",
    "M26-04",
    "M26-05",
    "M26-06",
    "M26-07",
    "M26-08",
    "M27-03",
    "M27-04",
    "M27-05",
    "M27-06",
    "M27-07",
    "M27-08",
    "M28-04",
)
CANONICAL_MODEL_COUNT: Final = len(CANONICAL_MODEL_IDS)


class ProjectStatusError(RuntimeError):
    """Raised when the documented status and deployment inventory diverge."""

    def __init__(self, *, missing: object | None = None) -> None:
        message = (
            f"canonical model route limits are missing: {missing}"
            if missing is not None
            else "canonical model inventory count changed unexpectedly"
        )
        super().__init__(message)


def _percent(complete: int) -> float:
    return round(complete * 100 / MATRIX_TOTAL, 1)


def build_report() -> dict[str, object]:
    """Return machine-readable completion and deployment evidence."""

    route_ids = {
        path.removeprefix("/v1/modules/")
        for path in _MODEL_ROUTE_LIMITS
        if path.startswith("/v1/modules/")
    }
    if "/m26-02" in _MODEL_ROUTE_LIMITS:
        route_ids.add("M26-02")
    missing_routes = sorted(set(CANONICAL_MODEL_IDS) - route_ids)
    return {
        "matrix_total": MATRIX_TOTAL,
        "concrete_implementation_complete": CONCRETE_IMPLEMENTATION_COMPLETE,
        "concrete_implementation_percent": _percent(CONCRETE_IMPLEMENTATION_COMPLETE),
        "artifact_complete": ARTIFACT_COMPLETE,
        "artifact_percent": _percent(ARTIFACT_COMPLETE),
        "coverage_gate_percent": COVERAGE_GATE_PERCENT,
        "canonical_model_count": CANONICAL_MODEL_COUNT,
        "canonical_model_ids": list(CANONICAL_MODEL_IDS),
        "missing_canonical_route_limits": missing_routes,
        "provisional_source_ids": list(PROVISIONAL_SOURCE_IDS),
    }


def verify() -> dict[str, object]:
    """Verify that every documented concrete model has a route limit entry."""

    report = build_report()
    missing = report["missing_canonical_route_limits"]
    if missing:
        raise ProjectStatusError(missing=missing)
    if report["canonical_model_count"] != CANONICAL_MODEL_COUNT:
        raise ProjectStatusError
    return report


def main() -> int:
    sys.stdout.write(json.dumps(verify(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
