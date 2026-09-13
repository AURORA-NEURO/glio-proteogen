# ruff: noqa: C901, S314, T201, TRY003
"""Verify the exact CPTAC GBM Table S2/S3 sources and emit a safe receipt.

The receipt contains only public source metadata and workbook structure. It never
copies worksheet cells, sample headers, patient identifiers, or identifier-derived
digests. The source workbooks remain external and are verified again immediately
before the receipt is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final
from xml.etree import ElementTree as ET

SOURCE_LOCK_SCHEMA: Final = "glio-cptac-gbm-supplement-source-lock/1.0.0"
ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/"
PAPER_DOI: Final = "10.1016/j.ccell.2021.01.006"
_MAIN_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_DIMENSION_RE: Final = re.compile(rb'<dimension\s+ref="([A-Z]+[0-9]+(?::[A-Z]+[0-9]+)?)"')
_MAX_ZIP_ENTRIES: Final = 2_048
_MAX_UNCOMPRESSED_BYTES: Final = 2_000_000_000
_MAX_CONTROL_XML_BYTES: Final = 2_097_152
_SHEET_PREFIX_BYTES: Final = 262_144


@dataclass(frozen=True, slots=True)
class SupplementLock:
    label: str
    official_filename: str
    bytes: int
    sha256: str
    source_url: str
    sheet_dimensions: tuple[tuple[str, str], ...]


TABLE_S2_LOCK: Final = SupplementLock(
    label="table_s2_processed_data",
    official_filename="NIHMS1665743-supplement-3.xlsx",
    bytes=129_239_538,
    sha256="59c33b6140c88c394da50fd7461774233074dda12361df7989fe51b8b8e28a13",
    source_url=(
        "https://pmc.ncbi.nlm.nih.gov/articles/instance/8044053/bin/"
        "NIHMS1665743-supplement-3.xlsx"
    ),
    sheet_dimensions=(
        ("README", "A1:C17"),
        ("somatic_mutation", "A1:DT6758"),
        ("somatic_cnv_segment", "A1:F54716"),
        ("somatic_cnv_gene_gistic", "A1:CV27218"),
        ("structural_variant_manta", "A1:Q10622"),
        ("gene_expression_fpkm_uq", "A1:DH45915"),
        ("circular_rna_fpkm_uq", "A1:CY3671"),
        ("mirna_mature_tpm", "A1:DK2884"),
        ("proteome_normalized", "A1:DH10999"),
        ("phosphoproteome_normalized", "A1:DI70331"),
        ("acetylome_normalized", "A1:DI12456"),
        ("lipidome_positive_normalized", "A1:CJ335"),
        ("lipidome_negative_normalized", "A1:CJ249"),
        ("metabolome_normalized", "A1:CJ135"),
        ("cbttc_proteome_normalized", "A1:AQ8"),
        ("cbttc_phospho_normalized", "A1:AS2"),
    ),
)

TABLE_S3_LOCK: Final = SupplementLock(
    label="table_s3_published_summaries",
    official_filename="NIHMS1665743-supplement-4.xlsx",
    bytes=357_622,
    sha256="098b596756a84c4744b934f25dc5b9a1e49f992827e2d1223179dfb4655f08f5",
    source_url=(
        "https://pmc.ncbi.nlm.nih.gov/articles/instance/8044053/bin/"
        "NIHMS1665743-supplement-4.xlsx"
    ),
    sheet_dimensions=(
        ("README", "A1:C5"),
        ("nmf_features", "A1:F2261"),
        ("top50_de_mirnas", "A1:E51"),
        ("iProFun_rna_protein", "A1:E8259"),
    ),
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_exact_file(path: Path, lock: SupplementLock) -> None:
    try:
        before = path.stat()
    except FileNotFoundError as error:
        raise ValueError(f"{lock.label} source file does not exist") from error
    if not path.is_file():
        raise ValueError(f"{lock.label} source path is not a regular file")
    if before.st_size != lock.bytes:
        raise ValueError(f"{lock.label} byte length does not match the source lock")
    observed = _sha256(path)
    after = path.stat()
    if before.st_dev != after.st_dev or before.st_ino != after.st_ino:
        raise ValueError(f"{lock.label} source identity changed during verification")
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f"{lock.label} source changed during verification")
    if observed != lock.sha256:
        raise ValueError(f"{lock.label} SHA-256 does not match the source lock")


def _read_bounded(archive: zipfile.ZipFile, name: str, max_bytes: int) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise ValueError(f"workbook omitted required member {name}") from error
    if info.file_size > max_bytes:
        raise ValueError(f"workbook member {name} exceeds its structural byte limit")
    data = archive.read(info)
    if len(data) != info.file_size:
        raise ValueError(f"workbook member {name} was truncated")
    return data


def _normalized_sheet_target(target: str) -> str:
    target_path = PurePosixPath(target)
    normalized = (
        str(target_path).lstrip("/")
        if target_path.is_absolute()
        else str(PurePosixPath("xl") / target_path)
    )
    if not normalized.startswith("xl/worksheets/") or ".." in PurePosixPath(normalized).parts:
        raise ValueError("workbook relationship escaped the worksheet namespace")
    return normalized


def _workbook_dimensions(path: Path) -> tuple[tuple[str, str], ...]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("source is not a readable XLSX workbook") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ZIP_ENTRIES:
            raise ValueError("workbook contains too many ZIP members")
        if sum(info.file_size for info in infos) > _MAX_UNCOMPRESSED_BYTES:
            raise ValueError("workbook uncompressed size exceeds the structural limit")
        # XML is parsed only after the entire workbook matches its exact SHA-256 lock;
        # control members and total expansion are also bounded above.
        workbook_root = ET.fromstring(
            _read_bounded(archive, "xl/workbook.xml", _MAX_CONTROL_XML_BYTES)
        )
        rels_root = ET.fromstring(
            _read_bounded(archive, "xl/_rels/workbook.xml.rels", _MAX_CONTROL_XML_BYTES)
        )
        relationships: dict[str, str] = {}
        for relationship in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            if relationship.attrib.get("TargetMode") == "External":
                continue
            if not relationship.attrib.get("Type", "").endswith("/worksheet"):
                continue
            relationship_id = relationship.attrib.get("Id")
            target = relationship.attrib.get("Target")
            if relationship_id is not None and target is not None:
                relationships[relationship_id] = _normalized_sheet_target(target)

        result: list[tuple[str, str]] = []
        names: set[str] = set()
        for sheet in workbook_root.findall(f".//{{{_MAIN_NS}}}sheet"):
            name = sheet.attrib.get("name")
            relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
            if not name or not relationship_id or relationship_id not in relationships:
                raise ValueError("workbook sheet relationship is incomplete")
            if name in names:
                raise ValueError("workbook contains duplicate sheet names")
            names.add(name)
            member_name = relationships[relationship_id]
            try:
                with archive.open(member_name) as stream:
                    prefix = stream.read(_SHEET_PREFIX_BYTES)
            except KeyError as error:
                raise ValueError("workbook worksheet member is missing") from error
            match = _DIMENSION_RE.search(prefix)
            if match is None:
                raise ValueError(f"workbook sheet {name} omitted its bounded dimension")
            result.append((name, match.group(1).decode("ascii")))
        return tuple(result)


def _verify_source(path: Path, lock: SupplementLock) -> None:
    _verify_exact_file(path, lock)
    if _workbook_dimensions(path) != lock.sheet_dimensions:
        raise ValueError(f"{lock.label} workbook structure does not match the source lock")


def _file_receipt(lock: SupplementLock) -> dict[str, object]:
    return {
        "label": lock.label,
        "official_filename": lock.official_filename,
        "bytes": lock.bytes,
        "sha256": f"sha256:{lock.sha256}",
        "source_url": lock.source_url,
        "sheet_dimensions": [
            {"sheet": sheet, "dimension": dimension}
            for sheet, dimension in lock.sheet_dimensions
        ],
    }


def capture(table_s2: Path, table_s3: Path, destination: Path) -> dict[str, object]:
    """Verify both official workbooks twice and write a cell-free canonical receipt."""

    _verify_source(table_s2, TABLE_S2_LOCK)
    _verify_source(table_s3, TABLE_S3_LOCK)
    receipt: dict[str, object] = {
        "schema_version": SOURCE_LOCK_SCHEMA,
        "paper": {"doi": PAPER_DOI, "article_url": ARTICLE_URL},
        "sources": {
            "table_s2": _file_receipt(TABLE_S2_LOCK),
            "table_s3": _file_receipt(TABLE_S3_LOCK),
        },
        "privacy": {
            "worksheet_cells_emitted": False,
            "sample_headers_emitted": False,
            "patient_identifiers_emitted": False,
            "identifier_derived_digests_emitted": False,
        },
        "scientific_semantics": {
            "source_status": "captured_not_admitted",
            "fit_status": "not_fitted",
            "table_s3_zero_interpretation": "published_positive_call_not_reported",
            "claim_ceiling": "source_structure_and_integrity_only",
            "research_use_only": True,
            "non_prescriptive": True,
        },
    }
    _verify_source(table_s2, TABLE_S2_LOCK)
    _verify_source(table_s3, TABLE_S3_LOCK)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_bytes(receipt))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-s2", type=Path, required=True)
    parser.add_argument("--table-s3", type=Path, required=True)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    receipt = capture(arguments.table_s2, arguments.table_s3, arguments.destination)
    sources = receipt["sources"]
    if not isinstance(sources, dict):
        raise TypeError("capture receipt sources are malformed")
    print(
        json.dumps(
            {
                "destination": str(arguments.destination),
                "bytes": arguments.destination.stat().st_size,
                "sources": sorted(sources),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
