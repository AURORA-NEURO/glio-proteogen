"""Strict contracts for M02-07 joint support-envelope routing.

M02-07 does not decide eight independent booleans.  A route is supported only
when one reviewed envelope admits the complete C02 identification context.
Compact receipts keep the public request transportable without copying the
potentially multi-megabyte M02-06 result into another module.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m02_04 import (
    IdentificationAssayProfile,
    IdentificationMetricStatus,
    IdentificationQualityDisposition,
    MetricObservationState,
    assay_profile_digest,
)
from glio_proteogen.contracts.m02_06 import HarmonizationDisposition
from glio_proteogen.contracts.m02_07.canonical import (
    configuration_digest,
    context_digest,
    context_receipt_digest,
    fact_digest,
    policy_digest,
    prerequisites_digest,
    profile_digest,
    request_manifest_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0207_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-07"
M0207_CONTRACT_VERSION: Final = "1.0.0"
M0207_MAX_ENVELOPES: Final = 64
M0207_MAX_FACT_VALUES: Final = 64
M0207_MAX_PLATFORM_IDS: Final = 2_048
M0207_MAX_ABSTENTIONS: Final = (M0207_MAX_ENVELOPES * 8) + 3
M0207_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0207_SUPPORT_LIMITATION_CODE: Final = "identification_support_routing_only"
M0207_AUTHORITY_LIMITATION_CODE: Final = "external_receipt_issuers_unverified"
M0207_SUPPORT_LIMITATION_STATEMENT: Final = (
    "This result routes a reviewed identification support envelope only; it does not infer "
    "protein subtype, proteotype, biology, kinase activity, or treatment response."
)
M0207_AUTHORITY_LIMITATION_STATEMENT: Final = (
    "Caller-supplied control, fact, quality, and harmonization receipt issuers are not "
    "authenticated by M02-07."
)
M0207_COMBINATION_REASON_CODE: Final = "support_envelope_combination_outside_domain"
M0207_COMBINATION_REMEDIATION_CODE: Final = "select_one_reviewed_joint_envelope"
M0207_PROFILE_EVIDENCE_LABEL: Final = "reviewed joint support-envelope profile"
M0207_POLICY_EVIDENCE_LABEL: Final = "reviewed support-routing policy"
M0207_ASSAY_EVIDENCE_LABEL: Final = "M02-04 assay profile"
M0207_QUALITY_EVIDENCE_LABEL: Final = "compact M02-04 quality receipt"
M0207_HARMONIZATION_EVIDENCE_LABEL: Final = "compact M02-06 harmonization receipt"
M0207_UNCERTAINTY_RATIONALES: Final = {
    "measurement": "M02-07 does not re-estimate measurement uncertainty.",
    "sampling": "M02-07 does not infer cohort or sampling uncertainty.",
    "parameter": "The reviewed joint support envelopes use fixed deterministic parameters.",
    "model_form": (
        "The deterministic joint-envelope router has no calibrated model-form uncertainty."
    ),
    "identification": (
        "Upstream identification uncertainty is preserved through compact receipts, "
        "not re-estimated."
    ),
    "support": "Support is a deterministic reviewed-envelope decision, not a probability.",
    "transport": "External receipt and evidence issuers are not authenticated by M02-07.",
}
M0207_SENSITIVITY_NOTES: Final = (
    "Missing or unknown support facts remain indeterminate and force abstention.",
    "Support requires one complete reviewed joint envelope; cross-envelope unions are not "
    "promoted.",
)
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_DIMENSION_COUNT: Final = 8
_DECLARED_DIMENSION_COUNT: Final = 4
_CONTEXT_ROLE_COUNT: Final = 3
_DECLARED_DIMENSIONS: Final = frozenset({"specimen", "disease_class", "reference", "intended_use"})


class IdentificationSupportDimension(StrEnum):
    ASSAY = "assay"
    SPECIMEN = "specimen"
    DISEASE_CLASS = "disease_class"
    QUALITY = "quality"
    COMPLETENESS = "completeness"
    PLATFORM = "platform"
    REFERENCE = "reference"
    INTENDED_USE = "intended_use"


class DeclaredSupportState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"


class DimensionSupportDecision(StrEnum):
    SUPPORTED = "supported"
    OUTSIDE_DOMAIN = "outside_domain"
    INDETERMINATE = "indeterminate"


class EnvelopeSupportDecision(StrEnum):
    CONFIRMED = "confirmed"
    ELIMINATED = "eliminated"
    PROVISIONAL = "provisional"


class IdentificationSupportDisposition(StrEnum):
    SUPPORTED = "supported"
    ABSTAINED = "abstained"


class IdentificationContextRole(StrEnum):
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"
    TREATMENT_HISTORY = "treatment_history"


class IdentificationAbstentionCode(StrEnum):
    DIMENSION_OUTSIDE_DOMAIN = "dimension_outside_domain"
    DIMENSION_INDETERMINATE = "dimension_indeterminate"
    PREREQUISITE_UNRELEASABLE = "prerequisite_unreleasable"
    JOINT_COMBINATION_OUTSIDE_DOMAIN = "joint_combination_outside_domain"


class IdentificationQualitySupportReceipt(FrozenModel):
    module_id: Literal["GLIO-PROTEOGEN-M02-04"] = "GLIO-PROTEOGEN-M02-04"
    result_digest: Sha256Digest
    disposition: IdentificationQualityDisposition
    assay_profile_digest: Sha256Digest
    assay_profile_evidence_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    metric_statuses: tuple[IdentificationMetricStatus, ...] = Field(min_length=6, max_length=6)
    completeness_state: MetricObservationState
    completeness_status: IdentificationMetricStatus
    completeness_value: float | None = Field(default=None, ge=0.0, le=1.0)
    artifact: ArtifactReference

    @model_validator(mode="after")
    def receipt_is_closed(self) -> IdentificationQualitySupportReceipt:
        if self.artifact.digest != self.result_digest:
            raise ValueError("M02-04 receipt artifact must bind the issued result digest")
        if self.completeness_state is MetricObservationState.OBSERVED:
            if self.completeness_value is None:
                raise ValueError("observed completeness receipt requires a value")
        elif self.completeness_value is not None:
            raise ValueError("non-observed completeness receipt cannot carry a value")
        if self.completeness_status is IdentificationMetricStatus.NOT_EVALUABLE:
            if self.completeness_state is MetricObservationState.OBSERVED:
                raise ValueError("not-evaluable completeness cannot be observed")
        elif self.completeness_state is not MetricObservationState.OBSERVED:
            raise ValueError("evaluable completeness must be observed")
        return self


class IdentificationHarmonizationSupportReceipt(FrozenModel):
    module_id: Literal["GLIO-PROTEOGEN-M02-06"] = "GLIO-PROTEOGEN-M02-06"
    result_digest: Sha256Digest
    disposition: HarmonizationDisposition
    m0204_result_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    unit: Literal["log2_abundance"] = "log2_abundance"
    platform_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0207_MAX_PLATFORM_IDS,
    )
    total_value_count: int = Field(gt=0, le=2_048)
    nonexcluded_value_count: int = Field(ge=0, le=2_048)
    evaluable_value_count: int = Field(ge=0, le=2_048)
    artifact: ArtifactReference

    @model_validator(mode="after")
    def receipt_is_closed(self) -> IdentificationHarmonizationSupportReceipt:
        if self.artifact.digest != self.result_digest:
            raise ValueError("M02-06 receipt artifact must bind the issued result digest")
        if len(set(self.platform_ids)) != len(self.platform_ids):
            raise ValueError("harmonization receipt platform identifiers must be unique")
        if not (
            self.evaluable_value_count <= self.nonexcluded_value_count <= self.total_value_count
        ):
            raise ValueError("harmonization receipt counts are inconsistent")
        return self


class IdentificationSupportPrerequisites(FrozenModel):
    assay_profile: IdentificationAssayProfile
    quality: IdentificationQualitySupportReceipt
    harmonization: IdentificationHarmonizationSupportReceipt

    @model_validator(mode="after")
    def receipts_share_one_lineage(self) -> IdentificationSupportPrerequisites:
        if assay_profile_digest(self.assay_profile) != self.quality.assay_profile_digest:
            raise ValueError("assay profile does not bind the M02-04 receipt")
        if self.assay_profile.evidence.digest != self.quality.assay_profile_evidence_digest:
            raise ValueError("assay evidence does not bind the M02-04 receipt")
        if self.harmonization.m0204_result_digest != self.quality.result_digest:
            raise ValueError("M02-06 receipt does not bind the supplied M02-04 receipt")
        if self.harmonization.identity_subject_digest != self.quality.identity_subject_digest:
            raise ValueError("M02-04 and M02-06 receipts use different identity lineages")
        return self


class DeclaredSupportFact(FrozenModel):
    dimension: IdentificationSupportDimension
    state: DeclaredSupportState
    values: tuple[Identifier, ...] = Field(default=(), max_length=M0207_MAX_FACT_VALUES)
    evidence: tuple[ArtifactReference, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def fact_shape_is_closed(self) -> DeclaredSupportFact:
        if self.dimension.value not in _DECLARED_DIMENSIONS:
            raise ValueError("this support dimension is derived from prerequisite receipts")
        if len(set(self.values)) != len(self.values):
            raise ValueError("declared support values must be unique")
        if len({item.digest for item in self.evidence}) != len(self.evidence):
            raise ValueError("declared support evidence digests must be unique")
        if self.state is DeclaredSupportState.OBSERVED:
            if not self.values:
                raise ValueError("observed support fact requires at least one value")
        elif self.values:
            raise ValueError("missing or unknown support fact cannot carry values")
        return self


class IdentificationContextReceipt(FrozenModel):
    role: IdentificationContextRole
    state: DeclaredSupportState
    reference: ArtifactReference


class IdentificationDimensionRemediation(FrozenModel):
    dimension: IdentificationSupportDimension
    outside_reason_code: Identifier
    indeterminate_reason_code: Identifier
    remediation_code: Identifier


class IdentificationSupportEnvelope(FrozenModel):
    envelope_id: Identifier
    assay_types: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    specimen_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    disease_class_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    quality_statuses: tuple[IdentificationMetricStatus, ...] = Field(min_length=1, max_length=4)
    minimum_completeness: float = Field(ge=0.0, le=1.0)
    platform_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    reference_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    intended_use_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    required_context_roles: tuple[IdentificationContextRole, ...] = Field(
        min_length=1,
        max_length=3,
    )
    remediations: tuple[IdentificationDimensionRemediation, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def envelope_is_one_closed_joint_domain(self) -> IdentificationSupportEnvelope:
        set_fields = (
            self.assay_types,
            self.specimen_terms,
            self.disease_class_terms,
            self.quality_statuses,
            self.platform_ids,
            self.reference_ids,
            self.intended_use_terms,
            self.required_context_roles,
        )
        if any(len(set(values)) != len(values) for values in set_fields):
            raise ValueError("support-envelope membership sets must be unique")
        dimensions = [item.dimension for item in self.remediations]
        if len(set(dimensions)) != _DIMENSION_COUNT or set(dimensions) != set(
            IdentificationSupportDimension
        ):
            raise ValueError("support envelope requires one remediation for every dimension")
        return self


class IdentificationSupportProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    envelopes: tuple[IdentificationSupportEnvelope, ...] = Field(
        min_length=1,
        max_length=M0207_MAX_ENVELOPES,
    )
    evidence: ArtifactReference

    @model_validator(mode="after")
    def envelope_ids_are_unique(self) -> IdentificationSupportProfile:
        ids = [item.envelope_id for item in self.envelopes]
        if len(set(ids)) != len(ids):
            raise ValueError("support-envelope identifiers must be unique")
        return self


class IdentificationSupportPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_envelopes: int = Field(default=M0207_MAX_ENVELOPES, gt=0, le=M0207_MAX_ENVELOPES)
    require_releasable_prerequisites: Literal[True] = True
    evidence: ArtifactReference


def _validate_route_boundary(  # noqa: PLR0913,PLR0917 - exact public boundary inputs.
    context: ExecutionContext,
    prerequisites: IdentificationSupportPrerequisites,
    profile: IdentificationSupportProfile,
    policy: IdentificationSupportPolicy,
    facts: tuple[DeclaredSupportFact, ...],
    receipts: tuple[IdentificationContextReceipt, ...],
) -> None:
    _require_authorized_context(context)
    fact_dimensions = [item.dimension for item in facts]
    if (
        len(facts) != _DECLARED_DIMENSION_COUNT
        or {item.value for item in fact_dimensions} != _DECLARED_DIMENSIONS
        or len(set(fact_dimensions)) != _DECLARED_DIMENSION_COUNT
    ):
        raise ValueError("route requires exactly the four caller-declared dimensions")
    roles = [item.role for item in receipts]
    if (
        len(receipts) != _CONTEXT_ROLE_COUNT
        or len(set(roles)) != _CONTEXT_ROLE_COUNT
        or set(roles) != set(IdentificationContextRole)
    ):
        raise ValueError("route requires every identification context receipt")
    if len(profile.envelopes) > policy.max_envelopes:
        raise ValueError("support profile exceeds its policy envelope capacity")
    expected_configuration = configuration_digest(profile, policy)
    if context.references.approved_configuration.evidence.digest != expected_configuration:
        raise ValueError("approved configuration does not bind M02-07")
    if (
        context.references.identity_lineage.binding_digest
        != prerequisites.quality.identity_subject_digest
    ):
        raise ValueError("identity control does not bind the prerequisite lineage")
    support_route_evidence_index(context, prerequisites, profile, policy, facts, receipts)


def support_route_evidence_index(  # noqa: PLR0913,PLR0917 - exact evidence sources.
    context: ExecutionContext,
    prerequisites: IdentificationSupportPrerequisites,
    profile: IdentificationSupportProfile,
    policy: IdentificationSupportPolicy,
    facts: tuple[DeclaredSupportFact, ...],
    receipts: tuple[IdentificationContextReceipt, ...],
) -> tuple[tuple[ArtifactReference, str], ...]:
    """Return the exact compact evidence index and authority-safe claims."""

    references = context.references
    sources: list[tuple[ArtifactReference, str]] = [
        (references.approved_configuration.evidence, "approved_configuration control"),
        (references.identity_lineage.evidence, "identity_lineage control"),
        (references.provenance.evidence, "provenance control"),
        (references.consent.evidence, "consent control"),
        (references.quality.evidence, "quality control"),
        (references.support.evidence, "support control"),
        (references.intended_use.evidence, "intended_use control"),
        (profile.evidence, M0207_PROFILE_EVIDENCE_LABEL),
        (policy.evidence, M0207_POLICY_EVIDENCE_LABEL),
        (prerequisites.assay_profile.evidence, M0207_ASSAY_EVIDENCE_LABEL),
        (prerequisites.quality.artifact, M0207_QUALITY_EVIDENCE_LABEL),
        (prerequisites.harmonization.artifact, M0207_HARMONIZATION_EVIDENCE_LABEL),
    ]
    for fact in facts:
        sources.extend(
            (reference, f"{fact.dimension.value} support fact") for reference in fact.evidence
        )
    sources.extend(
        (receipt.reference, f"{receipt.role.value} context receipt") for receipt in receipts
    )
    grouped: dict[str, tuple[ArtifactReference, set[str]]] = {}
    for reference, label in sources:
        existing = grouped.get(reference.digest)
        if existing is None:
            grouped[reference.digest] = (reference, {label})
        else:
            if existing[0] != reference:
                raise ValueError("one evidence digest cannot carry conflicting artifact metadata")
            existing[1].add(label)
    return tuple(
        (
            grouped[digest][0],
            "Caller-declared M02-07 evidence for "
            f"{', '.join(sorted(grouped[digest][1]))}; issuer is not authenticated.",
        )
        for digest in sorted(grouped)
    )


class RouteIdentificationSupportRequest(FrozenModel):
    operation: Literal["route_identification_support"] = "route_identification_support"
    contract_version: Literal["1.0.0"] = M0207_CONTRACT_VERSION
    context: ExecutionContext
    prerequisites: IdentificationSupportPrerequisites
    profile: IdentificationSupportProfile
    policy: IdentificationSupportPolicy
    declared_facts: tuple[DeclaredSupportFact, ...] = Field(min_length=4, max_length=4)
    context_receipts: tuple[IdentificationContextReceipt, ...] = Field(min_length=3, max_length=3)
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_bound_and_closed(self) -> RouteIdentificationSupportRequest:
        _validate_route_boundary(
            self.context,
            self.prerequisites,
            self.profile,
            self.policy,
            self.declared_facts,
            self.context_receipts,
        )
        if len(canonical_json_bytes(self)) > M0207_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("M02-07 canonical request exceeds the public ingress byte limit")
        return self


class IdentificationDimensionAssessment(FrozenModel):
    dimension: IdentificationSupportDimension
    decision: DimensionSupportDecision
    values: tuple[Identifier, ...] = Field(default=(), max_length=M0207_MAX_PLATFORM_IDS)
    numeric_value: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_code: Identifier | None = None
    remediation_code: Identifier | None = None

    @model_validator(mode="after")
    def assessment_codes_match_decision(self) -> IdentificationDimensionAssessment:
        has_codes = self.reason_code is not None and self.remediation_code is not None
        if (self.decision is DimensionSupportDecision.SUPPORTED) == has_codes:
            raise ValueError("only blocking dimension assessments require reason and remediation")
        return self


class IdentificationEnvelopeAssessment(FrozenModel):
    envelope_id: Identifier
    decision: EnvelopeSupportDecision
    dimensions: tuple[IdentificationDimensionAssessment, ...] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def decision_matches_dimensions(self) -> IdentificationEnvelopeAssessment:
        dimensions = [item.dimension for item in self.dimensions]
        if len(set(dimensions)) != _DIMENSION_COUNT or set(dimensions) != set(
            IdentificationSupportDimension
        ):
            raise ValueError("envelope assessment must cover every support dimension")
        decisions = {item.decision for item in self.dimensions}
        expected = (
            EnvelopeSupportDecision.ELIMINATED
            if DimensionSupportDecision.OUTSIDE_DOMAIN in decisions
            else EnvelopeSupportDecision.PROVISIONAL
            if DimensionSupportDecision.INDETERMINATE in decisions
            else EnvelopeSupportDecision.CONFIRMED
        )
        if self.decision is not expected:
            raise ValueError("envelope decision contradicts its dimension assessments")
        return self


class IdentificationAbstention(FrozenModel):
    code: IdentificationAbstentionCode
    envelope_id: Identifier | None = None
    dimension: IdentificationSupportDimension | None = None
    upstream_module_id: Literal["GLIO-PROTEOGEN-M02-04", "GLIO-PROTEOGEN-M02-06"] | None = None
    reason_code: Identifier
    remediation_code: Identifier

    @model_validator(mode="after")
    def abstention_shape_matches_code(self) -> IdentificationAbstention:
        if self.code in {
            IdentificationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
            IdentificationAbstentionCode.DIMENSION_INDETERMINATE,
        }:
            if self.envelope_id is None or self.dimension is None or self.upstream_module_id:
                raise ValueError("dimension abstention requires only envelope and dimension")
        elif self.code is IdentificationAbstentionCode.PREREQUISITE_UNRELEASABLE:
            if self.upstream_module_id is None or self.envelope_id or self.dimension:
                raise ValueError("prerequisite abstention requires only an upstream module")
        elif self.envelope_id or self.dimension or self.upstream_module_id:
            raise ValueError("combination abstention cannot name one envelope or dimension")
        return self


def _remediation(
    envelope: IdentificationSupportEnvelope,
    dimension: IdentificationSupportDimension,
) -> IdentificationDimensionRemediation:
    return next(item for item in envelope.remediations if item.dimension is dimension)


def _assessment(  # noqa: PLR0913 - one exact dimension projection.
    envelope: IdentificationSupportEnvelope,
    dimension: IdentificationSupportDimension,
    state: DeclaredSupportState,
    values: tuple[str, ...],
    allowed: set[str],
    *,
    numeric_value: float | None = None,
    minimum: float | None = None,
    context_supported: bool = True,
) -> IdentificationDimensionAssessment:
    remediation = _remediation(envelope, dimension)
    if state is not DeclaredSupportState.OBSERVED or not context_supported:
        decision = DimensionSupportDecision.INDETERMINATE
        reason = remediation.indeterminate_reason_code
    elif minimum is not None:
        decision = (
            DimensionSupportDecision.SUPPORTED
            if numeric_value is not None and numeric_value >= minimum
            else DimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    else:
        decision = (
            DimensionSupportDecision.SUPPORTED
            if set(values).issubset(allowed)
            else DimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    return IdentificationDimensionAssessment(
        dimension=dimension,
        decision=decision,
        values=tuple(sorted(values)),
        numeric_value=numeric_value,
        reason_code=None if decision is DimensionSupportDecision.SUPPORTED else reason,
        remediation_code=(
            None if decision is DimensionSupportDecision.SUPPORTED else remediation.remediation_code
        ),
    )


def _fact_map(
    facts: tuple[DeclaredSupportFact, ...],
) -> dict[IdentificationSupportDimension, DeclaredSupportFact]:
    return {item.dimension: item for item in facts}


def _context_is_supported(
    envelope: IdentificationSupportEnvelope,
    receipts: tuple[IdentificationContextReceipt, ...],
    dimension: IdentificationSupportDimension,
) -> bool:
    by_role = {item.role: item for item in receipts}
    relevant_roles = {
        IdentificationSupportDimension.REFERENCE: {
            IdentificationContextRole.GENOME_TRANSCRIPTOME,
            IdentificationContextRole.PTM_ANNOTATIONS,
        },
        IdentificationSupportDimension.INTENDED_USE: {
            IdentificationContextRole.TREATMENT_HISTORY,
        },
    }[dimension]
    return all(
        by_role[role].state is DeclaredSupportState.OBSERVED
        for role in envelope.required_context_roles
        if role in relevant_roles
    )


def _envelope_assessment(
    envelope: IdentificationSupportEnvelope,
    prerequisites: IdentificationSupportPrerequisites,
    facts: tuple[DeclaredSupportFact, ...],
    contexts: tuple[IdentificationContextReceipt, ...],
) -> IdentificationEnvelopeAssessment:
    fact_by_dimension = _fact_map(facts)
    quality = prerequisites.quality
    harmonization = prerequisites.harmonization
    quality_releasable = quality.disposition is IdentificationQualityDisposition.ACCEPTED
    harmonization_releasable = harmonization.disposition is HarmonizationDisposition.ACCEPTED
    completeness_observed = (
        quality_releasable
        and harmonization_releasable
        and quality.completeness_state is MetricObservationState.OBSERVED
        and quality.completeness_value is not None
        and harmonization.nonexcluded_value_count > 0
    )
    completeness = (
        min(
            quality.completeness_value,
            harmonization.evaluable_value_count / harmonization.nonexcluded_value_count,
        )
        if completeness_observed and quality.completeness_value is not None
        else None
    )
    specimen = fact_by_dimension[IdentificationSupportDimension.SPECIMEN]
    disease = fact_by_dimension[IdentificationSupportDimension.DISEASE_CLASS]
    reference = fact_by_dimension[IdentificationSupportDimension.REFERENCE]
    intended_use = fact_by_dimension[IdentificationSupportDimension.INTENDED_USE]
    dimensions = (
        _assessment(
            envelope,
            IdentificationSupportDimension.ASSAY,
            DeclaredSupportState.OBSERVED,
            (prerequisites.assay_profile.assay_type.value,),
            set(envelope.assay_types),
        ),
        _assessment(
            envelope,
            specimen.dimension,
            specimen.state,
            specimen.values,
            set(envelope.specimen_terms),
        ),
        _assessment(
            envelope,
            disease.dimension,
            disease.state,
            disease.values,
            set(envelope.disease_class_terms),
        ),
        _assessment(
            envelope,
            IdentificationSupportDimension.QUALITY,
            (DeclaredSupportState.OBSERVED if quality_releasable else DeclaredSupportState.UNKNOWN),
            tuple(item.value for item in quality.metric_statuses),
            {item.value for item in envelope.quality_statuses},
        ),
        _assessment(
            envelope,
            IdentificationSupportDimension.COMPLETENESS,
            (
                DeclaredSupportState.OBSERVED
                if completeness_observed
                else DeclaredSupportState.UNKNOWN
            ),
            (),
            set(),
            numeric_value=completeness,
            minimum=envelope.minimum_completeness,
        ),
        _assessment(
            envelope,
            IdentificationSupportDimension.PLATFORM,
            (
                DeclaredSupportState.OBSERVED
                if harmonization_releasable
                else DeclaredSupportState.UNKNOWN
            ),
            harmonization.platform_ids,
            set(envelope.platform_ids),
        ),
        _assessment(
            envelope,
            reference.dimension,
            reference.state,
            reference.values,
            set(envelope.reference_ids),
            context_supported=_context_is_supported(
                envelope,
                contexts,
                IdentificationSupportDimension.REFERENCE,
            ),
        ),
        _assessment(
            envelope,
            intended_use.dimension,
            intended_use.state,
            intended_use.values,
            set(envelope.intended_use_terms),
            context_supported=_context_is_supported(
                envelope,
                contexts,
                IdentificationSupportDimension.INTENDED_USE,
            ),
        ),
    )
    decisions = {item.decision for item in dimensions}
    decision = (
        EnvelopeSupportDecision.ELIMINATED
        if DimensionSupportDecision.OUTSIDE_DOMAIN in decisions
        else EnvelopeSupportDecision.PROVISIONAL
        if DimensionSupportDecision.INDETERMINATE in decisions
        else EnvelopeSupportDecision.CONFIRMED
    )
    return IdentificationEnvelopeAssessment(
        envelope_id=envelope.envelope_id,
        decision=decision,
        dimensions=dimensions,
    )


def _union_covers(
    assessments: tuple[IdentificationEnvelopeAssessment, ...],
) -> bool:
    for dimension in IdentificationSupportDimension:
        if not any(
            next(item for item in assessment.dimensions if item.dimension is dimension).decision
            is DimensionSupportDecision.SUPPORTED
            for assessment in assessments
        ):
            return False
    return True


def derive_support_route(
    prerequisites: IdentificationSupportPrerequisites,
    profile: IdentificationSupportProfile,
    facts: tuple[DeclaredSupportFact, ...],
    contexts: tuple[IdentificationContextReceipt, ...],
) -> tuple[
    tuple[IdentificationEnvelopeAssessment, ...],
    tuple[Identifier, ...],
    tuple[IdentificationAbstention, ...],
]:
    """Derive the complete joint-envelope decision from privacy-safe inputs."""

    assessments = tuple(
        sorted(
            (
                _envelope_assessment(envelope, prerequisites, facts, contexts)
                for envelope in profile.envelopes
            ),
            key=lambda item: item.envelope_id,
        )
    )
    matched = tuple(
        item.envelope_id
        for item in assessments
        if item.decision is EnvelopeSupportDecision.CONFIRMED
    )
    if matched:
        return assessments, matched, ()
    abstentions: list[IdentificationAbstention] = []
    if prerequisites.quality.disposition is not IdentificationQualityDisposition.ACCEPTED:
        abstentions.append(
            IdentificationAbstention(
                code=IdentificationAbstentionCode.PREREQUISITE_UNRELEASABLE,
                upstream_module_id="GLIO-PROTEOGEN-M02-04",
                reason_code="m0204.quality.unreleasable",
                remediation_code="resolve_upstream_prerequisite",
            )
        )
    if prerequisites.harmonization.disposition is not HarmonizationDisposition.ACCEPTED:
        abstentions.append(
            IdentificationAbstention(
                code=IdentificationAbstentionCode.PREREQUISITE_UNRELEASABLE,
                upstream_module_id="GLIO-PROTEOGEN-M02-06",
                reason_code="m0206.harmonization.unreleasable",
                remediation_code="resolve_upstream_prerequisite",
            )
        )
    for envelope in assessments:
        for dimension in envelope.dimensions:
            if dimension.decision is DimensionSupportDecision.SUPPORTED:
                continue
            abstentions.append(
                IdentificationAbstention(
                    code=(
                        IdentificationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
                        if dimension.decision is DimensionSupportDecision.OUTSIDE_DOMAIN
                        else IdentificationAbstentionCode.DIMENSION_INDETERMINATE
                    ),
                    envelope_id=envelope.envelope_id,
                    dimension=dimension.dimension,
                    reason_code=dimension.reason_code or "support_dimension_unresolved",
                    remediation_code=dimension.remediation_code or "review_support_dimension",
                )
            )
    if _union_covers(assessments):
        abstentions.append(
            IdentificationAbstention(
                code=IdentificationAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN,
                reason_code=M0207_COMBINATION_REASON_CODE,
                remediation_code=M0207_COMBINATION_REMEDIATION_CODE,
            )
        )
    unique = {
        (
            item.code.value,
            item.envelope_id or "",
            item.dimension.value if item.dimension else "",
            item.upstream_module_id or "",
            item.reason_code,
            item.remediation_code,
        ): item
        for item in abstentions
    }
    return assessments, (), tuple(unique[key] for key in sorted(unique))


class IdentificationSupportRouteResult(FrozenModel):
    output_type: Literal["identification_support_route_result"] = (
        "identification_support_route_result"
    )
    route_id: Identifier
    result_version: Literal["1.0.0"] = M0207_CONTRACT_VERSION
    request_digest: Sha256Digest
    context_digest: Sha256Digest
    context: ExecutionContext
    prerequisites_digest: Sha256Digest
    prerequisites: IdentificationSupportPrerequisites
    profile_digest: Sha256Digest
    profile: IdentificationSupportProfile
    policy_digest: Sha256Digest
    policy: IdentificationSupportPolicy
    configuration_digest: Sha256Digest
    declared_facts: tuple[DeclaredSupportFact, ...] = Field(min_length=4, max_length=4)
    context_receipts: tuple[IdentificationContextReceipt, ...] = Field(min_length=3, max_length=3)
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: IdentificationSupportDisposition
    matched_envelope_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0207_MAX_ENVELOPES)
    envelope_assessments: tuple[IdentificationEnvelopeAssessment, ...] = Field(
        min_length=1,
        max_length=M0207_MAX_ENVELOPES,
    )
    abstention_reasons: tuple[IdentificationAbstention, ...] = Field(
        default=(),
        max_length=M0207_MAX_ABSTENTIONS,
    )
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=128)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> IdentificationSupportRouteResult:
        _validate_result(self)
        expected = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected)
        elif self.result_digest != expected:
            raise ValueError("M02-07 result digest does not match its content")
        return self


def _validate_result(result: IdentificationSupportRouteResult) -> None:
    _validate_route_boundary(
        result.context,
        result.prerequisites,
        result.profile,
        result.policy,
        result.declared_facts,
        result.context_receipts,
    )
    if result.context_digest != context_digest(result.context):
        raise ValueError("support-route execution context digest is inconsistent")
    if result.profile_digest != profile_digest(result.profile):
        raise ValueError("support-route profile digest is inconsistent")
    if result.policy_digest != policy_digest(result.policy):
        raise ValueError("support-route policy digest is inconsistent")
    if result.configuration_digest != configuration_digest(result.profile, result.policy):
        raise ValueError("support-route configuration digest is inconsistent")
    if result.prerequisites_digest != prerequisites_digest(result.prerequisites):
        raise ValueError("support-route prerequisite digest is inconsistent")
    expected_request = request_manifest_digest(
        active_context_digest=result.context_digest,
        active_prerequisites_digest=result.prerequisites_digest,
        active_profile_digest=result.profile_digest,
        active_policy_digest=result.policy_digest,
        fact_digests=tuple(fact_digest(item) for item in result.declared_facts),
        context_receipt_digests=tuple(
            context_receipt_digest(item) for item in result.context_receipts
        ),
        supersedes_result_digest=result.supersedes_result_digest,
    )
    if result.request_digest != expected_request:
        raise ValueError("support-route request digest is inconsistent")
    expected_assessments, expected_matches, expected_abstentions = derive_support_route(
        result.prerequisites,
        result.profile,
        result.declared_facts,
        result.context_receipts,
    )
    if (
        result.envelope_assessments != expected_assessments
        or result.matched_envelope_ids != expected_matches
        or result.abstention_reasons != expected_abstentions
    ):
        raise ValueError("support-route output contradicts joint-envelope evaluation")
    expected_disposition = (
        IdentificationSupportDisposition.SUPPORTED
        if expected_matches
        else IdentificationSupportDisposition.ABSTAINED
    )
    if result.disposition is not expected_disposition:
        raise ValueError("support-route disposition contradicts its envelope matches")
    expected_support = {
        IdentificationSupportDisposition.SUPPORTED: (
            SupportStatus.LIMITED,
            "identification_support_confirmed",
            "One reviewed joint identification support envelope was confirmed.",
            False,
        ),
        IdentificationSupportDisposition.ABSTAINED: (
            SupportStatus.UNSUPPORTED,
            "identification_support_abstained",
            "No reviewed joint identification support envelope was confirmed.",
            True,
        ),
    }[result.disposition]
    if (
        result.support.status,
        result.support.reason_code,
        result.support.rationale,
        result.human_review_required,
    ) != expected_support:
        raise ValueError("support-route support envelope contradicts disposition")
    expected_limitations = {
        M0207_SUPPORT_LIMITATION_CODE: M0207_SUPPORT_LIMITATION_STATEMENT,
        M0207_AUTHORITY_LIMITATION_CODE: M0207_AUTHORITY_LIMITATION_STATEMENT,
    }
    if {item.code: item.statement for item in result.limitations} != expected_limitations:
        raise ValueError("support route requires both fixed limitations")
    suffix = result.request_digest.removeprefix("sha256:")
    provenance = result.provenance
    if (
        result.route_id != f"route.m0207.{suffix}"
        or provenance.activity_id != f"activity.m0207.{suffix}"
        or provenance.actor_id != result.context.actor_id
        or provenance.module_id != M0207_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or result.completed_at != result.context.occurred_at
        or provenance.configuration_digest != result.configuration_digest
    ):
        raise ValueError("M02-07 provenance is inconsistent")
    required = {
        result.request_digest,
        result.context_digest,
        result.prerequisites_digest,
        result.profile_digest,
        result.policy_digest,
        result.configuration_digest,
        result.prerequisites.quality.result_digest,
        result.prerequisites.harmonization.result_digest,
        *(item.evidence_digest for item in provenance.control_decisions),
    }
    if set(provenance.input_digests) != required or len(provenance.input_digests) != len(required):
        raise ValueError("M02-07 provenance must contain the exact unique input digest set")
    _validate_controls(result)
    _validate_evidence(result)
    _validate_uncertainty(result.uncertainty)


def _validate_controls(result: IdentificationSupportRouteResult) -> None:
    references = result.context.references
    identity_subject = result.prerequisites.quality.identity_subject_digest
    expected = {
        "approved_configuration": (
            references.approved_configuration.decision_id,
            references.approved_configuration.state.value,
            references.approved_configuration.policy_version,
            references.approved_configuration.evidence.digest,
            None,
        ),
        "identity_lineage": (
            references.identity_lineage.decision_id,
            references.identity_lineage.state.value,
            references.identity_lineage.policy_version,
            references.identity_lineage.evidence.digest,
            identity_subject,
        ),
        "provenance": (
            references.provenance.decision_id,
            references.provenance.state.value,
            references.provenance.policy_version,
            references.provenance.evidence.digest,
            None,
        ),
        "consent": (
            references.consent.decision_id,
            references.consent.state.value,
            references.consent.policy_version,
            references.consent.evidence.digest,
            None,
        ),
        "quality": (
            references.quality.decision_id,
            references.quality.state.value,
            references.quality.policy_version,
            references.quality.evidence.digest,
            None,
        ),
        "support": (
            references.support.decision_id,
            references.support.state.value,
            references.support.policy_version,
            references.support.evidence.digest,
            None,
        ),
        "intended_use": (
            references.intended_use.decision_id,
            references.intended_use.state.value,
            references.intended_use.policy_version,
            references.intended_use.evidence.digest,
            None,
        ),
    }
    actual = {
        item.role.value: (
            item.decision_id,
            item.state,
            item.policy_version,
            item.evidence_digest,
            item.subject_digest,
        )
        for item in result.provenance.control_decisions
    }
    if actual != expected:
        raise ValueError("M02-07 control decisions do not match the embedded context")
    consent = references.consent
    if (
        result.provenance.consent_decision_id,
        result.provenance.consent_state,
        result.provenance.consent_policy_version,
        result.provenance.consent_evidence_digest,
    ) != (
        consent.decision_id,
        consent.state,
        consent.policy_version,
        consent.evidence.digest,
    ):
        raise ValueError("M02-07 consent provenance is inconsistent")


def _validate_evidence(result: IdentificationSupportRouteResult) -> None:
    expected_index = support_route_evidence_index(
        result.context,
        result.prerequisites,
        result.profile,
        result.policy,
        result.declared_facts,
        result.context_receipts,
    )
    expected = {
        reference.digest: (reference, "evidence", claim) for reference, claim in expected_index
    }
    actual = {
        item.reference.digest: (item.reference, item.role, item.claim) for item in result.evidence
    }
    if len(actual) != len(result.evidence) or actual != expected:
        raise ValueError("M02-07 evidence index or authority-safe claims are inconsistent")


def _validate_uncertainty(uncertainty: UncertaintyProfile) -> None:
    for dimension, rationale in M0207_UNCERTAINTY_RATIONALES.items():
        estimate = getattr(uncertainty, dimension)
        if (
            estimate.state is not EstimateState.NOT_ESTIMABLE
            or estimate.probability is not None
            or estimate.rationale != rationale
        ):
            raise ValueError("M02-07 uncertainty must remain deterministic and not estimable")
    if uncertainty.sensitivity_notes != M0207_SENSITIVITY_NOTES:
        raise ValueError("M02-07 uncertainty sensitivity notes are inconsistent")


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M02-07")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage is not resolved")
    if any(
        item.state is not UpstreamDecisionState.ACCEPTED
        for item in (
            references.approved_configuration,
            references.provenance,
            references.quality,
            references.support,
            references.intended_use,
        )
    ):
        raise ValueError("upstream controls do not authorize M02-07")


__all__ = [
    "M0207_AUTHORITY_LIMITATION_CODE",
    "M0207_AUTHORITY_LIMITATION_STATEMENT",
    "M0207_CONTRACT_VERSION",
    "M0207_MAX_ABSTENTIONS",
    "M0207_MAX_CANONICAL_REQUEST_BYTES",
    "M0207_MAX_ENVELOPES",
    "M0207_MAX_PLATFORM_IDS",
    "M0207_MODULE_ID",
    "M0207_SENSITIVITY_NOTES",
    "M0207_SUPPORT_LIMITATION_CODE",
    "M0207_SUPPORT_LIMITATION_STATEMENT",
    "M0207_UNCERTAINTY_RATIONALES",
    "DeclaredSupportFact",
    "DeclaredSupportState",
    "DimensionSupportDecision",
    "EnvelopeSupportDecision",
    "IdentificationAbstention",
    "IdentificationAbstentionCode",
    "IdentificationContextReceipt",
    "IdentificationContextRole",
    "IdentificationDimensionAssessment",
    "IdentificationDimensionRemediation",
    "IdentificationEnvelopeAssessment",
    "IdentificationHarmonizationSupportReceipt",
    "IdentificationQualitySupportReceipt",
    "IdentificationSupportDimension",
    "IdentificationSupportDisposition",
    "IdentificationSupportEnvelope",
    "IdentificationSupportPolicy",
    "IdentificationSupportPrerequisites",
    "IdentificationSupportProfile",
    "IdentificationSupportRouteResult",
    "RouteIdentificationSupportRequest",
    "derive_support_route",
    "support_route_evidence_index",
]
