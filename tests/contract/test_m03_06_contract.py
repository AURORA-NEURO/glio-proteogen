"""Strict relational contracts for M03-06 fixed-point support harmonization."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from evals.m03_06.run import Scenario, build_scenario
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m03_06 import (
    M0306_CONTRACT_VERSION,
    M0306_FACTOR_COUNT,
    M0306_GATE,
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MAX_FINDINGS,
    M0306_MAX_STAGES,
    M0306_MAX_UNITS,
    M0306_MODULE_ID,
    M0306_OPERATION,
    M0306_OWNER,
    M0306_PARENT,
    M0306_RATE_SCALE,
    M0306_SAFETY_CLASS,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceArtifactAction,
    ProteinInferenceArtifactEvaluationState,
    ProteinInferenceArtifactHarmonizationReceipt,
    ProteinInferenceHarmonizationDiagnosticStatus,
    ProteinInferenceHarmonizationFinding,
    ProteinInferenceHarmonizationFindingAction,
    ProteinInferenceHarmonizationFindingCode,
    ProteinInferenceHarmonizationPolicy,
    ProteinInferenceHarmonizationProfile,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceInvariantDiagnostic,
    ProteinInferenceNormalizationFactor,
    ProteinInferenceNormalizationStage,
    ProteinInferenceSupportInvariant,
    ProteinInferenceSupportInvariantKind,
    ProteinInferenceSupportLedger,
    ProteinInferenceSupportLevelShift,
    ProteinInferenceSupportObservation,
    ProteinInferenceSupportObservationState,
    ProteinInferenceSupportShiftState,
    ProteinInferenceTechnicalEffectDiagnostic,
    artifact_harmonization_receipt,
    canonical_request_digest,
    contract_json_schema,
    finding_for,
    lower_median,
    normalized_request,
    normalized_result,
    result_payload_digest,
    support_ledger_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    harmonize_protein_inference_support,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "profile",
    "stage",
    "artifact-receipt",
    "unit-receipt",
    "support-ledger",
    "observation",
    "invariant",
    "analysis",
    "value",
    "transformation-manifest",
    "finding",
)


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def canonical_request(scenario: Scenario) -> HarmonizeProteinInferenceSupportRequest:
    return scenario.request


@pytest.fixture(scope="module")
def canonical_result(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> ProteinInferenceHarmonizationResult:
    return harmonize_protein_inference_support(canonical_request)


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value.model_dump(mode="python"))  # type: ignore[attr-defined]


def _resigned_ledger(
    request: HarmonizeProteinInferenceSupportRequest,
    **updates: object,
) -> ProteinInferenceSupportLedger:
    ledger = request.support_ledger
    assert ledger is not None
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    payload.update(updates)
    payload["ledger_digest"] = support_ledger_digest(payload)
    return ProteinInferenceSupportLedger.model_validate(payload, strict=True)


def test_public_abi_constants_and_closed_enums_are_exact() -> None:
    assert (
        M0306_MODULE_ID,
        M0306_OPERATION,
        M0306_CONTRACT_VERSION,
        M0306_OWNER,
        M0306_SAFETY_CLASS,
        M0306_GATE,
        M0306_PARENT,
    ) == (
        "GLIO-PROTEOGEN-M03-06",
        "harmonize_protein_inference_support",
        "1.0.0",
        "Platform engineering",
        "S2",
        "G1",
        "complex_activity",
    )
    assert M0306_RATE_SCALE == 10**6
    assert M0306_FACTOR_COUNT == M0306_MAX_STAGES == len(
        ProteinInferenceNormalizationFactor
    )
    assert M0306_MAX_UNITS == 2**9
    assert {item.value for item in ProteinInferenceNormalizationFactor} == {
        "platform",
        "batch",
        "laboratory",
        "build",
        "depth",
        "purity",
        "composition",
        "preanalytic",
    }
    assert {item.value for item in ProteinInferenceSupportObservationState} == {
        "observed",
        "missing",
        "censored",
        "not_applicable",
        "unsupported",
    }
    assert len(ProteinInferenceHarmonizationFindingCode) == M0306_MAX_FINDINGS


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_all_installed_schemas_are_standalone_strict_draft_2020_12(name: str) -> None:
    schema = contract_json_schema(cast("Any", name))
    Draft202012Validator.check_schema(schema)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == (
        f"urn:aurora-neuro:glio-proteogen:{M0306_MODULE_ID}:1.0.0:{name}"
    )
    assert schema["additionalProperties"] is False
    metadata = cast("dict[str, object]", schema["x-glio-contract"])
    assert metadata["moduleId"] == M0306_MODULE_ID
    assert metadata["strict"] is True
    assert metadata["fixedPointScale"] == M0306_RATE_SCALE
    assert metadata["rawPayloadInSchema"] is False
    assert metadata["reparsesRawPayload"] is False
    assert metadata["calibratedProbability"] is False
    if name == "request":
        assert metadata["maxRequestBytes"] == M0306_MAX_CANONICAL_REQUEST_BYTES


def test_genuine_m0305_projection_and_compact_receipt_reconstruct_exactly(
    scenario: Scenario,
) -> None:
    receipt = scenario.request.artifact_receipt

    assert receipt == artifact_harmonization_receipt(scenario.artifact_result)
    assert receipt.evaluation_state is ProteinInferenceArtifactEvaluationState.COMPLETE
    assert receipt.unit_count == len(receipt.units) == len(scenario.unit_ids)
    assert receipt.artifact_result_digest == scenario.artifact_result.result_digest
    assert receipt.artifact_reference.digest == scenario.artifact_result.result_digest
    assert receipt.artifact_reference.media_type == "application/vnd.glio-proteogen.m03-05+json"

    with pytest.raises(ValidationError, match="digest closure"):
        ProteinInferenceArtifactHarmonizationReceipt.model_validate(
            receipt.model_copy(update={"receipt_digest": _ZERO_DIGEST}),
            strict=True,
        )


def test_observation_state_numeric_shapes_are_disjoint_and_strict(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    observation = ledger.observations[0]

    for state, coordinate, bound in (
        (ProteinInferenceSupportObservationState.OBSERVED, 0, None),
        (ProteinInferenceSupportObservationState.CENSORED, None, 0),
        (ProteinInferenceSupportObservationState.MISSING, None, None),
        (ProteinInferenceSupportObservationState.NOT_APPLICABLE, None, None),
        (ProteinInferenceSupportObservationState.UNSUPPORTED, None, None),
    ):
        rebuilt = ProteinInferenceSupportObservation.model_validate(
            observation.model_copy(
                update={
                    "state": state,
                    "support_coordinate_ppm": coordinate,
                    "censoring_upper_bound_ppm": bound,
                }
            ),
            strict=True,
        )
        assert rebuilt.state is state
        assert rebuilt.support_coordinate_ppm == coordinate
        assert rebuilt.censoring_upper_bound_ppm == bound
        assert rebuilt.is_calibrated_probability is False

    with pytest.raises(ValidationError, match="observed support"):
        ProteinInferenceSupportObservation.model_validate(
            observation.model_copy(update={"support_coordinate_ppm": None}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="non-observed support"):
        ProteinInferenceSupportObservation.model_validate(
            observation.model_copy(
                update={"state": ProteinInferenceSupportObservationState.MISSING}
            ),
            strict=True,
        )


def test_observation_requires_all_eight_factors_and_closed_artifact_action(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    observation = ledger.observations[0]

    with pytest.raises(ValidationError, match="every technical factor"):
        ProteinInferenceSupportObservation.model_validate(
            observation.model_copy(
                update={
                    "factor_levels": (
                        *observation.factor_levels[:-1],
                        observation.factor_levels[0],
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="artifact posterior"):
        ProteinInferenceSupportObservation.model_validate(
            observation.model_copy(
                update={"artifact_action": ProteinInferenceArtifactAction.REVIEW}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="evidence digests must be unique"):
        ProteinInferenceSupportObservation.model_validate(
            observation.model_copy(update={"evidence": observation.evidence * 2}),
            strict=True,
        )


def test_support_ledger_closes_unit_projection_invariants_and_digest(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    assert len(ledger.observations) == canonical_request.artifact_receipt.unit_count
    assert {item.kind for item in ledger.invariants} == set(
        ProteinInferenceSupportInvariantKind
    )

    duplicate_kind = ledger.invariants[0].model_copy(
        update={"invariant_id": "invariant." + ("f" * 64)}
    )
    with pytest.raises(ValidationError, match="every protected invariant kind"):
        _resigned_ledger(
            canonical_request,
            invariants=(ledger.invariants[0], duplicate_kind, ledger.invariants[1]),
        )
    unknown = ledger.invariants[0].model_copy(
        update={"left_unit_ids": ("unit." + ("f" * 64),)}
    )
    with pytest.raises(ValidationError, match="unknown unit"):
        _resigned_ledger(
            canonical_request,
            invariants=(unknown, *ledger.invariants[1:]),
        )
    with pytest.raises(ValidationError, match="digest does not match"):
        ProteinInferenceSupportLedger.model_validate(
            ledger.model_copy(update={"ledger_digest": _ZERO_DIGEST}),
            strict=True,
        )


def test_invariant_kind_specific_member_shapes_are_closed(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    rank = next(
        item
        for item in ledger.invariants
        if item.kind is ProteinInferenceSupportInvariantKind.SUPPORT_RANK
    )

    extra_unit = next(
        item.unit_id
        for item in ledger.observations
        if item.unit_id not in {*rank.left_unit_ids, *rank.right_unit_ids}
    )
    with pytest.raises(ValidationError, match="exactly one unit"):
        ProteinInferenceSupportInvariant.model_validate(
            rank.model_copy(update={"left_unit_ids": (*rank.left_unit_ids, extra_unit)}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="unique and disjoint"):
        ProteinInferenceSupportInvariant.model_validate(
            rank.model_copy(update={"right_unit_ids": rank.left_unit_ids}),
            strict=True,
        )


def test_profile_stage_and_policy_match_domains_are_closed(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    policy = canonical_request.policy
    profile = policy.profiles[0]
    assert tuple(item.ordinal for item in profile.stages) == tuple(range(1, 9))
    assert {item.factor for item in profile.stages} == set(ProteinInferenceNormalizationFactor)

    repeated_factor = tuple(
        stage.model_copy(update={"factor": profile.stages[0].factor})
        if index == 1
        else stage
        for index, stage in enumerate(profile.stages)
    )
    with pytest.raises(ValidationError, match="every technical factor"):
        ProteinInferenceHarmonizationProfile.model_validate(
            profile.model_copy(update={"stages": repeated_factor}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="versions must be unique"):
        ProteinInferenceHarmonizationProfile.model_validate(
            profile.model_copy(
                update={
                    "approved_assay_protocol_versions": (
                        profile.approved_assay_protocol_versions[0],
                    )
                    * 2
                }
            ),
            strict=True,
        )
    overlapping = profile.model_copy(
        update={"profile_id": "profile." + ("f" * 64)}
    )
    with pytest.raises(ValidationError, match="match domains must be disjoint"):
        ProteinInferenceHarmonizationPolicy.model_validate(
            policy.model_copy(update={"profiles": (profile, overlapping)}),
            strict=True,
        )


def test_stage_anchor_sets_are_canonical_unique_and_disjoint(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    stage = canonical_request.policy.profiles[0].stages[0]
    reversed_stage = ProteinInferenceNormalizationStage.model_validate(
        stage.model_copy(
            update={
                "estimation_anchor_ids": tuple(reversed(stage.estimation_anchor_ids)),
                "validation_anchor_ids": tuple(reversed(stage.validation_anchor_ids)),
            }
        ),
        strict=True,
    )
    assert reversed_stage == stage
    with pytest.raises(ValidationError, match="unique and disjoint"):
        ProteinInferenceNormalizationStage.model_validate(
            stage.model_copy(update={"validation_anchor_ids": stage.estimation_anchor_ids}),
            strict=True,
        )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((5,), 5),
        ((9, 1), 1),
        ((9, 1, 5), 5),
        ((9, 1, 7, 3), 3),
        ((-1_000_000, 1_000_000), -1_000_000),
    ],
)
def test_lower_median_is_exact_integer_lower_order_statistic(
    values: tuple[int, ...],
    expected: int,
) -> None:
    assert lower_median(values) == expected


def test_lower_median_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one integer"):
        lower_median(())


def test_level_shift_state_and_exact_cap_relations_are_closed(
    canonical_result: ProteinInferenceHarmonizationResult,
) -> None:
    manifest = canonical_result.transformation_manifest
    assert manifest is not None
    stage = manifest.stages[0]
    estimated = next(
        item
        for item in stage.level_shifts
        if item.state is ProteinInferenceSupportShiftState.ESTIMATED
        and item.estimated_shift_ppm != 0
    )
    assert estimated.applied_shift_ppm is not None

    forged_shift = estimated.model_copy(
        update={"applied_shift_ppm": estimated.applied_shift_ppm + 1}
    )
    with pytest.raises(ValidationError, match="exact and below its cap"):
        type(stage).model_validate(
            stage.model_copy(
                update={
                    "level_shifts": tuple(
                        forged_shift if item.level_id == estimated.level_id else item
                        for item in stage.level_shifts
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="cannot carry numeric"):
        ProteinInferenceSupportLevelShift.model_validate(
            estimated.model_copy(update={"state": ProteinInferenceSupportShiftState.NOT_EVALUABLE}),
            strict=True,
        )


def test_technical_and_invariant_diagnostic_statuses_are_derived(
    canonical_result: ProteinInferenceHarmonizationResult,
) -> None:
    technical = canonical_result.technical_effect_diagnostics[0]
    invariant = canonical_result.invariant_diagnostics[0]
    assert technical.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
    assert invariant.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED

    with pytest.raises(ValidationError, match="deterministic status"):
        ProteinInferenceTechnicalEffectDiagnostic.model_validate(
            technical.model_copy(
                update={"status": ProteinInferenceHarmonizationDiagnosticStatus.FAILED}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="deterministic status"):
        ProteinInferenceInvariantDiagnostic.model_validate(
            invariant.model_copy(
                update={"status": ProteinInferenceHarmonizationDiagnosticStatus.FAILED}
            ),
            strict=True,
        )


def test_all_finding_codes_have_one_deterministic_action_message_and_id() -> None:
    expected_action = {
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_REJECTED: (
            ProteinInferenceHarmonizationFindingAction.REJECT
        ),
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED: (
            ProteinInferenceHarmonizationFindingAction.QUARANTINE
        ),
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_ABSTAINED: (
            ProteinInferenceHarmonizationFindingAction.ABSTAIN
        ),
    }
    findings = tuple(finding_for(code) for code in ProteinInferenceHarmonizationFindingCode)
    assert len({item.finding_id for item in findings}) == len(findings) == M0306_MAX_FINDINGS
    assert all(item.message and "MPEPTIDEK" not in item.message for item in findings)
    assert all(item.action is expected_action[item.code] for item in findings[:3])

    forged = findings[0].model_copy(update={"message": "caller supplied"})
    with pytest.raises(ValidationError, match="closed vocabulary"):
        ProteinInferenceHarmonizationFinding.model_validate(forged, strict=True)


def test_request_canonicalization_preserves_complete_typed_equality(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    payload = _payload(canonical_request)
    payload["artifact_receipt"]["units"] = tuple(
        reversed(payload["artifact_receipt"]["units"])
    )
    payload["support_ledger"]["observations"] = tuple(
        reversed(payload["support_ledger"]["observations"])
    )
    payload["support_ledger"]["invariants"] = tuple(
        reversed(payload["support_ledger"]["invariants"])
    )
    payload["policy"]["profiles"] = tuple(reversed(payload["policy"]["profiles"]))
    payload["policy"]["profiles"][0]["stages"] = tuple(
        reversed(payload["policy"]["profiles"][0]["stages"])
    )

    reordered = HarmonizeProteinInferenceSupportRequest.model_validate(payload, strict=True)
    assert reordered == canonical_request
    assert normalized_request(reordered) == normalized_request(canonical_request)
    assert canonical_request_digest(reordered) == canonical_request_digest(canonical_request)
    assert harmonize_protein_inference_support(reordered) == harmonize_protein_inference_support(
        canonical_request
    )


def test_canonical_result_envelope_is_strict_replay_closed(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    canonical_result: ProteinInferenceHarmonizationResult,
) -> None:
    strict = ProteinInferenceHarmonizationResult.model_validate_json(
        canonical_json_bytes(canonical_result),
        strict=True,
    )
    request_hash = canonical_request_digest(canonical_request)

    assert strict == canonical_result
    assert strict.result_id == f"result.m0306.{request_hash.removeprefix('sha256:')}"
    assert strict.request_digest == request_hash
    assert strict.result_digest == result_payload_digest(strict)
    assert strict.analysis is not None
    assert strict.transformation_manifest is not None
    assert strict.analysis.parent_target == strict.parent_target == M0306_PARENT
    assert not strict.emits_complex_activity
    assert not strict.infers_identity
    assert not strict.infers_protein
    assert not strict.infers_proteoform
    assert not strict.infers_kinase_activity
    assert normalized_result(strict) == normalized_result(canonical_result)


def test_contract_models_reject_unknown_fields_and_are_frozen(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    payload = _payload(canonical_request)
    payload["undeclared"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HarmonizeProteinInferenceSupportRequest.model_validate(payload, strict=True)
    with pytest.raises(ValidationError, match="frozen"):
        canonical_request.policy.max_units = 1  # type: ignore[misc]


def test_resigned_result_cannot_substitute_nested_analysis(
    canonical_result: ProteinInferenceHarmonizationResult,
) -> None:
    payload = deepcopy(_payload(canonical_result))
    assert payload["analysis"] is not None
    payload["analysis"]["values"][0]["harmonized_support_coordinate_ppm"] += 1
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError):
        ProteinInferenceHarmonizationResult.model_validate(payload, strict=True)
