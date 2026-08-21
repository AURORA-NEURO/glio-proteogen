"""Bounded multi-run research evidence with explicit missingness and QC."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from hashlib import sha256
from math import isfinite, log2
from statistics import median
from typing import cast

from .cohort_provenance import CohortSourceManifest
from .evidence import EvidenceBundle, EvidenceQuality, EvidenceRecord, aggregate_evidence
from .pipeline import ResearchRunRequest, ResearchRunResult, run_research_protein_inference

MAX_COHORT_SAMPLES = 32
_NORMALIZATION_POLICIES = {"none", "within_label_median_v1"}
_MIN_LABEL_REPLICATES = 2
__all__ = [
    "CohortGroupQc",
    "CohortLabelContrast",
    "CohortLabelGroupEvidence",
    "CohortLabelQc",
    "CohortQcPolicy",
    "CohortSampleQc",
    "CohortSampleScale",
    "ResearchCohortRequest",
    "ResearchCohortResult",
    "ResearchCohortSample",
    "aggregate_cohort_evidence",
    "replay_research_cohort",
    "run_research_cohort",
]


def _label(value: str, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 128
        or value != value.strip()
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field} must be a bounded opaque identifier")
    return value


@dataclass(frozen=True, slots=True)
class ResearchCohortSample:
    """One independently replayable run in a cohort."""

    sample_id: str
    request: ResearchRunRequest
    cohort_label: str = "default"
    replicate_label: str = "replicate-1"

    def __post_init__(self) -> None:
        if not isinstance(self.request, ResearchRunRequest):
            raise TypeError("request must be a ResearchRunRequest")
        _label(self.sample_id, "sample_id")
        _label(self.cohort_label, "cohort_label")
        _label(self.replicate_label, "replicate_label")
        if self.request.sample_id != self.sample_id:
            raise ValueError("sample_id must match the embedded run request")


@dataclass(frozen=True, slots=True)
class _CohortLabelSample:
    """Minimal label metadata used to replay cohort projections without raw requests."""

    sample_id: str
    cohort_label: str

    def __post_init__(self) -> None:
        _label(self.sample_id, "sample_id")
        _label(self.cohort_label, "cohort_label")


@dataclass(frozen=True, slots=True)
class CohortQcPolicy:
    """Caller-declared descriptive QC gate; it never infers a biological label."""

    min_replicates: int = 2
    max_missingness_rate: float = 0.5
    min_observed_groups: int = 1

    def __post_init__(self) -> None:
        if (
            type(self.min_replicates) is not int
            or not 1 <= self.min_replicates <= MAX_COHORT_SAMPLES
        ):
            raise ValueError("min_replicates is outside the bounded range")
        if (
            type(self.max_missingness_rate) is not float
            or not isfinite(self.max_missingness_rate)
            or not 0.0 <= self.max_missingness_rate <= 1.0
        ):
            raise ValueError("max_missingness_rate must be a finite fraction")
        if type(self.min_observed_groups) is not int or not self.min_observed_groups >= 0:
            raise ValueError("min_observed_groups must be a non-negative integer")

    def as_dict(self) -> dict[str, object]:
        return {
            "max_missingness_rate": self.max_missingness_rate,
            "min_observed_groups": self.min_observed_groups,
            "min_replicates": self.min_replicates,
        }


@dataclass(frozen=True, slots=True)
class ResearchCohortRequest:
    """Caller-declared, configuration-compatible set of research runs."""

    samples: tuple[ResearchCohortSample, ...]
    provenance_policy: str = "homogeneous"
    normalization_policy: str = "none"
    qc_policy: CohortQcPolicy = CohortQcPolicy()
    source_manifest: CohortSourceManifest | None = None

    def __post_init__(self) -> None:
        if type(self.samples) is not tuple or any(
            not isinstance(sample, ResearchCohortSample) for sample in self.samples
        ):
            raise TypeError("samples must be a tuple of ResearchCohortSample values")
        if self.provenance_policy not in {
            "homogeneous",
            "local_only",
            "external_same_study",
            "mixed_declared",
        }:
            raise ValueError("provenance_policy is not supported")
        if self.normalization_policy not in _NORMALIZATION_POLICIES:
            raise ValueError("normalization_policy is not supported")
        if not isinstance(self.qc_policy, CohortQcPolicy):
            raise TypeError("qc_policy must be a CohortQcPolicy")
        if self.source_manifest is not None and not isinstance(
            self.source_manifest, CohortSourceManifest
        ):
            raise TypeError("source_manifest must be a CohortSourceManifest")
        if not 2 <= len(self.samples) <= MAX_COHORT_SAMPLES:
            raise ValueError("cohort sample count is outside the bounded range")
        sample_ids = tuple(sample.sample_id for sample in self.samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("cohort sample IDs must be unique")
        replicate_keys = tuple(
            (sample.cohort_label, sample.replicate_label) for sample in self.samples
        )
        if len(replicate_keys) != len(set(replicate_keys)):
            raise ValueError("cohort replicate labels must be unique within each cohort")


@dataclass(frozen=True, slots=True)
class CohortSampleQc:
    sample_id: str
    cohort_label: str
    replicate_label: str
    spectra_seen: int
    ms2_spectra_seen: int
    accepted_psms: int
    quantified_groups: int
    missing_groups: int
    missingness_rate: float
    decoy_winners: int
    collision_winners: int
    max_precursor_error_ppm: float | None
    normalization_scale: float | None = None
    normalization_status: str = "not_applied"

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted_psms": self.accepted_psms,
            "cohort_label": self.cohort_label,
            "collision_winners": self.collision_winners,
            "decoy_winners": self.decoy_winners,
            "max_precursor_error_ppm": self.max_precursor_error_ppm,
            "missing_groups": self.missing_groups,
            "missingness_rate": self.missingness_rate,
            "ms2_spectra_seen": self.ms2_spectra_seen,
            "quantified_groups": self.quantified_groups,
            "replicate_label": self.replicate_label,
            "sample_id": self.sample_id,
            "spectra_seen": self.spectra_seen,
            "normalization_scale": self.normalization_scale,
            "normalization_status": self.normalization_status,
        }


@dataclass(frozen=True, slots=True)
class CohortGroupQc:
    group_accessions: tuple[str, ...]
    observed_samples: int
    missing_samples: int
    missingness_rate: float
    median_intensity: float | None
    mad_intensity: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "group_accessions": list(self.group_accessions),
            "mad_intensity": self.mad_intensity,
            "median_intensity": self.median_intensity,
            "missing_samples": self.missing_samples,
            "missingness_rate": self.missingness_rate,
            "observed_samples": self.observed_samples,
        }


@dataclass(frozen=True, slots=True)
class CohortSampleScale:
    """Auditable sample-level scale derived from positive shared groups only."""

    sample_id: str
    cohort_label: str
    scale_factor: float | None
    overlap_groups: int
    positive_groups: int
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "cohort_label": self.cohort_label,
            "overlap_groups": self.overlap_groups,
            "positive_groups": self.positive_groups,
            "sample_id": self.sample_id,
            "scale_factor": self.scale_factor,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class CohortLabelQc:
    """Label-local descriptive QC; labels are caller metadata, never inferred biology."""

    cohort_label: str
    sample_count: int
    replicate_count: int
    observed_cells: int
    missing_cells: int
    missingness_rate: float
    median_intensity: float | None
    mad_intensity: float | None
    status: str
    normalization_status: str = "not_applied"
    independent_replicates: int = 0
    technical_replicates: int = 0
    unknown_replicates: int = 0
    duplicate_sources: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "cohort_label": self.cohort_label,
            "mad_intensity": self.mad_intensity,
            "median_intensity": self.median_intensity,
            "missing_cells": self.missing_cells,
            "missingness_rate": self.missingness_rate,
            "observed_cells": self.observed_cells,
            "replicate_count": self.replicate_count,
            "sample_count": self.sample_count,
            "status": self.status,
            "normalization_status": self.normalization_status,
            "independent_replicates": self.independent_replicates,
            "technical_replicates": self.technical_replicates,
            "unknown_replicates": self.unknown_replicates,
            "duplicate_sources": self.duplicate_sources,
        }


@dataclass(frozen=True, slots=True)
class CohortLabelGroupEvidence:
    """Label-by-group descriptive evidence with explicit abstention states."""

    cohort_label: str
    group_accessions: tuple[str, ...]
    observed_replicates: int
    missing_replicates: int
    missingness_rate: float
    median_normalized_intensity: float | None
    mad_normalized_intensity: float | None
    status: str
    independent_observed_replicates: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "cohort_label": self.cohort_label,
            "group_accessions": list(self.group_accessions),
            "mad_normalized_intensity": self.mad_normalized_intensity,
            "median_normalized_intensity": self.median_normalized_intensity,
            "missing_replicates": self.missing_replicates,
            "missingness_rate": self.missingness_rate,
            "observed_replicates": self.observed_replicates,
            "status": self.status,
            "independent_observed_replicates": self.independent_observed_replicates,
        }


@dataclass(frozen=True, slots=True)
class CohortLabelContrast:
    """Descriptive contrast between two caller-declared cohort labels.

    This is an evidence projection over normalized group medians, not a
    differential-expression test.  Labels are supplied by the caller and are
    never inferred from values, disease metadata, or protein names.  A ratio
    and log2 ratio are emitted only when both label medians are positive,
    both upstream label-by-group QC statuses are descriptive, and each label has
    at least one independent observed replicate for the group; missing,
    non-positive, non-finite-derived, or unverified-QC cells remain explicit
    abstentions rather than imputed effects.
    """

    cohort_label_a: str
    cohort_label_b: str
    group_accessions: tuple[str, ...]
    label_a_median: float | None
    label_b_median: float | None
    median_difference: float | None
    median_ratio: float | None
    log2_median_ratio: float | None
    label_a_observed_replicates: int
    label_b_observed_replicates: int
    label_a_missingness_rate: float
    label_b_missingness_rate: float
    label_a_status: str
    label_b_status: str
    status: str

    def __post_init__(self) -> None:
        _label(self.cohort_label_a, "cohort_label_a")
        _label(self.cohort_label_b, "cohort_label_b")
        if self.cohort_label_a >= self.cohort_label_b:
            raise ValueError("contrast labels must be in strict lexical order")
        if not self.group_accessions or any(
            not isinstance(accession, str) or not accession for accession in self.group_accessions
        ):
            raise ValueError("contrast must declare a non-empty group accession tuple")
        if (
            type(self.label_a_observed_replicates) is not int
            or self.label_a_observed_replicates < 0
        ):
            raise ValueError("label_a_observed_replicates must be non-negative")
        if (
            type(self.label_b_observed_replicates) is not int
            or self.label_b_observed_replicates < 0
        ):
            raise ValueError("label_b_observed_replicates must be non-negative")
        for value, field_name in (
            (self.label_a_missingness_rate, "label_a_missingness_rate"),
            (self.label_b_missingness_rate, "label_b_missingness_rate"),
        ):
            if type(value) not in (int, float) or not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be a finite fraction")
        if self.status not in {
            "descriptive",
            "abstained_label_qc",
            "abstained_missing_or_nonpositive",
            "abstained_nonfinite_derived",
        }:
            raise ValueError("contrast status is not supported")
        nonnegative = (
            self.label_a_median,
            self.label_b_median,
            self.median_ratio,
        )
        if any(value is not None and (not isfinite(value) or value < 0) for value in nonnegative):
            raise ValueError("contrast median fields must be finite and non-negative")
        if any(
            value is not None and not isfinite(value)
            for value in (self.median_difference, self.log2_median_ratio)
        ):
            raise ValueError("contrast derived fields must be finite")
        if (
            self.median_difference is not None
            and self.label_a_median is not None
            and self.label_b_median is not None
            and self.median_difference != self.label_a_median - self.label_b_median
        ):
            raise ValueError("contrast difference is not derived from label medians")
        if self.status == "descriptive":
            if (
                self.label_a_median is None
                or self.label_b_median is None
                or self.label_a_median <= 0
                or self.label_b_median <= 0
                or self.median_ratio is None
                or self.log2_median_ratio is None
            ):
                raise ValueError("descriptive contrast requires two positive medians")
            if self.label_a_status != "descriptive" or self.label_b_status != "descriptive":
                raise ValueError("descriptive contrast requires descriptive label QC")
            expected_ratio = self.label_a_median / self.label_b_median
            expected_log_ratio = log2(expected_ratio)
            if self.median_ratio != expected_ratio:
                raise ValueError("contrast ratio is not derived from label medians")
            if self.log2_median_ratio != expected_log_ratio:
                raise ValueError("contrast log2 ratio is not derived from label medians")
        elif any(
            value is not None
            for value in (self.median_difference, self.median_ratio, self.log2_median_ratio)
        ):
            raise ValueError("abstained contrast cannot carry a derived effect")

    def as_dict(self) -> dict[str, object]:
        return {
            "cohort_label_a": self.cohort_label_a,
            "cohort_label_b": self.cohort_label_b,
            "group_accessions": list(self.group_accessions),
            "label_a_median": self.label_a_median,
            "label_a_missingness_rate": self.label_a_missingness_rate,
            "label_a_observed_replicates": self.label_a_observed_replicates,
            "label_a_status": self.label_a_status,
            "label_b_median": self.label_b_median,
            "label_b_missingness_rate": self.label_b_missingness_rate,
            "label_b_observed_replicates": self.label_b_observed_replicates,
            "label_b_status": self.label_b_status,
            "log2_median_ratio": self.log2_median_ratio,
            "median_difference": self.median_difference,
            "median_ratio": self.median_ratio,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ResearchCohortResult:
    """Content-addressed sample-by-group matrix with explicit missing cells."""

    sample_ids: tuple[str, ...]
    group_accessions: tuple[tuple[str, ...], ...]
    matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...]
    sample_qc: tuple[CohortSampleQc, ...]
    group_qc: tuple[CohortGroupQc, ...]
    child_result_digests: tuple[tuple[str, str], ...]
    configuration: tuple[tuple[str, object], ...]
    result_digest: str
    raw_matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...] = ()
    normalized_matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...] = ()
    sample_scales: tuple[CohortSampleScale, ...] = ()
    label_qc: tuple[CohortLabelQc, ...] = ()
    label_group_evidence: tuple[CohortLabelGroupEvidence, ...] = ()
    source_manifest: CohortSourceManifest | None = None
    evidence_bundle: EvidenceBundle | None = None
    label_contrasts: tuple[CohortLabelContrast, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "child_result_digests": [list(item) for item in self.child_result_digests],
            "configuration": dict(self.configuration),
            "group_accessions": [list(item) for item in self.group_accessions],
            "group_qc": [item.as_dict() for item in self.group_qc],
            "matrix": [[list(group), list(values)] for group, values in self.matrix],
            "normalized_matrix": [
                [list(group), list(values)] for group, values in self.normalized_matrix
            ],
            "raw_matrix": [[list(group), list(values)] for group, values in self.raw_matrix],
            "result_digest": self.result_digest,
            "sample_ids": list(self.sample_ids),
            "sample_qc": [item.as_dict() for item in self.sample_qc],
            "sample_scales": [item.as_dict() for item in self.sample_scales],
            "label_qc": [item.as_dict() for item in self.label_qc],
            "label_group_evidence": [item.as_dict() for item in self.label_group_evidence],
            "label_contrasts": [item.as_dict() for item in self.label_contrasts],
            "source_manifest": (
                self.source_manifest.as_dict() if self.source_manifest is not None else None
            ),
            "evidence_bundle": (
                self.evidence_bundle.as_dict() if self.evidence_bundle is not None else None
            ),
        }


def _digest(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _build_evidence_bundle(
    *,
    sample_ids: tuple[str, ...],
    group_accessions: tuple[tuple[str, ...], ...],
    matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...],
    raw_matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...],
    normalized_matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...],
    sample_qc: tuple[CohortSampleQc, ...],
    group_qc: tuple[CohortGroupQc, ...],
    sample_scales: tuple[CohortSampleScale, ...],
    label_qc: tuple[CohortLabelQc, ...],
    label_group_evidence: tuple[CohortLabelGroupEvidence, ...],
    label_contrasts: tuple[CohortLabelContrast, ...],
    source_manifest: CohortSourceManifest,
    configuration: tuple[tuple[str, object], ...],
) -> EvidenceBundle:
    """Create independently verifiable matrix, QC, and provenance receipts.

    The cohort result already contains these projections, but previously they
    had no inner evidence identities.  Splitting the receipt by scientific
    responsibility makes it possible to archive or verify matrix values, QC
    decisions, and external-source provenance independently while retaining one
    deterministic outer digest.  This is descriptive research evidence only.
    """

    total_cells = sum(len(values) for _, values in matrix)
    observed_cells = sum(value is not None for _, values in matrix for value in values)
    matrix_completeness = observed_cells / total_cells if total_cells else 0.0
    independent_sources = source_manifest.source_identity_counts(sample_ids)["unique_sources"]
    matrix_quality = EvidenceQuality(
        status="computed",
        auditability=1.0,
        completeness=matrix_completeness,
        independent_sources=independent_sources,
        basis="deterministic_matrix_projection",
    )
    qc_quality = EvidenceQuality(
        status="computed",
        auditability=1.0,
        completeness=1.0 if sample_qc and group_qc else 0.0,
        independent_sources=independent_sources,
        basis="deterministic_qc_projection",
    )
    provenance_quality = EvidenceQuality(
        status="verified",
        auditability=1.0,
        completeness=1.0,
        independent_sources=independent_sources,
        basis="source_manifest_bytes_and_receipts",
    )
    contrast_quality = EvidenceQuality(
        status="computed",
        auditability=1.0,
        completeness=1.0 if label_contrasts else 0.0,
        independent_sources=independent_sources,
        basis="caller_label_descriptive_median_contrasts_no_imputation",
    )
    records = (
        EvidenceRecord.create(
            "cohort.matrix.v1",
            "glio_proteogen.research.cohort",
            "computed_matrix",
            {
                "group_accessions": [list(item) for item in group_accessions],
                "matrix": [[list(group), list(values)] for group, values in matrix],
                "normalized_matrix": [
                    [list(group), list(values)] for group, values in normalized_matrix
                ],
                "raw_matrix": [[list(group), list(values)] for group, values in raw_matrix],
                "sample_ids": list(sample_ids),
            },
            quality=matrix_quality,
        ),
        EvidenceRecord.create(
            "cohort.qc.v1",
            "glio_proteogen.research.cohort",
            "descriptive_qc",
            {
                "group_qc": [item.as_dict() for item in group_qc],
                "label_group_evidence": [item.as_dict() for item in label_group_evidence],
                "label_qc": [item.as_dict() for item in label_qc],
                "sample_qc": [item.as_dict() for item in sample_qc],
                "sample_scales": [item.as_dict() for item in sample_scales],
            },
            quality=qc_quality,
        ),
        EvidenceRecord.create(
            "cohort.provenance.v1",
            "glio_proteogen.research.cohort",
            "source_provenance",
            {
                "configuration": dict(configuration),
                "source_manifest": source_manifest.as_dict(),
                "source_manifest_digest": source_manifest.digest,
            },
            quality=provenance_quality,
        ),
        EvidenceRecord.create(
            "cohort.contrast.v1",
            "glio_proteogen.research.cohort",
            "descriptive_label_contrast",
            {
                "contrasts": [item.as_dict() for item in label_contrasts],
                "policy": "caller-label-median-difference-ratio-log2-v1-no-imputation",
            },
            quality=contrast_quality,
        ),
    )
    return aggregate_evidence(records)


def aggregate_cohort_evidence(result: ResearchCohortResult) -> EvidenceBundle:
    """Recompute and verify the inner evidence receipt for a cohort result.

    This helper is intentionally separate from replay: it verifies the three
    evidence domains without executing mzML parsing again.  A forged result,
    stale evidence payload, or changed source manifest therefore fails before a
    consumer treats the projection as an auditable cohort receipt.
    """

    if not isinstance(result, ResearchCohortResult):
        raise TypeError("result must be a ResearchCohortResult")
    if result.source_manifest is None:
        raise ValueError("cohort result has no source manifest")
    _validate_matrix_qc_projection(result)
    configuration = dict(result.configuration)
    raw_qc_policy = configuration.get("cohort_qc_policy")
    if not isinstance(raw_qc_policy, dict):
        raise TypeError("cohort QC policy is not reproducible")
    try:
        qc_policy = CohortQcPolicy(**raw_qc_policy)
    except (TypeError, ValueError) as error:
        raise ValueError("cohort QC policy is not reproducible") from error
    normalization_policy = configuration.get("cohort_normalization_policy")
    if normalization_policy not in _NORMALIZATION_POLICIES:
        raise ValueError("cohort normalization policy is not reproducible")
    label_metadata = tuple(
        _CohortLabelSample(item.sample_id, item.cohort_label) for item in result.sample_qc
    )
    (
        expected_normalized_matrix,
        expected_sample_scales,
        expected_label_qc,
        expected_label_group_evidence,
        _,
    ) = _build_label_evidence(
        label_metadata,
        result.group_accessions,
        result.raw_matrix,
        normalization_policy,
        qc_policy,
        result.source_manifest,
    )
    if (
        expected_normalized_matrix != result.normalized_matrix
        or expected_sample_scales != result.sample_scales
        or expected_label_qc != result.label_qc
        or expected_label_group_evidence != result.label_group_evidence
    ):
        raise ValueError("cohort label evidence is not reproducible")
    observed = _build_evidence_bundle(
        sample_ids=result.sample_ids,
        group_accessions=result.group_accessions,
        matrix=result.matrix,
        raw_matrix=result.raw_matrix,
        normalized_matrix=result.normalized_matrix,
        sample_qc=result.sample_qc,
        group_qc=result.group_qc,
        sample_scales=result.sample_scales,
        label_qc=result.label_qc,
        label_group_evidence=result.label_group_evidence,
        label_contrasts=result.label_contrasts,
        source_manifest=result.source_manifest,
        configuration=result.configuration,
    )
    if result.evidence_bundle is None:
        raise ValueError("cohort result has no evidence bundle")
    expected_contrasts = _build_label_contrasts(result.label_group_evidence)
    if expected_contrasts != result.label_contrasts:
        raise ValueError("cohort label contrasts are not reproducible")
    if observed.as_dict() != result.evidence_bundle.as_dict():
        raise ValueError("cohort evidence bundle is not reproducible")
    # The inner bundle can be coherent even when a caller swaps in a complete
    # bundle from another result.  Keep this non-executing verifier bound to the
    # complete outer projection as well, so a stale result digest cannot pass as
    # an auditable cohort receipt.
    expected_payload = result.as_dict()
    expected_digest = expected_payload.pop("result_digest")
    if expected_digest != result.result_digest or _digest(expected_payload) != expected_digest:
        raise ValueError("cohort result digest is invalid")
    return observed


def _compatible_configuration(results: tuple[ResearchRunResult, ...]) -> None:
    if not results:
        raise ValueError("cohort has no run results")
    first = dict(results[0].configuration)
    baseline = {
        key: value
        for key, value in first.items()
        if key
        not in {
            "external_source_id",
            "external_source_sha256",
            "external_pdc_file",
            "external_pdc_response_sha256",
            "external_pdc_receipt",
            "cohort_provenance_policy",
        }
    }
    for result in results[1:]:
        current = dict(result.configuration)
        comparable = {
            key: value
            for key, value in current.items()
            if key
            not in {
                "external_source_id",
                "external_source_sha256",
                "external_pdc_file",
                "external_pdc_response_sha256",
                "external_pdc_receipt",
                "cohort_provenance_policy",
            }
        }
        if comparable != baseline or result.fasta_sha256 != results[0].fasta_sha256:
            raise ValueError("cohort runs must share FASTA and search configuration")


def _source_provenance(result: ResearchRunResult) -> dict[str, object]:
    configuration = dict(result.configuration)
    return {
        "external_source_id": configuration.get("external_source_id"),
        "external_source_sha256": configuration.get("external_source_sha256"),
        "external_pdc_file": configuration.get("external_pdc_file"),
        "external_pdc_response_sha256": configuration.get("external_pdc_response_sha256"),
        "external_pdc_receipt": configuration.get("external_pdc_receipt"),
        "mzml_sha256": result.mzml_sha256,
        "fasta_sha256": result.fasta_sha256,
    }


def _positive(value: float | None) -> bool:
    return value is not None and isfinite(value) and value > 0.0


def _require_positive(value: float | None) -> float:
    if value is None or not isfinite(value) or value <= 0.0:
        raise RuntimeError("normalization shared group was not positive")
    return value


def _median_mad(values: tuple[float, ...]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    center = float(median(values))
    deviations = tuple(abs(value - center) for value in values)
    return center, float(median(deviations)) if deviations else None


def _build_label_contrasts(
    label_group_evidence: tuple[CohortLabelGroupEvidence, ...],
) -> tuple[CohortLabelContrast, ...]:
    """Build bounded pairwise label contrasts from normalized label evidence.

    This deliberately compares caller labels lexically and never treats a label
    as a disease, treatment, or biological class.  The source evidence already
    contains missingness-aware medians; no raw cell is imputed to zero here.
    """

    by_key = {(item.cohort_label, item.group_accessions): item for item in label_group_evidence}
    labels = tuple(sorted({item.cohort_label for item in label_group_evidence}))
    groups = tuple(sorted({item.group_accessions for item in label_group_evidence}))
    contrasts: list[CohortLabelContrast] = []
    for index, label_a in enumerate(labels):
        for label_b in labels[index + 1 :]:
            for group in groups:
                left = by_key[(label_a, group)]
                right = by_key[(label_b, group)]
                left_median = left.median_normalized_intensity
                right_median = right.median_normalized_intensity
                if (
                    left_median is None
                    or right_median is None
                    or not isfinite(left_median)
                    or not isfinite(right_median)
                    or left_median <= 0
                    or right_median <= 0
                ):
                    difference = None
                    ratio = None
                    log_ratio = None
                    status = "abstained_missing_or_nonpositive"
                elif (
                    left.status != "descriptive"
                    or right.status != "descriptive"
                    or left.independent_observed_replicates < 1
                    or right.independent_observed_replicates < 1
                ):
                    difference = None
                    ratio = None
                    log_ratio = None
                    status = "abstained_label_qc"
                else:
                    difference = left_median - right_median
                    ratio = left_median / right_median
                    if not isfinite(difference) or not isfinite(ratio) or ratio <= 0.0:
                        difference = None
                        ratio = None
                        log_ratio = None
                        status = "abstained_nonfinite_derived"
                    else:
                        log_ratio = log2(ratio)
                        if not isfinite(log_ratio):
                            difference = None
                            ratio = None
                            log_ratio = None
                            status = "abstained_nonfinite_derived"
                        else:
                            status = "descriptive"
                contrasts.append(
                    CohortLabelContrast(
                        cohort_label_a=label_a,
                        cohort_label_b=label_b,
                        group_accessions=group,
                        label_a_median=left_median,
                        label_b_median=right_median,
                        median_difference=difference,
                        median_ratio=ratio,
                        log2_median_ratio=log_ratio,
                        label_a_observed_replicates=left.observed_replicates,
                        label_b_observed_replicates=right.observed_replicates,
                        label_a_missingness_rate=left.missingness_rate,
                        label_b_missingness_rate=right.missingness_rate,
                        label_a_status=left.status,
                        label_b_status=right.status,
                        status=status,
                    )
                )
    return tuple(contrasts)


def _build_group_qc(
    matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...],
) -> tuple[CohortGroupQc, ...]:
    """Derive group QC directly from the canonical raw matrix projection."""

    output: list[CohortGroupQc] = []
    for group, row in matrix:
        observed = tuple(value for value in row if value is not None)
        center = float(median(observed)) if observed else None
        deviations = tuple(abs(value - center) for value in observed) if center is not None else ()
        output.append(
            CohortGroupQc(
                group_accessions=group,
                observed_samples=len(observed),
                missing_samples=len(row) - len(observed),
                missingness_rate=(len(row) - len(observed)) / len(row) if row else 1.0,
                median_intensity=center,
                mad_intensity=float(median(deviations)) if deviations else None,
            )
        )
    return tuple(output)


def _validate_matrix_qc_projection(result: ResearchCohortResult) -> None:
    """Reject a receipt whose QC fields are not derived from its matrix."""

    if result.sample_ids != tuple(sorted(result.sample_ids)):
        raise ValueError("cohort sample IDs are not canonically ordered")
    groups = tuple(group for group, _ in result.matrix)
    if groups != result.group_accessions:
        raise ValueError("cohort matrix groups are not reproducible")
    if result.raw_matrix != result.matrix:
        raise ValueError("cohort raw matrix is not reproducible")
    if tuple(group for group, _ in result.normalized_matrix) != groups:
        raise ValueError("cohort normalized matrix groups are not reproducible")
    for matrix_name, matrix in (
        ("matrix", result.matrix),
        ("normalized matrix", result.normalized_matrix),
    ):
        for _, values in matrix:
            if len(values) != len(result.sample_ids):
                raise ValueError(f"cohort {matrix_name} row length is not reproducible")
            if any(
                value is not None
                and (type(value) not in (int, float) or not isfinite(value) or value < 0)
                for value in values
            ):
                raise ValueError(f"cohort {matrix_name} contains invalid intensity")
    if tuple(item.sample_id for item in result.sample_qc) != result.sample_ids:
        raise ValueError("cohort sample QC is not canonically ordered")
    expected_group_qc = _build_group_qc(result.matrix)
    if expected_group_qc != result.group_qc:
        raise ValueError("cohort group QC is not derived from the matrix")
    scale_by_sample = {item.sample_id: item for item in result.sample_scales}
    if (
        tuple(item.sample_id for item in result.sample_scales) != result.sample_ids
        or set(scale_by_sample) != set(result.sample_ids)
        or len(scale_by_sample) != len(result.sample_scales)
    ):
        raise ValueError("cohort sample scales are not reproducible")
    for index, item in enumerate(result.sample_qc):
        observed = sum(
            value is not None for _, values in result.matrix for value in (values[index],)
        )
        missing = len(result.group_accessions) - observed
        expected_missingness = (
            missing / len(result.group_accessions) if result.group_accessions else 1.0
        )
        if (
            item.quantified_groups != observed
            or item.missing_groups != missing
            or item.missingness_rate != expected_missingness
        ):
            raise ValueError("cohort sample QC is not derived from the matrix")
        scale = scale_by_sample[item.sample_id]
        if (
            item.normalization_scale != scale.scale_factor
            or item.normalization_status != scale.status
        ):
            raise ValueError("cohort sample QC is not linked to sample scales")


def _build_label_evidence(  # noqa: PLR0915, PLR0917
    ordered_samples: tuple[ResearchCohortSample | _CohortLabelSample, ...],
    groups: tuple[tuple[str, ...], ...],
    raw_matrix: tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...],
    policy: str,
    qc_policy: CohortQcPolicy,
    source_manifest: CohortSourceManifest,
) -> tuple[
    tuple[tuple[tuple[str, ...], tuple[float | None, ...]], ...],
    tuple[CohortSampleScale, ...],
    tuple[CohortLabelQc, ...],
    tuple[CohortLabelGroupEvidence, ...],
    tuple[str, ...],
]:
    """Normalize only within caller labels and retain every abstention explicitly."""

    labels: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(ordered_samples):
        labels[sample.cohort_label].append(index)
    # The matrix is group-major; transpose once into sample-major rows.
    sample_rows: list[dict[tuple[str, ...], float | None]] = [
        {group: values[index] for group, values in raw_matrix}
        for index in range(len(ordered_samples))
    ]
    normalized_rows = [dict(row) for row in sample_rows]
    scale_values: list[CohortSampleScale | None] = [None] * len(ordered_samples)
    label_status: dict[str, str] = {}
    label_qc: list[CohortLabelQc] = []
    label_evidence: list[CohortLabelGroupEvidence] = []

    for label in sorted(labels):
        indices = tuple(labels[label])
        bindings = tuple(
            source_manifest.for_sample(ordered_samples[index].sample_id) for index in indices
        )
        biological_indices = tuple(
            index
            for index in indices
            if source_manifest.for_sample(ordered_samples[index].sample_id).replicate_kind
            == "biological"
        )
        technical_indices = tuple(
            index
            for index in indices
            if source_manifest.for_sample(ordered_samples[index].sample_id).replicate_kind
            == "technical"
        )
        biological_sources = {
            source_manifest.for_sample(ordered_samples[index].sample_id).source_identity
            for index in biological_indices
        }
        technical_count = sum(item.replicate_kind == "technical" for item in bindings)
        unknown_count = sum(item.replicate_kind == "unknown" for item in bindings)
        duplicate_count = len(bindings) - len({item.source_identity for item in bindings})
        support_indices = biological_indices
        shared = tuple(
            group
            for group in groups
            if all(_positive(sample_rows[index].get(group)) for index in support_indices)
        )
        positive_counts = {
            index: sum(_positive(sample_rows[index].get(group)) for group in groups)
            for index in indices
        }
        if policy == "none":
            status = "not_applied"
            factors: dict[int, float | None] = dict.fromkeys(indices, 1.0)
        elif unknown_count:
            status = "abstained_unknown_independence"
            factors = dict.fromkeys(indices)
        elif len(biological_sources) < _MIN_LABEL_REPLICATES:
            status = "abstained_insufficient_replicates"
            factors = dict.fromkeys(indices)
        elif not shared:
            status = "abstained_insufficient_overlap"
            factors = dict.fromkeys(indices)
        else:
            sample_centers = {
                index: float(
                    median(
                        tuple(
                            _require_positive(sample_rows[index][group])
                            for group in shared
                            if sample_rows[index][group] is not None
                        )
                    )
                )
                for index in support_indices
            }
            target = float(median(tuple(sample_centers.values())))
            factors = {
                index: (
                    target / sample_centers[index]
                    if isfinite(sample_centers[index]) and sample_centers[index] > 0
                    else None
                )
                if index in sample_centers
                else None
                for index in indices
            }
            if any(
                factor is None or not isfinite(factor)
                for factor in (factors[index] for index in support_indices)
            ):
                status = "abstained_invalid_scale"
                factors = dict.fromkeys(indices)
            else:
                status = "normalized"
        observed_groups = sum(
            any(_positive(sample_rows[index].get(group)) for index in indices) for group in groups
        )
        total_cells = len(indices) * len(groups)
        observed_cells = sum(
            _positive(sample_rows[index].get(group)) for index in indices for group in groups
        )
        missingness_rate = (total_cells - observed_cells) / total_cells if total_cells else 1.0
        if status in {"normalized", "not_applied"}:
            if missingness_rate > qc_policy.max_missingness_rate:
                qc_status = "abstained_missingness"
            elif observed_groups < qc_policy.min_observed_groups:
                qc_status = "abstained_insufficient_observed_groups"
            elif unknown_count:
                qc_status = "unverified_independence"
            elif len(biological_sources) < qc_policy.min_replicates:
                qc_status = "abstained_insufficient_replicates"
            else:
                qc_status = "descriptive"
        else:
            qc_status = status
        label_status[label] = qc_status
        for index in indices:
            factor = factors[index]
            if factor is None:
                normalized_rows[index] = dict.fromkeys(groups)
            elif policy == "none":
                normalized_rows[index] = dict(sample_rows[index])
            else:
                normalized_rows[index] = {
                    group: value * factor if value is not None and _positive(value) else value
                    for group, value in sample_rows[index].items()
                }
            scale_values[index] = CohortSampleScale(
                sample_id=ordered_samples[index].sample_id,
                cohort_label=label,
                scale_factor=factor,
                overlap_groups=len(shared),
                positive_groups=positive_counts[index],
                status=(
                    "abstained_technical_replicate"
                    if index in technical_indices and factor is None and status == "normalized"
                    else status
                ),
            )
        # A no-normalization request is an identity projection, not a claim that
        # QC passed.  Preserve that caller-requested projection (and its scale
        # receipts) while retaining the abstained QC status that gates derived
        # label evidence.  Support-dependent normalization policies continue to
        # null their projection when a QC gate fails.
        if qc_status.startswith("abstained") and policy != "none":
            for index in indices:
                normalized_rows[index] = dict.fromkeys(groups)
        label_values = tuple(
            float(value)
            for index in indices
            for value in normalized_rows[index].values()
            if value is not None and _positive(value)
        )
        label_center, label_mad = _median_mad(label_values)
        label_qc.append(
            CohortLabelQc(
                cohort_label=label,
                sample_count=len(indices),
                replicate_count=len(indices),
                observed_cells=observed_cells,
                missing_cells=total_cells - observed_cells,
                missingness_rate=(total_cells - observed_cells) / total_cells
                if total_cells
                else 1.0,
                median_intensity=label_center,
                mad_intensity=label_mad,
                status=qc_status,
                normalization_status=status,
                independent_replicates=len(biological_sources),
                technical_replicates=technical_count,
                unknown_replicates=unknown_count,
                duplicate_sources=duplicate_count,
            )
        )
        for group in groups:
            values = tuple(normalized_rows[index].get(group) for index in indices)
            observed = tuple(
                float(value) for value in values if value is not None and _positive(value)
            )
            center, mad = _median_mad(observed)
            independent_observed = sum(
                _positive(sample_rows[index].get(group)) for index in biological_indices
            )
            evidence_status = (
                "abstained_insufficient_replicates"
                if qc_status == "descriptive" and independent_observed < 1
                else qc_status
            )
            label_evidence.append(
                CohortLabelGroupEvidence(
                    cohort_label=label,
                    group_accessions=group,
                    observed_replicates=len(observed),
                    missing_replicates=len(values) - len(observed),
                    missingness_rate=(len(values) - len(observed)) / len(values) if values else 1.0,
                    median_normalized_intensity=center,
                    mad_normalized_intensity=mad,
                    status=evidence_status,
                    independent_observed_replicates=independent_observed,
                )
            )
    if any(value is None for value in scale_values):
        raise RuntimeError("cohort normalization did not produce one scale record per sample")
    normalized_matrix = tuple(
        (group, tuple(normalized_rows[index].get(group) for index in range(len(ordered_samples))))
        for group in groups
    )
    return (
        normalized_matrix,
        tuple(value for value in scale_values if value is not None),
        tuple(label_qc),
        tuple(label_evidence),
        tuple(label_status[label] for label in sorted(label_status)),
    )


def _validate_provenance_policy(
    request: ResearchCohortRequest, samples: tuple[ResearchCohortSample, ...]
) -> None:
    receipts = tuple(sample.request.external_pdc_receipt for sample in samples)
    declared_external = tuple(
        sample.request.external_pdc_file is not None or receipt is not None
        for sample, receipt in zip(samples, receipts, strict=True)
    )
    bound = tuple(receipt is not None for receipt in receipts)
    policy = request.provenance_policy

    def validate_metadata_snapshots() -> None:
        """Reject cohorts that silently combine metadata snapshot versions."""

        if request.source_manifest is None:
            return
        digests = {
            request.source_manifest.for_sample(sample.sample_id).metadata_snapshot_digest
            for sample in samples
        }
        if len(digests) > 1:
            raise ValueError("cohort metadata snapshot digests must be identical or all absent")

    if policy == "local_only" and any(declared_external):
        raise ValueError("local_only cohorts cannot contain external PDC declarations")
    if policy == "external_same_study":
        if not all(declared_external) or not all(bound):
            raise ValueError("external_same_study requires a receipt for every sample")
        studies = {receipt.file.study_id for receipt in receipts if receipt is not None}
        responses = {receipt.response_sha256 for receipt in receipts if receipt is not None}
        if len(studies) != 1 or len(responses) != 1:
            raise ValueError("external_same_study requires one study and one catalog response")
    elif policy == "homogeneous":
        if any(declared_external) and not all(declared_external):
            raise ValueError("homogeneous cohorts cannot mix local and catalog-attested samples")
        if all(declared_external) and not all(bound):
            raise ValueError("homogeneous external cohorts require catalog receipts")
        if all(bound) and receipts:
            studies = {receipt.file.study_id for receipt in receipts if receipt is not None}
            responses = {receipt.response_sha256 for receipt in receipts if receipt is not None}
            if len(studies) != 1 or len(responses) != 1:
                raise ValueError(
                    "homogeneous PDC cohorts require one study and one catalog response"
                )
    validate_metadata_snapshots()


def _source_manifest(
    request: ResearchCohortRequest, ordered_samples: tuple[ResearchCohortSample, ...]
) -> CohortSourceManifest:
    if request.source_manifest is not None:
        manifest = request.source_manifest
    else:
        manifest = CohortSourceManifest.from_requests(
            tuple(sample.request for sample in ordered_samples)
        )
    manifest.validate_against_samples(
        tuple(sample.sample_id for sample in ordered_samples),
        tuple(sample.request for sample in ordered_samples),
        tuple(
            sha256(cast("bytes", sample.request.mzml_source)).hexdigest()
            for sample in ordered_samples
        ),
    )
    manifest.validate_independence()
    return manifest


def run_research_cohort(request: ResearchCohortRequest) -> ResearchCohortResult:
    """Run compatible samples and emit a deterministic matrix without imputation."""

    ordered_samples = tuple(sorted(request.samples, key=lambda item: item.sample_id))
    _validate_provenance_policy(request, ordered_samples)
    # Provenance policy and source-manifest validation are admission boundaries.
    # Reject mixed, unattested, snapshot-incompatible, or byte-mismatched cohorts
    # before parsing or traversing raw mzML; otherwise a rejected source could
    # still trigger scientific computation before the safe failure.
    source_manifest = _source_manifest(request, ordered_samples)
    child = tuple(run_research_protein_inference(item.request) for item in ordered_samples)
    _compatible_configuration(child)
    sample_ids = tuple(item.sample_id for item in ordered_samples)
    groups = tuple(
        sorted({group.accessions for result in child for group in result.protein_groups})
    )
    values_by_sample: list[dict[tuple[str, ...], float | None]] = []
    qc: list[CohortSampleQc] = []
    for sample, result in zip(ordered_samples, child, strict=True):
        values: dict[tuple[str, ...], float | None] = {}
        for quant in result.protein_group_quantifications:
            values[quant.group_accessions] = (
                quant.primary_intensity if quant.status == "quantified" else None
            )
        values_by_sample.append(values)
        missing = sum(group not in values or values[group] is None for group in groups)
        diagnostics = dict(result.search_diagnostics)
        raw_max_precursor_error = diagnostics.get("max_precursor_error_ppm")
        qc.append(
            CohortSampleQc(
                sample_id=sample.sample_id,
                cohort_label=sample.cohort_label,
                replicate_label=sample.replicate_label,
                spectra_seen=result.spectra_seen,
                ms2_spectra_seen=result.ms2_spectra_seen,
                accepted_psms=len(result.accepted_psms),
                quantified_groups=sum(value is not None for value in values.values()),
                missing_groups=missing,
                missingness_rate=missing / len(groups) if groups else 1.0,
                decoy_winners=result.fdr_summary.decoy_winners if result.fdr_summary else 0,
                collision_winners=result.fdr_summary.collision_winners if result.fdr_summary else 0,
                max_precursor_error_ppm=(
                    float(raw_max_precursor_error)
                    if isinstance(raw_max_precursor_error, (int, float))
                    else None
                ),
            )
        )
    matrix = tuple(
        (group, tuple(values.get(group) for values in values_by_sample)) for group in groups
    )
    normalized_matrix, sample_scales, label_qc, label_group_evidence, _ = _build_label_evidence(
        ordered_samples,
        groups,
        matrix,
        request.normalization_policy,
        request.qc_policy,
        source_manifest,
    )
    label_contrasts = _build_label_contrasts(label_group_evidence)
    scale_by_sample = {item.sample_id: item for item in sample_scales}
    qc = [
        replace(
            item,
            normalization_scale=scale_by_sample[item.sample_id].scale_factor,
            normalization_status=scale_by_sample[item.sample_id].status,
        )
        for item in qc
    ]
    group_qc = _build_group_qc(matrix)
    configuration = tuple(
        sorted(
            {
                "cohort_version": "research-cohort-3",
                "cohort_provenance_policy": request.provenance_policy,
                "cohort_normalization_policy": request.normalization_policy,
                "cohort_normalization_version": (
                    "none" if request.normalization_policy == "none" else "within-label-median-v1"
                ),
                "cohort_qc_policy": request.qc_policy.as_dict(),
                "cohort_contrast_version": "caller-label-median-contrast-v1",
                "cohort_source_manifest_digest": source_manifest.digest,
                "cohort_source_manifest": source_manifest.as_dict(),
                "sample_ids": list(sample_ids),
                "fasta_sha256": child[0].fasta_sha256,
                "missingness_policy": "absent-or-nonquantifiable-is-null-no-imputation",
                "matrix_feature": "accepted-protein-group-primary-intensity",
                "child_result_digests": [result.result_digest for result in child],
                "sample_source_provenance": [
                    {
                        "sample_id": sample.sample_id,
                        **_source_provenance(result),
                    }
                    for sample, result in zip(ordered_samples, child, strict=True)
                ],
            }.items()
        )
    )
    evidence_bundle = _build_evidence_bundle(
        sample_ids=sample_ids,
        group_accessions=groups,
        matrix=matrix,
        raw_matrix=matrix,
        normalized_matrix=normalized_matrix,
        sample_qc=tuple(qc),
        group_qc=group_qc,
        sample_scales=sample_scales,
        label_qc=label_qc,
        label_group_evidence=label_group_evidence,
        label_contrasts=label_contrasts,
        source_manifest=source_manifest,
        configuration=configuration,
    )
    payload = {
        "sample_ids": list(sample_ids),
        "group_accessions": [list(group) for group in groups],
        "matrix": [[list(group), list(values)] for group, values in matrix],
        "raw_matrix": [[list(group), list(values)] for group, values in matrix],
        "normalized_matrix": [[list(group), list(values)] for group, values in normalized_matrix],
        "sample_qc": [item.as_dict() for item in qc],
        "group_qc": [item.as_dict() for item in group_qc],
        "sample_scales": [item.as_dict() for item in sample_scales],
        "label_qc": [item.as_dict() for item in label_qc],
        "label_group_evidence": [item.as_dict() for item in label_group_evidence],
        "label_contrasts": [item.as_dict() for item in label_contrasts],
        "source_manifest": source_manifest.as_dict(),
        "child_result_digests": [
            [sample.sample_id, result.result_digest]
            for sample, result in zip(ordered_samples, child, strict=True)
        ],
        "configuration": dict(configuration),
        "evidence_bundle": evidence_bundle.as_dict(),
    }
    return ResearchCohortResult(
        sample_ids=sample_ids,
        group_accessions=groups,
        matrix=matrix,
        sample_qc=tuple(qc),
        group_qc=tuple(group_qc),
        child_result_digests=tuple(
            (sample.sample_id, result.result_digest)
            for sample, result in zip(ordered_samples, child, strict=True)
        ),
        configuration=configuration,
        result_digest=_digest(payload),
        raw_matrix=matrix,
        normalized_matrix=normalized_matrix,
        sample_scales=sample_scales,
        label_qc=label_qc,
        label_group_evidence=label_group_evidence,
        label_contrasts=label_contrasts,
        source_manifest=source_manifest,
        evidence_bundle=evidence_bundle,
    )


def replay_research_cohort(
    request: ResearchCohortRequest, expected: ResearchCohortResult
) -> ResearchCohortResult:
    expected_payload = expected.as_dict()
    expected_digest = expected_payload.pop("result_digest")
    if expected_digest != expected.result_digest or _digest(expected_payload) != expected_digest:
        raise ValueError("expected cohort result digest is invalid")
    observed = run_research_cohort(request)
    if observed.as_dict() != {**expected_payload, "result_digest": expected_digest}:
        raise ValueError("cohort replay or digest verification failed")
    return observed
