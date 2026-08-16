"""Substantive negative-path coverage for the provisional M05-06 boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from evals.m05_06.run import build_scenario

from glio_proteogen.contracts.m05_05 import (
    PtmLocalizationArtifactPosteriorState,
)
from glio_proteogen.contracts.m05_06 import (
    M0506_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationArtifactAction,
    PtmLocalizationArtifactEvaluationState,
    PtmLocalizationArtifactTargetReceipt,
    PtmLocalizationArtifactTargetState,
    PtmLocalizationHarmonizationFinding,
    PtmLocalizationHarmonizationFindingAction,
    PtmLocalizationHarmonizationFindingCode,
    PtmLocalizationSupportLevelShift,
    PtmLocalizationSupportObservationState,
    PtmLocalizationSupportShiftState,
)
from glio_proteogen.contracts.m05_06.canonical import (
    analysis_digest,
    artifact_receipt_digest,
    computation_receipt_digest,
    configuration_digest,
    manifest_digest,
    normalized_analysis,
    normalized_artifact_receipt,
    normalized_computation_receipt,
    normalized_manifest,
    normalized_policy,
    normalized_result_payload,
    normalized_support_ledger,
    policy_digest,
    support_ledger_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Plugin,
    M0506Service,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.engine import (
    M0506PtmLocalizationHarmonizationEngine,
    PtmLocalizationHarmonizationAuthorizationError,
    _target_projection,
    _validate_json_request,
    artifact_harmonization_receipt,
    preflight_ptm_localization_harmonization_authorization,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.plugin import (
    _TOKEN_SEAL,
    ValidatedM0506Request,
)


@pytest.fixture(scope="module")
def clear_scenario() -> Any:
    return build_scenario("clear")


def _validate(model_type: Any, model: Any, **changes: Any) -> Any:
    payload = model.model_dump(mode="json")
    payload.update(changes)
    return model_type.model_validate(payload, strict=True)


def test_canonical_helpers_cover_nested_collections_and_digest_projections() -> None:
    document = {"receipt_digest": "sha256:" + ("0" * 64), "items": [1, {"ok": True}]}
    assert normalized_artifact_receipt(document) == document
    assert normalized_support_ledger(document) == document
    assert normalized_analysis(document) == document
    assert normalized_manifest(document) == document
    assert normalized_computation_receipt(document) == document
    assert normalized_result_payload(document) == document
    assert normalized_policy(document) == document
    assert artifact_receipt_digest(document).startswith("sha256:")
    assert support_ledger_digest(document).startswith("sha256:")
    assert analysis_digest(document).startswith("sha256:")
    assert manifest_digest(document).startswith("sha256:")
    assert computation_receipt_digest(document).startswith("sha256:")
    assert policy_digest(document).startswith("sha256:")
    with pytest.raises(TypeError, match="unsupported canonical value"):
        normalized_policy(object())  # type: ignore[arg-type]


def test_authorization_preflight_fails_closed_for_exploding_mapping() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, _default: object = None) -> object:
            raise RuntimeError(key)

    with pytest.raises(PtmLocalizationHarmonizationAuthorizationError):
        preflight_ptm_localization_harmonization_authorization(ExplodingMapping())


def test_failed_mapping_is_sanitized_before_support_traversal(clear_scenario: Any) -> None:
    quarantined = build_scenario("quarantined")
    forged = quarantined.request.model_dump(mode="python")
    forged["support_ledger"] = clear_scenario.request.support_ledger.model_dump(mode="python")
    result = M0506PtmLocalizationHarmonizationEngine().harmonize(forged)
    assert result.disposition.value == "quarantined"
    assert result.analysis is None


def _projection_case(
    clear_scenario: Any,
    *,
    state: str = "clear",
    observation: str = "observed",
    flagged: bool = False,
    excluded: bool = False,
) -> SimpleNamespace:
    source = clear_scenario.request.artifact_result
    target_id = source.artifact_posteriors[0].target_id
    unit_kind = source.artifact_posteriors[0].unit_kind
    posteriors = tuple(
        SimpleNamespace(
            target_id=target_id,
            unit_kind=unit_kind,
            state=state,
            observation_state=observation,
            posterior_digest=sha256_digest({"posterior": index}),
        )
        for index in range(7)
    )
    flags = (
        SimpleNamespace(target_id=target_id, flag_id="flag." + ("1" * 64)),
    ) if flagged else ()
    exclusions = (SimpleNamespace(target_id=target_id),) if excluded else ()
    return SimpleNamespace(
        artifact_posteriors=posteriors,
        contamination_flags=flags,
        exclusion_mask=exclusions,
    )


def test_target_projection_covers_excluded_review_indeterminate_and_clear() -> None:
    scenario = build_scenario("clear")
    excluded = _target_projection(
        _projection_case(scenario, state=PtmLocalizationArtifactPosteriorState.DETECTED.value)
    )[0]
    reviewed = _target_projection(
        _projection_case(scenario, state=PtmLocalizationArtifactPosteriorState.SUSPECTED.value)
    )[0]
    flagged = _target_projection(_projection_case(scenario, flagged=True))[0]
    indeterminate = _target_projection(
        _projection_case(
            scenario,
            state=PtmLocalizationArtifactPosteriorState.CLEAR.value,
            observation="missing",
        )
    )[0]
    clear = _target_projection(_projection_case(scenario))[0]
    assert excluded.target_state is PtmLocalizationArtifactTargetState.EXCLUDED
    assert reviewed.target_state is PtmLocalizationArtifactTargetState.REVIEW
    assert flagged.target_state is PtmLocalizationArtifactTargetState.REVIEW
    assert indeterminate.target_state is PtmLocalizationArtifactTargetState.INDETERMINATE
    assert clear.target_state is PtmLocalizationArtifactTargetState.CLEAR
    with pytest.raises(ValueError, match="all seven"):
        _target_projection(
            SimpleNamespace(
                artifact_posteriors=_projection_case(scenario).artifact_posteriors[:-1],
                contamination_flags=(),
                exclusion_mask=(),
            )
        )


def test_artifact_receipt_rejects_missing_complete_upstream(clear_scenario: Any) -> None:
    source = clear_scenario.request.artifact_result
    request = SimpleNamespace(
        quality_result_digest=source.request.quality_result_digest,
        identity_resolution_digest=source.request.identity_resolution_digest,
        raw_input_receipt_digest=source.request.raw_input_receipt_digest,
        raw_input_result=None,
    )
    result = SimpleNamespace(
        artifact_posteriors=source.artifact_posteriors,
        contamination_flags=source.contamination_flags,
        exclusion_mask=source.exclusion_mask,
        request=request,
        receipt=None,
        disposition=source.disposition,
        result_id=source.result_id,
        result_version=source.result_version,
        result_digest=source.result_digest,
        request_digest=source.request_digest,
        support=source.support,
        human_review_required=source.human_review_required,
        completed_at=source.completed_at,
    )
    with pytest.raises(ValueError, match="complete receipt"):
        artifact_harmonization_receipt(result)


def test_json_request_size_is_rejected_before_authorization() -> None:
    with pytest.raises(ValueError, match="byte limit"):
        _validate_json_request({}, b"x" * (M0506_MAX_CANONICAL_REQUEST_BYTES + 1))


def test_engine_rejects_stale_receipt_and_abstains_for_missing_profile_or_ledger(
    clear_scenario: Any,
) -> None:
    request = clear_scenario.request
    stale_receipt = request.artifact_receipt.model_copy(
        update={"artifact_result_digest": "sha256:" + ("0" * 64)}
    )
    with pytest.raises(ValueError, match="exact full"):
        M0506PtmLocalizationHarmonizationEngine().harmonize_validated(
            request.model_copy(update={"artifact_receipt": stale_receipt})
        )
    wrong_profile = request.policy.profiles[0].model_copy(
        update={"approved_artifact_contract_versions": ("9.9.9",)}
    )
    no_profile = request.policy.model_copy(update={"profiles": (wrong_profile,)})
    approved = request.context.references.approved_configuration
    approved = approved.model_copy(
        update={
            "evidence": approved.evidence.model_copy(
                update={"digest": configuration_digest(no_profile)}
            )
        }
    )
    references = request.context.references.model_copy(
        update={"approved_configuration": approved}
    )
    context = request.context.model_copy(update={"references": references})
    profile_result = M0506PtmLocalizationHarmonizationEngine().harmonize_validated(
        request.model_copy(update={"policy": no_profile, "context": context})
    )
    assert profile_result.disposition.value == "abstained"
    with pytest.raises(ValueError, match="requires an exactly bound support ledger"):
        M0506PtmLocalizationHarmonizationEngine().harmonize_validated(
            request.model_copy(update={"support_ledger": None})
        )


def test_plugin_rejects_invalid_typed_token_and_post_validation_mutation(
    clear_scenario: Any,
) -> None:
    plugin = M0506Plugin(M0506Service())
    invalid = ValidatedM0506Request(request=object(), _seal=_TOKEN_SEAL)
    with pytest.raises(TypeError):
        plugin.run(invalid)
    token = plugin.validate(clear_scenario.request)
    object.__setattr__(
        token,
        "request",
        clear_scenario.request.model_copy(
            update={"supersedes_result_digest": "sha256:" + ("1" * 64)}
        ),
    )
    with pytest.raises(TypeError):
        plugin.run(token)


def test_target_projection_contract_rejects_duplicate_flags_action_and_digest(
    clear_scenario: Any,
) -> None:
    target = clear_scenario.request.artifact_receipt.targets[0]
    with pytest.raises(ValueError, match="posterior digests"):
        PtmLocalizationArtifactTargetReceipt.posterior_digests_are_canonical(
            (target.posterior_digests[0],) * 7
        )
    with pytest.raises(ValueError, match="opaque identifiers"):
        PtmLocalizationArtifactTargetReceipt.flags_are_opaque(("bad",))
    with pytest.raises(ValueError, match="contradicts"):
        target.model_copy(
            update={"action": PtmLocalizationArtifactAction.EXCLUDE}
        ).projection_is_closed()
    with pytest.raises(ValueError, match="binding digest"):
        target.model_copy(
            update={"posterior_binding_digest": "sha256:" + ("0" * 64)}
        ).projection_is_closed()
    with pytest.raises(ValueError, match="cannot carry"):
        target.model_copy(
            update={"contamination_flag_ids": ("flag." + ("1" * 64),)}
        ).projection_is_closed()


def test_receipt_contract_rejects_stale_counts_bindings_and_abi(clear_scenario: Any) -> None:
    receipt = clear_scenario.request.artifact_receipt
    bad = "sha256:" + ("0" * 64)
    with pytest.raises(ValueError, match="target count"):
        receipt.model_copy(update={"target_count": 0}).receipt_is_closed()
    with pytest.raises(ValueError, match="evaluation state"):
        receipt.model_copy(
            update={"evaluation_state": PtmLocalizationArtifactEvaluationState.NOT_EVALUABLE}
        ).receipt_is_closed()
    with pytest.raises(ValueError, match="target binding"):
        receipt.model_copy(update={"target_binding_digest": bad}).receipt_is_closed()
    reference = receipt.artifact_reference.model_copy(update={"version": "0.0.0"})
    with pytest.raises(ValueError, match="ABI"):
        receipt.model_copy(update={"artifact_reference": reference}).receipt_is_closed()
    with pytest.raises(ValueError, match="does not bind"):
        receipt.model_copy(update={"artifact_result_digest": bad}).receipt_is_closed()
    with pytest.raises(ValueError, match="digest is stale"):
        receipt.model_copy(update={"receipt_digest": bad}).receipt_is_closed()


def test_observation_contract_rejects_binding_factor_and_missingness_errors(
    clear_scenario: Any,
) -> None:
    observation = clear_scenario.request.support_ledger.observations[0]
    bad = "sha256:" + ("0" * 64)
    with pytest.raises(ValueError, match="posterior binding"):
        observation.model_copy(update={"posterior_binding_digest": bad}).observation_is_closed()
    factor_models = observation.factor_levels
    factor_models = (factor_models[0],) * len(factor_models)
    with pytest.raises(ValueError, match="all eight"):
        observation.model_copy(update={"factor_levels": factor_models}).observation_is_closed()
    with pytest.raises(ValueError, match="state/action"):
        observation.model_copy(
            update={"artifact_action": PtmLocalizationArtifactAction.EXCLUDE}
        ).observation_is_closed()
    with pytest.raises(ValueError, match="exactly one"):
        observation.model_copy(update={"support_coordinate_ppm": None}).observation_is_closed()
    censored = observation.model_copy()
    object.__setattr__(censored, "state", PtmLocalizationSupportObservationState.CENSORED)
    object.__setattr__(censored, "support_coordinate_ppm", None)
    with pytest.raises(ValueError, match="upper bound"):
        censored.observation_is_closed()
    missing = observation.model_copy(update={"censoring_upper_bound_ppm": 1})
    object.__setattr__(missing, "state", PtmLocalizationSupportObservationState.MISSING)
    with pytest.raises(ValueError, match="numeric coordinates"):
        missing.observation_is_closed()


def test_ledger_stage_profile_shift_and_finding_contracts_reject_invalid_shapes(
    clear_scenario: Any,
) -> None:
    ledger = clear_scenario.request.support_ledger
    observations = (ledger.observations[0], ledger.observations[0])
    with pytest.raises(ValueError, match="unique target"):
        ledger.model_copy(update={"observations": observations}).ledger_is_closed()

    profile = clear_scenario.request.policy.profiles[0]
    stages = list(profile.stages)
    stages[0] = stages[0].model_copy(update={"ordinal": stages[1].ordinal})
    with pytest.raises(ValueError, match="ordinals"):
        profile.model_copy(update={"stages": tuple(stages)}).profile_is_closed()
    stages = list(profile.stages)
    stages[0] = stages[0].model_copy(update={"factor": stages[1].factor})
    with pytest.raises(ValueError, match="every technical factor"):
        profile.model_copy(update={"stages": tuple(stages)}).profile_is_closed()

    stage = profile.stages[0]
    with pytest.raises(ValueError, match="disjoint"):
        stage.model_copy(
            update={
                "estimation_anchor_ids": (stage.reference_level_id,),
                "validation_anchor_ids": (stage.reference_level_id,),
            }
        ).stage_is_closed()

    shift = PtmLocalizationSupportLevelShift(
        stage_id=stage.stage_id,
        ordinal=stage.ordinal,
        factor=stage.factor,
        level_id=stage.reference_level_id,
        state=PtmLocalizationSupportShiftState.ESTIMATED,
        estimated_shift_ppm=1,
        applied_shift_ppm=1,
        estimation_pair_count=1,
        validation_pair_count=1,
    )
    with pytest.raises(ValueError, match="cannot carry numbers"):
        shift.model_copy(
            update={"state": PtmLocalizationSupportShiftState.NOT_EVALUABLE}
        ).shift_shape_is_closed()
    with pytest.raises(ValueError, match="require an estimate"):
        shift.model_copy(update={"estimated_shift_ppm": None}).shift_shape_is_closed()
    finding = PtmLocalizationHarmonizationFinding.model_construct(
        finding_id="evidence." + ("0" * 64),
        code=PtmLocalizationHarmonizationFindingCode.UPSTREAM_ABSTAINED,
        action=PtmLocalizationHarmonizationFindingAction.QUARANTINE,
        message="invalid",
    )
    with pytest.raises(ValueError, match="action contradicts"):
        finding.finding_is_closed()
