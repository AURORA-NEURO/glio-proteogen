"""Adversarial and replay coverage for M15-08."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m15_08 import (
    M1508_M1507_INPUT_MEDIA_TYPE,
    AssembleComplexActivityMechanismDossierRequest,
    DossierDiagnosticStatus,
    MechanismDossierConfiguration,
    MechanismDossierFindingCode,
    MechanismDossierStatus,
    result_payload_digest,
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
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_08_mechanism_evidence_dossier as m1508,
)

_LINK_COUNT = 5


def _digest(label: str) -> str:
    return sha256_digest({"m1508-test": label})


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1508.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M15-08 test evidence.",
    )


def _context() -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m1508",
        actor_id="reviewer.test",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request() -> AssembleComplexActivityMechanismDossierRequest:
    configuration = MechanismDossierConfiguration(
        configuration_id="configuration.m1508",
        version="1.0.0",
        model_family="conformal_proteotype",
        source_manifest=(_artifact("manifest-proteome"), _artifact("manifest-genome")),
        evidence=(_evidence("configuration-evidence"),),
    )
    return AssembleComplexActivityMechanismDossierRequest(
        request_id="request.m1508",
        context=_context(),
        upstream_result=ArtifactReference(
            artifact_id="upstream.m1507",
            version="0.1.0-provisional",
            digest=_digest("upstream"),
            media_type=M1508_M1507_INPUT_MEDIA_TYPE,
        ),
        configuration=configuration,
        source_artifacts=(_artifact("proteome"), _artifact("genome"), _artifact("ptm")),
    )


def test_supported_replay_preserves_chain_counter_evidence_and_ceiling() -> None:
    service = m1508.M1508Service()
    result = service.execute(_request())
    assert result.status is MechanismDossierStatus.READY
    assert result.dossier is not None
    assert len(result.dossier.links) == _LINK_COUNT
    assert result.dossier.counter_evidence[0].challenges_link_ids == ("link.m1508.mechanism",)
    assert result.dossier.validation_routes[0].status.value == "planned"
    assert result.dossier.claim_ceiling.prohibited_interpretations
    assert result.findings == (MechanismDossierFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,)
    assert all(
        diagnostic.status in {DossierDiagnosticStatus.PASS, DossierDiagnosticStatus.WARNING}
        for diagnostic in result.diagnostics
    )
    assert result.parent_target == "complex_activity"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert service.verify(result).result_digest == result.result_digest


def test_denied_control_fails_closed() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    with pytest.raises(m1508.M1508AuthorizationError):
        m1508.M1508Service().execute(request.model_copy(update={"context": denied_context}))


def test_upstream_and_source_boundaries_reject() -> None:
    request = _request()
    wrong_upstream = request.model_copy(
        update={
            "upstream_result": request.upstream_result.model_copy(
                update={"media_type": "application/json"}
            )
        }
    )
    with pytest.raises(ValueError, match="M15-07"):
        m1508.M1508Service().construct(wrong_upstream)
    duplicate = request.source_artifacts[0]
    duplicate_payload = request.model_dump(mode="python")
    duplicate_payload["source_artifacts"] = (duplicate, duplicate)
    with pytest.raises(ValueError, match="unique"):
        AssembleComplexActivityMechanismDossierRequest(
            **duplicate_payload,
        )


def test_tampered_result_fails_replay_verification() -> None:
    result = m1508.M1508Service().execute(_request())
    tampered = result.model_copy(update={"human_review_required": False})
    with pytest.raises(m1508.M1508ReplayVerificationError):
        m1508.M1508Service().verify(tampered)


def test_replay_mismatch_is_distinguished_from_digest_tamper() -> None:
    result = m1508.M1508Service().execute(_request())
    changed = result.model_copy(update={"human_review_required": False})
    changed = changed.model_copy(update={"result_digest": result_payload_digest(changed)})
    with pytest.raises(m1508.M1508ReplayVerificationError):
        m1508.M1508Service().verify(changed)


def test_digest_tamper_is_rejected_when_deterministic_replay_is_disabled() -> None:
    result = m1508.M1508Service().execute(_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises(m1508.M1508ReplayVerificationError):
        m1508.M1508Service().verify(forged, replay=False)


def test_mapping_service_and_plugin_paths() -> None:
    request = _request()
    service = m1508.M1508Service()
    mapping = request.model_dump(mode="python")
    assert service.validate_request(request).request_id == request.request_id
    assert service.validate_request(mapping).request_id == request.request_id
    assert service.construct(mapping).status is MechanismDossierStatus.READY
    plugin = m1508.M1508Plugin(service)
    validated = plugin.validate(request.model_dump_json())
    assert plugin.validate(request).request.request_id == request.request_id
    result = plugin.run(validated)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M15-08"
    assert plugin.verify(result, replay=False).result_id == result.result_id
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="strict request"):
        service.validate_request(object())


def test_invalid_engine_candidate_and_authorization_shape_fail_closed() -> None:
    request = _request()

    class Candidate:
        context = request.context

    with pytest.raises(TypeError, match="strict request"):
        m1508.M1508Service().construct(Candidate())

    class Broken:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(m1508.M1508AuthorizationError):
        m1508.preflight_m1508_authorization(Broken())


def test_duplicate_evidence_is_canonicalized() -> None:
    original = _request()
    request = original.model_copy(
        update={
            "configuration": original.configuration.model_copy(
                update={"source_manifest": (original.source_artifacts[0],)}
            )
        }
    )
    result = m1508.M1508Service().execute(request)
    keys = [
        (
            item.reference.artifact_id,
            item.reference.version,
            item.reference.digest,
            item.reference.media_type,
        )
        for item in result.evidence
    ]
    assert len(keys) == len(set(keys))


def test_unknown_field_is_rejected_strictly() -> None:
    payload = _request().model_dump(mode="json")
    payload["unexpected"] = "reject"
    with pytest.raises(ValueError, match="extra"):
        AssembleComplexActivityMechanismDossierRequest.model_validate_json(
            json.dumps(payload), strict=True
        )
