"""Execute the locked synthetic M14-03 evaluator corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tests.modules.c14_microenvironment_protein_deconvolution.test_m14_03_runtime import (
    _artifact,
    _request,
)

from glio_proteogen.contracts.m14_03 import (
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_03_mechanistic_feature_constructor as m1403,
)

_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m14_03" / "scenarios.json"


def _case_request(kind: str) -> object:  # noqa: PLR0911
    request = _request()
    if kind == "supported":
        return request
    if kind == "unsupported_family":
        return _request(model_family="scientific_model_not_frozen")
    if kind == "duplicate_negative_control":
        configuration = request.configuration.model_copy(
            update={
                "negative_control_artifacts": (
                    _artifact("duplicate-control"),
                    _artifact("duplicate-control"),
                )
            }
        )
        return request.model_copy(update={"configuration": configuration})
    if kind == "denied_control":
        return _request(quality=UpstreamDecisionState.REJECTED)
    if kind == "wrong_upstream":
        return request.model_copy(
            update={"upstream_result": _artifact("wrong-upstream", media_type="application/json")}
        )
    if kind == "unknown_field":
        payload = request.model_dump(mode="python")
        payload["unexpected"] = True
        return payload
    if kind == "self_loop":
        lineage = MechanisticFeatureLineage(
            feature_id="feature.m1403.evaluator",
            source_artifacts=(_artifact("self-loop"),),
            claim="Caller-declared evaluator feature.",
        )
        feature = MechanisticFeature(
            feature_id="feature.m1403.evaluator",
            version="1.0.0",
            kind=MechanisticFeatureKind.PATHWAY,
            value_kind=MechanisticValueKind.CATEGORICAL,
            unit="caller_declared",
            category="caller_declared:pathway",
            lineage=lineage,
        )
        return {
            "relation": {
                "relation_id": "relation.m1403.self-loop",
                "source_feature_id": feature.feature_id,
                "target_feature_id": feature.feature_id,
                "kind": MechanisticRelationKind.PARTICIPATES,
            }
        }
    if kind == "empty_source":
        return request.model_copy(update={"source_artifacts": ()})
    raise _UnknownEvaluatorCaseError


class _UnknownEvaluatorCaseError(ValueError):
    def __init__(self) -> None:
        super().__init__("unknown evaluator case")


def _execute(kind: str) -> str:
    candidate = _case_request(kind)
    if kind == "self_loop":
        MechanisticRelation.model_validate(candidate["relation"], strict=True)  # type: ignore[index]
        return "constructed"
    if kind == "empty_source":
        ConstructProteinSubtypeMechanisticFeaturesRequest.model_validate(candidate, strict=True)
        return "constructed"
    result = m1403.M1403Service().construct(candidate)
    return result.status.value


def main() -> int:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    outcomes: list[dict[str, Any]] = []
    for case in fixture["cases"]:
        expected = case["expected"]
        try:
            actual = _execute(case["kind"])
        except m1403.M1403AuthorizationError:
            actual = "authorization_error"
        except (ValidationError, TypeError, ValueError):
            actual = "validation_error"
        passed = actual == expected
        outcomes.append(
            {"id": case["id"], "actual": actual, "expected": expected, "passed": passed}
        )
    declared = len(fixture["cases"])
    executed = len(outcomes)
    report = {
        "module_id": fixture["module_id"],
        "dossier_slice": fixture["dossier_slice"],
        "requirement_sha256": fixture["requirement_sha256"],
        "declared": declared,
        "executed": executed,
        "passed": declared == executed and all(item["passed"] for item in outcomes),
        "outcomes": outcomes,
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
