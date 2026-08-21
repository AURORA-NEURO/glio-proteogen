"""Provisional M14-03 mechanistic feature-constructor contracts.

The M14-03 dossier requires interpretable pathway, topology, state, lineage,
kinetics, spatial, and regulatory features tied to a protein subtype, with
source evidence, stoichiometric/topology and unit invariants, negative-control
gating, and safe abstention. The public ABI is provisional pending owner
confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m14_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
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
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M14-03 dossier slice.
M1403_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-03"
M1403_OPERATION: Final = "construct_protein_subtype_mechanistic_features"
M1403_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1403_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-03+json"
M1403_M1402_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-02+json"
M1403_PARENT: Final = "protein_subtype"
M1403_OWNER: Final = "Platform engineering"
M1403_SAFETY_CLASS: Final = "S2"
M1403_GATE: Final = "G1"
M1403_PROVISIONAL_ABI: Final = True
M1403_DOSSIER_SLICE: Final = "4804-4847"
M1403_REQUIREMENT_SHA256: Final = (
    "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M1403_MAX_FEATURES: Final = 2_048
M1403_MAX_RELATIONS: Final = 4_096
M1403_MAX_TRANSFORMATIONS: Final = 512
M1403_MAX_EVIDENCE: Final = 64
M1403_MAX_DIAGNOSTICS: Final = 128
M1403_MAX_FINDINGS: Final = 64
M1403_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1403_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1403_EVIDENCE_CLAIM: Final = (
    "Caller-declared M14-03 mechanistic feature evidence; issuer authority "
    "is not authenticated."
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
    STOICHIOMETRIC_INVARIANT_FAILED = "stoichiometric_invariant_failed"
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
        min_length=1, max_length=M1403_MAX_EVIDENCE
    )
    claim: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1403_MAX_TRANSFORMATIONS
    )
    complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)


class MechanisticFeature(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    kind: MechanisticFeatureKind
    value_kind: MechanisticValueKind
    unit: NonEmptyStr
    scalar_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    lineage: MechanisticFeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> MechanisticFeature:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        present = sum(
            (self.scalar_value is not None, has_interval, self.category is not None)
        )
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
    weight: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)

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
        min_length=1, max_length=M1403_MAX_TRANSFORMATIONS
    )
    stoichiometry_reference: ArtifactReference
    negative_control_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1403_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)


class MechanisticFeatureObject(FrozenModel):
    """Versioned mechanistic features with stoichiometric source closure."""

    object_id: Identifier
    version: SemanticVersion
    features: tuple[MechanisticFeature, ...] = Field(
        min_length=1, max_length=M1403_MAX_FEATURES
    )
    relations: tuple[MechanisticRelation, ...] = Field(
        default=(), max_length=M1403_MAX_RELATIONS
    )
    configuration: MechanisticFeatureConfiguration
    lineage_complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def object_is_closed(self) -> MechanisticFeatureObject:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("mechanistic feature ids must be unique")
        known = set(feature_ids)
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)


class ConstructProteinSubtypeMechanisticFeaturesRequest(FrozenModel):
    """Provisional request ABI bound to the M14-02 upstream artifact."""

    operation: Literal["construct_protein_subtype_mechanistic_features"] = M1403_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1403_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanisticFeatureConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1403_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
        if self.upstream_result.media_type != M1403_M1402_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M14-02 upstream result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        return self


class ProteinSubtypeMechanisticFeatureResult(FrozenModel):
    """Mechanistic feature result with invariant diagnostics and abstention."""

    output_type: Literal["protein_subtype_mechanistic_features"] = (
        "protein_subtype_mechanistic_features"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1403_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructProteinSubtypeMechanisticFeaturesRequest
    status: MechanisticConstructionStatus
    feature_object: MechanisticFeatureObject | None = None
    diagnostics: tuple[MechanisticFeatureDiagnostic, ...] = Field(
        min_length=1, max_length=M1403_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanisticFindingCode, ...] = Field(
        default=(), max_length=M1403_MAX_FINDINGS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1403_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1403_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeMechanisticFeatureResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed = {MechanisticDiagnosticStatus.FAIL, MechanisticDiagnosticStatus.NOT_EVALUABLE}
        if self.status is MechanisticConstructionStatus.CONSTRUCTED:
            if (
                self.feature_object is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
                or any(item.status in failed for item in self.diagnostics)
            ):
                raise ValueError("constructed result requires review-only, invariant-safe output")
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


__all__ = [
    "M1403_CONTRACT_VERSION",
    "M1403_DOSSIER_SLICE",
    "M1403_EVIDENCE_CLAIM",
    "M1403_GATE",
    "M1403_M1402_INPUT_MEDIA_TYPE",
    "M1403_MAX_CANONICAL_REQUEST_BYTES",
    "M1403_MAX_CANONICAL_RESULT_BYTES",
    "M1403_MAX_DIAGNOSTICS",
    "M1403_MAX_EVIDENCE",
    "M1403_MAX_FEATURES",
    "M1403_MAX_FINDINGS",
    "M1403_MAX_RELATIONS",
    "M1403_MAX_TRANSFORMATIONS",
    "M1403_MODULE_ID",
    "M1403_OPERATION",
    "M1403_OUTPUT_MEDIA_TYPE",
    "M1403_OWNER",
    "M1403_PARENT",
    "M1403_PROVISIONAL_ABI",
    "M1403_REQUIREMENT_SHA256",
    "M1403_SAFETY_CLASS",
    "ConstructProteinSubtypeMechanisticFeaturesRequest",
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
    "ProteinSubtypeMechanisticFeatureResult",
]
