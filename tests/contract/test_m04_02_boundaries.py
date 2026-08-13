"""Adversarial boundary tests for M04-02 identity-lineage reconciliation."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any, cast

import pytest
from evals.m04_02.run import build_scenario_request

from glio_proteogen.contracts.m04_02 import (
    M0402_MAX_APPROVED_METHODS,
    M0402_MAX_ARTIFACT_CLAIMS,
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    M0402_MAX_DERIVATION_SOURCES,
    M0402_MAX_EVIDENCE,
    ProteoformIdentityLineageFinding,
    ProteoformIdentityLineageFindingAction,
    ProteoformIdentityLineageFindingCode,
    ProteoformIdentityLineagePolicy,
    ProteoformIdentityLineageReceipt,
    ProteoformIdentityLineageResolution,
    ProteoformLineageArtifactClaim,
    ProteoformLineageArtifactDerivation,
    ProteoformLineageArtifactRole,
    ProteoformLineageDisposition,
    ProteoformLineageEvidenceState,
    ReconcileProteoformIdentityLineageRequest,
    ResolvedProteoformIdentityLineageGraph,
    canonical_request_digest,
    configuration_digest,
    derive_proteoform_reconciliation,
    expected_receipt,
    expected_support,
    receipt_digest,
    resolved_graph_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    M0402Plugin,
    M0402Service,
    ProteoformIdentityLineageAuthorizationError,
    preflight_proteoform_identity_lineage_authorization,
    reconcile_proteoform_identity_lineage,
)


def _oid(namespace: str, label: str) -> str:
    return f"{namespace}.{sha256_digest(label).removeprefix('sha256:')}"


def _request_payload(case_id: str = "canonical_all_seven_entity_chain") -> dict[str, Any]:
    return deepcopy(build_scenario_request(case_id).model_dump(mode="python"))


def _rebind_policy(payload: dict[str, Any]) -> None:
    policy = ProteoformIdentityLineagePolicy.model_validate(payload["policy"], strict=True)
    references = cast("dict[str, Any]", payload["context"])["references"]
    approved = cast("dict[str, Any]", references["approved_configuration"])
    cast("dict[str, Any]", approved["evidence"])["digest"] = configuration_digest(policy)


@pytest.mark.contract
def test_canonical_request_strict_json_round_trip_is_total() -> None:
    canonical = build_scenario_request()
    reconstructed = ReconcileProteoformIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(canonical.model_dump(mode="json")), strict=True
    )
    assert reconstructed == canonical


@pytest.mark.contract
@pytest.mark.parametrize(
    ("container", "field", "message"),
    [
        ("identity_resolution", "resolution_digest", "M01-02 derived digests"),
        ("protocol_result", "result_digest", "M04-01 derived digests"),
    ],
)
def test_embedded_zero_digest_sentinel_is_rejected_from_strict_json(
    container: str,
    field: str,
    message: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="json")
    cast("dict[str, Any]", payload[container])[field] = "sha256:" + ("0" * 64)
    with pytest.raises(ValueError, match=message):
        ReconcileProteoformIdentityLineageRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("method_identity", "method identities"),
        ("evidence_digest", "evidence digests"),
        ("evidence_identity", "evidence artifact identities"),
        ("policy_media", "exact role"),
    ],
)
def test_policy_rejects_ambiguous_authority_and_evidence(
    mutation: str,
    message: str,
) -> None:
    payload = _request_payload("semantic_reorder_full_result_equality")["policy"]
    policy = cast("dict[str, Any]", payload)
    methods = cast("tuple[dict[str, Any], ...]", policy["approved_derivation_methods"])
    if mutation == "method_identity":
        methods[1]["method_id"] = methods[0]["method_id"]
        methods[1]["version"] = methods[0]["version"]
    elif mutation == "evidence_digest":
        cast("dict[str, Any]", methods[0]["evidence"])["digest"] = cast(
            "dict[str, Any]", policy["evidence"]
        )["digest"]
    elif mutation == "evidence_identity":
        evidence = cast("dict[str, Any]", methods[0]["evidence"])
        policy_evidence = cast("dict[str, Any]", policy["evidence"])
        evidence["artifact_id"] = policy_evidence["artifact_id"]
        evidence["version"] = policy_evidence["version"]
    else:
        cast("dict[str, Any]", policy["evidence"])["media_type"] = (
            "application/vnd.glio-proteogen.control+json"
        )
    with pytest.raises(ValueError, match=message):
        ProteoformIdentityLineagePolicy.model_validate(policy, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("model", "mutation", "message"),
    [
        ("claim", "duplicate_subject", "subject component identifiers"),
        ("claim", "wrong_media", "exact role"),
        ("derivation", "duplicate_source", "source claim identifiers"),
        ("derivation", "self_target", "consume its target"),
    ],
)
def test_claim_and_derivation_models_reject_ambiguous_structure(
    model: str,
    mutation: str,
    message: str,
) -> None:
    request = build_scenario_request()
    validator: type[ProteoformLineageArtifactClaim | ProteoformLineageArtifactDerivation]
    if model == "claim":
        payload = request.artifact_claims[0].model_dump(mode="python")
        validator = ProteoformLineageArtifactClaim
        if mutation == "duplicate_subject":
            subject = payload["declared_subject_component_ids"][0]
            payload["declared_subject_component_ids"] = (subject, subject)
        else:
            cast("dict[str, Any]", payload["artifact"])["media_type"] = (
                "application/vnd.glio-proteogen.control+json"
            )
    else:
        payload = request.derivations[0].model_dump(mode="python")
        validator = ProteoformLineageArtifactDerivation
        sources = payload["source_claim_ids"]
        if mutation == "duplicate_source":
            payload["source_claim_ids"] = (*sources, sources[0])
        else:
            payload["source_claim_ids"] = (*sources, payload["target_claim_id"])
    with pytest.raises(ValueError, match=message):
        validator.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("request_id", "request identifier"),
        ("future_policy", "policy cannot postdate"),
        ("future_upstream", "upstream result cannot postdate"),
        ("identity_binding", "identity chain"),
        ("configuration", "approved configuration"),
        ("duplicate_claim", "artifact claim identifiers"),
        ("unknown_anchor", "unknown identity entity"),
        ("physical_anchor", "derived-object anchors"),
        ("missing_role", "four source roles"),
        ("dangling_source", "unknown claim"),
        ("source_cap", "sources exceed"),
        ("unapproved_method", "method is not approved"),
        ("wrong_target", "target the exact input bundle"),
        ("disconnected", "consume every non-bundle claim"),
        ("submitted_evidence_conflict", "submitted evidence identity"),
        ("claim_control_conflict", "control evidence identity"),
        ("claim_upstream_conflict", "upstream evidence content"),
    ],
)
def test_request_relational_forgery_matrix(  # noqa: C901, PLR0912, PLR0915
    mutation: str,
    message: str,
) -> None:
    case_id = (
        "same_binding_scope_collision"
        if mutation in {"source_cap", "disconnected"}
        else ("canonical_all_seven_entity_chain")
    )
    payload = _request_payload(case_id)
    context = cast("dict[str, Any]", payload["context"])
    references = cast("dict[str, Any]", context["references"])
    policy = cast("dict[str, Any]", payload["policy"])
    claims = list(cast("tuple[dict[str, Any], ...]", payload["artifact_claims"]))
    derivation = cast("tuple[dict[str, Any], ...]", payload["derivations"])[0]

    if mutation == "request_id":
        payload["request_id"] = _oid("request", "split")
    elif mutation == "future_policy":
        policy["reviewed_at"] = context["occurred_at"] + timedelta(microseconds=1)
    elif mutation == "future_upstream":
        context["occurred_at"] -= timedelta(hours=1)
        policy["reviewed_at"] = context["occurred_at"]
        _rebind_policy(payload)
    elif mutation == "identity_binding":
        cast("dict[str, Any]", references["identity_lineage"])["binding_digest"] = sha256_digest(
            "stale identity"
        )
    elif mutation == "configuration":
        cast(
            "dict[str, Any]",
            cast("dict[str, Any]", references["approved_configuration"])["evidence"],
        )["digest"] = sha256_digest("stale config")
    elif mutation == "duplicate_claim":
        claims[-1]["claim_id"] = claims[0]["claim_id"]
        payload["artifact_claims"] = tuple(claims)
    elif mutation in {"unknown_anchor", "physical_anchor"}:
        claims[0]["identity_entity_id"] = "missing" if mutation == "unknown_anchor" else "pat-a"
        payload["artifact_claims"] = tuple(claims)
    elif mutation == "missing_role":
        genome = next(
            item for item in claims if item["role"] is ProteoformLineageArtifactRole.GENOME_MANIFEST
        )
        mass = next(
            item
            for item in claims
            if item["role"] is ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
        )
        genome["role"] = ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
        cast("dict[str, Any]", genome["artifact"])["media_type"] = cast(
            "dict[str, Any]", mass["artifact"]
        )["media_type"]
        payload["artifact_claims"] = tuple(claims)
    elif mutation == "dangling_source":
        derivation["source_claim_ids"] = (
            _oid("claim", "missing"),
            *derivation["source_claim_ids"][1:],
        )
    elif mutation == "source_cap":
        policy["max_derivation_sources"] = 4
        _rebind_policy(payload)
    elif mutation == "unapproved_method":
        derivation["method_id"] = _oid("method", "unapproved")
    elif mutation == "wrong_target":
        former_target = derivation["target_claim_id"]
        sources = tuple(derivation["source_claim_ids"])
        derivation["target_claim_id"] = sources[0]
        derivation["source_claim_ids"] = (*sources[1:], former_target)
    elif mutation == "disconnected":
        derivation["source_claim_ids"] = tuple(derivation["source_claim_ids"][:-1])
    elif mutation == "submitted_evidence_conflict":
        derivation_evidence = cast("dict[str, Any]", derivation["evidence"])
        policy_evidence = cast("dict[str, Any]", policy["evidence"])
        derivation_evidence["artifact_id"] = policy_evidence["artifact_id"]
        derivation_evidence["version"] = policy_evidence["version"]
    elif mutation == "claim_control_conflict":
        control = cast("dict[str, Any]", cast("dict[str, Any]", references["consent"])["evidence"])
        artifact = cast("dict[str, Any]", claims[0]["artifact"])
        artifact["artifact_id"] = control["artifact_id"]
        artifact["version"] = control["version"]
        payload["artifact_claims"] = tuple(claims)
    else:
        upstream = cast(
            "dict[str, Any]",
            cast(
                "tuple[dict[str, Any], ...]",
                cast("dict[str, Any]", payload["protocol_result"])["evidence"],
            )[1]["reference"],
        )
        artifact = cast("dict[str, Any]", claims[0]["artifact"])
        artifact["artifact_id"] = upstream["artifact_id"]
        artifact["version"] = upstream["version"]
        payload["artifact_claims"] = tuple(claims)

    with pytest.raises(ValueError, match=message):
        ReconcileProteoformIdentityLineageRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_semantic_result_reorder_reconstructs_to_complete_typed_equality() -> None:
    canonical = reconcile_proteoform_identity_lineage(
        build_scenario_request("semantic_reorder_full_result_equality")
    )
    payload = canonical.model_dump(mode="json")
    request = cast("dict[str, Any]", payload["request"])
    cast("list[object]", request["artifact_claims"]).reverse()
    cast("list[object]", request["derivations"]).reverse()
    policy = cast("dict[str, Any]", request["policy"])
    cast("list[object]", policy["approved_derivation_methods"]).reverse()
    for claim in cast("list[dict[str, Any]]", request["artifact_claims"]):
        cast("list[object]", claim["declared_subject_component_ids"]).reverse()
    for derivation in cast("list[dict[str, Any]]", request["derivations"]):
        cast("list[object]", derivation["source_claim_ids"]).reverse()

    graph = cast("dict[str, Any]", payload["graph"])
    cast("list[object]", graph["artifacts"]).reverse()
    cast("list[object]", graph["derivations"]).reverse()
    for artifact in cast("list[dict[str, Any]]", graph["artifacts"]):
        cast("list[object]", artifact["declared_subject_component_ids"]).reverse()
        cast("list[object]", artifact["resolved_subject_component_ids"]).reverse()
        cast("list[object]", artifact["finding_codes"]).reverse()
    for derivation in cast("list[dict[str, Any]]", graph["derivations"]):
        cast("list[object]", derivation["source_claim_ids"]).reverse()
        cast("list[object]", derivation["propagated_subject_component_ids"]).reverse()
    for field in ("findings", "evidence", "limitations"):
        cast("list[object]", payload[field]).reverse()
    for finding in cast("list[dict[str, Any]]", payload["findings"]):
        cast("list[object]", finding["claim_ids"]).reverse()
        cast("list[object]", finding["derivation_ids"]).reverse()
    provenance = cast("dict[str, Any]", payload["provenance"])
    cast("list[object]", provenance["input_digests"]).reverse()
    cast("list[object]", provenance["control_decisions"]).reverse()
    uncertainty = cast("dict[str, Any]", payload["uncertainty"])
    cast("list[object]", uncertainty["sensitivity_notes"]).reverse()

    reconstructed = ProteoformIdentityLineageResolution.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert reconstructed == canonical


@pytest.mark.contract
def test_duplicate_content_across_distinct_roles_is_retained_without_quarantine() -> None:
    payload = deepcopy(build_scenario_request().model_dump(mode="python"))
    claims = cast("tuple[dict[str, Any], ...]", payload["artifact_claims"])
    first_artifact = cast("dict[str, Any]", claims[0]["artifact"])
    second_artifact = cast("dict[str, Any]", claims[1]["artifact"])
    second_artifact["digest"] = first_artifact["digest"]
    request = ReconcileProteoformIdentityLineageRequest.model_validate(payload, strict=True)
    graph, findings, disposition = derive_proteoform_reconciliation(request)
    assert len(graph.artifacts) == len(request.artifact_claims)
    assert disposition is ProteoformLineageDisposition.RECONCILED
    assert {finding.code for finding in findings} == {
        ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED
    }


@pytest.mark.contract
@pytest.mark.parametrize(
    "state",
    [
        ProteoformLineageEvidenceState.MISSING,
        ProteoformLineageEvidenceState.INDETERMINATE,
        ProteoformLineageEvidenceState.UNSUPPORTED,
        ProteoformLineageEvidenceState.REDACTED,
    ],
)
def test_all_nonobserved_artifact_states_abstain_without_inference(
    state: ProteoformLineageEvidenceState,
) -> None:
    request = build_scenario_request(f"{state.value}_abstains")
    graph, findings, disposition = derive_proteoform_reconciliation(request)
    assert disposition is ProteoformLineageDisposition.ABSTAINED
    assert {finding.code for finding in findings} == {
        ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE
    }
    assert {artifact.evidence_state for artifact in graph.artifacts} == {state}


@pytest.mark.contract
@pytest.mark.parametrize(
    ("case_id", "expected_disposition", "expected_codes"),
    [
        (
            "producer_identity_and_protocol_drift",
            ProteoformLineageDisposition.QUARANTINED,
            {
                ProteoformIdentityLineageFindingCode.PRODUCER_IDENTITY_DRIFT,
                ProteoformIdentityLineageFindingCode.PRODUCER_PROTOCOL_DRIFT,
            },
        ),
        (
            "producer_reference_and_coordinate_drift",
            ProteoformLineageDisposition.QUARANTINED,
            {
                ProteoformIdentityLineageFindingCode.PRODUCER_REFERENCE_BUNDLE_DRIFT,
                ProteoformIdentityLineageFindingCode.PRODUCER_COORDINATE_POLICY_DRIFT,
            },
        ),
        (
            "same_binding_scope_collision",
            ProteoformLineageDisposition.QUARANTINED,
            {ProteoformIdentityLineageFindingCode.BINDING_SCOPE_COLLISION},
        ),
        (
            "artifact_identity_digest_collision",
            ProteoformLineageDisposition.QUARANTINED,
            {ProteoformIdentityLineageFindingCode.ARTIFACT_IDENTITY_COLLISION},
        ),
        (
            "physical_cross_patient_link",
            ProteoformLineageDisposition.QUARANTINED,
            {
                ProteoformIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION,
                ProteoformIdentityLineageFindingCode.CROSS_PATIENT_LINK,
                ProteoformIdentityLineageFindingCode.IDENTITY_SWAP,
            },
        ),
        (
            "valid_unresolved_identity_abstains",
            ProteoformLineageDisposition.ABSTAINED,
            {ProteoformIdentityLineageFindingCode.UPSTREAM_IDENTITY_UNRESOLVED},
        ),
        (
            "valid_quarantined_m0401_quarantines",
            ProteoformLineageDisposition.QUARANTINED,
            {ProteoformIdentityLineageFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT},
        ),
    ],
)
def test_closed_finding_matrix_and_precedence(
    case_id: str,
    expected_disposition: ProteoformLineageDisposition,
    expected_codes: set[ProteoformIdentityLineageFindingCode],
) -> None:
    _, findings, disposition = derive_proteoform_reconciliation(build_scenario_request(case_id))
    assert disposition is expected_disposition
    assert {finding.code for finding in findings} == expected_codes


@pytest.mark.contract
def test_quarantine_precedes_simultaneous_abstention() -> None:
    payload = _request_payload("missing_abstains")
    claims = cast("tuple[dict[str, Any], ...]", payload["artifact_claims"])
    claims[0]["producer_identity_resolution_digest"] = sha256_digest("drift")
    request = ReconcileProteoformIdentityLineageRequest.model_validate(payload, strict=True)
    _, findings, disposition = derive_proteoform_reconciliation(request)
    assert disposition is ProteoformLineageDisposition.QUARANTINED
    assert {
        ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,
        ProteoformIdentityLineageFindingCode.PRODUCER_IDENTITY_DRIFT,
    }.issubset({finding.code for finding in findings})


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("evidence_without_code", "evidence-state finding"),
        ("code_without_evidence", "evidence-state finding"),
        ("duplicate_without_code", "duplicate-content findings"),
        ("upstream_code", "non-artifact finding code"),
        ("stale_digest", "graph digest"),
    ],
)
def test_standalone_graph_rejects_resigned_relational_forgery(
    mutation: str,
    message: str,
) -> None:
    request = build_scenario_request()
    graph, _, _ = derive_proteoform_reconciliation(request)
    payload = graph.model_dump(mode="python")
    artifacts = list(cast("tuple[dict[str, Any], ...]", payload["artifacts"]))
    if mutation == "evidence_without_code":
        artifacts[0]["evidence_state"] = ProteoformLineageEvidenceState.MISSING
    elif mutation == "code_without_evidence":
        artifacts[0]["finding_codes"] = (
            ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,
        )
    elif mutation == "duplicate_without_code":
        artifacts[1]["artifact_digest"] = artifacts[0]["artifact_digest"]
    elif mutation == "upstream_code":
        artifacts[0]["finding_codes"] = (
            ProteoformIdentityLineageFindingCode.UPSTREAM_IDENTITY_UNRESOLVED,
        )
    else:
        payload["physical_graph_digest"] = sha256_digest("stale physical graph")
    payload["artifacts"] = tuple(artifacts)
    if mutation != "stale_digest":
        payload["graph_digest"] = resolved_graph_digest(payload)
    with pytest.raises(ValueError, match=message):
        ResolvedProteoformIdentityLineageGraph.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_code", "finding codes must be unique"),
        ("stale_digest", "receipt digest"),
    ],
)
def test_standalone_receipt_rejects_duplicate_or_stale_content(
    mutation: str,
    message: str,
) -> None:
    request = build_scenario_request("missing_abstains")
    graph, findings, disposition = derive_proteoform_reconciliation(request)
    receipt = expected_receipt(request, graph, disposition, findings=findings)
    payload = receipt.model_dump(mode="python")
    if mutation == "duplicate_code":
        payload["finding_codes"] = (*payload["finding_codes"], payload["finding_codes"][0])
        payload["receipt_digest"] = receipt_digest(payload)
    else:
        payload["policy_digest"] = sha256_digest("stale policy")
    with pytest.raises(ValueError, match=message):
        ProteoformIdentityLineageReceipt.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_artifact_id", "resolved artifact identifiers"),
        ("missing_role", "exact five-role shape"),
        ("dangling_endpoint", "endpoints are not closed"),
        ("wrong_topology", "closed artifact topology"),
        ("wrong_propagation", "subject propagation"),
        ("unmarked_lineage_collision", "physical-lineage paths as a collision"),
    ],
)
def test_standalone_graph_structural_matrix(
    mutation: str,
    message: str,
) -> None:
    request = build_scenario_request(
        "physical_cross_patient_link"
        if mutation == "unmarked_lineage_collision"
        else "canonical_all_seven_entity_chain"
    )
    graph, _, _ = derive_proteoform_reconciliation(request)
    payload = graph.model_dump(mode="python")
    artifacts = list(cast("tuple[dict[str, Any], ...]", payload["artifacts"]))
    derivation = cast("tuple[dict[str, Any], ...]", payload["derivations"])[0]
    if mutation == "duplicate_artifact_id":
        artifacts[1]["claim_id"] = artifacts[0]["claim_id"]
    elif mutation == "missing_role":
        artifacts[0]["role"] = ProteoformLineageArtifactRole.GENOME_MANIFEST
    elif mutation == "dangling_endpoint":
        derivation["source_claim_ids"] = (
            _oid("claim", "dangling"),
            *derivation["source_claim_ids"][1:],
        )
    elif mutation == "wrong_topology":
        derivation["source_claim_ids"] = tuple(derivation["source_claim_ids"][:-1])
    elif mutation == "wrong_propagation":
        derivation["propagated_subject_component_ids"] = (sha256_digest("wrong subject"),)
    else:
        for artifact in artifacts:
            artifact["finding_codes"] = tuple(
                code
                for code in artifact["finding_codes"]
                if code is not ProteoformIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION
            )
    payload["artifacts"] = tuple(artifacts)
    payload["graph_digest"] = resolved_graph_digest(payload)
    with pytest.raises(ValueError, match=message):
        ResolvedProteoformIdentityLineageGraph.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    "mutation",
    [
        "result_id",
        "request_digest",
        "identity_digest",
        "protocol_digest",
        "policy_digest",
        "configuration_digest",
        "graph_digest",
        "receipt",
        "graph",
        "finding",
        "disposition_envelope",
        "provenance",
        "evidence",
        "limitations",
        "completed_at",
    ],
)
def test_resigned_result_relational_forgery_matrix(  # noqa: C901, PLR0912
    mutation: str,
) -> None:
    canonical = reconcile_proteoform_identity_lineage(build_scenario_request())
    payload = canonical.model_dump(mode="python")
    forged = sha256_digest({"forged": mutation})
    if mutation == "result_id":
        payload["result_id"] = f"result.m0402.{forged.removeprefix('sha256:')}"
    elif mutation == "request_digest":
        payload["request_digest"] = forged
    elif mutation == "identity_digest":
        payload["identity_resolution_digest"] = forged
    elif mutation == "protocol_digest":
        payload["protocol_result_digest"] = forged
    elif mutation == "policy_digest":
        payload["policy_digest"] = forged
    elif mutation == "configuration_digest":
        payload["configuration_digest"] = forged
    elif mutation == "graph_digest":
        payload["graph_digest"] = forged
    elif mutation == "receipt":
        receipt = cast("dict[str, Any]", payload["receipt"])
        receipt["policy_digest"] = forged
        receipt["receipt_digest"] = receipt_digest(receipt)
    elif mutation == "graph":
        graph = cast("dict[str, Any]", payload["graph"])
        graph["physical_graph_digest"] = forged
        graph["graph_digest"] = resolved_graph_digest(graph)
        payload["graph_digest"] = graph["graph_digest"]
    elif mutation == "finding":
        payload["findings"] = (
            ProteoformIdentityLineageFinding(
                code=ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED,
                action=ProteoformIdentityLineageFindingAction.RECORD,
                evidence_basis_digest=forged,
            ),
        )
    elif mutation == "disposition_envelope":
        payload["disposition"] = ProteoformLineageDisposition.ABSTAINED
        payload["support"] = expected_support(ProteoformLineageDisposition.ABSTAINED)
        payload["human_review_required"] = True
    elif mutation == "provenance":
        provenance = cast("dict[str, Any]", payload["provenance"])
        provenance["input_digests"] = (*provenance["input_digests"], forged)
    elif mutation == "evidence":
        evidence = list(cast("tuple[dict[str, Any], ...]", payload["evidence"]))
        cast("dict[str, Any]", evidence[0]["reference"])["digest"] = forged
        payload["evidence"] = tuple(evidence)
    elif mutation == "limitations":
        limitations = list(cast("tuple[dict[str, Any], ...]", payload["limitations"]))
        limitations[0]["statement"] = "forged boundary"
        payload["limitations"] = tuple(limitations)
    else:
        payload["completed_at"] += timedelta(microseconds=1)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="embedded reconciliation request"):
        ProteoformIdentityLineageResolution.model_validate(payload, strict=True)


@pytest.mark.contract
def test_stale_result_digest_is_rejected_independently() -> None:
    canonical = reconcile_proteoform_identity_lineage(build_scenario_request())
    payload = canonical.model_dump(mode="python")
    payload["result_digest"] = sha256_digest("stale result")
    with pytest.raises(ValueError, match="result digest"):
        ProteoformIdentityLineageResolution.model_validate(payload, strict=True)


@pytest.mark.contract
def test_direct_service_and_plugin_json_boundaries_are_identical() -> None:
    request = build_scenario_request()
    service = M0402Service()
    plugin = M0402Plugin(service)
    direct = reconcile_proteoform_identity_lineage(request)
    assert service.validate_request(request) == request
    assert service.execute(request) == direct
    token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))
    assert token.request == request
    assert plugin.run(token) == direct
    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M04-02"
    assert descriptor.gate == "G0"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


@pytest.mark.contract
@pytest.mark.parametrize(
    ("role", "state"),
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
def test_each_denied_control_fails_preflight_before_governed_material(
    role: str,
    state: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="json")
    references = cast("dict[str, Any]", cast("dict[str, Any]", payload["context"])["references"])
    cast("dict[str, Any]", references[role])["state"] = state
    payload["artifact_claims"] = _ExplodingValue()
    payload["identity_resolution"] = _ExplodingValue()
    with pytest.raises(ProteoformIdentityLineageAuthorizationError):
        preflight_proteoform_identity_lineage_authorization(payload)


class _ExplodingValue:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(name)

    def __iter__(self) -> Any:
        raise AssertionError("iterated")


class _HostileDict(dict[str, Any]):
    traversals = 0

    def get(self, key: str, default: object = None) -> object:
        type(self).traversals += 1
        raise AssertionError((key, default))

    def __getitem__(self, key: str) -> Any:
        type(self).traversals += 1
        raise AssertionError(key)

    def items(self) -> Any:
        type(self).traversals += 1
        raise AssertionError("items")

    def __iter__(self) -> Any:
        type(self).traversals += 1
        raise AssertionError("iter")


@pytest.mark.contract
def test_builtin_dict_subclass_overrides_are_ignored_across_runtime() -> None:
    canonical = reconcile_proteoform_identity_lineage(build_scenario_request())
    hostile = _HostileDict(build_scenario_request().model_dump(mode="python"))
    _HostileDict.traversals = 0
    preflight_proteoform_identity_lineage_authorization(hostile)
    assert reconcile_proteoform_identity_lineage(hostile) == canonical
    assert _HostileDict.traversals == 0


@pytest.mark.contract
def test_arbitrary_mapping_and_accessor_exception_fail_closed() -> None:
    class ArbitraryMapping:
        @property
        def context(self) -> object:
            raise AssertionError("accessed")

    with pytest.raises(ProteoformIdentityLineageAuthorizationError):
        preflight_proteoform_identity_lineage_authorization(ArbitraryMapping())


@pytest.mark.contract
def test_maximum_shape_executes_at_exact_caps() -> None:
    request = build_scenario_request("maximum_shape_accepted")
    result = reconcile_proteoform_identity_lineage(request)
    assert len(request.artifact_claims) == M0402_MAX_ARTIFACT_CLAIMS
    assert len(request.derivations[0].source_claim_ids) == M0402_MAX_DERIVATION_SOURCES
    assert len(request.policy.approved_derivation_methods) == M0402_MAX_APPROVED_METHODS
    assert len(result.evidence) == M0402_MAX_EVIDENCE
    assert (
        len(canonical_json_bytes(request.model_dump(mode="json")))
        < M0402_MAX_CANONICAL_REQUEST_BYTES
    )
    assert result.disposition is ProteoformLineageDisposition.QUARANTINED


@pytest.mark.contract
def test_supersession_digest_is_explicit_in_provenance() -> None:
    payload = _request_payload()
    prior = sha256_digest("prior result")
    payload["supersedes_result_digest"] = prior
    request = ReconcileProteoformIdentityLineageRequest.model_validate(payload, strict=True)
    result = reconcile_proteoform_identity_lineage(request)
    assert prior in result.provenance.input_digests


@pytest.mark.contract
def test_embedded_identity_semantic_reorder_reconstructs_to_request_equality() -> None:
    canonical = build_scenario_request("semantic_reorder_full_result_equality")
    payload = canonical.model_dump(mode="json")
    identity = cast("dict[str, Any]", payload["identity_resolution"])
    for field in ("components", "assertion_dispositions", "issues", "evidence", "limitations"):
        cast("list[object]", identity[field]).reverse()
    graph = cast("dict[str, Any]", identity["graph"])
    cast("list[object]", graph["nodes"]).reverse()
    cast("list[object]", graph["operations"]).reverse()
    provenance = cast("dict[str, Any]", identity["provenance"])
    cast("list[object]", provenance["input_digests"]).reverse()
    cast("list[object]", provenance["control_decisions"]).reverse()
    for component in cast("list[dict[str, Any]]", identity["components"]):
        cast("list[object]", component["member_entity_ids"]).reverse()
        cast("list[object]", component["subject_component_ids"]).reverse()
    for node in cast("list[dict[str, Any]]", graph["nodes"]):
        cast("list[object]", node["subject_component_ids"]).reverse()
    for operation in cast("list[dict[str, Any]]", graph["operations"]):
        cast("list[object]", operation["source_entity_ids"]).reverse()
        cast("list[object]", operation["target_entity_ids"]).reverse()

    reconstructed = ReconcileProteoformIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert canonical_request_digest(reconstructed) == canonical_request_digest(canonical)
    assert reconstructed == canonical


@pytest.mark.contract
@pytest.mark.parametrize(
    ("code", "wrong_action"),
    [
        (
            ProteoformIdentityLineageFindingCode.IDENTITY_SWAP,
            ProteoformIdentityLineageFindingAction.RECORD,
        ),
        (
            ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED,
            ProteoformIdentityLineageFindingAction.QUARANTINE,
        ),
        (
            ProteoformIdentityLineageFindingCode.UPSTREAM_IDENTITY_UNRESOLVED,
            ProteoformIdentityLineageFindingAction.RECORD,
        ),
    ],
)
def test_standalone_finding_rejects_code_action_substitution(
    code: ProteoformIdentityLineageFindingCode,
    wrong_action: ProteoformIdentityLineageFindingAction,
) -> None:
    with pytest.raises(ValueError, match="action"):
        ProteoformIdentityLineageFinding(
            code=code,
            action=wrong_action,
            evidence_basis_digest=sha256_digest("standalone-finding"),
        )


@pytest.mark.contract
def test_standalone_receipt_rejects_resigned_disposition_substitution() -> None:
    request = build_scenario_request()
    graph, _, disposition = derive_proteoform_reconciliation(request)
    receipt = expected_receipt(request, graph, disposition)
    payload = receipt.model_dump(mode="python")
    payload["disposition"] = ProteoformLineageDisposition.QUARANTINED
    payload["receipt_digest"] = receipt_digest(payload)
    with pytest.raises(ValueError, match="disposition"):
        ProteoformIdentityLineageReceipt.model_validate(payload, strict=True)
