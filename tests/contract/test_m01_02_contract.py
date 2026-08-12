"""Locked public-contract behavior for M01-02 identity reconciliation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_02 import v1 as m0102_contract
from glio_proteogen.contracts.m01_02.canonical import canonical_request_digest
from glio_proteogen.contracts.m01_02.canonical import policy_digest as canonical_policy_digest
from glio_proteogen.contracts.m01_02.schema import (
    CONTRACT_VERSION,
    JSON_SCHEMA_DIALECT,
    SCHEMA_ID_PREFIX,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.contracts.m01_02.v1 import (
    ConcordanceAggregate,
    IdentityEntity,
    IdentityIssue,
    IdentityIssueAction,
    IdentityIssueSeverity,
    IdentityLineageResolution,
    LineageOperation,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    M0102Service,
)

pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
SNAPSHOT_PATH = ROOT / "tests" / "snapshots" / "m01_02" / "schema_digests.json"
PUBLIC_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "policy",
    "entity",
    "operation",
    "resolution",
)
DERIVED_DIGEST_SENTINEL = "sha256:" + ("0" * 64)
EXPECTED_MAX_INFORMATIVE_LOCI = 500_000_000_000
EXPECTED_DIAMOND_PRODUCERS = 2


def _corpus() -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _request_payload(case_id: str = "complete_ordinary_lineage") -> dict[str, Any]:
    scenario = next(
        scenario for scenario in _corpus()["scenarios"] if scenario["case_id"] == case_id
    )
    return cast("dict[str, Any]", deepcopy(scenario["request"]))


def _request(case_id: str = "complete_ordinary_lineage") -> ReconcileIdentityLineageRequest:
    return TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
        json.dumps(_request_payload(case_id)),
        strict=True,
    )


def _resolution_payload(
    tmp_path: Path,
    case_id: str = "complete_ordinary_lineage",
) -> dict[str, Any]:
    with M0102EventStore(tmp_path / f"{case_id}.sqlite3") as store:
        output = M0102Service(store).execute(_request(case_id))
    return cast("dict[str, Any]", output.model_dump(mode="json"))


def _reset_resolution_digests(payload: dict[str, Any], *, graph: bool = False) -> None:
    if graph:
        payload["graph"]["graph_digest"] = DERIVED_DIGEST_SENTINEL
    payload["resolution_digest"] = DERIVED_DIGEST_SENTINEL


def _assert_output_rejected(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TypeAdapter(IdentityLineageResolution).validate_json(
            json.dumps(payload),
            strict=True,
        )


def _definition(schema: dict[str, Any], name: str) -> dict[str, Any]:
    if schema.get("title") == name:
        return schema
    return cast("dict[str, Any]", schema["$defs"][name])


def test_public_json_schema_snapshots_are_locked() -> None:
    expected = strict_json_loads(SNAPSHOT_PATH.read_bytes())
    documents = {name: contract_json_schema(name) for name in PUBLIC_SCHEMA_NAMES}
    actual = {
        "contract_version": CONTRACT_VERSION,
        "dialect": JSON_SCHEMA_DIALECT,
        "schemas": {
            name: {"$id": document["$id"], "digest": sha256_digest(document)}
            for name, document in documents.items()
        },
    }

    assert actual == expected


@pytest.mark.parametrize("name", PUBLIC_SCHEMA_NAMES)
def test_public_schema_is_self_identifying_draft_2020_12(name: ContractName) -> None:
    document = contract_json_schema(name)

    assert document["$schema"] == JSON_SCHEMA_DIALECT
    assert document["$id"] == f"{SCHEMA_ID_PREFIX}:{name}"
    Draft202012Validator.check_schema(document)


@pytest.mark.parametrize("name", PUBLIC_SCHEMA_NAMES)
def test_public_schema_declares_authoritative_strict_runtime(name: ContractName) -> None:
    profile = cast(
        "dict[str, Any]",
        contract_json_schema(name)["x-glio-validation-profile"],
    )

    assert profile == {
        "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
        "scope": "structural schema plus expressible relational invariants",
        "strictJson": True,
        "silentCoercion": False,
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus the M01-02 solver",
        "extensionKeywords": [
            "x-glio-uniqueBy",
            "x-glio-uniqueByFields",
            "x-glio-relationalInvariants",
        ],
    }


def test_public_schema_extensions_name_domain_identity_keys() -> None:
    request = cast("dict[str, Any]", contract_json_schema("request"))
    output = cast("dict[str, Any]", contract_json_schema("output"))

    request_root = _definition(request, "ReconcileIdentityLineageRequest")
    assert request_root["properties"]["entities"]["x-glio-uniqueBy"] == "/entity_id"
    assert request_root["properties"]["assertions"]["x-glio-uniqueBy"] == "/assertion_id"
    assert request_root["properties"]["lineage_operations"]["x-glio-uniqueBy"] == (
        "/operation_id"
    )
    assert request_root["properties"]["concordance_observations"][
        "x-glio-uniqueBy"
    ] == "/observation_id"
    assert _definition(request, "IdentityEntity")["properties"]["identity_tokens"][
        "x-glio-uniqueByFields"
    ] == [
        "/issuer_id",
        "/namespace_id",
        "/scope_id",
        "/key_id",
        "/token_version",
    ]
    assert _definition(request, "IdentityEntity")["properties"]["evidence"][
        "x-glio-uniqueByFields"
    ] == ["/artifact_id", "/version", "/digest", "/media_type"]
    output_root = _definition(output, "IdentityLineageResolution")
    assert output_root["properties"]["components"]["x-glio-uniqueBy"] == (
        "/component_id"
    )
    assert output_root["properties"]["evidence"]["x-glio-uniqueByFields"] == [
        "/reference/artifact_id",
        "/reference/version",
        "/reference/digest",
        "/reference/media_type",
        "/role",
        "/claim",
    ]
    assert output_root["properties"]["limitations"]["x-glio-uniqueBy"] == "/code"
    assert _definition(output, "IdentityProvenanceRecord")["properties"][
        "control_decisions"
    ]["x-glio-uniqueBy"] == "/role"


def test_runtime_request_and_standard_schema_accept_locked_positive() -> None:
    payload = _request_payload()
    schema = contract_json_schema("request")

    standard_errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
    )
    runtime = TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
        json.dumps(payload),
        strict=True,
    )

    assert not standard_errors
    assert runtime.operation == "reconcile"


def test_denied_contract_checks_authorization_before_policy_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _request_payload()
    payload["context"]["references"]["consent"]["state"] = "revoked"
    calls = 0

    def tracked_policy_digest(policy: Any) -> str:
        nonlocal calls
        calls += 1
        return canonical_policy_digest(policy)

    monkeypatch.setattr(m0102_contract, "policy_digest", tracked_policy_digest)

    with pytest.raises(ValidationError, match="consent does not authorize"):
        TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
            json.dumps(payload),
            strict=True,
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("mutation", "runtime_error"),
    [
        (lambda payload: payload.update(operation="recommend"), "literal_error"),
        (lambda payload: payload.update(unknown="field"), "extra_forbidden"),
        (lambda payload: payload["entities"].clear(), "too_short"),
    ],
)
def test_standard_schema_or_runtime_rejects_closed_boundary_violation(
    mutation: Any,
    runtime_error: str,
) -> None:
    payload = _request_payload()
    mutation(payload)
    standard_errors = list(
        Draft202012Validator(
            contract_json_schema("request"),
            format_checker=FormatChecker(),
        ).iter_errors(payload)
    )

    with pytest.raises(ValidationError, match=runtime_error):
        TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
            json.dumps(payload),
            strict=True,
        )
    assert standard_errors


def test_runtime_relational_profile_rejects_duplicate_entity_ids() -> None:
    payload = _request_payload()
    payload["entities"].append(deepcopy(payload["entities"][0]))

    with pytest.raises(ValidationError, match="entity identifiers must be unique"):
        TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
            json.dumps(payload),
            strict=True,
        )


def test_concordance_aggregate_covers_the_full_legal_locus_domain() -> None:
    maximum = m0102_contract.M0102_MAX_OBSERVATIONS * 10_000_000

    aggregate = ConcordanceAggregate(
        informative_loci=maximum,
        concordant_loci=maximum,
    )

    assert m0102_contract.M0102_MAX_INFORMATIVE_LOCI == EXPECTED_MAX_INFORMATIVE_LOCI
    assert aggregate.informative_loci == maximum
    with pytest.raises(ValidationError, match="less than or equal to 500000000000"):
        ConcordanceAggregate(
            informative_loci=maximum + 1,
            concordant_loci=maximum + 1,
        )


def test_request_rejects_multiple_material_producers_even_for_one_patient() -> None:
    payload = _request_payload()
    second_producer = deepcopy(payload["lineage_operations"][3])
    second_producer["operation_id"] = "op-material-bypass"
    second_producer["source_entity_ids"] = ["alq-a"]
    payload["lineage_operations"].append(second_producer)

    with pytest.raises(ValidationError, match="more than one producing operation"):
        TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
            json.dumps(payload),
            strict=True,
        )


def test_request_preserves_duplicate_operation_review_semantics() -> None:
    payload = _request_payload()
    logical_duplicate = deepcopy(payload["lineage_operations"][1])
    logical_duplicate["operation_id"] = "op-logical-duplicate"
    payload["lineage_operations"].append(logical_duplicate)

    request = TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
        json.dumps(payload),
        strict=True,
    )

    assert len(request.lineage_operations) == len(payload["lineage_operations"])


def test_request_allows_multiple_computed_producers_for_a_derived_object() -> None:
    request = _request("acyclic_diamond_is_not_cycle")

    producers = [
        operation
        for operation in request.lineage_operations
        if "obj-c" in operation.target_entity_ids
    ]

    assert len(producers) == EXPECTED_DIAMOND_PRODUCERS
    assert {operation.kind.value for operation in producers} == {"computed_from"}


def test_unknown_lineage_target_is_a_validation_error_not_a_key_error() -> None:
    payload = _request_payload()
    payload["lineage_operations"][0]["target_entity_ids"] = ["missing-target"]

    with pytest.raises(ValidationError, match="unknown entity"):
        TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
            json.dumps(payload),
            strict=True,
        )


def test_request_digest_is_invariant_to_unordered_collection_permutations() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["entities"].reverse()
    payload["lineage_operations"].reverse()
    for operation in payload["lineage_operations"]:
        operation["source_entity_ids"].reverse()
        operation["target_entity_ids"].reverse()
    permuted = TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
        json.dumps(payload),
        strict=True,
    )

    assert canonical_request_digest(permuted) == canonical_request_digest(request)


def test_request_digest_normalizes_symmetric_endpoint_orientation() -> None:
    request = _request("authorized_explicit_same_as")
    payload = request.model_dump(mode="json")
    assertion = payload["assertions"][0]
    assertion["left_entity_id"], assertion["right_entity_id"] = (
        assertion["right_entity_id"],
        assertion["left_entity_id"],
    )
    reversed_request = TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
        json.dumps(payload),
        strict=True,
    )

    assert canonical_request_digest(reversed_request) == canonical_request_digest(request)


def test_contract_models_revalidate_forged_instances() -> None:
    request = _request()
    forged = request.model_copy(update={"entities": (request.entities[0], request.entities[0])})

    with pytest.raises(ValidationError, match="entity identifiers must be unique"):
        TypeAdapter(ReconcileIdentityLineageRequest).validate_python(forged, strict=True)


def test_entity_and_operation_contracts_reject_silent_coercion() -> None:
    request = _request()
    entity = request.entities[0].model_dump(mode="json")
    entity["composition"] = 1
    operation = request.lineage_operations[0].model_dump(mode="json")
    operation["mixed_subject"] = "false"

    with pytest.raises(ValidationError):
        TypeAdapter(IdentityEntity).validate_json(json.dumps(entity), strict=True)
    with pytest.raises(ValidationError):
        TypeAdapter(LineageOperation).validate_json(json.dumps(operation), strict=True)


def test_public_output_round_trips_through_runtime_and_standard_schema(tmp_path: Path) -> None:
    with M0102EventStore(tmp_path / "ledger.sqlite3") as store:
        output = M0102Service(store).execute(_request())
    encoded = canonical_json_bytes(output)
    decoded = TypeAdapter(IdentityLineageResolution).validate_json(encoded, strict=True)
    standard_errors = list(
        Draft202012Validator(
            contract_json_schema("output"),
            format_checker=FormatChecker(),
        ).iter_errors(json.loads(encoded))
    )

    assert decoded == output
    assert not standard_errors


def test_public_output_rejects_duplicate_top_level_evidence(tmp_path: Path) -> None:
    with M0102EventStore(tmp_path / "ledger.sqlite3") as store:
        output = M0102Service(store).execute(_request())
    payload = output.model_dump(mode="json")
    payload["evidence"][-1] = deepcopy(payload["evidence"][0])

    with pytest.raises(ValidationError, match="resolution evidence references must be unique"):
        TypeAdapter(IdentityLineageResolution).validate_json(
            json.dumps(payload),
            strict=True,
        )


def test_public_output_rejects_node_component_subject_disagreement(tmp_path: Path) -> None:
    with M0102EventStore(tmp_path / "ledger.sqlite3") as store:
        output = M0102Service(store).execute(_request())
    payload = output.model_dump(mode="json")
    specimen = next(node for node in payload["graph"]["nodes"] if node["entity_id"] == "spc-a")
    specimen["subject_component_ids"] = [specimen["component_id"]]
    payload["graph"]["graph_digest"] = DERIVED_DIGEST_SENTINEL
    payload["core_digest"] = DERIVED_DIGEST_SENTINEL
    payload["resolution_digest"] = DERIVED_DIGEST_SENTINEL

    with pytest.raises(ValidationError, match="subject bindings contradict"):
        TypeAdapter(IdentityLineageResolution).validate_json(
            json.dumps(payload),
            strict=True,
        )


def test_public_output_rejects_semantically_invalid_resolved_transition(
    tmp_path: Path,
) -> None:
    with M0102EventStore(tmp_path / "ledger.sqlite3") as store:
        output = M0102Service(store).execute(_request())
    payload = output.model_dump(mode="json")
    payload["graph"]["operations"][0]["kind"] = "computed_from"
    payload["graph"]["graph_digest"] = DERIVED_DIGEST_SENTINEL
    payload["core_digest"] = DERIVED_DIGEST_SENTINEL
    payload["resolution_digest"] = DERIVED_DIGEST_SENTINEL

    with pytest.raises(ValidationError, match="transition is not allowed"):
        TypeAdapter(IdentityLineageResolution).validate_json(
            json.dumps(payload),
            strict=True,
        )


def test_public_graph_rejects_multiple_material_producers(tmp_path: Path) -> None:
    payload = _resolution_payload(tmp_path)
    second_producer = deepcopy(payload["graph"]["operations"][3])
    second_producer["operation_id"] = "op-forged-second-producer"
    second_producer["source_entity_ids"] = ["alq-a"]
    payload["graph"]["operations"].append(second_producer)
    _reset_resolution_digests(payload, graph=True)

    _assert_output_rejected(payload, "more than one producing operation")


def test_public_output_rejects_resolved_ordinary_cross_patient_forgery(
    tmp_path: Path,
) -> None:
    payload = _resolution_payload(tmp_path)
    patient_component = next(
        node["component_id"]
        for node in payload["graph"]["nodes"]
        if node["kind"] == "patient"
    )
    target = next(
        node
        for node in payload["graph"]["nodes"]
        if node["entity_id"] == "alq-a"
    )
    target["subject_component_ids"] = []
    component = next(
        component
        for component in payload["components"]
        if component["component_id"] == target["component_id"]
    )
    component["subject_component_ids"] = []
    component["composition"] = "unknown"
    assert patient_component
    _reset_resolution_digests(payload, graph=True)

    _assert_output_rejected(payload, "ordinary lineage subject semantics require quarantine")


def test_public_output_rejects_resolved_pool_mixed_flag_forgery(tmp_path: Path) -> None:
    payload = _resolution_payload(tmp_path, "explicit_pool_preserves_multiple_patients")
    payload["graph"]["operations"][0]["mixed_subject"] = False
    _reset_resolution_digests(payload, graph=True)

    _assert_output_rejected(payload, "pooled lineage subject semantics require quarantine")


def test_public_output_rejects_resolved_demultiplex_containment_forgery(
    tmp_path: Path,
) -> None:
    payload = _resolution_payload(tmp_path, "explicit_pool_preserves_multiple_patients")
    pool_operation = payload["graph"]["operations"][0]
    target_id = pool_operation["target_entity_ids"][0]
    source_ids = list(pool_operation["source_entity_ids"])
    pool_operation.update(
        operation_id="op-forged-demultiplex",
        kind="demultiplexed_from",
        source_entity_ids=[source_ids[0]],
        target_entity_ids=[source_ids[1], target_id],
        mixed_subject=False,
    )
    _reset_resolution_digests(payload, graph=True)

    _assert_output_rejected(
        payload,
        "demultiplex target subjects must be contained by the source",
    )


def test_cross_kind_component_requires_exact_bound_quarantine_issue(tmp_path: Path) -> None:
    payload = _resolution_payload(tmp_path, "cross_kind_assertion_quarantine")
    assert payload["issues"][0]["code"] == "component.cross_kind"
    TypeAdapter(IdentityLineageResolution).validate_json(json.dumps(payload), strict=True)

    payload["issues"][0]["component_ids"] = []
    _reset_resolution_digests(payload)

    _assert_output_rejected(payload, "mixed-kind identity component requires")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["provenance"]["control_decisions"][0].update(
                state="rejected"
            ),
            "upstream controls must be accepted",
        ),
        (
            lambda payload: payload["provenance"].update(consent_decision_id="forged"),
            "consent fields contradict",
        ),
        (
            lambda payload: payload["provenance"].update(
                configuration_digest="sha256:" + ("f" * 64)
            ),
            "configuration digest contradicts",
        ),
        (
            lambda payload: payload["evidence"][0]["reference"].update(
                digest="sha256:" + ("f" * 64)
            ),
            "control evidence contradicts",
        ),
        (
            lambda payload: payload["provenance"]["input_digests"].clear(),
            "too_short|input digests are incomplete",
        ),
        (
            lambda payload: payload["provenance"].update(
                generated_at="2026-08-11T00:00:01Z"
            ),
            "timestamp contradicts",
        ),
        (
            lambda payload: payload["provenance"].update(module_version="9.9.9"),
            "module version contradicts",
        ),
        (
            lambda payload: payload.update(resolution_id="resolution.forged"),
            "identifier does not bind",
        ),
        (
            lambda payload: payload["provenance"].update(activity_id="activity.forged"),
            "activity does not bind",
        ),
    ],
)
def test_public_output_rejects_forged_envelope_cross_bindings(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    payload = _resolution_payload(tmp_path)
    mutation(payload)
    _reset_resolution_digests(payload)

    _assert_output_rejected(payload, message)


def test_identity_issue_requires_complete_evidence_binding_metadata() -> None:
    schema = contract_json_schema("output")
    issue_schema = _definition(schema, "IdentityIssue")

    assert {"evidence_basis_digest", "evidence_reference_count"}.issubset(
        issue_schema["required"]
    )
    with pytest.raises(ValidationError, match="Field required"):
        TypeAdapter(IdentityIssue).validate_python(
            {
                "code": "lineage.test",
                "severity": "critical",
                "action": "quarantine",
                "message": "test issue",
            },
            strict=True,
        )


def test_identity_issue_rejects_silent_evidence_truncation() -> None:
    request = _request()

    with pytest.raises(ValidationError, match="cannot be smaller than retained evidence"):
        TypeAdapter(IdentityIssue).validate_python(
            {
                "code": "lineage.test",
                "severity": IdentityIssueSeverity.CRITICAL,
                "action": IdentityIssueAction.QUARANTINE,
                "evidence_basis_digest": "sha256:" + ("a" * 64),
                "evidence_reference_count": 0,
                "message": "test issue",
                "evidence": (request.entities[0].evidence[0],),
            },
            strict=True,
        )
