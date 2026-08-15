"""Runtime, replay and safety coverage for provisional M11-08."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m11_08 import (
    M1108_M1107_INPUT_MEDIA_TYPE,
    AssembleVariantPeptideMechanismDossierRequest,
    CounterEvidenceRecord,
    DossierDiagnosticStatus,
    MechanismDossierAssumption,
    MechanismDossierConfiguration,
    MechanismDossierStatus,
    MechanismEvidenceLink,
    MechanismEvidenceLinkKind,
    MechanismEvidenceSource,
    MechanismEvidenceSourceKind,
    ReconstructionStep,
    ValidationRoute,
    ValidationRouteStatus,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_08_mechanism_evidence_dossier import (
    M1108AuthorizationError,
    M1108MechanismEvidenceDossierPlugin,
    M1108MechanismEvidenceDossierService,
    assemble_mechanism_dossier,
    preflight_m1108_authorization,
    verify_mechanism_dossier_result,
)


def artifact(name: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode().hex() * 64)[:64],
        media_type=media_type,
    )


def evidence(name: str, role: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=artifact(name),
        role=role,
        claim=f"Caller-declared evidence for {name}.",
    )


def accepted(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact(f"control.{name}"),
    )


def context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m1108",
        actor_id="actor.reviewer",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact("control.identity"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def source(source_id: str, kind: MechanismEvidenceSourceKind) -> MechanismEvidenceSource:
    return MechanismEvidenceSource(
        source_id=source_id,
        kind=kind,
        artifact=artifact(f"artifact.{source_id}"),
        claim=f"Caller-declared {kind.value} source.",
        evidence=(evidence(f"evidence.{source_id}"),),
    )


def request() -> AssembleVariantPeptideMechanismDossierRequest:
    sources = (
        source("source.ms", MechanismEvidenceSourceKind.MASS_SPECTROMETRY_PROTEOME),
        source("source.genome", MechanismEvidenceSourceKind.GENOME_TRANSCRIPTOME),
        source("source.ptm", MechanismEvidenceSourceKind.PTM_ANNOTATIONS),
        source("source.variant", MechanismEvidenceSourceKind.UPSTREAM_VARIANT_PEPTIDE),
        source("source.quality", MechanismEvidenceSourceKind.QUALITY_SUPPORT),
    )
    links = (
        MechanismEvidenceLink(
            link_id="link.input",
            kind=MechanismEvidenceLinkKind.INPUT,
            assertion="The declared measurements enter the evidence chain.",
            predecessor_ids=("source.ms", "source.genome", "source.ptm"),
            evidence=(evidence("evidence.link-input"),),
            assumptions=("Source identities and units are caller-owned.",),
        ),
        MechanismEvidenceLink(
            link_id="link.mechanism",
            kind=MechanismEvidenceLinkKind.MECHANISM,
            assertion="A protein-native mechanism association is structurally traceable.",
            predecessor_ids=("link.input", "source.variant"),
            evidence=(evidence("evidence.link-mechanism"),),
            assumptions=("The mechanism interpretation remains review-bound.",),
        ),
        MechanismEvidenceLink(
            link_id="link.ceiling",
            kind=MechanismEvidenceLinkKind.CLAIM_CEILING,
            assertion="The claim ceiling prevents prohibited interpretations.",
            predecessor_ids=("link.mechanism",),
            evidence=(evidence("evidence.link-ceiling"),),
            assumptions=("Independent review is required for promotion.",),
        ),
    )
    configuration = MechanismDossierConfiguration(
        configuration_id="configuration.m1108",
        version="1.0.0",
        model_family="curated_mechanistic_baseline",
        source_manifest=(artifact("artifact.configuration"),),
        evidence=(evidence("evidence.configuration"),),
    )
    return AssembleVariantPeptideMechanismDossierRequest(
        request_id="request.m1108",
        context=context(),
        upstream_result=artifact("upstream.variant-peptide", M1108_M1107_INPUT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=sources,
        assumptions=(
            MechanismDossierAssumption(
                assumption_id="assumption.review",
                statement="Every link remains caller-attributed until independent review.",
                evidence=(evidence("evidence.assumption"),),
            ),
        ),
        links=links,
        counter_evidence=(
            CounterEvidenceRecord(
                counter_evidence_id="counter.discordance",
                statement="Transcript-protein discordance remains visible as counter-evidence.",
                impact="It may weaken the mechanism association.",
                challenges_link_ids=("link.mechanism",),
                evidence=(evidence("evidence.counter", "counter_evidence"),),
            ),
        ),
        validation_routes=(
            ValidationRoute(
                route_id="route.orthogonal",
                method="orthogonal assay and negative control",
                status=ValidationRouteStatus.COMPLETE,
                required_experiment="Independent orthogonal assay",
                acceptance_criterion="Prespecified concordance threshold",
                evidence=(evidence("evidence.route"),),
            ),
        ),
        reconstruction_steps=(
            ReconstructionStep(
                sequence=1,
                operation="assemble_evidence_chain",
                input_digests=(artifact("upstream.variant-peptide").digest,),
                output_digest=artifact("output.m1108").digest,
                evidence=(evidence("evidence.reconstruction"),),
            ),
        ),
        reviewer_id="reviewer.bioinformatics",
    )


def test_supported_dossier_is_closed_and_replayable() -> None:
    result = assemble_mechanism_dossier(request())
    assert result.status is MechanismDossierStatus.READY
    assert result.dossier is not None
    assert result.dossier.claim_ceiling.prohibited_interpretations
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.human_review_required
    assert verify_mechanism_dossier_result(result)


def test_missing_source_abstains_without_emitting_dossier() -> None:
    original = request()
    incomplete = original.model_copy(update={"source_artifacts": original.source_artifacts[:-1]})
    result = assemble_mechanism_dossier(incomplete)
    assert result.status is MechanismDossierStatus.ABSTAINED
    assert result.dossier is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason
    assert any(
        diagnostic.status is DossierDiagnosticStatus.NOT_EVALUABLE
        for diagnostic in result.diagnostics
    )


def test_failed_validation_route_abstains() -> None:
    original = request()
    route = original.validation_routes[0].model_copy(
        update={"status": ValidationRouteStatus.FAILED}
    )
    failed = original.model_copy(update={"validation_routes": (route,)})
    result = assemble_mechanism_dossier(failed)
    assert result.status is MechanismDossierStatus.ABSTAINED
    assert "validation_route_unresolved" in {item.value for item in result.findings}


def test_denied_consent_fails_before_request_validation() -> None:
    original = request()
    references = original.context.references.model_copy(
        update={
            "consent": original.context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    denied = original.model_copy(
        update={"context": original.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M1108AuthorizationError):
        assemble_mechanism_dossier(denied)


def test_replay_tamper_is_rejected_and_plugin_requires_capability() -> None:
    result = assemble_mechanism_dossier(request())
    tampered = result.model_copy(update={"result_id": "result.tampered"})
    assert not verify_mechanism_dossier_result(tampered)
    plugin = M1108MechanismEvidenceDossierPlugin(M1108MechanismEvidenceDossierService())
    token = plugin.validate(request())
    assert plugin.run(token).result_digest == result.result_digest
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_authorization_preflight_does_not_traverse_opaque_source() -> None:
    original = request()

    class HostileArtifact:
        @property
        def artifact_id(self) -> str:
            raise AssertionError

    # The preflight only reads the seven control states; model validation is
    # intentionally deferred until after that safe authorization check.
    preflight_m1108_authorization(
        {"context": original.context, "source_artifacts": (HostileArtifact(),)}
    )
