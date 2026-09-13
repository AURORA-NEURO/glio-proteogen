# ruff: noqa: C901, PLR0912, PLR0915, PLR2004, T201, TRY003, TRY004
"""Fit a de-identified protein transition axis from PDC000514.

This is a deliberately source-locked importer, not a general PDC parser.  It consumes
the three exact PDC protein artifacts used by Kim et al. plus a canonical official
versioned metadata response, verifies their byte identity, reconciles the biospecimen
and file manifests with the TMT inputs, and emits coefficients rather than raw patient
measurements.  Blank cells remain missing throughout; no imputation occurs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple, cast

import numpy as np
import numpy.typing as npt

MODEL_ID: Final = "kncc-paired-protein-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-paired-protein-transition-artifact/1.0.0"
PDC_STUDY_ID: Final = "PDC000514"
PDC_STUDY_VERSION_UUID: Final = "524d5116-b6de-4e36-892a-e35dba7d0170"
PDC_GRAPHQL_ENDPOINT: Final = "https://pdc.cancer.gov/graphql"
PDC_GRAPHQL_API_VERSION: Final = "1.0.0"
PDC_SOURCE_MANIFEST_SCHEMA: Final = "glio-proteogen.pdc000514-source-manifest/1.0.0"
PDC_SOURCE_MANIFEST_FILENAME: Final = "PDC000514.v1.canonical-source-lock.json"
# Filled only after canonical capture; the importer fails closed on both values.
PDC_SOURCE_MANIFEST_BYTES: Final = 1_362_739
PDC_SOURCE_MANIFEST_SHA256: Final = (
    "03d41fffeb04749296a95bd5cd5dd5829ddedc5f8f791941c011b94d6836a247"
)
PDC_STUDY_CATALOG_QUERY: Final = (
    '{ studyCatalog(pdc_study_id: "PDC000514") { pdc_study_id versions { study_id '
    "study_submitter_id submitter_id_name study_shortname study_version is_latest_version } } }"
)
PDC_VERSIONED_BIOSPECIMEN_QUERY: Final = (
    '{ biospecimenPerStudy(study_id: "524d5116-b6de-4e36-892a-e35dba7d0170", '
    "acceptDUA: true) { aliquot_id sample_id case_id aliquot_submitter_id "
    "sample_submitter_id case_submitter_id aliquot_status case_status sample_status "
    "project_name sample_type disease_type primary_site pool taxon } }"
)
PDC_VERSIONED_FILES_QUERY: Final = (
    '{ filesPerStudy(study_id: "524d5116-b6de-4e36-892a-e35dba7d0170", offset: 0, '
    "limit: 25000, acceptDUA: true) { study_id pdc_study_id study_submitter_id study_name "
    "file_id file_name file_submitter_id file_type md5sum file_size data_category "
    "file_format } }"
)
ARTICLE_TITLE: Final = "Integrated proteogenomic characterization of glioblastoma evolution"
ARTICLE_DOI: Final = "10.1016/j.ccell.2023.12.015"
ARTICLE_PMID: Final = "38215747"
ARTICLE_PMCID: Final = "PMC10939876"

PRIMARY_MEASURE: Final = "Unshared Log"
ABLATION_MEASURE: Final = "Log"
AGGREGATE_ROW_LABELS: Final = ("Mean", "Median", "StdDev")

EXPECTED_MATRIX_ROW_LABELS: Final = 11_323
EXPECTED_BIOLOGICAL_GENES: Final = 11_320
EXPECTED_COMPLETE_PAIRS_BEFORE_EXCLUSION: Final = 105
EXPECTED_STRICT_PAIRS: Final = 104
EXPECTED_INCOMPLETE_PATIENTS: Final = 4
EXPECTED_EXCLUDED_SPECIMEN_LABELS: Final = 6
EXPECTED_EXCLUDED_PATIENT_GROUPS: Final = 5
EXPECTED_VERSIONED_BIOSPECIMEN_RECORDS: Final = 216
EXPECTED_VERSIONED_BIOLOGICAL_SPECIMENS: Final = 214
EXPECTED_VERSIONED_FILE_RECORDS: Final = 2_503
EXPECTED_SAMPLE_MAP_ROWS: Final = 624
EXPECTED_ANALYTICAL_SAMPLES: Final = 26
EXPECTED_MEASUREMENT_CHANNELS: Final = 260
EXPECTED_DUPLICATED_SPECIMEN_LABELS: Final = 7
EXPECTED_HGNC_EXACT_APPROVED: Final = 11_232
EXPECTED_HGNC_UNIQUE_ALIAS: Final = 80
EXPECTED_HGNC_AMBIGUOUS: Final = 4
EXPECTED_HGNC_UNRESOLVED: Final = 4
EXPECTED_HGNC_COLLISIONS: Final = 0
EXPECTED_HGNC_ADMITTED: Final = 11_312
HGNC_SOURCE_FILENAME: Final = "hgnc_complete_set.txt"
HGNC_SOURCE_BYTES: Final = 16_948_224
HGNC_SOURCE_SHA256: Final = "854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"

HUBER_K: Final = 1.345
HUBER_MAX_ITERATIONS: Final = 32
HUBER_TOLERANCE: Final = 1.0e-10
MIN_TRAIN_COVERAGE: Final = 0.60
MIN_SCORE_WEIGHT_COVERAGE: Final = 0.50
INTENSITY_FLOOR_QUANTILE: Final = 0.10
MIN_INTENSITY_FLOOR: Final = 1.0e-4
OUTER_FOLDS: Final = 8
INNER_FOLDS: Final = 5
TOP_FEATURE_CANDIDATES: Final = (16, 32, 64, 128, 256, 512)
BOOTSTRAP_REPLICATES: Final = 512
BOOTSTRAP_BATCH_SIZE: Final = 32

SAMPLE_MAP_HEADER: Final = (
    "FileNameRegEx",
    "AnalyticalSample",
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
    "LabelReagent",
    "Ratios",
    "Fraction",
)
TMT_CHANNELS: Final = SAMPLE_MAP_HEADER[2:13]
EXPECTED_RATIOS: Final = (
    "127N/126C,127C/126C,128N/126C,128C/126C,129N/126C,129C/126C,"
    "130N/126C,130C/126C,131N/126C,131C/126C"
)
MATRIX_METADATA_COLUMNS: Final = (
    "NCBIGeneID",
    "Authority",
    "Description",
    "Organism",
    "Chromosome",
    "Locus",
)
SUMMARY_METADATA_COLUMNS: Final = (
    "Spectral Counts",
    "Distinct Peptides",
    "Unshared Peptides",
    "NCBIGeneID",
    "Authority",
    "Description",
    "Organism",
    "Chromosome",
    "Locus",
    "Proteins",
    "Assays",
)

_ENTRY_PATTERN: Final = re.compile(r"^(?P<label>[^:]+):(?P<uuid>[0-9a-f-]{36})$")
_MATRIX_COLUMN_PATTERN: Final = re.compile(
    r"^(?P<measure>Unshared Log|Log) (?P<label>[^:]+):(?P<uuid>[0-9a-f-]{36})/"
    r"ref:(?P<reference>[0-9a-f-]{36})$"
)
_SPECIMEN_PATTERN: Final = re.compile(r"^(?P<patient>KNCC_GBM\d{4})_(?P<time>T[12])$")


class SourceFileLock(NamedTuple):
    filename: str
    uuid: str
    bytes: int
    md5: str
    sha256: str


SOURCE_FILES: Final = (
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Proteome.tmt11.tsv",
        "a07f3432-b1e0-4082-91c1-96bad4a4ac38",
        109_341_696,
        "36d0b951c1aaac1c52faf08d1894b1cb",
        "c8430c9a1fcd87dc16d221904d45d639d9372e5e5c5eb49bdcb5c36e0de183c6",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Proteome.sample.txt",
        "ec09a0de-a5ef-442d-a105-705bb780c734",
        480_961,
        "d8c6d3880dc8a4485ec95ca6fbaf052a",
        "4f0f41c3442ba6fe8dda8c000853bd3c5ded4c191899f08c5ea7c339cf200b71",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Proteome.summary.tsv",
        "604ce993-b140-4552-81cf-18d7ed598e4e",
        7_042_065,
        "8f785aa0bd7d1f727a38f4b60f65c5f2",
        "fcc12209f69dc1c8e2a3fc24c3c885cd6daed4d165f8afebe16f28fada2c591f",
    ),
)


FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class Cohort:
    genes: tuple[str, ...]
    hgnc_ids: tuple[str, ...]
    source_gene_labels: tuple[str, ...]
    mapping_basis: tuple[str, ...]
    patient_groups: tuple[str, ...]
    primary_delta: FloatArray
    ordinary_delta: FloatArray
    unshared_peptides: IntArray
    oracles: dict[str, object]


@dataclass(frozen=True, slots=True)
class AxisFit:
    center: FloatArray
    scale: FloatArray
    support: IntArray
    eligible: BoolArray
    effect: FloatArray
    order: IntArray
    intensity_floor: float
    iterations: int
    converged: bool


class VersionedSourceMetadata(NamedTuple):
    specimen_labels: frozenset[str]
    sample_type_mismatch_patient_groups: frozenset[str]
    oracles: dict[str, object]


def _file_digests(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def verify_source_files(source_dir: Path) -> dict[str, Path]:
    """Verify all exact source UUID/byte/digest locks, failing closed."""

    result: dict[str, Path] = {}
    for lock in SOURCE_FILES:
        path = source_dir / lock.filename
        if not path.is_file():
            raise ValueError(f"missing locked PDC source file: {lock.filename}")
        if path.stat().st_size != lock.bytes:
            raise ValueError(f"source byte-size mismatch: {lock.filename}")
        md5, sha256 = _file_digests(path)
        if md5 != lock.md5 or sha256 != lock.sha256:
            raise ValueError(f"source digest mismatch: {lock.filename}")
        result[lock.filename] = path
    return result


def _object_field(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"PDC source manifest field {key!r} is not an object")
    return cast("dict[str, object]", value)


def _record_array(value: object, key: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"PDC source manifest field {key!r} is not a record array")
    return cast("list[dict[str, object]]", value)


def verify_versioned_source_manifest(source_dir: Path) -> VersionedSourceMetadata:
    """Verify the exact official versioned PDC metadata snapshot and its cohort semantics."""

    path = source_dir / PDC_SOURCE_MANIFEST_FILENAME
    if not path.is_file():
        raise ValueError(f"missing locked PDC source manifest: {PDC_SOURCE_MANIFEST_FILENAME}")
    payload = path.read_bytes()
    if len(payload) != PDC_SOURCE_MANIFEST_BYTES:
        raise ValueError("PDC source manifest byte-size mismatch")
    if hashlib.sha256(payload).hexdigest() != PDC_SOURCE_MANIFEST_SHA256:
        raise ValueError("PDC source manifest SHA-256 mismatch")
    raw = cast("object", json.loads(payload))
    manifest = _object_field(raw, "root")
    if _canonical_bytes(manifest) != payload:
        raise ValueError("PDC source manifest is not canonical JSON")
    if manifest.get("schema_version") != PDC_SOURCE_MANIFEST_SCHEMA:
        raise ValueError("unexpected PDC source manifest schema")

    source = _object_field(manifest.get("source"), "source")
    expected_source = {
        "endpoint": PDC_GRAPHQL_ENDPOINT,
        "api_version": PDC_GRAPHQL_API_VERSION,
        "documentation": "https://pdc.cancer.gov/pdc-docs/api-documentation",
        "pdc_study_id": PDC_STUDY_ID,
        "pdc_study_version_uuid": PDC_STUDY_VERSION_UUID,
    }
    if any(source.get(key) != value for key, value in expected_source.items()):
        raise ValueError("PDC source manifest provenance changed")
    queries = _object_field(manifest.get("query_provenance"), "query_provenance")
    if queries != {
        "study_catalog": PDC_STUDY_CATALOG_QUERY,
        "versioned_biospecimens": PDC_VERSIONED_BIOSPECIMEN_QUERY,
        "versioned_files": PDC_VERSIONED_FILES_QUERY,
    }:
        raise ValueError("PDC source manifest query provenance changed")

    responses = _object_field(manifest.get("responses"), "responses")
    catalog = _record_array(responses.get("study_catalog"), "study_catalog")
    expected_catalog = [
        {
            "pdc_study_id": PDC_STUDY_ID,
            "versions": [
                {
                    "study_id": PDC_STUDY_VERSION_UUID,
                    "study_submitter_id": "KNCC Glioblastoma Evolution - Proteome",
                    "submitter_id_name": "KNCC Glioblastoma Evolution - Proteome",
                    "study_shortname": "KNCC Glioblastoma Evolution - Proteome",
                    "study_version": "1",
                    "is_latest_version": "yes",
                }
            ],
        }
    ]
    if catalog != expected_catalog:
        raise ValueError("PDC study catalog version binding changed")

    files = _record_array(responses.get("versioned_files"), "versioned_files")
    if len(files) != EXPECTED_VERSIONED_FILE_RECORDS:
        raise ValueError("unexpected versioned PDC file-manifest record count")
    file_ids = [str(row.get("file_id", "")) for row in files]
    if len(set(file_ids)) != len(file_ids):
        raise ValueError("duplicate file UUID in versioned PDC file manifest")
    if any(
        row.get("study_id") != PDC_STUDY_VERSION_UUID or row.get("pdc_study_id") != PDC_STUDY_ID
        for row in files
    ):
        raise ValueError("versioned PDC file manifest crosses study versions")
    by_filename: dict[str, dict[str, object]] = {}
    for row in files:
        filename = str(row.get("file_name", ""))
        if filename in {lock.filename for lock in SOURCE_FILES}:
            if filename in by_filename:
                raise ValueError("duplicate locked filename in versioned PDC file manifest")
            by_filename[filename] = row
    for lock in SOURCE_FILES:
        locked_row = by_filename.get(lock.filename)
        if locked_row is None:
            raise ValueError("locked file is absent from versioned PDC file manifest")
        if (
            locked_row.get("file_id") != lock.uuid
            or str(locked_row.get("file_size")) != str(lock.bytes)
            or locked_row.get("md5sum") != lock.md5
        ):
            raise ValueError("locked file identity differs from versioned PDC file manifest")

    biospecimens = _record_array(responses.get("versioned_biospecimens"), "versioned_biospecimens")
    if len(biospecimens) != EXPECTED_VERSIONED_BIOSPECIMEN_RECORDS:
        raise ValueError("unexpected versioned PDC biospecimen record count")
    specimen_rows: dict[str, dict[str, object]] = {}
    mismatch_groups: set[str] = set()
    aliquot_ids: set[str] = set()
    for row in biospecimens:
        aliquot_id = str(row.get("aliquot_id", ""))
        if not aliquot_id or aliquot_id in aliquot_ids:
            raise ValueError("missing or duplicate versioned PDC aliquot UUID")
        aliquot_ids.add(aliquot_id)
        label = str(row.get("sample_submitter_id", ""))
        match = _SPECIMEN_PATTERN.fullmatch(label)
        if match is None:
            continue
        if label in specimen_rows:
            raise ValueError("duplicate biological specimen in versioned PDC metadata")
        patient = match.group("patient")
        if row.get("case_submitter_id") != patient or row.get("aliquot_submitter_id") != label:
            raise ValueError("versioned PDC biospecimen hierarchy is inconsistent")
        expected_type = "Primary Tumor" if match.group("time") == "T1" else "Recurrent Tumor"
        actual_type = row.get("sample_type")
        if actual_type != expected_type:
            if match.group("time") != "T1" or actual_type != "Recurrent Tumor":
                raise ValueError("unexpected PDC sample-type mismatch semantics")
            mismatch_groups.add(patient)
        specimen_rows[label] = row
    if len(specimen_rows) != EXPECTED_VERSIONED_BIOLOGICAL_SPECIMENS:
        raise ValueError("unexpected versioned PDC biological-specimen inventory")
    if len(mismatch_groups) != 1:
        raise ValueError("expected exactly one versioned PDC sample-type mismatch")
    return VersionedSourceMetadata(
        specimen_labels=frozenset(specimen_rows),
        sample_type_mismatch_patient_groups=frozenset(mismatch_groups),
        oracles={
            "official_versioned_biospecimen_records": len(biospecimens),
            "official_versioned_biological_specimen_labels": len(specimen_rows),
            "official_sample_type_mismatch_patient_groups": len(mismatch_groups),
            "official_versioned_file_manifest_records": len(files),
        },
    )


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _hgnc_mapping(
    hgnc_source: Path,
    source_labels: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], IntArray, dict[str, object]]:
    if not hgnc_source.is_file() or hgnc_source.name != HGNC_SOURCE_FILENAME:
        raise ValueError("missing pinned HGNC complete-set authority")
    if hgnc_source.stat().st_size != HGNC_SOURCE_BYTES:
        raise ValueError("HGNC complete-set byte-size mismatch")
    _, actual_sha = _file_digests(hgnc_source)
    if actual_sha != HGNC_SOURCE_SHA256:
        raise ValueError("HGNC complete-set SHA-256 mismatch")

    approved: dict[str, dict[str, str]] = {}
    aliases: dict[str, set[str]] = defaultdict(set)
    with hgnc_source.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"hgnc_id", "symbol", "prev_symbol", "alias_symbol"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("unexpected HGNC complete-set header")
        for row in reader:
            symbol = row["symbol"]
            if symbol in approved:
                raise ValueError("duplicate approved symbol in HGNC authority")
            approved[symbol] = row
            for field in ("prev_symbol", "alias_symbol"):
                for alias in filter(None, row[field].split("|")):
                    aliases[alias].add(symbol)

    candidates: list[tuple[int, str, str, str]] = []
    exact_count = 0
    alias_count = 0
    ambiguous_count = 0
    unresolved_count = 0
    for index, source_label in enumerate(source_labels):
        if source_label in approved:
            candidates.append((index, source_label, source_label, "approved_symbol"))
            exact_count += 1
            continue
        targets = aliases.get(source_label, set())
        if len(targets) == 0:
            unresolved_count += 1
            continue
        if len(targets) != 1:
            ambiguous_count += 1
            continue
        target = next(iter(targets))
        record = approved[target]
        previous = set(filter(None, record["prev_symbol"].split("|")))
        basis = "previous_symbol" if source_label in previous else "alias_symbol"
        candidates.append((index, source_label, target, basis))
        alias_count += 1

    by_target: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
    for candidate in candidates:
        by_target[candidate[2]].append(candidate)
    collisions = {target for target, records in by_target.items() if len(records) > 1}
    admitted = [candidate for candidate in candidates if candidate[2] not in collisions]
    if (
        exact_count != EXPECTED_HGNC_EXACT_APPROVED
        or alias_count != EXPECTED_HGNC_UNIQUE_ALIAS
        or ambiguous_count != EXPECTED_HGNC_AMBIGUOUS
        or unresolved_count != EXPECTED_HGNC_UNRESOLVED
        or len(collisions) != EXPECTED_HGNC_COLLISIONS
        or len(admitted) != EXPECTED_HGNC_ADMITTED
    ):
        raise ValueError("HGNC gene-identity mapping inventory changed")

    mapping_projection = [
        {
            "hgnc_id": approved[target]["hgnc_id"],
            "mapping_basis": basis,
            "source_gene_label": source_label,
            "gene_symbol": target,
        }
        for _, source_label, target, basis in admitted
    ]
    return (
        tuple(item[2] for item in admitted),
        tuple(approved[item[2]]["hgnc_id"] for item in admitted),
        tuple(item[3] for item in admitted),
        np.asarray([item[0] for item in admitted], dtype=np.int64),
        {
            "source_biological_gene_labels": len(source_labels),
            "hgnc_exact_approved_symbols": exact_count,
            "hgnc_unique_previous_or_alias_mappings": alias_count,
            "hgnc_ambiguous_labels_excluded": ambiguous_count,
            "hgnc_unresolved_labels_excluded": unresolved_count,
            "hgnc_mapped_labels_before_collision_exclusion": len(candidates),
            "hgnc_colliding_approved_symbols_excluded": len(collisions),
            "hgnc_admitted_unique_approved_symbols": len(admitted),
            "hgnc_mapping_digest": _canonical_digest(mapping_projection),
        },
    )


def _parse_entry(value: str) -> tuple[str, str]:
    match = _ENTRY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid sample-map channel entry: {value!r}")
    return match.group("label"), match.group("uuid")


def _sample_map_headers(path: Path) -> tuple[set[tuple[str, str, str]], dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != SAMPLE_MAP_HEADER:
            raise ValueError("unexpected PDC sample-map header")
        rows = list(reader)
    if len(rows) != EXPECTED_SAMPLE_MAP_ROWS:
        raise ValueError("unexpected PDC sample-map row count")

    by_analytical: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["Ratios"] != EXPECTED_RATIOS:
            raise ValueError("unexpected PDC TMT ratio grammar")
        by_analytical[row["AnalyticalSample"]].append(row)
    if len(by_analytical) != EXPECTED_ANALYTICAL_SAMPLES:
        raise ValueError("unexpected analytical-sample count")

    expected: set[tuple[str, str, str]] = set()
    for analytical_rows in by_analytical.values():
        fractions = {int(row["Fraction"]) for row in analytical_rows}
        if fractions != set(range(1, 25)):
            raise ValueError("analytical sample does not contain exactly fractions 1..24")
        first = analytical_rows[0]
        stable_fields = (*TMT_CHANNELS, "LabelReagent", "Ratios")
        if any(
            any(row[field] != first[field] for field in stable_fields) for row in analytical_rows
        ):
            raise ValueError("sample-map channel assignment changes between fractions")
        reference_label, reference_uuid = _parse_entry(first["126C"])
        if reference_label != "ref":
            raise ValueError("126C is not the reference channel")
        for channel in TMT_CHANNELS[1:]:
            label, sample_uuid = _parse_entry(first[channel])
            item = (label, sample_uuid, reference_uuid)
            if item in expected:
                raise ValueError("duplicate PDC sample-map measurement UUID")
            expected.add(item)
    if len(expected) != EXPECTED_MEASUREMENT_CHANNELS:
        raise ValueError("unexpected sample-map measurement-channel count")
    return expected, {
        "sample_map_rows": len(rows),
        "analytical_samples": len(by_analytical),
        "fractions_per_analytical_sample": 24,
        "measurement_channels_per_measure": len(expected),
    }


def _measurement_columns(
    header: list[str],
    expected: set[tuple[str, str, str]],
) -> tuple[dict[str, dict[str, list[int]]], dict[str, object]]:
    if not header or header[0] != "Gene" or tuple(header[-6:]) != MATRIX_METADATA_COLUMNS:
        raise ValueError("unexpected PDC protein-matrix header")
    result: dict[str, dict[str, list[int]]] = {
        PRIMARY_MEASURE: defaultdict(list),
        ABLATION_MEASURE: defaultdict(list),
    }
    seen: dict[str, set[tuple[str, str, str]]] = {
        PRIMARY_MEASURE: set(),
        ABLATION_MEASURE: set(),
    }
    for index, column in enumerate(header[1:-6], start=1):
        match = _MATRIX_COLUMN_PATTERN.fullmatch(column)
        if match is None:
            raise ValueError(f"unexpected PDC protein measurement column: {column!r}")
        measure = match.group("measure")
        source_key = (match.group("label"), match.group("uuid"), match.group("reference"))
        if source_key not in expected or source_key in seen[measure]:
            raise ValueError("protein matrix does not exactly match the PDC sample map")
        seen[measure].add(source_key)
        result[measure][match.group("label")].append(index)
    if any(items != expected for items in seen.values()):
        raise ValueError("protein matrix omits a sample-map channel")

    real_labels = {
        label for label in result[PRIMARY_MEASURE] if _SPECIMEN_PATTERN.fullmatch(label) is not None
    }
    if set(result[PRIMARY_MEASURE]) != set(result[ABLATION_MEASURE]):
        raise ValueError("Log and Unshared Log specimen inventories differ")
    duplicated = sum(len(result[PRIMARY_MEASURE][label]) > 1 for label in real_labels)
    extra_channels = sum(len(result[PRIMARY_MEASURE][label]) - 1 for label in real_labels)
    if duplicated != EXPECTED_DUPLICATED_SPECIMEN_LABELS or extra_channels != 7:
        raise ValueError("unexpected technical-channel duplication inventory")
    return result, {
        "biological_specimen_labels": len(real_labels),
        "duplicated_specimen_labels": duplicated,
        "extra_technical_channels": extra_channels,
    }


def _strict_patients(
    labels: set[str], metadata: VersionedSourceMetadata
) -> tuple[tuple[str, ...], dict[str, object]]:
    biological_labels = {
        label for label in labels if _SPECIMEN_PATTERN.fullmatch(label) is not None
    }
    if biological_labels != metadata.specimen_labels:
        raise ValueError("protein matrix and versioned PDC biospecimen inventories differ")
    patient_times: dict[str, set[str]] = defaultdict(set)
    for label in biological_labels:
        match = _SPECIMEN_PATTERN.fullmatch(label)
        if match is not None:
            patient_times[match.group("patient")].add(match.group("time"))
    complete = sorted(patient for patient, times in patient_times.items() if times == {"T1", "T2"})
    incomplete = sorted(
        patient for patient, times in patient_times.items() if times != {"T1", "T2"}
    )
    if len(complete) != EXPECTED_COMPLETE_PAIRS_BEFORE_EXCLUSION:
        raise ValueError("unexpected complete T1/T2 pair count")
    if len(incomplete) != EXPECTED_INCOMPLETE_PATIENTS:
        raise ValueError("unexpected incomplete patient count")
    mismatch_groups = metadata.sample_type_mismatch_patient_groups
    if not mismatch_groups.issubset(complete):
        raise ValueError("versioned PDC sample-type mismatch is not a complete matrix pair")
    strict = tuple(patient for patient in complete if patient not in mismatch_groups)
    if len(strict) != EXPECTED_STRICT_PAIRS:
        raise ValueError("unexpected strict T1/T2 pair count")
    excluded_specimen_labels = sum(len(patient_times[patient]) for patient in incomplete) + 2 * len(
        mismatch_groups
    )
    excluded_patient_groups = len(incomplete) + len(mismatch_groups)
    if (
        excluded_specimen_labels != EXPECTED_EXCLUDED_SPECIMEN_LABELS
        or excluded_patient_groups != EXPECTED_EXCLUDED_PATIENT_GROUPS
    ):
        raise ValueError("unexpected strict-pair exclusion inventory")
    return strict, {
        "source_biological_specimen_labels": len(biological_labels),
        "complete_pairs_before_sample_type_exclusion": len(complete),
        "incomplete_patient_groups_excluded": len(incomplete),
        "sample_type_mismatch_patient_groups_excluded": len(mismatch_groups),
        "excluded_specimen_labels": excluded_specimen_labels,
        "excluded_patient_groups": excluded_patient_groups,
        "strict_t1_t2_pairs": len(strict),
    }


def _float_cell(value: str) -> float:
    if value == "":
        return math.nan
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite numeric token in PDC matrix")
    return result


def _collapse_columns(raw: FloatArray, indices: list[int]) -> FloatArray:
    if len(indices) == 1:
        return raw[:, indices[0]].copy()
    if len(indices) != 2:
        raise ValueError("unexpected number of technical channels for one specimen")
    left = raw[:, indices[0]]
    right = raw[:, indices[1]]
    left_valid = np.isfinite(left)
    right_valid = np.isfinite(right)
    result = np.full(left.shape, np.nan, dtype=np.float64)
    result[left_valid & ~right_valid] = left[left_valid & ~right_valid]
    result[right_valid & ~left_valid] = right[right_valid & ~left_valid]
    both = left_valid & right_valid
    result[both] = (left[both] + right[both]) / 2.0
    return result


def _read_matrix(
    path: Path,
    expected_headers: set[tuple[str, str, str]],
    metadata: VersionedSourceMetadata,
) -> tuple[tuple[str, ...], tuple[str, ...], FloatArray, FloatArray, dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        columns, column_oracles = _measurement_columns(header, expected_headers)
        patients, pair_oracles = _strict_patients(set(columns[PRIMARY_MEASURE]), metadata)
        primary_positions = [
            index for indices in columns[PRIMARY_MEASURE].values() for index in indices
        ]
        ordinary_positions = [
            index for indices in columns[ABLATION_MEASURE].values() for index in indices
        ]
        if len(primary_positions) != EXPECTED_MEASUREMENT_CHANNELS:
            raise ValueError("unexpected primary measurement count")

        gene_rows: list[str] = []
        primary_rows: list[FloatArray] = []
        ordinary_rows: list[FloatArray] = []
        aggregate_labels: list[str] = []
        expected_width = len(header)
        for row_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(f"ragged PDC matrix row {row_number}")
            label = row[0]
            if label in AGGREGATE_ROW_LABELS:
                aggregate_labels.append(label)
                continue
            gene_rows.append(label)
            primary_rows.append(
                np.fromiter(
                    (_float_cell(row[index]) for index in primary_positions),
                    dtype=np.float64,
                    count=len(primary_positions),
                )
            )
            ordinary_rows.append(
                np.fromiter(
                    (_float_cell(row[index]) for index in ordinary_positions),
                    dtype=np.float64,
                    count=len(ordinary_positions),
                )
            )

    if tuple(aggregate_labels) != AGGREGATE_ROW_LABELS:
        raise ValueError("PDC aggregate rows are missing, reordered, or duplicated")
    if len(gene_rows) + len(aggregate_labels) != EXPECTED_MATRIX_ROW_LABELS:
        raise ValueError("unexpected matrix row-label count")
    if len(gene_rows) != EXPECTED_BIOLOGICAL_GENES or len(set(gene_rows)) != len(gene_rows):
        raise ValueError("unexpected unique biological-gene inventory")

    primary_raw = np.stack(primary_rows)
    ordinary_raw = np.stack(ordinary_rows)
    primary_index = {position: offset for offset, position in enumerate(primary_positions)}
    ordinary_index = {position: offset for offset, position in enumerate(ordinary_positions)}

    def deltas(raw: FloatArray, measure: str, position_map: dict[int, int]) -> FloatArray:
        output = np.empty((len(patients), len(gene_rows)), dtype=np.float64)
        for patient_index, patient in enumerate(patients):
            t1 = [position_map[index] for index in columns[measure][f"{patient}_T1"]]
            t2 = [position_map[index] for index in columns[measure][f"{patient}_T2"]]
            left = _collapse_columns(raw, t1)
            right = _collapse_columns(raw, t2)
            output[patient_index] = right - left
        return output

    primary_delta = deltas(primary_raw, PRIMARY_MEASURE, primary_index)
    ordinary_delta = deltas(ordinary_raw, ABLATION_MEASURE, ordinary_index)
    oracles = {
        **column_oracles,
        **pair_oracles,
        "matrix_unique_row_labels": len(gene_rows) + len(aggregate_labels),
        "aggregate_rows_excluded_from_fit": list(aggregate_labels),
        "admitted_biological_genes": len(gene_rows),
        "primary_finite_paired_deltas": int(np.isfinite(primary_delta).sum()),
        "ordinary_log_finite_paired_deltas": int(np.isfinite(ordinary_delta).sum()),
    }
    return tuple(gene_rows), patients, primary_delta, ordinary_delta, oracles


def _read_summary(
    path: Path, expected_genes: tuple[str, ...]
) -> tuple[IntArray, dict[str, object]]:
    support: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        if header[0] != "Gene" or tuple(header[-11:]) != SUMMARY_METADATA_COLUMNS:
            raise ValueError("unexpected PDC protein-summary header")
        unshared_index = len(header) - 9
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(f"ragged PDC summary row {row_number}")
            gene = row[0]
            if gene in support:
                raise ValueError(f"duplicate summary gene: {gene}")
            value = int(row[unshared_index])
            if value < 1:
                raise ValueError("summary unshared-peptide support must be positive")
            support[gene] = value
    if set(support) != set(expected_genes) or len(support) != EXPECTED_BIOLOGICAL_GENES:
        raise ValueError("summary and matrix biological-gene inventories differ")
    ordered = np.asarray([support[gene] for gene in expected_genes], dtype=np.int64)
    return ordered, {
        "summary_unique_biological_genes": len(support),
        "unshared_peptide_support_min": int(ordered.min()),
        "unshared_peptide_support_median": float(np.median(ordered)),
        "unshared_peptide_support_max": int(ordered.max()),
    }


def load_cohort(source_dir: Path, hgnc_source: Path) -> Cohort:
    paths = verify_source_files(source_dir)
    versioned_metadata = verify_versioned_source_manifest(source_dir)
    expected_headers, sample_oracles = _sample_map_headers(
        paths["KNCC_Glioblastoma_Evolution_Proteome.sample.txt"]
    )
    genes, patients, primary, ordinary, matrix_oracles = _read_matrix(
        paths["KNCC_Glioblastoma_Evolution_Proteome.tmt11.tsv"],
        expected_headers,
        versioned_metadata,
    )
    source_support, summary_oracles = _read_summary(
        paths["KNCC_Glioblastoma_Evolution_Proteome.summary.tsv"], genes
    )
    approved_genes, hgnc_ids, mapping_basis, admitted_indices, identity_oracles = _hgnc_mapping(
        hgnc_source, genes
    )
    return Cohort(
        genes=approved_genes,
        hgnc_ids=hgnc_ids,
        source_gene_labels=tuple(genes[index] for index in admitted_indices),
        mapping_basis=mapping_basis,
        patient_groups=patients,
        primary_delta=primary[:, admitted_indices],
        ordinary_delta=ordinary[:, admitted_indices],
        unshared_peptides=source_support[admitted_indices],
        oracles={
            **sample_oracles,
            **matrix_oracles,
            **summary_oracles,
            **identity_oracles,
            **versioned_metadata.oracles,
        },
    )


def _fit_axis(delta: FloatArray, genes: tuple[str, ...]) -> AxisFit:
    pair_count = delta.shape[0]
    finite = np.isfinite(delta)
    support = finite.sum(axis=0).astype(np.int64)
    minimum_support = max(3, math.ceil(MIN_TRAIN_COVERAGE * pair_count))
    eligible = support >= minimum_support
    safe = np.where(finite, delta, np.nan)
    with np.errstate(all="ignore"):
        center = np.nanmedian(safe, axis=0)
        mad = np.nanmedian(np.abs(safe - center), axis=0) * 1.4826
    positive_scales = mad[eligible & np.isfinite(mad) & (mad > 0.0)]
    if positive_scales.size == 0:
        intensity_floor = MIN_INTENSITY_FLOOR
    else:
        intensity_floor = max(
            MIN_INTENSITY_FLOOR,
            float(np.quantile(positive_scales, INTENSITY_FLOOR_QUANTILE)),
        )
    support_floor = intensity_floor * np.sqrt(pair_count / np.maximum(support, 1))
    scale = np.maximum(np.where(np.isfinite(mad), mad, 0.0), support_floor)
    scale = np.maximum(scale, intensity_floor)
    center = np.where(np.isfinite(center), center, 0.0)

    converged = False
    iterations = 0
    for step in range(1, HUBER_MAX_ITERATIONS + 1):
        iterations = step
        residual = (delta - center) / scale
        absolute = np.abs(residual)
        weights = np.where(absolute <= HUBER_K, 1.0, HUBER_K / np.maximum(absolute, 1e-15))
        weights = np.where(finite, weights, 0.0)
        denominator = weights.sum(axis=0)
        # The explicit weighted reduction avoids materializing a second masked matrix.
        updated = np.divide(
            (np.where(finite, delta, 0.0) * weights).sum(axis=0),
            np.maximum(denominator, 1e-15),
        )
        updated = np.where(eligible, updated, center)
        change = float(np.max(np.abs(updated - center)))
        center = updated
        if change <= HUBER_TOLERANCE:
            converged = True
            break

    effect = np.zeros(delta.shape[1], dtype=np.float64)
    effect[eligible] = (
        center[eligible]
        / scale[eligible]
        * np.sqrt(support[eligible].astype(np.float64) / pair_count)
    )
    gene_order = np.asarray(genes, dtype=object)
    order = np.lexsort((gene_order, -np.abs(effect))).astype(np.int64)
    order = order[eligible[order]]
    return AxisFit(
        center=center,
        scale=scale,
        support=support,
        eligible=eligible,
        effect=effect,
        order=order,
        intensity_floor=intensity_floor,
        iterations=iterations,
        converged=converged,
    )


def _weights(fit: AxisFit, top_count: int) -> tuple[IntArray, FloatArray]:
    selected = fit.order[: min(top_count, fit.order.size)]
    values = fit.effect[selected].astype(np.float64, copy=True)
    norm = float(np.abs(values).sum())
    if norm <= 0.0:
        return selected, np.zeros_like(values)
    return selected, values / norm


def _project(
    delta: FloatArray,
    scale: FloatArray,
    selected: IntArray,
    weights: FloatArray,
) -> tuple[FloatArray, FloatArray, IntArray]:
    values = delta[:, selected]
    valid = np.isfinite(values)
    absolute_weights = np.abs(weights)
    denominator = valid.astype(np.float64).dot(absolute_weights)
    overlap = valid.sum(axis=1).astype(np.int64)
    numerator = np.where(valid, values / scale[selected], 0.0).dot(weights)
    minimum_features = max(3, math.ceil(MIN_SCORE_WEIGHT_COVERAGE * len(selected)))
    supported = (denominator >= MIN_SCORE_WEIGHT_COVERAGE) & (overlap >= minimum_features)
    scores = np.full(delta.shape[0], np.nan, dtype=np.float64)
    scores[supported] = numerator[supported] / denominator[supported]
    return scores, denominator, overlap


def _score_metrics(scores: FloatArray) -> dict[str, float | int]:
    supported = np.isfinite(scores)
    supported_scores = scores[supported]
    if supported_scores.size == 0:
        return {
            "supported_pairs": 0,
            "abstained_pairs": int(scores.size),
            "direction_accuracy": 0.0,
            "balanced_label_swap_accuracy": 0.0,
            "median_sign_margin": 0.0,
        }
    accuracy = float(np.mean(supported_scores > 0.0))
    return {
        "supported_pairs": int(supported_scores.size),
        "abstained_pairs": int(scores.size - supported_scores.size),
        "direction_accuracy": accuracy,
        # Genuine and within-pair T1/T2-swapped examples are exact sign mirrors.
        "balanced_label_swap_accuracy": accuracy,
        "median_sign_margin": float(np.median(2.0 * supported_scores)),
    }


def _folds(groups: tuple[str, ...], count: int, salt: str) -> tuple[IntArray, ...]:
    ordered = sorted(
        range(len(groups)),
        key=lambda index: hashlib.sha256(f"{salt}:{groups[index]}".encode()).digest(),
    )
    buckets: list[list[int]] = [[] for _ in range(count)]
    for offset, index in enumerate(ordered):
        buckets[offset % count].append(index)
    return tuple(np.asarray(bucket, dtype=np.int64) for bucket in buckets)


def _candidate_result(
    delta: FloatArray,
    genes: tuple[str, ...],
    train: IntArray,
    held: IntArray,
    top_count: int,
) -> tuple[dict[str, float | int], FloatArray]:
    fit = _fit_axis(delta[train], genes)
    selected, weights = _weights(fit, top_count)
    scores, _, _ = _project(delta[held], fit.scale, selected, weights)
    metrics = _score_metrics(scores)
    return {"top_feature_count": len(selected), **metrics}, scores


def _selection_key(metrics: dict[str, float | int]) -> tuple[float, float, float, int]:
    total = int(metrics["supported_pairs"]) + int(metrics["abstained_pairs"])
    abstention = float(metrics["abstained_pairs"]) / max(total, 1)
    return (
        float(metrics["direction_accuracy"]),
        float(metrics["median_sign_margin"]),
        -abstention,
        -int(metrics["top_feature_count"]),
    )


def _nested_cross_validation(cohort: Cohort) -> tuple[int, dict[str, object]]:
    outer = _folds(cohort.patient_groups, OUTER_FOLDS, "kncc-outer-v1")
    all_indices = np.arange(len(cohort.patient_groups), dtype=np.int64)
    outer_results: list[dict[str, object]] = []
    selected_counts: Counter[int] = Counter()
    candidate_records: dict[int, list[dict[str, float | int]]] = defaultdict(list)
    pooled_held_scores: list[float] = []

    for outer_index, held in enumerate(outer):
        train = np.setdiff1d(all_indices, held, assume_unique=True)
        train_groups = tuple(cohort.patient_groups[index] for index in train)
        inner_local = _folds(train_groups, INNER_FOLDS, f"kncc-inner-v1:{outer_index}")
        metrics_by_count: dict[int, list[dict[str, float | int]]] = {
            count: [] for count in TOP_FEATURE_CANDIDATES
        }
        for inner_held_local in inner_local:
            inner_train_local = np.setdiff1d(
                np.arange(train.size, dtype=np.int64), inner_held_local, assume_unique=True
            )
            inner_fit = _fit_axis(cohort.primary_delta[train[inner_train_local]], cohort.genes)
            for top_count in TOP_FEATURE_CANDIDATES:
                inner_selected, inner_weights = _weights(inner_fit, top_count)
                inner_scores, _, _ = _project(
                    cohort.primary_delta[train[inner_held_local]],
                    inner_fit.scale,
                    inner_selected,
                    inner_weights,
                )
                metrics = {
                    "top_feature_count": len(inner_selected),
                    **_score_metrics(inner_scores),
                }
                metrics_by_count[top_count].append(metrics)
                candidate_records[top_count].append(metrics)
        summaries: dict[int, dict[str, float | int]] = {}
        for top_count in TOP_FEATURE_CANDIDATES:
            fold_metrics = metrics_by_count[top_count]
            summaries[top_count] = {
                "top_feature_count": top_count,
                "supported_pairs": sum(int(item["supported_pairs"]) for item in fold_metrics),
                "abstained_pairs": sum(int(item["abstained_pairs"]) for item in fold_metrics),
                "balanced_label_swap_accuracy": float(
                    np.mean([float(item["balanced_label_swap_accuracy"]) for item in fold_metrics])
                ),
                "direction_accuracy": float(
                    np.mean([float(item["direction_accuracy"]) for item in fold_metrics])
                ),
                "median_sign_margin": float(
                    np.median([float(item["median_sign_margin"]) for item in fold_metrics])
                ),
            }
        selected_top = max(
            TOP_FEATURE_CANDIDATES, key=lambda count: _selection_key(summaries[count])
        )
        selected_counts[selected_top] += 1
        outer_metrics, outer_scores = _candidate_result(
            cohort.primary_delta, cohort.genes, train, held, selected_top
        )
        pooled_held_scores.extend(float(value) for value in outer_scores[np.isfinite(outer_scores)])
        outer_results.append(
            {
                "fold_index": outer_index,
                "training_pairs": int(train.size),
                "held_pairs": int(held.size),
                "selected_top_feature_count": selected_top,
                **{
                    key: value for key, value in outer_metrics.items() if key != "top_feature_count"
                },
            }
        )

    selected_top = max(
        TOP_FEATURE_CANDIDATES,
        key=lambda count: (
            selected_counts[count],
            *_selection_key(
                {
                    "top_feature_count": count,
                    "supported_pairs": sum(
                        int(x["supported_pairs"]) for x in candidate_records[count]
                    ),
                    "abstained_pairs": sum(
                        int(x["abstained_pairs"]) for x in candidate_records[count]
                    ),
                    "balanced_label_swap_accuracy": float(
                        np.mean(
                            [
                                float(x["balanced_label_swap_accuracy"])
                                for x in candidate_records[count]
                            ]
                        )
                    ),
                    "direction_accuracy": float(
                        np.mean([float(x["direction_accuracy"]) for x in candidate_records[count]])
                    ),
                    "median_sign_margin": float(
                        np.median(
                            [float(x["median_sign_margin"]) for x in candidate_records[count]]
                        )
                    ),
                }
            ),
        ),
    )
    supported_total = sum(cast("int", item["supported_pairs"]) for item in outer_results)
    abstained_total = sum(cast("int", item["abstained_pairs"]) for item in outer_results)
    weighted_correct = sum(
        cast("float", item["direction_accuracy"]) * cast("int", item["supported_pairs"])
        for item in outer_results
    )
    evaluation = {
        "protocol": "patient-grouped nested cross-validation with all preprocessing refit",
        "outer_fold_count": OUTER_FOLDS,
        "inner_fold_count": INNER_FOLDS,
        "outer_fold_sizes": [len(fold) for fold in outer],
        "selected_top_feature_count": selected_top,
        "outer_selected_top_feature_counts": {
            str(count): selected_counts[count] for count in TOP_FEATURE_CANDIDATES
        },
        "supported_pairs": supported_total,
        "abstained_pairs": abstained_total,
        "direction_accuracy": weighted_correct / max(supported_total, 1),
        "balanced_label_swap_accuracy": weighted_correct / max(supported_total, 1),
        "balanced_label_swap_accuracy_role": (
            "derived symmetry oracle: within-pair T1/T2 label swap is the exact sign mirror "
            "of each genuinely held T2-minus-T1 projection; not independent evidence"
        ),
        "median_sign_margin": float(np.median(2.0 * np.asarray(pooled_held_scores))),
        "median_sign_margin_aggregation": (
            "pooled median across all supported held-pair margins; fold medians are retained "
            "in outer_folds"
        ),
        "outer_folds": outer_results,
    }
    return selected_top, evaluation


def _bootstrap(
    cohort: Cohort,
    fit: AxisFit,
    top_count: int,
    replicates: int,
) -> tuple[FloatArray, FloatArray, dict[str, object]]:
    patient_count, gene_count = cohort.primary_delta.shape
    finite = np.isfinite(cohort.primary_delta)
    residual = (cohort.primary_delta - fit.center) / fit.scale
    clipped = np.clip(residual, -HUBER_K, HUBER_K) * fit.scale
    clipped = np.where(finite, clipped, 0.0)
    inlier = (finite & (np.abs(residual) < HUBER_K)).astype(np.float64)
    finite_float = finite.astype(np.float64)
    seed_material = f"{MODEL_ID}:{SOURCE_FILES[0].sha256}:patient-bootstrap-v1".encode()
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
    coefficient_draws = np.zeros((replicates, gene_count), dtype=np.float32)
    selected_count = np.zeros(gene_count, dtype=np.int64)
    ensemble_rows: list[dict[str, object]] = []
    minimum_support = max(3, math.ceil(MIN_TRAIN_COVERAGE * patient_count))

    for start in range(0, replicates, BOOTSTRAP_BATCH_SIZE):
        batch_size = min(BOOTSTRAP_BATCH_SIZE, replicates - start)
        replicate_seeds = [
            int.from_bytes(
                hashlib.sha256(f"{seed}:replicate:{start + local}".encode()).digest()[:8],
                "big",
            )
            for local in range(batch_size)
        ]
        counts = np.stack(
            [
                np.random.default_rng(replicate_seed).multinomial(
                    patient_count,
                    np.full(patient_count, 1.0 / patient_count),
                )
                for replicate_seed in replicate_seeds
            ]
        ).astype(np.float64)
        numerator = counts.dot(clipped)
        derivative = counts.dot(inlier)
        support = counts.dot(finite_float)
        centers = fit.center + np.divide(
            numerator,
            np.maximum(derivative, 1.0),
        )
        effects = centers / fit.scale * np.sqrt(support / patient_count)
        effects[support < minimum_support] = 0.0
        for local in range(batch_size):
            order = np.lexsort((np.asarray(cohort.genes, dtype=object), -np.abs(effects[local])))
            order = order[effects[local, order] != 0.0][:top_count]
            values = effects[local, order]
            norm = float(np.abs(values).sum())
            if norm <= 0.0:
                raise ValueError("bootstrap replicate has no supported transition coefficients")
            values = values / norm
            draw_index = start + local
            coefficient_draws[draw_index, order] = values.astype(np.float32)
            selected_count[order] += 1
            stable_order = np.argsort(order, kind="stable")
            replicate_projection: dict[str, object] = {
                "replicate_index": draw_index,
                "seed_hex": f"{replicate_seeds[local]:016x}",
                "intercept": 0.0,
                "feature_indices": [int(value) for value in order[stable_order]],
                "coefficients": [_q(value) for value in values[stable_order]],
            }
            ensemble_rows.append(
                {
                    **replicate_projection,
                    "replicate_digest": _canonical_digest(replicate_projection),
                }
            )

    stability = selected_count.astype(np.float64) / replicates
    intervals = np.quantile(coefficient_draws.astype(np.float64), [0.05, 0.5, 0.95], axis=0).T
    bootstrap_summary: dict[str, object] = {
        "method": (
            "deterministic patient multinomial bootstrap with fixed-scale one-step Huber "
            "influence approximation and top-k reselection"
        ),
        "uncertainty_role": (
            "fixed-scale one-step coefficient uncertainty approximation; not model validation"
        ),
        "validation_role": "none",
        "reference_fit_policy": (
            "full-cohort Huber center and transition scales are the frozen reference for every "
            "one-step replicate; only nested cross-validation supplies held-pair evaluation"
        ),
        "seed_derivation": (
            "master: first 64 bits of SHA-256(model id, matrix SHA-256, method id); "
            "replicate: first 64 bits of SHA-256(master seed, replicate index)"
        ),
        "master_seed_hex": f"{seed:016x}",
        "requested_replicates": replicates,
        "completed_replicates": replicates,
        "interval": "central 90% (5th/95th percentiles)",
        "coefficient_ensemble": {
            "feature_index_basis": "zero-based index into artifact features array",
            "coefficient_quantization_decimal_places": 8,
            "coefficient_normalization": "L1 absolute sum approximately one after quantization",
            "scale_policy": (
                "frozen full-cohort feature transition_scale; uncertainty approximation only"
            ),
            "ensemble_digest": _canonical_digest(ensemble_rows),
            "replicates": ensemble_rows,
        },
    }
    return stability, intervals, bootstrap_summary


def _rankdata(values: FloatArray) -> FloatArray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=np.float64)
    ranks[order] = np.arange(values.size, dtype=np.float64)
    return ranks


def _ordinary_ablation(cohort: Cohort, top_count: int, primary_fit: AxisFit) -> dict[str, object]:
    ordinary_fit = _fit_axis(cohort.ordinary_delta, cohort.genes)
    primary_selected, primary_weights = _weights(primary_fit, top_count)
    ordinary_selected, ordinary_weights = _weights(ordinary_fit, top_count)
    primary_dense = np.zeros(len(cohort.genes), dtype=np.float64)
    ordinary_dense = np.zeros(len(cohort.genes), dtype=np.float64)
    primary_dense[primary_selected] = primary_weights
    ordinary_dense[ordinary_selected] = ordinary_weights
    stable_order = np.argsort(ordinary_selected, kind="stable")
    projection: dict[str, object] = {
        "ablation_id": "kncc-ordinary-log-shared-peptide-axis/1.0.0",
        "feature_indices": [int(value) for value in ordinary_selected[stable_order]],
        "coefficients": [_q(value) for value in ordinary_weights[stable_order]],
        "transition_scales": [
            _q(value) for value in ordinary_fit.scale[ordinary_selected[stable_order]]
        ],
        "intercept": 0.0,
        "coefficient_normalization": "L1 absolute sum approximately one after quantization",
        "scale_policy": "ordinary-Log cohort Huber/MAD and support variance scales",
    }
    denominator = float(np.linalg.norm(primary_dense) * np.linalg.norm(ordinary_dense))
    cosine = float(primary_dense.dot(ordinary_dense) / denominator) if denominator else 0.0
    overlap = len(set(primary_selected.tolist()) & set(ordinary_selected.tolist()))
    primary_scores, _, _ = _project(
        cohort.primary_delta, primary_fit.scale, primary_selected, primary_weights
    )
    ordinary_scores, _, _ = _project(
        cohort.ordinary_delta, ordinary_fit.scale, ordinary_selected, ordinary_weights
    )
    valid = np.isfinite(primary_scores) & np.isfinite(ordinary_scores)
    if valid.sum() >= 3:
        rank_correlation = float(
            np.corrcoef(_rankdata(primary_scores[valid]), _rankdata(ordinary_scores[valid]))[0, 1]
        )
    else:
        rank_correlation = 0.0
    return {
        "measure": ABLATION_MEASURE,
        "ablation_family": "source_processing",
        "ablation_kind": "identification_ambiguity_and_shared_peptide_inclusion",
        "role": (
            "source-processing ablation only; never substituted for the Unshared Log primary fit"
        ),
        "interpretation": (
            "Ordinary Log includes shared-peptide evidence and therefore probes source "
            "identification ambiguity; it is not a caller technical-replicate ablation."
        ),
        "selected_feature_overlap": overlap,
        "selected_feature_jaccard": overlap
        / max(len(set(primary_selected) | set(ordinary_selected)), 1),
        "coefficient_cosine": cosine,
        "paired_score_rank_correlation": rank_correlation,
        "supported_pair_count": int(valid.sum()),
        "ordinary_fit_converged": ordinary_fit.converged,
        "ordinary_fit_iterations": ordinary_fit.iterations,
        "frozen_projection": {
            **projection,
            "projection_digest": _canonical_digest(projection),
        },
    }


def _q(value: float) -> float:
    result = round(float(value), 8)
    return 0.0 if result == 0.0 else result


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _assert_deidentified_artifact(
    artifact: dict[str, object], patient_groups: tuple[str, ...]
) -> None:
    payload = _canonical_bytes(artifact)
    lowered = payload.lower()
    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", lowered))
    for patient in patient_groups:
        for identifier in (patient, f"{patient}_T1", f"{patient}_T2"):
            variants = {identifier, identifier.lower(), identifier.upper()}
            for variant in variants:
                encoded = variant.encode("utf-8")
                if encoded.lower() in lowered:
                    raise ValueError("patient/specimen identifier leaked into coefficient artifact")
                source_forms = (encoded, encoded + b"\n", json.dumps(variant).encode("utf-8"))
                for source_form in source_forms:
                    derived = (
                        hashlib.md5(source_form, usedforsecurity=False).hexdigest(),
                        hashlib.sha1(source_form, usedforsecurity=False).hexdigest(),
                        hashlib.sha256(source_form).hexdigest(),
                        hashlib.sha512(source_form).hexdigest(),
                    )
                    if any(value.encode("ascii") in digest_tokens for value in derived):
                        raise ValueError(
                            "low-entropy patient/specimen hash leaked into coefficient artifact"
                        )


def build_artifact(
    cohort: Cohort, *, bootstrap_replicates: int = BOOTSTRAP_REPLICATES
) -> dict[str, object]:
    if bootstrap_replicates < 1:
        raise ValueError("bootstrap_replicates must be positive")
    selected_top, evaluation = _nested_cross_validation(cohort)
    fit = _fit_axis(cohort.primary_delta, cohort.genes)
    selected, coefficients = _weights(fit, selected_top)
    dense_coefficients = np.zeros(len(cohort.genes), dtype=np.float64)
    dense_coefficients[selected] = coefficients
    stability, intervals, bootstrap = _bootstrap(cohort, fit, selected_top, bootstrap_replicates)
    ablation = _ordinary_ablation(cohort, selected_top, fit)
    selected_set = set(selected.tolist())
    features = [
        {
            "gene_symbol": gene,
            "hgnc_id": cohort.hgnc_ids[index],
            "source_gene_label": cohort.source_gene_labels[index],
            "mapping_basis": cohort.mapping_basis[index],
            "transition_center": _q(fit.center[index]),
            "transition_scale": _q(fit.scale[index]),
            "paired_support": int(fit.support[index]),
            "paired_coverage": _q(fit.support[index] / len(cohort.patient_groups)),
            "unshared_peptides": int(cohort.unshared_peptides[index]),
            "eligible": bool(fit.eligible[index]),
            "selected": index in selected_set,
            "coefficient": _q(dense_coefficients[index]),
            "bootstrap_selection_stability": _q(stability[index]),
            "coefficient_interval_90": [_q(value) for value in intervals[index]],
        }
        for index, gene in enumerate(cohort.genes)
    ]
    artifact: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "source_lock": {
            "pdc_study_id": PDC_STUDY_ID,
            "pdc_study_version_uuid": PDC_STUDY_VERSION_UUID,
            "versioned_source_manifest": {
                "filename": PDC_SOURCE_MANIFEST_FILENAME,
                "bytes": PDC_SOURCE_MANIFEST_BYTES,
                "sha256": f"sha256:{PDC_SOURCE_MANIFEST_SHA256}",
                "schema_version": PDC_SOURCE_MANIFEST_SCHEMA,
                "graphql_api_version": PDC_GRAPHQL_API_VERSION,
                "biospecimen_response_records": EXPECTED_VERSIONED_BIOSPECIMEN_RECORDS,
                "file_manifest_response_records": EXPECTED_VERSIONED_FILE_RECORDS,
                "binding": (
                    "exact canonical full responses for the versioned biospecimen and file "
                    "queries plus the study-catalog version record"
                ),
            },
            "files": [
                {
                    "filename": lock.filename,
                    "uuid": lock.uuid,
                    "bytes": lock.bytes,
                    "md5": lock.md5,
                    "sha256": lock.sha256,
                    "uuid_size_md5_binding": "versioned_source_manifest",
                }
                for lock in SOURCE_FILES
            ],
        },
        "cohort_oracles": cohort.oracles,
        "gene_identity": {
            "authority": "HGNC complete set",
            "authority_filename": HGNC_SOURCE_FILENAME,
            "authority_bytes": HGNC_SOURCE_BYTES,
            "authority_sha256": f"sha256:{HGNC_SOURCE_SHA256}",
            "authority_url": (
                "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/"
                "hgnc_complete_set.txt"
            ),
            "authority_license": "CC0-1.0",
            "policy": (
                "exact case-sensitive approved symbol first, otherwise exactly one HGNC "
                "previous/alias target; ambiguous, unresolved, and colliding targets abstain"
            ),
            "mapping_digest": cohort.oracles["hgnc_mapping_digest"],
        },
        "preprocessing": {
            "primary_measure": PRIMARY_MEASURE,
            "source_processing_primary": "Unshared Log (unique-peptide evidence)",
            "source_processing_ablation": "ordinary Log (shared-peptide-inclusive evidence)",
            "technical_channel_collapse": "median within source specimen label and timepoint",
            "missing_value_policy": "blank remains missing; a T2-T1 delta requires both values",
            "aggregate_row_policy": "Mean, Median, and StdDev are source summaries, not genes",
            "metadata_conflict_policy": (
                "one T1-labelled pair whose official versioned PDC sample type is recurrent "
                "is derived from the locked biospecimen response and excluded before fitting"
            ),
        },
        "hyperparameters": {
            "huber_k": HUBER_K,
            "huber_max_iterations": HUBER_MAX_ITERATIONS,
            "huber_tolerance": HUBER_TOLERANCE,
            "minimum_training_pair_coverage": MIN_TRAIN_COVERAGE,
            "minimum_scoring_weight_coverage": MIN_SCORE_WEIGHT_COVERAGE,
            "intensity_floor_quantile": INTENSITY_FLOOR_QUANTILE,
            "minimum_intensity_floor": MIN_INTENSITY_FLOOR,
            "top_feature_candidates": list(TOP_FEATURE_CANDIDATES),
            "outer_folds": OUTER_FOLDS,
            "inner_folds": INNER_FOLDS,
            "bootstrap_replicates": bootstrap_replicates,
        },
        "fit": {
            "model_form": (
                "normalized rank-1 source-cohort T2-minus-T1 concordance axis; not a recurrence "
                "outcome predictor"
            ),
            "selected_top_feature_count": len(selected),
            "eligible_feature_count": int(fit.eligible.sum()),
            "intensity_variance_floor": _q(fit.intensity_floor),
            "support_variance_floor": (
                "intensity floor multiplied by sqrt(training pairs / finite paired support)"
            ),
            "huber_iterations": fit.iterations,
            "huber_converged": fit.converged,
            "coefficient_normalization": "L1 absolute sum equals one",
        },
        "fit_evaluation": evaluation,
        "bootstrap": bootstrap,
        "ordinary_log_ablation": ablation,
        "features": features,
        "provenance": {
            "article_authors": "Kim et al.",
            "article_title": ARTICLE_TITLE,
            "article_journal": "Cancer Cell 42(3):358-377.e8 (2024)",
            "article_doi": ARTICLE_DOI,
            "pmid": ARTICLE_PMID,
            "pmcid": ARTICLE_PMCID,
            "pdc_data_use_guideline": "https://pdc.cancer.gov/pdc/data-use-guidelines",
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "transformation_notice": (
                "Transformed by GLIO-PROTEOGEN into a de-identified coefficient artifact. "
                "Technical channels were median-collapsed; strict paired protein changes were "
                "robustly fit; no raw patient matrices, sample UUIDs, or patient identifiers are "
                "redistributed. This adaptation is not endorsed by the source authors."
            ),
            "limitations": [
                "Research use only; not clinically validated and not prescriptive.",
                (
                    "The axis describes concordance with this source cohort's paired T2-T1 "
                    "protein change."
                ),
                (
                    "It does not predict recurrence, survival, treatment response, or "
                    "individual outcome."
                ),
                (
                    "Coefficients inherit missingness, batch, sampling, and cohort-selection "
                    "limitations."
                ),
            ],
        },
    }
    _assert_deidentified_artifact(artifact, cohort.patient_groups)
    content_digest = "sha256:" + hashlib.sha256(_canonical_bytes(artifact)).hexdigest()
    return {**artifact, "artifact_digest": content_digest}


def write_artifact(artifact: dict[str, object], destination: Path) -> None:
    payload = _canonical_bytes(artifact)
    if b"KNCC_GBM" in payload:
        raise ValueError("patient/specimen identifiers leaked into coefficient artifact")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _default_output() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm"
        / "data"
        / "kncc_paired_protein_transition.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_default_output())
    args = parser.parse_args()
    cohort = load_cohort(args.source_dir, args.hgnc_source)
    artifact = build_artifact(cohort)
    write_artifact(artifact, args.output)
    payload = args.output.read_bytes()
    print(
        json.dumps(
            {
                "output": str(args.output),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "artifact_digest": artifact["artifact_digest"],
                "strict_pairs": cohort.oracles["strict_t1_t2_pairs"],
                "source_biological_gene_labels": cohort.oracles["source_biological_gene_labels"],
                "hgnc_admitted_genes": cohort.oracles["hgnc_admitted_unique_approved_symbols"],
                "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
