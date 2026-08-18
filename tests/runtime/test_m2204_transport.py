"""Runtime, replay, service, plugin, and abstention coverage for M22-04."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m22_04 import (
    M2204_M2202_INPUT_MEDIA_TYPE,
    M2204_M2203_INPUT_MEDIA_TYPE,
    EvaluateProteinRnaDiscordanceExternalTransportRequest,
    EvaluationStatus,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m22_04_external_transport_evaluator import (
    M2204AuthorizationError,
    M2204Engine,
    M2204Plugin,
    M2204ReplayError,
    M2204Service,
    ValidatedM2204Request,
    evaluate_protein_rna_discordance_external_transport,
)

DIMENSIONS = tuple(TransportDimension)


def _artifact(
    name: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2204.{name}",
        version="1.0.0",
        digest=sha256_digest({"m2204": name, "media": media_type}),
        media_type=media_type,
    )


def _evidence(name: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(name),
            role="evidence",
            claim="Caller-declared M22-04 transport evidence.",
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.9,
        rationale="Caller-declared transport uncertainty estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Transport issuer authority remains caller-declared.",),
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2204.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        name: _artifact(f"control-{name}")
        for name in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.m2204.synthetic",
        actor_id="actor.m2204.synthetic",
        occurred_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2204.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2204.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2204.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended"]),
        ),
    )


def _config() -> TransportConfiguration:
    return TransportConfiguration(
        configuration_id="configuration.m2204.synthetic",
        version="1.0.0",
        required_dimensions=DIMENSIONS,
        minimum_calibration_floor=0.8,
        evidence=_evidence("configuration"),
    )


def _validation(dimension: TransportDimension) -> TransportValidation:
    return TransportValidation(
        validation_id=f"validation.m2204.{dimension.value}",
        dimension=dimension,
        source_domain="source-domain",
        target_domain="target-domain",
        assay_or_platform="orthogonal immunoassay",
        specimen_description="frozen glioma specimen",
        sample_count=12,
        provenance_artifact=_artifact(f"provenance-{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=_evidence(f"validation-{dimension.value}"),
    )


def _evaluation(
    dimension: TransportDimension,
    status: TransportStatus = TransportStatus.SUPPORTED,
) -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id=f"evaluation.m2204.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="transport calibration",
        metric_value=0.9 if status is TransportStatus.SUPPORTED else 0.5,
        calibration_floor=0.8,
        rationale="Caller-declared external transport evaluation.",
        evidence=_evidence(f"evaluation-{dimension.value}"),
    )


def _request(
    evaluations: tuple[TransportEvaluation, ...] | None = None,
) -> EvaluateProteinRnaDiscordanceExternalTransportRequest:
    truth = _artifact("truth", M2204_M2202_INPUT_MEDIA_TYPE)
    benchmark = _artifact("benchmark", M2204_M2203_INPUT_MEDIA_TYPE)
    return EvaluateProteinRnaDiscordanceExternalTransportRequest(
        request_id="request.m2204.synthetic",
        context=_context(),
        benchmark_package=benchmark,
        upstream_truth=truth,
        validations=tuple(_validation(dimension) for dimension in DIMENSIONS),
        evaluations=evaluations or tuple(_evaluation(dimension) for dimension in DIMENSIONS),
        configuration=_config(),
        source_artifacts=(truth, benchmark, _artifact("source")),
    )


def test_engine_evaluates_all_dimensions_and_replays_exactly() -> None:
    request = _request()
    result = M2204Engine().evaluate(request)
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.report.support_domain.retained_dimensions == DIMENSIONS
    assert M2204Engine().replay(result) == result


def test_partial_narrowing_is_explicit_and_total_narrowing_abstains() -> None:
    evaluations = [_evaluation(dimension) for dimension in DIMENSIONS]
    evaluations[0] = _evaluation(TransportDimension.SITE, TransportStatus.DOMAIN_NARROWED)
    result = M2204Engine().evaluate(_request(evaluations=tuple(evaluations)))
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.report.support_domain.narrowed_dimensions == (TransportDimension.SITE,)
    all_narrowed = tuple(
        _evaluation(dimension, TransportStatus.DOMAIN_NARROWED) for dimension in DIMENSIONS
    )
    abstained = M2204Engine().evaluate(_request(evaluations=all_narrowed))
    assert abstained.status is EvaluationStatus.ABSTAINED
    assert abstained.report is None


def test_authorization_service_plugin_and_public_entry_point() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    references = request.context.references.model_copy(update={"consent": consent})
    with pytest.raises(M2204AuthorizationError):
        M2204Engine().evaluate(
            request.model_copy(
                update={"context": request.context.model_copy(update={"references": references})}
            )
        )
    service = M2204Service()
    result = service.evaluate(request.model_dump_json())
    assert service.replay(result.model_dump_json()) == result
    assert service.evaluate(request.model_dump(mode="json")) == result
    assert service.replay(result.model_dump(mode="json")) == result
    plugin = M2204Plugin(service)
    token = plugin.validate(request)
    assert plugin.run(token) == result
    assert plugin.validate_request(request) == request
    assert plugin.replay(result) == result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M22-04"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(ValidatedM2204Request(request, object()))
    assert evaluate_protein_rna_discordance_external_transport(request) == result


def test_replay_rejects_tampering() -> None:
    result = M2204Engine().evaluate(_request())
    with pytest.raises(M2204ReplayError):
        M2204Engine().replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
