"""Gene-wide count capacity and variation diagnostics, without fitting or selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest

from .contracts import (
    CNV_AXIS,
    PROFILE_ID,
    PROTEIN_AXIS,
    RNA_AXIS,
    STATES,
    FeatureMatrix,
    FeatureSpaceError,
)

if TYPE_CHECKING:
    from glio_proteogen.research.cptac_gbm_external_admission.contracts import GeneIdentity

PATTERNS: Final = tuple(f"{value:03b}" for value in range(8))
ASSAY_ORDER: Final = (CNV_AXIS, RNA_AXIS, PROTEIN_AXIS)
FoldArray = npt.NDArray[np.int8]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class GeneCoverage:
    identity: GeneIdentity
    candidate_specimens: int
    protein_feature_present: bool
    observed_cnv: int
    observed_rna: int
    observed_protein: int
    rna_protein_complete: int
    cnv_protein_complete: int
    joint_complete: int
    zero_cnv: int
    zero_rna: int
    zero_protein: int
    pattern_counts_cnv_rna_protein: tuple[int, ...]
    cnv_state_counts: tuple[int, ...]
    rna_state_counts: tuple[int, ...]
    protein_state_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CountSupportCapacity:
    joint_complete: int
    fold_joint_counts: tuple[int, ...]
    minimum_validation_joint: int
    minimum_outer_training_joint: int
    minimum_inner_training_joint: int
    all_five_fold_count_support_possible: bool


@dataclass(frozen=True, slots=True)
class TrainingVariationDiagnostics:
    training_contexts: int
    cnv_contexts_with_variation: int
    rna_contexts_with_variation: int
    protein_contexts_with_variation: int


@dataclass(frozen=True, slots=True)
class SourceGeneFeature:
    coverage: GeneCoverage
    count_capacity: CountSupportCapacity
    training_variation: TrainingVariationDiagnostics


@dataclass(frozen=True, slots=True)
class SourceFeatureCatalog:
    profile_id: str
    feature_axis_digest: str
    candidate_digest: str
    source_case_count: int
    source_fold_assignment_digest: str
    genes: tuple[SourceGeneFeature, ...]
    count_supported_genes: int
    source_count_candidate_hgnc_digest: str
    measurement_matrix_bytes: int
    availability_matrix_bytes: int
    state_order: tuple[str, ...] = STATES
    pattern_order_cnv_rna_protein: tuple[str, ...] = PATTERNS
    assay_order: tuple[str, ...] = ASSAY_ORDER
    variation_is_a_gate: bool = False
    fit_eligibility_established: bool = False
    numerical_rank_or_convergence_established: bool = False
    model_fits_performed: bool = False
    association_tested: bool = False
    values_imputed: bool = False
    values_transformed: bool = False
    selection_uses_external_values: bool = False

    @property
    def digest(self) -> str:
        return sha256_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class ExternalFeatureCoverage:
    profile_id: str
    source_catalog_digest: str
    feature_axis_digest: str
    candidate_digest: str
    external_case_count: int
    genes: tuple[GeneCoverage, ...]
    external_joint_minimum: int
    external_count_sufficient_genes: int
    source_and_external_count_sufficient_genes: int
    state_order: tuple[str, ...] = STATES
    pattern_order_cnv_rna_protein: tuple[str, ...] = PATTERNS
    assay_order: tuple[str, ...] = ASSAY_ORDER
    source_axis_changed: bool = False
    fit_or_transfer_eligibility_established: bool = False
    model_fits_performed: bool = False
    selection_uses_external_values: bool = False
    aligned_external_validation: bool = False

    @property
    def digest(self) -> str:
        return sha256_digest(asdict(self))


def _coverage(matrix: FeatureMatrix) -> tuple[GeneCoverage, ...]:
    cnv, rna, protein = (
        values == 0 for values in (matrix.cnv_states, matrix.rna_states, matrix.protein_states)
    )
    codes = cnv.astype(np.uint8) * 4 + rna.astype(np.uint8) * 2 + protein.astype(np.uint8)
    pattern_counts = tuple(np.sum(codes == pattern, axis=1) for pattern in range(8))
    states = tuple(
        tuple(np.sum(values == code, axis=1) for code in range(len(STATES)))
        for values in (matrix.cnv_states, matrix.rna_states, matrix.protein_states)
    )
    paired_rna, paired_cnv = np.sum(rna & protein, axis=1), np.sum(cnv & protein, axis=1)
    zero_counts = tuple(
        np.sum(values == 0, axis=1) for values in (matrix.cnv, matrix.rna, matrix.protein)
    )
    return tuple(
        GeneCoverage(
            identity=identity,
            candidate_specimens=matrix.case_count,
            protein_feature_present=not bool(np.all(matrix.protein_states[index] == 1)),
            observed_cnv=int(states[0][0][index]),
            observed_rna=int(states[1][0][index]),
            observed_protein=int(states[2][0][index]),
            rna_protein_complete=int(paired_rna[index]),
            cnv_protein_complete=int(paired_cnv[index]),
            joint_complete=int(pattern_counts[7][index]),
            zero_cnv=int(zero_counts[0][index]),
            zero_rna=int(zero_counts[1][index]),
            zero_protein=int(zero_counts[2][index]),
            pattern_counts_cnv_rna_protein=tuple(int(values[index]) for values in pattern_counts),
            cnv_state_counts=tuple(int(values[index]) for values in states[0]),
            rna_state_counts=tuple(int(values[index]) for values in states[1]),
            protein_state_counts=tuple(int(values[index]) for values in states[2]),
        )
        for index, identity in enumerate(matrix.axis.identities)
    )


def _source_folds(folds: FoldArray, cases: int) -> FoldArray:
    if (
        type(folds) is not np.ndarray
        or folds.dtype != np.dtype(np.int8)
        or folds.shape != (cases,)
        or not 60 <= cases <= 1_000
        or {int(value) for value in np.unique(folds)} != set(range(5))
    ):
        raise FeatureSpaceError("source catalog requires all five original bounded patient folds")
    return folds


def _capacity(complete: BoolArray, folds: FoldArray) -> CountSupportCapacity:
    total = int(np.sum(complete))
    counts = tuple(int(np.sum(complete & (folds == fold))) for fold in range(5))
    outer = min(total - count for count in counts)
    inner = min(total - counts[a] - counts[b] for a in range(5) for b in range(5) if a != b)
    validation = min(counts)
    return CountSupportCapacity(
        total,
        counts,
        validation,
        outer,
        inner,
        total >= 60 and validation >= 3 and outer >= 48 and inner >= 32,
    )


def _variation(
    arrays: tuple[npt.NDArray[np.float64], ...],
    complete: BoolArray,
    contexts: tuple[BoolArray, ...],
) -> TrainingVariationDiagnostics:
    counts = []
    for array in arrays:
        varied = 0
        for context in contexts:
            values = array[complete & context]
            varied += len(values) >= 2 and bool(np.any(values != values[0]))
        counts.append(varied)
    return TrainingVariationDiagnostics(len(contexts), *counts)


def build_source_catalog(matrix: FeatureMatrix, folds: FoldArray) -> SourceFeatureCatalog:
    """Expose source counts and non-gating variation; do not fit or rank genes."""
    if not isinstance(matrix, FeatureMatrix):
        raise FeatureSpaceError("source catalog requires a validated transient feature matrix")
    folds = _source_folds(folds, matrix.case_count)
    contexts = (
        np.ones(matrix.case_count, dtype=np.bool_),
        *(folds != fold for fold in range(5)),
        *((folds != a) & (folds != b) for a in range(5) for b in range(5) if a != b),
    )
    coverages = _coverage(matrix)
    features = []
    for index, coverage in enumerate(coverages):
        complete = (
            (matrix.cnv_states[index] == 0)
            & (matrix.rna_states[index] == 0)
            & (matrix.protein_states[index] == 0)
        )
        features.append(
            SourceGeneFeature(
                coverage,
                _capacity(complete, folds),
                _variation(
                    (matrix.cnv[index], matrix.rna[index], matrix.protein[index]),
                    complete,
                    contexts,
                ),
            )
        )
    candidates = tuple(
        feature.coverage.identity.hgnc_id
        for feature in features
        if feature.count_capacity.all_five_fold_count_support_possible
    )
    return SourceFeatureCatalog(
        PROFILE_ID,
        matrix.axis.digest,
        matrix.candidate_digest,
        matrix.case_count,
        sha256_digest(tuple(int(value) for value in folds)),
        tuple(features),
        len(candidates),
        sha256_digest(candidates),
        matrix.measurement_bytes,
        sum(
            values.nbytes
            for values in (matrix.cnv_states, matrix.rna_states, matrix.protein_states)
        ),
    )


def project_external_coverage(
    source: SourceFeatureCatalog, matrix: FeatureMatrix
) -> ExternalFeatureCoverage:
    """Apply an unchanged source axis; external coverage never selects source genes."""
    if not isinstance(source, SourceFeatureCatalog) or not isinstance(matrix, FeatureMatrix):
        raise FeatureSpaceError(
            "external projection requires a frozen source catalog and validated matrix"
        )
    if (
        source.profile_id != PROFILE_ID
        or source.feature_axis_digest != matrix.axis.digest
        or tuple(feature.coverage.identity for feature in source.genes) != matrix.axis.identities
    ):
        raise FeatureSpaceError("external projection cannot change the frozen source feature axis")
    coverages = _coverage(matrix)
    return ExternalFeatureCoverage(
        PROFILE_ID,
        source.digest,
        matrix.axis.digest,
        matrix.candidate_digest,
        matrix.case_count,
        coverages,
        48,
        sum(coverage.joint_complete >= 48 for coverage in coverages),
        sum(
            coverage.joint_complete >= 48
            and feature.count_capacity.all_five_fold_count_support_possible
            for feature, coverage in zip(source.genes, coverages, strict=True)
        ),
    )
