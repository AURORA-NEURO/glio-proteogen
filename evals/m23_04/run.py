"""Deterministic M23-04 evaluator over frozen transport scenarios."""

# ruff: noqa: TRY003, T201

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

from glio_proteogen.contracts.m23_04 import (
    M2304_DOSSIER_SHA256,
    M2304_DOSSIER_SLICE,
    EvaluateVariantPeptideExternalTransportRequest,
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
from glio_proteogen.modules.c21_reference_material.m23_04_external_transport_evaluator import (
    M2304AuthorizationError,
    M2304Engine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M23-04"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m23_04" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "supported_all_dimensions",
    "domain_narrowed",
    "not_evaluable_abstention",
    "no_retained_domain_abstention",
    "specimen_boundary",
    "authorization_gate",
    "source_binding_closure",
    "replay_tamper_determinism",
)
DIMENSIONS: Final = tuple(TransportDimension)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m2304_fixture": label})


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2304.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M23-04 transport evidence.",
        ),
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    decision = {
        role: UpstreamDecisionReference(
            decision_id=f"decision.m2304.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}"),
        )
        for role in ("configuration", "provenance", "quality", "support", "intended-use")
    }
    return ContextReferences(
        approved_configuration=decision["configuration"],
        identity_lineage=IdentityLineageReference(
            decision_id="decision.m2304.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=_digest("identity-binding"),
            evidence=_artifact("control-identity"),
        ),
        provenance=decision["provenance"],
        consent=ConsentReference(
            decision_id="decision.m2304.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control-consent"),
        ),
        quality=decision["quality"],
        support=decision["support"],
        intended_use=decision["intended-use"],
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
        validation_id=f"validation.m2304.{dimension.value}",
        dimension=dimension,
        source_domain="source-domain",
        target_domain="target-domain",
        assay_or_platform="isoform-aware proteome platform",
        specimen_description="caller-declared frozen glioma specimen",
        sample_count=12,
        provenance_artifact=_artifact(f"provenance-{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=_evidence(f"validation-{dimension.value}"),
    )


def _evaluation(
    dimension: TransportDimension, status: TransportStatus = TransportStatus.SUPPORTED
) -> TransportEvaluation:
    floor = 0.8
    value = 0.9 if status is TransportStatus.SUPPORTED else 0.5
    return TransportEvaluation(
        evaluation_id=f"evaluation.m2304.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="transport calibration",
        metric_value=value,
        calibration_floor=floor,
        rationale="Caller-declared independent external transport evaluation.",
        evidence=_evidence(f"evaluation-{dimension.value}"),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    statuses: tuple[TransportStatus, ...] | None = None,
) -> EvaluateVariantPeptideExternalTransportRequest:
    inputs = {
        label: _artifact(label)
        for label in (
            "mass-spectrometry-proteome",
            "genome-transcriptome",
            "ptm-annotations",
            "benchmark",
        )
    }
    statuses = statuses or (TransportStatus.SUPPORTED,) * len(DIMENSIONS)
    evaluations = tuple(
        _evaluation(dimension, status)
        for dimension, status in zip(DIMENSIONS, statuses, strict=True)
    )
    return EvaluateVariantPeptideExternalTransportRequest(
        request_id="request.m2304.evaluator",
        context=ExecutionContext(
            request_id="request.m2304.evaluator",
            actor_id="actor.m2304.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        mass_spectrometry_proteome=inputs["mass-spectrometry-proteome"],
        genome_transcriptome=inputs["genome-transcriptome"],
        ptm_annotations=inputs["ptm-annotations"],
        benchmark_package=inputs["benchmark"],
        validations=tuple(_validation(dimension) for dimension in DIMENSIONS),
        evaluations=evaluations,
        configuration=TransportConfiguration(
            configuration_id="configuration.m2304.evaluator",
            version="1.0.0",
            required_dimensions=DIMENSIONS,
            minimum_calibration_floor=0.8,
            evidence=_evidence("configuration"),
        ),
        source_artifacts=tuple(inputs.values()),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def _check(name: str, *, passed: bool, detail: object) -> EvalCheck:
    return EvalCheck(name, passed, str(detail))


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M23-04 fixture case IDs are not locked")
    engine = M2304Engine()
    checks: list[EvalCheck] = []
    supported = engine.evaluate(build_scenario_request())
    checks.append(
        _check(
            "supported_all_dimensions",
            passed=supported.status is EvaluationStatus.EVALUATED and supported.report is not None,
            detail=supported.status.value,
        )
    )
    narrowed = (TransportStatus.DOMAIN_NARROWED,) + (TransportStatus.SUPPORTED,) * 6
    narrowed_result = engine.evaluate(build_scenario_request(statuses=narrowed))
    checks.append(
        _check(
            "domain_narrowed",
            passed=narrowed_result.status is EvaluationStatus.EVALUATED
            and narrowed_result.report is not None
            and narrowed_result.report.support_domain.narrowed_dimensions
            == (TransportDimension.SITE,),
            detail=narrowed_result.status.value,
        )
    )
    not_evaluable = engine.evaluate(
        build_scenario_request(
            statuses=(TransportStatus.NOT_EVALUABLE,) + (TransportStatus.SUPPORTED,) * 6
        )
    )
    checks.append(
        _check(
            "not_evaluable_abstention",
            passed=not_evaluable.status is EvaluationStatus.ABSTAINED
            and not_evaluable.report is None,
            detail=not_evaluable.abstention_reason or "",
        )
    )
    all_narrowed = engine.evaluate(
        build_scenario_request(statuses=(TransportStatus.DOMAIN_NARROWED,) * len(DIMENSIONS))
    )
    checks.append(
        _check(
            "no_retained_domain_abstention",
            passed=all_narrowed.status is EvaluationStatus.ABSTAINED
            and all_narrowed.report is None,
            detail=all_narrowed.abstention_reason or "",
        )
    )
    specimen = (TransportStatus.SUPPORTED,) * 6 + (TransportStatus.DOMAIN_NARROWED,)
    specimen_result = engine.evaluate(build_scenario_request(statuses=specimen))
    checks.append(
        _check(
            "specimen_boundary",
            passed=specimen_result.report is not None
            and any(item.code.value == "specimen_mismatch" for item in specimen_result.findings),
            detail=specimen_result.status.value,
        )
    )
    try:
        engine.evaluate(build_scenario_request(accepted=False))
    except M2304AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(
        _check("authorization_gate", passed=authorization_ok, detail="denied controls rejected")
    )
    request = build_scenario_request()
    tampered_sources = request.model_copy(
        update={"source_artifacts": request.source_artifacts[:-1]}
    )
    try:
        TypeAdapter(EvaluateVariantPeptideExternalTransportRequest).validate_python(
            tampered_sources, strict=True
        )
    except ValueError:
        source_ok = True
    else:
        source_ok = False
    checks.append(
        _check("source_binding_closure", passed=source_ok, detail="exact source artifacts required")
    )
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
        _check(
            "replay_tamper_determinism",
            passed=replay == supported and tamper_rejected and repeat == supported,
            detail=supported.result_digest,
        )
    )
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2304_DOSSIER_SHA256,
        "dossier_slice": M2304_DOSSIER_SLICE,
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
