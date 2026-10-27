# ruff: noqa: PLR0913, T201, TRY003
"""Run an additive post-hoc two-cohort patient-resampling sensitivity audit.

The original raw-assay stress result must be replayed without alteration before
any sensitivity calculation. This tool never promotes the historical artifact
or claims nominal interval coverage, biological validation, or clinical use.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import asdict, fields
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import (
    DistinctCohortReceipt,
    assert_distinct_cohort_plans,
    load_discovery_plan,
)
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.resampling import (
    REPLICATES,
    resampling_profile,
)
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    PROFILE_ID as PARENT_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    FrozenSourceGeneFit,
    TransferGeneResult,
    deterministic_patient_folds,
    evaluate_external_gene,
    fit_source_gene,
)
from glio_proteogen.research.cptac_gbm_external_admission.transfer_sensitivity import (
    PROFILE_ID,
    REQUIRED,
    ExternalGeneInputs,
    PanelSensitivityResult,
    SourceGeneInputs,
    TwoCohortSensitivityResult,
    evaluate_panel_sensitivity,
)
from tools import evaluate_cptac_gbm_provider_transfer as parent

PARENT_PROTOCOL_DIGEST: Final = (
    "sha256:94b76dada0f8c48aab989500b58e85462f30791508bac161e7216305c6bec588"
)
PARENT_REPORT_MAX_BYTES: Final = 2 * 1024 * 1024
EVALUATION_ID: Final = "cptac-gbm-provider-transfer-two-cohort-real-source-sensitivity/1.0.0"
CohortInputs = parent.CohortInputs


class ParentReportError(ValueError):
    """A bounded locked historical report failed its immutable contract."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ParentReportError("parent report contains a duplicate JSON field")
        result[key] = value
    return result


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ParentReportError("parent report contains a non-finite JSON number")
    return value


def _nonfinite_constant(_token: str) -> None:
    raise ParentReportError("parent report contains a non-finite JSON constant")


def _parent_scope(document: dict[str, Any]) -> None:
    genes = document.get("genes")
    if (
        document.get("evaluation_id") != parent.EVALUATION_ID
        or document.get("profile_id") != PARENT_PROFILE_ID
        or document.get("protocol_digest") != PARENT_PROTOCOL_DIGEST
        or document.get("all_panel_genes_retained") is not True
        or document.get("measurement_bytes_reverified") is not True
        or any(
            document.get(key) is not False
            for key in ("aligned_external_validation", "clinical_validation", "default_promotion")
        )
        or document.get("redistribution_status") != "local_only_terms_unverified"
        or type(genes) is not list
        or len(genes) != len(PANEL)
        or any(type(row) is not dict for row in genes)
        or tuple(row.get("gene") for row in genes) != PANEL
        or any(
            set(row) != {"gene", *(item.name for item in fields(TransferGeneResult))}
            for row in genes
        )
    ):
        raise ParentReportError("parent report does not match the frozen research scope")
    accepted = sum(row.get("accepted") is True for row in genes)
    if (
        type(document.get("accepted_genes")) is not int
        or type(document.get("abstained_genes")) is not int
        or document["accepted_genes"] != accepted
        or document["abstained_genes"] != len(PANEL) - accepted
        or any(type(row.get("accepted")) is not bool for row in genes)
    ):
        raise ParentReportError("parent report panel outcome counts are inconsistent")


def load_parent_report(path: Path, *, lock: SourceLock) -> dict[str, Any]:
    """Admit one exact bounded canonical parent report; no measurement reads."""
    payload = read_verified_source(path, lock, max_bytes=PARENT_REPORT_MAX_BYTES)
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_float=_finite_float,
            parse_constant=_nonfinite_constant,
        )
        if type(document) is not dict:
            raise ParentReportError("parent report must be a JSON object")  # noqa: TRY301
        digest = document.get("report_digest")
        if type(digest) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ParentReportError("parent report lacks a canonical digest")  # noqa: TRY301
        body = {key: value for key, value in document.items() if key != "report_digest"}
        if sha256_digest(body) != digest or canonical_json_bytes(document) != payload:
            raise ParentReportError("parent report canonical digest or bytes did not match")  # noqa: TRY301
        _parent_scope(document)
        parent._aggregate_only(document)
    except ParentReportError:
        raise
    except (UnicodeError, ValueError, TypeError, KeyError, RecursionError):
        raise ParentReportError(
            "parent report was not accepted as canonical research JSON"
        ) from None
    return document


def frozen_protocol(
    *,
    parent_protocol: dict[str, Any],
    parent_report_lock: SourceLock,
    parent_report_digest: str,
    source_fold_assignment_digest: str,
) -> dict[str, Any]:
    """Bind the additive method and its exact historical parent before measurements."""
    body = {key: value for key, value in parent_protocol.items() if key != "protocol_digest"}
    if (
        parent_protocol.get("protocol_digest") != PARENT_PROTOCOL_DIGEST
        or sha256_digest(body) != PARENT_PROTOCOL_DIGEST
        or type(parent_report_digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", parent_report_digest) is None
        or type(source_fold_assignment_digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", source_fold_assignment_digest) is None
        or not isinstance(parent_report_lock, SourceLock)
        or parent_report_lock.bytes > PARENT_REPORT_MAX_BYTES
    ):
        raise ParentReportError("sensitivity protocol requires the exact frozen parent")
    root = files("glio_proteogen.research.cptac_gbm_external_admission")
    protocol: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "panel": PANEL,
        "parent_protocol": parent_protocol,
        "parent_protocol_digest": PARENT_PROTOCOL_DIGEST,
        "parent_report_lock": asdict(parent_report_lock),
        "parent_report_digest": parent_report_digest,
        "parent_report_maximum_bytes": PARENT_REPORT_MAX_BYTES,
        "source_original_fold_assignment_digest": source_fold_assignment_digest,
        "parent_source_fits_and_all_gene_results_must_replay": True,
        "method_sources": {
            name: parent._digest(root.joinpath(name).read_bytes())
            for name in ("transfer_sensitivity.py", "resampling.py")
        },
        "tool_source_digest": parent._digest(Path(__file__).read_bytes()),
        "method_document_digest": parent._digest(
            Path(__file__)
            .resolve()
            .parent.parent.joinpath("docs", "research", "cptac-gbm-transfer-source-uncertainty.md")
            .read_bytes()
        ),
        "post_hoc": True,
        "original_point_source_fitting_before_external_measurement_reads": True,
        "bootstrap_refit_inputs_source_only": True,
        "bootstrap_refits_after_external_loading": True,
        "parent_points_and_abstentions_immutable": True,
        "source_patient_resampling": True,
        "external_patient_resampling": True,
        "resampling_profile": asdict(resampling_profile()),
        "bootstrap": {
            "replicates": REPLICATES,
            "required": REQUIRED,
            "empirical_percentile_level": 0.9,
            "quantiles": "nearest rank ceil(B*.05), ceil(B*.95) among successful draws",
            "schedule_request_digest": "whole sensitivity protocol digest, identical for all genes",
            "models_and_contrasts_paired_on_same_draws": True,
            "source_models_refitted_and_selection_repeated": True,
            "source_original_patient_fold_assignments_fixed": True,
            "duplicate_source_copies_keep_original_fold": True,
        },
        "support_counts_represent_expanded_observation_mass": True,
        "unique_and_kish_counts_are_descriptive_diagnostics": True,
        "resampled_rows_create_new_independent_patients": False,
        "old_original_source_common_oof_minimum": 60,
        "old_original_external_complete_minimum": 48,
        "original_support_gates_lowered": False,
        "source_and_external_sampling_conditional_on_fixed_source_folds": True,
        "assay_axes_converted_or_batch_corrected": False,
        "values_imputed": False,
        "nominal_interval_coverage_established": False,
        "simultaneous_or_multiplicity_adjusted_inference": False,
        "aligned_external_validation": False,
        "clinical_validation": False,
        "causal_identification": False,
        "default_promotion": False,
        "redistribution_status": "local_only_terms_unverified",
    }
    protocol["protocol_digest"] = sha256_digest(protocol)
    return protocol


def _admit_metadata(
    *,
    discovery: CohortInputs,
    confirmatory: CohortInputs,
    discovery_map_bindings_path: Path,
    discovery_map_bindings_sha256: str,
    processing_evidence_path: Path,
    processing_evidence_sha256: str,
    parent_report: dict[str, Any],
) -> tuple[metadata.ExternalAdmissionPlan, metadata.ExternalAdmissionPlan, DistinctCohortReceipt]:
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
    parent._processing_boundary(
        processing_evidence_path,
        processing_evidence_sha256,
        discovery_choices_sha256=discovery.choices_sha256,
        confirmatory_choices_sha256=confirmatory.choices_sha256,
        selected_file_set_digest=sha256_digest(sorted((*source_plan.files, *external_plan.files))),
    )
    for key, value in (
        ("source_metadata", asdict(source_plan.receipt)),
        ("external_metadata", asdict(external_plan.receipt)),
        ("metadata_separation", asdict(separation)),
    ):
        if canonical_json_bytes(parent_report.get(key)) != canonical_json_bytes(value):
            raise ParentReportError("historical parent metadata does not replay")
    return source_plan, external_plan, separation


def _check_source_fits(
    fitted: tuple[FrozenSourceGeneFit, ...], parent_report: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    receipts = tuple(
        {"gene": gene, **asdict(fit.receipt)} for gene, fit in zip(PANEL, fitted, strict=True)
    )
    for receipt, previous in zip(receipts, parent_report["genes"], strict=True):
        if canonical_json_bytes(receipt) != canonical_json_bytes(
            {"gene": previous["gene"], **previous["source"]}
        ):
            raise ParentReportError("historical parent source fits do not replay")
    historical_payload = {
        "protocol_digest": PARENT_PROTOCOL_DIGEST,
        "source_fits": receipts,
        "external_measurements_read": False,
    }
    if sha256_digest(historical_payload) != parent_report.get("source_fit_receipts_digest"):
        raise ParentReportError("historical parent source receipt digest does not replay")
    return receipts


def _check_measurement_receipts(
    source: parent._CohortMatrix,
    external: parent._CohortMatrix,
    parent_report: dict[str, Any],
) -> None:
    for key, value in (
        ("source_protein", source.protein_receipt),
        ("external_protein", external.protein_receipt),
        ("source_coverage", source.coverage),
        ("external_coverage", external.coverage),
    ):
        if canonical_json_bytes(value) != canonical_json_bytes(parent_report.get(key)):
            raise ParentReportError("historical parent measurement receipts do not replay")


def _replay_parent_results(
    fitted: tuple[FrozenSourceGeneFit, ...],
    external: parent._CohortMatrix,
    parent_report: dict[str, Any],
) -> tuple[TransferGeneResult, ...]:
    results = tuple(
        evaluate_external_gene(
            fit,
            external.cnv[index],
            external.rna[index],
            external.protein[index],
            request_digest=sha256_digest({"protocol_digest": PARENT_PROTOCOL_DIGEST, "gene": gene}),
        )
        for index, (gene, fit) in enumerate(zip(PANEL, fitted, strict=True))
    )
    for gene, result, previous in zip(PANEL, results, parent_report["genes"], strict=True):
        if canonical_json_bytes({"gene": gene, **asdict(result)}) != canonical_json_bytes(previous):
            raise ParentReportError("historical parent gene outcomes do not replay")
    return results


def _check_panel_result(
    panel: PanelSensitivityResult,
    parent_results: tuple[TransferGeneResult, ...],
    request_digest: str,
) -> None:
    eligible = sum(result.accepted for result in parent_results)
    joint = panel.jointly_successful_draws_all_eligible
    if (
        panel.profile_id != PROFILE_ID
        or panel.request_digest != request_digest
        or panel.shared_replicates != REPLICATES
        or panel.point_eligible_genes != eligible
        or len(panel.gene_results) != len(PANEL)
        or (eligible == 0 and joint is not None)
        or (eligible > 0 and (type(joint) is not int or not 0 <= joint <= REPLICATES))
        or panel.cross_gene_inference_established is not False
    ):
        raise ValueError("sensitivity panel does not match the frozen evaluation")
    for result, previous in zip(panel.gene_results, parent_results, strict=True):
        if (
            result.profile_id != PROFILE_ID
            or result.request_digest != request_digest
            or canonical_json_bytes(asdict(result.parent_result))
            != canonical_json_bytes(asdict(previous))
            or result.draws_required != REQUIRED
            or result.draws_attempted != (REPLICATES if previous.accepted else 0)
            or not 0 <= result.draws_successful <= result.draws_attempted
            or (
                result.accepted
                and (
                    not previous.accepted
                    or result.draws_successful < REQUIRED
                    or result.uncertainty is None
                )
            )
            or result.original_point_estimates_changed is not False
            or result.post_hoc is not True
            or result.calibrated_coverage_established is not False
            or any(
                getattr(result, key) is not False
                for key in (
                    "aligned_external_validation",
                    "clinical_validation",
                    "default_promotion",
                )
            )
        ):
            raise ValueError("sensitivity result changed the frozen parent outcome")


_RANGE_FIELDS: Final = (
    "primary_joint",
    "primary_frozen_reference",
    "primary_refit_minus_frozen",
    "secondary_joint",
    "secondary_frozen_reference",
    "secondary_refit_minus_frozen",
)
_VARIANCE_FIELDS: Final = (
    "joint_variance",
    "frozen_reference_variance",
    "source_perturbation_variance",
    "twice_covariance",
    "reconstructed_variance",
    "reconstruction_error",
)


def _summary_row(gene: str, result: TwoCohortSensitivityResult) -> dict[str, Any]:
    row: dict[str, Any] = {
        "gene": gene,
        "parent_accepted": result.parent_result.accepted,
        "parent_primary_full_minus_cnv_mae": result.parent_result.primary_full_minus_cnv_mae,
        "parent_secondary_selected_minus_full_mae": (
            result.parent_result.secondary_selected_minus_full_mae
        ),
        "sensitivity_accepted": result.accepted,
        "draws_attempted": result.draws_attempted,
        "draws_successful": result.draws_successful,
        "draws_required": result.draws_required,
        "accepted_source_refits": result.accepted_source_refits,
        "frozen_reference_available_draws": result.frozen_reference_available_draws,
        "reference_available_but_unmatched_draws": result.reference_available_but_unmatched_draws,
        "unavailable_source_selections": result.unavailable_source_selections,
        "failure_reason": result.failure_reason,
    }
    for name in _RANGE_FIELDS:
        interval = getattr(result.uncertainty, name) if result.uncertainty else None
        row[name + "_lower_p05"] = interval.lower if interval else None
        row[name + "_upper_p95"] = interval.upper if interval else None
    for endpoint in ("primary", "secondary"):
        identity = (
            getattr(result.uncertainty, endpoint + "_variance_identity")
            if result.uncertainty
            else None
        )
        for name in _VARIANCE_FIELDS:
            row[endpoint + "_" + name] = getattr(identity, name) if identity else None
    return row


def _write_summary(path: Path, results: tuple[tuple[str, TwoCohortSensitivityResult], ...]) -> None:
    columns = (
        "gene",
        "parent_accepted",
        "parent_primary_full_minus_cnv_mae",
        "parent_secondary_selected_minus_full_mae",
        "sensitivity_accepted",
        "draws_attempted",
        "draws_successful",
        "draws_required",
        "accepted_source_refits",
        "frozen_reference_available_draws",
        "reference_available_but_unmatched_draws",
        "unavailable_source_selections",
        "failure_reason",
        *(name + suffix for name in _RANGE_FIELDS for suffix in ("_lower_p05", "_upper_p95")),
        *(
            endpoint + "_" + name
            for endpoint in ("primary", "secondary")
            for name in _VARIANCE_FIELDS
        ),
    )
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for gene, result in results:
            writer.writerow(_summary_row(gene, result))


def evaluate(
    *,
    discovery: CohortInputs,
    confirmatory: CohortInputs,
    discovery_map_bindings_path: Path,
    discovery_map_bindings_sha256: str,
    hgnc_path: Path,
    processing_evidence_path: Path,
    processing_evidence_sha256: str,
    parent_report_path: Path,
    parent_report_lock: SourceLock,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay the locked parent, then run the separately frozen post-hoc method."""
    previous = load_parent_report(parent_report_path, lock=parent_report_lock)
    source_plan, external_plan, separation = _admit_metadata(
        discovery=discovery,
        confirmatory=confirmatory,
        discovery_map_bindings_path=discovery_map_bindings_path,
        discovery_map_bindings_sha256=discovery_map_bindings_sha256,
        processing_evidence_path=processing_evidence_path,
        processing_evidence_sha256=processing_evidence_sha256,
        parent_report=previous,
    )
    parent_protocol = parent.frozen_protocol(
        discovery=discovery,
        confirmatory=confirmatory,
        discovery_map_bindings_sha256=discovery_map_bindings_sha256,
        processing_evidence_sha256=processing_evidence_sha256,
    )
    folds = deterministic_patient_folds(
        tuple(candidate.case_submitter_id for candidate in source_plan.candidates)
    )
    protocol = frozen_protocol(
        parent_protocol=parent_protocol,
        parent_report_lock=parent_report_lock,
        parent_report_digest=previous["report_digest"],
        source_fold_assignment_digest=sha256_digest(tuple(int(value) for value in folds)),
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    parent._write_json(output_dir / "protocol.json", protocol)
    source = parent._read_cohort(discovery, source_plan, hgnc_path=hgnc_path, discovery=True)
    fitted = tuple(
        fit_source_gene(source.cnv[index], source.rna[index], source.protein[index], folds)
        for index in range(len(PANEL))
    )
    receipts = _check_source_fits(fitted, previous)
    source_receipts = {
        "protocol_digest": protocol["protocol_digest"],
        "parent_protocol_digest": PARENT_PROTOCOL_DIGEST,
        "parent_source_fit_receipts_digest": previous["source_fit_receipts_digest"],
        "source_fits": receipts,
        "parent_source_fits_replayed": True,
        "external_measurements_read": False,
    }
    parent._write_json(output_dir / "source-fit-receipts.json", source_receipts)
    external = parent._read_cohort(
        confirmatory, external_plan, hgnc_path=hgnc_path, discovery=False
    )
    _check_measurement_receipts(source, external, previous)
    parent_results = _replay_parent_results(fitted, external, previous)
    panel = evaluate_panel_sensitivity(
        source_fits=fitted,
        source_inputs=tuple(
            SourceGeneInputs(source.cnv[index], source.rna[index], source.protein[index], folds)
            for index in range(len(PANEL))
        ),
        external_inputs=tuple(
            ExternalGeneInputs(external.cnv[index], external.rna[index], external.protein[index])
            for index in range(len(PANEL))
        ),
        parent_results=parent_results,
        request_digest=protocol["protocol_digest"],
    )
    _check_panel_result(panel, parent_results, protocol["protocol_digest"])
    panel_summary = asdict(panel)
    panel_summary.pop("gene_results")
    results = tuple(zip(PANEL, panel.gene_results, strict=True))
    report: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "parent_protocol_digest": PARENT_PROTOCOL_DIGEST,
        "parent_report_digest": previous["report_digest"],
        "parent_report_lock": asdict(parent_report_lock),
        "source_fit_receipts_digest": sha256_digest(source_receipts),
        "parent_point_replay_verified": True,
        "all_parent_gene_outcomes_preserved": True,
        "parent_accepted_genes": previous["accepted_genes"],
        "parent_abstained_genes": previous["abstained_genes"],
        "metadata_separation": asdict(separation),
        "source_coverage": source.coverage,
        "external_coverage": external.coverage,
        "panel_sensitivity": panel_summary,
        "genes": tuple({"gene": gene, **asdict(result)} for gene, result in results),
        "accepted_genes": sum(result.accepted for _, result in results),
        "abstained_genes": sum(not result.accepted for _, result in results),
        "all_panel_genes_retained": True,
        "post_hoc": True,
        "source_original_patient_fold_assignments_fixed": True,
        "support_counts_represent_expanded_observation_mass": True,
        "unique_and_kish_counts_are_descriptive_diagnostics": True,
        "resampled_rows_create_new_independent_patients": False,
        "original_support_gates_lowered": False,
        "nominal_interval_coverage_established": False,
        "aligned_external_validation": False,
        "clinical_validation": False,
        "causal_identification": False,
        "default_promotion": False,
        "limitations": (
            (
                "Post-hoc sensitivity follows inspection of the frozen historical stress results; "
                "it is not prospective or independent confirmation."
            ),
            (
                "Patient resampling is conditional on the admitted two cohorts, fixed source "
                "folds, empirical measurements, selected estimator and numerical failure rules."
            ),
            (
                "Expanded copies are empirical frequency mass, not additional distinct biological "
                "patients; unique counts and Kish concentration remain descriptive."
            ),
            (
                "Empirical percentile ranges condition on successful paired replays and do not "
                "establish nominal coverage after adaptive model selection."
            ),
            (
                "No assay/reference equivalence, genetic donor independence, causal decomposition, "
                "clinical utility or automatic model promotion is established."
            ),
            (
                "Source hashes bind local integrity and replay, not remote issuer authentication "
                "or redistribution permission."
            ),
        ),
        "redistribution_status": "local_only_terms_unverified",
    }
    report["report_digest"] = sha256_digest(report)
    parent._write_json(output_dir / "evaluation.json", report)
    _write_summary(output_dir / "summary.csv", results)
    return {
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "report_digest": report["report_digest"],
        "parent_report_digest": previous["report_digest"],
        "accepted_genes": report["accepted_genes"],
        "abstained_genes": report["abstained_genes"],
        "parent_accepted_genes": previous["accepted_genes"],
        "parent_abstained_genes": previous["abstained_genes"],
        "verified_assay_files": len(source_plan.files) + len(external_plan.files),
        "post_hoc": True,
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
    parser.add_argument("--parent-report", required=True, type=Path)
    parser.add_argument("--parent-report-bytes", required=True, type=int)
    parser.add_argument("--parent-report-md5", required=True)
    parser.add_argument("--parent-report-sha256", required=True)
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
            parent_report_path=args.parent_report,
            parent_report_lock=SourceLock(
                args.parent_report_bytes, args.parent_report_md5, args.parent_report_sha256
            ),
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, TypeError):
        parser.exit(
            2,
            "Transfer sensitivity failed; private inputs or immutable parent contracts "
            "were not satisfied.\n",
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
