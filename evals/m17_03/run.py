"""Frozen synthetic evaluator for M17-03 fusion and aggregation."""

# Synthetic evaluator builders intentionally keep scenario arguments explicit.
# ruff: noqa: E501, FBT001, FBT002, T201

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m17_03 import (
    M1703_M1702_INPUT_MEDIA_TYPE,
    DisagreementRecord,
    DisagreementStatus,
    FuseVariantPeptideEvidenceRequest,
    FusionConfiguration,
    FusionStatus,
    ReliabilityBand,
    SignedPropagationRecord,
    SourceContribution,
    SourceKind,
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_03_fusion_aggregation_engine import (
    M1703AuthorizationError,
    M1703FusionAggregationEngine,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m17_03" / "scenarios.json"


def _artifact(name: str, digest_char: str = "a", media: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + digest_char * 64,
        media_type=media,
    )


def _evidence(name: str, digest_char: str = "b") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name, digest_char),
        role="evidence",
        claim="Synthetic caller-declared M17-03 evidence.",
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
            decision_id="decision.provenance", state=state, policy_version="1.0.0", evidence=_artifact("control-provenance", "3")
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED if accepted else ConsentState.WITHHELD,
            policy_version="1.0.0",
            evidence=_artifact("control-consent", "4"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality", state=state, policy_version="1.0.0", evidence=_artifact("control-quality", "5")
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support", state=state, policy_version="1.0.0", evidence=_artifact("control-support", "6")
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended", state=state, policy_version="1.0.0", evidence=_artifact("control-intended", "7")
        ),
    )


def _contribution(
    source_id: str,
    kind: SourceKind,
    score: float,
    band: ReliabilityBand,
) -> SourceContribution:
    return SourceContribution(
        source_id=source_id,
        kind=kind,
        artifact=_artifact(f"artifact-{source_id}", str((ord(source_id[-1]) % 8) + 1)),
        claim="Synthetic component-specific source claim.",
        reliability_score=score,
        reliability_band=band,
        uncertainty_note="Caller-declared reliability and uncertainty.",
        evidence=(_evidence(f"evidence-{source_id}"),),
    )


def build_scenario_request(
    scenario: str = "healthy",
    *,
    accepted: bool = True,
) -> FuseVariantPeptideEvidenceRequest:
    alignment = _artifact("alignment.m1702", "8", M1703_M1702_INPUT_MEDIA_TYPE)
    first = _contribution("source-1", SourceKind.MASS_SPECTROMETRY_PROTEOME, 0.9, ReliabilityBand.HIGH)
    second = _contribution("source-2", SourceKind.TRANSCRIPTOME, 0.8, ReliabilityBand.HIGH)
    contributions = (first, second)
    disagreements: tuple[DisagreementRecord, ...] = ()
    if scenario == "disagreement":
        disagreements = (
            DisagreementRecord(
                disagreement_id="disagreement.1",
                source_ids=(first.source_id, second.source_id),
                description="Synthetic source disagreement remains visible.",
                status=DisagreementStatus.OPEN,
                evidence=(_evidence("disagreement.1", "9"),),
            ),
        )
    elif scenario == "low_reliability":
        first = _contribution("source-1", SourceKind.MASS_SPECTROMETRY_PROTEOME, 0.2, ReliabilityBand.LOW)
        contributions = (first, second)
    elif scenario == "unsupported":
        first = _contribution("source-1", SourceKind.MASS_SPECTROMETRY_PROTEOME, 0.0, ReliabilityBand.NOT_EVALUABLE)
        contributions = (first, second)
    config_evidence = (_evidence("configuration.1", "c"),)
    configuration = FusionConfiguration(
        configuration_id="configuration.1",
        version="0.1.0",
        reliability_threshold=0.7,
        evidence=config_evidence,
    )
    propagation = (
        SignedPropagationRecord(
            propagation_id="propagation.1",
            source_id=first.source_id,
            target_id="variant-peptide-target",
            signature_digest="sha256:" + "d" * 64,
            assertion="Synthetic signed propagation assertion.",
            evidence=(_evidence("propagation.1", "e"),),
        ),
    )
    source_artifacts = (alignment, first.artifact, second.artifact, config_evidence[0].reference)
    context = ExecutionContext(
        request_id="request.m1703",
        actor_id="actor.synthetic",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted),
    )
    return FuseVariantPeptideEvidenceRequest(
        request_id="request.m1703",
        context=context,
        alignment_result=alignment,
        contributions=contributions,
        disagreements=disagreements,
        propagation=propagation,
        configuration=configuration,
        source_artifacts=source_artifacts,
    )


def run_evaluator() -> dict[str, Any]:
    engine = M1703FusionAggregationEngine()
    checks: list[dict[str, object]] = []
    for name, scenario, expected in (
        ("healthy_integrated", "healthy", FusionStatus.INTEGRATED),
        ("disagreement_visible", "disagreement", FusionStatus.INTEGRATED),
        ("low_reliability_review", "low_reliability", FusionStatus.INTEGRATED),
        ("unsupported_abstention", "unsupported", FusionStatus.ABSTAINED),
    ):
        result = engine.infer(build_scenario_request(scenario))
        checks.append({"name": name, "passed": result.status is expected})
    replay = engine.infer(build_scenario_request())
    checks.append({"name": "replay", "passed": engine.verify(replay) == replay})
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1703AuthorizationError:
        denied = True
    else:
        denied = False
    checks.append({"name": "authorization_gate", "passed": denied})
    return {
        "module_id": "GLIO-PROTEOGEN-M17-03",
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
