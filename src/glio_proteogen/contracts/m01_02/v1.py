"""Version 1 contracts for deterministic identity and lineage reconciliation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal, Protocol

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m01_02.canonical import (
    graph_digest,
    policy_digest,
    resolution_core_digest,
    resolution_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    EvidenceReference,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

M0102_CONTRACT_VERSION: Final = "1.0.0"
M0102_MODULE_VERSION: Final[SemanticVersion] = "1.0.0"
M0102_IDENTITY_LIMITATION_CODE: Final = "identity_lineage_only"
M0102_AUTHORITY_LIMITATION_CODE: Final = "external_identity_authority_unverified"
M0102_RESERVED_LIMITATION_CODES: Final = frozenset(
    {M0102_IDENTITY_LIMITATION_CODE, M0102_AUTHORITY_LIMITATION_CODE}
)
M0102_MAX_ENTITIES: Final = 10_000
M0102_MAX_OPERATIONS: Final = 40_000
M0102_MAX_ASSERTIONS: Final = 20_000
M0102_MAX_OBSERVATIONS: Final = 50_000
M0102_MAX_INFORMATIVE_LOCI: Final = M0102_MAX_OBSERVATIONS * 10_000_000
M0102_MAX_COMPONENT_SIZE: Final = 256
M0102_MAX_DEPTH: Final = 64
M0102_MAX_EVIDENCE: Final = 50_000
M0102_MAX_EVIDENCE_PER_ITEM: Final = 64
M0102_MAX_ISSUES: Final = 1_000
_MINIMUM_MULTI_CARDINALITY: Final = 2
_DERIVED_DIGEST_SENTINEL: Final[Sha256Digest] = "sha256:" + ("0" * 64)

ChannelLabel = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"),
]


def _unique_evidence(
    values: tuple[ArtifactReference, ...],
) -> tuple[ArtifactReference, ...]:
    identities = [
        (value.artifact_id, value.version, value.digest, value.media_type) for value in values
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("evidence references must be unique within one declaration")
    return values


class EntityKind(StrEnum):
    PATIENT = "patient"
    SPECIMEN = "specimen"
    ALIQUOT = "aliquot"
    SECTION = "section"
    ANALYTE = "analyte"
    RUN = "run"
    DERIVED_OBJECT = "derived_object"


class EntityComposition(StrEnum):
    SINGLE_SUBJECT = "single_subject"
    MULTI_SUBJECT = "multi_subject"
    UNKNOWN = "unknown"


class LineageOperationKind(StrEnum):
    COLLECTED_FROM = "collected_from"
    SUBDIVIDED_FROM = "subdivided_from"
    SECTIONED_FROM = "sectioned_from"
    EXTRACTED_FROM = "extracted_from"
    ACQUIRED_FROM = "acquired_from"
    COMPUTED_FROM = "computed_from"
    POOLED_FROM = "pooled_from"
    DEMULTIPLEXED_FROM = "demultiplexed_from"


M0102_ORDINARY_TRANSITIONS: Final = frozenset(
    {
        (LineageOperationKind.COLLECTED_FROM, EntityKind.PATIENT, EntityKind.SPECIMEN),
        (LineageOperationKind.SUBDIVIDED_FROM, EntityKind.SPECIMEN, EntityKind.SPECIMEN),
        (LineageOperationKind.SUBDIVIDED_FROM, EntityKind.SPECIMEN, EntityKind.ALIQUOT),
        (LineageOperationKind.SUBDIVIDED_FROM, EntityKind.ALIQUOT, EntityKind.ALIQUOT),
        (LineageOperationKind.SECTIONED_FROM, EntityKind.SPECIMEN, EntityKind.SECTION),
        (LineageOperationKind.SECTIONED_FROM, EntityKind.ALIQUOT, EntityKind.SECTION),
        (LineageOperationKind.EXTRACTED_FROM, EntityKind.SPECIMEN, EntityKind.ANALYTE),
        (LineageOperationKind.EXTRACTED_FROM, EntityKind.ALIQUOT, EntityKind.ANALYTE),
        (LineageOperationKind.EXTRACTED_FROM, EntityKind.SECTION, EntityKind.ANALYTE),
        (LineageOperationKind.ACQUIRED_FROM, EntityKind.ANALYTE, EntityKind.RUN),
        (LineageOperationKind.COMPUTED_FROM, EntityKind.RUN, EntityKind.DERIVED_OBJECT),
        (
            LineageOperationKind.COMPUTED_FROM,
            EntityKind.DERIVED_OBJECT,
            EntityKind.DERIVED_OBJECT,
        ),
    }
)
M0102_SPECIAL_LINEAGE_KINDS: Final = frozenset(
    {EntityKind.ALIQUOT, EntityKind.ANALYTE}
)


class ConcordanceClassification(StrEnum):
    CONCORDANT = "concordant"
    DISCORDANT = "discordant"
    INDETERMINATE = "indeterminate"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    EXCLUDED_DEPENDENT = "excluded_dependent"


class ResolutionDecision(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CONFLICTED = "conflicted"
    QUARANTINED = "quarantined"


class IdentityIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IdentityIssueAction(StrEnum):
    RECORD = "record"
    REJECT = "reject"
    QUARANTINE = "quarantine"
    HUMAN_REVIEW = "human_review"


class AssertionDispositionState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class ScopedIdentityToken(FrozenModel):
    """Externally issued project-scoped HMAC token; never a direct identifier."""

    issuer_id: Identifier
    namespace_id: Identifier
    scope_id: Identifier
    key_id: Identifier
    token_version: SemanticVersion
    entity_kind: EntityKind
    token_digest: Sha256Digest
    evidence: ArtifactReference


class IdentityEntity(FrozenModel):
    entity_id: Identifier
    kind: EntityKind
    composition: EntityComposition
    identity_tokens: tuple[ScopedIdentityToken, ...] = Field(default=(), max_length=64)
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def tokens_match_entity(self) -> IdentityEntity:
        if any(token.entity_kind is not self.kind for token in self.identity_tokens):
            raise ValueError("identity token kind must match its entity")
        scopes = [
            (
                token.issuer_id,
                token.namespace_id,
                token.scope_id,
                token.key_id,
                token.token_version,
            )
            for token in self.identity_tokens
        ]
        if len(scopes) != len(set(scopes)):
            raise ValueError("identity token authority scopes must be unique per entity")
        if self.kind is EntityKind.PATIENT and self.composition is EntityComposition.MULTI_SUBJECT:
            raise ValueError("a patient entity cannot be declared multi-subject")
        return self


class SameAsAssertion(FrozenModel):
    assertion_type: Literal["same_as"] = "same_as"
    assertion_id: Identifier
    left_entity_id: Identifier
    right_entity_id: Identifier
    authority_decision_id: Identifier
    policy_version: SemanticVersion
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def endpoints_are_distinct(self) -> SameAsAssertion:
        if self.left_entity_id == self.right_entity_id:
            raise ValueError("same-as endpoints must be distinct")
        return self


class DifferentFromAssertion(FrozenModel):
    assertion_type: Literal["different_from"] = "different_from"
    assertion_id: Identifier
    left_entity_id: Identifier
    right_entity_id: Identifier
    authority_decision_id: Identifier
    policy_version: SemanticVersion
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def endpoints_are_distinct(self) -> DifferentFromAssertion:
        if self.left_entity_id == self.right_entity_id:
            raise ValueError("different-from endpoints must be distinct")
        return self


class SubjectMembershipAssertion(FrozenModel):
    assertion_type: Literal["subject_membership"] = "subject_membership"
    assertion_id: Identifier
    entity_id: Identifier
    subject_entity_id: Identifier
    authority_decision_id: Identifier
    policy_version: SemanticVersion
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def endpoints_are_distinct(self) -> SubjectMembershipAssertion:
        if self.entity_id == self.subject_entity_id:
            raise ValueError("subject membership endpoints must be distinct")
        return self


IdentityAssertion = Annotated[
    SameAsAssertion | DifferentFromAssertion | SubjectMembershipAssertion,
    Field(discriminator="assertion_type"),
]


class DemultiplexChannel(FrozenModel):
    channel_id: ChannelLabel
    source_entity_id: Identifier
    target_entity_id: Identifier
    tag_digest: Sha256Digest
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)


class LineageOperation(FrozenModel):
    operation_id: Identifier
    kind: LineageOperationKind
    source_entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    target_entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    mixed_subject: bool = False
    channels: tuple[DemultiplexChannel, ...] = Field(default=(), max_length=256)
    authority_decision_id: Identifier
    policy_version: SemanticVersion
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def cardinality_matches_operation(self) -> LineageOperation:
        if len(self.source_entity_ids) != len(set(self.source_entity_ids)) or len(
            self.target_entity_ids
        ) != len(set(self.target_entity_ids)):
            raise ValueError("lineage operation endpoints must be unique")
        if set(self.source_entity_ids) & set(self.target_entity_ids):
            raise ValueError("lineage operations cannot contain a self endpoint")
        if self.kind is LineageOperationKind.POOLED_FROM:
            if (
                len(self.source_entity_ids) < _MINIMUM_MULTI_CARDINALITY
                or len(self.target_entity_ids) != 1
            ):
                raise ValueError("pooled-from operations require N-to-one cardinality")
            if self.channels:
                raise ValueError("pooled-from operations cannot carry demultiplex channels")
        elif self.kind is LineageOperationKind.DEMULTIPLEXED_FROM:
            if (
                len(self.source_entity_ids) != 1
                or len(self.target_entity_ids) < _MINIMUM_MULTI_CARDINALITY
            ):
                raise ValueError("demultiplexed-from operations require one-to-N cardinality")
            expected = set(self.target_entity_ids)
            actual = {channel.target_entity_id for channel in self.channels}
            if actual != expected or len(self.channels) != len(expected):
                raise ValueError("demultiplex channels must cover every target exactly once")
            source_id = self.source_entity_ids[0]
            if any(channel.source_entity_id != source_id for channel in self.channels):
                raise ValueError("demultiplex channels must reference the sole source")
            channel_ids = [channel.channel_id for channel in self.channels]
            tag_digests = [channel.tag_digest for channel in self.channels]
            if len(channel_ids) != len(set(channel_ids)) or len(tag_digests) != len(
                set(tag_digests)
            ):
                raise ValueError("demultiplex channels and tag digests must be unique")
        elif (
            len(self.source_entity_ids) != 1
            or len(self.target_entity_ids) != 1
            or self.channels
            or self.mixed_subject
        ):
            raise ValueError("ordinary lineage operations require one-to-one cardinality")
        if self.kind is not LineageOperationKind.POOLED_FROM and self.mixed_subject:
            raise ValueError("only a pooled-from operation may declare mixed-subject input")
        return self


class ConcordanceObservation(FrozenModel):
    """Privacy-minimized aggregate; it cannot authorize an identity union."""

    observation_id: Identifier
    root_observation_id: Identifier
    left_entity_id: Identifier
    right_entity_id: Identifier
    target_id: Identifier
    classification: ConcordanceClassification
    informative_count: int = Field(ge=0, le=10_000_000)
    concordant_count: int = Field(ge=0, le=10_000_000)
    discordant_count: int = Field(ge=0, le=10_000_000)
    method_id: Identifier
    method_version: SemanticVersion
    assay_lineage_digest: Sha256Digest
    panel_digest: Sha256Digest
    reference_digest: Sha256Digest
    evidence_policy_version: SemanticVersion
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def counts_match_classification(self) -> ConcordanceObservation:
        if self.left_entity_id == self.right_entity_id:
            raise ValueError("concordance comparison endpoints must be distinct")
        if self.concordant_count + self.discordant_count != self.informative_count:
            raise ValueError("concordance counts must sum to the informative count")
        non_evaluable = {
            ConcordanceClassification.INDETERMINATE,
            ConcordanceClassification.MISSING,
            ConcordanceClassification.UNSUPPORTED,
            ConcordanceClassification.EXCLUDED_DEPENDENT,
        }
        if self.classification in non_evaluable and self.informative_count != 0:
            raise ValueError("non-evaluable concordance cannot carry informative counts")
        if (
            self.classification is ConcordanceClassification.CONCORDANT
            and self.concordant_count == 0
        ):
            raise ValueError("concordant evidence requires a concordant observation")
        if (
            self.classification is ConcordanceClassification.DISCORDANT
            and self.discordant_count == 0
        ):
            raise ValueError("discordant evidence requires a discordant observation")
        return self


class IdentityResolutionPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_entities: int = Field(default=M0102_MAX_ENTITIES, ge=1, le=M0102_MAX_ENTITIES)
    max_operations: int = Field(default=M0102_MAX_OPERATIONS, ge=1, le=M0102_MAX_OPERATIONS)
    max_assertions: int = Field(default=M0102_MAX_ASSERTIONS, ge=1, le=M0102_MAX_ASSERTIONS)
    max_observations: int = Field(
        default=M0102_MAX_OBSERVATIONS,
        ge=1,
        le=M0102_MAX_OBSERVATIONS,
    )
    max_component_size: int = Field(
        default=M0102_MAX_COMPONENT_SIZE,
        ge=1,
        le=M0102_MAX_COMPONENT_SIZE,
    )
    maximum_depth: int = Field(default=M0102_MAX_DEPTH, ge=1, le=M0102_MAX_DEPTH)
    allow_mixed_subject_pooling: bool = False
    require_demultiplex_authority: bool = True
    allowed_operation_kinds: tuple[LineageOperationKind, ...] = Field(
        min_length=1,
        max_length=len(LineageOperationKind),
    )

    @field_validator("allowed_operation_kinds")
    @classmethod
    def operation_kinds_are_unique(
        cls,
        values: tuple[LineageOperationKind, ...],
    ) -> tuple[LineageOperationKind, ...]:
        if len(values) != len(set(values)):
            raise ValueError("allowed lineage operation kinds must be unique")
        return values


class IdentityAuthorityReference(FrozenModel):
    decision_id: Identifier
    state: UpstreamDecisionState
    policy_version: SemanticVersion
    evidence: ArtifactReference


class IdentityReconciliationReferences(FrozenModel):
    approved_configuration: UpstreamDecisionReference
    identity_authority: IdentityAuthorityReference
    provenance: UpstreamDecisionReference
    consent: ConsentReference
    quality: UpstreamDecisionReference
    support: UpstreamDecisionReference
    intended_use: UpstreamDecisionReference


class IdentityExecutionContext(FrozenModel):
    request_id: Identifier
    actor_id: Identifier
    occurred_at: AwareDatetime
    references: IdentityReconciliationReferences


def _validate_authorization_states(references: IdentityReconciliationReferences) -> None:
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize identity reconciliation")
    if references.identity_authority.state is not UpstreamDecisionState.ACCEPTED:
        raise ValueError("identity authority does not authorize reconciliation")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("an upstream control does not authorize reconciliation")


class ReconcileIdentityLineageRequest(FrozenModel):
    operation: Literal["reconcile"] = "reconcile"
    contract_version: Literal["1.0.0"] = M0102_CONTRACT_VERSION
    context: IdentityExecutionContext
    policy: IdentityResolutionPolicy
    entities: tuple[IdentityEntity, ...] = Field(min_length=1, max_length=M0102_MAX_ENTITIES)
    assertions: tuple[IdentityAssertion, ...] = Field(default=(), max_length=M0102_MAX_ASSERTIONS)
    lineage_operations: tuple[LineageOperation, ...] = Field(
        default=(),
        max_length=M0102_MAX_OPERATIONS,
    )
    concordance_observations: tuple[ConcordanceObservation, ...] = Field(
        default=(),
        max_length=M0102_MAX_OBSERVATIONS,
    )
    supersedes_resolution_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed_and_authority_bound(self) -> ReconcileIdentityLineageRequest:
        references = self.context.references
        _validate_authorization_states(references)
        _require_unique_ids(self.entities, "entity_id", "entity")
        _require_unique_ids(self.assertions, "assertion_id", "assertion")
        _require_unique_ids(self.lineage_operations, "operation_id", "lineage operation")
        _require_unique_ids(
            self.concordance_observations,
            "observation_id",
            "concordance observation",
        )
        if len(self.entities) > self.policy.max_entities:
            raise ValueError("entity count exceeds the active policy")
        if len(self.assertions) > self.policy.max_assertions:
            raise ValueError("assertion count exceeds the active policy")
        if len(self.lineage_operations) > self.policy.max_operations:
            raise ValueError("lineage operation count exceeds the active policy")
        if len(self.concordance_observations) > self.policy.max_observations:
            raise ValueError("concordance observation count exceeds the active policy")
        if (
            self.context.references.approved_configuration.evidence.digest
            != policy_digest(self.policy)
        ):
            raise ValueError("approved configuration does not bind the active identity policy")
        authority = references.identity_authority
        if authority.policy_version != self.policy.version:
            raise ValueError("identity authority does not bind the active policy version")
        entity_map = {entity.entity_id: entity for entity in self.entities}
        for assertion in self.assertions:
            _validate_assertion_reference(assertion, entity_map, authority, self.policy)
        for operation in self.lineage_operations:
            _validate_operation_reference(operation, entity_map, authority, self.policy)
        _validate_unique_lineage_producers(self.lineage_operations, entity_map)
        for observation in self.concordance_observations:
            observation_references = {
                observation.left_entity_id,
                observation.right_entity_id,
                observation.target_id,
            }
            if not observation_references.issubset(entity_map):
                raise ValueError("concordance observation references an unknown entity")
        evidence_total = _request_evidence_count(self)
        if evidence_total > M0102_MAX_EVIDENCE:
            raise ValueError("request evidence references exceed the global limit")
        return self


def _require_unique_ids(records: tuple[object, ...], field: str, label: str) -> None:
    values = [getattr(record, field) for record in records]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} identifiers must be unique")


def _validate_unique_lineage_producers(
    operations: tuple[LineageOperation | ResolvedLineageOperation, ...],
    entities: dict[str, IdentityEntity] | dict[str, ResolvedIdentityNode],
) -> None:
    producers: dict[
        str,
        dict[
            tuple[LineageOperationKind, tuple[Identifier, ...], tuple[Identifier, ...]],
            LineageOperation | ResolvedLineageOperation,
        ],
    ] = {}
    for operation in operations:
        signature = (
            operation.kind,
            tuple(sorted(operation.source_entity_ids)),
            tuple(sorted(operation.target_entity_ids)),
        )
        for target_id in operation.target_entity_ids:
            producers.setdefault(target_id, {}).setdefault(signature, operation)
    for target_id, unique_producers in producers.items():
        target_producers = tuple(unique_producers.values())
        if len(target_producers) <= 1:
            continue
        target = entities.get(target_id)
        derived_computation = (
            target is not None
            and target.kind is EntityKind.DERIVED_OBJECT
            and all(
                operation.kind is LineageOperationKind.COMPUTED_FROM
                for operation in target_producers
            )
        )
        if not derived_computation:
            raise ValueError("lineage target has more than one producing operation")


def _validate_assertion_reference(
    assertion: IdentityAssertion,
    entities: dict[str, IdentityEntity],
    authority: IdentityAuthorityReference,
    policy: IdentityResolutionPolicy,
) -> None:
    if isinstance(assertion, SubjectMembershipAssertion):
        references = {assertion.entity_id, assertion.subject_entity_id}
        if assertion.subject_entity_id in entities and (
            entities[assertion.subject_entity_id].kind is not EntityKind.PATIENT
        ):
            raise ValueError("subject membership must target a patient entity")
    else:
        references = {assertion.left_entity_id, assertion.right_entity_id}
    if not references.issubset(entities):
        raise ValueError("identity assertion references an unknown entity")
    if assertion.authority_decision_id != authority.decision_id:
        raise ValueError("identity assertion authority does not match the execution context")
    if assertion.policy_version != policy.version:
        raise ValueError("identity assertion does not bind the active policy version")


def _validate_operation_reference(
    operation: LineageOperation,
    entities: dict[str, IdentityEntity],
    authority: IdentityAuthorityReference,
    policy: IdentityResolutionPolicy,
) -> None:
    references = set(operation.source_entity_ids) | set(operation.target_entity_ids)
    if not references.issubset(entities):
        raise ValueError("lineage operation references an unknown entity")
    if operation.authority_decision_id != authority.decision_id:
        raise ValueError("lineage operation authority does not match the execution context")
    if operation.policy_version != policy.version:
        raise ValueError("lineage operation does not bind the active policy version")
    if operation.kind not in policy.allowed_operation_kinds:
        raise ValueError("lineage operation is disabled by the active policy")


def _request_evidence_count(request: ReconcileIdentityLineageRequest) -> int:
    token_evidence = sum(len(entity.identity_tokens) for entity in request.entities)
    return (
        sum(len(entity.evidence) for entity in request.entities)
        + token_evidence
        + sum(len(assertion.evidence) for assertion in request.assertions)
        + sum(
            len(operation.evidence)
            + sum(len(channel.evidence) for channel in operation.channels)
            for operation in request.lineage_operations
        )
        + sum(len(observation.evidence) for observation in request.concordance_observations)
    )


class IdentityComponent(FrozenModel):
    component_id: Sha256Digest
    member_entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    composition: EntityComposition

    @model_validator(mode="after")
    def members_and_subjects_are_unique(self) -> IdentityComponent:
        if len(self.member_entity_ids) != len(set(self.member_entity_ids)):
            raise ValueError("identity component members must be unique")
        if len(self.subject_component_ids) != len(set(self.subject_component_ids)):
            raise ValueError("identity component subject references must be unique")
        if (
            self.composition is EntityComposition.SINGLE_SUBJECT
            and len(self.subject_component_ids) != 1
        ):
            raise ValueError("single-subject components require one subject component")
        if (
            self.composition is EntityComposition.MULTI_SUBJECT
            and len(self.subject_component_ids) < _MINIMUM_MULTI_CARDINALITY
        ):
            raise ValueError("multi-subject components require multiple subject components")
        if self.composition is EntityComposition.UNKNOWN and self.subject_component_ids:
            raise ValueError("unknown-composition components cannot claim a subject component")
        return self


class ResolvedIdentityNode(FrozenModel):
    entity_id: Identifier
    kind: EntityKind
    component_id: Sha256Digest
    subject_component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)

    @field_validator("subject_component_ids")
    @classmethod
    def subject_components_are_unique(
        cls,
        values: tuple[Sha256Digest, ...],
    ) -> tuple[Sha256Digest, ...]:
        if len(values) != len(set(values)):
            raise ValueError("resolved subject component identifiers must be unique")
        return values


class ResolvedLineageOperation(FrozenModel):
    """Privacy-minimized operation: no tags, authority material, or submitted evidence."""

    operation_id: Identifier
    kind: LineageOperationKind
    source_entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    target_entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    mixed_subject: bool = False

    @model_validator(mode="after")
    def endpoints_are_unique_and_disjoint(self) -> ResolvedLineageOperation:
        if len(self.source_entity_ids) != len(set(self.source_entity_ids)) or len(
            self.target_entity_ids
        ) != len(set(self.target_entity_ids)):
            raise ValueError("resolved lineage endpoints must be unique")
        if set(self.source_entity_ids) & set(self.target_entity_ids):
            raise ValueError("resolved lineage operation cannot contain a self endpoint")
        if self.kind is LineageOperationKind.POOLED_FROM:
            if (
                len(self.source_entity_ids) < _MINIMUM_MULTI_CARDINALITY
                or len(self.target_entity_ids) != 1
            ):
                raise ValueError("resolved pooled-from operation requires N-to-one cardinality")
        elif self.kind is LineageOperationKind.DEMULTIPLEXED_FROM:
            if (
                len(self.source_entity_ids) != 1
                or len(self.target_entity_ids) < _MINIMUM_MULTI_CARDINALITY
                or self.mixed_subject
            ):
                raise ValueError(
                    "resolved demultiplexed-from operation requires one-to-N cardinality"
                )
        elif (
            len(self.source_entity_ids) != 1
            or len(self.target_entity_ids) != 1
            or self.mixed_subject
        ):
            raise ValueError("resolved ordinary operation requires one-to-one cardinality")
        return self


class ResolvedLineageGraph(FrozenModel):
    nodes: tuple[ResolvedIdentityNode, ...] = Field(min_length=1, max_length=M0102_MAX_ENTITIES)
    operations: tuple[ResolvedLineageOperation, ...] = Field(
        default=(),
        max_length=M0102_MAX_OPERATIONS,
    )
    graph_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL

    @model_validator(mode="after")
    def graph_is_closed_and_digest_bound(self) -> ResolvedLineageGraph:
        _require_unique_ids(self.nodes, "entity_id", "resolved node")
        _require_unique_ids(self.operations, "operation_id", "resolved lineage operation")
        node_map = {node.entity_id: node for node in self.nodes}
        for operation in self.operations:
            endpoints = set(operation.source_entity_ids) | set(operation.target_entity_ids)
            if not endpoints.issubset(node_map):
                raise ValueError("resolved lineage graph references an unknown node")
            source_kinds = {node_map[entity_id].kind for entity_id in operation.source_entity_ids}
            target_kinds = {node_map[entity_id].kind for entity_id in operation.target_entity_ids}
            if operation.kind in {
                LineageOperationKind.POOLED_FROM,
                LineageOperationKind.DEMULTIPLEXED_FROM,
            }:
                if (
                    len(source_kinds) != 1
                    or source_kinds != target_kinds
                    or not source_kinds.issubset(M0102_SPECIAL_LINEAGE_KINDS)
                ):
                    raise ValueError("resolved special lineage operation has invalid entity kinds")
            else:
                transition = (
                    operation.kind,
                    next(iter(source_kinds)),
                    next(iter(target_kinds)),
                )
                if transition not in M0102_ORDINARY_TRANSITIONS:
                    raise ValueError("resolved ordinary lineage transition is not allowed")
        _validate_unique_lineage_producers(self.operations, node_map)
        expected = graph_digest(self)
        if self.graph_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "graph_digest", expected)
        elif self.graph_digest != expected:
            raise ValueError("resolved lineage graph digest does not match its content")
        return self


class AssertionDisposition(FrozenModel):
    assertion_id: Identifier
    state: AssertionDispositionState
    reason_code: Identifier
    evidence: tuple[ArtifactReference, ...] = Field(
        default=(),
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)


class ConcordanceAggregate(FrozenModel):
    """Descriptive counts only; never a calibrated probability or merge authority."""

    concordant: int = Field(default=0, ge=0, le=M0102_MAX_OBSERVATIONS)
    discordant: int = Field(default=0, ge=0, le=M0102_MAX_OBSERVATIONS)
    indeterminate: int = Field(default=0, ge=0, le=M0102_MAX_OBSERVATIONS)
    missing: int = Field(default=0, ge=0, le=M0102_MAX_OBSERVATIONS)
    unsupported: int = Field(default=0, ge=0, le=M0102_MAX_OBSERVATIONS)
    excluded_dependent: int = Field(default=0, ge=0, le=M0102_MAX_OBSERVATIONS)
    informative_loci: int = Field(default=0, ge=0, le=M0102_MAX_INFORMATIVE_LOCI)
    concordant_loci: int = Field(default=0, ge=0, le=M0102_MAX_INFORMATIVE_LOCI)
    discordant_loci: int = Field(default=0, ge=0, le=M0102_MAX_INFORMATIVE_LOCI)

    @model_validator(mode="after")
    def locus_counts_are_closed(self) -> ConcordanceAggregate:
        if self.concordant_loci + self.discordant_loci != self.informative_loci:
            raise ValueError("aggregate locus counts must sum to informative loci")
        return self


class IdentityIssue(FrozenModel):
    code: Identifier
    severity: IdentityIssueSeverity
    action: IdentityIssueAction
    evidence_basis_digest: Sha256Digest
    evidence_reference_count: int = Field(ge=0, le=M0102_MAX_EVIDENCE)
    entity_ids: tuple[Identifier, ...] = Field(default=(), max_length=256)
    component_ids: tuple[Sha256Digest, ...] = Field(default=(), max_length=256)
    operation_ids: tuple[Identifier, ...] = Field(default=(), max_length=256)
    assertion_ids: tuple[Identifier, ...] = Field(default=(), max_length=256)
    message: NonEmptyStr
    evidence: tuple[ArtifactReference, ...] = Field(
        default=(),
        max_length=M0102_MAX_EVIDENCE_PER_ITEM,
    )

    _evidence_is_unique = field_validator("evidence")(_unique_evidence)

    @model_validator(mode="after")
    def issue_references_are_unique(self) -> IdentityIssue:
        for values in (
            self.entity_ids,
            self.component_ids,
            self.operation_ids,
            self.assertion_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("identity issue references must be unique")
        if self.evidence_reference_count < len(self.evidence):
            raise ValueError(
                "identity issue evidence count cannot be smaller than retained evidence"
            )
        return self


class IdentityControlRole(StrEnum):
    APPROVED_CONFIGURATION = "approved_configuration"
    IDENTITY_AUTHORITY = "identity_authority"
    PROVENANCE = "provenance"
    CONSENT = "consent"
    QUALITY = "quality"
    SUPPORT = "support"
    INTENDED_USE = "intended_use"


_CONTROL_EVIDENCE_ROLE_BY_CLAIM: Final = {
    (
        f"Caller-declared {role.value.replace('_', '-')} control reference; "
        "issuer and content are not authenticated by M01-02."
    ): role
    for role in IdentityControlRole
}


class IdentityControlDecisionRecord(FrozenModel):
    role: IdentityControlRole
    decision_id: Identifier
    state: Identifier
    policy_version: SemanticVersion
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def state_matches_role(self) -> IdentityControlDecisionRecord:
        allowed = (
            {state.value for state in ConsentState}
            if self.role is IdentityControlRole.CONSENT
            else {state.value for state in UpstreamDecisionState}
        )
        if self.state not in allowed:
            raise ValueError("control decision state is invalid for its M01-02 role")
        return self


class IdentityProvenanceRecord(FrozenModel):
    activity_id: Identifier
    actor_id: Identifier
    module_id: Literal["GLIO-PROTEOGEN-M01-02"] = "GLIO-PROTEOGEN-M01-02"
    module_version: SemanticVersion
    generated_at: AwareDatetime
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=10_000)
    evidence_manifest_digest: Sha256Digest
    configuration_digest: Sha256Digest
    consent_decision_id: Identifier
    consent_state: ConsentState
    consent_policy_version: SemanticVersion
    consent_evidence_digest: Sha256Digest
    control_decisions: tuple[IdentityControlDecisionRecord, ...] = Field(
        min_length=7,
        max_length=7,
    )

    @field_validator("control_decisions")
    @classmethod
    def all_control_roles_are_recorded(
        cls,
        records: tuple[IdentityControlDecisionRecord, ...],
    ) -> tuple[IdentityControlDecisionRecord, ...]:
        roles = [record.role for record in records]
        if len(roles) != len(set(roles)) or set(roles) != set(IdentityControlRole):
            raise ValueError("M01-02 provenance must record all seven controls exactly once")
        return records


def _validate_output_limitations(
    limitations: tuple[Limitation, ...],
) -> tuple[Limitation, ...]:
    codes = [limitation.code for limitation in limitations]
    if len(codes) != len(set(codes)):
        raise ValueError("resolution limitation codes must be unique")
    if not M0102_RESERVED_LIMITATION_CODES.issubset(codes):
        raise ValueError("resolution is missing a mandatory M01-02 limitation")
    return limitations


class _ResolutionCore(Protocol):
    @property
    def resolution_id(self) -> Identifier: ...

    @property
    def request_digest(self) -> Sha256Digest: ...

    @property
    def policy_digest(self) -> Sha256Digest: ...

    @property
    def components(self) -> tuple[IdentityComponent, ...]: ...

    @property
    def graph(self) -> ResolvedLineageGraph: ...

    @property
    def issues(self) -> tuple[IdentityIssue, ...]: ...


_IssueBindings = dict[
    Identifier,
    tuple[set[Identifier], set[Sha256Digest], set[Identifier]],
]


def _quarantine_issue_bindings(issues: tuple[IdentityIssue, ...]) -> _IssueBindings:
    bindings: _IssueBindings = {}
    for issue in issues:
        if (
            issue.action is not IdentityIssueAction.QUARANTINE
            or issue.severity is not IdentityIssueSeverity.CRITICAL
        ):
            continue
        entity_ids, component_ids, operation_ids = bindings.setdefault(
            issue.code,
            (set(), set(), set()),
        )
        entity_ids.update(issue.entity_ids)
        component_ids.update(issue.component_ids)
        operation_ids.update(issue.operation_ids)
    return bindings


def _has_bound_quarantine_issue(
    bindings: _IssueBindings,
    codes: Identifier | tuple[Identifier, ...],
    *,
    target_entity_ids: tuple[Identifier, ...] = (),
    operation_id: Identifier | None = None,
    component_id: Sha256Digest | None = None,
) -> bool:
    expected_codes = (codes,) if isinstance(codes, str) else codes
    targets = set(target_entity_ids)
    for code in expected_codes:
        issue_binding = bindings.get(code)
        if issue_binding is None:
            continue
        entity_ids, component_ids, operation_ids = issue_binding
        if component_id is not None and component_id in component_ids:
            return True
        if operation_id is not None and operation_id in operation_ids:
            return True
        if targets & entity_ids:
            return True
    return False


def _validate_lineage_subject_semantics(
    graph: ResolvedLineageGraph,
    issue_bindings: _IssueBindings,
) -> None:
    node_map = {node.entity_id: node for node in graph.nodes}
    for operation in graph.operations:
        source_subjects = [
            set(node_map[entity_id].subject_component_ids)
            for entity_id in operation.source_entity_ids
        ]
        target_subjects = [
            set(node_map[entity_id].subject_component_ids)
            for entity_id in operation.target_entity_ids
        ]
        if operation.kind is LineageOperationKind.POOLED_FROM:
            target_binding = target_subjects[0]
            if any(not subjects for subjects in source_subjects):
                if target_binding:
                    raise ValueError("an unresolved pool source requires an unbound target")
                if not _has_bound_quarantine_issue(
                    issue_bindings,
                    "pool.source_identity_unresolved",
                    target_entity_ids=operation.target_entity_ids,
                    operation_id=operation.operation_id,
                ):
                    raise ValueError(
                        "an unresolved pool source requires a bound quarantine issue"
                    )
                continue
            expected = set().union(*source_subjects)
            expected_mixed = len(expected) > 1
            if (
                target_binding != expected or operation.mixed_subject is not expected_mixed
            ) and not _has_bound_quarantine_issue(
                issue_bindings,
                "pool.composition_mismatch",
                target_entity_ids=operation.target_entity_ids,
                operation_id=operation.operation_id,
            ):
                raise ValueError("pooled lineage subject semantics require quarantine")
            continue
        if operation.kind is LineageOperationKind.DEMULTIPLEXED_FROM:
            source_binding = source_subjects[0]
            for target_id, target_binding in zip(
                operation.target_entity_ids,
                target_subjects,
                strict=True,
            ):
                if not target_binding:
                    if not _has_bound_quarantine_issue(
                        issue_bindings,
                        (
                            "demultiplex.target_identity_unresolved",
                            "demultiplex.cross_patient",
                        ),
                        target_entity_ids=(target_id,),
                        operation_id=operation.operation_id,
                    ):
                        raise ValueError(
                            "an unbound demultiplex target requires a bound quarantine issue"
                        )
                elif not target_binding.issubset(source_binding) and not (
                    _has_bound_quarantine_issue(
                        issue_bindings,
                        "demultiplex.cross_patient",
                        target_entity_ids=(target_id,),
                        operation_id=operation.operation_id,
                    )
                ):
                    raise ValueError(
                        "demultiplex target subjects must be contained by the source"
                    )
            continue
        if source_subjects[0] != target_subjects[0] and not (
            _has_bound_quarantine_issue(
                issue_bindings,
                "lineage.cross_patient",
                target_entity_ids=operation.target_entity_ids,
                operation_id=operation.operation_id,
            )
        ):
            raise ValueError("ordinary lineage subject semantics require quarantine")


def _validate_resolution_core(resolution: _ResolutionCore) -> None:
    expected_resolution_id = (
        f"resolution.{resolution.request_digest.removeprefix('sha256:')}"
    )
    if resolution.resolution_id != expected_resolution_id:
        raise ValueError("identity resolution identifier does not bind its request digest")
    components = resolution.components
    graph = resolution.graph
    issue_bindings = _quarantine_issue_bindings(resolution.issues)
    component_ids = [component.component_id for component in components]
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("identity component identifiers must be unique")
    known_components = set(component_ids)
    members = [member for component in components for member in component.member_entity_ids]
    if len(members) != len(set(members)):
        raise ValueError("resolved entities must occur in exactly one identity component")
    node_map = {node.entity_id: node for node in graph.nodes}
    if set(node_map) != set(members):
        raise ValueError("resolved graph nodes must exactly cover identity component members")
    for component in components:
        if any(
            node_map[member].component_id != component.component_id
            for member in component.member_entity_ids
        ):
            raise ValueError("resolved graph node references the wrong identity component")
        component_kinds = {node_map[member].kind for member in component.member_entity_ids}
        if len(component_kinds) > 1 and not _has_bound_quarantine_issue(
            issue_bindings,
            "component.cross_kind",
            component_id=component.component_id,
        ):
            raise ValueError("a mixed-kind identity component requires a bound quarantine issue")
        if not set(component.subject_component_ids).issubset(known_components):
            raise ValueError("component references an unknown subject component")
        if any(
            node_map[member].subject_component_ids != component.subject_component_ids
            for member in component.member_entity_ids
        ):
            raise ValueError("resolved node subject bindings contradict its component")
    if any(
        not set(node.subject_component_ids).issubset(known_components)
        for node in graph.nodes
    ):
        raise ValueError("resolved node references an unknown subject component")
    patient_components = {
        node.component_id for node in graph.nodes if node.kind is EntityKind.PATIENT
    }
    referenced_subject_components = {
        subject_id for component in components for subject_id in component.subject_component_ids
    }
    if not referenced_subject_components.issubset(patient_components):
        raise ValueError("subject component does not contain a patient node")
    _validate_lineage_subject_semantics(graph, issue_bindings)


def _validate_control_evidence(
    evidence_records: tuple[EvidenceReference, ...],
    controls: dict[IdentityControlRole, IdentityControlDecisionRecord],
) -> None:
    if len(evidence_records) != len(IdentityControlRole):
        raise ValueError("resolution must bind exactly seven control evidence references")
    evidence_by_role: dict[IdentityControlRole, EvidenceReference] = {}
    for evidence in evidence_records:
        role = _CONTROL_EVIDENCE_ROLE_BY_CLAIM.get(evidence.claim)
        if role is None or evidence.role != "evidence" or role in evidence_by_role:
            raise ValueError("resolution control evidence claim is not uniquely role-bound")
        evidence_by_role[role] = evidence
    if set(evidence_by_role) != set(IdentityControlRole):
        raise ValueError("resolution control evidence does not cover all seven roles")
    if any(
        evidence_by_role[role].reference.digest != record.evidence_digest
        for role, record in controls.items()
    ):
        raise ValueError("resolution control evidence contradicts its provenance record")


def _validate_resolution_envelope(resolution: IdentityLineageResolution) -> None:
    provenance = resolution.provenance
    controls = {record.role: record for record in provenance.control_decisions}
    consent = controls[IdentityControlRole.CONSENT]
    if consent.state != ConsentState.GRANTED.value:
        raise ValueError("resolution provenance consent control must be granted")
    if any(
        record.state != UpstreamDecisionState.ACCEPTED.value
        for role, record in controls.items()
        if role is not IdentityControlRole.CONSENT
    ):
        raise ValueError("resolution provenance upstream controls must be accepted")
    if (
        provenance.consent_decision_id != consent.decision_id
        or provenance.consent_state.value != consent.state
        or provenance.consent_policy_version != consent.policy_version
        or provenance.consent_evidence_digest != consent.evidence_digest
    ):
        raise ValueError("resolution provenance consent fields contradict its control record")
    approved_configuration = controls[IdentityControlRole.APPROVED_CONFIGURATION]
    if provenance.configuration_digest != approved_configuration.evidence_digest:
        raise ValueError("resolution configuration digest contradicts its control evidence")
    _validate_control_evidence(resolution.evidence, controls)
    required_input_digests = {
        resolution.request_digest,
        resolution.policy_digest,
        resolution.core_digest,
        resolution.graph.graph_digest,
        provenance.evidence_manifest_digest,
        *(record.evidence_digest for record in controls.values()),
    }
    if not required_input_digests.issubset(provenance.input_digests):
        raise ValueError("resolution provenance input digests are incomplete")
    if provenance.generated_at != resolution.resolved_at:
        raise ValueError("resolution provenance timestamp contradicts resolution time")
    if provenance.module_version != resolution.resolution_version:
        raise ValueError("resolution provenance module version contradicts resolution version")
    expected_activity_id = (
        f"activity.m0102.{resolution.request_digest.removeprefix('sha256:')}"
    )
    if provenance.activity_id != expected_activity_id:
        raise ValueError("resolution provenance activity does not bind its request digest")


class IdentityLineageResolutionDraft(FrozenModel):
    """Pure resolution semantics before service evidence and ledger commitment."""

    output_type: Literal["identity_lineage_resolution_draft"] = (
        "identity_lineage_resolution_draft"
    )
    resolution_id: Identifier
    resolution_version: SemanticVersion
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    core_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    decision: ResolutionDecision
    components: tuple[IdentityComponent, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_ENTITIES,
    )
    graph: ResolvedLineageGraph
    assertion_dispositions: tuple[AssertionDisposition, ...] = Field(
        default=(),
        max_length=M0102_MAX_ASSERTIONS,
    )
    concordance: ConcordanceAggregate
    issues: tuple[IdentityIssue, ...] = Field(default=(), max_length=M0102_MAX_ISSUES)
    human_review_required: bool
    resolved_at: AwareDatetime
    supersedes_resolution_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def core_is_coherent_and_digest_bound(self) -> IdentityLineageResolutionDraft:
        _require_unique_ids(self.assertion_dispositions, "assertion_id", "assertion disposition")
        _validate_resolution_core(self)
        _validate_resolution_decision(self)
        expected = resolution_core_digest(self)
        if self.core_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "core_digest", expected)
        elif self.core_digest != expected:
            raise ValueError("identity resolution core digest does not match its content")
        return self


class IdentityLineageResolution(FrozenModel):
    output_type: Literal["identity_lineage_resolution"] = "identity_lineage_resolution"
    resolution_id: Identifier
    resolution_version: SemanticVersion
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    core_digest: Sha256Digest
    resolution_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    event_digest: Sha256Digest
    decision: ResolutionDecision
    components: tuple[IdentityComponent, ...] = Field(min_length=1, max_length=M0102_MAX_ENTITIES)
    graph: ResolvedLineageGraph
    assertion_dispositions: tuple[AssertionDisposition, ...] = Field(
        default=(),
        max_length=M0102_MAX_ASSERTIONS,
    )
    concordance: ConcordanceAggregate
    issues: tuple[IdentityIssue, ...] = Field(default=(), max_length=M0102_MAX_ISSUES)
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: IdentityProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=1_000)
    human_review_required: bool
    resolved_at: AwareDatetime
    supersedes_resolution_digest: Sha256Digest | None = None

    @field_validator("limitations")
    @classmethod
    def limitations_are_closed(
        cls,
        limitations: tuple[Limitation, ...],
    ) -> tuple[Limitation, ...]:
        return _validate_output_limitations(limitations)

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        evidence: tuple[EvidenceReference, ...],
    ) -> tuple[EvidenceReference, ...]:
        if len(evidence) != len(set(evidence)):
            raise ValueError("resolution evidence references must be unique")
        return evidence

    @model_validator(mode="after")
    def envelope_is_coherent(self) -> IdentityLineageResolution:
        _require_unique_ids(self.assertion_dispositions, "assertion_id", "assertion disposition")
        _validate_resolution_core(self)
        _validate_resolution_decision(self)
        if self.core_digest != resolution_core_digest(self):
            raise ValueError("identity resolution envelope does not bind its semantic core")
        _validate_resolution_envelope(self)
        expected = resolution_payload_digest(self)
        if self.resolution_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "resolution_digest", expected)
        elif self.resolution_digest != expected:
            raise ValueError("identity resolution digest does not match its content")
        return self


def _validate_resolution_decision(
    resolution: IdentityLineageResolution | IdentityLineageResolutionDraft,
) -> None:
    actions = {issue.action for issue in resolution.issues}
    if IdentityIssueAction.QUARANTINE in actions:
        expected_decision = ResolutionDecision.QUARANTINED
    elif IdentityIssueAction.REJECT in actions:
        expected_decision = ResolutionDecision.CONFLICTED
    elif IdentityIssueAction.HUMAN_REVIEW in actions:
        expected_decision = ResolutionDecision.UNRESOLVED
    else:
        expected_decision = ResolutionDecision.RESOLVED
    if resolution.decision is not expected_decision:
        raise ValueError("identity resolution decision contradicts its issue actions")
    expected_review = resolution.decision is not ResolutionDecision.RESOLVED or any(
        issue.severity is IdentityIssueSeverity.CRITICAL for issue in resolution.issues
    )
    if resolution.human_review_required is not expected_review:
        raise ValueError("identity resolution human-review flag contradicts its issues")
    if isinstance(resolution, IdentityLineageResolutionDraft):
        return
    expected_support = {
        ResolutionDecision.RESOLVED: (SupportStatus.LIMITED, "identity_lineage_resolved"),
        ResolutionDecision.UNRESOLVED: (
            SupportStatus.REVIEW_REQUIRED,
            "identity_lineage_unresolved",
        ),
        ResolutionDecision.CONFLICTED: (
            SupportStatus.UNSUPPORTED,
            "identity_lineage_conflicted",
        ),
        ResolutionDecision.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identity_lineage_quarantined",
        ),
    }[resolution.decision]
    if (resolution.support.status, resolution.support.reason_code) != expected_support:
        raise ValueError("identity resolution support contradicts its decision")


__all__ = [
    "M0102_CONTRACT_VERSION",
    "M0102_MAX_INFORMATIVE_LOCI",
    "M0102_ORDINARY_TRANSITIONS",
    "M0102_SPECIAL_LINEAGE_KINDS",
    "AssertionDisposition",
    "AssertionDispositionState",
    "ConcordanceAggregate",
    "ConcordanceClassification",
    "ConcordanceObservation",
    "DemultiplexChannel",
    "DifferentFromAssertion",
    "EntityComposition",
    "EntityKind",
    "IdentityAssertion",
    "IdentityAuthorityReference",
    "IdentityComponent",
    "IdentityControlDecisionRecord",
    "IdentityControlRole",
    "IdentityEntity",
    "IdentityExecutionContext",
    "IdentityIssue",
    "IdentityIssueAction",
    "IdentityIssueSeverity",
    "IdentityLineageResolution",
    "IdentityLineageResolutionDraft",
    "IdentityProvenanceRecord",
    "IdentityReconciliationReferences",
    "IdentityResolutionPolicy",
    "LineageOperation",
    "LineageOperationKind",
    "ReconcileIdentityLineageRequest",
    "ResolutionDecision",
    "ResolvedIdentityNode",
    "ResolvedLineageGraph",
    "ResolvedLineageOperation",
    "SameAsAssertion",
    "ScopedIdentityToken",
    "SubjectMembershipAssertion",
]
