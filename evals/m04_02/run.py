"""Replay the locked M04-02 synthetic proteoform identity-lineage corpus."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Final, NoReturn, TypedDict, cast
from unittest.mock import patch

from pydantic import TypeAdapter, ValidationError

from evals.m04_01.run import build_scenario_request as build_m0401_request
from glio_proteogen.contracts.m01_02 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m04_01 import (
    ApprovedCoordinateProfile,
    CoordinateConvention,
    EvaluateProteoformProtocolRequest,
    ProteoformProtocolConformanceResult,
    ReviewedProteoformConformanceProfile,
)
from glio_proteogen.contracts.m04_01 import (
    configuration_digest as m0401_configuration_digest,
)
from glio_proteogen.contracts.m04_01 import (
    receipt_digest as m0401_receipt_digest,
)
from glio_proteogen.contracts.m04_01 import (
    result_payload_digest as m0401_result_payload_digest,
)
from glio_proteogen.contracts.m04_02 import (
    M0402_MAX_APPROVED_METHODS,
    M0402_MAX_ARTIFACT_CLAIMS,
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    M0402_MAX_DERIVATION_SOURCES,
    M0402_MAX_EVIDENCE,
    ApprovedProteoformDerivationMethod,
    ProteoformIdentityLineagePolicy,
    ProteoformIdentityLineageResolution,
    ProteoformLineageArtifactClaim,
    ProteoformLineageArtifactDerivation,
    ProteoformLineageArtifactRole,
    ProteoformLineageDisposition,
    ProteoformLineageEvidenceState,
    ReconcileProteoformIdentityLineageRequest,
    ResolvedProteoformLineageArtifact,
    canonical_request_digest,
    configuration_digest,
    opaque_proteoform_lineage_identifier,
    resolved_graph_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ExecutionContext
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    M0102Service,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    evaluate_proteoform_protocol,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    M0402Plugin,
    M0402Service,
    ProteoformIdentityLineageAuthorizationError,
    preflight_proteoform_identity_lineage_authorization,
    reconcile_proteoform_identity_lineage,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    engine as m0402_engine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-02"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m04_02" / "scenarios.json"
M0102_SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
EXPECTED_ALLOCATION: Final = (6, 6, 7, 6, 8, 9, 8, 20)
EXPECTED_GROUP_COUNT: Final = 8
EXPECTED_CASE_COUNT: Final = 70
EXPECTED_SOURCE_ROLE_COUNT: Final = 4
EXPECTED_DUPLICATE_PAIR_SIZE: Final = 2
FIXED_TIME: Final = datetime(2026, 8, 13, 12, tzinfo=UTC)
CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-02.policy+json"
DERIVATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-02.derivation+json"
ROLE_MEDIA_TYPES: Final = {
    ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST: (
        "application/vnd.glio-proteogen.m04-02.mass-spectrometry-proteome-manifest+json"
    ),
    ProteoformLineageArtifactRole.GENOME_MANIFEST: (
        "application/vnd.glio-proteogen.m04-02.genome-manifest+json"
    ),
    ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST: (
        "application/vnd.glio-proteogen.m04-02.transcriptome-manifest+json"
    ),
    ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST: (
        "application/vnd.glio-proteogen.m04-02.ptm-annotation-manifest+json"
    ),
    ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE: (
        "application/vnd.glio-proteogen.m04-02.protein-rna-discordance-input-bundle+json"
    ),
}

_M0102_REQUEST_ADAPTER = TypeAdapter(ReconcileIdentityLineageRequest)
_M0402_REQUEST_ADAPTER = TypeAdapter(ReconcileProteoformIdentityLineageRequest)
_M0402_RESULT_ADAPTER = TypeAdapter(ProteoformIdentityLineageResolution)


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]
    case_expectations: dict[str, str]
    expected_case_count: int


class Corpus(TypedDict):
    module_id: str
    scenario_groups: list[ScenarioGroup]
    expected_group_count: int
    expected_total_case_count: int
    expected_case_allocation: list[int]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _oid(namespace: str, label: object) -> str:
    value = f"{namespace}.{sha256_digest({'m0402': label}).removeprefix('sha256:')}"
    return opaque_proteoform_lineage_identifier(cast("Any", namespace), value)


def _artifact(
    label: str,
    *,
    media_type: str,
    digest: str | None = None,
    artifact_label: str | None = None,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", artifact_label or label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0402_evidence": label}),
        media_type=media_type,
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
            mapping[item] for item in cast("list[str]", operation["source_entity_ids"])
        ]
        operation["target_entity_ids"] = [
            mapping[item] for item in cast("list[str]", operation["target_entity_ids"])
        ]
    payload["entities"] = [*first_entities, *second_entities]
    payload["lineage_operations"] = [*first_operations, *second_operations]
    return _strict_m0102_request(payload)


def _unresolved_full_chain_identity_request() -> ReconcileIdentityLineageRequest:
    payload = _m0102_payload("complete_ordinary_lineage")
    unresolved = _m0102_payload("missing_concordance_is_not_negative")
    comparison = next(
        entity
        for entity in cast("list[dict[str, Any]]", unresolved["entities"])
        if entity["entity_id"] == "spc-comparison"
    )
    cast("list[dict[str, Any]]", payload["entities"]).append(copy.deepcopy(comparison))
    payload["concordance_observations"] = copy.deepcopy(unresolved["concordance_observations"])
    return _strict_m0102_request(payload)


def _genuine_identity_resolution(case_id: str) -> IdentityLineageResolution:
    if case_id == "valid_unresolved_identity_abstains":
        request = _unresolved_full_chain_identity_request()
    elif case_id in {
        "specimen_subject_swap",
        "aliquot_subject_swap",
        "run_subject_swap",
        "derived_object_subject_swap",
        "swap_does_not_relabel",
        "swap_does_not_rewrite_edges",
        "physical_cross_patient_link",
        "mass_spec_cross_patient_binding",
        "genome_transcript_source_mismatch",
        "bundle_mixed_subject",
        "propagation_reaches_bundle_only",
        "no_patient_assignment_inferred",
    }:
        request = _two_subject_identity_request()
    else:
        request = _strict_m0102_request(_m0102_payload("complete_ordinary_lineage"))
    with TemporaryDirectory(prefix="m0402-m0102-") as temporary:
        store = M0102EventStore(Path(temporary) / "identity.sqlite3")
        with M0102Service(store) as service:
            return service.execute(request)


def _genuine_protocol_result(
    identity: IdentityLineageResolution,
    *,
    case_id: str,
) -> ProteoformProtocolConformanceResult:
    seed = build_m0401_request("canonical_reference_bundle_conforms")
    profile = seed.conformance_profile
    if case_id == "valid_quarantined_m0401_quarantines":
        profile_payload = profile.model_dump(mode="python")
        profile_payload["approved_coordinate_profiles"] = (
            ApprovedCoordinateProfile(
                genome_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                transcript_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                protein_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                coordinate_mapping_version="99.0.0",
            ),
        )
        profile = ReviewedProteoformConformanceProfile.model_validate(
            profile_payload,
            strict=True,
        )
    references = seed.context.references.model_copy(
        update={
            "approved_configuration": (
                seed.context.references.approved_configuration.model_copy(
                    update={
                        "evidence": (
                            seed.context.references.approved_configuration.evidence.model_copy(
                                update={
                                    "digest": m0401_configuration_digest(
                                        seed.protocol_schema,
                                        profile,
                                    )
                                }
                            )
                        )
                    }
                )
            ),
            "identity_lineage": seed.context.references.identity_lineage.model_copy(
                update={"binding_digest": identity.resolution_digest}
            ),
        }
    )
    context = seed.context.model_copy(update={"references": references})
    request = EvaluateProteoformProtocolRequest(
        request_id=context.request_id,
        context=context,
        protocol_schema=seed.protocol_schema,
        conformance_profile=profile,
        supersedes_result_digest=None,
    )
    return evaluate_proteoform_protocol(request)


def _policy(*, maximum: bool = False, reorderable: bool = False) -> ProteoformIdentityLineagePolicy:
    method_count = 64 if maximum else 2 if reorderable else 1
    methods = tuple(
        ApprovedProteoformDerivationMethod(
            method_id=_oid("method", index),
            version=f"1.0.{index}",
            evidence=_artifact(
                f"method-{index}",
                media_type=DERIVATION_MEDIA_TYPE,
            ),
        )
        for index in range(method_count)
    )
    return ProteoformIdentityLineagePolicy(
        policy_id=_oid("policy", "maximum" if maximum else "canonical"),
        version="1.0.0",
        max_artifact_claims=M0402_MAX_ARTIFACT_CLAIMS if maximum else 16,
        max_derivation_sources=255 if maximum else 15,
        approved_derivation_methods=methods,
        evidence=_artifact("policy", media_type=POLICY_MEDIA_TYPE),
        reviewed_by=_oid("reviewer", "synthetic"),
        reviewed_at=FIXED_TIME,
    )


def _anchor_subjects(
    identity: IdentityLineageResolution,
    entity_id: str,
) -> tuple[str, ...]:
    return next(
        node.subject_component_ids for node in identity.graph.nodes if node.entity_id == entity_id
    )


def _claim(  # noqa: PLR0913 - explicit artifact-claim mutation controls.
    *,
    index: int,
    role: ProteoformLineageArtifactRole,
    identity: IdentityLineageResolution,
    protocol: ProteoformProtocolConformanceResult,
    entity_id: str = "obj-a",
    subjects: tuple[str, ...] | None = None,
    evidence_state: ProteoformLineageEvidenceState = ProteoformLineageEvidenceState.OBSERVED,
    digest: str | None = None,
    artifact_label: str | None = None,
) -> ProteoformLineageArtifactClaim:
    label = f"{role.value}-{index:03d}"
    return ProteoformLineageArtifactClaim(
        claim_id=_oid("claim", label),
        role=role,
        artifact=_artifact(
            label,
            media_type=ROLE_MEDIA_TYPES[role],
            digest=digest,
            artifact_label=artifact_label,
        ),
        identity_entity_id=entity_id,
        declared_subject_component_ids=subjects or _anchor_subjects(identity, entity_id),
        producer_identity_resolution_digest=identity.resolution_digest,
        producer_protocol_result_digest=protocol.result_digest,
        producer_reference_bundle_digest=protocol.receipt.reference_bundle_digest,
        producer_coordinate_policy_digest=protocol.receipt.coordinate_policy_digest,
        evidence_state=evidence_state,
    )


def _canonical_claims(
    identity: IdentityLineageResolution,
    protocol: ProteoformProtocolConformanceResult,
    *,
    evidence_state: ProteoformLineageEvidenceState = ProteoformLineageEvidenceState.OBSERVED,
) -> tuple[ProteoformLineageArtifactClaim, ...]:
    return tuple(
        _claim(
            index=index,
            role=role,
            identity=identity,
            protocol=protocol,
            evidence_state=evidence_state,
        )
        for index, role in enumerate(ProteoformLineageArtifactRole)
    )


def _claim_with(
    claim: ProteoformLineageArtifactClaim,
    **updates: object,
) -> ProteoformLineageArtifactClaim:
    payload = claim.model_dump(mode="python")
    payload.update(updates)
    return ProteoformLineageArtifactClaim.model_validate(payload, strict=True)


def _claim_for_role(
    claims: tuple[ProteoformLineageArtifactClaim, ...],
    role: ProteoformLineageArtifactRole,
) -> ProteoformLineageArtifactClaim:
    return next(item for item in claims if item.role is role)


def _context(
    protocol: ProteoformProtocolConformanceResult,
    identity: IdentityLineageResolution,
    policy: ProteoformIdentityLineagePolicy,
) -> ExecutionContext:
    base = protocol.request.context
    references = base.references.model_copy(
        update={
            "approved_configuration": base.references.approved_configuration.model_copy(
                update={
                    "evidence": base.references.approved_configuration.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            ),
            "identity_lineage": base.references.identity_lineage.model_copy(
                update={"binding_digest": identity.resolution_digest}
            ),
            "quality": base.references.quality.model_copy(
                update={
                    "evidence": base.references.quality.evidence.model_copy(
                        update={"digest": protocol.result_digest}
                    )
                }
            ),
        }
    )
    return base.model_copy(update={"references": references})


def build_scenario_request(
    case_id: str = "canonical_all_seven_entity_chain",
) -> ReconcileProteoformIdentityLineageRequest:
    """Execute public M01-02 and M04-01, then build one strict M04-02 request."""

    identity = _genuine_identity_resolution(case_id)
    protocol = _genuine_protocol_result(identity, case_id=case_id)
    maximum = case_id == "maximum_shape_accepted"
    reorderable = case_id == "semantic_reorder_full_result_equality"
    policy = _policy(maximum=maximum, reorderable=reorderable)
    state = {
        "missing_abstains": ProteoformLineageEvidenceState.MISSING,
        "indeterminate_abstains": ProteoformLineageEvidenceState.INDETERMINATE,
        "unsupported_abstains": ProteoformLineageEvidenceState.UNSUPPORTED,
        "redacted_abstains": ProteoformLineageEvidenceState.REDACTED,
    }.get(case_id, ProteoformLineageEvidenceState.OBSERVED)
    if maximum:
        source_roles = tuple(ProteoformLineageArtifactRole)[:-1]
        claims = (
            *(
                _claim(
                    index=index,
                    role=source_roles[index % len(source_roles)],
                    identity=identity,
                    protocol=protocol,
                )
                for index in range(M0402_MAX_DERIVATION_SOURCES)
            ),
            _claim(
                index=M0402_MAX_DERIVATION_SOURCES,
                role=ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE,
                identity=identity,
                protocol=protocol,
            ),
        )
    else:
        claims = _canonical_claims(identity, protocol, evidence_state=state)

    swap_roles = {
        "specimen_subject_swap": ProteoformLineageArtifactRole.GENOME_MANIFEST,
        "aliquot_subject_swap": ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
        "run_subject_swap": ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST,
        "derived_object_subject_swap": ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST,
        "swap_does_not_relabel": ProteoformLineageArtifactRole.GENOME_MANIFEST,
        "swap_does_not_rewrite_edges": ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
    }
    if case_id in swap_roles:
        target = _claim_for_role(claims, swap_roles[case_id])
        replacement = _claim_with(
            target,
            declared_subject_component_ids=_anchor_subjects(identity, "obj-b"),
        )
        claims = tuple(replacement if item.claim_id == target.claim_id else item for item in claims)

    if case_id in {
        "same_binding_scope_collision",
        "duplicate_content_same_scope_retained",
        "all_collision_participants_retained",
        "collision_and_duplicate_coexist",
    }:
        original = _claim_for_role(
            claims,
            ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST,
        )
        extra = _claim(
            index=100,
            role=original.role,
            identity=identity,
            protocol=protocol,
            digest=(
                original.artifact.digest if case_id != "same_binding_scope_collision" else None
            ),
        )
        claims = (*claims, extra)

    if case_id in {
        "duplicate_content_different_scope_retained",
        "duplicate_has_no_authoritative_copy",
    }:
        original = _claim_for_role(
            claims,
            ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST,
        )
        genome = _claim_for_role(claims, ProteoformLineageArtifactRole.GENOME_MANIFEST)
        duplicate = _claim_with(
            genome,
            artifact=genome.artifact.model_copy(update={"digest": original.artifact.digest}),
        )
        claims = tuple(duplicate if item.claim_id == genome.claim_id else item for item in claims)

    if case_id in {"artifact_identity_digest_collision", "collision_and_duplicate_coexist"}:
        genome = _claim_for_role(claims, ProteoformLineageArtifactRole.GENOME_MANIFEST)
        transcriptome = _claim_for_role(
            claims,
            ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
        )
        collision = _claim_with(
            transcriptome,
            artifact=transcriptome.artifact.model_copy(
                update={"artifact_id": genome.artifact.artifact_id}
            ),
        )
        claims = tuple(
            collision if item.claim_id == transcriptome.claim_id else item for item in claims
        )

    cross_patient_cases = {
        "physical_cross_patient_link",
        "mass_spec_cross_patient_binding",
        "genome_transcript_source_mismatch",
        "bundle_mixed_subject",
        "propagation_reaches_bundle_only",
        "no_patient_assignment_inferred",
    }
    if case_id in cross_patient_cases:
        roles_on_second_path = {
            "physical_cross_patient_link": {
                ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST,
                ProteoformLineageArtifactRole.GENOME_MANIFEST,
            },
            "mass_spec_cross_patient_binding": {
                ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
            },
            "genome_transcript_source_mismatch": {
                ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST
            },
        }.get(
            case_id,
            {ProteoformLineageArtifactRole.GENOME_MANIFEST},
        )
        claims = tuple(
            _claim_with(
                item,
                identity_entity_id="obj-b",
                declared_subject_component_ids=_anchor_subjects(identity, "obj-b"),
            )
            if item.role in roles_on_second_path
            else item
            for item in claims
        )
        if case_id == "bundle_mixed_subject":
            bundle_claim = _claim_for_role(
                claims,
                ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE,
            )
            mixed = tuple(
                sorted(
                    {
                        *_anchor_subjects(identity, "obj-a"),
                        *_anchor_subjects(identity, "obj-b"),
                    }
                )
            )
            claims = tuple(
                _claim_with(item, declared_subject_component_ids=mixed)
                if item.claim_id == bundle_claim.claim_id
                else item
                for item in claims
            )

    drift_fields = {
        "producer_identity_and_protocol_drift": {
            "producer_identity_resolution_digest": sha256_digest({"stale": "identity"}),
            "producer_protocol_result_digest": sha256_digest({"stale": "protocol"}),
        },
        "producer_reference_and_coordinate_drift": {
            "producer_reference_bundle_digest": sha256_digest({"stale": "reference"}),
            "producer_coordinate_policy_digest": sha256_digest({"stale": "coordinate"}),
        },
    }
    if case_id in drift_fields:
        target = claims[0]
        changed = _claim_with(target, **drift_fields[case_id])
        claims = tuple(changed if item.claim_id == target.claim_id else item for item in claims)
    bundle = next(
        item
        for item in claims
        if item.role is ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE
    )
    sources = tuple(item.claim_id for item in claims if item is not bundle)
    method = policy.approved_derivation_methods[0]
    derivation = ProteoformLineageArtifactDerivation(
        derivation_id=_oid("derivation", "canonical"),
        source_claim_ids=sources,
        target_claim_id=bundle.claim_id,
        method_id=method.method_id,
        method_version=method.version,
        evidence=_artifact("derivation", media_type=DERIVATION_MEDIA_TYPE),
    )
    context = _context(protocol, identity, policy)
    return ReconcileProteoformIdentityLineageRequest(
        request_id=context.request_id,
        context=context,
        identity_resolution=identity,
        protocol_result=protocol,
        policy=policy,
        artifact_claims=claims,
        derivations=(derivation,),
        supersedes_result_digest=None,
    )


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _inventory_checks(corpus: Corpus) -> list[EvalCheck]:
    groups = corpus["scenario_groups"]
    case_ids = [case for group in groups for case in group["case_ids"]]
    allocation = tuple(len(group["case_ids"]) for group in groups)
    return [
        EvalCheck(
            name="corpus.locked_inventory",
            passed=(
                corpus["module_id"] == MODULE_ID
                and len(groups) == EXPECTED_GROUP_COUNT
                and allocation == EXPECTED_ALLOCATION
                and len(case_ids) == EXPECTED_CASE_COUNT
                and len(set(case_ids)) == EXPECTED_CASE_COUNT
                and all(
                    set(group["case_ids"]) == set(group["case_expectations"]) for group in groups
                )
            ),
            detail=f"groups={len(groups)} cases={len(case_ids)} allocation={allocation}",
        )
    ]


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _strict_request(payload: dict[str, Any]) -> ReconcileProteoformIdentityLineageRequest:
    return _M0402_REQUEST_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)


def _codes(result: ProteoformIdentityLineageResolution) -> set[str]:
    finding_codes = {finding.code.value for finding in result.findings}
    receipt_codes = {code.value for code in result.receipt.finding_codes}
    exact_actions = {
        "duplicate_content_retained": "record",
        "upstream_identity_unresolved": "abstain",
        "identity_not_evaluable": "abstain",
        "artifact_evidence_not_evaluable": "abstain",
    }
    if (
        finding_codes != receipt_codes
        or tuple(result.receipt.finding_codes) != tuple(sorted(result.receipt.finding_codes))
        or result.receipt.disposition is not result.disposition
        or any(
            finding.action.value != exact_actions.get(finding.code.value, "quarantine")
            for finding in result.findings
        )
    ):
        return {"__receipt_or_action_mismatch__"}
    return finding_codes


def _result(
    case_id: str = "canonical_all_seven_entity_chain",
) -> ProteoformIdentityLineageResolution:
    return reconcile_proteoform_identity_lineage(build_scenario_request(case_id))


def _rejected_request(
    case_id: str,
    mutate: Callable[[dict[str, Any]], None],
    *,
    base: str = "canonical_all_seven_entity_chain",
) -> EvalCheck:
    payload = build_scenario_request(base).model_dump(mode="json", exclude_none=False)
    mutate(payload)
    try:
        request = _strict_request(payload)
        reconcile_proteoform_identity_lineage(request)
    except (ValidationError, ValueError) as error:
        return _scenario(
            case_id,
            passed=True,
            detail=f"validation_rejected:{type(error).__name__}",
        )
    return _scenario(case_id, passed=False, detail="request unexpectedly accepted")


def _rejected_result(
    case_id: str,
    result: ProteoformIdentityLineageResolution,
    mutate: Callable[[dict[str, Any]], None],
    *,
    recompute_outer: bool = True,
) -> EvalCheck:
    payload = result.model_dump(mode="json", exclude_none=False)
    mutate(payload)
    if recompute_outer:
        payload["result_digest"] = result_payload_digest(payload)
    try:
        _M0402_RESULT_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
    except (ValidationError, ValueError) as error:
        return _scenario(
            case_id,
            passed=True,
            detail=f"validation_rejected:{type(error).__name__}",
        )
    return _scenario(case_id, passed=False, detail="result forgery unexpectedly accepted")


def _canonical_checks() -> list[EvalCheck]:
    request = build_scenario_request()
    result = reconcile_proteoform_identity_lineage(request)
    entity_kinds = {node.kind.value for node in request.identity_resolution.graph.nodes}
    roles = {artifact.role for artifact in result.graph.artifacts}
    bundle = next(
        artifact
        for artifact in result.graph.artifacts
        if artifact.role is ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE
    )
    derivation = result.graph.derivations[0]
    physical_edges = {
        operation.operation_id for operation in request.identity_resolution.graph.operations
    }
    artifact_edges = {item.derivation_id for item in result.graph.derivations}
    retained_claims = {item.claim_id for item in result.graph.artifacts}
    submitted_claims = {item.claim_id for item in request.artifact_claims}
    retained_derivations = {item.derivation_id for item in result.graph.derivations}
    submitted_derivations = {item.derivation_id for item in request.derivations}
    bindings_exact = (
        result.identity_resolution_digest
        == result.receipt.identity_resolution_digest
        == request.identity_resolution.resolution_digest
        == request.protocol_result.receipt.identity_subject_digest
        and result.protocol_result_digest
        == result.receipt.protocol_result_digest
        == request.protocol_result.result_digest
        and result.receipt.protocol_receipt_digest == request.protocol_result.receipt.receipt_digest
        and result.receipt.reference_bundle_digest
        == request.protocol_result.receipt.reference_bundle_digest
        and result.receipt.coordinate_policy_digest
        == request.protocol_result.receipt.coordinate_policy_digest
    )
    canonical = (
        result.disposition is ProteoformLineageDisposition.RECONCILED and _codes(result) == set()
    )
    return [
        _scenario(
            "canonical_all_seven_entity_chain",
            passed=canonical
            and entity_kinds
            == {"patient", "specimen", "aliquot", "section", "analyte", "run", "derived_object"},
            detail=f"kinds={','.join(sorted(entity_kinds))}",
        ),
        _scenario(
            "canonical_all_five_artifact_roles",
            passed=canonical and roles == set(ProteoformLineageArtifactRole),
            detail=f"roles={len(roles)}",
        ),
        _scenario(
            "exact_single_four_role_assembly",
            passed=canonical
            and len(result.graph.derivations) == 1
            and len(derivation.source_claim_ids) == EXPECTED_SOURCE_ROLE_COUNT
            and derivation.target_claim_id == bundle.claim_id
            and set(derivation.source_claim_ids) == submitted_claims - {bundle.claim_id},
            detail=f"sources={len(derivation.source_claim_ids)};targets=1",
        ),
        _scenario(
            "physical_and_artifact_graphs_remain_distinct",
            passed=canonical
            and physical_edges.isdisjoint(artifact_edges)
            and result.graph.physical_graph_digest == request.identity_resolution.graph.graph_digest
            and result.graph.graph_digest != result.graph.physical_graph_digest,
            detail=f"physical_edges={len(physical_edges)};artifact_edges={len(artifact_edges)}",
        ),
        _scenario(
            "exact_m0102_m0401_bindings",
            passed=canonical and bindings_exact,
            detail=f"identity={result.identity_resolution_digest};protocol={result.protocol_result_digest}",
        ),
        _scenario(
            "immutable_nonsecret_graph_retention",
            passed=canonical
            and retained_claims == submitted_claims
            and retained_derivations == submitted_derivations
            and not result.mutates_upstream
            and result.request.identity_resolution == request.identity_resolution,
            detail=f"claims={len(retained_claims)};derivations={len(retained_derivations)}",
        ),
    ]


def _swap_checks() -> list[EvalCheck]:
    case_ids = (
        "specimen_subject_swap",
        "aliquot_subject_swap",
        "run_subject_swap",
        "derived_object_subject_swap",
        "swap_does_not_relabel",
        "swap_does_not_rewrite_edges",
    )
    requests = {case_id: build_scenario_request(case_id) for case_id in case_ids}
    results = {
        case_id: reconcile_proteoform_identity_lineage(request)
        for case_id, request in requests.items()
    }
    checks: list[EvalCheck] = []
    for case_id in case_ids[:4]:
        result = results[case_id]
        checks.append(
            _scenario(
                case_id,
                passed=result.disposition is ProteoformLineageDisposition.QUARANTINED
                and "identity_swap" in _codes(result),
                detail=f"codes={','.join(sorted(_codes(result)))}",
            )
        )
    relabel_case = "swap_does_not_relabel"
    relabel_result = results[relabel_case]
    relabel_request = requests[relabel_case]
    checks.append(
        _scenario(
            relabel_case,
            passed=relabel_result.disposition is ProteoformLineageDisposition.QUARANTINED
            and "identity_swap" in _codes(relabel_result)
            and relabel_result.request.identity_resolution == relabel_request.identity_resolution
            and not relabel_result.infers_identity
            and not relabel_result.mutates_upstream,
            detail="quarantined; exact embedded nodes retained",
        )
    )
    edge_case = "swap_does_not_rewrite_edges"
    edge_result = results[edge_case]
    edge_request = requests[edge_case]
    submitted_edges = {
        (edge.derivation_id, edge.source_claim_ids, edge.target_claim_id)
        for edge in edge_request.derivations
    }
    resolved_edges = {
        (edge.derivation_id, edge.source_claim_ids, edge.target_claim_id)
        for edge in edge_result.graph.derivations
    }
    checks.append(
        _scenario(
            edge_case,
            passed=edge_result.disposition is ProteoformLineageDisposition.QUARANTINED
            and "identity_swap" in _codes(edge_result)
            and submitted_edges == resolved_edges
            and edge_result.graph.physical_graph_digest
            == edge_request.identity_resolution.graph.graph_digest,
            detail="physical and artifact edges retained",
        )
    )
    return checks


def _collision_checks() -> list[EvalCheck]:
    cases = {
        case_id: _result(case_id)
        for case_id in (
            "same_binding_scope_collision",
            "artifact_identity_digest_collision",
            "duplicate_content_same_scope_retained",
            "duplicate_content_different_scope_retained",
            "all_collision_participants_retained",
            "duplicate_has_no_authoritative_copy",
            "collision_and_duplicate_coexist",
        )
    }

    def duplicates(
        result: ProteoformIdentityLineageResolution,
    ) -> list[ResolvedProteoformLineageArtifact]:
        counts: dict[str, int] = {}
        for artifact in result.graph.artifacts:
            counts[artifact.artifact_digest] = counts.get(artifact.artifact_digest, 0) + 1
        duplicate_digests = {digest for digest, count in counts.items() if count > 1}
        return [
            artifact
            for artifact in result.graph.artifacts
            if artifact.artifact_digest in duplicate_digests
        ]

    same = cases["same_binding_scope_collision"]
    identity = cases["artifact_identity_digest_collision"]
    same_duplicate = cases["duplicate_content_same_scope_retained"]
    different_duplicate = cases["duplicate_content_different_scope_retained"]
    retained = cases["all_collision_participants_retained"]
    no_authority = cases["duplicate_has_no_authoritative_copy"]
    combined = cases["collision_and_duplicate_coexist"]
    return [
        _scenario(
            "same_binding_scope_collision",
            passed=same.disposition is ProteoformLineageDisposition.QUARANTINED
            and "binding_scope_collision" in _codes(same),
            detail=f"codes={','.join(sorted(_codes(same)))}",
        ),
        _scenario(
            "artifact_identity_digest_collision",
            passed=identity.disposition is ProteoformLineageDisposition.QUARANTINED
            and "artifact_identity_collision" in _codes(identity),
            detail=f"codes={','.join(sorted(_codes(identity)))}",
        ),
        _scenario(
            "duplicate_content_same_scope_retained",
            passed=same_duplicate.disposition is ProteoformLineageDisposition.QUARANTINED
            and {"binding_scope_collision", "duplicate_content_retained"}.issubset(
                _codes(same_duplicate)
            )
            and len(duplicates(same_duplicate)) == EXPECTED_DUPLICATE_PAIR_SIZE,
            detail=f"duplicates={len(duplicates(same_duplicate))}",
        ),
        _scenario(
            "duplicate_content_different_scope_retained",
            passed=different_duplicate.disposition is ProteoformLineageDisposition.RECONCILED
            and _codes(different_duplicate) == {"duplicate_content_retained"}
            and len(duplicates(different_duplicate)) == EXPECTED_DUPLICATE_PAIR_SIZE,
            detail=f"codes={','.join(sorted(_codes(different_duplicate)))}",
        ),
        _scenario(
            "all_collision_participants_retained",
            passed=retained.disposition is ProteoformLineageDisposition.QUARANTINED
            and len(retained.graph.artifacts) == len(retained.request.artifact_claims)
            and "binding_scope_collision" in _codes(retained),
            detail=f"retained={len(retained.graph.artifacts)}",
        ),
        _scenario(
            "duplicate_has_no_authoritative_copy",
            passed=no_authority.disposition is ProteoformLineageDisposition.RECONCILED
            and len(duplicates(no_authority)) == EXPECTED_DUPLICATE_PAIR_SIZE
            and all(
                "authoritative" not in artifact.model_dump(mode="python")
                for artifact in duplicates(no_authority)
            ),
            detail="both duplicate declarations retained without selection",
        ),
        _scenario(
            "collision_and_duplicate_coexist",
            passed=combined.disposition is ProteoformLineageDisposition.QUARANTINED
            and {
                "artifact_identity_collision",
                "binding_scope_collision",
                "duplicate_content_retained",
            }.issubset(_codes(combined))
            and len(combined.graph.artifacts) == len(combined.request.artifact_claims),
            detail=f"codes={','.join(sorted(_codes(combined)))}",
        ),
    ]


def _cross_patient_checks() -> list[EvalCheck]:
    case_ids = (
        "physical_cross_patient_link",
        "mass_spec_cross_patient_binding",
        "genome_transcript_source_mismatch",
        "bundle_mixed_subject",
        "propagation_reaches_bundle_only",
        "no_patient_assignment_inferred",
    )
    results = {case_id: _result(case_id) for case_id in case_ids}
    checks = [
        _scenario(
            case_id,
            passed=results[case_id].disposition is ProteoformLineageDisposition.QUARANTINED
            and "cross_patient_link" in _codes(results[case_id]),
            detail=f"codes={','.join(sorted(_codes(results[case_id])))}",
        )
        for case_id in case_ids[:4]
    ]
    propagation = results["propagation_reaches_bundle_only"]
    target_id = propagation.graph.derivations[0].target_claim_id
    mixed_artifacts = {
        artifact.claim_id
        for artifact in propagation.graph.artifacts
        if len(artifact.resolved_subject_component_ids) > 1
    }
    checks.append(
        _scenario(
            "propagation_reaches_bundle_only",
            passed=propagation.disposition is ProteoformLineageDisposition.QUARANTINED
            and "cross_patient_link" in _codes(propagation)
            and mixed_artifacts == {target_id},
            detail=f"mixed_artifacts={len(mixed_artifacts)}",
        )
    )
    nonassignment = results["no_patient_assignment_inferred"]
    upstream_subjects = {
        subject
        for node in nonassignment.request.identity_resolution.graph.nodes
        for subject in node.subject_component_ids
    }
    output_subjects = {
        subject
        for artifact in nonassignment.graph.artifacts
        for subject in artifact.resolved_subject_component_ids
    }
    checks.append(
        _scenario(
            "no_patient_assignment_inferred",
            passed=nonassignment.disposition is ProteoformLineageDisposition.QUARANTINED
            and "cross_patient_link" in _codes(nonassignment)
            and output_subjects.issubset(upstream_subjects)
            and not nonassignment.infers_identity,
            detail=f"upstream_subjects={len(upstream_subjects)};output_subjects={len(output_subjects)}",
        )
    )
    return checks


def _malformed_shape_checks() -> list[EvalCheck]:
    def missing_kind(payload: dict[str, Any]) -> None:
        identity = cast("dict[str, Any]", payload["identity_resolution"])
        graph = cast("dict[str, Any]", identity["graph"])
        graph["nodes"] = [
            item
            for item in cast("list[dict[str, Any]]", graph["nodes"])
            if item["kind"] != "specimen"
        ]

    def unknown_role(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["artifact_claims"])[0]["role"] = "raw_table"

    def replace_role(payload: dict[str, Any], *, role: str, media_type: str) -> None:
        claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
        target = next(item for item in claims if item["role"] == "ptm_annotation_manifest")
        target["role"] = role
        cast("dict[str, Any]", target["artifact"])["media_type"] = media_type

    def missing_role(payload: dict[str, Any]) -> None:
        replace_role(
            payload,
            role="genome_manifest",
            media_type=ROLE_MEDIA_TYPES[ProteoformLineageArtifactRole.GENOME_MANIFEST],
        )

    def multiple_bundles(payload: dict[str, Any]) -> None:
        replace_role(
            payload,
            role="protein_rna_discordance_input_bundle",
            media_type=ROLE_MEDIA_TYPES[
                ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE
            ],
        )

    def self_dependency(payload: dict[str, Any]) -> None:
        derivation = cast("list[dict[str, Any]]", payload["derivations"])[0]
        sources = cast("list[str]", derivation["source_claim_ids"])
        sources[0] = cast("str", derivation["target_claim_id"])

    def dangling(payload: dict[str, Any]) -> None:
        derivation = cast("list[dict[str, Any]]", payload["derivations"])[0]
        cast("list[str]", derivation["source_claim_ids"])[0] = _oid("claim", "dangling")

    def disconnected(payload: dict[str, Any]) -> None:
        derivation = cast("list[dict[str, Any]]", payload["derivations"])[0]
        sources = cast("list[str]", derivation["source_claim_ids"])
        sources.pop()

    def unapproved(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["derivations"])[0]["method_id"] = _oid(
            "method", "unapproved"
        )

    return [
        _rejected_request("missing_required_entity_kind", missing_kind),
        _rejected_request("unknown_artifact_role", unknown_role),
        _rejected_request("missing_required_source_role", missing_role),
        _rejected_request("multiple_bundle_targets", multiple_bundles),
        _rejected_request("derivation_self_dependency", self_dependency),
        _rejected_request("dangling_endpoint", dangling),
        _rejected_request(
            "disconnected_source",
            disconnected,
            base="same_binding_scope_collision",
        ),
        _rejected_request("unapproved_derivation_method", unapproved),
    ]


def _upstream_drift_checks() -> list[EvalCheck]:
    stale = sha256_digest({"m0402": "stale"})

    def stale_context(payload: dict[str, Any]) -> None:
        cast("dict[str, Any]", payload["context"])["references"]["identity_lineage"][
            "binding_digest"
        ] = stale

    def stale_identity(payload: dict[str, Any]) -> None:
        cast("dict[str, Any]", payload["identity_resolution"])["resolution_digest"] = stale

    def resigned_protocol(payload: dict[str, Any]) -> None:
        protocol = cast("dict[str, Any]", payload["protocol_result"])
        cast("dict[str, Any]", protocol["support"])["rationale"] = (
            "re-signed caller assertion outside the reviewed protocol result"
        )
        protocol["result_digest"] = m0401_result_payload_digest(protocol)

    def identity_receipt_mismatch(payload: dict[str, Any]) -> None:
        protocol = cast("dict[str, Any]", payload["protocol_result"])
        receipt = cast("dict[str, Any]", protocol["receipt"])
        receipt["identity_subject_digest"] = stale
        receipt["receipt_digest"] = m0401_receipt_digest(receipt)
        protocol["result_digest"] = m0401_result_payload_digest(protocol)

    def intended_use_mismatch(payload: dict[str, Any]) -> None:
        protocol = cast("dict[str, Any]", payload["protocol_result"])
        receipt = cast("dict[str, Any]", protocol["receipt"])
        receipt["intended_use_evidence_digest"] = stale
        receipt["receipt_digest"] = m0401_receipt_digest(receipt)
        protocol["result_digest"] = m0401_result_payload_digest(protocol)

    unresolved = _result("valid_unresolved_identity_abstains")
    nonconformant = _result("valid_quarantined_m0401_quarantines")
    producer_pair = _result("producer_identity_and_protocol_drift")
    reference_pair = _result("producer_reference_and_coordinate_drift")
    return [
        _rejected_request("stale_context_identity_binding", stale_context),
        _rejected_request("self_inconsistent_identity_result", stale_identity),
        _scenario(
            "valid_unresolved_identity_abstains",
            passed=unresolved.disposition is ProteoformLineageDisposition.ABSTAINED
            and _codes(unresolved) == {"upstream_identity_unresolved"},
            detail=f"codes={','.join(sorted(_codes(unresolved)))}",
        ),
        _scenario(
            "valid_quarantined_m0401_quarantines",
            passed=nonconformant.disposition is ProteoformLineageDisposition.QUARANTINED
            and _codes(nonconformant) == {"upstream_protocol_nonconformant"},
            detail=f"codes={','.join(sorted(_codes(nonconformant)))}",
        ),
        _rejected_request("resigned_m0401_forgery_rejected", resigned_protocol),
        _rejected_request("m0401_identity_receipt_mismatch", identity_receipt_mismatch),
        _rejected_request("m0401_intended_use_mismatch", intended_use_mismatch),
        _scenario(
            "producer_identity_and_protocol_drift",
            passed=producer_pair.disposition is ProteoformLineageDisposition.QUARANTINED
            and _codes(producer_pair) == {"producer_identity_drift", "producer_protocol_drift"},
            detail=f"codes={','.join(sorted(_codes(producer_pair)))}",
        ),
        _scenario(
            "producer_reference_and_coordinate_drift",
            passed=reference_pair.disposition is ProteoformLineageDisposition.QUARANTINED
            and _codes(reference_pair)
            == {
                "producer_reference_bundle_drift",
                "producer_coordinate_policy_drift",
            },
            detail=f"codes={','.join(sorted(_codes(reference_pair)))}",
        ),
    ]


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            *map(str, value),
            *(key for child in value.values() for key in _recursive_keys(child)),
        }
    if isinstance(value, list | tuple):
        return {key for child in value for key in _recursive_keys(child)}
    return set()


def _recursive_strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {
            *map(str, value),
            *(item for child in value.values() for item in _recursive_strings(child)),
        }
    if isinstance(value, list | tuple):
        return {item for child in value for item in _recursive_strings(child)}
    return set()


def _evidence_authority_checks() -> list[EvalCheck]:
    states = {
        "observed_reconciles": ProteoformLineageEvidenceState.OBSERVED,
        "missing_abstains": ProteoformLineageEvidenceState.MISSING,
        "indeterminate_abstains": ProteoformLineageEvidenceState.INDETERMINATE,
        "unsupported_abstains": ProteoformLineageEvidenceState.UNSUPPORTED,
        "redacted_abstains": ProteoformLineageEvidenceState.REDACTED,
    }
    results = {case_id: _result(case_id) for case_id in states}
    observed = results["observed_reconciles"]
    checks = [
        _scenario(
            "observed_reconciles",
            passed=observed.disposition is ProteoformLineageDisposition.RECONCILED
            and not _codes(observed)
            and all(
                artifact.evidence_state is ProteoformLineageEvidenceState.OBSERVED
                for artifact in observed.graph.artifacts
            ),
            detail="observed categorical evidence reconciled",
        )
    ]
    for case_id, state in tuple(states.items())[1:]:
        result = results[case_id]
        checks.append(
            _scenario(
                case_id,
                passed=result.disposition is ProteoformLineageDisposition.ABSTAINED
                and _codes(result) == {"artifact_evidence_not_evaluable"}
                and all(artifact.evidence_state is state for artifact in result.graph.artifacts),
                detail=f"state={state.value};codes={','.join(sorted(_codes(result)))}",
            )
        )
    component_views = {
        case_id: tuple(
            (
                artifact.claim_id,
                artifact.declared_subject_component_ids,
                artifact.resolved_subject_component_ids,
            )
            for artifact in result.graph.artifacts
        )
        for case_id, result in results.items()
    }
    checks.append(
        _scenario(
            "all_states_preserve_components",
            passed=len(set(component_views.values())) == 1
            and all(not result.infers_identity for result in results.values()),
            detail="all five categorical states preserve exact identity components",
        )
    )
    rendered = observed.model_dump(mode="json", exclude_none=False)
    keys = _recursive_keys(rendered)
    strings = _recursive_strings(rendered)
    forbidden_protein = {
        "protein_presence",
        "protein_absence",
        "observed_protein",
        "protein_accession",
        "proteoform_presence",
    }
    checks.append(
        _scenario(
            "no_protein_presence_or_absence",
            passed=not forbidden_protein.intersection(keys | strings)
            and not observed.infers_protein
            and not observed.infers_proteoform,
            detail="no protein presence, absence, or proteoform claim",
        )
    )
    forbidden_cn = {
        "raw_copy_number",
        "copy_number_value",
        "protein_rna_discordance_claim",
        "discordance_state",
    }
    checks.append(
        _scenario(
            "no_cn_or_discordance_inference",
            passed=not forbidden_cn.intersection(keys | strings)
            and not observed.performs_cn_to_protein_regression
            and not observed.emits_protein_rna_discordance
            and not observed.performs_all_omics_fusion,
            detail="no copy-number, discordance, or fusion inference",
        )
    )
    return checks


class _TraversalTrap:
    touched = 0

    def __getattribute__(self, name: str) -> object:
        if name == "touched":
            return object.__getattribute__(self, name)
        type(self).touched += 1
        raise AssertionError


class _ArbitraryMapping(Mapping[str, object]):
    touched = 0

    def __getitem__(self, key: str) -> object:
        type(self).touched += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        type(self).touched += 1
        raise AssertionError("iter")

    def __len__(self) -> int:
        type(self).touched += 1
        raise AssertionError("len")


class _HostileDict(dict[str, object]):
    def get(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError

    def items(self) -> NoReturn:
        raise AssertionError

    def __iter__(self) -> NoReturn:
        raise AssertionError


class _FirewallBaseException(BaseException):
    pass


def _authorization_check(case_id: str, *, role: str, state: str) -> EvalCheck:
    payload = build_scenario_request().model_dump(mode="python", exclude_none=False)
    references = cast("dict[str, Any]", cast("dict[str, Any]", payload["context"])["references"])
    cast("dict[str, Any]", references[role])["state"] = state
    _TraversalTrap.touched = 0
    payload["artifact_claims"] = _TraversalTrap()
    try:
        preflight_proteoform_identity_lineage_authorization(payload)
    except ProteoformIdentityLineageAuthorizationError:
        return _scenario(
            case_id,
            passed=_TraversalTrap.touched == 0,
            detail=f"authorization_rejected;governed_traversals={_TraversalTrap.touched}",
        )
    return _scenario(case_id, passed=False, detail="authorization unexpectedly accepted")


def _firewall_check() -> EvalCheck:
    case_id = "dict_subclass_firewall_exception_and_baseexception_boundary"
    canonical = build_scenario_request()
    expected = reconcile_proteoform_identity_lineage(canonical)

    def hostile(value: object) -> object:
        if isinstance(value, dict):
            return _HostileDict({key: hostile(item) for key, item in value.items()})
        if isinstance(value, list):
            return [hostile(item) for item in value]
        return value

    candidate = hostile(canonical.model_dump(mode="python", exclude_none=False))
    actual = reconcile_proteoform_identity_lineage(candidate)
    exception_closed = False
    with patch.object(m0402_engine, "_member", side_effect=RuntimeError("ordinary")):
        try:
            preflight_proteoform_identity_lineage_authorization(canonical)
        except ProteoformIdentityLineageAuthorizationError:
            exception_closed = True
    base_propagated = False
    with patch.object(m0402_engine, "_member", side_effect=_FirewallBaseException()):
        try:
            preflight_proteoform_identity_lineage_authorization(canonical)
        except _FirewallBaseException:
            base_propagated = True
    return _scenario(
        case_id,
        passed=actual == expected and exception_closed and base_propagated,
        detail=(
            f"hostile_dict_equality={actual == expected};"
            f"exception_fail_closed={exception_closed};baseexception_propagated={base_propagated}"
        ),
    )


def _duplicate_json_check() -> EvalCheck:
    request = build_scenario_request()
    rendered = request.model_dump_json(exclude_none=False)
    duplicate = rendered.replace(
        "{",
        '{"operation":"reconcile_proteoform_identity_lineage",',
        1,
    )
    plugin = M0402Plugin(M0402Service())
    try:
        plugin.validate(duplicate)
    except StrictJsonError as error:
        return _scenario(
            "duplicate_json_rejected",
            passed=error.code.value == "json_duplicate_key",
            detail=f"validation_rejected:{error.code.value}",
        )
    return _scenario("duplicate_json_rejected", passed=False, detail="duplicate JSON accepted")


def _maximum_shape_check() -> EvalCheck:
    request = build_scenario_request("maximum_shape_accepted")
    result = reconcile_proteoform_identity_lineage(request)
    passed = (
        len(request.artifact_claims) == M0402_MAX_ARTIFACT_CLAIMS
        and len(request.derivations[0].source_claim_ids) == M0402_MAX_DERIVATION_SOURCES
        and len(request.policy.approved_derivation_methods) == M0402_MAX_APPROVED_METHODS
        and len(result.evidence) == M0402_MAX_EVIDENCE
        and result.disposition is ProteoformLineageDisposition.QUARANTINED
        and "binding_scope_collision" in _codes(result)
    )
    return _scenario(
        "maximum_shape_accepted",
        passed=passed,
        detail=(
            f"claims={len(request.artifact_claims)};sources="
            f"{len(request.derivations[0].source_claim_ids)};methods="
            f"{len(request.policy.approved_derivation_methods)};evidence={len(result.evidence)};"
            f"disposition={result.disposition.value}"
        ),
    )


def _semantic_reorder_check() -> EvalCheck:
    request = build_scenario_request("semantic_reorder_full_result_equality")
    payload = request.model_dump(mode="json", exclude_none=False)
    cast("list[Any]", payload["artifact_claims"]).reverse()
    cast("list[Any]", payload["derivations"]).reverse()
    policy = cast("dict[str, Any]", payload["policy"])
    cast("list[Any]", policy["approved_derivation_methods"]).reverse()
    for claim in cast("list[dict[str, Any]]", payload["artifact_claims"]):
        cast("list[Any]", claim["declared_subject_component_ids"]).reverse()
    for derivation in cast("list[dict[str, Any]]", payload["derivations"]):
        cast("list[Any]", derivation["source_claim_ids"]).reverse()
    reordered = _strict_request(payload)
    left = reconcile_proteoform_identity_lineage(request)
    right = reconcile_proteoform_identity_lineage(reordered)
    return _scenario(
        "semantic_reorder_full_result_equality",
        passed=request == reordered
        and canonical_request_digest(request) == canonical_request_digest(reordered)
        and left == right
        and left.model_dump_json() == right.model_dump_json(),
        detail=f"result_digest={left.result_digest};complete_equality={left == right}",
    )


def _privacy_check() -> EvalCheck:
    result = _result()
    rendered = json.dumps(result.model_dump(mode="json", exclude_none=False), sort_keys=True)
    payload = build_scenario_request().model_dump(mode="json", exclude_none=False)
    cast("list[dict[str, Any]]", payload["artifact_claims"])[0]["biological_claim"] = (
        "patient_name_canary"
    )
    canary_rejected = False
    sanitized = ""
    try:
        _strict_request(payload)
    except ValidationError as error:
        canary_rejected = True
        sanitized = json.dumps(sanitized_validation_errors(error), sort_keys=True)
    canaries = {
        "patient_name_canary",
        "raw_sequence_canary",
        "raw_copy_number_canary",
        "raw_rna_abundance_canary",
        "raw_protein_abundance_canary",
        "ptm_site_canary",
        "treatment_canary",
    }
    keys = _recursive_keys(result.model_dump(mode="json", exclude_none=False))
    return _scenario(
        "recursive_privacy_canary_absent",
        passed=canary_rejected
        and "patient_name_canary" not in sanitized
        and all(canary not in rendered for canary in canaries)
        and not {
            "direct_identifier",
            "sequence",
            "accession",
            "copy_number_value",
            "rna_abundance",
            "protein_abundance",
            "ptm_site",
            "treatment_recommendation",
        }.intersection(keys),
        detail="injected canary rejected without reflection; recursive result scan clean",
    )


def _forgery_check() -> EvalCheck:
    result = _result("producer_identity_and_protocol_drift")
    stale = sha256_digest({"m0402": "resigned-forgery"})

    def accepted(mutate: Callable[[dict[str, Any]], None]) -> bool:
        payload = result.model_dump(mode="json", exclude_none=False)
        mutate(payload)
        payload["result_digest"] = result_payload_digest(payload)
        try:
            _M0402_RESULT_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
        except (ValidationError, ValueError):
            return False
        return True

    def graph(payload: dict[str, Any]) -> None:
        graph_payload = cast("dict[str, Any]", payload["graph"])
        cast("list[dict[str, Any]]", graph_payload["artifacts"])[0]["artifact_digest"] = stale
        graph_payload["graph_digest"] = resolved_graph_digest(graph_payload)
        payload["graph_digest"] = graph_payload["graph_digest"]

    def finding(payload: dict[str, Any]) -> None:
        cast("list[dict[str, Any]]", payload["findings"])[0]["evidence_basis_digest"] = stale

    def provenance(payload: dict[str, Any]) -> None:
        cast("dict[str, Any]", payload["provenance"])["configuration_digest"] = stale

    def evidence(payload: dict[str, Any]) -> None:
        cast("dict[str, Any]", cast("list[Any]", payload["evidence"])[0])["claim"] = (
            "re-signed synthetic evidence claim"
        )

    rejected = [not accepted(mutate) for mutate in (graph, finding, provenance, evidence)]
    return _scenario(
        "resigned_graph_finding_provenance_evidence_forgery_rejected",
        passed=all(rejected),
        detail=f"rejected_regions={sum(rejected)}/4",
    )


def _authority_ceiling_check() -> EvalCheck:
    result = _result()
    expected_false = {
        "emits_protein_rna_discordance",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_identity",
        "infers_consent",
        "infers_protein",
        "infers_proteoform",
        "infers_kinase_activity",
        "performs_cn_to_protein_regression",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream",
    }
    payload = result.model_dump(mode="json", exclude_none=False)
    seen: dict[str, list[object]] = {field: [] for field in expected_false}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in seen:
                    seen[key].append(child)
                collect(child)
        elif isinstance(value, list | tuple):
            for child in value:
                collect(child)

    collect(payload)
    exact = all(values and all(value is False for value in values) for values in seen.values())
    return _scenario(
        "recursive_authority_ceiling",
        passed=exact
        and result.parent_target == "protein_rna_discordance"
        and result.receipt.parent_target == "protein_rna_discordance",
        detail=f"exact_false_fields={sum(bool(values) for values in seen.values())}/13",
    )


def _strict_boundary_checks() -> list[EvalCheck]:
    controls = (
        ("approved_configuration_denied_zero_traversal", "approved_configuration", "rejected"),
        ("identity_lineage_unresolved_zero_traversal", "identity_lineage", "unresolved"),
        ("provenance_denied_zero_traversal", "provenance", "rejected"),
        ("consent_denied_zero_traversal", "consent", "withheld"),
        ("quality_denied_zero_traversal", "quality", "rejected"),
        ("support_denied_zero_traversal", "support", "rejected"),
        ("intended_use_denied_zero_traversal", "intended_use", "rejected"),
    )
    checks = [
        _authorization_check(case_id, role=role, state=state) for case_id, role, state in controls
    ]
    _ArbitraryMapping.touched = 0
    try:
        preflight_proteoform_identity_lineage_authorization(_ArbitraryMapping())
    except ProteoformIdentityLineageAuthorizationError:
        checks.append(
            _scenario(
                "arbitrary_mapping_denied_zero_traversal",
                passed=_ArbitraryMapping.touched == 0,
                detail=f"authorization_rejected;mapping_traversals={_ArbitraryMapping.touched}",
            )
        )
    else:
        checks.append(
            _scenario(
                "arbitrary_mapping_denied_zero_traversal",
                passed=False,
                detail="arbitrary mapping unexpectedly accepted",
            )
        )
    checks.extend(
        [
            _firewall_check(),
            _duplicate_json_check(),
            _rejected_request(
                "unknown_field_rejected",
                lambda payload: payload.__setitem__("unknown_field", "unexpected"),
            ),
            _rejected_request(
                "scalar_coercion_rejected",
                lambda payload: cast("dict[str, Any]", payload["policy"]).__setitem__(
                    "max_artifact_claims", "16"
                ),
            ),
            _maximum_shape_check(),
        ]
    )

    def first_excess_claim(payload: dict[str, Any]) -> None:
        claims = cast("list[dict[str, Any]]", payload["artifact_claims"])
        extra = copy.deepcopy(claims[0])
        extra["claim_id"] = _oid("claim", "first-excess")
        cast("dict[str, Any]", extra["artifact"])["artifact_id"] = _oid("evidence", "first-excess")
        cast("dict[str, Any]", extra["artifact"])["digest"] = sha256_digest(
            {"m0402": "first-excess"}
        )
        claims.append(extra)
        derivation = cast("list[dict[str, Any]]", payload["derivations"])[0]
        cast("list[str]", derivation["source_claim_ids"]).append(extra["claim_id"])

    def first_excess_method(payload: dict[str, Any]) -> None:
        policy = cast("dict[str, Any]", payload["policy"])
        methods = cast("list[dict[str, Any]]", policy["approved_derivation_methods"])
        extra = copy.deepcopy(methods[0])
        extra["method_id"] = _oid("method", "first-excess")
        extra["version"] = "1.0.64"
        evidence = cast("dict[str, Any]", extra["evidence"])
        evidence["artifact_id"] = _oid("evidence", "method-first-excess")
        evidence["digest"] = sha256_digest({"m0402": "method-first-excess"})
        methods.append(extra)

    def first_excess_subject(payload: dict[str, Any]) -> None:
        claim = cast("list[dict[str, Any]]", payload["artifact_claims"])[0]
        claim["declared_subject_component_ids"] = [
            sha256_digest({"m0402_subject": index}) for index in range(257)
        ]

    def mutation_rejects(
        base: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> bool:
        payload = build_scenario_request(base).model_dump(mode="json", exclude_none=False)
        mutate(payload)
        try:
            _strict_request(payload)
        except (ValidationError, ValueError):
            return True
        return False

    first_excesses = (
        mutation_rejects("maximum_shape_accepted", first_excess_claim),
        mutation_rejects("maximum_shape_accepted", first_excess_method),
        mutation_rejects("canonical_all_seven_entity_chain", first_excess_subject),
    )
    checks.append(
        _scenario(
            "first_excess_rejected",
            passed=all(first_excesses),
            detail=(f"rejected_claim_source_method_subject_caps={sum(first_excesses)}/3"),
        )
    )
    oversized = b"{}" + (b" " * (M0402_MAX_CANONICAL_REQUEST_BYTES - 1))
    try:
        M0402Plugin(M0402Service()).validate(oversized)
    except StrictJsonError as error:
        checks.append(
            _scenario(
                "request_4mib_plus_one_rejected",
                passed=error.code.value == "json_too_large",
                detail=f"validation_rejected:{error.code.value};bytes={len(oversized)}",
            )
        )
    else:
        checks.append(
            _scenario(
                "request_4mib_plus_one_rejected",
                passed=False,
                detail="oversized request unexpectedly accepted",
            )
        )
    checks.extend(
        [
            _semantic_reorder_check(),
            _privacy_check(),
            _rejected_result(
                "stale_result_digest_rejected",
                _result(),
                lambda payload: payload.__setitem__(
                    "result_digest", sha256_digest({"m0402": "stale-result"})
                ),
                recompute_outer=False,
            ),
            _forgery_check(),
            _authority_ceiling_check(),
        ]
    )
    return checks


def run_evaluation() -> dict[str, object]:
    """Execute every locked case through a substantive public-boundary oracle."""

    corpus = _corpus()
    checks = _inventory_checks(corpus)
    declared = [case for group in corpus["scenario_groups"] for case in group["case_ids"]]
    groups = (
        _canonical_checks(),
        _swap_checks(),
        _collision_checks(),
        _cross_patient_checks(),
        _malformed_shape_checks(),
        _upstream_drift_checks(),
        _evidence_authority_checks(),
        _strict_boundary_checks(),
    )
    scenario_checks = [check for group in groups for check in group]
    checks.extend(scenario_checks)
    executed = [check.name.removeprefix("scenario.") for check in scenario_checks]
    missing = sorted(set(declared) - set(executed))
    extra = sorted(set(executed) - set(declared))
    duplicated = sorted(case_id for case_id in set(executed) if executed.count(case_id) != 1)
    checks.append(
        EvalCheck(
            "corpus.executable_coverage",
            not missing
            and not extra
            and not duplicated
            and len(executed) == EXPECTED_CASE_COUNT
            and tuple(len(group) for group in groups) == EXPECTED_ALLOCATION,
            (
                f"declared={len(declared)};executed={len(executed)};"
                f"allocation={tuple(len(group) for group in groups)}"
            ),
        )
    )
    return {
        "module_id": MODULE_ID,
        "passed": all(check.passed for check in checks),
        "phase": "locked_executable_corpus",
        "declared_case_count": len(declared),
        "executed_case_count": len(executed),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
        "duplicated_case_ids": duplicated,
        "checks": [asdict(check) for check in checks],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


__all__ = ["build_scenario_request", "main", "run_evaluation"]


if __name__ == "__main__":
    raise SystemExit(main())
