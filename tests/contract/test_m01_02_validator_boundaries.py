"""Focused relational boundaries for the public M01-02 contract models."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m01_02.canonical import policy_digest
from glio_proteogen.contracts.m01_02.v1 import (
    ConcordanceAggregate,
    ConcordanceObservation,
    DifferentFromAssertion,
    IdentityComponent,
    IdentityEntity,
    IdentityIssue,
    IdentityLineageResolution,
    IdentityLineageResolutionDraft,
    IdentityResolutionPolicy,
    LineageOperation,
    ReconcileIdentityLineageRequest,
    ResolvedIdentityNode,
    ResolvedLineageOperation,
    SameAsAssertion,
    SubjectMembershipAssertion,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import M0102Service
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    reconcile_identity_lineage,
)

pytestmark = pytest.mark.contract

SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m01_02" / "scenarios.json"
DIGEST_A = "sha256:" + ("a" * 64)
DIGEST_B = "sha256:" + ("b" * 64)
Mutation = Callable[[dict[str, Any]], None]


def _payload(case_id: str = "complete_ordinary_lineage") -> dict[str, Any]:
    corpus = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenario = next(case for case in corpus["scenarios"] if case["case_id"] == case_id)
    return deepcopy(scenario["request"])


def _validate(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    return model.model_validate_json(json.dumps(payload), strict=True)


def _reject(model: type[BaseModel], payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _validate(model, payload)


def _token(*, kind: str = "specimen", digest: str = DIGEST_A) -> dict[str, Any]:
    return {
        "issuer_id": "issuer.synthetic",
        "namespace_id": "namespace.synthetic",
        "scope_id": "scope.synthetic",
        "key_id": "key.synthetic",
        "token_version": "1.0.0",
        "entity_kind": kind,
        "token_digest": digest,
        "evidence": deepcopy(_payload()["entities"][0]["evidence"][0]),
    }


def _duplicate_entity_evidence(payload: dict[str, Any]) -> None:
    payload["evidence"].append(deepcopy(payload["evidence"][0]))


def _mismatched_token_kind(payload: dict[str, Any]) -> None:
    payload["identity_tokens"] = [_token(kind="patient")]


def _duplicate_token_scope(payload: dict[str, Any]) -> None:
    payload["identity_tokens"] = [_token(), _token(digest=DIGEST_B)]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_duplicate_entity_evidence, "evidence references must be unique"),
        (_mismatched_token_kind, "identity token kind must match"),
        (_duplicate_token_scope, "authority scopes must be unique"),
        (lambda payload: payload.update(kind="patient", composition="multi_subject"),
         "patient entity cannot be declared multi-subject"),
    ],
)
def test_entity_relational_boundaries(mutation: Mutation, message: str) -> None:
    entity = _payload()["entities"][1]
    mutation(entity)

    _reject(IdentityEntity, entity, message)


@pytest.mark.parametrize(
    ("model", "case_id", "assertion_index", "mutation", "message"),
    [
        (
            SameAsAssertion,
            "authorized_explicit_same_as",
            0,
            lambda value: value.update(right_entity_id=value["left_entity_id"]),
            "same-as endpoints must be distinct",
        ),
        (
            DifferentFromAssertion,
            "poisoned_bridge_atomic_quarantine",
            2,
            lambda value: value.update(right_entity_id=value["left_entity_id"]),
            "different-from endpoints must be distinct",
        ),
        (
            SubjectMembershipAssertion,
            "authorized_explicit_same_as",
            1,
            lambda value: value.update(subject_entity_id=value["entity_id"]),
            "subject membership endpoints must be distinct",
        ),
    ],
)
def test_assertion_endpoints_must_be_distinct(
    model: type[BaseModel],
    case_id: str,
    assertion_index: int,
    mutation: Mutation,
    message: str,
) -> None:
    assertion = _payload(case_id)["assertions"][assertion_index]
    mutation(assertion)

    _reject(model, assertion, message)


def _valid_demultiplex() -> dict[str, Any]:
    operation = _payload("ambiguous_demultiplex_fails_closed")["lineage_operations"][0]
    operation["channels"][1]["channel_id"] = "channel-2"
    operation["channels"][1]["tag_digest"] = DIGEST_B
    return operation


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_endpoint", "endpoints must be unique"),
        ("self_endpoint", "cannot contain a self endpoint"),
        ("ordinary_cardinality", "ordinary lineage operations require one-to-one"),
        ("pool_cardinality", "pooled-from operations require N-to-one"),
        ("pool_channels", "pooled-from operations cannot carry"),
        ("demux_cardinality", "demultiplexed-from operations require one-to-N"),
        ("demux_coverage", "channels must cover every target exactly once"),
        ("demux_source", "channels must reference the sole source"),
        ("demux_uniqueness", "channels and tag digests must be unique"),
    ],
)
def test_lineage_operation_rejects_relational_ambiguity(case: str, message: str) -> None:
    ordinary = deepcopy(_payload()["lineage_operations"][0])
    pool = deepcopy(_payload("explicit_pool_preserves_multiple_patients")["lineage_operations"][0])
    demux = _valid_demultiplex()
    operations = {
        "duplicate_endpoint": {**ordinary, "source_entity_ids": ["pat-a", "pat-a"]},
        "self_endpoint": {**ordinary, "target_entity_ids": ["pat-a"]},
        "ordinary_cardinality": {**ordinary, "target_entity_ids": ["spc-a", "spc-b"]},
        "pool_cardinality": {**pool, "source_entity_ids": ["alq-a"]},
        "pool_channels": {**pool, "channels": [deepcopy(demux["channels"][0])]},
        "demux_cardinality": {**demux, "source_entity_ids": ["ana-pool", "ana-x"]},
        "demux_coverage": {**demux, "channels": demux["channels"][:1]},
        "demux_source": deepcopy(demux),
        "demux_uniqueness": deepcopy(demux),
    }
    operations["demux_source"]["channels"][0]["source_entity_id"] = "ana-x"
    operations["demux_uniqueness"]["channels"][1]["channel_id"] = "channel-1"

    _reject(LineageOperation, operations[case], message)


def test_pool_and_demultiplex_valid_cardinality_boundaries_are_accepted() -> None:
    pool = _payload("explicit_pool_preserves_multiple_patients")["lineage_operations"][0]

    assert _validate(LineageOperation, pool).kind.value == "pooled_from"
    assert _validate(LineageOperation, _valid_demultiplex()).kind.value == "demultiplexed_from"


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"right_entity_id": "spc-a"}, "endpoints must be distinct"),
        ({"informative_count": 2}, "counts must sum to the informative count"),
        (
            {"classification": "indeterminate"},
            "non-evaluable concordance cannot carry informative counts",
        ),
        (
            {"classification": "concordant", "informative_count": 0, "concordant_count": 0},
            "concordant evidence requires a concordant observation",
        ),
        (
            {"classification": "discordant", "informative_count": 0, "concordant_count": 0},
            "discordant evidence requires a discordant observation",
        ),
    ],
)
def test_concordance_classification_and_counts_are_closed(
    updates: dict[str, Any],
    message: str,
) -> None:
    observation = _payload("concordance_never_implicitly_merges")[
        "concordance_observations"
    ][0]
    observation.update(updates)

    _reject(ConcordanceObservation, observation, message)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"member_entity_ids": ["spc-a", "spc-a"]}, "members must be unique"),
        (
            {"subject_component_ids": [DIGEST_A, DIGEST_A]},
            "subject references must be unique",
        ),
        ({"subject_component_ids": []}, "single-subject components require one"),
        (
            {"composition": "multi_subject"},
            "multi-subject components require multiple",
        ),
        (
            {"composition": "unknown"},
            "unknown-composition components cannot claim",
        ),
    ],
)
def test_identity_component_composition_matches_subject_cardinality(
    updates: dict[str, Any],
    message: str,
) -> None:
    component = {
        "component_id": DIGEST_B,
        "member_entity_ids": ["spc-a"],
        "subject_component_ids": [DIGEST_A],
        "composition": "single_subject",
    }
    component.update(updates)

    _reject(IdentityComponent, component, message)


def test_resolved_node_and_aggregate_reject_duplicate_or_open_counts() -> None:
    _reject(
        ResolvedIdentityNode,
        {
            "entity_id": "spc-a",
            "kind": "specimen",
            "component_id": DIGEST_B,
            "subject_component_ids": [DIGEST_A, DIGEST_A],
        },
        "subject component identifiers must be unique",
    )
    _reject(
        ConcordanceAggregate,
        {"informative_loci": 2, "concordant_loci": 1, "discordant_loci": 0},
        "aggregate locus counts must sum",
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "operation_id": "op-resolved",
                "kind": "pooled_from",
                "source_entity_ids": ["alq-a"],
                "target_entity_ids": ["alq-pool"],
            },
            "resolved pooled-from operation requires N-to-one",
        ),
        (
            {
                "operation_id": "op-resolved",
                "kind": "demultiplexed_from",
                "source_entity_ids": ["ana-pool"],
                "target_entity_ids": ["ana-a", "ana-b"],
                "mixed_subject": True,
            },
            "resolved demultiplexed-from operation requires one-to-N",
        ),
        (
            {
                "operation_id": "op-resolved",
                "kind": "collected_from",
                "source_entity_ids": ["pat-a"],
                "target_entity_ids": ["spc-a", "spc-b"],
            },
            "resolved ordinary operation requires one-to-one",
        ),
    ],
)
def test_resolved_lineage_operation_keeps_public_cardinality_closed(
    payload: dict[str, Any],
    message: str,
) -> None:
    _reject(ResolvedLineageOperation, payload, message)


def _rebind_configuration(payload: dict[str, Any]) -> None:
    policy = IdentityResolutionPolicy.model_validate_json(
        json.dumps(payload["policy"]),
        strict=True,
    )
    payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        policy_digest(policy)
    )


@pytest.mark.parametrize(
    ("case_id", "mutation", "message"),
    [
        (
            "complete_ordinary_lineage",
            lambda value: value["context"]["references"]["identity_authority"].update(
                state="rejected"
            ),
            "identity authority does not authorize",
        ),
        (
            "complete_ordinary_lineage",
            lambda value: value["context"]["references"]["quality"].update(state="rejected"),
            "upstream control does not authorize",
        ),
        (
            "complete_ordinary_lineage",
            lambda value: value["policy"].update(max_entities=6),
            "entity count exceeds the active policy",
        ),
        (
            "authorized_explicit_same_as",
            lambda value: value["policy"].update(max_assertions=1),
            "assertion count exceeds the active policy",
        ),
        (
            "complete_ordinary_lineage",
            lambda value: value["policy"].update(max_operations=5),
            "lineage operation count exceeds the active policy",
        ),
        (
            "complete_ordinary_lineage",
            lambda value: value["context"]["references"]["approved_configuration"][
                "evidence"
            ].update(digest=DIGEST_A),
            "approved configuration does not bind",
        ),
        (
            "authorized_explicit_same_as",
            lambda value: value["assertions"][0].update(authority_decision_id="wrong"),
            "assertion authority does not match",
        ),
        (
            "authorized_explicit_same_as",
            lambda value: value["assertions"][0].update(policy_version="2.0.0"),
            "assertion does not bind the active policy",
        ),
        (
            "complete_ordinary_lineage",
            lambda value: value["lineage_operations"][0].update(
                authority_decision_id="wrong"
            ),
            "lineage operation authority does not match",
        ),
        (
            "complete_ordinary_lineage",
            lambda value: value["lineage_operations"][0].update(policy_version="2.0.0"),
            "lineage operation does not bind the active policy",
        ),
        (
            "concordance_never_implicitly_merges",
            lambda value: value["concordance_observations"][0].update(target_id="unknown"),
            "concordance observation references an unknown entity",
        ),
    ],
)
def test_request_cross_record_authority_and_policy_bindings(
    case_id: str,
    mutation: Mutation,
    message: str,
) -> None:
    request = _payload(case_id)
    mutation(request)

    _reject(ReconcileIdentityLineageRequest, request, message)


def test_request_rejects_disabled_operation_after_configuration_rebinding() -> None:
    request = _payload()
    request["policy"]["allowed_operation_kinds"].remove("collected_from")
    _rebind_configuration(request)

    _reject(
        ReconcileIdentityLineageRequest,
        request,
        "lineage operation is disabled by the active policy",
    )


def test_policy_and_issue_collections_use_domain_identity_not_list_position() -> None:
    policy = deepcopy(_payload()["policy"])
    policy["allowed_operation_kinds"].append(policy["allowed_operation_kinds"][0])
    _reject(IdentityResolutionPolicy, policy, "operation kinds must be unique")

    issue = {
        "code": "identity.test",
        "severity": "warning",
        "action": "record",
        "evidence_basis_digest": DIGEST_A,
        "evidence_reference_count": 0,
        "entity_ids": ["spc-a", "spc-a"],
        "message": "synthetic boundary",
    }
    _reject(IdentityIssue, issue, "identity issue references must be unique")


def _output_payload(tmp_path: Path, case_id: str = "complete_ordinary_lineage") -> dict[str, Any]:
    request = ReconcileIdentityLineageRequest.model_validate_json(
        json.dumps(_payload(case_id)),
        strict=True,
    )
    with M0102EventStore(tmp_path / f"{case_id}.sqlite3") as store:
        output = M0102Service(store).execute(request)
    return output.model_dump(mode="json")


def _reject_output(payload: dict[str, Any], message: str) -> None:
    _reject(IdentityLineageResolution, payload, message)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_component", "component identifiers must be unique"),
        ("duplicate_member", "resolved entities must occur in exactly one"),
        ("node_coverage", "nodes must exactly cover"),
        ("wrong_component", "node references the wrong identity component"),
        ("unknown_subject", "component references an unknown subject component"),
        ("nonpatient_subject", "subject component does not contain a patient node"),
    ],
)
def test_resolution_rejects_incoherent_component_graph_bindings(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    payload = _output_payload(tmp_path, "authorized_explicit_same_as")
    components = payload["components"]
    nodes = payload["graph"]["nodes"]
    if case == "duplicate_component":
        components[1]["component_id"] = components[0]["component_id"]
    elif case == "duplicate_member":
        components[0]["member_entity_ids"].append(components[1]["member_entity_ids"][0])
    elif case == "node_coverage":
        nodes.pop()
    elif case == "wrong_component":
        nodes[0]["component_id"] = components[1]["component_id"]
    elif case == "unknown_subject":
        component = next(value for value in components if value["composition"] == "single_subject")
        component["subject_component_ids"] = [DIGEST_A]
    else:
        specimen_component = next(
            value for value in components if "spc-a" in value["member_entity_ids"]
        )
        specimen_component["subject_component_ids"] = [specimen_component["component_id"]]
        for node in nodes:
            if node["entity_id"] in specimen_component["member_entity_ids"]:
                node["subject_component_ids"] = [specimen_component["component_id"]]
    payload["graph"]["graph_digest"] = "sha256:" + ("0" * 64)
    payload["resolution_digest"] = "sha256:" + ("0" * 64)

    _reject_output(payload, message)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("evidence_count", "exactly seven control evidence"),
        ("evidence_claim", "claim is not uniquely role-bound"),
        ("consent_state", "consent control must be granted"),
        ("input_digest", "input digests are incomplete"),
        ("control_roles", "record all seven controls exactly once"),
    ],
)
def test_resolution_rejects_incoherent_control_provenance(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    payload = _output_payload(tmp_path)
    if case == "evidence_count":
        payload["evidence"].pop()
    elif case == "evidence_claim":
        payload["evidence"][0]["claim"] = "unrecognized control claim"
    elif case == "consent_state":
        consent = next(
            value
            for value in payload["provenance"]["control_decisions"]
            if value["role"] == "consent"
        )
        consent["state"] = "withheld"
    elif case == "input_digest":
        payload["provenance"]["input_digests"].remove(payload["request_digest"])
    else:
        controls = payload["provenance"]["control_decisions"]
        controls[-1]["role"] = controls[0]["role"]
    payload["resolution_digest"] = "sha256:" + ("0" * 64)

    _reject_output(payload, message)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("core", "envelope does not bind its semantic core"),
        ("payload_digest", "resolution digest does not match"),
        ("decision", "decision contradicts its issue actions"),
        ("review", "human-review flag contradicts"),
        ("support", "support contradicts its decision"),
        ("duplicate_limitation", "limitation codes must be unique"),
        ("missing_limitation", "missing a mandatory M01-02 limitation"),
    ],
)
def test_resolution_rejects_forged_decision_and_digest_envelope(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    payload = _output_payload(tmp_path)
    if case == "core":
        payload["core_digest"] = DIGEST_A
    elif case == "payload_digest":
        payload["resolution_digest"] = DIGEST_A
    elif case == "decision":
        payload["decision"] = "unresolved"
    elif case == "review":
        payload["human_review_required"] = True
    elif case == "support":
        payload["support"]["reason_code"] = "forged_reason"
    elif case == "duplicate_limitation":
        payload["limitations"][1] = deepcopy(payload["limitations"][0])
    else:
        payload["limitations"][-1]["code"] = "synthetic_additional_limitation"

    _reject_output(payload, message)


def test_draft_rejects_a_forged_core_digest() -> None:
    request = ReconcileIdentityLineageRequest.model_validate_json(
        json.dumps(_payload()),
        strict=True,
    )
    draft = reconcile_identity_lineage(request).model_dump(mode="json")
    draft["core_digest"] = DIGEST_A

    _reject(IdentityLineageResolutionDraft, draft, "core digest does not match")
