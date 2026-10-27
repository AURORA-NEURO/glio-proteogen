"""Conserve reviewed source context without diagnosing cases or running a model."""

from __future__ import annotations

import json
import re
from collections import Counter, deque
from enum import StrEnum
from typing import Literal, Never, Self, SupportsIndex

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

from .contracts import (
    MAX_CASES,
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_RECORDS,
    MAX_CONTEXT_SOURCES,
    AdmissionError,
    canonical_bytes,
    digest,
    validate_digest,
)

EVIDENCE_SCHEMA = "cptac-gbm-reviewed-context-evidence/1.0.0"
INVENTORY_SCHEMA = "cptac-gbm-context-inventory/1.0.0"


class ContextState(StrEnum):
    SOURCE_SUPPORTED = "source_supported"
    OUT_OF_SCOPE = "out_of_scope"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class ContextComponent(StrEnum):
    ORGANISM = "organism"
    DISEASE_POPULATION = "disease_population"
    PRIMARY_POPULATION_MAPPING = "primary_population_mapping"
    SPECIMEN_MATERIAL = "specimen_material"
    ASSAY_CONTEXT = "assay_context"
    RAW_COUNT_COORDINATE = "raw_count_coordinate"
    BATCH_CORRECTION = "batch_correction"
    COLLECTION_TIMEPOINT = "collection_timepoint"
    TREATMENT_EXPOSURE = "treatment_exposure"


REQUIRED_COMPONENTS = tuple(ContextComponent)[:5]
COMPONENTS = tuple(ContextComponent)
DESCRIPTIVE_COMPONENTS = (
    ContextComponent.COLLECTION_TIMEPOINT,
    ContextComponent.TREATMENT_EXPOSURE,
)
TIMEPOINT_VALUES = ("initial", "recurrent", "other", "unknown", "conflicting")
TREATMENT_VALUES = ("unexposed", "exposed", "other", "unknown", "conflicting")


class ContextAssertion(StrEnum):
    SUPPORTS_TARGET = "supports_target"
    OPPOSES_TARGET = "opposes_target"
    UNKNOWN = "unknown"
    DESCRIPTIVE = "descriptive"


class ReviewBasis(StrEnum):
    ORGANISM = "explicit_source_organism"
    DIAGNOSIS = "explicit_integrated_diagnosis"
    POPULATION = "explicit_source_population_mapping"
    MATERIAL = "explicit_source_material"
    ASSAY = "explicit_source_assay"
    PROCESSING = "explicit_source_processing"
    TIMEPOINT = "explicit_source_timepoint"
    TREATMENT = "explicit_source_treatment"
    UNRESOLVED = "unresolved_source_observation"


class LineageScope(StrEnum):
    EXACT_SPECIMEN = "exact_specimen"
    REVIEWED_CASE_TO_SPECIMEN = "reviewed_case_to_specimen"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class ContextReason(StrEnum):
    NOT_PROVIDED = "not_provided"
    NO_RECORDS = "no_records"
    MISSING_COMPONENT = "missing_component"
    SOURCE_FIELD_ABSENT = "source_field_absent"
    NOT_REPORTED = "not_reported"
    NOT_TESTED = "not_tested"
    INSUFFICIENT_ASSAY_SCOPE = "insufficient_assay_scope"
    UNRESOLVED_PRIMARY_MAPPING = "unresolved_primary_mapping"
    UNRESOLVED_LINEAGE = "unresolved_lineage"
    AMBIGUOUS_LINEAGE = "ambiguous_lineage"
    EXPLICIT_OPPOSITION = "explicit_opposition"
    CONTRADICTORY_ASSERTIONS = "contradictory_assertions"
    CONTRADICTORY_DESCRIPTIONS = "contradictory_descriptions"


_BASES = {
    ContextComponent.ORGANISM: ReviewBasis.ORGANISM,
    ContextComponent.DISEASE_POPULATION: ReviewBasis.DIAGNOSIS,
    ContextComponent.PRIMARY_POPULATION_MAPPING: ReviewBasis.POPULATION,
    ContextComponent.SPECIMEN_MATERIAL: ReviewBasis.MATERIAL,
    ContextComponent.ASSAY_CONTEXT: ReviewBasis.ASSAY,
    ContextComponent.RAW_COUNT_COORDINATE: ReviewBasis.PROCESSING,
    ContextComponent.BATCH_CORRECTION: ReviewBasis.PROCESSING,
    ContextComponent.COLLECTION_TIMEPOINT: ReviewBasis.TIMEPOINT,
    ContextComponent.TREATMENT_EXPOSURE: ReviewBasis.TREATMENT,
}
_INPUT_REASONS = frozenset(
    (
        ContextReason.SOURCE_FIELD_ABSENT,
        ContextReason.NOT_REPORTED,
        ContextReason.NOT_TESTED,
        ContextReason.INSUFFICIENT_ASSAY_SCOPE,
        ContextReason.UNRESOLVED_PRIMARY_MAPPING,
        ContextReason.UNRESOLVED_LINEAGE,
        ContextReason.AMBIGUOUS_LINEAGE,
    )
)


def _text(value: object, *, maximum: int, identifier: bool = False, empty: bool = False) -> str:
    if (
        type(value) is not str
        or len(value) > maximum
        or (not empty and (not value or value.strip() != value))
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or (identifier and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value) is None)
    ):
        raise AdmissionError("context text is invalid")
    return value


class _Private:
    __slots__ = ()

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("private context evidence is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("private context evidence is immutable")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} private>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise TypeError("private context evidence cannot be pickled")


class ContextTarget(_Private):
    """A caller's exact admitted RNA-file/lineage binding, never public metadata."""

    __slots__ = ("_lineage_digest", "_rna_key")
    _rna_key: str
    _lineage_digest: str

    def __init__(self, rna_key: str, lineage_digest: str) -> None:
        object.__setattr__(self, "_rna_key", _text(rna_key, maximum=128, identifier=True))
        object.__setattr__(self, "_lineage_digest", validate_digest(lineage_digest))

    @property
    def rna_key(self) -> str:
        return self._rna_key

    @property
    def lineage_digest(self) -> str:
        return self._lineage_digest


class ReviewedContextRecord(_Private):
    """An explicit reviewed semantic assertion; original text is never classified."""

    __slots__ = (
        "_assertion",
        "_component",
        "_descriptive_value",
        "_lineage_scope",
        "_reason_code",
        "_record_key",
        "_review_basis",
        "_source_digest",
        "_source_location",
        "_source_value",
        "_supersedes",
        "_supersession_source_location",
    )
    _record_key: str
    _source_digest: str
    _source_location: str
    _source_value: str
    _component: ContextComponent
    _assertion: ContextAssertion
    _review_basis: ReviewBasis
    _lineage_scope: LineageScope
    _reason_code: ContextReason | None
    _descriptive_value: str | None
    _supersedes: tuple[str, ...]
    _supersession_source_location: str | None

    def __init__(
        self,
        *,
        record_key: str,
        source_digest: str,
        source_location: str,
        source_value: str,
        component: ContextComponent,
        assertion: ContextAssertion,
        review_basis: ReviewBasis,
        lineage_scope: LineageScope,
        reason_code: ContextReason | None = None,
        descriptive_value: str | None = None,
        supersedes: tuple[str, ...] = (),
        supersession_source_location: str | None = None,
    ) -> None:
        key = _text(record_key, maximum=128, identifier=True)
        source = validate_digest(source_digest)
        location = _text(source_location, maximum=512)
        value = _text(source_value, maximum=2048, empty=True)
        if (
            type(component) is not ContextComponent
            or type(assertion) is not ContextAssertion
            or type(review_basis) is not ReviewBasis
            or type(lineage_scope) is not LineageScope
            or (reason_code is not None and type(reason_code) is not ContextReason)
        ):
            raise AdmissionError("context semantic type is invalid")
        if review_basis not in (_BASES[component], ReviewBasis.UNRESOLVED):
            raise AdmissionError("context review basis does not match its component")
        unknown = assertion is ContextAssertion.UNKNOWN or (
            assertion is ContextAssertion.DESCRIPTIVE and descriptive_value == "unknown"
        )
        if unknown:
            if reason_code not in _INPUT_REASONS:
                raise AdmissionError("unknown context requires an explicit reason")
        elif reason_code is not None or not value.strip() or review_basis is ReviewBasis.UNRESOLVED:
            raise AdmissionError("resolved context requires an explicit source review")
        if component in DESCRIPTIVE_COMPONENTS:
            allowed = (
                TIMEPOINT_VALUES
                if component is ContextComponent.COLLECTION_TIMEPOINT
                else TREATMENT_VALUES
            )
            if (
                assertion is not ContextAssertion.DESCRIPTIVE
                or descriptive_value not in allowed[:-1]
            ):
                raise AdmissionError("descriptive context is invalid")
        elif assertion is ContextAssertion.DESCRIPTIVE or descriptive_value is not None:
            raise AdmissionError("context descriptor is not applicable")
        if lineage_scope in (LineageScope.UNRESOLVED, LineageScope.AMBIGUOUS):
            expected = (
                ContextReason.UNRESOLVED_LINEAGE
                if lineage_scope is LineageScope.UNRESOLVED
                else ContextReason.AMBIGUOUS_LINEAGE
            )
            if not unknown or reason_code is not expected:
                raise AdmissionError("unresolved context linkage cannot support a claim")
        if type(supersedes) is not tuple or len(supersedes) > 64:
            raise AdmissionError("context supersession is invalid")
        predecessors = tuple(_text(x, maximum=128, identifier=True) for x in supersedes)
        if len(set(predecessors)) != len(predecessors) or key in predecessors:
            raise AdmissionError("context supersession is invalid")
        if predecessors:
            correction = _text(supersession_source_location, maximum=512)
        elif supersession_source_location is not None:
            raise AdmissionError("context supersession evidence is not applicable")
        else:
            correction = None
        for name, item in (
            ("record_key", key),
            ("source_digest", source),
            ("source_location", location),
            ("source_value", value),
            ("component", component),
            ("assertion", assertion),
            ("review_basis", review_basis),
            ("lineage_scope", lineage_scope),
            ("reason_code", reason_code),
            ("descriptive_value", descriptive_value),
            ("supersedes", predecessors),
            ("supersession_source_location", correction),
        ):
            object.__setattr__(self, "_" + name, item)

    @property
    def record_key(self) -> str:
        return self._record_key

    @property
    def source_digest(self) -> str:
        return self._source_digest

    @property
    def component(self) -> ContextComponent:
        return self._component

    @property
    def assertion(self) -> ContextAssertion:
        return self._assertion

    @property
    def lineage_scope(self) -> LineageScope:
        return self._lineage_scope

    @property
    def reason_code(self) -> ContextReason | None:
        return self._reason_code

    @property
    def descriptive_value(self) -> str | None:
        return self._descriptive_value

    @property
    def supersedes(self) -> tuple[str, ...]:
        return self._supersedes

    def _document(self) -> dict[str, object]:
        return {
            "record_key": self._record_key,
            "source_digest": self._source_digest,
            "source_location": self._source_location,
            "source_value": self._source_value,
            "component": self._component.value,
            "assertion": self._assertion.value,
            "review_basis": self._review_basis.value,
            "lineage_scope": self._lineage_scope.value,
            "reason_code": self._reason_code.value if self._reason_code is not None else None,
            "descriptive_value": self._descriptive_value,
            "supersedes": sorted(self._supersedes),
            "supersession_source_location": self._supersession_source_location,
        }


class SpecimenContextEvidence(_Private):
    __slots__ = ("_records", "_target")
    _target: ContextTarget
    _records: tuple[ReviewedContextRecord, ...]

    def __init__(self, target: ContextTarget, records: tuple[ReviewedContextRecord, ...]) -> None:
        if (
            type(target) is not ContextTarget
            or type(records) is not tuple
            or len(records) > MAX_CONTEXT_RECORDS
        ):
            raise AdmissionError("specimen context evidence is invalid")
        if any(type(record) is not ReviewedContextRecord for record in records):
            raise AdmissionError("specimen context record type is invalid")
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_records", records)

    @property
    def target(self) -> ContextTarget:
        return self._target

    @property
    def records(self) -> tuple[ReviewedContextRecord, ...]:
        return self._records


class ContextStateCounts(FrozenModel):
    source_supported: int = Field(ge=0, le=MAX_CASES)
    out_of_scope: int = Field(ge=0, le=MAX_CASES)
    unknown: int = Field(ge=0, le=MAX_CASES)
    conflicting: int = Field(ge=0, le=MAX_CASES)

    @property
    def total(self) -> int:
        return self.source_supported + self.out_of_scope + self.unknown + self.conflicting


class ComponentStateCounts(FrozenModel):
    component: ContextComponent
    states: ContextStateCounts


class DescriptiveContextCounts(FrozenModel):
    values: tuple[tuple[str, int], ...]


class ContextReasonCount(FrozenModel):
    reason_code: ContextReason
    specimen_count: int = Field(ge=1, le=MAX_CASES)


class ContextInventoryReceipt(FrozenModel):
    schema_version: Literal["cptac-gbm-context-inventory/1.0.0"] = (
        "cptac-gbm-context-inventory/1.0.0"
    )
    profile_id: Literal["cptac-gbm-native-star-purity-preflight/1.0.0"] = (
        "cptac-gbm-native-star-purity-preflight/1.0.0"
    )
    planned_count: int = Field(ge=1, le=MAX_CASES)
    provided_entry_count: int = Field(ge=0, le=MAX_CASES)
    not_provided_count: int = Field(ge=0, le=MAX_CASES)
    verified_source_count: int = Field(ge=0, le=MAX_CONTEXT_SOURCES)
    used_source_count: int = Field(ge=0, le=MAX_CONTEXT_SOURCES)
    input_record_count: int = Field(ge=0, le=MAX_CONTEXT_RECORDS)
    distinct_record_count: int = Field(ge=0, le=MAX_CONTEXT_RECORDS)
    duplicate_record_count: int = Field(ge=0, le=MAX_CONTEXT_RECORDS)
    superseded_record_count: int = Field(ge=0, le=MAX_CONTEXT_RECORDS)
    state_counts: ContextStateCounts
    component_state_counts: tuple[ComponentStateCounts, ...]
    collection_timepoint_counts: DescriptiveContextCounts
    treatment_exposure_counts: DescriptiveContextCounts
    reason_counts: tuple[ContextReasonCount, ...]
    ordered_axis_digest: Sha256Digest
    evidence_digest: Sha256Digest
    verified_source_set_digest: Sha256Digest
    source_assertions_independently_authenticated: Literal[False] = False
    source_lineage_independently_reproved: Literal[False] = False
    clinical_validation: Literal[False] = False
    inference_context_constructed: Literal[False] = False
    context_filters_count_preflight: Literal[False] = False
    existing_eligibility_flag_overwritten: Literal[False] = False
    operational_declarations_inferred: Literal[False] = False
    models_executed: Literal[False] = False

    @model_validator(mode="after")
    def conserved(self) -> Self:
        if (
            self.provided_entry_count + self.not_provided_count != self.planned_count
            or self.state_counts.total != self.planned_count
            or self.not_provided_count > self.state_counts.unknown
            or self.used_source_count > self.verified_source_count
            or self.used_source_count > self.distinct_record_count
            or (self.distinct_record_count > 0 and self.used_source_count == 0)
            or (self.provided_entry_count == 0 and self.input_record_count != 0)
            or self.distinct_record_count + self.duplicate_record_count != self.input_record_count
            or self.superseded_record_count > self.distinct_record_count
            or (
                self.distinct_record_count > 0
                and self.superseded_record_count == self.distinct_record_count
            )
            or tuple(row.component for row in self.component_state_counts) != COMPONENTS
            or any(row.states.total != self.planned_count for row in self.component_state_counts)
            or any(
                row.states.unknown < self.not_provided_count for row in self.component_state_counts
            )
            or tuple(row.reason_code for row in self.reason_counts)
            != tuple(sorted({row.reason_code for row in self.reason_counts}))
        ):
            raise ValueError("context aggregate counts are not conserved")
        reasons = {row.reason_code: row.specimen_count for row in self.reason_counts}
        if (
            reasons.get(ContextReason.NOT_PROVIDED, 0) != self.not_provided_count
            or reasons.get(ContextReason.NO_RECORDS, 0) > self.provided_entry_count
        ):
            raise ValueError("context absence reasons are not conserved")
        for values, expected, component in (
            (
                self.collection_timepoint_counts.values,
                TIMEPOINT_VALUES,
                self.component_state_counts[7],
            ),
            (
                self.treatment_exposure_counts.values,
                TREATMENT_VALUES,
                self.component_state_counts[8],
            ),
        ):
            if (
                tuple(row[0] for row in values) != expected
                or any(type(row[1]) is not int or not 0 <= row[1] <= MAX_CASES for row in values)
                or sum(row[1] for row in values) != self.planned_count
                or component.states.source_supported != sum(row[1] for row in values[:3])
                or component.states.unknown != values[3][1]
                or component.states.conflicting != values[4][1]
                or component.states.out_of_scope != 0
            ):
                raise ValueError("context descriptor counts are not conserved")
        return self


class SpecimenContextAssessment(_Private):
    __slots__ = ("_components", "_reasons", "_records", "_state", "_timepoint", "_treatment")
    _state: ContextState
    _components: tuple[ContextState, ...]
    _timepoint: str
    _treatment: str
    _reasons: tuple[ContextReason, ...]
    _records: tuple[ReviewedContextRecord, ...]

    def __init__(
        self,
        *,
        state: ContextState,
        components: tuple[ContextState, ...],
        timepoint: str,
        treatment: str,
        reasons: tuple[ContextReason, ...],
        records: tuple[ReviewedContextRecord, ...],
    ) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_components", components)
        object.__setattr__(self, "_timepoint", timepoint)
        object.__setattr__(self, "_treatment", treatment)
        object.__setattr__(self, "_reasons", reasons)
        object.__setattr__(self, "_records", records)

    @property
    def state(self) -> ContextState:
        return self._state

    @property
    def component_states(self) -> tuple[ContextState, ...]:
        return self._components

    @property
    def collection_timepoint(self) -> str:
        return self._timepoint

    @property
    def treatment_exposure(self) -> str:
        return self._treatment

    @property
    def reason_codes(self) -> tuple[ContextReason, ...]:
        return self._reasons


class ContextInventory(_Private):
    __slots__ = ("_assessments", "_receipt")
    _assessments: tuple[SpecimenContextAssessment, ...]
    _receipt: ContextInventoryReceipt

    def __init__(
        self,
        assessments: tuple[SpecimenContextAssessment, ...],
        receipt: ContextInventoryReceipt,
    ) -> None:
        object.__setattr__(self, "_assessments", assessments)
        object.__setattr__(self, "_receipt", receipt)

    @property
    def assessments(self) -> tuple[SpecimenContextAssessment, ...]:
        return self._assessments

    @property
    def receipt(self) -> ContextInventoryReceipt:
        return self._receipt


def _active_records(
    records: tuple[ReviewedContextRecord, ...],
) -> tuple[tuple[ReviewedContextRecord, ...], tuple[ReviewedContextRecord, ...], int]:
    unique: dict[str, ReviewedContextRecord] = {}
    for record in records:
        previous = unique.get(record.record_key)
        if previous is not None and previous._document() != record._document():
            raise AdmissionError("context record key has contradictory payloads")
        unique[record.record_key] = record
    indegrees = dict.fromkeys(unique, 0)
    superseded: set[str] = set()
    for record in unique.values():
        for predecessor in record.supersedes:
            prior = unique.get(predecessor)
            if prior is None or prior.component is not record.component:
                raise AdmissionError(
                    "context correction does not bind a same-component predecessor"
                )
            indegrees[predecessor] += 1
            superseded.add(predecessor)
    ready = deque(key for key, degree in indegrees.items() if degree == 0)
    visited = 0
    while ready:
        key = ready.popleft()
        visited += 1
        for predecessor in unique[key].supersedes:
            indegrees[predecessor] -= 1
            if indegrees[predecessor] == 0:
                ready.append(predecessor)
    if visited != len(unique):
        raise AdmissionError("context correction graph is cyclic")
    ordered = tuple(unique[key] for key in sorted(unique))
    return (
        ordered,
        tuple(record for record in ordered if record.record_key not in superseded),
        len(superseded),
    )


def _description(
    records: tuple[ReviewedContextRecord, ...],
    reasons: set[ContextReason],
) -> tuple[ContextState, str, set[ContextReason]]:
    values = {
        record.descriptive_value
        for record in records
        if record.descriptive_value is not None and record.descriptive_value != "unknown"
    }
    if len(values) > 1:
        reasons.add(ContextReason.CONTRADICTORY_DESCRIPTIONS)
        return ContextState.CONFLICTING, "conflicting", reasons
    if values:
        return ContextState.SOURCE_SUPPORTED, next(iter(values)), reasons
    return ContextState.UNKNOWN, "unknown", reasons


def _component(
    component: ContextComponent,
    records: tuple[ReviewedContextRecord, ...],
) -> tuple[ContextState, str | None, set[ContextReason]]:
    relevant = tuple(record for record in records if record.component is component)
    reasons = {r.reason_code for r in relevant if r.reason_code is not None}
    if any(record.lineage_scope is LineageScope.AMBIGUOUS for record in relevant):
        return (
            ContextState.CONFLICTING,
            "conflicting" if component in DESCRIPTIVE_COMPONENTS else None,
            reasons,
        )
    if component in DESCRIPTIVE_COMPONENTS:
        return _description(relevant, reasons)
    assertions = {record.assertion for record in relevant}
    if {ContextAssertion.SUPPORTS_TARGET, ContextAssertion.OPPOSES_TARGET} <= assertions:
        reasons.add(ContextReason.CONTRADICTORY_ASSERTIONS)
        return ContextState.CONFLICTING, None, reasons
    if ContextAssertion.OPPOSES_TARGET in assertions:
        reasons.add(ContextReason.EXPLICIT_OPPOSITION)
        return ContextState.OUT_OF_SCOPE, None, reasons
    if ContextAssertion.SUPPORTS_TARGET in assertions:
        return ContextState.SOURCE_SUPPORTED, None, reasons
    return ContextState.UNKNOWN, None, reasons


def _state_counts(states: tuple[ContextState, ...]) -> ContextStateCounts:
    counts = Counter(states)
    return ContextStateCounts(**{state.value: counts[state] for state in ContextState})


def _prepare_inventory(
    targets: tuple[ContextTarget, ...],
    evidence: tuple[SpecimenContextEvidence, ...],
    verified_source_digests: tuple[str, ...],
) -> tuple[tuple[str, ...], dict[str, SpecimenContextEvidence], int]:
    if (
        type(targets) is not tuple
        or not 1 <= len(targets) <= MAX_CASES
        or any(type(target) is not ContextTarget for target in targets)
        or type(evidence) is not tuple
        or len(evidence) > len(targets)
        or any(type(entry) is not SpecimenContextEvidence for entry in evidence)
        or type(verified_source_digests) is not tuple
        or len(verified_source_digests) > MAX_CONTEXT_SOURCES
    ):
        raise AdmissionError("context inventory bounds or types are invalid")
    axis = {target.rna_key: target for target in targets}
    if len(axis) != len(targets):
        raise AdmissionError("context RNA axis has duplicate keys")
    verified = tuple(validate_digest(value) for value in verified_source_digests)
    if len(set(verified)) != len(verified):
        raise AdmissionError("context source allowlist has duplicate bindings")
    entries: dict[str, SpecimenContextEvidence] = {}
    input_count = 0
    for entry in evidence:
        target = axis.get(entry.target.rna_key)
        if (
            target is None
            or target.lineage_digest != entry.target.lineage_digest
            or entry.target.rna_key in entries
        ):
            raise AdmissionError("context evidence does not match the exact planned RNA lineage")
        entries[entry.target.rna_key] = entry
        input_count += len(entry.records)
        if input_count > MAX_CONTEXT_RECORDS:
            raise AdmissionError("context record bound exceeded")
        if any(record.source_digest not in verified for record in entry.records):
            raise AdmissionError("context record source has not been byte-verified")
    return verified, entries, input_count


def assess_context_inventory(
    targets: tuple[ContextTarget, ...],
    evidence: tuple[SpecimenContextEvidence, ...] = (),
    *,
    verified_source_digests: tuple[str, ...] = (),
) -> ContextInventory:
    """Bind explicit reviewed records; never inspect expression or diagnose a case."""
    verified, entries, input_count = _prepare_inventory(targets, evidence, verified_source_digests)
    assessments: list[SpecimenContextAssessment] = []
    normalized: list[dict[str, object]] = []
    used: set[str] = set()
    distinct_count = superseded_count = 0
    for target in targets:
        entry = entries.get(target.rna_key)
        records = entry.records if entry is not None else ()
        distinct, active, superseded = _active_records(records)
        distinct_count += len(distinct)
        superseded_count += superseded
        used.update(record.source_digest for record in distinct)
        reasons: set[ContextReason] = set()
        if entry is None:
            reasons.add(ContextReason.NOT_PROVIDED)
        elif not records:
            reasons.add(ContextReason.NO_RECORDS)
        states: list[ContextState] = []
        descriptors: dict[ContextComponent, str] = {}
        for component in COMPONENTS:
            state, description, additional = _component(component, active)
            states.append(state)
            reasons.update(additional)
            if (
                entry is not None
                and component in REQUIRED_COMPONENTS
                and not any(record.component is component for record in active)
            ):
                reasons.add(ContextReason.MISSING_COMPONENT)
            if description is not None:
                descriptors[component] = description
        required = states[: len(REQUIRED_COMPONENTS)]
        overall = (
            ContextState.CONFLICTING
            if ContextState.CONFLICTING in required
            else ContextState.OUT_OF_SCOPE
            if ContextState.OUT_OF_SCOPE in required
            else ContextState.UNKNOWN
            if ContextState.UNKNOWN in required
            else ContextState.SOURCE_SUPPORTED
        )
        assessments.append(
            SpecimenContextAssessment(
                state=overall,
                components=tuple(states),
                timepoint=descriptors[ContextComponent.COLLECTION_TIMEPOINT],
                treatment=descriptors[ContextComponent.TREATMENT_EXPOSURE],
                reasons=tuple(sorted(reasons)),
                records=distinct,
            )
        )
        normalized.append(
            {
                "rna_key": target.rna_key,
                "lineage_digest": target.lineage_digest,
                "provided": entry is not None,
                "records": sorted((record._document() for record in records), key=canonical_bytes),
            }
        )
    encoded = canonical_bytes({"schema_version": EVIDENCE_SCHEMA, "entries": normalized})
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise AdmissionError("context evidence byte bound exceeded")
    result = tuple(assessments)
    reason_counts = Counter(reason for assessment in result for reason in assessment.reason_codes)
    receipt = ContextInventoryReceipt(
        planned_count=len(targets),
        provided_entry_count=len(entries),
        not_provided_count=len(targets) - len(entries),
        verified_source_count=len(verified),
        used_source_count=len(used),
        input_record_count=input_count,
        distinct_record_count=distinct_count,
        duplicate_record_count=input_count - distinct_count,
        superseded_record_count=superseded_count,
        state_counts=_state_counts(tuple(item.state for item in result)),
        component_state_counts=tuple(
            ComponentStateCounts(
                component=component,
                states=_state_counts(tuple(item.component_states[index] for item in result)),
            )
            for index, component in enumerate(COMPONENTS)
        ),
        collection_timepoint_counts=DescriptiveContextCounts(
            values=tuple(
                (value, sum(item.collection_timepoint == value for item in result))
                for value in TIMEPOINT_VALUES
            )
        ),
        treatment_exposure_counts=DescriptiveContextCounts(
            values=tuple(
                (value, sum(item.treatment_exposure == value for item in result))
                for value in TREATMENT_VALUES
            )
        ),
        reason_counts=tuple(
            ContextReasonCount(reason_code=reason, specimen_count=reason_counts[reason])
            for reason in sorted(reason_counts)
        ),
        ordered_axis_digest=digest(
            [
                {"rna_key": target.rna_key, "lineage_digest": target.lineage_digest}
                for target in targets
            ]
        ),
        evidence_digest=digest({"schema_version": EVIDENCE_SCHEMA, "entries": normalized}),
        verified_source_set_digest=digest(sorted(verified)),
    )
    return ContextInventory(result, receipt)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError("context JSON has duplicate keys")
        result[key] = value
    return result


def _enum(enum: type[StrEnum], value: object) -> StrEnum:
    if type(value) is not str:
        raise AdmissionError("context JSON semantic type is invalid")
    try:
        return enum(value)
    except ValueError:
        raise AdmissionError("context JSON semantic value is invalid") from None


def parse_context_evidence(
    payload: bytes,
    *,
    targets: tuple[ContextTarget, ...],
    verified_source_digests: tuple[str, ...] = (),
) -> ContextInventory:
    """Parse an already bounded/hash-verified private document, with a closed schema."""
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_CONTEXT_BYTES:
        raise AdmissionError("context JSON byte bound or type is invalid")
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_object)
    except (ValueError, UnicodeError, RecursionError):
        raise AdmissionError("context JSON is invalid") from None
    if (
        type(document) is not dict
        or set(document) != {"schema_version", "entries"}
        or document["schema_version"] != EVIDENCE_SCHEMA
        or type(document["entries"]) is not list
        or len(document["entries"]) > MAX_CASES
    ):
        raise AdmissionError("context JSON document schema is invalid")
    entries: list[SpecimenContextEvidence] = []
    required = {
        "record_key",
        "source_digest",
        "source_location",
        "source_value",
        "component",
        "assertion",
        "review_basis",
        "lineage_scope",
    }
    optional = {"reason_code", "descriptive_value", "supersedes", "supersession_source_location"}
    total = 0
    try:
        for row in document["entries"]:
            if (
                type(row) is not dict
                or set(row) != {"rna_key", "lineage_digest", "records"}
                or type(row["records"]) is not list
            ):
                raise AdmissionError("context JSON entry schema is invalid")
            total += len(row["records"])
            if total > MAX_CONTEXT_RECORDS:
                raise AdmissionError("context record bound exceeded")
            records: list[ReviewedContextRecord] = []
            for value in row["records"]:
                if (
                    type(value) is not dict
                    or not required <= set(value)
                    or not set(value) <= required | optional
                    or type(value.get("supersedes", [])) is not list
                ):
                    raise AdmissionError("context JSON record schema is invalid")
                records.append(
                    ReviewedContextRecord(
                        record_key=value["record_key"],
                        source_digest=value["source_digest"],
                        source_location=value["source_location"],
                        source_value=value["source_value"],
                        component=ContextComponent(_enum(ContextComponent, value["component"])),
                        assertion=ContextAssertion(_enum(ContextAssertion, value["assertion"])),
                        review_basis=ReviewBasis(_enum(ReviewBasis, value["review_basis"])),
                        lineage_scope=LineageScope(_enum(LineageScope, value["lineage_scope"])),
                        reason_code=(
                            ContextReason(_enum(ContextReason, value["reason_code"]))
                            if value.get("reason_code") is not None
                            else None
                        ),
                        descriptive_value=value.get("descriptive_value"),
                        supersedes=tuple(value.get("supersedes", [])),
                        supersession_source_location=value.get("supersession_source_location"),
                    )
                )
            entries.append(
                SpecimenContextEvidence(
                    ContextTarget(row["rna_key"], row["lineage_digest"]),
                    tuple(records),
                )
            )
    except (KeyError, TypeError, ValueError, RecursionError):
        raise AdmissionError("context JSON record is invalid") from None
    return assess_context_inventory(
        targets, tuple(entries), verified_source_digests=verified_source_digests
    )


__all__ = [
    "COMPONENTS",
    "DESCRIPTIVE_COMPONENTS",
    "EVIDENCE_SCHEMA",
    "INVENTORY_SCHEMA",
    "REQUIRED_COMPONENTS",
    "ContextAssertion",
    "ContextComponent",
    "ContextInventory",
    "ContextInventoryReceipt",
    "ContextReason",
    "ContextReasonCount",
    "ContextState",
    "ContextStateCounts",
    "ContextTarget",
    "LineageScope",
    "ReviewBasis",
    "ReviewedContextRecord",
    "SpecimenContextAssessment",
    "SpecimenContextEvidence",
    "assess_context_inventory",
    "parse_context_evidence",
]
