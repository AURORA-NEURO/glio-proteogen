"""Contract-facing deterministic protocol conformance evaluator for M02-01."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, TypeGuard

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_01 import (
    M0201_AUTHORITY_LIMITATION_CODE,
    M0201_CONFORMANCE_LIMITATION_CODE,
    M0201_CONTRACT_VERSION,
    M0201_MODULE_ID,
    AllowedTermPairRule,
    CompatibilityRule,
    ConditionalStateRule,
    ConformanceDisposition,
    ConformanceEvaluation,
    ConformanceStatus,
    EvaluateConformanceRequest,
    EvaluationState,
    FieldEvaluation,
    FieldObservation,
    NumericRangeRule,
    ObservationState,
    PresenceRule,
    RuleEvaluation,
    TermInSetRule,
    ValueKind,
    canonical_request_digest,
    configuration_digest,
    profile_digest,
    schema_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final[TypeAdapter[EvaluateConformanceRequest]] = TypeAdapter(
    EvaluateConformanceRequest
)
_AUTHORIZATION_MESSAGE: Final = "conformance evaluation requires accepted upstream controls"
_LIMITATIONS: Final = (
    Limitation(
        code=M0201_CONFORMANCE_LIMITATION_CODE,
        statement=(
            "This result validates declared metadata against one pinned schema and profile; "
            "it does not establish scientific, assay, biological, or clinical validity."
        ),
    ),
    Limitation(
        code=M0201_AUTHORITY_LIMITATION_CODE,
        statement=(
            "Upstream authorization, schema, vocabulary, and evidence authorities are "
            "caller-declared and are not authenticated by M02-01."
        ),
    ),
)


class ConformanceAuthorizationError(ValueError):
    """Authorization failed before metadata observations were traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M0201ConformanceEvaluator:
    """Evaluate one immutable request without persistence or unit conversion."""

    __slots__ = ()

    def evaluate(self, request: EvaluateConformanceRequest) -> ConformanceEvaluation:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_conformance_authorization(validated)
        field_evaluations = _field_evaluations(validated)
        rule_evaluations = _rule_evaluations(validated)
        status = _status(field_evaluations, rule_evaluations)
        disposition = (
            ConformanceDisposition.CONFORMANT
            if status is ConformanceStatus.CONFORMANT
            else ConformanceDisposition.QUARANTINED
        )
        request_hash = canonical_request_digest(validated)
        schema_hash = schema_digest(validated.protocol_schema)
        profile_hash = profile_digest(validated.conformance_profile)
        configuration_hash = configuration_digest(
            validated.protocol_schema,
            validated.conformance_profile,
        )
        return ConformanceEvaluation(
            evaluation_id=f"evaluation.m0201.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            schema_digest=schema_hash,
            profile_digest=profile_hash,
            configuration_digest=configuration_hash,
            status=status,
            disposition=disposition,
            field_evaluations=field_evaluations,
            rule_evaluations=rule_evaluations,
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                (request_hash, schema_hash, profile_hash, configuration_hash),
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is ConformanceDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_evaluation_digest=validated.supersedes_evaluation_digest,
        )


def evaluate_conformance(request: EvaluateConformanceRequest) -> ConformanceEvaluation:
    """Convenience entry point for stateless callers and agent tools."""

    return M0201ConformanceEvaluator().evaluate(request)


def preflight_conformance_authorization(candidate: object) -> None:
    """Reject raw unauthorized requests before reading schema or observations."""

    context = (
        candidate.context
        if isinstance(candidate, EvaluateConformanceRequest)
        else candidate.get("context")
        if isinstance(candidate, Mapping)
        else None
    )
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
        _value(_value(references, role), "state") != state
        for role, state in expected.items()
    ):
        raise ConformanceAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _field_evaluations(
    request: EvaluateConformanceRequest,
) -> tuple[FieldEvaluation, ...]:
    observations = {item.field_id: item for item in request.observations}
    vocabulary_terms = {
        item.vocabulary_id: frozenset(item.terms)
        for item in request.protocol_schema.vocabularies
    }
    results: list[FieldEvaluation] = []
    for field in sorted(request.protocol_schema.fields, key=lambda item: item.field_id):
        observation = observations.get(field.field_id)
        observation_ids = () if observation is None else (observation.observation_id,)
        if observation is None:
            state = EvaluationState.NOT_EVALUABLE if field.required else EvaluationState.PASS
            reason = "mandatory_field_missing" if field.required else "optional_field_absent"
        elif observation.state in {
            ObservationState.MISSING,
            ObservationState.UNKNOWN,
            ObservationState.CONFLICTING,
        }:
            state = EvaluationState.NOT_EVALUABLE
            category = "mandatory" if field.required else "optional"
            reason = f"{category}_value_{observation.state.value}"
        elif observation.state is ObservationState.NOT_APPLICABLE:
            state = EvaluationState.PASS if field.allow_not_applicable else EvaluationState.FAIL
            reason = (
                "not_applicable_allowed"
                if field.allow_not_applicable
                else "not_applicable_disallowed"
            )
        elif len(observation.values) < field.min_items:
            state, reason = EvaluationState.FAIL, "cardinality_below_minimum"
        elif len(observation.values) > field.max_items:
            state, reason = EvaluationState.FAIL, "cardinality_exceeded"
        elif field.unit_id != observation.unit_id:
            state, reason = EvaluationState.FAIL, "unit_incompatible"
        elif not all(_value_matches_kind(value, field.value_kind) for value in observation.values):
            state, reason = EvaluationState.FAIL, "value_type_incompatible"
        elif field.vocabulary_id is not None and not all(
            value in vocabulary_terms[field.vocabulary_id]
            for value in observation.values
        ):
            state, reason = EvaluationState.FAIL, "controlled_term_unsupported"
        else:
            state, reason = EvaluationState.PASS, "field_conformant"
        results.append(
            FieldEvaluation(
                field_id=field.field_id,
                state=state,
                reason_code=reason,
                observation_ids=observation_ids,
            )
        )
    return tuple(results)


def _value_matches_kind(value: object, kind: ValueKind) -> bool:
    if kind in {ValueKind.TEXT, ValueKind.TERM}:
        return isinstance(value, str)
    if kind is ValueKind.BOOLEAN:
        return isinstance(value, bool)
    if kind is ValueKind.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, int | float) and not isinstance(value, bool)


def _rule_evaluations(
    request: EvaluateConformanceRequest,
) -> tuple[RuleEvaluation, ...]:
    observations = {item.field_id: item for item in request.observations}
    fields = {item.field_id: item for item in request.protocol_schema.fields}
    results: list[RuleEvaluation] = []
    for rule in sorted(request.protocol_schema.compatibility_rules, key=lambda item: item.rule_id):
        state = _rule_state(rule, observations)
        results.append(
            RuleEvaluation(
                rule_id=rule.rule_id,
                state=state,
                action=rule.action,
                reason_code=(
                    _rule_reason(
                        rule,
                        state,
                        observations.get(rule.field_id),
                        required=fields[rule.field_id].required,
                    )
                ),
                remediation_code=(
                    None if state is EvaluationState.PASS else rule.remediation_code
                ),
            )
        )
    return tuple(results)


def _rule_reason(
    rule: CompatibilityRule,
    state: EvaluationState,
    observation: FieldObservation | None,
    *,
    required: bool,
) -> str:
    if state is EvaluationState.PASS:
        return "rule_conformant"
    if not isinstance(rule, PresenceRule) or observation is None:
        return rule.reason_code
    if observation.state in {
        ObservationState.MISSING,
        ObservationState.UNKNOWN,
        ObservationState.CONFLICTING,
    }:
        category = "mandatory" if required else "optional"
        return f"{category}_value_{observation.state.value}"
    if observation.state is ObservationState.NOT_APPLICABLE:
        return "not_applicable_disallowed"
    return rule.reason_code


def _rule_state(  # noqa: C901, PLR0911 - direct closed-rule dispatch.
    rule: CompatibilityRule,
    observations: Mapping[str, FieldObservation],
) -> EvaluationState:
    observation = observations.get(rule.field_id)
    if isinstance(rule, PresenceRule):
        return _presence_state(observation)
    if isinstance(rule, ConditionalStateRule):
        trigger = observations.get(rule.trigger_field_id)
        if not _observed(trigger):
            return EvaluationState.NOT_EVALUABLE
        trigger_values = trigger.values
        if not any(value in rule.trigger_terms for value in trigger_values):
            return EvaluationState.PASS
        if observation is None:
            return EvaluationState.NOT_EVALUABLE
        return (
            EvaluationState.PASS
            if observation.state is rule.required_state
            else EvaluationState.FAIL
        )
    if isinstance(rule, AllowedTermPairRule):
        other = observations.get(rule.other_field_id)
        if not _observed(observation) or not _observed(other):
            return EvaluationState.NOT_EVALUABLE
        pairs = {(item.left, item.right) for item in rule.allowed_pairs}
        values = observation.values
        other_values = other.values
        return (
            EvaluationState.PASS
            if all((left, right) in pairs for left in values for right in other_values)
            else EvaluationState.FAIL
        )
    if not _observed(observation):
        return EvaluationState.NOT_EVALUABLE
    values = observation.values
    if isinstance(rule, TermInSetRule):
        matched = all(isinstance(value, str) and value in rule.allowed_terms for value in values)
    elif isinstance(rule, NumericRangeRule):
        matched = all(_number_in_range(value, rule.minimum, rule.maximum) for value in values)
    else:
        matched = all(isinstance(value, bool) and value is rule.expected for value in values)
    return EvaluationState.PASS if matched else EvaluationState.FAIL


def _observed(candidate: FieldObservation | None) -> TypeGuard[FieldObservation]:
    return candidate is not None and candidate.state is ObservationState.OBSERVED


def _presence_state(candidate: FieldObservation | None) -> EvaluationState:
    if candidate is None or candidate.state in {
        ObservationState.MISSING,
        ObservationState.UNKNOWN,
        ObservationState.CONFLICTING,
    }:
        return EvaluationState.NOT_EVALUABLE
    return (
        EvaluationState.PASS
        if candidate.state is ObservationState.OBSERVED
        else EvaluationState.FAIL
    )


def _number_in_range(value: object, minimum: float | None, maximum: float | None) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    number = float(value)
    return (minimum is None or number >= minimum) and (maximum is None or number <= maximum)


def _status(
    fields: tuple[FieldEvaluation, ...],
    rules: tuple[RuleEvaluation, ...],
) -> ConformanceStatus:
    states = tuple(item.state for item in fields) + tuple(item.state for item in rules)
    if EvaluationState.FAIL in states:
        return ConformanceStatus.NONCONFORMANT
    if EvaluationState.NOT_EVALUABLE in states:
        return ConformanceStatus.INDETERMINATE
    return ConformanceStatus.CONFORMANT


def _support(disposition: ConformanceDisposition) -> SupportDecision:
    if disposition is ConformanceDisposition.CONFORMANT:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="metadata_conformant",
            rationale="Declared metadata conforms to the pinned schema and profile.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="metadata_quarantined",
        rationale="Metadata is nonconformant or unresolved and requires review.",
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)

    return UncertaintyProfile(
        measurement=unavailable("Metadata conformance does not estimate measurement uncertainty."),
        sampling=unavailable("Metadata conformance does not estimate sampling uncertainty."),
        parameter=unavailable("The deterministic evaluator fits no parameters."),
        model_form=unavailable("No learned model is used."),
        identification=unavailable("Metadata identity is caller-declared."),
        support=unavailable("Support follows deterministic schema rules."),
        transport=unavailable("External schema authority is not assessed."),
    )


def _controls(request: EvaluateConformanceRequest) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
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
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(
    request: EvaluateConformanceRequest,
    hashes: tuple[str, str, str, str],
) -> ProvenanceRecord:
    request_hash, schema_hash, active_profile_hash, configuration_hash = hashes
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m0201.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0201_MODULE_ID,
        module_version=M0201_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    schema_hash,
                    active_profile_hash,
                    configuration_hash,
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(request: EvaluateConformanceRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: tuple[ArtifactReference, ...] = (
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
        request.protocol_schema.evidence,
        request.conformance_profile.evidence,
        *(item.evidence for item in request.protocol_schema.vocabularies),
        *(item.evidence for item in request.protocol_schema.units),
    )
    return tuple(
        EvidenceReference(
            reference=item,
            role="evidence",
            claim="Caller-declared content-addressed protocol-conformance evidence.",
        )
        for item in sorted(set(artifacts), key=canonical_json_bytes)
    )


__all__ = [
    "ConformanceAuthorizationError",
    "M0201ConformanceEvaluator",
    "evaluate_conformance",
    "preflight_conformance_authorization",
]
