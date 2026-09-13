# ruff: noqa: C901, TRY003
"""Reproducibly import Neftel et al. Cell 2019 Supplementary Table S2.

The generated runtime artifact preserves the authors' symbols and ranks exactly.
HGNC aliases are recorded in separate fields; this importer never rewrites source data.
It intentionally uses only the Python standard library so maintainers can reproduce the
artifact without adding a spreadsheet parser to the application's dependency graph.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Final

SOURCE_URL: Final = (
    "https://ars.els-cdn.com/content/image/1-s2.0-S0092867419306877-mmc2.xlsx"
)
SOURCE_SHA256: Final = "208e73ab3d22c494caf85c867d69dc6be38df3fc62ab1f043d7fcc5441066277"
HGNC_SOURCE_SHA256: Final = "854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
PROGRAM_COLUMNS: Final = (
    ("A", "MES2"),
    ("B", "MES1"),
    ("C", "AC"),
    ("D", "OPC"),
    ("E", "NPC1"),
    ("F", "NPC2"),
    ("G", "G1/S"),
    ("H", "G2/M"),
)
EXPECTED_COUNTS: Final = {
    "MES2": 50,
    "MES1": 50,
    "AC": 39,
    "OPC": 50,
    "NPC1": 50,
    "NPC2": 50,
    "G1/S": 29,
    "G2/M": 45,
}
ALIASES: Final = {
    "WARS": "WARS1",
    "ERO1L": "ERO1A",
    "C8orf4": "TCIM",
    "METTL7B": "TMT1B",
    "PPAP2B": "PLPP3",
    "LPPR1": "PLPPR1",
    "TMEM206": "PACC1",
    "HRASLS": "PLAAT1",
    "HN1": "JPT1",
    "GPR56": "ADGRG1",
    "HMP19": "NSG2",
    "SEPT3": "SEPTIN3",
    "KIAA0101": "PCLAF",
    "HIST1H4C": "H4C3",
    "MLF1IP": "CENPU",
    "H2AFZ": "H2AZ1",
}
UNSUPPORTED_NON_PROTEIN_LOCI: Final = frozenset(
    {"SOX2-OT", "MIAT", "DLX6-AS1", "TMEM161B-AS1", "LOC150568"}
)
_XML_NS: Final = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


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


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))  # noqa: S314
    return [
        "".join(node.text or "" for node in item.findall(".//m:t", _XML_NS))
        for item in root.findall("m:si", _XML_NS)
    ]


def _table_cells(source: Path) -> dict[tuple[int, str], str]:
    with zipfile.ZipFile(source) as archive:
        strings = _shared_strings(archive)
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))  # noqa: S314
    cells: dict[tuple[int, str], str] = {}
    for cell in root.findall(".//m:c", _XML_NS):
        reference = cell.attrib["r"]
        column_match = re.match(r"[A-Z]+", reference)
        row_match = re.search(r"\d+", reference)
        value = cell.find("m:v", _XML_NS)
        if column_match is None or row_match is None or value is None or value.text is None:
            continue
        raw_value = strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
        cells[(int(row_match.group()), column_match.group())] = raw_value
    return cells


def _hgnc_records(hgnc_source: Path) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    actual_sha = _sha256(hgnc_source)
    if actual_sha != HGNC_SOURCE_SHA256:
        raise ValueError(
            f"HGNC SHA-256 mismatch: expected {HGNC_SOURCE_SHA256}, got {actual_sha}"
        )
    by_symbol: dict[str, dict[str, str]] = {}
    aliases: dict[str, set[str]] = {}
    with hgnc_source.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            symbol = row["symbol"]
            by_symbol[symbol] = row
            for field in ("prev_symbol", "alias_symbol"):
                for alias in filter(None, row[field].split("|")):
                    aliases.setdefault(alias, set()).add(symbol)
    return by_symbol, aliases


def build_manifest(source: Path, hgnc_source: Path) -> dict[str, object]:
    """Build the canonical manifest after validating the pinned source workbook."""

    actual_sha = _sha256(source)
    if actual_sha != SOURCE_SHA256:
        raise ValueError(f"source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha}")
    cells = _table_cells(source)
    hgnc_by_symbol, hgnc_aliases = _hgnc_records(hgnc_source)
    protein_background_symbols = sorted(
        symbol for symbol, record in hgnc_by_symbol.items() if record["uniprot_ids"]
    )
    protein_background_digest = _canonical_digest(protein_background_symbols)
    if cells.get((1, "A")) != "Table S2. Meta-module gene lists.":
        raise ValueError("unexpected Table S2 title")
    programs: list[dict[str, object]] = []
    encountered_unsupported: set[str] = set()
    for column, program_id in PROGRAM_COLUMNS:
        if cells.get((5, column)) != program_id:
            raise ValueError(f"unexpected program heading in column {column}")
        raw_symbols = [cells[(row, column)] for row in range(6, 56) if (row, column) in cells]
        if len(raw_symbols) != EXPECTED_COUNTS[program_id]:
            raise ValueError(f"unexpected marker count for {program_id}")
        if len(raw_symbols) != len(set(raw_symbols)):
            raise ValueError(f"duplicate marker within {program_id}")
        markers: list[dict[str, object]] = []
        for rank, raw_symbol in enumerate(raw_symbols, start=1):
            normalized_symbol = ALIASES.get(raw_symbol, raw_symbol)
            record = hgnc_by_symbol.get(normalized_symbol)
            uniprot_ids = tuple(
                filter(None, record["uniprot_ids"].split("|"))
            ) if record is not None else ()
            eligible = bool(uniprot_ids)
            if not eligible:
                encountered_unsupported.add(raw_symbol)
            markers.append(
                {
                    "hgnc_id": None if record is None else record["hgnc_id"],
                    "protein_eligible": eligible,
                    "rank": rank,
                    "raw_symbol": raw_symbol,
                    "normalized_symbol": normalized_symbol,
                    "uniprot_ids": list(uniprot_ids),
                }
            )
        programs.append(
            {
                "markers": markers,
                "program_id": program_id,
                "source_column": column,
                "source_marker_count": len(markers),
            }
        )
    if encountered_unsupported != set(UNSUPPORTED_NON_PROTEIN_LOCI):
        raise ValueError("unsupported non-protein locus inventory does not match the source")
    alias_records: list[dict[str, str]] = []
    for raw, normalized in sorted(ALIASES.items()):
        record = hgnc_by_symbol.get(normalized)
        if record is None or not record["uniprot_ids"]:
            raise ValueError(f"normalized HGNC protein record missing for {raw}->{normalized}")
        if normalized not in hgnc_aliases.get(raw, set()):
            raise ValueError(f"HGNC previous/alias-symbol mapping missing for {raw}->{normalized}")
        mapping_basis = (
            "previous_symbol"
            if raw in set(filter(None, record["prev_symbol"].split("|")))
            else "alias_symbol"
        )
        alias_records.append(
            {
                "mapping_basis": mapping_basis,
                "normalized_symbol": normalized,
                "raw_symbol": raw,
            }
        )
    return {
        "normalization": {
            "alias_policy": "exact_case_sensitive_hgnc_previous_symbol_map",
            "aliases": alias_records,
            "authority": "HGNC complete set",
            "authority_license": "CC0-1.0",
            "authority_sha256": f"sha256:{HGNC_SOURCE_SHA256}",
            "authority_url": (
                "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/"
                "hgnc_complete_set.txt"
            ),
            "derivation": (
                "approved symbols, previous/alias mappings, and UniProt eligibility "
                "validated against the pinned HGNC TSV"
            ),
            "protein_background_count": len(protein_background_symbols),
            "protein_background_digest": protein_background_digest,
            "protein_background_policy": (
                "exact approved HGNC symbols carrying at least one UniProt identifier in the "
                "pinned authority; only these normalized identifiers may enter rank background"
            ),
            "protein_background_symbols": protein_background_symbols,
            "unsupported_non_protein_loci": sorted(UNSUPPORTED_NON_PROTEIN_LOCI),
        },
        "programs": programs,
        "schema_version": "neftel-table-s2-protein-catalog/1.0.0",
        "source": {
            "article_doi": "10.1016/j.cell.2019.06.024",
            "article_title": (
                "An Integrative Model of Cellular States, Plasticity, and Genetics for "
                "Glioblastoma"
            ),
            "selection_note": (
                "Each meta-module contains genes with average log-ratio above 2, restricted "
                "to at most 50 genes and listed by descending average log-ratio."
            ),
            "source_filename": "1-s2.0-S0092867419306877-mmc2.xlsx",
            "source_sha256": f"sha256:{SOURCE_SHA256}",
            "source_size_bytes": source.stat().st_size,
            "source_url": SOURCE_URL,
            "table": "Table S2",
        },
    }


def _download_source(destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "glio-proteogen-neftel-importer/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        destination.write_bytes(response.read())


def _download_hgnc(destination: Path) -> None:
    url = (
        "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/"
        "hgnc_complete_set.txt"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "glio-proteogen-neftel-importer/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        destination.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Previously downloaded pinned XLSX")
    parser.add_argument("--hgnc-source", type=Path, help="Pinned HGNC complete-set TSV")
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.source is None or arguments.hgnc_source is None:
        with tempfile.TemporaryDirectory(prefix="glio-neftel-") as directory:
            source = arguments.source or Path(directory) / "table-s2.xlsx"
            hgnc_source = arguments.hgnc_source or Path(directory) / "hgnc-complete-set.txt"
            if arguments.source is None:
                _download_source(source)
            if arguments.hgnc_source is None:
                _download_hgnc(hgnc_source)
            manifest = build_manifest(source, hgnc_source)
    else:
        manifest = build_manifest(arguments.source, arguments.hgnc_source)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
