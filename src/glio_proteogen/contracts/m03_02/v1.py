"""Version 1 contracts for M03-02 identity-lineage reconciliation."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m01_02 import (
    EntityKind,
    IdentityLineageResolution,
)
from glio_proteogen.contracts.m03_01 import (  # noqa: TC001 - Pydantic runtime types.
    DeclaredUnresolvedState,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.contracts.m03_02.canonical import (
    canonical_request_digest,
    configuration_digest,
    normalized_request,
    policy_digest,
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

M0302_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-02"
M0302_OPERATION: Final = "reconcile_protein_inference_identity_lineage"
M0302_PARENT: Final = "complex_activity"
M0302_CONTRACT_VERSION: Final = "1.0.0"
M0302_MAX_ARTIFACT_CLAIMS: Final = 256
M0302_DERIVATION_COUNT: Final = 3
M0302_CN_RECEIPT_COUNT: Final = 1
M0302_MAX_DERIVATION_SOURCES: Final = 253
M0302_MAX_SUBJECT_COMPONENT_IDS: Final = 256
M0302_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
# Seven per-claim findings, one finding per duplicate-content pair, one per
# conflicting artifact-identity pair, two upstream findings, and one copy-number
# finding at the exact public request maximum.
M0302_MAX_FINDINGS: Final = (
    (7 * M0302_MAX_ARTIFACT_CLAIMS)
    + (2 * (M0302_MAX_ARTIFACT_CLAIMS // 2))
    + M0302_DERIVATION_COUNT
    + 3
)
_MINIMUM_DUPLICATE_COUNT: Final = 2
M0302_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed M03-02 lineage reconciliation evidence."
)
M0302_RECONCILED_RATIONALE: Final = (
    "The artifact derivation lineage reconciles to one exact governed identity context."
)
M0302_QUARANTINED_RATIONALE: Final = (
    "A lineage discrepancy or reviewed-context mismatch requires quarantine and review."
)
M0302_ABSTAINED_RATIONALE: Final = (
    "Identity or categorical concordance evidence is not evaluable, so reconciliation abstains."
)
M0302_UNCERTAINTY_RATIONALES: Final = (
    "M03-02 consumes categorical lineage evidence and estimates no measurement uncertainty.",
    "M03-02 performs no sampling model.",
    "The deterministic reconciler fits no parameters.",
    "M03-02 executes no learned identity or activity model.",
    "No peptide or protein identity is inferred.",
    "Support is a deterministic lineage-closure decision.",
    "External identity and reference authorities are caller-declared.",
)
M0302_SENSITIVITY_NOTES: Final = (
    "Missing, unsupported, indeterminate, conflicting, or redacted evidence never becomes "
    "negative.",
    "Copy-number concordance can corroborate or downgrade but cannot create or merge identity.",
)


class ArtifactClaimRole(StrEnum):
    """Closed artifact roles consumed and reconciled by M03-02."""

    PEPTIDE_EVIDENCE_MANIFEST = "peptide_evidence_manifest"
    PROTEIN_GROUP_MANIFEST = "protein_group_manifest"
    AMBIGUITY_MANIFEST = "ambiguity_manifest"
    COMPLEX_ACTIVITY_INPUT_BUNDLE = "complex_activity_input_bundle"


class CopyNumberConcordanceState(StrEnum):
    """Closed copy-number concordance states."""

    CONCORDANT = "concordant"
    DISCORDANT = "discordant"
    INDETERMINATE = "indeterminate"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class ReconciliationDisposition(StrEnum):
    """Closed release dispositions."""

    RECONCILED = "reconciled"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class ApprovedCopyNumberMethod(FrozenModel):
    """One reviewed aggregate copy-number comparison method."""

    method_id: Identifier
    version: SemanticVersion
    evidence: ArtifactReference


class ApprovedDerivationMethod(FrozenModel):
    """One reviewed artifact-derivation method."""

    method_id: Identifier
    version: SemanticVersion
    evidence: ArtifactReference


class ProteinInferenceLineagePolicy(FrozenModel):
    """Reviewed bounds for one M03-02 reconciliation closure."""

    policy_id: Identifier
    version: SemanticVersion
    max_artifact_claims: int = Field(
        default=M0302_MAX_ARTIFACT_CLAIMS,
        ge=4,
        le=M0302_MAX_ARTIFACT_CLAIMS,
    )
    max_derivation_sources: int = Field(
        default=M0302_MAX_DERIVATION_SOURCES,
        ge=1,
        le=M0302_MAX_DERIVATION_SOURCES,
    )
    quarantine_on_cn_discordance: Literal[True] = True
    abstain_on_indeterminate_identity: Literal[True] = True
    approved_derivation_methods: tuple[ApprovedDerivationMethod, ...] = Field(
        min_length=1,
        max_length=64,
    )
    approved_cn_methods: tuple[ApprovedCopyNumberMethod, ...] = Field(
        min_length=1,
        max_length=64,
    )

    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("approved_derivation_methods", "approved_cn_methods")
    @classmethod
    def methods_are_unique(
        cls,
        values: tuple[ApprovedDerivationMethod, ...] | tuple[ApprovedCopyNumberMethod, ...],
    ) -> tuple[ApprovedDerivationMethod, ...] | tuple[ApprovedCopyNumberMethod, ...]:
        identities = [(item.method_id, item.version) for item in values]
        if len(identities) != len(set(identities)):
            raise ValueError("approved method identities must be unique")
        return values

    @model_validator(mode="after")
    def evidence_digests_are_unique(self) -> ProteinInferenceLineagePolicy:
        artifacts = (
            self.evidence,
            *(item.evidence for item in self.approved_derivation_methods),
            *(item.evidence for item in self.approved_cn_methods),
        )
        digests = tuple(item.digest for item in artifacts)
        if len(digests) != len(set(digests)):
            raise ValueError("policy evidence digests must be unique")
        identities = tuple((item.artifact_id, item.version) for item in artifacts)
        if len(identities) != len(set(identities)):
            raise ValueError("policy evidence artifact identities must be unique")
        return self


class ProteinInferenceArtifactClaim(FrozenModel):
    """Content-addressed, privacy-minimized node in the handoff DAG."""

    claim_id: Identifier
    role: ArtifactClaimRole
    artifact: ArtifactReference
    identity_entity_id: Identifier
    declared_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    producer_identity_resolution_digest: Sha256Digest
    producer_protocol_result_digest: Sha256Digest
    producer_search_space_digest: Sha256Digest
    evidence_state: Literal["observed"] | DeclaredUnresolvedState

    @field_validator("declared_subject_component_ids")
    @classmethod
    def subject_components_are_unique(
        cls,
        values: tuple[Sha256Digest, ...],
    ) -> tuple[Sha256Digest, ...]:
        if len(values) != len(set(values)):
            raise ValueError("declared subject component identifiers must be unique")
        return values


class ProteinInferenceArtifactDerivation(FrozenModel):
    """N-to-one derivation whose endpoints must close over submitted claims."""

    derivation_id: Identifier
    source_claim_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0302_MAX_DERIVATION_SOURCES,
    )
    target_claim_id: Identifier
    method_id: Identifier
    method_version: SemanticVersion
    evidence: ArtifactReference

    @model_validator(mode="after")
    def endpoints_are_unique_and_disjoint(self) -> ProteinInferenceArtifactDerivation:
        if len(self.source_claim_ids) != len(set(self.source_claim_ids)):
            raise ValueError("derivation source claim identifiers must be unique")
        if self.target_claim_id in self.source_claim_ids:
            raise ValueError("a derivation cannot consume its target claim")
        return self


class CopyNumberConcordanceReceipt(FrozenModel):
    """Aggregate concordance declaration; no locus-level or dosage values are exposed."""

    receipt_id: Identifier
    claim_id: Identifier
    identity_entity_id: Identifier
    state: CopyNumberConcordanceState
    method_id: Identifier
    method_version: SemanticVersion
    informative_feature_count: int = Field(ge=0, le=10_000_000)
    concordant_feature_count: int = Field(ge=0, le=10_000_000)
    discordant_feature_count: int = Field(ge=0, le=10_000_000)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def aggregate_counts_match_state(self) -> CopyNumberConcordanceReceipt:
        if (
            self.concordant_feature_count + self.discordant_feature_count
            != self.informative_feature_count
        ):
            raise ValueError("copy-number concordance counts do not close")
        if (
            self.state
            in {
                CopyNumberConcordanceState.INDETERMINATE,
                CopyNumberConcordanceState.MISSING,
                CopyNumberConcordanceState.UNSUPPORTED,
            }
            and self.informative_feature_count != 0
        ):
            raise ValueError("non-evaluable copy-number receipt cannot carry feature counts")
        if self.state is CopyNumberConcordanceState.CONCORDANT and (
            self.concordant_feature_count == 0 or self.discordant_feature_count != 0
        ):
            raise ValueError("concordant copy-number receipt requires only concordant features")
        if (
            self.state is CopyNumberConcordanceState.DISCORDANT
            and self.discordant_feature_count == 0
        ):
            raise ValueError("discordant copy-number receipt requires discordant features")
        return self


class ReconcileProteinInferenceIdentityLineageRequest(FrozenModel):
    """One exact, authorized protein-inference lineage closure request."""

    operation: Literal["reconcile_protein_inference_identity_lineage"] = M0302_OPERATION
    contract_version: Literal["1.0.0"] = M0302_CONTRACT_VERSION
    context: ExecutionContext
    identity_resolution: IdentityLineageResolution
    protocol_result: ProteinInferenceProtocolConformanceResult
    policy: ProteinInferenceLineagePolicy
    artifact_claims: tuple[ProteinInferenceArtifactClaim, ...] = Field(
        min_length=4,
        max_length=M0302_MAX_ARTIFACT_CLAIMS,
    )
    derivations: tuple[ProteinInferenceArtifactDerivation, ...] = Field(
        min_length=M0302_DERIVATION_COUNT,
        max_length=M0302_DERIVATION_COUNT,
    )
    cn_receipts: tuple[CopyNumberConcordanceReceipt, ...] = Field(
        min_length=M0302_CN_RECEIPT_COUNT,
        max_length=M0302_CN_RECEIPT_COUNT,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> ReconcileProteinInferenceIdentityLineageRequest:
        _require_authorized_context(self.context)
        if self.policy.reviewed_at > self.context.occurred_at:
            raise ValueError("lineage policy cannot postdate reconciliation")
        if (
            self.identity_resolution.resolved_at > self.context.occurred_at
            or self.protocol_result.completed_at > self.context.occurred_at
        ):
            raise ValueError("upstream result cannot postdate reconciliation")
        if self.protocol_result.completed_at < self.identity_resolution.resolved_at:
            raise ValueError("M03-01 protocol result cannot predate its M01-02 identity binding")
        identity_digest = self.identity_resolution.resolution_digest
        if (
            self.context.references.identity_lineage.binding_digest != identity_digest
            or self.protocol_result.receipt.identity_subject_digest != identity_digest
        ):
            raise ValueError("M03-02 identity chain does not bind the exact M01-02 resolution")
        config_hash = configuration_digest(self.policy)
        if self.context.references.approved_configuration.evidence.digest != config_hash:
            raise ValueError("approved configuration does not bind the M03-02 policy")
        if len(self.artifact_claims) > self.policy.max_artifact_claims:
            raise ValueError("artifact claims exceed the active policy")
        _validate_unique_ids(self.artifact_claims, "claim_id", "artifact claim")
        _validate_unique_ids(self.derivations, "derivation_id", "artifact derivation")
        _validate_unique_ids(self.cn_receipts, "receipt_id", "copy-number receipt")
        _validate_evidence_identity_consistency(self)
        claims = {claim.claim_id: claim for claim in self.artifact_claims}
        upstream_nodes = {node.entity_id: node for node in self.identity_resolution.graph.nodes}
        for claim in self.artifact_claims:
            node = upstream_nodes.get(claim.identity_entity_id)
            if node is None:
                raise ValueError("artifact claim references an unknown identity entity")
            if node.kind is not EntityKind.DERIVED_OBJECT:
                raise ValueError("protein-inference artifacts require derived-object anchors")
        _validate_artifact_dag(self.derivations, claims, self.policy)
        _validate_subject_propagation(self.derivations, claims, upstream_nodes)
        _validate_cn_receipts(self.cn_receipts, claims, self.policy)
        if len(canonical_json_bytes(normalized_request(self))) > M0302_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M03-02 request exceeds the 4 MiB ingress bound")
        return self


def _validate_unique_ids(
    values: tuple[object, ...],
    field: str,
    label: str,
) -> None:
    identifiers = tuple(getattr(item, field) for item in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label} identifiers must be unique")


def _validate_evidence_identity_consistency(
    request: ReconcileProteinInferenceIdentityLineageRequest,
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
        *(item.evidence for item in request.policy.approved_cn_methods),
        *(derivation.evidence for derivation in request.derivations),
        *(receipt.evidence for receipt in request.cn_receipts),
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
    derivations: tuple[ProteinInferenceArtifactDerivation, ...],
    claims: dict[Identifier, ProteinInferenceArtifactClaim],
    policy: ProteinInferenceLineagePolicy,
) -> None:
    roles: dict[ArtifactClaimRole, set[Identifier]] = {
        role: {claim_id for claim_id, claim in claims.items() if claim.role is role}
        for role in ArtifactClaimRole
    }
    if (
        not roles[ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST]
        or len(roles[ArtifactClaimRole.PROTEIN_GROUP_MANIFEST]) != 1
        or len(roles[ArtifactClaimRole.AMBIGUITY_MANIFEST]) != 1
        or len(roles[ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE]) != 1
    ):
        raise ValueError("artifact DAG requires peptide roots and one group, ambiguity, and bundle")
    producers: dict[Identifier, ProteinInferenceArtifactDerivation] = {}
    approved = {(item.method_id, item.version) for item in policy.approved_derivation_methods}
    for derivation in derivations:
        endpoints = set(derivation.source_claim_ids) | {derivation.target_claim_id}
        if not endpoints.issubset(claims):
            raise ValueError("artifact derivation references an unknown claim")
        if len(derivation.source_claim_ids) > policy.max_derivation_sources:
            raise ValueError("artifact derivation sources exceed the active policy")
        if (derivation.method_id, derivation.method_version) not in approved:
            raise ValueError("artifact derivation method is not approved")
        if derivation.target_claim_id in producers:
            raise ValueError("artifact claim cannot have multiple producers")
        producers[derivation.target_claim_id] = derivation
    peptide_ids = roles[ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST]
    group_id = next(iter(roles[ArtifactClaimRole.PROTEIN_GROUP_MANIFEST]))
    ambiguity_id = next(iter(roles[ArtifactClaimRole.AMBIGUITY_MANIFEST]))
    bundle_id = next(iter(roles[ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE]))
    if set(producers) != {group_id, ambiguity_id, bundle_id}:
        raise ValueError("artifact DAG requires exactly one producer for every non-root")
    if set(producers[group_id].source_claim_ids) != peptide_ids:
        raise ValueError("protein-group manifest must consume every peptide-evidence root")
    if producers[ambiguity_id].source_claim_ids != (group_id,):
        raise ValueError("ambiguity manifest must consume exactly the protein-group manifest")
    if set(producers[bundle_id].source_claim_ids) != {group_id, ambiguity_id}:
        raise ValueError("complex-activity bundle requires group and ambiguity parents")


def _validate_cn_receipts(
    receipts: tuple[CopyNumberConcordanceReceipt, ...],
    claims: dict[Identifier, ProteinInferenceArtifactClaim],
    policy: ProteinInferenceLineagePolicy,
) -> None:
    receipt = receipts[0]
    claim = claims.get(receipt.claim_id)
    if claim is None or claim.role is not ArtifactClaimRole.PROTEIN_GROUP_MANIFEST:
        raise ValueError("copy-number receipt must bind the protein-group manifest")
    if receipt.identity_entity_id != claim.identity_entity_id:
        raise ValueError("copy-number receipt identity does not match its protein-group claim")
    approved = {(item.method_id, item.version) for item in policy.approved_cn_methods}
    if (
        receipt.state is not CopyNumberConcordanceState.UNSUPPORTED
        and (receipt.method_id, receipt.method_version) not in approved
    ):
        raise ValueError("evaluable copy-number receipt method is not approved")


def _validate_subject_propagation(
    derivations: tuple[ProteinInferenceArtifactDerivation, ...],
    claims: dict[Identifier, ProteinInferenceArtifactClaim],
    upstream_nodes: dict[Identifier, ResolvedIdentityNode],
) -> None:
    subjects: dict[Identifier, tuple[Sha256Digest, ...]] = {}
    derivations_by_target = {derivation.target_claim_id: derivation for derivation in derivations}
    for role in ArtifactClaimRole:
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
            if len(propagated) > M0302_MAX_SUBJECT_COMPONENT_IDS:
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
        raise ValueError("protein-inference lineage reconciliation is not authorized")


class ReconciliationFindingCode(StrEnum):
    UPSTREAM_IDENTITY_UNRESOLVED = "upstream_identity_unresolved"
    UPSTREAM_PROTOCOL_NONCONFORMANT = "upstream_protocol_nonconformant"
    IDENTITY_NOT_EVALUABLE = "identity_not_evaluable"
    IDENTITY_SWAP = "identity_swap"
    CROSS_PATIENT_LINK = "cross_patient_link"
    ARTIFACT_LINEAGE_COLLISION = "artifact_lineage_collision"
    DUPLICATE_CONTENT_RETAINED = "duplicate_content_retained"
    PRODUCER_IDENTITY_DRIFT = "producer_identity_drift"
    PRODUCER_PROTOCOL_DRIFT = "producer_protocol_drift"
    PRODUCER_SEARCH_SPACE_DRIFT = "producer_search_space_drift"
    ARTIFACT_EVIDENCE_NOT_EVALUABLE = "artifact_evidence_not_evaluable"
    CN_DISCORDANT = "cn_discordant"
    CN_NOT_EVALUABLE = "cn_not_evaluable"


class ReconciliationFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class ProteinInferenceLineageFinding(FrozenModel):
    code: ReconciliationFindingCode
    action: ReconciliationFindingAction
    claim_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0302_MAX_ARTIFACT_CLAIMS)
    derivation_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0302_DERIVATION_COUNT)
    evidence_basis_digest: Sha256Digest

    @model_validator(mode="after")
    def references_are_unique(self) -> ProteinInferenceLineageFinding:
        if len(self.claim_ids) != len(set(self.claim_ids)) or len(self.derivation_ids) != len(
            set(self.derivation_ids)
        ):
            raise ValueError("finding references must be unique")
        return self


class ResolvedProteinInferenceArtifact(FrozenModel):
    claim_id: Identifier
    role: ArtifactClaimRole
    artifact_digest: Sha256Digest
    identity_entity_id: Identifier
    lineage_path_digest: Sha256Digest
    declared_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    resolved_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    evidence_state: Literal["observed"] | DeclaredUnresolvedState
    finding_codes: tuple[ReconciliationFindingCode, ...] = Field(default=(), max_length=16)


class ResolvedProteinInferenceDerivation(FrozenModel):
    derivation_id: Identifier
    source_claim_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0302_MAX_DERIVATION_SOURCES
    )
    target_claim_id: Identifier
    method_id: Identifier
    method_version: SemanticVersion
    evidence_digest: Sha256Digest
    propagated_subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)


class ResolvedProteinInferenceLineageGraph(FrozenModel):
    artifacts: tuple[ResolvedProteinInferenceArtifact, ...] = Field(
        min_length=4, max_length=M0302_MAX_ARTIFACT_CLAIMS
    )
    derivations: tuple[ResolvedProteinInferenceDerivation, ...] = Field(
        min_length=M0302_DERIVATION_COUNT,
        max_length=M0302_DERIVATION_COUNT,
    )
    graph_digest: Sha256Digest

    @model_validator(mode="after")
    def graph_is_closed_and_digest_is_exact(self) -> ResolvedProteinInferenceLineageGraph:
        _validate_unique_ids(self.artifacts, "claim_id", "resolved artifact")
        _validate_unique_ids(self.derivations, "derivation_id", "resolved derivation")
        artifacts = {artifact.claim_id: artifact for artifact in self.artifacts}
        roles = {
            role: {artifact.claim_id for artifact in self.artifacts if artifact.role is role}
            for role in ArtifactClaimRole
        }
        if (
            not roles[ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST]
            or len(roles[ArtifactClaimRole.PROTEIN_GROUP_MANIFEST]) != 1
            or len(roles[ArtifactClaimRole.AMBIGUITY_MANIFEST]) != 1
            or len(roles[ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE]) != 1
        ):
            raise ValueError("resolved graph does not contain the exact four-role shape")
        producers: dict[Identifier, ResolvedProteinInferenceDerivation] = {}
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
        group_id = next(iter(roles[ArtifactClaimRole.PROTEIN_GROUP_MANIFEST]))
        ambiguity_id = next(iter(roles[ArtifactClaimRole.AMBIGUITY_MANIFEST]))
        bundle_id = next(iter(roles[ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE]))
        if (
            set(producers) != {group_id, ambiguity_id, bundle_id}
            or set(producers[group_id].source_claim_ids)
            != roles[ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST]
            or producers[ambiguity_id].source_claim_ids != (group_id,)
            or set(producers[bundle_id].source_claim_ids) != {group_id, ambiguity_id}
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
                ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION
                not in artifacts[claim_id].finding_codes
                for claim_id in (*derivation.source_claim_ids, target_id)
            ):
                raise ValueError(
                    "resolved graph must retain divergent physical-lineage paths as a collision"
                )
        for artifact in self.artifacts:
            if (
                len(artifact.declared_subject_component_ids)
                != len(set(artifact.declared_subject_component_ids))
                or len(artifact.resolved_subject_component_ids)
                != len(set(artifact.resolved_subject_component_ids))
                or len(artifact.finding_codes) != len(set(artifact.finding_codes))
            ):
                raise ValueError("resolved artifact collections must be unique")
        for derivation in self.derivations:
            if len(derivation.propagated_subject_component_ids) != len(
                set(derivation.propagated_subject_component_ids)
            ):
                raise ValueError("resolved derivation subjects must be unique")
        if self.graph_digest != resolved_graph_digest(self):
            raise ValueError("resolved M03-02 graph digest does not match its content")
        return self


class ProteinInferenceLineageReceipt(FrozenModel):
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    protocol_schema_digest: Sha256Digest
    search_space_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    graph_digest: Sha256Digest
    parent_target: Literal["complex_activity"] = M0302_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    disposition: ReconciliationDisposition


def derive_reconciliation(  # noqa: PLR0912, PLR0915 - explicit closed finding matrix.
    request: ReconcileProteinInferenceIdentityLineageRequest,
) -> tuple[
    ResolvedProteinInferenceLineageGraph,
    tuple[ProteinInferenceLineageFinding, ...],
    ReconciliationDisposition,
]:
    """Derive the exact privacy-minimized graph, findings, and disposition."""

    claims = {claim.claim_id: claim for claim in request.artifact_claims}
    upstream_nodes = {node.entity_id: node for node in request.identity_resolution.graph.nodes}
    subjects: dict[Identifier, tuple[Sha256Digest, ...]] = {}
    finding_codes: dict[Identifier, set[ReconciliationFindingCode]] = {
        claim_id: set() for claim_id in claims
    }
    finding_specs: set[
        tuple[
            ReconciliationFindingCode,
            ReconciliationFindingAction,
            tuple[Identifier, ...],
            tuple[Identifier, ...],
            Sha256Digest,
        ]
    ] = set()

    def add_finding(
        code: ReconciliationFindingCode,
        action: ReconciliationFindingAction,
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

    if request.identity_resolution.decision.value != "resolved":
        add_finding(
            ReconciliationFindingCode.UPSTREAM_IDENTITY_UNRESOLVED,
            ReconciliationFindingAction.ABSTAIN,
            basis=request.identity_resolution.resolution_digest,
        )
    if request.protocol_result.disposition.value != "conformant":
        add_finding(
            ReconciliationFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT,
            ReconciliationFindingAction.QUARANTINE,
            basis=request.protocol_result.result_digest,
        )

    derivations_by_target = {
        derivation.target_claim_id: derivation for derivation in request.derivations
    }
    role_order = (
        ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST,
        ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
        ArtifactClaimRole.AMBIGUITY_MANIFEST,
        ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
    )
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
                        _lineage_path_digest(
                            request.identity_resolution,
                            claims[claim_id].identity_entity_id,
                        ),
                    )
                    for claim_id in participating_ids
                }
                if len(lineage_contexts) > 1:
                    add_finding(
                        ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION,
                        ReconciliationFindingAction.QUARANTINE,
                        claim_ids=participating_ids,
                        derivation_ids=(producer.derivation_id,),
                        basis=tuple(sorted(lineage_contexts)),
                    )
            if not node_subjects or not propagated:
                add_finding(
                    ReconciliationFindingCode.IDENTITY_NOT_EVALUABLE,
                    ReconciliationFindingAction.ABSTAIN,
                    claim_ids=(claim.claim_id,),
                    basis=(node_subjects, propagated),
                )
            if tuple(sorted(claim.declared_subject_component_ids)) != node_subjects or (
                producer is not None and propagated != node_subjects
            ):
                add_finding(
                    ReconciliationFindingCode.IDENTITY_SWAP,
                    ReconciliationFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    derivation_ids=() if producer is None else (producer.derivation_id,),
                    basis=(claim.declared_subject_component_ids, node_subjects, propagated),
                )
            if len(set(node_subjects) | set(propagated)) > 1:
                add_finding(
                    ReconciliationFindingCode.CROSS_PATIENT_LINK,
                    ReconciliationFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=(node_subjects, propagated),
                )
            if (
                claim.producer_identity_resolution_digest
                != request.identity_resolution.resolution_digest
            ):
                add_finding(
                    ReconciliationFindingCode.PRODUCER_IDENTITY_DRIFT,
                    ReconciliationFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_identity_resolution_digest,
                )
            if claim.producer_protocol_result_digest != request.protocol_result.result_digest:
                add_finding(
                    ReconciliationFindingCode.PRODUCER_PROTOCOL_DRIFT,
                    ReconciliationFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_protocol_result_digest,
                )
            if (
                claim.producer_search_space_digest
                != request.protocol_result.receipt.search_space_digest
            ):
                add_finding(
                    ReconciliationFindingCode.PRODUCER_SEARCH_SPACE_DRIFT,
                    ReconciliationFindingAction.QUARANTINE,
                    claim_ids=(claim.claim_id,),
                    basis=claim.producer_search_space_digest,
                )
            if claim.evidence_state != "observed":
                add_finding(
                    ReconciliationFindingCode.ARTIFACT_EVIDENCE_NOT_EVALUABLE,
                    ReconciliationFindingAction.ABSTAIN,
                    claim_ids=(claim.claim_id,),
                    basis=claim.evidence_state,
                )

    digest_groups: dict[Sha256Digest, list[ProteinInferenceArtifactClaim]] = {}
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
                _lineage_path_digest(request.identity_resolution, claim.identity_entity_id),
            )
            for claim in grouped
        }
        code = (
            ReconciliationFindingCode.DUPLICATE_CONTENT_RETAINED
            if len(contexts) == 1
            else ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION
        )
        add_finding(
            code,
            ReconciliationFindingAction.QUARANTINE,
            claim_ids=tuple(item.claim_id for item in grouped),
            basis=(digest, tuple(sorted(contexts, key=canonical_json_bytes))),
        )

    identity_groups: dict[
        tuple[Identifier, SemanticVersion], list[ProteinInferenceArtifactClaim]
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
            ReconciliationFindingCode.ARTIFACT_LINEAGE_COLLISION,
            ReconciliationFindingAction.QUARANTINE,
            claim_ids=tuple(item.claim_id for item in grouped),
            basis=(identity, tuple(sorted(declarations))),
        )

    cn = request.cn_receipts[0]
    if cn.state is CopyNumberConcordanceState.DISCORDANT:
        add_finding(
            ReconciliationFindingCode.CN_DISCORDANT,
            ReconciliationFindingAction.QUARANTINE,
            claim_ids=(cn.claim_id,),
            basis=cn,
        )
    elif cn.state in {
        CopyNumberConcordanceState.INDETERMINATE,
        CopyNumberConcordanceState.MISSING,
        CopyNumberConcordanceState.UNSUPPORTED,
    }:
        add_finding(
            ReconciliationFindingCode.CN_NOT_EVALUABLE,
            ReconciliationFindingAction.ABSTAIN,
            claim_ids=(cn.claim_id,),
            basis=cn,
        )

    artifacts = tuple(
        ResolvedProteinInferenceArtifact(
            claim_id=claim.claim_id,
            role=claim.role,
            artifact_digest=claim.artifact.digest,
            identity_entity_id=claim.identity_entity_id,
            lineage_path_digest=_lineage_path_digest(
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
        ResolvedProteinInferenceDerivation(
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
        "artifacts": artifacts,
        "derivations": resolved_derivations,
        "graph_digest": "sha256:" + ("0" * 64),
    }
    graph_payload["graph_digest"] = resolved_graph_digest(graph_payload)
    graph = ResolvedProteinInferenceLineageGraph.model_validate(graph_payload, strict=True)
    findings = tuple(
        ProteinInferenceLineageFinding(
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
        ReconciliationDisposition.QUARANTINED
        if ReconciliationFindingAction.QUARANTINE in actions
        else ReconciliationDisposition.ABSTAINED
        if ReconciliationFindingAction.ABSTAIN in actions
        else ReconciliationDisposition.RECONCILED
    )
    return graph, findings, disposition


def _lineage_path_digest(
    resolution: IdentityLineageResolution,
    entity_id: Identifier,
) -> Sha256Digest:
    reverse: dict[Identifier, list[tuple[Identifier, tuple[Identifier, ...]]]] = {}
    for operation in resolution.graph.operations:
        for target in operation.target_entity_ids:
            reverse.setdefault(target, []).append(
                (operation.operation_id, operation.source_entity_ids)
            )
    nodes = {entity_id}
    operations: set[Identifier] = set()
    pending = [entity_id]
    while pending:
        target = pending.pop()
        for operation_id, sources in reverse.get(target, []):
            operations.add(operation_id)
            for source in sources:
                if source not in nodes:
                    nodes.add(source)
                    pending.append(source)
    return sha256_digest(
        {"entity_ids": tuple(sorted(nodes)), "operation_ids": tuple(sorted(operations))}
    )


def reconciliation_evidence_index(
    request: ReconcileProteinInferenceIdentityLineageRequest,
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
        *(item.evidence for item in request.policy.approved_cn_methods),
        *(item.artifact for item in request.artifact_claims),
        *(item.evidence for item in request.derivations),
        *(item.evidence for item in request.cn_receipts),
    )
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item for item in artifacts
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0302_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
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


def expected_support(disposition: ReconciliationDisposition) -> SupportDecision:
    if disposition is ReconciliationDisposition.RECONCILED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="protein_inference_lineage_reconciled",
            rationale=M0302_RECONCILED_RATIONALE,
        )
    if disposition is ReconciliationDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="protein_inference_lineage_quarantined",
            rationale=M0302_QUARANTINED_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="protein_inference_lineage_abstained",
        rationale=M0302_ABSTAINED_RATIONALE,
    )


def expected_uncertainty() -> UncertaintyProfile:
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0302_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0302_SENSITIVITY_NOTES,
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="identity_lineage_reconciliation_only",
            statement=(
                "This result reconciles caller-declared protein-inference artifact lineage; "
                "it does not authenticate a person, infer identity, relabel upstream evidence, "
                "or establish that a peptide or protein was observed."
            ),
        ),
        Limitation(
            code="cn_concordance_and_activity_not_inferred",
            statement=(
                "Copy-number concordance is categorical corroborating evidence only; it cannot "
                "merge identity or produce protein, complex, kinase, subtype, treatment, or "
                "clinical claims."
            ),
        ),
    )


def expected_provenance(
    request: ReconcileProteinInferenceIdentityLineageRequest,
    request_hash: Sha256Digest,
    graph_hash: Sha256Digest,
) -> ProvenanceRecord:
    config_hash = configuration_digest(request.policy)
    active_policy_hash = policy_digest(request.policy)
    evidence = reconciliation_evidence_index(request)
    controls = expected_control_decisions(request.context)
    input_digests = tuple(
        sorted(
            {
                request_hash,
                request.identity_resolution.resolution_digest,
                request.protocol_result.result_digest,
                request.protocol_result.protocol_digest,
                request.protocol_result.receipt.search_space_digest,
                active_policy_hash,
                config_hash,
                graph_hash,
                *(item.reference.digest for item in evidence),
                *(item.evidence_digest for item in controls),
            }
        )
    )
    refs = request.context.references
    suffix = request_hash.removeprefix("sha256:")
    return ProvenanceRecord(
        activity_id=f"activity.m0302.{suffix}",
        actor_id=request.context.actor_id,
        module_id=M0302_MODULE_ID,
        module_version=M0302_CONTRACT_VERSION,
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
    findings: tuple[ProteinInferenceLineageFinding, ...],
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


class ProteinInferenceIdentityLineageResolution(NonInferenceResultModel):
    output_type: Literal["protein_inference_identity_lineage_resolution"] = (
        "protein_inference_identity_lineage_resolution"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0302_CONTRACT_VERSION
    request_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    graph_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ReconcileProteinInferenceIdentityLineageRequest
    receipt: ProteinInferenceLineageReceipt
    graph: ResolvedProteinInferenceLineageGraph
    findings: tuple[ProteinInferenceLineageFinding, ...] = Field(
        default=(), max_length=M0302_MAX_FINDINGS
    )
    disposition: ReconciliationDisposition
    parent_target: Literal["complex_activity"] = M0302_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    # Identical caller-declared artifacts may legitimately support several controls;
    # the role-specific provenance records retain those bindings while this index
    # contains the exact de-duplicated content-reference set.
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> ProteinInferenceIdentityLineageResolution:
        request_hash = canonical_request_digest(self.request)
        active_policy_hash = policy_digest(self.request.policy)
        config_hash = configuration_digest(self.request.policy)
        graph, findings, disposition = derive_reconciliation(self.request)
        expected_receipt = ProteinInferenceLineageReceipt(
            identity_resolution_digest=self.request.identity_resolution.resolution_digest,
            protocol_result_digest=self.request.protocol_result.result_digest,
            protocol_schema_digest=self.request.protocol_result.protocol_digest,
            search_space_digest=self.request.protocol_result.receipt.search_space_digest,
            policy_digest=active_policy_hash,
            configuration_digest=config_hash,
            graph_digest=graph.graph_digest,
            disposition=disposition,
        )
        suffix = request_hash.removeprefix("sha256:")
        if (
            self.result_id != f"result.m0302.{suffix}"
            or self.request_digest != request_hash
            or self.identity_resolution_digest != self.request.identity_resolution.resolution_digest
            or self.protocol_result_digest != self.request.protocol_result.result_digest
            or self.policy_digest != active_policy_hash
            or self.configuration_digest != config_hash
            or self.graph_digest != graph.graph_digest
            or self.receipt != expected_receipt
            or self.graph.graph_digest != graph.graph_digest
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
            != tuple(sorted(reconciliation_evidence_index(self.request), key=canonical_json_bytes))
            or tuple(sorted(self.limitations, key=canonical_json_bytes))
            != tuple(sorted(expected_limitations(), key=canonical_json_bytes))
            or self.human_review_required
            != (disposition is not ReconciliationDisposition.RECONCILED)
            or self.completed_at != self.request.context.occurred_at
        ):
            raise ValueError("M03-02 result contradicts its embedded reconciliation request")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M03-02 result digest does not match its canonical content")
        return self


__all__ = [name for name in globals() if not name.startswith("_")]
