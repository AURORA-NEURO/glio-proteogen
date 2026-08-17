"""Adversarial closure for the M05-05 strict boundary and replay firewall."""

from __future__ import annotations

import json
from collections import UserDict
from typing import Any, cast

import pytest
from evals.m05_05.run import build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m05_05 import (
    PtmLocalizationArtifactDetectorClass,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationArtifactEvidenceLedger,
    PtmLocalizationArtifactObservationState,
    PtmLocalizationArtifactPosteriorState,
)
from glio_proteogen.contracts.m05_05.canonical import (
    canonical_request_digest,
    configuration_digest,
    contamination_flag_digest,
    event_digest,
    evidence_ledger_digest,
    normalized_contamination_flag,
    normalized_event,
    normalized_evidence_ledger,
    normalized_exclusion_mask_entry,
    normalized_finding,
    normalized_policy,
    normalized_posterior,
    normalized_profile,
    normalized_receipt,
    normalized_request,
    normalized_result,
    normalized_result_payload,
    normalized_threshold,
    policy_digest,
    posterior_digest,
    profile_digest,
    receipt_digest,
    result_payload_digest,
    threshold_digest,
)
from glio_proteogen.contracts.m05_05.v1 import opaque_ptm_localization_artifact_identifier
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    M0505Plugin,
    M0505Service,
    PtmLocalizationArtifactAuthorizationError,
    PtmLocalizationArtifactInputError,
    detect_ptm_localization_artifacts,
)
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection.engine import (
    _built_in_sequence_length,
    _expected_disposition,
    _expected_findings,
    _expected_posteriors,
    _expected_provenance,
    _ForbiddenEvidenceLedgerError,
    _matching_profile,
    _member,
    _plain_value,
    _prepare_artifact_request_candidate,
    _state_text,
    _validate_json_request,
    _validate_ledger_shape_before_copy,
    _validate_outer_request_shape,
    _validate_policy_shape_before_copy,
    preflight_ptm_localization_artifact_authorization,
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


def test_helper_firewalls_cover_model_and_sequence_branches() -> None:
    request = build_scenario("clear").request
    payload = request.model_dump(mode="python", exclude_none=False)
    _validate_outer_request_shape(request)
    _validate_outer_request_shape(payload)
    assert _member(request, "request_id") == request.request_id
    assert _state_text(PtmLocalizationArtifactDisposition.CLEARED.value) == "cleared"
    plain_request = _plain_value(request)
    assert isinstance(plain_request, dict)
    assert plain_request["request_id"] == request.request_id
    with pytest.raises(TypeError):
        _validate_policy_shape_before_copy({"profiles": [{"thresholds": [None] * 6}]})
    with pytest.raises(TypeError):
        _validate_ledger_shape_before_copy({"events": [{"evidence": [None] * 9}]})
    denied = request.model_dump(mode="python", exclude_none=False)
    denied["context"]["references"]["quality"]["state"] = "denied"
    with pytest.raises(PtmLocalizationArtifactAuthorizationError):
        preflight_ptm_localization_artifact_authorization(denied)


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
    assert normalized_evidence_ledger(request.evidence_ledger) == normalized_evidence_ledger(  # type: ignore[arg-type]
        request.evidence_ledger.model_dump(mode="json")  # type: ignore[union-attr]
    )


def test_canonical_projections_cover_owned_dict_and_model_paths() -> None:
    scenario = build_scenario("contamination_detected")
    request = scenario.request
    result = detect_ptm_localization_artifacts(request)
    profile = request.policy.profiles[0]
    threshold = profile.thresholds[0]
    ledger = cast("PtmLocalizationArtifactEvidenceLedger", request.evidence_ledger)
    event = ledger.events[0]
    posterior = result.artifact_posteriors[0]
    finding = result.findings[0]
    exclusion = result.exclusion_mask[0]
    flag = result.contamination_flags[0]
    values = (
        (normalized_threshold, threshold),
        (normalized_profile, profile),
        (normalized_policy, request.policy),
        (normalized_event, event),
        (normalized_exclusion_mask_entry, exclusion),
        (normalized_posterior, posterior),
        (normalized_contamination_flag, flag),
        (normalized_finding, finding),
        (normalized_receipt, result.receipt),
        (normalized_request, request),
        (normalized_result, result),
        (normalized_result_payload, result),
    )
    for projector, model in values:
        assert projector(model) == projector(model.model_dump(mode="json"))
    assert threshold_digest(threshold) == threshold_digest(threshold.model_dump(mode="json"))
    assert profile_digest(profile) == profile_digest(profile.model_dump(mode="json"))
    assert policy_digest(request.policy) == policy_digest(request.policy.model_dump(mode="json"))


def test_result_replay_rejects_every_derived_region_projection() -> None:
    result = detect_ptm_localization_artifacts(build_scenario("contamination_detected").request)
    posterior = result.artifact_posteriors[0]
    flag = result.contamination_flags[0]
    exclusion = result.exclusion_mask[0]

    for field in ("request_digest", "policy_digest", "configuration_digest", "receipt_digest"):
        _reject_model(result, **{field: "sha256:" + ("0" * 64)})
    _reject_model(result, artifact_posteriors=(posterior, posterior))
    _reject_model(result, contamination_flags=(flag, flag))
    _reject_model(
        result,
        contamination_flags=(flag.model_copy(update={"target_id": "target." + ("f" * 64)}),),
    )
    _reject_model(
        result,
        exclusion_mask=(
            exclusion.model_copy(
                update={"triggering_posterior_digests": ("sha256:" + ("0" * 64),)}
            ),
        ),
    )


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


def _reject_validator(model: Any, validator: str, **updates: object) -> None:
    candidate = model.model_copy(update=updates)
    with pytest.raises((TypeError, ValueError)):
        getattr(candidate, validator)()


def test_direct_validator_and_engine_edges_remain_fail_closed() -> None:  # noqa: PLR0915
    zero = "sha256:" + ("0" * 64)
    request = build_scenario("clear").request.model_copy(deep=True)
    profile = request.policy.profiles[0]
    threshold = profile.thresholds[0]
    event = request.evidence_ledger.events[0]  # type: ignore[union-attr]
    ledger = cast("PtmLocalizationArtifactEvidenceLedger", request.evidence_ledger)

    # Exercise valid opaque namespace return and validator-only branches that
    # strict reconstruction rejects before the after-validator can run.
    assert opaque_ptm_localization_artifact_identifier(request.request_id, "request")
    _reject_validator(profile, "profile_is_closed", thresholds=(threshold,) * 7)
    profile2 = profile.model_copy(update={"profile_id": "profile." + ("1" * 64)})
    _reject_validator(request.policy, "policy_is_closed", profiles=(profile, profile2))
    _reject_validator(
        event,
        "event_is_closed",
        observation_state=PtmLocalizationArtifactObservationState.MISSING,
        evaluated_count=10,
    )
    _reject_validator(
        event,
        "event_is_closed",
        observation_state=PtmLocalizationArtifactObservationState.MISSING,
        seeded_critical=True,
    )
    _reject_validator(ledger, "ledger_is_closed", events=ledger.events[:-1])
    duplicate_class = (
        ledger.events[0],
        ledger.events[1].model_copy(update={"detector_class": ledger.events[0].detector_class}),
        *ledger.events[2:],
    )
    _reject_validator(ledger, "ledger_is_closed", events=duplicate_class)
    missing_class = (
        *ledger.events[:-1],
        ledger.events[-1].model_copy(update={"detector_class": ledger.events[0].detector_class}),
    )
    _reject_validator(ledger, "ledger_is_closed", events=missing_class)

    refs = request.context.references
    denied = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    _reject_validator(
        request,
        "request_is_closed",
        context=request.context.model_copy(
            update={"references": refs.model_copy(update={"consent": denied})}
        ),
    )
    _reject_validator(request, "request_is_closed", raw_input_receipt_digest=zero)
    forged_provenance = refs.provenance.model_copy(
        update={"evidence": refs.provenance.evidence.model_copy(update={"digest": zero})}
    )
    _reject_validator(
        request,
        "request_is_closed",
        context=request.context.model_copy(
            update={"references": refs.model_copy(update={"provenance": forged_provenance})}
        ),
    )
    forged_configuration = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(update={"digest": zero})
        }
    )
    _reject_validator(
        request,
        "request_is_closed",
        context=request.context.model_copy(
            update={
                "references": refs.model_copy(
                    update={"approved_configuration": forged_configuration}
                )
            }
        ),
    )
    forged_raw = request.raw_input_result.model_copy(update={"disposition": "quarantined"})
    _reject_validator(request, "request_is_closed", raw_input_result=forged_raw)
    unsupported_profile = profile.model_copy(
        update={"approved_quality_contract_versions": ("9.9.9",)}
    )
    unsupported_policy = request.policy.model_copy(update={"profiles": (unsupported_profile,)})
    supported_configuration = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(unsupported_policy)}
            )
        }
    )
    _reject_validator(
        request,
        "request_is_closed",
        policy=unsupported_policy,
        context=request.context.model_copy(
            update={
                "references": refs.model_copy(
                    update={"approved_configuration": supported_configuration}
                )
            }
        ),
    )
    _reject_validator(
        request,
        "request_is_closed",
        evidence_ledger=ledger.model_copy(update={"quality_result_digest": zero}),
    )

    missing = detect_ptm_localization_artifacts(build_scenario("missing_required").request)
    _reject_validator(missing.artifact_posteriors[0], "posterior_is_closed", posterior_ppm=1)
    contaminated = detect_ptm_localization_artifacts(
        build_scenario("contamination_detected").request
    )
    flag = contaminated.contamination_flags[0]
    _reject_validator(
        flag,
        "flag_is_closed",
        detector_class=PtmLocalizationArtifactDetectorClass.TECHNICAL_ARTIFACT,
    )
    _reject_validator(
        contaminated,
        "result_is_closed",
        artifact_posteriors=(contaminated.artifact_posteriors[0],) * 2,
    )

    unsupported_request = request.model_copy(update={"policy": unsupported_policy})
    assert _expected_posteriors(unsupported_request) == ()
    assert _expected_findings(unsupported_request, (), ())
    assert _expected_disposition(unsupported_request, ())
    superseding = request.model_copy(update={"supersedes_result_digest": zero})
    assert zero in _expected_provenance(superseding).input_digests

    with pytest.raises(_ForbiddenEvidenceLedgerError):
        _prepare_artifact_request_candidate(
            request.model_dump(mode="python", exclude_none=False)
            | {"quality_disposition": "abstained"}
        )
    with pytest.raises(TypeError):
        _prepare_artifact_request_candidate(
            request.model_dump(mode="python", exclude_none=False)
            | {"policy": {"profiles": list(range(17))}}
        )
    with pytest.raises(TypeError):
        _member({1: "invalid"}, "invalid")
    context = request.context.model_copy(deep=True)
    object.__setattr__(context, "__dict__", {1: "invalid"})
    with pytest.raises(TypeError):
        _member(context, "references")
    assert _state_text(object()) is None
    _validate_policy_shape_before_copy({"profiles": object()})
    with pytest.raises(TypeError):
        _validate_policy_shape_before_copy({"profiles": [{"thresholds": [object()] * 6}]})
    _validate_ledger_shape_before_copy({"events": object()})
    with pytest.raises(TypeError):
        _validate_ledger_shape_before_copy({"events": [{"evidence": [object()] * 9}]})
    with pytest.raises(TypeError):
        _plain_value([object()] * 513)
    with pytest.raises(TypeError):
        _plain_value((object(),) * 513)
    with pytest.raises(TypeError):
        _plain_value(UserDict({"value": 1}))


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
    _reject_model(request, quality_contract_version="9.9.9")
    _reject_model(request, quality_configuration_digest="sha256:" + ("0" * 64))
    _reject_model(request, quality_receipt_digest="sha256:" + ("0" * 64))
    _reject_model(request, identity_resolution_digest="sha256:" + ("0" * 64))
    _reject_model(
        request,
        context=request.context.model_copy(
            update={
                "references": request.context.references.model_copy(
                    update={
                        "quality": request.context.references.quality.model_copy(
                            update={
                                "evidence": request.context.references.quality.evidence.model_copy(
                                    update={"digest": "sha256:" + ("0" * 64)}
                                )
                            }
                        )
                    }
                )
            }
        ),
    )
    _reject_model(
        ledger,
        events=(ledger.events[0].model_copy(update={"sequence": 2}), *ledger.events[1:]),
    )
    _reject_model(
        ledger,
        events=(
            ledger.events[0].model_copy(update={"detector_class": ledger.events[1].detector_class}),
            *ledger.events[1:],
        ),
    )


def test_contract_closure_rejects_output_nested_digest_and_capability_tampering() -> None:
    result = detect_ptm_localization_artifacts(build_scenario("contamination_detected").request)
    posterior = result.artifact_posteriors[0]
    exclusion = result.exclusion_mask[0]
    finding = result.findings[0]
    flag = result.contamination_flags[0]

    _reject_model(posterior, posterior_ppm=None)
    _reject_model(posterior, lower_bound_ppm=1_000_000, upper_bound_ppm=0)
    _reject_model(posterior, state=PtmLocalizationArtifactPosteriorState.INDETERMINATE)
    _reject_model(posterior, posterior_digest="sha256:" + ("0" * 64))
    _reject_model(exclusion, triggering_posterior_digests=(posterior.posterior_digest,) * 2)
    _reject_model(finding, message="forged finding message")
    _reject_model(result.receipt, receipt_digest="sha256:" + ("0" * 64))
    _reject_model(
        result.receipt, event_digests=(), posterior_digests=result.receipt.posterior_digests
    )
    _reject_model(result, result_digest="sha256:" + ("0" * 64))
    _reject_model(result, human_review_required=False)
    _reject_model(
        result,
        contamination_flags=(
            flag.model_copy(
                update={
                    "detector_class": "technical_artifact",
                }
            ),
        ),
    )


def test_safe_failure_receipt_cannot_claim_traversal() -> None:
    result = detect_ptm_localization_artifacts(build_scenario("missing_required").request)
    with pytest.raises(ValidationError):
        type(result.receipt).model_validate(
            result.receipt.model_copy(
                update={
                    "event_digests": ("sha256:" + ("0" * 64),),
                    "posterior_digests": ("sha256:" + ("0" * 64),),
                }
            ).model_dump(mode="python"),
            strict=True,
        )
