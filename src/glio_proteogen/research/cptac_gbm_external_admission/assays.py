"""Strict local readers for two explicitly distinct GDC measurement axes.

Every byte/MD5/SHA256 binding is verified before decoding. These readers do not
attribute a file to a participant: the caller-trusted frozen plan binds the
asserted provenance. Only the fixed panel is exposed, transiently and without value
transformations. The receipt contains schema and coverage counts only.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from .contracts import PANEL, HgncReference, IdentityResolutionError, SourceLock
from .identity import normalize_ensembl_gene_id
from .source import read_verified_source

if TYPE_CHECKING:
    from pathlib import Path

MAX_ASSAY_BYTES = 10_000_000
MAX_ASSAY_ROWS = 100_000
MAX_RECORD_CHARACTERS = 4_096
RNA_COLUMNS = (
    "gene_id",
    "gene_name",
    "gene_type",
    "unstranded",
    "stranded_first",
    "stranded_second",
    "tpm_unstranded",
    "fpkm_unstranded",
    "fpkm_uq_unstranded",
)
CNV_COLUMNS = (
    "gene_id",
    "gene_name",
    "chromosome",
    "start",
    "end",
    "copy_number",
    "min_copy_number",
    "max_copy_number",
)
RNA_SUMMARY_LABELS = frozenset(("N_unmapped", "N_multimapping", "N_noFeature", "N_ambiguous"))
RNA_ANNOTATION_COMMENT = "# gene-model: GENCODE v36"
Axis = Literal["star_fpkm_uq_unstranded", "ascat_total_copy_number"]
PanelState = Literal[
    "observed",
    "absent_feature",
    "unresolved_reference",
    "ambiguous_identity",
    "symbol_disagreement",
    "missing_measurement",
]
PANEL_STATES: tuple[PanelState, ...] = (
    "observed",
    "absent_feature",
    "unresolved_reference",
    "ambiguous_identity",
    "symbol_disagreement",
    "missing_measurement",
)
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]


class AssayFormatError(ValueError):
    """A sanitized schema failure; never includes paths, IDs or source rows."""


@dataclass(frozen=True, slots=True)
class AssaySchemaReceipt:
    """Aggregate evidence for one file, without participant or gene values."""

    axis: Axis
    workflow: str
    annotation_release: str | None
    input_bytes: int
    data_rows: int
    gene_rows: int
    summary_rows: int
    versioned_gene_rows: int
    par_y_gene_rows: int
    duplicate_gene_symbol_groups: int
    ambiguous_reference_gene_ids: int
    missing_gene_rows: int
    observed_zero_gene_rows: int
    panel_size: int
    panel_observed_count: int
    panel_absent_count: int
    panel_unresolved_reference_count: int
    panel_ambiguous_identity_count: int
    panel_symbol_disagreement_count: int
    panel_missing_measurement_count: int


@dataclass(frozen=True, slots=True)
class ParsedAssayPanel:
    """Development-only fixed-panel values, never a serializable artifact."""

    receipt: AssaySchemaReceipt
    values: FloatArray = field(repr=False)
    panel_states: tuple[PanelState, ...] = field(repr=False)
    observed: BoolArray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.values) is not np.ndarray
            or self.values.dtype != np.dtype(np.float64)
            or self.values.shape != (len(PANEL),)
            or bool(np.any(np.isinf(self.values)))
            or bool(np.any(self.values[np.isfinite(self.values)] < 0))
        ):
            raise AssayFormatError("transient panel shape or numeric type is invalid")
        if (
            type(self.panel_states) is not tuple
            or len(self.panel_states) != len(PANEL)
            or any(state not in PANEL_STATES for state in self.panel_states)
            or not np.array_equal(
                np.isfinite(self.values), [state == "observed" for state in self.panel_states]
            )
        ):
            raise AssayFormatError("transient panel availability states are invalid")
        counts = Counter(self.panel_states)
        expected_counts = (
            self.receipt.panel_observed_count,
            self.receipt.panel_absent_count,
            self.receipt.panel_unresolved_reference_count,
            self.receipt.panel_ambiguous_identity_count,
            self.receipt.panel_symbol_disagreement_count,
            self.receipt.panel_missing_measurement_count,
        )
        if tuple(counts[state] for state in PANEL_STATES) != expected_counts:
            raise AssayFormatError("transient panel states disagree with aggregate counts")
        immutable = np.frombuffer(np.ascontiguousarray(self.values).tobytes(), dtype=np.float64)
        observed = np.frombuffer(np.isfinite(immutable).tobytes(), dtype=np.bool_)
        object.__setattr__(self, "values", immutable)
        object.__setattr__(self, "observed", observed)

    @property
    def panel_symbols(self) -> tuple[str, ...]:
        return PANEL

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient assay measurements cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient assay measurements cannot be serialized")


@dataclass(frozen=True, slots=True)
class _GeneRow:
    name: str
    value: float | None = field(repr=False)


def _records(payload: bytes, *, rna: bool) -> list[list[str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AssayFormatError("assay must be uncompressed UTF-8 tabular text") from None
    if any((ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127 for char in text):
        raise AssayFormatError("assay text contains an invalid control character")
    lines = text.splitlines()
    if rna and (not lines or lines.pop(0) != RNA_ANNOTATION_COMMENT):
        raise AssayFormatError("RNA assay must declare the exact GENCODE v36 gene model")
    columns = RNA_COLUMNS if rna else CNV_COLUMNS
    if not lines or tuple(lines.pop(0).split("\t")) != columns:
        raise AssayFormatError("assay header does not match the required workflow schema")
    if not 1 <= len(lines) <= MAX_ASSAY_ROWS:
        raise AssayFormatError("assay row count is outside the supported bound")
    records = []
    for line in lines:
        row = line.split("\t")
        if len(line) > MAX_RECORD_CHARACTERS or len(row) != len(columns):
            raise AssayFormatError("assay record width is invalid")
        records.append(row)
    return records


def _unsigned_integer(value: str) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise AssayFormatError("assay integer field is invalid")
    return int(value)


def _nonnegative_finite(value: str) -> float:
    if re.fullmatch(r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is None:
        raise AssayFormatError("assay numeric field is invalid")
    try:
        number = float(value)
    except ValueError:
        raise AssayFormatError("assay numeric field is invalid") from None
    if not math.isfinite(number) or number < 0:
        raise AssayFormatError("assay numeric field is not finite and nonnegative")
    return number


def _identifier(value: str) -> str:
    try:
        return normalize_ensembl_gene_id(value)
    except IdentityResolutionError:
        raise AssayFormatError(
            "assay gene identifier does not match the supported Ensembl grammar"
        ) from None


def _name(value: str) -> None:
    if (
        not value
        or len(value) > 256
        or value != value.strip()
        or any(char.isspace() for char in value)
    ):
        raise AssayFormatError("assay gene annotation field is invalid")


def _rna_value(row: list[str]) -> float:
    _name(row[2])
    for value in row[3:6]:
        _unsigned_integer(value)
    normalized = tuple(_nonnegative_finite(value) for value in row[6:9])
    return normalized[2]


def _cnv_value(row: list[str]) -> float | None:
    _name(row[2])
    start, end = (_unsigned_integer(value) for value in row[3:5])
    if start > end:
        raise AssayFormatError("CNV genomic interval is reversed")
    if all(value == "" for value in row[5:8]):
        return None
    values = tuple(_nonnegative_finite(value) for value in row[5:8])
    if any(not value.is_integer() for value in values):
        raise AssayFormatError("AscatNGS gene copy numbers must be integer-valued")
    copy_number, minimum, maximum = values
    if not minimum <= copy_number <= maximum:
        raise AssayFormatError("CNV minimum, total and maximum values are inconsistent")
    return copy_number


def _panel_gene(
    symbol: str, rows: dict[str, _GeneRow], symbols: Counter[str], hgnc: HgncReference
) -> tuple[PanelState, float | None]:
    identity = hgnc.by_symbol.get(symbol)
    if identity is None or identity.ensembl_gene_id is None:
        return "unresolved_reference", None
    reference_id = identity.ensembl_gene_id
    candidates = hgnc.by_ensembl.get(reference_id, ())
    if (
        identity.symbol != symbol
        or hgnc.by_hgnc.get(identity.hgnc_id) != identity
        or len(candidates) != 1
        or candidates[0] != identity
    ):
        return "ambiguous_identity", None
    row = rows.get(reference_id)
    if row is None:
        return "absent_feature", None
    if row.name != symbol:
        return "symbol_disagreement", None
    if symbols[symbol] != 1:
        return "ambiguous_identity", None
    return ("missing_measurement", None) if row.value is None else ("observed", row.value)


def _panel(
    rows: dict[str, _GeneRow], symbols: Counter[str], hgnc: HgncReference
) -> tuple[FloatArray, tuple[PanelState, ...]]:
    values = np.full(len(PANEL), np.nan, dtype=np.float64)
    states: list[PanelState] = []
    for index, symbol in enumerate(PANEL):
        state, value = _panel_gene(symbol, rows, symbols, hgnc)
        states.append(state)
        if value is not None:
            values[index] = value
    return values, tuple(states)


def _parse(payload: bytes, *, hgnc: HgncReference, rna: bool) -> ParsedAssayPanel:
    records = _records(payload, rna=rna)
    genes: dict[str, _GeneRow] = {}
    originals: set[str] = set()
    symbols: Counter[str] = Counter()
    summaries: set[str] = set()
    versioned = par_y = missing = zeros = ambiguous = 0
    for row in records:
        if rna and row[0] in RNA_SUMMARY_LABELS:
            if row[0] in summaries or any(row[index] for index in (1, 2, 6, 7, 8)):
                raise AssayFormatError(
                    "RNA summary rows have invalid metadata or normalized values"
                )
            for raw_count in row[3:6]:
                _unsigned_integer(raw_count)
            summaries.add(row[0])
            continue
        gene_id = _identifier(row[0])
        if row[0] in originals or gene_id in genes:
            raise AssayFormatError(
                "assay contains duplicate exact or version-stripped gene identifiers"
            )
        _name(row[1])
        value = _rna_value(row) if rna else _cnv_value(row)
        originals.add(row[0])
        genes[gene_id] = _GeneRow(row[1], value)
        symbols[row[1]] += 1
        versioned += row[0] != gene_id
        par_y += gene_id.endswith("_PAR_Y")
        missing += value is None
        zeros += value == 0.0
        ambiguous += len(hgnc.by_ensembl.get(gene_id, ())) > 1
    if not genes or (rna and summaries != RNA_SUMMARY_LABELS):
        raise AssayFormatError("assay must contain gene rows and the required RNA summaries")
    values, states = _panel(genes, symbols, hgnc)
    outcomes = Counter(states)
    receipt = AssaySchemaReceipt(
        axis="star_fpkm_uq_unstranded" if rna else "ascat_total_copy_number",
        workflow="STAR - Counts" if rna else "AscatNGS",
        annotation_release="GENCODE v36" if rna else None,
        input_bytes=len(payload),
        data_rows=len(records),
        gene_rows=len(genes),
        summary_rows=len(summaries),
        versioned_gene_rows=versioned,
        par_y_gene_rows=par_y,
        duplicate_gene_symbol_groups=sum(count > 1 for count in symbols.values()),
        ambiguous_reference_gene_ids=ambiguous,
        missing_gene_rows=missing,
        observed_zero_gene_rows=zeros,
        panel_size=len(PANEL),
        panel_observed_count=outcomes["observed"],
        panel_absent_count=outcomes["absent_feature"],
        panel_unresolved_reference_count=outcomes["unresolved_reference"],
        panel_ambiguous_identity_count=outcomes["ambiguous_identity"],
        panel_symbol_disagreement_count=outcomes["symbol_disagreement"],
        panel_missing_measurement_count=outcomes["missing_measurement"],
    )
    return ParsedAssayPanel(receipt, values, states)


def parse_star_counts_v36(path: Path, *, lock: SourceLock, hgnc: HgncReference) -> ParsedAssayPanel:
    """Read only the explicit unstranded FPKM-UQ axis after exact byte checks."""
    payload = read_verified_source(path, lock, max_bytes=MAX_ASSAY_BYTES)
    return _parse(payload, hgnc=hgnc, rna=True)


def parse_ascat_gene_cnv(path: Path, *, lock: SourceLock, hgnc: HgncReference) -> ParsedAssayPanel:
    """Read integer total copy number; preserve missingness and undeclared release."""
    payload = read_verified_source(path, lock, max_bytes=MAX_ASSAY_BYTES)
    return _parse(payload, hgnc=hgnc, rna=False)
