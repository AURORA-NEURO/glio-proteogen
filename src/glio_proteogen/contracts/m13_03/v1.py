"""Provisional M13-03 mechanistic feature-constructor contracts.

The M13-03 dossier requires interpretable pathway, topology, state, lineage,
kinetics, spatial, and regulatory features tied to a proteotype, with source
evidence, pathway/topology and unit invariants, negative-control gating, and
safe abstention. The public ABI is not frozen; these symbols are provisional
scaffolding pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m13_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M13-03 dossier slice.
M1303_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-03"
M1303_OPERATION: Final = "construct_proteotype_mechanistic_features"
M1303_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1303_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-03+json"
M1303_M1302_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-02+json"
M1303_PARENT: Final = "proteotype"
M1303_OWNER: Final = "Data engineering"
M1303_SAFETY_CLASS: Final = "S2"
M1303_GATE: Final = "G1"
M1303_PROVISIONAL_ABI: Final = True
M1303_MAX_FEATURES: Final = 2_048
M1303_MAX_RELATIONS: Final = 4_096
M1303_MAX_TRANSFORMATIONS: Final = 512
M1303_MAX_EVIDENCE: Final = 64
M1303_MAX_DIAGNOSTICS: Final = 128
M1303_MAX_DIAGNOSTIC_MESSAGE: Final = 512
M1303_MAX_FINDINGS: Final = 64
M1303_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1303_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1303_EVIDENCE_CLAIM: Final = (
    "Caller-declared M13-03 mechanistic feature evidence; issuer authority is not authenticated."
)


class MechanisticFeatureKind(StrEnum):
    PATHWAY = "pathway"
    TOPOLOGY = "topology"
    STATE = "state"
    LINEAGE = "lineage"
    KINETICS = "kinetics"
    SPATIAL = "spatial"
    REGULATORY = "regulatory"


class MechanisticValueKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class MechanisticConstructionStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class MechanisticDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class MechanisticFindingCode(StrEnum):
    INPUT_INCOMPLETE = "input_incomplete"
    UNIT_INVARIANT_FAILED = "unit_invariant_failed"
    TOPOLOGY_INVARIANT_FAILED = "topology_invariant_failed"
    NEGATIVE_CONTROL_FAILED = "negative_control_failed"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class MechanisticRelationKind(StrEnum):
    ACTIVATES = "activates"
    INHIBITS = "inhibits"
    PARTICIPATES = "participates"
    PRECEDES = "precedes"
    COLOCALIZES = "colocalizes"
    REGULATES = "regulates"


class MechanisticFeatureLineage(FrozenModel):
    """Complete source attribution for one mechanistic feature."""

    feature_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1303_MAX_EVIDENCE
    )
    claim: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1303_MAX_TRANSFORMATIONS
    )
    complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)


class MechanisticFeature(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    kind: MechanisticFeatureKind
    value_kind: MechanisticValueKind
    unit: NonEmptyStr
    scalar_value: float | None = Field(default=None, ge=-1_000_000.0, le=1_000_000.0)
    lower_bound: float | None = Field(default=None, ge=-1_000_000.0, le=1_000_000.0)
    upper_bound: float | None = Field(default=None, ge=-1_000_000.0, le=1_000_000.0)
    category: NonEmptyStr | None = None
    lineage: MechanisticFeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> MechanisticFeature:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        present = sum((self.scalar_value is not None, has_interval, self.category is not None))
        if self.value_kind is MechanisticValueKind.SCALAR:
            if self.scalar_value is None or has_interval or self.category is not None:
                raise ValueError("scalar feature requires exactly one scalar value")
        elif self.value_kind is MechanisticValueKind.INTERVAL:
            if (
                self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or self.category is not None
                or self.scalar_value is not None
            ):
                raise ValueError("interval feature requires ordered bounds")
        elif self.category is None or self.scalar_value is not None or has_interval:
            raise ValueError("categorical feature requires only a category")
        if present != 1:
            raise ValueError("mechanistic feature requires one value representation")
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("feature lineage id must match feature id")
        return self


class MechanisticRelation(FrozenModel):
    relation_id: Identifier
    source_feature_id: Identifier
    target_feature_id: Identifier
    kind: MechanisticRelationKind
    weight: float | None = Field(default=None, ge=-1.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)

    @model_validator(mode="after")
    def relation_is_not_self_loop(self) -> MechanisticRelation:
        if self.source_feature_id == self.target_feature_id:
            raise ValueError("mechanistic relation cannot be a self-loop")
        return self


class MechanisticFeatureConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1303_MAX_TRANSFORMATIONS
    )
    pathway_reference: ArtifactReference
    negative_control_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1303_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_is_closed(self) -> MechanisticFeatureConfiguration:
        if len(self.transformation_ids) != len(set(self.transformation_ids)):
            raise ValueError("configuration transformation ids must be unique")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.negative_control_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("negative-control artifact references must be unique")
        return self


class MechanisticFeatureObject(FrozenModel):
    """Versioned mechanistic features with pathway and source closure."""

    object_id: Identifier
    version: SemanticVersion
    features: tuple[MechanisticFeature, ...] = Field(min_length=1, max_length=M1303_MAX_FEATURES)
    relations: tuple[MechanisticRelation, ...] = Field(default=(), max_length=M1303_MAX_RELATIONS)
    configuration: MechanisticFeatureConfiguration
    lineage_complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)

    @model_validator(mode="after")
    def object_is_closed(self) -> MechanisticFeatureObject:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("mechanistic feature ids must be unique")
        known = set(feature_ids)
        if not any(item.kind is MechanisticFeatureKind.PATHWAY for item in self.features):
            raise ValueError("mechanistic feature object requires a pathway feature")
        relation_ids = tuple(item.relation_id for item in self.relations)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("mechanistic relation ids must be unique")
        for relation in self.relations:
            if relation.source_feature_id not in known or relation.target_feature_id not in known:
                raise ValueError("mechanistic relation references an unknown feature")
        transformation_ids = set(self.configuration.transformation_ids)
        for feature in self.features:
            if not set(feature.lineage.transformation_ids) <= transformation_ids:
                raise ValueError("feature lineage references an unknown transformation")
        return self


class MechanisticFeatureDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: MechanisticDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)

    @field_validator("message")
    @classmethod
    def diagnostic_message_is_bounded(cls, value: str) -> str:
        if len(value) > M1303_MAX_DIAGNOSTIC_MESSAGE:
            raise ValueError("diagnostic message is too long")
        return value


class ConstructProteotypeMechanisticFeaturesRequest(FrozenModel):
    """Provisional request ABI bound to the M13-02 upstream artifact."""

    operation: Literal["construct_proteotype_mechanistic_features"] = M1303_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1303_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanisticFeatureConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1303_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructProteotypeMechanisticFeaturesRequest:
        if self.upstream_result.media_type != M1303_M1302_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M13-02 upstream result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        config_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.configuration.negative_control_artifacts
        )
        if any(item in config_keys for item in keys):
            raise ValueError("source artifacts cannot alias negative-control artifacts")
        return self


class ProteotypeMechanisticFeatureResult(FrozenModel):
    """Mechanistic feature result with invariant diagnostics and abstention."""

    output_type: Literal["proteotype_mechanistic_features"] = "proteotype_mechanistic_features"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1303_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructProteotypeMechanisticFeaturesRequest
    status: MechanisticConstructionStatus
    feature_object: MechanisticFeatureObject | None = None
    diagnostics: tuple[MechanisticFeatureDiagnostic, ...] = Field(
        min_length=1, max_length=M1303_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanisticFindingCode, ...] = Field(default=(), max_length=M1303_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1303_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1303_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeMechanisticFeatureResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("diagnostic ids must be unique")
        if not self.evidence:
            raise ValueError("result evidence must be explicit")
        failed = {MechanisticDiagnosticStatus.FAIL, MechanisticDiagnosticStatus.NOT_EVALUABLE}
        if self.status is MechanisticConstructionStatus.CONSTRUCTED:
            if (
                self.feature_object is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
            ):
                raise ValueError("constructed result requires supported, invariant-safe output")
        elif (
            self.feature_object is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no feature object and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return the conservative seven-dimension uncertainty baseline."""

    return UncertaintyProfile(
        measurement=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=0.8,
            rationale="Caller-declared measurement support.",
        ),
        sampling=UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="Sampling frame is not traversed by this module.",
        ),
        parameter=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=0.75,
            rationale="Locked configuration parameter uncertainty.",
        ),
        model_form=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=0.7,
            rationale="Reference mechanistic model form.",
        ),
        identification=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=0.8,
            rationale="Caller-declared source identification support.",
        ),
        support=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=0.8,
            rationale="Upstream support controls accepted.",
        ),
        transport=UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="Transport domain is not inferred from opaque artifacts.",
        ),
        sensitivity_notes=(
            "Scores are deterministic digest-derived reference features; "
            "no raw payload is traversed.",
        ),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    """Return explicit interpretation ceilings required by the dossier."""

    return (
        Limitation(
            code="provisional_abi",
            statement="M13-03 ABI remains provisional pending owner confirmation.",
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Source evidence is caller-declared and issuer authority is not authenticated."
            ),
        ),
        Limitation(
            code="no_kinase_state",
            statement="Kinase-state ownership remains exclusively outside M13-03.",
        ),
        Limitation(
            code="no_treatment", statement="This module never emits treatment recommendations."
        ),
    )


def feature_evidence_index(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    """Build a stable evidence index without reading referenced artifacts."""

    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1303_EVIDENCE_CLAIM)
        for artifact in (*request.source_artifacts, request.upstream_result)
    )


def expected_provenance(
    request: ConstructProteotypeMechanisticFeaturesRequest,
    *,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Derive audit provenance from the immutable request and seven controls."""

    references = request.context.references
    controls = (
        ("approved_configuration", references.approved_configuration),
        ("identity_lineage", references.identity_lineage),
        ("provenance", references.provenance),
        ("consent", references.consent),
        ("quality", references.quality),
        ("support", references.support),
        ("intended_use", references.intended_use),
    )
    decisions = []
    for role, reference in controls:
        subject = references.identity_lineage.binding_digest if role == "identity_lineage" else None
        decisions.append(
            ControlDecisionRecord(
                role=ControlRole(role),
                decision_id=reference.decision_id,
                state=reference.state.value,
                policy_version=reference.policy_version,
                evidence_digest=reference.evidence.digest,
                subject_digest=subject,
            )
        )
    return ProvenanceRecord(
        activity_id=f"activity.m1303.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1303_MODULE_ID,
        module_version=M1303_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            item.digest for item in (*request.source_artifacts, request.upstream_result)
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=tuple(decisions),
    )


__all__ = [
    "M1303_CONTRACT_VERSION",
    "M1303_EVIDENCE_CLAIM",
    "M1303_GATE",
    "M1303_M1302_INPUT_MEDIA_TYPE",
    "M1303_MAX_CANONICAL_REQUEST_BYTES",
    "M1303_MAX_CANONICAL_RESULT_BYTES",
    "M1303_MAX_DIAGNOSTICS",
    "M1303_MAX_EVIDENCE",
    "M1303_MAX_FEATURES",
    "M1303_MAX_FINDINGS",
    "M1303_MAX_RELATIONS",
    "M1303_MAX_TRANSFORMATIONS",
    "M1303_MODULE_ID",
    "M1303_OPERATION",
    "M1303_OUTPUT_MEDIA_TYPE",
    "M1303_OWNER",
    "M1303_PARENT",
    "M1303_PROVISIONAL_ABI",
    "M1303_SAFETY_CLASS",
    "ConstructProteotypeMechanisticFeaturesRequest",
    "MechanisticConstructionStatus",
    "MechanisticDiagnosticStatus",
    "MechanisticFeature",
    "MechanisticFeatureConfiguration",
    "MechanisticFeatureDiagnostic",
    "MechanisticFeatureKind",
    "MechanisticFeatureLineage",
    "MechanisticFeatureObject",
    "MechanisticFindingCode",
    "MechanisticRelation",
    "MechanisticRelationKind",
    "MechanisticValueKind",
    "ProteotypeMechanisticFeatureResult",
    "expected_limitations",
    "expected_provenance",
    "expected_uncertainty",
    "feature_evidence_index",
]
