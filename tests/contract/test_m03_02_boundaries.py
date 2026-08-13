"""Exact cardinality, topology, identity, and copy-number bounds for M03-02."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import pytest
from evals.m03_02.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m01_02 import ReconcileIdentityLineageRequest
from glio_proteogen.contracts.m03_01 import EvaluateProteinInferenceProtocolRequest
from glio_proteogen.contracts.m03_02 import (
    CopyNumberConcordanceReceipt,
    ProteinInferenceArtifactClaim,
    ProteinInferenceArtifactDerivation,
    ProteinInferenceIdentityLineageResolution,
    ProteinInferenceLineagePolicy,
    ReconcileProteinInferenceIdentityLineageRequest,
    ReconciliationDisposition,
    ReconciliationFindingCode,
    ResolvedProteinInferenceArtifact,
    ResolvedProteinInferenceDerivation,
    ResolvedProteinInferenceLineageGraph,
    canonical_request_digest,
    configuration_digest,
    resolved_graph_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import M0102Service
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    evaluate_protein_inference_protocol,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    reconcile_protein_inference_identity_lineage,
)

_FORGED_DIGEST = "sha256:" + ("f" * 64)
_MAX_ARTIFACT_CLAIMS = 256
_MAX_DERIVATION_SOURCES = 253
_MAX_SUBJECTS = 256
_MAX_CN_FEATURES = 10_000_000
_MIN_ARTIFACT_CLAIMS = 4
_DERIVATION_COUNT = 3
_MAX_METHODS = 64
_FIVE_CLAIMS = 5
_TWO_SUBJECTS = 2
_M0102_SCENARIOS = Path("tests/fixtures/m01_02/scenarios.json")


@pytest.fixture(scope="module")
def base_request() -> ReconcileProteinInferenceIdentityLineageRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def base_payload(base_request: ReconcileProteinInferenceIdentityLineageRequest) -> dict[str, Any]:
    return _payload(base_request)


@pytest.fixture(scope="module")
def base_result(
    base_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> ProteinInferenceIdentityLineageResolution:
    return reconcile_protein_inference_identity_lineage(base_request)


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_request(payload: dict[str, Any]) -> ReconcileProteinInferenceIdentityLineageRequest:
    return ReconcileProteinInferenceIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_policy(payload: dict[str, Any]) -> ProteinInferenceLineagePolicy:
    return ProteinInferenceLineagePolicy.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_claim(payload: dict[str, Any]) -> ProteinInferenceArtifactClaim:
    return ProteinInferenceArtifactClaim.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_derivation(payload: dict[str, Any]) -> ProteinInferenceArtifactDerivation:
    return ProteinInferenceArtifactDerivation.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_cn(payload: dict[str, Any]) -> CopyNumberConcordanceReceipt:
    return CopyNumberConcordanceReceipt.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_graph(payload: dict[str, Any]) -> ResolvedProteinInferenceLineageGraph:
    return ResolvedProteinInferenceLineageGraph.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _resign_graph(payload: dict[str, Any]) -> None:
    payload["graph_digest"] = resolved_graph_digest(payload)


def _add_peptide_claim(payload: dict[str, Any], index: int) -> None:
    claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
    new_claim = deepcopy(claims[0])
    claim_id = f"claim.peptide.extra.{index:03d}"
    new_claim["claim_id"] = claim_id
    new_claim["artifact"]["artifact_id"] = f"artifact.m0302.extra.{index:03d}"
    new_claim["artifact"]["digest"] = sha256_digest({"m0302-extra": index})
    claims.append(new_claim)
    group_edge = next(
        edge
        for edge in cast("list[dict[str, Any]]", payload["derivations"])
        if edge["target_claim_id"] == "claim.group"
    )
    cast("list[str]", group_edge["source_claim_ids"]).append(claim_id)


def _set_config_binding(payload: dict[str, Any]) -> None:
    payload["context"]["references"]["approved_configuration"]["evidence"][
        "digest"
    ] = configuration_digest(payload["policy"])


def _divergent_same_subject_request() -> ReconcileProteinInferenceIdentityLineageRequest:
    corpus = cast("dict[str, Any]", strict_json_loads(_M0102_SCENARIOS.read_bytes()))
    scenario = next(
        item
        for item in cast("list[dict[str, Any]]", corpus["scenarios"])
        if item["case_id"] == "complete_ordinary_lineage"
    )
    identity_payload = deepcopy(cast("dict[str, Any]", scenario["request"]))
    second_object = deepcopy(identity_payload["entities"][-1])
    second_object["entity_id"] = "obj-b"
    identity_payload["entities"].append(second_object)
    second_operation = deepcopy(identity_payload["lineage_operations"][-1])
    second_operation["operation_id"] = "op-07"
    second_operation["target_entity_ids"] = ["obj-b"]
    identity_payload["lineage_operations"].append(second_operation)
    identity_request = ReconcileIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(identity_payload), strict=True
    )
    with TemporaryDirectory(prefix="m0302-divergent-") as temporary:
        store = M0102EventStore(Path(temporary) / "identity.sqlite3")
        with M0102Service(store) as service:
            identity = service.execute(identity_request)

    seed = build_scenario_request()
    protocol_context = seed.protocol_result.context.model_copy(
        update={
            "references": seed.protocol_result.context.references.model_copy(
                update={
                    "identity_lineage": (
                        seed.protocol_result.context.references.identity_lineage.model_copy(
                            update={"binding_digest": identity.resolution_digest}
                        )
                    )
                }
            )
        }
    )
    protocol = evaluate_protein_inference_protocol(
        EvaluateProteinInferenceProtocolRequest(
            context=protocol_context,
            protocol_schema=seed.protocol_result.protocol_schema,
            conformance_profile=seed.protocol_result.conformance_profile,
        )
    )
    payload = _payload(seed)
    payload["identity_resolution"] = _payload(identity)
    payload["protocol_result"] = _payload(protocol)
    payload["context"]["references"]["identity_lineage"]["binding_digest"] = (
        identity.resolution_digest
    )
    subjects = next(
        node.subject_component_ids for node in identity.graph.nodes if node.entity_id == "obj-a"
    )
    for claim in cast("list[dict[str, Any]]", payload["artifact_claims"]):
        if claim["claim_id"] != "claim.peptide.000":
            claim["identity_entity_id"] = "obj-b"
        claim["declared_subject_component_ids"] = list(subjects)
        claim["producer_identity_resolution_digest"] = identity.resolution_digest
        claim["producer_protocol_result_digest"] = protocol.result_digest
        claim["producer_search_space_digest"] = protocol.receipt.search_space_digest
    payload["cn_receipts"][0]["identity_entity_id"] = "obj-b"
    return _validate_request(payload)


@pytest.mark.contract
def test_policy_exact_lower_and_upper_cardinalities_are_accepted(
    base_payload: dict[str, Any],
) -> None:
    lower = deepcopy(base_payload["policy"])
    lower["max_artifact_claims"] = 4
    lower["max_derivation_sources"] = 1
    assert _validate_policy(lower).max_artifact_claims == _MIN_ARTIFACT_CLAIMS
    assert _validate_policy(lower).max_derivation_sources == 1

    upper = deepcopy(base_payload["policy"])
    upper["max_artifact_claims"] = _MAX_ARTIFACT_CLAIMS
    upper["max_derivation_sources"] = _MAX_DERIVATION_SOURCES
    assert _validate_policy(upper).max_artifact_claims == _MAX_ARTIFACT_CLAIMS
    assert _validate_policy(upper).max_derivation_sources == _MAX_DERIVATION_SOURCES


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_artifact_claims", 3),
        ("max_artifact_claims", _MAX_ARTIFACT_CLAIMS + 1),
        ("max_derivation_sources", 0),
        ("max_derivation_sources", _MAX_DERIVATION_SOURCES + 1),
    ],
)
def test_policy_numeric_underflow_and_max_plus_one_are_rejected(
    base_payload: dict[str, Any],
    field: str,
    value: int,
) -> None:
    payload = deepcopy(base_payload["policy"])
    payload[field] = value
    with pytest.raises(ValidationError):
        _validate_policy(payload)


@pytest.mark.contract
@pytest.mark.parametrize("field", ["approved_derivation_methods", "approved_cn_methods"])
def test_policy_method_lists_accept_64_and_reject_65(
    base_payload: dict[str, Any],
    field: str,
) -> None:
    payload = deepcopy(base_payload["policy"])
    template = deepcopy(payload[field][0])
    methods: list[dict[str, Any]] = []
    for index in range(_MAX_METHODS):
        method = deepcopy(template)
        method["method_id"] = f"method.m0302.{field}.{index:02d}"
        method["evidence"]["artifact_id"] = f"artifact.m0302.{field}.{index:02d}"
        method["evidence"]["digest"] = sha256_digest({field: index})
        methods.append(method)
    payload[field] = methods
    assert len(_validate_policy(payload).model_dump(mode="python")[field]) == _MAX_METHODS
    payload[field].append(deepcopy(methods[-1]))
    payload[field][-1]["method_id"] = f"method.m0302.{field}.64"
    payload[field][-1]["evidence"]["artifact_id"] = f"artifact.m0302.{field}.64"
    payload[field][-1]["evidence"]["digest"] = sha256_digest({field: 64})
    with pytest.raises(ValidationError, match="at most 64 items"):
        _validate_policy(payload)


@pytest.mark.contract
@pytest.mark.parametrize("field", ["approved_derivation_methods", "approved_cn_methods"])
def test_policy_methods_require_unique_identity_and_evidence_digest(
    base_payload: dict[str, Any],
    field: str,
) -> None:
    payload = deepcopy(base_payload["policy"])
    payload[field].append(deepcopy(payload[field][0]))
    with pytest.raises(ValidationError, match="method identities must be unique"):
        _validate_policy(payload)

    payload = deepcopy(base_payload["policy"])
    second = deepcopy(payload[field][0])
    second["method_id"] = f"{second['method_id']}.alternate"
    payload[field].append(second)
    with pytest.raises(ValidationError, match="policy evidence digests must be unique"):
        _validate_policy(payload)


@pytest.mark.contract
def test_policy_safety_flags_are_literal_true_not_preferences(
    base_payload: dict[str, Any],
) -> None:
    for field in ("quarantine_on_cn_discordance", "abstain_on_indeterminate_identity"):
        payload = deepcopy(base_payload["policy"])
        payload[field] = False
        with pytest.raises(ValidationError):
            _validate_policy(payload)


@pytest.mark.contract
def test_claim_subject_collection_accepts_exact_256_and_rejects_257(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload["artifact_claims"][0])
    payload["declared_subject_component_ids"] = [
        sha256_digest({"subject": index}) for index in range(_MAX_SUBJECTS)
    ]
    assert len(_validate_claim(payload).declared_subject_component_ids) == _MAX_SUBJECTS
    payload["declared_subject_component_ids"].append(sha256_digest({"subject": 256}))
    with pytest.raises(ValidationError, match="at most 256 items"):
        _validate_claim(payload)


@pytest.mark.contract
def test_claim_subject_collection_rejects_duplicates(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload["artifact_claims"][0])
    payload["declared_subject_component_ids"].append(
        payload["declared_subject_component_ids"][0]
    )
    with pytest.raises(ValidationError, match="subject component identifiers must be unique"):
        _validate_claim(payload)


@pytest.mark.contract
def test_derivation_source_collection_accepts_253_and_rejects_254(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload["derivations"][0])
    payload["source_claim_ids"] = [
        f"claim.peptide.boundary.{index:03d}" for index in range(_MAX_DERIVATION_SOURCES)
    ]
    assert len(_validate_derivation(payload).source_claim_ids) == _MAX_DERIVATION_SOURCES
    payload["source_claim_ids"].append("claim.peptide.boundary.253")
    with pytest.raises(ValidationError, match="at most 253 items"):
        _validate_derivation(payload)


@pytest.mark.contract
def test_derivation_rejects_empty_duplicate_and_self_sources(
    base_payload: dict[str, Any],
) -> None:
    original = deepcopy(base_payload["derivations"][0])
    mutations: tuple[tuple[list[str], str], ...] = (
        ([], "at least 1 item"),
        ([original["source_claim_ids"][0]] * 2, "source claim identifiers must be unique"),
        ([original["target_claim_id"]], "cannot consume its target claim"),
    )
    for sources, message in mutations:
        payload = deepcopy(original)
        payload["source_claim_ids"] = sources
        with pytest.raises(ValidationError, match=message):
            _validate_derivation(payload)


@pytest.mark.contract
def test_minimum_exact_four_role_dag_is_accepted(
    base_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> None:
    assert len(base_request.artifact_claims) == _MIN_ARTIFACT_CLAIMS
    assert len(base_request.derivations) == _DERIVATION_COUNT
    assert len(base_request.cn_receipts) == 1
    result = reconcile_protein_inference_identity_lineage(base_request)
    assert result.disposition is ReconciliationDisposition.RECONCILED


@pytest.mark.contract
def test_maximum_256_claim_253_root_shape_is_total() -> None:
    request = build_scenario_request("maximum")
    result = reconcile_protein_inference_identity_lineage(request)
    assert len(request.artifact_claims) == _MAX_ARTIFACT_CLAIMS
    group = next(edge for edge in request.derivations if edge.target_claim_id == "claim.group")
    assert len(group.source_claim_ids) == _MAX_DERIVATION_SOURCES
    assert len(result.graph.artifacts) == _MAX_ARTIFACT_CLAIMS
    assert result.disposition is ReconciliationDisposition.RECONCILED
    assert result.result_digest == result_payload_digest(result)


@pytest.mark.contract
def test_claim_count_256_is_accepted_and_257_rejected() -> None:
    maximum = build_scenario_request("maximum")
    assert len(maximum.artifact_claims) == _MAX_ARTIFACT_CLAIMS
    payload = _payload(maximum)
    _add_peptide_claim(payload, 257)
    with pytest.raises(ValidationError, match="at most 256 items"):
        _validate_request(payload)


@pytest.mark.contract
def test_active_policy_can_be_narrower_than_schema_but_not_than_request(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload)
    _add_peptide_claim(payload, 1)
    payload["policy"]["max_artifact_claims"] = 4
    _set_config_binding(payload)
    with pytest.raises(ValidationError, match="artifact claims exceed the active policy"):
        _validate_request(payload)

    payload = deepcopy(base_payload)
    _add_peptide_claim(payload, 1)
    payload["policy"]["max_artifact_claims"] = 5
    payload["policy"]["max_derivation_sources"] = 2
    _set_config_binding(payload)
    assert len(_validate_request(payload).artifact_claims) == _FIVE_CLAIMS


@pytest.mark.contract
def test_active_derivation_source_policy_rejects_cap_plus_one(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload)
    _add_peptide_claim(payload, 1)
    payload["policy"]["max_artifact_claims"] = 5
    payload["policy"]["max_derivation_sources"] = 1
    _set_config_binding(payload)
    with pytest.raises(ValidationError, match="sources exceed the active policy"):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_claim_id", "artifact claim identifiers must be unique"),
        ("duplicate_derivation_id", "artifact derivation identifiers must be unique"),
        ("missing_peptide", "requires peptide roots"),
        ("second_ambiguity", "requires peptide roots"),
        ("second_bundle", "requires peptide roots"),
        ("unknown_source", "references an unknown claim"),
        ("unknown_target", "references an unknown claim"),
        ("group_missing_root", "consume every peptide-evidence root"),
        ("group_extra_source", "consume every peptide-evidence root"),
        ("ambiguity_wrong_source", "consume exactly the protein-group manifest"),
        ("bundle_missing_parent", "requires group and ambiguity parents"),
        ("unapproved_method", "method is not approved"),
    ],
)
def test_every_request_dag_relationship_branch_rejects(  # noqa: C901
    base_payload: dict[str, Any],
    mutation: str,
    message: str,
) -> None:
    payload = deepcopy(base_payload)
    claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
    edges = cast("list[dict[str, Any]]", payload["derivations"])
    if mutation == "duplicate_claim_id":
        claims[1]["claim_id"] = claims[0]["claim_id"]
    elif mutation == "duplicate_derivation_id":
        edges[1]["derivation_id"] = edges[0]["derivation_id"]
    elif mutation == "missing_peptide":
        claims[0]["role"] = "protein_group_manifest"
    elif mutation == "second_ambiguity":
        claims[0]["role"] = "ambiguity_manifest"
    elif mutation == "second_bundle":
        claims[0]["role"] = "complex_activity_input_bundle"
    elif mutation == "unknown_source":
        edges[0]["source_claim_ids"] = ["claim.unknown"]
    elif mutation == "unknown_target":
        edges[0]["target_claim_id"] = "claim.unknown"
    elif mutation == "group_missing_root":
        extra = deepcopy(claims[0])
        extra["claim_id"] = "claim.peptide.unconsumed"
        extra["artifact"]["artifact_id"] = "artifact.m0302.unconsumed"
        extra["artifact"]["digest"] = sha256_digest({"peptide": "unconsumed"})
        claims.append(extra)
    elif mutation == "group_extra_source":
        edges[0]["source_claim_ids"].append("claim.ambiguity")
    elif mutation == "ambiguity_wrong_source":
        edges[1]["source_claim_ids"] = ["claim.peptide.000"]
    elif mutation == "bundle_missing_parent":
        edges[2]["source_claim_ids"] = ["claim.group"]
    elif mutation == "unapproved_method":
        edges[0]["method_id"] = "derivation.unapproved"
    with pytest.raises(ValidationError, match=message):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize("role", ["protein_group_manifest", "ambiguity_manifest"])
def test_role_counts_reject_a_second_non_root_even_with_five_claims(
    base_payload: dict[str, Any],
    role: str,
) -> None:
    payload = deepcopy(base_payload)
    extra = deepcopy(payload["artifact_claims"][0])
    extra["claim_id"] = f"claim.extra.{role}"
    extra["role"] = role
    extra["artifact"]["artifact_id"] = f"artifact.m0302.extra.{role}"
    extra["artifact"]["digest"] = sha256_digest({"extra-role": role})
    payload["artifact_claims"].append(extra)
    with pytest.raises(ValidationError, match="requires peptide roots"):
        _validate_request(payload)


@pytest.mark.contract
def test_claim_anchor_must_exist_and_be_a_derived_object(
    base_payload: dict[str, Any],
) -> None:
    unknown = deepcopy(base_payload)
    unknown["artifact_claims"][0]["identity_entity_id"] = "obj-unknown"
    with pytest.raises(ValidationError, match="unknown identity entity"):
        _validate_request(unknown)

    non_derived = deepcopy(base_payload)
    non_derived["artifact_claims"][0]["identity_entity_id"] = "run-a"
    with pytest.raises(ValidationError, match="require derived-object anchors"):
        _validate_request(non_derived)


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "producer_identity_resolution_digest",
        "producer_protocol_result_digest",
        "producer_search_space_digest",
    ],
)
def test_stale_producer_bindings_are_typed_findings_not_boundary_rejections(
    base_payload: dict[str, Any],
    field: str,
) -> None:
    payload = deepcopy(base_payload)
    payload["artifact_claims"][0][field] = _FORGED_DIGEST
    request = _validate_request(payload)
    result = reconcile_protein_inference_identity_lineage(request)
    expected = {
        "producer_identity_resolution_digest": ReconciliationFindingCode.PRODUCER_IDENTITY_DRIFT,
        "producer_protocol_result_digest": ReconciliationFindingCode.PRODUCER_PROTOCOL_DRIFT,
        "producer_search_space_digest": ReconciliationFindingCode.PRODUCER_SEARCH_SPACE_DRIFT,
    }[field]
    assert result.disposition is ReconciliationDisposition.QUARANTINED
    assert expected in {finding.code for finding in result.findings}


@pytest.mark.contract
def test_valid_nonresolved_identity_abstains_and_nonconformant_protocol_quarantines() -> None:
    identity = reconcile_protein_inference_identity_lineage(
        build_scenario_request("identity_unresolved")
    )
    protocol = reconcile_protein_inference_identity_lineage(
        build_scenario_request("protocol_nonconformant")
    )
    assert identity.disposition is ReconciliationDisposition.ABSTAINED
    assert ReconciliationFindingCode.UPSTREAM_IDENTITY_UNRESOLVED in {
        finding.code for finding in identity.findings
    }
    assert protocol.disposition is ReconciliationDisposition.QUARANTINED
    assert ReconciliationFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT in {
        finding.code for finding in protocol.findings
    }


@pytest.mark.contract
def test_quarantine_takes_precedence_when_abstain_and_quarantine_coexist() -> None:
    payload = _payload(build_scenario_request("cn_missing"))
    payload["artifact_claims"][0]["producer_protocol_result_digest"] = _FORGED_DIGEST
    result = reconcile_protein_inference_identity_lineage(_validate_request(payload))
    actions = {finding.action.value for finding in result.findings}
    assert actions == {"abstain", "quarantine"}
    assert result.disposition is ReconciliationDisposition.QUARANTINED
    assert result.human_review_required


@pytest.mark.contract
@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("context_identity", "identity chain does not bind"),
        ("protocol_identity", "identity chain does not bind"),
        ("configuration", "approved configuration does not bind"),
    ],
)
def test_stale_identity_chain_and_configuration_bindings_hard_reject(
    base_payload: dict[str, Any],
    target: str,
    message: str,
) -> None:
    payload = deepcopy(base_payload)
    if target == "context_identity":
        payload["context"]["references"]["identity_lineage"]["binding_digest"] = (
            _FORGED_DIGEST
        )
    elif target == "protocol_identity":
        payload["protocol_result"]["receipt"]["identity_subject_digest"] = _FORGED_DIGEST
        message = "result provenance and receipt envelope is inconsistent"
    else:
        payload["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = _FORGED_DIGEST
    with pytest.raises(ValidationError, match=message):
        _validate_request(payload)


@pytest.mark.contract
def test_policy_cannot_postdate_reconciliation(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload)
    payload["policy"]["reviewed_at"] = (
        build_scenario_request().context.occurred_at + timedelta(seconds=1)
    ).isoformat()
    _set_config_binding(payload)
    with pytest.raises(ValidationError, match="policy cannot postdate"):
        _validate_request(payload)


@pytest.mark.contract
def test_genuine_protocol_result_cannot_postdate_reconciliation(
    base_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> None:
    occurred_at = base_request.protocol_result.completed_at - timedelta(seconds=1)
    policy = base_request.policy.model_copy(
        update={"reviewed_at": occurred_at - timedelta(seconds=1)}
    )
    context = base_request.context.model_copy(
        update={
            "occurred_at": occurred_at,
            "references": base_request.context.references.model_copy(
                update={
                    "approved_configuration": (
                        base_request.context.references.approved_configuration.model_copy(
                            update={
                                "evidence": (
                                    base_request.context.references.approved_configuration.evidence.model_copy(
                                        update={"digest": configuration_digest(policy)}
                                    )
                                )
                            }
                        )
                    )
                }
            ),
        }
    )
    with pytest.raises(ValidationError, match="upstream result cannot postdate"):
        ReconcileProteinInferenceIdentityLineageRequest(
            context=context,
            identity_resolution=base_request.identity_resolution,
            protocol_result=base_request.protocol_result,
            policy=policy,
            artifact_claims=base_request.artifact_claims,
            derivations=base_request.derivations,
            cn_receipts=base_request.cn_receipts,
        )


@pytest.mark.contract
def test_genuine_protocol_result_cannot_predate_identity_resolution(
    base_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> None:
    protocol = base_request.protocol_result.model_copy(
        update={
            "completed_at": base_request.identity_resolution.resolved_at
            - timedelta(seconds=1)
        }
    )
    with pytest.raises(ValidationError, match="result provenance and receipt envelope"):
        ReconcileProteinInferenceIdentityLineageRequest(
            context=base_request.context,
            identity_resolution=base_request.identity_resolution,
            protocol_result=protocol,
            policy=base_request.policy,
            artifact_claims=base_request.artifact_claims,
            derivations=base_request.derivations,
            cn_receipts=base_request.cn_receipts,
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("case", "accepted_label"),
    [
        (("concordant", 1, 1, 0), "accepted"),
        (("concordant", 0, 0, 0), "rejected"),
        (("concordant", 2, 1, 1), "rejected"),
        (("discordant", 1, 0, 1), "accepted"),
        (("discordant", 2, 1, 1), "accepted"),
        (("discordant", 1, 1, 0), "rejected"),
        (("indeterminate", 0, 0, 0), "accepted"),
        (("indeterminate", 1, 1, 0), "rejected"),
        (("missing", 0, 0, 0), "accepted"),
        (("missing", 1, 1, 0), "rejected"),
        (("unsupported", 0, 0, 0), "accepted"),
        (("unsupported", 1, 0, 1), "rejected"),
    ],
)
def test_copy_number_state_count_matrix_is_exact(
    base_payload: dict[str, Any],
    case: tuple[str, int, int, int],
    accepted_label: str,
) -> None:
    state, informative, concordant, discordant = case
    payload = deepcopy(base_payload["cn_receipts"][0])
    payload.update(
        {
            "state": state,
            "informative_feature_count": informative,
            "concordant_feature_count": concordant,
            "discordant_feature_count": discordant,
        }
    )
    if accepted_label == "accepted":
        assert _validate_cn(payload).state.value == state
    else:
        with pytest.raises(ValidationError):
            _validate_cn(payload)


@pytest.mark.contract
def test_copy_number_arithmetic_and_numeric_caps_are_exact(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload["cn_receipts"][0])
    payload.update(
        {
            "informative_feature_count": _MAX_CN_FEATURES,
            "concordant_feature_count": _MAX_CN_FEATURES,
            "discordant_feature_count": 0,
        }
    )
    assert _validate_cn(payload).informative_feature_count == _MAX_CN_FEATURES
    for field in (
        "informative_feature_count",
        "concordant_feature_count",
        "discordant_feature_count",
    ):
        invalid = deepcopy(payload)
        invalid[field] = _MAX_CN_FEATURES + 1
        with pytest.raises(ValidationError):
            _validate_cn(invalid)
        invalid[field] = -1
        with pytest.raises(ValidationError):
            _validate_cn(invalid)

    mismatch = deepcopy(base_payload["cn_receipts"][0])
    mismatch["informative_feature_count"] += 1
    with pytest.raises(ValidationError, match="counts do not close"):
        _validate_cn(mismatch)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("case", "accepted_label"),
    [
        (("concordant", "approved"), "accepted"),
        (("discordant", "approved"), "accepted"),
        (("indeterminate", "approved"), "accepted"),
        (("missing", "approved"), "accepted"),
        (("unsupported", "approved"), "accepted"),
        (("concordant", "unapproved"), "rejected"),
        (("discordant", "unapproved"), "rejected"),
        (("indeterminate", "unapproved"), "rejected"),
        (("missing", "unapproved"), "rejected"),
        (("unsupported", "unapproved"), "accepted"),
    ],
)
def test_copy_number_method_approval_matrix(
    case: tuple[str, str],
    accepted_label: str,
) -> None:
    state, approval = case
    payload = _payload(build_scenario_request(f"cn_{state}"))
    if approval == "unapproved":
        payload["cn_receipts"][0]["method_id"] = "cn.aggregate.unapproved"
    if accepted_label == "accepted":
        assert _validate_request(payload).cn_receipts[0].state.value == state
    else:
        with pytest.raises(ValidationError, match="method is not approved"):
            _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("zero", "at least 1 item"),
        ("two", "at most 1 item"),
        ("unknown_claim", "must bind the protein-group manifest"),
        ("wrong_role", "must bind the protein-group manifest"),
        ("wrong_identity", "identity does not match"),
    ],
)
def test_copy_number_receipt_count_and_binding_are_exact(
    base_payload: dict[str, Any],
    mutation: str,
    message: str,
) -> None:
    payload = deepcopy(base_payload)
    receipts = payload["cn_receipts"]
    if mutation == "zero":
        receipts.clear()
    elif mutation == "two":
        second = deepcopy(receipts[0])
        second["receipt_id"] = "receipt.cn.second"
        second["evidence"]["artifact_id"] = "artifact.m0302.receipt.cn.second"
        second["evidence"]["digest"] = sha256_digest({"cn": "second"})
        receipts.append(second)
    elif mutation == "unknown_claim":
        receipts[0]["claim_id"] = "claim.unknown"
    elif mutation == "wrong_role":
        receipts[0]["claim_id"] = "claim.peptide.000"
    else:
        receipts[0]["identity_entity_id"] = "obj-unknown"
    with pytest.raises(ValidationError, match=message):
        _validate_request(payload)


@pytest.mark.contract
def test_all_cn_states_preserve_identity_and_have_exact_dispositions() -> None:
    expected = {
        "concordant": ReconciliationDisposition.RECONCILED,
        "discordant": ReconciliationDisposition.QUARANTINED,
        "indeterminate": ReconciliationDisposition.ABSTAINED,
        "missing": ReconciliationDisposition.ABSTAINED,
        "unsupported": ReconciliationDisposition.ABSTAINED,
    }
    subject_views: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {}
    for state, disposition in expected.items():
        result = reconcile_protein_inference_identity_lineage(
            build_scenario_request(f"cn_{state}")
        )
        assert result.disposition is disposition
        assert not result.infers_identity
        subject_views[state] = tuple(
            (artifact.claim_id, artifact.resolved_subject_component_ids)
            for artifact in result.graph.artifacts
        )
    assert len(set(subject_views.values())) == 1


@pytest.mark.contract
def test_duplicate_content_is_retained_and_collision_is_distinctly_quarantined() -> None:
    duplicate = reconcile_protein_inference_identity_lineage(
        build_scenario_request("duplicate")
    )
    collision = reconcile_protein_inference_identity_lineage(
        build_scenario_request("collision")
    )
    combined = reconcile_protein_inference_identity_lineage(
        build_scenario_request("collision_and_duplicate")
    )
    assert len(duplicate.graph.artifacts) == _FIVE_CLAIMS
    assert ReconciliationFindingCode.DUPLICATE_CONTENT_RETAINED in {
        item.code for item in duplicate.findings
    }
    assert ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION in {
        item.code for item in collision.findings
    }
    assert {item.code for item in combined.findings} == {
        ReconciliationFindingCode.DUPLICATE_CONTENT_RETAINED,
        ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION,
    }
    assert all(
        result.disposition is ReconciliationDisposition.QUARANTINED
        for result in (duplicate, collision, combined)
    )


@pytest.mark.contract
def test_submitted_evidence_identity_cannot_claim_conflicting_content(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload)
    payload["derivations"][0]["evidence"]["artifact_id"] = payload["policy"][
        "evidence"
    ]["artifact_id"]
    payload["derivations"][0]["evidence"]["version"] = payload["policy"]["evidence"][
        "version"
    ]
    with pytest.raises(ValidationError, match="conflicting content"):
        _validate_request(payload)

    payload = deepcopy(base_payload)
    claim = payload["artifact_claims"][0]
    claim["artifact"]["artifact_id"] = payload["policy"]["evidence"]["artifact_id"]
    claim["artifact"]["version"] = payload["policy"]["evidence"]["version"]
    with pytest.raises(ValidationError, match="cannot contradict a control evidence identity"):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize("upstream", ["identity_resolution", "protocol_result"])
def test_claim_cannot_contradict_embedded_upstream_evidence_content(
    base_payload: dict[str, Any],
    upstream: str,
) -> None:
    payload = deepcopy(base_payload)
    upstream_evidence = payload[upstream]["evidence"][0]["reference"]
    claim = payload["artifact_claims"][0]["artifact"]
    claim["artifact_id"] = upstream_evidence["artifact_id"]
    claim["version"] = upstream_evidence["version"]
    claim["digest"] = _FORGED_DIGEST
    claim["media_type"] = "application/x-forged"
    with pytest.raises(ValidationError, match="embedded upstream evidence content"):
        _validate_request(payload)


@pytest.mark.contract
def test_claim_may_match_one_of_reused_upstream_identity_content_pairs(
    base_payload: dict[str, Any],
) -> None:
    payload = deepcopy(base_payload)
    upstream_evidence = payload["identity_resolution"]["evidence"]
    by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in upstream_evidence:
        reference = item["reference"]
        by_identity.setdefault(
            (reference["artifact_id"], reference["version"]), []
        ).append(reference)
    references = next(values for values in by_identity.values() if len(values) > 1)
    claim = payload["artifact_claims"][0]["artifact"]
    claim.update(deepcopy(references[-1]))
    assert _validate_request(payload).artifact_claims[0].artifact.digest == references[-1][
        "digest"
    ]


@pytest.mark.contract
def test_divergent_same_subject_physical_lineage_is_collision_and_quarantine() -> None:
    request = _divergent_same_subject_request()
    result = reconcile_protein_inference_identity_lineage(request)
    assert result.disposition is ReconciliationDisposition.QUARANTINED
    collision_findings = {
        finding
        for finding in result.findings
        if finding.code is ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION
    }
    assert collision_findings
    participants = {
        claim_id for finding in collision_findings for claim_id in finding.claim_ids
    }
    assert {"claim.peptide.000", "claim.group"}.issubset(participants)
    by_id = {artifact.claim_id: artifact for artifact in result.graph.artifacts}
    assert all(
        ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION
        in by_id[claim_id].finding_codes
        for claim_id in participants
    )


@pytest.mark.contract
def test_standalone_graph_rejects_removed_divergent_lineage_collision_marker() -> None:
    result = reconcile_protein_inference_identity_lineage(
        _divergent_same_subject_request()
    )
    payload = _payload(result.graph)
    participant = next(
        artifact
        for artifact in payload["artifacts"]
        if "artifact_lineage_collision" in artifact["finding_codes"]
    )
    participant["finding_codes"].remove("artifact_lineage_collision")
    _resign_graph(payload)
    with pytest.raises(ValidationError, match="divergent physical-lineage paths"):
        _validate_graph(payload)


@pytest.mark.contract
def test_declared_subject_mismatch_does_not_alter_propagated_subjects() -> None:
    payload = _payload(build_scenario_request())
    declared = sha256_digest({"declared": "mismatch"})
    for claim in payload["artifact_claims"]:
        claim["declared_subject_component_ids"] = [declared]
    result = reconcile_protein_inference_identity_lineage(_validate_request(payload))
    assert result.disposition is ReconciliationDisposition.QUARANTINED
    assert ReconciliationFindingCode.IDENTITY_SWAP in {
        finding.code for finding in result.findings
    }
    assert all(
        declared not in artifact.resolved_subject_component_ids
        for artifact in result.graph.artifacts
    )


@pytest.mark.contract
def test_cross_patient_subjects_propagate_only_through_reachable_descendants() -> None:
    result = reconcile_protein_inference_identity_lineage(
        build_scenario_request("cross_patient")
    )
    by_id = {artifact.claim_id: artifact for artifact in result.graph.artifacts}
    roots = ("claim.peptide.000", "claim.peptide.001")
    affected = ("claim.group", "claim.ambiguity", "claim.bundle")
    assert all(len(by_id[claim_id].resolved_subject_component_ids) == 1 for claim_id in roots)
    assert all(
        len(by_id[claim_id].resolved_subject_component_ids) == _TWO_SUBJECTS
        for claim_id in affected
    )
    assert result.disposition is ReconciliationDisposition.QUARANTINED
    assert not result.infers_identity


@pytest.mark.contract
def test_standalone_graph_accepts_exact_topology_and_digest(
    base_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    graph = _validate_graph(_payload(base_result.graph))
    assert graph == base_result.graph
    assert graph.graph_digest == resolved_graph_digest(graph)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_artifact", "resolved artifact identifiers must be unique"),
        ("duplicate_edge", "resolved derivation identifiers must be unique"),
        ("second_group", "exact four-role shape"),
        ("unknown_endpoint", "endpoints are not closed"),
        ("self_endpoint", "endpoints are not closed"),
        ("multiple_producer", "endpoints are not closed"),
        ("wrong_group_sources", "closed artifact topology"),
        ("wrong_ambiguity_source", "closed artifact topology"),
        ("wrong_bundle_sources", "closed artifact topology"),
        ("wrong_propagated_edge", "subject propagation contradicts"),
        ("wrong_propagated_node", "subject propagation contradicts"),
        ("duplicate_declared", "collections must be unique"),
        ("duplicate_resolved", "subject propagation contradicts"),
        ("duplicate_finding_code", "collections must be unique"),
        ("duplicate_edge_subject", "subject propagation contradicts"),
    ],
)
def test_standalone_graph_rejects_every_topology_and_propagation_contradiction(  # noqa: C901, PLR0912
    base_result: ProteinInferenceIdentityLineageResolution,
    mutation: str,
    message: str,
) -> None:
    payload = _payload(base_result.graph)
    artifacts = cast("list[dict[str, Any]]", payload["artifacts"])
    edges = cast("list[dict[str, Any]]", payload["derivations"])
    by_id = {item["claim_id"]: item for item in artifacts}
    by_target = {item["target_claim_id"]: item for item in edges}
    if mutation == "duplicate_artifact":
        artifacts[1]["claim_id"] = artifacts[0]["claim_id"]
    elif mutation == "duplicate_edge":
        edges[1]["derivation_id"] = edges[0]["derivation_id"]
    elif mutation == "second_group":
        by_id["claim.peptide.000"]["role"] = "protein_group_manifest"
    elif mutation == "unknown_endpoint":
        edges[0]["source_claim_ids"] = ["claim.unknown"]
    elif mutation == "self_endpoint":
        edges[0]["source_claim_ids"] = [edges[0]["target_claim_id"]]
    elif mutation == "multiple_producer":
        edges[1]["target_claim_id"] = edges[0]["target_claim_id"]
    elif mutation == "wrong_group_sources":
        by_target["claim.group"]["source_claim_ids"] = ["claim.ambiguity"]
    elif mutation == "wrong_ambiguity_source":
        by_target["claim.ambiguity"]["source_claim_ids"] = ["claim.peptide.000"]
    elif mutation == "wrong_bundle_sources":
        by_target["claim.bundle"]["source_claim_ids"] = ["claim.group"]
    elif mutation == "wrong_propagated_edge":
        by_target["claim.group"]["propagated_subject_component_ids"] = [_FORGED_DIGEST]
    elif mutation == "wrong_propagated_node":
        by_id["claim.group"]["resolved_subject_component_ids"] = [_FORGED_DIGEST]
    elif mutation == "duplicate_declared":
        values = by_id["claim.group"]["declared_subject_component_ids"]
        values.append(values[0])
    elif mutation == "duplicate_resolved":
        values = by_id["claim.group"]["resolved_subject_component_ids"]
        values.append(values[0])
    elif mutation == "duplicate_finding_code":
        by_id["claim.group"]["finding_codes"] = ["identity_swap", "identity_swap"]
    else:
        values = by_target["claim.group"]["propagated_subject_component_ids"]
        values.append(values[0])
    _resign_graph(payload)
    with pytest.raises(ValidationError, match=message):
        _validate_graph(payload)


@pytest.mark.contract
def test_standalone_graph_digest_is_mandatory_nonzero_and_exact(
    base_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    missing = _payload(base_result.graph)
    missing.pop("graph_digest")
    zero = _payload(base_result.graph)
    zero["graph_digest"] = "sha256:" + ("0" * 64)
    stale = _payload(base_result.graph)
    stale["graph_digest"] = _FORGED_DIGEST
    for payload in (missing, zero, stale):
        with pytest.raises(ValidationError):
            _validate_graph(payload)


@pytest.mark.contract
def test_standalone_graph_collection_caps_are_exact(
    base_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    artifact_payload = _payload(base_result.graph.artifacts[0])
    artifact_payload["declared_subject_component_ids"] = [
        sha256_digest({"declared": index}) for index in range(_MAX_SUBJECTS)
    ]
    artifact_payload["resolved_subject_component_ids"] = [
        sha256_digest({"resolved": index}) for index in range(_MAX_SUBJECTS)
    ]
    assert len(
        ResolvedProteinInferenceArtifact.model_validate_json(
            canonical_json_bytes(artifact_payload), strict=True
        ).resolved_subject_component_ids
    ) == _MAX_SUBJECTS
    artifact_payload["resolved_subject_component_ids"].append(
        sha256_digest({"resolved": 256})
    )
    with pytest.raises(ValidationError, match="at most 256 items"):
        ResolvedProteinInferenceArtifact.model_validate_json(
            canonical_json_bytes(artifact_payload), strict=True
        )

    derivation_payload = _payload(base_result.graph.derivations[0])
    derivation_payload["source_claim_ids"] = [
        f"claim.boundary.{index:03d}" for index in range(_MAX_DERIVATION_SOURCES)
    ]
    assert len(
        ResolvedProteinInferenceDerivation.model_validate_json(
            canonical_json_bytes(derivation_payload), strict=True
        ).source_claim_ids
    ) == _MAX_DERIVATION_SOURCES
    derivation_payload["source_claim_ids"].append("claim.boundary.253")
    with pytest.raises(ValidationError, match="at most 253 items"):
        ResolvedProteinInferenceDerivation.model_validate_json(
            canonical_json_bytes(derivation_payload), strict=True
        )


@pytest.mark.contract
def test_result_graph_forgery_rejects_even_when_inner_and_outer_digests_are_resigned(
    base_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    payload = _payload(base_result)
    payload["graph"]["artifacts"][0]["artifact_digest"] = _FORGED_DIGEST
    payload["graph"]["graph_digest"] = resolved_graph_digest(payload["graph"])
    payload["graph_digest"] = payload["graph"]["graph_digest"]
    payload["receipt"]["graph_digest"] = payload["graph"]["graph_digest"]
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="contradicts its embedded reconciliation request"):
        ProteinInferenceIdentityLineageResolution.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
def test_result_findings_are_not_a_free_set_after_resigning(
    base_result: ProteinInferenceIdentityLineageResolution,
) -> None:
    payload = _payload(base_result)
    payload["findings"] = [
        {
            "code": "producer_identity_drift",
            "action": "quarantine",
            "claim_ids": ["claim.peptide.000"],
            "derivation_ids": [],
            "evidence_basis_digest": sha256_digest({"forged": "finding"}),
        }
    ]
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="contradicts its embedded reconciliation request"):
        ProteinInferenceIdentityLineageResolution.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
def test_request_digest_changes_for_semantic_content_but_not_semantic_order(
    base_request: ReconcileProteinInferenceIdentityLineageRequest,
) -> None:
    payload = _payload(base_request)
    original = canonical_request_digest(payload)
    payload["artifact_claims"][0]["artifact"]["digest"] = _FORGED_DIGEST
    changed = _validate_request(payload)
    assert canonical_request_digest(changed) != original

    payload = _payload(base_request)
    payload["artifact_claims"].reverse()
    payload["derivations"].reverse()
    payload["cn_receipts"].reverse()
    reordered = _validate_request(payload)
    assert canonical_request_digest(reordered) == original
