"""Adversarial contract and canonicalization checks for M03-01."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from evals.m03_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m03_01 import (
    AccessionAliasPolicy,
    ComplexActivityHandoffRequirements,
    ContractName,
    DeclaredUnresolvedState,
    EvaluateProteinInferenceProtocolRequest,
    HandoffReceiptRole,
    ProteinErrorMeasure,
    ProteinInferenceApplicability,
    ProteinInferenceIdentityKey,
    ProteinInferenceProtocolConformanceResult,
    ProteinInferenceProtocolSchema,
    ProtocolFindingState,
    ProtocolSection,
    RepresentativeSelection,
    ReviewedProteinInferenceConformanceProfile,
    SharedPeptideStrategy,
    TargetDecoyStrategy,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    expected_protocol_findings,
    profile_digest,
    protocol_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Plugin,
    M0301Service,
    ProteinInferenceProtocolAuthorizationError,
    evaluate_protein_inference_protocol,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_FORGED_DIGEST = "sha256:" + ("f" * 64)
_MAX_REVIEWED_SEARCH_SPACES = 256
_MAX_REVIEWED_VERSIONS = 32


class _HostileMapping(Mapping[str, object]):
    def __init__(self, data: dict[str, object], explosive_key: str) -> None:
        self._data = data
        self._explosive_key = explosive_key

    def __getitem__(self, key: str) -> object:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: object = None) -> object:
        if key == self._explosive_key:
            raise OSError
        return self._data.get(key, default)


class _TraversalProbe(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def __getitem__(self, key: str) -> object:
        self.traversals += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        self.traversals += 1
        raise AssertionError("iteration")

    def __len__(self) -> int:
        self.traversals += 1
        raise AssertionError("length")


def _json_payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_protocol(payload: dict[str, Any]) -> ProteinInferenceProtocolSchema:
    return ProteinInferenceProtocolSchema.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_profile(payload: dict[str, Any]) -> ReviewedProteinInferenceConformanceProfile:
    return ReviewedProteinInferenceConformanceProfile.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _request_for(
    protocol: ProteinInferenceProtocolSchema,
    profile: ReviewedProteinInferenceConformanceProfile,
) -> EvaluateProteinInferenceProtocolRequest:
    payload = _json_payload(build_scenario_request())
    payload["protocol_schema"] = protocol.model_dump(mode="json")
    payload["conformance_profile"] = profile.model_dump(mode="json")
    payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        configuration_digest(protocol, profile)
    )
    return EvaluateProteinInferenceProtocolRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _finding_states(
    protocol: ProteinInferenceProtocolSchema,
    profile: ReviewedProteinInferenceConformanceProfile,
) -> dict[ProtocolSection, ProtocolFindingState]:
    return {
        finding.section: finding.state
        for finding in expected_protocol_findings(protocol, profile)
    }


@pytest.mark.contract
def test_every_exported_schema_is_strict_versioned_and_authority_bounded() -> None:
    names: tuple[ContractName, ...] = (
        "request",
        "output",
        "protocol",
        "profile",
        "search-space",
        "ambiguity",
        "receipt",
    )
    for name in names:
        schema = contract_json_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-01:1.0.0:{name}"
        )
        assert schema["additionalProperties"] is False
        metadata = schema["x-glio-contract"]
        assert metadata == {
            "moduleId": "GLIO-PROTEOGEN-M03-01",
            "contractVersion": "1.0.0",
            "strict": True,
            "rawPayload": False,
            "observedPeptideAssignment": False,
            "proteinInference": False,
            "proteoformInference": False,
            "isoformInference": False,
            "gliomaSpecificBiologyInference": False,
            "biologicalInterpretation": False,
        }
        definitions = cast("dict[str, dict[str, Any]]", schema.get("$defs", {}))
        for definition in definitions.values():
            if definition.get("type") == "object":
                assert definition["additionalProperties"] is False

    output = contract_json_schema("output")
    assert "result_digest" in cast("list[str]", output["required"])
    assert not {
        "protein_assignment",
        "protein_inference",
        "complex_activity",
        "kinase_activity",
        "treatment_recommendation",
    }.intersection(cast("dict[str, Any]", output["properties"]))


@pytest.mark.contract
@pytest.mark.parametrize(
    ("location", "field", "value"),
    [
        ("request", "unexpected", True),
        ("protocol", "unexpected", True),
        ("search_space", "unexpected", True),
        ("composition", "unexpected", True),
        ("profile", "unexpected", True),
    ],
)
def test_unknown_fields_are_rejected_at_every_major_input_boundary(
    location: str,
    field: str,
    value: object,
) -> None:
    payload = _json_payload(build_scenario_request())
    target: dict[str, Any] = {
        "request": payload,
        "protocol": payload["protocol_schema"],
        "search_space": payload["protocol_schema"]["search_space"],
        "composition": payload["protocol_schema"]["search_space"]["composition"],
        "profile": payload["conformance_profile"],
    }[location]
    target[field] = value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluateProteinInferenceProtocolRequest.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("protocol_schema", "search_space", "composition", "canonical_sequences"), "20000"),
        (("protocol_schema", "error_control", "thresholds", 0, "maximum"), "0.01"),
        (("protocol_schema", "peptide_eligibility", "min_length"), True),
        (("conformance_profile", "max_missed_cleavages"), 2.0),
    ],
)
def test_python_contract_does_not_coerce_scalar_types(
    path: tuple[str | int, ...],
    value: object,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value

    with pytest.raises(ValidationError):
        EvaluateProteinInferenceProtocolRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_every_semantic_request_collection_can_reorder_without_changing_output() -> None:
    request = build_scenario_request()
    protocol = request.protocol_schema
    profile_payload = _json_payload(request.conformance_profile)
    search = profile_payload["approved_search_spaces"][0]
    profile_payload.update(
        {
            "approved_applicabilities": [item.value for item in ProteinInferenceApplicability],
            "approved_search_spaces": [
                search,
                {
                    **search,
                    "build_id": "build.synthetic.alternate",
                    "content_digest": sha256_digest({"m0301": "alternate-space"}),
                },
            ],
            "approved_assay_protocol_versions": ["2.1.0", "2.2.0"],
            "approved_specimen_processing_versions": ["1.4.0", "1.5.0"],
            "approved_controlled_vocabularies": [
                profile_payload["approved_controlled_vocabularies"][0],
                {
                    "vocabulary_id": "vocabulary.synthetic.alternate",
                    "version": "1.0.0",
                },
            ],
            "approved_unit_system_versions": ["1.0.0", "2.0.0"],
            "allowed_target_decoy_strategies": [item.value for item in TargetDecoyStrategy],
            "allowed_protein_error_measures": [item.value for item in ProteinErrorMeasure],
            "allowed_shared_peptide_strategies": [item.value for item in SharedPeptideStrategy],
            "allowed_representative_selections": [item.value for item in RepresentativeSelection],
        }
    )
    profile = _validate_profile(profile_payload)
    expanded = _request_for(protocol, profile)
    reordered_payload = _json_payload(expanded)
    protocol_payload = reordered_payload["protocol_schema"]
    for field in (
        "required_identity_keys",
        "declared_unresolved_states",
    ):
        protocol_payload[field].reverse()
    protocol_payload["error_control"]["thresholds"].reverse()
    protocol_payload["complex_activity_handoff"]["required_receipt_roles"].reverse()
    profile_payload = reordered_payload["conformance_profile"]
    for field in (
        "approved_applicabilities",
        "approved_search_spaces",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabularies",
        "approved_unit_system_versions",
        "allowed_target_decoy_strategies",
        "allowed_protein_error_measures",
        "allowed_shared_peptide_strategies",
        "allowed_representative_selections",
    ):
        profile_payload[field].reverse()
    reordered = EvaluateProteinInferenceProtocolRequest.model_validate_json(
        canonical_json_bytes(reordered_payload),
        strict=True,
    )

    assert canonical_request_digest(expanded) == canonical_request_digest(reordered)
    assert protocol_digest(expanded.protocol_schema) == protocol_digest(reordered.protocol_schema)
    assert profile_digest(expanded.conformance_profile) == profile_digest(
        reordered.conformance_profile
    )
    assert evaluate_protein_inference_protocol(expanded) == evaluate_protein_inference_protocol(
        reordered
    )
    assert evaluate_protein_inference_protocol(expanded).model_dump_json() == (
        evaluate_protein_inference_protocol(reordered).model_dump_json()
    )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("applicability", "dia"),
        ("assay_protocol_version", "9.0.0"),
        ("specimen_processing_version", "9.0.0"),
        ("controlled_vocabulary_id", "vocabulary.synthetic.other"),
        ("controlled_vocabulary_version", "9.0.0"),
        ("unit_system_version", "9.0.0"),
    ],
)
def test_each_applicability_comparison_fails_only_its_section(
    field: str,
    replacement: object,
) -> None:
    request = build_scenario_request()
    payload = _json_payload(request.protocol_schema)
    payload[field] = replacement
    states = _finding_states(_validate_protocol(payload), request.conformance_profile)

    assert states[ProtocolSection.APPLICABILITY] is ProtocolFindingState.FAIL
    assert all(
        state is ProtocolFindingState.PASS
        for section, state in states.items()
        if section is not ProtocolSection.APPLICABILITY
    )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("namespace", "reference.synthetic.other"),
        ("release", "2027.1.0"),
        ("build_id", "build.synthetic.other"),
        ("content_digest", _FORGED_DIGEST),
    ],
)
def test_each_search_space_identity_comparison_is_exact(
    field: str,
    replacement: object,
) -> None:
    request = build_scenario_request()
    payload = _json_payload(request.protocol_schema)
    payload["search_space"][field] = replacement
    states = _finding_states(_validate_protocol(payload), request.conformance_profile)

    assert states[ProtocolSection.SEARCH_SPACE] is ProtocolFindingState.FAIL
    assert sum(state is ProtocolFindingState.FAIL for state in states.values()) == 1


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("min_length", 6),
        ("max_length", 46),
        ("max_missed_cleavages", 3),
        ("max_variable_modifications", 4),
    ],
)
def test_each_peptide_eligibility_comparison_is_enforced(
    field: str,
    replacement: object,
) -> None:
    request = build_scenario_request()
    payload = _json_payload(request.protocol_schema)
    payload["peptide_eligibility"][field] = replacement
    states = _finding_states(_validate_protocol(payload), request.conformance_profile)

    assert states[ProtocolSection.PEPTIDE_ELIGIBILITY] is ProtocolFindingState.FAIL


@pytest.mark.contract
def test_q_value_branches_bind_both_error_control_levels() -> None:
    request = build_scenario_request()
    peptide_payload = _json_payload(request.protocol_schema)
    peptide_payload["error_control"]["thresholds"][0]["maximum"] = 0.02
    peptide_states = _finding_states(
        _validate_protocol(peptide_payload),
        request.conformance_profile,
    )
    assert peptide_states[ProtocolSection.ERROR_CONTROL] is ProtocolFindingState.FAIL
    assert peptide_states[ProtocolSection.PEPTIDE_ELIGIBILITY] is ProtocolFindingState.FAIL

    protein_payload = _json_payload(request.protocol_schema)
    protein_payload["error_control"]["thresholds"][1]["maximum"] = 0.02
    protein_states = _finding_states(
        _validate_protocol(protein_payload),
        request.conformance_profile,
    )
    assert protein_states[ProtocolSection.ERROR_CONTROL] is ProtocolFindingState.FAIL
    assert protein_states[ProtocolSection.PEPTIDE_ELIGIBILITY] is ProtocolFindingState.PASS


@pytest.mark.contract
def test_absent_or_non_q_peptide_threshold_does_not_invent_a_q_value_failure() -> None:
    request = build_scenario_request()
    missing_payload = _json_payload(request.protocol_schema)
    missing_payload["error_control"]["thresholds"] = [
        missing_payload["error_control"]["thresholds"][1]
    ]
    missing_states = _finding_states(
        _validate_protocol(missing_payload),
        request.conformance_profile,
    )
    assert missing_states[ProtocolSection.ERROR_CONTROL] is ProtocolFindingState.PASS
    assert missing_states[ProtocolSection.PEPTIDE_ELIGIBILITY] is ProtocolFindingState.PASS

    non_q_payload = _json_payload(request.protocol_schema)
    non_q_payload["error_control"]["thresholds"][0].update(
        {"measure": "posterior_error_probability", "maximum": 0.01}
    )
    profile_payload = _json_payload(request.conformance_profile)
    profile_payload["allowed_protein_error_measures"] = [
        "q_value",
        "posterior_error_probability",
    ]
    non_q_states = _finding_states(
        _validate_protocol(non_q_payload),
        _validate_profile(profile_payload),
    )
    assert non_q_states[ProtocolSection.ERROR_CONTROL] is ProtocolFindingState.PASS
    assert non_q_states[ProtocolSection.PEPTIDE_ELIGIBILITY] is ProtocolFindingState.PASS


@pytest.mark.contract
def test_non_q_protein_threshold_and_all_reviewed_strategy_branches() -> None:
    request = build_scenario_request()
    protocol_payload = _json_payload(request.protocol_schema)
    protocol_payload["error_control"]["thresholds"][1].update(
        {"measure": "posterior_error_probability", "maximum": 0.01}
    )
    profile_payload = _json_payload(request.conformance_profile)
    profile_payload["allowed_protein_error_measures"] = [
        "q_value",
        "posterior_error_probability",
    ]
    states = _finding_states(
        _validate_protocol(protocol_payload),
        _validate_profile(profile_payload),
    )
    assert states[ProtocolSection.ERROR_CONTROL] is ProtocolFindingState.PASS

    cases = (
        ("allowed_target_decoy_strategies", ["separate"], ProtocolSection.ERROR_CONTROL),
        (
            "allowed_protein_error_measures",
            ["posterior_error_probability"],
            ProtocolSection.ERROR_CONTROL,
        ),
        ("allowed_shared_peptide_strategies", ["exclude"], ProtocolSection.ASSIGNMENT),
        ("allowed_representative_selections", ["none"], ProtocolSection.GROUPING),
    )
    for field, replacement, expected_section in cases:
        changed = _json_payload(request.conformance_profile)
        changed[field] = replacement
        case_states = _finding_states(request.protocol_schema, _validate_profile(changed))
        assert case_states[expected_section] is ProtocolFindingState.FAIL


@pytest.mark.contract
@pytest.mark.parametrize(
    "case",
    [
        "psm_q_value",
        "peptide_posterior_error_probability",
        "protein_posterior_error_probability",
        "protein_picked_fdr",
    ],
)
def test_every_fractional_error_measure_is_bounded_by_its_level_cap(case: str) -> None:
    base = build_scenario_request()
    protocol_payload = _json_payload(base.protocol_schema)
    profile_payload = _json_payload(base.conformance_profile)
    if case == "psm_q_value":
        protocol_payload["error_control"]["thresholds"].append(
            {"level": "psm", "measure": "q_value", "maximum": 1.0, "scale": "fraction"}
        )
    elif case == "peptide_posterior_error_probability":
        protocol_payload["error_control"]["thresholds"][0].update(
            {"measure": "posterior_error_probability", "maximum": 0.02}
        )
        profile_payload["allowed_protein_error_measures"].append(
            "posterior_error_probability"
        )
    elif case == "protein_posterior_error_probability":
        protocol_payload["error_control"]["thresholds"][1].update(
            {"measure": "posterior_error_probability", "maximum": 0.02}
        )
        profile_payload["allowed_protein_error_measures"].append(
            "posterior_error_probability"
        )
    else:
        protocol_payload["search_space"]["target_decoy_strategy"] = "picked"
        protocol_payload["error_control"]["target_decoy_strategy"] = "picked"
        protocol_payload["error_control"]["thresholds"][1].update(
            {"measure": "picked_fdr", "maximum": 0.02}
        )
        profile_payload["allowed_target_decoy_strategies"] = ["picked"]
        profile_payload["allowed_protein_error_measures"].append("picked_fdr")
    protocol = _validate_protocol(protocol_payload)
    profile_payload["protocol_schema_digest"] = protocol_digest(protocol)
    profile = _validate_profile(profile_payload)

    result = evaluate_protein_inference_protocol(_request_for(protocol, profile))
    failed = {item.section for item in result.findings if item.state is ProtocolFindingState.FAIL}
    assert ProtocolSection.ERROR_CONTROL in failed
    assert result.disposition.value == "quarantined"
    if case == "peptide_posterior_error_probability":
        assert ProtocolSection.PEPTIDE_ELIGIBILITY in failed


@pytest.mark.contract
def test_review_timestamp_may_equal_evaluation_but_cannot_postdate_it() -> None:
    base = build_scenario_request()
    assert base.conformance_profile.reviewed_at == base.context.occurred_at
    assert EvaluateProteinInferenceProtocolRequest.model_validate(base, strict=True) == base

    profile_payload = _json_payload(base.conformance_profile)
    profile_payload["reviewed_at"] = base.context.occurred_at + timedelta(microseconds=1)
    future_profile = _validate_profile(profile_payload)
    with pytest.raises(ValidationError, match="cannot postdate"):
        _request_for(base.protocol_schema, future_profile)


@pytest.mark.contract
def test_equivalent_datetime_offsets_produce_full_request_and_result_identity() -> None:
    base = build_scenario_request()
    offset = timezone(timedelta(hours=-5))
    payload = base.model_dump(mode="python")
    payload["context"]["occurred_at"] = datetime(2026, 8, 12, 7, tzinfo=offset)
    payload["conformance_profile"]["reviewed_at"] = datetime(
        2026,
        8,
        12,
        7,
        tzinfo=offset,
    )
    offset_request = EvaluateProteinInferenceProtocolRequest.model_validate(
        payload,
        strict=True,
    )

    assert offset_request.context.occurred_at.utcoffset() == timedelta(hours=-5)
    assert canonical_request_digest(base) == canonical_request_digest(offset_request)
    baseline_result = evaluate_protein_inference_protocol(base)
    offset_result = evaluate_protein_inference_protocol(offset_request)
    assert baseline_result == offset_result
    assert baseline_result.model_dump_json() == offset_result.model_dump_json()


@pytest.mark.contract
def test_signed_zero_error_fractions_produce_full_result_identity() -> None:
    base = build_scenario_request()

    def request_with_zero(value: float) -> EvaluateProteinInferenceProtocolRequest:
        protocol_payload = _json_payload(base.protocol_schema)
        protocol_payload["error_control"]["thresholds"][0]["maximum"] = value
        protocol = _validate_protocol(protocol_payload)
        profile_payload = _json_payload(base.conformance_profile)
        profile_payload["protocol_schema_digest"] = protocol_digest(protocol)
        profile_payload["max_peptide_error_fraction"] = value
        profile = _validate_profile(profile_payload)
        return _request_for(protocol, profile)

    positive = request_with_zero(0.0)
    negative = request_with_zero(-0.0)
    assert canonical_request_digest(positive) == canonical_request_digest(negative)
    positive_result = evaluate_protein_inference_protocol(positive)
    negative_result = evaluate_protein_inference_protocol(negative)
    assert positive_result == negative_result
    assert positive_result.model_dump_json() == negative_result.model_dump_json()


@pytest.mark.contract
def test_exact_reviewed_profile_collection_caps_accept_max_and_reject_max_plus_one() -> None:
    request = build_scenario_request()
    payload = _json_payload(request.conformance_profile)
    seed = payload["approved_search_spaces"][0]
    spaces = [
        {
            **seed,
            "build_id": f"build.synthetic.reviewed-{index}",
            "content_digest": sha256_digest({"m0301-space": index}),
        }
        for index in range(_MAX_REVIEWED_SEARCH_SPACES)
    ]
    payload["approved_search_spaces"] = spaces
    assert (
        len(_validate_profile(payload).approved_search_spaces)
        == _MAX_REVIEWED_SEARCH_SPACES
    )
    payload["approved_search_spaces"] = [
        *spaces,
        {
            **seed,
            "build_id": "build.synthetic.reviewed-overflow",
            "content_digest": sha256_digest({"m0301-space": "overflow"}),
        },
    ]
    with pytest.raises(ValidationError, match="at most 256 items"):
        _validate_profile(payload)

    versions = [f"1.0.{index}" for index in range(_MAX_REVIEWED_VERSIONS)]
    payload = _json_payload(request.conformance_profile)
    payload["approved_assay_protocol_versions"] = versions
    assert (
        len(_validate_profile(payload).approved_assay_protocol_versions)
        == _MAX_REVIEWED_VERSIONS
    )
    payload["approved_assay_protocol_versions"] = [*versions, "1.0.32"]
    with pytest.raises(ValidationError, match="at most 32 items"):
        _validate_profile(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "approved_applicabilities",
        "approved_search_spaces",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabularies",
        "approved_unit_system_versions",
        "allowed_target_decoy_strategies",
        "allowed_protein_error_measures",
        "allowed_shared_peptide_strategies",
        "allowed_representative_selections",
    ],
)
def test_every_reviewed_profile_collection_rejects_duplicates(field: str) -> None:
    payload = _json_payload(build_scenario_request().conformance_profile)
    payload[field].append(deepcopy(payload[field][0]))

    with pytest.raises(ValidationError, match="collections must be unique"):
        _validate_profile(payload)


@pytest.mark.contract
def test_search_space_identity_is_unique_even_when_content_digest_differs() -> None:
    payload = _json_payload(build_scenario_request().conformance_profile)
    duplicate_identity = deepcopy(payload["approved_search_spaces"][0])
    duplicate_identity["content_digest"] = _FORGED_DIGEST
    payload["approved_search_spaces"].append(duplicate_identity)

    with pytest.raises(ValidationError, match="identities must be unique"):
        _validate_profile(payload)


@pytest.mark.contract
def test_reviewed_profile_rejects_reversed_peptide_interval() -> None:
    payload = _json_payload(build_scenario_request().conformance_profile)
    payload.update({"min_peptide_length": 46, "max_peptide_length": 45})

    with pytest.raises(ValidationError, match="interval is reversed"):
        _validate_profile(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("pin", "replacement", "message"),
    [
        ("protocol_schema_id", "schema.synthetic.other", "does not pin"),
        ("protocol_schema_version", "9.0.0", "does not pin"),
        ("protocol_schema_digest", _FORGED_DIGEST, "does not pin"),
    ],
)
def test_request_requires_each_exact_profile_pin(
    pin: str,
    replacement: object,
    message: str,
) -> None:
    payload = _json_payload(build_scenario_request())
    payload["conformance_profile"][pin] = replacement

    with pytest.raises(ValidationError, match=message):
        EvaluateProteinInferenceProtocolRequest.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
def test_request_requires_configuration_binding_and_distinct_control_evidence() -> None:
    payload = _json_payload(build_scenario_request())
    payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        _FORGED_DIGEST
    )
    with pytest.raises(ValidationError, match="does not bind protocol and profile"):
        EvaluateProteinInferenceProtocolRequest.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )

    payload = _json_payload(build_scenario_request())
    controls = payload["context"]["references"]
    controls["quality"]["evidence"]["digest"] = controls["support"]["evidence"]["digest"]
    with pytest.raises(ValidationError, match="distinct evidence digests"):
        EvaluateProteinInferenceProtocolRequest.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("control", "state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "unknown"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "unknown"),
        ("intended_use", "rejected"),
    ],
)
def test_typed_request_rejects_each_unauthorized_control(control: str, state: str) -> None:
    payload = _json_payload(build_scenario_request())
    payload["context"]["references"][control]["state"] = state

    with pytest.raises(ValidationError, match="evaluation is not authorized"):
        EvaluateProteinInferenceProtocolRequest.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize("explosive_level", ["candidate", "context"])
def test_all_python_boundaries_fail_closed_on_hostile_accessors_before_payload_traversal(
    explosive_level: str,
) -> None:
    service = M0301Service()
    plugin = M0301Plugin(service)
    boundaries = (
        evaluate_protein_inference_protocol,
        service.validate_request,
        service.execute,
        plugin.validate,
    )
    for boundary in boundaries:
        protocol = _TraversalProbe()
        profile = _TraversalProbe()
        context: Mapping[str, object] = _HostileMapping({}, "references")
        candidate: Mapping[str, object] = _HostileMapping(
            {
                "context": context,
                "protocol_schema": protocol,
                "conformance_profile": profile,
            },
            "context" if explosive_level == "candidate" else "never",
        )
        with pytest.raises(
            ProteinInferenceProtocolAuthorizationError,
            match="accepted upstream controls",
        ):
            boundary(candidate)
        assert protocol.traversals == 0
        assert profile.traversals == 0


@pytest.mark.contract
def test_full_enumerations_are_total_and_exact_in_protocol() -> None:
    request = build_scenario_request()
    assert set(request.protocol_schema.required_identity_keys) == set(ProteinInferenceIdentityKey)
    assert set(request.protocol_schema.declared_unresolved_states) == set(DeclaredUnresolvedState)
    assert set(request.protocol_schema.complex_activity_handoff.required_receipt_roles) == set(
        HandoffReceiptRole
    )
    cases = (
        ("required_identity_keys", "protocol must declare every mandatory"),
        ("declared_unresolved_states", "must distinguish every governed"),
    )
    for field, message in cases:
        payload = _json_payload(request.protocol_schema)
        payload[field][-1] = payload[field][0]
        with pytest.raises(ValidationError, match=message):
            _validate_protocol(payload)

    handoff = _json_payload(request.protocol_schema.complex_activity_handoff)
    handoff["required_receipt_roles"][-1] = handoff["required_receipt_roles"][0]
    with pytest.raises(ValidationError, match="every receipt role exactly once"):
        ComplexActivityHandoffRequirements.model_validate_json(
            canonical_json_bytes(handoff),
            strict=True,
        )


@pytest.mark.contract
def test_protocol_requires_matching_strategy_and_distinct_role_evidence() -> None:
    payload = _json_payload(build_scenario_request().protocol_schema)
    payload["error_control"]["target_decoy_strategy"] = "separate"
    with pytest.raises(ValidationError, match="strategies must match"):
        _validate_protocol(payload)

    for path in (
        ("peptide_eligibility", "modification_vocabulary_reference"),
        ("complex_activity_handoff", "evidence"),
    ):
        payload = _json_payload(build_scenario_request().protocol_schema)
        payload[path[0]][path[1]]["digest"] = payload["evidence"]["digest"]
        with pytest.raises(ValidationError, match="evidence roles require distinct"):
            _validate_protocol(payload)


@pytest.mark.contract
def test_alias_and_ambiguity_safety_flags_are_literal_not_preferences() -> None:
    alias = _json_payload(AccessionAliasPolicy())
    for field in tuple(alias):
        changed = deepcopy(alias)
        changed[field] = False
        with pytest.raises(ValidationError):
            AccessionAliasPolicy.model_validate_json(canonical_json_bytes(changed), strict=True)

    payload = _json_payload(build_scenario_request().protocol_schema)
    payload["ambiguity"]["unresolved_is_not_negative"] = False
    with pytest.raises(ValidationError):
        _validate_protocol(payload)


@pytest.mark.contract
def test_output_digest_is_mandatory_nonzero_and_exact() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    missing = _json_payload(result)
    missing.pop("result_digest")
    zero = _json_payload(result)
    zero["result_digest"] = _ZERO_DIGEST
    stale = _json_payload(result)
    stale["result_digest"] = _FORGED_DIGEST

    for payload in (missing, zero, stale):
        with pytest.raises(ValidationError):
            ProteinInferenceProtocolConformanceResult.model_validate_json(
                canonical_json_bytes(payload),
                strict=True,
            )


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "request_digest",
        "protocol_digest",
        "profile_digest",
        "configuration_digest",
    ],
)
def test_resigned_output_cannot_forge_top_level_bindings(field: str) -> None:
    payload = _json_payload(evaluate_protein_inference_protocol(build_scenario_request()))
    payload[field] = _FORGED_DIGEST
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="bindings are inconsistent"):
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "protocol_digest",
        "profile_digest",
        "configuration_digest",
        "search_space_digest",
        "error_control_digest",
        "assignment_digest",
        "protein_group_digest",
        "ambiguity_digest",
        "handoff_digest",
    ],
)
def test_resigned_output_cannot_forge_any_receipt_digest(field: str) -> None:
    payload = _json_payload(evaluate_protein_inference_protocol(build_scenario_request()))
    payload["receipt"][field] = _FORGED_DIGEST
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="receipt contradicts"):
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
def test_resigned_output_cannot_forge_findings_or_disposition_envelope() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    cases: tuple[tuple[tuple[str | int, ...], object, str], ...] = (
        (("findings", 0, "reason_code"), "forged_reason", "findings contradict"),
        (("findings", 0, "remediation_code"), "forged_remediation", "findings contradict"),
        (("status",), "nonconformant", "disposition envelope"),
        (("disposition",), "quarantined", "disposition envelope"),
        (("receipt", "disposition"), "quarantined", "disposition envelope"),
        (("support", "status"), "review_required", "disposition envelope"),
        (("support", "reason_code"), "forged_support", "disposition envelope"),
        (("support", "rationale"), "Forged support rationale.", "disposition envelope"),
        (("human_review_required",), True, "disposition envelope"),
    )
    for path, replacement, message in cases:
        payload = _json_payload(result)
        cursor: Any = payload
        for segment in path[:-1]:
            cursor = cursor[segment]
        cursor[path[-1]] = replacement
        payload["result_digest"] = result_payload_digest(payload)
        with pytest.raises(ValidationError, match=message):
            ProteinInferenceProtocolConformanceResult.model_validate_json(
                canonical_json_bytes(payload),
                strict=True,
            )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("result_id",), "result.m0301.forged"),
        (("provenance", "activity_id"), "activity.m0301.forged"),
        (("provenance", "actor_id"), "actor.synthetic.forged"),
        (("provenance", "module_id"), "GLIO-PROTEOGEN-M03-99"),
        (("provenance", "module_version"), "9.0.0"),
        (("provenance", "generated_at"), "2026-08-12T12:00:01Z"),
        (("completed_at",), "2026-08-12T12:00:01Z"),
        (("provenance", "configuration_digest"), _FORGED_DIGEST),
        (("provenance", "consent_decision_id"), "decision.synthetic.forged"),
        (("provenance", "consent_state"), "withheld"),
        (("provenance", "consent_policy_version"), "9.0.0"),
        (("provenance", "consent_evidence_digest"), _FORGED_DIGEST),
        (("receipt", "identity_subject_digest"), _FORGED_DIGEST),
        (("receipt", "intended_use_evidence_digest"), _FORGED_DIGEST),
    ],
)
def test_resigned_output_cannot_forge_ownership_envelope(
    path: tuple[str, ...],
    replacement: object,
) -> None:
    payload = _json_payload(evaluate_protein_inference_protocol(build_scenario_request()))
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = replacement
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="provenance and receipt envelope"):
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
def test_resigned_output_cannot_forge_control_records_or_input_set() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    cases: tuple[tuple[tuple[str | int, ...], object], ...] = (
        (("provenance", "control_decisions", 0, "decision_id"), "decision.synthetic.forged"),
        (("provenance", "control_decisions", 0, "state"), "rejected"),
        (("provenance", "control_decisions", 0, "policy_version"), "9.0.0"),
        (("provenance", "control_decisions", 0, "evidence_digest"), _FORGED_DIGEST),
        (("provenance", "control_decisions", 1, "subject_digest"), _FORGED_DIGEST),
        (("provenance", "input_digests", 0), _FORGED_DIGEST),
    )
    for path, replacement in cases:
        payload = _json_payload(result)
        cursor: Any = payload
        for segment in path[:-1]:
            cursor = cursor[segment]
        cursor[path[-1]] = replacement
        payload["result_digest"] = result_payload_digest(payload)
        with pytest.raises(ValidationError, match="provenance and receipt envelope"):
            ProteinInferenceProtocolConformanceResult.model_validate_json(
                canonical_json_bytes(payload),
                strict=True,
            )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("evidence", 0, "claim"), "Forged evidence claim.", "evidence index contradicts"),
        (
            ("limitations", 0, "statement"),
            "Forged authority expansion.",
            "limitations exceed",
        ),
        (
            ("uncertainty", "measurement", "rationale"),
            "Forged calibrated rationale.",
            "uncertainty cannot claim",
        ),
        (
            ("uncertainty", "sensitivity_notes", 0),
            "Forged sensitivity statement.",
            "uncertainty cannot claim",
        ),
    ],
)
def test_resigned_output_cannot_forge_evidence_limitations_or_uncertainty(
    path: tuple[str | int, ...],
    replacement: object,
    message: str,
) -> None:
    payload = _json_payload(evaluate_protein_inference_protocol(build_scenario_request()))
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = replacement
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match=message):
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.contract
def test_resigned_output_cannot_duplicate_or_remove_evidence() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    for mutate in ("duplicate", "remove"):
        payload = _json_payload(result)
        if mutate == "duplicate":
            payload["evidence"].append(deepcopy(payload["evidence"][0]))
        else:
            payload["evidence"].pop()
        payload["result_digest"] = result_payload_digest(payload)
        with pytest.raises(ValidationError, match="evidence index contradicts"):
            ProteinInferenceProtocolConformanceResult.model_validate_json(
                canonical_json_bytes(payload),
                strict=True,
            )


@pytest.mark.contract
def test_semantic_output_collections_can_reorder_with_the_same_digest() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    payload = _json_payload(result)
    for path in (
        ("findings",),
        ("evidence",),
        ("limitations",),
        ("provenance", "input_digests"),
        ("provenance", "control_decisions"),
    ):
        cursor: Any = payload
        for segment in path:
            cursor = cursor[segment]
        cursor.reverse()
    payload["result_digest"] = result_payload_digest(payload)

    validated = ProteinInferenceProtocolConformanceResult.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )
    assert validated.result_digest == result.result_digest
