"""Focused lifecycle and fail-closed tests for M03-01."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy

import pytest
from evals.m03_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m03_01 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
    ProtocolConformanceDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Plugin,
    M0301Service,
    ProteinInferenceProtocolAuthorizationError,
    evaluate_protein_inference_protocol,
)

_SECTION_COUNT = 8


class _HostileTraversalError(AssertionError):
    pass


class _HostileProtocol(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def __getitem__(self, key: str) -> object:
        self.traversals += 1
        raise _HostileTraversalError(key)

    def __iter__(self) -> Iterator[str]:
        self.traversals += 1
        raise _HostileTraversalError

    def __len__(self) -> int:
        self.traversals += 1
        raise _HostileTraversalError


def test_canonical_protocol_emits_one_closed_nonzero_receipt() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())

    assert result.disposition is ProtocolConformanceDisposition.CONFORMANT
    assert result.result_digest != "sha256:" + ("0" * 64)
    assert len(result.findings) == _SECTION_COUNT
    assert len({item.section for item in result.findings}) == _SECTION_COUNT
    assert result.receipt.parent_target == "complex_activity"
    assert not result.protocol_schema.complex_activity_handoff.emit_activity_inference
    assert (
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            result.model_dump_json(),
            strict=True,
        )
        == result
    )


@pytest.mark.parametrize(
    ("case", "section"),
    [
        ("applicability_not_approved", "applicability"),
        ("assay_protocol_version_not_approved", "applicability"),
        ("specimen_processing_version_not_approved", "applicability"),
        ("controlled_vocabulary_version_not_approved", "applicability"),
        ("unit_system_version_not_approved", "applicability"),
        ("search_space_build_digest_mismatch", "search_space"),
        ("target_decoy_strategy_not_reviewed", "error_control"),
        ("competition_scope_mismatch", "error_control"),
        ("shared_assignment_not_reviewed", "assignment"),
        ("representative_selection_not_reviewed", "grouping"),
        ("peptide_eligibility_not_reviewed", "peptide_eligibility"),
    ],
)
def test_reviewed_domain_mismatch_is_typed_quarantine(case: str, section: str) -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request(case))

    failed = {item.section.value for item in result.findings if item.state.value == "fail"}
    assert result.disposition is ProtocolConformanceDisposition.QUARANTINED
    assert result.human_review_required
    assert section in failed


def test_semantic_protocol_set_reordering_has_full_result_equality() -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    protocol = payload["protocol_schema"]
    protocol["required_identity_keys"].reverse()
    protocol["declared_unresolved_states"].reverse()
    protocol["error_control"]["thresholds"].reverse()
    protocol["complex_activity_handoff"]["required_receipt_roles"].reverse()
    reordered = EvaluateProteinInferenceProtocolRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )

    left = evaluate_protein_inference_protocol(request)
    right = evaluate_protein_inference_protocol(reordered)
    assert left == right
    assert left.model_dump_json() == right.model_dump_json()


def test_direct_engine_authorizes_before_hostile_protocol_traversal() -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    hostile = _HostileProtocol()
    payload["protocol_schema"] = hostile

    with pytest.raises(ProteinInferenceProtocolAuthorizationError):
        evaluate_protein_inference_protocol(payload)
    assert hostile.traversals == 0


def test_result_contract_rejects_a_coherent_looking_forged_finding() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    payload = result.model_dump(mode="python")
    payload["findings"][0]["reason_code"] = "forged_review_finding"
    payload["result_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValidationError, match="findings contradict"):
        ProteinInferenceProtocolConformanceResult.model_validate(payload, strict=True)


def test_plugin_enforces_validate_then_run_capability() -> None:
    request = build_scenario_request()
    plugin = M0301Plugin(M0301Service())
    token = plugin.validate(canonical_json_bytes(request))

    assert plugin.run(token) == evaluate_protein_inference_protocol(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]


def test_plugin_descriptor_preserves_exact_ownership_boundary() -> None:
    descriptor = M0301Plugin(M0301Service()).descriptor()

    assert descriptor.title == "Protocol and metadata specification"
    assert (descriptor.owner, descriptor.safety_class, descriptor.gate) == (
        "Bioinformatics",
        "S2",
        "G0",
    )
    rendered = " ".join(descriptor.prohibited_outputs)
    assert "complex-activity" in rendered
    assert "kinase-activity" in rendered


def test_unknown_output_fields_and_stale_receipts_are_rejected() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    unknown = result.model_dump(mode="python")
    unknown["protein_inference"] = {"accession": "forbidden"}
    stale = deepcopy(result.model_dump(mode="python"))
    stale["receipt"]["search_space_digest"] = "sha256:" + ("f" * 64)

    with pytest.raises(ValidationError):
        ProteinInferenceProtocolConformanceResult.model_validate(unknown, strict=True)
    with pytest.raises(ValidationError, match="receipt contradicts"):
        ProteinInferenceProtocolConformanceResult.model_validate(stale, strict=True)


def test_result_digest_is_required_and_zero_sentinel_is_rejected() -> None:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    missing = result.model_dump(mode="python")
    missing.pop("result_digest")
    zero = result.model_dump(mode="python")
    zero["result_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValidationError, match="Field required"):
        ProteinInferenceProtocolConformanceResult.model_validate(missing, strict=True)
    with pytest.raises(ValidationError, match="result digest does not match"):
        ProteinInferenceProtocolConformanceResult.model_validate(zero, strict=True)
