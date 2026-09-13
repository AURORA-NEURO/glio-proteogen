"""Local-only exact-source fitter for CPTAC GBM cis-dosage evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact import CisDosageArtifact, build_artifact, write_artifact
from .contracts import (
    CohortArtifactSummary,
    DerivationStatus,
    ExactSourceLock,
    FitReceipt,
)
from .errors import FitNotEvaluableError
from .model import fit_gene_cross_validated, gene_fit_document
from .ooxml import PreparedCohort, load_table_s3_flags, prepare_cohort
from .source import HGNC_LOCK, TABLE_S2_LOCK, TABLE_S3_LOCK, _stage_exact_sources


def _fit_cohort(
    cohort: PreparedCohort,
    *,
    source_locks: tuple[ExactSourceLock, ...],
    derivation_status: DerivationStatus,
    table_s3_flags: dict[str, tuple[bool, bool]] | None = None,
) -> CisDosageArtifact:
    """Internal aggregate fitter; callers own the derivation-status boundary."""

    evidence: dict[str, dict[str, Any]] = {}
    flags_included = table_s3_flags is not None
    for gene in cohort.common_genes:
        fit = fit_gene_cross_validated(
            cohort.cnv[gene],
            cohort.rna[gene],
            cohort.protein[gene],
            cohort.folds,
        )
        if fit is None:
            continue
        record = gene_fit_document(fit)
        evidence[gene] = record
    if not evidence:
        raise FitNotEvaluableError("no genes satisfied cross-validated support requirements")
    cohort_summary = CohortArtifactSummary(
        exact_common_measurement_count=cohort.exact_common_measurement_count,
        patient_group_count=cohort.patient_group_count,
        common_gene_count=len(cohort.common_genes),
        fitted_gene_count=len(evidence),
        table_s3_flags_included=flags_included,
    )
    return build_artifact(
        source_locks=source_locks,
        cohort=cohort_summary,
        gene_evidence=evidence,
        derivation_status=derivation_status,
        table_s3_flags=table_s3_flags,
    )


def _fit_prepared_cohort_unverified(
    cohort: PreparedCohort,
    *,
    source_locks: tuple[ExactSourceLock, ...],
    table_s3_flags: dict[str, tuple[bool, bool]] | None = None,
) -> CisDosageArtifact:
    """Internal synthetic oracle helper that can never mint analyzable evidence."""

    return _fit_cohort(
        cohort,
        source_locks=source_locks,
        derivation_status=DerivationStatus.SYNTHETIC_UNVERIFIED,
        table_s3_flags=table_s3_flags,
    )


def _assert_production_cohort_invariants(cohort: PreparedCohort) -> None:
    if cohort.exact_common_measurement_count != 96 or cohort.patient_group_count != 96:
        raise FitNotEvaluableError("staged sources do not match the locked 96-sample cohort")
    if len(cohort.common_genes) != 10_430:
        raise FitNotEvaluableError("staged sources do not match the locked common-gene universe")


def fit_local_artifact(
    *,
    table_s2: Path,
    hgnc: Path,
    output: Path,
    table_s3: Path | None = None,
) -> FitReceipt:
    """Stage exact immutable snapshots, fit them, and publish one local artifact."""

    source_locks = (
        (TABLE_S2_LOCK, TABLE_S3_LOCK, HGNC_LOCK)
        if table_s3 is not None
        else (TABLE_S2_LOCK, HGNC_LOCK)
    )
    with _stage_exact_sources(
        table_s2=table_s2,
        hgnc=hgnc,
        table_s3=table_s3,
    ) as staged:
        cohort = prepare_cohort(staged.table_s2, staged.hgnc)
        _assert_production_cohort_invariants(cohort)
        flags = load_table_s3_flags(staged.table_s3) if staged.table_s3 is not None else None
        artifact = _fit_cohort(
            cohort,
            source_locks=source_locks,
            derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
            table_s3_flags=flags,
        )
        if artifact.cohort.fitted_gene_count != 9_457:
            raise FitNotEvaluableError(
                "staged sources do not reproduce the locked fitted-gene count"
            )
        byte_digest, artifact_bytes = write_artifact(output, artifact)
    return FitReceipt(
        artifact_content_digest=artifact.artifact_content_digest,
        artifact_byte_digest=byte_digest,
        artifact_bytes=artifact_bytes,
        fitted_gene_count=artifact.cohort.fitted_gene_count,
        common_gene_count=artifact.cohort.common_gene_count,
        exact_common_measurement_count=artifact.cohort.exact_common_measurement_count,
        table_s3_flags_included=artifact.cohort.table_s3_flags_included,
    )


__all__ = ["fit_local_artifact"]
