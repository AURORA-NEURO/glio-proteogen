"""Version 1 contracts for GLIO-PROTEOGEN-M01-01."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m01_01.canonical import protocol_digest
from glio_proteogen.contracts.m01_01.ucum import (
    UCUM_SYSTEM_VERSION,
    SupportedUcumCode,
    unit_dimension,
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

JsonPointer = Annotated[
    str,
    StringConstraints(pattern=r"^(?:/(?:[^~/]|~0|~1)*)+$", max_length=512),
]
VocabularyCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"),
]


def _non_blank_scalar(value: str) -> str:
    if not value.strip():
        raise ValueError("scalar text cannot be empty or whitespace-only")
    return value


UnitCode = SupportedUcumCode
ScalarText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=65_536),
    AfterValidator(_non_blank_scalar),
]
type ScalarValue = ScalarText | int | float | bool
M0101_MAX_DECLARED_LIMITATIONS: Final = 998
M0101_SCOPE_LIMITATION_CODE: Final = "metadata_conformance_only"
M0101_UNVERIFIED_CONTROLS_LIMITATION_CODE: Final = "external_controls_unverified"
M0101_RESERVED_LIMITATION_CODES: Final = frozenset(
    {M0101_SCOPE_LIMITATION_CODE, M0101_UNVERIFIED_CONTROLS_LIMITATION_CODE}
)


class MissingnessState(StrEnum):
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    REDACTED = "redacted"
    UNSUPPORTED = "unsupported"


class ValueKind(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    IDENTIFIER = "identifier"
    TERM = "term"


class VocabularyTerm(FrozenModel):
    code: VocabularyCode
    label: NonEmptyStr
    definition: NonEmptyStr


class VocabularyDefinition(FrozenModel):
    vocabulary_id: Identifier
    version: SemanticVersion
    terms: tuple[VocabularyTerm, ...] = Field(min_length=1, max_length=10_000)

    @field_validator("terms")
    @classmethod
    def term_codes_are_unique(cls, terms: tuple[VocabularyTerm, ...]) -> tuple[VocabularyTerm, ...]:
        codes = [term.code for term in terms]
        if len(codes) != len(set(codes)):
            raise ValueError("vocabulary term codes must be unique")
        return terms


class UnitDefinition(FrozenModel):
    code: UnitCode
    system: Literal["UCUM"]
    system_version: Literal["2.2"]
    dimension: Identifier
    definition: NonEmptyStr

    @model_validator(mode="after")
    def dimension_matches_pinned_ucum(self) -> UnitDefinition:
        if self.system_version != UCUM_SYSTEM_VERSION:
            raise ValueError("unit system version is not supported")
        if self.dimension != unit_dimension(self.code):
            raise ValueError("declared unit dimension does not match pinned UCUM semantics")
        return self


class Cardinality(FrozenModel):
    minimum: int = Field(ge=0, le=1_000_000)
    maximum: int | None = Field(default=None, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def ordered_bounds(self) -> Cardinality:
        if self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cardinality cannot exceed maximum")
        return self


class NumericBounds(FrozenModel):
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def ordered_bounds(self) -> NumericBounds:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum value cannot exceed maximum value")
        return self


class FieldSpecification(FrozenModel):
    path: JsonPointer
    title: NonEmptyStr
    description: NonEmptyStr
    value_kind: ValueKind
    required: bool
    cardinality: Cardinality
    identity_key: bool = False
    unit_dimension: Identifier | None = None
    allowed_units: tuple[UnitCode, ...] = Field(default=(), max_length=256)
    reference_unit: UnitCode | None = None
    vocabulary_id: Identifier | None = None
    allowed_missingness: tuple[MissingnessState, ...] = Field(default=(), max_length=5)
    pattern: str | None = Field(default=None, max_length=512)
    numeric_bounds: NumericBounds | None = None

    @model_validator(mode="after")
    def constraints_match_kind(self) -> FieldSpecification:
        _validate_field_collections(self)
        _validate_field_units(self)
        _validate_field_value_constraints(self)
        _validate_identity_field(self)
        return self


def _validate_field_collections(field: FieldSpecification) -> None:
    if len(field.allowed_units) != len(set(field.allowed_units)):
        raise ValueError("allowed unit codes must be unique")
    if len(field.allowed_missingness) != len(set(field.allowed_missingness)):
        raise ValueError("allowed missingness states must be unique")


def _validate_field_units(field: FieldSpecification) -> None:
    if field.allowed_units and field.unit_dimension is None:
        raise ValueError("allowed units require a declared dimension")
    if field.unit_dimension is not None and not field.allowed_units:
        raise ValueError("unit dimension requires at least one allowed unit")
    if field.allowed_units and field.reference_unit is None:
        raise ValueError("unitful fields require an explicit reference unit")
    if not field.allowed_units and field.reference_unit is not None:
        raise ValueError("unitless fields cannot declare a reference unit")
    if field.reference_unit is not None and field.reference_unit not in field.allowed_units:
        raise ValueError("reference unit must belong to the allowed unit set")
    if field.allowed_units and field.value_kind not in {ValueKind.INTEGER, ValueKind.NUMBER}:
        raise ValueError("UCUM units may only constrain integer or number fields")


def _validate_field_value_constraints(field: FieldSpecification) -> None:
    if field.vocabulary_id is not None and field.value_kind is not ValueKind.TERM:
        raise ValueError("controlled vocabulary is only valid for term fields")
    if field.value_kind is ValueKind.TERM and field.vocabulary_id is None:
        raise ValueError("term fields require a registered controlled vocabulary")
    if field.pattern is not None and field.value_kind not in {
        ValueKind.TEXT,
        ValueKind.IDENTIFIER,
        ValueKind.TIMESTAMP,
    }:
        raise ValueError("pattern is only valid for text-like fields")
    if field.numeric_bounds is not None and field.value_kind not in {
        ValueKind.INTEGER,
        ValueKind.NUMBER,
    }:
        raise ValueError("numeric bounds are only valid for numeric fields")
    if field.required and field.cardinality.minimum == 0:
        raise ValueError("required fields need minimum cardinality of at least one")


def _validate_identity_field(field: FieldSpecification) -> None:
    if field.identity_key and (
        not field.required
        or field.value_kind is not ValueKind.IDENTIFIER
        or field.cardinality.minimum != 1
        or field.cardinality.maximum != 1
        or field.allowed_missingness
    ):
        raise ValueError(
            "identity keys must be required, identifier-valued, exactly singular, "
            "and never unresolved"
        )


class PredicateOperator(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    EQUALS = "equals"
    IN = "in"


class CompatibilityPredicate(FrozenModel):
    path: JsonPointer
    operator: PredicateOperator
    values: tuple[ScalarValue, ...] = Field(default=(), max_length=1_000)
    unit: UnitCode | None = None

    @model_validator(mode="after")
    def values_match_operator(self) -> CompatibilityPredicate:
        expects_values = self.operator in {PredicateOperator.EQUALS, PredicateOperator.IN}
        if expects_values and not self.values:
            raise ValueError("equals/in predicates require values")
        if not expects_values and self.values:
            raise ValueError("present/absent predicates cannot carry values")
        if not expects_values and self.unit is not None:
            raise ValueError("present/absent predicates cannot carry a unit")
        if self.operator is PredicateOperator.EQUALS and len(self.values) != 1:
            raise ValueError("equals predicate requires exactly one value")
        return self


class IssueAction(StrEnum):
    REJECT = "reject"
    QUARANTINE = "quarantine"
    HUMAN_REVIEW = "human_review"


class CompatibilityRule(FrozenModel):
    rule_id: Identifier
    description: NonEmptyStr
    when_all: tuple[CompatibilityPredicate, ...] = Field(min_length=1, max_length=64)
    require_all: tuple[CompatibilityPredicate, ...] = Field(min_length=1, max_length=64)
    on_failure: IssueAction


def _scalar_matches_field_kind(value: ScalarValue, kind: ValueKind) -> bool:
    if kind is ValueKind.NUMBER:
        return type(value) in {int, float}
    if kind is ValueKind.INTEGER:
        return type(value) is int
    if kind is ValueKind.BOOLEAN:
        return type(value) is bool
    return type(value) is str


def _validate_predicate_for_field(
    predicate: CompatibilityPredicate,
    field: FieldSpecification,
    vocabulary_terms: dict[str, frozenset[str]],
) -> None:
    if any(not _scalar_matches_field_kind(value, field.value_kind) for value in predicate.values):
        raise ValueError("compatibility predicate value kind does not match its field")
    carries_values = predicate.operator in {PredicateOperator.EQUALS, PredicateOperator.IN}
    if field.allowed_units and carries_values:
        if predicate.unit is None:
            raise ValueError("unitful value predicates require an explicit UCUM unit")
        if predicate.unit not in field.allowed_units:
            raise ValueError("predicate unit is not allowed for its field")
    elif predicate.unit is not None:
        raise ValueError("unitless or presence predicates cannot carry a UCUM unit")
    if field.value_kind is ValueKind.TERM and carries_values:
        vocabulary_id = field.vocabulary_id
        if vocabulary_id is None or any(
            value not in vocabulary_terms[vocabulary_id] for value in predicate.values
        ):
            raise ValueError("term predicate references an unknown controlled term")


class ProtocolSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    title: NonEmptyStr
    description: NonEmptyStr
    assay_versions: tuple[SemanticVersion, ...] = Field(min_length=1, max_length=256)
    specimen_versions: tuple[SemanticVersion, ...] = Field(min_length=1, max_length=256)
    fields: tuple[FieldSpecification, ...] = Field(min_length=1, max_length=10_000)
    vocabularies: tuple[VocabularyDefinition, ...] = Field(default=(), max_length=1_000)
    units: tuple[UnitDefinition, ...] = Field(default=(), max_length=10_000)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(default=(), max_length=10_000)
    # One output slot is reserved for the non-removable M01-01 interpretation ceiling.
    limitations: tuple[Limitation, ...] = Field(
        min_length=1,
        max_length=M0101_MAX_DECLARED_LIMITATIONS,
    )

    @field_validator("limitations")
    @classmethod
    def limitation_codes_are_unique(
        cls,
        limitations: tuple[Limitation, ...],
    ) -> tuple[Limitation, ...]:
        codes = [limitation.code for limitation in limitations]
        if len(codes) != len(set(codes)):
            raise ValueError("limitation codes must be unique")
        if M0101_RESERVED_LIMITATION_CODES.intersection(codes):
            raise ValueError("M01-01 module limitation codes are reserved")
        return limitations

    @model_validator(mode="after")
    def references_are_closed_and_unique(self) -> ProtocolSchema:
        if len(self.assay_versions) != len(set(self.assay_versions)):
            raise ValueError("assay versions must be unique")
        if len(self.specimen_versions) != len(set(self.specimen_versions)):
            raise ValueError("specimen versions must be unique")
        paths = [field.path for field in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("field paths must be unique")
        vocabulary_ids = [vocabulary.vocabulary_id for vocabulary in self.vocabularies]
        if len(vocabulary_ids) != len(set(vocabulary_ids)):
            raise ValueError("vocabulary IDs must be unique")
        unit_codes = [unit.code for unit in self.units]
        if len(unit_codes) != len(set(unit_codes)):
            raise ValueError("unit codes must be unique")
        rule_ids = [rule.rule_id for rule in self.compatibility_rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("compatibility rule IDs must be unique")
        known_vocabularies = set(vocabulary_ids)
        known_units = set(unit_codes)
        for field in self.fields:
            if field.vocabulary_id is not None and field.vocabulary_id not in known_vocabularies:
                raise ValueError(f"field {field.path} references unknown vocabulary")
            if not set(field.allowed_units).issubset(known_units):
                raise ValueError(f"field {field.path} references unknown unit")
        known_paths = set(paths)
        fields_by_path = {field.path: field for field in self.fields}
        vocabulary_terms = {
            vocabulary.vocabulary_id: frozenset(term.code for term in vocabulary.terms)
            for vocabulary in self.vocabularies
        }
        for rule in self.compatibility_rules:
            for predicate in (*rule.when_all, *rule.require_all):
                if predicate.path not in known_paths:
                    raise ValueError(f"rule {rule.rule_id} references unknown field")
                _validate_predicate_for_field(
                    predicate,
                    fields_by_path[predicate.path],
                    vocabulary_terms,
                )
        return self


class ObservedValue(FrozenModel):
    state: Literal["observed"] = "observed"
    value: ScalarValue
    unit: UnitCode | None = None


class UnresolvedValue(FrozenModel):
    state: Literal["missing", "unknown", "not_applicable", "redacted", "unsupported"]
    reason_code: Identifier
    explanation: NonEmptyStr
    evidence: ArtifactReference | None = None


type MetadataValue = Annotated[
    ObservedValue | UnresolvedValue,
    Field(discriminator="state"),
]


class MetadataEntry(FrozenModel):
    path: JsonPointer
    values: tuple[MetadataValue, ...] = Field(min_length=1, max_length=10_000)


class MetadataDocument(FrozenModel):
    document_id: Identifier
    schema_id: Identifier
    schema_version: SemanticVersion
    assay_version: SemanticVersion
    specimen_version: SemanticVersion
    entries: tuple[MetadataEntry, ...] = Field(max_length=10_000)

    @field_validator("entries")
    @classmethod
    def entry_paths_are_unique(
        cls, entries: tuple[MetadataEntry, ...]
    ) -> tuple[MetadataEntry, ...]:
        paths = [entry.path for entry in entries]
        if len(paths) != len(set(paths)):
            raise ValueError("metadata entry paths must be unique")
        return entries


class ProtocolReference(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    digest: Sha256Digest


class ProtocolLookup(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion


class RegisterProtocolRequest(FrozenModel):
    operation: Literal["register"] = "register"
    context: ExecutionContext
    protocol_schema: ProtocolSchema


class EvaluateMetadataRequest(FrozenModel):
    operation: Literal["evaluate"] = "evaluate"
    context: ExecutionContext
    protocol: ProtocolReference
    document: MetadataDocument


type M0101Request = Annotated[
    RegisterProtocolRequest | EvaluateMetadataRequest,
    Field(discriminator="operation"),
]


def _validate_output_limitations(
    limitations: tuple[Limitation, ...],
) -> tuple[Limitation, ...]:
    codes = [limitation.code for limitation in limitations]
    if len(codes) != len(set(codes)):
        raise ValueError("output limitation codes must be unique")
    if not M0101_RESERVED_LIMITATION_CODES.issubset(codes):
        raise ValueError("output is missing a mandatory M01-01 limitation")
    return limitations


class ProtocolSchemaReceipt(FrozenModel):
    output_type: Literal["protocol_schema"] = "protocol_schema"
    receipt_version: SemanticVersion
    protocol: ProtocolReference
    protocol_schema: ProtocolSchema
    event_digest: Sha256Digest
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=1_000)

    @field_validator("limitations")
    @classmethod
    def mandatory_limitations_are_unique(
        cls,
        limitations: tuple[Limitation, ...],
    ) -> tuple[Limitation, ...]:
        return _validate_output_limitations(limitations)

    @model_validator(mode="after")
    def protocol_reference_matches_embedded_schema(self) -> ProtocolSchemaReceipt:
        if (
            self.protocol.schema_id != self.protocol_schema.schema_id
            or self.protocol.version != self.protocol_schema.version
            or self.protocol.digest != protocol_digest(self.protocol_schema)
        ):
            raise ValueError("protocol reference does not match its embedded schema")
        if (
            self.support.status is not SupportStatus.LIMITED
            or self.support.reason_code != "protocol_schema_structurally_valid"
        ):
            raise ValueError("protocol receipt support must disclose unverified controls")
        return self


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConformanceIssue(FrozenModel):
    code: Identifier
    path: JsonPointer
    severity: IssueSeverity
    action: IssueAction
    message: NonEmptyStr
    evidence: tuple[ArtifactReference, ...] = Field(default=(), max_length=64)


class ConformanceDecision(StrEnum):
    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"


class ConformanceProfile(FrozenModel):
    output_type: Literal["conformance_profile"] = "conformance_profile"
    profile_version: SemanticVersion
    protocol: ProtocolReference
    document_digest: Sha256Digest
    decision: ConformanceDecision
    support: SupportDecision
    issues: tuple[ConformanceIssue, ...] = Field(max_length=256)
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=1_000)
    human_review_required: bool
    event_digest: Sha256Digest
    evaluated_at: AwareDatetime

    @field_validator("limitations")
    @classmethod
    def mandatory_limitations_are_unique(
        cls,
        limitations: tuple[Limitation, ...],
    ) -> tuple[Limitation, ...]:
        return _validate_output_limitations(limitations)

    @model_validator(mode="after")
    def decision_envelope_matches_issues(self) -> ConformanceProfile:
        actions = {issue.action for issue in self.issues}
        if IssueAction.QUARANTINE in actions:
            expected_decision = ConformanceDecision.QUARANTINED
        elif IssueAction.REJECT in actions:
            expected_decision = ConformanceDecision.NONCONFORMANT
        elif IssueAction.HUMAN_REVIEW in actions:
            expected_decision = ConformanceDecision.REVIEW_REQUIRED
        else:
            expected_decision = ConformanceDecision.CONFORMANT
        if self.decision is not expected_decision:
            raise ValueError("conformance decision contradicts issue actions")
        expected_review = bool(actions & {IssueAction.QUARANTINE, IssueAction.HUMAN_REVIEW}) or any(
            issue.severity is IssueSeverity.CRITICAL for issue in self.issues
        )
        if self.human_review_required is not expected_review:
            raise ValueError("human-review flag contradicts issues")
        expected_support = {
            ConformanceDecision.CONFORMANT: (
                SupportStatus.LIMITED,
                "metadata_structurally_conformant",
            ),
            ConformanceDecision.NONCONFORMANT: (
                SupportStatus.UNSUPPORTED,
                "metadata_nonconformant",
            ),
            ConformanceDecision.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                "metadata_quarantined",
            ),
            ConformanceDecision.REVIEW_REQUIRED: (
                SupportStatus.REVIEW_REQUIRED,
                "metadata_review_required",
            ),
        }[self.decision]
        if (self.support.status, self.support.reason_code) != expected_support:
            raise ValueError("support decision contradicts conformance decision")
        return self


type M0101Output = Annotated[
    ProtocolSchemaReceipt | ConformanceProfile,
    Field(discriminator="output_type"),
]
