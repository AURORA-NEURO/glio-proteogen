"""Provisional M10-02 representation and feature-constructor contracts.

The M10-02 dossier requires feature lineage, scaling, masks, covariates,
provenance, deterministic locked transformations, and leakage-safe behavior.
It does not freeze the public ABI, feature catalogue, operation, media type,
or capacities.  All symbols here are provisional scaffolding pending owner
review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M10-02 dossier slice.
M1002_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-02"
M1002_OPERATION: Final = "construct_protein_rna_representation"
M1002_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1002_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-02+json"
M1002_M1001_SCHEMA_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-01+json"
M1002_PARENT: Final = "protein_rna_discordance"
M1002_OWNER: Final = "Bioinformatics"
M1002_SAFETY_CLASS: Final = "S2"
M1002_GATE: Final = "G1"
M1002_PROVISIONAL_ABI: Final = True
M1002_MAX_FEATURES: Final = 2_048
M1002_MAX_TRANSFORMATIONS: Final = 512
M1002_MAX_COVARIATES: Final = 128
M1002_MAX_EVIDENCE: Final = 64
M1002_MAX_DIAGNOSTICS: Final = 128
M1002_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1002_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1002_EVIDENCE_CLAIM: Final = (
    "Caller-declared M10-02 representation evidence; issuer authority is not authenticated."
)


class RepresentationMethod(StrEnum):
    LEARNED_MECHANISTIC = "learned_mechanistic"
    ELASTIC_NET_CONSEQUENCE = "elastic_net_consequence"
    CN_TO_PROTEIN_REGRESSION = "cn_to_protein_regression"
    SELECTIVE_ENSEMBLE = "selective_ensemble"


class RepresentationFeatureValueKind(StrEnum):
    SCALAR = "scalar"
    VECTOR = "vector"
    CATEGORICAL = "categorical"


class RepresentationMissingness(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    MASKED = "masked"
    UNSUPPORTED = "unsupported"


class ScalingMethod(StrEnum):
    NONE = "none"
    STANDARD = "standard"
    ROBUST = "robust"
    LOG = "log"


class CovariateRole(StrEnum):
    BIOLOGICAL = "biological"
    TECHNICAL = "technical"
    BATCH = "batch"
    QUALITY = "quality"


class RepresentationDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class RepresentationConstructionStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class FeatureLineage(FrozenModel):
    """Immutable lineage linking every output feature to source artifacts."""

    feature_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1002_MAX_EVIDENCE
    )
    transformation_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1002_MAX_TRANSFORMATIONS
    )
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)


class TransformationStep(FrozenModel):
    """Deterministic transformation with explicit fit scope and leakage guard."""

    transformation_id: Identifier
    operation: NonEmptyStr
    input_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1002_MAX_FEATURES)
    output_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1002_MAX_FEATURES)
    fit_scope: Literal["training_only", "reference_only", "none"]
    fit_artifact: ArtifactReference | None = None
    deterministic: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def leakage_guard_is_closed(self) -> TransformationStep:
        if self.fit_scope == "none" and self.fit_artifact is not None:
            raise ValueError("fit artifact is forbidden for a fit-free transformation")
        if self.fit_scope != "none" and self.fit_artifact is None:
            raise ValueError("fitted transformation requires an explicit fit artifact")
        return self


class ScalingPolicy(FrozenModel):
    scaling_id: Identifier
    method: ScalingMethod
    fit_scope: Literal["training_only", "reference_only", "none"]
    parameters_artifact: ArtifactReference | None = None
    locked: Literal[True] = True

    @model_validator(mode="after")
    def scaling_fit_scope_is_closed(self) -> ScalingPolicy:
        if self.fit_scope == "none" and self.parameters_artifact is not None:
            raise ValueError("fit parameters are forbidden when scaling fit scope is none")
        if self.fit_scope != "none" and self.parameters_artifact is None:
            raise ValueError("fitted scaling requires an explicit parameters artifact")
        return self


class MaskPolicy(FrozenModel):
    mask_id: Identifier
    missingness_states: tuple[RepresentationMissingness, ...] = Field(
        min_length=1,
        max_length=len(RepresentationMissingness),
    )
    replacement: Literal["mask_token", "missing_indicator", "none"]
    locked: Literal[True] = True


class CovariateDefinition(FrozenModel):
    covariate_id: Identifier
    role: CovariateRole
    artifact: ArtifactReference
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)


class RepresentationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: RepresentationMethod
    transformations: tuple[TransformationStep, ...] = Field(
        min_length=1, max_length=M1002_MAX_TRANSFORMATIONS
    )
    scaling: tuple[ScalingPolicy, ...] = Field(default=(), max_length=M1002_MAX_FEATURES)
    masks: tuple[MaskPolicy, ...] = Field(default=(), max_length=M1002_MAX_FEATURES)
    covariates: tuple[CovariateDefinition, ...] = Field(
        default=(), max_length=M1002_MAX_COVARIATES
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_ids_are_unique(self) -> RepresentationConfiguration:
        ids = (
            tuple(item.transformation_id for item in self.transformations),
            tuple(item.scaling_id for item in self.scaling),
            tuple(item.mask_id for item in self.masks),
            tuple(item.covariate_id for item in self.covariates),
        )
        if any(len(values) != len(set(values)) for values in ids):
            raise ValueError("representation configuration identifiers must be unique")
        return self


class RepresentationFeature(FrozenModel):
    feature_id: Identifier
    value_kind: RepresentationFeatureValueKind
    state: RepresentationMissingness
    unit: NonEmptyStr
    scalar_value: float | None = None
    category: NonEmptyStr | None = None
    vector: tuple[float, ...] = Field(default=(), max_length=4_096)
    lineage: FeatureLineage
    scaling_id: Identifier | None = None
    mask_id: Identifier | None = None
    covariate_ids: tuple[Identifier, ...] = Field(default=(), max_length=M1002_MAX_COVARIATES)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> RepresentationFeature:
        present = sum(
            (
                self.scalar_value is not None,
                self.category is not None,
                bool(self.vector),
            )
        )
        if self.state is RepresentationMissingness.OBSERVED:
            if present != 1:
                raise ValueError("observed representation feature requires exactly one value")
        elif present:
            raise ValueError("non-observed representation feature cannot carry a value")
        if (
            self.value_kind is RepresentationFeatureValueKind.SCALAR
            and self.scalar_value is None
            and self.state is RepresentationMissingness.OBSERVED
        ):
            raise ValueError("scalar representation feature requires a scalar value")
        if (
            self.value_kind is RepresentationFeatureValueKind.CATEGORICAL
            and self.category is None
            and self.state is RepresentationMissingness.OBSERVED
        ):
            raise ValueError("categorical representation feature requires a category")
        if (
            self.value_kind is RepresentationFeatureValueKind.VECTOR
            and not self.vector
            and self.state is RepresentationMissingness.OBSERVED
        ):
            raise ValueError("vector representation feature requires vector values")
        return self


class AnalysisRepresentation(FrozenModel):
    """Versioned deterministic representation with complete feature lineage."""

    representation_id: Identifier
    version: SemanticVersion
    method: RepresentationMethod
    features: tuple[RepresentationFeature, ...] = Field(
        min_length=1, max_length=M1002_MAX_FEATURES
    )
    transformations: tuple[TransformationStep, ...] = Field(
        min_length=1, max_length=M1002_MAX_TRANSFORMATIONS
    )
    covariates: tuple[CovariateDefinition, ...] = Field(
        default=(), max_length=M1002_MAX_COVARIATES
    )
    deterministic: Literal[True] = True
    lineage_complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def representation_is_closed(self) -> AnalysisRepresentation:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("representation feature ids must be unique")
        transformation_ids = {item.transformation_id for item in self.transformations}
        for feature in self.features:
            if not set(feature.lineage.transformation_ids) <= transformation_ids:
                raise ValueError("feature lineage references an unknown transformation")
        covariate_ids = {item.covariate_id for item in self.covariates}
        for feature in self.features:
            if not set(feature.covariate_ids) <= covariate_ids:
                raise ValueError("feature references an unknown covariate")
        return self


class RepresentationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: RepresentationDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)


class ConstructProteinRnaRepresentationRequest(FrozenModel):
    """Provisional request ABI bound to the M10-01 formal-state schema."""

    operation: Literal["construct_protein_rna_representation"] = M1002_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1002_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    formal_state_schema: ArtifactReference
    configuration: RepresentationConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1002_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructProteinRnaRepresentationRequest:
        if self.formal_state_schema.media_type != M1002_M1001_SCHEMA_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M10-01 formal-state schema")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        return self


class ProteinRnaRepresentationResult(FrozenModel):
    """Representation result with explicit leakage diagnostics and abstention."""

    output_type: Literal["protein_rna_analysis_representation"] = (
        "protein_rna_analysis_representation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1002_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructProteinRnaRepresentationRequest
    status: RepresentationConstructionStatus
    representation: AnalysisRepresentation | None = None
    diagnostics: tuple[RepresentationDiagnostic, ...] = Field(
        min_length=1, max_length=M1002_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1002_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1002_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaRepresentationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed = {
            RepresentationDiagnosticStatus.FAIL,
            RepresentationDiagnosticStatus.NOT_EVALUABLE,
        }
        if self.status is RepresentationConstructionStatus.CONSTRUCTED:
            if (
                self.representation is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
            ):
                raise ValueError("constructed result requires supported, leakage-safe output")
        elif (
            self.representation is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no representation and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1002_CONTRACT_VERSION",
    "M1002_EVIDENCE_CLAIM",
    "M1002_GATE",
    "M1002_M1001_SCHEMA_MEDIA_TYPE",
    "M1002_MAX_CANONICAL_REQUEST_BYTES",
    "M1002_MAX_CANONICAL_RESULT_BYTES",
    "M1002_MAX_COVARIATES",
    "M1002_MAX_DIAGNOSTICS",
    "M1002_MAX_EVIDENCE",
    "M1002_MAX_FEATURES",
    "M1002_MAX_TRANSFORMATIONS",
    "M1002_MODULE_ID",
    "M1002_OPERATION",
    "M1002_OUTPUT_MEDIA_TYPE",
    "M1002_OWNER",
    "M1002_PARENT",
    "M1002_PROVISIONAL_ABI",
    "M1002_SAFETY_CLASS",
    "AnalysisRepresentation",
    "ConstructProteinRnaRepresentationRequest",
    "CovariateDefinition",
    "CovariateRole",
    "FeatureLineage",
    "MaskPolicy",
    "ProteinRnaRepresentationResult",
    "RepresentationConfiguration",
    "RepresentationConstructionStatus",
    "RepresentationDiagnostic",
    "RepresentationDiagnosticStatus",
    "RepresentationFeature",
    "RepresentationFeatureValueKind",
    "RepresentationMethod",
    "RepresentationMissingness",
    "ScalingMethod",
    "ScalingPolicy",
    "TransformationStep",
]
