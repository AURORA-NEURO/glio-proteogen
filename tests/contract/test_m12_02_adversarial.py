"""Adversarial contract, control, replay, and safe-failure coverage for M12-02."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m12_02 import (
    ApplicableMechanism,
    BiomarkerPanelContextStratificationResult,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    ContextProfile,
    ContextStratifierPolicy,
    MechanismApplicability,
)
from glio_proteogen.contracts.m12_02.canonical import (
    canonical_request_digest,
    normalized_request,
    normalized_result_payload,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c12_driver_to_protein_consequence import (
    m12_02_context_subtype_stratifier as m1202_runtime,
)
from tests.contract.test_m12_02_contract import _artifact, _observation, _request

_DIGEST = "sha256:" + ("c" * 64)
_MAX_EVIDENCE = 64
M1202ContextAuthorizationError = m1202_runtime.M1202ContextAuthorizationError
M1202ContextEngine = m1202_runtime.M1202ContextEngine
M1202ReplayVerificationError = m1202_runtime.M1202ReplayVerificationError
preflight_context_authorization = m1202_runtime.preflight_context_authorization


def test_contract_rejects_unresolved_normalized_value_duplicate_dimensions_and_empty_evidence() -> (
    None
):
    unresolved_data = _observation(
        ContextDimension.SUBTYPE,
        "unknown",
        201,
    ).model_dump(mode="python")
    unresolved_data["status"] = ContextObservationStatus.UNRESOLVED
    with pytest.raises(ValueError, match="unresolved context observation"):
        ContextObservation.model_validate(unresolved_data, strict=True)
    with pytest.raises(ValueError, match="required context dimensions"):
        ContextStratifierPolicy(
            required_dimensions=(ContextDimension.SUBTYPE, ContextDimension.SUBTYPE),
            configuration=_request().policy.configuration,
        )
    with pytest.raises(ValueError, match="applicable mechanism requires evidence"):
        ApplicableMechanism(
            mechanism_id="mechanism.applicable",
            label="Applicable",
            applicability=MechanismApplicability.APPLICABLE,
            rationale="Missing evidence must fail closed.",
        )


def test_profile_and_request_duplicate_ids_fail_closed() -> None:
    base = _request()
    with pytest.raises(ValueError, match="request context observation ids"):
        type(base)(
            request_id=base.request_id,
            context=base.context,
            driver_consequence_result=base.driver_consequence_result,
            policy=base.policy,
            observations=(base.observations[0], base.observations[0]),
            source_artifacts=base.source_artifacts,
        )
    with pytest.raises(ValueError, match="context observation ids"):
        ContextProfile(
            profile_id="profile.duplicate",
            version="1.0.0",
            observations=(base.observations[0], base.observations[0]),
            evidence=(),
        )
    with pytest.raises(ValueError, match="unresolved context dimensions"):
        ContextProfile(
            profile_id="profile.duplicate-dimensions",
            version="1.0.0",
            observations=(base.observations[0],),
            unresolved_dimensions=(ContextDimension.SUBTYPE, ContextDimension.SUBTYPE),
            evidence=(),
        )


def test_result_closure_rejects_each_tampered_envelope_field() -> None:
    engine = M1202ContextEngine()
    result = engine.stratify(_request())
    payload = result.model_dump(mode="python")
    mutations: tuple[tuple[str, object], ...] = (
        ("request_digest", _DIGEST),
        ("result_id", "result.tampered"),
        ("evidence", []),
        (
            "evidence",
            tuple(item.model_copy(update={"role": "counter_evidence"}) for item in result.evidence),
        ),
        ("human_review_required", True),
        ("result_digest", _DIGEST),
    )
    for field, value in mutations:
        tampered = dict(payload)
        tampered[field] = value
        with pytest.raises(ValidationError):
            BiomarkerPanelContextStratificationResult.model_validate(tampered, strict=True)

    abstained = engine.stratify(
        _request(
            tuple(
                item
                for item in _request().observations
                if item.dimension is not ContextDimension.PLATFORM
            )
        )
    )
    abstained_payload = abstained.model_dump(mode="python")
    abstained_payload["human_review_required"] = False
    with pytest.raises(ValidationError, match="abstention requires human review"):
        BiomarkerPanelContextStratificationResult.model_validate(abstained_payload, strict=True)

    no_profile = dict(payload)
    no_profile["context_profile"] = None
    with pytest.raises(ValidationError, match="stratified result requires"):
        BiomarkerPanelContextStratificationResult.model_validate(no_profile, strict=True)

    profile_mismatch = dict(payload)
    profile = dict(profile_mismatch["context_profile"])
    profile["observations"] = (result.request.observations[0],)
    profile_mismatch["context_profile"] = profile
    with pytest.raises(ValidationError, match="preserve every request observation"):
        BiomarkerPanelContextStratificationResult.model_validate(profile_mismatch, strict=True)

    unsafe_abstention = dict(abstained.model_dump(mode="python"))
    unsafe_abstention["support_decision"] = abstained.support_decision.model_copy(
        update={"status": SupportStatus.SUPPORTED}
    )
    with pytest.raises(ValidationError, match="abstained result requires"):
        BiomarkerPanelContextStratificationResult.model_validate(unsafe_abstention, strict=True)


def test_replay_without_recompute_invalid_input_and_forced_mismatch() -> None:
    engine = M1202ContextEngine()
    result = engine.stratify(_request())
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1202ReplayVerificationError):
        engine.verify(object())
    with (
        patch.object(M1202ContextEngine, "stratify", return_value=object()),
        pytest.raises(M1202ReplayVerificationError),
    ):
        engine.verify(result)


def test_hostile_controls_and_duplicate_artifacts_fail_closed_or_bound_evidence() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(M1202ContextAuthorizationError):
        preflight_context_authorization(Hostile())

    base = _request()
    sources = (_artifact("source.extra.duplicate"),) * 2 + tuple(
        _artifact(f"source.extra.{index}") for index in range(64)
    )
    sources = sources[:_MAX_EVIDENCE]
    result = M1202ContextEngine().stratify(base.model_copy(update={"source_artifacts": sources}))
    assert len(result.evidence) == _MAX_EVIDENCE


def test_canonical_dict_projections_and_non_supported_mechanisms() -> None:
    request = _request()
    result = M1202ContextEngine().stratify(request)
    assert normalized_request(request) == request.model_dump(mode="json")
    assert normalized_request(request.model_dump(mode="json")) == request.model_dump(mode="json")
    assert canonical_request_digest(request).startswith("sha256:")
    assert "result_digest" not in normalized_result_payload(result)
    assert result_payload_digest(result) == result.result_digest
    assert m1202_runtime.engine._mechanisms(
        (request.observations[0].model_copy(update={"status": ContextObservationStatus.LIMITED}),)
    )
