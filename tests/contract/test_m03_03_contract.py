"""Public contract, canonicalization, and replay checks for M03-03."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from evals.m03_03.run import Scenario, build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_03 import (
    ContractName,
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceBuildState,
    ProteinInferenceCompression,
    ProteinInferenceDiagnosticAction,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceLineageIngestionReceipt,
    ProteinInferenceParseDiagnostic,
    ProteinInferenceProtocolIngestionReceipt,
    ProteinInferenceRawAdmissionResult,
    ProteinInferenceRawFormat,
    ProteinInferenceRawRole,
    admission_evidence_index,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    diagnostic_for,
    expected_admission_receipt,
    expected_disposition,
    expected_limitations,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    lineage_ingestion_receipt,
    lineage_receipt_digest,
    normalized_lineage_receipt,
    normalized_policy,
    normalized_protocol_receipt,
    normalized_request,
    normalized_result_payload,
    normalized_sources,
    policy_digest,
    protocol_ingestion_receipt,
    protocol_receipt_digest,
    result_payload_digest,
    source_manifest_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ingest_protein_inference_raw_inputs,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_FORGED_DIGEST = "sha256:" + ("f" * 64)
_CONTROL_COUNT = 7
_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "policy",
    "source",
    "protocol-receipt",
    "lineage-receipt",
    "raw-input",
    "receipt",
)


@pytest.fixture(scope="module")
def canonical_scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def canonical_result(canonical_scenario: Scenario) -> ProteinInferenceRawAdmissionResult:
    return ingest_protein_inference_raw_inputs(
        canonical_scenario.request,
        canonical_scenario.sources,
    )


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_request(payload: dict[str, Any]) -> IngestProteinInferenceRawInputsRequest:
    return IngestProteinInferenceRawInputsRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_result(payload: dict[str, Any]) -> ProteinInferenceRawAdmissionResult:
    return ProteinInferenceRawAdmissionResult.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _set_path(payload: dict[str, Any], path: tuple[str | int, ...], value: object) -> None:
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value


def _assert_resigned_result_rejected(
    result: ProteinInferenceRawAdmissionResult,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    payload = _payload(result)
    _set_path(payload, path, replacement)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        _validate_result(payload)


def _assert_recursive_objects_are_closed(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for child in value.values():
            _assert_recursive_objects_are_closed(child)
    elif isinstance(value, list):
        for child in value:
            _assert_recursive_objects_are_closed(child)


@pytest.mark.contract
def test_all_eight_schemas_are_draft_2020_strict_and_authority_bounded() -> None:
    expected_metadata = {
        "moduleId": "GLIO-PROTEOGEN-M03-03",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawPayloadInSchema": False,
        "identityInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "isoformInference": False,
        "gliomaSpecificBiologyInference": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
    }
    for name in _SCHEMA_NAMES:
        schema = contract_json_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-03:1.0.0:{name}"
        )
        metadata = deepcopy(expected_metadata)
        if name == "request":
            metadata["maxRequestBytes"] = 4 * 1024 * 1024
        assert schema["x-glio-contract"] == metadata
        _assert_recursive_objects_are_closed(schema)

    output = contract_json_schema("output")
    assert "result_digest" in cast("list[str]", output["required"])
    assert not {
        "raw_payload",
        "raw_bytes",
        "protein_assignment",
        "protein_abundance",
        "complex_activity",
        "kinase_activity",
        "treatment_recommendation",
    }.intersection(cast("dict[str, Any]", output["properties"]))


@pytest.mark.contract
def test_all_closed_enumerations_are_exact_and_total() -> None:
    assert tuple(item.value for item in ProteinInferenceRawRole) == (
        "spectra",
        "peptide_evidence",
        "protein_group_manifest",
        "ambiguity_manifest",
        "complex_activity_input_bundle",
        "canonical_sequences",
        "decoy_sequences",
        "isoform_sequences",
        "variant_sequences",
        "contaminant_sequences",
        "ptm_vocabulary",
        "genomic_context",
        "transcript_context",
    )
    assert tuple(item.value for item in ProteinInferenceRawFormat) == (
        "mzML",
        "mzIdentML",
        "protein_group_json",
        "ambiguity_json",
        "complex_bundle_json",
        "FASTA",
        "PSI_MOD_OBO",
        "VCF",
        "GFF3",
    )
    assert tuple(item.value for item in ProteinInferenceCompression) == ("none", "gzip")
    assert tuple(item.value for item in ProteinInferenceAdmissionDisposition) == (
        "validated",
        "quarantined",
        "abstained",
        "rejected",
    )
    assert tuple(item.value for item in ProteinInferenceBuildState) == (
        "exact",
        "mismatched",
        "missing",
        "unsupported",
        "not_applicable",
    )
    assert tuple(item.value for item in ProteinInferenceDiagnosticAction) == (
        "record",
        "quarantine",
        "abstain",
        "reject",
    )
    assert {item.value for item in ProteinInferenceDiagnosticCode} == {
        "checksum_mismatch",
        "declared_size_mismatch",
        "raw_size_limit_exceeded",
        "decoded_size_limit_exceeded",
        "invalid_gzip",
        "unsupported_format",
        "unsupported_version",
        "malformed_content",
        "forbidden_xml_construct",
        "duplicate_json_key",
        "dangling_reference",
        "role_format_mismatch",
        "build_mismatch",
        "build_missing",
        "build_unsupported",
        "controlled_vocabulary_mismatch",
        "unit_profile_mismatch",
        "assembly_mismatch",
        "cross_source_disagreement",
        "upstream_quarantined",
        "upstream_abstained",
        "upstream_shape_unsupported",
    }


@pytest.mark.contract
@pytest.mark.parametrize(
    "path",
    [
        (),
        ("policy",),
        ("sources", 0),
        ("protocol_receipt",),
        ("protocol_receipt", "search_space"),
        ("lineage_receipt",),
        ("lineage_receipt", "artifacts", 0),
    ],
)
def test_unknown_fields_are_rejected_at_every_input_layer(
    canonical_scenario: Scenario,
    path: tuple[str | int, ...],
) -> None:
    payload = _payload(canonical_scenario.request)
    target: Any = payload
    for segment in path:
        target = target[segment]
    target["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("policy", "max_sources"), "64"),
        (("policy", "max_source_bytes"), 1_048_576.0),
        (("sources", 0, "byte_length"), "10"),
        (("sources", 0, "bound_claim_id"), False),
        (("lineage_receipt", "artifacts", 0, "finding_codes"), "identity_swap"),
    ],
)
def test_strict_ingress_never_coerces_scalars_or_collections(
    canonical_scenario: Scenario,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    payload = canonical_scenario.request.model_dump(mode="python")
    _set_path(payload, path, replacement)
    with pytest.raises(ValidationError):
        IngestProteinInferenceRawInputsRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_request_canonicalization_has_typed_dict_parity_and_semantic_order(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    payload = _payload(request)
    expected = canonical_request_digest(request)
    assert expected == canonical_request_digest(payload)
    assert canonical_json_bytes(normalized_request(request)) == canonical_json_bytes(
        normalized_request(payload)
    )
    assert canonical_json_bytes(normalized_policy(request.policy)) == canonical_json_bytes(
        normalized_policy(payload["policy"])
    )
    assert canonical_json_bytes(normalized_sources(request.sources)) == canonical_json_bytes(
        normalized_sources(payload["sources"])
    )
    assert canonical_json_bytes(normalized_protocol_receipt(request.protocol_receipt)) == (
        canonical_json_bytes(normalized_protocol_receipt(payload["protocol_receipt"]))
    )
    assert canonical_json_bytes(normalized_lineage_receipt(request.lineage_receipt)) == (
        canonical_json_bytes(normalized_lineage_receipt(payload["lineage_receipt"]))
    )

    cast("list[Any]", payload["sources"]).reverse()
    cast("list[Any]", payload["policy"]["approved_genome_builds"]).reverse()
    cast("list[Any]", payload["policy"]["approved_transcript_builds"]).reverse()
    cast("list[Any]", payload["lineage_receipt"]["artifacts"]).reverse()
    for artifact in cast("list[dict[str, Any]]", payload["lineage_receipt"]["artifacts"]):
        cast("list[str]", artifact["finding_codes"]).reverse()
    reordered = _validate_request(payload)
    assert canonical_request_digest(reordered) == expected
    assert source_manifest_digest(reordered.sources) == request.source_manifest_digest


@pytest.mark.contract
def test_upstream_receipt_projections_are_typed_dict_equal_and_content_addressed(
    canonical_scenario: Scenario,
) -> None:
    protocol_typed = protocol_ingestion_receipt(canonical_scenario.protocol_result)
    protocol_mapping = protocol_ingestion_receipt(
        canonical_scenario.protocol_result.model_dump(mode="python")
    )
    lineage_typed = lineage_ingestion_receipt(canonical_scenario.lineage_result)
    lineage_mapping = lineage_ingestion_receipt(
        canonical_scenario.lineage_result.model_dump(mode="python")
    )
    assert protocol_typed == protocol_mapping == canonical_scenario.request.protocol_receipt
    assert lineage_typed == lineage_mapping == canonical_scenario.request.lineage_receipt
    assert protocol_typed.receipt_digest == protocol_receipt_digest(protocol_typed)
    assert lineage_typed.receipt_digest == lineage_receipt_digest(lineage_typed)

    stale_protocol = _payload(protocol_typed)
    stale_protocol["receipt_digest"] = _FORGED_DIGEST
    with pytest.raises(ValidationError, match="receipt digest"):
        ProteinInferenceProtocolIngestionReceipt.model_validate_json(
            canonical_json_bytes(stale_protocol), strict=True
        )
    stale_lineage = _payload(lineage_typed)
    stale_lineage["receipt_digest"] = _FORGED_DIGEST
    with pytest.raises(ValidationError, match="receipt digest"):
        ProteinInferenceLineageIngestionReceipt.model_validate_json(
            canonical_json_bytes(stale_lineage), strict=True
        )


@pytest.mark.contract
def test_public_runtime_is_total_deterministic_and_typed_mapping_equal(
    canonical_scenario: Scenario,
) -> None:
    typed = ingest_protein_inference_raw_inputs(
        canonical_scenario.request,
        canonical_scenario.sources,
    )
    mapping = ingest_protein_inference_raw_inputs(
        canonical_scenario.request.model_dump(mode="python"),
        canonical_scenario.sources,
    )
    replay = ingest_protein_inference_raw_inputs(
        canonical_scenario.request,
        canonical_scenario.sources,
    )
    assert typed == mapping == replay
    assert typed.model_dump_json() == mapping.model_dump_json() == replay.model_dump_json()


@pytest.mark.contract
def test_semantic_request_reorder_produces_the_identical_full_result(
    canonical_scenario: Scenario,
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    payload = _payload(canonical_scenario.request)
    cast("list[Any]", payload["sources"]).reverse()
    cast("list[Any]", payload["lineage_receipt"]["artifacts"]).reverse()
    reordered = _validate_request(payload)
    reversed_mapping = dict(reversed(tuple(canonical_scenario.sources.items())))
    result = ingest_protein_inference_raw_inputs(reordered, reversed_mapping)
    assert result == canonical_result
    assert result.model_dump_json() == canonical_result.model_dump_json()


@pytest.mark.contract
def test_result_normalization_has_typed_dict_parity_and_semantic_order(
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    payload = _payload(canonical_result)
    assert canonical_json_bytes(normalized_result_payload(canonical_result)) == (
        canonical_json_bytes(normalized_result_payload(payload))
    )
    assert result_payload_digest(canonical_result) == result_payload_digest(payload)
    cast("list[Any]", payload["raw_inputs"]).reverse()
    cast("list[Any]", payload["diagnostics"]).reverse()
    cast("list[Any]", payload["evidence"]).reverse()
    cast("list[Any]", payload["limitations"]).reverse()
    cast("list[Any]", payload["provenance"]["input_digests"]).reverse()
    cast("list[Any]", payload["provenance"]["control_decisions"]).reverse()
    cast("list[Any]", payload["uncertainty"]["sensitivity_notes"]).reverse()
    assert result_payload_digest(payload) == canonical_result.result_digest
    assert _validate_result(payload).result_digest == canonical_result.result_digest


@pytest.mark.contract
def test_result_digest_is_required_nonzero_and_exact(
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    missing = _payload(canonical_result)
    missing.pop("result_digest")
    zero = _payload(canonical_result)
    zero["result_digest"] = _ZERO_DIGEST
    stale = _payload(canonical_result)
    stale["result_digest"] = _FORGED_DIGEST
    for payload in (missing, zero, stale):
        with pytest.raises(ValidationError):
            _validate_result(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("result_id",), "result.m0303.forged"),
        (("request_digest",), _FORGED_DIGEST),
        (("policy_digest",), _FORGED_DIGEST),
        (("configuration_digest",), _FORGED_DIGEST),
        (("receipt", "protocol_receipt_digest"), _FORGED_DIGEST),
        (("receipt", "lineage_receipt_digest"), _FORGED_DIGEST),
        (("receipt", "source_manifest_digest"), _FORGED_DIGEST),
        (("receipt", "disposition"), "abstained"),
        (("disposition",), "abstained"),
        (("parent_target",), "kinase_activity"),
        (("emits_complex_activity",), True),
        (("infers_identity",), True),
        (("infers_protein",), True),
        (("infers_kinase_activity",), True),
        (("human_review_required",), True),
        (("completed_at",), "2026-08-12T15:00:01Z"),
    ],
)
def test_resigned_result_cannot_forge_top_level_or_receipt_binding(
    canonical_result: ProteinInferenceRawAdmissionResult,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("raw_inputs", 0, "source_digest"), _FORGED_DIGEST),
        (("raw_inputs", 0, "source_size_bytes"), 1),
        (("raw_inputs", 0, "detected_format"), "FASTA"),
        (("raw_inputs", 0, "compression"), "gzip"),
        (("raw_inputs", 0, "compression"), None),
        (("raw_inputs", 0, "build", "state"), "unsupported"),
    ],
)
def test_resigned_result_cannot_forge_request_derivable_raw_summary(
    canonical_result: ProteinInferenceRawAdmissionResult,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
def test_resigned_result_cannot_add_an_ungrounded_transport_diagnostic(
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    payload = _payload(canonical_result)
    source_id = cast("str", payload["raw_inputs"][0]["source_id"])
    diagnostic = diagnostic_for(
        ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
        (source_id,),
    )
    disposition = expected_disposition((diagnostic,))
    payload["diagnostics"] = [diagnostic.model_dump(mode="json")]
    payload["disposition"] = disposition.value
    payload["receipt"] = expected_admission_receipt(
        canonical_result.request,
        disposition,
    ).model_dump(mode="json")
    payload["support"] = expected_support(disposition).model_dump(mode="json")
    payload["human_review_required"] = True
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        _validate_result(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("support", "status"), "review_required"),
        (("support", "reason_code"), "forged_support"),
        (("support", "rationale"), "Forged support rationale."),
        (("uncertainty", "measurement", "state"), "not_applicable"),
        (("uncertainty", "sampling", "rationale"), "Forged sampling rationale."),
        (("uncertainty", "parameter", "rationale"), "Forged parameter rationale."),
        (("uncertainty", "model_form", "rationale"), "Forged model rationale."),
        (("uncertainty", "identification", "rationale"), "Forged identity rationale."),
        (("uncertainty", "support", "rationale"), "Forged support rationale."),
        (("uncertainty", "transport", "rationale"), "Forged transport rationale."),
        (("uncertainty", "sensitivity_notes", 0), "Forged sensitivity note."),
    ],
)
def test_resigned_result_cannot_forge_support_or_uncertainty(
    canonical_result: ProteinInferenceRawAdmissionResult,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("provenance", "activity_id"), "activity.m0303.forged"),
        (("provenance", "actor_id"), "actor.m0303.forged"),
        (("provenance", "module_id"), "GLIO-PROTEOGEN-M03-99"),
        (("provenance", "module_version"), "9.0.0"),
        (("provenance", "generated_at"), "2026-08-12T15:00:01Z"),
        (("provenance", "configuration_digest"), _FORGED_DIGEST),
        (("provenance", "consent_decision_id"), "decision.m0303.forged"),
        (("provenance", "consent_state"), "withheld"),
        (("provenance", "input_digests", 0), _FORGED_DIGEST),
        (("provenance", "control_decisions", 0, "decision_id"), "decision.forged"),
        (("provenance", "control_decisions", 0, "state"), "rejected"),
        (("evidence", 0, "role"), "counter_evidence"),
        (("evidence", 0, "claim"), "Forged evidence claim."),
        (("evidence", 0, "reference", "digest"), _FORGED_DIGEST),
        (("limitations", 0, "code"), "forged_limitation"),
        (("limitations", 0, "statement"), "Forged authority expansion."),
    ],
)
def test_resigned_result_cannot_forge_provenance_evidence_or_limitations(
    canonical_result: ProteinInferenceRawAdmissionResult,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
def test_exact_envelope_helpers_replay_the_complete_result(
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    result = canonical_result
    request = result.request
    assert result.disposition is expected_disposition(result.diagnostics)
    assert result.receipt == expected_admission_receipt(request, result.disposition)
    assert result.support == expected_support(result.disposition)
    assert result.uncertainty == expected_uncertainty()
    assert result.provenance == expected_provenance(request, result.request_digest)
    assert tuple(sorted(result.evidence, key=canonical_json_bytes)) == tuple(
        sorted(admission_evidence_index(request), key=canonical_json_bytes)
    )
    assert tuple(sorted(result.limitations, key=canonical_json_bytes)) == tuple(
        sorted(expected_limitations(), key=canonical_json_bytes)
    )
    assert result.policy_digest == policy_digest(request.policy)
    assert result.configuration_digest == configuration_digest(request.policy)


@pytest.mark.contract
def test_evidence_and_provenance_sets_are_exact_unique_and_content_addressed(
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    evidence = canonical_result.evidence
    assert len(evidence) == len(
        {
            (
                item.reference.artifact_id,
                item.reference.version,
                item.reference.digest,
                item.reference.media_type,
            )
            for item in evidence
        }
    )
    expected_inputs = {
        canonical_result.request_digest,
        canonical_result.policy_digest,
        canonical_result.configuration_digest,
        canonical_result.request.source_manifest_digest,
        protocol_receipt_digest(canonical_result.request.protocol_receipt),
        lineage_receipt_digest(canonical_result.request.lineage_receipt),
        canonical_result.request.protocol_receipt.protocol_result_digest,
        canonical_result.request.protocol_receipt.protocol_digest,
        canonical_result.request.protocol_receipt.search_space_digest,
        canonical_result.request.lineage_receipt.lineage_result_digest,
        canonical_result.request.lineage_receipt.lineage_request_digest,
        canonical_result.request.lineage_receipt.identity_resolution_digest,
        canonical_result.request.lineage_receipt.graph_digest,
        *(item.reference.digest for item in evidence),
        *(item.evidence_digest for item in canonical_result.provenance.control_decisions),
    }
    assert canonical_result.provenance.input_digests == tuple(sorted(expected_inputs))
    assert len(canonical_result.provenance.control_decisions) == _CONTROL_COUNT


@pytest.mark.contract
def test_diagnostic_vocabulary_has_fixed_action_message_and_identifier() -> None:
    expected_actions = {
        ProteinInferenceDiagnosticAction.REJECT: {
            ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
            ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH,
            ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED,
            ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED,
            ProteinInferenceDiagnosticCode.INVALID_GZIP,
        },
        ProteinInferenceDiagnosticAction.ABSTAIN: {
            ProteinInferenceDiagnosticCode.UNSUPPORTED_FORMAT,
            ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION,
            ProteinInferenceDiagnosticCode.BUILD_MISSING,
            ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED,
            ProteinInferenceDiagnosticCode.UPSTREAM_ABSTAINED,
            ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED,
        },
        ProteinInferenceDiagnosticAction.QUARANTINE: {
            ProteinInferenceDiagnosticCode.MALFORMED_CONTENT,
            ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT,
            ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY,
            ProteinInferenceDiagnosticCode.DANGLING_REFERENCE,
            ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH,
            ProteinInferenceDiagnosticCode.BUILD_MISMATCH,
            ProteinInferenceDiagnosticCode.CONTROLLED_VOCABULARY_MISMATCH,
            ProteinInferenceDiagnosticCode.UNIT_PROFILE_MISMATCH,
            ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH,
            ProteinInferenceDiagnosticCode.CROSS_SOURCE_DISAGREEMENT,
            ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED,
        },
    }
    observed: set[ProteinInferenceDiagnosticCode] = set()
    messages: set[str] = set()
    for action, codes in expected_actions.items():
        for code in codes:
            diagnostic = diagnostic_for(code, ("source.z", "source.a"))
            assert diagnostic.action is action
            assert diagnostic.source_ids == ("source.a", "source.z")
            assert diagnostic.message.endswith(".")
            assert diagnostic.diagnostic_id.startswith(f"diagnostic.m0303.{code.value}.")
            assert ProteinInferenceParseDiagnostic.model_validate(diagnostic, strict=True) == (
                diagnostic
            )
            observed.add(code)
            messages.add(diagnostic.message)
    assert observed == set(ProteinInferenceDiagnosticCode)
    assert len(messages) == len(ProteinInferenceDiagnosticCode)


@pytest.mark.contract
def test_diagnostic_precedence_is_reject_then_quarantine_then_abstain() -> None:
    reject = diagnostic_for(ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH)
    quarantine = diagnostic_for(ProteinInferenceDiagnosticCode.BUILD_MISMATCH)
    abstain = diagnostic_for(ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION)
    assert expected_disposition(()) is ProteinInferenceAdmissionDisposition.VALIDATED
    assert expected_disposition((abstain,)) is ProteinInferenceAdmissionDisposition.ABSTAINED
    assert expected_disposition((abstain, quarantine)) is (
        ProteinInferenceAdmissionDisposition.QUARANTINED
    )
    assert expected_disposition((abstain, quarantine, reject)) is (
        ProteinInferenceAdmissionDisposition.REJECTED
    )


@pytest.mark.contract
def test_result_contains_no_raw_content_or_scientific_inference_claims(
    canonical_scenario: Scenario,
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    rendered = canonical_result.model_dump_json()
    for source in canonical_scenario.sources.values():
        assert source.decode("utf-8", errors="ignore") not in rendered
    for forbidden in (
        "MPEPTIDEK",
        "scan=1",
        "group.synthetic.1",
        "ambiguity.synthetic.1",
        "protein_presence",
        "protein_absence",
        "protein_abundance",
        "activity_score",
        "treatment_recommendation",
    ):
        assert forbidden not in rendered
    assert not canonical_result.emits_complex_activity
    assert not canonical_result.infers_identity
    assert not canonical_result.infers_protein
    assert not canonical_result.infers_kinase_activity


@pytest.mark.contract
def test_duplicate_or_missing_exact_envelope_entries_are_rejected(
    canonical_result: ProteinInferenceRawAdmissionResult,
) -> None:
    for field in ("evidence", "limitations"):
        for mutation in ("duplicate", "remove"):
            payload = _payload(canonical_result)
            collection = cast("list[dict[str, Any]]", payload[field])
            if mutation == "duplicate":
                collection.append(deepcopy(collection[0]))
            else:
                collection.pop()
            payload["result_digest"] = result_payload_digest(payload)
            with pytest.raises(ValidationError):
                _validate_result(payload)
