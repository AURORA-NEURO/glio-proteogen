"""Adversarial runtime coverage for provisional M10-06."""

# Dossier control and status-count literals are intentional assertions.
# ruff: noqa: PLR2004

import pytest
from evals.m10_06.run import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m10_06 import (
    M1006_NOMINAL_COVERAGE,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyDimension,
    UncertaintyFinding,
    UncertaintyFindingCode,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_06.canonical import verify_result_digest
from glio_proteogen.kernel.models import (
    ControlRole,
    EstimateState,
    EvidenceReference,
    UncertaintyEstimate,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_06_uncertainty_decomposition import (
    M1006UncertaintyDecompositionAuthorizationError,
    M1006UncertaintyDecompositionEngine,
    M1006UncertaintyDecompositionPlugin,
    M1006UncertaintyDecompositionReplayError,
    M1006UncertaintyDecompositionService,
    decompose_protein_rna_discordance_uncertainty,
    preflight_uncertainty_decomposition_authorization,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_06_uncertainty_decomposition.plugin import (  # noqa: E501
    ValidatedM1006UncertaintyRequest,
)


def test_runtime_abstention_contains_seven_uncertainties_and_sensitivity() -> None:
    result = M1006UncertaintyDecompositionService().execute(build_request())
    assert result.status.value == "abstained"
    assert result.decomposition is None
    assert result.sensitivity_envelope.status is SensitivityEnvelopeStatus.ABSTAINED
    assert result.human_review_required is True
    assert len(result.findings) == 3
    assert len(result.evidence) == 5
    assert result.uncertainty.transport.state is EstimateState.NOT_ESTIMABLE
    assert len(result.provenance.control_decisions) == 7
    assert result.emits_parent is False


def test_replay_and_tamper_verification_are_byte_stable() -> None:
    service = M1006UncertaintyDecompositionService()
    result = service.execute(build_request())
    assert service.verify(result).model_dump_json() == result.model_dump_json()
    assert service.verify(result, replay=False).result_id == result.result_id
    with pytest.raises(M1006UncertaintyDecompositionReplayError):
        service.verify(result.model_copy(update={"abstention_reason": "tampered"}))


def test_unresolved_control_and_hostile_candidate_fail_closed() -> None:
    request = build_request(accepted_controls=False)
    with pytest.raises(M1006UncertaintyDecompositionAuthorizationError):
        M1006UncertaintyDecompositionService().execute(request)

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile")

    with pytest.raises(M1006UncertaintyDecompositionAuthorizationError):
        preflight_uncertainty_decomposition_authorization(Hostile())


def test_plugin_parse_once_token_descriptor_and_forgery() -> None:
    plugin = M1006UncertaintyDecompositionPlugin(M1006UncertaintyDecompositionService())
    request = build_request()
    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)
    assert result.status.value == "abstained"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M10-06"
    forged = ValidatedM1006UncertaintyRequest(request=request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_expected_provenance_and_public_operation_are_complete() -> None:
    request = build_request()
    result = decompose_protein_rna_discordance_uncertainty(request)
    assert result.request.request_id == request.request_id
    assert {item.role for item in result.provenance.control_decisions} == set(ControlRole)
    digest = result.request_digest
    assert expected_provenance(request, digest).module_id == "GLIO-PROTEOGEN-M10-06"
    uncertainty = expected_uncertainty()
    assert all(
        getattr(uncertainty, dimension).state is EstimateState.NOT_ESTIMABLE
        for dimension in (
            "measurement",
            "sampling",
            "parameter",
            "model_form",
            "identification",
            "support",
            "transport",
        )
    )


def test_sensitivity_and_policy_coverage_closure() -> None:
    evaluated = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=0.85,
        upper_bound=0.95,
        observed_coverage=0.9,
        rationale="Locked synthetic calibration envelope.",
    )
    assert evaluated.nominal_coverage == M1006_NOMINAL_COVERAGE
    with pytest.raises(ValidationError):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            lower_bound=0.9,
            upper_bound=0.8,
            observed_coverage=0.9,
            rationale="unordered",
        )
    with pytest.raises(ValidationError):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.NOT_EVALUABLE,
            observed_coverage=0.9,
            rationale="non-evaluated coverage is forbidden",
        )
    policy = build_request().policy
    assert policy.locked is True
    with pytest.raises(ValidationError):
        UncertaintyDecompositionPolicy(
            policy_id="policy.bad",
            version="0.1.0",
            method="bad",
            nominal_coverage=0.89,
            calibration_reference=policy.calibration_reference,
        )


def test_evidence_roles_and_component_set_are_closed() -> None:
    artifact = build_request().policy.calibration_reference
    counter = EvidenceReference(reference=artifact, role="counter_evidence", claim="counter")
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED, probability=0.2, rationale="fixture estimate"
    )
    with pytest.raises(ValidationError):
        UncertaintyComponent(
            dimension=UncertaintyDimension.MEASUREMENT,
            estimate=estimate,
            rationale="wrong evidence role",
            evidence=(counter,),
        )
    with pytest.raises(ValidationError):
        UncertaintyFinding(
            finding_id="finding.bad",
            code=UncertaintyFindingCode.CALIBRATION_NOT_LOCKED,
            message="wrong evidence role",
            evidence=(counter,),
        )
    components = tuple(
        UncertaintyComponent(
            dimension=dimension,
            estimate=estimate,
            rationale="closed component",
        )
        for dimension in UncertaintyDimension
    )
    decomposition = UncertaintyDecomposition(
        decomposition_id="decomposition.closed",
        components=components,
        method="locked-statistical-estimator",
        model_reference=artifact,
    )
    assert len(decomposition.components) == 7


def test_request_and_result_digest_closures_reject_mutations() -> None:
    request = build_request()
    with pytest.raises(ValidationError):
        request.model_validate(
            request.model_dump(mode="python")
            | {"context": request.context.model_copy(update={"request_id": "other"})},
            strict=True,
        )
    with pytest.raises(ValidationError):
        request.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])},
            strict=True,
        )
    result = M1006UncertaintyDecompositionEngine().decompose(request)
    assert verify_result_digest(result) is True
    assert verify_result_digest({}) is False
    with pytest.raises(ValidationError):
        type(result).model_validate(
            result.model_dump(mode="python") | {"result_id": "wrong"}, strict=True
        )
    with pytest.raises(M1006UncertaintyDecompositionReplayError):
        M1006UncertaintyDecompositionEngine().verify(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
        )
