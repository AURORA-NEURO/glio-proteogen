"""Closed, byte-locked inherited census artifacts; no model or assay execution."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
import types
from collections import Counter
from dataclasses import asdict, fields
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import (
    Literal,
    NoReturn,
    SupportsIndex,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import DistinctCohortReceipt
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    SourceLock,
)
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    ProteinAdmissionReceipt,
    ProteinPanelCoverage,
)
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_feature_space import atlas, cohort
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    PROFILE_ID as FEATURE_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.contracts import (
    SourceCensusReceipt,
    SourceManifestBinding,
)
from glio_proteogen.research.cptac_gbm_source_fit_census.storage import (
    decode_manifest,
    decode_page,
    hydrate_source_fit_receipt,
)

from .contracts import (
    BASELINE_PROFILE_ID,
    EXECUTION_ARTIFACT_NAMES,
    MAX_BASELINE_DOCUMENT_BYTES,
    MAX_CASES,
    MAX_FEATURES,
    MAX_PAGE_BYTES,
    MAX_PHASE_BYTES,
    PROFILE_ID,
    ArtifactBinding,
    BaselineCensusReceipt,
    ExecutionBaselineError,
    artifact_limit,
    require_digest,
    require_integer,
)

_PROTOCOL_FIELDS = frozenset(
    (
        "aligned_external_validation",
        "anchor_request_digest",
        "assay_axes_converted_or_batch_corrected",
        "association_tested",
        "capacity_flag_filters_fits",
        "causal_identification",
        "clinical_validation",
        "count_capacity_is_fit_eligibility",
        "crash_restart_requires_complete_source_predictor_replay",
        "default_promotion",
        "default_source_page_size",
        "evaluation_id",
        "every_gene_reaches_original_source_fitter",
        "expected_input_domain_rejection_retained",
        "external_bootstrap",
        "feature_space_protocol",
        "feature_space_protocol_digest",
        "fitter_internal_standardization",
        "fitting_magnitude_bound",
        "gene_universe",
        "genes_ranked",
        "genetic_donor_independence_proven",
        "historical_report_reader_source_digest",
        "hydration_refits_source_models",
        "maximum_cases",
        "maximum_external_phase_bytes",
        "maximum_features",
        "maximum_gene_case_cells",
        "maximum_manifest_bytes",
        "maximum_page_bytes",
        "maximum_page_genes",
        "maximum_source_phase_bytes",
        "method_document_digest",
        "method_sources",
        "model_fits_performed",
        "multiplicity_adjusted_discoveries",
        "nominal_interval_coverage_established",
        "nonanchor_request_digest",
        "parent_report_digest",
        "parent_report_lock",
        "parent_source_receipts_and_complete_anchor_results_must_replay",
        "post_hoc",
        "prediction_scoring_performed",
        "private_predictors_persisted",
        "profile_id",
        "protocol_digest",
        "redistribution_status",
        "reference_material_equivalence_proven",
        "simultaneous_gene_inference_established",
        "source_fit_candidate_attempts_maximum_including_median",
        "source_fit_implementation",
        "source_fold_assignment_digest",
        "source_huber_fit_attempts_maximum",
        "source_huber_iteration_budget",
        "source_patient_refit_bootstrap_performed",
        "source_receipts_sealed_before_external_measurement_reads",
        "tool_source_digest",
        "unexpected_software_error_stops_incomplete_run",
        "values_imputed",
        "values_transformed",
        "variation_diagnostic_filters_fits",
        "workers",
    )
)
_REPORT_FIELDS = frozenset(
    (
        "aligned_external_validation",
        "all_genes_attempted",
        "all_genes_retained",
        "all_original_source_receipts_and_external_results_replayed",
        "assay_axes_converted_or_batch_corrected",
        "association_tested",
        "capacity_fit_cross_table",
        "capacity_flag_filters_fits",
        "causal_identification",
        "clinical_validation",
        "count_capacity_is_fit_eligibility",
        "default_promotion",
        "evaluation_id",
        "external_build_receipt",
        "external_case_count",
        "external_document_digest",
        "external_manifest_digest",
        "external_stage_counts",
        "feature_axis_digest",
        "genes_ranked",
        "genetic_donor_independence_proven",
        "limitations",
        "metadata_separation",
        "model_fits_performed",
        "multiplicity_adjusted_discoveries",
        "nominal_interval_coverage_established",
        "parent_report_digest",
        "post_hoc",
        "prediction_scoring_performed",
        "profile_id",
        "protocol_digest",
        "redistribution_status",
        "reference_material_equivalence_proven",
        "report_digest",
        "simultaneous_gene_inference_established",
        "source_abstained_genes",
        "source_accepted_genes",
        "source_build_receipt",
        "source_case_count",
        "source_document_digest",
        "source_feature_count",
        "source_input_domain_rejected_genes",
        "source_manifest_binding",
        "source_manifest_digest",
        "source_manifest_sealed_before_external_measurement_reads",
        "source_patient_refit_bootstrap_performed",
        "summary_sha256",
        "values_imputed",
        "values_transformed",
        "variation_diagnostic_filters_fits",
    )
)
_SOURCE_FIELDS = frozenset(
    (
        "catalog_digest",
        "evaluation_id",
        "external_measurements_read",
        "profile_id",
        "protocol_digest",
        "redistribution_status",
        "source_build_receipt",
        "source_catalog",
        "source_document_digest",
        "source_universe_receipt",
    )
)
_EXTERNAL_FIELDS = frozenset(
    (
        "evaluation_id",
        "external_build_receipt",
        "external_catalog",
        "external_catalog_digest",
        "external_document_digest",
        "profile_id",
        "protocol_digest",
        "redistribution_status",
        "source_catalog_digest",
        "source_document_digest",
        "source_manifest_digest",
    )
)
_CHECK_FIELDS = frozenset(
    (
        "all_sixteen_original_source_receipts_replayed",
        "capacity_fit_cross_table",
        "checks_digest",
        "external_measurements_read",
        "parent_report_digest",
        "profile_id",
        "protocol_digest",
        "source_document_digest",
        "source_manifest_binding",
        "source_manifest_digest",
    )
)
_PROGRESS_FIELDS = frozenset(
    (
        "complete",
        "external_accepted",
        "external_evaluator_attempted",
        "external_genes_processed",
        "external_measurements_read",
        "phase",
        "profile_id",
        "protocol_digest",
        "source_abstained",
        "source_accepted",
        "source_attempted",
        "source_input_domain_rejected",
        "total_genes",
    )
)
_FEATURE_PROTOCOL_FIELDS = frozenset(
    (
        "aggregate_structural_sequence_policy",
        "aligned_external_validation",
        "assay_axes_converted_or_batch_corrected",
        "assay_order",
        "association_tested",
        "causal_identification",
        "clinical_validation",
        "complete_processing_identity_proven",
        "default_promotion",
        "eligibility_admitted",
        "evaluation_id",
        "external_axis_expansion_allowed",
        "external_joint_complete_descriptive_minimum",
        "fit_eligibility_established",
        "genes_ranked",
        "genetic_donor_independence_proven",
        "literature_anchors",
        "maximum_cases",
        "maximum_features",
        "maximum_gene_case_cells",
        "maximum_json_bytes",
        "metadata_issuer_authenticated_by_hashes",
        "method_document_digest",
        "method_sources",
        "model_fits_performed",
        "multiplicity_adjusted_discoveries",
        "nominal_interval_coverage_established",
        "numerical_rank_or_convergence_established",
        "original_support_gates_lowered",
        "pattern_order_cnv_rna_protein",
        "prediction_scoring_performed",
        "profile_id",
        "protocol_digest",
        "redistribution_status",
        "reference_material_equivalence_proven",
        "selection_uses_association_outcomes",
        "selection_uses_external_values",
        "source_axis_rule",
        "source_catalog_persisted_before_external_measurement_reads",
        "source_count_capacity",
        "source_fold_assignment_digest",
        "source_input_protocol",
        "source_input_protocol_digest",
        "source_input_protocol_role",
        "source_variation_diagnostics",
        "state_order",
        "tool_source_digest",
        "transfer_eligibility_established",
        "values_imputed",
        "values_transformed",
        "variation_is_a_gate",
    )
)
_PROVIDER_PROTOCOL_FIELDS = frozenset(
    (
        "aligned_external_validation",
        "assay_axes_converted_or_batch_corrected",
        "bootstrap",
        "candidate_tie_order",
        "canonical_dependency_source",
        "clinical_validation",
        "complete_processing_identity_proven",
        "default_promotion",
        "evaluation_id",
        "external_common_complete_minimum",
        "external_minimum_basis",
        "final_selection",
        "huber_dependency_source",
        "input_bindings",
        "iteration_budget",
        "machine",
        "measurement_axes",
        "metadata_issuer_authenticated_by_hashes",
        "method_document_digest",
        "nested_dependency_sources",
        "nested_source_gates",
        "numpy",
        "panel",
        "platform_system",
        "primary_contrast",
        "prior_information",
        "profile_id",
        "protocol_digest",
        "python",
        "redistribution_status",
        "reference_material_equivalence_proven",
        "secondary_contrast",
        "source_folds",
        "source_modules",
        "source_only_fit_before_any_external_measurement_read",
        "source_training_robust_center_scale_only",
        "tool_source_digest",
        "values_imputed",
    )
)


def _fail() -> NoReturn:
    raise ExecutionBaselineError("inherited census artifacts failed their closed contract")


def _object(value: object, names: frozenset[str] | set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != names:
        _fail()
    return cast("dict[str, object]", value)


def _same(left: object, right: object) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _string(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or any(ord(char) < 32 for char in value)
    ):
        _fail()
    return value


def _integer(value: object, maximum: int = MAX_FEATURES) -> int:
    return require_integer(value, minimum=0, maximum=maximum)


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _number(value: object, *, nonnegative: bool = False) -> float:
    if type(value) is not float or not math.isfinite(value) or (nonnegative and value < 0):
        _fail()
    return value


def _pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in rows:
        if key in result:
            _fail()
        result[key] = value
    return result


def _invalid_constant(_value: str) -> NoReturn:
    _fail()


def _json(payload: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid_constant
        )
        if type(value) is not dict or canonical_json_bytes(value) != payload:
            _fail()
    except ExecutionBaselineError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ExecutionBaselineError("baseline JSON is not canonical bounded data") from None
    return cast("dict[str, object]", value)


def _embedded(value: dict[str, object], field: str, expected: object | None = None) -> str:
    digest = require_digest(value.get(field))
    if sha256_digest({key: item for key, item in value.items() if key != field}) != digest or (
        expected is not None and digest != expected
    ):
        _fail()
    return digest


def _snapshot(metadata: os.stat_result, *, directory: bool = False) -> tuple[int, ...]:
    regular = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not regular or getattr(metadata, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
    ):
        raise ExecutionBaselineError("baseline artifacts require regular non-link paths")
    identity = (metadata.st_dev, metadata.st_ino)
    return (
        identity
        if directory
        else (
            *identity,
            metadata.st_size,
            metadata.st_mtime_ns,
            getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns),
        )
    )


def _directory(path: Path) -> tuple[int, ...]:
    for ancestor in (*reversed(path.parents), path):
        _snapshot(ancestor.lstat(), directory=True)
    return _snapshot(path.lstat(), directory=True)


def _read(directory: Path, name: str, binding: ArtifactBinding | None = None) -> bytes:
    maximum = artifact_limit(name)
    try:
        root_identity = _directory(directory)
        path = directory.joinpath(*name.split("/"))
        _directory(path.parent)
        before = _snapshot(path.lstat())
        size = before[2]
        if not 1 <= size <= maximum or (
            binding is not None and (size != binding.bytes or name != binding.relative_path)
        ):
            _fail()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _snapshot(opened) != before:
                _fail()
            data = stream.read(size + 1)
            after = os.fstat(stream.fileno())
        if (
            len(data) != size
            or _snapshot(after) != before
            or opened.st_ctime_ns != after.st_ctime_ns
            or _snapshot(path.lstat()) != before
            or _directory(directory) != root_identity
        ):
            _fail()
        if binding is not None and "sha256:" + hashlib.sha256(data).hexdigest() != binding.sha256:
            _fail()
    except ExecutionBaselineError:
        raise
    except (OSError, TypeError, ValueError):
        raise ExecutionBaselineError("baseline aggregate file could not be verified") from None
    return data


_REGISTERED = frozenset(
    (
        GeneIdentity,
        SourceLock,
        SourceManifestBinding,
        ProteinAdmissionReceipt,
        ProteinPanelCoverage,
        DistinctCohortReceipt,
        cohort.SourceUniverseReceipt,
        cohort.CohortBuildReceipt,
        cohort.AxisSchemaSummary,
        cohort.SchemaHistogram,
        cohort.SchemaHistogramBin,
        atlas.SourceFeatureCatalog,
        atlas.SourceGeneFeature,
        atlas.GeneCoverage,
        atlas.CountSupportCapacity,
        atlas.TrainingVariationDiagnostics,
        atlas.ExternalFeatureCoverage,
        transfer.TransferMetrics,
        transfer.ConditionalInterval,
        transfer.ConditionalMetricIntervals,
        transfer.ConditionalUncertainty,
        transfer.TransferGeneResult,
    )
)


@lru_cache(maxsize=32)
def _hints(kind: type[object]) -> dict[str, object]:
    namespace = {**vars(sys.modules[kind.__module__]), "GeneIdentity": GeneIdentity}
    return cast("dict[str, object]", get_type_hints(kind, globalns=namespace))


def _typed(value: object, annotation: object) -> None:
    if annotation is transfer.SourceFitReceipt:
        hydrate_source_fit_receipt(value)
    elif annotation is type(None):
        if value is not None:
            _fail()
    elif annotation is bool:
        _boolean(value)
    elif annotation is int:
        _integer(value, 2**64 - 1)
    elif annotation is float:
        _number(value)
    elif annotation is str:
        _string(value)
    elif get_origin(annotation) is Literal:
        if not any(type(value) is type(item) and value == item for item in get_args(annotation)):
            _fail()
    elif get_origin(annotation) in (types.UnionType, Union):
        for option in get_args(annotation):
            try:
                _typed(value, option)
            except ExecutionBaselineError:
                continue
            return
        _fail()
    elif get_origin(annotation) is tuple:
        arguments = get_args(annotation)
        if (
            type(value) is not list
            or len(arguments) != 2
            or arguments[1] is not Ellipsis
            or len(value) > MAX_FEATURES
        ):
            _fail()
        if arguments[0] in (str, int, float) and len(value) > 16:
            _fail()
        for item in value:
            _typed(item, arguments[0])
    elif isinstance(annotation, type) and annotation in _REGISTERED:
        row = _object(value, {field.name for field in fields(annotation)})
        for field, kind in _hints(annotation).items():
            _typed(row[field], kind)
        if annotation is GeneIdentity:
            GeneIdentity(**cast("dict[str, str | None]", row))  # type: ignore[arg-type]
        elif annotation is SourceLock:
            SourceLock(**row)  # type: ignore[arg-type]
    else:
        _fail()


def _metadata(value: object, *, depth: int = 0) -> None:
    if depth > 16:
        _fail()
    if type(value) is dict:
        forbidden = {
            "values",
            "predictions",
            "residuals",
            "case_id",
            "sample_id",
            "file_id",
            "indices",
            "patient_keys",
            "fold_memberships",
            "beta",
            "x_center",
            "x_scale",
        }
        if forbidden.intersection(value):
            _fail()
        for key, child in value.items():
            _string(key)
            _metadata(child, depth=depth + 1)
    elif type(value) is list:
        if len(value) > 16 or any(type(item) in (dict, list, int, float, bool) for item in value):
            _fail()
        for item in value:
            _string(item)
    elif type(value) is str:
        _string(value)
    elif type(value) is int:
        _integer(value, 2**64 - 1)
    elif type(value) is bool:
        _boolean(value)
    elif type(value) is float:
        _number(value)
    elif value is not None:
        _fail()


def _module_bindings(value: object, package: str, names: tuple[str, ...]) -> None:
    row = _object(value, set(names))
    root = files(package)
    for name in names:
        if (
            require_digest(row[name])
            != "sha256:"
            + hashlib.sha256(root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        ):
            _fail()


def _protocol(value: dict[str, object]) -> dict[str, object]:
    row = _object(value, _PROTOCOL_FIELDS)
    _metadata(row)
    _embedded(row, "protocol_digest")
    if (
        row["profile_id"] != BASELINE_PROFILE_ID
        or row["every_gene_reaches_original_source_fitter"] is not True
        or row["source_receipts_sealed_before_external_measurement_reads"] is not True
        or row["private_predictors_persisted"] is not False
        or row["hydration_refits_source_models"] is not False
    ):
        _fail()
    for name, expected in {
        "source_fit_candidate_attempts_maximum_including_median": 104,
        "source_huber_fit_attempts_maximum": 78,
        "source_huber_iteration_budget": 240,
        "workers": 1,
        "maximum_page_genes": 64,
        "maximum_page_bytes": MAX_PAGE_BYTES,
        "maximum_manifest_bytes": MAX_PAGE_BYTES,
        "maximum_source_phase_bytes": MAX_PHASE_BYTES,
        "maximum_external_phase_bytes": MAX_PHASE_BYTES,
        "maximum_features": MAX_FEATURES,
        "maximum_cases": MAX_CASES,
        "maximum_gene_case_cells": 2_000_000,
    }.items():
        if type(row[name]) is not int or row[name] != expected:
            _fail()
    require_integer(row["default_source_page_size"], minimum=1, maximum=64)
    if _number(row["fitting_magnitude_bound"]) != 1e12:
        _fail()
    _module_bindings(
        row["method_sources"],
        "glio_proteogen.research.cptac_gbm_source_fit_census",
        ("__init__.py", "contracts.py", "storage.py", "engine.py"),
    )
    nested = _object(row["feature_space_protocol"], _FEATURE_PROTOCOL_FIELDS)
    _embedded(nested, "protocol_digest", row["feature_space_protocol_digest"])
    if (
        nested["profile_id"] != FEATURE_PROFILE_ID
        or nested["source_fold_assignment_digest"] != row["source_fold_assignment_digest"]
    ):
        _fail()
    _module_bindings(
        nested["method_sources"],
        "glio_proteogen.research.cptac_gbm_feature_space",
        ("__init__.py", "contracts.py", "assays.py", "cohort.py", "atlas.py"),
    )
    original = _object(nested["source_input_protocol"], _PROVIDER_PROTOCOL_FIELDS)
    _embedded(original, "protocol_digest", nested["source_input_protocol_digest"])
    if original["profile_id"] != transfer.PROFILE_ID or not _same(original["panel"], PANEL):
        _fail()
    _module_bindings(
        original["source_modules"],
        "glio_proteogen.research.cptac_gbm_external_admission",
        (
            "contracts.py",
            "source.py",
            "identity.py",
            "protein.py",
            "discovery.py",
            "assays.py",
            "plan.py",
            "cohort_plan.py",
            "transfer.py",
        ),
    )
    _module_bindings(
        original["nested_dependency_sources"],
        "glio_proteogen.research.cptac_gbm_transcript_protein_discordance",
        ("nested_selection.py", "model.py", "convergence.py", "profile.py"),
    )
    for scope in (row, nested, original):
        for key, item in scope.items():
            if key.endswith(("_digest", "_source")) and key not in (
                "anchor_request_digest",
                "nonanchor_request_digest",
            ):
                require_digest(item)
    if (
        row["anchor_request_digest"]
        != "SHA256 canonical {protocol_digest: original provider protocol digest, gene: approved symbol}"
        or row["nonanchor_request_digest"]
        != "SHA256 canonical {census_protocol_digest: new protocol digest, hgnc_id: stable HGNC ID}"
    ):
        _fail()
    return row


def _coverage(row: dict[str, object], cases: int) -> None:
    _typed(row, atlas.GeneCoverage)
    if row["candidate_specimens"] != cases:
        _fail()
    states = []
    for axis in ("cnv", "rna", "protein"):
        values = cast("list[object]", row[axis + "_state_counts"])
        if (
            len(values) != 6
            or sum(cast("list[int]", values)) != cases
            or row["observed_" + axis] != values[0]
            or cast("int", row["zero_" + axis]) > cast("int", values[0])
        ):
            _fail()
        states.append(values)
    patterns = cast("list[int]", row["pattern_counts_cnv_rna_protein"])
    if (
        len(patterns) != 8
        or sum(patterns) != cases
        or row["joint_complete"] != patterns[7]
        or row["rna_protein_complete"] != patterns[3] + patterns[7]
        or row["cnv_protein_complete"] != patterns[5] + patterns[7]
        or row["protein_feature_present"] != (states[2][1] != cases)
    ):
        _fail()
    if any(
        sum(patterns[code] for code in range(8) if code & bit) != states[index][0]
        for index, bit in enumerate((4, 2, 1))
    ):
        _fail()


def _catalog(
    value: object, *, source: bool, cases: int, axis: str, candidate: str, fold_digest: str
) -> tuple[dict[str, object], tuple[GeneIdentity, ...]]:
    kind = atlas.SourceFeatureCatalog if source else atlas.ExternalFeatureCoverage
    _typed(value, kind)
    catalog = cast("dict[str, object]", value)
    genes = cast("list[dict[str, object]]", catalog["genes"])
    if (
        not 1 <= len(genes) <= MAX_FEATURES
        or catalog["profile_id"] != FEATURE_PROFILE_ID
        or catalog["feature_axis_digest"] != axis
        or catalog["candidate_digest"] != candidate
        or catalog["source_case_count" if source else "external_case_count"] != cases
    ):
        _fail()
    identities = []
    count_supported = []
    for gene in genes:
        coverage = cast("dict[str, object]", gene["coverage"]) if source else gene
        _coverage(coverage, cases)
        identity = GeneIdentity(**cast("dict[str, str | None]", coverage["identity"]))  # type: ignore[arg-type]
        identities.append(identity)
        if source:
            capacity = cast("dict[str, object]", gene["count_capacity"])
            counts = cast("list[int]", capacity["fold_joint_counts"])
            total = cast("int", coverage["joint_complete"])
            if len(counts) != 5 or sum(counts) != total:
                _fail()
            validation = min(counts)
            outer = min(total - count for count in counts)
            inner = min(total - counts[a] - counts[b] for a in range(5) for b in range(5) if a != b)
            possible = total >= 60 and validation >= 3 and outer >= 48 and inner >= 32
            expected = {
                "joint_complete": total,
                "fold_joint_counts": counts,
                "minimum_validation_joint": validation,
                "minimum_outer_training_joint": outer,
                "minimum_inner_training_joint": inner,
                "all_five_fold_count_support_possible": possible,
            }
            if not _same(capacity, expected):
                _fail()
            if possible:
                count_supported.append(identity.hgnc_id)
            variation = cast("dict[str, object]", gene["training_variation"])
            if variation["training_contexts"] != 26 or any(
                cast("int", count) > 26 for count in variation.values()
            ):
                _fail()
    axis_identities = tuple(identities)
    if (
        tuple(identity.hgnc_id for identity in identities)
        != tuple(sorted({identity.hgnc_id for identity in identities}))
        or len({identity.symbol for identity in identities}) != len(identities)
        or sha256_digest(tuple(asdict(identity) for identity in identities)) != axis
    ):
        _fail()
    if (
        catalog["state_order"]
        != [
            "observed",
            "absent_feature",
            "unresolved_reference",
            "ambiguous_identity",
            "symbol_disagreement",
            "missing_measurement",
        ]
        or catalog["pattern_order_cnv_rna_protein"] != [f"{index:03b}" for index in range(8)]
        or catalog["assay_order"]
        != [
            "ascat_total_copy_number",
            "star_fpkm_uq_unstranded",
            "cdap_unshared_log2_specimen_reference_ratio",
        ]
        or catalog["selection_uses_external_values"] is not False
        or catalog["model_fits_performed"] is not False
    ):
        _fail()
    if source:
        if (
            catalog["source_fold_assignment_digest"] != fold_digest
            or catalog["count_supported_genes"] != len(count_supported)
            or catalog["source_count_candidate_hgnc_digest"]
            != sha256_digest(tuple(count_supported))
            or catalog["measurement_matrix_bytes"] != 3 * len(genes) * cases * 8
            or catalog["availability_matrix_bytes"] != 3 * len(genes) * cases
            or any(
                catalog[field] is not False
                for field in (
                    "variation_is_a_gate",
                    "fit_eligibility_established",
                    "numerical_rank_or_convergence_established",
                    "association_tested",
                    "values_imputed",
                    "values_transformed",
                )
            )
        ):
            _fail()
    elif (
        catalog["external_joint_minimum"] != 48
        or catalog["external_count_sufficient_genes"]
        != sum(cast("int", gene["joint_complete"]) >= 48 for gene in genes)
        or any(
            catalog[field] is not False
            for field in (
                "source_axis_changed",
                "fit_or_transfer_eligibility_established",
                "aligned_external_validation",
            )
        )
    ):
        _fail()
    return catalog, axis_identities


def _build(
    value: object, catalog: dict[str, object], *, source: bool, cases: int, features: int
) -> dict[str, object]:
    _typed(value, cohort.CohortBuildReceipt)
    row = cast("dict[str, object]", value)
    if (
        row["profile_id"] != FEATURE_PROFILE_ID
        or row["feature_axis_digest"] != catalog["feature_axis_digest"]
        or row["candidate_digest"] != catalog["candidate_digest"]
        or any(
            row[field] != cases
            for field in ("candidate_specimens", "verified_rna_files", "verified_cnv_files")
        )
    ):
        _fail()
    protein = cast("dict[str, object]", row["source_protein_receipt"])
    if (
        protein["candidate_digest"] != row["candidate_digest"]
        or protein["candidate_count"] != cases
        or protein["biological_feature_rows"]
        != cast("int", protein["identified_feature_rows"])
        + cast("int", protein["unavailable_identity_rows"])
    ):
        _fail()
    for name in ("protein_sha256", "sample_map_sha256", "hgnc_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", _string(protein[name])) is None:
            _fail()
    for prefix in ("unshared", "all_peptide"):
        if (
            cast("int", protein["finite_" + prefix + "_cells"])
            + cast("int", protein["missing_" + prefix + "_cells"])
            != protein["biological_feature_rows"] * cases
        ):
            _fail()
    if [
        item["gene"] for item in cast("list[dict[str, object]]", protein["panel_coverage"])
    ] != list(PANEL):
        _fail()
    expected_profile = (
        "cptac-gbm-discovery-protein-admission/1.0.0"
        if source
        else "cptac-gbm-confirmatory-protein-admission/1.0.0"
    )
    if protein["profile_id"] != expected_profile or cast(
        "int", protein["finite_zero_unshared_cells"]
    ) > cast("int", protein["finite_unshared_cells"]):
        _fail()
    for panel_row in cast("list[dict[str, object]]", protein["panel_coverage"]):
        if panel_row["source_rows"] not in (0, 1):
            _fail()
        counts = [
            panel_row[field]
            for field in ("unshared_finite", "unshared_missing", "all_peptide_finite")
        ]
        if panel_row["source_rows"] == 0:
            if counts != [None, None, None]:
                _fail()
        elif (
            any(value is None or cast("int", value) > cases for value in counts)
            or cast("int", counts[0]) + cast("int", counts[1]) != cases
        ):
            _fail()
    summaries = cast("list[dict[str, object]]", row["schema_summaries"])
    if len(summaries) != 2:
        _fail()
    genes = cast("list[dict[str, object]]", catalog["genes"])
    fields_expected = {
        "data_rows",
        "gene_rows",
        "summary_rows",
        "versioned_gene_rows",
        "par_y_gene_rows",
        "duplicate_gene_symbol_groups",
        "ambiguous_reference_gene_ids",
        "missing_gene_rows",
        "observed_zero_gene_rows",
    }
    for index, (axis, workflow, annotation) in enumerate(
        (
            ("ascat_total_copy_number", "AscatNGS", None),
            ("star_fpkm_uq_unstranded", "STAR - Counts", "GENCODE v36"),
        )
    ):
        summary = summaries[index]
        if (
            summary["axis"] != axis
            or summary["workflow"] != workflow
            or summary["annotation_release"] != annotation
            or summary["verified_files"] != cases
            or summary["feature_count"] != features
            or cast("int", summary["verified_input_bytes"]) < cases
        ):
            _fail()
        axis_key = "cnv" if index == 0 else "rna"
        rows = [cast("dict[str, object]", gene["coverage"]) if source else gene for gene in genes]
        expected_states = [
            sum(cast("list[int]", gene[axis_key + "_state_counts"])[state] for gene in rows)
            for state in range(6)
        ]
        if summary["state_totals"] != expected_states or sum(expected_states) != features * cases:
            _fail()
        histograms = cast("list[dict[str, object]]", summary["histograms"])
        if {item["field"] for item in histograms} != fields_expected or len(histograms) != len(
            fields_expected
        ):
            _fail()
        for histogram in histograms:
            bins = cast("list[dict[str, int]]", histogram["bins"])
            if (
                not 1 <= len(bins) <= cases
                or [item["value"] for item in bins] != sorted({item["value"] for item in bins})
                or any(item["files"] < 1 for item in bins)
                or sum(item["files"] for item in bins) != cases
            ):
                _fail()
    return row


def _external_result(row: dict[str, object], source: object, request: str, cases: int) -> None:
    _typed(row, transfer.TransferGeneResult)
    if (
        row["profile_id"] != transfer.PROFILE_ID
        or row["request_digest"] != request
        or sha256_digest(row["source"]) != source
        or row["external_minimum"] != 48
        or cast("int", row["external_complete_count"]) > cases
        or cast("int", row["external_common_comparison_count"])
        > cast("int", row["external_complete_count"])
        or any(
            row[field] is not False
            for field in ("aligned_external_validation", "clinical_validation", "default_promotion")
        )
    ):
        _fail()
    metrics = cast("list[dict[str, object]]", row["point_metrics"])
    if metrics and [item["candidate"] for item in metrics] != [
        *transfer.CANDIDATE_ORDER,
        "selected_policy",
    ]:
        _fail()
    for metric in metrics:
        if (
            metric["observed_count"] != row["external_common_comparison_count"]
            or _number(metric["mae"], nonnegative=True) < 0
            or _number(metric["rmse"], nonnegative=True) < 0
        ):
            _fail()
    uncertainty = row["uncertainty"]
    if row["accepted"] is not (row["failure_reason"] is None) or row["accepted"] is not (
        uncertainty is not None
    ):
        _fail()
    if uncertainty is not None:
        intervals = cast("dict[str, object]", uncertainty)
        expected_seed = int.from_bytes(
            hashlib.sha256((transfer.PROFILE_ID + ":external-paired:" + request).encode()).digest()[
                :8
            ],
            "big",
        )
        successful = cast("int", intervals["replicates_successful"])
        if (
            not metrics
            or intervals["seed"] != expected_seed
            or intervals["replicates_requested"] != 128
            or intervals["replicates_required"] != 103
            or not 103 <= successful <= 128
            or intervals["interval_scope"]
            != "external patient sampling conditional on frozen source fit"
            or any(
                intervals[field] is not False
                for field in (
                    "training_refitted",
                    "selection_repeated",
                    "training_uncertainty_available",
                )
            )
        ):
            _fail()
        expected_order = [*transfer.CANDIDATE_ORDER, "selected_policy"]
        interval_metrics = cast("list[dict[str, object]]", intervals["metrics"])
        if [item["candidate"] for item in interval_metrics] != expected_order:
            _fail()
        all_intervals = [
            intervals["primary_full_minus_cnv_mae"],
            intervals["secondary_selected_minus_full_mae"],
        ]
        for metric in interval_metrics:
            all_intervals.extend(
                metric[field]
                for field in ("mae", "rmse", "r2_vs_source_training_median")
                if metric[field] is not None
            )
        for item in all_intervals:
            interval = cast("dict[str, object]", item)
            if (
                interval["confidence_level"] != 0.9
                or not 103 <= cast("int", interval["replicates"]) <= successful
                or cast("float", interval["lower"]) > cast("float", interval["upper"])
            ):
                _fail()


_CONSTRUCTION_TOKEN = object()


class BaselineCensus:
    """Immutable aggregate artifact authority; it never contains predictors."""

    __slots__ = ("_bindings", "_protocol", "_receipt", "_report", "_source_names")
    _bindings: tuple[ArtifactBinding, ...]
    _protocol: bytes
    _report: bytes
    _receipt: BaselineCensusReceipt
    _source_names: frozenset[str]

    def __init__(
        self,
        token: object,
        *,
        bindings: tuple[ArtifactBinding, ...],
        protocol: bytes,
        report: bytes,
        receipt: BaselineCensusReceipt,
    ) -> None:
        if token is not _CONSTRUCTION_TOKEN:
            raise ExecutionBaselineError("baseline artifacts must pass the locked public loader")
        object.__setattr__(self, "_bindings", bindings)
        object.__setattr__(self, "_protocol", protocol)
        object.__setattr__(self, "_report", report)
        object.__setattr__(self, "_receipt", receipt)
        object.__setattr__(
            self,
            "_source_names",
            frozenset(
                binding.relative_path
                for binding in bindings
                if binding.relative_path
                in ("protocol.json", "source-catalog.json", "source-checks.json")
                or binding.relative_path.startswith("source-fit/")
            ),
        )

    @property
    def receipt(self) -> BaselineCensusReceipt:
        return self._receipt

    @property
    def numerical_protocol_digest(self) -> str:
        return self.receipt.numerical_protocol_digest

    @property
    def artifact_bindings(self) -> tuple[ArtifactBinding, ...]:
        return self._bindings

    def protocol_document(self) -> dict[str, object]:
        return _json(self._protocol)

    def report_document(self) -> dict[str, object]:
        return _json(self._report)

    def assert_artifact(self, relative_path: str, actual_bytes: bytes) -> None:
        if type(relative_path) is not str or type(actual_bytes) is not bytes:
            _fail()
        binding = next(
            (item for item in self.artifact_bindings if item.relative_path == relative_path), None
        )
        if (
            binding is None
            or len(actual_bytes) != binding.bytes
            or "sha256:" + hashlib.sha256(actual_bytes).hexdigest() != binding.sha256
        ):
            raise ExecutionBaselineError(
                "inherited numerical artifact differs from its locked baseline"
            )

    def verify_artifact_file(self, output_dir: Path, relative_path: str) -> None:
        """Read one locked aggregate once, with its size and path snapshot bounded."""
        if type(relative_path) is not str:
            _fail()
        binding = next(
            (item for item in self.artifact_bindings if item.relative_path == relative_path), None
        )
        if binding is None:
            raise ExecutionBaselineError("artifact is outside the inherited baseline namespace")
        directory = _output_directory(output_dir)
        self.assert_artifact(relative_path, _read(directory, relative_path, binding))

    def verify_source_phase(self, output_dir: Path) -> None:
        directory = _output_directory(output_dir)
        expected = {name for name in self._source_names if name.startswith("source-fit/")}
        if _tree(directory, scope="source-fit") != expected:
            raise ExecutionBaselineError(
                "written source phase is not the exact inherited namespace"
            )
        for binding in self.artifact_bindings:
            if binding.relative_path in self._source_names:
                self.assert_artifact(
                    binding.relative_path, _read(directory, binding.relative_path, binding)
                )

    def verify_complete_output(
        self, output_dir: Path, allowed_extra_names: tuple[str, ...] = EXECUTION_ARTIFACT_NAMES
    ) -> None:
        if type(allowed_extra_names) is not tuple or allowed_extra_names not in (
            EXECUTION_ARTIFACT_NAMES[:1],
            EXECUTION_ARTIFACT_NAMES,
        ):
            raise ExecutionBaselineError(
                "only the two declared execution envelope names are permitted"
            )
        directory = _output_directory(output_dir)
        expected = {binding.relative_path for binding in self.artifact_bindings}
        actual = _tree(directory)
        if not expected <= actual or not actual <= expected | set(allowed_extra_names):
            raise ExecutionBaselineError(
                "completed output is not the exact inherited artifact tree"
            )
        for binding in self.artifact_bindings:
            self.assert_artifact(
                binding.relative_path, _read(directory, binding.relative_path, binding)
            )

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("the locked census baseline is immutable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("the artifact authority cannot be serialized; export its receipt")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("the artifact authority cannot be serialized; export its receipt")

    def __repr__(self) -> str:
        return f"BaselineCensus(feature_count={self.receipt.feature_count}, artifacts={self.receipt.artifact_count})"


def _output_directory(value: Path) -> Path:
    if not isinstance(value, Path):
        _fail()
    directory = value.absolute()
    try:
        _directory(directory)
    except (OSError, ValueError):
        raise ExecutionBaselineError(
            "baseline replay requires a regular output directory"
        ) from None
    return directory


def _tree(directory: Path, *, scope: str | None = None) -> set[str]:
    result = set()
    root = directory / scope if scope is not None else directory
    try:
        _directory(root)
        for path in root.rglob("*"):
            if path.is_dir():
                _directory(path)
                if path.relative_to(directory).as_posix() not in {
                    "source-fit",
                    "source-fit/pages",
                    "external-score",
                    "external-score/pages",
                }:
                    _fail()
            else:
                _snapshot(path.lstat())
                result.add(path.relative_to(directory).as_posix())
    except ExecutionBaselineError:
        raise
    except OSError:
        raise ExecutionBaselineError("baseline replay namespace could not be verified") from None
    return result


def _binding(name: str, payload: bytes) -> ArtifactBinding:
    return ArtifactBinding(name, len(payload), "sha256:" + hashlib.sha256(payload).hexdigest())


def _summary_row(
    record: dict[str, object], source: dict[str, object], *, capacity: bool
) -> dict[str, object]:
    receipt = cast("dict[str,object] | None", source["source"])
    result = cast("dict[str,object] | None", record["result"])
    metrics = (
        {
            item["candidate"]: item
            for item in cast("list[dict[str,object]]", result["point_metrics"])
        }
        if result is not None
        else {}
    )
    nested = (
        cast("dict[str,object] | None", receipt["nested_point_summary"])
        if receipt is not None
        else None
    )
    uncertainty = (
        cast("dict[str,object] | None", result["uncertainty"]) if result is not None else None
    )
    identity = cast("dict[str,object]", record["identity"])
    row = {key: identity[key] for key in ("hgnc_id", "symbol", "entrez_id", "ensembl_gene_id")}
    row.update(
        {
            "source_all_five_fold_count_support_possible": capacity,
            "source_accepted": record["source_accepted"],
            "source_complete_count": receipt["complete_count"] if receipt else None,
            "source_common_oof_count": receipt["common_oof_count"] if receipt else None,
            "source_selected_candidate": receipt["selected_candidate"] if receipt else None,
            "nested_selected_policy_oof_mae": cast("dict[str,object]", nested["selected"])["mae"]
            if nested
            else None,
            "source_input_domain_rejection": record["source_input_domain_rejection"],
            "source_failure_reason": receipt["failure_reason"] if receipt else None,
        }
    )
    for key in (
        "external_evaluator_attempted",
        "external_input_domain_rejection",
        "external_complete_count",
        "external_support_sufficient",
        "point_scores_available",
        "conditional_intervals_available",
        "external_result_accepted",
    ):
        row[key] = record[key]
    row.update(
        {
            "external_failure_reason": result["failure_reason"] if result else None,
            "full_mae": metrics.get("full", {}).get("mae"),
            "cnv_only_mae": metrics.get("cnv_only", {}).get("mae"),
            "selected_policy_mae": metrics.get("selected_policy", {}).get("mae"),
            "full_minus_cnv_mae": result["primary_full_minus_cnv_mae"] if result else None,
            "selected_minus_full_mae": result["secondary_selected_minus_full_mae"]
            if result
            else None,
            "primary_lower90": cast("dict[str,object]", uncertainty["primary_full_minus_cnv_mae"])[
                "lower"
            ]
            if uncertainty
            else None,
            "primary_upper90": cast("dict[str,object]", uncertainty["primary_full_minus_cnv_mae"])[
                "upper"
            ]
            if uncertainty
            else None,
        }
    )
    return row


def _source_records(
    directory: Path,
    manifest: object,
    catalog: dict[str, object],
    identities: tuple[GeneIdentity, ...],
    bindings: list[ArtifactBinding],
) -> tuple[list[dict[str, object]], Counter[str], list[dict[str, object]]]:
    if type(manifest) is not SourceCensusReceipt:
        _fail()
    summaries: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    cross: Counter[tuple[bool, str]] = Counter()
    records_digests = []
    catalog_genes = cast("list[dict[str,object]]", catalog["genes"])
    for binding in manifest.pages:
        name = "source-fit/" + binding.file_name
        data = _read(directory, name, ArtifactBinding(name, binding.bytes, binding.sha256))
        bindings.append(_binding(name, data))
        page = decode_page(data)
        start = len(summaries)
        if (
            page.digest != binding.page_digest
            or page.page_number != binding.page_number
            or len(page.genes) != binding.gene_count
            or page.genes[0].identity.hgnc_id != binding.first_hgnc_id
            or page.genes[-1].identity.hgnc_id != binding.last_hgnc_id
            or len(page.genes) != min(manifest.page_size, len(identities) - start)
        ):
            _fail()
        for field in (
            "profile_id",
            "request_digest",
            "feature_axis_digest",
            "candidate_digest",
            "source_catalog_digest",
            "source_fold_assignment_digest",
        ):
            if getattr(page, field) != getattr(manifest, field):
                _fail()
        for record in page.genes:
            index = len(summaries)
            if index >= len(identities) or record.identity != identities[index]:
                _fail()
            records_digests.append(record.digest)
            receipt = record.source
            nested = receipt.nested_point_summary if receipt else None
            selected = {"mae": nested.selected.mae} if nested else None
            summary: dict[str, object] = {
                "record_digest": record.digest,
                "receipt_digest": sha256_digest(asdict(receipt)) if receipt else None,
                "domain_rejection": record.input_domain_rejection,
                "accepted": receipt.accepted if receipt else False,
                "source": {
                    "complete_count": receipt.complete_count,
                    "common_oof_count": receipt.common_oof_count,
                    "selected_candidate": receipt.selected_candidate,
                    "failure_reason": receipt.failure_reason,
                    "nested_point_summary": {"selected": selected} if selected else None,
                }
                if receipt
                else None,
            }
            summaries.append(summary)
            status = (
                "input_domain_rejected"
                if receipt is None
                else "accepted"
                if receipt.accepted
                else "abstained"
            )
            counts[status] += 1
            capacity = cast("dict[str,object]", catalog_genes[index]["count_capacity"])[
                "all_five_fold_count_support_possible"
            ]
            cross[(cast("bool", capacity), status)] += 1
    if (
        len(summaries) != len(identities)
        or tuple(records_digests) != manifest.gene_record_digests
        or (counts["accepted"], counts["abstained"], counts["input_domain_rejected"])
        != (manifest.accepted_genes, manifest.abstained_genes, manifest.input_domain_rejected_genes)
    ):
        _fail()
    cross_table: list[dict[str, object]] = [
        {"count_capacity": capacity, "source_status": status, "genes": cross[(capacity, status)]}
        for capacity in (False, True)
        for status in ("accepted", "abstained", "input_domain_rejected")
    ]
    return summaries, counts, cross_table


def _external_records(  # noqa: PLR0915 - closed ordered page and record conservation.
    directory: Path,
    *,
    manifest: dict[str, object],
    protocol: dict[str, object],
    identities: tuple[GeneIdentity, ...],
    sources: list[dict[str, object]],
    catalog: dict[str, object],
    capacities: tuple[bool, ...],
    bindings: list[ArtifactBinding],
) -> tuple[Counter[str], list[dict[str, object]]]:
    names = {
        "profile_id",
        "protocol_digest",
        "source_manifest_digest",
        "external_document_digest",
        "feature_axis_digest",
        "total_genes",
        "pages",
        "stage_counts",
        "complete",
        "all_sixteen_original_results_replayed",
        "redistribution_status",
        "manifest_digest",
    }
    _object(manifest, names)
    if (
        manifest["profile_id"] != BASELINE_PROFILE_ID
        or manifest["protocol_digest"] != protocol["protocol_digest"]
        or manifest["total_genes"] != len(identities)
        or type(manifest["total_genes"]) is not int
        or manifest["complete"] is not True
        or manifest["all_sixteen_original_results_replayed"] is not True
    ):
        _fail()
    page_size = cast("int", protocol["default_source_page_size"])
    pages = manifest["pages"]
    if type(pages) is not list or len(pages) != (len(identities) + page_size - 1) // page_size:
        _fail()
    nested_protocol = cast("dict[str,object]", protocol["feature_space_protocol"])
    anchor_protocol = require_digest(nested_protocol["source_input_protocol_digest"])
    counts: Counter[str] = Counter()
    rows = []
    offset = 0
    genes = cast("list[dict[str,object]]", catalog["genes"])
    for number, value in enumerate(pages):
        binding = _object(
            value,
            {
                "page_number",
                "file_name",
                "bytes",
                "sha256",
                "page_digest",
                "gene_count",
                "first_hgnc_id",
                "last_hgnc_id",
            },
        )
        name = f"external-score/pages/{number:05d}.json"
        if _integer(binding["page_number"]) != number or binding["file_name"] != name:
            _fail()
        data = _read(
            directory,
            name,
            ArtifactBinding(name, cast("int", binding["bytes"]), cast("str", binding["sha256"])),
        )
        bindings.append(_binding(name, data))
        page = _object(
            _json(data),
            {
                "profile_id",
                "protocol_digest",
                "source_manifest_digest",
                "feature_axis_digest",
                "page_number",
                "genes",
                "redistribution_status",
                "page_digest",
            },
        )
        _embedded(page, "page_digest", binding["page_digest"])
        for field in (
            "profile_id",
            "protocol_digest",
            "source_manifest_digest",
            "feature_axis_digest",
            "redistribution_status",
        ):
            if page[field] != manifest[field]:
                _fail()
        records = page["genes"]
        if (
            _integer(page["page_number"]) != number
            or type(records) is not list
            or len(records) != require_integer(binding["gene_count"], minimum=1, maximum=64)
            or len(records) != min(page_size, len(identities) - offset)
        ):
            _fail()
        if (
            cast("dict[str,object]", records[0])["identity"] != asdict(identities[offset])
            or cast("dict[str,object]", records[-1])["identity"]
            != asdict(identities[offset + len(records) - 1])
            or binding["first_hgnc_id"] != identities[offset].hgnc_id
            or binding["last_hgnc_id"] != identities[offset + len(records) - 1].hgnc_id
        ):
            _fail()
        for raw in records:
            record = _object(
                raw,
                {
                    "identity",
                    "source_record_digest",
                    "source_input_domain_rejection",
                    "source_accepted",
                    "external_evaluator_attempted",
                    "external_input_domain_rejection",
                    "external_complete_count",
                    "external_support_sufficient",
                    "point_scores_available",
                    "conditional_intervals_available",
                    "external_result_accepted",
                    "result",
                },
            )
            identity, source = identities[offset], sources[offset]
            if (
                not _same(record["identity"], asdict(identity))
                or record["source_record_digest"] != source["record_digest"]
                or record["source_input_domain_rejection"] != source["domain_rejection"]
                or record["source_accepted"] is not source["accepted"]
            ):
                _fail()
            result = record["result"]
            expected_request = (
                sha256_digest({"protocol_digest": anchor_protocol, "gene": identity.symbol})
                if identity.symbol in PANEL
                else sha256_digest(
                    {
                        "census_protocol_digest": protocol["protocol_digest"],
                        "hgnc_id": identity.hgnc_id,
                    }
                )
            )
            if result is not None:
                result_row = cast("dict[str,object]", result)
                _external_result(
                    result_row,
                    source["receipt_digest"],
                    expected_request,
                    cast("int", catalog["external_case_count"]),
                )
            complete = _integer(record["external_complete_count"], MAX_CASES)
            if (
                complete != genes[offset]["joint_complete"]
                or record["external_support_sufficient"] is not (complete >= 48)
                or record["external_evaluator_attempted"] is not (source["source"] is not None)
                or record["point_scores_available"]
                is not bool(
                    result is not None and cast("dict[str,object]", result)["point_metrics"]
                )
                or record["conditional_intervals_available"]
                is not bool(
                    result is not None
                    and cast("dict[str,object]", result)["uncertainty"] is not None
                )
                or record["external_result_accepted"]
                is not bool(result is not None and cast("dict[str,object]", result)["accepted"])
            ):
                _fail()
            rejection = record["external_input_domain_rejection"]
            if rejection not in (
                None,
                "external finite inputs exceed the frozen scoring magnitude domain",
            ) or (result is None) != (source["source"] is None or rejection is not None):
                _fail()
            for key in (
                "source_accepted",
                "external_evaluator_attempted",
                "external_support_sufficient",
                "point_scores_available",
                "conditional_intervals_available",
                "external_result_accepted",
            ):
                counts[key] += _boolean(record[key])
            counts["external_input_domain_rejected"] += rejection is not None
            source_summary = {"source": source["source"]}
            rows.append(_summary_row(record, source_summary, capacity=capacities[offset]))
            offset += 1
    if offset != len(identities) or not _same(dict(counts), manifest["stage_counts"]):
        _fail()
    # Only compact CSV cells survive the streaming record loop. No predictor or
    # participant vector is materialized by this metadata loader.
    return counts, rows


def _validate_roots(protocol: dict[str, object], report: dict[str, object]) -> tuple[int, int, int]:
    _object(report, _REPORT_FIELDS)
    _embedded(report, "report_digest")
    if (
        report["profile_id"] != BASELINE_PROFILE_ID
        or report["protocol_digest"] != protocol["protocol_digest"]
        or report["parent_report_digest"] != protocol["parent_report_digest"]
        or report["evaluation_id"] != protocol["evaluation_id"]
    ):
        _fail()
    for field in (
        "all_genes_attempted",
        "all_genes_retained",
        "all_original_source_receipts_and_external_results_replayed",
        "source_manifest_sealed_before_external_measurement_reads",
        "model_fits_performed",
        "prediction_scoring_performed",
        "post_hoc",
    ):
        if report[field] is not True:
            _fail()
    false_fields = {
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
    }
    for document in (protocol, report):
        if (
            any(document[field] is not False for field in false_fields)
            or document["redistribution_status"] != "local_only_terms_unverified"
        ):
            _fail()
    _typed(report["metadata_separation"], DistinctCohortReceipt)
    _typed(report["limitations"], tuple[str, ...])
    _typed(report["source_manifest_binding"], SourceManifestBinding)
    _typed(protocol["parent_report_lock"], SourceLock)
    features = require_integer(
        report["source_feature_count"], minimum=len(PANEL), maximum=MAX_FEATURES
    )
    source_cases = require_integer(report["source_case_count"], minimum=60, maximum=MAX_CASES)
    external_cases = require_integer(report["external_case_count"], minimum=1, maximum=MAX_CASES)
    separation = cast("dict[str, object]", report["metadata_separation"])
    if (
        separation["training_candidates"] != source_cases
        or separation["test_candidates"] != external_cases
        or separation["checked_identifier_namespaces"]
        != [
            "case_submitter_id",
            "sample_submitter_id",
            "gdc_sample_uuid",
            "protein_aliquot_submitter_id",
            "protein_aliquot_uuid",
            "rna_or_cnv_file_id",
        ]
        or any(
            separation[field] != 0
            for field in (
                "case_submitter_overlaps",
                "sample_submitter_overlaps",
                "gdc_sample_uuid_overlaps",
                "protein_aliquot_submitter_overlaps",
                "protein_aliquot_uuid_overlaps",
                "assay_file_overlaps",
            )
        )
        or separation["donor_independence_admitted"] is not False
    ):
        _fail()
    if (
        any(
            _integer(report[field]) > features
            for field in (
                "source_accepted_genes",
                "source_abstained_genes",
                "source_input_domain_rejected_genes",
            )
        )
        or sum(
            cast("int", report[field])
            for field in (
                "source_accepted_genes",
                "source_abstained_genes",
                "source_input_domain_rejected_genes",
            )
        )
        != features
    ):
        _fail()
    for field in (
        "protocol_digest",
        "parent_report_digest",
        "source_document_digest",
        "external_document_digest",
        "source_manifest_digest",
        "external_manifest_digest",
        "summary_sha256",
        "feature_axis_digest",
    ):
        require_digest(report[field])
    return features, source_cases, external_cases


def _load_baseline(  # noqa: PLR0915 - one ordered integrity chain before authority creation.
    directory: Path, protocol_lock: SourceLock, evaluation_lock: SourceLock
) -> BaselineCensus:
    directory = _output_directory(directory)
    for lock in (protocol_lock, evaluation_lock):
        if type(lock) is not SourceLock or lock.bytes > MAX_BASELINE_DOCUMENT_BYTES:
            _fail()
    protocol_data = read_verified_source(
        directory / "protocol.json", protocol_lock, max_bytes=MAX_BASELINE_DOCUMENT_BYTES
    )
    report_data = read_verified_source(
        directory / "evaluation.json", evaluation_lock, max_bytes=MAX_BASELINE_DOCUMENT_BYTES
    )
    protocol, report = _protocol(_json(protocol_data)), _json(report_data)
    features, source_cases, external_cases = _validate_roots(protocol, report)
    bindings = [_binding("protocol.json", protocol_data), _binding("evaluation.json", report_data)]
    documents = {}
    for name in (
        "source-catalog.json",
        "source-checks.json",
        "external-coverage.json",
        "progress.json",
    ):
        data = _read(directory, name)
        bindings.append(_binding(name, data))
        documents[name] = _json(data)
    source_document = _object(documents["source-catalog.json"], _SOURCE_FIELDS)
    external_document = _object(documents["external-coverage.json"], _EXTERNAL_FIELDS)
    checks = _object(documents["source-checks.json"], _CHECK_FIELDS)
    progress = _object(documents["progress.json"], _PROGRESS_FIELDS)
    for document in documents.values():
        if (
            document["profile_id"] != BASELINE_PROFILE_ID
            or document["protocol_digest"] != protocol["protocol_digest"]
        ):
            _fail()
    _embedded(source_document, "source_document_digest", report["source_document_digest"])
    _embedded(external_document, "external_document_digest", report["external_document_digest"])
    _embedded(checks, "checks_digest")
    if (
        source_document["external_measurements_read"] is not False
        or checks["external_measurements_read"] is not False
        or checks["all_sixteen_original_source_receipts_replayed"] is not True
        or checks["source_document_digest"] != source_document["source_document_digest"]
        or checks["parent_report_digest"] != report["parent_report_digest"]
    ):
        _fail()
    axis = require_digest(report["feature_axis_digest"])
    fold_digest = require_digest(protocol["source_fold_assignment_digest"])
    source_candidate = require_digest(
        cast("dict[str,object]", source_document["source_build_receipt"])["candidate_digest"]
    )
    external_candidate = require_digest(
        cast("dict[str,object]", external_document["external_build_receipt"])["candidate_digest"]
    )
    source_catalog, identities = _catalog(
        source_document["source_catalog"],
        source=True,
        cases=source_cases,
        axis=axis,
        candidate=source_candidate,
        fold_digest=fold_digest,
    )
    external_catalog, external_identities = _catalog(
        external_document["external_catalog"],
        source=False,
        cases=external_cases,
        axis=axis,
        candidate=external_candidate,
        fold_digest=fold_digest,
    )
    if (
        len(identities) != features
        or identities != external_identities
        or not set(PANEL) <= {identity.symbol for identity in identities}
        or external_catalog["source_and_external_count_sufficient_genes"]
        != sum(
            cast("dict[str, object]", source_gene["count_capacity"])[
                "all_five_fold_count_support_possible"
            ]
            is True
            and cast("int", external_gene["joint_complete"]) >= 48
            for source_gene, external_gene in zip(
                cast("list[dict[str, object]]", source_catalog["genes"]),
                cast("list[dict[str, object]]", external_catalog["genes"]),
                strict=True,
            )
        )
    ):
        _fail()
    source_digest = sha256_digest(source_catalog)
    if (
        source_digest != source_document["catalog_digest"]
        or source_digest != external_document["source_catalog_digest"]
        or source_digest != external_catalog["source_catalog_digest"]
        or sha256_digest(external_catalog) != external_document["external_catalog_digest"]
        or external_document["source_document_digest"] != source_document["source_document_digest"]
        or external_document["source_manifest_digest"] != report["source_manifest_digest"]
    ):
        _fail()
    source_build = _build(
        source_document["source_build_receipt"],
        source_catalog,
        source=True,
        cases=source_cases,
        features=features,
    )
    external_build = _build(
        external_document["external_build_receipt"],
        external_catalog,
        source=False,
        cases=external_cases,
        features=features,
    )
    if not _same(source_build, report["source_build_receipt"]) or not _same(
        external_build, report["external_build_receipt"]
    ):
        _fail()
    universe = source_document["source_universe_receipt"]
    _typed(universe, cohort.SourceUniverseReceipt)
    universe = cast("dict[str,object]", universe)
    source_genes = cast("list[dict[str,object]]", source_catalog["genes"])
    present = sum(
        cast("dict[str,object]", row["coverage"])["protein_feature_present"] is True
        for row in source_genes
    )
    if (
        universe["profile_id"] != FEATURE_PROFILE_ID
        or universe["feature_count"] != features
        or universe["feature_axis_digest"] != axis
        or universe["approved_source_protein_genes"] != present
        or universe["literature_anchor_only_count"] != features - present
        or universe["source_protein_rows"]
        != universe["approved_source_protein_genes"]
        + cast("int", universe["unresolved_source_protein_rows"])
        or universe["source_protein_receipt_digest"]
        != sha256_digest(source_build["source_protein_receipt"])
        or universe["selection_uses_external_values"] is not False
        or universe["selection_uses_association_outcomes"] is not False
    ):
        _fail()
    manifest_name = "source-fit/source-census-manifest.json"
    declared = cast("dict[str,object]", report["source_manifest_binding"])
    manifest_data = _read(
        directory,
        manifest_name,
        ArtifactBinding(
            manifest_name, cast("int", declared["bytes"]), cast("str", declared["sha256"])
        ),
    )
    bindings.append(_binding(manifest_name, manifest_data))
    source_manifest = decode_manifest(manifest_data)
    if (
        not _same(declared, checks["source_manifest_binding"])
        or declared["manifest_digest"] != source_manifest.digest
        or source_manifest.digest != report["source_manifest_digest"]
        or source_manifest.digest != checks["source_manifest_digest"]
        or source_manifest.request_digest != protocol["protocol_digest"]
        or source_manifest.feature_axis_digest != axis
        or source_manifest.candidate_digest != source_candidate
        or source_manifest.source_catalog_digest != source_digest
        or source_manifest.source_fold_assignment_digest != fold_digest
        or source_manifest.total_genes != features
        or source_manifest.page_size != protocol["default_source_page_size"]
    ):
        _fail()
    numerical_inputs = cast(
        "dict[str, object]",
        cast(
            "dict[str, object]",
            cast("dict[str, object]", protocol["feature_space_protocol"])["source_input_protocol"],
        )["input_bindings"],
    )
    for label, build in (("source", source_build), ("external", external_build)):
        protein_receipt = cast("dict[str, object]", build["source_protein_receipt"])
        for field, lock_name in (
            ("protein_sha256", label + "_protein"),
            ("sample_map_sha256", label + "_map"),
            ("hgnc_sha256", "hgnc"),
        ):
            if (
                protein_receipt[field]
                != cast("dict[str, object]", numerical_inputs[lock_name])["sha256"]
            ):
                _fail()
    sources, source_counts, cross = _source_records(
        directory, source_manifest, source_catalog, identities, bindings
    )
    if (
        (
            source_counts["accepted"],
            source_counts["abstained"],
            source_counts["input_domain_rejected"],
        )
        != (
            report["source_accepted_genes"],
            report["source_abstained_genes"],
            report["source_input_domain_rejected_genes"],
        )
        or not _same(cross, checks["capacity_fit_cross_table"])
        or not _same(cross, report["capacity_fit_cross_table"])
    ):
        _fail()
    external_manifest_data = _read(directory, "external-score/manifest.json")
    bindings.append(_binding("external-score/manifest.json", external_manifest_data))
    external_manifest = _json(external_manifest_data)
    _embedded(external_manifest, "manifest_digest", report["external_manifest_digest"])
    if (
        external_manifest["source_manifest_digest"] != source_manifest.digest
        or external_manifest["external_document_digest"]
        != external_document["external_document_digest"]
        or external_manifest["feature_axis_digest"] != axis
    ):
        _fail()
    capacities = tuple(
        cast(
            "bool",
            cast("dict[str,object]", row["count_capacity"])["all_five_fold_count_support_possible"],
        )
        for row in source_genes
    )
    external_counts, summary_rows = _external_records(
        directory,
        manifest=external_manifest,
        protocol=protocol,
        identities=identities,
        sources=sources,
        catalog=external_catalog,
        capacities=capacities,
        bindings=bindings,
    )
    if not _same(dict(external_counts), report["external_stage_counts"]):
        _fail()
    data = _read(directory, "summary.csv")
    bindings.append(_binding("summary.csv", data))
    if "sha256:" + hashlib.sha256(data).hexdigest() != report["summary_sha256"]:
        _fail()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
    if reader.fieldnames != list(summary_rows[0]):
        _fail()
    count = 0
    for actual, expected in zip(reader, summary_rows, strict=True):
        for key, value in expected.items():
            text = "" if value is None else str(value)
            if actual[key] != text and not (
                type(value) is float and value == 0 and actual[key] in ("0.0", "-0.0")
            ):
                _fail()
        count += 1
    if count != features:
        _fail()
    progress_expected = {
        "profile_id": BASELINE_PROFILE_ID,
        "protocol_digest": protocol["protocol_digest"],
        "phase": "complete",
        "total_genes": features,
        "source_attempted": features,
        "source_accepted": source_counts["accepted"],
        "source_abstained": source_counts["abstained"],
        "source_input_domain_rejected": source_counts["input_domain_rejected"],
        "external_genes_processed": features,
        "external_evaluator_attempted": external_counts["external_evaluator_attempted"],
        "external_accepted": external_counts["external_result_accepted"],
        "external_measurements_read": True,
        "complete": True,
    }
    if not _same(progress, progress_expected):
        _fail()
    for prefix in ("source-fit/", "external-score/"):
        if (
            sum(binding.bytes for binding in bindings if binding.relative_path.startswith(prefix))
            > MAX_PHASE_BYTES
        ):
            _fail()
    immutable_bindings = tuple(sorted(bindings, key=lambda binding: binding.relative_path))
    if len({binding.relative_path for binding in immutable_bindings}) != len(
        immutable_bindings
    ) or _tree(directory) != {binding.relative_path for binding in immutable_bindings}:
        _fail()
    receipt = BaselineCensusReceipt(
        PROFILE_ID,
        BASELINE_PROFILE_ID,
        protocol_lock,
        evaluation_lock,
        require_digest(protocol["protocol_digest"]),
        require_digest(report["report_digest"]),
        require_digest(
            cast("dict[str,object]", protocol["feature_space_protocol"])[
                "source_input_protocol_digest"
            ]
        ),
        fold_digest,
        axis,
        source_manifest.digest,
        require_digest(external_manifest["manifest_digest"]),
        features,
        source_cases,
        external_cases,
        len(source_manifest.pages),
        len(cast("list[object]", external_manifest["pages"])),
        len(immutable_bindings),
        sha256_digest(tuple(asdict(binding) for binding in immutable_bindings)),
    )
    return BaselineCensus(
        _CONSTRUCTION_TOKEN,
        bindings=immutable_bindings,
        protocol=protocol_data,
        report=report_data,
        receipt=receipt,
    )


def load_baseline_census(
    *, directory: Path, protocol_lock: SourceLock, evaluation_lock: SourceLock
) -> BaselineCensus:
    """Verify all inherited aggregate bytes; do not load measurements or fit models.

    Caller-provided locks establish local integrity and replay, not issuer trust.
    The new runner must additionally recreate the old numerical protocol from its
    runtime admitted metadata before numerical execution. No outcome filters the
    baseline axis or the exact complete artifact inventory.
    """
    try:
        return _load_baseline(directory, protocol_lock, evaluation_lock)
    except ExecutionBaselineError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ExecutionBaselineError("locked census baseline could not be admitted") from None


__all__ = ["BaselineCensus", "load_baseline_census"]
