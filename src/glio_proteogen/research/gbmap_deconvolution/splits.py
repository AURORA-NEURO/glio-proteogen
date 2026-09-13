"""Leakage-safe donor/study validation planning for the GBmap fitter.

The transient plan contains donor keys because the offline fitter must exclude
whole biological donors.  The de-identified receipt deliberately contains only
counts and study keys: it never emits donor identifiers or identifier hashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .aggregate import (
    MIN_DONORS_PER_LINEAGE,
    MIN_STUDIES_PER_LINEAGE,
    AggregateReference,
    DonorLabelAggregate,
    donor_label_is_eligible,
)
from .errors import GbmapInputError

ValidationKind = Literal["whole_study", "within_study_donor"]

STRATIFIED_DONOR_FOLD_COUNT: Final = 5
MAX_REFERENCE_DONORS: Final = 4_096
MAX_REFERENCE_STUDIES: Final = 64
MAX_VALIDATION_FOLDS: Final = 1_024

_LABEL_REASON_ORDER: Final = (
    "insufficient_training_donors",
    "insufficient_training_studies",
    "no_eligible_holdout_records",
)
_FOLD_REASON_ORDER: Final = (
    "no_eligible_holdout_records",
    "no_same_study_training_donor",
    "fewer_than_two_evaluable_labels",
)


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{name} must be a nonempty trimmed string")
    return value


def _identifier_tuple(value: object, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ValueError(f"{name} must be an exact tuple")
    identifiers = tuple(_identifier(item, f"{name} item") for item in value)
    if not allow_empty and not identifiers:
        raise ValueError(f"{name} must not be empty")
    if identifiers != tuple(sorted(identifiers)) or len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{name} must be unique and lexically sorted")
    return identifiers


def _exact_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be an exact nonnegative integer")
    return value


def _ordered_reasons(value: object, allowed: tuple[str, ...], name: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ValueError(f"{name} must be an exact tuple")
    if any(type(reason) is not str or reason not in allowed for reason in value):
        raise ValueError(f"{name} contains an unknown reason")
    expected = tuple(reason for reason in allowed if reason in value)
    if value != expected:
        raise ValueError(f"{name} must be unique and canonically ordered")
    return value


@dataclass(frozen=True, slots=True)
class LabelFoldSupport:
    """Per-lineage support for one leakage-safe validation fold."""

    modeled_label: str
    training_usable_donor_count: int
    training_usable_study_count: int
    held_usable_donor_count: int
    held_usable_study_count: int
    evaluable: bool
    abstention_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.modeled_label, "modeled_label")
        counts = (
            _exact_nonnegative_int(
                self.training_usable_donor_count,
                "training_usable_donor_count",
            ),
            _exact_nonnegative_int(
                self.training_usable_study_count,
                "training_usable_study_count",
            ),
            _exact_nonnegative_int(self.held_usable_donor_count, "held_usable_donor_count"),
            _exact_nonnegative_int(self.held_usable_study_count, "held_usable_study_count"),
        )
        reasons = _ordered_reasons(
            self.abstention_reasons,
            _LABEL_REASON_ORDER,
            "label abstention_reasons",
        )
        expected: list[str] = []
        if counts[0] < MIN_DONORS_PER_LINEAGE:
            expected.append("insufficient_training_donors")
        if counts[1] < MIN_STUDIES_PER_LINEAGE:
            expected.append("insufficient_training_studies")
        if counts[2] == 0 or counts[3] == 0:
            expected.append("no_eligible_holdout_records")
        if reasons != tuple(expected) or self.evaluable is not (not expected):
            raise ValueError("label fold support does not match fixed evaluability gates")


@dataclass(frozen=True, slots=True)
class DeidentifiedValidationFoldReceipt:
    """Fold evidence safe to retain without donor identifiers or their hashes."""

    fold_id: str
    kind: ValidationKind
    training_study_keys: tuple[str, ...]
    held_study_keys: tuple[str, ...]
    training_donor_count: int
    held_donor_count: int
    label_support: tuple[LabelFoldSupport, ...]
    evaluable: bool
    abstention_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_fold_common(
            fold_id=self.fold_id,
            kind=self.kind,
            training_study_keys=self.training_study_keys,
            held_study_keys=self.held_study_keys,
            label_support=self.label_support,
            evaluable=self.evaluable,
            abstention_reasons=self.abstention_reasons,
        )
        _exact_nonnegative_int(self.training_donor_count, "training_donor_count")
        if _exact_nonnegative_int(self.held_donor_count, "held_donor_count") < 1:
            raise ValueError("held_donor_count must be positive")


@dataclass(frozen=True, slots=True)
class TransientValidationFold:
    """Internal fold carrying exact donors; this object must never be serialized."""

    fold_id: str
    kind: ValidationKind
    training_donor_keys: tuple[str, ...]
    held_donor_keys: tuple[str, ...]
    training_study_keys: tuple[str, ...]
    held_study_keys: tuple[str, ...]
    label_support: tuple[LabelFoldSupport, ...]
    evaluable: bool
    abstention_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        training_donors = _identifier_tuple(
            self.training_donor_keys,
            "training_donor_keys",
            allow_empty=True,
        )
        held_donors = _identifier_tuple(self.held_donor_keys, "held_donor_keys")
        if set(training_donors) & set(held_donors):
            raise ValueError("training and held donor keys must be disjoint")
        _validate_fold_common(
            fold_id=self.fold_id,
            kind=self.kind,
            training_study_keys=self.training_study_keys,
            held_study_keys=self.held_study_keys,
            label_support=self.label_support,
            evaluable=self.evaluable,
            abstention_reasons=self.abstention_reasons,
        )

    def deidentified_receipt(self) -> DeidentifiedValidationFoldReceipt:
        """Drop donor identities without replacing them with linkable hashes."""

        return DeidentifiedValidationFoldReceipt(
            fold_id=self.fold_id,
            kind=self.kind,
            training_study_keys=self.training_study_keys,
            held_study_keys=self.held_study_keys,
            training_donor_count=len(self.training_donor_keys),
            held_donor_count=len(self.held_donor_keys),
            label_support=self.label_support,
            evaluable=self.evaluable,
            abstention_reasons=self.abstention_reasons,
        )


def _validate_fold_common(
    *,
    fold_id: object,
    kind: object,
    training_study_keys: object,
    held_study_keys: object,
    label_support: object,
    evaluable: object,
    abstention_reasons: object,
) -> None:
    _identifier(fold_id, "fold_id")
    if kind not in ("whole_study", "within_study_donor"):
        raise ValueError("validation kind is unsupported")
    training_studies = _identifier_tuple(
        training_study_keys,
        "training_study_keys",
        allow_empty=True,
    )
    held_studies = _identifier_tuple(held_study_keys, "held_study_keys")
    if kind == "whole_study":
        if len(held_studies) != 1:
            raise ValueError("a whole-study validation fold must hold exactly one study")
        if set(training_studies) & set(held_studies):
            raise ValueError("whole-study folds cannot retain the held study in training")
    if type(label_support) is not tuple or not label_support:
        raise ValueError("label_support must be a nonempty exact tuple")
    if any(type(item) is not LabelFoldSupport for item in label_support):
        raise ValueError("label_support must contain exact LabelFoldSupport instances")
    labels = tuple(item.modeled_label for item in label_support)
    if labels != tuple(sorted(labels)) or len(labels) != len(set(labels)):
        raise ValueError("label_support must be unique and lexically sorted")
    reasons = _ordered_reasons(abstention_reasons, _FOLD_REASON_ORDER, "fold abstention_reasons")
    if type(evaluable) is not bool:
        raise ValueError("evaluable must be an exact Boolean")
    if evaluable is not (not reasons):
        raise ValueError("fold evaluability does not reconcile with abstention reasons")


@dataclass(frozen=True, slots=True)
class ValidationSplitReceipt:
    """De-identified split manifest bound to source and extraction provenance."""

    source_file_sha256: str
    source_bytes: int
    taxonomy_digest: str
    extraction_recipe_digest: str
    folds: tuple[DeidentifiedValidationFoldReceipt, ...]

    def __post_init__(self) -> None:
        for name, value in (
            ("source_file_sha256", self.source_file_sha256),
            ("taxonomy_digest", self.taxonomy_digest),
            ("extraction_recipe_digest", self.extraction_recipe_digest),
        ):
            if type(value) is not str or not value.startswith("sha256:") or len(value) != 71:
                raise ValueError(f"{name} must be a canonical sha256 digest")
        if type(self.source_bytes) is not int or self.source_bytes < 1:
            raise ValueError("source_bytes must be an exact positive integer")
        if type(self.folds) is not tuple or not self.folds:
            raise ValueError("folds must be a nonempty exact tuple")
        if any(type(fold) is not DeidentifiedValidationFoldReceipt for fold in self.folds):
            raise ValueError("folds must contain exact de-identified receipts")
        fold_ids = tuple(fold.fold_id for fold in self.folds)
        if len(fold_ids) != len(set(fold_ids)):
            raise ValueError("validation fold identifiers must be unique")


@dataclass(frozen=True, slots=True)
class ValidationSplitPlan:
    """Transient exact partitions plus a separately safe retained receipt."""

    aggregate_content_digest: str
    feature_order_digest: str
    folds: tuple[TransientValidationFold, ...]
    receipt: ValidationSplitReceipt
    _fold_index: dict[str, TransientValidationFold] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("aggregate_content_digest", self.aggregate_content_digest),
            ("feature_order_digest", self.feature_order_digest),
        ):
            if type(value) is not str or not value.startswith("sha256:") or len(value) != 71:
                raise ValueError(f"{name} must be a canonical sha256 digest")
        if type(self.folds) is not tuple or not self.folds:
            raise ValueError("folds must be a nonempty exact tuple")
        if any(type(fold) is not TransientValidationFold for fold in self.folds):
            raise ValueError("folds must contain exact transient validation folds")
        if len(self.folds) > MAX_VALIDATION_FOLDS:
            raise ValueError("validation plan exceeds its fixed fold bound")
        expected = tuple(fold.deidentified_receipt() for fold in self.folds)
        if self.receipt.folds != expected:
            raise ValueError("de-identified split receipt does not match transient folds")
        object.__setattr__(self, "_fold_index", {fold.fold_id: fold for fold in self.folds})

    def partition_records(
        self,
        reference: AggregateReference,
        fold_id: str,
    ) -> tuple[tuple[DonorLabelAggregate, ...], tuple[DonorLabelAggregate, ...]]:
        """Return exact training/held records after verifying reference binding."""

        if type(reference) is not AggregateReference:
            raise GbmapInputError("reference must be an exact AggregateReference instance")
        if (
            reference.aggregate_content_digest != self.aggregate_content_digest
            or reference.feature_order_digest != self.feature_order_digest
        ):
            raise GbmapInputError("validation plan does not bind the supplied aggregate reference")
        if type(fold_id) is not str or fold_id not in self._fold_index:
            raise GbmapInputError("validation fold identifier is unknown")
        fold = self._fold_index[fold_id]
        training = frozenset(fold.training_donor_keys)
        held = frozenset(fold.held_donor_keys)
        training_records: list[DonorLabelAggregate] = []
        held_records: list[DonorLabelAggregate] = []
        for record in reference.records:
            if record.donor_key in training:
                training_records.append(record)
            elif record.donor_key in held:
                held_records.append(record)
        return tuple(training_records), tuple(held_records)


def _label_support(
    labels: tuple[str, ...],
    training: tuple[DonorLabelAggregate, ...],
    held: tuple[DonorLabelAggregate, ...],
) -> tuple[LabelFoldSupport, ...]:
    support: list[LabelFoldSupport] = []
    for label in labels:
        training_label = tuple(record for record in training if record.modeled_label == label)
        held_label = tuple(record for record in held if record.modeled_label == label)
        training_donors = {record.donor_key for record in training_label}
        training_studies = {record.study_key for record in training_label}
        held_donors = {record.donor_key for record in held_label}
        held_studies = {record.study_key for record in held_label}
        reasons: list[str] = []
        if len(training_donors) < MIN_DONORS_PER_LINEAGE:
            reasons.append("insufficient_training_donors")
        if len(training_studies) < MIN_STUDIES_PER_LINEAGE:
            reasons.append("insufficient_training_studies")
        if not held_donors:
            reasons.append("no_eligible_holdout_records")
        support.append(
            LabelFoldSupport(
                modeled_label=label,
                training_usable_donor_count=len(training_donors),
                training_usable_study_count=len(training_studies),
                held_usable_donor_count=len(held_donors),
                held_usable_study_count=len(held_studies),
                evaluable=not reasons,
                abstention_reasons=tuple(reasons),
            )
        )
    return tuple(support)


def _fold(
    *,
    fold_id: str,
    kind: ValidationKind,
    training_donors: tuple[str, ...],
    held_donors: tuple[str, ...],
    donor_study: dict[str, str],
    usable_records: tuple[DonorLabelAggregate, ...],
    labels: tuple[str, ...],
) -> TransientValidationFold:
    training_set = frozenset(training_donors)
    held_set = frozenset(held_donors)
    training_records = tuple(
        record for record in usable_records if record.donor_key in training_set
    )
    held_records = tuple(record for record in usable_records if record.donor_key in held_set)
    support = _label_support(labels, training_records, held_records)
    held_studies = tuple(sorted({donor_study[donor] for donor in held_donors}))
    training_studies = tuple(sorted({donor_study[donor] for donor in training_donors}))
    reasons: list[str] = []
    if not held_records:
        reasons.append("no_eligible_holdout_records")
    if kind == "within_study_donor" and not set(held_studies).issubset(training_studies):
        reasons.append("no_same_study_training_donor")
    if sum(item.evaluable for item in support) < 2:
        reasons.append("fewer_than_two_evaluable_labels")
    return TransientValidationFold(
        fold_id=fold_id,
        kind=kind,
        training_donor_keys=training_donors,
        held_donor_keys=held_donors,
        training_study_keys=training_studies,
        held_study_keys=held_studies,
        label_support=support,
        evaluable=not reasons,
        abstention_reasons=tuple(reasons),
    )


def build_validation_split_plan(
    reference: AggregateReference,
    *,
    cancellation: CancellationContext | None = None,
) -> ValidationSplitPlan:
    """Build deterministic whole-study and within-study donor holdouts."""

    checkpoint(cancellation)
    if type(reference) is not AggregateReference:
        raise GbmapInputError("reference must be an exact AggregateReference instance")
    usable_records = tuple(
        record for record in reference.records if donor_label_is_eligible(record)
    )
    if not usable_records:
        raise GbmapInputError("validation planning requires eligible donor-label aggregates")
    labels = tuple(sorted({record.modeled_label for record in usable_records}))
    if len(labels) < 2:
        raise GbmapInputError("validation planning requires at least two modeled labels")
    donor_study: dict[str, str] = {}
    for record in usable_records:
        prior = donor_study.setdefault(record.donor_key, record.study_key)
        if prior != record.study_key:
            raise GbmapInputError("one donor cannot cross study boundaries")
    donor_keys = tuple(sorted(donor_study))
    study_keys = tuple(sorted(set(donor_study.values())))
    if len(donor_keys) > MAX_REFERENCE_DONORS:
        raise GbmapInputError("aggregate reference exceeds the donor bound")
    if len(study_keys) > MAX_REFERENCE_STUDIES:
        raise GbmapInputError("aggregate reference exceeds the study bound")

    folds: list[TransientValidationFold] = []
    donor_set = frozenset(donor_keys)
    for index, study in enumerate(study_keys, start=1):
        checkpoint(cancellation)
        held = tuple(donor for donor in donor_keys if donor_study[donor] == study)
        training = tuple(sorted(donor_set - frozenset(held)))
        folds.append(
            _fold(
                fold_id=f"whole-study-{index:04d}",
                kind="whole_study",
                training_donors=training,
                held_donors=held,
                donor_study=donor_study,
                usable_records=usable_records,
                labels=labels,
            )
        )

    donors_by_study = {
        study: tuple(donor for donor in donor_keys if donor_study[donor] == study)
        for study in study_keys
    }
    donor_fold_count = min(
        STRATIFIED_DONOR_FOLD_COUNT,
        max(len(donors) for donors in donors_by_study.values()),
    )
    for group in range(donor_fold_count):
        checkpoint(cancellation)
        held = tuple(
            sorted(
                donor
                for study in study_keys
                for offset, donor in enumerate(donors_by_study[study])
                if offset % donor_fold_count == group
            )
        )
        if not held:
            continue
        training = tuple(sorted(donor_set - frozenset(held)))
        folds.append(
            _fold(
                fold_id=f"within-study-donor-{group + 1:04d}",
                kind="within_study_donor",
                training_donors=training,
                held_donors=held,
                donor_study=donor_study,
                usable_records=usable_records,
                labels=labels,
            )
        )
    if not folds or len(folds) > MAX_VALIDATION_FOLDS:
        raise GbmapInputError("validation split plan exceeds its fixed fold bound")
    transient = tuple(folds)
    receipt = ValidationSplitReceipt(
        source_file_sha256=reference.source_file_sha256,
        source_bytes=reference.source_bytes,
        taxonomy_digest=reference.taxonomy_digest,
        extraction_recipe_digest=reference.extraction_recipe_digest,
        folds=tuple(fold.deidentified_receipt() for fold in transient),
    )
    return ValidationSplitPlan(
        aggregate_content_digest=reference.aggregate_content_digest,
        feature_order_digest=reference.feature_order_digest,
        folds=transient,
        receipt=receipt,
    )


__all__ = [
    "MAX_REFERENCE_DONORS",
    "MAX_REFERENCE_STUDIES",
    "MAX_VALIDATION_FOLDS",
    "STRATIFIED_DONOR_FOLD_COUNT",
    "DeidentifiedValidationFoldReceipt",
    "LabelFoldSupport",
    "TransientValidationFold",
    "ValidationKind",
    "ValidationSplitPlan",
    "ValidationSplitReceipt",
    "build_validation_split_plan",
]
