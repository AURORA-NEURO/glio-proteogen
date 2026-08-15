"""Contract, runtime, replay, safety, and plugin tests for M12-08."""

# The matrix deliberately exercises fail-closed boundaries.
# ruff: noqa: ARG005, E501, PLR2004, TRY003

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from jsonschema import Draft202012Validator

import glio_proteogen.modules.c12_driver_to_protein_consequence.m12_08_mechanism_evidence_dossier.engine as engine_module
from glio_proteogen.contracts.m12_08 import (
    M1208_M1207_INPUT_MEDIA_TYPE,
    M1208_MODULE_ID,
    AssembleBiomarkerPanelMechanismDossierRequest,
    BiomarkerPanelMechanismDossierResult,
    DossierDiagnosticStatus,
    MechanismDossierConfiguration,
    MechanismDossierStatus,
    MechanismEvidenceDossier,
    MechanismEvidenceLinkKind,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_08_mechanism_evidence_dossier import (
    M1208AuthorizationError,
    M1208MechanismEvidenceEngine,
    M1208Plugin,
    M1208ReplayVerificationError,
    M1208Service,
    ValidatedM1208Request,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1208": label}),
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
    model_family: str = "bayesian_graph_baseline_stack",
    *,
    accepted: bool = True,
    upstream_label: str = "m1207-result",
) -> AssembleBiomarkerPanelMechanismDossierRequest:
    config = MechanismDossierConfiguration(
        configuration_id="configuration.m1208",
        version="1.0.0",
        model_family=model_family,
        source_manifest=(_artifact("configuration-manifest"),),
    )
    return AssembleBiomarkerPanelMechanismDossierRequest(
        request_id="request.m1208",
        context=ExecutionContext(
            request_id="request.m1208",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        upstream_result=_artifact(upstream_label, M1208_M1207_INPUT_MEDIA_TYPE),
        configuration=config,
        source_artifacts=(_artifact("source.proteome"), _artifact("source.genome")),
    )


def test_supported_dossier_is_complete_and_replayable() -> None:
    engine = M1208MechanismEvidenceEngine()
    result = engine.infer(_request())
    assert result.status is MechanismDossierStatus.READY
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.provenance.module_id == M1208_MODULE_ID
    assert result.dossier is not None
    assert {item.kind for item in result.dossier.links} == set(MechanismEvidenceLinkKind)
    assert result.dossier.counter_evidence[0].evidence[0].role == "counter_evidence"
    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


@pytest.mark.parametrize(
    "model_family",
    [
        "network_factor_hybrid",
        "curated_rule_enrichment",
        "orthogonal_consensus_baseline_stack",
    ],
)
def test_closed_architecture_families_are_deterministic(model_family: str) -> None:
    result = M1208MechanismEvidenceEngine().infer(_request(model_family))
    assert result.status is MechanismDossierStatus.READY
    assert result.dossier is not None
    assert result.dossier.configuration.model_family == model_family


@pytest.mark.parametrize("model_family", ["foundation_assisted", "", "not-a-model"])
def test_unknown_architecture_abstains_without_dossier(model_family: str) -> None:
    if not model_family:
        with pytest.raises(ValueError, match="at least 1 character"):
            _request(model_family)
        return
    result = M1208MechanismEvidenceEngine().infer(_request(model_family))
    assert result.status is MechanismDossierStatus.ABSTAINED
    assert result.dossier is None
    assert result.abstention_reason
    assert result.human_review_required
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


@pytest.mark.parametrize("upstream_label", ["m1207-unsupported", "m1207-ood", "m1207-conflict"])
def test_unsafe_upstream_metadata_abstains_safely(upstream_label: str) -> None:
    result = M1208MechanismEvidenceEngine().infer(_request(upstream_label=upstream_label))
    assert result.status is MechanismDossierStatus.ABSTAINED
    assert result.dossier is None
    assert result.findings
    assert result.diagnostics[0].status is DossierDiagnosticStatus.NOT_EVALUABLE


def test_controls_are_checked_before_materialization() -> None:
    with pytest.raises(M1208AuthorizationError):
        M1208MechanismEvidenceEngine().infer(_request(accepted=False))

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("must not traverse hostile payload")

    with pytest.raises(M1208AuthorizationError):
        M1208MechanismEvidenceEngine().infer(Hostile())


def test_tampering_and_replay_mismatch_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1208MechanismEvidenceEngine()
    result = engine.infer(_request())
    with pytest.raises(M1208ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}))
    original = engine_module.M1208MechanismEvidenceEngine.infer
    monkeypatch.setattr(
        engine_module.M1208MechanismEvidenceEngine,
        "infer",
        lambda self, request: original(self, _request("network_factor_hybrid")),
    )
    with pytest.raises(M1208ReplayVerificationError):
        engine.verify(result)
    assert engine.verify(result, replay=False) == result


def test_plugin_requires_issued_capability_and_preserves_parse_once() -> None:
    plugin = M1208Plugin(M1208Service())
    request = _request()
    token = plugin.validate(request)
    assert isinstance(token, ValidatedM1208Request)
    assert plugin.run(token).status is MechanismDossierStatus.READY
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    payload = request.model_dump_json()
    assert plugin.validate(payload).request == request


def test_service_validates_controls_and_replays() -> None:
    service = M1208Service()
    validated = service.validate_request(_request())
    result = service.execute(validated)
    assert service.verify(result) == result


def test_result_digest_is_canonical_and_all_evidence_is_typed() -> None:
    result = M1208MechanismEvidenceEngine().infer(_request())
    assert result.result_digest == result_payload_digest(result)
    assert result.evidence
    assert all(reference.role == "evidence" for reference in result.evidence)
    assert all(
        estimate.state.value == "estimated"
        for estimate in (
            result.uncertainty.measurement,
            result.uncertainty.sampling,
            result.uncertainty.parameter,
            result.uncertainty.model_form,
            result.uncertainty.identification,
            result.uncertainty.support,
            result.uncertainty.transport,
        )
    )


def test_contract_rejects_incomplete_chain_and_duplicate_diagnostics() -> None:
    result = M1208MechanismEvidenceEngine().infer(_request())
    assert result.dossier is not None
    with pytest.raises(ValueError, match="every mechanism chain link"):
        MechanismEvidenceDossier(
            dossier_id=result.dossier.dossier_id,
            version=result.dossier.version,
            links=result.dossier.links[:1],
            counter_evidence=result.dossier.counter_evidence,
            validation_routes=result.dossier.validation_routes,
            uncertainty=result.dossier.uncertainty,
            claim_ceiling=result.dossier.claim_ceiling,
            configuration=result.dossier.configuration,
            reviewer_id=result.dossier.reviewer_id,
        )
    duplicate = result.model_copy(
        update={"diagnostics": (result.diagnostics[0], result.diagnostics[0])}
    )
    with pytest.raises(ValueError, match="diagnostic identifiers"):
        BiomarkerPanelMechanismDossierResult.model_validate(duplicate, strict=True)


def test_schema_exports_are_valid_and_strict() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 9
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["x-glio-contract"]["provisionalAbi"] is True
        assert schema["x-glio-contract"]["reconstructableChainRequired"] is True
        assert schema["x-glio-contract"]["counterEvidenceRequired"] is True
