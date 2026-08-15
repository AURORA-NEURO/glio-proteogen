"""Negative-path matrix for M12-06 contract closure and safe replay."""

# This file deliberately uses parametrized error messages and long module paths
# to keep the adversarial matrix aligned with the contract wording.
# ruff: noqa: E501

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_06 import (
    PerturbationKind,
    PerturbationPolicy,
    PerturbationResponse,
    PerturbationResponseStatus,
    PerturbationScenario,
    PerturbationStatus,
    SensitivityMetric,
    SensitivitySurface,
    SimulateBiomarkerPanelPerturbationRequest,
)
from glio_proteogen.kernel.models import EvidenceReference
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.engine import (
    M1206AuthorizationError,
    preflight_m1206_authorization,
    simulate_biomarker_panel_perturbation,
)
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.service import (
    M1206Service,
)
from tests.contract.test_m12_06_runtime import _artifact, _request


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact("negative.evidence", 88),
        role="evidence",
        claim="Adversarial evidence.",
    )


def test_preflight_non_mapping_fails_closed() -> None:
    with pytest.raises(M1206AuthorizationError):
        preflight_m1206_authorization(object())


def test_policy_bounds_are_ordered() -> None:
    request = _request()
    payload = request.policy.model_dump(mode="json")
    payload["response_lower_bound"] = 1.0
    payload["response_upper_bound"] = 0.0
    with pytest.raises(ValueError, match="lower bound"):
        PerturbationPolicy.model_validate(payload, strict=False)


def test_scenario_supported_requires_non_placeholder_and_evidence() -> None:
    base = {
        "scenario_id": "scenario-negative",
        "kind": PerturbationKind.IN_SILICO,
        "parameter": "signal",
        "baseline_value": 0.2,
        "perturbed_value": 0.3,
        "unit": "relative",
        "status": PerturbationStatus.SUPPORTED,
        "assumption": "bounded",
        "source_artifact": _artifact("source", 90),
    }
    with pytest.raises(ValueError, match="requires evidence"):
        PerturbationScenario.model_validate(base, strict=True)
    base["source_artifact"] = _artifact("source", 0)
    base["evidence"] = (_evidence(),)
    with pytest.raises(ValueError, match="placeholder"):
        PerturbationScenario.model_validate(base, strict=True)


def test_unsupported_positive_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive evidence"):
        PerturbationScenario(
            scenario_id="scenario-negative",
            kind=PerturbationKind.IN_SILICO,
            parameter="signal",
            baseline_value=0.2,
            perturbed_value=0.3,
            unit="relative",
            status=PerturbationStatus.UNSUPPORTED,
            assumption="unsupported",
            source_artifact=_artifact("source", 91),
            evidence=(_evidence(),),
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"envelope_lower": 1.0, "envelope_upper": 0.0}, "envelope"),
        ({"perturbed_response": 2.0}, "outside"),
        ({"baseline_response": -1.0}, "outside"),
        ({"delta": 0.4}, "delta"),
    ],
)
def test_response_bounds_and_delta_are_closed(updates: dict[str, float], message: str) -> None:
    payload = {
        "scenario_id": "response-negative",
        "status": PerturbationResponseStatus.EVALUATED,
        "metric": SensitivityMetric.ABSOLUTE_DELTA,
        "baseline_response": 0.2,
        "perturbed_response": 0.3,
        "delta": 0.1,
        "envelope_lower": 0.0,
        "envelope_upper": 1.0,
        "evidence": (_evidence(),),
    }
    payload.update(updates)
    with pytest.raises(ValueError, match=message):
        PerturbationResponse.model_validate(payload, strict=True)


def test_unevaluable_surface_and_duplicate_ids_rejected() -> None:
    response = PerturbationResponse(
        scenario_id="response-negative",
        status=PerturbationResponseStatus.NOT_EVALUABLE,
        metric=SensitivityMetric.ABSOLUTE_DELTA,
        baseline_response=0.2,
        perturbed_response=0.2,
        delta=0.0,
        envelope_lower=0.0,
        envelope_upper=1.0,
    )
    with pytest.raises(ValueError, match="unevaluable"):
        SensitivitySurface(
            surface_id="surface-negative",
            axes=("signal",),
            responses=(response,),
            assumptions=("bounded",),
            evidence=(_evidence(),),
        )
    evaluated = response.model_copy(
        update={"status": PerturbationResponseStatus.EVALUATED, "evidence": (_evidence(),)}
    )
    with pytest.raises(ValueError, match="unique"):
        SensitivitySurface(
            surface_id="surface-negative",
            axes=("signal",),
            responses=(evaluated, evaluated),
            assumptions=("bounded",),
            evidence=(_evidence(),),
        )


def test_request_duplicate_scenarios_and_operation_entrypoint() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["scenarios"] = [payload["scenarios"][0], payload["scenarios"][0]]
    with pytest.raises(ValueError, match="unique"):
        TypeAdapter(SimulateBiomarkerPanelPerturbationRequest).validate_python(
            payload, strict=False
        )
    distinct = request.scenarios[0].model_copy(update={"scenario_id": "scenario-2"})
    too_many = request.model_copy(update={"scenarios": (request.scenarios[0], distinct)})
    too_many_payload = too_many.model_dump(mode="json")
    too_many_payload["policy"]["maximum_scenarios"] = 1
    with pytest.raises(ValueError, match="scenario limit"):
        TypeAdapter(SimulateBiomarkerPanelPerturbationRequest).validate_python(
            too_many_payload, strict=False
        )
    result = simulate_biomarker_panel_perturbation(request)
    assert result.status.value == "simulated"


def test_result_closure_rejects_wrong_request_and_status_shapes() -> None:
    request = _request()
    result = simulate_biomarker_panel_perturbation(request)
    payload = result.model_dump(mode="json")
    payload["request_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="request digest"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)
    simulated_missing = result.model_dump(mode="json")
    simulated_missing["sensitivity_surface"] = None
    simulated_missing["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="supported sensitivity"):
        type(result).model_validate_json(canonical_json_bytes(simulated_missing), strict=True)
    abstained_with_surface = result.model_dump(mode="json")
    abstained_with_surface["status"] = "abstained"
    abstained_with_surface["abstention_reason"] = "review"
    abstained_with_surface["support_decision"]["status"] = "review_required"
    abstained_with_surface["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="safe status"):
        type(result).model_validate_json(canonical_json_bytes(abstained_with_surface), strict=True)


def test_perturbed_value_outside_envelope_abstains() -> None:
    result = M1206Service().execute(_request(value=0.95))
    assert result.sensitivity_surface is None
