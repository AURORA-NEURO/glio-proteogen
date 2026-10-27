# ruff: noqa: PLR0913, T201, TRY003
"""Recompute frozen census numerics with separately bound operational execution."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_census_execution.baseline import (
    BaselineCensus,
    load_baseline_census,
)
from glio_proteogen.research.cptac_gbm_census_execution.contracts import (
    PROFILE_ID as EXECUTION_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_census_execution.progress import (
    DEFAULT_POLICY,
    MAX_PROGRESS_BYTES,
    RETRYABLE_WINERRORS,
    write_progress_snapshot,
)
from glio_proteogen.research.cptac_gbm_external_admission import discovery as discovery_module
from glio_proteogen.research.cptac_gbm_external_admission import protein
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    SourceLock,
)
from glio_proteogen.research.cptac_gbm_external_admission.identity import read_locked_hgnc
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    deterministic_patient_folds,
)
from glio_proteogen.research.cptac_gbm_feature_space.atlas import (
    SourceFeatureCatalog,
    build_source_catalog,
    project_external_coverage,
)
from glio_proteogen.research.cptac_gbm_feature_space.cohort import (
    build_cohort_matrix,
    derive_source_axis,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.contracts import (
    DEFAULT_PAGE_SIZE,
    MAX_MANIFEST_BYTES,
    PROFILE_ID,
    CensusError,
    ReceiptPageBinding,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.engine import (
    FrozenSourceCensus,
    fit_source_census,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.storage import JsonCensusReceiptStore
from tools import evaluate_cptac_gbm_feature_space as admission
from tools import evaluate_cptac_gbm_provider_transfer as parent
from tools import evaluate_cptac_gbm_source_fit_census as numerical
from tools import evaluate_cptac_gbm_transfer_sensitivity as historical

if TYPE_CHECKING:
    from collections.abc import Callable

    from glio_proteogen.research.cptac_gbm_feature_space.contracts import FeatureMatrix

EVALUATION_ID: Final = numerical.EVALUATION_ID
EXECUTION_EVALUATION_ID: Final = "cptac-gbm-real-census-execution/1.0.0"
MAX_EXTERNAL_BYTES: Final = numerical.MAX_EXTERNAL_BYTES
CohortInputs = parent.CohortInputs
_FALSE_FLAGS: Final = numerical._FALSE_FLAGS
_EXECUTION_NAMES: Final = ("execution-protocol.json", "execution.json")


def frozen_protocol(
    *, numerical_protocol: dict[str, Any], baseline: BaselineCensus
) -> dict[str, Any]:
    """Bind actual new execution code separately from unchanged numerical seeds."""
    if canonical_json_bytes(numerical_protocol) != canonical_json_bytes(
        baseline.protocol_document()
    ):
        raise CensusError("execution requires the identical frozen numerical protocol")
    root = files("glio_proteogen.research.cptac_gbm_census_execution")
    document: dict[str, Any] = {
        "profile_id": EXECUTION_PROFILE_ID,
        "evaluation_id": EXECUTION_EVALUATION_ID,
        "numerical_profile_id": numerical_protocol["profile_id"],
        "numerical_protocol_digest": numerical_protocol["protocol_digest"],
        "baseline_receipt": asdict(baseline.receipt),
        "baseline_artifact_inventory_digest": sha256_digest(
            tuple(asdict(row) for row in baseline.artifact_bindings)
        ),
        "baseline_artifact_count": len(baseline.artifact_bindings),
        "additional_artifact_names": _EXECUTION_NAMES,
        "execution_method_sources": {
            name: parent._digest(root.joinpath(name).read_bytes())
            for name in ("__init__.py", "contracts.py", "baseline.py", "progress.py")
        },
        "execution_tool_source_digest": parent._digest(Path(__file__).read_bytes()),
        "execution_method_document_digest": parent._digest(
            Path(__file__)
            .resolve()
            .parent.parent.joinpath("docs/research/cptac-gbm-census-execution.md")
            .read_bytes()
        ),
        "inherited_reference_tool_source_digest": parent._digest(
            Path(numerical.__file__).read_bytes()
        ),
        "progress_retry_policy": asdict(DEFAULT_POLICY),
        "maximum_progress_bytes": MAX_PROGRESS_BYTES,
        "retryable_windows_errors": tuple(sorted(RETRYABLE_WINERRORS)),
        "retry_scope": (
            "Only replacement of one already-written canonical progress payload; "
            "no fitting or scoring is retried."
        ),
        "retry_budget_bounds_scheduling_not_uninterruptible_os_call": True,
        "old_cli_retroactively_changed": False,
        "new_execution_provenance_required": True,
        "all_inherited_numerical_artifacts_must_replay_byte_exactly": True,
        "source_artifact_parity_before_external_measurements": True,
        "numerical_request_digest_uses_execution_protocol": False,
        "source_fits_recomputed": True,
        "baseline_predictors_reused": False,
        "private_predictors_persisted": False,
        "resume_supported": False,
        "exhaustion_is_operational_failure_not_gene_abstention": True,
        "retry_timings_or_counts_persisted": False,
        "post_hoc": True,
        "new_scientific_inference_lane": False,
        "biological_validation": False,
        "clinical_validation": False,
        "multiplicity_adjusted_discoveries": False,
        "redistribution_status": "local_only_terms_unverified",
    }
    parent._aggregate_only(document)
    document["execution_protocol_digest"] = sha256_digest(document)
    return document


def _progress(
    output: Path,
    state: dict[str, Any],
    *,
    cancel: Callable[[], None] | None = None,
    **changes: object,
) -> None:
    state.update(changes)
    parent._aggregate_only(state)
    write_progress_snapshot(output, canonical_json_bytes(state), cancel=cancel)


def _execution_seal(
    output: Path, *, baseline: BaselineCensus, protocol: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    baseline.verify_complete_output(output, allowed_extra_names=("execution-protocol.json",))
    expected = canonical_json_bytes(protocol)
    lock = SourceLock(
        bytes=len(expected),
        md5=hashlib.md5(expected, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(expected).hexdigest(),
    )
    read_verified_source(output / "execution-protocol.json", lock, max_bytes=2 * 1024**2)
    document: dict[str, Any] = {
        "profile_id": EXECUTION_PROFILE_ID,
        "evaluation_id": EXECUTION_EVALUATION_ID,
        "execution_protocol_digest": protocol["execution_protocol_digest"],
        "numerical_profile_id": report["profile_id"],
        "numerical_protocol_digest": report["protocol_digest"],
        "numerical_report_digest": report["report_digest"],
        "baseline_artifact_inventory_digest": protocol["baseline_artifact_inventory_digest"],
        "inherited_artifact_count": len(baseline.artifact_bindings),
        "all_inherited_artifacts_byte_identical": True,
        "source_parity_verified_before_external_measurements": True,
        "all_genes_attempted_and_retained": True,
        "source_fits_recomputed": True,
        "baseline_predictors_reused": False,
        "private_predictors_persisted": False,
        "numerical_request_digest_uses_execution_protocol": False,
        "retry_timings_or_counts_persisted": False,
        "new_scientific_inference_lane": False,
        "biological_validation": False,
        "clinical_validation": False,
        "post_hoc": True,
        "complete": True,
        "redistribution_status": "local_only_terms_unverified",
    }
    document["execution_digest"] = sha256_digest(document)
    admission._write_json(output / "execution.json", document)
    return document


def _separate_output(baseline_dir: Path, output_dir: Path) -> None:
    if not isinstance(baseline_dir, Path) or not isinstance(output_dir, Path):
        raise CensusError("execution directories must be explicit local paths")
    original, target = baseline_dir.resolve(), output_dir.resolve()
    if target.is_relative_to(original) or original.is_relative_to(target):
        raise CensusError("execution output and baseline directories must be disjoint")


def _score_external(
    *,
    output_dir: Path,
    state: dict[str, Any],
    protocol: dict[str, Any],
    census: FrozenSourceCensus,
    store: JsonCensusReceiptStore,
    catalog: SourceFeatureCatalog,
    external: FeatureMatrix,
    external_document_digest: str,
    previous: dict[str, Any],
    page_size: int,
    baseline: BaselineCensus,
    cancel: Callable[[], None] | None,
) -> tuple[dict[str, Any], Counter[str], str]:
    """Score every aligned gene using already frozen private predictors."""
    (output_dir / "external-score/pages").mkdir(parents=True, exist_ok=False)
    _progress(output_dir, state, phase="external_scoring", cancel=cancel)
    pages: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    old_results = {row["gene"]: row for row in previous["genes"]}
    anchors_checked: set[str] = set()
    summary_digest = hashlib.sha256()
    with (output_dir / "summary.csv").open("x", newline="", encoding="utf-8") as stream:
        writer: csv.DictWriter[str] | None = None
        for index, gene in enumerate(catalog.genes):
            if cancel is not None:
                cancel()
            identity = gene.coverage.identity
            record = census.source_gene_record(identity.hgnc_id, store=store)
            evaluated = numerical._external_record(
                record,
                census=census,
                store=store,
                external=external,
                index=index,
                protocol=protocol,
            )
            if identity.symbol in PANEL:
                result = evaluated["result"]
                if result is None or canonical_json_bytes(
                    {"gene": identity.symbol, **result}
                ) != canonical_json_bytes(old_results[identity.symbol]):
                    raise CensusError("complete historical anchor result did not replay")
                anchors_checked.add(identity.symbol)
            counts.update(numerical._count_external_stages([evaluated]))
            records.append(evaluated)
            row = numerical._summary_row(
                evaluated,
                record,
                capacity=gene.count_capacity.all_five_fold_count_support_possible,
            )
            parent._aggregate_only(row)
            if writer is None:
                writer = csv.DictWriter(stream, fieldnames=tuple(row), lineterminator="\n")
                writer.writeheader()
            writer.writerow(row)
            if len(records) == page_size or index + 1 == len(catalog.genes):
                page = numerical._write_external_page(
                    output_dir,
                    records,
                    number=len(pages),
                    protocol=protocol,
                    source_manifest_digest=census.receipt.digest,
                    feature_axis_digest=external.axis.digest,
                    bytes_already_written=sum(item["bytes"] for item in pages),
                )
                baseline.verify_artifact_file(output_dir, page["file_name"])
                pages.append(page)
                if sum(item["bytes"] for item in pages) > MAX_EXTERNAL_BYTES:
                    raise CensusError("external result pages exceed their total byte bound")
                records = []
                stream.flush()
                _progress(
                    output_dir,
                    state,
                    cancel=cancel,
                    external_genes_processed=index + 1,
                    external_evaluator_attempted=counts["external_evaluator_attempted"],
                    external_accepted=counts["external_result_accepted"],
                )
    summary_digest.update((output_dir / "summary.csv").read_bytes())
    if anchors_checked != set(PANEL):
        raise CensusError("external scoring did not retain every historical anchor")
    external_manifest = {
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_manifest_digest": census.receipt.digest,
        "external_document_digest": external_document_digest,
        "feature_axis_digest": external.axis.digest,
        "total_genes": len(catalog.genes),
        "pages": pages,
        "stage_counts": dict(counts),
        "complete": True,
        "all_sixteen_original_results_replayed": True,
        "redistribution_status": "local_only_terms_unverified",
    }
    external_manifest["manifest_digest"] = sha256_digest(external_manifest)
    if len(canonical_json_bytes(external_manifest)) > MAX_MANIFEST_BYTES:
        raise CensusError("external score manifest exceeds its byte bound")
    numerical._seal_external_manifest(output_dir, external_manifest, external)
    return external_manifest, counts, "sha256:" + summary_digest.hexdigest()


def evaluate(  # noqa: PLR0915 - Preserve the inherited, explicitly ordered phase orchestration.
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
    baseline_dir: Path,
    baseline_protocol_lock: SourceLock,
    baseline_evaluation_lock: SourceLock,
    output_dir: Path,
    page_size: int = DEFAULT_PAGE_SIZE,
    cancel: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Attempt every gene, seal source evidence, then score identical external rows."""
    _separate_output(baseline_dir, output_dir)
    if cancel is not None:
        cancel()
    baseline = load_baseline_census(
        directory=baseline_dir,
        protocol_lock=baseline_protocol_lock,
        evaluation_lock=baseline_evaluation_lock,
    )
    previous = historical.load_parent_report(parent_report_path, lock=parent_report_lock)
    source_plan, external_plan, separation = admission._admit_metadata(
        discovery=discovery,
        confirmatory=confirmatory,
        discovery_map_bindings_path=discovery_map_bindings_path,
        discovery_map_bindings_sha256=discovery_map_bindings_sha256,
        processing_evidence_path=processing_evidence_path,
        processing_evidence_sha256=processing_evidence_sha256,
    )
    input_protocol = parent.frozen_protocol(
        discovery=discovery,
        confirmatory=confirmatory,
        discovery_map_bindings_sha256=discovery_map_bindings_sha256,
        processing_evidence_sha256=processing_evidence_sha256,
    )
    folds = deterministic_patient_folds(
        tuple(row.case_submitter_id for row in source_plan.candidates)
    )
    feature_protocol = admission.frozen_protocol(
        source_input_protocol=input_protocol,
        source_fold_assignment_digest=sha256_digest(tuple(int(value) for value in folds)),
    )
    protocol = numerical.frozen_protocol(
        feature_space_protocol=feature_protocol,
        parent_report_lock=parent_report_lock,
        parent_report_digest=previous["report_digest"],
        page_size=page_size,
    )
    execution_protocol = frozen_protocol(numerical_protocol=protocol, baseline=baseline)
    if cancel is not None:
        cancel()
    output_dir.mkdir(parents=True, exist_ok=False)
    admission._write_json(output_dir / "execution-protocol.json", execution_protocol)
    admission._write_json(output_dir / "protocol.json", protocol)
    state: dict[str, Any] = {
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "phase": "source_admission",
        "total_genes": 0,
        "source_attempted": 0,
        "source_accepted": 0,
        "source_abstained": 0,
        "source_input_domain_rejected": 0,
        "external_genes_processed": 0,
        "external_evaluator_attempted": 0,
        "external_accepted": 0,
        "external_measurements_read": False,
        "complete": False,
    }
    _progress(output_dir, state, cancel=cancel)
    hgnc = read_locked_hgnc(hgnc_path)
    source_protein = discovery_module.admit_discovery_protein(
        protein_path=discovery.protein_path,
        sample_map_path=discovery.sample_map_path,
        hgnc_path=hgnc_path,
        candidate_aliquots=source_plan.protein_aliquots,
    )
    universe = derive_source_axis(protein=source_protein, hgnc=hgnc)
    source = build_cohort_matrix(
        axis=universe.axis,
        protein=source_protein,
        plan=source_plan,
        files_manifest_path=discovery.files_manifest_path,
        hgnc=hgnc,
    )
    catalog = build_source_catalog(source.matrix, folds)
    numerical._check_coverage(catalog, source.receipt, previous, "source")
    source_document = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_universe_receipt": asdict(universe.receipt),
        "source_build_receipt": asdict(source.receipt),
        "source_catalog": asdict(catalog),
        "catalog_digest": catalog.digest,
        "external_measurements_read": False,
        "redistribution_status": "local_only_terms_unverified",
    }
    source_document["source_document_digest"] = sha256_digest(source_document)
    admission._write_json(
        output_dir / "source-catalog.json",
        source_document,
        catalog=catalog,
        axis=universe.axis,
        build_receipts=(source.receipt,),
    )
    store = JsonCensusReceiptStore(output_dir / "source-fit")
    _progress(
        output_dir,
        state,
        phase="source_fitting",
        total_genes=len(universe.axis.identities),
        cancel=cancel,
    )

    def checkpoint(binding: ReceiptPageBinding) -> None:
        page = store.read_page(binding)
        accepted = sum(row.source is not None and row.source.accepted for row in page.genes)
        rejected = sum(row.source is None for row in page.genes)
        _progress(
            output_dir,
            state,
            cancel=cancel,
            source_attempted=state["source_attempted"] + len(page.genes),
            source_accepted=state["source_accepted"] + accepted,
            source_abstained=state["source_abstained"] + len(page.genes) - accepted - rejected,
            source_input_domain_rejected=state["source_input_domain_rejected"] + rejected,
        )

    census = fit_source_census(
        source.matrix,
        folds,
        catalog=catalog,
        request_digest=protocol["protocol_digest"],
        store=store,
        page_size=page_size,
        checkpoint=checkpoint,
        cancel=cancel,
    )
    numerical._check_anchor_sources(census, store, catalog, previous)
    cross_table = numerical._source_cross_table(census, store, catalog)
    source_checks = {
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_manifest_binding": asdict(census.binding),
        "source_manifest_digest": census.receipt.digest,
        "source_document_digest": source_document["source_document_digest"],
        "parent_report_digest": previous["report_digest"],
        "all_sixteen_original_source_receipts_replayed": True,
        "capacity_fit_cross_table": cross_table,
        "external_measurements_read": False,
    }
    source_checks["checks_digest"] = sha256_digest(source_checks)
    admission._write_json(output_dir / "source-checks.json", source_checks)
    baseline.verify_source_phase(output_dir)
    if cancel is not None:
        cancel()
    source_build = source.receipt
    del source, source_protein
    _progress(
        output_dir,
        state,
        phase="external_admission",
        external_measurements_read=True,
        cancel=cancel,
    )
    external_protein = protein.admit_confirmatory_protein(
        protein_path=confirmatory.protein_path,
        sample_map_path=confirmatory.sample_map_path,
        hgnc_path=hgnc_path,
        candidate_aliquots=external_plan.protein_aliquots,
    )
    external = build_cohort_matrix(
        axis=universe.axis,
        protein=external_protein,
        plan=external_plan,
        files_manifest_path=confirmatory.files_manifest_path,
        hgnc=hgnc,
    )
    projected = project_external_coverage(catalog, external.matrix)
    numerical._check_coverage(projected, external.receipt, previous, "external")
    external_document = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_catalog_digest": catalog.digest,
        "source_document_digest": source_document["source_document_digest"],
        "source_manifest_digest": census.receipt.digest,
        "external_build_receipt": asdict(external.receipt),
        "external_catalog": asdict(projected),
        "external_catalog_digest": projected.digest,
        "redistribution_status": "local_only_terms_unverified",
    }
    external_document["external_document_digest"] = sha256_digest(external_document)
    admission._write_json(
        output_dir / "external-coverage.json",
        external_document,
        catalog=projected,
        axis=universe.axis,
        build_receipts=(external.receipt,),
    )
    external_manifest, counts, summary_sha256 = _score_external(
        output_dir=output_dir,
        state=state,
        protocol=protocol,
        census=census,
        store=store,
        catalog=catalog,
        external=external.matrix,
        external_document_digest=external_document["external_document_digest"],
        previous=previous,
        page_size=page_size,
        baseline=baseline,
        cancel=cancel,
    )
    report = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "parent_report_digest": previous["report_digest"],
        "source_document_digest": source_document["source_document_digest"],
        "external_document_digest": external_document["external_document_digest"],
        "source_manifest_binding": asdict(census.binding),
        "source_manifest_digest": census.receipt.digest,
        "external_manifest_digest": external_manifest["manifest_digest"],
        "summary_sha256": summary_sha256,
        "feature_axis_digest": universe.axis.digest,
        "source_feature_count": len(catalog.genes),
        "source_case_count": catalog.source_case_count,
        "external_case_count": projected.external_case_count,
        "source_accepted_genes": census.receipt.accepted_genes,
        "source_abstained_genes": census.receipt.abstained_genes,
        "source_input_domain_rejected_genes": census.receipt.input_domain_rejected_genes,
        "capacity_fit_cross_table": cross_table,
        "external_stage_counts": dict(counts),
        "source_build_receipt": asdict(source_build),
        "external_build_receipt": asdict(external.receipt),
        "metadata_separation": asdict(separation),
        "all_genes_attempted": True,
        "all_genes_retained": True,
        "all_original_source_receipts_and_external_results_replayed": True,
        "source_manifest_sealed_before_external_measurement_reads": True,
        "model_fits_performed": True,
        "prediction_scoring_performed": True,
        "post_hoc": True,
        **dict.fromkeys(_FALSE_FLAGS, False),
        "redistribution_status": "local_only_terms_unverified",
        "limitations": (
            "Numerical acceptance describes the unchanged reconstruction algorithm; "
            "no biomarker, mechanistic, causal or clinical discovery follows.",
            "Different genes have different complete-case patients and target scales; "
            "genes times cases is not an independent sample size.",
            "Source family selection uses OOF reconstruction loss; its winning selection "
            "criterion is not an unbiased estimate of that selected winner's performance.",
            "Conditional external intervals omit source fitting/selection uncertainty "
            "and do not establish nominal or simultaneous coverage.",
            "Provider processing, reference materials, molecular eligibility "
            "and genetic donor independence remain separately unproved.",
        ),
    }
    report["report_digest"] = sha256_digest(report)
    admission._write_json(
        output_dir / "evaluation.json", report, build_receipts=(source_build, external.receipt)
    )
    _progress(output_dir, state, phase="complete", complete=True, cancel=cancel)
    execution = _execution_seal(
        output_dir, baseline=baseline, protocol=execution_protocol, report=report
    )
    return {
        **execution,
        **{
            key: report[key]
            for key in (
                "parent_report_digest",
                "source_feature_count",
                "source_accepted_genes",
                "source_abstained_genes",
                "source_input_domain_rejected_genes",
                "external_stage_counts",
                "all_genes_retained",
                "redistribution_status",
            )
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for prefix in ("source", "external"):
        for name in ("choices", "files-manifest", "protein", "sample-map"):
            parser.add_argument(f"--{prefix}-{name}", required=True, type=Path)
        for name in ("choices-sha256", "files-manifest-sha256"):
            parser.add_argument(f"--{prefix}-{name}", required=True)
    parser.add_argument("--hgnc", type=Path, required=True)
    parser.add_argument("--source-map-bindings", type=Path, required=True)
    parser.add_argument("--source-map-bindings-sha256", required=True)
    parser.add_argument("--processing-evidence", type=Path, required=True)
    parser.add_argument("--processing-evidence-sha256", required=True)
    parser.add_argument("--parent-report", type=Path, required=True)
    parser.add_argument("--parent-report-bytes", type=int, required=True)
    parser.add_argument("--parent-report-md5", required=True)
    parser.add_argument("--parent-report-sha256", required=True)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    for prefix in ("baseline-protocol", "baseline-evaluation"):
        parser.add_argument(f"--{prefix}-bytes", type=int, required=True)
        parser.add_argument(f"--{prefix}-md5", required=True)
        parser.add_argument(f"--{prefix}-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
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
        result = evaluate(
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
            baseline_dir=args.baseline_dir,
            baseline_protocol_lock=SourceLock(
                args.baseline_protocol_bytes,
                args.baseline_protocol_md5,
                args.baseline_protocol_sha256,
            ),
            baseline_evaluation_lock=SourceLock(
                args.baseline_evaluation_bytes,
                args.baseline_evaluation_md5,
                args.baseline_evaluation_sha256,
            ),
            output_dir=args.output,
            page_size=args.page_size,
        )
    except Exception:  # noqa: BLE001 - CLI errors must not disclose private execution context.
        print(
            "Census execution did not complete; retain incomplete local evidence "
            "without treating it as a finished result.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
