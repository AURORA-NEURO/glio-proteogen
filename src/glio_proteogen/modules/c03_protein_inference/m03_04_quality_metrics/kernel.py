"""Exact integer kernel for M03-04 evidence-graph quality metrics."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m03_04 import (
    M0304_RATE_SCALE,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricDirection,
    ProteinInferenceQualityMetricProvenance,
    ProteinInferenceQualityMetricResult,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityThreshold,
    claim_binding_digest,
    fact_ledger_digest,
    profile_digest,
    source_binding_digest,
    threshold_digest,
)


@dataclass(frozen=True, slots=True)
class ProteinInferenceMetricFact:
    """One privacy-minimized rational fact before threshold classification."""

    state: ProteinInferenceQualityObservationState
    numerator: int
    denominator: int
    censored_count: int = 0


class _MissingFactLedgerError(ValueError):
    def __init__(self) -> None:
        super().__init__("fact ledger required")


def matching_quality_profile(
    request: ComputeProteinInferenceQualityRequest,
) -> ProteinInferenceAssayQualityProfile | None:
    """Select the one reviewed assay/CV/unit profile without fallback coercion."""

    ledger = request.fact_ledger
    receipt = request.raw_quality_receipt
    if ledger is None:
        return None
    return next(
        (
            profile
            for profile in request.policy.profiles
            if profile.applicability is ledger.applicability
            and receipt.assay_protocol_version in profile.approved_assay_protocol_versions
            and receipt.controlled_vocabulary_version
            in profile.approved_controlled_vocabulary_versions
            and receipt.unit_system_version in profile.approved_unit_system_versions
        ),
        None,
    )


def quality_ledger_bindings_close(request: ComputeProteinInferenceQualityRequest) -> bool:
    """Verify every ledger binding against the exact compact M03-03 projection."""

    ledger = request.fact_ledger
    if ledger is None:
        return False
    receipt = request.raw_quality_receipt
    return all(
        left == right
        for left, right in (
            (ledger.admission_result_digest, receipt.admission_result_digest),
            (ledger.protocol_result_digest, receipt.protocol_result_digest),
            (ledger.search_space_digest, receipt.search_space_digest),
            (ledger.identity_resolution_digest, receipt.identity_resolution_digest),
            (ledger.source_manifest_digest, receipt.source_manifest_digest),
            (ledger.source_binding_digest, source_binding_digest(receipt.sources)),
            (ledger.claim_binding_digest, claim_binding_digest(receipt.claims)),
        )
    )


def protein_inference_metric_facts(
    request: ComputeProteinInferenceQualityRequest,
) -> dict[ProteinInferenceQualityMetricCode, ProteinInferenceMetricFact]:
    """Project the eight exact ratios from the closed receipt and aggregate ledger."""

    ledger = request.fact_ledger
    if ledger is None:
        return {}
    receipt = request.raw_quality_receipt
    counts = ledger.counts
    states = ledger.states
    return {
        ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS: (
            ProteinInferenceMetricFact(
                state=ProteinInferenceQualityObservationState.OBSERVED,
                numerator=len(receipt.sources),
                denominator=receipt.source_count,
            )
        ),
        ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE: (
            ProteinInferenceMetricFact(
                state=states.peptide_assignment,
                numerator=(
                    counts.unique_assigned_peptide_evidence_count
                    + counts.shared_group_assigned_peptide_evidence_count
                ),
                denominator=counts.eligible_peptide_evidence_count,
            )
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN: (
            ProteinInferenceMetricFact(
                state=states.ambiguity_burden,
                numerator=counts.ambiguous_group_member_assignment_count,
                denominator=counts.total_group_member_assignment_count,
            )
        ),
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE: (
            ProteinInferenceMetricFact(
                state=states.proteoform_discrimination,
                numerator=counts.discriminating_proteoform_claim_count,
                denominator=counts.eligible_proteoform_claim_count,
            )
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT: (
            ProteinInferenceMetricFact(
                state=states.detection_support,
                numerator=counts.quantifiable_group_count,
                denominator=counts.detection_eligible_group_count,
                censored_count=counts.left_censored_group_count,
            )
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE: (
            ProteinInferenceMetricFact(
                state=states.competition_closure,
                numerator=counts.competition_closed_group_count,
                denominator=counts.competition_eligible_group_count,
            )
        ),
        ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY: (
            ProteinInferenceMetricFact(
                state=states.control_recovery,
                numerator=counts.control_recovered_group_count,
                denominator=counts.control_expected_group_count,
            )
        ),
        ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: (
            ProteinInferenceMetricFact(
                state=states.sample_context_coherence,
                numerator=counts.context_coherent_binding_count,
                denominator=counts.context_applicable_binding_count,
            )
        ),
    }


def classify_quality_ratio(  # noqa: PLR0911 - exact closed threshold bands.
    numerator: int,
    denominator: int,
    threshold: ProteinInferenceQualityThreshold,
) -> ProteinInferenceQualityMetricStatus:
    """Classify one exact rational by cross multiplication, never rounded ppm."""

    if denominator == 0:
        return ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
    value_product = numerator * M0304_RATE_SCALE
    pass_product = threshold.pass_threshold_ppm * denominator
    warning_product = threshold.warning_threshold_ppm * denominator
    if threshold.direction is ProteinInferenceQualityMetricDirection.AT_LEAST:
        if value_product >= pass_product:
            return ProteinInferenceQualityMetricStatus.PASS
        if value_product >= warning_product:
            return ProteinInferenceQualityMetricStatus.WARNING
        return ProteinInferenceQualityMetricStatus.FAIL
    if value_product <= pass_product:
        return ProteinInferenceQualityMetricStatus.PASS
    if value_product <= warning_product:
        return ProteinInferenceQualityMetricStatus.WARNING
    return ProteinInferenceQualityMetricStatus.FAIL


def compute_quality_metrics(
    request: ComputeProteinInferenceQualityRequest,
    profile: ProteinInferenceAssayQualityProfile,
) -> tuple[ProteinInferenceQualityMetricResult, ...]:
    """Evaluate all eight metrics with exact state, ratio, threshold, and provenance closure."""

    ledger = request.fact_ledger
    if ledger is None:  # pragma: no cover - engine calls only inside the traversable envelope.
        raise _MissingFactLedgerError
    facts = protein_inference_metric_facts(request)
    thresholds = {item.metric_code: item for item in profile.thresholds}
    ledger_hash = fact_ledger_digest(ledger)
    profile_hash = profile_digest(profile)
    results: list[ProteinInferenceQualityMetricResult] = []
    no_value_states = {
        ProteinInferenceQualityObservationState.MISSING,
        ProteinInferenceQualityObservationState.NOT_APPLICABLE,
        ProteinInferenceQualityObservationState.UNSUPPORTED,
    }
    for code in ProteinInferenceQualityMetricCode:
        fact = facts[code]
        threshold = thresholds[code]
        provenance = ProteinInferenceQualityMetricProvenance(
            admission_result_digest=request.raw_quality_receipt.admission_result_digest,
            fact_ledger_digest=ledger_hash,
            profile_digest=profile_hash,
            threshold_digest=threshold_digest(threshold),
            source_binding_digest=ledger.source_binding_digest,
            claim_binding_digest=ledger.claim_binding_digest,
        )
        if fact.state in no_value_states:
            results.append(
                ProteinInferenceQualityMetricResult(
                    metric_code=code,
                    observation_state=fact.state,
                    status=(
                        ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                        if fact.state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
                        else ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
                    ),
                    required=threshold.required,
                    provenance=provenance,
                )
            )
            continue
        results.append(
            ProteinInferenceQualityMetricResult(
                metric_code=code,
                observation_state=fact.state,
                status=classify_quality_ratio(
                    fact.numerator,
                    fact.denominator,
                    threshold,
                ),
                required=threshold.required,
                numerator=fact.numerator,
                denominator=fact.denominator,
                value_ppm=(
                    (fact.numerator * M0304_RATE_SCALE + fact.denominator // 2) // fact.denominator
                    if fact.denominator
                    else None
                ),
                censored_count=fact.censored_count,
                provenance=provenance,
            )
        )
    return tuple(results)


__all__ = [
    "ProteinInferenceMetricFact",
    "classify_quality_ratio",
    "compute_quality_metrics",
    "matching_quality_profile",
    "protein_inference_metric_facts",
    "quality_ledger_bindings_close",
]
