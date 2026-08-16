"""Adversarial closure for the provisional M20-04 contract spine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_04 import (
    M2004_M2003_INPUT_MEDIA_TYPE,
    AdapterFindingCode,
    AdaptProteinSubtypeIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseKind,
    IntendedUseRegistration,
    PolicyDecision,
    PolicyDecisionStatus,
    ProteinSubtypeIntendedUseAdapterResult,
    canonical_request_digest,
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
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m20_04_intended_use_adapter as m2004,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2004.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2004:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M20-04 evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2004.{role}",
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
        request_id="request.m2004.synthetic",
        actor_id="actor.m2004.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2004.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2004.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2004.consent",
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
        registration_id="registration.m2004.synthetic",
        version="1.0.0",
        intended_use=IntendedUseKind.INTERNAL_VALIDATION,
        audience="Data engineering reviewer",
        evidence_tier=2,
        claim_ceiling=ClaimCeiling(
            maximum_claim="Descriptive protein subtype state.",
            prohibited_interpretations=("treatment recommendation", "diagnosis"),
            rationale="Evidence tier bounds interpretation.",
            evidence=evidence,
        ),
        display_semantics=DisplaySemantics(
            section_order=("support", "uncertainty", "evidence", "limitations"),
            safe_default="Show bounded internal-validation context.",
            evidence=evidence,
        ),
        evidence=evidence,
    )


def _request(*, upstream: ArtifactReference | None = None) -> AdaptProteinSubtypeIntendedUseRequest:
    upstream = upstream or _artifact("integrated", M2004_M2003_INPUT_MEDIA_TYPE)
    return AdaptProteinSubtypeIntendedUseRequest(
        request_id="request.m2004.synthetic",
        context=_context(),
        upstream_result=upstream,
        registration=_registration(),
        source_artifacts=(upstream, _artifact("registration")),
    )


def test_request_requires_exact_m20_03_media_and_unique_sources() -> None:
    with pytest.raises(ValidationError, match="M20-03"):
        _request(upstream=_artifact("wrong"))
    request = _request()
    with pytest.raises(ValidationError, match="source artifact ids"):
        TypeAdapter(AdaptProteinSubtypeIntendedUseRequest).validate_python(
            request.model_copy(update={"source_artifacts": (request.upstream_result,) * 2}),
            strict=True,
        )


def test_registration_and_policy_collections_are_closed() -> None:
    registration = _registration()
    with pytest.raises(ValidationError, match="prohibited interpretations"):
        ClaimCeiling.model_validate(
            registration.claim_ceiling.model_dump()
            | {"prohibited_interpretations": ("treatment", "treatment")}
        )
    with pytest.raises(ValidationError, match="registration evidence"):
        IntendedUseRegistration.model_validate(
            registration.model_dump() | {"evidence": registration.evidence + registration.evidence}
        )


def test_contract_constants_make_authority_and_upstream_binding_explicit() -> None:
    assert _request().upstream_result.media_type == M2004_M2003_INPUT_MEDIA_TYPE


def test_display_and_policy_collections_reject_duplicate_members() -> None:
    registration = _registration()
    with pytest.raises(ValidationError, match="display section order"):
        DisplaySemantics.model_validate(
            registration.display_semantics.model_dump() | {"section_order": ("support", "support")}
        )
    with pytest.raises(ValidationError, match="blocked claims"):
        PolicyDecision(
            status=PolicyDecisionStatus.BLOCKED,
            reason_code=AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
            rationale="Review required.",
            blocked_claims=("claim", "claim"),
            evidence=registration.evidence,
        )


def test_result_identity_and_digest_closures_reject_tampering() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump()).startswith("sha256:")
    result = m2004.M2004Engine().adapt(request)
    payload = result.model_dump()
    for field, message in (
        ("request_digest", "request digest"),
        ("result_id", "result identifier"),
        ("result_digest", "result digest"),
    ):
        tampered = dict(payload)
        tampered[field] = "sha256:" + "1" * 64 if field != "result_id" else "result.tampered"
        with pytest.raises(ValidationError, match=message):
            TypeAdapter(ProteinSubtypeIntendedUseAdapterResult).validate_python(
                tampered, strict=True
            )


def test_result_status_closures_reject_missing_object_or_review() -> None:
    request = _request()
    engine = m2004.M2004Engine()
    adapted = engine.adapt(request)
    payload = adapted.model_dump()
    payload["adapted_object"] = None
    with pytest.raises(ValidationError, match="adapted result"):
        TypeAdapter(ProteinSubtypeIntendedUseAdapterResult).validate_python(payload, strict=True)
    blocked = engine.adapt(
        request.model_copy(
            update={
                "registration": request.registration.model_copy(
                    update={
                        "claim_ceiling": request.registration.claim_ceiling.model_copy(
                            update={"maximum_claim": "Treatment recommendation."}
                        )
                    }
                )
            }
        )
    )
    blocked_payload = blocked.model_dump()
    blocked_payload["findings"] = (*blocked_payload["findings"], blocked_payload["findings"][0])
    with pytest.raises(ValidationError, match="finding ids"):
        TypeAdapter(ProteinSubtypeIntendedUseAdapterResult).validate_python(
            blocked_payload, strict=True
        )
    blocked_payload["findings"] = blocked.model_dump()["findings"]
    blocked_payload["human_review_required"] = False
    with pytest.raises(ValidationError, match="abstained result"):
        TypeAdapter(ProteinSubtypeIntendedUseAdapterResult).validate_python(
            blocked_payload, strict=True
        )
