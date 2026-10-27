"""Source-defined exact gene axes and private, aligned cohort assembly.

Only the receipt dataclasses are intended for serialization. The source gene
universe does not consult external measurements, associations, or outcomes.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, NoReturn, SupportsIndex

import numpy as np

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    HgncReference,
    SourceLock,
)
from glio_proteogen.research.cptac_gbm_external_admission.discovery import (
    PROFILE_ID as DISCOVERY_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.discovery import (
    DiscoveryProteinAdmission,
)
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AssayInputBinding,
    CandidateBinding,
    ExternalAdmissionPlan,
    ExternalAdmissionReceipt,
)
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    PROFILE_ID as CONFIRMATORY_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    ConfirmatoryProteinAdmission,
    ProteinAdmissionReceipt,
)

from . import assays
from .contracts import (
    CNV_AXIS,
    MAX_CELLS,
    MAX_FEATURES,
    PROFILE_ID,
    RNA_AXIS,
    STATES,
    AssayAxis,
    FeatureAxis,
    FeatureMatrix,
    FeatureSpaceError,
    FloatArray,
    ProjectedAssay,
    ProjectionReceipt,
    StateArray,
    require_digest,
)

_UUID: Final = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_SCHEMA_FIELDS: Final = (
    "data_rows",
    "gene_rows",
    "summary_rows",
    "versioned_gene_rows",
    "par_y_gene_rows",
    "duplicate_gene_symbol_groups",
    "ambiguous_reference_gene_ids",
    "missing_gene_rows",
    "observed_zero_gene_rows",
)
ProteinAdmission = DiscoveryProteinAdmission | ConfirmatoryProteinAdmission


@dataclass(frozen=True, slots=True)
class SourceUniverseReceipt:
    profile_id: str
    source_protein_rows: int
    approved_source_protein_genes: int
    unresolved_source_protein_rows: int
    literature_anchor_only_count: int
    feature_count: int
    feature_axis_digest: str
    source_protein_receipt_digest: str
    selection_uses_external_values: bool = False
    selection_uses_association_outcomes: bool = False


@dataclass(frozen=True, slots=True)
class SourceUniverse:
    axis: FeatureAxis = field(repr=False)
    receipt: SourceUniverseReceipt


@dataclass(frozen=True, slots=True)
class SchemaHistogramBin:
    value: int
    files: int


@dataclass(frozen=True, slots=True)
class SchemaHistogram:
    field: str
    bins: tuple[SchemaHistogramBin, ...]


@dataclass(frozen=True, slots=True)
class AxisSchemaSummary:
    axis: AssayAxis
    workflow: str
    annotation_release: str | None
    verified_files: int
    verified_input_bytes: int
    feature_count: int
    state_totals: tuple[int, ...]
    histograms: tuple[SchemaHistogram, ...]


@dataclass(frozen=True, slots=True)
class CohortBuildReceipt:
    profile_id: str
    feature_axis_digest: str
    candidate_digest: str
    candidate_specimens: int
    verified_rna_files: int
    verified_cnv_files: int
    source_protein_receipt: ProteinAdmissionReceipt
    protein_rows_outside_source_axis: int
    schema_summaries: tuple[AxisSchemaSummary, ...]


class CohortAdmission:
    """Immutable transient wrapper; dataclass conversion is receipt-only.

    A dataclass wrapper would allow ``asdict`` to recursively copy all private
    matrix arrays despite their pickle guards. This wrapper deliberately is not
    a dataclass, while its aggregate receipt remains one.
    """

    __slots__ = ("matrix", "receipt")
    matrix: FeatureMatrix
    receipt: CohortBuildReceipt

    def __init__(self, matrix: FeatureMatrix, receipt: CohortBuildReceipt) -> None:
        if not isinstance(matrix, FeatureMatrix) or not isinstance(receipt, CohortBuildReceipt):
            raise FeatureSpaceError(
                "cohort admission requires a private matrix and aggregate receipt"
            )
        object.__setattr__(self, "matrix", matrix)
        object.__setattr__(self, "receipt", receipt)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("transient cohort admission is immutable")

    def __repr__(self) -> str:
        return f"CohortAdmission(receipt={self.receipt!r})"

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient cohort admission cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient cohort admission cannot be serialized")


def _reference_identity(identity: GeneIdentity, hgnc: HgncReference) -> None:
    if (
        not isinstance(identity, GeneIdentity)
        or hgnc.by_hgnc.get(identity.hgnc_id) != identity
        or hgnc.by_symbol.get(identity.symbol) != identity
    ):
        raise FeatureSpaceError("protein or axis identities disagree with the exact HGNC reference")


def _validate_protein(protein: ProteinAdmission, hgnc: HgncReference) -> dict[str, int]:
    if not isinstance(hgnc, HgncReference) or not isinstance(
        protein, (DiscoveryProteinAdmission, ConfirmatoryProteinAdmission)
    ):
        raise FeatureSpaceError("an admitted protein source and exact HGNC reference are required")
    count = 72 if isinstance(protein, DiscoveryProteinAdmission) else 56
    profile = DISCOVERY_PROFILE_ID if count == 72 else CONFIRMATORY_PROFILE_ID
    receipt = protein.receipt
    require_digest(protein.candidate_digest)
    if (
        not isinstance(receipt, ProteinAdmissionReceipt)
        or receipt.profile_id != profile
        or receipt.candidate_count != count
        or receipt.candidate_digest != protein.candidate_digest
        or type(protein.values) is not np.ndarray
        or protein.values.dtype != np.dtype(np.float64)
        or protein.values.ndim != 2
        or protein.values.shape[1] != count
        or type(protein.identities) is not tuple
        or not 1 <= len(protein.identities) <= MAX_FEATURES
        or len(protein.identities) != protein.values.shape[0]
        or receipt.biological_feature_rows != len(protein.identities)
        or bool(np.any(np.isinf(protein.values)))
    ):
        raise FeatureSpaceError("protein admission dimensions or source receipt disagree")
    index: dict[str, int] = {}
    symbols: set[str] = set()
    for row, identity in enumerate(protein.identities):
        if identity is None:
            continue
        _reference_identity(identity, hgnc)
        if identity.hgnc_id in index or identity.symbol in symbols:
            raise FeatureSpaceError("protein rows do not have unique approved identities")
        index[identity.hgnc_id] = row
        symbols.add(identity.symbol)
    if (
        receipt.identified_feature_rows != len(index)
        or receipt.unavailable_identity_rows != len(protein.identities) - len(index)
        or receipt.finite_unshared_cells != int(np.count_nonzero(np.isfinite(protein.values)))
        or receipt.missing_unshared_cells != int(np.count_nonzero(np.isnan(protein.values)))
        or receipt.finite_zero_unshared_cells != int(np.count_nonzero(protein.values == 0))
    ):
        raise FeatureSpaceError("protein admission aggregate counts disagree with its measurements")
    return index


def derive_source_axis(
    *, protein: DiscoveryProteinAdmission, hgnc: HgncReference
) -> SourceUniverse:
    """Freeze approved source-protein genes and all predeclared literature anchors."""
    if not isinstance(protein, DiscoveryProteinAdmission):
        raise FeatureSpaceError("only the discovery protein admission may define the source axis")
    source = _validate_protein(protein, hgnc)
    identities = {key: hgnc.by_hgnc[key] for key in source}
    for symbol in PANEL:
        identity = hgnc.by_symbol.get(symbol)
        if identity is None:
            raise FeatureSpaceError("the exact HGNC reference lacks a required literature anchor")
        _reference_identity(identity, hgnc)
        identities[identity.hgnc_id] = identity
    axis = FeatureAxis(tuple(identities[key] for key in sorted(identities)))
    return SourceUniverse(
        axis,
        SourceUniverseReceipt(
            profile_id=PROFILE_ID,
            source_protein_rows=len(protein.identities),
            approved_source_protein_genes=len(source),
            unresolved_source_protein_rows=len(protein.identities) - len(source),
            literature_anchor_only_count=len(identities) - len(source),
            feature_count=len(axis.identities),
            feature_axis_digest=axis.digest,
            source_protein_receipt_digest=sha256_digest(asdict(protein.receipt)),
        ),
    )


def _valid_label(value: str) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 256
        and value.strip() == value
        and value != "POOL"
        and not value.startswith("Withdrawn:")
        and all(character.isprintable() for character in value)
    )


def _validate_plan(plan: ExternalAdmissionPlan, *, count: int) -> None:
    if not isinstance(plan, ExternalAdmissionPlan) or not isinstance(
        plan.receipt, ExternalAdmissionReceipt
    ):
        raise FeatureSpaceError("an admitted exact specimen and file plan is required")
    receipt = plan.receipt
    if (
        len(plan.candidates) != count
        or receipt.candidate_count != count
        or receipt.rna_file_count != count
        or receipt.cnv_file_count != count
        or receipt.paired_file_count != 2 * count
        or len(plan.files) != 2 * count
    ):
        raise FeatureSpaceError("specimen and file plan dimensions disagree")
    seen: tuple[set[str], ...] = tuple(set() for _ in range(5))
    references: set[str] = set()
    for candidate in plan.candidates:
        if not isinstance(candidate, CandidateBinding):
            raise FeatureSpaceError("specimen plan contains an invalid binding")
        labels = (
            candidate.case_submitter_id,
            candidate.sample_submitter_id,
            candidate.gdc_sample_uuid,
            candidate.protein_aliquot_submitter_id,
            candidate.protein_aliquot_uuid,
        )
        if any(not _valid_label(value) for value in labels) or any(
            _UUID.fullmatch(value) is None
            for value in (candidate.gdc_sample_uuid, candidate.protein_aliquot_uuid)
        ):
            raise FeatureSpaceError("specimen plan contains an invalid exact identifier")
        for values, value in zip(seen, labels, strict=True):
            if value in values:
                raise FeatureSpaceError("specimen plan repeats a participant or specimen binding")
            values.add(value)
        for file_id, workflow in (
            (candidate.rna_file_id, "STAR - Counts"),
            (candidate.cnv_file_id, "AscatNGS"),
        ):
            if type(file_id) is not str or _UUID.fullmatch(file_id) is None:
                raise FeatureSpaceError("assay file bindings contain an invalid exact identifier")
            binding = plan.files.get(file_id)
            if (
                file_id in references
                or not isinstance(binding, AssayInputBinding)
                or not isinstance(binding.lock, SourceLock)
                or binding.relative_path != file_id + ".bin"
                or binding.workflow != workflow
            ):
                raise FeatureSpaceError("assay file bindings are not exact unique workflow matches")
            references.add(file_id)


def _project_protein(
    axis: FeatureAxis, protein: ProteinAdmission, index: dict[str, int]
) -> tuple[FloatArray, StateArray]:
    values = np.full((len(axis.identities), protein.values.shape[1]), np.nan, dtype=np.float64)
    states = np.full(values.shape, 1, dtype=np.uint8)
    for row, identity in enumerate(axis.identities):
        source_row = index.get(identity.hgnc_id)
        if source_row is not None:
            values[row] = protein.values[source_row]
            states[row] = np.where(np.isfinite(values[row]), 0, 5)
    return values, states


def _check_projection(
    projected: ProjectedAssay,
    *,
    feature_axis_digest: str,
    feature_count: int,
    assay_axis: AssayAxis,
    binding: AssayInputBinding,
) -> ProjectionReceipt:
    if not isinstance(projected, ProjectedAssay):
        raise FeatureSpaceError("assay reader did not return a validated projection")
    receipt = projected.receipt
    if (
        receipt.axis != assay_axis
        or receipt.workflow != binding.workflow
        or receipt.feature_axis_digest != feature_axis_digest
        or receipt.feature_count != feature_count
        or receipt.input_bytes != binding.lock.bytes
    ):
        raise FeatureSpaceError("assay projection disagrees with its frozen gene or source binding")
    return receipt


def _schema_summary(
    axis: AssayAxis, receipts: list[ProjectionReceipt], *, feature_count: int
) -> AxisSchemaSummary:
    return AxisSchemaSummary(
        axis=axis,
        workflow="STAR - Counts" if axis == RNA_AXIS else "AscatNGS",
        annotation_release="GENCODE v36" if axis == RNA_AXIS else None,
        verified_files=len(receipts),
        verified_input_bytes=sum(receipt.input_bytes for receipt in receipts),
        feature_count=feature_count,
        state_totals=tuple(
            sum(receipt.state_counts[code] for receipt in receipts) for code in range(len(STATES))
        ),
        histograms=tuple(
            SchemaHistogram(
                field=name,
                bins=tuple(
                    SchemaHistogramBin(value=value, files=files)
                    for value, files in sorted(
                        Counter(int(getattr(receipt, name)) for receipt in receipts).items()
                    )
                ),
            )
            for name in _SCHEMA_FIELDS
        ),
    )


def build_cohort_matrix(
    *,
    axis: FeatureAxis,
    protein: ProteinAdmission,
    plan: ExternalAdmissionPlan,
    files_manifest_path: Path,
    hgnc: HgncReference,
) -> CohortAdmission:
    """Read each locked assay once and assemble only the already-frozen source axis.

    A manifest path locates files already bound by the admitted plan; this
    function does not reopen or reinterpret the manifest. Upstream plan loaders
    bind its bytes. Protein extras count approved rows outside this source axis.
    """
    index = _validate_protein(protein, hgnc)
    if not isinstance(axis, FeatureAxis) or not isinstance(files_manifest_path, Path):
        raise FeatureSpaceError("cohort assembly requires an admitted axis and manifest location")
    for identity in axis.identities:
        _reference_identity(identity, hgnc)
    count = protein.values.shape[1]
    _validate_plan(plan, count=count)
    candidate_digest = sha256_digest(plan.protein_aliquots)
    if candidate_digest != protein.candidate_digest:
        raise FeatureSpaceError("protein and assay specimen ordering digests disagree")
    if len(axis.identities) * count > MAX_CELLS:
        raise FeatureSpaceError("cohort assembly exceeds the bounded feature matrix size")
    shape = (len(axis.identities), count)
    feature_axis_digest = axis.digest
    rna = np.empty(shape, dtype=np.float64)
    cnv = np.empty(shape, dtype=np.float64)
    rna_states = np.empty(shape, dtype=np.uint8)
    cnv_states = np.empty(shape, dtype=np.uint8)
    rna_receipts: list[ProjectionReceipt] = []
    cnv_receipts: list[ProjectionReceipt] = []
    for column, candidate in enumerate(plan.candidates):
        rna_binding = plan.files[candidate.rna_file_id]
        projected_rna = assays.parse_star_counts_v36(
            files_manifest_path.parent / rna_binding.relative_path,
            lock=rna_binding.lock,
            hgnc=hgnc,
            axis=axis,
        )
        rna_receipts.append(
            _check_projection(
                projected_rna,
                feature_axis_digest=feature_axis_digest,
                feature_count=shape[0],
                assay_axis=RNA_AXIS,
                binding=rna_binding,
            )
        )
        rna[:, column], rna_states[:, column] = projected_rna.values, projected_rna.states
        cnv_binding = plan.files[candidate.cnv_file_id]
        projected_cnv = assays.parse_ascat_gene_cnv(
            files_manifest_path.parent / cnv_binding.relative_path,
            lock=cnv_binding.lock,
            hgnc=hgnc,
            axis=axis,
        )
        cnv_receipts.append(
            _check_projection(
                projected_cnv,
                feature_axis_digest=feature_axis_digest,
                feature_count=shape[0],
                assay_axis=CNV_AXIS,
                binding=cnv_binding,
            )
        )
        cnv[:, column], cnv_states[:, column] = projected_cnv.values, projected_cnv.states
    protein_values, protein_states = _project_protein(axis, protein, index)
    matrix = FeatureMatrix(
        axis, candidate_digest, cnv, rna, protein_values, cnv_states, rna_states, protein_states
    )
    return CohortAdmission(
        matrix,
        CohortBuildReceipt(
            profile_id=PROFILE_ID,
            feature_axis_digest=feature_axis_digest,
            candidate_digest=candidate_digest,
            candidate_specimens=count,
            verified_rna_files=len(rna_receipts),
            verified_cnv_files=len(cnv_receipts),
            source_protein_receipt=protein.receipt,
            protein_rows_outside_source_axis=len(set(index) - set(axis.hgnc_ids)),
            schema_summaries=(
                _schema_summary(CNV_AXIS, cnv_receipts, feature_count=len(axis.identities)),
                _schema_summary(RNA_AXIS, rna_receipts, feature_count=len(axis.identities)),
            ),
        ),
    )


__all__ = [
    "AxisSchemaSummary",
    "CohortAdmission",
    "CohortBuildReceipt",
    "SchemaHistogram",
    "SchemaHistogramBin",
    "SourceUniverse",
    "SourceUniverseReceipt",
    "build_cohort_matrix",
    "derive_source_axis",
]
