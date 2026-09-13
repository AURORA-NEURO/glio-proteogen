# ruff: noqa: S310, T201, TRY003, TRY004
"""Capture an exact canonical PDC000515 v1 metadata and local-file source lock.

The manifest is intentionally written beside the external raw inputs. It contains
source pseudonyms and UUIDs and must never be packaged. Expiring signed download
URLs and HTTP response metadata are deliberately excluded.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Final, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_kncc_longitudinal_phospho import (
    PDC_EXPERIMENTAL_DESIGN_QUERY,
    PDC_GRAPHQL_API_VERSION,
    PDC_GRAPHQL_ENDPOINT,
    PDC_SOURCE_MANIFEST_FILENAME,
    PDC_SOURCE_MANIFEST_SCHEMA,
    PDC_STUDY_CATALOG_QUERY,
    PDC_STUDY_ID,
    PDC_STUDY_VERSION_UUID,
    PDC_VERSIONED_BIOSPECIMEN_QUERY,
    PDC_VERSIONED_FILES_QUERY,
    PDC_VERSIONED_PROTOCOL_QUERY,
    PDC_VERSIONED_STUDY_QUERY,
    SOURCE_FILES,
    _canonical_bytes,
    verify_source_files,
)

_USER_AGENT: Final = "GLIO-PROTEOGEN-PDC000515-source-lock/1.0"


def _validate_private_destination(source_dir: Path, destination: Path) -> None:
    try:
        resolved_source = source_dir.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("PDC000515 source directory does not exist") from error
    expected = resolved_source / PDC_SOURCE_MANIFEST_FILENAME
    if destination.resolve(strict=False) != expected:
        raise ValueError(
            "the private PDC000515 source manifest must be written beside its verified "
            f"inputs as {PDC_SOURCE_MANIFEST_FILENAME}"
        )


def _post(query: str) -> dict[str, object]:
    body = json.dumps({"query": query}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        PDC_GRAPHQL_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
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


def _sort_nested_design(rows: list[dict[str, object]]) -> None:
    channels = (
        "tmt_126",
        "tmt_127n",
        "tmt_127c",
        "tmt_128n",
        "tmt_128c",
        "tmt_129n",
        "tmt_129c",
        "tmt_130n",
        "tmt_130c",
        "tmt_131",
        "tmt_131c",
    )
    for row in rows:
        for channel in channels:
            value = row.get(channel)
            if value is None:
                row[channel] = []
                continue
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                raise ValueError("PDC experimental-design channel is not a record array")
            row[channel] = sorted(
                cast("list[dict[str, object]]", value),
                key=lambda item: (
                    str(item.get("aliquot_run_metadata_id", "")),
                    str(item.get("aliquot_id", "")),
                ),
            )


def capture(source_dir: Path, destination: Path) -> dict[str, object]:
    """Fetch stable official fields and bind them to six locally verified files."""

    _validate_private_destination(source_dir, destination)
    verify_source_files(source_dir)

    catalog = _records(_post(PDC_STUDY_CATALOG_QUERY), "studyCatalog")
    for entry in catalog:
        versions = entry.get("versions")
        if not isinstance(versions, list) or not all(isinstance(item, dict) for item in versions):
            raise ValueError("PDC study catalog omitted version records")
        entry["versions"] = sorted(
            cast("list[dict[str, object]]", versions),
            key=lambda item: str(item.get("study_id", "")),
        )
    catalog.sort(key=lambda item: str(item.get("pdc_study_id", "")))

    studies = _records(_post(PDC_VERSIONED_STUDY_QUERY), "study")
    for study in studies:
        counts = study.get("filesCount")
        if not isinstance(counts, list) or not all(isinstance(item, dict) for item in counts):
            raise ValueError("PDC study response omitted its file counts")
        study["filesCount"] = sorted(
            cast("list[dict[str, object]]", counts),
            key=lambda item: (str(item.get("data_category", "")), str(item.get("file_type", ""))),
        )
    studies.sort(key=lambda item: str(item.get("study_id", "")))

    biospecimens = _records(_post(PDC_VERSIONED_BIOSPECIMEN_QUERY), "biospecimenPerStudy")
    biospecimens.sort(
        key=lambda item: (
            str(item.get("case_submitter_id", "")),
            str(item.get("sample_submitter_id", "")),
            str(item.get("aliquot_submitter_id", "")),
            str(item.get("aliquot_id", "")),
        )
    )

    files = _records(_post(PDC_VERSIONED_FILES_QUERY), "filesPerStudy")
    files.sort(key=lambda item: (str(item.get("file_id", "")), str(item.get("file_name", ""))))

    protocols = _records(_post(PDC_VERSIONED_PROTOCOL_QUERY), "protocolPerStudy")
    protocols.sort(key=lambda item: str(item.get("protocol_id", "")))

    design = _records(_post(PDC_EXPERIMENTAL_DESIGN_QUERY), "studyExperimentalDesign")
    _sort_nested_design(design)
    design.sort(
        key=lambda item: (
            str(item.get("study_run_metadata_id", "")),
            str(item.get("plex_dataset_name", "")),
        )
    )

    manifest: dict[str, object] = {
        "schema_version": PDC_SOURCE_MANIFEST_SCHEMA,
        "source": {
            "endpoint": PDC_GRAPHQL_ENDPOINT,
            "api_version": PDC_GRAPHQL_API_VERSION,
            "documentation": "https://pdc.cancer.gov/pdc-docs/api-documentation",
            "pdc_study_id": PDC_STUDY_ID,
            "pdc_study_version_uuid": PDC_STUDY_VERSION_UUID,
            "canonicalization": (
                "UTF-8 JSON, sorted object keys, compact separators, LF terminator; complete "
                "stable-field response collections are deterministically sorted; HTTP metadata "
                "and expiring signed URLs are excluded"
            ),
            "local_file_locks": [
                {
                    "filename": lock.filename,
                    "file_uuid": lock.uuid,
                    "bytes": lock.bytes,
                    "official_md5": lock.md5,
                    "observed_sha256": lock.sha256,
                }
                for lock in SOURCE_FILES
            ],
        },
        "query_provenance": {
            "study_catalog": PDC_STUDY_CATALOG_QUERY,
            "versioned_study": PDC_VERSIONED_STUDY_QUERY,
            "versioned_biospecimens": PDC_VERSIONED_BIOSPECIMEN_QUERY,
            "versioned_files": PDC_VERSIONED_FILES_QUERY,
            "versioned_protocol": PDC_VERSIONED_PROTOCOL_QUERY,
            "experimental_design": PDC_EXPERIMENTAL_DESIGN_QUERY,
        },
        "responses": {
            "study_catalog": catalog,
            "versioned_study": studies,
            "versioned_biospecimens": biospecimens,
            "versioned_files": files,
            "versioned_protocol": protocols,
            "experimental_design": design,
        },
    }
    # The network round-trips above are deliberately outside the source reads. Re-hash every
    # local file immediately before emitting the receipt so a replacement during that window
    # cannot inherit the canonical lock claims.
    verify_source_files(source_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_bytes(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = capture(args.source_dir, args.destination)
    responses = cast("dict[str, object]", manifest["responses"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "biospecimens": len(cast("list[object]", responses["versioned_biospecimens"])),
                "files": len(cast("list[object]", responses["versioned_files"])),
                "protocols": len(cast("list[object]", responses["versioned_protocol"])),
                "design_rows": len(cast("list[object]", responses["experimental_design"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
