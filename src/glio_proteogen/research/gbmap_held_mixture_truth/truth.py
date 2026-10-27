"""Private natural donor pools; no solver, calibration, artifact or source I/O.

Truth is reference-native count mass on the original HVG or caller-selected
axis, not genomewide RNA, cell fractions or histologic composition.  Donor
groups may combine specimens.  Captured reference cells need not represent
the tissue population.  An omission never changes the observed pooled counts.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Literal, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
    donor_label_is_eligible,
)
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.splits import (
    ValidationSplitPlan,
    build_validation_split_plan,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .contracts import (
    CallerOwnedMixtureContext,
    HeldMixtureTruthReceipt,
    LabelTruthCoverage,
    MixtureTruthError,
    UnitCoverageLedger,
)

IntVector = npt.NDArray[np.int64]
_INT64_MAX = int(np.iinfo(np.int64).max)


class _Private:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: private empirical count truth>"

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("private empirical truth is immutable")

    def __delattr__(self, _name: str) -> None:
        raise AttributeError("private empirical truth is immutable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("private empirical truth cannot be serialized")

    def __reduce__(self) -> NoReturn:
        raise TypeError("private empirical truth cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private empirical truth cannot be serialized")


def _fractions(masses: tuple[int, ...]) -> tuple[Fraction, ...] | None:
    total = sum(masses)
    return None if total == 0 else tuple(Fraction(value, total) for value in masses)


class EmpiricalMixtureCase(_Private):
    """One transient donor pool, without retaining a donor identifier."""

    __slots__ = ("_known_labels", "_selected_counts", "_selected_mass", "_source_mass")
    _selected_counts: IntVector
    _source_mass: tuple[int, ...]
    _selected_mass: tuple[int, ...]
    _known_labels: tuple[str, ...]

    def __init__(
        self,
        selected_counts: tuple[int, ...],
        source_mass: tuple[int, ...],
        selected_mass: tuple[int, ...],
        known_labels: tuple[str, ...],
    ) -> None:
        if (
            any(
                type(value) is not tuple
                for value in (selected_counts, source_mass, selected_mass, known_labels)
            )
            or not 2 <= len(selected_counts) <= 512
            or len(source_mass) != 20
            or len(selected_mass) != 20
            or any(type(label) is not str for label in known_labels)
            or known_labels != tuple(sorted(set(known_labels)))
            or set(known_labels) - set(PRODUCTION_SOURCE_LABELS)
            or any(
                type(value) is not int or value < 0
                for value in (*selected_counts, *source_mass, *selected_mass)
            )
            or any(value > _INT64_MAX for value in selected_counts)
            or sum(selected_counts) != sum(selected_mass)
            or any(
                selected > source
                for selected, source in zip(selected_mass, source_mass, strict=True)
            )
        ):
            raise MixtureTruthError("invalid private empirical count domain")
        frozen = np.frombuffer(
            np.asarray(selected_counts, dtype=np.int64).tobytes(), dtype=np.int64
        )
        object.__setattr__(self, "_selected_counts", frozen)
        object.__setattr__(self, "_source_mass", source_mass)
        object.__setattr__(self, "_selected_mass", selected_mass)
        object.__setattr__(self, "_known_labels", known_labels)

    @property
    def selected_counts(self) -> IntVector:
        return self._selected_counts

    @property
    def source_label_count_mass(self) -> tuple[int, ...]:
        return self._source_mass

    @property
    def selected_label_count_mass(self) -> tuple[int, ...]:
        return self._selected_mass

    @property
    def source_total_count_mass(self) -> int:
        return sum(self._source_mass)

    @property
    def selected_total_count_mass(self) -> int:
        return sum(self._selected_mass)

    @property
    def source_rna_fractions(self) -> tuple[Fraction, ...] | None:
        return _fractions(self._source_mass)

    @property
    def selected_rna_fractions(self) -> tuple[Fraction, ...] | None:
        return _fractions(self._selected_mass)

    @property
    def state(self) -> Literal["ready", "abstained"]:
        return "ready" if self.selected_total_count_mass > 0 else "abstained"

    @property
    def abstention_reason(
        self,
    ) -> Literal["zero_source_count_depth", "zero_selected_count_depth"] | None:
        if self.source_total_count_mass == 0:
            return "zero_source_count_depth"
        return "zero_selected_count_depth" if self.selected_total_count_mass == 0 else None

    def reclassify(self, omitted_labels: tuple[str, ...] = ()) -> MixtureTruthView:
        if (
            type(omitted_labels) is not tuple
            or any(type(label) is not str for label in omitted_labels)
            or omitted_labels != tuple(sorted(set(omitted_labels)))
            or set(omitted_labels) - set(self._known_labels)
        ):
            raise MixtureTruthError(
                "omission must be a sorted unique subset of caller-known labels"
            )
        remaining = tuple(label for label in self._known_labels if label not in omitted_labels)
        return MixtureTruthView(self, remaining)


class MixtureTruthView(_Private):
    """The same observed counts with a caller-relative omitted-mass target."""

    __slots__ = ("_case", "_remaining")
    _case: EmpiricalMixtureCase
    _remaining: tuple[str, ...]

    def __init__(self, case: EmpiricalMixtureCase, remaining: tuple[str, ...]) -> None:
        if (
            type(case) is not EmpiricalMixtureCase
            or type(remaining) is not tuple
            or any(type(label) is not str for label in remaining)
            or remaining != tuple(sorted(set(remaining)))
            or set(remaining) - set(case._known_labels)
        ):
            raise MixtureTruthError("invalid private omission view")
        object.__setattr__(self, "_case", case)
        object.__setattr__(self, "_remaining", remaining)

    @property
    def selected_counts(self) -> IntVector:
        return self._case.selected_counts

    @property
    def remaining_known_labels(self) -> tuple[str, ...]:
        return self._remaining

    @property
    def source_unknown_count_mass(self) -> int:
        return sum(
            value
            for label, value in zip(
                PRODUCTION_SOURCE_LABELS, self._case.source_label_count_mass, strict=True
            )
            if label not in self._remaining
        )

    @property
    def selected_unknown_count_mass(self) -> int:
        return sum(
            value
            for label, value in zip(
                PRODUCTION_SOURCE_LABELS, self._case.selected_label_count_mass, strict=True
            )
            if label not in self._remaining
        )

    @property
    def source_unknown_fraction(self) -> Fraction | None:
        total = self._case.source_total_count_mass
        return None if total == 0 else Fraction(self.source_unknown_count_mass, total)

    @property
    def selected_unknown_fraction(self) -> Fraction | None:
        total = self._case.selected_total_count_mass
        return None if total == 0 else Fraction(self.selected_unknown_count_mass, total)


class HeldMixtureTruth(_Private):
    __slots__ = ("_cases", "_receipt")
    _cases: tuple[EmpiricalMixtureCase, ...]
    _receipt: HeldMixtureTruthReceipt

    def __init__(
        self, cases: tuple[EmpiricalMixtureCase, ...], receipt: HeldMixtureTruthReceipt
    ) -> None:
        if (
            type(cases) is not tuple
            or any(type(case) is not EmpiricalMixtureCase for case in cases)
            or type(receipt) is not HeldMixtureTruthReceipt
            or len(cases) != receipt.held_unit_count
        ):
            raise MixtureTruthError("invalid private case collection")
        object.__setattr__(self, "_cases", cases)
        object.__setattr__(self, "_receipt", receipt)

    @property
    def cases(self) -> tuple[EmpiricalMixtureCase, ...]:
        return self._cases

    @property
    def receipt(self) -> HeldMixtureTruthReceipt:
        return self._receipt


def _unit_coverage(reference: AggregateReference, plan: ValidationSplitPlan) -> UnitCoverageLedger:
    source_units = {record.donor_key for record in reference.records}
    assigned = {
        unit for fold in plan.folds for unit in (*fold.training_donor_keys, *fold.held_donor_keys)
    }
    whole = Counter(
        unit for fold in plan.folds if fold.kind == "whole_study" for unit in fold.held_donor_keys
    )
    within = Counter(
        unit
        for fold in plan.folds
        if fold.kind == "within_study_donor"
        for unit in fold.held_donor_keys
    )
    if (
        set(whole) != assigned
        or any(value != 1 for value in whole.values())
        or any(value != 1 for value in within.values())
    ):
        raise MixtureTruthError("original fold ownership does not conserve assigned units")
    assigned_rows = sum(record.donor_key in assigned for record in reference.records)
    return UnitCoverageLedger(
        source_unit_count=len(source_units),
        split_assigned_unit_count=len(assigned),
        unassigned_unit_count=len(source_units - assigned),
        whole_study_held_once_unit_count=len(whole),
        within_study_held_once_unit_count=len(within),
        within_study_unheld_assigned_unit_count=len(assigned - set(within)),
        source_raw_record_count=len(reference.records),
        split_assigned_raw_record_count=assigned_rows,
        unassigned_raw_record_count=len(reference.records) - assigned_rows,
    )


def build_held_mixture_truth(  # noqa: PLR0915 - one bounded, explicit pure construction.
    reference: AggregateReference,
    plan: ValidationSplitPlan,
    *,
    fold_id: str,
    context: CallerOwnedMixtureContext,
    cancellation: CancellationContext | None = None,
) -> HeldMixtureTruth:
    """Pool all raw rows in each held donor group on one exact original fold.

    Reference eligibility affects the original split universe only.  Below-floor
    raw rows of assigned held units remain in these empirical mixtures.  Plan
    equality proves ownership, not that caller-known labels were learned.  No
    fitted weights, accuracy, calibration or clinical eligibility is produced.
    """

    if type(reference) is not AggregateReference or type(plan) is not ValidationSplitPlan:
        raise MixtureTruthError("truth requires exact aggregate reference and split plan")
    if type(context) is not CallerOwnedMixtureContext:
        raise MixtureTruthError("truth requires an exact caller-owned context")
    context = CallerOwnedMixtureContext.model_validate(context)
    if type(fold_id) is not str or not fold_id:
        raise MixtureTruthError("truth requires an exact original fold identifier")
    if cancellation is not None and type(cancellation) is not CancellationContext:
        raise MixtureTruthError("truth requires an exact cancellation context")
    checkpoint(cancellation)
    if set(reference.modeled_labels) - set(PRODUCTION_SOURCE_LABELS):
        raise MixtureTruthError("reference contains a nonpublic modeled label")
    fresh = build_validation_split_plan(reference, cancellation=cancellation)
    if plan != fresh:
        raise MixtureTruthError(
            "supplied plan differs from the freshly reconstructed original plan"
        )
    folds = {fold.fold_id: fold for fold in fresh.folds}
    if fold_id not in folds:
        raise MixtureTruthError("requested fold is outside the exact original plan")
    fold = folds[fold_id]
    training_rows, held_rows = fresh.partition_records(reference, fold_id)
    if (
        context.feature_order_digest != reference.feature_order_digest
        or any(index >= len(reference.feature_ids) for index in context.feature_indices)
        or set(context.known_labels) - {record.modeled_label for record in training_rows}
    ):
        raise MixtureTruthError("caller axis or labels do not match this training partition")
    by_unit: dict[str, list[DonorLabelAggregate]] = {}
    for row in held_rows:
        by_unit.setdefault(row.donor_key, []).append(row)
    cases = []
    present = Counter[str]()
    eligible = Counter[str]()
    source_positive = Counter[str]()
    selected_positive = Counter[str]()
    source_zero = Counter[str]()
    label_positions = {label: index for index, label in enumerate(PRODUCTION_SOURCE_LABELS)}
    for unit in fold.held_donor_keys:
        checkpoint(cancellation)
        source_mass = [0] * 20
        selected_mass = [0] * 20
        pooled = [0] * len(context.feature_indices)
        for row in by_unit[unit]:
            checkpoint(cancellation)
            position = label_positions[row.modeled_label]
            values = tuple(int(row.gene_counts[index]) for index in context.feature_indices)
            for index, value in enumerate(values):
                pooled[index] += value
                if pooled[index] > _INT64_MAX:
                    raise MixtureTruthError(
                        "pooled selected coordinate exceeds signed-int64 domain"
                    )
            source_mass[position] += row.total_umis
            selected_mass[position] += sum(values)
            present[row.modeled_label] += 1
            eligible[row.modeled_label] += donor_label_is_eligible(row)
            source_positive[row.modeled_label] += row.total_umis > 0
            selected_positive[row.modeled_label] += sum(values) > 0
            source_zero[row.modeled_label] += row.total_umis == 0
        cases.append(
            EmpiricalMixtureCase(
                tuple(pooled), tuple(source_mass), tuple(selected_mass), context.known_labels
            )
        )
    receipt = HeldMixtureTruthReceipt(
        fold_id=fold.fold_id,
        kind=fold.kind,
        fold_evaluable=fold.evaluable,
        source_feature_count=len(reference.feature_ids),
        selected_feature_count=len(context.feature_indices),
        known_label_count=len(context.known_labels),
        held_unit_count=len(cases),
        held_raw_record_count=len(held_rows),
        held_reference_eligible_record_count=sum(donor_label_is_eligible(row) for row in held_rows),
        ready_case_count=sum(case.state == "ready" for case in cases),
        zero_source_depth_case_count=sum(
            case.abstention_reason == "zero_source_count_depth" for case in cases
        ),
        zero_selected_depth_case_count=sum(
            case.abstention_reason == "zero_selected_count_depth" for case in cases
        ),
        labels=tuple(
            LabelTruthCoverage(
                modeled_label=label,
                known_in_context=label in context.known_labels,
                held_record_count=present[label],
                held_reference_eligible_record_count=eligible[label],
                held_source_positive_unit_count=source_positive[label],
                held_selected_positive_unit_count=selected_positive[label],
                held_source_positive_selected_zero_unit_count=source_positive[label]
                - selected_positive[label],
                held_source_zero_unit_count=source_zero[label],
                held_missing_record_unit_count=len(cases) - present[label],
            )
            for label in PRODUCTION_SOURCE_LABELS
        ),
        unit_coverage=_unit_coverage(reference, fresh),
    )
    return HeldMixtureTruth(tuple(cases), receipt)


__all__ = [
    "EmpiricalMixtureCase",
    "HeldMixtureTruth",
    "MixtureTruthView",
    "build_held_mixture_truth",
]
