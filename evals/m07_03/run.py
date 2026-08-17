"""Deterministic M07-03 evaluator and canonical fixture constructor."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m07_03 import (
    M0703_REPRESENTATION_MEDIA_TYPE,
    BaselineEstimate,
    BaselineEstimateKind,
    BaselineEstimatorFamily,
    BaselinePreprocessingPolicy,
    BaselineTuningRecord,
    EstimateCopyNumberDosageBaselineRequest,
    MatureBaselineConfiguration,
    canonical_result_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator import (
    M0703AuthorizationError,
    M0703Plugin,
    M0703ReplayVerificationError,
    M0703Service,
)


def artifact(
    name: str,
    fill: str,
    media_type: str = "application/json",
) -> ArtifactReference:
    """Create a deterministic content-addressed reference for fixture data."""

    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="1.0.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def context(request_id: str = "request.m0703", *, accepted: bool = True) -> ExecutionContext:
    """Build the seven caller-declared control decisions."""

    upstream_state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity_state = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent_state = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    identity = artifact("identity", "b")
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=upstream_state,
                policy_version="1.0.0",
                evidence=artifact("control", "a"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=identity_state,
                policy_version="1.0.0",
                binding_digest=identity.digest,
                evidence=identity,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=upstream_state,
                policy_version="1.0.0",
                evidence=artifact("provenance", "c"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent_state,
                policy_version="1.0.0",
                evidence=artifact("consent", "d"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=upstream_state,
                policy_version="1.0.0",
                evidence=artifact("quality", "e"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=upstream_state,
                policy_version="1.0.0",
                evidence=artifact("support", "f"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended-use",
                state=upstream_state,
                policy_version="1.0.0",
                evidence=artifact("intended", "0"),
            ),
        ),
    )


def request(
    *,
    accepted_controls: bool = True,
    representation_media_type: str = M0703_REPRESENTATION_MEDIA_TYPE,
) -> EstimateCopyNumberDosageBaselineRequest:
    """Build one complete, owner-reviewable M07-03 request."""

    representation = artifact("m0702.representation", "1", representation_media_type)
    preprocessing_evidence = EvidenceReference(
        reference=artifact("preprocessing", "2"),
        role="evidence",
        claim="locked unit and missingness policy",
    )
    tuning_evidence = EvidenceReference(
        reference=artifact("tuning", "3"),
        role="evidence",
        claim="locked baseline tuning record",
    )
    configuration_evidence = EvidenceReference(
        reference=artifact("configuration", "4"),
        role="evidence",
        claim="approved mature baseline configuration",
    )
    configuration = MatureBaselineConfiguration(
        configuration_id="configuration.m0703",
        version="1.0.0",
        estimator_family=BaselineEstimatorFamily.ROBUST_STATISTICAL,
        representation_media_type=M0703_REPRESENTATION_MEDIA_TYPE,
        preprocessing=BaselinePreprocessingPolicy(
            policy_id="policy.preprocessing",
            version="1.0.0",
            operations=("unit_normalization", "missingness_preservation"),
            evidence=(preprocessing_evidence,),
        ),
        tuning=BaselineTuningRecord(
            tuning_id="tuning.m0703",
            version="1.0.0",
            method="locked_robust_fit",
            objective="calibration_error",
            seed=7,
            metrics=("coverage_90", "median_absolute_error"),
            evidence=(tuning_evidence,),
        ),
        reference=representation,
        evidence=(configuration_evidence,),
    )
    return EstimateCopyNumberDosageBaselineRequest(
        request_id="request.m0703",
        context=context("request.m0703", accepted=accepted_controls),
        representation_result=representation,
        configuration=configuration,
        source_artifacts=(
            artifact("proteome.ms", "5"),
            artifact("genome.transcriptome", "6"),
            artifact("ptm.annotation", "7"),
        ),
    )


def _check(name: str, passed: bool, detail: str, /) -> dict[str, object]:  # noqa: FBT001
    return {"name": name, "passed": passed, "detail": detail}


def evaluate() -> dict[str, object]:
    """Run the locked safety and replay checks used by release evidence."""

    service = M0703Service()
    plugin = M0703Plugin(service)
    checks: list[dict[str, object]] = []
    result = service.execute(request())
    checks.append(
        _check(
            "safe_abstention",
            result.status.value == "abstained"
            and not result.estimates
            and result.abstention_reason is not None
            and result.human_review_required
            and result.support_decision.status is SupportStatus.REVIEW_REQUIRED
            and all(
                dimension.state.value == "not_estimable"
                for dimension in (
                    result.uncertainty.measurement,
                    result.uncertainty.sampling,
                    result.uncertainty.parameter,
                    result.uncertainty.model_form,
                    result.uncertainty.identification,
                    result.uncertainty.support,
                    result.uncertainty.transport,
                )
            ),
            "unsupported calibration is explicit and review-required",
        )
    )
    try:
        replayed = service.verify(result)
        replay_passed = replayed == result and verify_result_digest(replayed)
    except M0703ReplayVerificationError:
        replay_passed = False
    checks.append(
        _check("transitive_replay", replay_passed, "result verifies and reproduces exactly")
    )

    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    try:
        service.verify(tampered)
    except M0703ReplayVerificationError:
        tamper_passed = True
    else:
        tamper_passed = False
    checks.append(_check("tamper_rejection", tamper_passed, "changed payload fails digest/replay"))

    try:
        service.execute(request(accepted_controls=False))
    except M0703AuthorizationError:
        controls_passed = True
    else:
        controls_passed = False
    checks.append(
        _check("control_fail_closed", controls_passed, "unresolved controls are rejected")
    )

    try:
        service.execute(request(representation_media_type="application/json"))
    except ValidationError:
        media_passed = True
    else:
        media_passed = False
    checks.append(
        _check("representation_boundary", media_passed, "wrong upstream media type is rejected")
    )

    strict_duplicate_passed = False
    try:
        strict_json_loads(b'{"request_id":"a","request_id":"b"}', max_bytes=1024)
    except StrictJsonError:
        strict_duplicate_passed = True
    checks.append(
        _check(
            "strict_json_duplicate_rejection",
            strict_duplicate_passed,
            "duplicate keys fail closed",
        )
    )

    estimate_shape_passed = False
    try:
        BaselineEstimate(
            feature_id="feature.bad",
            kind=BaselineEstimateKind.SCALAR,
            unit="copies",
            estimate_value=1.0,
            lower_bound=0.0,
        )
    except ValidationError:
        estimate_shape_passed = True
    checks.append(
        _check(
            "typed_estimate_shape",
            estimate_shape_passed,
            "scalar/interval fields cannot be mixed",
        )
    )

    token = plugin.validate(canonical_json_bytes(request().model_dump(mode="json")))
    plugin_passed = plugin.run(token) == result and plugin.verify(result) == result
    checks.append(
        _check("plugin_parity", plugin_passed, "plugin parse/execute/verify equals service")
    )

    return {
        "module_id": "GLIO-PROTEOGEN-M07-03",
        "contract_version": "0.1.0-provisional",
        "passed": all(item["passed"] for item in checks),
        "check_count": len(checks),
        "checks": checks,
        "result_digest": canonical_result_digest(result),
    }


__all__ = ["artifact", "context", "evaluate", "request"]
