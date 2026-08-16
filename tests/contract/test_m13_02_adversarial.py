"""Adversarial closure matrix for M13-02 contracts and replay boundaries."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from glio_proteogen.contracts.m13_02 import (
    ApplicableMechanism,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    ContextStratificationStatus,
    MechanismApplicability,
    ProteotypeContextProfile,
    StratifierPolicy,
    StratifyProteotypeContextRequest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c11_protein_native_subtype.m13_02_context_subtype_stratifier import (
    M1302AuthorizationError,
    M1302Plugin,
    M1302Service,
    compute_proteotype_context,
    engine,
    preflight_context_authorization,
    verify_context_result,
)
from tests.contract.test_m13_02_runtime import _request


def test_contract_rejects_unresolved_normalized_value() -> None:
    request = _request()
    observation = request.observations[0]
    with pytest.raises(ValueError, match="cannot carry normalized value"):
        ContextObservation(
            observation_id=observation.observation_id,
            dimension=observation.dimension,
            value=observation.value,
            normalized_value="unsafe-normalization",
            status=ContextObservationStatus.UNRESOLVED,
            source_artifact=observation.source_artifact,
            evidence=observation.evidence,
        )


def test_contract_rejects_duplicate_policy_profile_request_and_mechanism_ids() -> None:
    request = _request()
    policy = request.policy
    with pytest.raises(ValueError, match="dimensions must be unique"):
        StratifierPolicy(
            required_dimensions=(ContextDimension.SUBTYPE, ContextDimension.SUBTYPE),
            configuration=policy.configuration,
        )
    with pytest.raises(ValueError, match="observation ids must be unique"):
        ProteotypeContextProfile(
            profile_id="profile-duplicate",
            version="1.0.0",
            observations=(request.observations[0], request.observations[0]),
        )
    with pytest.raises(ValueError, match="unresolved context dimensions"):
        ProteotypeContextProfile(
            profile_id="profile-duplicate-dimension",
            version="1.0.0",
            observations=(request.observations[0],),
            unresolved_dimensions=(ContextDimension.SUBTYPE, ContextDimension.SUBTYPE),
        )
    with pytest.raises(ValueError, match="observation ids must be unique"):
        StratifyProteotypeContextRequest(
            request_id=request.request_id,
            context=request.context,
            variant_peptide_result=request.variant_peptide_result,
            policy=request.policy,
            observations=(request.observations[0], request.observations[0]),
            mechanism_candidates=request.mechanism_candidates,
            source_artifacts=request.source_artifacts,
        )
    with pytest.raises(ValueError, match="candidate ids must be unique"):
        StratifyProteotypeContextRequest(
            request_id=request.request_id,
            context=request.context,
            variant_peptide_result=request.variant_peptide_result,
            policy=request.policy,
            observations=request.observations,
            mechanism_candidates=request.mechanism_candidates * 2,
            source_artifacts=request.source_artifacts,
        )


def test_contract_rejects_observation_source_not_declared() -> None:
    request = _request()
    with pytest.raises(ValueError, match="source must be declared"):
        StratifyProteotypeContextRequest(
            request_id=request.request_id,
            context=request.context,
            variant_peptide_result=request.variant_peptide_result,
            policy=request.policy,
            observations=request.observations,
            mechanism_candidates=request.mechanism_candidates,
            source_artifacts=(request.policy.configuration.model_reference,),
        )


def test_result_replay_closure_rejects_request_digest_and_payload_tampering() -> None:
    request = _request()
    result = compute_proteotype_context(request)
    with pytest.raises(ValueError, match="request digest"):
        type(result).model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64}), strict=True
        )
    with pytest.raises(ValueError, match="result digest"):
        type(result).model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64}), strict=True
        )
    mechanism = result.applicable_mechanisms[0]
    with pytest.raises(ValueError, match="mechanism ids"):
        type(result).model_validate(
            result.model_copy(update={"applicable_mechanisms": (mechanism, mechanism)}),
            strict=True,
        )
    abstained_mechanism = ApplicableMechanism(
        mechanism_id="mechanism.abstained",
        label="Abstained route",
        applicability=MechanismApplicability.ABSTAINED,
        rationale="No support.",
    )
    with pytest.raises(ValueError, match="cannot contain abstained"):
        type(result).model_validate(
            result.model_copy(update={"applicable_mechanisms": (abstained_mechanism,)}),
            strict=True,
        )
    with pytest.raises(ValueError, match="requires no profile"):
        type(result).model_validate(
            result.model_copy(
                update={
                    "status": ContextStratificationStatus.ABSTAINED,
                    "support_decision": result.support_decision.model_copy(
                        update={"status": SupportStatus.UNSUPPORTED}
                    ),
                }
            ),
            strict=True,
        )
    assert not verify_context_result({"status": "stratified"})


def test_replay_json_and_hostile_preflight_paths_fail_closed() -> None:
    request = _request()
    serialized = request.model_dump_json()
    assert engine.validate_json_request(serialized).request_id == request.request_id
    plugin = M1302Plugin(M1302Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M13-02"
    assert plugin.validate(request).request.request_id == request.request_id
    with pytest.raises(M1302AuthorizationError):
        preflight_context_authorization({})
    assert engine._member(object(), "context") is None
    assert engine._state_text(42) is None
    assert engine._member(request, "request_id") == request.request_id
    assert engine._state_text(request.context.references.consent.state) == "granted"
    assert engine._plain_value(request)["request_id"] == request.request_id
    assert engine._plain_value(["a", 1]) == ["a", 1]
    assert engine._plain_value(("a", 1)) == ("a", 1)
    with pytest.raises(TypeError, match="built-in JSON"):
        engine._plain_value({1: "invalid"})

    class HostileMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            return key

        def __iter__(self):
            return iter(("request_id",))

        def __len__(self) -> int:
            return 1

    with pytest.raises(TypeError, match="built-in JSON"):
        engine._plain_value(HostileMapping())


def test_unknown_candidate_dimension_is_not_a_negative_finding() -> None:
    request = _request()
    candidate = request.mechanism_candidates[0].model_copy(
        update={"required_dimensions": (ContextDimension.AGE,)}
    )
    result = compute_proteotype_context(
        request.model_copy(update={"mechanism_candidates": (candidate,)})
    )
    assert result.applicable_mechanisms[0].applicability.value == "unknown"
    assert result.applicable_mechanisms[0].evidence


def test_stratifier_direct_and_mechanism_conflict_branches() -> None:
    request = _request()
    assert engine.M1302ContextStratifier().compute(request).status.value == "stratified"
    conflicted = request.observations[0].model_copy(
        update={"status": ContextObservationStatus.CONFLICTED}
    )
    candidate = request.mechanism_candidates[0]
    output = engine._mechanisms(
        request.model_copy(update={"mechanism_candidates": (candidate,)}),
        {ContextDimension.SUBTYPE: (conflicted,)},
    )
    assert output[0].applicability is MechanismApplicability.UNKNOWN


def test_replay_digest_mismatch_and_preflight_exception_are_fail_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    original = engine.canonical_request_digest
    calls = 0

    def mismatch(value):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        digest = original(value)
        return digest if calls == 1 else "sha256:" + "0" * 64

    monkeypatch.setattr(engine, "canonical_request_digest", mismatch)
    with pytest.raises(ValueError, match="replay digest"):
        engine._validate_request(request.model_dump(mode="json"))
    monkeypatch.setattr(
        engine, "_member", lambda *_args: (_ for _ in ()).throw(RuntimeError("hostile"))
    )
    with pytest.raises(engine.M1302AuthorizationError):
        preflight_context_authorization(request)
    assert str(engine._ReplayDigestError())
