# ruff: noqa: C901, E501, PLR0911, PLR0912, PLR0913, PLR0915, PLR2004, T201, TRY003, TRY004
"""Bootstrap caller-side matched GBM factor coordinates.

This tool refits only the selected source factor features under deterministic
case-group resampling.  Protein factors are refit from the unshared protein
matrix; phosphosite factors are refit after the same robust parent-protein
adjustment used by the production adapter.  The receipt contains loading
cosine intervals and replicate support, never sample labels, values, or
resample indices.  It is an uncertainty diagnostic, not a released model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Final, cast

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
    complex_transition_source_catalog,
)
from tools.build_cptac_gbm_adjusted_phosphosite_catalog import (
    fit_parent_regression,
    read_phosphosite_matrix,
)
from tools.build_cptac_gbm_matched_feature_catalog import (
    PHOSPHOSITE_FILENAME,
    PROTEIN_FILENAME,
)
from tools.capture_cptac_gbm_matched_source_manifest import (
    MANIFEST_FILENAME,
    SAMPLE_MAP_FILES,
    _canonical_bytes,
    parse_sample_map,
    verify_local_files,
)
from tools.fit_cptac_gbm_complex_factors import fit_rank_one, read_protein_matrix

MODEL_ID: Final = "cptac-gbm-source-factor-bootstrap/1.0.0"
DEFAULT_BOOTSTRAPS: Final = 64
MAX_BOOTSTRAPS: Final = 256
LOWER_QUANTILE: Final = 0.05
UPPER_QUANTILE: Final = 0.95
MIN_SUCCESSFUL_REPLICATES: Final = 8
MIN_COSINE_SUPPORT: Final = 2


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _factor_map(receipt: dict[str, object], key: str) -> dict[str, dict[str, object]]:
    values = receipt.get(key)
    if not isinstance(values, list):
        raise ValueError(f"factor receipt is missing {key}")
    result: dict[str, dict[str, object]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise ValueError(f"factor receipt contains a non-object {key[:-1]}")
        item = cast("dict[str, object]", value)
        identifier = item.get("complex_id", item.get("pathway_id"))
        if not isinstance(identifier, str) or identifier in result:
            raise ValueError(f"factor receipt contains duplicate or invalid {key[:-1]} IDs")
        result[identifier] = item
    return result


def _case_groups(manifest_path: Path, labels: list[str]) -> tuple[np.ndarray, ...]:
    payload = cast("dict[str, object]", json.loads(manifest_path.read_bytes()))
    responses = cast("dict[str, object]", payload.get("responses"))
    biospecimens = cast("dict[str, object]", responses.get("biospecimens"))
    by_label: dict[str, str] = {}
    for study_id in ("PDC000204", "PDC000205"):
        rows = cast("list[dict[str, object]]", biospecimens.get(study_id))
        for row in rows:
            # The source lock also records one pooled reference channel.  It is
            # deliberately excluded from case-group resampling because it is not
            # represented as a matrix label or an independent biological case.
            if str(row.get("pool", "No")) == "Yes":
                continue
            label = str(row.get("aliquot_submitter_id", ""))
            case_id = str(row.get("case_id", ""))
            if label and case_id:
                previous = by_label.get(label)
                if previous is not None and previous != case_id:
                    raise ValueError(f"matched studies disagree on case group for {label}")
                by_label[label] = case_id
    if set(by_label) != set(labels):
        raise ValueError("manifest case groups do not exactly cover matrix labels")
    groups: dict[str, list[int]] = {}
    for index, label in enumerate(labels):
        groups.setdefault(by_label[label], []).append(index)
    return tuple(np.asarray(groups[key], dtype=np.int64) for key in sorted(groups))


def _cosine(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.ndim != 1 or right.ndim != 1 or left.size < MIN_COSINE_SUPPORT or left.size != right.size:
        return None
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1.0e-12:
        return None
    return float(np.dot(left, right) / denominator)


def _interval(values: list[float]) -> dict[str, object]:
    if len(values) < MIN_SUCCESSFUL_REPLICATES:
        return {"support": len(values), "lower": None, "median": None, "upper": None}
    array = np.asarray(values, dtype=np.float64)
    lower, median, upper = np.quantile(
        array, (LOWER_QUANTILE, 0.5, UPPER_QUANTILE), method="linear"
    )
    return {
        "support": len(values),
        "lower": round(float(lower), 8),
        "median": round(float(median), 8),
        "upper": round(float(upper), 8),
    }


def _site_ids(
    complex_factors: dict[str, dict[str, object]],
    pathway_factors: dict[str, dict[str, object]],
) -> set[str]:
    result: set[str] = set()
    for factor in (*complex_factors.values(), *pathway_factors.values()):
        phosphosite = factor.get("phosphosite", factor.get("phosphosite_factor"))
        if not isinstance(phosphosite, dict):
            continue
        features = phosphosite.get("features", phosphosite.get("phosphosite_features"))
        if not isinstance(features, list):
            continue
        for feature in features:
            if isinstance(feature, dict) and isinstance(feature.get("feature_id"), str):
                result.add(cast("str", feature["feature_id"]))
    return result


def _point_site_features(factor: dict[str, object]) -> tuple[list[str], np.ndarray] | None:
    phosphosite = factor.get("phosphosite")
    features: object
    if isinstance(phosphosite, dict):
        features = phosphosite.get("features", phosphosite.get("phosphosite_features"))
    else:
        # Pathway receipts keep the feature annotations beside the factor
        # object, while complex receipts nest them under ``phosphosite``.
        features = factor.get("phosphosite_features")
    if not isinstance(features, list):
        return None
    identifiers: list[str] = []
    loadings: list[float] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        identifier = feature.get("feature_id")
        loading = feature.get("loading")
        if isinstance(identifier, str) and isinstance(loading, (int, float)):
            identifiers.append(identifier)
            loadings.append(float(loading))
    return identifiers, np.asarray(loadings, dtype=np.float64)


def _point_protein_features(factor: dict[str, object]) -> tuple[list[str], np.ndarray] | None:
    members = factor.get("protein_members")
    protein_factor = factor.get("protein_factor")
    if not isinstance(members, list) or not isinstance(protein_factor, dict):
        return None
    loadings = protein_factor.get("loadings")
    if not isinstance(loadings, list) or len(members) != len(loadings):
        return None
    if not all(isinstance(member, str) and isinstance(loading, (int, float)) for member, loading in zip(members, loadings, strict=True)):
        return None
    return [cast("str", member) for member in members], np.asarray(loadings, dtype=np.float64)


def _factor_bootstrap_cosine(
    factor: dict[str, object],
    *,
    protein_matrix: np.ndarray,
    gene_index: dict[str, int],
    phosphosite_values: dict[str, np.ndarray],
    phosphosite_gene: dict[str, str],
    sample_indices: np.ndarray,
    modality: str,
) -> float | None:
    protein_features = _point_protein_features(factor)
    if modality == "protein":
        if protein_features is None:
            return None
        members, point = protein_features
        if any(member not in gene_index for member in members):
            return None
        indices = [gene_index[member] for member in members]
        try:
            fit = fit_rank_one(protein_matrix[indices][:, sample_indices])
        except ValueError:
            return None
        return _cosine(point, np.asarray(cast("list[float]", fit["loadings"]), dtype=np.float64))
    site_features = _point_site_features(factor)
    if site_features is None:
        return None
    identifiers, point = site_features
    residual_rows: list[np.ndarray] = []
    point_loadings: list[float] = []
    for identifier, point_loading in zip(identifiers, point, strict=True):
        values = phosphosite_values.get(identifier)
        gene = phosphosite_gene.get(identifier)
        if values is None or gene is None or gene not in gene_index:
            continue
        try:
            fit = fit_parent_regression(
                protein_matrix[gene_index[gene]][sample_indices], values[sample_indices]
            )
        except ValueError:
            continue
        residual_rows.append(cast("np.ndarray", fit["residuals"]))
        point_loadings.append(float(point_loading))
    if len(residual_rows) < MIN_COSINE_SUPPORT:
        return None
    try:
        fit = fit_rank_one(np.stack(residual_rows))
    except ValueError:
        return None
    return _cosine(
        np.asarray(point_loadings, dtype=np.float64),
        np.asarray(cast("list[float]", fit["loadings"]), dtype=np.float64),
    )


def bootstrap_factors(
    source_dir: Path,
    manifest_path: Path,
    complex_receipt_path: Path,
    pathway_receipt_path: Path,
    *,
    replicates: int = DEFAULT_BOOTSTRAPS,
) -> dict[str, object]:
    if replicates < MIN_SUCCESSFUL_REPLICATES or replicates > MAX_BOOTSTRAPS:
        raise ValueError(f"bootstrap replicates must be between {MIN_SUCCESSFUL_REPLICATES} and {MAX_BOOTSTRAPS}")
    paths = verify_local_files(source_dir)
    complex_receipt = cast("dict[str, object]", json.loads(complex_receipt_path.read_bytes()))
    pathway_receipt = cast("dict[str, object]", json.loads(pathway_receipt_path.read_bytes()))
    manifest_digest = str(complex_receipt.get("source_manifest_digest", ""))
    if manifest_digest != pathway_receipt.get("source_manifest_digest"):
        raise ValueError("factor receipts do not share a source manifest digest")
    if manifest_digest != _digest_file(manifest_path):
        raise ValueError("factor receipt manifest digest does not match manifest bytes")
    source = complex_transition_source_catalog()
    for receipt in (complex_receipt, pathway_receipt):
        if receipt.get("source_complex_catalog_digest") != source.content_digest:
            raise ValueError("factor receipt complex catalog digest does not match source catalog")
    complex_factors = _factor_map(complex_receipt, "factors")
    pathway_factors = _factor_map(pathway_receipt, "pathways")
    labels, _ = parse_sample_map(paths[SAMPLE_MAP_FILES["PDC000204"]].read_bytes())
    genes, protein_matrix, _ = read_protein_matrix(paths[PROTEIN_FILENAME], labels)
    phosphosite_rows, _ = read_phosphosite_matrix(paths[PHOSPHOSITE_FILENAME], labels)
    phosphosite_values = {
        cast("str", row["feature_id"]): cast("np.ndarray", row["values"])
        for row in phosphosite_rows
        if isinstance(row.get("feature_id"), str)
    }
    phosphosite_gene = {
        cast("str", row["feature_id"]): cast("str", row["gene"])
        for row in phosphosite_rows
        if isinstance(row.get("feature_id"), str) and isinstance(row.get("gene"), str)
    }
    gene_index = {gene: index for index, gene in enumerate(genes)}
    groups = _case_groups(manifest_path, labels)
    binding_by_id = {binding.reactome_id: binding for binding in source.complexes}
    complex_protein_values: dict[str, list[float]] = {identifier: [] for identifier in complex_factors}
    complex_site_values: dict[str, list[float]] = {identifier: [] for identifier in complex_factors}
    pathway_protein_values: dict[str, list[float]] = {identifier: [] for identifier in pathway_factors}
    pathway_site_values: dict[str, list[float]] = {identifier: [] for identifier in pathway_factors}
    seed_material = {
        "model_id": MODEL_ID,
        "source_manifest_digest": manifest_digest,
        "complex_receipt_digest": _digest_file(complex_receipt_path),
        "pathway_receipt_digest": _digest_file(pathway_receipt_path),
        "replicates": replicates,
    }
    base_seed = int(hashlib.sha256(_canonical_bytes(seed_material)).hexdigest()[:16], 16)
    seed_material_digest = "sha256:" + hashlib.sha256(_canonical_bytes(seed_material)).hexdigest()
    for replicate in range(replicates):
        rng = np.random.default_rng(base_seed + replicate)
        chosen = rng.integers(0, len(groups), size=len(groups))
        sample_indices = np.concatenate([groups[int(index)] for index in chosen])
        for identifier, factor in complex_factors.items():
            if identifier not in binding_by_id:
                raise ValueError(f"complex factor references a complex absent from the source catalog: {identifier}")
            protein_score = _factor_bootstrap_cosine(
                factor,
                protein_matrix=protein_matrix,
                gene_index=gene_index,
                phosphosite_values=phosphosite_values,
                phosphosite_gene=phosphosite_gene,
                sample_indices=sample_indices,
                modality="protein",
            )
            site_score = _factor_bootstrap_cosine(
                factor,
                protein_matrix=protein_matrix,
                gene_index=gene_index,
                phosphosite_values=phosphosite_values,
                phosphosite_gene=phosphosite_gene,
                sample_indices=sample_indices,
                modality="phosphosite",
            )
            if protein_score is not None:
                complex_protein_values[identifier].append(protein_score)
            if site_score is not None:
                complex_site_values[identifier].append(site_score)
        for identifier, factor in pathway_factors.items():
            protein_score = _factor_bootstrap_cosine(
                factor,
                protein_matrix=protein_matrix,
                gene_index=gene_index,
                phosphosite_values=phosphosite_values,
                phosphosite_gene=phosphosite_gene,
                sample_indices=sample_indices,
                modality="protein",
            )
            site_score = _factor_bootstrap_cosine(
                factor,
                protein_matrix=protein_matrix,
                gene_index=gene_index,
                phosphosite_values=phosphosite_values,
                phosphosite_gene=phosphosite_gene,
                sample_indices=sample_indices,
                modality="phosphosite",
            )
            if protein_score is not None:
                pathway_protein_values[identifier].append(protein_score)
            if site_score is not None:
                pathway_site_values[identifier].append(site_score)
    complexes = [
        {
            "complex_id": identifier,
            "protein_loading_cosine": _interval(complex_protein_values[identifier]),
            "phosphosite_loading_cosine": _interval(complex_site_values[identifier]),
        }
        for identifier in sorted(complex_factors)
    ]
    pathways = [
        {
            "pathway_id": identifier,
            "protein_loading_cosine": _interval(pathway_protein_values[identifier]),
            "phosphosite_loading_cosine": _interval(pathway_site_values[identifier]),
        }
        for identifier in sorted(pathway_factors)
    ]
    profile = {
        "model_id": MODEL_ID,
        "replicates": replicates,
        "sampling_unit": "exact manifest case group",
        "seed_policy": "sha256(source manifest, factor receipt digests, replicate index)",
        "interval": "deterministic 5th/50th/95th percentile of loading cosine to full-source fit",
        "parent_adjustment": "Theil-Sen-start Huber IRLS with missing-aware paired cells",
        "numpy_version": np.__version__,
        "lower_quantile": LOWER_QUANTILE,
        "upper_quantile": UPPER_QUANTILE,
        "min_successful_replicates": MIN_SUCCESSFUL_REPLICATES,
        "min_cosine_support": MIN_COSINE_SUPPORT,
        "max_replicates": MAX_BOOTSTRAPS,
        "raw_values_emitted": False,
        "resample_indices_emitted": False,
    }
    payload = {
        "schema_version": MODEL_ID,
        "algorithm_profile": profile,
        "algorithm_profile_digest": "sha256:" + hashlib.sha256(_canonical_bytes(profile)).hexdigest(),
        "source_manifest_digest": manifest_digest,
        "source_complex_catalog_digest": source.content_digest,
        "seed_material_digest": seed_material_digest,
        "factor_receipts": {
            "complex": _digest_file(complex_receipt_path),
            "pathway": _digest_file(pathway_receipt_path),
        },
        "source_files": {
            name: {"bytes": paths[name].stat().st_size, "sha256": _digest_file(paths[name])}
            for name in (PROTEIN_FILENAME, PHOSPHOSITE_FILENAME)
        },
        "replicates_requested": replicates,
        "case_group_count": len(groups),
        "complexes": complexes,
        "pathways": pathways,
        "limitations": [
            "Bootstrap intervals are source-cohort parameter sensitivity, not patient-level prediction intervals.",
            "Intervals compare refit loading directions to the full-source fit and do not establish external validity.",
            "Applied edge multipliers remain unchanged; nested held-out evaluation is still required.",
        ],
    }
    # Bind the complete canonical payload to a receipt digest.  The digest is
    # deliberately computed without itself so an auditor can validate a file
    # before trusting any of its interval values.
    payload["receipt_digest"] = "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return payload


def _receipt_digest(payload: dict[str, object]) -> str:
    """Return the canonical digest used by bootstrap receipts."""

    digest_payload = {key: value for key, value in payload.items() if key != "receipt_digest"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(digest_payload)).hexdigest()


def verify_bootstrap_receipt(
    source_dir: Path,
    manifest_path: Path,
    complex_receipt_path: Path,
    pathway_receipt_path: Path,
    receipt_path: Path,
) -> dict[str, object]:
    """Recompute and semantically verify a source-factor bootstrap receipt.

    This is intentionally caller-side and stateless: no source rows or
    resample indices are returned.  Every integrity check is reported so a
    receipt can be distinguished from a self-consistent but forged artifact.
    """

    report: dict[str, object] = {
        "model_id": MODEL_ID,
        "verified": False,
        "checks": {},
        "mismatches": [],
    }
    mismatches: list[str] = []
    report["mismatches"] = mismatches
    try:
        decoded: object = json.loads(receipt_path.read_bytes())
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        report["error"] = f"receipt could not be decoded: {type(exc).__name__}"
        mismatches.append("receipt_json")
        return report
    if not isinstance(decoded, dict):
        report["error"] = "receipt root must be an object"
        mismatches.append("receipt_shape")
        return report
    provided = cast("dict[str, object]", decoded)
    raw_replicates = provided.get("replicates_requested")
    if isinstance(raw_replicates, bool) or not isinstance(raw_replicates, int):
        report["error"] = "receipt replicates_requested must be an integer"
        mismatches.append("replicates_requested")
        return report
    if raw_replicates < MIN_SUCCESSFUL_REPLICATES or raw_replicates > MAX_BOOTSTRAPS:
        report["error"] = "receipt replicates_requested is outside the supported bounds"
        mismatches.append("replicates_requested")
        return report

    try:
        expected = bootstrap_factors(
            source_dir,
            manifest_path,
            complex_receipt_path,
            pathway_receipt_path,
            replicates=raw_replicates,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["error"] = f"recompute failed: {type(exc).__name__}"
        mismatches.append("recompute")
        return report

    provided_digest = provided.get("receipt_digest")
    expected_digest = cast("str", expected["receipt_digest"])
    provided_profile = provided.get("algorithm_profile")
    provided_profile_digest = provided.get("algorithm_profile_digest")
    profile_digest_self_check = (
        isinstance(provided_profile, dict)
        and isinstance(provided_profile_digest, str)
        and provided_profile_digest
        == "sha256:" + hashlib.sha256(_canonical_bytes(provided_profile)).hexdigest()
    )
    checks: dict[str, bool] = {
        "schema_version": provided.get("schema_version") == expected.get("schema_version"),
        "source_manifest_digest": provided.get("source_manifest_digest")
        == expected.get("source_manifest_digest"),
        "source_complex_catalog_digest": provided.get("source_complex_catalog_digest")
        == expected.get("source_complex_catalog_digest"),
        "factor_receipts": provided.get("factor_receipts") == expected.get("factor_receipts"),
        "source_files": provided.get("source_files") == expected.get("source_files"),
        "algorithm_profile": provided.get("algorithm_profile") == expected.get("algorithm_profile"),
        "algorithm_profile_digest": provided.get("algorithm_profile_digest")
        == expected.get("algorithm_profile_digest"),
        "algorithm_profile_digest_self": profile_digest_self_check,
        "seed_material_digest": provided.get("seed_material_digest")
        == expected.get("seed_material_digest"),
        "receipt_digest": isinstance(provided_digest, str)
        and provided_digest == _receipt_digest(provided),
        "recomputed_receipt_digest": provided_digest == expected_digest,
        "semantic_equal": _canonical_bytes(provided) == _canonical_bytes(expected),
    }
    for name, passed in checks.items():
        if not passed:
            mismatches.append(name)
    report["checks"] = checks
    report["provided_receipt_digest"] = provided_digest
    report["recomputed_receipt_digest"] = expected_digest
    report["request_digest"] = expected.get("seed_material_digest")
    report["profile_digest"] = expected.get("algorithm_profile_digest")
    report["verified"] = not mismatches
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--complex-receipt", type=Path, required=True)
    parser.add_argument("--pathway-receipt", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=DEFAULT_BOOTSTRAPS)
    parser.add_argument(
        "--verify-receipt",
        type=Path,
        default=None,
        help="Recompute and verify an existing receipt instead of writing a new one.",
    )
    parser.add_argument("destination", type=Path, nargs="?")
    args = parser.parse_args()
    manifest = args.manifest or args.source_dir / MANIFEST_FILENAME
    if args.verify_receipt is not None:
        report = verify_bootstrap_receipt(
            args.source_dir,
            manifest,
            args.complex_receipt,
            args.pathway_receipt,
            args.verify_receipt,
        )
        print(json.dumps(report, sort_keys=True))
        return 0 if report["verified"] is True else 1
    if args.destination is None:
        parser.error("destination is required unless --verify-receipt is supplied")
    payload = bootstrap_factors(
        args.source_dir,
        manifest,
        args.complex_receipt,
        args.pathway_receipt,
        replicates=args.replicates,
    )
    args.destination.write_bytes(_canonical_bytes(payload))
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "replicates": payload["replicates_requested"],
                "complexes": len(cast("list[object]", payload["complexes"])),
                "pathways": len(cast("list[object]", payload["pathways"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
