# ruff: noqa: C901, S314, TRY003
"""Admit the pinned Migliozzi et al. GBM functional-proteotype source tables.

Only the aggregate, source-ranked protein signatures in Supplementary Table 2d and
the aggregate pathway context in Supplementary Table 2e are projected. Patient and
sample matrices from the supplement are deliberately outside this builder's scope.

The pinned workbook is parsed as OOXML with the Python standard library. Exact source
bytes, worksheet identity, dimensions, titles, headers, row counts, numerical domains,
identifier uniqueness, and source ordering are checked before canonical JSON is emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

SOURCE_URL: Final = (
    "https://pmc.ncbi.nlm.nih.gov/articles/instance/9970878/bin/"
    "43018_2022_510_MOESM2_ESM.xlsx"
)
SOURCE_ARCHIVE_URL: Final = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9970878/supplementaryFiles"
)
SOURCE_FILENAME: Final = "43018_2022_510_MOESM2_ESM.xlsx"
SOURCE_SHA256: Final = "865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
SOURCE_SIZE_BYTES: Final = 7_635_280
ARTICLE_DOI: Final = "10.1038/s43018-022-00510-x"
ARTICLE_TITLE: Final = (
    "Integrative multi-omics networks identify PKCδ and DNA-PK as master kinases of "
    "glioblastoma subtypes and guide targeted cancer therapy"
)
SCHEMA_VERSION: Final = "gbm-functional-proteotype-catalog/1.0.0"

COMMON_TABLE_TITLE: Final = (
    "Supplementary Table 2: Multiomics data analysis of the four functional subtypes "
    "of CPTAC-GBM"
)
TABLE_2D_WORKSHEET: Final = "Tab 14 - Supplementary Table 2d"
TABLE_2D_DIMENSION: Final = "A1:O154"
TABLE_2D_TITLE: Final = (
    "Supplementary Table 2d: List of the highest 150 scoring proteins of the ranked "
    "lists of each GBM subtype"
)
TABLE_2D_HEADERS: Final = ("Gene", "Protein", "MWW score")
TABLE_2E_WORKSHEET: Final = "Tab 15 - Supplementary Table 2e"
TABLE_2E_DIMENSION: Final = "A1:S276"
TABLE_2E_TITLE: Final = (
    "Supplementary Table 2e: List of the highest active not-redundant biological "
    "pathways from the protein ranked lists of each GBM subtype"
)
TABLE_2E_HEADERS: Final = ("Biological pathway", "logitNES", "pValue", "qValue")

AXES: Final = ("GPM", "MTC", "NEU", "PPR")
AXIS_TITLES: Final = {
    "GPM": "Glycolytic/plurimetabolic (GPM)",
    "MTC": "Mitochondrial (MTC)",
    "NEU": "Neuronal (NEU)",
    "PPR": "Proliferative/progenitor (PPR)",
}
TABLE_2D_COLUMNS: Final = {
    "GPM": ("A", "B", "C"),
    "MTC": ("E", "F", "G"),
    "NEU": ("I", "J", "K"),
    "PPR": ("M", "N", "O"),
}
TABLE_2E_COLUMNS: Final = {
    "GPM": ("A", "B", "C", "D"),
    "MTC": ("F", "G", "H", "I"),
    "NEU": ("K", "L", "M", "N"),
    "PPR": ("P", "Q", "R", "S"),
}
EXPECTED_SIGNATURE_COUNTS: Final = dict.fromkeys(AXES, 150)
EXPECTED_PATHWAY_COUNTS: Final = {"GPM": 243, "MTC": 107, "NEU": 272, "PPR": 204}
TABLE_2D_LAST_ROW: Final = 154
TABLE_2E_LAST_ROW: Final = 276

_MAIN_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_PACKAGE_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REFERENCE: Final = re.compile(r"([A-Z]+)([1-9][0-9]*)\Z")

CellMap = dict[tuple[int, str], str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_digest(value: object) -> str:
    """Return the profile's canonical SHA-256 digest for a JSON-compatible value."""

    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def render_catalog(document: dict[str, object]) -> bytes:
    """Render deterministic, human-reviewable catalog bytes."""

    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return ()
    root = ET.fromstring(payload)
    return tuple(
        "".join(node.text or "" for node in item.findall(f".//{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    )


def _worksheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets: dict[str, str] = {}
    for item in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        relationship_id = item.attrib.get("Id", "")
        target = item.attrib.get("Target", "")
        if not relationship_id or not target or relationship_id in targets:
            raise ValueError("invalid or duplicate workbook relationship")
        targets[relationship_id] = target
    result: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        name = sheet.attrib.get("name", "")
        relationship_id = sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
        if not name or name in result or relationship_id not in targets:
            raise ValueError("invalid, duplicate, or unresolved worksheet")
        target_path = PurePosixPath(targets[relationship_id].lstrip("/"))
        if ".." in target_path.parts:
            raise ValueError("unsafe worksheet relationship target")
        path = (
            target_path
            if target_path.parts[:1] == ("xl",)
            else PurePosixPath("xl") / target_path
        )
        result[name] = path.as_posix()
    return result


def _worksheet_cells(
    archive: zipfile.ZipFile,
    path: str,
    shared_strings: tuple[str, ...],
) -> tuple[CellMap, str]:
    root = ET.fromstring(archive.read(path))
    dimension = root.find(f"{{{_MAIN_NS}}}dimension")
    if dimension is None or not dimension.attrib.get("ref"):
        raise ValueError(f"worksheet {path} has no dimension")
    cells: CellMap = {}
    for cell in root.findall(f".//{{{_MAIN_NS}}}c"):
        reference = cell.attrib.get("r", "")
        match = _CELL_REFERENCE.fullmatch(reference)
        if match is None:
            raise ValueError(f"invalid cell reference {reference!r}")
        key = (int(match.group(2)), match.group(1))
        if key in cells:
            raise ValueError(f"duplicate cell reference {reference}")
        if cell.find(f"{{{_MAIN_NS}}}f") is not None:
            raise ValueError(f"formula cell is not admissible: {reference}")
        value = cell.find(f"{{{_MAIN_NS}}}v")
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            raw_value = "".join(
                node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t")
            )
        elif value is None or value.text is None:
            raw_value = ""
        elif cell_type == "s":
            try:
                raw_value = shared_strings[int(value.text)]
            except (IndexError, ValueError) as error:
                raise ValueError(f"invalid shared-string reference in {reference}") from error
        else:
            raw_value = value.text
        cells[key] = raw_value
    return cells, dimension.attrib["ref"]


def _required_text(cells: CellMap, row: int, column: str) -> str:
    value = cells.get((row, column), "")
    if not value:
        raise ValueError(f"required source cell {column}{row} is empty")
    if value.strip() != value:
        raise ValueError(f"source cell {column}{row} has surrounding whitespace")
    return value


def _finite_number(cells: CellMap, row: int, column: str) -> float:
    raw_value = _required_text(cells, row, column)
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"source cell {column}{row} is not numeric") from error
    if not math.isfinite(value):
        raise ValueError(f"source cell {column}{row} is not finite")
    return value


def _validate_table_identity(
    cells: CellMap,
    *,
    table_title: str,
    headers: tuple[str, ...],
    columns_by_axis: Mapping[str, tuple[str, ...]],
) -> None:
    if cells.get((1, "A")) != COMMON_TABLE_TITLE or cells.get((2, "A")) != table_title:
        raise ValueError("unexpected Supplementary Table 2 title")
    for axis in AXES:
        columns = columns_by_axis[axis]
        if cells.get((3, columns[0])) != AXIS_TITLES[axis]:
            raise ValueError(f"unexpected {axis} axis heading")
        actual_headers = tuple(cells.get((4, column), "") for column in columns)
        if actual_headers != headers:
            raise ValueError(f"unexpected {axis} table headers")


def _protein_signatures(cells: CellMap) -> dict[str, list[dict[str, object]]]:
    _validate_table_identity(
        cells,
        table_title=TABLE_2D_TITLE,
        headers=TABLE_2D_HEADERS,
        columns_by_axis=TABLE_2D_COLUMNS,
    )
    result: dict[str, list[dict[str, object]]] = {}
    all_genes: set[str] = set()
    all_protein_labels: set[str] = set()
    for axis in AXES:
        gene_column, protein_column, score_column = TABLE_2D_COLUMNS[axis]
        rows: list[dict[str, object]] = []
        previous_score = math.inf
        for source_rank, row in enumerate(range(5, TABLE_2D_LAST_ROW + 1), start=1):
            gene = _required_text(cells, row, gene_column)
            protein_label = _required_text(cells, row, protein_column)
            score = _finite_number(cells, row, score_column)
            if score <= 0.0:
                raise ValueError(f"Table 2d MWW score must be positive at {score_column}{row}")
            if score > previous_score:
                raise ValueError(f"Table 2d MWW scores are not source-ranked for {axis}")
            if gene in all_genes:
                raise ValueError(f"Table 2d gene identifiers are not disjoint: {gene}")
            if protein_label in all_protein_labels:
                raise ValueError(f"duplicate Table 2d protein label: {protein_label}")
            all_genes.add(gene)
            all_protein_labels.add(protein_label)
            previous_score = score
            rows.append(
                {
                    "gene_symbol": gene,
                    "source_mww_score": score,
                    "source_protein_label": protein_label,
                    "source_rank": source_rank,
                }
            )
        if len(rows) != EXPECTED_SIGNATURE_COUNTS[axis]:
            raise ValueError(f"unexpected Table 2d signature count for {axis}")
        result[axis] = rows
    if len(all_genes) != sum(EXPECTED_SIGNATURE_COUNTS.values()):
        raise ValueError("unexpected Table 2d global gene count")
    return result


def _pathway_context(cells: CellMap) -> dict[str, list[dict[str, object]]]:
    _validate_table_identity(
        cells,
        table_title=TABLE_2E_TITLE,
        headers=TABLE_2E_HEADERS,
        columns_by_axis=TABLE_2E_COLUMNS,
    )
    result: dict[str, list[dict[str, object]]] = {}
    for axis in AXES:
        pathway_column, nes_column, p_column, q_column = TABLE_2E_COLUMNS[axis]
        rows: list[dict[str, object]] = []
        encountered_blank = False
        pathways: set[str] = set()
        for row in range(5, TABLE_2E_LAST_ROW + 1):
            raw_values = tuple(cells.get((row, column), "") for column in TABLE_2E_COLUMNS[axis])
            populated = tuple(bool(value) for value in raw_values)
            if not any(populated):
                encountered_blank = True
                continue
            if encountered_blank:
                raise ValueError(f"Table 2e {axis} contains a row after its blank tail")
            if not all(populated):
                raise ValueError(f"Table 2e {axis} contains a partial row at source row {row}")
            pathway = _required_text(cells, row, pathway_column)
            if pathway in pathways:
                raise ValueError(f"duplicate Table 2e pathway within {axis}: {pathway}")
            logit_nes = _finite_number(cells, row, nes_column)
            p_value = _finite_number(cells, row, p_column)
            q_value = _finite_number(cells, row, q_column)
            if logit_nes <= 0.0:
                raise ValueError(f"Table 2e logitNES must be positive at {nes_column}{row}")
            if not (0.0 < p_value <= 1.0):
                raise ValueError(f"Table 2e pValue is outside (0,1] at {p_column}{row}")
            if not (p_value <= q_value <= 1.0):
                raise ValueError(f"Table 2e qValue is invalid at {q_column}{row}")
            pathways.add(pathway)
            rows.append(
                {
                    "logit_nes": logit_nes,
                    "p_value": p_value,
                    "pathway": pathway,
                    "q_value": q_value,
                    "source_rank": len(rows) + 1,
                }
            )
        if len(rows) != EXPECTED_PATHWAY_COUNTS[axis]:
            raise ValueError(f"unexpected Table 2e pathway count for {axis}")
        result[axis] = rows
    return result


def build_catalog(source: Path) -> dict[str, object]:
    """Build the aggregate-only catalog after validating the exact source workbook."""

    if not source.is_file():
        raise ValueError(f"source workbook is not a file: {source}")
    actual_size = source.stat().st_size
    if actual_size != SOURCE_SIZE_BYTES:
        raise ValueError(
            f"source size mismatch: expected {SOURCE_SIZE_BYTES}, got {actual_size}"
        )
    actual_sha256 = _sha256(source)
    if actual_sha256 != SOURCE_SHA256:
        raise ValueError(
            f"source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha256}"
        )
    with zipfile.ZipFile(source) as archive:
        shared_strings = _shared_strings(archive)
        worksheet_paths = _worksheet_paths(archive)
        expected_names = (TABLE_2D_WORKSHEET, TABLE_2E_WORKSHEET)
        if any(name not in worksheet_paths for name in expected_names):
            raise ValueError("pinned Table 2d/2e worksheets are missing")
        table_2d_cells, table_2d_dimension = _worksheet_cells(
            archive,
            worksheet_paths[TABLE_2D_WORKSHEET],
            shared_strings,
        )
        table_2e_cells, table_2e_dimension = _worksheet_cells(
            archive,
            worksheet_paths[TABLE_2E_WORKSHEET],
            shared_strings,
        )
    if table_2d_dimension != TABLE_2D_DIMENSION:
        raise ValueError(f"unexpected Table 2d worksheet dimension: {table_2d_dimension}")
    if table_2e_dimension != TABLE_2E_DIMENSION:
        raise ValueError(f"unexpected Table 2e worksheet dimension: {table_2e_dimension}")
    axes = _protein_signatures(table_2d_cells)
    pathway_context = _pathway_context(table_2e_cells)
    payload: dict[str, object] = {
        "axes": axes,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "article_authors": "Migliozzi et al.",
            "article_doi": ARTICLE_DOI,
            "article_title": ARTICLE_TITLE,
            "article_year": 2023,
            "copyright": "© The Author(s) 2023",
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "pmcid": "PMC9970878",
            "source_archive_url": SOURCE_ARCHIVE_URL,
            "source_filename": SOURCE_FILENAME,
            "source_sha256": f"sha256:{SOURCE_SHA256}",
            "source_size_bytes": SOURCE_SIZE_BYTES,
            "source_url": SOURCE_URL,
            "third_party_notice": (
                "Third-party material remains subject to the credit lines in the source "
                "article. This catalog contains only aggregate Table 2d and Table 2e lists."
            ),
            "transformation_notice": (
                "Adapted aggregate projection: source-ranked functional-proteotype proteins "
                "and source cohort pathway context were extracted without patient or sample "
                "matrices. Source labels and numerical scores are retained without identifier "
                "normalization; downstream GLIO-PROTEOGEN methods are not source-author methods."
            ),
            "worksheets": {
                "table_2d": {
                    "dimension": TABLE_2D_DIMENSION,
                    "headers": list(TABLE_2D_HEADERS),
                    "record_counts": EXPECTED_SIGNATURE_COUNTS,
                    "table_title": TABLE_2D_TITLE,
                    "worksheet_name": TABLE_2D_WORKSHEET,
                },
                "table_2e": {
                    "dimension": TABLE_2E_DIMENSION,
                    "headers": list(TABLE_2E_HEADERS),
                    "record_counts": EXPECTED_PATHWAY_COUNTS,
                    "table_title": TABLE_2E_TITLE,
                    "worksheet_name": TABLE_2E_WORKSHEET,
                },
            },
        },
        "source_cohort_pathway_context": pathway_context,
    }
    return {**payload, "content_digest": canonical_digest(payload)}


def _write_or_check(document: dict[str, object], output: Path, *, check: bool) -> None:
    expected = render_catalog(document)
    if check:
        try:
            actual = output.read_bytes()
        except FileNotFoundError as error:
            raise ValueError(f"catalog does not exist for --check: {output}") from error
        if actual != expected:
            raise ValueError(
                f"catalog is not the canonical projection of the pinned source: {output}"
            )
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Pinned source XLSX")
    parser.add_argument("--output", required=True, type=Path, help="Catalog JSON path")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare --output with a rebuild without modifying it",
    )
    arguments = parser.parse_args()
    document = build_catalog(cast("Path", arguments.source))
    _write_or_check(document, cast("Path", arguments.output), check=arguments.check)


if __name__ == "__main__":
    main()
