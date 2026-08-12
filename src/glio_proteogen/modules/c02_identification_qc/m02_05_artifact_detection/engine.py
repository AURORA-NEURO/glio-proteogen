"""Stateless M02-05 wrapper over the shared deterministic artifact-rule kernel."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import chain
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_05 import ArtifactRule, Comparison
from glio_proteogen.contracts.m02_05 import (
    M0205_ARTIFACT_LIMITATION_CODE,
    M0205_AUTHORITY_LIMITATION_CODE,
    M0205_CONTRACT_VERSION,
    M0205_MODULE_ID,
    ArtifactClass,
    DetectIdentificationArtifactsRequest,
    DetectionDisposition,
    ExclusionMask,
    FlagDisposition,
    FlagProvenance,
    IdentificationArtifactDetectionResult,
    IdentificationArtifactFlag,
    IdentificationSignalObservation,
    IdentificationSignalState,
    PosteriorEstimate,
    PosteriorState,
    RuleEvaluationTrace,
    canonical_request_digest,
    configuration_digest,
    policy_digest,
    profile_digest,
    rule_digest,
    signal_summary_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.kernel import (
    Detection,
    FlagDecision,
    Predicate,
    Rule,
    Signal,
    SignalState,
    evaluate_rules,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_REQUEST_ADAPTER: Final[TypeAdapter[DetectIdentificationArtifactsRequest]] = TypeAdapter(
    DetectIdentificationArtifactsRequest
)
_LIMITATIONS: Final = (
    Limitation(
        code=M0205_ARTIFACT_LIMITATION_CODE,
        statement=(
            "This result screens configured identification-evidence artifact signals only; "
            "it does not infer protein subtype, proteotype, biology, kinase activity, or treatment."
        ),
    ),
    Limitation(
        code=M0205_AUTHORITY_LIMITATION_CODE,
        statement=(
            "Upstream controls, detector configuration, and aggregate signals are "
            "caller-declared references whose issuers M02-05 does not authenticate."
        ),
    ),
)


class IdentificationArtifactAuthorizationError(ValueError):
    """Denied controls detected before typed signal validation."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize identification artifact detection")


class M0205IdentificationArtifactEngine:
    """Evaluate C02 aggregate signals using the shared M01-05 rule kernel."""

    __slots__ = ()

    def detect(self, request: object) -> IdentificationArtifactDetectionResult:
        preflight_identification_artifact_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        configuration_hash = configuration_digest(
            validated.detector_profile,
            validated.policy,
            validated.rules,
        )
        flags = _flags(validated, configuration_hash)
        excluded = tuple(
            sorted(
                {
                    item.target_id
                    for item in flags
                    if item.disposition is FlagDisposition.EXCLUDE
                }
            )
        )
        review = tuple(
            sorted(
                {
                    item.target_id
                    for item in flags
                    if item.disposition
                    in {FlagDisposition.REVIEW, FlagDisposition.NOT_EVALUABLE}
                }
                - set(excluded)
            )
        )
        disposition = (
            DetectionDisposition.QUARANTINED
            if excluded or review
            else DetectionDisposition.ACCEPTED
        )
        request_hash = canonical_request_digest(validated)
        active_profile_digest = profile_digest(validated.detector_profile)
        active_policy_digest = policy_digest(validated.policy)
        return IdentificationArtifactDetectionResult(
            detection_id=f"detection.m0205.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            profile_id=validated.detector_profile.profile_id,
            profile_version=validated.detector_profile.version,
            profile_digest=active_profile_digest,
            profile_evidence_digest=validated.detector_profile.evidence.digest,
            required_rule_ids=tuple(sorted(validated.detector_profile.required_rule_ids)),
            policy_id=validated.policy.policy_id,
            policy_version=validated.policy.version,
            policy_digest=active_policy_digest,
            enabled_classes=tuple(
                sorted(validated.policy.enabled_classes, key=lambda item: item.value)
            ),
            max_rules=validated.policy.max_rules,
            max_signals=validated.policy.max_signals,
            max_flags=validated.policy.max_flags,
            max_evaluations=validated.policy.max_evaluations,
            configuration_digest=configuration_hash,
            disposition=disposition,
            review_threshold=validated.policy.review_threshold,
            exclusion_threshold=validated.policy.exclusion_threshold,
            evaluated_target_ids=tuple(
                sorted({item.target_id for item in validated.signals})
            ),
            flags=flags,
            exclusion_mask=ExclusionMask(
                excluded_target_ids=excluded,
                review_target_ids=review,
            ),
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                request_hash,
                active_profile_digest,
                active_policy_digest,
                configuration_hash,
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is DetectionDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def detect_identification_artifacts(request: object) -> IdentificationArtifactDetectionResult:
    return M0205IdentificationArtifactEngine().detect(request)


def preflight_identification_artifact_authorization(candidate: object) -> None:
    """Reject raw denial before Pydantic traverses aggregate signals."""

    context = _value(candidate, "context")
    references = _value(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _state(_value(_value(references, role), "state")) != state
        for role, state in expected.items()
    ):
        raise IdentificationArtifactAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _flags(
    request: DetectIdentificationArtifactsRequest,
    configuration_hash: str,
) -> tuple[IdentificationArtifactFlag, ...]:
    signals = {(item.target_id, item.signal_id): item for item in request.signals}
    targets = sorted({item.target_id for item in request.signals})
    grouped = {
        artifact_class: tuple(
            sorted(
                (item for item in request.rules if item.artifact_class is artifact_class),
                key=lambda item: item.rule_id,
            )
        )
        for artifact_class in ArtifactClass
    }
    return tuple(
        _flag(
            target_id,
            artifact_class,
            rules,
            tuple(
                signals[(target_id, rule.signal_id)]
                for rule in rules
                if (target_id, rule.signal_id) in signals
            ),
            request=request,
            configuration_hash=configuration_hash,
        )
        for target_id in targets
        for artifact_class, rules in grouped.items()
        if rules
    )


def _flag(  # noqa: PLR0913, PLR0917 - explicit audit inputs.
    target_id: str,
    artifact_class: ArtifactClass,
    rules: tuple[ArtifactRule, ...],
    observations: tuple[IdentificationSignalObservation, ...],
    request: DetectIdentificationArtifactsRequest,
    configuration_hash: str,
) -> IdentificationArtifactFlag:
    observations_by_signal = {item.signal_id: item for item in observations}
    canonical_observations = tuple(
        item.model_copy(
            update={"evidence": tuple(sorted(item.evidence, key=canonical_json_bytes))}
        )
        for item in sorted(observations_by_signal.values(), key=lambda item: item.signal_id)
    )
    by_signal = {item.signal_id: item for item in canonical_observations}
    kernel_signals = {
        item.signal_id: Signal(
            state=(
                SignalState.OBSERVED
                if item.state is IdentificationSignalState.OBSERVED
                else SignalState.MISSING
                if item.state in {
                    IdentificationSignalState.MISSING,
                    IdentificationSignalState.UNSUPPORTED,
                }
                else SignalState.NOT_APPLICABLE
            ),
            value=item.value,
        )
        for item in canonical_observations
    }
    kernel_rules = tuple(_kernel_rule(item) for item in rules)
    unsupported = any(
        item.state is IdentificationSignalState.UNSUPPORTED
        for item in canonical_observations
    )
    no_observed = not any(
        item.state is IdentificationSignalState.OBSERVED
        for item in canonical_observations
    )
    outcome = (
        Detection(None, FlagDecision.NOT_EVALUABLE, (), ())
        if unsupported or no_observed
        else evaluate_rules(
            kernel_rules,
            kernel_signals,
            clear_posterior=max(item.posterior_if_clear for item in rules),
            review_threshold=request.policy.review_threshold,
            exclusion_threshold=request.policy.exclusion_threshold,
        )
    )
    triggered_indexes = set(outcome.triggered_rule_indexes)
    evaluations = tuple(
        _trace(
            rule,
            by_signal.get(rule.signal_id),
            target_id=target_id,
            triggered=index in triggered_indexes,
        )
        for index, rule in enumerate(rules)
    )
    references = _unique_references(
        chain(
            (request.detector_profile.evidence,),
            (reference for item in canonical_observations for reference in item.evidence),
        )
    )
    return IdentificationArtifactFlag(
        target_id=target_id,
        artifact_class=artifact_class,
        posterior=PosteriorEstimate(
            state=(
                PosteriorState.NOT_EVALUABLE
                if outcome.posterior is None
                else PosteriorState.ESTIMATED
            ),
            value=outcome.posterior,
        ),
        disposition=FlagDisposition(outcome.decision.value),
        rule_ids=tuple(item.rule_id for item in rules),
        evaluations=evaluations,
        provenance=FlagProvenance(
            configuration_digest=configuration_hash,
            rule_digests=tuple(rule_digest(item) for item in rules),
            signal_digests=tuple(
                signal_summary_digest(item) for item in canonical_observations
            ),
        ),
        evidence=references,
    )


def _trace(
    rule: ArtifactRule,
    observation: IdentificationSignalObservation | None,
    *,
    target_id: str,
    triggered: bool,
) -> RuleEvaluationTrace:
    return RuleEvaluationTrace(
        target_id=target_id,
        rule_id=rule.rule_id,
        artifact_class=rule.artifact_class,
        signal_id=rule.signal_id,
        rule_digest=rule_digest(rule),
        rule=rule,
        signal_digest=(
            signal_summary_digest(observation)
            if observation is not None
            else None
        ),
        signal_state=observation.state if observation is not None else None,
        signal_value=observation.value if observation is not None else None,
        signal_unit=observation.unit if observation is not None else None,
        evidence_digests=(
            tuple(item.digest for item in observation.evidence)
            if observation is not None
            else ()
        ),
        triggered=triggered,
        posterior_if_triggered=rule.posterior_if_triggered,
        posterior_if_clear=rule.posterior_if_clear,
        required_signal=rule.required_signal,
        exclusion_eligible=rule.exclusion_eligible,
    )


def _kernel_rule(rule: ArtifactRule) -> Rule:
    predicate = {
        Comparison.GREATER_THAN_OR_EQUAL: Predicate.GREATER_THAN_OR_EQUAL,
        Comparison.LESS_THAN_OR_EQUAL: Predicate.LESS_THAN_OR_EQUAL,
        Comparison.WITHIN_RANGE: Predicate.WITHIN_RANGE,
        Comparison.OUTSIDE_RANGE: Predicate.OUTSIDE_RANGE,
        Comparison.BOOLEAN_EQUAL: Predicate.EQUAL,
    }[rule.comparison]
    threshold: float | bool = (
        rule.expected_bool
        if rule.expected_bool is not None
        else rule.threshold
        if rule.threshold is not None
        else 0.0
    )
    return Rule(
        signal_id=rule.signal_id,
        predicate=predicate,
        threshold=threshold,
        triggered_posterior=rule.posterior_if_triggered,
        upper_threshold=rule.upper_threshold,
        required=rule.required_signal,
        exclusion_eligible=rule.exclusion_eligible,
    )


def _support(disposition: DetectionDisposition) -> SupportDecision:
    if disposition is DetectionDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="identification_artifact_screen_quarantined",
            rationale="At least one identification-evidence artifact flag requires review.",
        )
    return SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="identification_artifact_screen_clear",
        rationale="Configured identification-evidence artifact rules completed without a flag.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("Aggregate signal measurement error is not calibrated."),
        sampling=_not_estimable("The request supplies no sampling distribution."),
        parameter=_not_estimable("Configured posteriors are reviewed triage values."),
        model_form=_not_estimable("No learned posterior-combination model is used."),
        identification=_not_estimable("Residual identification attribution error is not scored."),
        support=_not_estimable("Support is a deterministic policy state."),
        transport=_not_estimable("Transport beyond the pinned profile is not scored."),
        sensitivity_notes=(
            "Triggered rules aggregate by maximum configured posterior only.",
            "Missing or unsupported evidence is not evaluable and never interpreted as clear.",
        ),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in values
    )


def _provenance(
    request: DetectIdentificationArtifactsRequest,
    request_hash: str,
    active_profile_digest: str,
    active_policy_digest: str,
    configuration_hash: str,
) -> ProvenanceRecord:
    controls = _control_records(request.context)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_hash,
                active_profile_digest,
                active_policy_digest,
                configuration_hash,
                request.detector_profile.evidence.digest,
                *sorted(rule_digest(item) for item in request.rules),
                *(item.evidence_digest for item in controls),
            )
        )
    )
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m0205.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0205_MODULE_ID,
        module_version=M0205_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(
    request: DetectIdentificationArtifactsRequest,
) -> tuple[EvidenceReference, ...]:
    controls = _control_records(request.context)
    references_by_digest = {
        item.digest: item
        for item in (
            request.context.references.approved_configuration.evidence,
            request.context.references.identity_lineage.evidence,
            request.context.references.provenance.evidence,
            request.context.references.consent.evidence,
            request.context.references.quality.evidence,
            request.context.references.support.evidence,
            request.context.references.intended_use.evidence,
        )
    }
    control_evidence = tuple(
        EvidenceReference(
            reference=references_by_digest[item.evidence_digest],
            role="evidence",
            claim=f"Caller-declared {item.role.value} control; issuer is not authenticated.",
        )
        for item in controls
    )
    profile_reference = request.detector_profile.evidence.model_copy(
        update={"digest": request.detector_profile.evidence.digest}
    )
    profile_evidence = EvidenceReference(
        reference=profile_reference,
        role="evidence",
        claim="Caller-declared identification detector profile; issuer is not authenticated.",
    )
    return (*control_evidence, profile_evidence)


def _unique_references(references: Iterable[ArtifactReference]) -> tuple[ArtifactReference, ...]:
    return tuple(sorted(set(references), key=canonical_json_bytes))


__all__ = [
    "IdentificationArtifactAuthorizationError",
    "M0205IdentificationArtifactEngine",
    "detect_identification_artifacts",
    "preflight_identification_artifact_authorization",
]
