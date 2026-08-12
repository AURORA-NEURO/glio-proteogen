"""Strict public contracts for M02-01 protocol and metadata conformance."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m02_01.canonical import (
    configuration_digest,
    result_payload_digest,
    schema_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlRole,
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
    UpstreamDecisionState,
)

M0201_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-01"
M0201_CONTRACT_VERSION: Final = "1.0.0"
M0201_MAX_FIELDS: Final = 1024
M0201_MAX_OBSERVATIONS: Final = 4096
M0201_CONFORMANCE_LIMITATION_CODE: Final = "protocol_conformance_only"
M0201_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_CONFLICTING_MIN_VALUES: Final = 2

type ScalarValue = str | int | float | bool


class ValueKind(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TERM = "term"


class ObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    CONFLICTING = "conflicting"


class RuleAction(StrEnum):
    QUARANTINE = "quarantine"
    REVIEW = "review"


class EvaluationState(StrEnum):
    PASS = "pass"  # noqa: S105 - conformance outcome, not a credential.
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class ConformanceStatus(StrEnum):
    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"
    INDETERMINATE = "indeterminate"


class ConformanceDisposition(StrEnum):
    CONFORMANT = "conformant"
    QUARANTINED = "quarantined"


class VocabularyDefinition(FrozenModel):
    vocabulary_id: Identifier
    version: SemanticVersion
    terms: tuple[Identifier, ...] = Field(min_length=1, max_length=4096)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def terms_are_unique(self) -> VocabularyDefinition:
        if len(self.terms) != len(set(self.terms)):
            raise ValueError("vocabulary terms must be unique")
        return self


class UnitDefinition(FrozenModel):
    unit_id: Identifier
    symbol: NonEmptyStr
    quantity_kind: Identifier
    evidence: ArtifactReference


class ProtocolFieldDefinition(FrozenModel):
    field_id: Identifier
    label: NonEmptyStr
    value_kind: ValueKind
    required: bool
    min_items: int = Field(ge=0, le=256)
    max_items: int = Field(gt=0, le=256)
    vocabulary_id: Identifier | None = None
    unit_id: Identifier | None = None
    allow_not_applicable: bool = False

    @model_validator(mode="after")
    def shape_matches_value_kind(self) -> ProtocolFieldDefinition:
        if self.min_items > self.max_items or (self.required and self.min_items == 0):
            raise ValueError("field cardinality is inconsistent")
        if self.required and self.allow_not_applicable:
            raise ValueError("required fields cannot allow not-applicable observations")
        if (self.value_kind is ValueKind.TERM) != (self.vocabulary_id is not None):
            raise ValueError("only controlled-term fields require a vocabulary")
        if (
            self.value_kind not in {ValueKind.INTEGER, ValueKind.NUMBER}
            and self.unit_id is not None
        ):
            raise ValueError("only numeric fields may declare a unit")
        return self


class RuleBase(FrozenModel):
    rule_id: Identifier
    field_id: Identifier
    action: RuleAction
    reason_code: Identifier
    remediation_code: Identifier


class PresenceRule(RuleBase):
    kind: Literal["required_present"] = "required_present"


class TermInSetRule(RuleBase):
    kind: Literal["term_in_set"] = "term_in_set"
    allowed_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def allowed_terms_are_unique(self) -> TermInSetRule:
        if len(self.allowed_terms) != len(set(self.allowed_terms)):
            raise ValueError("term rule values must be unique")
        return self


class NumericRangeRule(RuleBase):
    kind: Literal["numeric_range"] = "numeric_range"
    minimum: float | None = None
    maximum: float | None = None
    unit_id: Identifier

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> NumericRangeRule:
        if self.minimum is None and self.maximum is None:
            raise ValueError("numeric range requires at least one bound")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("numeric range bounds must be ordered")
        return self


class BooleanEqualsRule(RuleBase):
    kind: Literal["boolean_equals"] = "boolean_equals"
    expected: bool


class ConditionalStateRule(RuleBase):
    kind: Literal["conditional_state"] = "conditional_state"
    trigger_field_id: Identifier
    trigger_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    required_state: ObservationState

    @model_validator(mode="after")
    def trigger_terms_are_unique(self) -> ConditionalStateRule:
        if len(self.trigger_terms) != len(set(self.trigger_terms)):
            raise ValueError("conditional trigger terms must be unique")
        return self


class AllowedTermPair(FrozenModel):
    left: Identifier
    right: Identifier


class AllowedTermPairRule(RuleBase):
    kind: Literal["allowed_term_pair"] = "allowed_term_pair"
    other_field_id: Identifier
    allowed_pairs: tuple[AllowedTermPair, ...] = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def pairs_are_unique(self) -> AllowedTermPairRule:
        if len(self.allowed_pairs) != len(set(self.allowed_pairs)):
            raise ValueError("allowed term pairs must be unique")
        return self


CompatibilityRule = Annotated[
    PresenceRule
    | TermInSetRule
    | NumericRangeRule
    | BooleanEqualsRule
    | ConditionalStateRule
    | AllowedTermPairRule,
    Field(discriminator="kind"),
]


class ProtocolSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    assay_type: Identifier
    specimen_type: Identifier
    fields: tuple[ProtocolFieldDefinition, ...] = Field(
        min_length=1,
        max_length=M0201_MAX_FIELDS,
    )
    vocabularies: tuple[VocabularyDefinition, ...] = Field(default=(), max_length=256)
    units: tuple[UnitDefinition, ...] = Field(default=(), max_length=256)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(default=(), max_length=2048)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def identifiers_and_references_close(self) -> ProtocolSchema:  # noqa: PLR0912
        collections = (
            tuple(item.field_id for item in self.fields),
            tuple(item.vocabulary_id for item in self.vocabularies),
            tuple(item.unit_id for item in self.units),
            tuple(item.rule_id for item in self.compatibility_rules),
        )
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("protocol schema identifiers must be unique")
        fields = {item.field_id: item for item in self.fields}
        vocabularies = {item.vocabulary_id: item for item in self.vocabularies}
        units = {item.unit_id: item for item in self.units}
        for field in self.fields:
            if field.vocabulary_id is not None and field.vocabulary_id not in vocabularies:
                raise ValueError("field vocabulary reference is unresolved")
            if field.unit_id is not None and field.unit_id not in units:
                raise ValueError("field unit reference is unresolved")
        for rule in self.compatibility_rules:
            target_field = fields.get(rule.field_id)
            if target_field is None:
                raise ValueError("compatibility rule field reference is unresolved")
            if isinstance(rule, TermInSetRule):
                if (
                    target_field.value_kind is not ValueKind.TERM
                    or target_field.vocabulary_id is None
                ):
                    raise ValueError("term rule requires a controlled-term field")
                if not set(rule.allowed_terms).issubset(
                    vocabularies[target_field.vocabulary_id].terms
                ):
                    raise ValueError("term rule values must belong to the field vocabulary")
            if isinstance(rule, NumericRangeRule) and (
                target_field.value_kind not in {ValueKind.INTEGER, ValueKind.NUMBER}
                or target_field.unit_id != rule.unit_id
            ):
                raise ValueError("numeric rule must match its field unit")
            if (
                isinstance(rule, BooleanEqualsRule)
                and target_field.value_kind is not ValueKind.BOOLEAN
            ):
                raise ValueError("boolean rule requires a boolean field")
            if isinstance(rule, ConditionalStateRule):
                trigger = fields.get(rule.trigger_field_id)
                if (
                    trigger is None
                    or trigger.value_kind is not ValueKind.TERM
                    or trigger.vocabulary_id is None
                ):
                    raise ValueError("conditional rule requires a controlled-term trigger")
                if not set(rule.trigger_terms).issubset(
                    vocabularies[trigger.vocabulary_id].terms
                ):
                    raise ValueError("conditional trigger terms must belong to its vocabulary")
            if isinstance(rule, AllowedTermPairRule):
                other = fields.get(rule.other_field_id)
                if (
                    target_field.value_kind is not ValueKind.TERM
                    or target_field.vocabulary_id is None
                    or other is None
                    or other.value_kind is not ValueKind.TERM
                    or other.vocabulary_id is None
                ):
                    raise ValueError("term-pair rule requires two controlled-term fields")
                left_terms = set(vocabularies[target_field.vocabulary_id].terms)
                right_terms = set(vocabularies[other.vocabulary_id].terms)
                if any(
                    pair.left not in left_terms or pair.right not in right_terms
                    for pair in rule.allowed_pairs
                ):
                    raise ValueError("allowed term pairs must belong to their vocabularies")
        return self


class ConformanceProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    schema_id: Identifier
    schema_version: SemanticVersion
    schema_digest: Sha256Digest
    max_observations: int = Field(default=M0201_MAX_OBSERVATIONS, gt=0, le=M0201_MAX_OBSERVATIONS)
    evidence: ArtifactReference


class FieldObservation(FrozenModel):
    observation_id: Identifier
    field_id: Identifier
    state: ObservationState
    values: tuple[ScalarValue, ...] = Field(default=(), max_length=256)
    unit_id: Identifier | None = None
    evidence: tuple[ArtifactReference, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def values_match_state(self) -> FieldObservation:
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("observation evidence references must be unique")
        if self.state is ObservationState.OBSERVED and not self.values:
            raise ValueError("observed fields require values")
        if (
            self.state is ObservationState.CONFLICTING
            and len(self.values) < _CONFLICTING_MIN_VALUES
        ):
            raise ValueError("conflicting fields require at least two values")
        if self.state not in {ObservationState.OBSERVED, ObservationState.CONFLICTING} and (
            self.values or self.unit_id is not None
        ):
            raise ValueError("unresolved fields cannot carry values or units")
        return self


class EvaluateConformanceRequest(FrozenModel):
    operation: Literal["evaluate_conformance"] = "evaluate_conformance"
    contract_version: Literal["1.0.0"] = M0201_CONTRACT_VERSION
    context: ExecutionContext
    protocol_schema: ProtocolSchema
    conformance_profile: ConformanceProfile
    observations: tuple[FieldObservation, ...] = Field(
        min_length=1,
        max_length=M0201_MAX_OBSERVATIONS,
    )
    supersedes_evaluation_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_pinned_closed_and_authorized(self) -> EvaluateConformanceRequest:
        _require_authorized_context(self.context)
        profile = self.conformance_profile
        schema = self.protocol_schema
        if (
            profile.schema_id != schema.schema_id
            or profile.schema_version != schema.version
            or profile.schema_digest != schema_digest(schema)
        ):
            raise ValueError("conformance profile does not pin the supplied protocol schema")
        if len(self.observations) > profile.max_observations:
            raise ValueError("observation count exceeds the conformance profile")
        identifiers = tuple(item.observation_id for item in self.observations)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("observation identifiers must be unique")
        observed_fields = tuple(item.field_id for item in self.observations)
        if len(observed_fields) != len(set(observed_fields)):
            raise ValueError("each protocol field may have only one observation")
        fields = {item.field_id for item in schema.fields}
        if any(item.field_id not in fields for item in self.observations):
            raise ValueError("observation field reference is unresolved")
        expected = configuration_digest(schema, profile)
        if self.context.references.approved_configuration.evidence.digest != expected:
            raise ValueError("approved configuration does not bind schema and profile")
        return self


class FieldEvaluation(FrozenModel):
    field_id: Identifier
    state: EvaluationState
    reason_code: Identifier
    observation_ids: tuple[Identifier, ...] = Field(default=(), max_length=256)


class RuleEvaluation(FrozenModel):
    rule_id: Identifier
    state: EvaluationState
    action: RuleAction
    reason_code: Identifier
    remediation_code: Identifier | None = None


class ConformanceEvaluation(FrozenModel):
    output_type: Literal["conformance_evaluation"] = "conformance_evaluation"
    evaluation_id: Identifier
    result_version: Literal["1.0.0"] = M0201_CONTRACT_VERSION
    request_digest: Sha256Digest
    schema_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    evaluation_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    status: ConformanceStatus
    disposition: ConformanceDisposition
    field_evaluations: tuple[FieldEvaluation, ...] = Field(
        min_length=1,
        max_length=M0201_MAX_FIELDS,
    )
    rule_evaluations: tuple[RuleEvaluation, ...] = Field(default=(), max_length=2048)
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=4096)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_evaluation_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def digest_is_bound(self) -> ConformanceEvaluation:
        field_ids = tuple(item.field_id for item in self.field_evaluations)
        rule_ids = tuple(item.rule_id for item in self.rule_evaluations)
        if len(field_ids) != len(set(field_ids)) or len(rule_ids) != len(set(rule_ids)):
            raise ValueError("conformance evaluation identifiers must be unique")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("conformance evaluation evidence must be unique")
        states = tuple(item.state for item in self.field_evaluations) + tuple(
            item.state for item in self.rule_evaluations
        )
        expected_status = (
            ConformanceStatus.NONCONFORMANT
            if EvaluationState.FAIL in states
            else (
                ConformanceStatus.INDETERMINATE
                if EvaluationState.NOT_EVALUABLE in states
                else ConformanceStatus.CONFORMANT
            )
        )
        if self.status is not expected_status:
            raise ValueError("conformance status contradicts its evaluations")
        expected_disposition = (
            ConformanceDisposition.CONFORMANT
            if self.status is ConformanceStatus.CONFORMANT
            else ConformanceDisposition.QUARANTINED
        )
        if self.disposition is not expected_disposition:
            raise ValueError("conformance disposition contradicts its status")
        expected_support = {
            ConformanceDisposition.CONFORMANT: (
                SupportStatus.SUPPORTED,
                "metadata_conformant",
                False,
            ),
            ConformanceDisposition.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                "metadata_quarantined",
                True,
            ),
        }[self.disposition]
        if (
            self.support.status,
            self.support.reason_code,
            self.human_review_required,
        ) != expected_support:
            raise ValueError("conformance support envelope contradicts its disposition")
        suffix = self.request_digest.removeprefix("sha256:")
        provenance = self.provenance
        if (
            self.evaluation_id != f"evaluation.m0201.{suffix}"
            or provenance.activity_id != f"activity.m0201.{suffix}"
            or provenance.module_id != M0201_MODULE_ID
            or provenance.module_version != self.result_version
            or provenance.generated_at != self.completed_at
            or provenance.configuration_digest != self.configuration_digest
            or not {
                self.request_digest,
                self.schema_digest,
                self.profile_digest,
                self.configuration_digest,
            }.issubset(provenance.input_digests)
        ):
            raise ValueError("conformance evaluation provenance envelope is inconsistent")
        states_by_role = {
            item.role: item.state for item in provenance.control_decisions
        }
        expected_controls = {
            ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.IDENTITY_LINEAGE: "resolved",
            ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.CONSENT: ConsentState.GRANTED.value,
            ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
        }
        if (
            provenance.consent_state is not ConsentState.GRANTED
            or states_by_role != expected_controls
        ):
            raise ValueError("conformance provenance requires accepted controls")
        if {item.code for item in self.limitations} != {
            M0201_CONFORMANCE_LIMITATION_CODE,
            M0201_AUTHORITY_LIMITATION_CODE,
        }:
            raise ValueError("conformance evaluation requires both limitation codes")
        expected = result_payload_digest(self)
        if self.evaluation_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "evaluation_digest", expected)
        elif self.evaluation_digest != expected:
            raise ValueError("conformance evaluation digest does not match its content")
        return self


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize conformance evaluation")
    if references.identity_lineage.state.value != "resolved":
        raise ValueError("identity lineage must be resolved before conformance evaluation")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state.value != "accepted" for reference in generic):
        raise ValueError("every upstream control must accept conformance evaluation")


__all__ = [
    "M0201_AUTHORITY_LIMITATION_CODE",
    "M0201_CONFORMANCE_LIMITATION_CODE",
    "M0201_CONTRACT_VERSION",
    "M0201_MODULE_ID",
    "AllowedTermPair",
    "AllowedTermPairRule",
    "BooleanEqualsRule",
    "CompatibilityRule",
    "ConditionalStateRule",
    "ConformanceDisposition",
    "ConformanceEvaluation",
    "ConformanceProfile",
    "ConformanceStatus",
    "EvaluateConformanceRequest",
    "EvaluationState",
    "FieldEvaluation",
    "FieldObservation",
    "NumericRangeRule",
    "ObservationState",
    "PresenceRule",
    "ProtocolFieldDefinition",
    "ProtocolSchema",
    "RuleAction",
    "RuleEvaluation",
    "TermInSetRule",
    "UnitDefinition",
    "ValueKind",
    "VocabularyDefinition",
]
