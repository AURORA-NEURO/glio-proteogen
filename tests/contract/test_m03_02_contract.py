"""Public contract, canonicalization, and replay checks for M03-02."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from evals.m03_02.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m03_02 import (
    ArtifactClaimRole,
    ContractName,
    CopyNumberConcordanceState,
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
    ReconciliationDisposition,
    ReconciliationFindingAction,
    ReconciliationFindingCode,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    normalized_graph_payload,
    normalized_request,
    normalized_result_payload,
    policy_digest,
    reconciliation_evidence_index,
    resolved_graph_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    reconcile_protein_inference_identity_lineage,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_FORGED_DIGEST = "sha256:" + ("f" * 64)
_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "policy",
    "artifact-claim",
    "derivation",
    "cn-receipt",
    "graph",
    "receipt",
)


@pytest.fixture(scope="module")
def canonical_request() -> ReconcileProteinInferenceIdentityLineageRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def canonical_result(
    canonical_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> ProteinInferenceIdentityLineageResolution:
    return reconcile_protein_inference_identity_lineage(canonical_request)


@pytest.fixture(scope="module")
def finding_result() -> ProteinInferenceIdentityLineageResolution:
    return reconcile_protein_inference_identity_lineage(build_scenario_request("collision"))


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_request(payload: dict[str, Any]) -> ReconcileProteinInferenceIdentityLineageRequest:
    return ReconcileProteinInferenceIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_result(payload: dict[str, Any]) -> ProteinInferenceIdentityLineageResolution:
    return ProteinInferenceIdentityLineageResolution.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _set_path(payload: dict[str, Any], path: tuple[str | int, ...], value: object) -> None:
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value


def _assert_resigned_result_rejected(
    result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    payload = _payload(result)
    _set_path(payload, path, value)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="contradicts its embedded reconciliation request"):
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
        "moduleId": "GLIO-PROTEOGEN-M03-02",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawPayload": False,
        "identityInference": False,
        "upstreamRelabeling": False,
        "complexActivityInference": False,
        "copyNumberIdentityMerge": False,
    }
    for name in _SCHEMA_NAMES:
        schema = contract_json_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-02:1.0.0:"
            f"{name}"
        )
        metadata = deepcopy(expected_metadata)
        if name == "request":
            metadata["maxRequestBytes"] = 4 * 1024 * 1024
        assert schema["x-glio-contract"] == metadata
        _assert_recursive_objects_are_closed(schema)

    output = contract_json_schema("output")
    assert "result_digest" in cast("list[str]", output["required"])
    assert not {
        "protein_assignment",
        "protein_abundance",
        "complex_activity",
        "kinase_activity",
        "treatment_recommendation",
    }.intersection(cast("dict[str, Any]", output["properties"]))


@pytest.mark.contract
def test_all_closed_enumerations_are_exact_and_total() -> None:
    assert tuple(item.value for item in ArtifactClaimRole) == (
        "peptide_evidence_manifest",
        "protein_group_manifest",
        "ambiguity_manifest",
        "complex_activity_input_bundle",
    )
    assert tuple(item.value for item in CopyNumberConcordanceState) == (
        "concordant",
        "discordant",
        "indeterminate",
        "missing",
        "unsupported",
    )
    assert tuple(item.value for item in ReconciliationDisposition) == (
        "reconciled",
        "quarantined",
        "abstained",
    )
    assert tuple(item.value for item in ReconciliationFindingAction) == (
        "record",
        "quarantine",
        "abstain",
    )
    assert {item.value for item in ReconciliationFindingCode} == {
        "upstream_identity_unresolved",
        "upstream_protocol_nonconformant",
        "identity_not_evaluable",
        "identity_swap",
        "cross_patient_link",
        "artifact_lineage_collision",
        "duplicate_content_retained",
        "producer_identity_drift",
        "producer_protocol_drift",
        "producer_search_space_drift",
        "artifact_evidence_not_evaluable",
        "cn_discordant",
        "cn_not_evaluable",
    }


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        ((), {"unexpected": True}),
        (("policy",), {"unexpected": True}),
        (("artifact_claims", 0), {"unexpected": True}),
        (("derivations", 0), {"unexpected": True}),
        (("cn_receipts", 0), {"unexpected": True}),
    ],
)
def test_unknown_fields_are_rejected_at_every_m03_02_input_layer(
    canonical_request: ReconcileProteinInferenceIdentityLineageRequest,
    path: tuple[str | int, ...],
    replacement: dict[str, bool],
) -> None:
    payload = _payload(canonical_request)
    cursor: Any = payload
    for segment in path:
        cursor = cursor[segment]
    cursor.update(replacement)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("policy", "max_artifact_claims"), "16"),
        (("artifact_claims", 0, "declared_subject_component_ids"), "sha256:bad"),
        (("cn_receipts", 0, "informative_feature_count"), "12"),
        (("cn_receipts", 0, "concordant_feature_count"), 12.0),
        (("cn_receipts", 0, "discordant_feature_count"), False),
    ],
)
def test_strict_ingress_never_coerces_scalars_or_collections(
    canonical_request: ReconcileProteinInferenceIdentityLineageRequest,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    payload = _payload(canonical_request)
    _set_path(payload, path, replacement)
    with pytest.raises(ValidationError):
        _validate_request(payload)


@pytest.mark.contract
def test_request_canonicalization_is_typed_dict_parity_and_input_order_independent(
    canonical_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> None:
    payload = _payload(canonical_request)
    typed_digest = canonical_request_digest(canonical_request)
    assert typed_digest == canonical_request_digest(payload)
    assert canonical_json_bytes(normalized_request(canonical_request)) == (
        canonical_json_bytes(normalized_request(payload))
    )
    assert policy_digest(canonical_request.policy) == policy_digest(payload["policy"])
    assert configuration_digest(canonical_request.policy) == configuration_digest(
        payload["policy"]
    )

    for field in ("artifact_claims", "derivations", "cn_receipts"):
        cast("list[Any]", payload[field]).reverse()
    for claim in cast("list[dict[str, Any]]", payload["artifact_claims"]):
        cast("list[str]", claim["declared_subject_component_ids"]).reverse()
    for derivation in cast("list[dict[str, Any]]", payload["derivations"]):
        cast("list[str]", derivation["source_claim_ids"]).reverse()
    reordered = _validate_request(payload)
    assert canonical_request_digest(reordered) == typed_digest
    assert reconcile_protein_inference_identity_lineage(reordered) == (
        reconcile_protein_inference_identity_lineage(canonical_request)
    )


@pytest.mark.contract
def test_nested_subject_identifier_reordering_is_semantic() -> None:
    request = build_scenario_request()
    payload = _payload(request)
    subjects = [sha256_digest({"subject": "a"}), sha256_digest({"subject": "b"})]
    for claim in cast("list[dict[str, Any]]", payload["artifact_claims"]):
        claim["declared_subject_component_ids"] = subjects
    forward = _validate_request(payload)
    forward_result = reconcile_protein_inference_identity_lineage(forward)

    for claim in cast("list[dict[str, Any]]", payload["artifact_claims"]):
        cast("list[str]", claim["declared_subject_component_ids"]).reverse()
    reverse = _validate_request(payload)
    reverse_result = reconcile_protein_inference_identity_lineage(reverse)
    assert canonical_request_digest(forward) == canonical_request_digest(reverse)
    assert forward_result == reverse_result
    assert forward_result.model_dump_json() == reverse_result.model_dump_json()


@pytest.mark.contract
def test_graph_and_result_digest_helpers_have_typed_dict_parity(
    canonical_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    graph_payload = _payload(canonical_result.graph)
    result_payload = _payload(canonical_result)
    assert normalized_graph_payload(canonical_result.graph) == normalized_graph_payload(
        graph_payload
    )
    assert resolved_graph_digest(canonical_result.graph) == resolved_graph_digest(
        graph_payload
    )
    assert canonical_json_bytes(normalized_result_payload(canonical_result)) == (
        canonical_json_bytes(normalized_result_payload(result_payload))
    )
    assert result_payload_digest(canonical_result) == result_payload_digest(result_payload)


@pytest.mark.contract
def test_public_runtime_is_total_deterministic_and_full_result_equal(
    canonical_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> None:
    typed = reconcile_protein_inference_identity_lineage(canonical_request)
    mapping = reconcile_protein_inference_identity_lineage(
        canonical_request.model_dump(mode="python")
    )
    replay = reconcile_protein_inference_identity_lineage(canonical_request)
    assert typed == mapping == replay
    assert typed.model_dump_json() == mapping.model_dump_json() == replay.model_dump_json()


@pytest.mark.contract
def test_output_digest_is_required_nonzero_and_exact(
    canonical_result: ProteinInferenceIdentityLineageResolution,
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
        (("result_id",), "result.m0302.forged"),
        (("request_digest",), _FORGED_DIGEST),
        (("identity_resolution_digest",), _FORGED_DIGEST),
        (("protocol_result_digest",), _FORGED_DIGEST),
        (("policy_digest",), _FORGED_DIGEST),
        (("configuration_digest",), _FORGED_DIGEST),
        (("graph_digest",), _FORGED_DIGEST),
    ],
)
def test_resigned_result_cannot_forge_any_top_level_binding(
    canonical_result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "identity_resolution_digest",
        "protocol_result_digest",
        "protocol_schema_digest",
        "search_space_digest",
        "policy_digest",
        "configuration_digest",
        "graph_digest",
    ],
)
def test_resigned_result_cannot_forge_any_receipt_digest(
    canonical_result: ProteinInferenceIdentityLineageResolution,
    field: str,
) -> None:
    _assert_resigned_result_rejected(canonical_result, ("receipt", field), _FORGED_DIGEST)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("receipt", "parent_target"), "kinase_activity"),
        (("receipt", "emits_complex_activity"), True),
        (("receipt", "infers_identity"), True),
        (("receipt", "disposition"), "abstained"),
        (("disposition",), "abstained"),
        (("parent_target",), "kinase_activity"),
        (("emits_complex_activity",), True),
        (("infers_identity",), True),
        (("human_review_required",), True),
        (("completed_at",), "2026-08-12T13:00:01Z"),
    ],
)
def test_result_cannot_forge_disposition_ownership_review_or_time(
    canonical_result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    payload = _payload(canonical_result)
    _set_path(payload, path, replacement)
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
        (("uncertainty", "support", "rationale"), "Forged decision rationale."),
        (("uncertainty", "transport", "rationale"), "Forged transport rationale."),
        (("uncertainty", "sensitivity_notes", 0), "Forged sensitivity note."),
    ],
)
def test_resigned_result_cannot_forge_support_or_any_uncertainty_dimension(
    canonical_result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("provenance", "activity_id"), "activity.m0302.forged"),
        (("provenance", "actor_id"), "actor.m0302.forged"),
        (("provenance", "module_id"), "GLIO-PROTEOGEN-M03-99"),
        (("provenance", "module_version"), "9.0.0"),
        (("provenance", "generated_at"), "2026-08-12T13:00:01Z"),
        (("provenance", "configuration_digest"), _FORGED_DIGEST),
        (("provenance", "consent_decision_id"), "decision.m0302.forged"),
        (("provenance", "consent_state"), "withheld"),
        (("provenance", "consent_policy_version"), "9.0.0"),
        (("provenance", "consent_evidence_digest"), _FORGED_DIGEST),
        (("provenance", "input_digests", 0), _FORGED_DIGEST),
        (("provenance", "control_decisions", 0, "decision_id"), "decision.forged"),
        (("provenance", "control_decisions", 0, "state"), "rejected"),
        (("provenance", "control_decisions", 0, "policy_version"), "9.0.0"),
        (("provenance", "control_decisions", 0, "evidence_digest"), _FORGED_DIGEST),
    ],
)
def test_resigned_result_cannot_forge_provenance_or_controls(
    canonical_result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("evidence", 0, "role"), "counter_evidence"),
        (("evidence", 0, "claim"), "Forged evidence claim."),
        (("evidence", 0, "reference", "digest"), _FORGED_DIGEST),
        (("limitations", 0, "code"), "forged_limitation"),
        (("limitations", 0, "statement"), "Forged authority expansion."),
    ],
)
def test_resigned_result_cannot_forge_evidence_or_limitations(
    canonical_result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(canonical_result, path, replacement)


@pytest.mark.contract
def test_evidence_index_and_provenance_input_set_are_exact(
    canonical_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    result = canonical_result
    assert tuple(sorted(result.evidence, key=canonical_json_bytes)) == tuple(
        sorted(reconciliation_evidence_index(result.request), key=canonical_json_bytes)
    )
    expected_inputs = {
        result.request_digest,
        result.identity_resolution_digest,
        result.protocol_result_digest,
        result.request.protocol_result.protocol_digest,
        result.request.protocol_result.receipt.search_space_digest,
        result.policy_digest,
        result.configuration_digest,
        result.graph_digest,
        *(item.reference.digest for item in result.evidence),
        *(item.evidence_digest for item in result.provenance.control_decisions),
    }
    assert result.provenance.input_digests == tuple(sorted(expected_inputs))
    assert len(result.evidence) == len(
        {
            (
                item.reference.artifact_id,
                item.reference.version,
                item.reference.digest,
                item.reference.media_type,
            )
            for item in result.evidence
        }
    )


@pytest.mark.contract
def test_resigned_result_cannot_duplicate_or_remove_evidence_or_limitations(
    canonical_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    for field in ("evidence", "limitations"):
        for action in ("duplicate", "remove"):
            payload = _payload(canonical_result)
            collection = cast("list[dict[str, Any]]", payload[field])
            if action == "duplicate":
                collection.append(deepcopy(collection[0]))
            else:
                collection.pop()
            payload["result_digest"] = result_payload_digest(payload)
            with pytest.raises(ValidationError):
                _validate_result(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("findings", 0, "code"), "producer_identity_drift"),
        (("findings", 0, "action"), "record"),
        (("findings", 0, "claim_ids", 0), "claim.bundle"),
        (("findings", 0, "evidence_basis_digest"), _FORGED_DIGEST),
    ],
)
def test_resigned_result_cannot_forge_findings(
    finding_result: ProteinInferenceIdentityLineageResolution,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(finding_result, path, replacement)


@pytest.mark.contract
def test_result_request_is_replayed_not_merely_outer_signed(
    canonical_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    payload = _payload(canonical_result)
    payload["request"]["supersedes_result_digest"] = _FORGED_DIGEST
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="contradicts its embedded reconciliation request"):
        _validate_result(payload)


@pytest.mark.contract
def test_semantic_output_collections_reorder_with_the_same_result_digest(
    finding_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    payload = _payload(finding_result)
    for path in (
        ("request", "artifact_claims"),
        ("request", "derivations"),
        ("graph", "artifacts"),
        ("graph", "derivations"),
        ("findings",),
        ("evidence",),
        ("limitations",),
        ("provenance", "input_digests"),
        ("provenance", "control_decisions"),
        ("uncertainty", "sensitivity_notes"),
    ):
        cursor: Any = payload
        for segment in path:
            cursor = cursor[segment]
        cursor.reverse()
    for finding in cast("list[dict[str, Any]]", payload["findings"]):
        cast("list[str]", finding["claim_ids"]).reverse()
        cast("list[str]", finding["derivation_ids"]).reverse()
    validated = _validate_result(payload)
    assert validated.result_digest == finding_result.result_digest
    assert result_payload_digest(validated) == finding_result.result_digest


@pytest.mark.contract
def test_unknown_fields_are_rejected_throughout_result_envelope(
    canonical_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    paths = (
        (),
        ("receipt",),
        ("graph",),
        ("graph", "artifacts", 0),
        ("graph", "derivations", 0),
        ("support",),
        ("uncertainty",),
        ("provenance",),
        ("evidence", 0),
        ("limitations", 0),
    )
    for path in paths:
        payload = _payload(canonical_result)
        cursor: Any = payload
        for segment in path:
            cursor = cursor[segment]
        cursor["unexpected"] = True
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _validate_result(payload)
