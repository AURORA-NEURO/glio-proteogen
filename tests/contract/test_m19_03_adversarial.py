"""Adversarial closure tests for the M19-03 contract and replay spine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m19_03 import (
    AggregationConfiguration,
    DisagreementRecord,
    DisagreementStatus,
    FuseProteotypeEvidenceRequest,
    FusionFinding,
    FusionFindingCode,
    FusionStatus,
    IntegratedEvidenceObject,
    ProteotypeIntegratedEvidenceResult,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
    canonical_request_bytes,
    canonical_request_digest,
    canonical_result_payload_bytes,
    result_payload_digest,
    verify_request_digest,
    verify_result_digest,
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
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_03_fusion_aggregation import (
    M1903Engine,
    fuse_proteotype_evidence,
)

_HIGH_RELIABILITY_THRESHOLD = 0.8
_MODERATE_RELIABILITY_THRESHOLD = 0.5


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1903.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1903:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M19-03 evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m1903.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.m1903.synthetic",
        actor_id="actor.m1903.synthetic",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1903.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1903.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m1903.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _contribution(name: str, score: float = 0.9) -> SourceContribution:
    artifact = _artifact(name)
    return SourceContribution(
        source_id=f"source.m1903.{name}",
        kind=SourceKind.MASS_SPECTROMETRY_PROTEOME,
        owner="M19-03 source owner",
        artifact=artifact,
        claim="component-specific proteotype evidence",
        reliability_score=score,
        reliability_band=(
            ReliabilityBand.HIGH
            if score >= _HIGH_RELIABILITY_THRESHOLD
            else ReliabilityBand.MODERATE
            if score >= _MODERATE_RELIABILITY_THRESHOLD
            else ReliabilityBand.LOW
        ),
        uncertainty_note="Synthetic declaration with explicit uncertainty.",
        evidence=(_evidence(artifact),),
    )


def _request(
    *,
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
    disagreements: tuple[DisagreementRecord, ...] = (),
) -> FuseProteotypeEvidenceRequest:
    first = _contribution("proteome")
    second = _contribution("genome", 0.7)
    contributions = (first, second)
    if source_artifacts is None:
        source_artifacts = tuple(item.artifact for item in contributions)
    return FuseProteotypeEvidenceRequest(
        request_id="request.m1903.synthetic",
        context=_context(),
        alignment_result=_artifact("alignment", "application/vnd.glio-proteogen.m19-02+json"),
        contributions=contributions,
        disagreements=disagreements,
        aggregate_values=("integrated_signal=0.84", "source_count=2"),
        configuration=AggregationConfiguration(
            configuration_id="configuration.m1903.synthetic",
            version="1.0.0",
            method="reliability_weighted_component_aggregation",
            reliability_threshold=0.7,
            component_specific=True,
            preserve_source_identity=True,
            preserve_disagreement=True,
            locked=True,
        ),
        source_artifacts=source_artifacts,
    )


def _validate_result(value: object) -> ProteotypeIntegratedEvidenceResult:
    return ProteotypeIntegratedEvidenceResult.model_validate(value, strict=True)


def test_reliability_band_cannot_overstate_numeric_score() -> None:
    artifact = _artifact("mismatch")
    with pytest.raises(ValueError, match="reliability band"):
        SourceContribution(
            source_id="source.m1903.mismatch",
            kind=SourceKind.GENOME,
            owner="M19-03 source owner",
            artifact=artifact,
            claim="component-specific genomic evidence",
            reliability_score=0.4,
            reliability_band=ReliabilityBand.HIGH,
            uncertainty_note="Synthetic declaration.",
            evidence=(_evidence(artifact),),
        )


def test_not_evaluable_contribution_cannot_carry_positive_score() -> None:
    artifact = _artifact("not-evaluable")
    with pytest.raises(ValueError, match="zero reliability score"):
        SourceContribution(
            source_id="source.m1903.not-evaluable",
            kind=SourceKind.GENOME,
            owner="M19-03 source owner",
            artifact=artifact,
            claim="component-specific genomic evidence",
            reliability_score=0.1,
            reliability_band=ReliabilityBand.NOT_EVALUABLE,
            uncertainty_note="No supported measurement.",
            evidence=(_evidence(artifact),),
        )


def test_request_rejects_unlisted_contribution_artifact() -> None:
    first = _contribution("proteome")
    with pytest.raises(ValueError, match="every contribution artifact"):
        _request(source_artifacts=(first.artifact,))


def test_request_rejects_duplicate_disagreement_ids() -> None:
    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m1903.same",
        source_ids=("source.m1903.proteome", "source.m1903.genome"),
        description="Synthetic disagreement.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("disagreement")),),
    )
    with pytest.raises(ValueError, match="disagreement ids"):
        _request(disagreements=(disagreement, disagreement))

    unknown = disagreement.model_copy(
        update={
            "disagreement_id": "disagreement.m1903.unknown.source",
            "source_ids": (
                "source.m1903.unknown",
                "source.m1903.genome",
            ),
        }
    )
    with pytest.raises(ValueError, match="unknown source"):
        _request(disagreements=(unknown,))


def test_request_digest_is_stable_and_tamper_sensitive() -> None:
    request = _request()
    digest = canonical_request_digest(request)
    assert verify_request_digest(request, digest)
    assert canonical_request_bytes(request) == canonical_request_bytes(request)
    altered = request.model_copy(update={"aggregate_values": ("integrated_signal=0.85",)})
    assert not verify_request_digest(altered, digest)


def test_canonical_result_helpers_accept_mapping_and_detect_tamper() -> None:
    payload = {"result_digest": "sha256:" + "0" * 64, "value": "stable"}
    digest = result_payload_digest(payload)
    assert canonical_result_payload_bytes(payload) == canonical_result_payload_bytes(payload)
    assert verify_result_digest(payload, digest)
    assert not verify_result_digest({**payload, "value": "changed"}, digest)

    assert canonical_request_digest(payload) == canonical_request_digest(dict(payload))


def test_disagreement_closure_rejects_invalid_resolution_and_source_ids() -> None:
    evidence = (_evidence(_artifact("invalid-disagreement")),)
    with pytest.raises(ValueError, match="resolved disagreement"):
        DisagreementRecord(
            disagreement_id="disagreement.m1903.invalid.resolved",
            source_ids=("source.m1903.proteome", "source.m1903.genome"),
            description="Invalid resolved disagreement.",
            status=DisagreementStatus.RESOLVED,
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="unresolved disagreement"):
        DisagreementRecord(
            disagreement_id="disagreement.m1903.invalid.open",
            source_ids=("source.m1903.proteome", "source.m1903.genome"),
            description="Invalid open disagreement.",
            status=DisagreementStatus.OPEN,
            resolution="Must not be present.",
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="source ids"):
        DisagreementRecord(
            disagreement_id="disagreement.m1903.invalid.duplicate",
            source_ids=("source.m1903.proteome", "source.m1903.proteome"),
            description="Duplicate source disagreement.",
            status=DisagreementStatus.OPEN,
            evidence=evidence,
        )


def test_integrated_object_closure_rejects_duplicates_and_unknown_sources() -> None:
    request = _request()

    with pytest.raises(ValueError, match="source contribution ids"):
        IntegratedEvidenceObject(
            integrated_id="integrated.m1903.duplicate",
            version="1.0.0",
            aggregate_claim="Duplicate integrated object.",
            contributions=(request.contributions[0], request.contributions[0]),
            aggregate_values=request.aggregate_values,
            configuration=request.configuration,
            evidence=request.contributions[0].evidence,
        )

    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m1903.unknown",
        source_ids=("source.m1903.unknown", "source.m1903.genome"),
        description="Unknown source disagreement.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("unknown")),),
    )
    with pytest.raises(ValueError, match="unknown source"):
        IntegratedEvidenceObject(
            integrated_id="integrated.m1903.invalid",
            version="1.0.0",
            aggregate_claim="Invalid integrated object.",
            contributions=request.contributions,
            disagreements=(disagreement,),
            aggregate_values=request.aggregate_values,
            configuration=request.configuration,
            evidence=request.contributions[0].evidence,
        )


def test_result_closure_rejects_request_and_evidence_tampering() -> None:
    result = M1903Engine().adapt(_request())
    zero = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="request digest"):
        _validate_result(result.model_copy(update={"request_digest": zero}))

    with pytest.raises(ValueError, match="supported attributable"):
        _validate_result(
            result.model_copy(
                update={
                    "support_decision": SupportDecision(
                        status=SupportStatus.REVIEW_REQUIRED,
                        reason_code="review.required",
                        rationale="Synthetic review.",
                    )
                }
            )
        )

    assert result.integrated_evidence is not None
    changed_source = result.request.contributions[0].model_copy(update={"claim": "changed"})
    changed_integrated = result.integrated_evidence.model_copy(
        update={
            "contributions": (changed_source, result.request.contributions[1]),
        }
    )
    with pytest.raises(ValueError, match="exact source contributions"):
        _validate_result(result.model_copy(update={"integrated_evidence": changed_integrated}))

    with pytest.raises(ValueError, match="aggregate values"):
        _validate_result(
            result.model_copy(
                update={
                    "integrated_evidence": result.integrated_evidence.model_copy(
                        update={"aggregate_values": ("changed",)}
                    )
                }
            )
        )

    with pytest.raises(ValueError, match="locked configuration"):
        _validate_result(
            result.model_copy(
                update={
                    "integrated_evidence": result.integrated_evidence.model_copy(
                        update={
                            "configuration": result.request.configuration.model_copy(
                                update={"method": "changed"}
                            )
                        }
                    )
                }
            )
        )


def test_result_closure_rejects_bad_abstention_findings_review_and_digest() -> None:
    result = M1903Engine().adapt(_request())
    zero = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="abstained result"):
        _validate_result(
            result.model_copy(
                update={
                    "status": FusionStatus.ABSTAINED,
                    "integrated_evidence": None,
                    "abstention_reason": None,
                    "support_decision": SupportDecision(
                        status=SupportStatus.SUPPORTED,
                        reason_code="supported.invalid",
                        rationale="Invalid abstention.",
                    ),
                }
            )
        )

    finding = FusionFinding(
        finding_id="finding.m19.duplicate",
        code=FusionFindingCode.INPUT_INCOMPLETE,
        message="Duplicate finding.",
    )
    with pytest.raises(ValueError, match="finding ids"):
        _validate_result(result.model_copy(update={"findings": (finding, finding)}))

    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m1903.review",
        source_ids=("source.m1903.proteome", "source.m1903.genome"),
        description="Open review disagreement.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("review")),),
    )
    reviewed = M1903Engine().adapt(_request(disagreements=(disagreement,)))
    with pytest.raises(ValueError, match="human review"):
        _validate_result(reviewed.model_copy(update={"human_review_required": False}))

    with pytest.raises(ValueError, match="result digest"):
        _validate_result(result.model_copy(update={"result_digest": zero}))


def test_runtime_entrypoints_and_replay_request_mismatch_are_covered() -> None:
    request = _request()
    result = fuse_proteotype_evidence(request)
    assert result.status is FusionStatus.INTEGRATED
    changed_request = request.model_copy(update={"aggregate_values": ("changed",)})
    tampered = result.model_copy(update={"request": changed_request})
    with pytest.raises(ValueError, match="request digest"):
        M1903Engine().replay(tampered)


@pytest.mark.parametrize(
    "surface",
    [
        "configuration_method",
        "configuration_evidence",
        "aggregate_value",
        "owner",
        "claim",
        "uncertainty_note",
        "contribution_evidence",
        "disagreement_description",
        "disagreement_resolution",
        "disagreement_evidence",
    ],
)
def test_every_caller_claim_surface_abstains_on_prohibited_scope(surface: str) -> None:
    request = _request()
    if surface == "configuration_method":
        candidate = request.model_copy(
            update={
                "configuration": request.configuration.model_copy(
                    update={"method": "glioma specific biology aggregation"}
                )
            }
        )
    elif surface == "configuration_evidence":
        evidence = _evidence(_artifact("configuration-claim")).model_copy(
            update={"claim": "isoform evidence"}
        )
        candidate = request.model_copy(
            update={
                "configuration": request.configuration.model_copy(update={"evidence": (evidence,)})
            }
        )
    elif surface == "aggregate_value":
        candidate = request.model_copy(
            update={"aggregate_values": ("protein inference result", "source_count=2")}
        )
    elif surface in {"owner", "claim", "uncertainty_note", "contribution_evidence"}:
        contribution = request.contributions[0]
        update: dict[str, object]
        if surface == "owner":
            update = {"owner": "proteoform authority"}
        elif surface == "claim":
            update = {"claim": "protein inference claim"}
        elif surface == "uncertainty_note":
            update = {"uncertainty_note": "identity inference uncertainty"}
        else:
            evidence = contribution.evidence[0].model_copy(update={"claim": "isoform evidence"})
            update = {"evidence": (evidence,)}
        candidate = request.model_copy(
            update={
                "contributions": (contribution.model_copy(update=update), request.contributions[1])
            }
        )
    else:
        status = (
            DisagreementStatus.RESOLVED
            if surface == "disagreement_resolution"
            else DisagreementStatus.OPEN
        )
        disagreement = DisagreementRecord(
            disagreement_id=f"disagreement.m1903.{surface}",
            source_ids=("source.m1903.proteome", "source.m1903.genome"),
            description=(
                "glioma specific biology disagreement"
                if surface == "disagreement_description"
                else "Open review disagreement."
            ),
            status=status,
            resolution="protein inference resolution"
            if surface == "disagreement_resolution"
            else None,
            evidence=(
                _evidence(_artifact(f"{surface}-evidence")).model_copy(
                    update={"claim": "proteoform evidence"}
                ),
            ),
        )
        candidate = request.model_copy(update={"disagreements": (disagreement,)})

    result = M1903Engine().adapt(candidate)
    assert result.status is FusionStatus.ABSTAINED
    assert result.integrated_evidence is None
    assert any(item.code is FusionFindingCode.OWNERSHIP_UNCLEAR for item in result.findings)
