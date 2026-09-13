# ruff: noqa: C901, E501, PLR0912, PLR0913, PLR2004, T201, TRY003
"""Build a private, de-identified CPTAC GBM matched feature catalog.

This is the first numerical adapter for the source-admitted PDC000204/PDC000205
bundle.  It compares qualified primary-tumor and solid-tissue-normal aliquots
using robust group locations, retains blanks as missing, keeps composite
phosphosite rows atomic, and reports model-derived uncertainty.  It never writes
patient identifiers or matrix cells to the output; the catalog is intended for
caller-side fitting and remains outside the package.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Final, cast

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.capture_cptac_gbm_matched_source_manifest import (
    MANIFEST_FILENAME,
    SAMPLE_MAP_FILES,
    _canonical_bytes,
    parse_sample_map,
    verify_local_files,
)

MODEL_ID: Final = "cptac-gbm-matched-feature-catalog/1.0.0"
MAX_STANDARDIZED_EFFECT: Final = 20.0
MIN_GROUP_SUPPORT: Final = 3
ROBUST_DELTA: Final = 1.345
ROBUST_ITERATIONS: Final = 32
ROBUST_SCALE_FLOOR: Final = 0.05
PROTEIN_FILENAME: Final = "CPTAC3_Glioblastoma_Multiforme_Proteome.tmt11.tsv"
PHOSPHOSITE_FILENAME: Final = "CPTAC3_Glioblastoma_Multiforme_Phosphoproteome.phosphosite.tmt11.tsv"
PROTEIN_AGGREGATE_ROWS: Final = frozenset({"Mean", "Median", "StdDev"})


def _finite_float(token: str) -> float:
    if not token:
        return math.nan
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("matrix contains a non-finite numeric value")
    return value


def _huber_location(values: np.ndarray) -> tuple[float, float, int]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return math.nan, math.nan, 0
    center = float(np.median(finite))
    mad = float(np.median(np.abs(finite - center)) * 1.4826)
    scale = max(mad, ROBUST_SCALE_FLOOR)
    for _ in range(ROBUST_ITERATIONS):
        residual = (finite - center) / scale
        weights = np.minimum(1.0, ROBUST_DELTA / np.maximum(np.abs(residual), 1.0e-15))
        updated = float(np.sum(weights * finite) / np.sum(weights))
        if abs(updated - center) <= 1.0e-10:
            center = updated
            break
        center = updated
    residual = finite - center
    robust_scale = max(float(np.median(np.abs(residual)) * 1.4826), ROBUST_SCALE_FLOOR)
    return center, robust_scale, int(finite.size)


def _contrast(
    tumor: np.ndarray,
    normal: np.ndarray,
    *,
    row_id: str,
    gene: str | None,
    modality: str,
    source_measure: str,
) -> dict[str, object]:
    tumor_center, tumor_scale, tumor_n = _huber_location(tumor)
    normal_center, normal_scale, normal_n = _huber_location(normal)
    total = tumor_n + normal_n
    if total == 0:
        return {
            "feature_id": row_id,
            "gene": gene,
            "modality": modality,
            "source_measure": source_measure,
            "state": "missing",
            "abstention_reason": "no finite tumor or normal observations",
            "tumor_support": 0,
            "normal_support": 0,
            "support_fraction": 0.0,
            "effect": None,
            "standard_error": None,
            "standardized_effect": None,
        }
    if tumor_n < MIN_GROUP_SUPPORT or normal_n < MIN_GROUP_SUPPORT:
        return {
            "feature_id": row_id,
            "gene": gene,
            "modality": modality,
            "source_measure": source_measure,
            "state": "unsupported",
            "abstention_reason": "fewer than three finite observations in one group",
            "tumor_support": tumor_n,
            "normal_support": normal_n,
            "support_fraction": round(total / (tumor.size + normal.size), 8),
            "effect": None,
            "standard_error": None,
            "standardized_effect": None,
        }
    effect = float(tumor_center - normal_center)
    standard_error = max(
        ROBUST_SCALE_FLOOR,
        math.sqrt((tumor_scale * tumor_scale / tumor_n) + (normal_scale * normal_scale / normal_n)),
    )
    standardized = effect / standard_error
    if not math.isfinite(standardized) or abs(standardized) > MAX_STANDARDIZED_EFFECT:
        return {
            "feature_id": row_id,
            "gene": gene,
            "modality": modality,
            "source_measure": source_measure,
            "state": "unsupported",
            "abstention_reason": "standardized effect is outside the ECGI input domain",
            "tumor_support": tumor_n,
            "normal_support": normal_n,
            "support_fraction": round(total / (tumor.size + normal.size), 8),
            "effect": round(effect, 8),
            "standard_error": round(standard_error, 8),
            "standardized_effect": None,
        }
    return {
        "feature_id": row_id,
        "gene": gene,
        "modality": modality,
        "source_measure": source_measure,
        "state": "observed",
        "abstention_reason": None,
        "tumor_support": tumor_n,
        "normal_support": normal_n,
        "support_fraction": round(total / (tumor.size + normal.size), 8),
        "effect": round(effect, 8),
        "standard_error": round(standard_error, 8),
        "standardized_effect": round(standardized, 8),
    }


def _metadata_from_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    payload = cast("dict[str, object]", json.loads(manifest_path.read_bytes()))
    responses = cast("dict[str, object]", payload.get("responses"))
    biospecimens = cast("dict[str, object]", responses.get("biospecimens"))
    by_label: dict[str, dict[str, str]] = {}
    for study_id in ("PDC000204", "PDC000205"):
        rows = cast("list[dict[str, object]]", biospecimens.get(study_id))
        for row in rows:
            label = str(row.get("aliquot_submitter_id", ""))
            if label:
                by_label.setdefault(label, {})[f"{study_id}:sample_type"] = str(
                    row.get("sample_type", "")
                )
                by_label[label][f"{study_id}:case_status"] = str(row.get("case_status", ""))
    if not by_label or any(
        f"{study_id}:sample_type" not in fields or f"{study_id}:case_status" not in fields
        for fields in by_label.values()
        for study_id in ("PDC000204", "PDC000205")
    ):
        raise ValueError("matched source manifest is missing official sample metadata")
    return by_label


def _group_indices(
    labels: list[str], metadata: dict[str, dict[str, str]]
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    tumor: list[int] = []
    normal: list[int] = []
    disqualified = 0
    for index, label in enumerate(labels):
        fields = metadata.get(label)
        if fields is None:
            raise ValueError(f"matrix label is absent from official biospecimen metadata: {label}")
        if fields["PDC000204:sample_type"] != fields["PDC000205:sample_type"]:
            raise ValueError(f"sample type disagreement for matched aliquot: {label}")
        if fields["PDC000204:case_status"] != fields["PDC000205:case_status"]:
            raise ValueError(f"case status disagreement for matched aliquot: {label}")
        if fields["PDC000204:case_status"] != "Qualified":
            disqualified += 1
            continue
        sample_type = fields["PDC000204:sample_type"]
        if sample_type == "Primary Tumor":
            tumor.append(index)
        elif sample_type == "Solid Tissue Normal":
            normal.append(index)
        else:
            raise ValueError(f"unsupported sample type in matched cohort: {sample_type}")
    if len(tumor) != 99 or len(normal) != 10 or disqualified != 1:
        raise ValueError(
            f"matched cohort oracle changed: tumors={len(tumor)}, normals={len(normal)}, disqualified={disqualified}"
        )
    return (
        np.asarray(tumor, dtype=np.int64),
        np.asarray(normal, dtype=np.int64),
        {
            "qualified_primary_tumors": len(tumor),
            "qualified_solid_tissue_normals": len(normal),
            "excluded_disqualified_aliquots": disqualified,
        },
    )


def _matrix_columns(header: list[str], labels: list[str], *, measure: str) -> list[int]:
    columns: list[int] = []
    seen: list[str] = []
    for index, cell in enumerate(header[1:], start=1):
        suffix = f" {measure}"
        if not cell.endswith(suffix) or (
            measure == "Log Ratio" and cell.endswith(" Unshared Log Ratio")
        ):
            continue
        seen.append(cell[: -len(suffix)])
        columns.append(index)
    if seen != labels or len(set(seen)) != len(seen):
        raise ValueError(
            f"matrix {measure!r} columns do not exactly match the official sample-map order"
        )
    return columns


def _read_matrix(
    path: Path,
    *,
    labels: list[str],
    tumor_indices: np.ndarray,
    normal_indices: np.ndarray,
    modality: str,
    measure: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    records: list[dict[str, object]] = []
    seen_feature_ids: set[str] = set()
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        if modality == "proteomics":
            if not header or header[0] != "Gene":
                raise ValueError("unexpected CPTAC protein matrix header")
            columns = _matrix_columns(header, labels, measure=measure)
            metadata_width = 6
        else:
            if not header or header[0] != "Phosphosite":
                raise ValueError("unexpected CPTAC phosphosite matrix header")
            columns = _matrix_columns(header, labels, measure="Log Ratio")
            metadata_width = 3
        expected_width = len(header)
        if len(columns) != len(labels) or len(header) < len(columns) + metadata_width + 1:
            raise ValueError("matrix does not contain the expected matched feature columns")
        for row_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(f"ragged CPTAC matrix row {row_number}")
            row_count += 1
            row_id = row[0]
            if modality == "proteomics":
                if row_id in PROTEIN_AGGREGATE_ROWS:
                    continue
                gene: str | None = row[0]
            else:
                gene = row[-2] or None
            if not row_id:
                raise ValueError(f"matrix row {row_number} has an empty feature identifier")
            if row_id in seen_feature_ids:
                raise ValueError(f"duplicate matrix feature identifier: {row_id}")
            seen_feature_ids.add(row_id)
            values = np.fromiter((_finite_float(row[index]) for index in columns), dtype=np.float64)
            record = _contrast(
                values[tumor_indices],
                values[normal_indices],
                row_id=row_id,
                gene=gene,
                modality=modality,
                source_measure=measure,
            )
            organism = row[-3] if modality == "proteomics" else row[-1]
            if organism and organism != "Homo sapiens":
                record.update(
                    state="unsupported",
                    abstention_reason="source feature is not annotated as Homo sapiens",
                    effect=None,
                    standard_error=None,
                    standardized_effect=None,
                )
            elif modality == "phosphoproteomics" and gene is None:
                record.update(
                    state="unsupported",
                    abstention_reason="phosphosite row has no source gene annotation",
                    effect=None,
                    standard_error=None,
                    standardized_effect=None,
                )
            records.append(record)
    if not records:
        raise ValueError("matrix has no feature rows")
    return records, {
        "rows": row_count,
        "observed": sum(item["state"] == "observed" for item in records),
        "missing": sum(item["state"] == "missing" for item in records),
        "unsupported": sum(item["state"] == "unsupported" for item in records),
    }


def build_catalog(source_dir: Path, manifest_path: Path) -> dict[str, object]:
    """Read a locked local bundle and return a de-identified feature catalog."""
    paths = verify_local_files(source_dir)
    manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    metadata = _metadata_from_manifest(manifest_path)
    protein_labels, protein_map = parse_sample_map(
        paths[SAMPLE_MAP_FILES["PDC000204"]].read_bytes()
    )
    phospho_labels, phospho_map = parse_sample_map(
        paths[SAMPLE_MAP_FILES["PDC000205"]].read_bytes()
    )
    if protein_labels != phospho_labels:
        raise ValueError("protein and phosphosite sample maps do not share exact label order")
    tumor, normal, cohort = _group_indices(protein_labels, metadata)
    protein, protein_oracles = _read_matrix(
        paths[PROTEIN_FILENAME],
        labels=protein_labels,
        tumor_indices=tumor,
        normal_indices=normal,
        modality="proteomics",
        measure="Unshared Log Ratio",
    )
    phosphosite, phosphosite_oracles = _read_matrix(
        paths[PHOSPHOSITE_FILENAME],
        labels=phospho_labels,
        tumor_indices=tumor,
        normal_indices=normal,
        modality="phosphoproteomics",
        measure="Log Ratio",
    )
    payload: dict[str, object] = {
        "schema_version": MODEL_ID,
        "source_manifest_digest": manifest_digest,
        "cohort": cohort,
        "sample_maps": {"protein": protein_map, "phosphoproteome": phospho_map},
        "measurement_semantics": {
            "protein_measure": "Unshared Log Ratio",
            "phosphosite_measure": "Log Ratio",
            "contrast": "robust qualified primary-tumor location minus qualified solid-tissue-normal location",
            "uncertainty": "model-derived robust MAD group scales propagated as a standard error; not analytical replicate error",
            "missingness": "blank source cells remain missing; no imputation or censoring bound is inferred",
            "disqualified_policy": "excluded from the contrast but retained in the cohort oracle",
            "composite_phosphosite_policy": "source phosphosite rows remain atomic; peptide/site strings are not split",
        },
        "feature_oracles": {"protein": protein_oracles, "phosphosite": phosphosite_oracles},
        "features": {"protein": protein, "phosphosite": phosphosite},
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = args.manifest or args.source_dir / MANIFEST_FILENAME
    payload = build_catalog(args.source_dir, manifest)
    args.destination.write_bytes(_canonical_bytes(payload))
    features = cast("dict[str, list[object]]", payload["features"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "protein_features": len(features["protein"]),
                "phosphosite_features": len(features["phosphosite"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
