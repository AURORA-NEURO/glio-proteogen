# ruff: noqa: C901, E501, PLR0912, PLR0915, PLR2004, T201, TRY003, TRY004
"""Build a source-locked de-identified PDC000515 phosphosite transition artifact.

This importer is intentionally specific to the exact PDC000515 v1 Protein Assembly.
It never packages patient-level measurements or identifiers. Blank measurements stay
missing, same-specimen channels are collapsed before differencing, and a paired delta
exists only when both time points are observed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, NamedTuple, cast

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.gbm_master_kinases.catalog import master_kinase_catalog

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL_ID: Final = "kncc-paired-phosphosite-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-paired-phosphosite-transition-artifact/1.0.0"
PROFILE_ID: Final = "kncc-pdc000515-tmt11-phosphosite-log2-transition/1.0.0"
PDC_STUDY_ID: Final = "PDC000515"
PDC_STUDY_VERSION_UUID: Final = "e5e0dd84-f982-46e3-b78a-5cb19eef31a8"
PDC_GRAPHQL_ENDPOINT: Final = "https://pdc.cancer.gov/graphql"
PDC_GRAPHQL_API_VERSION: Final = "1.0.0"
PDC_SOURCE_MANIFEST_SCHEMA: Final = "glio-proteogen.pdc000515-source-manifest/1.0.0"
PDC_SOURCE_MANIFEST_FILENAME: Final = "PDC000515.v1.canonical-source-lock.json"
# Filled after the first canonical capture and then treated as immutable.
PDC_SOURCE_MANIFEST_BYTES: Final = 708_545
PDC_SOURCE_MANIFEST_SHA256: Final = (
    "1b248983791886a9b4522de07d96abb517c416d793b789d435544745dbe6ed34"
)

PDC_STUDY_CATALOG_QUERY: Final = (
    '{ studyCatalog(pdc_study_id: "PDC000515") { pdc_study_id versions { study_id '
    "study_submitter_id submitter_id_name study_shortname study_version is_latest_version } } }"
)
PDC_VERSIONED_STUDY_QUERY: Final = (
    '{ study(study_id: "e5e0dd84-f982-46e3-b78a-5cb19eef31a8") { study_id pdc_study_id '
    "study_submitter_id program_id project_id study_name study_description program_name "
    "project_name disease_type primary_site analytical_fraction experiment_type cases_count "
    "aliquots_count filesCount { data_category file_type files_count } } }"
)
PDC_VERSIONED_BIOSPECIMEN_QUERY: Final = (
    '{ biospecimenPerStudy(study_id: "e5e0dd84-f982-46e3-b78a-5cb19eef31a8", '
    "acceptDUA: true) { aliquot_id sample_id case_id aliquot_submitter_id "
    "sample_submitter_id case_submitter_id aliquot_status case_status sample_status "
    "project_name sample_type disease_type primary_site pool taxon } }"
)
PDC_VERSIONED_FILES_QUERY: Final = (
    '{ filesPerStudy(study_id: "e5e0dd84-f982-46e3-b78a-5cb19eef31a8", offset: 0, '
    "limit: 25000, acceptDUA: true) { study_id pdc_study_id study_submitter_id study_name "
    "file_id file_name file_submitter_id file_type md5sum file_size data_category "
    "file_format } }"
)
PDC_VERSIONED_PROTOCOL_QUERY: Final = (
    '{ protocolPerStudy(study_id: "e5e0dd84-f982-46e3-b78a-5cb19eef31a8") { protocol_id '
    "protocol_submitter_id study_id pdc_study_id study_submitter_id program_id "
    "program_submitter_id protocol_name protocol_date document_name quantitation_strategy "
    "experiment_type label_free_quantitation labeled_quantitation isobaric_labeling_reagent "
    "reporter_ion_ms_level starting_amount starting_amount_uom digestion_reagent "
    "alkylation_reagent enrichment_strategy enrichment chromatography_dimensions_count "
    "one_d_chromatography_type two_d_chromatography_type fractions_analyzed_count column_type "
    "amount_on_column amount_on_column_uom column_length column_length_uom "
    "column_inner_diameter column_inner_diameter_uom particle_size particle_size_uom "
    "particle_type gradient_length gradient_length_uom instrument_make instrument_model "
    "dissociation_type ms1_resolution ms2_resolution dda_topn normalized_collision_energy "
    "acquistion_type dia_multiplexing dia_ims analytical_technique "
    "chromatography_instrument_make chromatography_instrument_model polarity "
    "reconstitution_solvent reconstitution_volume reconstitution_volume_uom "
    "internal_standards extraction_method ionization_mode } }"
)
PDC_EXPERIMENTAL_DESIGN_QUERY: Final = (
    '{ studyExperimentalDesign(pdc_study_id: "PDC000515") { pdc_study_id '
    "study_run_metadata_id study_run_metadata_submitter_id study_id study_submitter_id "
    "analyte acquisition_type protocol_id protocol_submitter_id polarity experiment_type "
    "plex_dataset_name experiment_number number_of_fractions "
    "tmt_126 { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_127n { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_127c { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_128n { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_128c { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_129n { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_129c { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_130n { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_130c { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_131 { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } "
    "tmt_131c { aliquot_id aliquot_run_metadata_id aliquot_submitter_id } } }"
)

ARTICLE_TITLE: Final = "Integrated proteogenomic characterization of glioblastoma evolution"
ARTICLE_DOI: Final = "10.1016/j.ccell.2023.12.015"
ARTICLE_PMID: Final = "38215747"
ARTICLE_PMCID: Final = "PMC10939876"

EXPECTED_VERSIONED_BIOSPECIMEN_RECORDS: Final = 180
EXPECTED_VERSIONED_BIOLOGICAL_SPECIMENS: Final = 178
EXPECTED_VERSIONED_FILE_RECORDS: Final = 1_064
EXPECTED_PROTOCOL_RECORDS: Final = 1
EXPECTED_DESIGN_ROWS: Final = 22
EXPECTED_SAMPLE_MAP_ROWS: Final = 264
EXPECTED_ANALYTICAL_SAMPLES: Final = 22
EXPECTED_FRACTIONS_PER_ANALYTICAL_SAMPLE: Final = 12
EXPECTED_MEASUREMENT_CHANNELS: Final = 220
EXPECTED_BIOLOGICAL_MEASUREMENT_CHANNELS: Final = 185
EXPECTED_BIOLOGICAL_SPECIMENS: Final = 178
EXPECTED_DUPLICATED_SPECIMEN_LABELS: Final = 7
EXPECTED_COMPLETE_PAIRS: Final = 89
EXPECTED_STRICT_PAIRS: Final = 88
EXPECTED_MATRIX_ROWS: Final = 24_015
EXPECTED_MATRIX_COLUMNS: Final = 224
EXPECTED_SINGLE_SITE_ROWS: Final = 21_475
EXPECTED_TWO_SITE_ROWS: Final = 2_290
EXPECTED_THREE_SITE_ROWS: Final = 250
EXPECTED_MULTI_PEPTIDE_ROWS: Final = 5_221

EXPECTED_FILE_INVENTORY: Final = {
    "Peptide Spectral Matches": (528, 3_009_332_827),
    "Processed Mass Spectra": (264, 137_735_404_593),
    "Protein Assembly": (6, 141_999_460),
    "Quality Metrics": (2, 7_972_167),
    "Raw Mass Spectra": (264, 1_131_600_728_153),
}

HGNC_SOURCE_FILENAME: Final = "hgnc_complete_set.txt"
HGNC_SOURCE_BYTES: Final = 16_948_224
HGNC_SOURCE_SHA256: Final = "854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"

HUBER_K: Final = 1.345
HUBER_MAX_ITERATIONS: Final = 24
HUBER_TOLERANCE: Final = 1.0e-10
MIN_TRAIN_COVERAGE: Final = 0.60
MIN_SCORE_WEIGHT_COVERAGE: Final = 0.50
INTENSITY_FLOOR_QUANTILE: Final = 0.10
MIN_INTENSITY_FLOOR: Final = 1.0e-4
OUTER_FOLDS: Final = 5
INNER_FOLDS: Final = 3
TOP_FEATURE_CANDIDATES: Final = (32, 64, 128, 256)
SELECTION_STABILITY_REPEATS: Final = 20
SELECTION_STABILITY_FOLDS: Final = 5
SELECTION_STABILITY_MINIMUM: Final = 0.80
SELECTION_STABILITY_WILSON_LOWER_MINIMUM: Final = 0.60
BOOTSTRAP_REPLICATES: Final = 64
BOOTSTRAP_MEDIAN_JACCARD_MINIMUM: Final = 0.50
EXPECTED_COHORT_SEMANTIC_DIGEST: Final = (
    "sha256:e293fd1df6edfa770f382401c1f530fa7c77d7c5908286c32c9125ea1fc90040"
)

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
MATRIX_METADATA_COLUMNS: Final = ("Peptide", "Gene", "Organism")

_ENTRY_PATTERN: Final = re.compile(r"^(?P<label>[^:]+):(?P<uuid>[0-9a-f-]{36})$")
_MATRIX_COLUMN_PATTERN: Final = re.compile(
    r"^Log (?P<label>[^:]+):(?P<uuid>[0-9a-f-]{36})/ref:(?P<reference>[0-9a-f-]{36})$"
)
_SPECIMEN_PATTERN: Final = re.compile(r"^(?P<patient>KNCC_GBM\d{4})_(?P<time>T[12])$")
_SITE_PATTERN: Final = re.compile(r"^ENSP\d+\.\d+:(?P<sites>(?:[sty]\d+)+)$")
_SITE_TOKEN_PATTERN: Final = re.compile(r"([sty])(\d+)")
_UUID_PATTERN_BYTES: Final = re.compile(
    rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


class SourceFileLock(NamedTuple):
    filename: str
    uuid: str
    bytes: int
    md5: str
    sha256: str


SOURCE_FILES: Final = (
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Phosphoproteome.label.txt",
        "ee9b645e-092e-4d94-9fb6-0b936e125039",
        522,
        "4e6cc0cb78f8e9143abd078694c2e610",
        "83f55a385bcc88d8780a75a8535c1e319e1c30633ff700e15ad87df5ae3792f4",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Phosphoproteome.peptides.tsv",
        "61f74ed4-77b0-40b9-aa7b-b6eadc0673cd",
        63_695_733,
        "e17edd5ac8b045dae10ee900c5f18bbb",
        "c8c419582bf4a1e3c011f9c35cf7cbe453bda566f4e18364e9bb6d92e32a206e",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Phosphoproteome.phosphopeptide.tmt11.tsv",
        "0bfd4904-153a-4eb0-ae99-7e9667fe79e4",
        39_476_036,
        "53fc6e9689d48dcc0875947787b40faf",
        "d513fe4ca28b70f873d28ecab563c758a1ffd3fb903fd5ebe7eba2f97b43eba8",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Phosphoproteome.phosphosite.tmt11.tsv",
        "dd668a70-2c1d-413e-b439-50d7aa47fd74",
        35_462_701,
        "367c076701733fd37b1965f3cb65bd18",
        "0bae05b8b80ea68d62acd25d89d2fef4b33d06a747dc8d89399ead62780c29fe",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Phosphoproteome.sample.txt",
        "355422f5-e199-4f02-a37e-17e9791bc49e",
        203_737,
        "0768c7087da1c0b354ea6208b1ff5c77",
        "71e6b8e88cb1920b6792c3c7c712fe740516d838b9c7fa8fe5d1c9ccbb82bef1",
    ),
    SourceFileLock(
        "KNCC_Glioblastoma_Evolution_Phosphoproteome.summary.tsv",
        "73e6eb70-7489-4469-ac7f-20ac095fa63d",
        3_160_731,
        "e5f6e2dea921a9560a5e63b03ce5b345",
        "e79c8220875713eee3d9ab7956329e1d54b748a0382f0c40abddc6e21f628c3c",
    ),
)

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class VersionedSourceMetadata:
    specimen_labels: frozenset[str]
    mismatch_patient_groups: frozenset[str]
    private_identifiers: frozenset[str]
    oracles: dict[str, object]


@dataclass(frozen=True, slots=True)
class SourceAttestation:
    """Exact immutable identities consumed by one fitted cohort build."""

    source_file_sha256: tuple[str, ...]
    parsed_snapshot_sha256: tuple[str, str]
    source_manifest_sha256: str
    hgnc_sha256: str
    cohort_semantic_digest: str


@dataclass(frozen=True, slots=True)
class PhosphositeCohort:
    site_groups: tuple[str, ...]
    source_genes: tuple[str, ...]
    approved_genes: tuple[str | None, ...]
    hgnc_ids: tuple[str | None, ...]
    gene_mapping_basis: tuple[str, ...]
    modified_peptides: tuple[tuple[str, ...], ...]
    sphinks_labels: tuple[str | None, ...]
    signature_kinases: tuple[tuple[str, ...], ...]
    patient_groups: tuple[str, ...]
    delta: FloatArray
    private_identifiers: frozenset[str]
    crosswalk_metadata: dict[str, object]
    oracles: dict[str, object]
    source_attestation: SourceAttestation | None = None


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


_ARTIFACT_WRITE_CAPABILITY = object()


@dataclass(frozen=True, slots=True)
class AttestedArtifact:
    """In-process receipt binding one validated document to immutable output bytes."""

    document: dict[str, object]
    canonical_payload: bytes
    private_identifiers: frozenset[str]
    capability: object


def _file_digests(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _payload_digests(payload: bytes) -> tuple[str, str]:
    return (
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _read_locked_payload(path: Path, lock: SourceFileLock) -> bytes:
    """Read once and verify the exact immutable bytes that downstream parsers consume."""

    if not path.is_file():
        raise ValueError(f"missing locked PDC000515 source file: {lock.filename}")
    payload = path.read_bytes()
    if len(payload) != lock.bytes:
        raise ValueError(f"source byte-size mismatch: {lock.filename}")
    md5, sha256 = _payload_digests(payload)
    if md5 != lock.md5 or sha256 != lock.sha256:
        raise ValueError(f"source digest mismatch: {lock.filename}")
    return payload


def _text_stream(payload: bytes) -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", newline="")


def _read_hgnc_payload(path: Path) -> bytes:
    if path.name != HGNC_SOURCE_FILENAME or not path.is_file():
        raise ValueError("missing pinned HGNC complete-set authority")
    payload = path.read_bytes()
    if len(payload) != HGNC_SOURCE_BYTES:
        raise ValueError("HGNC complete-set byte-size mismatch")
    if hashlib.sha256(payload).hexdigest() != HGNC_SOURCE_SHA256:
        raise ValueError("HGNC complete-set SHA-256 mismatch")
    return payload


def verify_source_files(source_dir: Path) -> dict[str, Path]:
    """Verify the six required Protein Assembly files; adjacent manifests are allowed."""

    result: dict[str, Path] = {}
    for lock in SOURCE_FILES:
        path = source_dir / lock.filename
        if not path.is_file():
            raise ValueError(f"missing locked PDC000515 source file: {lock.filename}")
        if path.stat().st_size != lock.bytes:
            raise ValueError(f"source byte-size mismatch: {lock.filename}")
        md5, sha256 = _file_digests(path)
        if md5 != lock.md5 or sha256 != lock.sha256:
            raise ValueError(f"source digest mismatch: {lock.filename}")
        result[lock.filename] = path
    return result


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"PDC source manifest field {name!r} is not an object")
    return cast("dict[str, object]", value)


def _records(value: object, name: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"PDC source manifest field {name!r} is not a record array")
    return cast("list[dict[str, object]]", value)


def verify_versioned_source_manifest(source_dir: Path) -> VersionedSourceMetadata:
    """Verify canonical official metadata and derive the strict-pair exclusion oracle."""

    path = source_dir / PDC_SOURCE_MANIFEST_FILENAME
    if not path.is_file():
        raise ValueError(f"missing locked PDC source manifest: {PDC_SOURCE_MANIFEST_FILENAME}")
    payload = path.read_bytes()
    if len(payload) != PDC_SOURCE_MANIFEST_BYTES:
        raise ValueError("PDC000515 source manifest byte-size mismatch")
    if hashlib.sha256(payload).hexdigest() != PDC_SOURCE_MANIFEST_SHA256:
        raise ValueError("PDC000515 source manifest SHA-256 mismatch")
    root = cast("object", json.loads(payload))
    manifest = _object(root, "root")
    if _canonical_bytes(manifest) != payload:
        raise ValueError("PDC000515 source manifest is not canonical JSON")
    if manifest.get("schema_version") != PDC_SOURCE_MANIFEST_SCHEMA:
        raise ValueError("unexpected PDC000515 source manifest schema")

    source = _object(manifest.get("source"), "source")
    expected_source = {
        "endpoint": PDC_GRAPHQL_ENDPOINT,
        "api_version": PDC_GRAPHQL_API_VERSION,
        "documentation": "https://pdc.cancer.gov/pdc-docs/api-documentation",
        "pdc_study_id": PDC_STUDY_ID,
        "pdc_study_version_uuid": PDC_STUDY_VERSION_UUID,
    }
    if any(source.get(key) != value for key, value in expected_source.items()):
        raise ValueError("PDC000515 source manifest provenance changed")
    expected_local = [
        {
            "filename": lock.filename,
            "file_uuid": lock.uuid,
            "bytes": lock.bytes,
            "official_md5": lock.md5,
            "observed_sha256": lock.sha256,
        }
        for lock in SOURCE_FILES
    ]
    if source.get("local_file_locks") != expected_local:
        raise ValueError("PDC000515 local file-lock projection changed")

    queries = _object(manifest.get("query_provenance"), "query_provenance")
    if queries != {
        "study_catalog": PDC_STUDY_CATALOG_QUERY,
        "versioned_study": PDC_VERSIONED_STUDY_QUERY,
        "versioned_biospecimens": PDC_VERSIONED_BIOSPECIMEN_QUERY,
        "versioned_files": PDC_VERSIONED_FILES_QUERY,
        "versioned_protocol": PDC_VERSIONED_PROTOCOL_QUERY,
        "experimental_design": PDC_EXPERIMENTAL_DESIGN_QUERY,
    }:
        raise ValueError("PDC000515 source query provenance changed")

    responses = _object(manifest.get("responses"), "responses")
    catalog = _records(responses.get("study_catalog"), "study_catalog")
    if catalog != [
        {
            "pdc_study_id": PDC_STUDY_ID,
            "versions": [
                {
                    "study_id": PDC_STUDY_VERSION_UUID,
                    "study_submitter_id": "KNCC Glioblastoma Evolution - Phosphoproteome",
                    "submitter_id_name": "KNCC Glioblastoma Evolution - Phosphoproteome",
                    "study_shortname": "KNCC Glioblastoma Evolution - Phosphoproteome",
                    "study_version": "1",
                    "is_latest_version": "yes",
                }
            ],
        }
    ]:
        raise ValueError("PDC000515 study catalog version binding changed")

    studies = _records(responses.get("versioned_study"), "versioned_study")
    if len(studies) != 1:
        raise ValueError("unexpected PDC000515 study response count")
    study = studies[0]
    if (
        study.get("study_id") != PDC_STUDY_VERSION_UUID
        or study.get("pdc_study_id") != PDC_STUDY_ID
        or study.get("study_name") != "KNCC Glioblastoma Evolution - Phosphoproteome"
        or study.get("analytical_fraction") != "Phosphoproteome"
        or study.get("experiment_type") != "TMT11"
        or int(str(study.get("cases_count"))) != 91
        or int(str(study.get("aliquots_count"))) != EXPECTED_VERSIONED_BIOSPECIMEN_RECORDS
    ):
        raise ValueError("PDC000515 study assay identity changed")

    files = _records(responses.get("versioned_files"), "versioned_files")
    if len(files) != EXPECTED_VERSIONED_FILE_RECORDS:
        raise ValueError("unexpected PDC000515 file-manifest record count")
    file_ids = [str(row.get("file_id", "")) for row in files]
    if len(set(file_ids)) != len(file_ids):
        raise ValueError("duplicate PDC000515 file UUID")
    if any(
        row.get("study_id") != PDC_STUDY_VERSION_UUID or row.get("pdc_study_id") != PDC_STUDY_ID
        for row in files
    ):
        raise ValueError("PDC000515 file manifest crosses study versions")
    inventory: dict[str, tuple[int, int]] = {}
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in files:
        grouped[str(row.get("data_category", ""))].append(row)
    for category, rows in grouped.items():
        inventory[category] = (len(rows), sum(int(str(row.get("file_size"))) for row in rows))
    if inventory != EXPECTED_FILE_INVENTORY:
        raise ValueError("PDC000515 full file inventory changed")
    by_name = {str(row.get("file_name", "")): row for row in files}
    if len(by_name) != len(files):
        raise ValueError("duplicate PDC000515 filename")
    for lock in SOURCE_FILES:
        locked_row = by_name.get(lock.filename)
        if locked_row is None or (
            locked_row.get("file_id") != lock.uuid
            or int(str(locked_row.get("file_size"))) != lock.bytes
            or locked_row.get("md5sum") != lock.md5
            or locked_row.get("data_category") != "Protein Assembly"
        ):
            raise ValueError("locked Protein Assembly identity differs from official metadata")

    biospecimens = _records(responses.get("versioned_biospecimens"), "versioned_biospecimens")
    if len(biospecimens) != EXPECTED_VERSIONED_BIOSPECIMEN_RECORDS:
        raise ValueError("unexpected PDC000515 biospecimen record count")
    specimen_labels: set[str] = set()
    mismatch_groups: set[str] = set()
    private_identifiers: set[str] = set()
    aliquot_ids: set[str] = set()
    for row in biospecimens:
        for field in (
            "aliquot_id",
            "sample_id",
            "case_id",
            "aliquot_submitter_id",
            "sample_submitter_id",
            "case_submitter_id",
        ):
            value = str(row.get(field, ""))
            if value and (
                _SPECIMEN_PATTERN.fullmatch(value) is not None
                or value.startswith("KNCC_GBM")
                or _UUID_PATTERN_BYTES.fullmatch(value.encode("ascii", errors="ignore")) is not None
            ):
                private_identifiers.add(value)
        aliquot_id = str(row.get("aliquot_id", ""))
        if not aliquot_id or aliquot_id in aliquot_ids:
            raise ValueError("missing or duplicate PDC000515 aliquot UUID")
        aliquot_ids.add(aliquot_id)
        label = str(row.get("sample_submitter_id", ""))
        match = _SPECIMEN_PATTERN.fullmatch(label)
        if match is None:
            continue
        if label in specimen_labels:
            raise ValueError("duplicate biological specimen in PDC000515 metadata")
        patient = match.group("patient")
        if row.get("case_submitter_id") != patient or row.get("aliquot_submitter_id") != label:
            raise ValueError("PDC000515 biospecimen hierarchy is inconsistent")
        expected_type = "Primary Tumor" if match.group("time") == "T1" else "Recurrent Tumor"
        actual_type = row.get("sample_type")
        if actual_type != expected_type:
            if match.group("time") != "T1" or actual_type != "Recurrent Tumor":
                raise ValueError("unexpected PDC000515 sample-type mismatch semantics")
            mismatch_groups.add(patient)
        specimen_labels.add(label)
    if len(specimen_labels) != EXPECTED_VERSIONED_BIOLOGICAL_SPECIMENS:
        raise ValueError("unexpected PDC000515 biological specimen count")
    if len(mismatch_groups) != 1:
        raise ValueError("expected exactly one PDC000515 sample-type mismatch")

    protocols = _records(responses.get("versioned_protocol"), "versioned_protocol")
    if len(protocols) != EXPECTED_PROTOCOL_RECORDS:
        raise ValueError("unexpected PDC000515 protocol count")
    protocol = protocols[0]
    if (
        protocol.get("study_id") != PDC_STUDY_VERSION_UUID
        or protocol.get("pdc_study_id") != PDC_STUDY_ID
        or protocol.get("protocol_id") != "5bb102e9-8e75-4ddc-9227-e75dc6cf58f5"
        or protocol.get("protocol_date") != "2023-12-15"
        or protocol.get("experiment_type") != "TMT11"
        or protocol.get("isobaric_labeling_reagent") != "TMT11"
        or protocol.get("reporter_ion_ms_level") != "MS2"
        or protocol.get("enrichment") != "Fe3+ NTA-Agarose (Qiagen)"
    ):
        raise ValueError("PDC000515 protocol identity changed")

    design = _records(responses.get("experimental_design"), "experimental_design")
    if len(design) != EXPECTED_DESIGN_ROWS:
        raise ValueError("unexpected PDC000515 experimental-design row count")
    design_ids = {str(row.get("study_run_metadata_id", "")) for row in design}
    if len(design_ids) != len(design) or any(
        row.get("study_id") != PDC_STUDY_VERSION_UUID
        or row.get("pdc_study_id") != PDC_STUDY_ID
        or row.get("experiment_type") != "TMT11"
        or str(row.get("number_of_fractions")) != "12"
        for row in design
    ):
        raise ValueError("PDC000515 experimental-design identity changed")

    return VersionedSourceMetadata(
        specimen_labels=frozenset(specimen_labels),
        mismatch_patient_groups=frozenset(mismatch_groups),
        private_identifiers=frozenset(private_identifiers),
        oracles={
            "official_versioned_biospecimen_records": len(biospecimens),
            "official_versioned_biological_specimens": len(specimen_labels),
            "official_sample_type_mismatch_patient_groups": len(mismatch_groups),
            "official_versioned_file_records": len(files),
            "official_protocol_records": len(protocols),
            "official_experimental_design_rows": len(design),
            "official_total_file_bytes": sum(value[1] for value in inventory.values()),
            "official_protein_assembly_bytes": inventory["Protein Assembly"][1],
        },
    )


def _parse_entry(value: str) -> tuple[str, str]:
    match = _ENTRY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid PDC000515 sample-map entry: {value!r}")
    return match.group("label"), match.group("uuid")


def _sample_map_headers(payload: bytes) -> tuple[set[tuple[str, str, str]], dict[str, object]]:
    with _text_stream(payload) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != SAMPLE_MAP_HEADER:
            raise ValueError("unexpected PDC000515 sample-map header")
        rows = list(reader)
    if len(rows) != EXPECTED_SAMPLE_MAP_ROWS:
        raise ValueError("unexpected PDC000515 sample-map row count")
    by_analytical: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["Ratios"] != EXPECTED_RATIOS:
            raise ValueError("unexpected PDC000515 TMT ratio grammar")
        by_analytical[row["AnalyticalSample"]].append(row)
    if len(by_analytical) != EXPECTED_ANALYTICAL_SAMPLES:
        raise ValueError("unexpected PDC000515 analytical-sample count")

    expected: set[tuple[str, str, str]] = set()
    for analytical_rows in by_analytical.values():
        fractions = {int(row["Fraction"]) for row in analytical_rows}
        if fractions != set(range(1, EXPECTED_FRACTIONS_PER_ANALYTICAL_SAMPLE + 1)):
            raise ValueError("PDC000515 plex does not contain fractions 1..12")
        first = analytical_rows[0]
        stable_fields = (*TMT_CHANNELS, "LabelReagent", "Ratios")
        if any(
            any(row[field] != first[field] for field in stable_fields) for row in analytical_rows
        ):
            raise ValueError("PDC000515 channel assignment changes between fractions")
        reference_label, reference_uuid = _parse_entry(first["126C"])
        if reference_label != "ref":
            raise ValueError("PDC000515 126C is not the reference channel")
        for channel in TMT_CHANNELS[1:]:
            label, sample_uuid = _parse_entry(first[channel])
            item = (label, sample_uuid, reference_uuid)
            if item in expected:
                raise ValueError("duplicate PDC000515 sample-map measurement")
            expected.add(item)
    if len(expected) != EXPECTED_MEASUREMENT_CHANNELS:
        raise ValueError("unexpected PDC000515 measurement-channel count")
    return expected, {
        "sample_map_rows": len(rows),
        "analytical_samples": len(by_analytical),
        "fractions_per_analytical_sample": EXPECTED_FRACTIONS_PER_ANALYTICAL_SAMPLE,
        "measurement_channels": len(expected),
    }


def _measurement_columns(
    header: list[str], expected: set[tuple[str, str, str]]
) -> tuple[dict[str, list[int]], dict[str, object]]:
    if (
        len(header) != EXPECTED_MATRIX_COLUMNS
        or header[0] != "Phosphosite"
        or tuple(header[-3:]) != MATRIX_METADATA_COLUMNS
    ):
        raise ValueError("unexpected PDC000515 phosphosite matrix header")
    result: dict[str, list[int]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for index, column in enumerate(header[1:-3], start=1):
        match = _MATRIX_COLUMN_PATTERN.fullmatch(column)
        if match is None:
            raise ValueError(f"unexpected PDC000515 measurement column: {column!r}")
        source_key = (match.group("label"), match.group("uuid"), match.group("reference"))
        if source_key not in expected or source_key in seen:
            raise ValueError("PDC000515 matrix does not exactly match the sample map")
        seen.add(source_key)
        result[match.group("label")].append(index)
    if seen != expected:
        raise ValueError("PDC000515 phosphosite matrix omits a sample-map channel")
    biological = {label for label in result if _SPECIMEN_PATTERN.fullmatch(label) is not None}
    biological_channels = sum(len(result[label]) for label in biological)
    duplicated = sum(len(result[label]) > 1 for label in biological)
    extra = biological_channels - len(biological)
    if (
        len(biological) != EXPECTED_BIOLOGICAL_SPECIMENS
        or biological_channels != EXPECTED_BIOLOGICAL_MEASUREMENT_CHANNELS
        or duplicated != EXPECTED_DUPLICATED_SPECIMEN_LABELS
        or extra != EXPECTED_DUPLICATED_SPECIMEN_LABELS
    ):
        raise ValueError("unexpected PDC000515 technical-repeat inventory")
    return result, {
        "source_biological_specimens": len(biological),
        "biological_measurement_channels": biological_channels,
        "duplicated_specimens": duplicated,
        "extra_technical_channels": extra,
        "non_biological_measurement_channels": len(expected) - biological_channels,
    }


def _strict_patients(
    labels: set[str], metadata: VersionedSourceMetadata
) -> tuple[tuple[str, ...], dict[str, object]]:
    biological = {label for label in labels if _SPECIMEN_PATTERN.fullmatch(label) is not None}
    if biological != metadata.specimen_labels:
        raise ValueError("PDC000515 matrix and official biospecimen inventories differ")
    patient_times: dict[str, set[str]] = defaultdict(set)
    for label in biological:
        match = _SPECIMEN_PATTERN.fullmatch(label)
        if match is not None:
            patient_times[match.group("patient")].add(match.group("time"))
    complete = sorted(patient for patient, times in patient_times.items() if times == {"T1", "T2"})
    if len(complete) != EXPECTED_COMPLETE_PAIRS or any(
        times != {"T1", "T2"} for times in patient_times.values()
    ):
        raise ValueError("unexpected PDC000515 nominal T1/T2 pair inventory")
    if not metadata.mismatch_patient_groups.issubset(complete):
        raise ValueError("PDC000515 metadata mismatch is not a complete pair")
    strict = tuple(
        patient for patient in complete if patient not in metadata.mismatch_patient_groups
    )
    if len(strict) != EXPECTED_STRICT_PAIRS:
        raise ValueError("unexpected PDC000515 strict-pair count")
    return strict, {
        "nominal_complete_pairs": len(complete),
        "sample_type_mismatch_pairs_excluded": len(metadata.mismatch_patient_groups),
        "strict_t1_t2_pairs": len(strict),
    }


def _float_cell(value: str) -> float:
    if value == "":
        return math.nan
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite numeric token in PDC000515 matrix")
    return result


def _collapse_columns(raw: FloatArray, indices: list[int]) -> FloatArray:
    if len(indices) == 1:
        return raw[:, indices[0]].copy()
    if len(indices) != 2:
        raise ValueError("unexpected PDC000515 technical-channel multiplicity")
    values = raw[:, indices]
    valid = np.isfinite(values)
    count = valid.sum(axis=1)
    result = np.full(raw.shape[0], np.nan, dtype=np.float64)
    one = count == 1
    result[one] = np.where(valid[one], values[one], 0.0).sum(axis=1)
    both = count == 2
    result[both] = values[both].mean(axis=1)
    return result


def _convert_modified_peptide(peptide: str) -> str:
    if not peptide or not re.fullmatch(r"[A-Za-z]+", peptide):
        raise ValueError("invalid PDC000515 canonical phosphopeptide sequence")
    output: list[str] = []
    modified = 0
    for residue in peptide:
        if residue in "sty":
            output.extend((residue.upper(), "*"))
            modified += 1
        elif residue.islower():
            raise ValueError("unexpected lowercase non-phosphorylated peptide residue")
        else:
            output.append(residue)
    if modified == 0:
        raise ValueError("PDC000515 phosphosite row peptide has no marked residue")
    return "".join(output)


def _read_matrix(
    payload: bytes,
    expected_headers: set[tuple[str, str, str]],
    metadata: VersionedSourceMetadata,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, ...], ...],
    tuple[str, ...],
    FloatArray,
    dict[str, object],
]:
    with _text_stream(payload) as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        columns, column_oracles = _measurement_columns(header, expected_headers)
        patients, pair_oracles = _strict_patients(set(columns), metadata)
        measurement_positions = list(range(1, len(header) - 3))
        position_map = {position: offset for offset, position in enumerate(measurement_positions)}
        site_groups: list[str] = []
        genes: list[str] = []
        peptides: list[tuple[str, ...]] = []
        raw_rows: list[FloatArray] = []
        site_cardinality = Counter[int]()
        multi_peptide_rows = 0
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(f"ragged PDC000515 matrix row {row_number}")
            site_group = row[0]
            match = _SITE_PATTERN.fullmatch(site_group)
            if match is None:
                raise ValueError(f"invalid PDC000515 site-group identifier at row {row_number}")
            tokens = _SITE_TOKEN_PATTERN.findall(match.group("sites"))
            if "".join(f"{residue}{position}" for residue, position in tokens) != match.group(
                "sites"
            ):
                raise ValueError("PDC000515 site-group tokenization is not lossless")
            site_cardinality[len(tokens)] += 1
            source_peptides = tuple(dict.fromkeys(row[-3].split(";")))
            if len(source_peptides) > 1:
                multi_peptide_rows += 1
            converted = tuple(
                sorted({_convert_modified_peptide(value) for value in source_peptides})
            )
            gene = row[-2]
            if not gene or any(token in gene for token in (";", "|", ",")):
                raise ValueError("PDC000515 row has missing or compound gene identity")
            if row[-1] != "Homo sapiens":
                raise ValueError("PDC000515 phosphosite matrix contains a non-human row")
            site_groups.append(site_group)
            genes.append(gene)
            peptides.append(converted)
            raw_rows.append(
                np.fromiter(
                    (_float_cell(row[index]) for index in measurement_positions),
                    dtype=np.float64,
                    count=len(measurement_positions),
                )
            )
    if len(site_groups) != EXPECTED_MATRIX_ROWS or len(set(site_groups)) != len(site_groups):
        raise ValueError("unexpected PDC000515 unique phosphosite-row inventory")
    if site_cardinality != Counter(
        {1: EXPECTED_SINGLE_SITE_ROWS, 2: EXPECTED_TWO_SITE_ROWS, 3: EXPECTED_THREE_SITE_ROWS}
    ):
        raise ValueError("PDC000515 composite-site inventory changed")
    if multi_peptide_rows != EXPECTED_MULTI_PEPTIDE_ROWS:
        raise ValueError("PDC000515 multi-peptide row inventory changed")

    raw = np.stack(raw_rows)
    delta = np.empty((len(patients), len(site_groups)), dtype=np.float64)
    for patient_index, patient in enumerate(patients):
        t1 = [position_map[index] for index in columns[f"{patient}_T1"]]
        t2 = [position_map[index] for index in columns[f"{patient}_T2"]]
        left = _collapse_columns(raw, t1)
        right = _collapse_columns(raw, t2)
        delta[patient_index] = right - left
    del raw
    finite_support = np.isfinite(delta).sum(axis=0)
    return (
        tuple(site_groups),
        tuple(genes),
        tuple(peptides),
        patients,
        delta,
        {
            **column_oracles,
            **pair_oracles,
            "matrix_rows": len(site_groups),
            "matrix_columns": len(header),
            "single_site_rows": site_cardinality[1],
            "two_site_composite_rows": site_cardinality[2],
            "three_site_composite_rows": site_cardinality[3],
            "multi_peptide_rows": multi_peptide_rows,
            "finite_paired_deltas": int(np.isfinite(delta).sum()),
            "paired_support_min": int(finite_support.min()),
            "paired_support_median": float(np.median(finite_support)),
            "paired_support_max": int(finite_support.max()),
            "sites_with_at_least_three_pairs": int((finite_support >= 3).sum()),
            "sites_with_at_least_half_pairs": int((finite_support >= 44).sum()),
            "sites_with_at_least_sixty_percent_pairs": int((finite_support >= 53).sum()),
        },
    )


def _hgnc_mapping(
    hgnc_payload: bytes, source_genes: tuple[str, ...]
) -> tuple[tuple[str | None, ...], tuple[str | None, ...], tuple[str, ...], dict[str, object]]:
    approved: dict[str, dict[str, str]] = {}
    aliases: dict[str, set[str]] = defaultdict(set)
    with _text_stream(hgnc_payload) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not {"hgnc_id", "symbol", "prev_symbol", "alias_symbol"}.issubset(
            reader.fieldnames or ()
        ):
            raise ValueError("unexpected HGNC complete-set header")
        for row in reader:
            symbol = row["symbol"]
            if symbol in approved:
                raise ValueError("duplicate approved symbol in HGNC authority")
            approved[symbol] = row
            for field in ("prev_symbol", "alias_symbol"):
                for alias in filter(None, row[field].split("|")):
                    aliases[alias].add(symbol)

    mapped_genes: list[str | None] = []
    hgnc_ids: list[str | None] = []
    bases: list[str] = []
    counts = Counter[str]()
    projection: list[dict[str, object]] = []
    for source_gene in source_genes:
        if source_gene in approved:
            target: str | None = source_gene
            basis = "approved_symbol"
        else:
            targets = aliases.get(source_gene, set())
            if len(targets) == 1:
                target = next(iter(targets))
                previous = set(filter(None, approved[target]["prev_symbol"].split("|")))
                basis = "previous_symbol" if source_gene in previous else "alias_symbol"
            elif targets:
                target = None
                basis = "ambiguous_alias"
            else:
                target = None
                basis = "unresolved"
        mapped_genes.append(target)
        hgnc_ids.append(approved[target]["hgnc_id"] if target is not None else None)
        bases.append(basis)
        counts[basis] += 1
        projection.append(
            {
                "source_gene": source_gene,
                "approved_gene": target,
                "hgnc_id": approved[target]["hgnc_id"] if target is not None else None,
                "mapping_basis": basis,
            }
        )
    return (
        tuple(mapped_genes),
        tuple(hgnc_ids),
        tuple(bases),
        {
            "authority": "HGNC complete set",
            "authority_filename": HGNC_SOURCE_FILENAME,
            "authority_bytes": HGNC_SOURCE_BYTES,
            "authority_sha256": "sha256:" + HGNC_SOURCE_SHA256,
            "authority_url": "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt",
            "authority_license": "CC0-1.0",
            "authority_release_identifier": None,
            "authority_retrieval_date": None,
            "authority_missing_metadata_note": "the existing PDC000514 lock supplies no HGNC release identifier or retrieval date; neither is inferred",
            "mapping_policy": "exact approved symbol, otherwise exactly one previous/alias target; ambiguous and unresolved genes abstain",
            "mapping_counts": dict(sorted(counts.items())),
            "mapping_digest": _canonical_digest(projection),
        },
    )


def _direct_sphinks_label(gene: str, site_group: str) -> str:
    match = _SITE_PATTERN.fullmatch(site_group)
    if match is None:
        raise ValueError("invalid site group while constructing SPHINKS crosswalk")
    tokens = _SITE_TOKEN_PATTERN.findall(match.group("sites"))
    suffix = "".join(f"{residue.upper()}{position}{residue}" for residue, position in tokens)
    return f"{gene}-{suffix}"


def _site_cardinality(site_group: str) -> int:
    match = _SITE_PATTERN.fullmatch(site_group)
    if match is None:
        raise ValueError("invalid site group in admitted feature inventory")
    return len(_SITE_TOKEN_PATTERN.findall(match.group("sites")))


def _sphinks_crosswalk(
    site_groups: tuple[str, ...],
    source_genes: tuple[str, ...],
    approved_genes: tuple[str | None, ...],
    peptides: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str | None, ...], tuple[tuple[str, ...], ...], dict[str, object]]:
    catalog = master_kinase_catalog()
    tuple_index = {(item.source_site_label, item.peptide) for item in catalog.background_tuples}
    kinases_by_label: dict[str, set[str]] = defaultdict(set)
    for edge in catalog.edges:
        kinases_by_label[edge.source_site_label].add(edge.hgnc_symbol)

    labels: list[str | None] = []
    kinases: list[tuple[str, ...]] = []
    projection: list[dict[str, object]] = []
    exact_count = 0
    signature_count = 0
    for site_group, source_gene, approved_gene, row_peptides in zip(
        site_groups, source_genes, approved_genes, peptides, strict=True
    ):
        candidate_genes = {source_gene}
        if approved_gene is not None:
            candidate_genes.add(approved_gene)
        matched: set[str] = set()
        for gene in candidate_genes:
            label = _direct_sphinks_label(gene, site_group)
            if any((label, peptide) in tuple_index for peptide in row_peptides):
                matched.add(label)
        matched_label: str | None = next(iter(matched)) if len(matched) == 1 else None
        memberships = (
            tuple(sorted(kinases_by_label.get(matched_label, set())))
            if matched_label is not None
            else ()
        )
        if matched_label is not None:
            exact_count += 1
        if memberships:
            signature_count += 1
        labels.append(matched_label)
        kinases.append(memberships)
        projection.append(
            {
                "source_site_group": site_group,
                "source_gene": source_gene,
                "approved_gene": approved_gene,
                "modified_peptides": list(row_peptides),
                "sphinks_source_site_label": matched_label,
                "signature_kinases": list(memberships),
            }
        )
    metadata = {
        "policy": (
            "exact PDC composite site label plus exact modified peptide sequence; source and "
            "approved gene candidates must resolve to exactly one frozen SPHINKS tuple; "
            "ambiguous or unmatched rows remain unsupported"
        ),
        "composite_site_policy": "composite site groups remain indivisible and are never projected onto individual sites",
        "catalog_artifact_digest": catalog.artifact_digest,
        "catalog_content_digest": catalog.content_digest,
        "catalog_background_tuple_digest": catalog.background_tuple_digest,
        "catalog_signature_edge_digest": catalog.signature_edge_digest,
        "source_article_authors": catalog.article_authors,
        "source_article_title": catalog.article_title,
        "source_article_doi": catalog.article_doi,
        "source_license": catalog.source_license,
        "source_license_url": catalog.source_license_url,
        "source_transformation_notice": catalog.transformation_notice,
        "exact_site_peptide_rows": exact_count,
        "signature_rows": signature_count,
        "crosswalk_digest": _canonical_digest(projection),
    }
    return tuple(labels), tuple(kinases), metadata


def load_cohort(source_dir: Path, hgnc_source: Path) -> PhosphositeCohort:
    paths = verify_source_files(source_dir)
    metadata = verify_versioned_source_manifest(source_dir)
    locks = {lock.filename: lock for lock in SOURCE_FILES}
    sample_name = "KNCC_Glioblastoma_Evolution_Phosphoproteome.sample.txt"
    matrix_name = "KNCC_Glioblastoma_Evolution_Phosphoproteome.phosphosite.tmt11.tsv"
    sample_payload = _read_locked_payload(paths[sample_name], locks[sample_name])
    matrix_payload = _read_locked_payload(paths[matrix_name], locks[matrix_name])
    hgnc_payload = _read_hgnc_payload(hgnc_source)
    expected_headers, sample_oracles = _sample_map_headers(sample_payload)
    site_groups, source_genes, peptides, patients, delta, matrix_oracles = _read_matrix(
        matrix_payload,
        expected_headers,
        metadata,
    )
    approved, hgnc_ids, mapping_basis, hgnc_metadata = _hgnc_mapping(hgnc_payload, source_genes)
    sphinks_labels, signature_kinases, crosswalk = _sphinks_crosswalk(
        site_groups, source_genes, approved, peptides
    )
    delta.setflags(write=False)
    cohort = PhosphositeCohort(
        site_groups=site_groups,
        source_genes=source_genes,
        approved_genes=approved,
        hgnc_ids=hgnc_ids,
        gene_mapping_basis=mapping_basis,
        modified_peptides=peptides,
        sphinks_labels=sphinks_labels,
        signature_kinases=signature_kinases,
        patient_groups=patients,
        delta=delta,
        private_identifiers=metadata.private_identifiers,
        crosswalk_metadata={"hgnc": hgnc_metadata, "sphinks": crosswalk},
        oracles={**metadata.oracles, **sample_oracles, **matrix_oracles},
        source_attestation=SourceAttestation(
            source_file_sha256=tuple(lock.sha256 for lock in SOURCE_FILES),
            parsed_snapshot_sha256=(
                hashlib.sha256(sample_payload).hexdigest(),
                hashlib.sha256(matrix_payload).hexdigest(),
            ),
            source_manifest_sha256=PDC_SOURCE_MANIFEST_SHA256,
            hgnc_sha256=HGNC_SOURCE_SHA256,
            cohort_semantic_digest="",
        ),
    )
    attestation = cohort.source_attestation
    if attestation is None:
        raise AssertionError("source-attested cohort construction lost its attestation")
    return replace(
        cohort,
        source_attestation=replace(
            attestation,
            cohort_semantic_digest=_cohort_semantic_digest(cohort),
        ),
    )


def _fit_axis(delta: FloatArray, labels: tuple[str, ...]) -> AxisFit:
    pair_count = delta.shape[0]
    finite = np.isfinite(delta)
    support = finite.sum(axis=0).astype(np.int64)
    minimum_support = max(3, math.ceil(MIN_TRAIN_COVERAGE * pair_count))
    eligible = support >= minimum_support
    safe = np.where(finite, delta, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        center = np.nanmedian(safe, axis=0)
        mad = np.nanmedian(np.abs(safe - center), axis=0) * 1.4826
    positive = mad[eligible & np.isfinite(mad) & (mad > 0.0)]
    intensity_floor = (
        MIN_INTENSITY_FLOOR
        if positive.size == 0
        else max(MIN_INTENSITY_FLOOR, float(np.quantile(positive, INTENSITY_FLOOR_QUANTILE)))
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
    effect[eligible] = center[eligible] / scale[eligible] * np.sqrt(support[eligible] / pair_count)
    order = np.lexsort((np.asarray(labels, dtype=object), -np.abs(effect))).astype(np.int64)
    order = order[eligible[order]]
    return AxisFit(
        center, scale, support, eligible, effect, order, intensity_floor, iterations, converged
    )


def _weights(fit: AxisFit, top_count: int) -> tuple[IntArray, FloatArray]:
    selected = fit.order[: min(top_count, fit.order.size)]
    values = fit.effect[selected].astype(np.float64, copy=True)
    norm = float(np.abs(values).sum())
    return selected, values / norm if norm > 0.0 else np.zeros_like(values)


def _project(
    delta: FloatArray, scale: FloatArray, selected: IntArray, weights: FloatArray
) -> tuple[FloatArray, FloatArray, IntArray]:
    values = delta[:, selected]
    valid = np.isfinite(values)
    absolute = np.abs(weights)
    denominator = valid.astype(np.float64).dot(absolute)
    overlap = valid.sum(axis=1).astype(np.int64)
    numerator = np.where(valid, values / scale[selected], 0.0).dot(weights)
    minimum_features = max(3, math.ceil(MIN_SCORE_WEIGHT_COVERAGE * len(selected)))
    supported = (denominator >= MIN_SCORE_WEIGHT_COVERAGE) & (overlap >= minimum_features)
    scores = np.full(delta.shape[0], np.nan, dtype=np.float64)
    scores[supported] = numerator[supported] / denominator[supported]
    return scores, denominator, overlap


def _score_metrics(scores: FloatArray) -> dict[str, float | int]:
    supported = np.isfinite(scores)
    values = scores[supported]
    if values.size == 0:
        return {
            "supported_pairs": 0,
            "abstained_pairs": int(scores.size),
            "direction_accuracy": 0.0,
            "median_sign_margin": 0.0,
        }
    return {
        "supported_pairs": int(values.size),
        "abstained_pairs": int(scores.size - values.size),
        "direction_accuracy": float(np.mean(values > 0.0)),
        "median_sign_margin": float(np.median(2.0 * values)),
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


def _candidate_summary(
    scores: list[float], *, total_pairs: int, top_feature_count: int
) -> dict[str, float | int]:
    values = np.asarray(scores, dtype=np.float64)
    supported = int(values.size)
    accuracy = float(np.mean(values > 0.0)) if supported else 0.0
    standard_error = (
        math.sqrt(max(accuracy * (1.0 - accuracy), 0.25 / supported) / supported)
        if supported
        else 1.0
    )
    return {
        "top_feature_count": top_feature_count,
        "supported_pairs": supported,
        "abstained_pairs": total_pairs - supported,
        "direction_accuracy": accuracy,
        "direction_accuracy_standard_error": standard_error,
        "median_sign_margin": float(np.median(2.0 * values)) if supported else 0.0,
    }


def _one_standard_error_choice(
    summaries: dict[int, dict[str, float | int]],
) -> tuple[int, dict[str, object]]:
    maximum_supported = max(int(item["supported_pairs"]) for item in summaries.values())
    coverage_matched = {
        count: item
        for count, item in summaries.items()
        if int(item["supported_pairs"]) == maximum_supported
    }
    best_count = max(
        coverage_matched,
        key=lambda count: (
            float(coverage_matched[count]["direction_accuracy"]),
            float(coverage_matched[count]["median_sign_margin"]),
            -count,
        ),
    )
    best = coverage_matched[best_count]
    threshold = float(best["direction_accuracy"]) - float(best["direction_accuracy_standard_error"])
    admissible = sorted(
        count
        for count, item in coverage_matched.items()
        if float(item["direction_accuracy"]) >= threshold
    )
    selected = admissible[0]
    return selected, {
        "rule": (
            "maximum held-pair support, then smallest feature count whose pooled held-pair "
            "accuracy is within one binomial standard error of the best candidate"
        ),
        "best_accuracy_candidate": best_count,
        "best_accuracy": float(best["direction_accuracy"]),
        "best_accuracy_standard_error": float(best["direction_accuracy_standard_error"]),
        "one_standard_error_threshold": threshold,
        "admissible_feature_counts": admissible,
        "selected_feature_count": selected,
    }


def _cross_validated_candidate_summaries(
    cohort: PhosphositeCohort, *, fold_count: int, salt: str
) -> dict[int, dict[str, float | int]]:
    folds = _folds(cohort.patient_groups, fold_count, salt)
    all_indices = np.arange(len(cohort.patient_groups), dtype=np.int64)
    by_count: dict[int, list[float]] = {count: [] for count in TOP_FEATURE_CANDIDATES}
    totals = dict.fromkeys(TOP_FEATURE_CANDIDATES, 0)
    for held in folds:
        train = np.setdiff1d(all_indices, held, assume_unique=True)
        fit = _fit_axis(cohort.delta[train], cohort.site_groups)
        for count in TOP_FEATURE_CANDIDATES:
            selected, weights = _weights(fit, count)
            scores, _, _ = _project(cohort.delta[held], fit.scale, selected, weights)
            by_count[count].extend(float(value) for value in scores[np.isfinite(scores)])
            totals[count] += int(scores.size)
    return {
        count: _candidate_summary(
            by_count[count], total_pairs=totals[count], top_feature_count=count
        )
        for count in TOP_FEATURE_CANDIDATES
    }


def _selection_partition_stability(
    cohort: PhosphositeCohort,
) -> tuple[int, dict[str, object]]:
    selections: list[int] = []
    repeat_summaries: list[dict[str, object]] = []
    repeat_accuracies: dict[int, list[float]] = defaultdict(list)
    repeat_supported: dict[int, list[int]] = defaultdict(list)
    repeat_abstained: dict[int, list[int]] = defaultdict(list)
    aggregate_margins: dict[int, list[float]] = defaultdict(list)
    for repeat in range(SELECTION_STABILITY_REPEATS):
        summaries = _cross_validated_candidate_summaries(
            cohort,
            fold_count=SELECTION_STABILITY_FOLDS,
            salt=f"pdc000515-selection-stability-v2:{repeat}",
        )
        selected, decision = _one_standard_error_choice(summaries)
        selections.append(selected)
        repeat_summaries.append(
            {
                "repeat_index": repeat,
                "selected_feature_count": selected,
                "candidate_summaries": {str(key): value for key, value in summaries.items()},
                "decision": decision,
            }
        )
        for count, summary in summaries.items():
            repeat_accuracies[count].append(float(summary["direction_accuracy"]))
            repeat_supported[count].append(int(summary["supported_pairs"]))
            repeat_abstained[count].append(int(summary["abstained_pairs"]))
            aggregate_margins[count].append(float(summary["median_sign_margin"]))

    aggregate: dict[int, dict[str, float | int]] = {}
    for count in TOP_FEATURE_CANDIDATES:
        accuracies = np.asarray(repeat_accuracies[count], dtype=np.float64)
        aggregate[count] = {
            "top_feature_count": count,
            "repeat_mean_direction_accuracy": float(np.mean(accuracies)),
            "repeat_accuracy_standard_deviation": float(np.std(accuracies, ddof=1)),
            "repeat_minimum_direction_accuracy": float(np.min(accuracies)),
            "repeat_maximum_direction_accuracy": float(np.max(accuracies)),
            "minimum_supported_pairs_per_repeat": min(repeat_supported[count]),
            "maximum_supported_pairs_per_repeat": max(repeat_supported[count]),
            "maximum_abstained_pairs_per_repeat": max(repeat_abstained[count]),
            "dependent_total_supported_evaluations": sum(repeat_supported[count]),
            "repeat_median_sign_margin": float(np.median(aggregate_margins[count])),
        }
    selection_counts = Counter(selections)
    modal_count, modal_occurrences = max(
        selection_counts.items(), key=lambda item: (item[1], -item[0])
    )
    modal_fraction = modal_occurrences / SELECTION_STABILITY_REPEATS
    z_95 = 1.959963984540054
    denominator = 1.0 + z_95**2 / SELECTION_STABILITY_REPEATS
    wilson_center = (modal_fraction + z_95**2 / (2.0 * SELECTION_STABILITY_REPEATS)) / denominator
    wilson_half_width = (
        z_95
        * math.sqrt(
            modal_fraction * (1.0 - modal_fraction) / SELECTION_STABILITY_REPEATS
            + z_95**2 / (4.0 * SELECTION_STABILITY_REPEATS**2)
        )
        / denominator
    )
    wilson_lower = wilson_center - wilson_half_width
    passed = (
        modal_fraction >= SELECTION_STABILITY_MINIMUM
        and wilson_lower >= SELECTION_STABILITY_WILSON_LOWER_MINIMUM
    )
    return modal_count, {
        "protocol": (
            "deterministic alternate patient-group partitions; each repeat refits every "
            "candidate and applies the same maximum-support one-standard-error rule; the "
            "modal repeat choice is used without treating repeated predictions from the same "
            "patients as independent"
        ),
        "repeat_count": SELECTION_STABILITY_REPEATS,
        "fold_count": SELECTION_STABILITY_FOLDS,
        "minimum_modal_fraction": SELECTION_STABILITY_MINIMUM,
        "minimum_wilson_95_lower_bound": SELECTION_STABILITY_WILSON_LOWER_MINIMUM,
        "selected_feature_count": modal_count,
        "selection_counts": {
            str(count): selection_counts[count] for count in TOP_FEATURE_CANDIDATES
        },
        "modal_feature_count": modal_count,
        "modal_fraction": modal_fraction,
        "modal_fraction_wilson_95_interval": [
            wilson_lower,
            wilson_center + wilson_half_width,
        ],
        "passed": passed,
        "repeat_descriptive_candidate_summaries": {
            str(key): value for key, value in aggregate.items()
        },
        "independence_guard": (
            "the dependent total held-pair evaluations are descriptive only and are never "
            "used as a binomial sample size"
        ),
        "repeats": repeat_summaries,
    }


def _nested_cross_validation(cohort: PhosphositeCohort) -> tuple[int, dict[str, object]]:
    outer = _folds(cohort.patient_groups, OUTER_FOLDS, "pdc000515-outer-v2")
    all_indices = np.arange(len(cohort.patient_groups), dtype=np.int64)
    selected_counts: Counter[int] = Counter()
    outer_results: list[dict[str, object]] = []
    pooled: list[float] = []
    fixed_candidate_scores: dict[int, list[float]] = {count: [] for count in TOP_FEATURE_CANDIDATES}
    fixed_candidate_totals = dict.fromkeys(TOP_FEATURE_CANDIDATES, 0)
    for outer_index, held in enumerate(outer):
        train = np.setdiff1d(all_indices, held, assume_unique=True)
        train_groups = tuple(cohort.patient_groups[index] for index in train)
        inner = _folds(train_groups, INNER_FOLDS, f"pdc000515-inner-v2:{outer_index}")
        by_count: dict[int, list[float]] = {count: [] for count in TOP_FEATURE_CANDIDATES}
        totals = dict.fromkeys(TOP_FEATURE_CANDIDATES, 0)
        for inner_held in inner:
            inner_train = np.setdiff1d(
                np.arange(train.size, dtype=np.int64), inner_held, assume_unique=True
            )
            fit = _fit_axis(cohort.delta[train[inner_train]], cohort.site_groups)
            for count in TOP_FEATURE_CANDIDATES:
                selected, weights = _weights(fit, count)
                scores, _, _ = _project(
                    cohort.delta[train[inner_held]], fit.scale, selected, weights
                )
                by_count[count].extend(float(value) for value in scores[np.isfinite(scores)])
                totals[count] += int(scores.size)
        summaries = {
            count: _candidate_summary(
                by_count[count], total_pairs=totals[count], top_feature_count=count
            )
            for count in TOP_FEATURE_CANDIDATES
        }
        selected_top, decision = _one_standard_error_choice(summaries)
        selected_counts[selected_top] += 1
        fit = _fit_axis(cohort.delta[train], cohort.site_groups)
        selected, weights = _weights(fit, selected_top)
        scores, _, _ = _project(cohort.delta[held], fit.scale, selected, weights)
        metrics = _score_metrics(scores)
        pooled.extend(float(value) for value in scores[np.isfinite(scores)])
        for count in TOP_FEATURE_CANDIDATES:
            fixed_selected, fixed_weights = _weights(fit, count)
            fixed_scores, _, _ = _project(
                cohort.delta[held], fit.scale, fixed_selected, fixed_weights
            )
            fixed_candidate_scores[count].extend(
                float(value) for value in fixed_scores[np.isfinite(fixed_scores)]
            )
            fixed_candidate_totals[count] += int(fixed_scores.size)
        outer_results.append(
            {
                "fold_index": outer_index,
                "training_pairs": int(train.size),
                "held_pairs": int(held.size),
                "selected_top_feature_count": selected_top,
                "inner_candidate_summaries": {str(key): value for key, value in summaries.items()},
                "inner_selection_decision": decision,
                **metrics,
            }
        )

    selected_top, partition_stability = _selection_partition_stability(cohort)
    fixed_summaries = {
        count: _candidate_summary(
            fixed_candidate_scores[count],
            total_pairs=fixed_candidate_totals[count],
            top_feature_count=count,
        )
        for count in TOP_FEATURE_CANDIDATES
    }
    supported = sum(cast("int", item["supported_pairs"]) for item in outer_results)
    abstained = sum(cast("int", item["abstained_pairs"]) for item in outer_results)
    correct = sum(
        cast("float", item["direction_accuracy"]) * cast("int", item["supported_pairs"])
        for item in outer_results
    )
    return selected_top, {
        "protocol": (
            "patient-grouped nested cross-validation with pooled inner held-pair scores, "
            "maximum-support one-standard-error selection, and every data-dependent fit "
            "restricted to training patients"
        ),
        "interpretation": (
            "held-pair recurrence-direction concordance; not clinical prediction or "
            "external validation"
        ),
        "outer_fold_count": OUTER_FOLDS,
        "inner_fold_count": INNER_FOLDS,
        "outer_fold_sizes": [len(fold) for fold in outer],
        "selected_top_feature_count": selected_top,
        "outer_selected_top_feature_counts": {
            str(count): selected_counts[count] for count in TOP_FEATURE_CANDIDATES
        },
        "selection_partition_stability": partition_stability,
        "fixed_candidate_outer_descriptive": {
            "validation_role": (
                "post-selection descriptive only; the release complexity was selected using "
                "alternate partitions of the full source cohort"
            ),
            "selected_feature_count": selected_top,
            "selected_feature_summary": fixed_summaries[selected_top],
            "candidate_summaries": {str(key): value for key, value in fixed_summaries.items()},
        },
        "supported_pairs": supported,
        "abstained_pairs": abstained,
        "direction_accuracy": correct / max(supported, 1),
        "balanced_label_swap_accuracy": correct / max(supported, 1),
        "balanced_label_swap_accuracy_role": (
            "derived sign-symmetry oracle from the same genuinely held within-patient "
            "contrasts; not independent evidence"
        ),
        "median_sign_margin": (float(np.median(2.0 * np.asarray(pooled))) if pooled else 0.0),
        "outer_folds": outer_results,
    }


def _bootstrap(
    cohort: PhosphositeCohort, fit: AxisFit, top_count: int, replicates: int
) -> tuple[FloatArray, FloatArray, dict[str, object]]:
    patient_count, site_count = cohort.delta.shape
    master = int.from_bytes(
        hashlib.sha256(
            f"{MODEL_ID}:{SOURCE_FILES[3].sha256}:patient-bootstrap-full-refit-v2".encode()
        ).digest()[:8],
        "big",
    )
    draws = np.zeros((replicates, site_count), dtype=np.float32)
    selected_count = np.zeros(site_count, dtype=np.int64)
    ensemble: list[dict[str, object]] = []
    final_selected = {int(value) for value in fit.order[:top_count]}
    jaccards: list[float] = []
    all_converged = True
    for replicate_index in range(replicates):
        seed = int.from_bytes(
            hashlib.sha256(f"{master}:replicate:{replicate_index}".encode()).digest()[:8],
            "big",
        )
        counts = np.random.default_rng(seed).multinomial(
            patient_count, np.full(patient_count, 1.0 / patient_count)
        )
        sampled_indices = np.repeat(np.arange(patient_count, dtype=np.int64), counts)
        replicate_fit = _fit_axis(cohort.delta[sampled_indices], cohort.site_groups)
        order = replicate_fit.order[fit.eligible[replicate_fit.order]][:top_count]
        values = replicate_fit.effect[order].astype(np.float64, copy=True)
        norm = float(np.abs(values).sum())
        if order.size == 0 or norm <= 0.0:
            raise ValueError("bootstrap replicate has no supported phosphosite coefficients")
        values /= norm
        draws[replicate_index, order] = values.astype(np.float32)
        selected_count[order] += 1
        replicate_selected = {int(value) for value in order}
        union = final_selected | replicate_selected
        jaccard = len(final_selected & replicate_selected) / max(len(union), 1)
        jaccards.append(jaccard)
        all_converged = all_converged and replicate_fit.converged
        stable = np.argsort(order, kind="stable")
        projection: dict[str, object] = {
            "replicate_index": replicate_index,
            "seed_hex": f"{seed:016x}",
            "fit_iterations": replicate_fit.iterations,
            "fit_converged": replicate_fit.converged,
            "selected_jaccard_to_final": _q(jaccard),
            "feature_indices": [int(value) for value in order[stable]],
            "coefficients": [_q(value) for value in values[stable]],
            "scales": [_q(replicate_fit.scale[value]) for value in order[stable]],
        }
        ensemble.append({**projection, "replicate_digest": _canonical_digest(projection)})
    intervals = np.quantile(draws.astype(np.float64), [0.05, 0.5, 0.95], axis=0).T
    median_jaccard = float(np.median(jaccards))
    return (
        selected_count / replicates,
        intervals,
        {
            "method": (
                "deterministic patient multinomial bootstrap with exact per-replicate Huber "
                "center, scale, support, and top-k refitting within the frozen full-cohort "
                "release-eligible inventory"
            ),
            "validation_role": "none",
            "uncertainty_role": (
                "full-cohort coefficient and feature-selection uncertainty; empirical intervals "
                "are not coverage-calibrated"
            ),
            "requested_replicates": replicates,
            "completed_replicates": replicates,
            "all_refits_converged": all_converged,
            "minimum_selected_jaccard_to_final": _q(min(jaccards)),
            "median_selected_jaccard_to_final": _q(median_jaccard),
            "feature_selection_stability_minimum": BOOTSTRAP_MEDIAN_JACCARD_MINIMUM,
            "feature_selection_stability_passed": (
                median_jaccard >= BOOTSTRAP_MEDIAN_JACCARD_MINIMUM
            ),
            "interval": "central 90% (5th/95th percentiles), not coverage-calibrated",
            "master_seed_hex": f"{master:016x}",
            "ensemble_digest": _canonical_digest(ensemble),
            "replicates": ensemble,
        },
    )


def _q(value: float) -> float:
    result = round(float(value), 8)
    return 0.0 if result == 0.0 else result


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _cohort_semantic_digest(cohort: PhosphositeCohort) -> str:
    metadata: dict[str, object] = {
        "site_groups": list(cohort.site_groups),
        "source_genes": list(cohort.source_genes),
        "approved_genes": list(cohort.approved_genes),
        "hgnc_ids": list(cohort.hgnc_ids),
        "gene_mapping_basis": list(cohort.gene_mapping_basis),
        "modified_peptides": [list(value) for value in cohort.modified_peptides],
        "sphinks_labels": list(cohort.sphinks_labels),
        "signature_kinases": [list(value) for value in cohort.signature_kinases],
        "patient_groups": list(cohort.patient_groups),
        "private_identifiers": sorted(cohort.private_identifiers),
        "crosswalk_metadata": cohort.crosswalk_metadata,
        "oracles": cohort.oracles,
    }
    delta = np.ascontiguousarray(cohort.delta, dtype="<f8")
    digest = hashlib.sha256()
    digest.update(b"glio-proteogen:pdc000515-cohort-semantic-snapshot:v1\x00")
    digest.update(_canonical_bytes(metadata))
    digest.update(json.dumps(delta.shape, separators=(",", ":")).encode("ascii"))
    digest.update(b"\x00<f8\x00")
    digest.update(delta.tobytes(order="C"))
    return "sha256:" + digest.hexdigest()


def _assert_deidentified_artifact(
    artifact: dict[str, object], private_identifiers: frozenset[str]
) -> None:
    raw_features = artifact.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("PDC000515 artifact feature inventory is not an array")
    for raw_feature in raw_features:
        feature = _object(raw_feature, "feature")
        released = feature.get("numerical_release_state") == "released_minimum_support"
        eligible = feature.get("eligible") is True
        numeric = (feature.get("transition_center"), feature.get("transition_scale"))
        if released is not eligible:
            raise ValueError("PDC000515 numerical release state disagrees with eligibility")
        if eligible and any(value is None for value in numeric):
            raise ValueError("eligible PDC000515 feature omitted aggregate numerics")
        if not eligible and any(value is not None for value in numeric):
            raise ValueError("low-support PDC000515 feature leaked aggregate numerics")
    payload = _canonical_bytes(artifact)
    lowered = payload.lower()
    if b"kncc_gbm" in lowered or b'"patient_groups"' in lowered:
        raise ValueError("patient/specimen labels leaked into PDC000515 artifact")
    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", lowered))
    for identifier in private_identifiers:
        encoded = identifier.encode("utf-8")
        if encoded.lower() in lowered:
            raise ValueError("PDC000515 private source identifier leaked into artifact")
        for source_form in (encoded, encoded + b"\n", json.dumps(identifier).encode("utf-8")):
            derived = {
                hashlib.md5(source_form, usedforsecurity=False).hexdigest().encode(),
                hashlib.sha1(source_form, usedforsecurity=False).hexdigest().encode(),
                hashlib.sha256(source_form).hexdigest().encode(),
                hashlib.sha512(source_form).hexdigest().encode(),
            }
            if not digest_tokens.isdisjoint(derived):
                raise ValueError("low-entropy source identifier hash leaked into artifact")
    allowed_uuids = {
        PDC_STUDY_VERSION_UUID.encode(),
        *(lock.uuid.encode() for lock in SOURCE_FILES),
    }
    observed_uuids = set(_UUID_PATTERN_BYTES.findall(lowered))
    if observed_uuids != allowed_uuids:
        raise ValueError("artifact UUID inventory is not limited to the study and six files")


def _canonical_patient_order(cohort: PhosphositeCohort) -> PhosphositeCohort:
    if len(set(cohort.patient_groups)) != len(cohort.patient_groups):
        raise ValueError("patient groups must be unique before canonical ordering")
    order = np.asarray(
        sorted(range(len(cohort.patient_groups)), key=cohort.patient_groups.__getitem__),
        dtype=np.int64,
    )
    if np.array_equal(order, np.arange(len(cohort.patient_groups), dtype=np.int64)):
        return cohort
    return replace(
        cohort,
        patient_groups=tuple(cohort.patient_groups[index] for index in order),
        delta=cohort.delta[order].copy(),
    )


def _expected_source_attestation() -> SourceAttestation:
    locks = {lock.filename: lock for lock in SOURCE_FILES}
    return SourceAttestation(
        source_file_sha256=tuple(lock.sha256 for lock in SOURCE_FILES),
        parsed_snapshot_sha256=(
            locks["KNCC_Glioblastoma_Evolution_Phosphoproteome.sample.txt"].sha256,
            locks["KNCC_Glioblastoma_Evolution_Phosphoproteome.phosphosite.tmt11.tsv"].sha256,
        ),
        source_manifest_sha256=PDC_SOURCE_MANIFEST_SHA256,
        hgnc_sha256=HGNC_SOURCE_SHA256,
        cohort_semantic_digest=EXPECTED_COHORT_SEMANTIC_DIGEST,
    )


def _build_artifact(
    cohort: PhosphositeCohort,
    *,
    bootstrap_replicates: int,
    source_attested: bool,
) -> dict[str, object]:
    if not 1 <= bootstrap_replicates <= 256:
        raise ValueError("bootstrap_replicates must be between 1 and 256")
    cohort = _canonical_patient_order(cohort)
    selected_top, evaluation = _nested_cross_validation(cohort)
    fit = _fit_axis(cohort.delta, cohort.site_groups)
    selected, coefficients = _weights(fit, selected_top)
    dense = np.zeros(len(cohort.site_groups), dtype=np.float64)
    dense[selected] = coefficients
    stability, intervals, bootstrap = _bootstrap(cohort, fit, selected_top, bootstrap_replicates)
    selected_set = set(selected.tolist())
    cardinalities = tuple(_site_cardinality(value) for value in cohort.site_groups)
    features = [
        {
            "source_site_group": site_group,
            "site_cardinality": cardinalities[index],
            "composite_site_group": cardinalities[index] > 1,
            "source_gene": cohort.source_genes[index],
            "approved_gene": cohort.approved_genes[index],
            "hgnc_id": cohort.hgnc_ids[index],
            "gene_mapping_basis": cohort.gene_mapping_basis[index],
            "modified_peptides": list(cohort.modified_peptides[index]),
            "sphinks_source_site_label": cohort.sphinks_labels[index],
            "sphinks_signature_kinases": list(cohort.signature_kinases[index]),
            "numerical_release_state": (
                "released_minimum_support"
                if fit.eligible[index]
                else "suppressed_insufficient_support"
            ),
            "transition_center": (_q(fit.center[index]) if fit.eligible[index] else None),
            "transition_scale": _q(fit.scale[index]) if fit.eligible[index] else None,
            "paired_support": int(fit.support[index]),
            "paired_coverage": _q(fit.support[index] / len(cohort.patient_groups)),
            "eligible": bool(fit.eligible[index]),
            "selected": index in selected_set,
            "coefficient": _q(dense[index]),
            "bootstrap_selection_stability": _q(stability[index]),
            "coefficient_interval_90": [_q(value) for value in intervals[index]],
        }
        for index, site_group in enumerate(cohort.site_groups)
    ]
    importer_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hgnc_crosswalk = _object(cohort.crosswalk_metadata["hgnc"], "hgnc_crosswalk")
    sphinks_crosswalk = _object(cohort.crosswalk_metadata["sphinks"], "sphinks_crosswalk")
    profile_payload: dict[str, object] = {
        "profile_id": PROFILE_ID,
        "model_id": MODEL_ID,
        "numpy_version": np.__version__,
        "source_manifest_sha256": "sha256:" + PDC_SOURCE_MANIFEST_SHA256,
        "source_file_sha256": ["sha256:" + lock.sha256 for lock in SOURCE_FILES],
        "hgnc_mapping_digest": hgnc_crosswalk["mapping_digest"],
        "sphinks_crosswalk_digest": sphinks_crosswalk["crosswalk_digest"],
        "importer_sha256": "sha256:" + importer_sha,
        "constants": {
            "huber_k": HUBER_K,
            "huber_max_iterations": HUBER_MAX_ITERATIONS,
            "huber_tolerance": HUBER_TOLERANCE,
            "minimum_training_pair_coverage": MIN_TRAIN_COVERAGE,
            "numerical_release_minimum_pair_coverage": MIN_TRAIN_COVERAGE,
            "minimum_scoring_weight_coverage": MIN_SCORE_WEIGHT_COVERAGE,
            "intensity_floor_quantile": INTENSITY_FLOOR_QUANTILE,
            "minimum_intensity_floor": MIN_INTENSITY_FLOOR,
            "outer_folds": OUTER_FOLDS,
            "inner_folds": INNER_FOLDS,
            "top_feature_candidates": list(TOP_FEATURE_CANDIDATES),
            "selection_rule": "maximum-support pooled one-standard-error smallest model",
            "selection_stability_repeats": SELECTION_STABILITY_REPEATS,
            "selection_stability_folds": SELECTION_STABILITY_FOLDS,
            "selection_stability_minimum": SELECTION_STABILITY_MINIMUM,
            "selection_stability_wilson_95_lower_minimum": (
                SELECTION_STABILITY_WILSON_LOWER_MINIMUM
            ),
            "bootstrap_method": (
                "exact patient multinomial full Huber refit and reselection within the "
                "frozen full-cohort release-eligible inventory"
            ),
            "bootstrap_replicates": bootstrap_replicates,
            "bootstrap_median_selected_jaccard_minimum": (BOOTSTRAP_MEDIAN_JACCARD_MINIMUM),
        },
    }
    artifact: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "profile_id": PROFILE_ID,
        "profile_digest": _canonical_digest(profile_payload),
        "profile": profile_payload,
        "source_attestation_state": (
            "verified_exact_snapshots" if source_attested else "unattested_test_only"
        ),
        "source_lock": {
            "pdc_study_id": PDC_STUDY_ID,
            "pdc_study_version_uuid": PDC_STUDY_VERSION_UUID,
            "versioned_source_manifest": {
                "filename": PDC_SOURCE_MANIFEST_FILENAME,
                "bytes": PDC_SOURCE_MANIFEST_BYTES,
                "sha256": "sha256:" + PDC_SOURCE_MANIFEST_SHA256,
                "schema_version": PDC_SOURCE_MANIFEST_SCHEMA,
                "graphql_api_version": PDC_GRAPHQL_API_VERSION,
                "binding": "complete canonical stable-field responses for exact study version plus six verified Protein Assembly files",
            },
            "files": [
                {
                    "filename": lock.filename,
                    "uuid": lock.uuid,
                    "bytes": lock.bytes,
                    "md5": lock.md5,
                    "sha256": lock.sha256,
                }
                for lock in SOURCE_FILES
            ],
        },
        "cohort_oracles": cohort.oracles,
        "crosswalk": cohort.crosswalk_metadata,
        "preprocessing": {
            "measurement": "PDC CDAP phosphosite Log sample/reference ratio",
            "paired_contrast": "T2-minus-T1 within the phosphoproteome assay",
            "technical_repeat_policy": "median collapse within exact source specimen before paired differencing",
            "missing_value_policy": "blank remains missing; paired delta requires observed T1 and T2",
            "composite_site_policy": "source multi-site groups are indivisible observations and are never split",
            "assay_compatibility": "phosphoproteome-only; no raw-level merge with PDC000514 protein ratios",
        },
        "fit": {
            "model_form": "robust sparse paired T2-minus-T1 phosphosite concordance axis",
            "interpretation": "source-cohort recurrence-transition concordance, not a recurrence outcome predictor",
            "selected_top_feature_count": len(selected),
            "eligible_feature_count": int(fit.eligible.sum()),
            "intensity_variance_floor": _q(fit.intensity_floor),
            "huber_iterations": fit.iterations,
            "huber_converged": fit.converged,
            "coefficient_normalization": "L1 absolute sum equals one",
        },
        "fit_evaluation": evaluation,
        "bootstrap": bootstrap,
        "runtime_quality_gates": {
            "selection_stability_passed": (
                _object(
                    evaluation["selection_partition_stability"],
                    "selection_partition_stability",
                ).get("passed")
                is True
            ),
            "bootstrap_full_refit_passed": bootstrap.get("all_refits_converged") is True,
            "bootstrap_feature_selection_stability_passed": (
                bootstrap.get("feature_selection_stability_passed") is True
            ),
            "bootstrap_calibration_passed": False,
            "bootstrap_calibration_reason": (
                "exact source-cohort resampling quantifies fit and selection variability, "
                "but no independent interval-coverage calibration cohort exists"
            ),
            "output_policy": (
                "uncalibrated bootstrap intervals force runtime output to LIMITED or "
                "ABSTAINED even when selection stability and every exact refit pass"
            ),
        },
        "occupancy_like_view": {
            "support": "not_fitted",
            "reason": "cognate-protein adjustment is deliberately deferred until its own training-fold-only implementation and outer-CV tests are complete",
            "silent_fusion": False,
        },
        "features": features,
        "provenance": {
            "article_authors": "Kim et al.",
            "article_title": ARTICLE_TITLE,
            "article_journal": "Cancer Cell 42(3):358-377.e8 (2024)",
            "article_doi": ARTICLE_DOI,
            "pmid": ARTICLE_PMID,
            "pmcid": ARTICLE_PMCID,
            "pdc_study_url": "https://pdc.cancer.gov/pdc/study/PDC000515",
            "pdc_data_use_guideline": "https://pdc.cancer.gov/pdc/data-use-guidelines",
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "transformation_notice": "Transformed into de-identified aggregate phosphosite coefficients; source patient observations, labels, and sample/case/aliquot UUIDs are not redistributed. Changes are not endorsed by PDC or the source authors.",
            "third_party_sources": [
                {
                    "role": (
                        "exact modified-peptide/site crosswalk and frozen kinase-signature "
                        "memberships for matched rows"
                    ),
                    "article_authors": sphinks_crosswalk["source_article_authors"],
                    "article_title": sphinks_crosswalk["source_article_title"],
                    "article_doi": sphinks_crosswalk["source_article_doi"],
                    "license": sphinks_crosswalk["source_license"],
                    "license_url": sphinks_crosswalk["source_license_url"],
                    "transformation_notice": sphinks_crosswalk["source_transformation_notice"],
                }
            ],
            "limitations": [
                "Research use only; not clinically validated, diagnostic, prognostic, or prescriptive.",
                "Nested held-pair concordance is internal source-cohort evidence, not external validation.",
                "The phosphosite matrix is sparse and inherits TMT, enrichment, localization, batch, sampling, and cohort-selection limitations.",
                "Composite phosphosite groups cannot be interpreted as independently quantified residues.",
                "No protein/phosphosite fusion or occupancy-like estimate is emitted by this artifact version.",
            ],
        },
    }
    _assert_deidentified_artifact(artifact, cohort.private_identifiers)
    return {**artifact, "artifact_digest": _canonical_digest(artifact)}


def build_artifact(
    cohort: PhosphositeCohort, *, bootstrap_replicates: int = BOOTSTRAP_REPLICATES
) -> AttestedArtifact:
    """Build a production artifact only from the exact verified byte snapshots."""

    if cohort.delta.flags.writeable:
        raise ValueError("production PDC000515 cohort matrix must be immutable")
    if _cohort_semantic_digest(cohort) != EXPECTED_COHORT_SEMANTIC_DIGEST:
        raise ValueError("production PDC000515 cohort semantic digest changed")
    if cohort.source_attestation != _expected_source_attestation():
        raise ValueError(
            "production PDC000515 artifact requires an exact source-snapshot attestation"
        )
    document = _build_artifact(
        cohort,
        bootstrap_replicates=bootstrap_replicates,
        source_attested=True,
    )
    return AttestedArtifact(
        document=document,
        canonical_payload=_canonical_bytes(document),
        private_identifiers=cohort.private_identifiers,
        capability=_ARTIFACT_WRITE_CAPABILITY,
    )


def _build_unattested_artifact_for_tests(
    cohort: PhosphositeCohort, *, bootstrap_replicates: int
) -> dict[str, object]:
    if cohort.source_attestation is not None:
        raise ValueError("test-only builder rejects source-attested cohorts")
    return _build_artifact(
        cohort,
        bootstrap_replicates=bootstrap_replicates,
        source_attested=False,
    )


def write_artifact(artifact: object, destination: Path) -> None:
    if not isinstance(artifact, AttestedArtifact):
        raise ValueError("refusing to write an unattested PDC000515 artifact")
    if artifact.capability is not _ARTIFACT_WRITE_CAPABILITY:
        raise ValueError("refusing to write a PDC000515 artifact with an invalid receipt")
    document = artifact.document
    if document.get("source_attestation_state") != "verified_exact_snapshots":
        raise ValueError("refusing to write an unattested PDC000515 artifact")
    payload = _canonical_bytes(document)
    if payload != artifact.canonical_payload:
        raise ValueError("PDC000515 artifact changed after validation")
    content = dict(document)
    supplied_digest = content.pop("artifact_digest", None)
    if supplied_digest != _canonical_digest(content):
        raise ValueError("PDC000515 artifact content digest changed before write")
    _assert_deidentified_artifact(document, artifact.private_identifiers)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _default_output() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm_phospho"
        / "data"
        / "kncc_paired_phosphosite_transition.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument("--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES)
    args = parser.parse_args()
    cohort = load_cohort(args.source_dir, args.hgnc_source)
    artifact = build_artifact(cohort, bootstrap_replicates=args.bootstrap_replicates)
    write_artifact(artifact, args.output)
    payload = args.output.read_bytes()
    document = artifact.document
    print(
        json.dumps(
            {
                "output": str(args.output),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "artifact_digest": document["artifact_digest"],
                "profile_digest": document["profile_digest"],
                "strict_pairs": cohort.oracles["strict_t1_t2_pairs"],
                "phosphosite_rows": len(cohort.site_groups),
                "bootstrap_replicates": args.bootstrap_replicates,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
