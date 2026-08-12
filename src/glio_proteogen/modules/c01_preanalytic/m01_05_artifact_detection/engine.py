"""Pure contract-facing artifact detection engine for M01-05."""

from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    ArtifactDetectionResult,
    ArtifactFlag,
    ArtifactRule,
    Comparison,
    DetectArtifactsRequest,
    DetectionDisposition,
    ExclusionMask,
    FlagDisposition,
    FlagProvenance,
    PosteriorEstimate,
    PosteriorState,
    SignalObservation,
    canonical_request_digest,
    configuration_digest,
    rule_digest,
    signal_digest,
)
from glio_proteogen.contracts.m01_05.v1 import M0105_CONTRACT_VERSION, M0105_MODULE_ID
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

_REQUEST_ADAPTER: Final[TypeAdapter[DetectArtifactsRequest]] = TypeAdapter(
    DetectArtifactsRequest
)
_LIMITATIONS: Final = (
    Limitation(
        code="artifact_detection_only",
        statement=(
            "This result reports configured technical artifact signals only; it does not infer "
            "proteotype, kinase state, biological absence, clinical meaning, or treatment."
        ),
    ),
    Limitation(
        code="external_controls_unverified",
        statement=(
            "Upstream controls, detector configuration, and signal artifacts are "
            "caller-declared references whose issuers M01-05 does not authenticate."
        ),
    ),
)


class M0105DetectionEngine:
    """Evaluate configured rules without I/O, learned inference, or evidence mutation."""

    __slots__ = ()

    def detect(self, request: DetectArtifactsRequest) -> ArtifactDetectionResult:
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
                    if item.disposition in {
                        FlagDisposition.REVIEW,
                        FlagDisposition.NOT_EVALUABLE,
                    }
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
        return ArtifactDetectionResult(
            detection_id=f"detection.m0105.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            configuration_digest=configuration_hash,
            disposition=disposition,
            flags=flags,
            exclusion_mask=ExclusionMask(
                excluded_target_ids=excluded,
                review_target_ids=review,
            ),
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                flags,
                request_hash,
                configuration_hash,
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is DetectionDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def detect_artifacts(request: DetectArtifactsRequest) -> ArtifactDetectionResult:
    return M0105DetectionEngine().detect(request)


def _flags(
    request: DetectArtifactsRequest,
    configuration_hash: str,
) -> tuple[ArtifactFlag, ...]:
    signals = {(item.target_id, item.signal_id): item for item in request.signals}
    targets = sorted({item.target_id for item in request.signals})
    grouped: dict[ArtifactClass, tuple[ArtifactRule, ...]] = {}
    for artifact_class in ArtifactClass:
        grouped[artifact_class] = tuple(
            sorted(
                (item for item in request.rules if item.artifact_class is artifact_class),
                key=lambda item: item.rule_id,
            )
        )
    flags: list[ArtifactFlag] = []
    for target_id in targets:
        for artifact_class, rules in grouped.items():
            if not rules:
                continue
            inputs = tuple(
                signals[(target_id, rule.signal_id)]
                for rule in rules
                if (target_id, rule.signal_id) in signals
            )
            flags.append(
                _flag(
                    target_id,
                    artifact_class,
                    rules,
                    inputs,
                    request=request,
                    configuration_hash=configuration_hash,
                )
            )
    return tuple(flags)


def _flag(  # noqa: PLR0913, PLR0917 - explicit inputs keep evaluation auditable.
    target_id: str,
    artifact_class: ArtifactClass,
    rules: tuple[ArtifactRule, ...],
    observations: tuple[SignalObservation, ...],
    request: DetectArtifactsRequest,
    configuration_hash: str,
) -> ArtifactFlag:
    input_map = {
        item.signal_id: Signal(
            state=SignalState(item.state.value),
            value=item.value,
        )
        for item in observations
    }
    configured_rules = tuple(_kernel_rule(rule) for rule in rules)
    incompatible = tuple(
        rule.signal_id
        for rule in rules
        if (observation := next(
            (item for item in observations if item.signal_id == rule.signal_id),
            None,
        ))
        is not None
        and not _compatible(rule, observation)
    )
    outcome = (
        Detection(
            posterior=None,
            decision=FlagDecision.NOT_EVALUABLE,
            triggered_rule_indexes=(),
            missing_signal_ids=tuple(sorted(set(incompatible))),
        )
        if incompatible
        else evaluate_rules(
            configured_rules,
            input_map,
            clear_posterior=max(rule.posterior_if_clear for rule in rules),
            review_threshold=request.policy.review_threshold,
            exclusion_threshold=request.policy.exclusion_threshold,
        )
    )
    posterior = PosteriorEstimate(
        state=(
            PosteriorState.NOT_EVALUABLE
            if outcome.posterior is None
            else PosteriorState.ESTIMATED
        ),
        value=outcome.posterior,
    )
    return ArtifactFlag(
        target_id=target_id,
        artifact_class=artifact_class,
        posterior=posterior,
        disposition=FlagDisposition(outcome.decision.value),
        rule_ids=tuple(rule.rule_id for rule in rules),
        provenance=FlagProvenance(
            configuration_digest=configuration_hash,
            rule_digests=tuple(dict.fromkeys(rule_digest(rule) for rule in rules)),
            signal_digests=tuple(
                dict.fromkeys(signal_digest(item) for item in observations)
            ),
        ),
        evidence=_bounded_references(
            chain(
                (request.detector_profile.evidence,),
                (item for observation in observations for item in observation.evidence),
            ),
            limit=64,
        ),
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


def _compatible(rule: ArtifactRule, observation: SignalObservation) -> bool:
    if observation.state.value != "observed":
        return True
    if rule.comparison is Comparison.BOOLEAN_EQUAL:
        return isinstance(observation.value, bool) and observation.unit is None
    return (
        isinstance(observation.value, float)
        and rule.unit is not None
        and observation.unit == rule.unit
    )


def _support(disposition: DetectionDisposition) -> SupportDecision:
    if disposition is DetectionDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="artifact_screen_quarantined",
            rationale="At least one artifact flag requires review or exclusion.",
        )
    return SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="artifact_screen_clear",
        rationale="Configured artifact rules completed without a review or exclusion flag.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("Signal measurement error was not calibrated in this request."),
        sampling=_not_estimable("The request supplies no sampling distribution."),
        parameter=_not_estimable("Configured rule posteriors are not fitted by M01-05."),
        model_form=_not_estimable("No learned or probabilistic-combination model is used."),
        identification=_not_estimable("Residual target attribution error is not scored."),
        support=_not_estimable("Support is a deterministic policy state, not a probability."),
        transport=_not_estimable("Transport beyond configured targets and signals is not scored."),
        sensitivity_notes=(
            "Triggered rules aggregate by maximum configured posterior only.",
            "Missing required signals are not evaluable and never interpreted as clear.",
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
    request: DetectArtifactsRequest,
    flags: tuple[ArtifactFlag, ...],
    request_hash: str,
    configuration_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _control_records(request.context)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_hash,
                configuration_hash,
                *(digest for flag in flags for digest in flag.provenance.rule_digests),
                *(digest for flag in flags for digest in flag.provenance.signal_digests),
                *(item.evidence_digest for item in controls),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0105.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0105_MODULE_ID,
        module_version=M0105_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(request: DetectArtifactsRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    control_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=(
                f"Caller-declared {role.value.replace('_', '-')} control reference; issuer and "
                "content are not authenticated by M01-05."
            ),
        )
        for role, reference in controls
    )
    signal_references = _bounded_references(
        chain(
            (request.detector_profile.evidence,),
            (item for signal in request.signals for item in signal.evidence),
        ),
        limit=505,
    )
    signal_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim="Caller-declared detector evidence; M01-05 does not retain its source payload.",
        )
        for reference in signal_references
    )
    return (*control_evidence, *signal_evidence)


def _bounded_references(
    references: Iterable[ArtifactReference],
    *,
    limit: int,
) -> tuple[ArtifactReference, ...]:
    return tuple(sorted(set(references), key=canonical_json_bytes)[:limit])


__all__ = ["M0105DetectionEngine", "detect_artifacts"]
