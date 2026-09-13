# ruff: noqa: S310, T201, TRY003, TRY004
"""Capture a canonical, version-specific PDC000514 source metadata response.

The output intentionally stays beside the raw PDC inputs and is never packaged.  It
contains source pseudonyms, so the fitted coefficient artifact binds only its exact
byte digest and high-level inventories.
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

from tools.import_kncc_longitudinal_gbm import (
    PDC_GRAPHQL_API_VERSION,
    PDC_GRAPHQL_ENDPOINT,
    PDC_SOURCE_MANIFEST_SCHEMA,
    PDC_STUDY_CATALOG_QUERY,
    PDC_STUDY_ID,
    PDC_STUDY_VERSION_UUID,
    PDC_VERSIONED_BIOSPECIMEN_QUERY,
    PDC_VERSIONED_FILES_QUERY,
    _canonical_bytes,
)

_USER_AGENT: Final = "GLIO-PROTEOGEN-PDC-source-lock/1.0"


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
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"PDC GraphQL response {key!r} is not a record array")
    return cast("list[dict[str, object]]", value)


def capture(destination: Path) -> dict[str, object]:
    """Fetch stable fields and return their deterministically sorted canonical snapshot."""

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
                "data arrays for the exact stable-field queries are sorted by documented IDs; "
                "HTTP metadata and expiring signed URLs are excluded"
            ),
        },
        "query_provenance": {
            "study_catalog": PDC_STUDY_CATALOG_QUERY,
            "versioned_biospecimens": PDC_VERSIONED_BIOSPECIMEN_QUERY,
            "versioned_files": PDC_VERSIONED_FILES_QUERY,
        },
        "responses": {
            "study_catalog": catalog,
            "versioned_biospecimens": biospecimens,
            "versioned_files": files,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_bytes(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = capture(args.destination)
    responses = cast("dict[str, object]", manifest["responses"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "biospecimens": len(cast("list[object]", responses["versioned_biospecimens"])),
                "files": len(cast("list[object]", responses["versioned_files"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
