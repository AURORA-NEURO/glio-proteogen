"""Deterministic M20-08 evaluator over frozen monitoring scenarios."""

# ruff: noqa: PLR0913, TRY003, T201

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_08 import (
    M2008_M2007_INPUT_MEDIA_TYPE,
    HealthSignal,
    HealthSignalKind,
    HealthSignalStatus,
    MonitorProteinSubtypeTranslationHealthRequest,
    RollbackDecision,
    TranslationHealthStatus,
    TranslationMonitoringConfiguration,
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
from glio_proteogen.modules.c20_biomarker_panel.m20_08_translation_monitoring_rollback import (
    M2008AuthorizationError,
    M2008TranslationMonitoringEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M20-08"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m20_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "healthy_continue",
    "support_drift_suspend",
    "critical_discrepancy_rollback",
    "not_evaluable_abstention",
    "replay_and_tamper",
    "authorization_gate",
    "upstream_media_boundary",
    "deterministic_repeat",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m2008_fixture": label})


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M20-08 monitoring evidence.",
        ),
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=_digest("identity.binding"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended-use",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended-use"),
        ),
    )


def _configuration() -> TranslationMonitoringConfiguration:
    return TranslationMonitoringConfiguration(
        configuration_id="configuration.m2008",
        version="1.0.0",
        reference_artifact=_artifact("monitoring-reference"),
        monitoring_window="rolling 30 days",
        critical_threshold="discrepancy drift requires rollback review",
        evidence=_evidence("configuration"),
    )


def _signal(
    signal_id: str,
    kind: HealthSignalKind,
    metric: str,
    observed: float,
    status: HealthSignalStatus,
    lower: float | None,
    upper: float | None,
) -> HealthSignal:
    return HealthSignal(
        signal_id=signal_id,
        kind=kind,
        metric=metric,
        observed_value=observed,
        lower_bound=lower,
        upper_bound=upper,
        status=status,
        source_artifacts=(_artifact(f"signal-{signal_id}"),),
        evidence=_evidence(f"evidence-{signal_id}"),
    )


def healthy_signal() -> HealthSignal:
    return _signal(
        "signal.support",
        HealthSignalKind.SUPPORT_DRIFT,
        "support proportion",
        0.95,
        HealthSignalStatus.WITHIN_ENVELOPE,
        0.80,
        1.0,
    )


def build_scenario_request(
    *, accepted: bool = True, signals: tuple[HealthSignal, ...] | None = None
) -> MonitorProteinSubtypeTranslationHealthRequest:
    upstream = _artifact("upstream-result", M2008_M2007_INPUT_MEDIA_TYPE)
    return MonitorProteinSubtypeTranslationHealthRequest(
        request_id="request.m2008",
        context=ExecutionContext(
            request_id="request.m2008",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        upstream_result=upstream,
        configuration=_configuration(),
        signals=signals or (healthy_signal(),),
        source_artifacts=(upstream, _artifact("source-proteome")),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M20-08 fixture case IDs are not locked")
    engine = M2008TranslationMonitoringEngine()
    checks: list[EvalCheck] = []
    healthy = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "healthy_continue",
            healthy.health_status is TranslationHealthStatus.HEALTHY
            and healthy.rollback_decision is RollbackDecision.CONTINUE,
            healthy.health_status.value,
        )
    )
    degraded = engine.infer(
        build_scenario_request(
            signals=(
                _signal(
                    "signal.support",
                    HealthSignalKind.SUPPORT_DRIFT,
                    "support proportion",
                    0.72,
                    HealthSignalStatus.DRIFTING,
                    0.80,
                    1.0,
                ),
            )
        )
    )
    checks.append(
        EvalCheck(
            "support_drift_suspend",
            degraded.health_status is TranslationHealthStatus.DEGRADED
            and degraded.rollback_decision is RollbackDecision.SUSPEND
            and degraded.human_review_required,
            degraded.health_status.value,
        )
    )
    critical = engine.infer(
        build_scenario_request(
            signals=(
                _signal(
                    "signal.discrepancy",
                    HealthSignalKind.DISCREPANCY,
                    "critical discrepancy count",
                    4.0,
                    HealthSignalStatus.DRIFTING,
                    0.0,
                    1.0,
                ),
            )
        )
    )
    checks.append(
        EvalCheck(
            "critical_discrepancy_rollback",
            critical.health_status is TranslationHealthStatus.CRITICAL
            and critical.rollback_decision is RollbackDecision.ROLLBACK
            and critical.human_review_required,
            critical.health_status.value,
        )
    )
    unsupported = engine.infer(
        build_scenario_request(
            signals=(
                _signal(
                    "signal.unknown",
                    HealthSignalKind.WORKFLOW_EFFECT,
                    "workflow effect",
                    0.0,
                    HealthSignalStatus.NOT_EVALUABLE,
                    None,
                    None,
                ),
            )
        )
    )
    checks.append(
        EvalCheck(
            "not_evaluable_abstention",
            unsupported.health_status is TranslationHealthStatus.ABSTAINED
            and unsupported.rollback_decision is RollbackDecision.ABSTAIN
            and unsupported.report is None
            and unsupported.human_review_required,
            unsupported.abstention_reason or "",
        )
    )
    replay = engine.infer(build_scenario_request())
    tampered = replay.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.verify(tampered)
    except Exception:  # noqa: BLE001
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(
        EvalCheck(
            "replay_and_tamper",
            engine.verify(replay) == replay and tamper_rejected,
            "replay and tamper",
        )
    )
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M2008AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied controls rejected"))
    try:
        TypeAdapter(MonitorProteinSubtypeTranslationHealthRequest).validate_python(
            build_scenario_request().model_copy(update={"upstream_result": _artifact("wrong")}),
            strict=True,
        )
    except ValueError:
        media_ok = True
    else:
        media_ok = False
    checks.append(EvalCheck("upstream_media_boundary", media_ok, "M20-07 media type required"))
    repeat = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "deterministic_repeat",
            repeat.model_dump(mode="json") == healthy.model_dump(mode="json"),
            repeat.result_digest,
        )
    )
    return {
        "module_id": MODULE_ID,
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
