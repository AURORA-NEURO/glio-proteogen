"""Adversarial closure tests for the M19-04 contract and replay spine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m19_04 import (
    AdapterFinding,
    AdapterFindingCode,
    AdapterStatus,
    AdaptProteotypeIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseKind,
    IntendedUseRegistration,
    IntendedUseSpecificObject,
    PolicyDecision,
    PolicyDecisionStatus,
    ProteotypeIntendedUseAdapterResult,
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
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_04_intended_use_adapter import (
    M1904Engine,
)

type _ControlReference = UpstreamDecisionReference | IdentityLineageReference | ConsentReference


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1904.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1904:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M19-04 evidence; issuer authority is not authenticated.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m1904.{role}",
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
        request_id="request.m1904.synthetic",
        actor_id="actor.m1904.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1904.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1904.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m1904.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _registration() -> IntendedUseRegistration:
    evidence = (_evidence(_artifact("registration")),)
    return IntendedUseRegistration(
        registration_id="registration.m1904.synthetic",
        version="1.0.0",
        intended_use=IntendedUseKind.CLINICAL_REVIEW,
        audience="Clinical science reviewer",
        evidence_tier=2,
        claim_ceiling=ClaimCeiling(
            maximum_claim="Descriptive proteotype state within the registered context.",
            prohibited_interpretations=(
                "Treatment recommendation",
                "KINOPHOS kinase activity",
            ),
            rationale="The caller-declared evidence tier bounds interpretation.",
            evidence=evidence,
        ),
        display_semantics=DisplaySemantics(
            section_order=("finding", "support", "uncertainty", "limitations"),
            safe_default="Show bounded research context and explicit abstention.",
            evidence=evidence,
        ),
        evidence=evidence,
    )


def _request(
    *,
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
) -> AdaptProteotypeIntendedUseRequest:
    upstream = _artifact("integrated", "application/vnd.glio-proteogen.m19-03+json")
    if source_artifacts is None:
        source_artifacts = (upstream, _artifact("supporting"))
    return AdaptProteotypeIntendedUseRequest(
        request_id="request.m1904.synthetic",
        context=_context(),
        upstream_result=upstream,
        registration=_registration(),
        source_artifacts=source_artifacts,
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.1,
        rationale="Synthetic bounded uncertainty estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Synthetic sensitivity note.",),
    )


def _provenance(request: AdaptProteotypeIntendedUseRequest) -> ProvenanceRecord:
    refs = request.context.references
    role_to_ref: dict[ControlRole, _ControlReference] = {
        ControlRole.APPROVED_CONFIGURATION: refs.approved_configuration,
        ControlRole.IDENTITY_LINEAGE: refs.identity_lineage,
        ControlRole.PROVENANCE: refs.provenance,
        ControlRole.CONSENT: refs.consent,
        ControlRole.QUALITY: refs.quality,
        ControlRole.SUPPORT: refs.support,
        ControlRole.INTENDED_USE: refs.intended_use,
    }
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=ref.decision_id,
            state=ref.state.value,
            policy_version=ref.policy_version,
            evidence_digest=ref.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, ref in role_to_ref.items()
    )
    consent = refs.consent
    return ProvenanceRecord(
        activity_id="activity.m1904.synthetic",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M19-04",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=consent.decision_id,
        consent_state=consent.state,
        consent_policy_version=consent.policy_version,
        consent_evidence_digest=consent.evidence.digest,
        control_decisions=decisions,
    )


def _valid_result() -> ProteotypeIntendedUseAdapterResult:
    request = _request()
    uncertainty = _uncertainty()
    evidence = (_evidence(request.upstream_result),)
    policy = PolicyDecision(
        status=PolicyDecisionStatus.ALLOWED,
        reason_code=AdapterFindingCode.ALLOWED,
        rationale="Registered intended use and supported upstream evidence.",
        evidence=evidence,
    )
    adapted = IntendedUseSpecificObject(
        object_id="object.m1904.synthetic",
        version="0.1.0-provisional",
        upstream_result=request.upstream_result,
        registration=request.registration,
        policy_decision=policy,
        uncertainty=uncertainty,
        evidence=evidence,
    )
    result = ProteotypeIntendedUseAdapterResult.model_construct(
        result_id="result.placeholder",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=AdapterStatus.ADAPTED,
        adapted_object=adapted,
        policy_decision=policy,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="support.m1904.accepted",
            rationale="Synthetic upstream support is explicitly declared.",
        ),
        uncertainty=uncertainty,
        provenance=_provenance(request),
        evidence=evidence,
        limitations=(
            Limitation(
                code="limitation.m1904.bounded_claim",
                statement="Output is limited to the registered intended use.",
            ),
        ),
        human_review_required=False,
    )
    result = result.model_copy(
        update={
            "result_id": f"result.{result.request_digest.removeprefix('sha256:')}",
        }
    )
    return result.model_copy(update={"result_digest": result_payload_digest(result)})


def _revalidate(result: ProteotypeIntendedUseAdapterResult) -> ProteotypeIntendedUseAdapterResult:
    return ProteotypeIntendedUseAdapterResult.model_validate(result, strict=True)


def test_replay_helpers_are_stable_and_tamper_sensitive() -> None:
    request = _request()
    digest = canonical_request_digest(request)
    assert verify_request_digest(request, digest)
    assert canonical_request_bytes(request) == canonical_request_bytes(request)
    altered = request.model_copy(update={"request_id": "request.m1904.changed"})
    assert not verify_request_digest(altered, digest)

    payload = {"result_digest": "sha256:" + "0" * 64, "value": "stable"}
    result_digest = result_payload_digest(payload)
    assert verify_result_digest(payload, result_digest)
    assert canonical_result_payload_bytes(payload) == canonical_result_payload_bytes(payload)
    assert not verify_result_digest({**payload, "value": "changed"}, result_digest)


def test_claim_and_display_registrations_reject_duplicate_order() -> None:
    evidence = (_evidence(_artifact("duplicate")),)
    with pytest.raises(ValueError, match="prohibited interpretations"):
        ClaimCeiling(
            maximum_claim="Bounded claim.",
            prohibited_interpretations=("treatment", "treatment"),
            rationale="Duplicate must not be silently collapsed.",
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="display section order"):
        DisplaySemantics(
            section_order=("support", "support"),
            safe_default="Show support.",
            evidence=evidence,
        )


def test_request_requires_unique_and_exact_upstream_artifact_binding() -> None:
    upstream = _artifact("integrated", "application/vnd.glio-proteogen.m19-03+json")
    with pytest.raises(ValueError, match="artifact ids"):
        _request(source_artifacts=(upstream, upstream))
    with pytest.raises(ValueError, match="upstream result exactly"):
        _request(source_artifacts=(_artifact("other"),))


def test_policy_status_cannot_hide_blocked_claims() -> None:
    evidence = (_evidence(_artifact("policy")),)
    with pytest.raises(ValueError, match="requires blocked claims"):
        PolicyDecision(
            status=PolicyDecisionStatus.BLOCKED,
            reason_code=AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
            rationale="A blocked claim must be visible.",
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="cannot carry blocked claims"):
        PolicyDecision(
            status=PolicyDecisionStatus.ALLOWED,
            reason_code=AdapterFindingCode.ALLOWED,
            rationale="Allowed output cannot carry blocked claims.",
            blocked_claims=("treatment recommendation",),
            evidence=evidence,
        )


def test_result_closure_rejects_identifier_and_object_tampering() -> None:
    result = _valid_result()
    adapted_object = result.adapted_object
    assert adapted_object is not None
    with pytest.raises(ValueError, match="identifier"):
        _revalidate(result.model_copy(update={"result_id": "result.wrong"}))
    with pytest.raises(ValueError, match="adapted object"):
        _revalidate(
            result.model_copy(
                update={
                    "adapted_object": adapted_object.model_copy(
                        update={"upstream_result": _artifact("different")}
                    )
                }
            )
        )
    finding = AdapterFinding(
        finding_id="finding.m1904.duplicate",
        code=AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
        message="Duplicate finding identity.",
    )
    with pytest.raises(ValueError, match="finding ids"):
        _revalidate(result.model_copy(update={"findings": (finding, finding)}))


def test_abstention_requires_human_review_and_safe_support() -> None:
    result = _valid_result()
    with pytest.raises(ValueError, match="abstained result"):
        _revalidate(
            result.model_copy(
                update={
                    "status": AdapterStatus.ABSTAINED,
                    "adapted_object": None,
                    "abstention_reason": "Unsupported intended use.",
                    "support_decision": SupportDecision(
                        status=SupportStatus.SUPPORTED,
                        reason_code="support.invalid",
                        rationale="Supported cannot describe abstention.",
                    ),
                    "human_review_required": True,
                }
            )
        )


@pytest.mark.parametrize(
    "surface",
    [
        "audience",
        "maximum_claim",
        "rationale",
        "claim_ceiling_evidence",
        "display_default",
        "display_evidence",
        "registration_evidence",
    ],
)
def test_all_caller_claim_surfaces_block_prohibited_scope(surface: str) -> None:
    request = _request()
    registration = request.registration
    if surface == "audience":
        registration = registration.model_copy(update={"audience": "glioma-specific audience"})
    elif surface in {"maximum_claim", "rationale", "claim_ceiling_evidence"}:
        ceiling = registration.claim_ceiling
        if surface == "maximum_claim":
            ceiling = ceiling.model_copy(update={"maximum_claim": "proteoform inference claim"})
        elif surface == "rationale":
            ceiling = ceiling.model_copy(update={"rationale": "identity inference rationale"})
        else:
            evidence = ceiling.evidence[0].model_copy(update={"claim": "isoform evidence"})
            ceiling = ceiling.model_copy(update={"evidence": (evidence,)})
        registration = registration.model_copy(update={"claim_ceiling": ceiling})
    elif surface in {"display_default", "display_evidence"}:
        display = registration.display_semantics
        if surface == "display_default":
            display = display.model_copy(update={"safe_default": "Show protein inference."})
        else:
            evidence = display.evidence[0].model_copy(update={"claim": "proteoform evidence"})
            display = display.model_copy(update={"evidence": (evidence,)})
        registration = registration.model_copy(update={"display_semantics": display})
    else:
        evidence = registration.evidence[0].model_copy(update={"claim": "isoform evidence"})
        registration = registration.model_copy(update={"evidence": (evidence,)})

    result = M1904Engine().adapt(request.model_copy(update={"registration": registration}))
    assert result.status is AdapterStatus.ABSTAINED
    assert any(item.code is AdapterFindingCode.CLAIM_EXCEEDS_CEILING for item in result.findings)
    with pytest.raises(ValueError, match="human review"):
        _revalidate(
            result.model_copy(
                update={
                    "status": AdapterStatus.ABSTAINED,
                    "adapted_object": None,
                    "abstention_reason": "Unsupported intended use.",
                    "support_decision": SupportDecision(
                        status=SupportStatus.UNSUPPORTED,
                        reason_code="support.unsupported",
                        rationale="Synthetic unsupported input.",
                    ),
                    "policy_decision": PolicyDecision(
                        status=PolicyDecisionStatus.ABSTAINED,
                        reason_code=AdapterFindingCode.UPSTREAM_UNSUPPORTED,
                        rationale="Abstention is visible and reviewable.",
                        blocked_claims=("unsupported claim",),
                        evidence=result.evidence,
                    ),
                    "human_review_required": False,
                }
            )
        )
