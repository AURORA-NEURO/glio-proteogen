"""Exact, local admission of the confirmatory CDAP protein source.

This decoder exposes one explicitly chosen measurement, Unshared Log Ratio.
It performs no modelling, imputation, cohort harmonization or scale conversion.
Only the aggregate receipt is intended for serialization.
"""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest

from .contracts import PANEL, GeneIdentity, HgncReference, SourceLock
from .identity import HGNC_LOCK, read_locked_hgnc
from .source import read_verified_source

PROFILE_ID: Final = "cptac-gbm-confirmatory-protein-admission/1.0.0"
PROTEIN_LOCK: Final = SourceLock(
    bytes=63_339_871,
    md5="76b3317fdf6e54113ac91530f96a491c",
    sha256="1383ba1eecd3c50c4c38008b4f10c4661dac65ea95d33ebac41ff5a432a79a19",
)
SAMPLE_MAP_LOCK: Final = SourceLock(
    bytes=4_649,
    md5="c2c925086abe1ca8dd8fe826ff12ad0a",
    sha256="72c3effc3d281e0c94ae12256e457afb30aa9836a34db19195c8dacff7b5f40b",
)
PRIMARY_MEASURE: Final = "Unshared Log Ratio"
_ALL_PEPTIDE_MEASURE: Final = "Log Ratio"
_MEASURES: Final = (PRIMARY_MEASURE, _ALL_PEPTIDE_MEASURE)
_CHANNELS: Final = (
    "126C",
    "127N",
    "127C",
    "128N",
    "128C",
    "129N",
    "129C",
    "130N",
    "130C",
    "131N",
    "131C",
)
_RATIOS: Final = ",".join(f"{channel}/126C" for channel in _CHANNELS[1:])
_SAMPLE_HEADER: Final = ("FileNameRegEx", "AnalyticalSample", *_CHANNELS, "LabelReagent", "Ratios")
_ANNOTATIONS: Final = ("NCBIGeneID", "Authority", "Description", "Organism", "Chromosome", "Locus")
_AGGREGATES: Final = ("Mean", "Median", "StdDev")
FloatArray = npt.NDArray[np.float64]


class ProteinAdmissionError(ValueError):
    """Sanitized structural or identity rejection without source identifiers."""


@dataclass(frozen=True, slots=True)
class ProteinPanelCoverage:
    gene: str
    source_rows: int
    unshared_finite: int | None
    unshared_missing: int | None
    all_peptide_finite: int | None


@dataclass(frozen=True, slots=True)
class ProteinAdmissionReceipt:
    profile_id: str
    protein_sha256: str
    sample_map_sha256: str
    hgnc_sha256: str
    candidate_digest: str
    candidate_count: int
    biological_feature_rows: int
    identified_feature_rows: int
    unavailable_identity_rows: int
    source_aggregate_rows_excluded: int
    withdrawn_aliquots_excluded: int
    pool_targets_excluded: int
    finite_unshared_cells: int
    missing_unshared_cells: int
    finite_zero_unshared_cells: int
    finite_all_peptide_cells: int
    missing_all_peptide_cells: int
    panel_coverage: tuple[ProteinPanelCoverage, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConfirmatoryProteinAdmission:
    candidate_digest: str
    values: FloatArray = field(repr=False)
    identities: tuple[GeneIdentity | None, ...] = field(repr=False)
    receipt: ProteinAdmissionReceipt

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient protein admission cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient protein admission cannot be serialized")


@dataclass(frozen=True, slots=True)
class _ProteinShape:
    """Private source inventory oracle; production has no configurable bypass."""

    candidate_count: int = 56
    active_aliquots: int = 147
    withdrawn_aliquots: int = 2
    pool_targets: int = 1
    sample_map_plexes: int = 15
    biological_rows: int = 11_159

    @property
    def measurement_targets(self) -> int:
        return self.active_aliquots + self.withdrawn_aliquots + self.pool_targets


_SOURCE_SHAPE: Final = _ProteinShape()


@dataclass(frozen=True, slots=True)
class _MapInventory:
    active: frozenset[str] = field(repr=False)
    withdrawn: frozenset[str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _DecodedProtein:
    values: FloatArray = field(repr=False)
    identities: tuple[GeneIdentity | None, ...] = field(repr=False)
    finite_unshared: int
    missing_unshared: int
    zero_unshared: int
    finite_all_peptide: int
    missing_all_peptide: int
    panel_coverage: tuple[ProteinPanelCoverage, ...]

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient protein contents cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient protein contents cannot be serialized")


def _validate_candidates(candidate_aliquots: tuple[str, ...], shape: _ProteinShape) -> None:
    if type(candidate_aliquots) is not tuple or len(candidate_aliquots) != shape.candidate_count:
        raise ProteinAdmissionError("protein candidate inventory is not admitted")
    if any(
        type(label) is not str
        or not label
        or len(label) > 256
        or label == "POOL"
        or label.startswith("Withdrawn:")
        or any(character.isspace() or ord(character) < 32 for character in label)
        for label in candidate_aliquots
    ):
        raise ProteinAdmissionError("protein candidate labels are not admitted")
    if len(set(candidate_aliquots)) != len(candidate_aliquots):
        raise ProteinAdmissionError("protein candidate labels are not unique")


def _tsv(payload: bytes) -> Iterator[list[str]]:
    try:
        return csv.reader(io.StringIO(payload.decode("utf-8-sig")), delimiter="\t", strict=True)
    except UnicodeError:
        raise ProteinAdmissionError("protein source is not admitted UTF-8 TSV") from None


def _sample_inventory(
    payload: bytes, candidate_aliquots: tuple[str, ...], shape: _ProteinShape
) -> _MapInventory:
    reader = _tsv(payload)
    if tuple(next(reader, ())) != _SAMPLE_HEADER:
        raise ProteinAdmissionError("protein sample-map schema is not admitted")
    occurrences: Counter[str] = Counter()
    withdrawn: set[str] = set()
    analytical: set[str] = set()
    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > shape.sample_map_plexes or len(row) != len(_SAMPLE_HEADER):
            raise ProteinAdmissionError("protein sample-map inventory is not admitted")
        if not row[0] or not row[1] or row[1] in analytical or not row[-2]:
            raise ProteinAdmissionError("protein sample-map analytical units are not unique")
        analytical.add(row[1])
        if row[-1] != _RATIOS or row[2] != "POOL":
            raise ProteinAdmissionError("protein sample-map reference ratios are not admitted")
        for label in row[3:13]:
            if not label:
                raise ProteinAdmissionError("protein sample-map assignment is empty")
            if label == "POOL":
                continue
            if label.startswith("Withdrawn:"):
                if label in withdrawn:
                    raise ProteinAdmissionError("protein withdrawn assignment is duplicated")
                withdrawn.add(label)
            else:
                occurrences[label] += 1
    if (
        row_count != shape.sample_map_plexes
        or len(occurrences) != shape.active_aliquots
        or any(count != 1 for count in occurrences.values())
        or len(withdrawn) != shape.withdrawn_aliquots
        or any(occurrences[label] != 1 for label in candidate_aliquots)
    ):
        raise ProteinAdmissionError("protein sample-map candidate assignments are not admitted")
    return _MapInventory(frozenset(occurrences), frozenset(withdrawn))


def _measurement_columns(
    header: list[str], inventory: _MapInventory, shape: _ProteinShape
) -> dict[str, dict[str, int]]:
    if (
        len(header) != 1 + 2 * shape.measurement_targets + len(_ANNOTATIONS)
        or header[0] != "Gene"
        or tuple(header[-6:]) != _ANNOTATIONS
        or len(header) != len(set(header))
    ):
        raise ProteinAdmissionError("protein matrix schema is not admitted")
    columns: dict[str, dict[str, int]] = {measure: {} for measure in _MEASURES}
    allowed = inventory.active | inventory.withdrawn | {"POOL"}
    for index, name in enumerate(header[1:-6], start=1):
        measure = (
            PRIMARY_MEASURE
            if name.endswith(" " + PRIMARY_MEASURE)
            else _ALL_PEPTIDE_MEASURE
            if name.endswith(" " + _ALL_PEPTIDE_MEASURE)
            else None
        )
        if measure is None:
            raise ProteinAdmissionError("protein measurement family is not admitted")
        label = name[: -(len(measure) + 1)]
        if label not in allowed or label in columns[measure]:
            raise ProteinAdmissionError("protein measurement binding is not admitted")
        columns[measure][label] = index
    if any(set(columns[measure]) != allowed for measure in _MEASURES):
        raise ProteinAdmissionError(
            "protein measurement families have different specimen inventories"
        )
    return columns


def _number(value: str) -> float:
    if value == "":
        return math.nan
    if len(value) > 128:
        raise ProteinAdmissionError("protein numeric field exceeds the admitted bound")
    try:
        result = float(value)
    except ValueError:
        raise ProteinAdmissionError("protein measurement is not a finite number or blank") from None
    if not math.isfinite(result):
        raise ProteinAdmissionError("protein measurement is not a finite number or blank")
    return result


def _identity(
    source_symbol: str, entrez: str, authority: str, hgnc: HgncReference
) -> GeneIdentity | None:
    if not entrez.isascii() or not entrez.isdigit() or entrez.startswith("0"):
        raise ProteinAdmissionError("protein NCBI gene identity is not admitted")
    identity = hgnc.by_hgnc.get(authority)
    if identity is None or identity.entrez_id is None:
        return None
    if identity.entrez_id != entrez:
        raise ProteinAdmissionError("protein stable gene identifiers disagree")
    symbol_identity = hgnc.by_symbol.get(source_symbol)
    if symbol_identity is not None and symbol_identity.hgnc_id != identity.hgnc_id:
        raise ProteinAdmissionError("protein approved symbol and authority disagree")
    return identity


def _decode_protein_contents(
    protein: bytes,
    sample_map: bytes,
    hgnc: HgncReference,
    candidate_aliquots: tuple[str, ...],
    *,
    shape: _ProteinShape = _SOURCE_SHAPE,
) -> _DecodedProtein:
    """Pure private decoder; only the public function verifies source admission."""

    if len(protein) > PROTEIN_LOCK.bytes or len(sample_map) > SAMPLE_MAP_LOCK.bytes:
        raise ProteinAdmissionError("protein source contents exceed the admitted bound")
    _validate_candidates(candidate_aliquots, shape)
    if any(gene not in hgnc.by_symbol for gene in PANEL):
        raise ProteinAdmissionError("protein HGNC panel reference is incomplete")
    try:
        inventory = _sample_inventory(sample_map, candidate_aliquots, shape)
        return _decode_matrix(protein, hgnc, candidate_aliquots, inventory, shape)
    except (csv.Error, UnicodeError):
        raise ProteinAdmissionError("protein source TSV structure is not admitted") from None


def _decode_matrix(  # noqa: PLR0915 - one explicit source-row admission boundary.
    protein: bytes,
    hgnc: HgncReference,
    candidate_aliquots: tuple[str, ...],
    inventory: _MapInventory,
    shape: _ProteinShape,
) -> _DecodedProtein:
    reader = _tsv(protein)
    header = next(reader, [])
    columns = _measurement_columns(header, inventory, shape)
    values = np.empty((shape.biological_rows, shape.candidate_count), dtype=np.float64)
    identities: list[GeneIdentity | None] = []
    seen_genes: set[str] = set()
    seen_entrez: set[str] = set()
    seen_hgnc: set[str] = set()
    panel_identities = tuple(hgnc.by_symbol[gene] for gene in PANEL)
    panel_hgnc_ids = {panel_identity.hgnc_id for panel_identity in panel_identities}
    panel_entrez_ids = {
        panel_identity.entrez_id
        for panel_identity in panel_identities
        if panel_identity.entrez_id is not None
    }
    aggregates: Counter[str] = Counter()
    panel: dict[str, ProteinPanelCoverage] = {}
    finite_unshared = missing_unshared = zero_unshared = 0
    finite_all = missing_all = 0
    active_columns = tuple(
        index
        for measure in _MEASURES
        for label, index in columns[measure].items()
        if label in inventory.active
    )
    selected = {
        measure: tuple(columns[measure][label] for label in candidate_aliquots)
        for measure in _MEASURES
    }
    for row in reader:
        if len(row) != len(header):
            raise ProteinAdmissionError("protein matrix contains a ragged row")
        symbol = row[0]
        if symbol in _AGGREGATES:
            aggregates[symbol] += 1
            if aggregates[symbol] > 1:
                raise ProteinAdmissionError("protein aggregate rows are duplicated")
            continue
        index = len(identities)
        if index >= shape.biological_rows:
            raise ProteinAdmissionError("protein feature inventory exceeds the admitted bound")
        if (
            not symbol
            or len(symbol) > 256
            or symbol in seen_genes
            or any(character.isspace() or ord(character) < 32 for character in symbol)
        ):
            raise ProteinAdmissionError("protein source feature is empty or duplicated")
        if row[-3] != "Homo sapiens":
            raise ProteinAdmissionError("protein source organism is not admitted")
        entrez, authority = row[-6], row[-5]
        if entrez in seen_entrez:
            raise ProteinAdmissionError("protein source gene identifiers collide")
        identity = _identity(symbol, entrez, authority, hgnc)
        if identity is None and (
            symbol in PANEL or authority in panel_hgnc_ids or entrez in panel_entrez_ids
        ):
            raise ProteinAdmissionError("protein unresolved feature overlaps frozen-panel identity")
        if identity is not None:
            if identity.hgnc_id in seen_hgnc:
                raise ProteinAdmissionError("protein approved gene identities collide")
            seen_hgnc.add(identity.hgnc_id)
        seen_genes.add(symbol)
        seen_entrez.add(entrez)
        identities.append(identity)
        # Validate both active source families, but never select a shared-peptide
        # value as a replacement for an unavailable unshared measurement.
        parsed = {column: _number(row[column]) for column in active_columns}
        unshared = tuple(parsed[column] for column in selected[PRIMARY_MEASURE])
        all_peptide = tuple(parsed[column] for column in selected[_ALL_PEPTIDE_MEASURE])
        values[index] = unshared
        observed = sum(math.isfinite(value) for value in unshared)
        shared_observed = sum(math.isfinite(value) for value in all_peptide)
        finite_unshared += observed
        missing_unshared += shape.candidate_count - observed
        zero_unshared += sum(value == 0.0 for value in unshared)
        finite_all += shared_observed
        missing_all += shape.candidate_count - shared_observed
        if identity is not None and identity.symbol in PANEL:
            if symbol != identity.symbol:
                raise ProteinAdmissionError("protein frozen-panel source symbol is not exact")
            panel[identity.symbol] = ProteinPanelCoverage(
                identity.symbol, 1, observed, shape.candidate_count - observed, shared_observed
            )
    if (
        len(identities) != shape.biological_rows
        or aggregates != Counter(dict.fromkeys(_AGGREGATES, 1))
        or set(panel) != set(PANEL) - {"CDKN2B"}
        or "CDKN2B" in seen_genes
    ):
        raise ProteinAdmissionError("protein feature or frozen-panel inventory is not admitted")
    panel_coverage = tuple(
        panel.get(gene, ProteinPanelCoverage(gene, 0, None, None, None)) for gene in PANEL
    )
    immutable = np.frombuffer(values.tobytes(), dtype=np.float64).reshape(values.shape)
    return _DecodedProtein(
        immutable,
        tuple(identities),
        finite_unshared,
        missing_unshared,
        zero_unshared,
        finite_all,
        missing_all,
        panel_coverage,
    )


def admit_confirmatory_protein(
    *,
    protein_path: Path,
    sample_map_path: Path,
    hgnc_path: Path,
    candidate_aliquots: tuple[str, ...],
) -> ConfirmatoryProteinAdmission:
    """Verify fixed local bytes, then decode the ordered 56-candidate source."""

    _validate_candidates(candidate_aliquots, _SOURCE_SHAPE)
    protein = read_verified_source(protein_path, PROTEIN_LOCK, max_bytes=PROTEIN_LOCK.bytes)
    sample_map = read_verified_source(
        sample_map_path, SAMPLE_MAP_LOCK, max_bytes=SAMPLE_MAP_LOCK.bytes
    )
    hgnc = read_locked_hgnc(hgnc_path)
    decoded = _decode_protein_contents(protein, sample_map, hgnc, candidate_aliquots)
    digest = sha256_digest(candidate_aliquots)
    unavailable = sum(identity is None for identity in decoded.identities)
    receipt = ProteinAdmissionReceipt(
        PROFILE_ID,
        PROTEIN_LOCK.sha256,
        SAMPLE_MAP_LOCK.sha256,
        HGNC_LOCK.sha256,
        digest,
        len(candidate_aliquots),
        len(decoded.identities),
        len(decoded.identities) - unavailable,
        unavailable,
        len(_AGGREGATES),
        _SOURCE_SHAPE.withdrawn_aliquots,
        _SOURCE_SHAPE.pool_targets,
        decoded.finite_unshared,
        decoded.missing_unshared,
        decoded.zero_unshared,
        decoded.finite_all_peptide,
        decoded.missing_all_peptide,
        decoded.panel_coverage,
        (
            "Protein-only source admission does not establish a complete external cohort or compatible CNV/RNA support.",
            "Values are CDAP median-normalized log2 sample/common-reference ratios from unshared peptides; no scale conversion or imputation is performed.",
            "All-peptide Log Ratio is counted only as a distinct coverage comparator and is never used to fill the selected measurement.",
            "Unavailable feature identities remain explicit as None; their source rows must not be used as approved genes.",
            "The historical disease scope, pooled reference, upstream preprocessing, treatment eligibility, donor independence and reuse terms remain separately unadmitted.",
            "No modelling, clinical prediction, mechanistic discovery or external validation follows from this receipt.",
        ),
    )
    return ConfirmatoryProteinAdmission(digest, decoded.values, decoded.identities, receipt)


__all__ = [
    "PRIMARY_MEASURE",
    "PROFILE_ID",
    "PROTEIN_LOCK",
    "SAMPLE_MAP_LOCK",
    "ConfirmatoryProteinAdmission",
    "ProteinAdmissionError",
    "ProteinAdmissionReceipt",
    "ProteinPanelCoverage",
    "admit_confirmatory_protein",
]
