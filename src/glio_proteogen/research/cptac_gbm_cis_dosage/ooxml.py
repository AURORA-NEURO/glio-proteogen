"""Bounded OOXML streaming for exact locked CPTAC GBM workbooks.

Only the three fitted assay matrices and optional Table S3 flags are streamed.
The parser does not return, log, or separately persist sample headers or patient
rows. The local fitter does parse an ephemeral whole-source staged snapshot;
that snapshot is owned and cleaned by the source-staging boundary.
"""

from __future__ import annotations

import collections
import csv
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import defusedxml.ElementTree as SafeET
import numpy as np
import numpy.typing as npt

from .errors import FitNotEvaluableError

MAIN: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
ROW_TAG: Final = f"{{{MAIN}}}row"
CELL_TAG: Final = f"{{{MAIN}}}c"
SI_TAG: Final = f"{{{MAIN}}}si"
V_TAG: Final = f"{{{MAIN}}}v"
T_TAG: Final = f"{{{MAIN}}}t"
TARGET_SHEETS: Final = (
    "somatic_cnv_gene_gistic",
    "gene_expression_fpkm_uq",
    "proteome_normalized",
)

CellToken = tuple[str, str]
GeneMapper = Callable[[str | None], str | None]
Float32Array = npt.NDArray[np.float32]
Int8Array = npt.NDArray[np.int8]


@dataclass(slots=True)
class SheetScan:
    name: str
    member: str
    rows: int
    columns: int
    header_tokens: dict[int, CellToken | None]
    gene_token_counts: collections.Counter[CellToken | None]


@dataclass(slots=True)
class PreparedCohort:
    cnv: dict[str, Float32Array]
    rna: dict[str, Float32Array]
    protein: dict[str, Float32Array]
    folds: Int8Array
    common_genes: tuple[str, ...]
    exact_common_measurement_count: int
    patient_group_count: int


def workbook_sheet_map(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = SafeET.fromstring(archive.read("xl/workbook.xml"))
    relationships = SafeET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relationships.findall(f"{{{PKG_REL}}}Relationship")
    }
    sheets = workbook.find(f"{{{MAIN}}}sheets")
    if sheets is None:
        raise FitNotEvaluableError("workbook contains no sheets")
    output: dict[str, str] = {}
    for sheet in sheets:
        name = sheet.attrib["name"]
        target = targets[sheet.attrib[f"{{{REL}}}id"]].replace("\\", "/")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target
        output[name] = target
    return output


def column_index(reference: str) -> int:
    value = 0
    found = False
    for character in reference:
        if not character.isalpha():
            break
        found = True
        value = value * 26 + ord(character.upper()) - 64
    if not found:
        raise FitNotEvaluableError("worksheet cell has an invalid coordinate")
    return value - 1


def _cell_token(cell: ET.Element) -> CellToken | None:  # noqa: PLR0911
    kind = cell.attrib.get("t", "n")
    if kind == "inlineStr":
        return "text", "".join((node.text or "") for node in cell.findall(f".//{T_TAG}"))
    value_node = cell.find(V_TAG)
    if value_node is None or value_node.text is None:
        return None
    if kind == "s":
        return "shared", value_node.text
    if kind == "str":
        return "text", value_node.text
    if kind == "b":
        return "bool", value_node.text
    if kind == "e":
        return "error", value_node.text
    return "number", value_node.text


def _scan_sheet(
    archive: zipfile.ZipFile,
    name: str,
    member: str,
    needed_shared: set[int],
) -> SheetScan:
    rows = 0
    columns = 0
    header: dict[int, CellToken | None] = {}
    gene_counts: collections.Counter[CellToken | None] = collections.Counter()
    with archive.open(member) as stream:
        for _, element in SafeET.iterparse(stream, events=("end",)):
            if element.tag != ROW_TAG:
                continue
            rows += 1
            row_number = int(element.attrib.get("r", rows))
            for cell in element.findall(CELL_TAG):
                index = column_index(cell.attrib.get("r", "A1"))
                columns = max(columns, index + 1)
                if row_number == 1:
                    token = _cell_token(cell)
                    header[index] = token
                    if token is not None and token[0] == "shared":
                        needed_shared.add(int(token[1]))
                elif index == 0:
                    token = _cell_token(cell)
                    gene_counts[token] += 1
                    if token is not None and token[0] == "shared":
                        needed_shared.add(int(token[1]))
                    break
            element.clear()
    return SheetScan(name, member, rows, columns, header, gene_counts)


def _resolve_shared_strings(
    archive: zipfile.ZipFile,
    needed: set[int],
) -> dict[int, str]:
    resolved: dict[int, str] = {}
    if not needed:
        return resolved
    index = -1
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, element in SafeET.iterparse(stream, events=("end",)):
            if element.tag != SI_TAG:
                continue
            index += 1
            if index in needed:
                resolved[index] = "".join(
                    (node.text or "") for node in element.findall(f".//{T_TAG}")
                )
            element.clear()
    if needed.difference(resolved):
        raise FitNotEvaluableError("workbook shared strings are incomplete")
    return resolved


def _token_text(token: CellToken | None, shared: dict[int, str]) -> str | None:
    if token is None:
        return None
    kind, value = token
    if kind == "shared":
        return shared[int(value)]
    return value if kind == "text" else None


def _token_number(token: CellToken | None) -> float:
    if token is None or token[0] not in {"number", "bool"}:
        return math.nan
    try:
        value = float(token[1])
    except ValueError:
        return math.nan
    return value if math.isfinite(value) else math.nan


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolved_headers(scan: SheetScan, shared: dict[int, str]) -> dict[int, str]:
    return {
        column: text
        for column, token in scan.header_tokens.items()
        if (text := _token_text(token, shared)) is not None
    }


def _resolved_gene_counts(
    scan: SheetScan,
    shared: dict[int, str],
) -> collections.Counter[str]:
    output: collections.Counter[str] = collections.Counter()
    for token, count in scan.gene_token_counts.items():
        text = _normalized_text(_token_text(token, shared))
        if text is not None:
            output[text] += count
    return output


def load_hgnc_map(path: Path) -> tuple[dict[str, str], set[str]]:
    candidates: dict[str, set[str]] = collections.defaultdict(set)
    symbols: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"symbol", "ensembl_gene_id", "status"}
        if not required.issubset(reader.fieldnames or []):
            raise FitNotEvaluableError("HGNC source schema does not match the admitted snapshot")
        for row in reader:
            if row.get("status") != "Approved":
                continue
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                continue
            symbols.add(symbol)
            for ensembl in (row.get("ensembl_gene_id") or "").split("|"):
                if key := ensembl.strip():
                    candidates[key].add(symbol)
    mapping = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    return mapping, symbols


def _gene_mappers(
    ensembl_to_symbol: dict[str, str],
    approved_symbols: set[str],
) -> dict[str, GeneMapper]:
    def cnv(value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"(.+)\|chr(?:[0-9]+|X|Y|M|MT)", value)
        symbol = match.group(1) if match else value
        return symbol if symbol in approved_symbols else None

    def rna(value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"(ENSG[0-9]+)(?:\.[0-9]+)?", value)
        return ensembl_to_symbol.get(match.group(1)) if match else None

    def protein(value: str | None) -> str | None:
        return value if value in approved_symbols else None

    return {
        "somatic_cnv_gene_gistic": cnv,
        "gene_expression_fpkm_uq": rna,
        "proteome_normalized": protein,
    }


def _mapped_counts(
    raw: collections.Counter[str],
    mapper: GeneMapper,
) -> collections.Counter[str]:
    output: collections.Counter[str] = collections.Counter()
    for value, count in raw.items():
        if (gene := mapper(value)) is not None:
            output[gene] += count
    return output


def _patient_group(value: str) -> str:
    for pattern in (
        r"^(C3[NL]-[A-Za-z0-9]{5})",
        r"^(TCGA-[A-Za-z0-9]{2}-[A-Za-z0-9]{4})",
    ):
        if match := re.match(pattern, value):
            return match.group(1)
    return value


def _load_gene_matrix(  # noqa: PLR0917 - explicit transient stream context.
    archive: zipfile.ZipFile,
    scan: SheetScan,
    shared: dict[int, str],
    unique_genes: set[str],
    sample_to_index: dict[str, int],
    mapper: GeneMapper,
) -> dict[str, Float32Array]:
    header = _resolved_headers(scan, shared)
    selected_columns = {
        column: sample_to_index[value]
        for column, value in header.items()
        if value in sample_to_index
    }
    matrix: dict[str, Float32Array] = {}
    with archive.open(scan.member) as stream:
        for _, element in SafeET.iterparse(stream, events=("end",)):
            if element.tag != ROW_TAG:
                continue
            row_number = int(element.attrib.get("r", "0"))
            if row_number <= 1:
                element.clear()
                continue
            cells = element.findall(CELL_TAG)
            gene: str | None = None
            for cell in cells:
                if column_index(cell.attrib.get("r", "A1")) == 0:
                    gene = mapper(_normalized_text(_token_text(_cell_token(cell), shared)))
                    break
            if gene is None or gene not in unique_genes or gene in matrix:
                element.clear()
                continue
            values = np.full(len(sample_to_index), np.nan, dtype=np.float32)
            for cell in cells:
                sample_index = selected_columns.get(column_index(cell.attrib.get("r", "A1")))
                if sample_index is not None:
                    values[sample_index] = _token_number(_cell_token(cell))
            matrix[gene] = values
            element.clear()
    return matrix


def prepare_cohort(table_s2: Path, hgnc: Path) -> PreparedCohort:
    ensembl_to_symbol, approved_symbols = load_hgnc_map(hgnc)
    mappers = _gene_mappers(ensembl_to_symbol, approved_symbols)
    with zipfile.ZipFile(table_s2) as archive:
        sheets = workbook_sheet_map(archive)
        if set(TARGET_SHEETS).difference(sheets):
            raise FitNotEvaluableError("Table S2 is missing a required assay sheet")
        needed_shared: set[int] = set()
        scans = {
            name: _scan_sheet(archive, name, sheets[name], needed_shared) for name in TARGET_SHEETS
        }
        shared = _resolve_shared_strings(archive, needed_shared)
        headers = {name: _resolved_headers(scan, shared) for name, scan in scans.items()}
        sample_sets = {name: set(value.values()) for name, value in headers.items()}
        for name, header in headers.items():
            sample_sets[name].discard(header.get(0))
        common_samples = set.intersection(*(sample_sets[name] for name in TARGET_SHEETS))
        common_order = [
            value
            for column, value in sorted(headers[TARGET_SHEETS[0]].items())
            if column != 0 and value in common_samples
        ]
        if len(common_order) != len(common_samples):
            raise FitNotEvaluableError("duplicate common measurement headers are forbidden")
        if len(common_order) < 60:
            raise FitNotEvaluableError("fewer than sixty exact common measurements are available")
        patient_groups = [_patient_group(value) for value in common_order]
        unique_groups = list(dict.fromkeys(patient_groups))
        shuffled_groups = list(unique_groups)
        np.random.default_rng(20_260_829).shuffle(shuffled_groups)
        group_fold = {group: index % 5 for index, group in enumerate(shuffled_groups)}
        folds = np.asarray([group_fold[group] for group in patient_groups], dtype=np.int8)
        sample_to_index = {value: index for index, value in enumerate(common_order)}

        mapped_counts = {
            name: _mapped_counts(_resolved_gene_counts(scans[name], shared), mappers[name])
            for name in TARGET_SHEETS
        }
        unique_gene_sets = {
            name: {gene for gene, count in counts.items() if count == 1}
            for name, counts in mapped_counts.items()
        }
        common_genes = set.intersection(*(unique_gene_sets[name] for name in TARGET_SHEETS))
        if not common_genes:
            raise FitNotEvaluableError("no collision-free common HGNC genes are available")
        matrices = {
            name: _load_gene_matrix(
                archive,
                scans[name],
                shared,
                common_genes,
                sample_to_index,
                mappers[name],
            )
            for name in TARGET_SHEETS
        }
    if any(set(matrix) != common_genes for matrix in matrices.values()):
        raise FitNotEvaluableError("one or more exact common gene rows could not be streamed")
    return PreparedCohort(
        cnv=matrices[TARGET_SHEETS[0]],
        rna=matrices[TARGET_SHEETS[1]],
        protein=matrices[TARGET_SHEETS[2]],
        folds=folds,
        common_genes=tuple(sorted(common_genes)),
        exact_common_measurement_count=len(common_order),
        patient_group_count=len(unique_groups),
    )


def load_table_s3_flags(table_s3: Path) -> dict[str, tuple[bool, bool]]:
    with zipfile.ZipFile(table_s3) as archive:
        sheets = workbook_sheet_map(archive)
        member = sheets.get("iProFun_rna_protein")
        if member is None:
            raise FitNotEvaluableError("Table S3 is missing its iProFun flag sheet")
        needed: set[int] = set()
        scan = _scan_sheet(archive, "iProFun_rna_protein", member, needed)
        shared = _resolve_shared_strings(archive, needed)
        header_to_column = {value: key for key, value in _resolved_headers(scan, shared).items()}
        try:
            gene_column = header_to_column["gene"]
            rna_column = header_to_column["CNV RNA"]
            protein_column = header_to_column["CNV Protein"]
        except KeyError as error:
            raise FitNotEvaluableError(
                "Table S3 iProFun flags have an unexpected schema"
            ) from error
        flags: dict[str, tuple[bool, bool]] = {}
        with archive.open(member) as stream:
            for _, element in SafeET.iterparse(stream, events=("end",)):
                if element.tag != ROW_TAG:
                    continue
                row_number = int(element.attrib.get("r", "0"))
                if row_number <= 1:
                    element.clear()
                    continue
                tokens = {
                    column_index(cell.attrib.get("r", "A1")): _cell_token(cell)
                    for cell in element.findall(CELL_TAG)
                    if column_index(cell.attrib.get("r", "A1"))
                    in {gene_column, rna_column, protein_column}
                }
                gene = _normalized_text(_token_text(tokens.get(gene_column), shared))
                rna_value = _token_number(tokens.get(rna_column))
                protein_value = _token_number(tokens.get(protein_column))
                if (
                    gene is not None
                    and gene not in flags
                    and rna_value in {0.0, 1.0}
                    and protein_value in {0.0, 1.0}
                ):
                    flags[gene] = rna_value == 1.0, protein_value == 1.0
                element.clear()
    return flags


__all__ = [
    "PreparedCohort",
    "column_index",
    "load_hgnc_map",
    "load_table_s3_flags",
    "prepare_cohort",
    "workbook_sheet_map",
]
