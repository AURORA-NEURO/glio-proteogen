# ruff: noqa: PLR0913, T201, TRY003
"""Run local raw-assay transfer stress with frozen source-only model selection."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from dataclasses import asdict, dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import discovery as source_protein
from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_external_admission import protein as test_protein
from glio_proteogen.research.cptac_gbm_external_admission.assays import (
    ParsedAssayPanel,
    parse_ascat_gene_cnv,
    parse_star_counts_v36,
)
from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import (
    assert_distinct_cohort_plans,
    load_discovery_plan,
)
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL
from glio_proteogen.research.cptac_gbm_external_admission.identity import (
    HGNC_LOCK,
    read_locked_hgnc,
)
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_REQUIRED,
    CANDIDATE_ORDER,
    EXTERNAL_MINIMUM,
    PROFILE_ID,
    TransferGeneResult,
    deterministic_patient_folds,
    evaluate_external_gene,
    fit_source_gene,
)

EVALUATION_ID: Final = "cptac-gbm-provider-transfer-real-source-evaluation/1.0.0"
SELECTED_ASSAY_FILES: Final = 256
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CohortInputs:
    choices_path: Path = field(repr=False)
    choices_sha256: str
    files_manifest_path: Path = field(repr=False)
    files_manifest_sha256: str
    protein_path: Path = field(repr=False)
    sample_map_path: Path = field(repr=False)


@dataclass(frozen=True, slots=True)
class _CohortMatrix:
    cnv: FloatArray = field(repr=False)
    rna: FloatArray = field(repr=False)
    protein: FloatArray = field(repr=False)
    coverage: tuple[dict[str, Any], ...]
    protein_receipt: dict[str, Any]

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient cohort matrices cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient cohort matrices cannot be serialized")


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def _processing_boundary(
    path: Path,
    digest: str,
    *,
    discovery_choices_sha256: str,
    confirmatory_choices_sha256: str,
    selected_file_set_digest: str,
) -> None:
    receipt = metadata._read_json(path, digest)
    if not isinstance(receipt, dict) or (
        receipt.get("receipt_id") != "cptac-raw-assay-processing-boundary/1.0.0"
        or receipt.get("selected_files_metadata_only") != SELECTED_ASSAY_FILES
        or receipt.get("discovery_choices_sha256") != discovery_choices_sha256
        or receipt.get("confirmatory_choices_sha256") != confirmatory_choices_sha256
        or receipt.get("selected_file_set_digest") != selected_file_set_digest
        or any(
            receipt.get(key) is not False
            for key in (
                "reference_material_equivalence_proven",
                "complete_processing_identity_proven",
                "genetic_donor_independence_proven",
                "cnv_gene_annotation_release_admitted",
            )
        )
    ):
        raise ValueError("processing evidence does not satisfy the declared stress boundary")
    groups = receipt.get("gdc_workflow_groups")
    if type(groups) is not list:
        raise ValueError("processing evidence lacks bounded workflow groups")
    totals: dict[tuple[str, str], int] = {}
    for row in groups:
        if not isinstance(row, dict) or type(row.get("files")) is not int or row["files"] < 1:
            raise ValueError("processing evidence workflow group is invalid")
        cohort, workflow = row.get("cohort"), row.get("workflow_type")
        if cohort not in ("discovery", "confirmatory") or workflow not in (
            "STAR - Counts",
            "AscatNGS",
        ):
            raise ValueError("processing evidence workflow scope is invalid")
        key = (cohort, workflow)
        totals[key] = totals.get(key, 0) + row["files"]
    if totals != {
        (cohort, workflow): count
        for cohort, count in (("discovery", 72), ("confirmatory", 56))
        for workflow in ("STAR - Counts", "AscatNGS")
    }:
        raise ValueError("processing evidence does not cover every selected assay file")


def frozen_protocol(
    *,
    discovery: CohortInputs,
    confirmatory: CohortInputs,
    discovery_map_bindings_sha256: str,
    processing_evidence_sha256: str,
) -> dict[str, Any]:
    """Bind code and fixed input sources before reading any assay measurements."""
    for value in (
        discovery.choices_sha256,
        discovery.files_manifest_sha256,
        confirmatory.choices_sha256,
        confirmatory.files_manifest_sha256,
        discovery_map_bindings_sha256,
        processing_evidence_sha256,
    ):
        metadata._sha256(value)
    root = files("glio_proteogen.research.cptac_gbm_external_admission")
    nested_root = files("glio_proteogen.research.cptac_gbm_transcript_protein_discordance")
    protocol: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform_system": platform.system(),
        "machine": platform.machine(),
        "panel": PANEL,
        "source_modules": {
            name: _digest(root.joinpath(name).read_bytes())
            for name in (
                "contracts.py",
                "source.py",
                "identity.py",
                "protein.py",
                "discovery.py",
                "assays.py",
                "plan.py",
                "cohort_plan.py",
                "transfer.py",
            )
        },
        "nested_dependency_sources": {
            name: _digest(nested_root.joinpath(name).read_bytes())
            for name in ("nested_selection.py", "model.py", "convergence.py", "profile.py")
        },
        "huber_dependency_source": _digest(
            files("glio_proteogen.research.cptac_gbm_cis_dosage").joinpath("model.py").read_bytes()
        ),
        "canonical_dependency_source": _digest(
            files("glio_proteogen.kernel").joinpath("canonical.py").read_bytes()
        ),
        "tool_source_digest": _digest(Path(__file__).read_bytes()),
        "method_document_digest": _digest(
            Path(__file__)
            .resolve()
            .parent.parent.joinpath("docs", "research", "cptac-gbm-provider-transfer.md")
            .read_bytes()
        ),
        "input_bindings": {
            "source_choices": discovery.choices_sha256,
            "source_manifest": discovery.files_manifest_sha256,
            "source_channel_bindings": discovery_map_bindings_sha256,
            "external_choices": confirmatory.choices_sha256,
            "external_manifest": confirmatory.files_manifest_sha256,
            "processing_evidence": processing_evidence_sha256,
            "source_protein": asdict(source_protein.PROTEIN_LOCK),
            "source_map": asdict(source_protein.SAMPLE_MAP_LOCK),
            "external_protein": asdict(test_protein.PROTEIN_LOCK),
            "external_map": asdict(test_protein.SAMPLE_MAP_LOCK),
            "hgnc": asdict(HGNC_LOCK),
        },
        "measurement_axes": {
            "protein": "CDAP median-normalized Unshared Log Ratio; log2 specimen/reference",
            "rna": "STAR GENCODEv36 fpkm_uq_unstranded",
            "cnv": "AscatNGS total copy_number; annotation release undeclared",
        },
        "source_folds": (
            "sort SHA256(ASCII case_submitter_id), tie by exact key, assign round-robin modulo5"
        ),
        "source_only_fit_before_any_external_measurement_read": True,
        "nested_source_gates": {
            "outer_train": 48,
            "outer_test": 3,
            "outer_folds": 4,
            "common_oof": 60,
            "inner_train": 32,
            "inner_test": 3,
        },
        "final_selection": (
            "pooled unrounded source fivefold OOF MAE; every candidate covers all "
            "source-complete cases; exact tie order fixed; refit all source-complete"
        ),
        "candidate_tie_order": CANDIDATE_ORDER,
        "iteration_budget": 240,
        "external_common_complete_minimum": EXTERNAL_MINIMUM,
        "external_minimum_basis": (
            "new engineering precision policy; not a validated power calculation "
            "or legacy gate change"
        ),
        "primary_contrast": "MAE(full) minus MAE(cnv_only)",
        "secondary_contrast": "MAE(selected_policy) minus MAE(full)",
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "required": BOOTSTRAP_REQUIRED,
            "confidence_level": 0.9,
            "quantile": "nearest rank ceil(B*p), p=.05/.95",
            "draws": "external complete-case patients, one shared draw across all models",
            "training_refitted": False,
            "training_uncertainty_available": False,
            "seed": (
                "first8 SHA256(profile_id + :external-paired: + gene request digest) "
                "as big-endian uint64"
            ),
        },
        "values_imputed": False,
        "assay_axes_converted_or_batch_corrected": False,
        "source_training_robust_center_scale_only": True,
        "reference_material_equivalence_proven": False,
        "complete_processing_identity_proven": False,
        "aligned_external_validation": False,
        "clinical_validation": False,
        "default_promotion": False,
        "metadata_issuer_authenticated_by_hashes": False,
        "prior_information": (
            "literature panel and source-informed model family; external protein "
            "coverage inspected before protocol freeze; no external prediction-error "
            "results used to choose this profile"
        ),
        "redistribution_status": "local_only_terms_unverified",
    }
    protocol["protocol_digest"] = sha256_digest(protocol)
    return protocol


def _aggregate_only(value: object) -> None:
    if isinstance(value, dict):
        if {
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
            "participants",
            "_predictors",
            "candidate_rows",
        }.intersection(value):
            raise ValueError("individual source fields cannot be exported")
        for item in value.values():
            _aggregate_only(item)
    elif isinstance(value, (list, tuple)):
        if len(value) in (56, 72, 112, 144):
            raise ValueError("individual source vectors cannot be exported")
        for item in value:
            _aggregate_only(item)
    elif isinstance(value, np.ndarray):
        raise TypeError("transient source arrays cannot be exported")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _aggregate_only(payload)
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(payload))


def _read_cohort(
    inputs: CohortInputs, plan: metadata.ExternalAdmissionPlan, *, hgnc_path: Path, discovery: bool
) -> _CohortMatrix:
    hgnc = read_locked_hgnc(hgnc_path)
    admit = (
        source_protein.admit_discovery_protein
        if discovery
        else test_protein.admit_confirmatory_protein
    )
    protein = admit(
        protein_path=inputs.protein_path,
        sample_map_path=inputs.sample_map_path,
        hgnc_path=hgnc_path,
        candidate_aliquots=plan.protein_aliquots,
    )
    count = 72 if discovery else 56
    if (
        len(plan.candidates) != count
        or protein.candidate_digest != sha256_digest(plan.protein_aliquots)
        or protein.values.shape != (len(protein.identities), count)
    ):
        raise ValueError("protein admission and ordered metadata plan differ")
    rna_panels: list[ParsedAssayPanel] = []
    cnv_panels: list[ParsedAssayPanel] = []
    for candidate in plan.candidates:
        rna_binding, cnv_binding = (
            plan.files[candidate.rna_file_id],
            plan.files[candidate.cnv_file_id],
        )
        rna_panels.append(
            parse_star_counts_v36(
                inputs.files_manifest_path.parent / rna_binding.relative_path,
                lock=rna_binding.lock,
                hgnc=hgnc,
            )
        )
        cnv_panels.append(
            parse_ascat_gene_cnv(
                inputs.files_manifest_path.parent / cnv_binding.relative_path,
                lock=cnv_binding.lock,
                hgnc=hgnc,
            )
        )
    for axis, panels in (
        ("star_fpkm_uq_unstranded", rna_panels),
        ("ascat_total_copy_number", cnv_panels),
    ):
        if any(
            panel.receipt.axis != axis
            or panel.panel_symbols != PANEL
            or panel.values.shape != (len(PANEL),)
            for panel in panels
        ):
            raise ValueError("assay family or identity order differs from the fixed panel")
    rna = np.column_stack([panel.values for panel in rna_panels])
    cnv = np.column_stack([panel.values for panel in cnv_panels])
    by_symbol = {
        identity.symbol: index
        for index, identity in enumerate(protein.identities)
        if identity is not None
    }
    if len(by_symbol) != sum(identity is not None for identity in protein.identities):
        raise ValueError("protein stable gene identities are not unique")
    protein_panel = np.vstack(
        [
            protein.values[by_symbol[gene]] if gene in by_symbol else np.full(count, np.nan)
            for gene in PANEL
        ]
    )
    coverage = tuple(
        {
            "gene": gene,
            "candidate_specimens": count,
            "protein_feature_present": gene in by_symbol,
            "observed_cnv": int(np.isfinite(cnv[index]).sum()),
            "observed_rna": int(np.isfinite(rna[index]).sum()),
            "observed_protein": int(np.isfinite(protein_panel[index]).sum()),
            "joint_complete": int(
                (
                    np.isfinite(cnv[index])
                    & np.isfinite(rna[index])
                    & np.isfinite(protein_panel[index])
                ).sum()
            ),
            "zero_cnv": int((cnv[index] == 0).sum()),
            "zero_rna": int((rna[index] == 0).sum()),
            "zero_protein": int((protein_panel[index] == 0).sum()),
        }
        for index, gene in enumerate(PANEL)
    )
    immutable = tuple(
        np.frombuffer(np.ascontiguousarray(values).tobytes(), dtype=np.float64).reshape(
            values.shape
        )
        for values in (cnv, rna, protein_panel)
    )
    return _CohortMatrix(
        immutable[0], immutable[1], immutable[2], coverage, asdict(protein.receipt)
    )


def _write_summary(path: Path, results: tuple[tuple[str, TransferGeneResult], ...]) -> None:
    fields = (
        "gene",
        "accepted",
        "source_complete",
        "source_common_oof",
        "external_complete",
        "external_common_comparison",
        "selected_candidate",
        "full_mae",
        "cnv_only_mae",
        "selected_mae",
        "full_minus_cnv_mae",
        "selected_minus_full_mae",
        "primary_lower90",
        "primary_upper90",
        "failure_reason",
    )
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for gene, result in results:
            metrics = {item.candidate: item for item in result.point_metrics}
            uncertainty = result.uncertainty
            writer.writerow(
                {
                    "gene": gene,
                    "accepted": result.accepted,
                    "source_complete": result.source.complete_count,
                    "source_common_oof": result.source.common_oof_count,
                    "external_complete": result.external_complete_count,
                    "external_common_comparison": result.external_common_comparison_count,
                    "selected_candidate": result.source.selected_candidate,
                    "full_mae": metrics["full"].mae if "full" in metrics else None,
                    "cnv_only_mae": metrics["cnv_only"].mae if "cnv_only" in metrics else None,
                    "selected_mae": metrics["selected_policy"].mae
                    if "selected_policy" in metrics
                    else None,
                    "full_minus_cnv_mae": result.primary_full_minus_cnv_mae,
                    "selected_minus_full_mae": result.secondary_selected_minus_full_mae,
                    "primary_lower90": uncertainty.primary_full_minus_cnv_mae.lower
                    if uncertainty
                    else None,
                    "primary_upper90": uncertainty.primary_full_minus_cnv_mae.upper
                    if uncertainty
                    else None,
                    "failure_reason": result.failure_reason,
                }
            )


def evaluate(
    *,
    discovery: CohortInputs,
    confirmatory: CohortInputs,
    discovery_map_bindings_path: Path,
    discovery_map_bindings_sha256: str,
    hgnc_path: Path,
    processing_evidence_path: Path,
    processing_evidence_sha256: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Read verified cohorts, fit source first, retain all16 aggregate outcomes."""
    source_plan = load_discovery_plan(
        choices_path=discovery.choices_path,
        choices_sha256=discovery.choices_sha256,
        map_bindings_path=discovery_map_bindings_path,
        map_bindings_sha256=discovery_map_bindings_sha256,
        files_manifest_path=discovery.files_manifest_path,
        files_manifest_sha256=discovery.files_manifest_sha256,
    )
    external_plan = metadata.load_admission_plan(
        choices_path=confirmatory.choices_path,
        choices_sha256=confirmatory.choices_sha256,
        files_manifest_path=confirmatory.files_manifest_path,
        files_manifest_sha256=confirmatory.files_manifest_sha256,
    )
    separation = assert_distinct_cohort_plans(source_plan, external_plan)
    _processing_boundary(
        processing_evidence_path,
        processing_evidence_sha256,
        discovery_choices_sha256=discovery.choices_sha256,
        confirmatory_choices_sha256=confirmatory.choices_sha256,
        selected_file_set_digest=sha256_digest(sorted((*source_plan.files, *external_plan.files))),
    )
    protocol = frozen_protocol(
        discovery=discovery,
        confirmatory=confirmatory,
        discovery_map_bindings_sha256=discovery_map_bindings_sha256,
        processing_evidence_sha256=processing_evidence_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "protocol.json", protocol)
    source = _read_cohort(discovery, source_plan, hgnc_path=hgnc_path, discovery=True)
    folds = deterministic_patient_folds(
        tuple(candidate.case_submitter_id for candidate in source_plan.candidates)
    )
    fitted = tuple(
        fit_source_gene(source.cnv[index], source.rna[index], source.protein[index], folds)
        for index in range(len(PANEL))
    )
    # Persist only aggregate fitting evidence before external measurements exist
    # in this process. Never serialize the transient fitted predictor objects.
    source_receipts = {
        "protocol_digest": protocol["protocol_digest"],
        "source_fits": tuple(
            {"gene": gene, **asdict(fit.receipt)} for gene, fit in zip(PANEL, fitted, strict=True)
        ),
        "external_measurements_read": False,
    }
    _write_json(output_dir / "source-fit-receipts.json", source_receipts)
    external = _read_cohort(confirmatory, external_plan, hgnc_path=hgnc_path, discovery=False)
    results = tuple(
        (
            gene,
            evaluate_external_gene(
                fit,
                external.cnv[index],
                external.rna[index],
                external.protein[index],
                request_digest=sha256_digest(
                    {"protocol_digest": protocol["protocol_digest"], "gene": gene}
                ),
            ),
        )
        for index, (gene, fit) in enumerate(zip(PANEL, fitted, strict=True))
    )
    report: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_fit_receipts_digest": sha256_digest(source_receipts),
        "metadata_separation": asdict(separation),
        "source_metadata": asdict(source_plan.receipt),
        "external_metadata": asdict(external_plan.receipt),
        "source_protein": source.protein_receipt,
        "external_protein": external.protein_receipt,
        "source_coverage": source.coverage,
        "external_coverage": external.coverage,
        "genes": tuple({"gene": gene, **asdict(result)} for gene, result in results),
        "accepted_genes": sum(result.accepted for _, result in results),
        "abstained_genes": sum(not result.accepted for _, result in results),
        "all_panel_genes_retained": True,
        "measurement_bytes_reverified": True,
        "aligned_external_validation": False,
        "clinical_validation": False,
        "default_promotion": False,
        "limitations": (
            (
                "Raw-coordinate prediction errors include historical provider and reference-pool "
                "shifts; physical reference-lot equivalence and complete processing identity "
                "are unproved."
            ),
            (
                "Intervals describe external patient resampling conditional on the frozen fitted "
                "source models; training, selection and full measurement uncertainty "
                "are unavailable."
            ),
            (
                "The literature panel, model family and inspected protein coverage predate this "
                "freeze; this is not a cohort-blind prospective clinical experiment."
            ),
            (
                "No genetic donor independence, contemporary molecular eligibility, clinical "
                "utility, causal mechanism, novel biomarker discovery or AlphaFold-scale "
                "capability is established."
            ),
            (
                "Nominal per-gene intervals are exploratory; no multiplicity-adjusted discoveries "
                "or automatic model promotion are made."
            ),
            (
                "Source captures and their hashes establish local integrity and explicit bindings, "
                "not remote issuer authentication or permission to redistribute source-derived "
                "measurements."
            ),
        ),
        "redistribution_status": "local_only_terms_unverified",
    }
    report["report_digest"] = sha256_digest(report)
    _write_json(output_dir / "evaluation.json", report)
    _write_summary(output_dir / "summary.csv", results)
    return {
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "report_digest": report["report_digest"],
        "accepted_genes": report["accepted_genes"],
        "abstained_genes": report["abstained_genes"],
        "verified_assay_files": len(source_plan.files) + len(external_plan.files),
        "aligned_external_validation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for prefix in ("source", "external"):
        for name in ("choices", "files-manifest", "protein", "sample-map"):
            parser.add_argument(f"--{prefix}-{name}", required=True, type=Path)
        for name in ("choices-sha256", "files-manifest-sha256"):
            parser.add_argument(f"--{prefix}-{name}", required=True)
    parser.add_argument("--source-map-bindings", required=True, type=Path)
    parser.add_argument("--source-map-bindings-sha256", required=True)
    parser.add_argument("--hgnc", required=True, type=Path)
    parser.add_argument("--processing-evidence", required=True, type=Path)
    parser.add_argument("--processing-evidence-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    def inputs(prefix: str) -> CohortInputs:
        return CohortInputs(
            *(
                getattr(args, f"{prefix}_{name}")
                for name in (
                    "choices",
                    "choices_sha256",
                    "files_manifest",
                    "files_manifest_sha256",
                    "protein",
                    "sample_map",
                )
            )
        )

    try:
        summary = evaluate(
            discovery=inputs("source"),
            confirmatory=inputs("external"),
            discovery_map_bindings_path=args.source_map_bindings,
            discovery_map_bindings_sha256=args.source_map_bindings_sha256,
            hgnc_path=args.hgnc,
            processing_evidence_path=args.processing_evidence,
            processing_evidence_sha256=args.processing_evidence_sha256,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, TypeError):
        parser.exit(
            2,
            "Provider-transfer evaluation failed; private inputs or frozen contracts "
            "were not satisfied.\n",
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
