"""Negative replay, firewall, and release-harness closure for M05-02."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from enum import StrEnum
from typing import TYPE_CHECKING, Self, cast

import pytest
from evals.m05_02 import benchmark as benchmark_module
from evals.m05_02 import run as evaluation_module
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m05_02 import (
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationIdentityLineageFinding,
    PtmLocalizationIdentityLineagePolicy,
    PtmLocalizationIdentityLineageReceipt,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactClaim,
    PtmLocalizationLineageDisposition,
    ReconcilePtmLocalizationIdentityLineageRequest,
    ResolvedPtmLocalizationIdentityLineageGraph,
    ResolvedPtmLocalizationLineageArtifact,
    ResolvedPtmLocalizationLineageDerivation,
    configuration_digest,
    expected_receipt,
    physical_lineage_path_digest,
    ptm_localization_lineage_evidence_index,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    M0502Plugin,
    M0502Service,
    PtmLocalizationIdentityLineageAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    engine as engine_module,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    plugin as plugin_module,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _digest(character: str) -> str:
    return "sha256:" + (character * 64)


def _identifier(namespace: str, character: str) -> str:
    return f"{namespace}.{character * 64}"


def _json_payload(model: BaseModel) -> dict[str, object]:
    return cast("dict[str, object]", model.model_dump(mode="json", exclude_none=False))


def _assert_json_rejected(
    model: type[BaseModel],
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        model.model_validate_json(canonical_json_bytes(payload), strict=True)


def _claim_clone(payload: dict[str, object], character: str) -> dict[str, object]:
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    clone = copy.deepcopy(claims[0])
    clone["claim_id"] = _identifier("claim", character)
    artifact = cast("dict[str, object]", clone["artifact"])
    artifact["artifact_id"] = _identifier("evidence", character)
    artifact["digest"] = _digest(character)
    return clone


def test_owned_policy_and_claim_validators_reject_aliasing_and_wrong_media() -> None:
    request = evaluation_module.build_scenario_request()

    claim = _json_payload(request.artifact_claims[0])
    claim_artifact = cast("dict[str, object]", claim["artifact"])
    claim_artifact["media_type"] = "application/json"
    _assert_json_rejected(
        PtmLocalizationLineageArtifactClaim,
        claim,
        "artifact media type is outside its exact role",
    )

    claim = _json_payload(request.artifact_claims[0])
    subjects = cast("list[str]", claim["declared_subject_component_ids"])
    claim["declared_subject_component_ids"] = [subjects[0], subjects[0]]
    _assert_json_rejected(
        PtmLocalizationLineageArtifactClaim,
        claim,
        "subject component identifiers must be unique",
    )

    policy = _json_payload(request.policy)
    configurations = cast("list[dict[str, object]]", policy["approved_configurations"])
    policy_evidence = cast("dict[str, object]", policy["evidence"])
    configuration_evidence = cast("dict[str, object]", configurations[0]["evidence"])
    configuration_evidence["digest"] = policy_evidence["digest"]
    _assert_json_rejected(
        PtmLocalizationIdentityLineagePolicy,
        policy,
        "policy evidence digests must be unique",
    )

    policy = _json_payload(request.policy)
    configurations = cast("list[dict[str, object]]", policy["approved_configurations"])
    policy_evidence = cast("dict[str, object]", policy["evidence"])
    configuration_evidence = cast("dict[str, object]", configurations[0]["evidence"])
    configuration_evidence["artifact_id"] = policy_evidence["artifact_id"]
    configuration_evidence["version"] = policy_evidence["version"]
    _assert_json_rejected(
        PtmLocalizationIdentityLineagePolicy,
        policy,
        "policy evidence artifact identities must be unique",
    )

    policy = _json_payload(request.policy)
    configurations = cast("list[dict[str, object]]", policy["approved_configurations"])
    duplicate = copy.deepcopy(configurations[0])
    duplicate_evidence = cast("dict[str, object]", duplicate["evidence"])
    duplicate_evidence["artifact_id"] = _identifier("evidence", "a")
    duplicate_evidence["digest"] = _digest("a")
    policy["approved_configurations"] = [*configurations, duplicate]
    _assert_json_rejected(
        PtmLocalizationIdentityLineagePolicy,
        policy,
        "approved configuration and method identities must be unique",
    )


def test_embedded_upstream_guards_reject_invalid_types_and_public_sentinels() -> None:
    request = evaluation_module.build_scenario_request()
    payload = request.model_dump(mode="python", exclude_none=False)
    payload["identity_resolution"] = object()
    with pytest.raises(ValidationError):
        ReconcilePtmLocalizationIdentityLineageRequest.model_validate(payload, strict=True)

    payload = _json_payload(request)
    identity = cast("dict[str, object]", payload["identity_resolution"])
    identity["resolution_digest"] = _digest("0")
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "M01-02 derived digests must be final",
    )

    payload = request.model_dump(mode="python", exclude_none=False)
    payload["protocol_result"] = object()
    with pytest.raises(ValidationError):
        ReconcilePtmLocalizationIdentityLineageRequest.model_validate(payload, strict=True)

    payload = _json_payload(request)
    protocol = cast("dict[str, object]", payload["protocol_result"])
    protocol["result_digest"] = _digest("0")
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "M05-01 derived digests must be final",
    )


def test_request_closure_rejects_nontraversable_claims_and_policy_overflow() -> None:
    unsupported = _json_payload(
        evaluation_module.build_scenario_request("unsupported_configuration_abstained")
    )
    canonical = _json_payload(evaluation_module.build_scenario_request())
    unsupported["artifact_claims"] = canonical["artifact_claims"]
    unsupported["derivations"] = canonical["derivations"]
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        unsupported,
        "non-traversable inputs require an empty artifact region",
    )

    payload = _json_payload(evaluation_module.build_scenario_request())
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    claims.append(_claim_clone(payload, "b"))
    policy = cast("dict[str, object]", payload["policy"])
    policy["max_artifact_claims"] = 5
    context = cast("dict[str, object]", payload["context"])
    references = cast("dict[str, object]", context["references"])
    approved = cast("dict[str, object]", references["approved_configuration"])
    approved_evidence = cast("dict[str, object]", approved["evidence"])
    typed_policy = PtmLocalizationIdentityLineagePolicy.model_validate_json(
        canonical_json_bytes(policy), strict=True
    )
    approved_evidence["digest"] = configuration_digest(typed_policy)
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "artifact claims exceed the active policy",
    )

    payload = _json_payload(evaluation_module.build_scenario_request())
    context = cast("dict[str, object]", payload["context"])
    references = cast("dict[str, object]", context["references"])
    consent = cast("dict[str, object]", references["consent"])
    consent["state"] = "withheld"
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "lineage reconciliation is not authorized",
    )


def test_request_evidence_identity_and_dag_rejections_are_closed() -> None:
    payload = _json_payload(evaluation_module.build_scenario_request())
    policy = cast("dict[str, object]", payload["policy"])
    policy_evidence = cast("dict[str, object]", policy["evidence"])
    derivations = cast("list[dict[str, object]]", payload["derivations"])
    derivation_evidence = cast("dict[str, object]", derivations[0]["evidence"])
    derivation_evidence["artifact_id"] = policy_evidence["artifact_id"]
    derivation_evidence["version"] = policy_evidence["version"]
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "submitted evidence identity cannot declare conflicting content",
    )

    payload = _json_payload(evaluation_module.build_scenario_request())
    policy = cast("dict[str, object]", payload["policy"])
    policy_evidence = cast("dict[str, object]", policy["evidence"])
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    artifact = cast("dict[str, object]", claims[0]["artifact"])
    artifact["artifact_id"] = policy_evidence["artifact_id"]
    artifact["version"] = policy_evidence["version"]
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "artifact claim cannot contradict a control evidence identity",
    )

    request = evaluation_module.build_scenario_request()
    submitted_identities = {
        (item.artifact_id, item.version)
        for item in (
            request.context.references.approved_configuration.evidence,
            request.context.references.identity_lineage.evidence,
            request.context.references.provenance.evidence,
            request.context.references.consent.evidence,
            request.context.references.quality.evidence,
            request.context.references.support.evidence,
            request.context.references.intended_use.evidence,
            request.policy.evidence,
            *(entry.evidence for entry in request.policy.approved_derivation_methods),
            *(entry.evidence for entry in request.derivations),
        )
    }
    upstream = next(
        item.reference
        for item in request.protocol_result.evidence
        if item.reference.artifact_id.startswith("evidence.")
        and (item.reference.artifact_id, item.reference.version) not in submitted_identities
    )
    payload = _json_payload(request)
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    artifact = cast("dict[str, object]", claims[0]["artifact"])
    artifact["artifact_id"] = upstream.artifact_id
    artifact["version"] = upstream.version
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "artifact claim cannot contradict embedded upstream evidence content",
    )

    payload = _json_payload(evaluation_module.build_scenario_request())
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    claims[0]["role"] = "genome_manifest"
    artifact = cast("dict[str, object]", claims[0]["artifact"])
    artifact["media_type"] = "application/vnd.glio-proteogen.m05-02.genome-manifest+json"
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "DAG requires four source roles",
    )


def test_derivation_policy_target_and_completeness_rejections_are_distinct() -> None:
    payload = _json_payload(evaluation_module.build_scenario_request())
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    extra = _claim_clone(payload, "c")
    claims.append(extra)
    derivations = cast("list[dict[str, object]]", payload["derivations"])
    sources = cast("list[str]", derivations[0]["source_claim_ids"])
    sources.append(cast("str", extra["claim_id"]))
    policy = cast("dict[str, object]", payload["policy"])
    policy["max_derivation_sources"] = 4
    context = cast("dict[str, object]", payload["context"])
    references = cast("dict[str, object]", context["references"])
    approved = cast("dict[str, object]", references["approved_configuration"])
    approved_evidence = cast("dict[str, object]", approved["evidence"])
    typed_policy = PtmLocalizationIdentityLineagePolicy.model_validate_json(
        canonical_json_bytes(policy), strict=True
    )
    approved_evidence["digest"] = configuration_digest(typed_policy)
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "derivation sources exceed the active policy",
    )

    payload = _json_payload(evaluation_module.build_scenario_request())
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    derivations = cast("list[dict[str, object]]", payload["derivations"])
    source_ids = cast("list[str]", derivations[0]["source_claim_ids"])
    old_target = cast("str", derivations[0]["target_claim_id"])
    new_target = source_ids[0]
    derivations[0]["source_claim_ids"] = [*source_ids[1:], old_target]
    derivations[0]["target_claim_id"] = new_target
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "derivation must target the exact input bundle",
    )

    payload = _json_payload(evaluation_module.build_scenario_request())
    claims = cast("list[dict[str, object]]", payload["artifact_claims"])
    claims.append(_claim_clone(payload, "d"))
    _assert_json_rejected(
        ReconcilePtmLocalizationIdentityLineageRequest,
        payload,
        "derivation must consume every non-bundle claim",
    )


def test_finding_and_resolved_collection_validators_reject_duplicates() -> None:
    result = evaluation_module.build_scenario_result("identity_swap_quarantined")
    finding = _json_payload(result.findings[0])
    claim_ids = cast("list[str]", finding["claim_ids"])
    finding["claim_ids"] = [claim_ids[0], claim_ids[0]]
    _assert_json_rejected(
        PtmLocalizationIdentityLineageFinding,
        finding,
        "finding references must be unique",
    )

    finding = _json_payload(result.findings[0])
    finding["action"] = "record"
    _assert_json_rejected(
        PtmLocalizationIdentityLineageFinding,
        finding,
        "finding action contradicts its closed finding code",
    )

    artifact = _json_payload(result.graph.artifacts[0])
    subjects = cast("list[str]", artifact["resolved_subject_component_ids"])
    artifact["resolved_subject_component_ids"] = [subjects[0], subjects[0]]
    _assert_json_rejected(
        ResolvedPtmLocalizationLineageArtifact,
        artifact,
        "resolved artifact collections must be unique",
    )

    derivation = _json_payload(result.graph.derivations[0])
    sources = cast("list[str]", derivation["source_claim_ids"])
    derivation["source_claim_ids"] = [sources[0], sources[0]]
    _assert_json_rejected(
        ResolvedPtmLocalizationLineageDerivation,
        derivation,
        "resolved derivation collections must be unique",
    )


def test_resolved_graph_rejects_partial_shape_topology_and_forged_digest() -> None:
    empty = _json_payload(
        evaluation_module.build_scenario_result("unsupported_configuration_abstained").graph
    )
    empty["graph_digest"] = _digest("e")
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        empty,
        "empty M05-02 graph digest",
    )

    canonical = _json_payload(evaluation_module.build_scenario_result().graph)
    partial = copy.deepcopy(canonical)
    partial["derivations"] = []
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        partial,
        "partial artifact region",
    )

    wrong_roles = copy.deepcopy(canonical)
    artifacts = cast("list[dict[str, object]]", wrong_roles["artifacts"])
    artifacts[0]["role"] = "variant_peptide_input_bundle"
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        wrong_roles,
        "exact five-role shape",
    )

    unknown_endpoint = copy.deepcopy(canonical)
    derivations = cast("list[dict[str, object]]", unknown_endpoint["derivations"])
    source_ids = cast("list[str]", derivations[0]["source_claim_ids"])
    source_ids[0] = _identifier("claim", "e")
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        unknown_endpoint,
        "derivation endpoints are not closed",
    )

    incomplete = copy.deepcopy(canonical)
    derivations = cast("list[dict[str, object]]", incomplete["derivations"])
    source_ids = cast("list[str]", derivations[0]["source_claim_ids"])
    derivations[0]["source_claim_ids"] = source_ids[:3]
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        incomplete,
        "contradicts the closed artifact topology",
    )

    bad_propagation = copy.deepcopy(canonical)
    derivations = cast("list[dict[str, object]]", bad_propagation["derivations"])
    derivations[0]["propagated_subject_component_ids"] = []
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        bad_propagation,
        "subject propagation contradicts",
    )

    wrong_digest = copy.deepcopy(canonical)
    wrong_digest["graph_digest"] = _digest("f")
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        wrong_digest,
        "graph digest does not match",
    )


def test_resolved_graph_retains_collision_state_and_closed_artifact_codes() -> None:
    collision = _json_payload(
        evaluation_module.build_scenario_result("two_patient_cross_link_quarantined").graph
    )
    artifacts = cast("list[dict[str, object]]", collision["artifacts"])
    for artifact in artifacts:
        codes = cast("list[str]", artifact["finding_codes"])
        if "artifact_lineage_collision" in codes:
            artifact["finding_codes"] = [
                code for code in codes if code != "artifact_lineage_collision"
            ]
            break
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        collision,
        "retain divergent physical-lineage paths as a collision",
    )

    evidence = _json_payload(
        evaluation_module.build_scenario_result("evidence_missing_abstained").graph
    )
    artifacts = cast("list[dict[str, object]]", evidence["artifacts"])
    missing = next(item for item in artifacts if item["evidence_state"] == "missing")
    missing["finding_codes"] = []
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        evidence,
        "evidence-state finding contradicts",
    )

    duplicate = _json_payload(evaluation_module.build_scenario_result().graph)
    artifacts = cast("list[dict[str, object]]", duplicate["artifacts"])
    artifacts[1]["artifact_digest"] = artifacts[0]["artifact_digest"]
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        duplicate,
        "duplicate-content findings contradict",
    )

    foreign_code = _json_payload(evaluation_module.build_scenario_result().graph)
    artifacts = cast("list[dict[str, object]]", foreign_code["artifacts"])
    artifacts[0]["finding_codes"] = ["upstream_configuration_unsupported"]
    _assert_json_rejected(
        ResolvedPtmLocalizationIdentityLineageGraph,
        foreign_code,
        "non-artifact finding code",
    )


def test_receipt_replay_rejects_duplicate_codes_disposition_and_digest_forgery() -> None:
    result = evaluation_module.build_scenario_result("identity_swap_quarantined")
    receipt = _json_payload(result.receipt)
    codes = cast("list[str]", receipt["finding_codes"])
    receipt["finding_codes"] = [codes[0], codes[0]]
    _assert_json_rejected(
        PtmLocalizationIdentityLineageReceipt,
        receipt,
        "receipt finding codes must be unique",
    )

    canonical = evaluation_module.build_scenario_result()
    receipt = _json_payload(canonical.receipt)
    receipt["disposition"] = "abstained"
    _assert_json_rejected(
        PtmLocalizationIdentityLineageReceipt,
        receipt,
        "receipt disposition contradicts",
    )

    receipt = _json_payload(canonical.receipt)
    receipt["receipt_digest"] = _digest("a")
    _assert_json_rejected(
        PtmLocalizationIdentityLineageReceipt,
        receipt,
        "receipt digest does not match",
    )

    assert (
        expected_receipt(
            canonical.request,
            canonical.graph,
            PtmLocalizationLineageDisposition.RECONCILED,
        )
        == canonical.receipt
    )
    with pytest.raises(ValueError, match="receipt inputs do not replay"):
        expected_receipt(
            canonical.request,
            evaluation_module.build_scenario_result("unsupported_configuration_abstained").graph,
            PtmLocalizationLineageDisposition.RECONCILED,
        )
    with pytest.raises(ValueError, match="disposition contradicts its findings"):
        expected_receipt(
            canonical.request,
            canonical.graph,
            PtmLocalizationLineageDisposition.ABSTAINED,
            findings=canonical.findings,
        )


def test_public_path_digest_and_evidence_index_fail_closed_on_absent_or_oversized_input() -> None:
    request = evaluation_module.build_scenario_request()
    with pytest.raises(ValueError, match="anchor is absent"):
        physical_lineage_path_digest(request.identity_resolution, "missing-entity")

    forged = request.model_copy(
        update={"artifact_claims": request.artifact_claims * 100},
    )
    with pytest.raises(ValueError, match="evidence index exceeds"):
        ptm_localization_lineage_evidence_index(forged)


class _MappingSubclass(dict[str, object]):
    pass


class _OnlyMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise KeyError(key)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(())

    def __len__(self) -> int:
        return 0


class _BadEnum(StrEnum):
    VALUE = "value"


class _AccessCounter:
    def __init__(self) -> None:
        self.calls = 0

    def touched(self) -> None:
        self.calls += 1


class _HostileList(list[object]):
    def __init__(self, counter: _AccessCounter) -> None:
        list.__init__(self, ("sealed",))
        self.counter = counter

    def __len__(self) -> int:
        self.counter.touched()
        return list.__len__(self)

    def __iter__(self):  # type: ignore[no-untyped-def]
        self.counter.touched()
        return list.__iter__(self)


class _HostileTuple(tuple[object, ...]):
    __slots__ = ()

    def __new__(cls, counter: _AccessCounter) -> Self:
        return tuple.__new__(cls, (counter,))

    @property
    def counter(self) -> _AccessCounter:
        return cast("_AccessCounter", tuple.__getitem__(self, 0))

    def __len__(self) -> int:
        self.counter.touched()
        return tuple.__len__(self)

    def __iter__(self):  # type: ignore[no-untyped-def]
        self.counter.touched()
        return tuple.__iter__(self)


class _VirtualMapping:
    def __init__(self, counter: _AccessCounter) -> None:
        self.counter = counter

    def __len__(self) -> int:
        self.counter.touched()
        return 0

    def __iter__(self):  # type: ignore[no-untyped-def]
        self.counter.touched()
        return iter(())

    def __getitem__(self, key: object) -> object:
        self.counter.touched()
        raise KeyError


class _VirtualSequence:
    def __init__(self, counter: _AccessCounter) -> None:
        self.counter = counter

    def __len__(self) -> int:
        self.counter.touched()
        return 0

    def __getitem__(self, index: object) -> object:
        self.counter.touched()
        raise IndexError


Mapping.register(_VirtualMapping)
Sequence.register(_VirtualSequence)


class _StorageCollisionKey:
    def __init__(self) -> None:
        self.hash_calls = 0
        self.eq_calls = 0

    def __hash__(self) -> int:
        self.hash_calls += 1
        return hash("context")

    def __eq__(self, other: object) -> bool:
        self.eq_calls += 1
        return False


def test_plain_value_firewall_closes_container_depth_budget_and_enum_edges() -> None:
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._validate_plain_mapping(cast("dict[object, object]", _MappingSubclass()))
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._validate_plain_mapping(dict.fromkeys(range(513)))
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._validate_plain_mapping({cast("object", 1): None})
    with pytest.raises(engine_module.PtmLocalizationIdentityLineageInputError):
        engine_module._validate_outer_request_shape(object())
    assert engine_module._member(object(), "context") is None

    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value(None, _depth=73)
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value(None, _budget=[0])
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value([None] * 257)
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value((None,) * 257)
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value(_OnlyMapping())

    object.__setattr__(_BadEnum.VALUE, "_value_", 1)
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value(_BadEnum.VALUE)


@pytest.mark.parametrize(
    "candidate_factory",
    [
        _HostileList,
        _HostileTuple,
        _VirtualMapping,
        _VirtualSequence,
    ],
)
def test_plain_value_rejects_collection_subclasses_and_virtual_abcs_without_access(
    candidate_factory: Callable[[_AccessCounter], object],
) -> None:
    counter = _AccessCounter()
    candidate = candidate_factory(counter)

    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._plain_value(candidate)

    assert counter.calls == 0


def test_already_constructed_request_rejects_unknown_and_hostile_storage_without_access() -> None:
    request = evaluation_module.build_scenario_request()
    storage = cast(
        "dict[object, object]",
        object.__getattribute__(request, "__dict__"),
    )
    canary = _AccessCounter()
    dict.__setitem__(storage, "recursive_canary", canary)

    with pytest.raises(
        engine_module.PtmLocalizationIdentityLineageInputError,
        match="failed strict validation",
    ):
        M0502Service().execute(request)
    assert canary.calls == 0

    request = evaluation_module.build_scenario_request()
    storage = cast(
        "dict[object, object]",
        object.__getattribute__(request, "__dict__"),
    )
    collision = _StorageCollisionKey()
    dict.__setitem__(storage, collision, "sealed")
    collision.hash_calls = 0
    collision.eq_calls = 0

    with pytest.raises(PtmLocalizationIdentityLineageAuthorizationError):
        M0502Service().execute(request)
    assert collision.hash_calls == collision.eq_calls == 0


def test_engine_preflight_and_serialized_size_fail_before_nested_replay() -> None:
    with pytest.raises(PtmLocalizationIdentityLineageAuthorizationError):
        engine_module.preflight_ptm_localization_identity_lineage_authorization(
            {cast("object", 1): "hostile"}
        )

    request = evaluation_module.build_scenario_request()
    payload = request.model_dump(mode="python", exclude_none=False)
    payload["policy"] = _OnlyMapping()
    with pytest.raises(engine_module._InvalidPlainValueError):
        engine_module._prepare_request_candidate(payload)

    with pytest.raises(engine_module._SerializedRequestTooLargeError):
        engine_module._validate_json_request(
            request,
            b"x" * (M0502_MAX_CANONICAL_REQUEST_BYTES + 1),
        )


def test_plugin_descriptor_and_mutated_token_snapshot_fail_closed() -> None:
    plugin = M0502Plugin(M0502Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-02"

    token = plugin.validate(evaluation_module.build_scenario_request())
    object.__setattr__(token.request, "policy", object())
    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(TypeError, match="validated request token"),
    ):
        plugin.run(token)


def test_plugin_rejects_copied_tokens_and_deep_equal_upstream_replacement() -> None:
    plugin = M0502Plugin(M0502Service())
    token = plugin.validate(evaluation_module.build_scenario_request())

    for copied in (copy.copy(token), copy.deepcopy(token)):
        with pytest.raises(TypeError, match="validated request token"):
            plugin.run(copied)

    token = plugin.validate(evaluation_module.build_scenario_request())
    replacement = copy.deepcopy(token.request.identity_resolution)
    assert replacement == token.request.identity_resolution
    assert replacement is not token.request.identity_resolution
    object.__setattr__(token.request, "identity_resolution", replacement)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_plugin_rejects_stale_nested_upstream_mutation() -> None:
    plugin = M0502Plugin(M0502Service())
    token = plugin.validate(evaluation_module.build_scenario_request())
    object.__setattr__(
        token.request.protocol_result,
        "result_id",
        _identifier("result.m0501", "f"),
    )

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_plugin_json_validation_parses_and_prepares_once_before_private_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decode_calls = 0
    prepare_calls = 0
    original_decode = cast("Callable[..., object]", plugin_module.__dict__["_strict_json_loads"])
    original_prepare = engine_module._prepare_request_candidate

    def counted_decode(
        payload: bytes | bytearray | str,
        *,
        max_bytes: int,
    ) -> object:
        nonlocal decode_calls
        decode_calls += 1
        return original_decode(payload, max_bytes=max_bytes)

    def counted_prepare(candidate: object) -> dict[str, object]:
        nonlocal prepare_calls
        prepare_calls += 1
        return original_prepare(candidate)

    monkeypatch.setattr(plugin_module, "_strict_json_loads", counted_decode)
    monkeypatch.setattr(engine_module, "_prepare_request_candidate", counted_prepare)
    plugin = M0502Plugin(M0502Service())
    token = plugin.validate(canonical_json_bytes(evaluation_module.build_scenario_request()))
    assert (decode_calls, prepare_calls) == (1, 1)

    result = plugin.run(token)
    assert result.disposition is PtmLocalizationLineageDisposition.RECONCILED
    assert (decode_calls, prepare_calls) == (1, 1)


def test_resigned_result_cannot_project_unknown_embedded_request_storage() -> None:
    result = evaluation_module.build_scenario_result()
    projected_request = copy.deepcopy(result.request)
    storage = cast(
        "dict[object, object]",
        object.__getattribute__(projected_request, "__dict__"),
    )
    dict.__setitem__(storage, "recursive_canary", "must-not-project")
    payload = result.model_dump(mode="python", exclude_none=False)
    payload["request"] = projected_request
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(
        ValidationError, match=r"request storage does not match|Extra inputs are not permitted"
    ):
        PtmLocalizationIdentityLineageResolution.model_validate(payload, strict=True)


def test_evaluation_inventory_rejects_identity_shape_duplicates_and_unknown_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="unknown M05-02 scenario"):
        evaluation_module.build_scenario_request("unknown")

    missing_identity = tmp_path / "missing-identity.json"
    missing_identity.write_text('{"scenarios": []}', encoding="utf-8")
    monkeypatch.setattr(evaluation_module, "M0102_SCENARIO_PATH", missing_identity)
    with pytest.raises(ValueError, match="canonical identity fixture is missing"):
        evaluation_module._m0102_payload()

    original_fixture = json.loads(evaluation_module.M0502_SCENARIO_PATH.read_text(encoding="utf-8"))
    invalid_identity = copy.deepcopy(original_fixture)
    invalid_identity["module_id"] = "wrong"
    fixture = tmp_path / "invalid-identity.json"
    fixture.write_text(json.dumps(invalid_identity), encoding="utf-8")
    monkeypatch.setattr(evaluation_module, "M0502_SCENARIO_PATH", fixture)
    with pytest.raises(ValueError, match="fixture identity is inconsistent"):
        evaluation_module._locked_inventory()

    invalid_shape = copy.deepcopy(original_fixture)
    invalid_shape["groups"].pop(next(iter(invalid_shape["groups"])))
    fixture.write_text(json.dumps(invalid_shape), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly eight groups and seventy cases"):
        evaluation_module._locked_inventory()

    duplicate = copy.deepcopy(original_fixture)
    groups = cast("dict[str, list[str]]", duplicate["groups"])
    group_values = list(groups.values())
    group_values[-1][-1] = group_values[0][0]
    fixture.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ValueError, match="case identifiers must be unique"):
        evaluation_module._locked_inventory()


def test_evaluation_negative_helpers_and_main_cover_both_exit_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = evaluation_module.build_scenario_request()
    result = evaluation_module.build_scenario_result()
    assert not evaluation_module._request_rejected(request)
    assert not evaluation_module._result_rejected(result)
    assert not evaluation_module._authorization_denied("consent", "granted")
    assert evaluation_module._nested_keys({"outer": [{"inner": 1}]}) == {"outer", "inner"}
    assert evaluation_module._nested_keys(1) == set()
    assert not evaluation_module._result_mutation("unknown")
    assert not evaluation_module._case_succeeds("unknown")

    passing = evaluation_module.EvaluationReport(
        module_id="GLIO-PROTEOGEN-M05-02",
        contract_version="1.0.0",
        declared_groups=8,
        group_case_counts={"group": 70},
        declared_cases=70,
        executed_cases=70,
        passed_cases=70,
        failed_cases=(),
        passed=True,
    )
    monkeypatch.setattr(evaluation_module, "run_evaluation", lambda: passing)
    assert evaluation_module.main([]) == 0
    assert '"passed": true' in capsys.readouterr().out

    output = tmp_path / "evaluation.json"
    monkeypatch.setattr(
        evaluation_module,
        "run_evaluation",
        lambda: replace(passing, passed_cases=69, failed_cases=("failed",), passed=False),
    )
    assert evaluation_module.main(["--output", str(output)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is False


def test_benchmark_rejects_invalid_workload_and_nondeterminism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(benchmark_module.InvalidIterationCountError):
        benchmark_module.run_benchmark(0)

    monkeypatch.setattr(
        benchmark_module,
        "build_scenario_request",
        lambda _scenario: evaluation_module.build_scenario_request(
            "unsupported_configuration_abstained"
        ),
    )
    with pytest.raises(benchmark_module.InvalidRepresentativeWorkloadError):
        benchmark_module.run_benchmark(1)

    monkeypatch.setattr(
        benchmark_module,
        "build_scenario_request",
        lambda _scenario: evaluation_module.build_scenario_request(),
    )
    outputs = iter(
        (
            evaluation_module.build_scenario_result(),
            evaluation_module.build_scenario_result("identity_swap_quarantined"),
        )
    )
    monkeypatch.setattr(
        benchmark_module,
        "reconcile_ptm_localization_identity_lineage",
        lambda _request: next(outputs),
    )
    with pytest.raises(benchmark_module.NonDeterministicBenchmarkError):
        benchmark_module.run_benchmark(1)


def test_benchmark_main_writes_stdout_file_and_both_exit_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = benchmark_module.run_benchmark(1)
    monkeypatch.setattr(benchmark_module, "run_benchmark", lambda _iterations: report)
    assert benchmark_module.main(["--iterations", "1"]) == 0
    assert '"passed": true' in capsys.readouterr().out

    output = tmp_path / "benchmark.json"
    monkeypatch.setattr(
        benchmark_module,
        "run_benchmark",
        lambda _iterations: replace(report, passed=False),
    )
    assert benchmark_module.main(["--iterations", "1", "--output", str(output)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is False
