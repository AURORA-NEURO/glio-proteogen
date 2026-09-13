"""Strict research contracts for the Migliozzi GBM functional proteotype lane.

The lane estimates bulk-protein concordance with four source-cohort functional
proteotype axes.  It does not emit a clinical subtype, a pathway activity call,
cellular composition, prognosis, causality, or treatment guidance.
"""

from __future__ import annotations

import math
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import (
    canonical_request_digest,
    objective_trace_digest,
    result_payload_digest,
    sha256_digest,
)
from .catalog import is_source_gene_symbol

ALGORITHM_ID = "migliozzi-gbm-functional-proteotype"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "migliozzi-gbm-functional-proteotype/1.0.0"

MAX_OBSERVATIONS = 4_096
MAX_BOOTSTRAPS = 256
MAX_PERMUTATIONS = 2_048
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 2 * 1_024 * 1_024
MAX_REPLAY_BYTES = 4 * 1_024 * 1_024
MAX_TOP_DRIVERS = 8
MAX_ABLATIONS = 24
MAX_PATHWAY_CONTEXTS = 16
MAX_SOLVER_ITERATIONS = 128
MAX_JSON_SAFE_INTEGER = 2**53 - 1
AXIS_CLASSIFICATION_THRESHOLD = 0.25

GeneSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*$"),
]
HttpsUrl = Annotated[
    str,
    StringConstraints(min_length=8, max_length=512, pattern=r"^https://[^\s]+$"),
]


class FunctionalProteotypeAxis(StrEnum):
    """Four exact bulk-GBM axes reported in Migliozzi et al. Table 2d."""

    GPM = "GPM"
    MTC = "MTC"
    NEU = "NEU"
    PPR = "PPR"


AXIS_ORDER: tuple[FunctionalProteotypeAxis, ...] = tuple(FunctionalProteotypeAxis)


class ProteinEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class AnalysisSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class AxisClassification(StrEnum):
    SOURCE_ALIGNED = "source_aligned"
    SOURCE_OPPOSED = "source_opposed"
    NEUTRAL = "neutral"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class AblationKind(StrEnum):
    SOURCE_RANK_QUARTILE = "source_rank_quartile"
    EVIDENCE_STATE = "evidence_state"
    TOP_DRIVER = "top_driver"


class SolverTermination(StrEnum):
    CONVERGED = "converged"
    MAXIMUM_ITERATIONS = "maximum_iterations"
    NUMERICAL_GUARD = "numerical_guard"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ProteinEvidence(FrozenModel):
    """One exact source protein with explicit value and absence semantics."""

    observation_id: Identifier
    gene_symbol: GeneSymbol
    state: ProteinEvidenceState
    standardized_effect: float | None = Field(
        default=None,
        ge=-20.0,
        le=20.0,
        description=("Point estimate when observed; an upper censoring limit when left_censored."),
    )
    standard_error: float | None = Field(default=None, gt=0.0, le=20.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def numerical_values_match_state(self) -> Self:
        active = self.state in {
            ProteinEvidenceState.OBSERVED,
            ProteinEvidenceState.LEFT_CENSORED,
        }
        if active and (self.standardized_effect is None or self.standard_error is None):
            raise ValueError("observed and left-censored evidence require effect and error")
        if active and self.quality_weight <= 0.0:
            raise ValueError("observed and left-censored evidence require positive quality")
        if not active and (self.standardized_effect is not None or self.standard_error is not None):
            raise ValueError("missing and unsupported evidence cannot carry numeric values")
        if not active and self.quality_weight != 0.0:
            raise ValueError("missing and unsupported evidence must have zero quality")
        return self


class FunctionalProteotypeRequest(FrozenModel):
    """Bounded, stateless input of standardized bulk-protein contrasts."""

    profile_id: Literal["migliozzi-gbm-functional-proteotype/1.0.0"] = (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    sample_id: Identifier
    observations: tuple[ProteinEvidence, ...] = Field(
        min_length=1,
        max_length=MAX_OBSERVATIONS,
    )
    bootstrap_replicates: int = Field(default=64, ge=16, le=MAX_BOOTSTRAPS)
    permutation_replicates: int = Field(default=256, ge=64, le=MAX_PERMUTATIONS)
    effect_scale: Literal["standardized_log2_abundance_contrast"] = (
        "standardized_log2_abundance_contrast"
    )
    effect_reference_id: Identifier

    @field_validator("observations")
    @classmethod
    def observations_are_unique(
        cls,
        values: tuple[ProteinEvidence, ...],
    ) -> tuple[ProteinEvidence, ...]:
        del cls
        observation_ids = tuple(item.observation_id for item in values)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation identifiers must be unique")
        gene_symbols = tuple(item.gene_symbol for item in values)
        if len(gene_symbols) != len(set(gene_symbols)):
            raise ValueError("gene symbols must be unique")
        unresolved = sorted(
            item.gene_symbol
            for item in values
            if item.state is not ProteinEvidenceState.UNSUPPORTED
            and not is_source_gene_symbol(item.gene_symbol)
        )
        if unresolved:
            preview = ", ".join(unresolved[:5])
            raise ValueError(
                "observed, left-censored, and missing evidence must resolve to exact "
                f"Table 2d gene symbols; rejected: {preview}"
            )
        return values

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class LatentInterval(FrozenModel):
    """A constrained latent-axis estimate and deterministic bootstrap interval."""

    estimate: float = Field(ge=-20.0, le=20.0)
    lower_bound: float = Field(ge=-40.0, le=40.0)
    upper_bound: float = Field(ge=-40.0, le=40.0)
    nominal_coverage: float = Field(default=0.9, ge=0.9, le=0.9)
    bootstrap_replicates_used: int = Field(ge=16, le=MAX_BOOTSTRAPS)

    @model_validator(mode="after")
    def interval_contains_estimate(self) -> Self:
        if not self.lower_bound <= self.estimate <= self.upper_bound:
            raise ValueError("latent interval must contain its estimate")
        return self


class RankComparison(FrozenModel):
    """Tie-corrected competitive rank evidence for one source axis."""

    signature_observed_count: int = Field(ge=1, le=MAX_OBSERVATIONS)
    complement_observed_count: int = Field(ge=1, le=MAX_OBSERVATIONS)
    u_statistic: float = Field(ge=0.0)
    rank_biserial: float = Field(ge=-1.0, le=1.0)
    tie_correction: float = Field(gt=0.0, le=1.0)
    null_standard_deviation: float = Field(ge=0.0, le=2.0)
    empirical_p_value: float = Field(ge=0.0, le=1.0)
    q_value: float = Field(ge=0.0, le=1.0)
    permutation_replicates_used: int = Field(ge=64, le=MAX_PERMUTATIONS)

    @model_validator(mode="after")
    def rank_statistics_are_coherent(self) -> Self:
        maximum_u = self.signature_observed_count * self.complement_observed_count
        if self.u_statistic > maximum_u:
            raise ValueError("U statistic exceeds the pairwise-comparison count")
        if self.q_value + 1e-12 < self.empirical_p_value:
            raise ValueError("BH q-value cannot be smaller than its raw p-value")
        return self


class AxisEvidenceCounts(FrozenModel):
    """Reconciled state counts for one 150-protein source signature."""

    source_signature_proteins: Literal[150] = 150
    declared_signature_proteins: int = Field(ge=0, le=150)
    observed_signature_proteins: int = Field(ge=0, le=150)
    left_censored_signature_proteins: int = Field(ge=0, le=150)
    missing_signature_proteins: int = Field(ge=0, le=150)
    unsupported_signature_proteins: int = Field(ge=0, le=150)
    unreported_signature_proteins: int = Field(ge=0, le=150)
    observed_background_proteins: int = Field(ge=0, le=MAX_OBSERVATIONS)
    active_signature_fraction: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def counts_reconcile(self) -> Self:
        declared = (
            self.observed_signature_proteins
            + self.left_censored_signature_proteins
            + self.missing_signature_proteins
            + self.unsupported_signature_proteins
        )
        if declared != self.declared_signature_proteins:
            raise ValueError("declared signature state counts must reconcile")
        if declared + self.unreported_signature_proteins != self.source_signature_proteins:
            raise ValueError("declared and unreported proteins must cover the source signature")
        active = self.observed_signature_proteins + self.left_censored_signature_proteins
        expected_fraction = active / self.source_signature_proteins
        if not math.isclose(
            self.active_signature_fraction,
            expected_fraction,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("active signature fraction must match evidence counts")
        return self


class ProteinDriver(FrozenModel):
    """Auditable Huber score contribution, never causal or leverage-adjusted influence."""

    observation_id: Identifier
    gene_symbol: GeneSymbol
    source_protein_label: NonEmptyStr
    axis: FunctionalProteotypeAxis
    source_rank: int = Field(ge=1, le=150)
    source_rank_quartile: int = Field(ge=1, le=4)
    source_mww_score: float = Field(ge=0.0, le=20.0)
    evidence_state: ProteinEvidenceState
    value_role: Literal["observed_point", "left_censored_upper_limit"]
    standardized_effect: float = Field(ge=-20.0, le=20.0)
    reliability_weight: float = Field(gt=0.0, le=1.0e6)
    source_loading: float = Field(gt=0.0, le=20.0)
    signed_contribution: float = Field(ge=-1.0e6, le=1.0e6)
    absolute_contribution: float = Field(ge=0.0, le=1.0e6)

    @model_validator(mode="after")
    def contribution_and_state_are_coherent(self) -> Self:
        if not math.isclose(
            self.absolute_contribution,
            abs(self.signed_contribution),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("absolute contribution must match signed contribution")
        expected_role = (
            "observed_point"
            if self.evidence_state is ProteinEvidenceState.OBSERVED
            else "left_censored_upper_limit"
        )
        if (
            self.evidence_state
            not in {
                ProteinEvidenceState.OBSERVED,
                ProteinEvidenceState.LEFT_CENSORED,
            }
            or self.value_role != expected_role
        ):
            raise ValueError("drivers must reference active evidence with the matching value role")
        expected_quartile = min(4, ((self.source_rank - 1) // 38) + 1)
        if self.source_rank_quartile != expected_quartile:
            raise ValueError("source rank quartile does not match source rank")
        return self


class AxisAblation(FrozenModel):
    """Sensitivity result from removing one source-defined evidence family."""

    kind: AblationKind
    target: NonEmptyStr
    proteins_removed: int = Field(ge=1, le=150)
    support_after_ablation: AnalysisSupport
    baseline_estimate: float | None = Field(default=None, ge=-20.0, le=20.0)
    ablated_estimate: float | None = Field(default=None, ge=-20.0, le=20.0)
    estimate_delta: float | None = Field(default=None, ge=-40.0, le=40.0)
    classification_after_ablation: AxisClassification
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def ablation_values_match_support(self) -> Self:
        estimates = (self.baseline_estimate, self.ablated_estimate, self.estimate_delta)
        if self.support_after_ablation is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in estimates):
                raise ValueError("abstained ablations cannot carry an estimate")
            if self.classification_after_ablation is not AxisClassification.NOT_ESTIMABLE:
                raise ValueError("abstained ablations must be not_estimable")
            if self.reason is None:
                raise ValueError("abstained ablations require a reason")
            return self
        if any(value is None for value in estimates):
            raise ValueError("estimated ablations require baseline, estimate, and delta")
        expected_delta = cast("float", self.ablated_estimate) - cast(
            "float", self.baseline_estimate
        )
        if not math.isclose(
            cast("float", self.estimate_delta),
            expected_delta,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("ablation delta must equal ablated minus baseline estimate")
        if self.classification_after_ablation is not AxisClassification.INDETERMINATE:
            raise ValueError(
                "estimated ablations without bootstrap intervals must be indeterminate"
            )
        if self.support_after_ablation is AnalysisSupport.LIMITED and self.reason is None:
            raise ValueError("limited ablations require a reason")
        if self.support_after_ablation is AnalysisSupport.SUPPORTED and self.reason is not None:
            raise ValueError("supported ablations cannot carry a limitation reason")
        return self


class SourceCohortPathwayContext(FrozenModel):
    """Published cohort context; never a pathway call for the submitted sample."""

    axis: FunctionalProteotypeAxis
    source_rank: int = Field(ge=1, le=272)
    pathway_name: NonEmptyStr
    source_logit_nes: float = Field(ge=-20.0, le=20.0)
    source_p_value: float = Field(ge=0.0, le=1.0)
    source_q_value: float = Field(ge=0.0, le=1.0)
    sample_inference_status: Literal["not_evaluated"] = "not_evaluated"
    interpretation: Literal["source_cohort_pathway_context_only"] = (
        "source_cohort_pathway_context_only"
    )

    @model_validator(mode="after")
    def adjusted_probability_is_coherent(self) -> Self:
        if self.source_q_value + 1e-12 < self.source_p_value:
            raise ValueError("source pathway q-value cannot be smaller than p-value")
        return self


def _classification_matches_interval(
    classification: AxisClassification,
    interval: LatentInterval,
) -> bool:
    threshold = AXIS_CLASSIFICATION_THRESHOLD
    if classification is AxisClassification.SOURCE_ALIGNED:
        return interval.lower_bound > threshold
    if classification is AxisClassification.SOURCE_OPPOSED:
        return interval.upper_bound < -threshold
    if classification is AxisClassification.NEUTRAL:
        return interval.lower_bound >= -threshold and interval.upper_bound <= threshold
    if classification is AxisClassification.INDETERMINATE:
        return not (
            interval.lower_bound > threshold
            or interval.upper_bound < -threshold
            or (interval.lower_bound >= -threshold and interval.upper_bound <= threshold)
        )
    return False


class AxisEvidence(FrozenModel):
    """One axis estimate with uncertainty, orthogonal rank evidence, and sensitivity."""

    axis: FunctionalProteotypeAxis
    support: AnalysisSupport
    classification: AxisClassification
    latent: LatentInterval | None = None
    rank: RankComparison | None = None
    evidence_counts: AxisEvidenceCounts
    effective_sample_size: float = Field(ge=0.0, le=150.0)
    stability: float = Field(ge=0.0, le=1.0)
    discordance: float = Field(ge=0.0, le=1.0)
    top_drivers: tuple[ProteinDriver, ...] = Field(default=(), max_length=MAX_TOP_DRIVERS)
    ablations: tuple[AxisAblation, ...] = Field(default=(), max_length=MAX_ABLATIONS)
    source_cohort_pathway_context: tuple[SourceCohortPathwayContext, ...] = Field(
        min_length=1,
        max_length=MAX_PATHWAY_CONTEXTS,
    )
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    estimate_semantics: Literal["bulk_protein_source_axis_concordance"] = (
        "bulk_protein_source_axis_concordance"
    )

    @model_validator(mode="after")
    def support_and_interpretation_are_coherent(self) -> Self:
        if any(item.axis is not self.axis for item in self.top_drivers):
            raise ValueError("all drivers must belong to the enclosing axis")
        if any(item.axis is not self.axis for item in self.source_cohort_pathway_context):
            raise ValueError("all pathway contexts must belong to the enclosing axis")
        driver_ids = tuple(item.gene_symbol for item in self.top_drivers)
        if len(driver_ids) != len(set(driver_ids)):
            raise ValueError("top-driver proteins must be unique")
        ablation_keys = tuple((item.kind, item.target) for item in self.ablations)
        if len(ablation_keys) != len(set(ablation_keys)):
            raise ValueError("ablation kind/target pairs must be unique")

        if self.support is AnalysisSupport.ABSTAINED:
            if self.classification is not AxisClassification.NOT_ESTIMABLE:
                raise ValueError("abstained axes must be not_estimable")
            if self.latent is not None or self.rank is not None or self.top_drivers:
                raise ValueError("abstained axes cannot carry estimates or drivers")
            if not self.abstention_reasons:
                raise ValueError("abstained axes require reasons")
            if self.ablations:
                raise ValueError("abstained axes cannot carry ablation estimates")
            return self

        if self.latent is None:
            raise ValueError("estimated axes require a latent interval")
        if self.classification is AxisClassification.NOT_ESTIMABLE:
            raise ValueError("estimated axes cannot be not_estimable")
        if not _classification_matches_interval(self.classification, self.latent):
            raise ValueError("axis classification is not supported by its interval")
        if self.support is AnalysisSupport.SUPPORTED and self.abstention_reasons:
            raise ValueError("supported axes cannot carry limitation reasons")
        if self.support is AnalysisSupport.LIMITED and not self.abstention_reasons:
            raise ValueError("limited axes require limitation reasons")
        if {item.kind for item in self.ablations} != set(AblationKind):
            raise ValueError("estimated axes require all three ablation families")
        return self


class ConstrainedAxisCoordinate(FrozenModel):
    axis: FunctionalProteotypeAxis
    estimate: float = Field(ge=-20.0, le=20.0)


class ObjectiveTraceStep(FrozenModel):
    """Paired objective values for one deterministic damping decision."""

    iteration: int = Field(ge=1, le=MAX_SOLVER_ITERATIONS)
    baseline_objective: float = Field(ge=0.0, le=1.0e18)
    candidate_objective: float = Field(ge=0.0, le=1.0e18)
    accepted_objective: float = Field(ge=0.0, le=1.0e18)
    damping: float = Field(ge=0.0, le=1.0)
    accepted: bool

    @model_validator(mode="after")
    def accepted_objective_matches_decision(self) -> Self:
        if self.accepted:
            if self.damping <= 0.0:
                raise ValueError("an accepted candidate requires positive damping")
            if self.accepted_objective > self.baseline_objective + 1e-12:
                raise ValueError("an accepted damped trial cannot increase the objective")
            return self
        if self.damping != 0.0:
            raise ValueError("a rejected candidate must report zero accepted damping")
        if not math.isclose(
            self.accepted_objective,
            self.baseline_objective,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("a rejected candidate must preserve the baseline objective")
        return self


class SolverDiagnostics(FrozenModel):
    """Diagnostics for the intercept-plus-four-axis equality-constrained solve."""

    converged: bool
    termination: SolverTermination
    iterations: int = Field(ge=0, le=MAX_SOLVER_ITERATIONS)
    intercept: float = Field(ge=-20.0, le=20.0)
    axis_coordinates: tuple[ConstrainedAxisCoordinate, ...] = Field(
        min_length=4,
        max_length=4,
    )
    sum_to_zero_residual: float = Field(ge=-1e-6, le=1e-6)
    initial_objective: float = Field(ge=0.0, le=1.0e18)
    final_objective: float = Field(ge=0.0, le=1.0e18)
    final_gradient_norm: float = Field(ge=0.0, le=1.0e18)
    maximum_coordinate_change: float = Field(ge=0.0, le=40.0)
    objective_trace: tuple[ObjectiveTraceStep, ...] = Field(max_length=MAX_SOLVER_ITERATIONS)
    objective_trace_digest: Sha256Digest

    @model_validator(mode="after")
    def constrained_trace_is_coherent(self) -> Self:
        axes = tuple(item.axis for item in self.axis_coordinates)
        if axes != AXIS_ORDER:
            raise ValueError("solver coordinates must contain GPM, MTC, NEU, PPR in order")
        coordinate_sum = sum(item.estimate for item in self.axis_coordinates)
        if not math.isclose(
            self.sum_to_zero_residual,
            coordinate_sum,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("sum-to-zero residual must equal the coordinate sum")
        if self.iterations != len(self.objective_trace):
            raise ValueError("solver iteration count must equal objective-trace length")
        if self.objective_trace_digest != objective_trace_digest(self.objective_trace):
            raise ValueError("objective-trace digest does not match trace content")
        if self.objective_trace:
            if not math.isclose(
                self.objective_trace[0].baseline_objective,
                self.initial_objective,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("first trace baseline must match initial objective")
            for previous, current in pairwise(self.objective_trace):
                if not math.isclose(
                    current.baseline_objective,
                    previous.accepted_objective,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    raise ValueError("objective trace must form a continuous monotone chain")
            if not math.isclose(
                self.final_objective,
                self.objective_trace[-1].accepted_objective,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("final objective must match the final accepted objective")
        elif not math.isclose(
            self.final_objective,
            self.initial_objective,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("a solver without iterations cannot change its objective")
        if self.converged != (self.termination is SolverTermination.CONVERGED):
            raise ValueError("convergence flag and termination reason must agree")
        if self.termination is SolverTermination.INSUFFICIENT_EVIDENCE and self.iterations != 0:
            raise ValueError("an insufficient-evidence solve must not report iterations")
        return self


class FunctionalProteotypeProvenance(FrozenModel):
    """Content locks and deterministic random identities for one result."""

    engine: Literal["migliozzi-gbm-functional-proteotype/1.0.0"] = (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    computational_digest: Sha256Digest
    catalog_content_digest: Sha256Digest
    catalog_artifact_digest: Sha256Digest
    source_workbook_digest: Sha256Digest
    signature_catalog_digest: Sha256Digest
    pathway_catalog_digest: Sha256Digest
    engine_source_digest: Sha256Digest
    numpy_version: Literal["2.5.2"] = "2.5.2"
    bootstrap_seed: int = Field(ge=0, le=MAX_JSON_SAFE_INTEGER)
    permutation_seed: int = Field(ge=0, le=MAX_JSON_SAFE_INTEGER)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    permutation_replicates_used: int = Field(ge=0, le=MAX_PERMUTATIONS)
    observation_source_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1,
        max_length=MAX_OBSERVATIONS,
    )
    source_article_doi: Literal["10.1038/s43018-022-00510-x"] = "10.1038/s43018-022-00510-x"
    source_article_title: NonEmptyStr
    source_article_authors: NonEmptyStr
    source_url: HttpsUrl
    source_license: Literal["CC-BY-4.0"] = "CC-BY-4.0"
    source_license_url: Literal["https://creativecommons.org/licenses/by/4.0/"] = (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    source_transformation_notice: NonEmptyStr

    @model_validator(mode="after")
    def replicate_counts_are_zero_or_evaluable(self) -> Self:
        if 0 < self.permutation_replicates_used < 64:
            raise ValueError("used permutation count must be zero or at least 64")
        return self


class FunctionalProteotypeResult(FrozenModel):
    """Digest-bound research receipt for one bulk-protein contrast."""

    algorithm_id: Literal["migliozzi-gbm-functional-proteotype"] = (
        "migliozzi-gbm-functional-proteotype"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["migliozzi-gbm-functional-proteotype/1.0.0"] = (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    effect_reference_id: Identifier
    solver: SolverDiagnostics
    axis_evidence: tuple[AxisEvidence, ...] = Field(min_length=4, max_length=4)
    provenance: FunctionalProteotypeProvenance
    output_semantics: Literal["bulk_gbm_functional_proteotype_evidence"] = (
        "bulk_gbm_functional_proteotype_evidence"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=4, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    clinical_subtype_inference: Literal[False] = False
    emits_subtype_classification: Literal[False] = False
    source_cohort_pathway_inference: Literal[False] = False

    @model_validator(mode="after")
    def receipt_is_content_bound(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if tuple(item.axis for item in self.axis_evidence) != AXIS_ORDER:
            raise ValueError("axis results must contain GPM, MTC, NEU, PPR in order")
        coordinates = {item.axis: item.estimate for item in self.solver.axis_coordinates}
        for evidence in self.axis_evidence:
            if evidence.latent is not None and not math.isclose(
                coordinates[evidence.axis],
                evidence.latent.estimate,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError("axis result estimate must match its constrained coordinate")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedFunctionalProteotypeResult(FrozenModel):
    """Caller-supplied receipt accepted structurally before exact replay."""

    algorithm_id: Literal["migliozzi-gbm-functional-proteotype"] = (
        "migliozzi-gbm-functional-proteotype"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["migliozzi-gbm-functional-proteotype/1.0.0"] = (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    effect_reference_id: Identifier
    solver: SolverDiagnostics
    axis_evidence: tuple[AxisEvidence, ...] = Field(min_length=4, max_length=4)
    provenance: FunctionalProteotypeProvenance
    output_semantics: Literal["bulk_gbm_functional_proteotype_evidence"] = (
        "bulk_gbm_functional_proteotype_evidence"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=4, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    clinical_subtype_inference: Literal[False] = False
    emits_subtype_classification: Literal[False] = False
    source_cohort_pathway_inference: Literal[False] = False


class ReplayVerificationRequest(FrozenModel):
    request: FunctionalProteotypeRequest
    result: FunctionalProteotypeResult | UnverifiedFunctionalProteotypeResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    solver_trace_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    provided_result_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    provided_solver_trace_digest: Sha256Digest
    recomputed_solver_trace_digest: Sha256Digest
    message: NonEmptyStr


class FunctionalProteotypeAlgorithmConstants(FrozenModel):
    loading_policy: Literal["source_mww_median_normalized_axis_loading_v1"]
    location_solver: Literal["huber_irls_kkt_sum_to_zero_v1"]
    censoring_loss: Literal["one_sided_upper_bound_huber_hinge_v1"]
    damping_policy: Literal["monotone_backtracking_v1"]
    bootstrap_policy: Literal["request_digest_seeded_normal_limit_perturbation_v1"]
    rank_estimator: Literal["tie_corrected_mann_whitney_rank_biserial_v1"]
    rank_null_policy: Literal["source_rank_quartile_stratified_two_sided_bh_v1"]
    ablation_policy: Literal["quartile_state_and_top_driver_refit_v1"]
    huber_delta: float = Field(gt=0.0, le=10.0)
    standard_error_floor: float = Field(gt=0.0, le=5.0)
    axis_ridge_penalty: float = Field(gt=0.0, le=1.0)
    intercept_ridge_penalty: float = Field(gt=0.0, le=1.0)
    coordinate_tolerance: float = Field(gt=0.0, le=1e-3)
    gradient_tolerance: float = Field(gt=0.0, le=1e-3)
    maximum_solver_iterations: int = Field(ge=8, le=MAX_SOLVER_ITERATIONS)
    initial_damping: float = Field(gt=0.0, le=1.0)
    minimum_damping: float = Field(gt=0.0, le=1.0)
    backtracking_factor: float = Field(gt=0.0, lt=1.0)
    maximum_backtracking_steps: int = Field(ge=1, le=32)
    objective_increase_tolerance: float = Field(ge=0.0, le=1e-3)
    axis_classification_threshold: float = Field(default=0.25, ge=0.25, le=0.25)
    exploratory_minimum_active_proteins: int = Field(ge=3, le=150)
    supported_minimum_active_proteins: int = Field(ge=3, le=150)
    supported_minimum_observed_proteins: int = Field(ge=3, le=150)
    supported_minimum_active_fraction: float = Field(gt=0.0, le=1.0)
    supported_minimum_effective_sample_size: float = Field(gt=0.0, le=150.0)
    minimum_rank_signature_proteins: int = Field(ge=3, le=150)
    minimum_rank_background_proteins: int = Field(ge=3, le=MAX_OBSERVATIONS)
    rank_q_threshold: float = Field(gt=0.0, le=1.0)
    interval_lower_quantile: float = Field(default=0.05, ge=0.05, le=0.05)
    interval_upper_quantile: float = Field(default=0.95, ge=0.95, le=0.95)
    minimum_bootstrap_success_fraction: float = Field(gt=0.5, le=1.0)
    minimum_interval_bootstrap_replicates: int = Field(ge=16, le=MAX_BOOTSTRAPS)
    quantization_decimals: int = Field(ge=4, le=12)
    random_seed_bytes: int = Field(ge=4, le=32)
    default_bootstrap_replicates: int = Field(ge=16, le=MAX_BOOTSTRAPS)
    default_permutation_replicates: int = Field(ge=64, le=MAX_PERMUTATIONS)
    top_driver_limit: int = Field(ge=1, le=MAX_TOP_DRIVERS)
    pathway_context_limit: int = Field(ge=1, le=MAX_PATHWAY_CONTEXTS)

    @model_validator(mode="after")
    def numerical_gates_are_ordered(self) -> Self:
        if self.minimum_damping > self.initial_damping:
            raise ValueError("minimum damping cannot exceed initial damping")
        expected_minimum_damping = self.initial_damping * (
            self.backtracking_factor ** (self.maximum_backtracking_steps - 1)
        )
        if not math.isclose(
            self.minimum_damping,
            expected_minimum_damping,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError(
                "minimum damping must match the final deterministic backtracking trial"
            )
        if self.supported_minimum_active_proteins < self.exploratory_minimum_active_proteins:
            raise ValueError("supported active-protein gate cannot be weaker than exploratory")
        return self


class FunctionalProteotypeLimits(FrozenModel):
    max_observations: Literal[4096] = 4096
    max_bootstrap_replicates: Literal[256] = 256
    max_permutation_replicates: Literal[2048] = 2048
    max_request_bytes: Literal[2097152] = 2_097_152
    max_result_bytes: Literal[2097152] = 2_097_152
    max_replay_bytes: Literal[4194304] = 4_194_304
    axis_count: Literal[4] = 4
    source_signature_proteins_per_axis: Literal[150] = 150
    source_signature_proteins_total: Literal[600] = 600
    source_pathway_rows_total: Literal[826] = 826
    max_top_drivers_per_axis: Literal[8] = 8
    max_ablations_per_axis: Literal[24] = 24
    max_pathway_contexts_per_axis: Literal[16] = 16


class AxisCatalogProfile(FrozenModel):
    axis: FunctionalProteotypeAxis
    signature_protein_count: Literal[150] = 150
    pathway_count: int = Field(ge=1, le=272)
    signature_digest: Sha256Digest
    pathway_digest: Sha256Digest


class FunctionalProteotypeProfile(FrozenModel):
    algorithm_id: Literal["migliozzi-gbm-functional-proteotype"] = (
        "migliozzi-gbm-functional-proteotype"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["migliozzi-gbm-functional-proteotype/1.0.0"] = (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    constants: FunctionalProteotypeAlgorithmConstants
    limits: FunctionalProteotypeLimits
    numpy_version: Literal["2.5.2"] = "2.5.2"
    catalog_content_digest: Sha256Digest
    catalog_artifact_digest: Sha256Digest
    source_workbook_digest: Literal[
        "sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
    ] = "sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
    signature_catalog_digest: Sha256Digest
    pathway_catalog_digest: Sha256Digest
    engine_source_digest: Sha256Digest
    axes: tuple[AxisCatalogProfile, ...] = Field(min_length=4, max_length=4)
    demo_id: Identifier
    demo_request_digest: Sha256Digest
    source_article_doi: Literal["10.1038/s43018-022-00510-x"] = "10.1038/s43018-022-00510-x"
    source_article_title: NonEmptyStr
    source_article_authors: NonEmptyStr
    source_url: HttpsUrl
    source_license: Literal["CC-BY-4.0"] = "CC-BY-4.0"
    source_license_url: Literal["https://creativecommons.org/licenses/by/4.0/"] = (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    source_transformation_notice: NonEmptyStr
    signature_sheet_mapping: Literal[
        "Tab 14 - Supplementary Table 2d rows 5:154; GPM A:C; MTC E:G; "
        "NEU I:K; PPR M:O; headers Gene|Protein|MWW score"
    ] = (
        "Tab 14 - Supplementary Table 2d rows 5:154; GPM A:C; MTC E:G; "
        "NEU I:K; PPR M:O; headers Gene|Protein|MWW score"
    )
    pathway_sheet_mapping: Literal[
        "Tab 15 - Supplementary Table 2e rows 5:end; GPM A:D; MTC F:I; "
        "NEU K:N; PPR P:S; headers Biological pathway|logitNES|pValue|qValue"
    ] = (
        "Tab 15 - Supplementary Table 2e rows 5:end; GPM A:D; MTC F:I; "
        "NEU K:N; PPR P:S; headers Biological pathway|logitNES|pValue|qValue"
    )
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    interpretation: Literal["bulk_gbm_functional_proteotype_evidence_non_prescriptive"] = (
        "bulk_gbm_functional_proteotype_evidence_non_prescriptive"
    )
    claim_ceiling: Literal[
        "bulk_tumor_protein_concordance_to_source_selected_cptac_gbm_signatures"
    ] = "bulk_tumor_protein_concordance_to_source_selected_cptac_gbm_signatures"

    @model_validator(mode="after")
    def all_axis_profiles_are_present(self) -> Self:
        if tuple(item.axis for item in self.axes) != AXIS_ORDER:
            raise ValueError("profile axes must contain GPM, MTC, NEU, PPR in order")
        if sum(item.pathway_count for item in self.axes) != 826:
            raise ValueError("profile axis pathway counts must reconcile to Table 2e")
        payload = self.model_dump(mode="json")
        payload.pop("profile_digest")
        if self.profile_digest != sha256_digest(payload):
            raise ValueError("profile digest does not match canonical profile content")
        return self


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "AXIS_CLASSIFICATION_THRESHOLD",
    "AXIS_ORDER",
    "MAX_ABLATIONS",
    "MAX_BOOTSTRAPS",
    "MAX_JSON_SAFE_INTEGER",
    "MAX_OBSERVATIONS",
    "MAX_PATHWAY_CONTEXTS",
    "MAX_PERMUTATIONS",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_SOLVER_ITERATIONS",
    "MAX_TOP_DRIVERS",
    "PROFILE_ID",
    "AblationKind",
    "AnalysisSupport",
    "AxisAblation",
    "AxisCatalogProfile",
    "AxisClassification",
    "AxisEvidence",
    "AxisEvidenceCounts",
    "ConstrainedAxisCoordinate",
    "FunctionalProteotypeAlgorithmConstants",
    "FunctionalProteotypeAxis",
    "FunctionalProteotypeLimits",
    "FunctionalProteotypeProfile",
    "FunctionalProteotypeProvenance",
    "FunctionalProteotypeRequest",
    "FunctionalProteotypeResult",
    "GeneSymbol",
    "HttpsUrl",
    "LatentInterval",
    "ObjectiveTraceStep",
    "ProteinDriver",
    "ProteinEvidence",
    "ProteinEvidenceState",
    "RankComparison",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "SolverDiagnostics",
    "SolverTermination",
    "SourceCohortPathwayContext",
    "UnverifiedFunctionalProteotypeResult",
]
