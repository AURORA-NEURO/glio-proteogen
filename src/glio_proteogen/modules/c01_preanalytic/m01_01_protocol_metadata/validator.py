"""Pure, deterministic conformance validation for M01-01 metadata.

This module deliberately has no clock, persistence, hashing, or provenance concerns.  It
accepts already-validated contracts, evaluates their semantic relationship, and returns a
small immutable report for the service layer to wrap in a public conformance profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from glio_proteogen.contracts.m01_01.canonical import identity_binding_digest
from glio_proteogen.contracts.m01_01.ucum import (
    convert_quantity,
    is_supported_ucum_code,
    unit_dimension,
)
from glio_proteogen.contracts.m01_01.v1 import (
    M0101_MAX_DECLARED_LIMITATIONS,
    M0101_RESERVED_LIMITATION_CODES,
    CompatibilityPredicate,
    ConformanceDecision,
    ConformanceIssue,
    FieldSpecification,
    IssueAction,
    IssueSeverity,
    MetadataDocument,
    MetadataEntry,
    MissingnessState,
    ObservedValue,
    PredicateOperator,
    ProtocolSchema,
    ScalarValue,
    UnitCode,
    UnitDefinition,
    UnresolvedValue,
    ValueKind,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ArtifactReference, ConsentState, Sha256Digest

if TYPE_CHECKING:
    from collections.abc import Mapping

_IDENTIFIER_PATTERN: Final = re.compile(r"^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$")
_VOCABULARY_CODE_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RFC3339_PATTERN: Final = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_MAX_PATTERN_INPUT_LENGTH: Final = 16_384
_MAX_PATTERN_REPEAT: Final = 4_096
_MAX_ISSUES: Final = 256
_MAX_MESSAGE_LENGTH: Final = 512
_CONSENT_PATH: Final = "/context/references/consent/state"
_ABSOLUTE_CONSENT_DENIAL_CODES: Final = frozenset({"consent.revoked", "consent.withheld"})


class _ValidatedScalarInvariantError(TypeError):
    """An internal call violated the already-validated scalar contract."""


class _UnitQuantityInvariantError(ValueError):
    """An internal call omitted a validated quantity unit."""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Internal, immutable outcome of one conformance evaluation."""

    decision: ConformanceDecision
    issues: tuple[ConformanceIssue, ...]
    human_review_required: bool


@dataclass(frozen=True, slots=True)
class _ConstraintContext:
    patterns: dict[str, re.Pattern[str]]
    vocabularies: dict[str, frozenset[str]]
    units_by_code: Mapping[UnitCode, UnitDefinition]
    collector: _IssueCollector


type _IssueKey = tuple[str, str, str, str, str, tuple[str, ...]]
type _ComparableScalar = str | bool | Decimal
type _TypedScalar = tuple[str, _ComparableScalar]


@dataclass(frozen=True, slots=True)
class _CompatibilityObservation:
    present: bool
    values: frozenset[_TypedScalar]
    indeterminate: bool


_ABSENT_COMPATIBILITY_OBSERVATION: Final = _CompatibilityObservation(
    present=False,
    values=frozenset(),
    indeterminate=False,
)


class _IssueCollector:
    """Bounded de-duplicating collector that also remembers omitted issue actions."""

    __slots__ = ("_actions", "_issues", "_truncated")

    def __init__(self) -> None:
        self._issues: dict[_IssueKey, ConformanceIssue] = {}
        self._actions: set[IssueAction] = set()
        self._truncated = False

    def add(  # noqa: PLR0913 - each diagnostic dimension is an explicit contract field.
        self,
        *,
        code: str,
        path: str,
        severity: IssueSeverity = IssueSeverity.ERROR,
        action: IssueAction = IssueAction.REJECT,
        message: str,
        evidence: tuple[ArtifactReference, ...] = (),
    ) -> None:
        self._actions.add(action)
        bounded_message = _bounded_message(message)
        evidence_keys = tuple(
            canonical_json_bytes(reference).decode("utf-8") for reference in evidence
        )
        key = (code, path, severity.value, action.value, bounded_message, evidence_keys)
        if key in self._issues:
            return
        if len(self._issues) >= _MAX_ISSUES - 1:
            self._truncated = True
            return
        self._issues[key] = ConformanceIssue(
            code=code,
            path=path,
            severity=severity,
            action=action,
            message=bounded_message,
            evidence=evidence,
        )

    def finish(self) -> ValidationReport:
        if self._truncated:
            self._actions.add(IssueAction.QUARANTINE)
            issue = ConformanceIssue(
                code="validation.issue_limit_reached",
                path="/entries",
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message="Additional conformance issues were omitted at the deterministic limit.",
            )
            key = _issue_sort_key(issue)
            self._issues[key] = issue
        issues = tuple(sorted(self._issues.values(), key=_issue_sort_key))
        decision = (
            ConformanceDecision.NONCONFORMANT
            if any(issue.code in _ABSOLUTE_CONSENT_DENIAL_CODES for issue in issues)
            else _decision_for(self._actions)
        )
        review_required = bool(
            self._actions & {IssueAction.QUARANTINE, IssueAction.HUMAN_REVIEW}
        ) or any(issue.severity is IssueSeverity.CRITICAL for issue in issues)
        return ValidationReport(
            decision=decision,
            issues=issues,
            human_review_required=review_required,
        )


def validate_protocol_schema(schema: ProtocolSchema) -> ValidationReport:
    """Validate semantic schema constraints that intentionally exceed shape validation."""

    collector = _IssueCollector()
    _validate_schema_limitations(schema, collector)
    _prepare_patterns(schema, collector)
    return collector.finish()


def _validate_schema_limitations(
    schema: ProtocolSchema,
    collector: _IssueCollector,
) -> None:
    codes = [limitation.code for limitation in schema.limitations]
    if len(codes) != len(set(codes)):
        collector.add(
            code="schema.limitation_code_duplicate",
            path="/limitations",
            message="Protocol limitation codes must be unique.",
        )
    if len(codes) > M0101_MAX_DECLARED_LIMITATIONS:
        collector.add(
            code="schema.limitation_capacity_exceeded",
            path="/limitations",
            message="Protocol limitations exceed the declared resource ceiling.",
        )
    if M0101_RESERVED_LIMITATION_CODES.intersection(codes):
        collector.add(
            code="schema.limitation_code_reserved",
            path="/limitations",
            severity=IssueSeverity.CRITICAL,
            message="The module-owned interpretation ceiling code is reserved.",
        )


def validate_metadata(
    schema: ProtocolSchema,
    document: MetadataDocument,
    *,
    consent_state: ConsentState,
    expected_identity_binding_digest: Sha256Digest | None = None,
) -> ValidationReport:
    """Evaluate a metadata document without mutation, inference, or external I/O."""

    collector = _IssueCollector()
    _validate_consent(consent_state, collector)
    _validate_document_identity(schema, document, collector)
    if (
        expected_identity_binding_digest is not None
        and identity_binding_digest(schema, document) != expected_identity_binding_digest
    ):
        collector.add(
            code="identity.lineage_binding_mismatch",
            path="/entries",
            severity=IssueSeverity.CRITICAL,
            action=IssueAction.QUARANTINE,
            message="Identity-key evidence does not match the supplied lineage binding.",
        )

    fields_by_path = {field.path: field for field in schema.fields}
    entries_by_path = {entry.path: entry for entry in document.entries}
    units_by_code = {unit.code: unit for unit in schema.units}
    vocabularies = {
        vocabulary.vocabulary_id: frozenset(term.code for term in vocabulary.terms)
        for vocabulary in schema.vocabularies
    }
    patterns = _prepare_patterns(schema, collector)
    context = _ConstraintContext(
        patterns=patterns,
        vocabularies=vocabularies,
        units_by_code=units_by_code,
        collector=collector,
    )

    for path in sorted(entries_by_path.keys() - fields_by_path.keys()):
        collector.add(
            code="field.unknown",
            path=path,
            message="The document contains a field not declared by the protocol schema.",
        )

    observations: dict[str, _CompatibilityObservation] = {}
    for path in sorted(fields_by_path):
        field = fields_by_path[path]
        entry = entries_by_path.get(path)
        if entry is None:
            _validate_absent_field(field, collector)
            observations[path] = _ABSENT_COMPATIBILITY_OBSERVATION
            continue
        _validate_cardinality(field, entry, collector)
        compatible_values, indeterminate = _validate_entry_values(
            field,
            entry,
            context,
        )
        observations[path] = _CompatibilityObservation(
            present=True,
            values=frozenset(compatible_values),
            indeterminate=indeterminate,
        )

    _validate_compatibility(schema, observations, collector)
    return collector.finish()


def _bounded_message(message: str) -> str:
    if len(message) <= _MAX_MESSAGE_LENGTH:
        return message
    return f"{message[: _MAX_MESSAGE_LENGTH - 3]}..."


def _issue_sort_key(issue: ConformanceIssue) -> _IssueKey:
    return (
        issue.code,
        issue.path,
        issue.severity.value,
        issue.action.value,
        issue.message,
        tuple(canonical_json_bytes(reference).decode("utf-8") for reference in issue.evidence),
    )


def _decision_for(actions: set[IssueAction]) -> ConformanceDecision:
    if IssueAction.QUARANTINE in actions:
        return ConformanceDecision.QUARANTINED
    if IssueAction.REJECT in actions:
        return ConformanceDecision.NONCONFORMANT
    if IssueAction.HUMAN_REVIEW in actions:
        return ConformanceDecision.REVIEW_REQUIRED
    return ConformanceDecision.CONFORMANT


def _validate_consent(consent_state: ConsentState, collector: _IssueCollector) -> None:
    if consent_state is ConsentState.GRANTED:
        return
    if consent_state is ConsentState.UNKNOWN:
        collector.add(
            code="consent.unknown",
            path=_CONSENT_PATH,
            severity=IssueSeverity.CRITICAL,
            action=IssueAction.QUARANTINE,
            message="Consent is unknown; metadata use must remain quarantined.",
        )
        return
    code = "consent.revoked" if consent_state is ConsentState.REVOKED else "consent.withheld"
    collector.add(
        code=code,
        path=_CONSENT_PATH,
        severity=IssueSeverity.CRITICAL,
        message="Consent does not authorize metadata evaluation.",
    )


def _validate_document_identity(
    schema: ProtocolSchema,
    document: MetadataDocument,
    collector: _IssueCollector,
) -> None:
    checks = (
        (
            document.schema_id != schema.schema_id,
            "document.schema_id_mismatch",
            "/schema_id",
            "The document schema identifier does not match the selected protocol.",
            IssueSeverity.ERROR,
            IssueAction.REJECT,
        ),
        (
            document.schema_version != schema.version,
            "document.schema_version_mismatch",
            "/schema_version",
            "The document schema version does not match the selected protocol.",
            IssueSeverity.ERROR,
            IssueAction.REJECT,
        ),
        (
            document.assay_version not in schema.assay_versions,
            "document.assay_version_unsupported",
            "/assay_version",
            "The document assay version is not supported by the protocol.",
            IssueSeverity.CRITICAL,
            IssueAction.QUARANTINE,
        ),
        (
            document.specimen_version not in schema.specimen_versions,
            "document.specimen_version_unsupported",
            "/specimen_version",
            "The document specimen version is not supported by the protocol.",
            IssueSeverity.CRITICAL,
            IssueAction.QUARANTINE,
        ),
    )
    for failed, code, path, message, severity, action in checks:
        if failed:
            collector.add(
                code=code,
                path=path,
                severity=severity,
                action=action,
                message=message,
            )


def _prepare_patterns(
    schema: ProtocolSchema,
    collector: _IssueCollector,
) -> dict[str, re.Pattern[str]]:
    patterns: dict[str, re.Pattern[str]] = {}
    actual_units = {unit.code: unit for unit in schema.units}
    for position, declared_unit in enumerate(schema.units):
        code = declared_unit.code
        if not is_supported_ucum_code(code):
            collector.add(
                code="schema.unit_code_unsupported",
                path="/units",
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message=f"Unit at position {position} is outside the pinned UCUM subset.",
            )
        elif declared_unit.dimension != unit_dimension(code):
            collector.add(
                code="schema.unit_dimension_invalid",
                path="/units",
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message=f"Unit at position {position} contradicts pinned UCUM semantics.",
            )
    for field in sorted(schema.fields, key=lambda item: item.path):
        _validate_schema_unit_relationship(field, actual_units, collector)
        if field.pattern is None:
            continue
        compiled, failure = _compile_safe_pattern(field.pattern)
        if compiled is None:
            collector.add(
                code=f"schema.pattern_{failure}",
                path=field.path,
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message="The field pattern is invalid or outside the bounded safe subset.",
            )
        else:
            patterns[field.path] = compiled
    return patterns


def _validate_schema_unit_relationship(
    field: FieldSpecification,
    units_by_code: Mapping[UnitCode, UnitDefinition],
    collector: _IssueCollector,
) -> None:
    if field.unit_dimension is None:
        if field.reference_unit is not None:
            collector.add(
                code="schema.reference_unit_unexpected",
                path=field.path,
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message="A unitless field cannot declare a reference unit.",
            )
        return
    if field.reference_unit is None or field.reference_unit not in field.allowed_units:
        collector.add(
            code="schema.reference_unit_invalid",
            path=field.path,
            severity=IssueSeverity.CRITICAL,
            action=IssueAction.QUARANTINE,
            message="A unitful field requires an allowed reference unit.",
        )
    if field.value_kind not in {ValueKind.INTEGER, ValueKind.NUMBER}:
        collector.add(
            code="schema.unit_kind_invalid",
            path=field.path,
            severity=IssueSeverity.CRITICAL,
            action=IssueAction.QUARANTINE,
            message="UCUM units may only constrain integer or number fields.",
        )
    for code in sorted(set(field.allowed_units)):
        unit = units_by_code.get(code)
        if unit is not None and unit.dimension != field.unit_dimension:
            collector.add(
                code="schema.unit_dimension_mismatch",
                path=field.path,
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message="An allowed UCUM code has a different dimension from its field.",
            )


def _compile_safe_pattern(pattern: str) -> tuple[re.Pattern[str] | None, str | None]:
    """Compile a linear, bounded regex subset; reject risky constructs before stdlib regex."""

    if not _is_bounded_pattern(pattern):
        return None, "unsafe"
    try:
        return re.compile(pattern), None
    except re.error:
        return None, "invalid"


def _is_bounded_pattern(pattern: str) -> bool:
    return _BoundedPatternScanner(pattern).scan()


class _BoundedPatternScanner:
    """Small recognizer for concatenated atoms with bounded repetition only."""

    __slots__ = ("_can_quantify", "_index", "_pattern", "_quantified")

    def __init__(self, pattern: str) -> None:
        self._pattern = pattern
        self._index = 0
        self._can_quantify = False
        self._quantified = False

    def scan(self) -> bool:
        while self._index < len(self._pattern):
            if not self._consume_token():
                return False
        return bool(self._pattern)

    def _consume_token(self) -> bool:
        character = self._pattern[self._index]
        if character == "\\":
            return self._consume_atom(_consume_escape(self._pattern, self._index))
        if character == "[":
            return self._consume_atom(_consume_character_class(self._pattern, self._index))
        if character in "()|*+?]}":
            return False
        if character == "{":
            return self._consume_quantifier()
        return self._consume_plain(character)

    def _consume_atom(self, next_index: int) -> bool:
        if next_index < 0:
            return False
        self._index = next_index
        self._can_quantify = True
        self._quantified = False
        return True

    def _consume_quantifier(self) -> bool:
        if not self._can_quantify or self._quantified:
            return False
        next_index = self._index + 1
        end = self._pattern.find("}", next_index)
        if end < 0 or not _bounded_repeat(self._pattern[next_index:end]):
            return False
        next_index = end + 1
        self._index = next_index
        self._can_quantify = False
        self._quantified = True
        return True

    def _consume_plain(self, character: str) -> bool:
        if character == "^" and self._index != 0:
            return False
        if character == "$" and self._index != len(self._pattern) - 1:
            return False
        self._index += 1
        self._can_quantify = character not in "^$"
        self._quantified = False
        return True


def _consume_escape(pattern: str, index: int) -> int:
    next_index = index + 1
    if next_index >= len(pattern):
        return -1
    escaped = pattern[next_index]
    allowed = "dDsSwW.[]{}?*+()|^$\\-"
    return next_index + 1 if escaped in allowed else -1


def _consume_character_class(pattern: str, index: int) -> int:
    cursor = index + 1
    if cursor < len(pattern) and pattern[cursor] == "^":
        cursor += 1
    has_member = False
    while cursor < len(pattern):
        character = pattern[cursor]
        if character == "\\":
            cursor = _consume_escape(pattern, cursor)
            if cursor < 0:
                return -1
            has_member = True
            continue
        if character == "]":
            return cursor + 1 if has_member else -1
        if character == "[":
            return -1
        has_member = True
        cursor += 1
    return -1


def _bounded_repeat(specification: str) -> bool:
    if not specification.isascii() or not specification.isdigit():
        return False
    return int(specification) <= _MAX_PATTERN_REPEAT


def _validate_absent_field(field: FieldSpecification, collector: _IssueCollector) -> None:
    if field.identity_key:
        collector.add(
            code="identity.missing",
            path=field.path,
            severity=IssueSeverity.CRITICAL,
            message="An identity key must have exactly one observed value.",
        )
    elif field.required:
        collector.add(
            code="field.required_missing",
            path=field.path,
            message="A required field is absent from the document.",
        )
    elif field.cardinality.minimum > 0:
        collector.add(
            code="field.cardinality_below_minimum",
            path=field.path,
            message="The field has fewer values than its minimum cardinality.",
        )


def _validate_cardinality(
    field: FieldSpecification,
    entry: MetadataEntry,
    collector: _IssueCollector,
) -> None:
    count = len(entry.values)
    if field.identity_key and count != 1:
        collector.add(
            code="identity.cardinality_invalid",
            path=field.path,
            severity=IssueSeverity.CRITICAL,
            message="An identity key must have exactly one observed value.",
        )
        return
    if count < field.cardinality.minimum:
        collector.add(
            code="field.cardinality_below_minimum",
            path=field.path,
            message="The field has fewer values than its minimum cardinality.",
        )
    maximum = field.cardinality.maximum
    if maximum is not None and count > maximum:
        collector.add(
            code="field.cardinality_above_maximum",
            path=field.path,
            message="The field has more values than its maximum cardinality.",
        )


def _validate_entry_values(
    field: FieldSpecification,
    entry: MetadataEntry,
    context: _ConstraintContext,
) -> tuple[tuple[_TypedScalar, ...], bool]:
    compatible: list[_TypedScalar] = []
    indeterminate = False
    ordered_values = sorted(entry.values, key=canonical_json_bytes)
    for position, metadata_value in enumerate(ordered_values):
        if isinstance(metadata_value, UnresolvedValue):
            _validate_unresolved(field, metadata_value, position, context.collector)
            indeterminate = True
            continue
        if _validate_observed(
            field,
            metadata_value,
            position,
            context,
        ):
            compatible.append(_typed_observed_scalar(field, metadata_value))
        else:
            indeterminate = True
    return tuple(compatible), indeterminate


def _validate_unresolved(
    field: FieldSpecification,
    value: UnresolvedValue,
    position: int,
    collector: _IssueCollector,
) -> None:
    state = MissingnessState(value.state)
    evidence = (value.evidence,) if value.evidence is not None else ()
    if state not in field.allowed_missingness:
        collector.add(
            code="value.missingness_not_allowed",
            path=field.path,
            message=f"Missingness at position {position} is not allowed for this field.",
            evidence=evidence,
        )
    collector.add(
        code=f"value.unresolved_{state.value}",
        path=field.path,
        severity=IssueSeverity.CRITICAL,
        action=IssueAction.QUARANTINE,
        message=(
            f"Unresolved {state.value} value at position {position} requires "
            "quarantine and review; the caller-provided reason is intentionally omitted."
        ),
        evidence=evidence,
    )
    if field.identity_key:
        collector.add(
            code="identity.unresolved",
            path=field.path,
            severity=IssueSeverity.CRITICAL,
            message="An identity key cannot use an unresolved value.",
            evidence=evidence,
        )


def _validate_observed(
    field: FieldSpecification,
    observed: ObservedValue,
    position: int,
    context: _ConstraintContext,
) -> bool:
    kind_valid = _validate_value_kind(field, observed.value, position, context.collector)
    unit_valid = _validate_unit(field, observed, position, context)
    constraints_valid = True
    if kind_valid:
        constraints_valid = _validate_scalar_constraints(
            field,
            observed,
            position,
            context,
            unit_valid=unit_valid,
        )
    return kind_valid and constraints_valid and unit_valid


def _validate_value_kind(
    field: FieldSpecification,
    value: ScalarValue,
    position: int,
    collector: _IssueCollector,
) -> bool:
    valid = _matches_value_kind(value, field.value_kind)
    if not valid:
        collector.add(
            code="value.kind_mismatch",
            path=field.path,
            message=f"Observed value at position {position} has the wrong strict value kind.",
        )
    return valid


def _matches_value_kind(value: ScalarValue, value_kind: ValueKind) -> bool:
    if value_kind in {ValueKind.TEXT, ValueKind.TIMESTAMP, ValueKind.IDENTIFIER, ValueKind.TERM}:
        return type(value) is str
    if value_kind is ValueKind.INTEGER:
        return type(value) is int
    if value_kind is ValueKind.NUMBER:
        return type(value) in {int, float}
    return type(value) is bool


def _validate_scalar_constraints(
    field: FieldSpecification,
    observed: ObservedValue,
    position: int,
    context: _ConstraintContext,
    *,
    unit_valid: bool,
) -> bool:
    value = observed.value
    valid = True
    if field.value_kind is ValueKind.TIMESTAMP and not _valid_timestamp(value):
        context.collector.add(
            code="value.timestamp_invalid",
            path=field.path,
            message=f"Timestamp at position {position} is not strict RFC 3339 with an offset.",
        )
        valid = False
    if field.value_kind is ValueKind.IDENTIFIER and not _valid_identifier(value):
        context.collector.add(
            code="value.identifier_invalid",
            path=field.path,
            message=f"Identifier at position {position} does not match identifier syntax.",
        )
        if field.identity_key:
            context.collector.add(
                code="identity.value_invalid",
                path=field.path,
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.HUMAN_REVIEW,
                message="An observed identity key has invalid identifier syntax.",
            )
        valid = False
    if field.value_kind is ValueKind.TERM:
        valid = (
            _validate_term(field, value, position, context.vocabularies, context.collector)
            and valid
        )
    if field.numeric_bounds is not None and unit_valid:
        valid = (
            _validate_numeric_bounds(
                field,
                observed,
                position,
                context.collector,
            )
            and valid
        )
    pattern = context.patterns.get(field.path)
    if pattern is not None:
        valid = _validate_pattern(field, value, position, pattern, context.collector) and valid
    return valid


def _valid_timestamp(value: ScalarValue) -> bool:
    if not isinstance(value, str) or _RFC3339_PATTERN.fullmatch(value) is None:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def _valid_identifier(value: ScalarValue) -> bool:
    return isinstance(value, str) and _IDENTIFIER_PATTERN.fullmatch(value) is not None


def _validate_term(
    field: FieldSpecification,
    value: ScalarValue,
    position: int,
    vocabularies: dict[str, frozenset[str]],
    collector: _IssueCollector,
) -> bool:
    if not isinstance(value, str) or _VOCABULARY_CODE_PATTERN.fullmatch(value) is None:
        collector.add(
            code="value.term_code_invalid",
            path=field.path,
            message=f"Term at position {position} does not match controlled-code syntax.",
        )
        return False
    vocabulary_id = field.vocabulary_id
    if vocabulary_id is not None and value not in vocabularies[vocabulary_id]:
        collector.add(
            code="value.term_unknown",
            path=field.path,
            message=f"Term at position {position} is absent from the controlled vocabulary.",
        )
        return False
    return True


def _validate_numeric_bounds(
    field: FieldSpecification,
    observed: ObservedValue,
    position: int,
    collector: _IssueCollector,
) -> bool:
    value = observed.value
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    bounds = field.numeric_bounds
    if bounds is None:
        return True
    comparable = _reference_quantity(field, value, observed.unit)
    valid = True
    if bounds.minimum is not None and comparable < Decimal(str(bounds.minimum)):
        collector.add(
            code="value.numeric_below_minimum",
            path=field.path,
            message=f"Numeric value at position {position} is below its inclusive minimum.",
        )
        valid = False
    if bounds.maximum is not None and comparable > Decimal(str(bounds.maximum)):
        collector.add(
            code="value.numeric_above_maximum",
            path=field.path,
            message=f"Numeric value at position {position} is above its inclusive maximum.",
        )
        valid = False
    return valid


def _validate_pattern(
    field: FieldSpecification,
    value: ScalarValue,
    position: int,
    pattern: re.Pattern[str],
    collector: _IssueCollector,
) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) > _MAX_PATTERN_INPUT_LENGTH:
        collector.add(
            code="value.pattern_input_too_long",
            path=field.path,
            message=f"Pattern input at position {position} exceeds the safe evaluation limit.",
        )
        return False
    if pattern.fullmatch(value) is not None:
        return True
    collector.add(
        code="value.pattern_mismatch",
        path=field.path,
        message=f"Observed value at position {position} does not match the field pattern.",
    )
    if field.identity_key:
        collector.add(
            code="identity.pattern_mismatch",
            path=field.path,
            severity=IssueSeverity.CRITICAL,
            action=IssueAction.HUMAN_REVIEW,
            message="An observed identity key contradicts its declared identity pattern.",
        )
    return False


def _validate_unit(
    field: FieldSpecification,
    observed: ObservedValue,
    position: int,
    context: _ConstraintContext,
) -> bool:
    unit_code = observed.unit
    if field.unit_dimension is None:
        if unit_code is None:
            return True
        context.collector.add(
            code="value.unit_unexpected",
            path=field.path,
            message=f"Observed value at position {position} carries an unexpected unit.",
        )
        return False
    if unit_code is None:
        context.collector.add(
            code="value.unit_required",
            path=field.path,
            message=f"Observed value at position {position} requires a UCUM unit.",
        )
        return False
    unit = context.units_by_code.get(unit_code)
    if unit is None:
        context.collector.add(
            code="value.unit_unknown",
            path=field.path,
            message=f"UCUM code at position {position} is not registered by the schema.",
        )
        return False
    valid = True
    if unit_code not in field.allowed_units:
        context.collector.add(
            code="value.unit_not_allowed",
            path=field.path,
            message=f"UCUM code at position {position} is not allowed for this field.",
        )
        valid = False
    if unit.dimension != field.unit_dimension:
        context.collector.add(
            code="value.unit_dimension_mismatch",
            path=field.path,
            message=f"UCUM code at position {position} has the wrong physical dimension.",
        )
        valid = False
    return valid


def _validate_compatibility(
    schema: ProtocolSchema,
    observations: dict[str, _CompatibilityObservation],
    collector: _IssueCollector,
) -> None:
    fields_by_path = {field.path: field for field in schema.fields}
    for rule in sorted(schema.compatibility_rules, key=lambda item: item.rule_id):
        applicability = tuple(
            _predicate_result(predicate, fields_by_path[predicate.path], observations)
            for predicate in rule.when_all
        )
        if False in applicability:
            continue
        if None in applicability:
            predicate = next(
                predicate
                for predicate, result in zip(rule.when_all, applicability, strict=True)
                if result is None
            )
            collector.add(
                code="compatibility.applicability_indeterminate",
                path=predicate.path,
                severity=IssueSeverity.CRITICAL,
                action=IssueAction.QUARANTINE,
                message=(
                    f"Compatibility rule {rule.rule_id} cannot determine whether its "
                    "precondition applies because evidence is unresolved or invalid."
                ),
            )
            continue
        for predicate in rule.require_all:
            result = _predicate_result(
                predicate,
                fields_by_path[predicate.path],
                observations,
            )
            if result is True:
                continue
            if result is None:
                collector.add(
                    code="compatibility.requirement_indeterminate",
                    path=predicate.path,
                    severity=IssueSeverity.CRITICAL,
                    action=IssueAction.QUARANTINE,
                    message=(
                        f"Compatibility rule {rule.rule_id} cannot evaluate a required "
                        "predicate because evidence is unresolved or invalid."
                    ),
                )
                continue
            collector.add(
                code="compatibility.requirement_failed",
                path=predicate.path,
                severity=_compatibility_severity(rule.on_failure),
                action=rule.on_failure,
                message=(
                    f"Compatibility rule {rule.rule_id} requires an unsatisfied "
                    f"{predicate.operator.value} predicate."
                ),
            )


def _predicate_result(
    predicate: CompatibilityPredicate,
    field: FieldSpecification,
    observations: dict[str, _CompatibilityObservation],
) -> bool | None:
    observation = observations.get(
        predicate.path,
        _ABSENT_COMPATIBILITY_OBSERVATION,
    )
    values = observation.values
    if predicate.operator is PredicateOperator.PRESENT:
        if values:
            return True
        return None if observation.present and observation.indeterminate else False
    if predicate.operator is PredicateOperator.ABSENT:
        if values:
            return False
        return None if observation.present and observation.indeterminate else True
    if any(
        _typed_predicate_scalar(field, predicate, expected) in values
        for expected in predicate.values
    ):
        return True
    return None if observation.indeterminate else False


def _reference_quantity(
    field: FieldSpecification,
    value: float,
    source_unit: str | None,
) -> Decimal:
    reference_unit = field.reference_unit
    if reference_unit is None:
        return Decimal(str(value))
    if source_unit is None or not is_supported_ucum_code(source_unit):
        raise _UnitQuantityInvariantError
    return convert_quantity(value, source=source_unit, target=reference_unit)


def _typed_observed_scalar(
    field: FieldSpecification,
    observed: ObservedValue,
) -> _TypedScalar:
    value = observed.value
    if field.value_kind in {ValueKind.INTEGER, ValueKind.NUMBER}:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise _ValidatedScalarInvariantError
        return "number", _reference_quantity(field, value, observed.unit)
    if field.value_kind is ValueKind.BOOLEAN:
        if not isinstance(value, bool):
            raise _ValidatedScalarInvariantError
        return "boolean", value
    if not isinstance(value, str):
        raise _ValidatedScalarInvariantError
    return "text", value


def _typed_predicate_scalar(
    field: FieldSpecification,
    predicate: CompatibilityPredicate,
    value: ScalarValue,
) -> _TypedScalar:
    if field.value_kind in {ValueKind.INTEGER, ValueKind.NUMBER}:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise _ValidatedScalarInvariantError
        return "number", _reference_quantity(field, value, predicate.unit)
    if field.value_kind is ValueKind.BOOLEAN:
        if not isinstance(value, bool):
            raise _ValidatedScalarInvariantError
        return "boolean", value
    if not isinstance(value, str):
        raise _ValidatedScalarInvariantError
    return "text", value


def _compatibility_severity(action: IssueAction) -> IssueSeverity:
    if action is IssueAction.QUARANTINE:
        return IssueSeverity.CRITICAL
    if action is IssueAction.HUMAN_REVIEW:
        return IssueSeverity.WARNING
    return IssueSeverity.ERROR


__all__ = ["ValidationReport", "validate_metadata", "validate_protocol_schema"]
