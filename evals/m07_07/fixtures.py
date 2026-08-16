"""Deterministic synthetic M07-07 evaluation builders.

All candidates and upstream results are constructed in memory from pinned
synthetic references.  No file, URL, model weight, or scientific content is
opened by the evaluator.
"""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m07_06 import (
    M0706_CONSTRAINT_MEDIA_TYPE,
    M0706_CONTRACT_VERSION,
    M0706_NOMINAL_COVERAGE,
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m07_06.canonical import (
    canonical_request_digest as upstream_request_digest,
)
from glio_proteogen.contracts.m07_06.canonical import (
    result_payload_digest as upstream_result_digest,
)
from glio_proteogen.contracts.m07_07 import (
    M0707_NOMINAL_COVERAGE,
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrationMethod,
    CalibrationPolicy,
    CalibrationStratum,
    CalibrationStratumDimension,
    SelectiveCandidate,
    SelectiveSupportThreshold,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706Service,
)

_DIGEST = "sha256:" + "a" * 64
_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="0.1.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def context(consent_state: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact("control"),
    )
    return ExecutionContext(
        request_id="request.context",
        actor_id="actor.synthetic",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=artifact("identity"),
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent_state,
                policy_version="1.0.0",
                evidence=artifact("consent"),
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def upstream(*, supported: bool) -> CopyNumberDosageUncertaintyDecompositionResult:
    policy = UncertaintyDecompositionPolicy(
        policy_id="policy.upstream",
        version="1.0.0",
        method="synthetic",
        calibration_reference=artifact("calibration"),
    )
    request = DecomposeCopyNumberDosageUncertaintyRequest(
        request_id="request.upstream",
        context=context(),
        constraint_result=artifact("constraint", M0706_CONSTRAINT_MEDIA_TYPE),
        policy=policy,
        source_artifacts=(artifact("upstream"),),
    )
    if not supported:
        return M0706Service().execute(request)
    request_digest = upstream_request_digest(request)
    estimated = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.1,
        rationale="synthetic fixture only",
    )
    decomposition = UncertaintyDecomposition(
        decomposition_id="decomposition.synthetic",
        components=tuple(
            UncertaintyComponent(
                dimension=dimension,
                estimate=estimated,
                rationale="synthetic fixture only",
            )
            for dimension in UncertaintyDimension
        ),
        method="synthetic",
        model_reference=artifact("model"),
    )
    payload: dict[str, object] = {
        "result_id": "result.upstream",
        "result_version": M0706_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _DIGEST,
        "request": request,
        "status": UncertaintyDecompositionStatus.DECOMPOSED,
        "decomposition": decomposition,
        "sensitivity_envelope": SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=M0706_NOMINAL_COVERAGE,
            lower_bound=0.85,
            upper_bound=0.95,
            observed_coverage=0.90,
            rationale="synthetic fixture only",
        ),
        "findings": (),
        "abstention_reason": None,
        "parent_target": "proteotype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="upstream_supported",
            rationale="synthetic fixture only",
        ),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(request, request_digest, sha256_digest(policy)),
        "evidence": (),
        "limitations": (Limitation(code="synthetic", statement="Synthetic fixture only."),),
        "human_review_required": False,
    }
    constructed = CopyNumberDosageUncertaintyDecompositionResult.model_construct(
        **payload  # type: ignore[arg-type]
    )
    payload["result_digest"] = upstream_result_digest(constructed)
    return CopyNumberDosageUncertaintyDecompositionResult.model_validate(payload, strict=True)


def policy(*, include_all_dimensions: bool = True) -> CalibrationPolicy:
    dimensions = (
        tuple(CalibrationStratumDimension)
        if include_all_dimensions
        else (CalibrationStratumDimension.SITE,)
    )
    strata = tuple(
        CalibrationStratum(
            stratum_id=f"stratum.{dimension.value}",
            dimension=dimension,
            label=dimension.value,
            sample_count=20,
            observed_coverage=0.90,
            calibration_error=0.02,
        )
        for dimension in dimensions
    )
    return CalibrationPolicy(
        policy_id="policy.calibration",
        version="1.0.0",
        method=CalibrationMethod.CONFORMAL,
        calibration_reference=artifact("calibration.m0707"),
        strata=strata,
        support_threshold=SelectiveSupportThreshold(
            threshold_id="threshold.m0707",
            version="1.0.0",
            minimum_support_score=0.8,
            maximum_ood_score=0.2,
            maximum_calibration_error=0.05,
            target_coverage=M0707_NOMINAL_COVERAGE,
        ),
    )


def request(
    *,
    supported: bool = True,
    consent_state: ConsentState = ConsentState.GRANTED,
    include_all_dimensions: bool = True,
    candidates: tuple[SelectiveCandidate, ...] | None = None,
) -> CalibrateSelectiveCopyNumberDosageRequest:
    active_policy = policy(include_all_dimensions=include_all_dimensions)
    strata = tuple(item.stratum_id for item in active_policy.strata)
    active_candidates = candidates
    if active_candidates is None:
        active_candidates = (
            SelectiveCandidate(
                feature_id="feature.good",
                estimate_value=1.25,
                labels=("low", "high"),
                support_score=0.95,
                ood_score=0.05,
                calibration_error=0.02,
                stratum_ids=strata,
            ),
        )
    return CalibrateSelectiveCopyNumberDosageRequest(
        request_id="request.m0707",
        context=context(consent_state),
        uncertainty_result=upstream(supported=supported),
        policy=active_policy,
        source_artifacts=(artifact("input"),),
        candidates=active_candidates,
    )


__all__ = ["artifact", "context", "policy", "request", "upstream"]
