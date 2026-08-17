"""Executable M12-03 evaluator over a frozen metadata-only scenario matrix."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m12_03 import (
    M1203_M1202_INPUT_MEDIA_TYPE,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticQualityStatus,
    MechanisticValueKind,
    NegativeControlStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c12_driver_protein_consequence import (
    MechanisticFeatureAuthorizationError,
    construct_mechanistic_features,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-03"
SCENARIO_PATH: Final = Path("tests/fixtures/m12_03/scenarios.json")


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"eval.artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1203_eval": label}),
        media_type=media_type,
    )


def _context(*, denied: bool = False) -> ExecutionContext:
    accepted = UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED
    consent = ConsentState.WITHHELD if denied else ConsentState.GRANTED
    return ExecutionContext(
        request_id="eval.request.m1203",
        actor_id="eval.actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="eval.approved",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("approved"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="eval.identity",
                state=(
                    IdentityLineageState.CONFLICTED if denied else IdentityLineageState.RESOLVED
                ),
                policy_version="1.0.0",
                binding_digest=sha256_digest({"subject": "eval"}),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="eval.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="eval.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="eval.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="eval.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="eval.intended-use",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended-use"),
            ),
        ),
    )


def build_request(
    *,
    negative: NegativeControlStatus = NegativeControlStatus.PASSED,
    quality: MechanisticQualityStatus = MechanisticQualityStatus.ACCEPTED,
    denied: bool = False,
) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
    source = _artifact("feature-source")
    feature = MechanisticFeature(
        feature_id="eval.feature.pathway",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.SCALAR,
        unit="score",
        scalar_value=0.75,
        lineage=MechanisticFeatureLineage(
            feature_id="eval.feature.pathway",
            source_artifacts=(source,),
            claim="Evaluation pathway feature is source-bound.",
            transformation_ids=("eval.transform",),
        ),
    )
    configuration = MechanisticFeatureConfiguration(
        configuration_id="eval.config",
        version="1.0.0",
        model_family="curated-mechanistic-baseline",
        transformation_ids=("eval.transform",),
        topology_reference=_artifact("topology"),
        negative_control_artifacts=(_artifact("negative-control"),),
    )
    return ConstructBiomarkerPanelMechanisticFeaturesRequest(
        request_id="eval.request.m1203",
        context=_context(denied=denied),
        upstream_result=_artifact("upstream", M1203_M1202_INPUT_MEDIA_TYPE),
        configuration=configuration,
        feature_inputs=(feature,),
        negative_control_status=negative,
        quality_status=quality,
        source_artifacts=(source,),
    )


def _fixture() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def run_evaluator() -> dict[str, object]:  # noqa: C901 - fixture matrix is intentionally explicit.
    fixture = _fixture()
    checks: list[EvalCheck] = []
    cases = cast("list[dict[str, object]]", fixture["cases"])
    for case in cases:
        case_id = str(case["case_id"])
        try:
            if case_id == "supported":
                result = construct_mechanistic_features(build_request())
                passed = (
                    result.status.value == case["expected_status"]
                    and result.feature_object is not None
                )
            elif case_id == "negative-failed":
                result = construct_mechanistic_features(
                    build_request(negative=NegativeControlStatus.FAILED)
                )
                passed = (
                    result.status.value == case["expected_status"] and result.feature_object is None
                )
            elif case_id == "negative-not-evaluable":
                result = construct_mechanistic_features(
                    build_request(negative=NegativeControlStatus.NOT_EVALUABLE)
                )
                passed = (
                    result.status.value == case["expected_status"] and result.feature_object is None
                )
            elif case_id == "quality-rejected":
                result = construct_mechanistic_features(
                    build_request(quality=MechanisticQualityStatus.REJECTED)
                )
                passed = (
                    result.status.value == case["expected_status"] and result.feature_object is None
                )
            elif case_id == "denied-control":
                try:
                    construct_mechanistic_features(build_request(denied=True))
                except MechanisticFeatureAuthorizationError:
                    passed = True
                else:
                    passed = False
            elif case_id == "deterministic-replay":
                first = construct_mechanistic_features(build_request())
                second = construct_mechanistic_features(build_request())
                passed = first.result_digest == second.result_digest
            else:
                passed = False
                detail = "unknown fixture case"
        except Exception as exc:  # noqa: BLE001 - evaluator reports failures, not traces.
            passed = False
            detail = type(exc).__name__
        else:
            detail = "passed" if passed else "expectation mismatch"
        checks.append(EvalCheck(case_id, passed, detail))
    fixture_digest = sha256_digest(fixture)
    return {
        "module_id": MODULE_ID,
        "fixture_path": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest,
        "declared_cases": len(checks),
        "executed_cases": len(checks),
        "passed_cases": sum(item.passed for item in checks),
        "passed": all(item.passed for item in checks),
        "checks": [asdict(item) for item in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    _ = parser.parse_args()
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
