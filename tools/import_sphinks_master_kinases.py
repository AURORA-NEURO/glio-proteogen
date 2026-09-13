# ruff: noqa: C901, S314, TRY003
"""Reproducibly import Migliozzi et al. SPHINKS/MK Tables 5a/d/e.

The source workbook is CC-BY-4.0.  This importer reads the OOXML package using only
the Python standard library, verifies the exact source bytes, and emits a canonical
JSON catalog.  It does not use or reproduce the authors' GitHub R code or RData.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final, cast

SOURCE_URL: Final = (
    "https://pmc.ncbi.nlm.nih.gov/articles/instance/9970878/bin/43018_2022_510_MOESM2_ESM.xlsx"
)
SOURCE_ARCHIVE_URL: Final = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9970878/supplementaryFiles"
)
SOURCE_SHA256: Final = "865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
SOURCE_SIZE_BYTES: Final = 7_635_280
MAX_SUPPLEMENT_ARCHIVE_BYTES: Final = 128 * 1_024 * 1_024
DOWNLOAD_TIMEOUT_SECONDS: Final = 120
DOWNLOAD_RETRY_BACKOFF_SECONDS: Final = (0.0, 1.0, 3.0)
ARTICLE_DOI: Final = "10.1038/s43018-022-00510-x"
ARTICLE_TITLE: Final = (
    "Integrative multi-omics networks identify PKCδ and DNA-PK as master kinases of "
    "glioblastoma subtypes and guide targeted cancer therapy"
)
EXPECTED_BACKGROUND_TUPLES: Final = 34_098
EXPECTED_BACKGROUND_LABELS: Final = 30_175
EXPECTED_MASTER_KINASES: Final = 24

SUBTYPE_BLOCKS_5A: Final = {
    "GPM": ("A", "B", "C", "D", "E"),
    "MTC": ("G", "H", "I", "J", "K"),
    "NEU": ("M", "N", "O", "P", "Q"),
    "PPR": ("S", "T", "U", "V", "W"),
}
SUBTYPE_BLOCKS_5D: Final = {
    "GPM": ("A", "B", "C", "D", "E", "F"),
    "MTC": ("H", "I", "J", "K", "L", "M"),
    "NEU": ("O", "P", "Q", "R", "S", "T"),
    "PPR": ("V", "W", "X", "Y", "Z", "AA"),
}

# Exact labels used by the paper mapped to current HGNC approved symbols.  Source
# labels remain present on every imported row; this map is a separate interpretation.
KINASE_LABEL_TO_HGNC: Final = {
    "PKCD": "PRKCD",
    "VRK2": "VRK2",
    "P38D": "MAPK13",
    "SYK": "SYK",
    "MK-2": "MAPKAPK2",
    "AMPKA1": "PRKAA1",
    "MNK1": "MKNK1",
    "IKKB": "IKBKB",
    "S6K2": "RPS6KB2",
    "PHKG2": "PHKG2",
    "GSK3B": "GSK3B",
    "PKCE": "PRKCE",
    "PAK3": "PAK3",
    "PAK1": "PAK1",
    "JNK3": "MAPK10",
    "TTBK2": "TTBK2",
    "BRAF": "BRAF",
    "CHK2": "CHEK2",
    "CDK2": "CDK2",
    "DNAPK": "PRKDC",
    "CDK6": "CDK6",
    "CK2A1": "CSNK2A1",
    "CDK1": "CDK1",
    "RAF1": "RAF1",
}
EXPECTED_SUBTYPE_KINASE_COUNTS: Final = {"GPM": 9, "MTC": 1, "NEU": 7, "PPR": 7}

_MAIN_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return tuple(
        "".join(node.text or "" for node in item.findall(f".//{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    )


def _worksheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        item.attrib["Id"]: item.attrib["Target"]
        for item in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
    }
    result: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        relationship_id = sheet.attrib[f"{{{_OFFICE_REL_NS}}}id"]
        target = targets[relationship_id].lstrip("/")
        result[sheet.attrib["name"]] = target if target.startswith("xl/") else f"xl/{target}"
    return result


def _worksheet_cells(
    archive: zipfile.ZipFile,
    path: str,
    shared_strings: tuple[str, ...],
) -> tuple[dict[tuple[int, str], str], str]:
    root = ET.fromstring(archive.read(path))
    dimension = root.find(f"{{{_MAIN_NS}}}dimension")
    if dimension is None:
        raise ValueError(f"worksheet {path} has no dimension")
    cells: dict[tuple[int, str], str] = {}
    for cell in root.findall(f".//{{{_MAIN_NS}}}c"):
        reference = cell.attrib["r"]
        column_match = re.match(r"[A-Z]+", reference)
        row_match = re.search(r"\d+", reference)
        if column_match is None or row_match is None:
            raise ValueError(f"invalid cell reference {reference}")
        value = cell.find(f"{{{_MAIN_NS}}}v")
        if value is None or value.text is None:
            raw_value = ""
        elif cell.attrib.get("t") == "s":
            raw_value = shared_strings[int(value.text)]
        elif cell.attrib.get("t") == "inlineStr":
            raw_value = "".join(node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t"))
        else:
            raw_value = value.text
        cells[(int(row_match.group()), column_match.group())] = raw_value
    return cells, dimension.attrib["ref"]


def _required(cells: dict[tuple[int, str], str], row: int, column: str) -> str:
    value = cells.get((row, column), "")
    if not value:
        raise ValueError(f"required source cell {column}{row} is empty")
    return value


def _number(cells: dict[tuple[int, str], str], row: int, column: str) -> float:
    return float(_required(cells, row, column))


def _background_manifest(cells: dict[tuple[int, str], str]) -> dict[str, object]:
    expected_title = "Supplementary Table 5a: Ranked lists of phospho-sites in each GBM subtype"
    if cells.get((2, "A")) != expected_title:
        raise ValueError("unexpected Supplementary Table 5a title")
    subtype_sets: dict[str, set[tuple[str, str, str]]] = {}
    protein_labels: dict[tuple[str, str, str], set[str]] = {}
    for subtype, (
        site_col,
        protein_col,
        _score_col,
        refseq_col,
        peptide_col,
    ) in SUBTYPE_BLOCKS_5A.items():
        tuples: set[tuple[str, str, str]] = set()
        for row in range(5, 34_103):
            site_label = _required(cells, row, site_col)
            source_tuple = (
                site_label,
                _required(cells, row, refseq_col),
                _required(cells, row, peptide_col),
            )
            if source_tuple in tuples:
                raise ValueError(f"duplicate Table 5a tuple in {subtype}: {source_tuple!r}")
            tuples.add(source_tuple)
            protein_labels.setdefault(source_tuple, set()).add(_required(cells, row, protein_col))
        if len(tuples) != EXPECTED_BACKGROUND_TUPLES:
            raise ValueError(f"unexpected Table 5a tuple count for {subtype}")
        subtype_sets[subtype] = tuples
    reference = subtype_sets["GPM"]
    if any(tuples != reference for tuples in subtype_sets.values()):
        raise ValueError("Table 5a tuple inventories differ between GBM subtypes")
    labels = sorted({item[0] for item in reference})
    if len(labels) != EXPECTED_BACKGROUND_LABELS:
        raise ValueError("unexpected Table 5a source-site label count")
    rows = [
        {
            "peptide": peptide,
            "refseq_id": refseq_id,
            "source_protein_labels": sorted(protein_labels[(site_label, refseq_id, peptide)]),
            "source_site_label": site_label,
        }
        for site_label, refseq_id, peptide in sorted(reference)
    ]
    tuples_projection = [[item[0], item[1], item[2]] for item in sorted(reference)]
    return {
        "ambiguity_policy": (
            "exact source site labels are retained; labels with multiple RefSeq/peptide tuples "
            "remain ambiguous and are never assigned an invented isoform"
        ),
        "label_count": len(labels),
        "label_digest": _canonical_digest(labels),
        "labels": labels,
        "tuple_count": len(rows),
        "tuple_digest": _canonical_digest(tuples_projection),
        "tuples": rows,
    }


def _master_kinases(cells: dict[tuple[int, str], str]) -> list[dict[str, object]]:
    expected_title = (
        "Supplementary Table 5e: Subtype-specific master kinases from SPHINKS/MK approach "
        "with corresponding MWW scores from protein and gene ranked lists from CPTAC, "
        "single cells and PDOs."
    )
    if cells.get((2, "A")) != expected_title:
        raise ValueError("unexpected Supplementary Table 5e title")
    modality_columns = {
        "cptac_protein_abundance": ("F", "G", "H", "I"),
        "cptac_gene_expression": ("J", "K", "L", "M"),
        "single_cell_gene_expression": ("N", "O", "P", "Q"),
        "pdo_gene_expression": ("R", "S", "T", "U"),
    }
    subtype_order = tuple(SUBTYPE_BLOCKS_5A)
    records: list[dict[str, object]] = []
    for row in range(5, 29):
        source_label = _required(cells, row, "A")
        if source_label not in KINASE_LABEL_TO_HGNC:
            raise ValueError(f"unmapped Table 5e kinase label {source_label}")
        subtype = _required(cells, row, "B")
        modality_scores = {
            modality: {
                subtype_id: _number(cells, row, column)
                for subtype_id, column in zip(subtype_order, columns, strict=True)
            }
            for modality, columns in modality_columns.items()
        }
        records.append(
            {
                "hgnc_symbol": KINASE_LABEL_TO_HGNC[source_label],
                "kinase_activity_mww_score": _number(cells, row, "C"),
                "log2fc_activity_subtype_vs_others": _number(cells, row, "D"),
                "modality_mww_scores": modality_scores,
                "p_value": _number(cells, row, "E"),
                "source_kinase_label": source_label,
                "source_row_id": f"table5e:{row:05d}",
                "source_row_number": row,
                "subtype": subtype,
            }
        )
    if (
        len(records) != EXPECTED_MASTER_KINASES
        or len({item["hgnc_symbol"] for item in records}) != EXPECTED_MASTER_KINASES
    ):
        raise ValueError("Table 5e must resolve to 24 unique HGNC kinase symbols")
    counts = {
        subtype: sum(item["subtype"] == subtype for item in records)
        for subtype in EXPECTED_SUBTYPE_KINASE_COUNTS
    }
    if counts != EXPECTED_SUBTYPE_KINASE_COUNTS:
        raise ValueError("unexpected Table 5e subtype kinase counts")
    return records


def _signature_edges(
    cells: dict[tuple[int, str], str],
    masters: list[dict[str, object]],
    background_labels: set[str],
) -> list[dict[str, object]]:
    if not str(cells.get((2, "A"), "")).startswith(
        "Supplementary Table 5d: Most active kinases from SPHINKS/MK approach"
    ):
        raise ValueError("unexpected Supplementary Table 5d title")
    expected_by_subtype = {
        subtype: {
            str(item["source_kinase_label"]) for item in masters if item["subtype"] == subtype
        }
        for subtype in SUBTYPE_BLOCKS_5D
    }
    records: list[dict[str, object]] = []
    encountered: dict[str, set[str]] = {subtype: set() for subtype in SUBTYPE_BLOCKS_5D}
    for subtype, (
        kinase_col,
        gene_col,
        protein_col,
        svm_col,
        rho_col,
        known_col,
    ) in SUBTYPE_BLOCKS_5D.items():
        for row in range(5, 1_808):
            block_values = tuple(
                cells.get((row, column), "")
                for column in (kinase_col, gene_col, protein_col, svm_col, rho_col, known_col)
            )
            if not any(block_values):
                continue
            if not all(block_values):
                raise ValueError(f"partially populated Table 5d source block at row {row}")
            source_kinase = block_values[0]
            encountered[subtype].add(source_kinase)
            if source_kinase not in expected_by_subtype[subtype]:
                raise ValueError(
                    f"Table 5d kinase {source_kinase} is not a Table 5e {subtype} master"
                )
            source_site = _required(cells, row, gene_col)
            if source_site not in background_labels:
                raise ValueError(
                    f"Table 5d target is absent from Table 5a background: {source_site}"
                )
            known = _required(cells, row, known_col)
            if known not in {"yes", "no"}:
                raise ValueError(f"invalid phosphosite-plus value at {known_col}{row}")
            records.append(
                {
                    "hgnc_symbol": KINASE_LABEL_TO_HGNC[source_kinase],
                    "known_phosphosite_plus_substrate": known == "yes",
                    "rho_spearman": _number(cells, row, rho_col),
                    "source_kinase_label": source_kinase,
                    "source_row_id": f"table5d:{subtype}:{row:05d}",
                    "source_row_number": row,
                    "source_site_label": source_site,
                    "source_target_protein_label": _required(cells, row, protein_col),
                    "subtype": subtype,
                    "svm_probability": _number(cells, row, svm_col),
                }
            )
    if encountered != expected_by_subtype:
        raise ValueError("Table 5d kinase inventory does not match Table 5e")
    source_row_ids = [str(item["source_row_id"]) for item in records]
    if len(source_row_ids) != len(set(source_row_ids)):
        raise ValueError("Table 5d source row identifiers are not unique")
    return records


def build_manifest(source: Path) -> dict[str, object]:
    """Build the canonical manifest after validating the pinned source workbook."""

    if source.stat().st_size != SOURCE_SIZE_BYTES:
        raise ValueError(
            f"source size mismatch: expected {SOURCE_SIZE_BYTES}, got {source.stat().st_size}"
        )
    actual_sha = _sha256(source)
    if actual_sha != SOURCE_SHA256:
        raise ValueError(f"source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha}")
    with zipfile.ZipFile(source) as archive:
        strings = _shared_strings(archive)
        paths = _worksheet_paths(archive)
        selected: dict[str, tuple[dict[tuple[int, str], str], str]] = {}
        for table in ("Table 5a", "Table 5d", "Table 5e"):
            matches = [name for name in paths if table in name]
            if len(matches) != 1:
                raise ValueError(f"expected exactly one worksheet for {table}")
            selected[table] = _worksheet_cells(archive, paths[matches[0]], strings)
    expected_dimensions = {"Table 5a": "A1:W34102", "Table 5d": "A1:AL1807", "Table 5e": "A1:AE28"}
    for table, expected in expected_dimensions.items():
        if selected[table][1] != expected:
            raise ValueError(f"unexpected {table} worksheet dimension")
    background = _background_manifest(selected["Table 5a"][0])
    masters = _master_kinases(selected["Table 5e"][0])
    background_labels = cast("list[str]", background["labels"])
    edges = _signature_edges(
        selected["Table 5d"][0],
        masters,
        set(background_labels),
    )
    alias_records = [
        {"hgnc_symbol": symbol, "source_kinase_label": label}
        for label, symbol in KINASE_LABEL_TO_HGNC.items()
    ]
    return {
        "background": background,
        "kinase_label_normalization": {
            "aliases": alias_records,
            "authority": "HGNC approved gene symbols",
            "mapping_digest": _canonical_digest(alias_records),
            "policy": (
                "exact paper labels are retained and mapped through this closed, "
                "profile-bound 24-label table"
            ),
        },
        "master_kinases": masters,
        "schema_version": "sphinks-gbm-master-kinase-catalog/1.0.0",
        "signature_edges": edges,
        "source": {
            "article_doi": ARTICLE_DOI,
            "article_title": ARTICLE_TITLE,
            "article_authors": "Migliozzi et al.",
            "article_year": 2023,
            "copyright": "© The Author(s) 2023",
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "pmcid": "PMC9970878",
            "source_filename": "43018_2022_510_MOESM2_ESM.xlsx",
            "source_sha256": f"sha256:{SOURCE_SHA256}",
            "source_size_bytes": SOURCE_SIZE_BYTES,
            "source_url": SOURCE_URL,
            "source_archive_url": SOURCE_ARCHIVE_URL,
            "third_party_notice": (
                "Third-party material follows the credit lines in the source article; the "
                "PhosphoSitePlus-derived yes/no flag is retained for provenance but receives "
                "no computational privilege in GLIO-PROTEOGEN."
            ),
            "transformation_notice": (
                "Adapted projection: Supplementary Tables 5a, 5d, and 5e were extracted into "
                "canonical sorted JSON; paper kinase labels were mapped through a closed HGNC "
                "table; repeated source rows were retained with row identities. The independent "
                "GLIO-PROTEOGEN concordance estimator is newly authored and is not SPHINKS/MK."
            ),
            "tables": [
                "Supplementary Table 5a",
                "Supplementary Table 5d",
                "Supplementary Table 5e",
            ],
        },
        "source_digests": {
            "background_label_digest": background["label_digest"],
            "background_tuple_digest": background["tuple_digest"],
            "master_kinase_digest": _canonical_digest(masters),
            "signature_edge_digest": _canonical_digest(edges),
        },
    }


def _download_bounded(url: str, maximum_bytes: int) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("supplement downloads require HTTPS")
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "glio-proteogen-sphinks-importer/1.0"},
    )
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
        declared_length = response.headers.get("Content-Length")
        if declared_length is not None and int(declared_length) > maximum_bytes:
            raise ValueError("supplement download exceeds the bounded byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(1024 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError("supplement download exceeds the bounded byte limit")
            chunks.append(chunk)
        return b"".join(chunks)


def _download_with_retry(url: str, maximum_bytes: int) -> bytes:
    last_error: OSError | TimeoutError | None = None
    for delay in DOWNLOAD_RETRY_BACKOFF_SECONDS:
        if delay:
            time.sleep(delay)
        try:
            return _download_bounded(url, maximum_bytes)
        except (OSError, TimeoutError) as error:
            last_error = error
    raise RuntimeError(
        "bounded Europe PMC supplement download failed after three deterministic attempts"
    ) from last_error


def _download_source(destination: Path) -> None:
    try:
        direct = _download_bounded(SOURCE_URL, SOURCE_SIZE_BYTES + 1)
    except (OSError, TimeoutError, ValueError):
        direct = b""
    if len(direct) == SOURCE_SIZE_BYTES and hashlib.sha256(direct).hexdigest() == SOURCE_SHA256:
        destination.write_bytes(direct)
        return
    archive_bytes = _download_with_retry(SOURCE_ARCHIVE_URL, MAX_SUPPLEMENT_ARCHIVE_BYTES)
    _extract_source_archive(archive_bytes, destination)


def _extract_source_archive(archive_bytes: bytes, destination: Path) -> None:
    if len(archive_bytes) > MAX_SUPPLEMENT_ARCHIVE_BYTES:
        raise ValueError("supplement archive exceeds the bounded byte limit")
    target_basename = "43018_2022_510_MOESM2_ESM.xlsx"
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        matches = [
            item
            for item in archive.infolist()
            if PurePosixPath(item.filename).name == target_basename
        ]
        if len(matches) != 1:
            raise ValueError("supplement archive must contain exactly one pinned source basename")
        member = matches[0]
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or member.is_dir() or member.flag_bits & 1:
            raise ValueError("unsafe or encrypted pinned source member in Europe PMC archive")
        if member.file_size != SOURCE_SIZE_BYTES:
            raise ValueError("pinned source member size mismatch in Europe PMC archive")
        digest = hashlib.sha256()
        total = 0
        with archive.open(member) as source_stream, destination.open("wb") as output_stream:
            while True:
                chunk = source_stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > SOURCE_SIZE_BYTES:
                    raise ValueError("pinned source member exceeded its exact byte limit")
                digest.update(chunk)
                output_stream.write(chunk)
        if total != SOURCE_SIZE_BYTES or digest.hexdigest() != SOURCE_SHA256:
            raise ValueError("pinned source member digest mismatch in Europe PMC archive")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--source", type=Path, help="Previously downloaded pinned XLSX")
    source_group.add_argument(
        "--source-archive",
        type=Path,
        help="Previously downloaded bounded Europe PMC supplementary ZIP",
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.source is None:
        with tempfile.TemporaryDirectory(prefix="glio-sphinks-") as directory:
            source = Path(directory) / "43018_2022_510_MOESM2_ESM.xlsx"
            if arguments.source_archive is None:
                _download_source(source)
            else:
                if arguments.source_archive.stat().st_size > MAX_SUPPLEMENT_ARCHIVE_BYTES:
                    raise ValueError("local supplement archive exceeds the bounded byte limit")
                _extract_source_archive(arguments.source_archive.read_bytes(), source)
            manifest = build_manifest(source)
    else:
        manifest = build_manifest(arguments.source)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


if __name__ == "__main__":
    main()
