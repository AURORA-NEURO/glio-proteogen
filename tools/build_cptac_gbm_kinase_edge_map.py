# ruff: noqa: C901, E501, PLR2004, T201, TRY003, TRY004
"""Build a caller-side SPHINKS-to-CPTAC GBM kinase-site crosswalk.

The matched CPTAC phosphoproteome uses RefSeq accession plus residue tokens
(``NP_...:s473``), while the licensed SPHINKS catalog uses HGNC gene symbols
(``AKT1-S473s``).  This tool joins them only on an exact gene and ordered
residue-token key.  Repeated SPHINKS rows are collapsed by the same
mean-probability policy used by the source kinase engine.  The output contains
topology and source provenance, never matrix values or sample identifiers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Final, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.gbm_master_kinases.catalog import SignatureEdge, master_kinase_catalog
from tools.capture_cptac_gbm_matched_source_manifest import _canonical_bytes

MODEL_ID: Final = "cptac-gbm-kinase-edge-map/1.0.0"
MIN_EDGE_WEIGHT: Final = 0.01
SPEARMAN_FLOOR: Final = 0.05
SITE_TOKEN_PATTERN: Final = re.compile(r"([sty])(\d+)", re.IGNORECASE)


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _site_key(gene: str, label: str) -> tuple[str, str] | None:
    """Normalize a source or matrix site to an exact gene/token tuple."""

    if not gene or not label:
        return None
    tokens = "".join(
        residue.lower() + position for residue, position in SITE_TOKEN_PATTERN.findall(label)
    )
    return (gene, tokens) if tokens else None


def _source_site_key(source_site_label: str) -> tuple[str, str] | None:
    if "-" not in source_site_label:
        return None
    gene, site = source_site_label.rsplit("-", 1)
    return _site_key(gene, site)


def _factor_feature_ids(factor_receipt: dict[str, object]) -> set[str]:
    factors = factor_receipt.get("factors")
    if not isinstance(factors, list):
        raise ValueError("factor receipt is missing factors")
    feature_ids: set[str] = set()
    for value in factors:
        if not isinstance(value, dict):
            raise ValueError("factor receipt contains a non-object factor")
        phosphosite = value.get("phosphosite")
        if not isinstance(phosphosite, dict):
            continue
        features = phosphosite.get("features")
        if not isinstance(features, list):
            raise ValueError("factor receipt contains malformed phosphosite features")
        for feature in features:
            if not isinstance(feature, dict):
                raise ValueError("factor receipt contains a non-object phosphosite feature")
            feature_id = feature.get("feature_id")
            if not isinstance(feature_id, str) or not feature_id:
                raise ValueError("factor receipt contains an invalid phosphosite feature ID")
            feature_ids.add(feature_id)
    if not feature_ids:
        raise ValueError("factor receipt contains no phosphosite features")
    return feature_ids


def _matched_sites(
    phosphosite_path: Path, selected_features: set[str]
) -> tuple[dict[tuple[str, str], str], set[tuple[str, str]]]:
    by_key: dict[tuple[str, str], str] = {}
    ambiguous: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    with phosphosite_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader, None)
        if header is None or len(header) < 3 or header[0] != "Phosphosite":
            raise ValueError("unexpected CPTAC phosphosite matrix header")
        expected_width = len(header)
        for row_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(f"ragged CPTAC phosphosite matrix row {row_number}")
            feature_id = row[0]
            if not feature_id or feature_id in seen_ids:
                raise ValueError(f"duplicate or empty CPTAC phosphosite ID at row {row_number}")
            seen_ids.add(feature_id)
            if feature_id not in selected_features:
                continue
            gene = row[-2]
            organism = row[-1]
            if organism and organism != "Homo sapiens":
                continue
            if ":" not in feature_id:
                continue
            key = _site_key(gene, feature_id.split(":", 1)[1])
            if key is None:
                continue
            previous = by_key.get(key)
            if previous is not None and previous != feature_id:
                ambiguous.add(key)
                by_key.pop(key, None)
            elif key not in ambiguous:
                by_key[key] = feature_id
    return by_key, ambiguous


def _edge_weight(mean_probability: float, mean_rho: float) -> float:
    return round(
        max(MIN_EDGE_WEIGHT, mean_probability * max(mean_rho, SPEARMAN_FLOOR)),
        8,
    )


def _receipt_digest(payload: dict[str, object]) -> str:
    """Return the canonical digest used by kinase edge-map receipts."""

    digest_payload = {key: value for key, value in payload.items() if key != "receipt_digest"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(digest_payload)).hexdigest()


def build_edge_map(
    phosphosite_path: Path,
    factor_receipt_path: Path,
    *,
    source_manifest_digest: str,
) -> dict[str, object]:
    decoded: object = json.loads(factor_receipt_path.read_bytes())
    if not isinstance(decoded, dict):
        raise ValueError("factor receipt is not a JSON object")
    factor_receipt = cast("dict[str, object]", decoded)
    factor_manifest_digest = factor_receipt.get("source_manifest_digest")
    if (
        not isinstance(factor_manifest_digest, str)
        or factor_manifest_digest != source_manifest_digest
    ):
        raise ValueError(
            "factor receipt manifest digest does not match the requested source manifest"
        )
    selected_features = _factor_feature_ids(factor_receipt)
    matched, ambiguous = _matched_sites(phosphosite_path, selected_features)
    catalog = master_kinase_catalog()
    grouped: dict[tuple[str, str], list[SignatureEdge]] = {}
    for edge in catalog.edges:
        key = _source_site_key(edge.source_site_label)
        if key is None or key in ambiguous:
            continue
        feature_id = matched.get(key)
        if feature_id is None:
            continue
        grouped.setdefault((edge.hgnc_symbol, feature_id), []).append(edge)

    records: list[dict[str, object]] = []
    for (kinase_id, feature_id), values in sorted(grouped.items()):
        probabilities = [value.svm_probability for value in values]
        correlations = [value.rho_spearman for value in values]
        source_ids = sorted(value.source_row_id for value in values)
        source_sites = sorted(value.source_site_label for value in values)
        known_count = sum(value.known_phosphosite_plus_substrate for value in values)
        mean_probability = math.fsum(probabilities) / len(probabilities)
        mean_rho = math.fsum(correlations) / len(correlations)
        records.append(
            {
                "kinase_id": kinase_id,
                "feature_id": feature_id,
                "source_site_labels": source_sites,
                "source_edge_ids": source_ids,
                "source_edge_count": len(values),
                "known_substrate_fraction": round(known_count / len(values), 8),
                "mean_svm_probability": round(mean_probability, 8),
                "mean_spearman_rho": round(mean_rho, 8),
                "edge_weight": _edge_weight(mean_probability, mean_rho),
                "sign": 1,
            }
        )

    profile = {
        "model_id": MODEL_ID,
        "join_key": "exact HGNC gene plus ordered S/T/Y residue tokens",
        "duplicate_policy": "mean source SVM probability and Spearman rho per kinase-site",
        "edge_weight_policy": "max(0.01, mean_svm_probability * max(mean_spearman_rho, 0.05))",
        "spearman_floor": SPEARMAN_FLOOR,
        "minimum_edge_weight": MIN_EDGE_WEIGHT,
        "source_kinase_profile": "sphinks-gbm-master-kinase-concordance/1.0.0",
        "raw_values_emitted": False,
    }
    payload: dict[str, object] = {
        "schema_version": MODEL_ID,
        "algorithm_profile": profile,
        "algorithm_profile_digest": "sha256:"
        + hashlib.sha256(_canonical_bytes(profile)).hexdigest(),
        "source_manifest_digest": source_manifest_digest,
        "factor_receipt_digest": _digest_file(factor_receipt_path),
        "phosphosite_source": {
            "bytes": phosphosite_path.stat().st_size,
            "sha256": _digest_file(phosphosite_path),
        },
        "source_kinase_catalog": {
            "content_digest": catalog.content_digest,
            "signature_edge_digest": catalog.signature_edge_digest,
            "alias_digest": catalog.alias_digest,
            "license": catalog.source_license,
            "license_url": catalog.source_license_url,
        },
        "selected_feature_count": len(selected_features),
        "mapped_feature_count": len({str(item["feature_id"]) for item in records}),
        "ambiguous_site_key_count": len(ambiguous),
        "kinase_count": len({str(item["kinase_id"]) for item in records}),
        "edge_count": len(records),
        "edges": records,
        "limitations": [
            "Mappings are exact source-site concordance annotations, not biochemical proof of kinase causality.",
            "Edge weights are fixed source reliability products and require nested ECGI evaluation before any multiplier tuning.",
            "The receipt contains topology and source digests only; sample values, labels, and matrix cells are never emitted.",
        ],
    }
    payload["receipt_digest"] = _receipt_digest(payload)
    return payload


def verify_edge_map_receipt(
    phosphosite_path: Path,
    factor_receipt_path: Path,
    *,
    source_manifest_digest: str,
    receipt_path: Path,
) -> dict[str, object]:
    """Recompute and semantically verify a source kinase edge-map receipt.

    Verification is caller-side and stateless.  The report contains only
    integrity booleans and digests; it never echoes matrix cells or sample
    values from the CPTAC source.
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
    try:
        expected = build_edge_map(
            phosphosite_path,
            factor_receipt_path,
            source_manifest_digest=source_manifest_digest,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["error"] = f"recompute failed: {type(exc).__name__}"
        mismatches.append("recompute")
        return report

    provided_profile = provided.get("algorithm_profile")
    provided_profile_digest = provided.get("algorithm_profile_digest")
    profile_digest_self_check = (
        isinstance(provided_profile, dict)
        and isinstance(provided_profile_digest, str)
        and provided_profile_digest
        == "sha256:" + hashlib.sha256(_canonical_bytes(provided_profile)).hexdigest()
    )
    provided_digest = provided.get("receipt_digest")
    expected_digest = cast("str", expected["receipt_digest"])
    checks: dict[str, bool] = {
        "schema_version": provided.get("schema_version") == expected.get("schema_version"),
        "algorithm_profile": provided.get("algorithm_profile") == expected.get("algorithm_profile"),
        "algorithm_profile_digest": provided.get("algorithm_profile_digest")
        == expected.get("algorithm_profile_digest"),
        "algorithm_profile_digest_self": profile_digest_self_check,
        "source_manifest_digest": provided.get("source_manifest_digest")
        == expected.get("source_manifest_digest"),
        "factor_receipt_digest": provided.get("factor_receipt_digest")
        == expected.get("factor_receipt_digest"),
        "phosphosite_source": provided.get("phosphosite_source")
        == expected.get("phosphosite_source"),
        "source_kinase_catalog": provided.get("source_kinase_catalog")
        == expected.get("source_kinase_catalog"),
        "counts": all(
            provided.get(key) == expected.get(key)
            for key in (
                "selected_feature_count",
                "mapped_feature_count",
                "ambiguous_site_key_count",
                "kinase_count",
                "edge_count",
            )
        ),
        "edges": provided.get("edges") == expected.get("edges"),
        "limitations": provided.get("limitations") == expected.get("limitations"),
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
    report["profile_digest"] = expected.get("algorithm_profile_digest")
    report["verified"] = not mismatches
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phosphosite-source", type=Path, required=True)
    parser.add_argument("--factor-receipt", type=Path, required=True)
    parser.add_argument("--source-manifest-digest", required=True)
    parser.add_argument(
        "destination",
        type=Path,
        nargs="?",
        help="Receipt destination; omit this when --verify-receipt is supplied.",
    )
    parser.add_argument(
        "--verify-receipt",
        type=Path,
        default=None,
        help="Recompute and verify an existing receipt instead of writing a new one.",
    )
    args = parser.parse_args()
    if args.verify_receipt is not None:
        report = verify_edge_map_receipt(
            args.phosphosite_source,
            args.factor_receipt,
            source_manifest_digest=args.source_manifest_digest,
            receipt_path=args.verify_receipt,
        )
        print(json.dumps(report, sort_keys=True))
        return 0 if report["verified"] is True else 1
    if args.destination is None:
        parser.error("destination is required unless --verify-receipt is supplied")
    payload = build_edge_map(
        args.phosphosite_source,
        args.factor_receipt,
        source_manifest_digest=args.source_manifest_digest,
    )
    args.destination.write_bytes(_canonical_bytes(payload))
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "features": payload["mapped_feature_count"],
                "kinases": payload["kinase_count"],
                "edges": payload["edge_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
