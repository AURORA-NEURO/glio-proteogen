"""Deterministic M22-04 evaluator over a frozen transport matrix."""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_04 import (
    M2204_DOSSIER_SHA256,
    M2204_DOSSIER_SLICE,
    M2204_M2202_INPUT_MEDIA_TYPE,
    M2204_M2203_INPUT_MEDIA_TYPE,
    EvaluateProteinRnaDiscordanceExternalTransportRequest,
    EvaluationStatus,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m22_04_external_transport_evaluator import (
    M2204AuthorizationError,
    M2204Engine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M22-04"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m22_04" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "supported_all_dimensions",
    "domain_narrowed",
    "not_evaluable_abstention",
    "no_retained_domain_abstention",
    "specimen_mismatch",
    "authorization_gate",
    "upstream_media_boundary",
    "replay_tamper_determinism",
)
DIMENSIONS: Final = tuple(TransportDimension)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m2204_fixture": label})


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2204.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M22-04 transport evidence.",
        ),
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    decisions = {
        role: UpstreamDecisionReference(
            decision_id=f"decision.m2204.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}"),
        )
        for role in ("configuration", "provenance", "quality", "support", "intended-use")
    }
    return ContextReferences(
        approved_configuration=decisions["configuration"],
        identity_lineage=IdentityLineageReference(
            decision_id="decision.m2204.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=_digest("identity-binding"),
            evidence=_artifact("control-identity"),
        ),
        provenance=decisions["provenance"],
        consent=ConsentReference(
            decision_id="decision.m2204.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control-consent"),
        ),
        quality=decisions["quality"],
        support=decisions["support"],
        intended_use=decisions["intended-use"],
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.9,
        rationale="Caller-declared transport uncertainty estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Issuer authority remains caller-declared.",),
    )


def _validation(dimension: TransportDimension) -> TransportValidation:
    return TransportValidation(
        validation_id=f"validation.m2204.{dimension.value}",
        dimension=dimension,
        source_domain="source-domain",
        target_domain="target-domain",
        assay_or_platform="orthogonal immunoassay",
        specimen_description="frozen specimen",
        sample_count=12,
        provenance_artifact=_artifact(f"provenance-{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=_evidence(f"validation-{dimension.value}"),
    )


def _evaluation(
    dimension: TransportDimension, status: TransportStatus = TransportStatus.SUPPORTED
) -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id=f"evaluation.m2204.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="transport calibration",
        metric_value=0.9 if status is TransportStatus.SUPPORTED else 0.5,
        calibration_floor=0.8,
        rationale="Caller-declared external transport evaluation.",
        evidence=_evidence(f"evaluation-{dimension.value}"),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    benchmark_media_type: str = M2204_M2203_INPUT_MEDIA_TYPE,
    statuses: tuple[TransportStatus, ...] | None = None,
) -> EvaluateProteinRnaDiscordanceExternalTransportRequest:
    truth = _artifact("truth", M2204_M2202_INPUT_MEDIA_TYPE)
    benchmark = _artifact("benchmark", benchmark_media_type)
    statuses = statuses or (TransportStatus.SUPPORTED,) * len(DIMENSIONS)
    evaluations = tuple(
        _evaluation(dimension, status)
        for dimension, status in zip(DIMENSIONS, statuses, strict=True)
    )
    return EvaluateProteinRnaDiscordanceExternalTransportRequest(
        request_id="request.m2204.evaluator",
        context=ExecutionContext(
            request_id="request.m2204.evaluator",
            actor_id="actor.m2204.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        benchmark_package=benchmark,
        upstream_truth=truth,
        validations=tuple(_validation(dimension) for dimension in DIMENSIONS),
        evaluations=evaluations,
        configuration=TransportConfiguration(
            configuration_id="configuration.m2204.evaluator",
            version="1.0.0",
            required_dimensions=DIMENSIONS,
            minimum_calibration_floor=0.8,
            evidence=_evidence("configuration"),
        ),
        source_artifacts=(truth, benchmark, _artifact("source")),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M22-04 fixture case IDs are not locked")
    engine = M2204Engine()
    checks: list[EvalCheck] = []
    supported = engine.evaluate(build_scenario_request())
    checks.append(
        EvalCheck(
            "supported_all_dimensions",
            supported.status is EvaluationStatus.EVALUATED,
            supported.status.value,
        )
    )
    narrowed = [TransportStatus.SUPPORTED] * len(DIMENSIONS)
    narrowed[0] = TransportStatus.DOMAIN_NARROWED
    narrowed_result = engine.evaluate(build_scenario_request(statuses=tuple(narrowed)))
    checks.append(
        EvalCheck(
            "domain_narrowed",
            narrowed_result.report is not None
            and narrowed_result.report.support_domain.narrowed_dimensions
            == (TransportDimension.SITE,),
            narrowed_result.status.value,
        )
    )
    not_evaluable = engine.evaluate(
        build_scenario_request(
            statuses=(TransportStatus.NOT_EVALUABLE,) + (TransportStatus.SUPPORTED,) * 6
        )
    )
    checks.append(
        EvalCheck(
            "not_evaluable_abstention",
            not_evaluable.status is EvaluationStatus.ABSTAINED and not_evaluable.report is None,
            not_evaluable.abstention_reason or "",
        )
    )
    all_narrowed = engine.evaluate(
        build_scenario_request(statuses=(TransportStatus.DOMAIN_NARROWED,) * len(DIMENSIONS))
    )
    checks.append(
        EvalCheck(
            "no_retained_domain_abstention",
            all_narrowed.status is EvaluationStatus.ABSTAINED and all_narrowed.report is None,
            all_narrowed.abstention_reason or "",
        )
    )
    specimen = [TransportStatus.SUPPORTED] * len(DIMENSIONS)
    specimen[-1] = TransportStatus.DOMAIN_NARROWED
    specimen_result = engine.evaluate(build_scenario_request(statuses=tuple(specimen)))
    checks.append(
        EvalCheck(
            "specimen_mismatch",
            specimen_result.report is not None
            and any(item.code.value == "specimen_mismatch" for item in specimen_result.findings),
            specimen_result.status.value,
        )
    )
    try:
        engine.evaluate(build_scenario_request(accepted=False))
    except M2204AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied controls rejected"))
    try:
        TypeAdapter(EvaluateProteinRnaDiscordanceExternalTransportRequest).validate_python(
            build_scenario_request(benchmark_media_type="application/json"), strict=True
        )
    except ValueError:
        media_ok = True
    else:
        media_ok = False
    checks.append(EvalCheck("upstream_media_boundary", media_ok, "M22-03 media type required"))
    replay = engine.replay(supported)
    tampered = supported.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.replay(tampered)
    except ValueError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    repeat = engine.evaluate(build_scenario_request())
    checks.append(
        EvalCheck(
            "replay_tamper_determinism",
            replay == supported and tamper_rejected and repeat == supported,
            supported.result_digest,
        )
    )
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2204_DOSSIER_SHA256,
        "dossier_slice": M2204_DOSSIER_SLICE,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(item.passed for item in checks),
        "total_cases": len(checks),
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail} for item in checks
        ],
        "passed": len(checks) == len(case_ids) and all(item.passed for item in checks),
        "schema_count": len(contract_json_schemas()),
        "request_digest": canonical_request_digest(build_scenario_request()),
        "uncertainty_dimensions": 7,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
