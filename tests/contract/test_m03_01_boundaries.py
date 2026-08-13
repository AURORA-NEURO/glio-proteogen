"""Exact numeric, cardinality, and relational boundaries for M03-01."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, cast

import pytest
from evals.m03_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m03_01 import (
    ComplexActivityHandoffRequirements,
    ErrorControlThreshold,
    PeptideEvidenceEligibilityPolicy,
    PeptideToProteinAssignmentPolicy,
    ProteinErrorControlPolicy,
    ProteinInferenceProtocolConformanceResult,
    ProteinInferenceProtocolSchema,
    RazorTieBreak,
    ReviewedProteinInferenceConformanceProfile,
    SearchSpaceComposition,
    SearchSpaceReceipt,
    SharedPeptideStrategy,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    evaluate_protein_inference_protocol,
)

_MAX_THRESHOLD_COUNT = 3
_PEPTIDE_EQUAL_BOUND = 45


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_composition(payload: dict[str, Any]) -> SearchSpaceComposition:
    return SearchSpaceComposition.model_validate_json(canonical_json_bytes(payload), strict=True)


def _validate_search_space(payload: dict[str, Any]) -> SearchSpaceReceipt:
    return SearchSpaceReceipt.model_validate_json(canonical_json_bytes(payload), strict=True)


def _validate_error_control(payload: dict[str, Any]) -> ProteinErrorControlPolicy:
    return ProteinErrorControlPolicy.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_assignment(payload: dict[str, Any]) -> PeptideToProteinAssignmentPolicy:
    return PeptideToProteinAssignmentPolicy.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


@pytest.mark.contract
def test_search_space_composition_accepts_the_joint_exact_maximum() -> None:
    composition = _validate_composition(
        {
            "canonical_sequences": 100_000_000,
            "isoform_sequences": 100_000_000,
            "variant_sequences": 0,
            "contaminant_sequences": 10_000_000,
            "decoy_sequences": 100_000_000,
            "target_sequences": 210_000_000,
            "total_sequences": 310_000_000,
        }
    )
    assert composition.target_sequences + composition.decoy_sequences == (
        composition.total_sequences
    )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "overflow"),
    [
        ("canonical_sequences", 100_000_001),
        ("isoform_sequences", 100_000_001),
        ("variant_sequences", 100_000_001),
        ("contaminant_sequences", 10_000_001),
        ("decoy_sequences", 100_000_001),
        ("target_sequences", 210_000_001),
        ("total_sequences", 310_000_001),
    ],
)
def test_each_search_space_count_rejects_max_plus_one(field: str, overflow: int) -> None:
    payload = _payload(build_scenario_request().protocol_schema.search_space.composition)
    payload[field] = overflow

    with pytest.raises(ValidationError):
        _validate_composition(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("canonical_sequences", 0),
        ("decoy_sequences", 0),
        ("target_sequences", 0),
        ("total_sequences", 0),
        ("isoform_sequences", -1),
        ("variant_sequences", -1),
        ("contaminant_sequences", -1),
    ],
)
def test_each_search_space_count_rejects_its_lower_underflow(field: str, value: int) -> None:
    payload = _payload(build_scenario_request().protocol_schema.search_space.composition)
    payload[field] = value

    with pytest.raises(ValidationError):
        _validate_composition(payload)


@pytest.mark.contract
@pytest.mark.parametrize("changed_total", ["target_sequences", "total_sequences"])
def test_search_space_arithmetic_must_close_exactly(changed_total: str) -> None:
    payload = _payload(build_scenario_request().protocol_schema.search_space.composition)
    payload[changed_total] += 1

    with pytest.raises(ValidationError, match="counts do not close"):
        _validate_composition(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("count_field", "reference_field"),
    [
        ("isoform_sequences", "isoform_reference"),
        ("variant_sequences", "variant_reference"),
        ("contaminant_sequences", "contaminant_reference"),
    ],
)
def test_optional_search_space_reference_is_present_exactly_when_count_is_positive(
    count_field: str,
    reference_field: str,
) -> None:
    original = _payload(build_scenario_request().protocol_schema.search_space)
    missing = deepcopy(original)
    missing[reference_field] = None
    with pytest.raises(ValidationError, match="exact pinned references"):
        _validate_search_space(missing)

    surplus = deepcopy(original)
    removed = surplus["composition"][count_field]
    surplus["composition"][count_field] = 0
    surplus["composition"]["target_sequences"] -= removed
    surplus["composition"]["total_sequences"] -= removed
    with pytest.raises(ValidationError, match="exact pinned references"):
        _validate_search_space(surplus)


@pytest.mark.contract
@pytest.mark.parametrize(
    "reference_field",
    [
        "decoy_reference",
        "isoform_reference",
        "variant_reference",
        "contaminant_reference",
        "evidence",
    ],
)
def test_each_search_space_reference_role_requires_a_distinct_digest(
    reference_field: str,
) -> None:
    payload = _payload(build_scenario_request().protocol_schema.search_space)
    payload[reference_field]["digest"] = payload["canonical_sequence_reference"]["digest"]

    with pytest.raises(ValidationError, match="distinct content digests"):
        _validate_search_space(payload)


@pytest.mark.contract
def test_error_control_accepts_exactly_three_unique_levels_and_rejects_four() -> None:
    payload = _payload(build_scenario_request().protocol_schema.error_control)
    payload["thresholds"].append(
        {
            "level": "psm",
            "measure": "q_value",
            "maximum": 0.01,
            "scale": "fraction",
        }
    )
    assert len(_validate_error_control(payload).thresholds) == _MAX_THRESHOLD_COUNT
    payload["thresholds"].append(
        {
            "level": "psm",
            "measure": "posterior_error_probability",
            "maximum": 0.01,
            "scale": "fraction",
        }
    )
    with pytest.raises(ValidationError, match="at most 3 items"):
        _validate_error_control(payload)


@pytest.mark.contract
def test_error_control_requires_unique_levels_and_a_protein_group_threshold() -> None:
    duplicate = _payload(build_scenario_request().protocol_schema.error_control)
    duplicate["thresholds"][1]["level"] = "peptide"
    with pytest.raises(ValidationError, match="unique levels including protein_group"):
        _validate_error_control(duplicate)

    missing = _payload(build_scenario_request().protocol_schema.error_control)
    missing["thresholds"] = [missing["thresholds"][0]]
    with pytest.raises(ValidationError, match="unique levels including protein_group"):
        _validate_error_control(missing)

    wrong_owner = _payload(build_scenario_request().protocol_schema.error_control)
    wrong_owner["protein_level"] = "peptide"
    with pytest.raises(ValidationError, match="must be protein-group level"):
        _validate_error_control(wrong_owner)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("maximum", "outcome"),
    [
        (0.0, "accept"),
        (1.0, "accept"),
        (-0.000_001, "reject"),
        (1.000_001, "reject"),
    ],
)
def test_error_fraction_accepts_closed_unit_interval(maximum: float, outcome: str) -> None:
    payload = {
        "level": "protein_group",
        "measure": "q_value",
        "maximum": maximum,
        "scale": "fraction",
    }
    if outcome == "accept":
        assert ErrorControlThreshold.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        ).maximum == maximum
    else:
        with pytest.raises(ValidationError):
            ErrorControlThreshold.model_validate_json(
                canonical_json_bytes(payload),
                strict=True,
            )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("level", "strategy", "outcome"),
    [
        ("protein_group", "picked", "accept"),
        ("protein_group", "concatenated", "reject"),
        ("peptide", "picked", "reject"),
        ("psm", "picked", "reject"),
    ],
)
def test_picked_fdr_requires_picked_protein_group_competition(
    level: str,
    strategy: str,
    outcome: str,
) -> None:
    payload = _payload(build_scenario_request().protocol_schema.error_control)
    payload["target_decoy_strategy"] = strategy
    payload["thresholds"] = [
        {
            "level": level,
            "measure": "picked_fdr",
            "maximum": 0.01,
            "scale": "fraction",
        },
        *(
            [
                {
                    "level": "protein_group",
                    "measure": "q_value",
                    "maximum": 0.01,
                    "scale": "fraction",
                }
            ]
            if level != "protein_group"
            else []
        ),
    ]
    if outcome == "accept":
        assert _validate_error_control(payload).thresholds[0].measure.value == "picked_fdr"
    else:
        with pytest.raises(ValidationError, match="picked FDR"):
            _validate_error_control(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("strategy", "tie_break", "outcome"),
    [
        (SharedPeptideStrategy.RAZOR, RazorTieBreak.LEXICOGRAPHIC_ACCESSION, "accept"),
        (SharedPeptideStrategy.RAZOR, RazorTieBreak.HIGHEST_UNIQUE_PEPTIDE_COUNT, "accept"),
        (SharedPeptideStrategy.RAZOR, RazorTieBreak.NONE, "reject"),
        (SharedPeptideStrategy.EXCLUDE, RazorTieBreak.NONE, "accept"),
        (SharedPeptideStrategy.GROUP_ONLY, RazorTieBreak.NONE, "accept"),
        (SharedPeptideStrategy.EXCLUDE, RazorTieBreak.LEXICOGRAPHIC_ACCESSION, "reject"),
        (
            SharedPeptideStrategy.GROUP_ONLY,
            RazorTieBreak.HIGHEST_UNIQUE_PEPTIDE_COUNT,
            "reject",
        ),
    ],
)
def test_assignment_strategy_and_tie_break_matrix_is_total(
    strategy: SharedPeptideStrategy,
    tie_break: RazorTieBreak,
    outcome: str,
) -> None:
    payload = {
        "shared_peptide_strategy": strategy,
        "razor_tie_break": tie_break,
        "shared_peptides_support_group_claims_only": True,
        "razor_never_supports_member_specific_claim": True,
    }
    if outcome == "accept":
        assert _validate_assignment(payload).shared_peptide_strategy is strategy
    else:
        with pytest.raises(ValidationError, match="requires exactly one deterministic"):
            _validate_assignment(payload)


@pytest.mark.contract
def test_peptide_length_interval_accepts_equality_and_rejects_reversal() -> None:
    payload = _payload(build_scenario_request().protocol_schema.peptide_eligibility)
    payload.update(
        {"min_length": _PEPTIDE_EQUAL_BOUND, "max_length": _PEPTIDE_EQUAL_BOUND}
    )
    assert (
        PeptideEvidenceEligibilityPolicy.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        ).min_length
        == _PEPTIDE_EQUAL_BOUND
    )
    payload.update({"min_length": 46, "max_length": 45})
    with pytest.raises(ValidationError, match="interval is reversed"):
        PeptideEvidenceEligibilityPolicy.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "uniqueness_relative_to_search_space",
        "include_decoy_and_contaminant_competitors",
    ],
)
def test_peptide_safety_declarations_are_required_true_literals(field: str) -> None:
    payload = _payload(build_scenario_request().protocol_schema.peptide_eligibility)
    payload[field] = False
    with pytest.raises(ValidationError):
        PeptideEvidenceEligibilityPolicy.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "unsafe"),
    [
        ("preserve_unresolved_groups", False),
        ("emit_activity_inference", True),
        ("activity_owner", "this_module"),
    ],
)
def test_complex_activity_handoff_cannot_expand_m03_01_authority(
    field: str,
    unsafe: object,
) -> None:
    payload = _payload(build_scenario_request().protocol_schema.complex_activity_handoff)
    payload[field] = unsafe
    with pytest.raises(ValidationError):
        ComplexActivityHandoffRequirements.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_psm_error_fraction", -0.000_001),
        ("max_psm_error_fraction", 1.000_001),
        ("max_peptide_error_fraction", -0.000_001),
        ("max_peptide_error_fraction", 1.000_001),
        ("max_protein_group_error_fraction", -0.000_001),
        ("max_protein_group_error_fraction", 1.000_001),
        ("min_peptide_length", 4),
        ("min_peptide_length", 101),
        ("max_peptide_length", 4),
        ("max_peptide_length", 201),
        ("max_missed_cleavages", -1),
        ("max_missed_cleavages", 11),
        ("max_variable_modifications", -1),
        ("max_variable_modifications", 21),
    ],
)
def test_each_reviewed_scalar_rejects_its_first_out_of_range_value(
    field: str,
    value: float,
) -> None:
    payload = _payload(build_scenario_request().conformance_profile)
    payload[field] = value
    with pytest.raises(ValidationError):
        ReviewedProteinInferenceConformanceProfile.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
def test_profile_requires_timezone_aware_review_timestamp() -> None:
    payload = build_scenario_request().conformance_profile.model_dump(mode="python")
    payload["reviewed_at"] = datetime(2026, 8, 12, 12)  # noqa: DTZ001 - deliberate case.
    with pytest.raises(ValidationError, match="timezone info"):
        ReviewedProteinInferenceConformanceProfile.model_validate(payload, strict=True)


@pytest.mark.contract
def test_protocol_evidence_roles_all_require_distinct_digests() -> None:
    base = build_scenario_request().protocol_schema
    for first_path, second_path in (
        (("evidence",), ("peptide_eligibility", "modification_vocabulary_reference")),
        (("evidence",), ("complex_activity_handoff", "evidence")),
        (
            ("peptide_eligibility", "modification_vocabulary_reference"),
            ("complex_activity_handoff", "evidence"),
        ),
    ):
        payload = _payload(base)
        first: Any = payload
        for segment in first_path:
            first = first[segment]
        second: Any = payload
        for segment in second_path:
            second = second[segment]
        second["digest"] = first["digest"]
        with pytest.raises(ValidationError, match="evidence roles require distinct"):
            ProteinInferenceProtocolSchema.model_validate_json(
                canonical_json_bytes(payload),
                strict=True,
            )


@pytest.mark.contract
def test_resigned_output_rejects_duplicate_or_missing_protocol_section() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    payload = _payload(result)
    payload["findings"][-1] = deepcopy(payload["findings"][0])
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="exactly one finding"):
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize("field", ["parent_target", "output_type", "result_version"])
def test_output_identity_and_parent_target_are_frozen_literals(field: str) -> None:
    payload = _payload(evaluate_protein_inference_protocol(build_scenario_request()))
    payload[field] = "forged"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )
