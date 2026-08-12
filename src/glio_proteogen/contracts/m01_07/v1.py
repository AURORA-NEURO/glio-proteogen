"""Strict public contracts for deterministic M01-07 support routing."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from glio_proteogen.contracts.m01_07.canonical import (
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlRole,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0107_MODULE_ID: Final = "GLIO-PROTEOGEN-M01-07"
M0107_CONTRACT_VERSION: Final = "1.0.0"
M0107_MAX_CRITERIA: Final = 256
M0107_MAX_EVIDENCE: Final = 256
M0107_MAX_REFERENCES_PER_EVIDENCE: Final = 64
M0107_SUPPORT_LIMITATION_CODE: Final = "support_routing_only"
M0107_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)

ValueUnit = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9%][A-Za-z0-9%._/*^-]*$",
    ),
]


class SupportDimension(StrEnum):
    ASSAY = "assay"
    SPECIMEN = "specimen"
    DISEASE_CLASS = "disease_class"
    QUALITY = "quality"
    COMPLETENESS = "completeness"
    PLATFORM = "platform"
    REFERENCE = "reference"
    INTENDED_USE = "intended_use"


class EvidenceState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class CriterionKind(StrEnum):
    TERM_IN_SET = "term_in_set"
    NUMERIC_RANGE = "numeric_range"
    BOOLEAN_EQUALS = "boolean_equals"
    REQUIRED_PRESENT = "required_present"


class CriterionDecision(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INDETERMINATE = "indeterminate"


class RouteDecision(StrEnum):
    SUPPORTED = "supported"
    ABSTAINED = "abstained"


class SupportCriterion(FrozenModel):
    criterion_id: Identifier
    dimension: SupportDimension
    evidence_id: Identifier
    kind: CriterionKind
    required: bool = True
    allow_not_applicable: bool = False
    allowed_terms: tuple[Identifier, ...] = Field(default=(), max_length=256)
    minimum: float | None = None
    maximum: float | None = None
    expected_bool: bool | None = None
    unit: ValueUnit | None = None
    reason_code: Identifier
    remediation_code: Identifier
    remediation_path: NonEmptyStr

    @model_validator(mode="after")
    def predicate_is_closed(self) -> SupportCriterion:  # noqa: PLR0912
        if self.required and self.allow_not_applicable:
            raise ValueError("required support criteria cannot allow not-applicable evidence")
        if self.kind is CriterionKind.TERM_IN_SET:
            if not self.allowed_terms or len(self.allowed_terms) != len(set(self.allowed_terms)):
                raise ValueError("term support criteria require unique allowed terms")
            if any(
                value is not None
                for value in (self.minimum, self.maximum, self.expected_bool, self.unit)
            ):
                raise ValueError("term support criteria cannot carry other predicate fields")
        elif self.kind is CriterionKind.NUMERIC_RANGE:
            if self.minimum is None and self.maximum is None:
                raise ValueError("numeric support criteria require at least one bound")
            if self.unit is None:
                raise ValueError("numeric support criteria require a unit")
            if self.allowed_terms or self.expected_bool is not None:
                raise ValueError("numeric support criteria cannot carry term or boolean fields")
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError("numeric support criterion bounds must be ordered")
        elif self.kind is CriterionKind.BOOLEAN_EQUALS:
            if self.expected_bool is None:
                raise ValueError("boolean support criteria require an expected value")
            if self.allowed_terms or any(
                value is not None for value in (self.minimum, self.maximum, self.unit)
            ):
                raise ValueError("boolean support criteria cannot carry other predicate fields")
        elif self.allowed_terms or any(
            value is not None
            for value in (self.minimum, self.maximum, self.expected_bool, self.unit)
        ):
            raise ValueError("presence criteria cannot carry comparison fields")
        return self


class SupportRoutingProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    criteria: tuple[SupportCriterion, ...] = Field(
        min_length=len(SupportDimension),
        max_length=M0107_MAX_CRITERIA,
    )
    evidence: ArtifactReference

    @model_validator(mode="after")
    def criteria_are_unique_and_cover_every_dimension(self) -> SupportRoutingProfile:
        identifiers = [criterion.criterion_id for criterion in self.criteria]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("support criterion identifiers must be unique")
        if {criterion.dimension for criterion in self.criteria} != set(SupportDimension):
            raise ValueError("support profile must cover every routing dimension")
        return self


class SupportEvidence(FrozenModel):
    evidence_id: Identifier
    dimension: SupportDimension
    state: EvidenceState
    value: str | float | bool | None = None
    unit: ValueUnit | None = None
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0107_MAX_REFERENCES_PER_EVIDENCE,
    )

    @model_validator(mode="after")
    def value_matches_state(self) -> SupportEvidence:
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("support evidence references must be unique")
        if self.state is EvidenceState.OBSERVED and self.value is None:
            raise ValueError("observed support evidence requires a value")
        if self.state is not EvidenceState.OBSERVED and (
            self.value is not None or self.unit is not None
        ):
            raise ValueError("non-observed support evidence cannot carry a value or unit")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("support evidence numeric values must be finite")
        return self


class SupportRoutingPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_criteria: int = Field(default=M0107_MAX_CRITERIA, gt=0, le=M0107_MAX_CRITERIA)
    max_evidence: int = Field(default=M0107_MAX_EVIDENCE, gt=0, le=M0107_MAX_EVIDENCE)


class RouteSupportRequest(FrozenModel):
    operation: Literal["route_support"] = "route_support"
    contract_version: Literal["1.0.0"] = M0107_CONTRACT_VERSION
    context: ExecutionContext
    profile: SupportRoutingProfile
    policy: SupportRoutingPolicy
    evidence: tuple[SupportEvidence, ...] = Field(
        min_length=1,
        max_length=M0107_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_configuration_bound(self) -> RouteSupportRequest:
        _require_authorized_context(self.context)
        if len(self.profile.criteria) > self.policy.max_criteria or len(
            self.evidence
        ) > self.policy.max_evidence:
            raise ValueError("support routing request exceeds the active policy")
        identifiers = [item.evidence_id for item in self.evidence]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("support evidence identifiers must be unique")
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        referenced = {criterion.evidence_id for criterion in self.profile.criteria}
        if referenced != set(evidence_by_id):
            raise ValueError("support profile and evidence identifiers must close exactly")
        for criterion in self.profile.criteria:
            item = evidence_by_id[criterion.evidence_id]
            if item.dimension is not criterion.dimension:
                raise ValueError("support evidence dimension contradicts its criterion")
            _validate_observed_value(criterion, item)
        expected = configuration_digest(self.profile, self.policy)
        if self.context.references.approved_configuration.evidence.digest != expected:
            raise ValueError("approved configuration does not bind the support router")
        return self


class CriterionAssessment(FrozenModel):
    criterion_id: Identifier
    dimension: SupportDimension
    required: bool
    allow_not_applicable: bool
    evidence_state: EvidenceState
    decision: CriterionDecision
    blocks_route: bool
    reason_code: Identifier | None = None
    remediation_code: Identifier | None = None
    remediation_path: NonEmptyStr | None = None
    evidence_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1,
        max_length=M0107_MAX_REFERENCES_PER_EVIDENCE,
    )

    @model_validator(mode="after")
    def explanation_matches_decision(self) -> CriterionAssessment:
        if len(self.evidence_digests) != len(set(self.evidence_digests)):
            raise ValueError("criterion assessment evidence digests must be unique")
        supported = self.decision is CriterionDecision.SUPPORTED
        explanations = (self.reason_code, self.remediation_code, self.remediation_path)
        if supported and any(value is not None for value in explanations):
            raise ValueError("supported criteria cannot carry abstention remediation")
        if not supported and any(value is None for value in explanations):
            raise ValueError("non-supported criteria require reason and remediation")
        expected_block = self.decision is not CriterionDecision.SUPPORTED
        if self.blocks_route is not expected_block:
            raise ValueError("criterion blocking state contradicts its decision")
        if self.evidence_state is EvidenceState.OBSERVED:
            if self.decision is CriterionDecision.INDETERMINATE:
                raise ValueError("observed evidence cannot produce an indeterminate assessment")
        elif self.evidence_state in {EvidenceState.MISSING, EvidenceState.UNKNOWN}:
            if self.decision is not CriterionDecision.INDETERMINATE:
                raise ValueError("missing or unknown evidence must remain indeterminate")
        else:
            expected = (
                CriterionDecision.SUPPORTED
                if not self.required and self.allow_not_applicable
                else CriterionDecision.INDETERMINATE
            )
            if self.decision is not expected:
                raise ValueError("not-applicable evidence contradicts criterion policy")
        return self


class SupportRoutingResult(FrozenModel):
    output_type: Literal["support_routing_result"] = "support_routing_result"
    routing_id: Identifier
    result_version: Literal["1.0.0"] = M0107_CONTRACT_VERSION
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    decision: RouteDecision
    assessments: tuple[CriterionAssessment, ...] = Field(
        min_length=len(SupportDimension),
        max_length=M0107_MAX_CRITERIA,
    )
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def envelope_is_coherent_and_digest_bound(self) -> SupportRoutingResult:
        identifiers = [item.criterion_id for item in self.assessments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("criterion assessments must be unique")
        if {item.dimension for item in self.assessments} != set(SupportDimension):
            raise ValueError("support result must assess every routing dimension")
        expected_decision = (
            RouteDecision.ABSTAINED
            if any(item.blocks_route for item in self.assessments)
            else RouteDecision.SUPPORTED
        )
        if self.decision is not expected_decision:
            raise ValueError("support routing decision contradicts its assessments")
        _validate_result_envelope(self)
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("support routing result digest does not match its content")
        return self


def _validate_observed_value(criterion: SupportCriterion, item: SupportEvidence) -> None:
    if item.state is not EvidenceState.OBSERVED:
        return
    if criterion.kind is CriterionKind.TERM_IN_SET and (
        not isinstance(item.value, str) or item.unit is not None
    ):
        raise ValueError("term support evidence must be text and unitless")
    if criterion.kind is CriterionKind.NUMERIC_RANGE and (
        not isinstance(item.value, float)
        or isinstance(item.value, bool)
        or item.unit != criterion.unit
    ):
        raise ValueError("numeric support evidence must match its criterion unit")
    if criterion.kind is CriterionKind.BOOLEAN_EQUALS and (
        not isinstance(item.value, bool) or item.unit is not None
    ):
        raise ValueError("boolean support evidence must be boolean and unitless")
    if criterion.kind is CriterionKind.REQUIRED_PRESENT and item.unit is not None:
        raise ValueError("presence support evidence must be unitless")


def _validate_result_envelope(result: SupportRoutingResult) -> None:
    expected_support = {
        RouteDecision.SUPPORTED: (SupportStatus.SUPPORTED, "support_domain_supported"),
        RouteDecision.ABSTAINED: (SupportStatus.REVIEW_REQUIRED, "support_domain_abstained"),
    }[result.decision]
    if (result.support.status, result.support.reason_code) != expected_support:
        raise ValueError("support decision contradicts routing outcome")
    if result.human_review_required is (result.decision is RouteDecision.SUPPORTED):
        raise ValueError("support routing review flag contradicts its decision")
    suffix = result.request_digest.removeprefix("sha256:")
    if result.routing_id != f"routing.m0107.{suffix}":
        raise ValueError("support routing identifier does not bind its request digest")
    if result.provenance.activity_id != f"activity.m0107.{suffix}":
        raise ValueError("support routing provenance does not bind its request digest")
    if result.provenance.module_id != M0107_MODULE_ID:
        raise ValueError("support routing provenance belongs to the wrong module")
    if result.provenance.module_version != result.result_version:
        raise ValueError("support routing provenance version contradicts the result")
    if result.provenance.generated_at != result.completed_at:
        raise ValueError("support routing provenance timestamp contradicts the result")
    if result.provenance.configuration_digest != result.configuration_digest:
        raise ValueError("support routing provenance contradicts the configuration")
    required = {
        result.request_digest,
        result.profile_digest,
        result.policy_digest,
        result.configuration_digest,
    }
    if not required.issubset(result.provenance.input_digests):
        raise ValueError("support routing provenance input digests are incomplete")
    if len(result.evidence) != len(set(result.evidence)):
        raise ValueError("support routing evidence references must be unique")
    if {item.code for item in result.limitations} != {
        M0107_SUPPORT_LIMITATION_CODE,
        M0107_AUTHORITY_LIMITATION_CODE,
    }:
        raise ValueError("support routing requires both module limitations")
    _validate_authorized_provenance(result.provenance, result.configuration_digest)


def _validate_authorized_provenance(
    provenance: ProvenanceRecord,
    configuration_hash: Sha256Digest,
) -> None:
    states = {item.role: item.state for item in provenance.control_decisions}
    expected_states = {
        ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
        ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.CONSENT: ConsentState.GRANTED.value,
        ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
    }
    if states != expected_states or provenance.consent_state is not ConsentState.GRANTED:
        raise ValueError("support routing provenance requires accepted authorization states")
    approved_configuration = next(
        item
        for item in provenance.control_decisions
        if item.role is ControlRole.APPROVED_CONFIGURATION
    )
    if approved_configuration.evidence_digest != configuration_hash:
        raise ValueError("approved configuration provenance must bind the routing configuration")
    consent = next(
        item for item in provenance.control_decisions if item.role is ControlRole.CONSENT
    )
    if (
        consent.decision_id != provenance.consent_decision_id
        or consent.policy_version != provenance.consent_policy_version
        or consent.evidence_digest != provenance.consent_evidence_digest
    ):
        raise ValueError("support routing consent provenance is internally inconsistent")


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize support routing")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before support routing")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("every upstream control must accept support routing")


__all__ = [
    "M0107_CONTRACT_VERSION",
    "M0107_MODULE_ID",
    "CriterionAssessment",
    "CriterionDecision",
    "CriterionKind",
    "EvidenceState",
    "RouteDecision",
    "RouteSupportRequest",
    "SupportCriterion",
    "SupportDimension",
    "SupportEvidence",
    "SupportRoutingPolicy",
    "SupportRoutingProfile",
    "SupportRoutingResult",
]
