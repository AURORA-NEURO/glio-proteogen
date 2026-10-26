# ruff: noqa: PLR0913, T201, TRY003
"""Run every source-defined gene through the unchanged source-only fitter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

import numpy as np

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import discovery as discovery_module
from glio_proteogen.research.cptac_gbm_external_admission import protein
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    SourceLock,
)
from glio_proteogen.research.cptac_gbm_external_admission.identity import read_locked_hgnc
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_REQUIRED,
    EXTERNAL_MINIMUM,
    TransferGeneResult,
    deterministic_patient_folds,
    evaluate_external_gene,
)
from glio_proteogen.research.cptac_gbm_feature_space.atlas import (
    ExternalFeatureCoverage,
    SourceFeatureCatalog,
    build_source_catalog,
    project_external_coverage,
)
from glio_proteogen.research.cptac_gbm_feature_space.cohort import (
    CohortBuildReceipt,
    build_cohort_matrix,
    derive_source_axis,
)
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    MAX_CASES,
    MAX_CELLS,
    MAX_FEATURES,
    FeatureMatrix,
)
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    PROFILE_ID as FEATURE_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.contracts import (
    DEFAULT_PAGE_SIZE,
    MAX_MANIFEST_BYTES,
    MAX_PAGE_BYTES,
    MAX_PAGE_SIZE,
    MAX_SOURCE_BYTES,
    PROFILE_ID,
    CensusError,
    ReceiptPageBinding,
    SourceGeneReceipt,
    require_digest,
    require_integer,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.engine import (
    FrozenSourceCensus,
    fit_source_census,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.storage import JsonCensusReceiptStore
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.nested_selection import (
    ITERATION_BUDGET,
    MAX_ABSOLUTE_INPUT,
)
from tools import evaluate_cptac_gbm_feature_space as admission
from tools import evaluate_cptac_gbm_provider_transfer as parent
from tools import evaluate_cptac_gbm_transfer_sensitivity as historical

EVALUATION_ID: Final = "cptac-gbm-real-gene-wide-source-fit-census/1.0.0"
MAX_EXTERNAL_BYTES: Final = MAX_SOURCE_BYTES
EXTERNAL_DOMAIN_REJECTION: Final = (
    "external finite inputs exceed the frozen scoring magnitude domain"
)
CohortInputs = parent.CohortInputs
_FALSE_FLAGS: Final = (
    "capacity_flag_filters_fits",
    "variation_diagnostic_filters_fits",
    "genes_ranked",
    "association_tested",
    "multiplicity_adjusted_discoveries",
    "causal_identification",
    "clinical_validation",
    "aligned_external_validation",
    "default_promotion",
    "nominal_interval_coverage_established",
    "simultaneous_gene_inference_established",
    "source_patient_refit_bootstrap_performed",
    "values_imputed",
    "values_transformed",
    "genetic_donor_independence_proven",
    "reference_material_equivalence_proven",
    "assay_axes_converted_or_batch_corrected",
    "count_capacity_is_fit_eligibility",
)


def frozen_protocol(
    *,
    feature_space_protocol: dict[str, Any],
    parent_report_lock: SourceLock,
    parent_report_digest: str,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Freeze algorithm, source locks and prior-panel replay before real fitting."""
    require_integer(page_size, minimum=1, maximum=MAX_PAGE_SIZE)
    require_digest(parent_report_digest)
    body = {key: value for key, value in feature_space_protocol.items() if key != "protocol_digest"}
    expected_admission = admission.frozen_protocol(
        source_input_protocol=feature_space_protocol["source_input_protocol"],
        source_fold_assignment_digest=feature_space_protocol["source_fold_assignment_digest"],
    )
    if (
        feature_space_protocol.get("profile_id") != FEATURE_PROFILE_ID
        or sha256_digest(body) != feature_space_protocol.get("protocol_digest")
        or canonical_json_bytes(feature_space_protocol) != canonical_json_bytes(expected_admission)
        or feature_space_protocol.get("source_input_protocol_digest")
        != admission.SOURCE_INPUT_PROTOCOL_DIGEST
        or type(parent_report_lock) is not SourceLock
        or parent_report_lock.bytes > historical.PARENT_REPORT_MAX_BYTES
    ):
        raise CensusError(
            "census protocol requires frozen admission and historical replay bindings"
        )
    root = files("glio_proteogen.research.cptac_gbm_source_fit_census")
    document: dict[str, Any] = {
        "evaluation_id": EVALUATION_ID,
        "profile_id": PROFILE_ID,
        "feature_space_protocol": feature_space_protocol,
        "feature_space_protocol_digest": feature_space_protocol["protocol_digest"],
        "source_fold_assignment_digest": feature_space_protocol["source_fold_assignment_digest"],
        "parent_report_lock": asdict(parent_report_lock),
        "parent_report_digest": parent_report_digest,
        "method_sources": {
            name: parent._digest(root.joinpath(name).read_bytes())
            for name in ("__init__.py", "contracts.py", "storage.py", "engine.py")
        },
        "tool_source_digest": parent._digest(Path(__file__).read_bytes()),
        "historical_report_reader_source_digest": parent._digest(
            Path(historical.__file__).read_bytes()
        ),
        "method_document_digest": parent._digest(
            Path(__file__)
            .resolve()
            .parent.parent.joinpath("docs/research/cptac-gbm-source-fit-census.md")
            .read_bytes()
        ),
        "gene_universe": (
            "Every identity on the unchanged source-defined HGNC axis, in canonical HGNC order."
        ),
        "every_gene_reaches_original_source_fitter": True,
        "source_fit_implementation": (
            "unchanged fit_source_gene; original child profile IDs and all receipt fields retained"
        ),
        "fitter_internal_standardization": (
            "Unchanged training-only centering and scaling inside the frozen fitter; "
            "provider assay coordinates receive no additional conversion or alignment."
        ),
        "source_fit_candidate_attempts_maximum_including_median": 104,
        "source_huber_fit_attempts_maximum": 78,
        "source_huber_iteration_budget": ITERATION_BUDGET,
        "fitting_magnitude_bound": MAX_ABSOLUTE_INPUT,
        "workers": 1,
        "source_receipts_sealed_before_external_measurement_reads": True,
        "private_predictors_persisted": False,
        "hydration_refits_source_models": False,
        "crash_restart_requires_complete_source_predictor_replay": True,
        "default_source_page_size": page_size,
        "maximum_page_genes": MAX_PAGE_SIZE,
        "maximum_page_bytes": MAX_PAGE_BYTES,
        "maximum_source_phase_bytes": MAX_SOURCE_BYTES,
        "maximum_external_phase_bytes": MAX_EXTERNAL_BYTES,
        "maximum_manifest_bytes": MAX_MANIFEST_BYTES,
        "maximum_features": MAX_FEATURES,
        "maximum_cases": MAX_CASES,
        "maximum_gene_case_cells": MAX_CELLS,
        "expected_input_domain_rejection_retained": True,
        "unexpected_software_error_stops_incomplete_run": True,
        "parent_source_receipts_and_complete_anchor_results_must_replay": True,
        "anchor_request_digest": (
            "SHA256 canonical {protocol_digest: original provider protocol digest, "
            "gene: approved symbol}"
        ),
        "nonanchor_request_digest": (
            "SHA256 canonical {census_protocol_digest: new protocol digest, "
            "hgnc_id: stable HGNC ID}"
        ),
        "external_bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "required": BOOTSTRAP_REQUIRED,
            "scope": (
                "Within-gene external case sampling conditional on frozen source fits and selection"
            ),
            "source_models_refitted": False,
            "source_selection_repeated": False,
            "simultaneous_genome_wide_interval": False,
        },
        "model_fits_performed": True,
        "prediction_scoring_performed": True,
        "post_hoc": True,
        **dict.fromkeys(_FALSE_FLAGS, False),
        "redistribution_status": "local_only_terms_unverified",
    }
    document["protocol_digest"] = sha256_digest(document)
    return document


def _progress(output: Path, state: dict[str, Any], **changes: object) -> None:
    state.update(changes)
    parent._aggregate_only(state)
    data = canonical_json_bytes(state)
    temporary = output / "progress.json.tmp"
    with temporary.open("xb") as stream:
        stream.write(data)
    temporary.replace(output / "progress.json")


def _check_coverage(
    catalog: SourceFeatureCatalog | ExternalFeatureCoverage,
    receipt: CohortBuildReceipt,
    previous: dict[str, Any],
    cohort: str,
) -> None:
    if canonical_json_bytes(asdict(receipt.source_protein_receipt)) != canonical_json_bytes(
        previous[cohort + "_protein"]
    ):
        raise CensusError("historical protein admission receipt did not replay")
    rows = (
        {row.coverage.identity.symbol: asdict(row.coverage) for row in catalog.genes}
        if isinstance(catalog, SourceFeatureCatalog)
        else {row.identity.symbol: asdict(row) for row in catalog.genes}
    )
    for expected in previous[cohort + "_coverage"]:
        row = rows.get(expected["gene"], {})
        if any(row.get(key) != value for key, value in expected.items() if key != "gene"):
            raise CensusError("historical anchor coverage did not replay")


def _check_anchor_sources(
    census: FrozenSourceCensus,
    store: JsonCensusReceiptStore,
    catalog: SourceFeatureCatalog,
    previous: dict[str, Any],
) -> None:
    by_symbol = {row.coverage.identity.symbol: row.coverage.identity for row in catalog.genes}
    for row in previous["genes"]:
        record = census.source_gene_record(by_symbol[row["gene"]].hgnc_id, store=store)
        if record.source is None or canonical_json_bytes(
            asdict(record.source)
        ) != canonical_json_bytes(row["source"]):
            raise CensusError("full historical anchor source receipt did not replay")


def _source_cross_table(
    census: FrozenSourceCensus,
    store: JsonCensusReceiptStore,
    catalog: SourceFeatureCatalog,
) -> tuple[dict[str, Any], ...]:
    counts: Counter[tuple[bool, str]] = Counter()
    for row in catalog.genes:
        record = census.source_gene_record(row.coverage.identity.hgnc_id, store=store)
        status = (
            "input_domain_rejected"
            if record.source is None
            else ("accepted" if record.source.accepted else "abstained")
        )
        counts[(row.count_capacity.all_five_fold_count_support_possible, status)] += 1
    return tuple(
        {"count_capacity": capacity, "source_status": status, "genes": counts[(capacity, status)]}
        for capacity in (False, True)
        for status in ("accepted", "abstained", "input_domain_rejected")
    )


def _gene_request(identity: GeneIdentity, protocol: dict[str, Any]) -> str:
    if identity.symbol in PANEL:
        return sha256_digest(
            {"protocol_digest": admission.SOURCE_INPUT_PROTOCOL_DIGEST, "gene": identity.symbol}
        )
    return sha256_digest(
        {"census_protocol_digest": protocol["protocol_digest"], "hgnc_id": identity.hgnc_id}
    )


def _external_record(
    record: SourceGeneReceipt,
    *,
    census: FrozenSourceCensus,
    store: JsonCensusReceiptStore,
    external: FeatureMatrix,
    index: int,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    fit = census.hydrate_gene(record.identity.hgnc_id, store=store)
    cnv, rna, target = external.cnv[index], external.rna[index], external.protein[index]
    complete_count = int((np.isfinite(cnv) & np.isfinite(rna) & np.isfinite(target)).sum())
    result: TransferGeneResult | None = None
    rejection = None
    if fit is not None:
        try:
            result = evaluate_external_gene(
                fit, cnv, rna, target, request_digest=_gene_request(record.identity, protocol)
            )
        except ValueError:
            if not any(
                bool(np.any(np.abs(value[np.isfinite(value)]) > MAX_ABSOLUTE_INPUT))
                for value in (cnv, rna, target)
            ):
                raise
            rejection = EXTERNAL_DOMAIN_REJECTION
    if result is not None and (
        type(result) is not TransferGeneResult or result.source != record.source
    ):
        raise CensusError("external scoring changed its frozen source receipt")
    document = {
        "identity": asdict(record.identity),
        "source_record_digest": record.digest,
        "source_input_domain_rejection": record.input_domain_rejection,
        "source_accepted": record.source.accepted if record.source is not None else False,
        "external_evaluator_attempted": fit is not None,
        "external_input_domain_rejection": rejection,
        "external_complete_count": complete_count,
        "external_support_sufficient": complete_count >= EXTERNAL_MINIMUM,
        "point_scores_available": bool(result is not None and result.point_metrics),
        "conditional_intervals_available": result is not None and result.uncertainty is not None,
        "external_result_accepted": result.accepted if result is not None else False,
        "result": asdict(result) if result is not None else None,
    }
    admission._extra_guard(document)
    parent._aggregate_only(document)
    return document


def _write_external_page(
    output: Path,
    records: list[dict[str, Any]],
    *,
    number: int,
    protocol: dict[str, Any],
    source_manifest_digest: str,
    feature_axis_digest: str,
    bytes_already_written: int = 0,
) -> dict[str, Any]:
    require_integer(number, minimum=0, maximum=MAX_FEATURES - 1)
    require_digest(protocol["protocol_digest"])
    require_digest(source_manifest_digest)
    require_digest(feature_axis_digest)
    require_integer(bytes_already_written, minimum=0, maximum=MAX_EXTERNAL_BYTES)
    if not 1 <= len(records) <= MAX_PAGE_SIZE:
        raise CensusError("external result page exceeds its gene bound")
    for record in records:
        admission._extra_guard(record)
        parent._aggregate_only(record)
    document = {
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "source_manifest_digest": source_manifest_digest,
        "feature_axis_digest": feature_axis_digest,
        "page_number": number,
        "genes": records,
        "redistribution_status": "local_only_terms_unverified",
    }
    document["page_digest"] = sha256_digest(document)
    data = canonical_json_bytes(document)
    if len(data) > MAX_PAGE_BYTES or bytes_already_written + len(data) > MAX_EXTERNAL_BYTES:
        raise CensusError("external result page exceeds its byte bound")
    file_name = f"external-score/pages/{number:05d}.json"
    path = output / file_name
    with path.open("xb") as stream:
        stream.write(data)
    return {
        "page_number": number,
        "file_name": file_name,
        "bytes": len(data),
        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "page_digest": document["page_digest"],
        "gene_count": len(records),
        "first_hgnc_id": records[0]["identity"]["hgnc_id"],
        "last_hgnc_id": records[-1]["identity"]["hgnc_id"],
    }


def _summary_row(
    record: dict[str, Any], source_record: SourceGeneReceipt, *, capacity: bool
) -> dict[str, Any]:
    result = record["result"]
    source = asdict(source_record.source) if source_record.source is not None else None
    metrics = (
        {item["candidate"]: item for item in result["point_metrics"]} if result is not None else {}
    )
    uncertainty = result["uncertainty"] if result is not None else None
    nested = source["nested_point_summary"] if source is not None else None
    return {
        **record["identity"],
        "source_all_five_fold_count_support_possible": capacity,
        "source_accepted": record["source_accepted"],
        "source_complete_count": source["complete_count"] if source is not None else None,
        "source_common_oof_count": source["common_oof_count"] if source is not None else None,
        "source_selected_candidate": source["selected_candidate"] if source is not None else None,
        "nested_selected_policy_oof_mae": nested["selected"]["mae"] if nested is not None else None,
        "source_input_domain_rejection": record["source_input_domain_rejection"],
        "source_failure_reason": source["failure_reason"] if source is not None else None,
        **{
            key: record[key]
            for key in (
                "external_evaluator_attempted",
                "external_input_domain_rejection",
                "external_complete_count",
                "external_support_sufficient",
                "point_scores_available",
                "conditional_intervals_available",
                "external_result_accepted",
            )
        },
        "external_failure_reason": result["failure_reason"] if result is not None else None,
        "full_mae": metrics.get("full", {}).get("mae"),
        "cnv_only_mae": metrics.get("cnv_only", {}).get("mae"),
        "selected_policy_mae": metrics.get("selected_policy", {}).get("mae"),
        "full_minus_cnv_mae": result["primary_full_minus_cnv_mae"] if result is not None else None,
        "selected_minus_full_mae": result["secondary_selected_minus_full_mae"]
        if result is not None
        else None,
        "primary_lower90": uncertainty["primary_full_minus_cnv_mae"]["lower"]
        if uncertainty
        else None,
        "primary_upper90": uncertainty["primary_full_minus_cnv_mae"]["upper"]
        if uncertainty
        else None,
    }


def _count_external_stages(records: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        admission._extra_guard(record)
        parent._aggregate_only(record)
        for key in (
            "source_accepted",
            "external_evaluator_attempted",
            "external_support_sufficient",
            "point_scores_available",
            "conditional_intervals_available",
            "external_result_accepted",
        ):
            if type(record[key]) is not bool:
                raise CensusError("external stage indicators must be exact booleans")
            counts[key] += record[key]
        counts["external_input_domain_rejected"] += (
            record["external_input_domain_rejection"] is not None
        )
    return counts


def _read_external_snapshot(path: Path, expected_bytes: int) -> bytes:
    """Read a bounded regular file while detecting replacement and growth."""
    require_integer(expected_bytes, minimum=1, maximum=MAX_PAGE_BYTES)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
        raise CensusError("external page is not the declared bounded regular file")

    def snapshot(value: os.stat_result) -> tuple[int, ...]:
        if not stat.S_ISREG(value.st_mode) or (
            getattr(value, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise CensusError("external page must retain its regular non-link binding")
        return (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            # Windows path/descriptor ctime semantics differ; birth time agrees.
            getattr(value, "st_birthtime_ns", value.st_ctime_ns),
        )

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if snapshot(before) != snapshot(opened):
            raise CensusError("external page changed while opening its snapshot")
        payload = stream.read(expected_bytes + 1)
        after = os.fstat(stream.fileno())
    if (
        len(payload) != expected_bytes
        or snapshot(before) != snapshot(after)
        or opened.st_ctime_ns != after.st_ctime_ns
        or snapshot(before) != snapshot(path.lstat())
    ):
        raise CensusError("external page changed during its bounded read")
    return payload


def _seal_external_manifest(output: Path, manifest: dict[str, Any], matrix: FeatureMatrix) -> None:
    """Recheck exact page bytes, axis partition and conserved stage counts."""
    pages = manifest["pages"]
    if (
        type(pages) is not list
        or not 1 <= len(pages) <= MAX_FEATURES
        or manifest["feature_axis_digest"] != matrix.axis.digest
        or manifest["total_genes"] != len(matrix.axis.identities)
        or manifest["complete"] is not True
        or manifest["profile_id"] != PROFILE_ID
        or manifest["manifest_digest"]
        != sha256_digest(
            {key: value for key, value in manifest.items() if key != "manifest_digest"}
        )
    ):
        raise CensusError("external manifest dimensions do not match its feature axis")
    offset = byte_count = 0
    stage_counts: Counter[str] = Counter()
    for index, raw in enumerate(pages):
        binding = ReceiptPageBinding(**{**raw, "file_name": f"pages/{index:05d}.json"})
        path = output / f"external-score/pages/{index:05d}.json"
        if (
            raw["file_name"] != f"external-score/pages/{index:05d}.json"
            or binding.page_number != index
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != binding.bytes
        ):
            raise CensusError("external page path or file size changed before sealing")
        payload = _read_external_snapshot(path, binding.bytes)
        if "sha256:" + hashlib.sha256(payload).hexdigest() != binding.sha256:
            raise CensusError("external page bytes changed before sealing")
        document = json.loads(payload)
        body = {key: value for key, value in document.items() if key != "page_digest"}
        records = document["genes"]
        if (
            canonical_json_bytes(document) != payload
            or sha256_digest(body) != binding.page_digest
            or document["page_digest"] != binding.page_digest
            or document["profile_id"] != PROFILE_ID
            or document["protocol_digest"] != manifest["protocol_digest"]
            or document["source_manifest_digest"] != manifest["source_manifest_digest"]
            or document["feature_axis_digest"] != matrix.axis.digest
            or document["page_number"] != index
            or type(records) is not list
            or len(records) != binding.gene_count
            or [record["identity"] for record in records]
            != [
                asdict(identity)
                for identity in matrix.axis.identities[offset : offset + len(records)]
            ]
            or records[0]["identity"]["hgnc_id"] != binding.first_hgnc_id
            or records[-1]["identity"]["hgnc_id"] != binding.last_hgnc_id
        ):
            raise CensusError("external page does not retain its bound canonical gene partition")
        stage_counts.update(_count_external_stages(records))
        parent._aggregate_only(raw)
        offset += len(records)
        byte_count += len(payload)
    if (
        offset != len(matrix.axis.identities)
        or byte_count > MAX_EXTERNAL_BYTES
        or dict(stage_counts) != manifest["stage_counts"]
        or {path.name for path in (output / "external-score/pages").iterdir()}
        != {f"{index:05d}.json" for index in range(len(pages))}
    ):
        raise CensusError("external manifest does not conserve all genes, bytes and stage counts")
    admission._extra_guard(manifest)
    parent._aggregate_only({**manifest, "pages": []})
    payload = canonical_json_bytes(manifest)
    if len(payload) > MAX_MANIFEST_BYTES or byte_count + len(payload) > MAX_EXTERNAL_BYTES:
        raise CensusError("external score manifest exceeds its byte bound")
    with (output / "external-score/manifest.json").open("xb") as stream:
        stream.write(payload)


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
) -> tuple[dict[str, Any], Counter[str], str]:
    """Score every aligned gene using already frozen private predictors."""
    (output_dir / "external-score/pages").mkdir(parents=True, exist_ok=False)
    _progress(output_dir, state, phase="external_scoring")
    pages: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    old_results = {row["gene"]: row for row in previous["genes"]}
    anchors_checked: set[str] = set()
    summary_digest = hashlib.sha256()
    with (output_dir / "summary.csv").open("x", newline="", encoding="utf-8") as stream:
        writer: csv.DictWriter[str] | None = None
        for index, gene in enumerate(catalog.genes):
            identity = gene.coverage.identity
            record = census.source_gene_record(identity.hgnc_id, store=store)
            evaluated = _external_record(
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
            counts.update(_count_external_stages([evaluated]))
            records.append(evaluated)
            row = _summary_row(
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
                page = _write_external_page(
                    output_dir,
                    records,
                    number=len(pages),
                    protocol=protocol,
                    source_manifest_digest=census.receipt.digest,
                    feature_axis_digest=external.axis.digest,
                    bytes_already_written=sum(item["bytes"] for item in pages),
                )
                pages.append(page)
                if sum(item["bytes"] for item in pages) > MAX_EXTERNAL_BYTES:
                    raise CensusError("external result pages exceed their total byte bound")
                records = []
                stream.flush()
                _progress(
                    output_dir,
                    state,
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
    _seal_external_manifest(output_dir, external_manifest, external)
    return external_manifest, counts, "sha256:" + summary_digest.hexdigest()


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
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Attempt every gene, seal source evidence, then score identical external rows."""
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
    protocol = frozen_protocol(
        feature_space_protocol=feature_protocol,
        parent_report_lock=parent_report_lock,
        parent_report_digest=previous["report_digest"],
        page_size=page_size,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
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
    _progress(output_dir, state)
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
    _check_coverage(catalog, source.receipt, previous, "source")
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
    _progress(output_dir, state, phase="source_fitting", total_genes=len(universe.axis.identities))

    def checkpoint(binding: ReceiptPageBinding) -> None:
        page = store.read_page(binding)
        accepted = sum(row.source is not None and row.source.accepted for row in page.genes)
        rejected = sum(row.source is None for row in page.genes)
        _progress(
            output_dir,
            state,
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
    )
    _check_anchor_sources(census, store, catalog, previous)
    cross_table = _source_cross_table(census, store, catalog)
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
    source_build = source.receipt
    del source, source_protein
    _progress(output_dir, state, phase="external_admission", external_measurements_read=True)
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
    _check_coverage(projected, external.receipt, previous, "external")
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
    _progress(output_dir, state, phase="complete", complete=True)
    return {
        key: report[key]
        for key in (
            "evaluation_id",
            "profile_id",
            "protocol_digest",
            "parent_report_digest",
            "report_digest",
            "source_feature_count",
            "source_accepted_genes",
            "source_abstained_genes",
            "source_input_domain_rejected_genes",
            "external_stage_counts",
            "all_genes_retained",
            "redistribution_status",
        )
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
            output_dir=args.output,
            page_size=args.page_size,
        )
    except Exception:  # noqa: BLE001 - CLI errors must not disclose private execution context.
        print(
            "Source-fit census did not complete; retain incomplete local evidence "
            "without treating it as a finished result.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
