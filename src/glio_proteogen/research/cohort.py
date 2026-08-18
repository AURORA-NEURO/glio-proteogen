"""Bounded multi-run research evidence with explicit missingness and QC."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from statistics import median

from .pipeline import ResearchRunRequest, ResearchRunResult, run_research_protein_inference

MAX_COHORT_SAMPLES = 32


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
class ResearchCohortRequest:
    """Caller-declared, configuration-compatible set of research runs."""

    samples: tuple[ResearchCohortSample, ...]
    provenance_policy: str = "homogeneous"

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

    def as_dict(self) -> dict[str, object]:
        return {
            "child_result_digests": [list(item) for item in self.child_result_digests],
            "configuration": dict(self.configuration),
            "group_accessions": [list(item) for item in self.group_accessions],
            "group_qc": [item.as_dict() for item in self.group_qc],
            "matrix": [[list(group), list(values)] for group, values in self.matrix],
            "result_digest": self.result_digest,
            "sample_ids": list(self.sample_ids),
            "sample_qc": [item.as_dict() for item in self.sample_qc],
        }


def _digest(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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


def run_research_cohort(request: ResearchCohortRequest) -> ResearchCohortResult:
    """Run compatible samples and emit a deterministic matrix without imputation."""

    ordered_samples = tuple(sorted(request.samples, key=lambda item: item.sample_id))
    child = tuple(run_research_protein_inference(item.request) for item in ordered_samples)
    _validate_provenance_policy(request, ordered_samples)
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
    group_qc: list[CohortGroupQc] = []
    for group, row in matrix:
        observed = tuple(value for value in row if value is not None)
        center = float(median(observed)) if observed else None
        deviations = tuple(abs(value - center) for value in observed) if center is not None else ()
        group_qc.append(
            CohortGroupQc(
                group_accessions=group,
                observed_samples=len(observed),
                missing_samples=len(row) - len(observed),
                missingness_rate=(len(row) - len(observed)) / len(row),
                median_intensity=center,
                mad_intensity=float(median(deviations)) if deviations else None,
            )
        )
    configuration = tuple(
        sorted(
            {
                "cohort_version": "research-cohort-1",
                "cohort_provenance_policy": request.provenance_policy,
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
    payload = {
        "sample_ids": list(sample_ids),
        "group_accessions": [list(group) for group in groups],
        "matrix": [[list(group), list(values)] for group, values in matrix],
        "sample_qc": [item.as_dict() for item in qc],
        "group_qc": [item.as_dict() for item in group_qc],
        "child_result_digests": [
            [sample.sample_id, result.result_digest]
            for sample, result in zip(ordered_samples, child, strict=True)
        ],
        "configuration": dict(configuration),
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
