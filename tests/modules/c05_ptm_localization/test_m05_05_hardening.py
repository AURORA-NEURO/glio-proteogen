"""Adversarial closure for the M05-05 strict boundary and replay firewall."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from evals.m05_05.run import build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m05_05 import (
    PtmLocalizationArtifactDisposition,
    PtmLocalizationArtifactEvidenceLedger,
    PtmLocalizationArtifactPosteriorState,
)
from glio_proteogen.contracts.m05_05.canonical import (
    canonical_request_digest,
    contamination_flag_digest,
    event_digest,
    evidence_ledger_digest,
    posterior_digest,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    M0505Plugin,
    M0505Service,
    PtmLocalizationArtifactAuthorizationError,
    PtmLocalizationArtifactInputError,
    detect_ptm_localization_artifacts,
)
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection.engine import (
    _built_in_sequence_length,
    _matching_profile,
    _member,
    _plain_value,
    _state_text,
    _validate_json_request,
    _validate_ledger_shape_before_copy,
    _validate_policy_shape_before_copy,
)

_TWO = 2


class _ExplodingMapping:
    """A hostile mapping that must never be traversed by the request firewall."""

    accesses = 0

    def __getitem__(self, _key: object) -> object:
        type(self).accesses += 1
        raise AssertionError


def test_non_builtin_mapping_is_rejected_without_key_access() -> None:
    _ExplodingMapping.accesses = 0

    with pytest.raises(
        (
            PtmLocalizationArtifactAuthorizationError,
            PtmLocalizationArtifactInputError,
            TypeError,
            ValueError,
        )
    ):
        detect_ptm_localization_artifacts(cast("Any", _ExplodingMapping()))

    assert _ExplodingMapping.accesses == 0


def test_unknown_outer_member_is_rejected_before_execution() -> None:
    request = build_scenario("clear").request
    payload = request.model_dump(mode="python", exclude_none=False)
    payload["unlocked_output"] = {"protein": "forbidden"}

    with pytest.raises((PtmLocalizationArtifactInputError, TypeError, ValueError)):
        M0505Service.validate_request(payload)


def test_serialized_duplicate_key_is_rejected_before_model_validation() -> None:
    request = build_scenario("clear").request
    serialized = canonical_json_bytes(request).decode("utf-8")
    duplicate = serialized[:-1] + ',"context":null}'
    plugin = M0505Plugin(M0505Service())

    with pytest.raises((TypeError, ValueError)):
        plugin.validate(duplicate)


def test_serialized_unknown_nested_member_is_rejected() -> None:
    request = build_scenario("clear").request
    payload = request.model_dump(mode="json", exclude_none=False)
    context = payload["context"]
    assert isinstance(context, dict)
    context["identity_inference"] = True
    serialized = json.dumps(payload, separators=(",", ":"))

    with pytest.raises((PtmLocalizationArtifactInputError, TypeError, ValueError)):
        M0505Plugin(M0505Service()).validate(serialized)


def test_nested_raw_digest_tamper_is_not_reflected_in_result() -> None:
    request = build_scenario("clear").request
    raw_result = request.raw_input_result.model_copy(
        update={"request_digest": "sha256:" + ("f" * 64)}
    )
    candidate = request.model_copy(update={"raw_input_result": raw_result})

    with pytest.raises(PtmLocalizationArtifactInputError):
        detect_ptm_localization_artifacts(candidate)


def test_quality_binding_tamper_is_rejected_before_ledger_traversal() -> None:
    request = build_scenario("clear").request
    candidate = request.model_copy(update={"quality_result_digest": "sha256:" + ("0" * 64)})

    with pytest.raises(PtmLocalizationArtifactInputError):
        detect_ptm_localization_artifacts(candidate)


@pytest.mark.parametrize("case_id", ["missing_required", "unsupported_required"])
def test_non_evaluable_inputs_abstain_without_negative_finding(case_id: str) -> None:
    result = detect_ptm_localization_artifacts(build_scenario(case_id).request)

    assert result.disposition is PtmLocalizationArtifactDisposition.ABSTAINED
    assert result.contamination_flags == ()
    assert result.exclusion_mask == ()
    assert all(item.posterior_ppm in (0, None) for item in result.artifact_posteriors)


def test_plugin_token_cannot_be_forged_by_copying_request() -> None:
    request = build_scenario("clear").request
    plugin = M0505Plugin(M0505Service())
    token = plugin.validate(request)
    forged = type(token)(request=token.request.model_copy(), _seal=token._seal)

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_plain_value_firewall_handles_builtin_and_hostile_containers() -> None:
    assert _plain_value({"a": [1, (2,)]}) == {"a": [1, (2,)]}
    assert _plain_value((1, 2)) == (1, 2)
    assert _built_in_sequence_length([1, 2]) == _TWO
    assert _built_in_sequence_length((1, 2)) == _TWO
    assert _built_in_sequence_length({1, 2}) is None
    assert _state_text("accepted") == "accepted"
    with pytest.raises(TypeError):
        _plain_value({"deep": {"deeper": 1}}, _depth=100)
    with pytest.raises(TypeError):
        _plain_value([1], _budget=[0])


def test_shape_firewalls_cover_policy_ledger_and_profile_mismatch() -> None:
    scenario = build_scenario("clear")
    policy = scenario.request.policy
    ledger = scenario.request.evidence_ledger
    assert ledger is not None
    _validate_policy_shape_before_copy(policy)
    _validate_ledger_shape_before_copy(ledger)
    assert _matching_profile(policy, object(), object()) is None
    assert _member({}, "missing") is not object()
    with pytest.raises(TypeError):
        _validate_policy_shape_before_copy({"profiles": list(range(17))})
    with pytest.raises(TypeError):
        _validate_ledger_shape_before_copy({"events": list(range(449))})


def test_canonical_dict_projections_cover_digest_helpers() -> None:
    scenario = build_scenario("clear")
    request = scenario.request
    result = detect_ptm_localization_artifacts(request)
    assert canonical_request_digest(request.model_dump(mode="json"))
    assert result_payload_digest(result.model_dump(mode="json"))
    assert evidence_ledger_digest(request.evidence_ledger.model_dump(mode="json"))  # type: ignore[union-attr]
    assert posterior_digest(result.artifact_posteriors[0].model_dump(mode="json"))
    assert event_digest(request.evidence_ledger.events[0].model_dump(mode="json"))  # type: ignore[union-attr]
    if result.contamination_flags:
        assert contamination_flag_digest(result.contamination_flags[0].model_dump(mode="json"))
    assert receipt_digest(result.receipt.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("case_id", "field", "value"),
    [
        ("clear", "quality_disposition", "invalid"),
        ("clear", "quality_disposition", "ABSTAINED"),
        ("clear", "evidence_ledger", {"events": []}),
    ],
)
def test_preparation_rejects_invalid_disposition_and_ledger_traversal(
    case_id: str, field: str, value: object
) -> None:
    request = build_scenario(case_id).request
    payload = request.model_dump(mode="python", exclude_none=False)
    payload[field] = value
    with pytest.raises((PtmLocalizationArtifactInputError, TypeError, ValueError)):
        M0505Service.validate_request(payload)


def test_serialized_size_firewall_rejects_oversized_input() -> None:
    scenario = build_scenario("clear")
    payload = canonical_json_bytes(scenario.request)
    with pytest.raises(ValueError, match="M05-05 canonical request exceeds"):
        _validate_json_request(json.loads(payload), payload + (b" " * (5 * 1024 * 1024)))


def _reject_model(model: Any, **updates: object) -> None:
    candidate = model.model_copy(update=updates).model_dump(mode="python", exclude_none=False)
    with pytest.raises(ValidationError):
        type(model).model_validate(candidate, strict=True)


def test_contract_closure_rejects_threshold_profile_policy_and_event_tampering() -> None:
    request = build_scenario("clear").request
    profile = request.policy.profiles[0]
    threshold = profile.thresholds[0]
    ledger = cast("PtmLocalizationArtifactEvidenceLedger", request.evidence_ledger)
    event = ledger.events[0]

    _reject_model(threshold, review_threshold_ppm=800_000)
    _reject_model(
        threshold,
        evidence=threshold.evidence.model_copy(update={"media_type": "application/json"}),
    )
    _reject_model(profile, thresholds=())
    _reject_model(request.policy, profiles=(profile, profile))
    _reject_model(event, supporting_count=11)
    _reject_model(event, observation_state="missing", evaluated_count=10)
    _reject_model(event, observation_state="missing", seeded_critical=True)


def test_contract_closure_rejects_ledger_binding_and_request_replay_tampering() -> None:
    # The locked builder is cached for evaluator determinism; isolate this
    # mutation matrix from prior hostile object.__setattr__ tests.
    request = build_scenario("clear").request.model_copy(deep=True)
    ledger = cast("PtmLocalizationArtifactEvidenceLedger", request.evidence_ledger)
    binding = build_scenario("ledger_binding_only").request.evidence_ledger
    assert binding is not None

    _reject_model(ledger, ledger_digest="sha256:" + ("0" * 64))
    _reject_model(ledger, events=ledger.events[:-1])
    _reject_model(binding, ledger_digest="sha256:" + ("0" * 64))
    _reject_model(request, request_id="request." + ("0" * 64))
    _reject_model(request, quality_result_digest="sha256:" + ("0" * 64))
    _reject_model(request, raw_input_receipt_digest="sha256:" + ("0" * 64))
    _reject_model(
        request,
        context=request.context.model_copy(update={"request_id": "request." + ("0" * 64)}),
    )


def test_contract_closure_rejects_output_nested_digest_and_capability_tampering() -> None:
    result = detect_ptm_localization_artifacts(build_scenario("seeded_critical").request)
    posterior = result.artifact_posteriors[0]
    exclusion = result.exclusion_mask[0]
    finding = result.findings[0]

    _reject_model(posterior, posterior_ppm=None)
    _reject_model(posterior, lower_bound_ppm=1_000_000, upper_bound_ppm=0)
    _reject_model(posterior, state=PtmLocalizationArtifactPosteriorState.INDETERMINATE)
    _reject_model(posterior, posterior_digest="sha256:" + ("0" * 64))
    _reject_model(exclusion, triggering_posterior_digests=(posterior.posterior_digest,) * 2)
    _reject_model(finding, message="forged finding message")
    _reject_model(result.receipt, receipt_digest="sha256:" + ("0" * 64))
    _reject_model(result, result_digest="sha256:" + ("0" * 64))
    _reject_model(result, human_review_required=False)
