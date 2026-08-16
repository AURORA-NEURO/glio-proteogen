"""Deterministic M07-04 evaluator and canonical fixture constructor."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError

from glio_proteogen.contracts.m07_04 import (
    M0704_REPRESENTATION_MEDIA_TYPE,
    EstimateCopyNumberDosageProbabilisticRequest,
    EstimatorObservation,
    PosteriorEstimateKind,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
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
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704_PROXY_OPTIMIZER,
    M0704Plugin,
    M0704Service,
    ProbabilisticEstimatorAuthorizationError,
    ProbabilisticEstimatorReplayError,
)

_EXPECTED_ESTIMATE_COUNT = 2


def artifact(name: str, fill: str, media_type: str = "application/json") -> ArtifactReference:
    """Create a deterministic content-addressed fixture reference."""

    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="1.0.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def context(request_id: str = "request.m0704", *, accepted: bool = True) -> ExecutionContext:
    """Build all seven caller-declared controls."""

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
    representation_media_type: str = M0704_REPRESENTATION_MEDIA_TYPE,
    family: ProbabilisticEstimatorFamily = ProbabilisticEstimatorFamily.MECHANISM_GUIDED,
    optimizer: str = M0704_PROXY_OPTIMIZER,
    categorical: bool = False,
) -> EstimateCopyNumberDosageProbabilisticRequest:
    """Build one complete request covering the dossier's required inputs."""

    representation = artifact("m0702.representation", "1", representation_media_type)
    sources = (
        artifact("proteome.ms", "5"),
        artifact("genome.transcriptome", "6"),
        artifact("ptm.annotation", "7"),
    )
    evidence = tuple(
        EvidenceReference(reference=source, role="evidence", claim="locked M07-04 fixture")
        for source in sources
    )
    configuration = ProbabilisticEstimatorConfiguration(
        configuration_id="configuration.m0704",
        version="1.0.0",
        estimator_family=family,
        representation_media_type=M0704_REPRESENTATION_MEDIA_TYPE,
        objective="copy_number_dosage_posterior_projection",
        priors=(
            ProbabilisticPrior(
                prior_id="prior.m0704.copy-number",
                version="1.0.0",
                kind=ProbabilisticPriorKind.NORMAL,
                parameters=(2.0, 1.0),
                evidence=evidence[:1],
            ),
        ),
        optimizer=optimizer,
        seed=17,
        max_iterations=100,
        reference=representation,
        evidence=evidence,
    )
    observations: tuple[EstimatorObservation, ...]
    if categorical:
        observations = (
            EstimatorObservation(
                observation_id="observation.category",
                feature_id="feature.copy-number",
                unit="copy-number",
                source_artifact_digest=sources[0].digest,
                category="amplified",
            ),
        )
    else:
        observations = (
            EstimatorObservation(
                observation_id="observation.scalar",
                feature_id="feature.copy-number",
                unit="copy-number",
                source_artifact_digest=sources[0].digest,
                scalar_value=2.0,
            ),
            EstimatorObservation(
                observation_id="observation.interval",
                feature_id="feature.allelic-balance",
                unit="fraction",
                source_artifact_digest=sources[1].digest,
                interval_lower=0.25,
                interval_upper=0.75,
            ),
        )
    return EstimateCopyNumberDosageProbabilisticRequest(
        request_id="request.m0704",
        context=context("request.m0704", accepted=accepted_controls),
        representation_result=representation,
        baseline_result_digest="sha256:" + ("8" * 64),
        configuration=configuration,
        observations=observations,
        source_artifacts=sources,
    )


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:  # noqa: FBT001
    return {"name": name, "passed": passed, "detail": detail}


def evaluate() -> dict[str, object]:  # noqa: PLR0915
    """Run safety, estimator, interface, and replay checks."""

    service = M0704Service()
    plugin = M0704Plugin(service)
    checks: list[dict[str, object]] = []
    candidate = request()
    result = service.execute(candidate)
    checks.append(
        _check(
            "numeric_projection",
            result.status.value == "estimated"
            and len(result.estimates) == _EXPECTED_ESTIMATE_COUNT
            and result.estimates[0].kind is PosteriorEstimateKind.SCALAR
            and result.support_decision.status is SupportStatus.SUPPORTED
            and result.uncertainty.measurement.state.value == "not_estimable",
            "locked mechanism-guided proxy emits typed finite estimates only",
        )
    )
    try:
        replayed = service.verify(result)
        replay_passed = replayed == result and verify_result_digest(replayed)
    except ProbabilisticEstimatorReplayError:
        replay_passed = False
    checks.append(_check("transitive_replay", replay_passed, "result verifies and replays exactly"))

    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    try:
        service.verify(tampered)
    except ProbabilisticEstimatorReplayError:
        tamper_passed = True
    else:
        tamper_passed = False
    checks.append(_check("tamper_rejection", tamper_passed, "changed receipt fails digest closure"))

    abstained = service.execute(request(categorical=True))
    checks.append(
        _check(
            "unsupported_abstention",
            abstained.status.value == "abstained"
            and not abstained.estimates
            and abstained.human_review_required
            and abstained.support_decision.status is SupportStatus.REVIEW_REQUIRED,
            "categorical dosage is not coerced to a negative or numeric finding",
        )
    )
    unsupported = service.execute(request(family=ProbabilisticEstimatorFamily.LEARNED))
    checks.append(
        _check(
            "family_abstention",
            unsupported.status.value == "abstained" and not unsupported.estimates,
            "unfrozen learned family abstains safely",
        )
    )
    try:
        service.execute(request(accepted_controls=False))
    except ProbabilisticEstimatorAuthorizationError:
        controls_passed = True
    else:
        controls_passed = False
    checks.append(
        _check("control_fail_closed", controls_passed, "denied controls fail before execution")
    )

    strict_duplicate_passed = False
    try:
        strict_json_loads(b'{"request_id":"a","request_id":"b"}', max_bytes=1024)
    except StrictJsonError:
        strict_duplicate_passed = True
    checks.append(
        _check("strict_duplicate_rejection", strict_duplicate_passed, "duplicate keys fail closed")
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

    serialized = canonical_json_bytes(candidate.model_dump(mode="json"))
    token = plugin.validate(serialized)
    plugin_passed = plugin.run(token) == result and plugin.verify(result) == result
    checks.append(
        _check("plugin_parity", plugin_passed, "plugin parse/execute/verify equals service")
    )

    mapping_result = service.execute(candidate.model_dump(mode="json"))
    checks.append(
        _check(
            "mapping_transport",
            mapping_result == result,
            "strict mapping transport is canonical",
        )
    )
    checks.append(
        _check(
            "digest_stability",
            canonical_result_digest(result) == result.result_digest,
            "canonical result digest is stable",
        )
    )
    return {
        "module_id": "GLIO-PROTEOGEN-M07-04",
        "contract_version": "0.1.0-provisional",
        "passed": all(item["passed"] for item in checks),
        "check_count": len(checks),
        "checks": checks,
        "result_digest": canonical_result_digest(result),
    }


__all__ = ["artifact", "context", "evaluate", "request"]
