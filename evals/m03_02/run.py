"""Execute the locked M03-02 identity-lineage reconciliation evidence corpus."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, TypedDict, cast

from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_01.run import build_scenario_request as build_m0301_request
from glio_proteogen.contracts.m01_02 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m03_01 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.contracts.m03_02 import (
    M0302_MAX_ARTIFACT_CLAIMS,
    ApprovedCopyNumberMethod,
    ApprovedDerivationMethod,
    ArtifactClaimRole,
    CopyNumberConcordanceReceipt,
    CopyNumberConcordanceState,
    ProteinInferenceArtifactClaim,
    ProteinInferenceArtifactDerivation,
    ProteinInferenceIdentityLineageResolution,
    ProteinInferenceLineagePolicy,
    ReconcileProteinInferenceIdentityLineageRequest,
    ReconciliationDisposition,
    ReconciliationFindingCode,
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ExecutionContext
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    M0102Service,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    evaluate_protein_inference_protocol,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    ProteinIdentityLineageAuthorizationError,
    preflight_protein_identity_lineage_authorization,
    reconcile_protein_inference_identity_lineage,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MODULE_ID = "GLIO-PROTEOGEN-M03-02"
ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m03_02" / "scenarios.json"
M0102_SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
_M0102_REQUEST_ADAPTER = TypeAdapter(ReconcileIdentityLineageRequest)
_M0302_REQUEST_ADAPTER = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)
_M0302_RESULT_ADAPTER = TypeAdapter(ProteinInferenceIdentityLineageResolution)
_DUPLICATE_PAIR_SIZE = 2
_EXPECTED_DERIVATION_COUNT = 3
_EXPECTED_GROUP_COUNT = 8
_EXPECTED_CASE_COUNT = 62


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    scenario_groups: list[ScenarioGroup]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, *, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m0302.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0302": label}),
        media_type="application/json",
    )


def _m0102_payload(case_id: str) -> dict[str, Any]:
    corpus = cast("dict[str, Any]", strict_json_loads(M0102_SCENARIO_PATH.read_bytes()))
    for scenario in cast("list[dict[str, Any]]", corpus["scenarios"]):
        if scenario["case_id"] == case_id:
            return copy.deepcopy(cast("dict[str, Any]", scenario["request"]))
    raise ValueError(case_id)


def _strict_m0102_request(payload: dict[str, Any]) -> ReconcileIdentityLineageRequest:
    return _M0102_REQUEST_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)


def _two_subject_identity_request() -> ReconcileIdentityLineageRequest:
    payload = _m0102_payload("complete_ordinary_lineage")
    first_entities = cast("list[dict[str, Any]]", payload["entities"])
    first_operations = cast("list[dict[str, Any]]", payload["lineage_operations"])
    mapping = {
        "pat-a": "pat-b",
        "spc-a": "spc-b",
        "alq-a": "alq-b",
        "sec-a": "sec-b",
        "ana-a": "ana-b",
        "run-a": "run-b",
        "obj-a": "obj-b",
    }
    second_entities = copy.deepcopy(first_entities)
    for entity in second_entities:
        entity["entity_id"] = mapping[cast("str", entity["entity_id"])]
    second_operations = copy.deepcopy(first_operations)
    for index, operation in enumerate(second_operations, start=7):
        operation["operation_id"] = f"op-{index:02d}"
        operation["source_entity_ids"] = [
            mapping[entity_id]
            for entity_id in cast("list[str]", operation["source_entity_ids"])
        ]
        operation["target_entity_ids"] = [
            mapping[entity_id]
            for entity_id in cast("list[str]", operation["target_entity_ids"])
        ]
    payload["entities"] = [*first_entities, *second_entities]
    payload["lineage_operations"] = [*first_operations, *second_operations]
    return _strict_m0102_request(payload)


def _genuine_identity_resolution(name: str) -> IdentityLineageResolution:
    if name == "identity_unresolved":
        request = _strict_m0102_request(_m0102_payload("lineage_cycle_quarantine"))
    elif name == "cross_patient":
        request = _two_subject_identity_request()
    else:
        request = _strict_m0102_request(_m0102_payload("complete_ordinary_lineage"))
    with TemporaryDirectory(prefix="m0302-m0102-") as temporary:
        store = M0102EventStore(Path(temporary) / "identity.sqlite3")
        with M0102Service(store) as service:
            return service.execute(request)


def _genuine_protocol_result(
    identity: IdentityLineageResolution,
    *,
    nonconformant: bool = False,
) -> ProteinInferenceProtocolConformanceResult:
    seed = build_m0301_request(
        "search_space_build_digest_mismatch" if nonconformant else "canonical"
    )
    references = seed.context.references.model_copy(
        update={
            "identity_lineage": seed.context.references.identity_lineage.model_copy(
                update={"binding_digest": identity.resolution_digest}
            )
        }
    )
    context = seed.context.model_copy(update={"references": references})
    request = EvaluateProteinInferenceProtocolRequest(
        context=context,
        protocol_schema=seed.protocol_schema,
        conformance_profile=seed.conformance_profile,
    )
    return evaluate_protein_inference_protocol(request)


def _policy(*, maximum: bool = False, reorderable: bool = False) -> ProteinInferenceLineagePolicy:
    derivation_methods = [
        ApprovedDerivationMethod(
            method_id="derivation.synthetic",
            version="1.0.0",
            evidence=_artifact("policy.derivation.primary"),
        )
    ]
    cn_methods = [
        ApprovedCopyNumberMethod(
            method_id="cn.aggregate.synthetic",
            version="1.0.0",
            evidence=_artifact("policy.cn.primary"),
        )
    ]
    if reorderable:
        derivation_methods.append(
            ApprovedDerivationMethod(
                method_id="derivation.synthetic.alternate",
                version="1.0.0",
                evidence=_artifact("policy.derivation.alternate"),
            )
        )
        cn_methods.append(
            ApprovedCopyNumberMethod(
                method_id="cn.aggregate.synthetic.alternate",
                version="1.0.0",
                evidence=_artifact("policy.cn.alternate"),
            )
        )
    return ProteinInferenceLineagePolicy(
        policy_id="policy.m0302.synthetic",
        version="1.0.0",
        max_artifact_claims=M0302_MAX_ARTIFACT_CLAIMS if maximum else 16,
        max_derivation_sources=253 if maximum else 8,
        approved_derivation_methods=tuple(derivation_methods),
        approved_cn_methods=tuple(cn_methods),
        evidence=_artifact("policy.root"),
        reviewed_by="reviewer.synthetic",
        reviewed_at=datetime(2026, 8, 12, 12, 30, tzinfo=UTC),
    )


def _context(
    protocol: ProteinInferenceProtocolConformanceResult,
    identity: IdentityLineageResolution,
    policy: ProteinInferenceLineagePolicy,
) -> ExecutionContext:
    base = protocol.context.references
    approved_configuration = base.approved_configuration.model_copy(
        update={
            "evidence": _artifact(
                "control.approved-configuration",
                digest=configuration_digest(policy),
            )
        }
    )
    identity_lineage = base.identity_lineage.model_copy(
        update={"binding_digest": identity.resolution_digest}
    )
    references = base.model_copy(
        update={
            "approved_configuration": approved_configuration,
            "identity_lineage": identity_lineage,
        }
    )
    return ExecutionContext(
        request_id="request.m0302.synthetic",
        actor_id="actor.m0302.synthetic",
        occurred_at=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        references=references,
    )


def _anchor_subjects(
    identity: IdentityLineageResolution,
    entity_id: str,
) -> tuple[str, ...]:
    return next(
        node.subject_component_ids
        for node in identity.graph.nodes
        if node.entity_id == entity_id
    )


def _claims(  # noqa: PLR0913 - explicit evidence-shape controls.
    identity: IdentityLineageResolution,
    protocol: ProteinInferenceProtocolConformanceResult,
    *,
    peptide_count: int = 1,
    cross_patient: bool = False,
    duplicate: bool = False,
    collision: bool = False,
) -> tuple[ProteinInferenceArtifactClaim, ...]:
    peptide_claims: list[ProteinInferenceArtifactClaim] = []
    for index in range(peptide_count):
        entity_id = "obj-b" if cross_patient and index == peptide_count - 1 else "obj-a"
        digest = (
            sha256_digest({"m0302": "duplicate-peptide"})
            if duplicate and index < _DUPLICATE_PAIR_SIZE
            else sha256_digest({"m0302": f"peptide-{index:03d}"})
        )
        peptide_claims.append(
            ProteinInferenceArtifactClaim(
                claim_id=f"claim.peptide.{index:03d}",
                role=ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST,
                artifact=_artifact(f"claim.peptide.{index:03d}", digest=digest),
                identity_entity_id=entity_id,
                declared_subject_component_ids=_anchor_subjects(identity, entity_id),
                producer_identity_resolution_digest=identity.resolution_digest,
                producer_protocol_result_digest=protocol.result_digest,
                producer_search_space_digest=protocol.receipt.search_space_digest,
                evidence_state="observed",
            )
        )
    group_digest = (
        peptide_claims[-1].artifact.digest
        if collision
        else sha256_digest({"m0302": "protein-group"})
    )
    subjects = _anchor_subjects(identity, "obj-a")
    return (
        *peptide_claims,
        ProteinInferenceArtifactClaim(
            claim_id="claim.group",
            role=ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
            artifact=_artifact("claim.group", digest=group_digest),
            identity_entity_id="obj-a",
            declared_subject_component_ids=subjects,
            producer_identity_resolution_digest=identity.resolution_digest,
            producer_protocol_result_digest=protocol.result_digest,
            producer_search_space_digest=protocol.receipt.search_space_digest,
            evidence_state="observed",
        ),
        ProteinInferenceArtifactClaim(
            claim_id="claim.ambiguity",
            role=ArtifactClaimRole.AMBIGUITY_MANIFEST,
            artifact=_artifact("claim.ambiguity"),
            identity_entity_id="obj-a",
            declared_subject_component_ids=subjects,
            producer_identity_resolution_digest=identity.resolution_digest,
            producer_protocol_result_digest=protocol.result_digest,
            producer_search_space_digest=protocol.receipt.search_space_digest,
            evidence_state="observed",
        ),
        ProteinInferenceArtifactClaim(
            claim_id="claim.bundle",
            role=ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
            artifact=_artifact("claim.bundle"),
            identity_entity_id="obj-a",
            declared_subject_component_ids=subjects,
            producer_identity_resolution_digest=identity.resolution_digest,
            producer_protocol_result_digest=protocol.result_digest,
            producer_search_space_digest=protocol.receipt.search_space_digest,
            evidence_state="observed",
        ),
    )


def _derivations(
    claims: tuple[ProteinInferenceArtifactClaim, ...],
) -> tuple[ProteinInferenceArtifactDerivation, ...]:
    peptides = tuple(
        claim.claim_id
        for claim in claims
        if claim.role is ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST
    )
    declarations = (
        ("derive.group", peptides, "claim.group"),
        ("derive.ambiguity", ("claim.group",), "claim.ambiguity"),
        ("derive.bundle", ("claim.group", "claim.ambiguity"), "claim.bundle"),
    )
    return tuple(
        ProteinInferenceArtifactDerivation(
            derivation_id=derivation_id,
            source_claim_ids=sources,
            target_claim_id=target,
            method_id="derivation.synthetic",
            method_version="1.0.0",
            evidence=_artifact(f"evidence.{derivation_id}"),
        )
        for derivation_id, sources, target in declarations
    )


def _cn_receipt(
    state: CopyNumberConcordanceState,
) -> CopyNumberConcordanceReceipt:
    informative, concordant, discordant = {
        CopyNumberConcordanceState.CONCORDANT: (12, 12, 0),
        CopyNumberConcordanceState.DISCORDANT: (12, 2, 10),
        CopyNumberConcordanceState.INDETERMINATE: (0, 0, 0),
        CopyNumberConcordanceState.MISSING: (0, 0, 0),
        CopyNumberConcordanceState.UNSUPPORTED: (0, 0, 0),
    }[state]
    return CopyNumberConcordanceReceipt(
        receipt_id="receipt.cn.synthetic",
        claim_id="claim.group",
        identity_entity_id="obj-a",
        state=state,
        method_id="cn.aggregate.synthetic",
        method_version="1.0.0",
        informative_feature_count=informative,
        concordant_feature_count=concordant,
        discordant_feature_count=discordant,
        evidence=_artifact(f"receipt.cn.{state.value}"),
    )


def build_scenario_request(
    name: str = "canonical",
) -> ReconcileProteinInferenceIdentityLineageRequest:
    """Build a strict request from genuine public M01-02 and M03-01 executions."""

    identity_name = (
        "identity_unresolved"
        if name == "identity_unresolved"
        else "cross_patient"
        if name == "cross_patient"
        else "canonical"
    )
    identity = _genuine_identity_resolution(identity_name)
    protocol = _genuine_protocol_result(
        identity,
        nonconformant=name == "protocol_nonconformant",
    )
    maximum = name == "maximum"
    reorderable = name == "reorderable"
    policy = _policy(maximum=maximum, reorderable=reorderable)
    state_name = name.removeprefix("cn_") if name.startswith("cn_") else "concordant"
    try:
        cn_state = CopyNumberConcordanceState(state_name)
    except ValueError:
        cn_state = CopyNumberConcordanceState.CONCORDANT
    duplicate = name in {"duplicate", "collision_and_duplicate"}
    collision = name in {"collision", "collision_and_duplicate"}
    peptide_count = (
        253
        if maximum
        else 3
        if name == "collision_and_duplicate"
        else 2
        if duplicate or name == "cross_patient"
        else 1
    )
    claims = _claims(
        identity,
        protocol,
        peptide_count=peptide_count,
        cross_patient=name == "cross_patient",
        duplicate=duplicate,
        collision=collision,
    )
    return ReconcileProteinInferenceIdentityLineageRequest(
        context=_context(protocol, identity, policy),
        identity_resolution=identity,
        protocol_result=protocol,
        policy=policy,
        artifact_claims=claims,
        derivations=_derivations(claims),
        cn_receipts=(_cn_receipt(cn_state),),
    )


def _strict_request(payload: dict[str, Any]) -> ReconcileProteinInferenceIdentityLineageRequest:
    return _M0302_REQUEST_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _codes(result: ProteinInferenceIdentityLineageResolution) -> set[str]:
    return {finding.code.value for finding in result.findings}


def _result(name: str = "canonical") -> ProteinInferenceIdentityLineageResolution:
    return reconcile_protein_inference_identity_lineage(build_scenario_request(name))


def _rejected_request(
    case_id: str,
    mutate: Callable[[dict[str, Any]], None],
    *,
    base: str = "canonical",
) -> EvalCheck:
    payload = build_scenario_request(base).model_dump(mode="json")
    mutate(payload)
    try:
        _strict_request(payload)
    except ValidationError as error:
        return _scenario(
            case_id,
            passed=True,
            detail=f"validation_rejected:{error.errors()[0]['type']}",
        )
    return _scenario(case_id, passed=False, detail="request unexpectedly accepted")


def _rejected_result(
    case_id: str,
    result: ProteinInferenceIdentityLineageResolution,
    mutate: Callable[[dict[str, Any]], None],
    *,
    recompute_outer: bool,
) -> EvalCheck:
    payload = result.model_dump(mode="json")
    mutate(payload)
    if recompute_outer:
        payload["result_digest"] = result_payload_digest(payload)
    try:
        _M0302_RESULT_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
    except ValidationError as error:
        return _scenario(
            case_id,
            passed=True,
            detail=f"validation_rejected:{error.errors()[0]['type']}",
        )
    return _scenario(
        case_id,
        passed=False,
        detail="result forgery unexpectedly accepted",
    )


def _canonical_checks() -> list[EvalCheck]:
    request = build_scenario_request()
    result = reconcile_protein_inference_identity_lineage(request)
    entity_kinds = {node.kind.value for node in request.identity_resolution.graph.nodes}
    roles = {node.role.value for node in result.graph.artifacts}
    physical_edges = {
        operation.operation_id for operation in request.identity_resolution.graph.operations
    }
    artifact_edges = {edge.derivation_id for edge in result.graph.derivations}
    submitted_claims = {claim.claim_id for claim in request.artifact_claims}
    retained_claims = {claim.claim_id for claim in result.graph.artifacts}
    submitted_derivations = {edge.derivation_id for edge in request.derivations}
    retained_derivations = {edge.derivation_id for edge in result.graph.derivations}
    bindings_exact = (
        result.identity_resolution_digest
        == request.identity_resolution.resolution_digest
        == result.receipt.identity_resolution_digest
        and result.protocol_result_digest
        == request.protocol_result.result_digest
        == result.receipt.protocol_result_digest
        and result.receipt.search_space_digest
        == request.protocol_result.receipt.search_space_digest
    )
    return [
        _scenario(
            "canonical_all_seven_entity_chain",
            passed=entity_kinds
            == {
                "patient",
                "specimen",
                "aliquot",
                "section",
                "analyte",
                "run",
                "derived_object",
            },
            detail=f"entity_kinds={','.join(sorted(entity_kinds))}",
        ),
        _scenario(
            "canonical_full_artifact_dag",
            passed=roles == {role.value for role in ArtifactClaimRole}
            and len(result.graph.derivations) == _EXPECTED_DERIVATION_COUNT,
            detail=f"roles={','.join(sorted(roles))};edges={len(result.graph.derivations)}",
        ),
        _scenario(
            "physical_and_artifact_graphs_remain_distinct",
            passed=physical_edges.isdisjoint(artifact_edges)
            and result.request.identity_resolution.resolution_digest
            == request.identity_resolution.resolution_digest
            and result.request.identity_resolution.graph.graph_digest
            == request.identity_resolution.graph.graph_digest,
            detail=f"physical={len(physical_edges)};artifact={len(artifact_edges)}",
        ),
        _scenario(
            "all_declared_nonsecret_nodes_edges_and_bindings_retained",
            passed=submitted_claims == retained_claims
            and submitted_derivations == retained_derivations,
            detail=f"claims={len(retained_claims)};derivations={len(retained_derivations)}",
        ),
        _scenario(
            "exact_upstream_and_protocol_bindings",
            passed=bindings_exact and result.disposition is ReconciliationDisposition.RECONCILED,
            detail=f"result_digest={result.result_digest}",
        ),
    ]


def _swap_request(claim_id: str) -> ReconcileProteinInferenceIdentityLineageRequest:
    payload = build_scenario_request().model_dump(mode="json")
    claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
    claim = next(item for item in claims if item["claim_id"] == claim_id)
    claim["declared_subject_component_ids"] = [
        sha256_digest({"m0302": f"swapped:{claim_id}"})
    ]
    return _strict_request(payload)


def _swap_checks() -> list[EvalCheck]:
    peptide_request = _swap_request("claim.peptide.000")
    group_request = _swap_request("claim.group")
    bundle_request = _swap_request("claim.bundle")
    peptide = reconcile_protein_inference_identity_lineage(peptide_request)
    group = reconcile_protein_inference_identity_lineage(group_request)
    bundle = reconcile_protein_inference_identity_lineage(bundle_request)
    preserved_edges = {
        (edge.derivation_id, edge.source_claim_ids, edge.target_claim_id)
        for edge in bundle.graph.derivations
    } == {
        (
            edge.derivation_id,
            tuple(sorted(edge.source_claim_ids)),
            edge.target_claim_id,
        )
        for edge in bundle_request.derivations
    }
    return [
        _scenario(
            "specimen_component_swap_detected",
            passed="identity_swap" in _codes(peptide),
            detail=f"codes={','.join(sorted(_codes(peptide)))}",
        ),
        _scenario(
            "run_component_swap_detected",
            passed="identity_swap" in _codes(group),
            detail=f"codes={','.join(sorted(_codes(group)))}",
        ),
        _scenario(
            "derived_object_subject_swap_detected",
            passed="identity_swap" in _codes(bundle),
            detail=f"codes={','.join(sorted(_codes(bundle)))}",
        ),
        _scenario(
            "swap_does_not_relabel_upstream_entity",
            passed=bundle.request.identity_resolution.resolution_digest
            == bundle_request.identity_resolution.resolution_digest
            and {
                (
                    node.entity_id,
                    node.kind,
                    node.component_id,
                    tuple(sorted(node.subject_component_ids)),
                )
                for node in bundle.request.identity_resolution.graph.nodes
            }
            == {
                (
                    node.entity_id,
                    node.kind,
                    node.component_id,
                    tuple(sorted(node.subject_component_ids)),
                )
                for node in bundle_request.identity_resolution.graph.nodes
            },
            detail="embedded M01-02 nodes retained exactly",
        ),
        _scenario(
            "swap_does_not_rewrite_physical_or_artifact_edge",
            passed=preserved_edges
            and bundle.request.identity_resolution.graph.graph_digest
            == bundle_request.identity_resolution.graph.graph_digest,
            detail="physical and artifact edges retained",
        ),
    ]


def _collision_checks() -> list[EvalCheck]:
    canonical = _result()
    collision = _result("collision")
    duplicate = _result("duplicate")
    combined = _result("collision_and_duplicate")
    duplicate_digest = sha256_digest({"m0302": "duplicate-peptide"})
    retained_duplicates = [
        artifact
        for artifact in duplicate.graph.artifacts
        if artifact.artifact_digest == duplicate_digest
    ]
    return [
        _scenario(
            "same_scope_identifier_collision",
            passed="artifact_lineage_collision" in _codes(collision),
            detail=f"codes={','.join(sorted(_codes(collision)))}",
        ),
        _scenario(
            "different_scope_digest_control_not_collision",
            passed="artifact_lineage_collision" not in _codes(canonical),
            detail="distinct content digests remain distinct",
        ),
        _scenario(
            "duplicate_content_distinct_bindings_retained",
            passed="duplicate_content_retained" in _codes(duplicate)
            and len(retained_duplicates) == _DUPLICATE_PAIR_SIZE,
            detail=f"retained={len(retained_duplicates)}",
        ),
        _scenario(
            "collision_participants_all_retained",
            passed=len(collision.graph.artifacts) == len(collision.request.artifact_claims),
            detail=f"retained={len(collision.graph.artifacts)}",
        ),
        _scenario(
            "duplicate_has_no_authoritative_copy",
            passed=len(retained_duplicates) == _DUPLICATE_PAIR_SIZE
            and all(
                "authoritative" not in type(node).model_fields
                for node in retained_duplicates
            ),
            detail="both declarations retained without authority selection",
        ),
        _scenario(
            "collision_and_duplicate_coexist_without_collapse",
            passed={
                "artifact_lineage_collision",
                "duplicate_content_retained",
            }.issubset(_codes(combined))
            and len(combined.graph.artifacts) == len(combined.request.artifact_claims),
            detail=f"codes={','.join(sorted(_codes(combined)))}",
        ),
    ]


def _cross_patient_checks() -> list[EvalCheck]:
    result = _result("cross_patient")
    by_claim = {artifact.claim_id: artifact for artifact in result.graph.artifacts}
    affected = {"claim.group", "claim.ambiguity", "claim.bundle"}
    roots = {
        claim_id
        for claim_id in by_claim
        if claim_id.startswith("claim.peptide.")
    }
    upstream_subjects = {
        subject
        for node in result.request.identity_resolution.graph.nodes
        for subject in node.subject_component_ids
    }
    output_subjects = {
        subject
        for node in result.graph.artifacts
        for subject in node.resolved_subject_component_ids
    }
    return [
        _scenario(
            "cross_patient_physical_link_detected",
            passed="cross_patient_link" in _codes(result),
            detail=f"codes={','.join(sorted(_codes(result)))}",
        ),
        _scenario(
            "run_cross_patient_binding_detected",
            passed=ReconciliationFindingCode.CROSS_PATIENT_LINK
            in by_claim["claim.group"].finding_codes,
            detail="mixed upstream subjects reach protein-group manifest",
        ),
        _scenario(
            "direct_artifact_binding_quarantined",
            passed=result.disposition is ReconciliationDisposition.QUARANTINED
            and ReconciliationFindingCode.IDENTITY_SWAP
            in by_claim["claim.group"].finding_codes,
            detail=result.disposition.value,
        ),
        _scenario(
            "reachable_artifact_descendants_quarantined",
            passed=all(
                ReconciliationFindingCode.CROSS_PATIENT_LINK
                in by_claim[claim_id].finding_codes
                for claim_id in affected
            ),
            detail=f"affected={','.join(sorted(affected))}",
        ),
        _scenario(
            "disconnected_artifact_branch_unaffected",
            passed=all(
                ReconciliationFindingCode.CROSS_PATIENT_LINK
                not in by_claim[claim_id].finding_codes
                for claim_id in roots
            ),
            detail=f"unaffected_roots={','.join(sorted(roots))}",
        ),
        _scenario(
            "propagation_does_not_create_patient_assignment",
            passed=not result.infers_identity and output_subjects.issubset(upstream_subjects),
            detail=f"upstream_subjects={len(upstream_subjects)}",
        ),
    ]


def _malformed_dag_checks() -> list[EvalCheck]:
    def cycle(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["derivations"])[0][
            "source_claim_ids"
        ] = ["claim.ambiguity"]

    def self_dependency(payload: dict[str, Any]) -> None:
        edge = cast("list[dict[str, Any]]", payload["derivations"])[0]
        edge["source_claim_ids"] = [edge["target_claim_id"]]

    def dangling(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["derivations"])[0][
            "source_claim_ids"
        ] = ["claim.unknown"]

    def unknown_role(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["artifact_claims"])[0]["role"] = (
            "raw_peptide_table"
        )

    def duplicate_node(payload: dict[str, Any]) -> None:
        claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
        claims[1]["claim_id"] = claims[0]["claim_id"]

    def duplicate_edge(payload: dict[str, Any]) -> None:
        edges = cast("list[dict[str, Any]]", payload["derivations"])
        edges[1]["derivation_id"] = edges[0]["derivation_id"]

    def multiple_producers(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["derivations"])[1][
            "target_claim_id"
        ] = "claim.group"

    def missing_root(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["artifact_claims"])[0]["role"] = (
            "protein_group_manifest"
        )

    return [
        _rejected_request("artifact_cycle_rejected", cycle),
        _rejected_request("artifact_self_dependency_rejected", self_dependency),
        _rejected_request("dangling_artifact_endpoint_rejected", dangling),
        _rejected_request("unknown_artifact_role_rejected", unknown_role),
        _rejected_request("duplicate_artifact_node_identifier_rejected", duplicate_node),
        _rejected_request("duplicate_artifact_edge_identifier_rejected", duplicate_edge),
        _rejected_request("unapproved_multiple_producers_rejected", multiple_producers),
        _rejected_request("missing_required_artifact_root_rejected", missing_root),
    ]


def _drift_checks() -> list[EvalCheck]:
    stale = sha256_digest({"m0302": "stale"})

    def stale_context(payload: dict[str, Any]) -> None:
        payload["context"]["references"]["identity_lineage"]["binding_digest"] = stale

    def stale_resolution(payload: dict[str, Any]) -> None:
        payload["identity_resolution"]["resolution_digest"] = stale

    def stale_protocol_context(payload: dict[str, Any]) -> None:
        payload["protocol_result"]["context"]["references"]["identity_lineage"][
            "binding_digest"
        ] = stale

    identity_unresolved = _result("identity_unresolved")
    protocol_nonconformant = _result("protocol_nonconformant")

    protocol_payload = build_scenario_request().model_dump(mode="json")
    for claim in cast("list[dict[str, Any]]", protocol_payload["artifact_claims"]):
        claim["producer_protocol_result_digest"] = stale
    protocol_drift = reconcile_protein_inference_identity_lineage(
        _strict_request(protocol_payload)
    )

    search_payload = build_scenario_request().model_dump(mode="json")
    for claim in cast("list[dict[str, Any]]", search_payload["artifact_claims"]):
        claim["producer_search_space_digest"] = stale
    search_drift = reconcile_protein_inference_identity_lineage(
        _strict_request(search_payload)
    )
    canonical = _result()
    return [
        _rejected_request("stale_identity_resolution_context_binding", stale_context),
        _rejected_request("stale_embedded_identity_resolution_digest", stale_resolution),
        _scenario(
            "valid_unresolved_identity_result_abstains",
            passed=identity_unresolved.disposition is ReconciliationDisposition.ABSTAINED
            and "upstream_identity_unresolved" in _codes(identity_unresolved),
            detail=f"codes={','.join(sorted(_codes(identity_unresolved)))}",
        ),
        _scenario(
            "valid_nonconformant_protocol_result_quarantines",
            passed=protocol_nonconformant.disposition
            is ReconciliationDisposition.QUARANTINED
            and "upstream_protocol_nonconformant" in _codes(protocol_nonconformant),
            detail=f"codes={','.join(sorted(_codes(protocol_nonconformant)))}",
        ),
        _rejected_request("stale_protocol_result_context_binding", stale_protocol_context),
        _scenario(
            "protocol_identity_drift_quarantined",
            passed=protocol_drift.disposition is ReconciliationDisposition.QUARANTINED
            and "producer_protocol_drift" in _codes(protocol_drift),
            detail=f"codes={','.join(sorted(_codes(protocol_drift)))}",
        ),
        _scenario(
            "search_space_build_drift_quarantined",
            passed=search_drift.disposition is ReconciliationDisposition.QUARANTINED
            and "producer_search_space_drift" in _codes(search_drift),
            detail=f"codes={','.join(sorted(_codes(search_drift)))}",
        ),
        _rejected_result(
            "artifact_graph_digest_stale_rejected",
            canonical,
            lambda payload: payload["graph"].__setitem__("graph_digest", stale),
            recompute_outer=True,
        ),
        _scenario(
            "display_label_match_does_not_override_digest_drift",
            passed="producer_search_space_drift" in _codes(search_drift)
            and all(
                claim.artifact.artifact_id.startswith("artifact.m0302")
                for claim in search_drift.request.artifact_claims
            ),
            detail="display identifiers retained; stale digest quarantined",
        ),
    ]


def _cn_checks() -> list[EvalCheck]:
    results = {
        state: _result(f"cn_{state}")
        for state in (
            "concordant",
            "discordant",
            "missing",
            "indeterminate",
            "unsupported",
        )
    }
    component_views = {
        state: tuple(
            (node.claim_id, node.resolved_subject_component_ids)
            for node in result.graph.artifacts
        )
        for state, result in results.items()
    }
    rendered = json.dumps(
        {state: result.model_dump(mode="json") for state, result in results.items()},
        sort_keys=True,
    )
    raw_terms = {
        "raw_copy_number_value",
        "raw_protein_abundance",
        "copy_number_segment",
        "protein_accession",
    }
    scientific_claims = {"protein_presence", "protein_absence"}
    return [
        _scenario(
            "cn_concordant_corroborates_only",
            passed=results["concordant"].disposition
            is ReconciliationDisposition.RECONCILED
            and not _codes(results["concordant"]),
            detail="categorical concordance adds no identity finding",
        ),
        _scenario(
            "cn_discordant_preserves_disagreement",
            passed=results["discordant"].disposition
            is ReconciliationDisposition.QUARANTINED
            and "cn_discordant" in _codes(results["discordant"]),
            detail=f"codes={','.join(sorted(_codes(results['discordant'])))}",
        ),
        _scenario(
            "cn_missing_abstains",
            passed=results["missing"].disposition is ReconciliationDisposition.ABSTAINED
            and "cn_not_evaluable" in _codes(results["missing"]),
            detail="missing remains not evaluable",
        ),
        _scenario(
            "cn_indeterminate_abstains",
            passed=results["indeterminate"].disposition
            is ReconciliationDisposition.ABSTAINED
            and "cn_not_evaluable" in _codes(results["indeterminate"]),
            detail="indeterminate remains not evaluable",
        ),
        _scenario(
            "cn_unsupported_abstains",
            passed=results["unsupported"].disposition
            is ReconciliationDisposition.ABSTAINED
            and "cn_not_evaluable" in _codes(results["unsupported"]),
            detail="unsupported remains not evaluable",
        ),
        _scenario(
            "all_cn_states_preserve_identity_components",
            passed=len(set(component_views.values())) == 1
            and all(not result.infers_identity for result in results.values()),
            detail="all five categorical states preserve exact components",
        ),
        _scenario(
            "all_cn_states_exclude_raw_measurements",
            passed=not any(term in rendered for term in raw_terms),
            detail="no raw copy-number or abundance material",
        ),
        _scenario(
            "all_cn_states_make_no_protein_presence_or_absence_claim",
            passed=not any(term in rendered for term in scientific_claims),
            detail="no protein presence or absence claim",
        ),
    ]


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            *map(str, value),
            *(key for child in value.values() for key in _all_keys(child)),
        }
    if isinstance(value, list | tuple):
        return {key for child in value for key in _all_keys(child)}
    return set()


def _authorization_check(
    case_id: str,
    *,
    role: str,
    state: str,
) -> EvalCheck:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][role]["state"] = state
    payload["artifact_claims"] = object()
    try:
        preflight_protein_identity_lineage_authorization(payload)
    except ProteinIdentityLineageAuthorizationError:
        return _scenario(
            case_id,
            passed=True,
            detail="authorization rejected before hostile artifact traversal",
        )
    return _scenario(case_id, passed=False, detail="authorization unexpectedly accepted")


def _semantic_reorder_check() -> EvalCheck:
    request = build_scenario_request("reorderable")
    payload = request.model_dump(mode="json")
    for field in ("artifact_claims", "derivations", "cn_receipts"):
        cast("list[Any]", payload[field]).reverse()
    policy = cast("dict[str, Any]", payload["policy"])
    cast("list[Any]", policy["approved_derivation_methods"]).reverse()
    cast("list[Any]", policy["approved_cn_methods"]).reverse()
    reordered = _strict_request(payload)
    left = reconcile_protein_inference_identity_lineage(request)
    right = reconcile_protein_inference_identity_lineage(reordered)
    return _scenario(
        "semantic_reorder_complete_result_equality",
        passed=left == right and left.model_dump_json() == right.model_dump_json(),
        detail=f"result_digest={left.result_digest}",
    )


def _boundary_checks() -> list[EvalCheck]:
    canonical = _result()
    collision = _result("collision")

    def unknown_field(payload: dict[str, Any]) -> None:
        payload["activity_score"] = 0.9

    def coerced_scalar(payload: dict[str, Any]) -> None:
        payload["cn_receipts"][0]["informative_feature_count"] = "12"

    def unknown_term(payload: dict[str, Any]) -> None:
        payload["cn_receipts"][0]["state"] = "probable_match"

    def missing_field(payload: dict[str, Any]) -> None:
        del payload["artifact_claims"][0]["role"]

    maximum = build_scenario_request("maximum")
    maximum_result = reconcile_protein_inference_identity_lineage(maximum)

    def first_excess(payload: dict[str, Any]) -> None:
        claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
        extra = copy.deepcopy(claims[0])
        extra["claim_id"] = "claim.peptide.first-excess"
        extra["artifact"] = _artifact("claim.peptide.first-excess").model_dump(mode="json")
        claims.append(extra)

    payload = canonical.model_dump(mode="json")
    keys = _all_keys(payload)
    rendered = json.dumps(payload, sort_keys=True)
    privacy_canaries = {
        "direct_patient_identifier",
        "raw_identity_token",
        "peptide_sequence",
        "raw_copy_number_value",
        "raw_protein_abundance",
    }
    forbidden_claims = {
        "observed_peptide",
        "protein_accession",
        "complex_activity_inference",
        "protein_subtype",
        "proteotype",
        "kinase_activity",
        "omics_fusion",
        "treatment_recommendation",
        "clinical_decision",
    }
    return [
        _authorization_check(
            "consent_denied_before_hostile_lineage_traversal",
            role="consent",
            state="withheld",
        ),
        _authorization_check(
            "unresolved_identity_before_hostile_artifact_traversal",
            role="identity_lineage",
            state="unresolved",
        ),
        _rejected_request("unknown_field_rejected", unknown_field),
        _rejected_request("coerced_scalar_rejected", coerced_scalar),
        _rejected_request("unknown_controlled_term_rejected", unknown_term),
        _rejected_request("mandatory_field_missing_rejected", missing_field),
        _scenario(
            "maximum_supported_graph_shape_accepted",
            passed=len(maximum.artifact_claims) == M0302_MAX_ARTIFACT_CLAIMS
            and maximum_result.disposition is ReconciliationDisposition.RECONCILED,
            detail=f"artifact_claims={len(maximum.artifact_claims)}",
        ),
        _rejected_request("first_graph_excess_rejected", first_excess, base="maximum"),
        _semantic_reorder_check(),
        _scenario(
            "privacy_canary_absent_recursively",
            passed=not privacy_canaries.intersection(keys)
            and not any(term in rendered for term in privacy_canaries),
            detail="privacy canaries absent from all keys and values",
        ),
        _rejected_result(
            "stale_result_digest_rejected",
            canonical,
            lambda value: value.__setitem__(
                "result_digest", sha256_digest({"m0302": "stale-result"})
            ),
            recompute_outer=False,
        ),
        _rejected_result(
            "mutated_finding_with_recomputed_outer_digest_rejected",
            collision,
            lambda value: value["findings"][0].__setitem__("action", "record"),
            recompute_outer=True,
        ),
        _rejected_result(
            "mutated_provenance_with_recomputed_outer_digest_rejected",
            canonical,
            lambda value: value["provenance"].__setitem__(
                "actor_id", "actor.forged"
            ),
            recompute_outer=True,
        ),
        _rejected_result(
            "mutated_evidence_with_recomputed_outer_digest_rejected",
            canonical,
            lambda value: value["evidence"][0].__setitem__(
                "claim", "Forged but structurally valid evidence claim."
            ),
            recompute_outer=True,
        ),
        _scenario(
            "recursive_output_ownership_boundary",
            passed=not any(term in rendered for term in forbidden_claims)
            and canonical.parent_target == "complex_activity"
            and not canonical.emits_complex_activity
            and not canonical.infers_identity,
            detail="lineage reconciliation only; no biological or clinical output",
        ),
    ]


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _corpus_check(corpus: Corpus) -> EvalCheck:
    case_count = sum(len(group["case_ids"]) for group in corpus["scenario_groups"])
    passed = (
        corpus["module_id"] == MODULE_ID
        and len(corpus["scenario_groups"]) == _EXPECTED_GROUP_COUNT
        and case_count == _EXPECTED_CASE_COUNT
    )
    return EvalCheck(
        name="corpus.locked_shape",
        passed=passed,
        detail=f"groups={len(corpus['scenario_groups'])};cases={case_count}",
    )


def _coverage_check(corpus: Corpus, checks: list[EvalCheck]) -> EvalCheck:
    declared = {
        case_id
        for group in corpus["scenario_groups"]
        for case_id in group["case_ids"]
    }
    executed = {
        check.name.removeprefix("scenario.")
        for check in checks
        if check.name.startswith("scenario.")
    }
    return EvalCheck(
        name="coverage.every_declared_scenario_has_exactly_one_oracle",
        passed=declared == executed
        and len(executed)
        == len(
            [check for check in checks if check.name.startswith("scenario.")]
        ),
        detail=(
            f"declared={len(declared)};executed={len(executed)};"
            f"missing={','.join(sorted(declared - executed)) or 'none'};"
            f"extra={','.join(sorted(executed - declared)) or 'none'}"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks = [
        _corpus_check(corpus),
        *_canonical_checks(),
        *_swap_checks(),
        *_collision_checks(),
        *_cross_patient_checks(),
        *_malformed_dag_checks(),
        *_drift_checks(),
        *_cn_checks(),
        *_boundary_checks(),
    ]
    checks.append(_coverage_check(corpus, checks))
    passed = all(check.passed for check in checks)
    canonical = _result()
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_group_count": len(corpus["scenario_groups"]),
        "scenario_case_count": sum(
            len(group["case_ids"]) for group in corpus["scenario_groups"]
        ),
        "corpus_digest": sha256_digest(corpus),
        "canonical_request_digest": canonical.request_digest,
        "canonical_result_digest": canonical.result_digest,
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
