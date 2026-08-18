"""Genuine deterministic builders for M05-02 identity-lineage reconciliation."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Final, cast

from pydantic import TypeAdapter, ValidationError

from evals.m05_01.run import build_scenario_request as build_m0501_request
from glio_proteogen.contracts.m01_02 import (
    EntityKind,
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m05_01 import (
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.contracts.m05_02 import (
    M0502_CONTRACT_VERSION,
    M0502_MAX_ARTIFACT_CLAIMS,
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    M0502_MAX_DERIVATION_SOURCES,
    ApprovedPtmLocalizationDerivationMethod,
    ApprovedPtmLocalizationLineageConfiguration,
    PtmLocalizationIdentityLineageFindingCode,
    PtmLocalizationIdentityLineagePolicy,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactClaim,
    PtmLocalizationLineageArtifactDerivation,
    PtmLocalizationLineageArtifactRole,
    PtmLocalizationLineageDisposition,
    PtmLocalizationLineageEvidenceState,
    ReconcilePtmLocalizationIdentityLineageRequest,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    contract_json_schemas,
    opaque_ptm_localization_lineage_identifier,
    receipt_digest,
    resolved_graph_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ExecutionContext
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import M0102Service
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    evaluate_ptm_localization_protocol,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    M0502Plugin,
    M0502Service,
    PtmLocalizationIdentityLineageAuthorizationError,
    ValidatedM0502Request,
    reconcile_ptm_localization_identity_lineage,
)

ROOT: Final = Path(__file__).parents[2]
M0102_SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
M0502_SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m05_02" / "scenarios.json"
PROTOCOL_TIME: Final = datetime(2026, 8, 12, 12, tzinfo=UTC)
RECONCILIATION_TIME: Final = datetime(2026, 8, 13, 12, tzinfo=UTC)
M0502_SCHEMA_COUNT: Final = 9
M0502_GROUP_COUNT: Final = 8
M0502_CASE_COUNT: Final = 70
POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-02.policy+json"
CONFIGURATION_MEDIA_TYPE: Final = (
    "application/vnd.glio-proteogen.m05-02.approved-configuration+json"
)
DERIVATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-02.derivation+json"
ROLE_MEDIA_TYPES: Final = {
    PtmLocalizationLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.mass-spectrometry-proteome-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.GENOME_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.genome-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.TRANSCRIPTOME_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.transcriptome-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.PTM_ANNOTATION_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.ptm-annotation-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.VARIANT_PEPTIDE_INPUT_BUNDLE: (
        "application/vnd.glio-proteogen.m05-02.variant-peptide-input-bundle+json"
    ),
}
_M0102_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileIdentityLineageRequest)


class _MissingIdentityFixtureError(ValueError):
    def __init__(self) -> None:
        super().__init__("M01-02 canonical identity fixture is missing")


class _UnknownScenarioError(ValueError):
    def __init__(self) -> None:
        super().__init__("unknown M05-02 scenario")


class _InvalidFixtureIdentityError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-02 locked fixture identity is inconsistent")


class _InvalidFixtureShapeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-02 fixture requires exactly eight groups and seventy cases")


class _DuplicateFixtureCaseError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-02 fixture case identifiers must be unique")


def _oid(namespace: str, label: object) -> str:
    value = f"{namespace}.{sha256_digest({'m0502': label}).removeprefix('sha256:')}"
    return opaque_ptm_localization_lineage_identifier(cast("Any", namespace), value)


def _artifact(label: str, *, media_type: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0502_evidence": label}),
        media_type=media_type,
    )


def _replace[T](model: T, **updates: object) -> T:
    model_type = type(model)
    payload = model.model_dump(mode="python", exclude_none=False)  # type: ignore[attr-defined]
    payload.update(updates)
    return model_type.model_validate(payload, strict=True)  # type: ignore[attr-defined,no-any-return]


def _m0102_payload(case_id: str = "complete_ordinary_lineage") -> dict[str, Any]:
    corpus = cast("dict[str, Any]", strict_json_loads(M0102_SCENARIO_PATH.read_bytes()))
    for scenario in cast("list[dict[str, Any]]", corpus["scenarios"]):
        if scenario["case_id"] == case_id:
            return copy.deepcopy(cast("dict[str, Any]", scenario["request"]))
    raise _MissingIdentityFixtureError


def _two_patient_lineage_payload() -> dict[str, Any]:
    payload = _m0102_payload()
    payload["context"]["request_id"] = "request.synthetic.m0502_two_patient_lineage"
    entities = cast("list[dict[str, Any]]", payload["entities"])
    operations = cast("list[dict[str, Any]]", payload["lineage_operations"])
    for entity in copy.deepcopy(entities):
        entity["entity_id"] = cast("str", entity["entity_id"]).replace("-a", "-b")
        for evidence in cast("list[dict[str, Any]]", entity["evidence"]):
            evidence["artifact_id"] = "artifact.synthetic.entity.b"
            evidence["digest"] = "sha256:" + ("b" * 64)
        entities.append(entity)
    for index, operation in enumerate(copy.deepcopy(operations), start=7):
        operation["operation_id"] = f"op-{index:02d}"
        operation["source_entity_ids"] = [
            item.replace("-a", "-b") for item in cast("list[str]", operation["source_entity_ids"])
        ]
        operation["target_entity_ids"] = [
            item.replace("-a", "-b") for item in cast("list[str]", operation["target_entity_ids"])
        ]
        for evidence in cast("list[dict[str, Any]]", operation["evidence"]):
            evidence["artifact_id"] = "artifact.synthetic.operation.b"
            evidence["digest"] = "sha256:" + ("d" * 64)
        operations.append(operation)
    return payload


@lru_cache(maxsize=4)
def _genuine_identity_resolution(
    case_id: str = "complete_ordinary_lineage",
) -> IdentityLineageResolution:
    payload = (
        _two_patient_lineage_payload()
        if case_id == "two_patient_lineage"
        else _m0102_payload(case_id)
    )
    request = _M0102_REQUEST_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
    with TemporaryDirectory(prefix="m0502-m0102-") as temporary:
        store = M0102EventStore(Path(temporary) / "identity.sqlite3")
        with M0102Service(store) as service:
            return service.execute(request)


def _genuine_protocol_result(
    identity: IdentityLineageResolution,
    *,
    scenario: str,
) -> PtmLocalizationProtocolConformanceResult:
    m0501_scenario = (
        "compatibility_failure_quarantined"
        if scenario == "upstream_protocol_quarantined"
        else "canonical_conformant"
    )
    payload = build_m0501_request(m0501_scenario).model_dump(mode="python", exclude_none=False)
    payload["context"]["occurred_at"] = PROTOCOL_TIME
    payload["context"]["references"]["identity_lineage"]["binding_digest"] = (
        identity.resolution_digest
    )
    request = EvaluatePtmLocalizationProtocolRequest.model_validate(payload, strict=True)
    return evaluate_ptm_localization_protocol(request)


def _policy(
    protocol: PtmLocalizationProtocolConformanceResult,
    *,
    approve_configuration: bool,
    maximum: bool = False,
) -> PtmLocalizationIdentityLineagePolicy:
    approved_configuration = ApprovedPtmLocalizationLineageConfiguration(
        configuration_id=_oid("configuration", "canonical"),
        protocol_result_version=protocol.result_version,
        configuration_digest=(
            protocol.configuration_digest
            if approve_configuration
            else sha256_digest({"unsupported": protocol.configuration_digest})
        ),
        reference_bundle_digest=protocol.receipt.reference_bundle_digest,
        assay_specimen_policy_digest=protocol.receipt.assay_specimen_policy_digest,
        evidence=_artifact("approved-configuration", media_type=CONFIGURATION_MEDIA_TYPE),
    )
    method = ApprovedPtmLocalizationDerivationMethod(
        method_id=_oid("method", "deterministic-lineage"),
        version="1.0.0",
        evidence=_artifact("method", media_type=DERIVATION_MEDIA_TYPE),
    )
    return PtmLocalizationIdentityLineagePolicy(
        policy_id=_oid("policy", "canonical"),
        version="1.0.0",
        max_artifact_claims=M0502_MAX_ARTIFACT_CLAIMS if maximum else 16,
        max_derivation_sources=M0502_MAX_DERIVATION_SOURCES if maximum else 15,
        approved_configurations=(approved_configuration,),
        approved_derivation_methods=(method,),
        evidence=_artifact("policy", media_type=POLICY_MEDIA_TYPE),
        reviewed_by=_oid("reviewer", "synthetic"),
        reviewed_at=PROTOCOL_TIME,
    )


def _anchor_subjects(
    identity: IdentityLineageResolution,
    entity_id: str = "obj-a",
) -> tuple[str, ...]:
    return next(
        node.subject_component_ids for node in identity.graph.nodes if node.entity_id == entity_id
    )


def _claims(
    identity: IdentityLineageResolution,
    protocol: PtmLocalizationProtocolConformanceResult,
    *,
    count: int = 5,
) -> tuple[PtmLocalizationLineageArtifactClaim, ...]:
    source_roles = tuple(
        role
        for role in PtmLocalizationLineageArtifactRole
        if role is not PtmLocalizationLineageArtifactRole.VARIANT_PEPTIDE_INPUT_BUNDLE
    )
    source_count = count - 1
    roles = (
        *(source_roles[index % len(source_roles)] for index in range(source_count)),
        PtmLocalizationLineageArtifactRole.VARIANT_PEPTIDE_INPUT_BUNDLE,
    )
    return tuple(
        PtmLocalizationLineageArtifactClaim(
            claim_id=_oid("claim", f"{index}:{role.value}"),
            role=role,
            artifact=_artifact(f"{index}:{role.value}", media_type=ROLE_MEDIA_TYPES[role]),
            identity_entity_id="obj-a",
            declared_subject_component_ids=_anchor_subjects(identity),
            producer_identity_resolution_digest=identity.resolution_digest,
            producer_protocol_result_digest=protocol.result_digest,
            producer_reference_bundle_digest=protocol.receipt.reference_bundle_digest,
            producer_configuration_digest=protocol.configuration_digest,
            producer_assay_specimen_policy_digest=(protocol.receipt.assay_specimen_policy_digest),
            evidence_state=PtmLocalizationLineageEvidenceState.OBSERVED,
        )
        for index, role in enumerate(roles)
    )


def _mutate_claims_for_scenario(  # noqa: C901 - closed scenario mutation matrix.
    claims: tuple[PtmLocalizationLineageArtifactClaim, ...],
    identity: IdentityLineageResolution,
    scenario: str,
) -> tuple[PtmLocalizationLineageArtifactClaim, ...]:
    mutable = list(claims)
    if scenario == "identity_swap_quarantined":
        mutable[0] = _replace(
            mutable[0],
            declared_subject_component_ids=(sha256_digest({"other_patient": True}),),
        )
    elif scenario == "two_patient_cross_link_quarantined":
        for index in range(1, len(mutable) - 1, 2):
            mutable[index] = _replace(
                mutable[index],
                identity_entity_id="obj-b",
                declared_subject_component_ids=_anchor_subjects(identity, "obj-b"),
            )
    elif scenario == "duplicate_content_recorded":
        mutable[2] = _replace(
            mutable[2],
            artifact=_replace(mutable[2].artifact, digest=mutable[1].artifact.digest),
        )
    elif scenario == "artifact_identity_collision_quarantined":
        mutable[2] = _replace(
            mutable[2],
            artifact=_replace(mutable[2].artifact, artifact_id=mutable[1].artifact.artifact_id),
        )
    elif scenario == "binding_scope_collision_quarantined":
        original = mutable[0]
        duplicate = _replace(
            original,
            claim_id=_oid("claim", "binding-scope-collision"),
            artifact=_artifact(
                "binding-scope-collision",
                media_type=ROLE_MEDIA_TYPES[original.role],
            ),
        )
        mutable.insert(-1, duplicate)
    elif scenario == "producer_identity_drift_quarantined":
        mutable[0] = _replace(
            mutable[0], producer_identity_resolution_digest=sha256_digest({"drift": "identity"})
        )
    elif scenario == "producer_protocol_drift_quarantined":
        mutable[0] = _replace(
            mutable[0], producer_protocol_result_digest=sha256_digest({"drift": "protocol"})
        )
    elif scenario == "producer_reference_drift_quarantined":
        mutable[0] = _replace(
            mutable[0], producer_reference_bundle_digest=sha256_digest({"drift": "reference"})
        )
    elif scenario == "producer_configuration_drift_quarantined":
        mutable[0] = _replace(
            mutable[0], producer_configuration_digest=sha256_digest({"drift": "configuration"})
        )
    elif scenario == "producer_assay_policy_drift_quarantined":
        mutable[0] = _replace(
            mutable[0],
            producer_assay_specimen_policy_digest=sha256_digest({"drift": "assay_policy"}),
        )
    elif scenario.startswith("evidence_"):
        state = PtmLocalizationLineageEvidenceState(
            scenario.removeprefix("evidence_").removesuffix("_abstained")
        )
        mutable[0] = _replace(mutable[0], evidence_state=state)
    return tuple(mutable)


def _derivation(
    claims: tuple[PtmLocalizationLineageArtifactClaim, ...],
    policy: PtmLocalizationIdentityLineagePolicy,
) -> PtmLocalizationLineageArtifactDerivation:
    target = next(
        item
        for item in claims
        if item.role is PtmLocalizationLineageArtifactRole.VARIANT_PEPTIDE_INPUT_BUNDLE
    )
    method = policy.approved_derivation_methods[0]
    return PtmLocalizationLineageArtifactDerivation(
        derivation_id=_oid("derivation", "variant-peptide"),
        source_claim_ids=tuple(item.claim_id for item in claims if item is not target),
        target_claim_id=target.claim_id,
        method_id=method.method_id,
        method_version=method.version,
        evidence=_artifact("derivation", media_type=DERIVATION_MEDIA_TYPE),
    )


def _context(
    protocol: PtmLocalizationProtocolConformanceResult,
    identity: IdentityLineageResolution,
    policy: PtmLocalizationIdentityLineagePolicy,
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
    return base.model_copy(update={"occurred_at": RECONCILIATION_TIME, "references": references})


def build_scenario_request(
    scenario: str = "canonical_reconciled",
) -> ReconcilePtmLocalizationIdentityLineageRequest:
    """Build one genuine strict M05-02 request through public upstream operations."""

    supported_scenarios = {
        "canonical_reconciled",
        "maximum_admitted_shape_quarantined",
        "superseding_recovery_reconciled",
        "unsupported_configuration_abstained",
        "upstream_protocol_quarantined",
        "upstream_identity_unresolved",
        "identity_swap_quarantined",
        "two_patient_cross_link_quarantined",
        "duplicate_content_recorded",
        "artifact_identity_collision_quarantined",
        "binding_scope_collision_quarantined",
        "producer_identity_drift_quarantined",
        "producer_protocol_drift_quarantined",
        "producer_reference_drift_quarantined",
        "producer_configuration_drift_quarantined",
        "producer_assay_policy_drift_quarantined",
        "evidence_missing_abstained",
        "evidence_indeterminate_abstained",
        "evidence_unsupported_abstained",
        "evidence_redacted_abstained",
    }
    if scenario not in supported_scenarios:
        raise _UnknownScenarioError
    identity_case = (
        "poisoned_bridge_atomic_quarantine"
        if scenario == "upstream_identity_unresolved"
        else "two_patient_lineage"
        if scenario == "two_patient_cross_link_quarantined"
        else "complete_ordinary_lineage"
    )
    identity = _genuine_identity_resolution(identity_case)
    protocol = _genuine_protocol_result(identity, scenario=scenario)
    maximum = scenario == "maximum_admitted_shape_quarantined"
    policy = _policy(
        protocol,
        approve_configuration=scenario != "unsupported_configuration_abstained",
        maximum=maximum,
    )
    traversable = (
        identity.decision.value == "resolved"
        and protocol.disposition.value == "conformant"
        and scenario != "unsupported_configuration_abstained"
    )
    claims = (
        _mutate_claims_for_scenario(
            _claims(
                identity,
                protocol,
                count=M0502_MAX_ARTIFACT_CLAIMS if maximum else 5,
            ),
            identity,
            scenario,
        )
        if traversable
        else ()
    )
    derivations = (_derivation(claims, policy),) if traversable else ()
    context = _context(protocol, identity, policy)
    return ReconcilePtmLocalizationIdentityLineageRequest(
        request_id=context.request_id,
        context=context,
        identity_resolution=identity,
        protocol_result=protocol,
        policy=policy,
        artifact_claims=claims,
        derivations=derivations,
        supersedes_result_digest=(
            sha256_digest({"superseded": "m0502"})
            if scenario == "superseding_recovery_reconciled"
            else None
        ),
    )


def build_scenario_result(
    scenario: str = "canonical_reconciled",
) -> PtmLocalizationIdentityLineageResolution:
    """Execute one genuine M05-02 scenario through the public operation."""

    return reconcile_ptm_localization_identity_lineage(build_scenario_request(scenario))


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    declared_groups: int
    group_case_counts: dict[str, int]
    declared_cases: int
    executed_cases: int
    passed_cases: int
    failed_cases: tuple[str, ...]
    passed: bool


class _TraversalCanary:
    def __iter__(self) -> object:
        raise AssertionError


def _request_rejected(payload: object) -> bool:
    try:
        ReconcilePtmLocalizationIdentityLineageRequest.model_validate(payload, strict=True)
    except ValidationError:
        return True
    return False


def _result_rejected(payload: object) -> bool:
    try:
        PtmLocalizationIdentityLineageResolution.model_validate(payload, strict=True)
    except ValidationError:
        return True
    return False


def _authorization_denied(control: str, state: str) -> bool:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][control]["state"] = state
    try:
        reconcile_ptm_localization_identity_lineage(payload)
    except PtmLocalizationIdentityLineageAuthorizationError:
        return True
    return False


def _semantic_reorder_is_equal() -> bool:
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    payload["artifact_claims"].reverse()
    payload["derivations"][0]["source_claim_ids"].reverse()
    payload["policy"]["approved_configurations"].reverse()
    payload["policy"]["approved_derivation_methods"].reverse()
    reordered = ReconcilePtmLocalizationIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    return reconcile_ptm_localization_identity_lineage(
        request
    ) == reconcile_ptm_localization_identity_lineage(reordered)


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            *(str(key) for key in value),
            *(nested for item in value.values() for nested in _nested_keys(item)),
        }
    if isinstance(value, list | tuple):
        return {nested for item in value for nested in _nested_keys(item)}
    return set()


def _scenario_has(
    scenario: str,
    disposition: PtmLocalizationLineageDisposition,
    *codes: PtmLocalizationIdentityLineageFindingCode,
) -> bool:
    result = build_scenario_result(scenario)
    observed = {finding.code for finding in result.findings}
    return result.disposition is disposition and set(codes).issubset(observed)


def _request_mutation(case_id: str) -> bool:  # noqa: C901, PLR0912 - closed fixture matrix.
    payload = build_scenario_request().model_dump(mode="python")
    claims = payload["artifact_claims"]
    derivation = payload["derivations"][0]
    if case_id == "unknown_field_rejected":
        payload["unknown"] = True
    elif case_id == "scalar_coercion_rejected":
        payload["contract_version"] = 1
    elif case_id == "request_context_id_mismatch_rejected":
        payload["request_id"] = _oid("request", "mismatch")
    elif case_id == "policy_chronology_rejected":
        payload["policy"]["reviewed_at"] = RECONCILIATION_TIME + timedelta(days=1)
    elif case_id == "quality_result_binding_rejected":
        payload["context"]["references"]["quality"]["evidence"]["digest"] = sha256_digest(
            {"stale": "quality"}
        )
    elif case_id == "intended_use_binding_rejected":
        payload["context"]["references"]["intended_use"]["evidence"]["digest"] = sha256_digest(
            {"stale": "intended_use"}
        )
    elif case_id == "policy_configuration_binding_rejected":
        payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            sha256_digest({"stale": "policy"})
        )
    elif case_id == "minimum_claim_shape_rejected":
        payload["artifact_claims"] = claims[:-1]
    elif case_id == "missing_derivation_rejected":
        payload["derivations"] = ()
    elif case_id == "duplicate_claim_identifier_rejected":
        claims[1]["claim_id"] = claims[0]["claim_id"]
    elif case_id == "duplicate_derivation_source_rejected":
        derivation["source_claim_ids"] = (
            derivation["source_claim_ids"][0],
            derivation["source_claim_ids"][0],
            *derivation["source_claim_ids"][2:],
        )
    elif case_id == "unknown_identity_anchor_rejected":
        claims[0]["identity_entity_id"] = "missing-entity"
    elif case_id == "nonderived_identity_anchor_rejected":
        claims[0]["identity_entity_id"] = "pat-a"
    elif case_id == "unknown_derivation_claim_rejected":
        derivation["source_claim_ids"] = (
            _oid("claim", "unknown"),
            *derivation["source_claim_ids"][1:],
        )
    elif case_id == "unapproved_derivation_method_rejected":
        derivation["method_id"] = _oid("method", "unapproved")
    elif case_id == "wrong_derivation_target_rejected":
        derivation["target_claim_id"] = derivation["source_claim_ids"][0]
    else:
        return False
    return _request_rejected(payload)


def _result_mutation(case_id: str) -> bool:
    scenario = "identity_swap_quarantined" if case_id == "finding_forgery_rejected" else None
    payload = build_scenario_result(scenario or "canonical_reconciled").model_dump(mode="python")
    if case_id == "result_digest_forgery_rejected":
        payload["result_digest"] = sha256_digest({"forged": "result"})
    elif case_id == "finding_forgery_rejected":
        payload["findings"][0]["evidence_basis_digest"] = sha256_digest({"forged": "finding"})
        payload["result_digest"] = result_payload_digest(payload)
    elif case_id == "receipt_forgery_rejected":
        payload["receipt"]["protocol_result_digest"] = sha256_digest({"forged": "receipt"})
        payload["receipt"]["receipt_digest"] = receipt_digest(payload["receipt"])
        payload["result_digest"] = result_payload_digest(payload)
    elif case_id == "graph_forgery_rejected":
        payload["graph"]["artifacts"][0]["resolved_subject_component_ids"] = ()
        payload["graph"]["graph_digest"] = resolved_graph_digest(payload["graph"])
        payload["graph_digest"] = payload["graph"]["graph_digest"]
        payload["result_digest"] = result_payload_digest(payload)
    elif case_id == "provenance_forgery_rejected":
        payload["provenance"]["model_version"] = "9.9.9"
        payload["result_digest"] = result_payload_digest(payload)
    else:
        return False
    return _result_rejected(payload)


def _case_succeeds(case_id: str) -> bool:  # noqa: C901, PLR0911, PLR0912, PLR0915
    scenario_cases = {
        "canonical_reconciled": (
            "canonical_reconciled",
            PtmLocalizationLineageDisposition.RECONCILED,
            (),
        ),
        "upstream_identity_unresolved_abstains": (
            "upstream_identity_unresolved",
            PtmLocalizationLineageDisposition.ABSTAINED,
            (PtmLocalizationIdentityLineageFindingCode.UPSTREAM_IDENTITY_UNRESOLVED,),
        ),
        "two_patient_cross_link_quarantined": (
            "two_patient_cross_link_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.CROSS_PATIENT_LINK,),
        ),
        "identity_swap_quarantined": (
            "identity_swap_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.IDENTITY_SWAP,),
        ),
        "duplicate_content_retained": (
            "duplicate_content_recorded",
            PtmLocalizationLineageDisposition.RECONCILED,
            (PtmLocalizationIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED,),
        ),
        "artifact_identity_collision_quarantined": (
            "artifact_identity_collision_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.ARTIFACT_IDENTITY_COLLISION,),
        ),
        "binding_scope_collision_quarantined": (
            "binding_scope_collision_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.BINDING_SCOPE_COLLISION,),
        ),
        "artifact_lineage_collision_quarantined": (
            "two_patient_cross_link_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION,),
        ),
        "producer_identity_drift_quarantined": (
            "producer_identity_drift_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.PRODUCER_IDENTITY_DRIFT,),
        ),
        "producer_protocol_drift_quarantined": (
            "producer_protocol_drift_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.PRODUCER_PROTOCOL_DRIFT,),
        ),
        "producer_reference_bundle_drift_quarantined": (
            "producer_reference_drift_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.PRODUCER_REFERENCE_BUNDLE_DRIFT,),
        ),
        "producer_configuration_drift_quarantined": (
            "producer_configuration_drift_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.PRODUCER_CONFIGURATION_DRIFT,),
        ),
        "producer_assay_policy_drift_quarantined": (
            "producer_assay_policy_drift_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.PRODUCER_ASSAY_SPECIMEN_POLICY_DRIFT,),
        ),
        "unsupported_configuration_abstains": (
            "unsupported_configuration_abstained",
            PtmLocalizationLineageDisposition.ABSTAINED,
            (PtmLocalizationIdentityLineageFindingCode.UPSTREAM_CONFIGURATION_UNSUPPORTED,),
        ),
        "upstream_protocol_quarantines": (
            "upstream_protocol_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            (PtmLocalizationIdentityLineageFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT,),
        ),
        "evidence_missing_abstains": (
            "evidence_missing_abstained",
            PtmLocalizationLineageDisposition.ABSTAINED,
            (PtmLocalizationIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,),
        ),
        "evidence_indeterminate_abstains": (
            "evidence_indeterminate_abstained",
            PtmLocalizationLineageDisposition.ABSTAINED,
            (PtmLocalizationIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,),
        ),
        "evidence_unsupported_abstains": (
            "evidence_unsupported_abstained",
            PtmLocalizationLineageDisposition.ABSTAINED,
            (PtmLocalizationIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,),
        ),
        "evidence_redacted_abstains": (
            "evidence_redacted_abstained",
            PtmLocalizationLineageDisposition.ABSTAINED,
            (PtmLocalizationIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,),
        ),
    }
    if case_id in scenario_cases:
        scenario, disposition, codes = scenario_cases[case_id]
        return _scenario_has(scenario, disposition, *codes)
    if case_id == "all_seven_physical_entity_kinds_preserved":
        result = build_scenario_result()
        return {node.kind for node in result.request.identity_resolution.graph.nodes} == set(
            EntityKind
        )
    if case_id == "exact_identity_resolution_embedded":
        request = build_scenario_request()
        result = reconcile_ptm_localization_identity_lineage(request)
        return result.request.identity_resolution == request.identity_resolution
    if case_id == "physical_graph_digest_bound":
        result = build_scenario_result()
        return (
            result.graph.physical_graph_digest
            == result.request.identity_resolution.graph.graph_digest
        )
    if case_id == "exact_subject_propagation":
        result = build_scenario_result()
        expected = _anchor_subjects(result.request.identity_resolution)
        return all(
            item.resolved_subject_component_ids == expected for item in result.graph.artifacts
        )
    if case_id == "immutable_resolution_roundtrip":
        result = build_scenario_result()
        return (
            PtmLocalizationIdentityLineageResolution.model_validate_json(
                result.model_dump_json(), strict=True
            )
            == result
        )
    if case_id == "missing_not_negative":
        result = build_scenario_result("evidence_missing_abstained")
        return result.disposition is PtmLocalizationLineageDisposition.ABSTAINED and all(
            finding.action.value != "record" for finding in result.findings
        )
    if case_id == "unsupported_not_negative":
        result = build_scenario_result("evidence_unsupported_abstained")
        return result.disposition is PtmLocalizationLineageDisposition.ABSTAINED and (
            result.support.status.value == "unsupported"
        )
    if case_id == "quarantine_precedes_abstain":
        result = build_scenario_result("two_patient_cross_link_quarantined")
        return result.disposition is PtmLocalizationLineageDisposition.QUARANTINED
    denial = {
        "configuration_control_denied": ("approved_configuration", "rejected"),
        "identity_control_denied": ("identity_lineage", "unresolved"),
        "provenance_control_denied": ("provenance", "rejected"),
        "consent_control_denied": ("consent", "withheld"),
        "quality_control_denied": ("quality", "rejected"),
        "support_control_denied": ("support", "rejected"),
        "intended_use_control_denied": ("intended_use", "rejected"),
    }
    if case_id in denial:
        return _authorization_denied(*denial[case_id])
    if case_id == "authorization_before_claim_traversal":
        payload = build_scenario_request().model_dump(mode="python")
        payload["context"]["references"]["consent"]["state"] = "withheld"
        payload["artifact_claims"] = _TraversalCanary()
        try:
            reconcile_ptm_localization_identity_lineage(payload)
        except PtmLocalizationIdentityLineageAuthorizationError:
            return True
        return False
    if case_id == "authorization_error_sanitized":
        payload = build_scenario_request().model_dump(mode="python")
        payload["context"]["references"]["quality"]["state"] = "rejected"
        try:
            reconcile_ptm_localization_identity_lineage(payload)
        except PtmLocalizationIdentityLineageAuthorizationError as error:
            return str(error) == (
                "PTM-localization identity-lineage reconciliation requires accepted upstream "
                "controls"
            )
        return False
    if case_id == "duplicate_json_rejected":
        serialized = (
            build_scenario_request()
            .model_dump_json()
            .replace(
                '"operation":"reconcile_ptm_localization_identity_lineage"',
                (
                    '"operation":"reconcile_ptm_localization_identity_lineage",'
                    '"operation":"reconcile_ptm_localization_identity_lineage"'
                ),
                1,
            )
        )
        try:
            M0502Plugin(M0502Service()).validate(serialized)
        except ValueError:
            return True
        return False
    if case_id == "nine_schemas_closed":
        return len(contract_json_schemas()) == M0502_SCHEMA_COUNT
    if _request_mutation(case_id):
        return True
    if case_id in {
        "result_digest_forgery_rejected",
        "finding_forgery_rejected",
        "receipt_forgery_rejected",
        "graph_forgery_rejected",
        "provenance_forgery_rejected",
    }:
        return _result_mutation(case_id)
    if case_id == "deterministic_result_equality":
        request = build_scenario_request()
        return reconcile_ptm_localization_identity_lineage(
            request
        ) == reconcile_ptm_localization_identity_lineage(request)
    if case_id == "semantic_reorder_equality":
        return _semantic_reorder_is_equal()
    if case_id == "biological_canary_absent":
        rendered = build_scenario_result().model_dump_json()
        return all(
            canary not in rendered
            for canary in ("MPEPTIDEK", "P12345", "EGFRvIII", "patient-raw-001")
        )
    if case_id == "raw_payload_fields_absent":
        keys = _nested_keys(build_scenario_result().model_dump(mode="json"))
        return not {"spectrum", "sequence", "abundance", "treatment"}.intersection(keys)
    if case_id == "uncertainty_support_domain_narrowed":
        result = build_scenario_result()
        estimates = (
            result.uncertainty.measurement,
            result.uncertainty.sampling,
            result.uncertainty.parameter,
            result.uncertainty.model_form,
            result.uncertainty.identification,
            result.uncertainty.support,
            result.uncertainty.transport,
        )
        return all(
            estimate.state.value == "not_estimable" and estimate.probability is None
            for estimate in estimates
        ) and any("narrowed" in note for note in result.uncertainty.sensitivity_notes)
    if case_id == "authority_flags_all_false":
        result = build_scenario_result()
        return not any(
            (
                result.emits_variant_peptide,
                result.emits_proteogenomic_state,
                result.emits_proteotype,
                result.emits_protein_level_subtype,
                result.infers_identity,
                result.infers_consent,
                result.infers_protein,
                result.infers_ptm_localization,
                result.infers_kinase_activity,
                result.performs_cn_to_protein_regression,
                result.performs_all_omics_fusion,
                result.recommends_treatment,
                result.mutates_upstream,
            )
        )
    if case_id == "variant_peptide_parent_context_only":
        result = build_scenario_result()
        return result.parent_target == "variant_peptide" and not result.emits_variant_peptide
    if case_id == "superseding_recovery_is_append_only":
        request = build_scenario_request("superseding_recovery_reconciled")
        result = reconcile_ptm_localization_identity_lineage(request)
        return (
            request.supersedes_result_digest is not None
            and request.supersedes_result_digest in result.provenance.input_digests
        )
    if case_id == "plugin_public_parity":
        request = build_scenario_request()
        plugin = M0502Plugin(M0502Service())
        return plugin.run(plugin.validate(canonical_json_bytes(request))) == build_scenario_result()
    if case_id == "copied_token_forgery_rejected":
        plugin = M0502Plugin(M0502Service())
        token = plugin.validate(build_scenario_request())
        forged = ValidatedM0502Request(token.request.model_copy(deep=True), token._seal)
        try:
            plugin.run(forged)
        except TypeError:
            return True
        return False
    if case_id == "strict_json_roundtrip":
        request = build_scenario_request()
        return (
            ReconcilePtmLocalizationIdentityLineageRequest.model_validate_json(
                canonical_json_bytes(request), strict=True
            )
            == request
        )
    if case_id == "maximum_request_within_byte_cap":
        request = build_scenario_request("maximum_admitted_shape_quarantined")
        result = reconcile_ptm_localization_identity_lineage(request)
        return (
            len(request.artifact_claims) == M0502_MAX_ARTIFACT_CLAIMS
            and len(request.derivations[0].source_claim_ids) == M0502_MAX_DERIVATION_SOURCES
            and len(canonical_json_bytes(request)) <= M0502_MAX_CANONICAL_REQUEST_BYTES
            and len(result.graph.artifacts) == M0502_MAX_ARTIFACT_CLAIMS
        )
    if case_id == "request_digest_is_canonical":
        result = build_scenario_result()
        return result.request_digest == canonical_request_digest(result.request)
    if case_id == "unknown_schema_name_rejected":
        try:
            contract_json_schema("not-a-contract")  # type: ignore[arg-type]
        except KeyError:
            return True
        return False
    return False


def _locked_inventory() -> tuple[dict[str, int], tuple[str, ...]]:
    payload = cast("dict[str, Any]", strict_json_loads(M0502_SCENARIO_PATH.read_bytes()))
    if (
        payload["module_id"] != "GLIO-PROTEOGEN-M05-02"
        or payload["contract_version"] != M0502_CONTRACT_VERSION
    ):
        raise _InvalidFixtureIdentityError
    groups = cast("dict[str, list[str]]", payload["groups"])
    counts = {name: len(cases) for name, cases in groups.items()}
    cases = tuple(case for group in groups.values() for case in group)
    if len(groups) != M0502_GROUP_COUNT or len(cases) != M0502_CASE_COUNT:
        raise _InvalidFixtureShapeError
    if len(set(cases)) != len(cases):
        raise _DuplicateFixtureCaseError
    return counts, cases


def run_evaluation() -> EvaluationReport:
    """Execute every declared M05-02 locked identity case exactly once."""

    group_counts, cases = _locked_inventory()
    failures = tuple(case for case in cases if not _case_succeeds(case))
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M05-02",
        contract_version=M0502_CONTRACT_VERSION,
        declared_groups=len(group_counts),
        group_case_counts=group_counts,
        declared_cases=len(cases),
        executed_cases=len(cases),
        passed_cases=len(cases) - len(failures),
        failed_cases=failures,
        passed=not failures,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = [
    "EvaluationReport",
    "build_scenario_request",
    "build_scenario_result",
    "main",
    "run_evaluation",
]


if __name__ == "__main__":
    raise SystemExit(main())
