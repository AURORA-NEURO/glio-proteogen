"""Adversarial M14-02 contract closure and replay-path tests."""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest

import glio_proteogen.contracts.m14_02.canonical as canonical_module
import glio_proteogen.modules.c14_microenvironment.m14_02_context_subtype_stratifier.engine as engine_module
from glio_proteogen.contracts.m14_02 import (
    ApplicableMechanism,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    ContextStratificationStatus,
    MechanismApplicability,
    ProteinSubtypeContextProfile,
    ProteinSubtypeContextStratificationResult,
    StratifierPolicy,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c14_microenvironment.m14_02_context_subtype_stratifier import (
    M1402ContextStratifier,
    M1402InferenceError,
    M1402ReplayVerificationError,
    stratify_protein_subtype_context,
)
from tests.modules.c14_microenvironment.test_m14_02_engine import _artifact, _request


def test_canonical_dict_projection_and_observation_policy_closure() -> None:
    assert canonical_module.canonical_request_digest({"request": "dict"}).startswith("sha256:")
    request = _request().model_dump(mode="python")
    request["policy"]["required_dimensions"] = (
        ContextDimension.SUBTYPE,
        ContextDimension.SUBTYPE,
    )
    with pytest.raises(ValueError, match="dimensions"):
        StratifierPolicy.model_validate(request["policy"], strict=True)
    with pytest.raises(ValueError, match="normalized"):
        ContextObservation(
            observation_id="observation.unresolved",
            dimension=ContextDimension.SUBTYPE,
            value="unknown",
            normalized_value="should-not-exist",
            status=ContextObservationStatus.UNRESOLVED,
            source_artifact=_artifact("unresolved"),
        )
    with pytest.raises(ValueError, match="requires evidence"):
        ContextObservation(
            observation_id="observation.supported",
            dimension=ContextDimension.SUBTYPE,
            value="candidate",
            status=ContextObservationStatus.SUPPORTED,
            source_artifact=_artifact("supported"),
        )
    with pytest.raises(ValueError, match="requires evidence"):
        ApplicableMechanism(
            mechanism_id="mechanism.applicable",
            label="Applicable",
            applicability=MechanismApplicability.APPLICABLE,
            rationale="Missing evidence.",
        )


def test_profile_and_result_ids_evidence_and_state_closure() -> None:
    result = M1402ContextStratifier().infer(_request())
    assert result.context_profile is not None
    profile = result.context_profile
    with pytest.raises(ValueError, match="observation ids"):
        ProteinSubtypeContextProfile.model_validate(
            profile.model_copy(
                update={"observations": (*profile.observations, profile.observations[0])}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="unresolved"):
        ProteinSubtypeContextProfile.model_validate(
            profile.model_copy(
                update={
                    "unresolved_dimensions": (ContextDimension.SUBTYPE, ContextDimension.SUBTYPE)
                }
            ),
            strict=True,
        )

    payload = result.model_dump(mode="python")
    payload["request_digest"] = sha256_digest("wrong")
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="request digest"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["result_id"] = "result.bad"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="identifier"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["applicable_mechanisms"] = (
        *result.applicable_mechanisms,
        result.applicable_mechanisms[0],
    )
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="mechanism ids"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["findings"] = (*result.findings, result.findings[0])
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="finding ids"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["evidence"] = ()
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="every result"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["evidence"] = (result.evidence[0].model_copy(update={"role": "counter_evidence"}),)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="every result"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["human_review_required"] = True
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="stratified result"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["status"] = ContextStratificationStatus.ABSTAINED
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="abstained result"):
        ProteinSubtypeContextStratificationResult.model_validate(payload, strict=True)


def test_preflight_mapping_failures_are_sanitized() -> None:
    engine = M1402ContextStratifier()
    with pytest.raises(ValueError, match="controls"):
        engine_module.preflight_context_authorization({})
    with pytest.raises(ValueError, match="controls"):
        engine_module.preflight_context_authorization({"context": {}})
    with pytest.raises(ValueError, match="controls"):
        engine_module.preflight_context_authorization({"context": {"references": None}})
    with pytest.raises(ValueError, match="controls"):
        engine.infer({"context": {"references": {}}})

    class Explosive(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError(key)

        def __iter__(self) -> Iterator[str]:
            return iter(("context",))

        def __len__(self) -> int:
            return 1

        def get(self, key: str, _default: object = None) -> object:
            raise RuntimeError(key)

    with pytest.raises(ValueError, match="controls"):
        engine_module.preflight_context_authorization(Explosive())


def test_engine_validation_and_replay_exception_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1402ContextStratifier()
    result = engine.infer(_request())
    request_dict = _request().model_dump(mode="json")
    request_dict["observations"] = ()
    with pytest.raises(M1402InferenceError):
        engine.infer(request_dict)

    original_adapter = engine_module._RESULT_ADAPTER

    class RejectingAdapter:
        def validate_python(self, _value: object, *, strict: bool) -> object:
            del strict
            raise ValueError("reject")

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", RejectingAdapter())
    with pytest.raises(M1402ReplayVerificationError):
        engine.verify(result)

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", original_adapter)
    original_infer = engine.infer
    monkeypatch.setattr(
        engine, "infer", lambda _request: (_ for _ in ()).throw(ValueError("replay"))
    )
    with pytest.raises(M1402ReplayVerificationError):
        engine.verify(result)
    monkeypatch.setattr(engine, "infer", original_infer)
    other = engine.infer(_request("state_space"))
    monkeypatch.setattr(engine, "infer", lambda _request: other)
    with pytest.raises(M1402ReplayVerificationError):
        engine.verify(result)
    assert (
        stratify_protein_subtype_context(_request()).status
        is ContextStratificationStatus.STRATIFIED
    )
