"""Synthetic evaluator for provisional M18-02 alignment behavior."""

# Synthetic metadata builders intentionally keep scenario arguments explicit.
# ruff: noqa: FBT001, FBT002, T201

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m18_02 import (
    M1802_M1801_INPUT_MEDIA_TYPE,
    AlignBiomarkerPanelSourcesRequest,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentObservation,
    AlignmentObservationStatus,
    AlignmentStatus,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
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
from glio_proteogen.modules.c18_spatial_proteomics.m18_02_cross_source_alignment import (
    M1802AuthorizationError,
    M1802CrossSourceAlignmentEngine,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m18_02" / "scenarios.json"


def _artifact(
    name: str, digest_char: str, media: str = "application/octet-stream"
) -> ArtifactReference:
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
        claim="Synthetic caller-declared M18-02 alignment evidence.",
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


def _observation(index: int, dimension: AlignmentDimension, scenario: str) -> AlignmentObservation:
    conflicted = scenario == "conflict" and dimension is AlignmentDimension.TERRITORY
    incomplete = scenario == "incomplete" and dimension is AlignmentDimension.REFERENCE
    status = (
        AlignmentObservationStatus.CONFLICTED
        if conflicted
        else AlignmentObservationStatus.NOT_EVALUABLE
        if incomplete
        else AlignmentObservationStatus.ALIGNED
    )
    values = ("territory-A", "territory-B") if conflicted else ("same",)
    return AlignmentObservation(
        observation_id=f"observation.m1802.{index}",
        dimension=dimension,
        source_ids=("source.proteome", "source.genome"),
        reference_value="same",
        observed_values=values,
        status=status,
        rationale="Synthetic dimension comparison remains attributable and explicit.",
        evidence=(_evidence(f"observation-{index}", "01234567"[index]),),
    )


def build_scenario_request(
    scenario: str = "supported",
    *,
    accepted: bool = True,
) -> AlignBiomarkerPanelSourcesRequest:
    context = ExecutionContext(
        request_id="request.m1802",
        actor_id="actor.synthetic",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted),
    )
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED
        if scenario == "unsupported"
        else SupportStatus.SUPPORTED,
        reason_code="m1802_synthetic_support",
        rationale="Synthetic support decision is caller-declared and bounded.",
    )
    upstream = _artifact("resolver.m1801", "9", M1802_M1801_INPUT_MEDIA_TYPE)
    source_artifacts = (
        upstream,
        _artifact("source.proteome", "a"),
        _artifact("source.genome", "b"),
    )
    dimensions = tuple(AlignmentDimension)
    observations = tuple(
        _observation(index, dimension, scenario) for index, dimension in enumerate(dimensions)
    )
    discrepancies = (
        (
            DiscrepancyMapEntry(
                discrepancy_id="discrepancy.m1802.territory",
                dimension=AlignmentDimension.TERRITORY,
                source_ids=("source.proteome", "source.genome"),
                severity=DiscrepancySeverity.CRITICAL,
                description="Territory labels disagree across source artifacts.",
                evidence=(_evidence("discrepancy-territory", "f"),),
            ),
        )
        if scenario == "conflict"
        else ()
    )
    configuration = AlignmentConfiguration(
        configuration_id="configuration.m1802",
        version="0.1.0",
        required_dimensions=dimensions,
        evidence=(_evidence("configuration.m1802", "e"),),
    )
    return AlignBiomarkerPanelSourcesRequest(
        request_id="request.m1802",
        context=context,
        upstream_result=upstream,
        source_artifacts=source_artifacts,
        observations=observations,
        discrepancies=discrepancies,
        configuration=configuration,
        support_decision=support,
    )


def run_evaluator() -> dict[str, Any]:
    engine = M1802CrossSourceAlignmentEngine()
    checks: list[dict[str, object]] = []
    for name, scenario, expected in (
        ("supported_alignment", "supported", AlignmentStatus.ALIGNED),
        ("conflict_abstention", "conflict", AlignmentStatus.ABSTAINED),
        ("incomplete_abstention", "incomplete", AlignmentStatus.ABSTAINED),
        ("unsupported_abstention", "unsupported", AlignmentStatus.ABSTAINED),
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
    except M1802AuthorizationError:
        denied = True
    else:
        denied = False
    checks.append({"name": "authorization_gate", "passed": denied})
    return {
        "module_id": "GLIO-PROTEOGEN-M18-02",
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
