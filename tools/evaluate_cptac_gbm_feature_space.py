# ruff: noqa: PLR0913, T201, TRY003
"""Admit a source-defined CPTAC gene universe and project external coverage only."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, fields
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, cast

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import discovery as source_protein
from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_external_admission import protein as external_protein
from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import (
    DistinctCohortReceipt,
    assert_distinct_cohort_plans,
    load_discovery_plan,
)
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL
from glio_proteogen.research.cptac_gbm_external_admission.identity import read_locked_hgnc
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    deterministic_patient_folds,
)
from glio_proteogen.research.cptac_gbm_feature_space.atlas import (
    ASSAY_ORDER,
    PATTERNS,
    ExternalFeatureCoverage,
    GeneCoverage,
    SourceFeatureCatalog,
    SourceGeneFeature,
    build_source_catalog,
    project_external_coverage,
)
from glio_proteogen.research.cptac_gbm_feature_space.cohort import (
    AxisSchemaSummary,
    CohortBuildReceipt,
    SchemaHistogram,
    SchemaHistogramBin,
    build_cohort_matrix,
    derive_source_axis,
)
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    MAX_CASES,
    MAX_CELLS,
    MAX_FEATURES,
    PROFILE_ID,
    STATES,
    FeatureAxis,
    FeatureSpaceError,
    require_digest,
)
from tools import evaluate_cptac_gbm_provider_transfer as parent

EVALUATION_ID: Final = "cptac-gbm-real-source-feature-space-admission/1.0.0"
SOURCE_INPUT_PROTOCOL_DIGEST: Final = (
    "sha256:94b76dada0f8c48aab989500b58e85462f30791508bac161e7216305c6bec588"
)
MAX_JSON_BYTES: Final = 64 * 1024 * 1024
CohortInputs = parent.CohortInputs
_FALSE_FLAGS: Final = (
    "model_fits_performed",
    "prediction_scoring_performed",
    "association_tested",
    "causal_identification",
    "clinical_validation",
    "default_promotion",
    "aligned_external_validation",
    "fit_eligibility_established",
    "transfer_eligibility_established",
    "eligibility_admitted",
    "assay_axes_converted_or_batch_corrected",
    "values_transformed",
    "values_imputed",
    "genes_ranked",
    "nominal_interval_coverage_established",
    "multiplicity_adjusted_discoveries",
    "genetic_donor_independence_proven",
    "reference_material_equivalence_proven",
    "complete_processing_identity_proven",
    "metadata_issuer_authenticated_by_hashes",
    "variation_is_a_gate",
    "selection_uses_external_values",
    "selection_uses_association_outcomes",
    "numerical_rank_or_convergence_established",
    "original_support_gates_lowered",
)
_PRIVATE_FIELDS: Final = frozenset(
    (
        "index",
        "indices",
        "row_index",
        "row_indices",
        "patient_index",
        "patient_indices",
        "folds",
        "fold_memberships",
        "fold_assignments",
        "case_keys",
        "case_ids",
        "measurement_vectors",
        "raw_values",
        "measurements",
        "bootstrap_draws",
    )
)


def frozen_protocol(
    *,
    source_input_protocol: dict[str, Any],
    source_fold_assignment_digest: str,
) -> dict[str, Any]:
    """Freeze the additive admission method using the unchanged source locks."""
    require_digest(source_fold_assignment_digest)
    body = {key: value for key, value in source_input_protocol.items() if key != "protocol_digest"}
    if (
        source_input_protocol.get("protocol_digest") != SOURCE_INPUT_PROTOCOL_DIGEST
        or sha256_digest(body) != SOURCE_INPUT_PROTOCOL_DIGEST
    ):
        raise FeatureSpaceError("feature-space admission requires the exact frozen source bindings")
    root = files("glio_proteogen.research.cptac_gbm_feature_space")
    protocol: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "source_input_protocol": source_input_protocol,
        "source_input_protocol_digest": SOURCE_INPUT_PROTOCOL_DIGEST,
        "source_input_protocol_role": (
            "Historical source locks and helper bindings; "
            "no historical model operation is executed."
        ),
        "source_fold_assignment_digest": source_fold_assignment_digest,
        "method_sources": {
            name: parent._digest(root.joinpath(name).read_bytes())
            for name in ("__init__.py", "contracts.py", "assays.py", "cohort.py", "atlas.py")
        },
        "tool_source_digest": parent._digest(Path(__file__).read_bytes()),
        "method_document_digest": parent._digest(
            Path(__file__)
            .resolve()
            .parent.parent.joinpath("docs", "research", "cptac-gbm-feature-space.md")
            .read_bytes()
        ),
        "source_axis_rule": (
            "Exact approved discovery-protein HGNC identities union all sixteen literature "
            "anchors; unique HGNC ID, lexicographic HGNC-ID order."
        ),
        "literature_anchors": PANEL,
        "source_catalog_persisted_before_external_measurement_reads": True,
        "external_axis_expansion_allowed": False,
        "state_order": STATES,
        "pattern_order_cnv_rna_protein": PATTERNS,
        "assay_order": ASSAY_ORDER,
        "source_count_capacity": {
            "joint_complete": 60,
            "minimum_validation_joint": 3,
            "minimum_outer_training_joint": 48,
            "minimum_inner_training_joint": 32,
            "all_five_original_folds_required": True,
            "ordered_inner_training_contexts": 20,
            "establishes_fitted_eligibility": False,
        },
        "source_variation_diagnostics": {
            "training_contexts": 26,
            "minimum_distinct_finite_values": 2,
            "gate": False,
            "establishes_numerical_rank": False,
        },
        "external_joint_complete_descriptive_minimum": 48,
        "maximum_features": MAX_FEATURES,
        "maximum_cases": MAX_CASES,
        "maximum_gene_case_cells": MAX_CELLS,
        "maximum_json_bytes": MAX_JSON_BYTES,
        "aggregate_structural_sequence_policy": (
            "Typed axis-bound gene records and verified-file histogram bins are checked "
            "record by record; patient arrays remain forbidden."
        ),
        **dict.fromkeys(_FALSE_FLAGS, False),
        "redistribution_status": "local_only_terms_unverified",
    }
    protocol["protocol_digest"] = sha256_digest(protocol)
    return protocol


def _extra_guard(value: object) -> None:
    if isinstance(value, dict):
        if _PRIVATE_FIELDS.intersection(value) or (
            "draws" in value and type(value["draws"]) is not str
        ):
            raise FeatureSpaceError("individual measurements or memberships cannot be exported")
        for item in value.values():
            _extra_guard(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _extra_guard(item)


def _catalog_records(
    payload: dict[str, Any],
    catalog: SourceFeatureCatalog | ExternalFeatureCoverage,
    axis: FeatureAxis,
) -> tuple[dict[str, Any], ...]:
    if (
        not isinstance(axis, FeatureAxis)
        or not isinstance(catalog, (SourceFeatureCatalog, ExternalFeatureCoverage))
        or type(catalog.genes) is not tuple
        or any(
            not isinstance(
                row,
                SourceGeneFeature if isinstance(catalog, SourceFeatureCatalog) else GeneCoverage,
            )
            for row in catalog.genes
        )
    ):
        raise FeatureSpaceError("catalog export requires typed aggregate gene records")
    source = isinstance(catalog, SourceFeatureCatalog)
    identities = (
        tuple(row.coverage.identity for row in catalog.genes)
        if isinstance(catalog, SourceFeatureCatalog)
        else tuple(row.identity for row in catalog.genes)
    )
    if catalog.feature_axis_digest != axis.digest or identities != axis.identities:
        raise FeatureSpaceError("exported catalog does not match the admitted feature axis")
    key = "source_catalog" if source else "external_catalog"
    expected = asdict(catalog)
    if payload.get(key) != expected or not 1 <= len(identities) <= MAX_FEATURES:
        raise FeatureSpaceError("exported catalog differs from its typed aggregate")
    return cast("tuple[dict[str, Any], ...]", payload[key]["genes"])


def _histogram_records(payload: dict[str, Any], receipt: CohortBuildReceipt) -> list[Any]:
    if not isinstance(receipt, CohortBuildReceipt):
        raise FeatureSpaceError("aggregate schema histograms require a typed cohort receipt")
    for summary in receipt.schema_summaries:
        if (
            not isinstance(summary, AxisSchemaSummary)
            or type(summary.verified_files) is not int
            or not 1 <= summary.verified_files <= MAX_CASES
        ):
            raise FeatureSpaceError("aggregate schema histograms require a typed file summary")
        for histogram in summary.histograms:
            if (
                not isinstance(histogram, SchemaHistogram)
                or type(histogram.bins) is not tuple
                or not 1 <= len(histogram.bins) <= summary.verified_files
                or any(
                    not isinstance(item, SchemaHistogramBin)
                    or type(item.value) is not int
                    or item.value < 0
                    or type(item.files) is not int
                    or item.files < 1
                    for item in histogram.bins
                )
                or sum(item.files for item in histogram.bins) != summary.verified_files
            ):
                raise FeatureSpaceError(
                    "aggregate schema histogram does not conserve verified files"
                )
    expected = asdict(receipt)
    matches = [
        payload[key]
        for key in ("source_build_receipt", "external_build_receipt")
        if payload.get(key) == expected
    ]
    if len(matches) != 1:
        raise FeatureSpaceError("exported cohort receipt differs from its typed aggregate")
    return [
        histogram["bins"]
        for summary in matches[0]["schema_summaries"]
        for histogram in summary["histograms"]
    ]


def _mask_sequences(value: object, allowed: set[int]) -> object:
    if id(value) in allowed:
        return []
    if isinstance(value, dict):
        return {key: _mask_sequences(item, allowed) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_mask_sequences(item, allowed) for item in value]
    return value


def _write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    catalog: SourceFeatureCatalog | ExternalFeatureCoverage | None = None,
    axis: FeatureAxis | None = None,
    build_receipts: tuple[CohortBuildReceipt, ...] = (),
) -> None:
    """Bound canonical exports; typed aggregate records never permit patient vectors."""
    structural: list[Any] = []
    if catalog is not None:
        if axis is None:
            raise FeatureSpaceError("catalog export requires its admitted feature axis")
        structural.append(_catalog_records(payload, catalog, axis))
    for receipt in build_receipts:
        structural.extend(_histogram_records(payload, receipt))
    _extra_guard(payload)
    parent._aggregate_only(_mask_sequences(payload, {id(item) for item in structural}))
    for sequence in structural:
        for record in sequence:
            parent._aggregate_only(record)
    encoded = canonical_json_bytes(payload)
    if len(encoded) > MAX_JSON_BYTES:
        raise FeatureSpaceError("canonical aggregate JSON exceeds the bounded export size")
    with path.open("xb") as stream:
        stream.write(encoded)


def _coverage_columns(prefix: str, coverage: GeneCoverage) -> dict[str, Any]:
    row = {
        f"{prefix}_{item.name}": getattr(coverage, item.name)
        for item in fields(GeneCoverage)
        if item.name
        not in (
            "identity",
            "pattern_counts_cnv_rna_protein",
            "cnv_state_counts",
            "rna_state_counts",
            "protein_state_counts",
        )
    }
    row.update(
        {
            f"{prefix}_pattern_{pattern}": count
            for pattern, count in zip(
                PATTERNS, coverage.pattern_counts_cnv_rna_protein, strict=True
            )
        }
    )
    for assay in ("cnv", "rna", "protein"):
        row.update(
            {
                f"{prefix}_{assay}_{state}": count
                for state, count in zip(
                    STATES, getattr(coverage, f"{assay}_state_counts"), strict=True
                )
            }
        )
    return row


def _summary_rows(
    source: SourceFeatureCatalog,
    external: ExternalFeatureCoverage,
) -> tuple[dict[str, Any], ...]:
    rows = []
    for feature, coverage in zip(source.genes, external.genes, strict=True):
        if feature.coverage.identity != coverage.identity:
            raise FeatureSpaceError("summary gene identities differ between catalogs")
        capacity = feature.count_capacity
        rows.append(
            {
                **asdict(coverage.identity),
                **_coverage_columns("source", feature.coverage),
                **_coverage_columns("external", coverage),
                **{
                    f"source_fold_{fold}_joint": count
                    for fold, count in enumerate(capacity.fold_joint_counts)
                },
                "source_minimum_validation_joint": capacity.minimum_validation_joint,
                "source_minimum_outer_training_joint": capacity.minimum_outer_training_joint,
                "source_minimum_inner_training_joint": capacity.minimum_inner_training_joint,
                "source_all_five_fold_count_support_possible": (
                    capacity.all_five_fold_count_support_possible
                ),
                **{
                    f"source_{key}": value
                    for key, value in asdict(feature.training_variation).items()
                },
                "external_joint_count_at_least_48": coverage.joint_complete
                >= external.external_joint_minimum,
                "both_cohort_count_sufficient": capacity.all_five_fold_count_support_possible
                and coverage.joint_complete >= external.external_joint_minimum,
            }
        )
    return tuple(rows)


def _write_summary(
    path: Path, source: SourceFeatureCatalog, external: ExternalFeatureCoverage
) -> None:
    rows = _summary_rows(source, external)
    for row in rows:
        _extra_guard(row)
        parent._aggregate_only(row)
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _admit_metadata(
    *,
    discovery: CohortInputs,
    confirmatory: CohortInputs,
    discovery_map_bindings_path: Path,
    discovery_map_bindings_sha256: str,
    processing_evidence_path: Path,
    processing_evidence_sha256: str,
) -> tuple[metadata.ExternalAdmissionPlan, metadata.ExternalAdmissionPlan, DistinctCohortReceipt]:
    source = load_discovery_plan(
        choices_path=discovery.choices_path,
        choices_sha256=discovery.choices_sha256,
        map_bindings_path=discovery_map_bindings_path,
        map_bindings_sha256=discovery_map_bindings_sha256,
        files_manifest_path=discovery.files_manifest_path,
        files_manifest_sha256=discovery.files_manifest_sha256,
    )
    external = metadata.load_admission_plan(
        choices_path=confirmatory.choices_path,
        choices_sha256=confirmatory.choices_sha256,
        files_manifest_path=confirmatory.files_manifest_path,
        files_manifest_sha256=confirmatory.files_manifest_sha256,
    )
    separation = assert_distinct_cohort_plans(source, external)
    parent._processing_boundary(
        processing_evidence_path,
        processing_evidence_sha256,
        discovery_choices_sha256=discovery.choices_sha256,
        confirmatory_choices_sha256=confirmatory.choices_sha256,
        selected_file_set_digest=sha256_digest(sorted((*source.files, *external.files))),
    )
    return source, external, separation


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
    """Persist the whole source catalog before projecting unchanged external axes."""
    source_plan, external_plan, separation = _admit_metadata(
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
    protocol = frozen_protocol(
        source_input_protocol=input_protocol,
        source_fold_assignment_digest=sha256_digest(tuple(int(value) for value in folds)),
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "protocol.json", protocol)
    hgnc = read_locked_hgnc(hgnc_path)
    protein = source_protein.admit_discovery_protein(
        protein_path=discovery.protein_path,
        sample_map_path=discovery.sample_map_path,
        hgnc_path=hgnc_path,
        candidate_aliquots=source_plan.protein_aliquots,
    )
    universe = derive_source_axis(protein=protein, hgnc=hgnc)
    if not set(PANEL).issubset({identity.symbol for identity in universe.axis.identities}):
        raise FeatureSpaceError("source axis must retain all sixteen literature anchors")
    source = build_cohort_matrix(
        axis=universe.axis,
        protein=protein,
        plan=source_plan,
        files_manifest_path=discovery.files_manifest_path,
        hgnc=hgnc,
    )
    catalog = build_source_catalog(source.matrix, folds)
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
    _write_json(
        output_dir / "source-catalog.json",
        source_document,
        catalog=catalog,
        axis=universe.axis,
        build_receipts=(source.receipt,),
    )
    external_admission = external_protein.admit_confirmatory_protein(
        protein_path=confirmatory.protein_path,
        sample_map_path=confirmatory.sample_map_path,
        hgnc_path=hgnc_path,
        candidate_aliquots=external_plan.protein_aliquots,
    )
    external = build_cohort_matrix(
        axis=universe.axis,
        protein=external_admission,
        plan=external_plan,
        files_manifest_path=confirmatory.files_manifest_path,
        hgnc=hgnc,
    )
    projected = project_external_coverage(catalog, external.matrix)
    external_document = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_catalog_digest": catalog.digest,
        "source_document_digest": source_document["source_document_digest"],
        "external_build_receipt": asdict(external.receipt),
        "external_catalog": asdict(projected),
        "external_catalog_digest": projected.digest,
        "redistribution_status": "local_only_terms_unverified",
    }
    external_document["external_document_digest"] = sha256_digest(external_document)
    _write_json(
        output_dir / "external-coverage.json",
        external_document,
        catalog=projected,
        axis=universe.axis,
        build_receipts=(external.receipt,),
    )
    report = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_document_digest": source_document["source_document_digest"],
        "external_document_digest": external_document["external_document_digest"],
        "source_catalog_digest": catalog.digest,
        "external_catalog_digest": projected.digest,
        "source_build_digest": sha256_digest(asdict(source.receipt)),
        "external_build_digest": sha256_digest(asdict(external.receipt)),
        "source_universe_receipt": asdict(universe.receipt),
        "metadata_separation": asdict(separation),
        "source_metadata": asdict(source_plan.receipt),
        "external_metadata": asdict(external_plan.receipt),
        "source_build_receipt": asdict(source.receipt),
        "external_build_receipt": asdict(external.receipt),
        "feature_axis_digest": universe.axis.digest,
        "source_feature_count": len(universe.axis.identities),
        "literature_anchor_count": len(PANEL),
        "all_literature_anchors_retained": True,
        "unresolved_source_protein_rows": universe.receipt.unresolved_source_protein_rows,
        "source_case_count": catalog.source_case_count,
        "external_case_count": projected.external_case_count,
        "source_count_capacity_genes": catalog.count_supported_genes,
        "external_count_sufficient_genes": projected.external_count_sufficient_genes,
        "source_and_external_count_sufficient_genes": (
            projected.source_and_external_count_sufficient_genes
        ),
        "state_order": STATES,
        "pattern_order_cnv_rna_protein": PATTERNS,
        "assay_order": ASSAY_ORDER,
        "pattern_semantics": (
            "Bits CNV,RNA,protein; 1 means observed finite value, including zero. "
            "All eight patterns are retained."
        ),
        "count_capacity_is_fit_eligibility": False,
        "measurement_bytes_reverified": True,
        "source_catalog_persisted_before_external_measurement_reads": True,
        **dict.fromkeys(_FALSE_FLAGS, False),
        "limitations": (
            (
                "Count capacity and distinct-value diagnostics establish no numerical fit, "
                "power, association, biological mechanism or biomarker discovery."
            ),
            (
                "External coverage is projected onto the unchanged source axis; "
                "it cannot admit genes or alter source counts."
            ),
            (
                "Historical raw provider coordinates and reference pools remain distinct; "
                "no aligned external validation or contemporary molecular eligibility "
                "is established."
            ),
            (
                "Source hashes bind local integrity and asserted provenance; "
                "issuer authentication, "
                "donor independence and redistribution permission remain unproved."
            ),
            (
                "This admission-only profile changes no historical fitting profile, threshold, "
                "point result or abstention."
            ),
        ),
        "redistribution_status": "local_only_terms_unverified",
    }
    report["report_digest"] = sha256_digest(report)
    _write_json(
        output_dir / "evaluation.json", report, build_receipts=(source.receipt, external.receipt)
    )
    _write_summary(output_dir / "summary.csv", catalog, projected)
    return {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "report_digest": report["report_digest"],
        "source_feature_count": len(universe.axis.identities),
        "source_count_capacity_genes": catalog.count_supported_genes,
        "external_count_sufficient_genes": projected.external_count_sufficient_genes,
        "source_and_external_count_sufficient_genes": (
            projected.source_and_external_count_sufficient_genes
        ),
        "verified_assay_files": len(source_plan.files) + len(external_plan.files),
        "model_fits_performed": False,
        "aligned_external_validation": False,
        "redistribution_status": "local_only_terms_unverified",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for prefix in ("source", "external"):
        for name in ("choices", "files-manifest", "protein", "sample-map"):
            parser.add_argument(f"--{prefix}-{name}", required=True, type=Path)
        for name in ("choices-sha256", "files-manifest-sha256"):
            parser.add_argument(f"--{prefix}-{name}", required=True)
    for name in ("source-map-bindings", "hgnc", "processing-evidence", "output-dir"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    for name in ("source-map-bindings-sha256", "processing-evidence-sha256"):
        parser.add_argument(f"--{name}", required=True)
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
            "Feature-space admission failed; private inputs or frozen contracts "
            "were not satisfied.\n",
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
