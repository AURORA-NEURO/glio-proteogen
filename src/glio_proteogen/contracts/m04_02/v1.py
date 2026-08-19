"""Strict M04-02 proteoform identity-lineage contracts."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, cast

from pydantic import (
    AwareDatetime,
    Field,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m01_02 import (
    EntityKind,
    IdentityLineageResolution,
)
from glio_proteogen.contracts.m04_01 import (
    ProteoformProtocolConformanceResult,
)
from glio_proteogen.contracts.m04_02.canonical import (
    canonical_request_digest,
    configuration_digest,
    normalized_identity_resolution,
    normalized_protocol_result,
    normalized_request,
    physical_lineage_path_digest,
    policy_digest,
    receipt_digest,
    resolved_graph_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonInferenceResultModel,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_02.v1 import ResolvedIdentityNode

M0402_MODULE_ID: Final = "GLIO-PROTEOGEN-M04-02"
M0402_OPERATION: Final = "reconcile_proteoform_identity_lineage"
M0402_PARENT: Final = "protein_rna_discordance"
M0402_CONTRACT_VERSION: Final = "1.0.0"
M0402_PHYSICAL_ENTITY_KIND_COUNT: Final = 7
M0402_ARTIFACT_ROLE_COUNT: Final = 5
M0402_MIN_ARTIFACT_CLAIMS: Final = 5
M0402_MAX_ARTIFACT_CLAIMS: Final = 256
M0402_DERIVATION_COUNT: Final = 1
M0402_MIN_DERIVATION_SOURCES: Final = 4
M0402_MAX_DERIVATION_SOURCES: Final = 255
M0402_MAX_SUBJECT_COMPONENT_IDS: Final = 256
M0402_MAX_APPROVED_METHODS: Final = 64
M0402_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0402_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0402_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0402_LIMITATION_COUNT: Final = 3
M0402_MIN_EVIDENCE: Final = 15
M0402_MAX_EVIDENCE: Final = 329
M0402_FINDING_CODE_COUNT: Final = 14
M0402_MAX_FINDINGS: Final = (
    (8 * M0402_MAX_ARTIFACT_CLAIMS) + (3 * (M0402_MAX_ARTIFACT_CLAIMS // 2)) + 1 + 2
)
_MINIMUM_DUPLICATE_COUNT: Final = 2
M0402_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed M04-02 lineage reconciliation evidence."
)
M0402_RECONCILED_RATIONALE: Final = (
    "The artifact derivation lineage reconciles to one exact governed identity context."
)
M0402_QUARANTINED_RATIONALE: Final = (
    "A lineage discrepancy or reviewed-context mismatch requires quarantine and review."
)
M0402_ABSTAINED_RATIONALE: Final = (
    "Identity or categorical concordance evidence is not evaluable, so reconciliation abstains."
)
M0402_UNCERTAINTY_RATIONALES: Final = (
    "M04-02 consumes categorical lineage evidence and estimates no measurement uncertainty.",
    "M04-02 performs no sampling model.",
    "The deterministic reconciler fits no parameters.",
    "M04-02 executes no learned identity or activity model.",
    "No peptide or protein identity is inferred.",
    "Support is a deterministic lineage-closure decision.",
    "External identity and reference authorities are caller-declared.",
)
M0402_SENSITIVITY_NOTES: Final = (
    "Missing, unsupported, indeterminate, conflicting, or redacted evidence never becomes "
    "negative.",
    "Lineage discrepancies are retained without relabeling, merging, or selecting authority.",
)

_OPAQUE_IDENTIFIER = re.compile(
    r"^(?:request|actor|decision|policy|method|claim|derivation|evidence|reviewer)"
    r"\.[0-9a-f]{64}$"
)
_LOWERCASE_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
_CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-02.policy+json"
_DERIVATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-02.derivation+json"

type ProteoformLineageOpaqueNamespace = Literal[
    "request",
    "actor",
    "decision",
    "policy",
    "method",
    "claim",
    "derivation",
    "evidence",
    "reviewer",
]


def opaque_proteoform_lineage_identifier(
    namespace: ProteoformLineageOpaqueNamespace,
    value: Identifier,
) -> Identifier:
    """Validate one caller-reflected identifier in its exact M04-02 namespace."""

    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"M04-02 {namespace} identifier must be opaque")
    return value


def _validate_artifact(
    value: ArtifactReference,
    *,
    media_type: str,
) -> ArtifactReference:
    opaque_proteoform_lineage_identifier("evidence", value.artifact_id)
    if _LOWERCASE_MEDIA_TYPE.fullmatch(value.media_type) is None or value.media_type != media_type:
        raise ValueError("M04-02 artifact media type is outside its exact role")
    return value


class ProteoformLineageArtifactRole(StrEnum):
    """Closed artifact roles consumed and reconciled by M04-02."""

    MASS_SPECTROMETRY_PROTEOME_MANIFEST = "mass_spectrometry_proteome_manifest"
    GENOME_MANIFEST = "genome_manifest"
    TRANSCRIPTOME_MANIFEST = "transcriptome_manifest"
    PTM_ANNOTATION_MANIFEST = "ptm_annotation_manifest"
    PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE = "protein_rna_discordance_input_bundle"


_ARTIFACT_MEDIA_TYPES: Final = {
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


class ProteoformLineageEvidenceState(StrEnum):
    """Closed categorical evidence states; no state implies biological absence."""

    OBSERVED = "observed"
    MISSING = "missing"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"
    REDACTED = "redacted"


class ProteoformLineageDisposition(StrEnum):
    """Closed release dispositions."""

    RECONCILED = "reconciled"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class ApprovedProteoformDerivationMethod(FrozenModel):
    """One reviewed artifact-derivation method."""

    method_id: Identifier
    version: SemanticVersion
    evidence: ArtifactReference

    @model_validator(mode="after")
    def identifiers_and_evidence_are_owned(self) -> ApprovedProteoformDerivationMethod:
        opaque_proteoform_lineage_identifier("method", self.method_id)
        _validate_artifact(self.evidence, media_type=_DERIVATION_MEDIA_TYPE)
        return self


class ProteoformIdentityLineagePolicy(FrozenModel):
    """Reviewed bounds for one M04-02 reconciliation closure."""

    policy_id: Identifier
    version: SemanticVersion
    max_artifact_claims: int = Field(
        default=M0402_MAX_ARTIFACT_CLAIMS,
        ge=M0402_MIN_ARTIFACT_CLAIMS,
        le=M0402_MAX_ARTIFACT_CLAIMS,
    )
    max_derivation_sources: int = Field(
        default=M0402_MAX_DERIVATION_SOURCES,
        ge=M0402_MIN_DERIVATION_SOURCES,
        le=M0402_MAX_DERIVATION_SOURCES,
    )
    quarantine_on_swap: Literal[True] = True
    quarantine_on_collision: Literal[True] = True
    retain_duplicate_content: Literal[True] = True
    quarantine_on_cross_patient_link: Literal[True] = True
    abstain_on_indeterminate_identity: Literal[True] = True
    require_all_seven_entity_kinds: Literal[True] = True
    approved_derivation_methods: tuple[ApprovedProteoformDerivationMethod, ...] = Field(
        min_length=1,
        max_length=M0402_MAX_APPROVED_METHODS,
    )

    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("approved_derivation_methods")
    @classmethod
    def methods_are_unique(
        cls,
        values: tuple[ApprovedProteoformDerivationMethod, ...],
    ) -> tuple[ApprovedProteoformDerivationMethod, ...]:
        identities = [(item.method_id, item.version) for item in values]
        if len(identities) != len(set(identities)):
            raise ValueError("approved method identities must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def evidence_digests_are_unique(self) -> ProteoformIdentityLineagePolicy:
        artifacts = (
            self.evidence,
            *(item.evidence for item in self.approved_derivation_methods),
        )
        digests = tuple(item.digest for item in artifacts)
        if len(digests) != len(set(digests)):
            raise ValueError("policy evidence digests must be unique")
        identities = tuple((item.artifact_id, item.version) for item in artifacts)
        if len(identities) != len(set(identities)):
            raise ValueError("policy evidence artifact identities must be unique")
        opaque_proteoform_lineage_identifier("policy", self.policy_id)
        opaque_proteoform_lineage_identifier("reviewer", self.reviewed_by)
        _validate_artifact(self.evidence, media_type=_POLICY_MEDIA_TYPE)
        return self


class ProteoformLineageArtifactClaim(FrozenModel):
    """Content-addressed, privacy-minimized node in the handoff DAG."""

    claim_id: Identifier
    role: ProteoformLineageArtifactRole
    artifact: ArtifactReference
    identity_entity_id: Identifier
    declared_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    producer_identity_resolution_digest: Sha256Digest
    producer_protocol_result_digest: Sha256Digest
    producer_reference_bundle_digest: Sha256Digest
    producer_coordinate_policy_digest: Sha256Digest
    evidence_state: ProteoformLineageEvidenceState

    @field_validator("declared_subject_component_ids")
    @classmethod
    def subject_components_are_unique(
        cls,
        values: tuple[Sha256Digest, ...],
    ) -> tuple[Sha256Digest, ...]:
        if len(values) != len(set(values)):
            raise ValueError("declared subject component identifiers must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def claim_identifiers_and_artifact_are_owned(self) -> ProteoformLineageArtifactClaim:
        opaque_proteoform_lineage_identifier("claim", self.claim_id)
        _validate_artifact(self.artifact, media_type=_ARTIFACT_MEDIA_TYPES[self.role])
        return self


class ProteoformLineageArtifactDerivation(FrozenModel):
    """N-to-one derivation whose endpoints must close over submitted claims."""

    derivation_id: Identifier
    source_claim_ids: tuple[Identifier, ...] = Field(
        min_length=M0402_MIN_DERIVATION_SOURCES,
        max_length=M0402_MAX_DERIVATION_SOURCES,
    )
    target_claim_id: Identifier
    method_id: Identifier
    method_version: SemanticVersion
    evidence: ArtifactReference

    @model_validator(mode="after")
    def endpoints_are_unique_and_disjoint(self) -> ProteoformLineageArtifactDerivation:
        if len(self.source_claim_ids) != len(set(self.source_claim_ids)):
            raise ValueError("derivation source claim identifiers must be unique")
        if self.target_claim_id in self.source_claim_ids:
            raise ValueError("a derivation cannot consume its target claim")
        opaque_proteoform_lineage_identifier("derivation", self.derivation_id)
        opaque_proteoform_lineage_identifier("method", self.method_id)
        _validate_artifact(self.evidence, media_type=_DERIVATION_MEDIA_TYPE)
        object.__setattr__(self, "source_claim_ids", tuple(sorted(self.source_claim_ids)))
        return self


class ReconcileProteoformIdentityLineageRequest(FrozenModel):
    """One exact, authorized proteoform lineage closure request."""

    operation: Literal["reconcile_proteoform_identity_lineage"] = M0402_OPERATION
    contract_version: Literal["1.0.0"] = M0402_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    identity_resolution: IdentityLineageResolution
    protocol_result: ProteoformProtocolConformanceResult
    policy: ProteoformIdentityLineagePolicy
    artifact_claims: tuple[ProteoformLineageArtifactClaim, ...] = Field(
        min_length=M0402_MIN_ARTIFACT_CLAIMS,
        max_length=M0402_MAX_ARTIFACT_CLAIMS,
    )
    derivations: tuple[ProteoformLineageArtifactDerivation, ...] = Field(
        min_length=M0402_DERIVATION_COUNT,
        max_length=M0402_DERIVATION_COUNT,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("identity_resolution", mode="wrap")
    @classmethod
    def identity_resolution_rejects_public_derived_sentinels(
        cls,
        value: object,
        handler: ValidatorFunctionWrapHandler,
    ) -> IdentityLineageResolution:
        resolution_digest: object
        core_digest: object
        graph_digest: object
        if isinstance(value, IdentityLineageResolution):
            resolution_digest = value.resolution_digest
            core_digest = value.core_digest
            graph_digest = value.graph.graph_digest
        elif isinstance(value, dict):
            resolution_digest = dict.get(value, "resolution_digest")
            core_digest = dict.get(value, "core_digest")
            graph = dict.get(value, "graph")
            graph_digest = dict.get(graph, "graph_digest") if isinstance(graph, dict) else None
        else:
            return cast("IdentityLineageResolution", handler(value))
        if M0402_ZERO_DIGEST in (resolution_digest, core_digest, graph_digest):
            raise ValueError("embedded M01-02 derived digests must be final, not sentinels")
        if isinstance(value, IdentityLineageResolution):
            parsed = value
        else:
            parsed = IdentityLineageResolution.model_validate_json(
                canonical_json_bytes(normalized_identity_resolution(value)), strict=True
            )
        return IdentityLineageResolution.model_validate_json(
            canonical_json_bytes(normalized_identity_resolution(parsed)), strict=True
        )

    @field_validator("protocol_result", mode="wrap")
    @classmethod
    def protocol_result_rejects_public_derived_sentinels(
        cls,
        value: object,
        handler: ValidatorFunctionWrapHandler,
    ) -> ProteoformProtocolConformanceResult:
        result_digest: object
        receipt_digest_value: object
        if isinstance(value, ProteoformProtocolConformanceResult):
            result_digest = value.result_digest
            receipt_digest_value = value.receipt.receipt_digest
        elif isinstance(value, dict):
            result_digest = dict.get(value, "result_digest")
            receipt = dict.get(value, "receipt")
            receipt_digest_value = (
                dict.get(receipt, "receipt_digest") if isinstance(receipt, dict) else None
            )
        else:
            return cast("ProteoformProtocolConformanceResult", handler(value))
        if M0402_ZERO_DIGEST in (result_digest, receipt_digest_value):
            raise ValueError("embedded M04-01 derived digests must be final, not sentinels")
        if isinstance(value, ProteoformProtocolConformanceResult):
            parsed = value
        else:
            parsed = ProteoformProtocolConformanceResult.model_validate_json(
                canonical_json_bytes(normalized_protocol_result(value)), strict=True
            )
        return ProteoformProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(normalized_protocol_result(parsed)), strict=True
        )

    @field_validator("artifact_claims", "derivations")
    @classmethod
    def semantic_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def request_is_closed(self) -> ReconcileProteoformIdentityLineageRequest:
        _require_authorized_context(self.context)
        opaque_proteoform_lineage_identifier("request", self.request_id)
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal the authorized context identifier")
        _validate_context_opacity(self.context)
        if self.policy.reviewed_at > self.context.occurred_at:
            raise ValueError("lineage policy cannot postdate reconciliation")
        if (
            self.identity_resolution.resolved_at > self.context.occurred_at
            or self.protocol_result.completed_at > self.context.occurred_at
        ):
            raise ValueError("upstream result cannot postdate reconciliation")
        if self.protocol_result.completed_at < self.identity_resolution.resolved_at:
            raise ValueError("M04-01 protocol result cannot predate its M01-02 identity binding")
        identity_digest = self.identity_resolution.resolution_digest
        if (
            self.context.references.identity_lineage.binding_digest != identity_digest
            or self.protocol_result.receipt.identity_subject_digest != identity_digest
            or self.context.references.quality.evidence.digest != self.protocol_result.result_digest
            or self.context.references.intended_use.evidence.digest
            != self.protocol_result.receipt.intended_use_evidence_digest
        ):
            raise ValueError("M04-02 identity chain does not bind the exact M01-02 resolution")
        config_hash = configuration_digest(self.policy)
        if self.context.references.approved_configuration.evidence.digest != config_hash:
            raise ValueError("approved configuration does not bind the M04-02 policy")
        if len(self.artifact_claims) > self.policy.max_artifact_claims:
            raise ValueError("artifact claims exceed the active policy")
        _validate_unique_ids(self.artifact_claims, "claim_id", "artifact claim")
        _validate_unique_ids(self.derivations, "derivation_id", "artifact derivation")
        _validate_evidence_identity_consistency(self)
        claims = {claim.claim_id: claim for claim in self.artifact_claims}
        upstream_nodes = {node.entity_id: node for node in self.identity_resolution.graph.nodes}
        for claim in self.artifact_claims:
            node = upstream_nodes.get(claim.identity_entity_id)
            if node is None:
                raise ValueError("artifact claim references an unknown identity entity")
            if node.kind is not EntityKind.DERIVED_OBJECT:
                raise ValueError("proteoform artifacts require derived-object anchors")
            _validate_physical_anchor_path(self.identity_resolution, claim.identity_entity_id)
        if self.policy.require_all_seven_entity_kinds and {
            node.kind for node in self.identity_resolution.graph.nodes
        } != set(EntityKind):
            raise ValueError("M04-02 requires every physical identity entity kind")
        _validate_artifact_dag(self.derivations, claims, self.policy)
        _validate_subject_propagation(self.derivations, claims, upstream_nodes)
        if len(canonical_json_bytes(normalized_request(self))) > M0402_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M04-02 request exceeds the 4 MiB ingress bound")
        return self


def _validate_unique_ids(
    values: tuple[object, ...],
    field: str,
    label: str,
) -> None:
    identifiers = tuple(getattr(item, field) for item in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label} identifiers must be unique")


def _validate_context_opacity(context: ExecutionContext) -> None:
    opaque_proteoform_lineage_identifier("request", context.request_id)
    opaque_proteoform_lineage_identifier("actor", context.actor_id)
    controls = (
        context.references.approved_configuration,
        context.references.identity_lineage,
        context.references.provenance,
        context.references.consent,
        context.references.quality,
        context.references.support,
        context.references.intended_use,
    )
    for control in controls:
        opaque_proteoform_lineage_identifier("decision", control.decision_id)
        _validate_artifact(control.evidence, media_type=_CONTROL_MEDIA_TYPE)


def _validate_physical_anchor_path(
    resolution: IdentityLineageResolution,
    anchor_id: Identifier,
) -> None:
    node_kinds = {node.entity_id: node.kind for node in resolution.graph.nodes}
    reverse: dict[Identifier, set[Identifier]] = {}
    for operation in resolution.graph.operations:
        for target in operation.target_entity_ids:
            reverse.setdefault(target, set()).update(operation.source_entity_ids)
    reachable = {anchor_id}
    pending = [anchor_id]
    while pending:
        target = pending.pop()
        for source in reverse.get(target, set()):
            if source not in reachable:
                reachable.add(source)
                pending.append(source)
    if {node_kinds[item] for item in reachable} != set(EntityKind):
        raise ValueError("artifact anchor lacks a governed seven-kind physical lineage path")


def _validate_evidence_identity_consistency(
    request: ReconcileProteoformIdentityLineageRequest,
) -> None:
    refs = request.context.references
    submitted_evidence = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        *(item.evidence for item in request.policy.approved_derivation_methods),
        *(derivation.evidence for derivation in request.derivations),
    )
    evidence_by_identity: dict[tuple[Identifier, SemanticVersion], tuple[Sha256Digest, str]] = {}
    for artifact in submitted_evidence:
        key = (artifact.artifact_id, artifact.version)
        content = (artifact.digest, artifact.media_type)
        previous = evidence_by_identity.setdefault(key, content)
        if previous != content:
            raise ValueError("one submitted evidence identity cannot declare conflicting content")
    for claim in request.artifact_claims:
        key = (claim.artifact.artifact_id, claim.artifact.version)
        content = (claim.artifact.digest, claim.artifact.media_type)
        if key in evidence_by_identity and evidence_by_identity[key] != content:
            raise ValueError("an artifact claim cannot contradict a control evidence identity")
        upstream_matches = (
            *(
                item.reference
                for item in request.identity_resolution.evidence
                if (item.reference.artifact_id, item.reference.version) == key
            ),
            *(
                item.reference
                for item in request.protocol_result.evidence
                if (item.reference.artifact_id, item.reference.version) == key
            ),
        )
        if upstream_matches and content not in {
            (item.digest, item.media_type) for item in upstream_matches
        }:
            raise ValueError(
                "an artifact claim cannot contradict embedded upstream evidence content"
            )


def _validate_artifact_dag(
    derivations: tuple[ProteoformLineageArtifactDerivation, ...],
    claims: dict[Identifier, ProteoformLineageArtifactClaim],
    policy: ProteoformIdentityLineagePolicy,
) -> None:
    roles: dict[ProteoformLineageArtifactRole, set[Identifier]] = {
        role: {claim_id for claim_id, claim in claims.items() if claim.role is role}
        for role in ProteoformLineageArtifactRole
    }
    bundle_ids = roles[ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE]
    source_ids = set(claims) - bundle_ids
    if len(bundle_ids) != 1 or any(
        not roles[role]
        for role in (
            ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST,
            ProteoformLineageArtifactRole.GENOME_MANIFEST,
            ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
            ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST,
        )
    ):
        raise ValueError("artifact DAG requires four source roles and exactly one bundle")
    approved = {(item.method_id, item.version) for item in policy.approved_derivation_methods}
    if len(derivations) != M0402_DERIVATION_COUNT:
        raise ValueError("artifact DAG requires exactly one assembly derivation")
    for derivation in derivations:
        endpoints = set(derivation.source_claim_ids) | {derivation.target_claim_id}
        if not endpoints.issubset(claims):
            raise ValueError("artifact derivation references an unknown claim")
        if len(derivation.source_claim_ids) > policy.max_derivation_sources:
            raise ValueError("artifact derivation sources exceed the active policy")
        if (derivation.method_id, derivation.method_version) not in approved:
            raise ValueError("artifact derivation method is not approved")
        if derivation.target_claim_id not in bundle_ids:
            raise ValueError("artifact derivation must target the exact input bundle")
        if set(derivation.source_claim_ids) != source_ids:
            raise ValueError("artifact derivation must consume every non-bundle claim")


def _validate_subject_propagation(
    derivations: tuple[ProteoformLineageArtifactDerivation, ...],
    claims: dict[Identifier, ProteoformLineageArtifactClaim],
    upstream_nodes: dict[Identifier, ResolvedIdentityNode],
) -> None:
    subjects: dict[Identifier, tuple[Sha256Digest, ...]] = {}
    derivations_by_target = {derivation.target_claim_id: derivation for derivation in derivations}
    for role in ProteoformLineageArtifactRole:
        for claim in sorted(
            (item for item in claims.values() if item.role is role),
            key=lambda item: item.claim_id,
        ):
            producer = derivations_by_target.get(claim.claim_id)
            if producer is None:
                node_subjects = tuple(
                    upstream_nodes[claim.identity_entity_id].subject_component_ids
                )
                propagated = node_subjects
            else:
                propagated = tuple(
                    sorted(
                        {
                            subject
                            for source_id in producer.source_claim_ids
                            for subject in subjects[source_id]
                        }
                    )
                )
            if len(propagated) > M0402_MAX_SUBJECT_COMPONENT_IDS:
                raise ValueError(
                    "artifact subject propagation exceeds the privacy-minimized output cap"
                )
            subjects[claim.claim_id] = propagated


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if (
        references.consent.state.value != "granted"
        or references.identity_lineage.state.value != "resolved"
        or any(
            item.state.value != "accepted"
            for item in (
                references.approved_configuration,
                references.provenance,
                references.quality,
                references.support,
                references.intended_use,
            )
        )
    ):
        raise ValueError("proteoform lineage reconciliation is not authorized")


class ProteoformIdentityLineageFindingCode(StrEnum):
    UPSTREAM_IDENTITY_UNRESOLVED = "upstream_identity_unresolved"
    UPSTREAM_PROTOCOL_NONCONFORMANT = "upstream_protocol_nonconformant"
    IDENTITY_NOT_EVALUABLE = "identity_not_evaluable"
    IDENTITY_SWAP = "identity_swap"
    CROSS_PATIENT_LINK = "cross_patient_link"
    ARTIFACT_LINEAGE_COLLISION = "artifact_lineage_collision"
    ARTIFACT_IDENTITY_COLLISION = "artifact_identity_collision"
    BINDING_SCOPE_COLLISION = "binding_scope_collision"
    DUPLICATE_CONTENT_RETAINED = "duplicate_content_retained"
    PRODUCER_IDENTITY_DRIFT = "producer_identity_drift"
    PRODUCER_PROTOCOL_DRIFT = "producer_protocol_drift"
    PRODUCER_REFERENCE_BUNDLE_DRIFT = "producer_reference_bundle_drift"
    PRODUCER_COORDINATE_POLICY_DRIFT = "producer_coordinate_policy_drift"
    ARTIFACT_EVIDENCE_NOT_EVALUABLE = "artifact_evidence_not_evaluable"


class ProteoformIdentityLineageFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


_FINDING_ACTION: Final = {
    ProteoformIdentityLineageFindingCode.UPSTREAM_IDENTITY_UNRESOLVED: (
        ProteoformIdentityLineageFindingAction.ABSTAIN
    ),
    ProteoformIdentityLineageFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.IDENTITY_NOT_EVALUABLE: (
        ProteoformIdentityLineageFindingAction.ABSTAIN
    ),
    ProteoformIdentityLineageFindingCode.IDENTITY_SWAP: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.CROSS_PATIENT_LINK: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.ARTIFACT_IDENTITY_COLLISION: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.BINDING_SCOPE_COLLISION: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED: (
        ProteoformIdentityLineageFindingAction.RECORD
    ),
    ProteoformIdentityLineageFindingCode.PRODUCER_IDENTITY_DRIFT: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.PRODUCER_PROTOCOL_DRIFT: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.PRODUCER_REFERENCE_BUNDLE_DRIFT: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.PRODUCER_COORDINATE_POLICY_DRIFT: (
        ProteoformIdentityLineageFindingAction.QUARANTINE
    ),
    ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE: (
        ProteoformIdentityLineageFindingAction.ABSTAIN
    ),
}


def _disposition_for_finding_codes(
    codes: tuple[ProteoformIdentityLineageFindingCode, ...],
) -> ProteoformLineageDisposition:
    actions = {_FINDING_ACTION[code] for code in codes}
    if ProteoformIdentityLineageFindingAction.QUARANTINE in actions:
        return ProteoformLineageDisposition.QUARANTINED
    if ProteoformIdentityLineageFindingAction.ABSTAIN in actions:
        return ProteoformLineageDisposition.ABSTAINED
    return ProteoformLineageDisposition.RECONCILED


class ProteoformIdentityLineageFinding(FrozenModel):
    code: ProteoformIdentityLineageFindingCode
    action: ProteoformIdentityLineageFindingAction
    claim_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0402_MAX_ARTIFACT_CLAIMS)
    derivation_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0402_DERIVATION_COUNT)
    evidence_basis_digest: Sha256Digest

    @field_validator("claim_ids", "derivation_ids")
    @classmethod
    def references_are_unique_and_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("finding references must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def action_matches_code(self) -> ProteoformIdentityLineageFinding:
        if self.action is not _FINDING_ACTION[self.code]:
            raise ValueError("M04-02 finding action contradicts its closed finding code")
        return self


class ResolvedProteoformLineageArtifact(FrozenModel):
    claim_id: Identifier
    role: ProteoformLineageArtifactRole
    artifact_digest: Sha256Digest
    identity_entity_id: Identifier
    lineage_path_digest: Sha256Digest
    declared_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    resolved_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    evidence_state: ProteoformLineageEvidenceState
    finding_codes: tuple[ProteoformIdentityLineageFindingCode, ...] = Field(
        default=(), max_length=16
    )

    @field_validator(
        "declared_subject_component_ids",
        "resolved_subject_component_ids",
        "finding_codes",
    )
    @classmethod
    def semantic_collections_are_unique_and_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        if len(values) != len(set(values)):
            raise ValueError("resolved artifact collections must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))


class ResolvedProteoformLineageDerivation(FrozenModel):
    derivation_id: Identifier
    source_claim_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0402_MAX_DERIVATION_SOURCES
    )
    target_claim_id: Identifier
    method_id: Identifier
    method_version: SemanticVersion
    evidence_digest: Sha256Digest
    propagated_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)

    @field_validator("source_claim_ids", "propagated_subject_component_ids")
    @classmethod
    def semantic_collections_are_unique_and_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        if len(values) != len(set(values)):
            raise ValueError("resolved derivation collections must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))


class ResolvedProteoformIdentityLineageGraph(FrozenModel):
    identity_resolution_digest: Sha256Digest
    physical_graph_digest: Sha256Digest
    artifacts: tuple[ResolvedProteoformLineageArtifact, ...] = Field(
        min_length=M0402_MIN_ARTIFACT_CLAIMS, max_length=M0402_MAX_ARTIFACT_CLAIMS
    )
    derivations: tuple[ResolvedProteoformLineageDerivation, ...] = Field(
        min_length=M0402_DERIVATION_COUNT,
        max_length=M0402_DERIVATION_COUNT,
    )
    graph_digest: Sha256Digest

    @field_validator("artifacts", "derivations")
    @classmethod
    def semantic_collections_are_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def graph_is_closed_and_digest_is_exact(  # noqa: PLR0912 - explicit topology closure.
        self,
    ) -> ResolvedProteoformIdentityLineageGraph:
        _validate_unique_ids(self.artifacts, "claim_id", "resolved artifact")
        _validate_unique_ids(self.derivations, "derivation_id", "resolved derivation")
        artifacts = {artifact.claim_id: artifact for artifact in self.artifacts}
        roles = {
            role: {artifact.claim_id for artifact in self.artifacts if artifact.role is role}
            for role in ProteoformLineageArtifactRole
        }
        bundle_ids = roles[ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE]
        if len(bundle_ids) != 1 or any(
            not roles[role]
            for role in (
                ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST,
                ProteoformLineageArtifactRole.GENOME_MANIFEST,
                ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
                ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST,
            )
        ):
            raise ValueError("resolved graph does not contain the exact five-role shape")
        producers: dict[Identifier, ResolvedProteoformLineageDerivation] = {}
        for derivation in self.derivations:
            if (
                len(derivation.source_claim_ids) != len(set(derivation.source_claim_ids))
                or derivation.target_claim_id in derivation.source_claim_ids
                or not (set(derivation.source_claim_ids) | {derivation.target_claim_id}).issubset(
                    artifacts
                )
                or derivation.target_claim_id in producers
            ):
                raise ValueError("resolved graph derivation endpoints are not closed")
            producers[derivation.target_claim_id] = derivation
        bundle_id = next(iter(bundle_ids))
        source_ids = set(artifacts) - {bundle_id}
        if (
            set(producers) != {bundle_id}
            or set(producers[bundle_id].source_claim_ids) != source_ids
        ):
            raise ValueError("resolved graph contradicts the closed artifact topology")
        for target_id, derivation in producers.items():
            propagated = tuple(
                sorted(
                    {
                        subject
                        for source_id in derivation.source_claim_ids
                        for subject in artifacts[source_id].resolved_subject_component_ids
                    }
                )
            )
            if (
                derivation.propagated_subject_component_ids != propagated
                or artifacts[target_id].resolved_subject_component_ids != propagated
            ):
                raise ValueError(
                    "resolved graph subject propagation contradicts its source artifacts"
                )
            lineage_contexts = {
                (
                    artifacts[claim_id].identity_entity_id,
                    artifacts[claim_id].lineage_path_digest,
                )
                for claim_id in (*derivation.source_claim_ids, target_id)
            }
            if len(lineage_contexts) > 1 and any(
                ProteoformIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION
                not in artifacts[claim_id].finding_codes
                for claim_id in (*derivation.source_claim_ids, target_id)
            ):
                raise ValueError(
                    "resolved graph must retain divergent physical-lineage paths as a collision"
                )
        duplicate_claim_ids: set[Identifier] = set()
        by_digest: dict[Sha256Digest, list[ResolvedProteoformLineageArtifact]] = {}
        for artifact in self.artifacts:
            by_digest.setdefault(artifact.artifact_digest, []).append(artifact)
        for grouped in by_digest.values():
            if len(grouped) >= _MINIMUM_DUPLICATE_COUNT:
                duplicate_claim_ids.update(item.claim_id for item in grouped)
        for artifact in self.artifacts:
            codes = set(artifact.finding_codes)
            if (artifact.evidence_state is not ProteoformLineageEvidenceState.OBSERVED) != (
                ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE in codes
            ):
                raise ValueError(
                    "resolved graph evidence-state finding contradicts its artifact state"
                )
            if (artifact.claim_id in duplicate_claim_ids) != (
                ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED in codes
            ):
                raise ValueError(
                    "resolved graph duplicate-content findings contradict artifact digests"
                )
            if not codes.issubset(
                {
                    ProteoformIdentityLineageFindingCode.IDENTITY_NOT_EVALUABLE,
                    ProteoformIdentityLineageFindingCode.IDENTITY_SWAP,
                    ProteoformIdentityLineageFindingCode.CROSS_PATIENT_LINK,
                    ProteoformIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION,
                    ProteoformIdentityLineageFindingCode.ARTIFACT_IDENTITY_COLLISION,
                    ProteoformIdentityLineageFindingCode.BINDING_SCOPE_COLLISION,
                    ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED,
                    ProteoformIdentityLineageFindingCode.PRODUCER_IDENTITY_DRIFT,
                    ProteoformIdentityLineageFindingCode.PRODUCER_PROTOCOL_DRIFT,
                    ProteoformIdentityLineageFindingCode.PRODUCER_REFERENCE_BUNDLE_DRIFT,
                    ProteoformIdentityLineageFindingCode.PRODUCER_COORDINATE_POLICY_DRIFT,
                    ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,
                }
            ):
                raise ValueError("resolved graph contains a non-artifact finding code")
        if self.graph_digest != resolved_graph_digest(self):
            raise ValueError("resolved M04-02 graph digest does not match its content")
        return self


class ProteoformIdentityLineageReceipt(FrozenModel):
    identity_resolution_digest: Sha256Digest
    physical_graph_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    protocol_receipt_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    coordinate_policy_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    graph_digest: Sha256Digest
    finding_codes: tuple[ProteoformIdentityLineageFindingCode, ...] = Field(
        default=(), max_length=M0402_FINDING_CODE_COUNT
    )
    parent_target: Literal["protein_rna_discordance"] = M0402_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    infers_identity: Literal[False] = False
    disposition: ProteoformLineageDisposition
    receipt_digest: Sha256Digest

    @field_validator("finding_codes")
    @classmethod
    def finding_codes_are_unique_and_canonical(
        cls,
        values: tuple[ProteoformIdentityLineageFindingCode, ...],
    ) -> tuple[ProteoformIdentityLineageFindingCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("M04-02 receipt finding codes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def receipt_is_digest_bound(self) -> ProteoformIdentityLineageReceipt:
        if self.disposition is not _disposition_for_finding_codes(self.finding_codes):
            raise ValueError("M04-02 receipt disposition contradicts its finding codes")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("M04-02 receipt digest does not match its canonical content")
        return self


def expected_receipt(
    request: ReconcileProteoformIdentityLineageRequest,
    graph: ResolvedProteoformIdentityLineageGraph,
    disposition: ProteoformLineageDisposition,
    *,
    findings: tuple[ProteoformIdentityLineageFinding, ...] | None = None,
) -> ProteoformIdentityLineageReceipt:
    """Derive the exact immutable M04-02 receipt."""

    if findings is None:
        replay_graph, findings, replay_disposition = derive_proteoform_reconciliation(request)
        if replay_graph != graph or replay_disposition is not disposition:
            raise ValueError("M04-02 receipt inputs do not replay from the request")
    finding_codes = tuple(sorted({finding.code for finding in findings}))
    if disposition is not _disposition_for_finding_codes(finding_codes):
        raise ValueError("M04-02 receipt disposition contradicts its findings")
    payload: dict[str, object] = {
        "identity_resolution_digest": request.identity_resolution.resolution_digest,
        "physical_graph_digest": request.identity_resolution.graph.graph_digest,
        "protocol_result_digest": request.protocol_result.result_digest,
        "protocol_receipt_digest": request.protocol_result.receipt.receipt_digest,
        "reference_bundle_digest": request.protocol_result.receipt.reference_bundle_digest,
        "coordinate_policy_digest": request.protocol_result.receipt.coordinate_policy_digest,
        "intended_use_evidence_digest": (
            request.protocol_result.receipt.intended_use_evidence_digest
        ),
        "policy_digest": policy_digest(request.policy),
        "configuration_digest": configuration_digest(request.policy),
        "graph_digest": graph.graph_digest,
        "finding_codes": finding_codes,
        "parent_target": M0402_PARENT,
        "emits_protein_rna_discordance": False,
        "infers_identity": False,
        "disposition": disposition,
        "receipt_digest": M0402_ZERO_DIGEST,
    }
    payload["receipt_digest"] = receipt_digest(payload)
    return ProteoformIdentityLineageReceipt.model_validate(payload, strict=True)


def derive_proteoform_reconciliation(  # noqa: PLR0912, PLR0915 - explicit closed finding matrix.
    request: ReconcileProteoformIdentityLineageRequest,
) -> tuple[
    ResolvedProteoformIdentityLineageGraph,
    tuple[ProteoformIdentityLineageFinding, ...],
    ProteoformLineageDisposition,
]:
    """Derive the exact privacy-minimized graph, findings, and disposition."""

    claims = {claim.claim_id: claim for claim in request.artifact_claims}
    upstream_nodes = {node.entity_id: node for node in request.identity_resolution.graph.nodes}
    subjects: dict[Identifier, tuple[Sha256Digest, ...]] = {}
    finding_codes: dict[Identifier, set[ProteoformIdentityLineageFindingCode]] = {
        claim_id: set() for claim_id in claims
    }
    finding_specs: set[
        tuple[
            ProteoformIdentityLineageFindingCode,
            ProteoformIdentityLineageFindingAction,
            tuple[Identifier, ...],
            tuple[Identifier, ...],
            Sha256Digest,
        ]
    ] = set()

    def add_finding(
        code: ProteoformIdentityLineageFindingCode,
        action: ProteoformIdentityLineageFindingAction,
        *,
        claim_ids: tuple[Identifier, ...] = (),
        derivation_ids: tuple[Identifier, ...] = (),
        basis: object,
    ) -> None:
        canonical_claims = tuple(sorted(set(claim_ids)))
        canonical_derivations = tuple(sorted(set(derivation_ids)))
        digest = sha256_digest(
            {
                "code": code,
                "claim_ids": canonical_claims,
                "derivation_ids": canonical_derivations,
                "basis": basis,
            }
        )
        finding_specs.add((code, action, canonical_claims, canonical_derivations, digest))
        for claim_id in canonical_claims:
            finding_codes[claim_id].add(code)

    upstream_identity_evaluable = request.identity_resolution.decision.value == "resolved"
    if not upstream_identity_evaluable:
        add_finding(
            ProteoformIdentityLineageFindingCode.UPSTREAM_IDENTITY_UNRESOLVED,
            ProteoformIdentityLineageFindingAction.ABSTAIN,
            basis=request.identity_resolution.resolution_digest,
        )
    if request.protocol_result.disposition.value != "conformant":
        add_finding(
            ProteoformIdentityLineageFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT,
            ProteoformIdentityLineageFindingAction.QUARANTINE,
            basis=request.protocol_result.result_digest,
        )

    derivations_by_target = {
        derivation.target_claim_id: derivation for derivation in request.derivations
    }
    role_order = tuple(ProteoformLineageArtifactRole)
    for role in role_order:
        for claim in sorted(
            (item for item in request.artifact_claims if item.role is role),
            key=lambda item: item.claim_id,
        ):
            node_subjects = tuple(
                sorted(upstream_nodes[claim.identity_entity_id].subject_component_ids)
            )
            producer = derivations_by_target.get(claim.claim_id)
            propagated = (
                node_subjects
                if producer is None
                else tuple(
                    sorted(
                        {
                            subject
                            for source_id in producer.source_claim_ids
                            for subject in subjects[source_id]
                        }
                    )
                )
            )
            subjects[claim.claim_id] = propagated
            if producer is not None:
                participating_ids = (*producer.source_claim_ids, claim.claim_id)
                lineage_contexts = {
                    (
                        claims[claim_id].identity_entity_id,
                        physical_lineage_path_digest(
                            request.identity_resolution,
                            claims[claim_id].identity_entity_id,
                        ),
                    )
                    for claim_id in participating_ids
                }
                if len(lineage_contexts) > 1:
                    add_finding(
                        ProteoformIdentityLineageFindingCode.ARTIFACT_LINEAGE_COLLISION,
                        ProteoformIdentityLineageFindingAction.QUARANTINE,
                        claim_ids=participating_ids,
                        derivation_ids=(producer.derivation_id,),
                        basis=tuple(sorted(lineage_contexts)),
                    )
            if upstream_identity_evaluable and (not node_subjects or not propagated):
                add_finding(
                    ProteoformIdentityLineageFindingCode.IDENTITY_NOT_EVALUABLE,
                    ProteoformIdentityLineageFindingAction.ABSTAIN,
                    claim_ids=(claim.claim_id,),
                    basis=(node_subjects, propagated),
                )
            if upstream_identity_evaluable and (
                tuple(sorted(claim.declared_subject_component_ids)) != node_subjects
                or (producer is not None and propagated != node_subjects)
            ):
                add_finding(
                    ProteoformIdentityLineageFindingCode.IDENTITY_SWAP,
                    ProteoformIdentityLineageFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    derivation_ids=() if producer is None else (producer.derivation_id,),
                    basis=(claim.declared_subject_component_ids, node_subjects, propagated),
                )
            if upstream_identity_evaluable and len(set(node_subjects) | set(propagated)) > 1:
                add_finding(
                    ProteoformIdentityLineageFindingCode.CROSS_PATIENT_LINK,
                    ProteoformIdentityLineageFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=(node_subjects, propagated),
                )
            if (
                claim.producer_identity_resolution_digest
                != request.identity_resolution.resolution_digest
            ):
                add_finding(
                    ProteoformIdentityLineageFindingCode.PRODUCER_IDENTITY_DRIFT,
                    ProteoformIdentityLineageFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_identity_resolution_digest,
                )
            if claim.producer_protocol_result_digest != request.protocol_result.result_digest:
                add_finding(
                    ProteoformIdentityLineageFindingCode.PRODUCER_PROTOCOL_DRIFT,
                    ProteoformIdentityLineageFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_protocol_result_digest,
                )
            if (
                claim.producer_reference_bundle_digest
                != request.protocol_result.receipt.reference_bundle_digest
            ):
                add_finding(
                    ProteoformIdentityLineageFindingCode.PRODUCER_REFERENCE_BUNDLE_DRIFT,
                    ProteoformIdentityLineageFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_reference_bundle_digest,
                )
            if (
                claim.producer_coordinate_policy_digest
                != request.protocol_result.receipt.coordinate_policy_digest
            ):
                add_finding(
                    ProteoformIdentityLineageFindingCode.PRODUCER_COORDINATE_POLICY_DRIFT,
                    ProteoformIdentityLineageFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_coordinate_policy_digest,
                )
            if claim.evidence_state is not ProteoformLineageEvidenceState.OBSERVED:
                add_finding(
                    ProteoformIdentityLineageFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,
                    ProteoformIdentityLineageFindingAction.ABSTAIN,
                    claim_ids=(claim.claim_id,),
                    basis=claim.evidence_state,
                )

    digest_groups: dict[Sha256Digest, list[ProteoformLineageArtifactClaim]] = {}
    for claim in request.artifact_claims:
        digest_groups.setdefault(claim.artifact.digest, []).append(claim)
    for digest, grouped in digest_groups.items():
        if len(grouped) < _MINIMUM_DUPLICATE_COUNT:
            continue
        contexts = {
            (
                claim.role,
                claim.identity_entity_id,
                subjects[claim.claim_id],
                physical_lineage_path_digest(request.identity_resolution, claim.identity_entity_id),
            )
            for claim in grouped
        }
        add_finding(
            ProteoformIdentityLineageFindingCode.DUPLICATE_CONTENT_RETAINED,
            ProteoformIdentityLineageFindingAction.RECORD,
            claim_ids=tuple(item.claim_id for item in grouped),
            basis=(digest, tuple(sorted(contexts, key=canonical_json_bytes))),
        )

    identity_groups: dict[
        tuple[Identifier, SemanticVersion], list[ProteoformLineageArtifactClaim]
    ] = {}
    for claim in request.artifact_claims:
        identity_groups.setdefault((claim.artifact.artifact_id, claim.artifact.version), []).append(
            claim
        )
    for identity, grouped in identity_groups.items():
        declarations = {(claim.artifact.digest, claim.artifact.media_type) for claim in grouped}
        if len(declarations) < _MINIMUM_DUPLICATE_COUNT:
            continue
        add_finding(
            ProteoformIdentityLineageFindingCode.ARTIFACT_IDENTITY_COLLISION,
            ProteoformIdentityLineageFindingAction.QUARANTINE,
            claim_ids=tuple(item.claim_id for item in grouped),
            basis=(identity, tuple(sorted(declarations))),
        )

    binding_groups: dict[
        tuple[ProteoformLineageArtifactRole, Identifier],
        list[ProteoformLineageArtifactClaim],
    ] = {}
    for claim in request.artifact_claims:
        binding_groups.setdefault((claim.role, claim.identity_entity_id), []).append(claim)
    for binding, grouped in binding_groups.items():
        if len(grouped) < _MINIMUM_DUPLICATE_COUNT:
            continue
        add_finding(
            ProteoformIdentityLineageFindingCode.BINDING_SCOPE_COLLISION,
            ProteoformIdentityLineageFindingAction.QUARANTINE,
            claim_ids=tuple(item.claim_id for item in grouped),
            basis=(binding, tuple(item.artifact.digest for item in grouped)),
        )

    artifacts = tuple(
        ResolvedProteoformLineageArtifact(
            claim_id=claim.claim_id,
            role=claim.role,
            artifact_digest=claim.artifact.digest,
            identity_entity_id=claim.identity_entity_id,
            lineage_path_digest=physical_lineage_path_digest(
                request.identity_resolution, claim.identity_entity_id
            ),
            declared_subject_component_ids=tuple(sorted(claim.declared_subject_component_ids)),
            resolved_subject_component_ids=subjects[claim.claim_id],
            evidence_state=claim.evidence_state,
            finding_codes=tuple(sorted(finding_codes[claim.claim_id])),
        )
        for claim in sorted(request.artifact_claims, key=lambda item: item.claim_id)
    )
    resolved_derivations = tuple(
        ResolvedProteoformLineageDerivation(
            derivation_id=derivation.derivation_id,
            source_claim_ids=tuple(sorted(derivation.source_claim_ids)),
            target_claim_id=derivation.target_claim_id,
            method_id=derivation.method_id,
            method_version=derivation.method_version,
            evidence_digest=derivation.evidence.digest,
            propagated_subject_component_ids=subjects[derivation.target_claim_id],
        )
        for derivation in sorted(request.derivations, key=lambda item: item.derivation_id)
    )
    graph_payload: dict[str, object] = {
        "identity_resolution_digest": request.identity_resolution.resolution_digest,
        "physical_graph_digest": request.identity_resolution.graph.graph_digest,
        "artifacts": artifacts,
        "derivations": resolved_derivations,
        "graph_digest": "sha256:" + ("0" * 64),
    }
    graph_payload["graph_digest"] = resolved_graph_digest(graph_payload)
    graph = ResolvedProteoformIdentityLineageGraph.model_validate(graph_payload, strict=True)
    findings = tuple(
        ProteoformIdentityLineageFinding(
            code=code,
            action=action,
            claim_ids=claim_ids,
            derivation_ids=derivation_ids,
            evidence_basis_digest=digest,
        )
        for code, action, claim_ids, derivation_ids, digest in sorted(
            finding_specs, key=canonical_json_bytes
        )
    )
    actions = {finding.action for finding in findings}
    disposition = (
        ProteoformLineageDisposition.QUARANTINED
        if ProteoformIdentityLineageFindingAction.QUARANTINE in actions
        else ProteoformLineageDisposition.ABSTAINED
        if ProteoformIdentityLineageFindingAction.ABSTAIN in actions
        else ProteoformLineageDisposition.RECONCILED
    )
    return graph, findings, disposition


def proteoform_lineage_evidence_index(
    request: ReconcileProteoformIdentityLineageRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: tuple[ArtifactReference, ...] = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        *(item.evidence for item in request.policy.approved_derivation_methods),
        *(item.artifact for item in request.artifact_claims),
        *(item.evidence for item in request.derivations),
    )
    if not M0402_MIN_EVIDENCE <= len(artifacts) <= M0402_MAX_EVIDENCE:
        raise ValueError("M04-02 evidence index exceeds its exact installed shape")
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=item,
                    role="evidence",
                    claim=M0402_EVIDENCE_CLAIM,
                )
                for item in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def expected_control_decisions(
    context: ExecutionContext,
) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    records = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return tuple(sorted(records, key=lambda item: item.role.value))


def expected_support(disposition: ProteoformLineageDisposition) -> SupportDecision:
    if disposition is ProteoformLineageDisposition.RECONCILED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="proteoform_identity_lineage_reconciled",
            rationale=M0402_RECONCILED_RATIONALE,
        )
    if disposition is ProteoformLineageDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="proteoform_identity_lineage_quarantined",
            rationale=M0402_QUARANTINED_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="proteoform_identity_lineage_abstained",
        rationale=M0402_ABSTAINED_RATIONALE,
    )


def expected_uncertainty() -> UncertaintyProfile:
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0402_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0402_SENSITIVITY_NOTES,
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="deterministic_identity_lineage_reconciliation_only",
                    statement=(
                        "This result reconciles caller-declared categorical lineage only; it "
                        "does not authenticate a person, infer identity, or relabel evidence."
                    ),
                ),
                Limitation(
                    code="caller_declared_authority_not_authenticated",
                    statement=(
                        "Configuration, identity, protocol, review, and evidence authorities "
                        "remain caller-declared and are not authenticated by M04-02."
                    ),
                ),
                Limitation(
                    code="no_identity_protein_discordance_or_clinical_inference",
                    statement=(
                        "No protein, proteoform, copy-number, protein-RNA discordance, kinase, "
                        "subtype, treatment, consent, or clinical claim is produced."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def expected_provenance(
    request: ReconcileProteoformIdentityLineageRequest,
    request_hash: Sha256Digest,
    graph_hash: Sha256Digest,
) -> ProvenanceRecord:
    config_hash = configuration_digest(request.policy)
    active_policy_hash = policy_digest(request.policy)
    evidence = proteoform_lineage_evidence_index(request)
    controls = expected_control_decisions(request.context)
    input_digests = tuple(
        sorted(
            {
                request_hash,
                request.identity_resolution.resolution_digest,
                request.identity_resolution.graph.graph_digest,
                request.protocol_result.result_digest,
                request.protocol_result.protocol_digest,
                request.protocol_result.receipt.receipt_digest,
                request.protocol_result.receipt.reference_bundle_digest,
                request.protocol_result.receipt.coordinate_policy_digest,
                request.protocol_result.receipt.intended_use_evidence_digest,
                active_policy_hash,
                config_hash,
                graph_hash,
                *(
                    (request.supersedes_result_digest,)
                    if request.supersedes_result_digest is not None
                    else ()
                ),
                *(item.reference.digest for item in evidence),
                *(item.evidence_digest for item in controls),
            }
        )
    )
    refs = request.context.references
    suffix = request_hash.removeprefix("sha256:")
    return ProvenanceRecord(
        activity_id=f"activity.m0402.{suffix}",
        actor_id=request.context.actor_id,
        module_id=M0402_MODULE_ID,
        module_version=M0402_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=config_hash,
        consent_decision_id=refs.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _normalized_findings(
    findings: tuple[ProteoformIdentityLineageFinding, ...],
) -> tuple[dict[str, object], ...]:
    values: list[dict[str, object]] = []
    for finding in findings:
        value = finding.model_dump(mode="python", exclude_none=False)
        value["claim_ids"] = tuple(sorted(finding.claim_ids))
        value["derivation_ids"] = tuple(sorted(finding.derivation_ids))
        values.append(value)
    return tuple(sorted(values, key=canonical_json_bytes))


def _normalized_provenance(provenance: ProvenanceRecord) -> dict[str, object]:
    value = provenance.model_dump(mode="python", exclude_none=False)
    value["input_digests"] = tuple(sorted(provenance.input_digests))
    value["control_decisions"] = tuple(sorted(value["control_decisions"], key=canonical_json_bytes))
    return value


def _normalized_uncertainty(uncertainty: UncertaintyProfile) -> dict[str, object]:
    value = uncertainty.model_dump(mode="python", exclude_none=False)
    value["sensitivity_notes"] = tuple(sorted(uncertainty.sensitivity_notes))
    return value


class ProteoformIdentityLineageResolution(NonInferenceResultModel):
    output_type: Literal["proteoform_identity_lineage_resolution"] = (
        "proteoform_identity_lineage_resolution"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0402_CONTRACT_VERSION
    request_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    graph_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ReconcileProteoformIdentityLineageRequest
    receipt: ProteoformIdentityLineageReceipt
    graph: ResolvedProteoformIdentityLineageGraph
    findings: tuple[ProteoformIdentityLineageFinding, ...] = Field(
        default=(), max_length=M0402_MAX_FINDINGS
    )
    disposition: ProteoformLineageDisposition
    parent_target: Literal["protein_rna_discordance"] = M0402_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=M0402_MIN_EVIDENCE, max_length=M0402_MAX_EVIDENCE
    )
    limitations: tuple[Limitation, ...] = Field(
        min_length=M0402_LIMITATION_COUNT, max_length=M0402_LIMITATION_COUNT
    )
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("findings", "evidence", "limitations")
    @classmethod
    def semantic_collections_are_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("provenance")
    @classmethod
    def provenance_collections_are_canonical(
        cls,
        value: ProvenanceRecord,
    ) -> ProvenanceRecord:
        return value.model_copy(
            update={
                "input_digests": tuple(sorted(value.input_digests)),
                "control_decisions": tuple(
                    sorted(value.control_decisions, key=canonical_json_bytes)
                ),
            }
        )

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_notes_are_canonical(
        cls,
        value: UncertaintyProfile,
    ) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> ProteoformIdentityLineageResolution:
        request_hash = canonical_request_digest(self.request)
        active_policy_hash = policy_digest(self.request.policy)
        config_hash = configuration_digest(self.request.policy)
        graph, findings, disposition = derive_proteoform_reconciliation(self.request)
        active_receipt = expected_receipt(self.request, graph, disposition, findings=findings)
        suffix = request_hash.removeprefix("sha256:")
        if (
            self.result_id != f"result.m0402.{suffix}"
            or self.request_digest != request_hash
            or self.identity_resolution_digest != self.request.identity_resolution.resolution_digest
            or self.protocol_result_digest != self.request.protocol_result.result_digest
            or self.policy_digest != active_policy_hash
            or self.configuration_digest != config_hash
            or self.graph_digest != graph.graph_digest
            or self.receipt != active_receipt
            or self.graph != graph
            or _normalized_findings(self.findings) != _normalized_findings(findings)
            or self.disposition is not disposition
            or self.support != expected_support(disposition)
            or _normalized_uncertainty(self.uncertainty)
            != _normalized_uncertainty(expected_uncertainty())
            or _normalized_provenance(self.provenance)
            != _normalized_provenance(
                expected_provenance(self.request, request_hash, graph.graph_digest)
            )
            or tuple(sorted(self.evidence, key=canonical_json_bytes))
            != tuple(
                sorted(proteoform_lineage_evidence_index(self.request), key=canonical_json_bytes)
            )
            or tuple(sorted(self.limitations, key=canonical_json_bytes))
            != tuple(sorted(expected_limitations(), key=canonical_json_bytes))
            or self.human_review_required
            != (disposition is not ProteoformLineageDisposition.RECONCILED)
            or self.completed_at != self.request.context.occurred_at
        ):
            raise ValueError("M04-02 result contradicts its embedded reconciliation request")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M04-02 result digest does not match its canonical content")
        return self


__all__ = [name for name in globals() if not name.startswith("_")]
