"""Provisional M11-03 mechanistic feature-constructor contracts.

The M11-03 dossier requires interpretable pathway, topology, state, lineage,
kinetics, spatial and regulatory features with source evidence, topology and
unit invariants, and safe abstention.  It does not freeze the public ABI,
feature catalogue, operation, media type, or capacities.  All symbols here
are provisional scaffolding pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m11_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M11-03 dossier slice.
M1103_MODULE_ID: Final = "GLIO-PROTEOGEN-M11-03"
M1103_OPERATION: Final = "construct_variant_peptide_mechanistic_features"
M1103_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1103_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-03+json"
M1103_M1102_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-02+json"
M1103_PARENT: Final = "variant_peptide"
M1103_OWNER: Final = "Quality engineering"
M1103_SAFETY_CLASS: Final = "S2"
M1103_GATE: Final = "G1"
M1103_PROVISIONAL_ABI: Final = True
M1103_MAX_FEATURES: Final = 2_048
M1103_MAX_RELATIONS: Final = 4_096
M1103_MAX_TRANSFORMATIONS: Final = 512
M1103_MAX_EVIDENCE: Final = 64
M1103_MAX_DIAGNOSTICS: Final = 128
M1103_MAX_FINDINGS: Final = 64
M1103_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1103_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1103_EVIDENCE_CLAIM: Final = (
    "Caller-declared M11-03 mechanistic feature evidence; issuer authority is not authenticated."
)

# Every numeric feature is a measured or derived quantity.  NaN/Inf would
# destroy canonical replay and make an invariant appear to pass, so the
# contract rejects them at the boundary rather than relying on serializers.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


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
        min_length=1, max_length=M1103_MAX_EVIDENCE
    )
    claim: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1103_MAX_TRANSFORMATIONS
    )
    complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)


class MechanisticFeature(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    kind: MechanisticFeatureKind
    value_kind: MechanisticValueKind
    unit: NonEmptyStr
    scalar_value: FiniteFloat | None = None
    lower_bound: FiniteFloat | None = None
    upper_bound: FiniteFloat | None = None
    category: NonEmptyStr | None = None
    lineage: MechanisticFeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)

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
    weight: FiniteFloat | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)

    @model_validator(mode="after")
    def relation_is_not_self_loop(self) -> MechanisticRelation:
        if self.source_feature_id == self.target_feature_id:
            raise ValueError("mechanistic relation cannot be a self-loop")
        if self.weight is not None and not -1.0 <= self.weight <= 1.0:
            raise ValueError("mechanistic relation weight must be within [-1, 1]")
        return self


class MechanisticFeatureConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1103_MAX_TRANSFORMATIONS
    )
    topology_reference: ArtifactReference
    negative_control_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1103_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)


class MechanisticFeatureObject(FrozenModel):
    """Versioned mechanistic feature object with topology and source closure."""

    object_id: Identifier
    version: SemanticVersion
    features: tuple[MechanisticFeature, ...] = Field(min_length=1, max_length=M1103_MAX_FEATURES)
    relations: tuple[MechanisticRelation, ...] = Field(default=(), max_length=M1103_MAX_RELATIONS)
    configuration: MechanisticFeatureConfiguration
    lineage_complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)

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
        if len(transformation_ids) != len(self.configuration.transformation_ids):
            raise ValueError("configuration transformation ids must be unique")
        negative_ids = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.configuration.negative_control_artifacts
        )
        if len(negative_ids) != len(set(negative_ids)):
            raise ValueError("negative-control artifacts must be unique")
        for feature in self.features:
            if not set(feature.lineage.transformation_ids) <= transformation_ids:
                raise ValueError("feature lineage references an unknown transformation")
        return self


class MechanisticFeatureDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: MechanisticDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)


class ConstructVariantPeptideMechanisticFeaturesRequest(FrozenModel):
    """Provisional request ABI bound to the M11-02 upstream artifact."""

    operation: Literal["construct_variant_peptide_mechanistic_features"] = M1103_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1103_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanisticFeatureConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1103_MAX_EVIDENCE
    )
    # The dossier does not freeze a feature catalogue or an estimator ABI.
    # These immutable declarations are therefore an explicitly provisional
    # seam: the runtime validates them, never traverses artifact payloads, and
    # preserves every declaration's lineage and value representation.
    declared_features: tuple[MechanisticFeature, ...] = Field(
        default=(), max_length=M1103_MAX_FEATURES
    )
    declared_relations: tuple[MechanisticRelation, ...] = Field(
        default=(), max_length=M1103_MAX_RELATIONS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructVariantPeptideMechanisticFeaturesRequest:
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal context request identifier")
        if self.upstream_result.media_type != M1103_M1102_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M11-02 upstream result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        if self.configuration.locked is not True:
            raise ValueError("mechanistic configuration must be locked")
        feature_ids = tuple(item.feature_id for item in self.declared_features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("declared feature ids must be unique")
        relation_ids = tuple(item.relation_id for item in self.declared_relations)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("declared relation ids must be unique")
        return self


class VariantPeptideMechanisticFeatureResult(FrozenModel):
    """Mechanistic feature result with invariant diagnostics and abstention."""

    output_type: Literal["variant_peptide_mechanistic_features"] = (
        "variant_peptide_mechanistic_features"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1103_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructVariantPeptideMechanisticFeaturesRequest
    status: MechanisticConstructionStatus
    feature_object: MechanisticFeatureObject | None = None
    diagnostics: tuple[MechanisticFeatureDiagnostic, ...] = Field(
        min_length=1, max_length=M1103_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanisticFindingCode, ...] = Field(default=(), max_length=M1103_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant_peptide"] = M1103_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1103_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideMechanisticFeatureResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
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


__all__ = [
    "M1103_CONTRACT_VERSION",
    "M1103_EVIDENCE_CLAIM",
    "M1103_GATE",
    "M1103_M1102_INPUT_MEDIA_TYPE",
    "M1103_MAX_CANONICAL_REQUEST_BYTES",
    "M1103_MAX_CANONICAL_RESULT_BYTES",
    "M1103_MAX_DIAGNOSTICS",
    "M1103_MAX_EVIDENCE",
    "M1103_MAX_FEATURES",
    "M1103_MAX_FINDINGS",
    "M1103_MAX_RELATIONS",
    "M1103_MAX_TRANSFORMATIONS",
    "M1103_MODULE_ID",
    "M1103_OPERATION",
    "M1103_OUTPUT_MEDIA_TYPE",
    "M1103_OWNER",
    "M1103_PARENT",
    "M1103_PROVISIONAL_ABI",
    "M1103_SAFETY_CLASS",
    "ConstructVariantPeptideMechanisticFeaturesRequest",
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
    "VariantPeptideMechanisticFeatureResult",
]
