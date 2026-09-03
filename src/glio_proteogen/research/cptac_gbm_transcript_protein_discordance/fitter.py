"""Exact-source local fitter for CPTAC GBM transcript--protein discordance."""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import PreparedCohort, prepare_cohort

from .artifact import TranscriptProteinDiscordanceArtifact, build_artifact, write_artifact
from .contracts import (
    MAX_QUERY_GENES,
    BootstrapEvidence,
    CohortArtifactSummary,
    DerivationStatus,
    ExactSourceLock,
    FiniteSampleInterval,
    FitReceipt,
    FoldConditionalEvidence,
    GeneDiscordanceStatistics,
    GeneSymbol,
    HeldOutModelMetrics,
)
from .errors import DiscordanceFitNotEvaluableError, DiscordanceInputError
from .model import (
    DiscordanceAggregateSummary,
    DiscordanceFitConfiguration,
    MetricSummary,
    fit_transcript_protein_discordance_gene,
)
from .model import (
    FiniteSampleInterval as ModelInterval,
)
from .profile import algorithm_profile
from .source import EXACT_SOURCE_LOCKS, _stage_exact_sources

_GENE_TUPLE_ADAPTER = TypeAdapter(tuple[GeneSymbol, ...])


def _validated_genes(value: object) -> tuple[str, ...]:
    try:
        genes = _GENE_TUPLE_ADAPTER.validate_python(value, strict=True)
    except ValidationError as error:
        raise DiscordanceInputError("fitting gene symbols are invalid") from error
    if not genes or len(genes) > MAX_QUERY_GENES:
        raise DiscordanceInputError("fitting requires between one and 256 genes")
    if len(genes) != len(set(genes)):
        raise DiscordanceInputError("fitting gene symbols must be unique")
    return tuple(sorted(genes))


def _interval(value: ModelInterval) -> FiniteSampleInterval:
    return FiniteSampleInterval(
        point_estimate=value.point_estimate,
        lower=value.lower,
        upper=value.upper,
        coverage=value.confidence_level,
        replicates=value.replicates,
    )


def _metrics(value: MetricSummary) -> HeldOutModelMetrics:
    return HeldOutModelMetrics(
        n_oof=value.patient_groups,
        spearman=value.spearman,
        r2_vs_fold_train_median=value.r2_vs_fold_train_median,
        mae=value.mae,
        residual_mad=value.residual_mad,
    )


def _statistics(value: DiscordanceAggregateSummary) -> GeneDiscordanceStatistics:
    bootstrap = value.bootstrap
    return GeneDiscordanceStatistics(
        full_model=_metrics(value.full_model),
        rna_only_r2=value.rna_only.r2_vs_fold_train_median,
        cnv_only_r2=value.cnv_only.r2_vs_fold_train_median,
        delta_r2_vs_rna_only=value.delta_r2_vs_rna_only,
        delta_r2_vs_cnv_only=value.delta_r2_vs_cnv_only,
        folds=FoldConditionalEvidence(
            valid_folds=value.valid_folds,
            converged_folds=value.valid_folds,
            conditional_rna_slope_median=value.conditional_rna_slope_median,
            conditional_rna_slope_mad=value.conditional_rna_slope_mad,
            conditional_rna_sign_stability=value.conditional_rna_slope_sign_stability,
        ),
        bootstrap=BootstrapEvidence(
            requested_replicates=bootstrap.replicates_requested,
            successful_replicates=bootstrap.replicates_successful,
            full_r2=_interval(bootstrap.full_model_r2),
            delta_r2_vs_rna_only=_interval(bootstrap.delta_r2_vs_rna_only),
            delta_r2_vs_cnv_only=_interval(bootstrap.delta_r2_vs_cnv_only),
            mae=_interval(bootstrap.full_model_mae),
            residual_mad=_interval(bootstrap.full_model_residual_mad),
            conditional_rna_slope=_interval(bootstrap.conditional_rna_slope),
            seed=bootstrap.seed,
        ),
    )


def _fit_seed_digest(
    *,
    gene_symbol: str,
    source_locks: tuple[ExactSourceLock, ...],
    profile_digest: str,
) -> str:
    return sha256_digest(
        {
            "schema": "cptac-gbm-transcript-protein-discordance-fit-seed/1.0.0",
            "profile_digest": profile_digest,
            "source_locks": [lock.model_dump(mode="json") for lock in source_locks],
            "gene_symbol": gene_symbol,
        }
    )


def _fit_cohort(
    cohort: PreparedCohort,
    *,
    gene_symbols: tuple[str, ...],
    source_locks: tuple[ExactSourceLock, ...],
    derivation_status: DerivationStatus,
    configuration: DiscordanceFitConfiguration,
) -> TranscriptProteinDiscordanceArtifact:
    unknown = set(gene_symbols).difference(cohort.common_genes)
    if unknown:
        raise DiscordanceInputError(
            "one or more requested fitting genes are absent from the exact common-gene universe"
        )
    statistics: dict[str, GeneDiscordanceStatistics] = {}
    bound_profile_digest = algorithm_profile().profile_digest
    for symbol in gene_symbols:
        fit = fit_transcript_protein_discordance_gene(
            cohort.cnv[symbol],
            cohort.rna[symbol],
            cohort.protein[symbol],
            cohort.folds,
            request_digest=_fit_seed_digest(
                gene_symbol=symbol,
                source_locks=source_locks,
                profile_digest=bound_profile_digest,
            ),
            configuration=configuration,
        )
        if fit is not None:
            statistics[symbol] = _statistics(fit.summary)
    if not statistics:
        raise DiscordanceFitNotEvaluableError(
            "no requested genes satisfied held-out and bootstrap support requirements"
        )
    cohort_summary = CohortArtifactSummary(
        exact_common_measurement_count=cohort.exact_common_measurement_count,
        patient_group_count=cohort.patient_group_count,
        common_gene_count=len(cohort.common_genes),
        fitted_gene_count=len(statistics),
    )
    return build_artifact(
        source_locks=source_locks,
        cohort=cohort_summary,
        attempted_gene_symbols=gene_symbols,
        gene_statistics=statistics,
        derivation_status=derivation_status,
    )


def _fit_prepared_cohort_unverified(
    cohort: PreparedCohort,
    *,
    gene_symbols: tuple[str, ...],
    source_locks: tuple[ExactSourceLock, ...],
    configuration: DiscordanceFitConfiguration | None = None,
) -> TranscriptProteinDiscordanceArtifact:
    """Internal synthetic-oracle helper; its artifact can never pass the service gate."""

    return _fit_cohort(
        cohort,
        gene_symbols=_validated_genes(gene_symbols),
        source_locks=source_locks,
        derivation_status=DerivationStatus.SYNTHETIC_UNVERIFIED,
        configuration=configuration or DiscordanceFitConfiguration(),
    )


def _assert_production_cohort_invariants(cohort: PreparedCohort) -> None:
    if cohort.exact_common_measurement_count != 96 or cohort.patient_group_count != 96:
        raise DiscordanceFitNotEvaluableError(
            "staged sources do not match the locked 96-patient-group cohort"
        )
    if len(cohort.common_genes) != 10_430:
        raise DiscordanceFitNotEvaluableError(
            "staged sources do not match the locked common-gene universe"
        )


def fit_local_artifact(
    *,
    table_s2: Path,
    hgnc: Path,
    output: Path,
    gene_symbols: tuple[str, ...],
) -> FitReceipt:
    """Fit up to 256 predeclared genes from private exact snapshots."""

    genes = _validated_genes(gene_symbols)
    with _stage_exact_sources(table_s2=table_s2, hgnc=hgnc) as staged:
        cohort = prepare_cohort(staged.table_s2, staged.hgnc)
        _assert_production_cohort_invariants(cohort)
        artifact = _fit_cohort(
            cohort,
            gene_symbols=genes,
            source_locks=EXACT_SOURCE_LOCKS,
            derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
            configuration=DiscordanceFitConfiguration(),
        )
        byte_digest, artifact_bytes = write_artifact(output, artifact)
    return FitReceipt(
        artifact_content_digest=artifact.artifact_content_digest,
        artifact_byte_digest=byte_digest,
        artifact_bytes=artifact_bytes,
        fitted_gene_count=artifact.cohort.fitted_gene_count,
    )


__all__ = ["fit_local_artifact"]
