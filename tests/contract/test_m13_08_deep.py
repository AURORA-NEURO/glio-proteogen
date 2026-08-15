"""Contract, runtime, replay, safety, and plugin tests for M13-08."""

# ruff: noqa: E501, PLR2004, TRY003

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import glio_proteogen.modules.c13_variant_peptide.m13_08_mechanism_evidence_dossier.engine as engine_module
from glio_proteogen.contracts.m13_08 import (
    M1308_M1307_INPUT_MEDIA_TYPE,
    M1308_MODULE_ID,
    AssembleProteotypeMechanismDossierRequest,
    DossierDiagnosticStatus,
    MechanismDossierConfiguration,
    MechanismDossierStatus,
    MechanismEvidenceLinkKind,
    ProteotypeMechanismDossierResult,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c13_variant_peptide.m13_08_mechanism_evidence_dossier import (
    M1308AuthorizationError,
    M1308DossierEngine,
    M1308Plugin,
    M1308ReplayVerificationError,
    M1308Service,
    ValidatedM1308Request,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1308": label}),
        media_type=media_type,
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
            binding_digest=sha256_digest("identity"),
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
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def _request(
    model_family: str = "bayesian_model_averaging", *, accepted: bool = True
) -> AssembleProteotypeMechanismDossierRequest:
    evidence = EvidenceReference(
        reference=_artifact("configuration.evidence"),
        role="evidence",
        claim="Locked dossier configuration.",
    )
    configuration = MechanismDossierConfiguration(
        configuration_id="configuration.m1308",
        version="1.0.0",
        model_family=model_family,
        source_manifest=(_artifact("manifest"),),
        evidence=(evidence,),
    )
    return AssembleProteotypeMechanismDossierRequest(
        request_id="request.m1308",
        context=ExecutionContext(
            request_id="request.m1308",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        upstream_result=_artifact("m1307-result", M1308_M1307_INPUT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(_artifact("source"),),
    )


def test_supported_dossier_is_reconstructable_and_replayable() -> None:
    engine = M1308DossierEngine()
    result = engine.infer(_request())
    assert result.status is MechanismDossierStatus.READY
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.dossier is not None
    assert result.provenance.module_id == M1308_MODULE_ID
    assert result.dossier.claim_ceiling.prohibited_interpretations
    assert any(
        link.kind is MechanismEvidenceLinkKind.CLAIM_CEILING for link in result.dossier.links
    )
    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


@pytest.mark.parametrize("family", ["state_space", "mechanistic", "foundation_assisted"])
def test_supported_model_family_variants_are_ready(family: str) -> None:
    result = M1308DossierEngine().infer(_request(family))
    assert result.status is MechanismDossierStatus.READY
    assert result.dossier is not None
    assert any(item.status is DossierDiagnosticStatus.PASS for item in result.diagnostics)


@pytest.mark.parametrize("family", ["abstain", "unknown-family", "bayesian_graph"])
def test_unsupported_family_abstains_without_dossier(family: str) -> None:
    result = M1308DossierEngine().infer(_request(family))
    assert result.status is MechanismDossierStatus.ABSTAINED
    assert result.dossier is None
    assert result.abstention_reason
    assert result.findings
    assert result.human_review_required
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_controls_and_hostile_candidate_fail_closed() -> None:
    with pytest.raises(M1308AuthorizationError):
        M1308DossierEngine().infer(_request(accepted=False))

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("opaque content must not be traversed")

    with pytest.raises(M1308AuthorizationError):
        M1308DossierEngine().infer(Hostile())


def test_tamper_replay_guards_and_plugin_capability() -> None:
    engine = M1308DossierEngine()
    result = engine.infer(_request())
    with pytest.raises(M1308ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}))
    assert engine.verify(result, replay=False) == result
    plugin = M1308Plugin(M1308Service())
    assert plugin.descriptor().module_id == M1308_MODULE_ID
    token = plugin.validate(_request())
    assert plugin.run(token).status is MechanismDossierStatus.READY
    assert isinstance(token, ValidatedM1308Request)
    forged = ValidatedM1308Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(StrictJsonError):
        plugin.validate('{"request_id":"a","request_id":"b"}')
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status is MechanismDossierStatus.READY


def test_request_and_result_contract_closure_rejects_forgery() -> None:
    request = _request()
    forged = request.model_dump(mode="python")
    forged["upstream_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M13-07"):
        AssembleProteotypeMechanismDossierRequest.model_validate(forged, strict=True)
    duplicate = request.model_dump(mode="python")
    duplicate["source_artifacts"] = (
        duplicate["source_artifacts"][0],
        duplicate["source_artifacts"][0],
    )
    with pytest.raises(ValueError, match="unique"):
        AssembleProteotypeMechanismDossierRequest.model_validate(duplicate, strict=True)
    result = M1308DossierEngine().infer(request)

    def resigned(**updates: object) -> dict[str, object]:
        payload = result.model_dump(mode="python")
        payload.update(updates)
        payload["result_digest"] = result_payload_digest(payload)
        return payload

    with pytest.raises(ValueError, match="result identifier"):
        ProteotypeMechanismDossierResult.model_validate(
            resigned(result_id="result.bad"), strict=True
        )
    with pytest.raises(ValueError, match="every result"):
        ProteotypeMechanismDossierResult.model_validate(resigned(evidence=()), strict=True)
    bad_review = result.model_dump(mode="python")
    bad_review["human_review_required"] = True
    bad_review["result_digest"] = result_payload_digest(bad_review)
    with pytest.raises(ValueError, match="ready result"):
        ProteotypeMechanismDossierResult.model_validate(bad_review, strict=True)


def test_uncertainty_and_service_public_paths() -> None:
    assert expected_uncertainty(supported=True).measurement.probability == 0.9
    assert expected_uncertainty(supported=False).measurement.probability is None
    service = M1308Service()
    request = _request()
    assert service.validate_request(request) == request
    result = service.execute(request)
    assert service.verify(result).status is MechanismDossierStatus.READY
    assert (
        engine_module.assemble_proteotype_mechanism_dossier(request).status
        is MechanismDossierStatus.READY
    )
