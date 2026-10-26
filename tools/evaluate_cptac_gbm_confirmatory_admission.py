# ruff: noqa: PLR0913, T201, TRY003
"""Produce aggregate joint coverage from frozen private confirmatory source inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

import numpy as np
from glio_proteogen.research.cptac_gbm_external_admission.plan import load_admission_plan

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.assays import (
    parse_ascat_gene_cnv,
    parse_star_counts_v36,
)
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL
from glio_proteogen.research.cptac_gbm_external_admission.coverage import (
    PROFILE_ID,
    JointCoverageReceipt,
    summarize_joint_coverage,
)
from glio_proteogen.research.cptac_gbm_external_admission.identity import read_locked_hgnc
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    PROTEIN_LOCK,
    SAMPLE_MAP_LOCK,
    admit_confirmatory_protein,
)

EVALUATION_ID: Final = "cptac-gbm-confirmatory-real-source-admission/1.0.0"
SOURCE_MODULES: Final = (
    "contracts.py",
    "source.py",
    "identity.py",
    "protein.py",
    "assays.py",
    "plan.py",
    "coverage.py",
)


def _source_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def frozen_protocol(*, choices_sha256: str, files_manifest_sha256: str) -> dict[str, Any]:
    """Bind method and caller-trusted frozen captures before reading measurements."""
    root = files("glio_proteogen.research.cptac_gbm_external_admission")
    protocol: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "panel": PANEL,
        "source_modules": {
            name: _source_digest(root.joinpath(name).read_bytes()) for name in SOURCE_MODULES
        },
        "tool_source_digest": _source_digest(Path(__file__).read_bytes()),
        "frozen_metadata_choices_sha256": "sha256:" + choices_sha256,
        "frozen_private_file_manifest_sha256": "sha256:" + files_manifest_sha256,
        "protein_source_lock": asdict(PROTEIN_LOCK),
        "protein_sample_map_lock": asdict(SAMPLE_MAP_LOCK),
        "measurement_axes": {
            "protein": "CDAP median-normalized Unshared Log Ratio; log2 specimen/common-reference",
            "rna": "STAR GENCODEv36 fpkm_uq_unstranded",
            "cnv": "AscatNGS total copy_number; annotation release undeclared",
        },
        "missingness_pattern_order": "CNV_RNA_PROTEIN;1=finite observed,0=unavailable",
        "values_transformed": False,
        "values_imputed": False,
        "models_fitted": False,
        "metadata_issuer_authenticated_by_hashes": False,
        "clinical_scope_or_assay_compatibility_admitted": False,
        "redistribution_status": "local_only_terms_unverified",
    }
    protocol["protocol_digest"] = sha256_digest(protocol)
    return protocol


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _aggregate_only(payload)
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(payload))


def _aggregate_only(value: object) -> None:
    forbidden = {
        "file_id",
        "relative_path",
        "case_submitter_id",
        "sample_submitter_id",
        "gdc_sample_uuid",
        "protein_aliquot_submitter_id",
        "protein_aliquot_uuid",
        "values",
        "predictions",
        "residuals",
        "candidate_rows",
        "participants",
    }
    if isinstance(value, dict):
        if forbidden.intersection(value):
            raise ValueError("individual source fields cannot be exported")
        for nested in value.values():
            _aggregate_only(nested)
    elif isinstance(value, (list, tuple)):
        if len(value) in (56, 112):
            raise ValueError("individual source vectors cannot be exported")
        for nested in value:
            _aggregate_only(nested)
    elif isinstance(value, np.ndarray):
        raise TypeError("transient source arrays cannot be exported")


def _write_summary(path: Path, coverage: JointCoverageReceipt) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "gene",
                "candidate_specimens",
                "protein_feature_present",
                "observed_cnv",
                "observed_rna",
                "observed_protein",
                "joint_complete",
                "zero_cnv",
                "zero_rna",
                "zero_protein",
                "legacy_common_oof_minimum",
                "legacy_common_oof_support_possible",
            ],
        )
        writer.writeheader()
        for gene in coverage.genes:
            row = asdict(gene)
            writer.writerow({key: row[key] for key in writer.fieldnames or ()})


def evaluate(
    *,
    choices_path: Path,
    choices_sha256: str,
    files_manifest_path: Path,
    files_manifest_sha256: str,
    protein_path: Path,
    sample_map_path: Path,
    hgnc_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Read every frozen file once per parser; write aggregate evidence only."""
    plan = load_admission_plan(
        choices_path=choices_path,
        choices_sha256=choices_sha256,
        files_manifest_path=files_manifest_path,
        files_manifest_sha256=files_manifest_sha256,
    )
    protocol = frozen_protocol(
        choices_sha256=choices_sha256, files_manifest_sha256=files_manifest_sha256
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "protocol.json", protocol)
    hgnc = read_locked_hgnc(hgnc_path)
    protein = admit_confirmatory_protein(
        protein_path=protein_path,
        sample_map_path=sample_map_path,
        hgnc_path=hgnc_path,
        candidate_aliquots=plan.protein_aliquots,
    )
    rna_panels = []
    cnv_panels = []
    for candidate in plan.candidates:
        rna_input = plan.files[candidate.rna_file_id]
        cnv_input = plan.files[candidate.cnv_file_id]
        rna_panels.append(
            parse_star_counts_v36(
                files_manifest_path.parent / rna_input.relative_path,
                lock=rna_input.lock,
                hgnc=hgnc,
            )
        )
        cnv_panels.append(
            parse_ascat_gene_cnv(
                files_manifest_path.parent / cnv_input.relative_path,
                lock=cnv_input.lock,
                hgnc=hgnc,
            )
        )
    coverage = summarize_joint_coverage(
        protein=protein, rna_panels=rna_panels, cnv_panels=cnv_panels
    )
    report: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "protocol_digest": protocol["protocol_digest"],
        "status": "all_declared_files_parsed_aggregate_coverage_only",
        "metadata_plan": asdict(plan.receipt),
        "measurement_bytes_reverified_by_assay_parsers": True,
        "protein": asdict(protein.receipt),
        "joint_coverage": asdict(coverage),
        "independent_validation": False,
        "legacy_estimator_changed": False,
        "redistribution_status": "local_only_terms_unverified",
    }
    report["report_digest"] = sha256_digest(report)
    _write_json(output_dir / "evaluation.json", report)
    _write_summary(output_dir / "summary.csv", coverage)
    return {
        "report_digest": report["report_digest"],
        "candidate_specimens": coverage.candidate_specimens,
        "verified_assay_files": coverage.verified_rna_files + coverage.verified_cnv_files,
        "joint_complete_gene_specimen_pairs": coverage.complete_gene_specimen_pairs,
        "legacy_fit_admitted": False,
        "independent_validation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--choices", required=True, type=Path)
    parser.add_argument("--choices-sha256", required=True)
    parser.add_argument("--files-manifest", required=True, type=Path)
    parser.add_argument("--files-manifest-sha256", required=True)
    parser.add_argument("--protein", required=True, type=Path)
    parser.add_argument("--sample-map", required=True, type=Path)
    parser.add_argument("--hgnc", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = evaluate(
            choices_path=args.choices,
            choices_sha256=args.choices_sha256,
            files_manifest_path=args.files_manifest,
            files_manifest_sha256=args.files_manifest_sha256,
            protein_path=args.protein,
            sample_map_path=args.sample_map,
            hgnc_path=args.hgnc,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, TypeError):
        parser.exit(
            2, "Source admission failed; private inputs did not satisfy the declared contracts.\n"
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
