"""Frozen synthetic evaluator for M17-07 downstream typed export."""

# Synthetic metadata builders intentionally keep scenario arguments explicit.
# ruff: noqa: E501, FBT001, FBT002, T201

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m17_07 import (
    M1707_M1706_INPUT_MEDIA_TYPE,
    CompatibilityMode,
    ExportField,
    ExportFieldType,
    ExportStatus,
    ExportVariantPeptideDownstreamContractRequest,
    DownstreamExportConfiguration,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_07_downstream_typed_export import (
    M1707AuthorizationError,
    M1707DownstreamTypedExportEngine,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m17_07" / "scenarios.json"


def _artifact(name: str, digest_char: str, media: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + digest_char * 64,
        media_type=media,
    )


def _evidence(name: str, digest_char: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name, digest_char),
        role="evidence",
        claim="Synthetic caller-declared M17-07 export evidence.",
    )


def _controls(accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-config", "1"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED if accepted else IdentityLineageState.CONFLICTED,
            policy_version="1.0.0",
            binding_digest="sha256:" + "2" * 64,
            evidence=_artifact("control-identity", "2"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-provenance", "3"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED if accepted else ConsentState.WITHHELD,
            policy_version="1.0.0",
            evidence=_artifact("control-consent", "4"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-quality", "5"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-support", "6"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-intended", "7"),
        ),
    )


def _field(index: int, field_type: ExportFieldType) -> ExportField:
    value = _artifact(f"value-{index}", "abc"[index])
    return ExportField(
        field_id=f"field.m1707.{index}",
        field_name=f"variant_peptide_field_{index}",
        value_type=field_type,
        field_version="0.1.0",
        owner="Data engineering",
        documentation="Documented synthetic downstream field with immutable source binding.",
        value_digest=value.digest,
        evidence=(_evidence(f"value-{index}", "abc"[index]),),
    )


def build_scenario_request(
    scenario: str = "supported",
    *,
    accepted: bool = True,
) -> ExportVariantPeptideDownstreamContractRequest:
    context = ExecutionContext(
        request_id="request.m1707",
        actor_id="actor.synthetic",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted),
    )
    consent = context.references.consent
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED if scenario == "unsupported" else SupportStatus.SUPPORTED,
        reason_code="m1707_synthetic_support",
        rationale="Synthetic support decision is caller-declared and bounded.",
    )
    compatibility = (
        CompatibilityMode.REVIEW_REQUIRED
        if scenario == "compatibility"
        else CompatibilityMode.VERSIONED
    )
    configuration = DownstreamExportConfiguration(
        configuration_id="configuration.m1707",
        version="0.1.0",
        compatibility=compatibility,
        evidence=(_evidence("configuration.m1707", "9"),),
    )
    adjudication = _artifact("adjudication.m1706", "8", M1707_M1706_INPUT_MEDIA_TYPE)
    fields = (_field(0, ExportFieldType.IDENTIFIER), _field(1, ExportFieldType.ENUM), _field(2, ExportFieldType.TEXT))
    source_artifacts = (adjudication,) + tuple(
        field.evidence[0].reference for field in fields
    )
    return ExportVariantPeptideDownstreamContractRequest(
        request_id="request.m1707",
        context=context,
        adjudication_result=adjudication,
        fields=fields,
        consent=consent,
        support_decision=support,
        configuration=configuration,
        source_artifacts=source_artifacts,
    )


def run_evaluator() -> dict[str, Any]:
    engine = M1707DownstreamTypedExportEngine()
    checks: list[dict[str, object]] = []
    for name, scenario, expected in (
        ("supported_export", "supported", ExportStatus.EXPORTED),
        ("unsupported_abstention", "unsupported", ExportStatus.ABSTAINED),
        ("compatibility_abstention", "compatibility", ExportStatus.ABSTAINED),
    ):
        result = engine.infer(build_scenario_request(scenario))
        checks.append({"name": name, "passed": result.status is expected})
    replay = engine.infer(build_scenario_request())
    checks.append({"name": "replay", "passed": engine.verify(replay) == replay})
    tampered = replay.model_copy(update={"result_digest": "sha256:" + ("a" * 64)})
    try:
        engine.verify(tampered)
    except Exception:  # noqa: BLE001
        tamper_detected = True
    else:
        tamper_detected = False
    checks.append({"name": "tamper", "passed": tamper_detected})
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1707AuthorizationError:
        denied = True
    else:
        denied = False
    checks.append({"name": "authorization_gate", "passed": denied})
    return {
        "module_id": "GLIO-PROTEOGEN-M17-07",
        "fixture": str(FIXTURE),
        "declared_cases": len(checks),
        "executed_cases": len(checks),
        "passed_cases": sum(bool(item["passed"]) for item in checks),
        "checks": checks,
        "passed": all(bool(item["passed"]) for item in checks),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_evaluator(), sort_keys=True))

