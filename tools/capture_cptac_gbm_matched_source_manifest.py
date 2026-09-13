# ruff: noqa: E501, PLR2004, S310, T201, TRY003, TRY004
"""Capture a private, exact source-admission receipt for matched CPTAC GBM assays.

The matched protein/phosphosite bundle is intentionally kept outside the repository.  This
tool binds the six local files to the official PDC000204/PDC000205 file manifests and proves
that the two TMT11 sample maps resolve to the same official aliquots.  The resulting JSON
contains source identifiers and must remain beside the external inputs; it is not package data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

PDC_GRAPHQL_ENDPOINT: Final = "https://pdc.cancer.gov/graphql"
PDC_GRAPHQL_API_VERSION: Final = "1.0.0"
MANIFEST_SCHEMA: Final = "glio-proteogen.cptac-gbm-matched-source-manifest/1.0.0"
MANIFEST_FILENAME: Final = "CPTAC_GBM_MATCHED.v1.canonical-source-lock.json"
STUDY_VERSIONS: Final = {
    "PDC000204": "cfe9f4a2-1797-11ea-9bfa-0a42f3c845fe",
    "PDC000205": "efc3143a-1797-11ea-9bfa-0a42f3c845fe",
}

SAMPLE_MAP_FILES: Final = {
    "PDC000204": "CPTAC3_Glioblastoma_Multiforme_Proteome.sample.txt",
    "PDC000205": "CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.sample.txt",
}
TMT_CHANNELS: Final = (
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


@dataclass(frozen=True, slots=True)
class FileLock:
    study_id: str
    filename: str
    file_uuid: str
    bytes: int
    md5: str
    sha256: str


# These locks are deliberately explicit.  A similarly named file from another study or
# processing release must fail admission rather than being silently substituted.
SOURCE_FILES: Final = (
    FileLock(
        "PDC000204",
        "CPTAC3_Glioblastoma_Multiforme_Proteome.tmt11.tsv",
        "9b86ba80-f981-4abe-97d4-a39f5e1d05b3",
        48_440_330,
        "ed614fb12f72b9db9bc4667b6d349949",
        "fc7c7b595211b81482db9281fb1592e58492eef87ab7db1fd64f7e4ec3bc96bd",
    ),
    FileLock(
        "PDC000204",
        "CPTAC3_Glioblastoma_Multiforme_Proteome.sample.txt",
        "966db837-8236-48ab-b3e3-338d93c36965",
        3_795,
        "b1a598ad26a66015f339366e44799d6a",
        "faea4574cd423c54b064c201391a9591160dc98ac3b6a443adaf8975914d74d1",
    ),
    FileLock(
        "PDC000204",
        "CPTAC3_Glioblastoma_Multiforme_Proteome.summary.tsv",
        "ef8e1793-c019-4126-aa3f-07c80d7bdd4a",
        3_440_988,
        "7c439373623435dc266baaf6f351c5d4",
        "fb720446fc749a55d9bef97830d94e2412f11a74a5909e2ffc11c43ca6742911",
    ),
    FileLock(
        "PDC000205",
        "CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.phosphosite.tmt11.tsv",
        "cb6980c7-b568-4451-926d-cb383d452385",
        40_120_930,
        "f298c0e57e16f388cb32c22a9960be32",
        "49b20d25b63ee5785ec9340420dc0482a834c89f36f996a0e9cf4b7eda2298e2",
    ),
    FileLock(
        "PDC000205",
        "CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.sample.txt",
        "f6e9a797-cbd6-4d1b-8880-eefe30e57610",
        3_869,
        "1ca536ae8b2b5b628fbcab44b4715a81",
        "5b5567ae9df8bcd3abed5dc1e219bb50403f021a83053e6c20585e8f52567f13",
    ),
    FileLock(
        "PDC000205",
        "CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.summary.tsv",
        "865c422d-ab2b-46eb-b6a6-79d7fb73c0c1",
        2_038_094,
        "1b44277d2f866e823d88dfe493ae20be",
        "297972bc5ac7eec63d0da50f357210f0f0b15136c1d8e93e158c45db712f5d0e",
    ),
)

FILE_QUERY: Final = {
    study_id: (
        '{ filesPerStudy(study_id: "' + version + '", offset: 0, limit: 25000, acceptDUA: true) '
        "{ study_id pdc_study_id file_id file_name file_submitter_id file_type md5sum "
        "file_size data_category file_format } }"
    )
    for study_id, version in STUDY_VERSIONS.items()
}
STUDY_QUERY: Final = {
    study_id: (
        '{ study(study_id: "'
        + version
        + '") { study_id pdc_study_id study_name disease_type primary_site '
        "analytical_fraction experiment_type cases_count aliquots_count filesCount "
        "{ data_category file_type files_count } } }"
    )
    for study_id, version in STUDY_VERSIONS.items()
}
BIOSPECIMEN_QUERY: Final = {
    study_id: (
        '{ biospecimenPerStudy(study_id: "'
        + version
        + '", acceptDUA: true) { aliquot_id sample_id case_id aliquot_submitter_id '
        "sample_submitter_id case_submitter_id aliquot_status case_status sample_status "
        "sample_type disease_type primary_site pool taxon } }"
    )
    for study_id, version in STUDY_VERSIONS.items()
}


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _post(query: str) -> dict[str, object]:
    body = json.dumps({"query": query}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        PDC_GRAPHQL_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GLIO-PROTEOGEN-GBM-source-lock/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = cast("object", json.load(response))
    if not isinstance(result, dict) or result.get("errors"):
        raise ValueError("PDC GraphQL request did not return a clean response")
    data = result.get("data")
    if not isinstance(data, dict):
        raise ValueError("PDC GraphQL response omitted its data object")
    return cast("dict[str, object]", data)


def _records(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key)
    if isinstance(value, dict):
        return [cast("dict[str, object]", value)]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"PDC GraphQL response {key!r} is not a record collection")
    return cast("list[dict[str, object]]", value)


def _validate_destination(source_dir: Path, destination: Path) -> Path:
    try:
        root = source_dir.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("matched GBM source directory does not exist") from error
    expected = root / MANIFEST_FILENAME
    if destination.resolve(strict=False) != expected:
        raise ValueError(
            f"the private matched-source manifest must be written beside its inputs as {MANIFEST_FILENAME}"
        )
    return root


def verify_local_files(source_dir: Path) -> dict[str, Path]:
    """Verify bytes, MD5 and SHA-256 for every admitted local file."""
    paths: dict[str, Path] = {}
    for lock in SOURCE_FILES:
        path = source_dir / lock.filename
        if not path.is_file():
            raise ValueError(f"missing locked source file: {lock.filename}")
        payload = path.read_bytes()
        if len(payload) != lock.bytes:
            raise ValueError(
                f"size mismatch for {lock.filename}: expected {lock.bytes}, got {len(payload)}"
            )
        md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest()
        if md5 != lock.md5:
            raise ValueError(f"MD5 mismatch for {lock.filename}")
        sha256 = hashlib.sha256(payload).hexdigest()
        if sha256 != lock.sha256:
            raise ValueError(f"SHA-256 mismatch for {lock.filename}")
        paths[lock.filename] = path
    return paths


def parse_sample_map(payload: bytes) -> tuple[list[str], dict[str, object]]:
    """Return non-pool aliquot labels in channel order and structural map oracles."""
    rows = [
        row
        for row in csv.DictReader(io.StringIO(payload.decode("utf-8")), delimiter="\t")
        if str(row.get("AnalyticalSample", "")).strip()
    ]
    if not rows:
        raise ValueError("sample map has no data rows")
    required = {
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
    }
    if not required.issubset(rows[0]):
        raise ValueError("sample map is missing one or more TMT11 columns")
    channels = TMT_CHANNELS
    for row in rows:
        if any(row.get(channel) is None for channel in channels):
            raise ValueError("sample map contains a truncated TMT11 row")
        if str(row.get("126C", "")).strip() != "POOL":
            raise ValueError("sample map must use POOL as the 126C reference channel")
        if any(
            str(row.get(channel, "")).strip() == "POOL" for channel in channels if channel != "126C"
        ):
            raise ValueError("sample map contains POOL in a non-reference channel")
    labels = [
        str(row[channel]).strip()
        for row in rows
        for channel in channels
        if str(row.get(channel, "")).strip() and str(row.get(channel, "")).strip() != "POOL"
    ]
    if len(labels) != len(set(labels)):
        raise ValueError("sample map contains duplicate non-pool aliquot labels")
    if len(labels) != 110:
        raise ValueError("sample map must contain exactly 110 non-pool aliquot labels")
    return labels, {
        "rows": len(rows),
        "analytical_samples": len({str(row["AnalyticalSample"]) for row in rows}),
        "channels": channels,
        "non_pool_labels": len(labels),
        "label_digest": "sha256:" + hashlib.sha256(_canonical_bytes(labels)).hexdigest(),
    }


def _file_manifest_records(
    records: list[dict[str, object]], study_id: str
) -> dict[str, dict[str, object]]:
    result = {
        str(row.get("file_name")): row
        for row in records
        if str(row.get("file_name", ""))
        in {lock.filename for lock in SOURCE_FILES if lock.study_id == study_id}
    }
    for lock in (item for item in SOURCE_FILES if item.study_id == study_id):
        row = result.get(lock.filename)
        if row is None:
            raise ValueError(f"PDC {study_id} manifest omitted {lock.filename}")
        file_size = row.get("file_size")
        if isinstance(file_size, str) and file_size.isdigit():
            file_size = int(file_size)
        if str(row.get("file_id")) != lock.file_uuid or file_size != lock.bytes:
            raise ValueError(f"official file identity mismatch for {study_id}/{lock.filename}")
        if str(row.get("md5sum", "")).lower() != lock.md5:
            raise ValueError(f"official MD5 mismatch for {study_id}/{lock.filename}")
        if str(row.get("data_category")) != "Protein Assembly":
            raise ValueError(f"unexpected data category for {study_id}/{lock.filename}")
    return result


def _validate_matched_biospecimens(
    biospecimens: dict[str, list[dict[str, object]]], labels: list[str]
) -> dict[str, object]:
    by_study: dict[str, dict[str, dict[str, object]]] = {}
    for study_id, rows in biospecimens.items():
        index = {
            str(row.get("aliquot_submitter_id")): row
            for row in rows
            if row.get("aliquot_submitter_id")
        }
        if len(rows) != 111 or len(index) != 111:
            raise ValueError(f"PDC {study_id} must expose 111 unique aliquot records")
        by_study[study_id] = index
    if len(labels) != 110:
        raise ValueError("matched TMT11 maps must contain exactly 110 non-pool aliquots")
    if set(labels) != set(by_study["PDC000204"]) - {"ref"} or set(labels) != set(
        by_study["PDC000205"]
    ) - {"ref"}:
        raise ValueError("local sample maps do not resolve to the official non-pool aliquot set")
    for label in labels:
        left, right = by_study["PDC000204"][label], by_study["PDC000205"][label]
        for field in ("case_id", "case_submitter_id", "sample_type", "taxon", "case_status"):
            if left.get(field) != right.get(field):
                raise ValueError(f"matched study metadata disagrees for {label}/{field}")
    primary_tumors = sum(
        by_study["PDC000204"][label].get("sample_type") == "Primary Tumor" for label in labels
    )
    normals = sum(
        by_study["PDC000204"][label].get("sample_type") == "Solid Tissue Normal" for label in labels
    )
    if (primary_tumors, normals) != (100, 10):
        raise ValueError(
            f"unexpected matched cohort sample types: tumors={primary_tumors}, normals={normals}"
        )
    qualified = sum(
        by_study["PDC000204"][label].get("case_status") == "Qualified" for label in labels
    )
    disqualified = sum(
        by_study["PDC000204"][label].get("case_status") == "Disqualified" for label in labels
    )
    if (qualified, disqualified) != (109, 1):
        raise ValueError(
            "matched non-pool cohort status oracle changed: "
            f"qualified={qualified}, disqualified={disqualified}"
        )
    return {
        "official_rows_per_study": {study_id: len(rows) for study_id, rows in biospecimens.items()},
        "matched_non_pool_aliquots": len(labels),
        "shared_primary_tumors": primary_tumors,
        "shared_solid_tissue_normals": normals,
        "shared_qualified_cases": qualified,
        "shared_disqualified_cases": disqualified,
        "pool_label": "ref",
    }


def capture(source_dir: Path, destination: Path) -> dict[str, object]:
    """Capture official metadata and bind it to the local six-file matched bundle."""
    root = _validate_destination(source_dir, destination)
    paths = verify_local_files(root)
    map_labels: dict[str, list[str]] = {}
    map_oracles: dict[str, dict[str, object]] = {}
    for study_id, filename in SAMPLE_MAP_FILES.items():
        map_labels[study_id], map_oracles[study_id] = parse_sample_map(paths[filename].read_bytes())
    if map_labels["PDC000204"] != map_labels["PDC000205"]:
        raise ValueError("protein and phosphosite sample maps have different non-pool order")

    studies: dict[str, list[dict[str, object]]] = {}
    files: dict[str, list[dict[str, object]]] = {}
    biospecimens: dict[str, list[dict[str, object]]] = {}
    for study_id in STUDY_VERSIONS:
        studies[study_id] = _records(_post(STUDY_QUERY[study_id]), "study")
        files[study_id] = _records(_post(FILE_QUERY[study_id]), "filesPerStudy")
        biospecimens[study_id] = _records(_post(BIOSPECIMEN_QUERY[study_id]), "biospecimenPerStudy")
        _file_manifest_records(files[study_id], study_id)
    cohort = _validate_matched_biospecimens(biospecimens, map_labels["PDC000204"])
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA,
        "source": {
            "endpoint": PDC_GRAPHQL_ENDPOINT,
            "api_version": PDC_GRAPHQL_API_VERSION,
            "study_versions": STUDY_VERSIONS,
            "local_file_locks": [
                {
                    "study_id": lock.study_id,
                    "filename": lock.filename,
                    "file_uuid": lock.file_uuid,
                    "bytes": lock.bytes,
                    "md5": lock.md5,
                    "sha256": lock.sha256,
                }
                for lock in SOURCE_FILES
            ],
            "canonicalization": "UTF-8 JSON, sorted keys, compact separators, LF terminator; network responses sorted by stable identifiers; expiring URLs and HTTP metadata excluded",
        },
        "query_provenance": {
            "study": STUDY_QUERY,
            "files": FILE_QUERY,
            "biospecimens": BIOSPECIMEN_QUERY,
        },
        "cohort_oracles": cohort,
        "sample_map_oracles": map_oracles,
        "responses": {
            "study": studies,
            "files": files,
            "biospecimens": biospecimens,
        },
    }
    # Sort response collections before hashing so replay is stable across API pagination order.
    responses = cast("dict[str, object]", manifest["responses"])
    for collection in responses.values():
        if isinstance(collection, dict):
            for rows in collection.values():
                if isinstance(rows, list):
                    rows.sort(
                        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"))
                    )
    verify_local_files(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_bytes(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = capture(args.source_dir, args.destination)
    cohort = cast("dict[str, object]", manifest["cohort_oracles"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": manifest["schema_version"],
                "matched_non_pool_aliquots": cohort["matched_non_pool_aliquots"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
