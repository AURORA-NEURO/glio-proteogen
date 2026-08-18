"""Deterministic M21-07 evaluator over frozen operational scenarios."""

# ruff: noqa: TRY003, T201

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m21_07 import (
    M2107_DOSSIER_SHA256,
    M2107_DOSSIER_SLICE,
    M2107_M2106_INPUT_MEDIA_TYPE,
    EvaluateComplexActivityHumanFactorsRequest,
    EvaluationStatus,
    FallbackScenario,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m21_07_human_factors_operational_evaluator import (  # noqa: E501
    M2107AuthorizationError,
    M2107Engine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M21-07"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m21_07" / "scenarios.json"
)
DIMENSIONS: Final = tuple(OperationalDimension)
EXPECTED_CASE_IDS: Final = (
    "supported_all_dimensions",
    "failed_dimensions_visible",
    "not_evaluable_abstention",
    "fallback_failure_visible",
    "authorization_gate",
    "upstream_media_boundary",
    "replay_tamper",
    "deterministic_repeat",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2107.{label}",
        version="1.0.0",
        digest=sha256_digest({"m2107": label, "media": media_type}),
        media_type=media_type,
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M21-07 operational evidence.",
        ),
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    decision = {
        role: UpstreamDecisionReference(
            decision_id=f"decision.m2107.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}"),
        )
        for role in ("configuration", "provenance", "quality", "support", "intended-use")
    }
    return ContextReferences(
        approved_configuration=decision["configuration"],
        identity_lineage=IdentityLineageReference(
            decision_id="decision.m2107.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("m2107.identity"),
            evidence=_artifact("control-identity"),
        ),
        provenance=decision["provenance"],
        consent=ConsentReference(
            decision_id="decision.m2107.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control-consent"),
        ),
        quality=decision["quality"],
        support=decision["support"],
        intended_use=decision["intended-use"],
    )


def _metric(
    dimension: OperationalDimension,
    status: OperationalStatus = OperationalStatus.PASS,
) -> OperationalMetric:
    return OperationalMetric(
        metric_id=f"metric.m2107.{dimension.value}",
        dimension=dimension,
        metric_name=f"{dimension.value} metric",
        observed_value=0.9 if status is OperationalStatus.PASS else 0.2,
        target_value=0.8,
        tolerance=0.1,
        sample_size=12,
        status=status,
        evidence=_evidence(f"metric-{dimension.value}"),
    )


def _fallback(status: OperationalStatus = OperationalStatus.PASS) -> FallbackScenario:
    return FallbackScenario(
        scenario_id="fallback.m2107.evaluator",
        trigger="operational interruption",
        fallback_path="manual review queue",
        recovery_seconds=30.0,
        fallback_available=status is not OperationalStatus.NOT_EVALUABLE,
        status=status,
        evidence=_evidence("fallback"),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    upstream_media_type: str = M2107_M2106_INPUT_MEDIA_TYPE,
    statuses: tuple[OperationalStatus, ...] | None = None,
    fallback_status: OperationalStatus = OperationalStatus.PASS,
) -> EvaluateComplexActivityHumanFactorsRequest:
    upstream = _artifact("upstream", upstream_media_type)
    statuses = statuses or (OperationalStatus.PASS,) * len(DIMENSIONS)
    return EvaluateComplexActivityHumanFactorsRequest(
        request_id="request.m2107.evaluator",
        context=ExecutionContext(
            request_id="request.m2107.evaluator",
            actor_id="actor.m2107.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        upstream_result=upstream,
        metrics=tuple(
            _metric(dimension, status)
            for dimension, status in zip(DIMENSIONS, statuses, strict=True)
        ),
        fallbacks=(_fallback(fallback_status),),
        configuration=OperationalConfiguration(
            configuration_id="configuration.m2107.evaluator",
            version="1.0.0",
            required_dimensions=DIMENSIONS,
            evidence=_evidence("configuration"),
        ),
        source_artifacts=(upstream, _artifact("source")),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M21-07 fixture case IDs are not locked")
    engine = M2107Engine()
    checks: list[EvalCheck] = []
    supported = engine.evaluate(build_scenario_request())
    checks.append(
        EvalCheck(
            "supported_all_dimensions",
            supported.status is EvaluationStatus.EVALUATED,
            supported.status.value,
        )
    )
    failed = list((OperationalStatus.PASS,) * len(DIMENSIONS))
    failed[1] = OperationalStatus.FAIL
    failed_result = engine.evaluate(build_scenario_request(statuses=tuple(failed)))
    checks.append(
        EvalCheck(
            "failed_dimensions_visible",
            any(item.code.value == "automation_bias_risk" for item in failed_result.findings),
            failed_result.status.value,
        )
    )
    abstained_statuses = list((OperationalStatus.PASS,) * len(DIMENSIONS))
    abstained_statuses[0] = OperationalStatus.NOT_EVALUABLE
    abstained = engine.evaluate(build_scenario_request(statuses=tuple(abstained_statuses)))
    checks.append(
        EvalCheck(
            "not_evaluable_abstention",
            abstained.status is EvaluationStatus.ABSTAINED and abstained.report is None,
            abstained.abstention_reason or "",
        )
    )
    fallback_failure = engine.evaluate(
        build_scenario_request(fallback_status=OperationalStatus.FAIL)
    )
    checks.append(
        EvalCheck(
            "fallback_failure_visible",
            any(item.code.value == "fallback_unavailable" for item in fallback_failure.findings),
            fallback_failure.status.value,
        )
    )
    try:
        engine.evaluate(build_scenario_request(accepted=False))
    except M2107AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied controls rejected"))
    try:
        TypeAdapter(EvaluateComplexActivityHumanFactorsRequest).validate_python(
            build_scenario_request(upstream_media_type="application/json"), strict=True
        )
    except ValueError:
        media_ok = True
    else:
        media_ok = False
    checks.append(EvalCheck("upstream_media_boundary", media_ok, "M21-06 media type required"))
    tampered = supported.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.replay(tampered)
    except ValueError:
        tamper_ok = True
    else:
        tamper_ok = False
    checks.append(
        EvalCheck(
            "replay_tamper",
            tamper_ok and engine.replay(supported) == supported,
            "replay and tamper",
        )
    )
    repeat = engine.evaluate(build_scenario_request())
    checks.append(EvalCheck("deterministic_repeat", repeat == supported, supported.result_digest))
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2107_DOSSIER_SHA256,
        "dossier_slice": M2107_DOSSIER_SLICE,
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
