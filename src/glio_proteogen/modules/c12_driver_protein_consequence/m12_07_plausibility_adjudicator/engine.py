"""Deterministic M12-07 plausibility and negative-control adjudicator.

M12-07 does not authenticate or inspect upstream artifacts.  It consumes
caller-declared control observations, keeps every hard control and conflict
visible, and abstains whenever a required observation is absent or unsafe.
This makes the provisional implementation useful for integration testing
without pretending that the dossier has frozen a scientific estimator ABI.
"""

from __future__ import annotations

import json
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_07 import (
    M1207_CONTRACT_VERSION,
    M1207_MODULE_ID,
    AdjudicateBiomarkerPanelPlausibilityRequest,
    BiomarkerPanelPlausibilityAdjudicationResult,
    ControlEvaluation,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityControl,
    PlausibilityFinding,
    PlausibilityFindingCode,
    PlausibilityGrade,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelPlausibilityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelPlausibilityAdjudicationResult)

_LIMITATIONS: Final = (
    Limitation(
        code="m1207.provisional_abi",
        statement="M12-07 ABI is provisional pending owner confirmation.",
    ),
    Limitation(
        code="m1207.no_kinase_inference",
        statement="This module does not infer kinase activity or treatment recommendations.",
    ),
    Limitation(
        code="m1207.caller_declared_observations",
        statement=(
            "Control observations are caller-declared and are not independently authenticated."
        ),
    ),
)

_UNCERTAINTY_NOTES: Final = (
    "Measurement, sampling, parameter, model-form, identification, support and "
    "transport uncertainty are emitted separately.",
    "Unsupported, missing or conflicting observations are abstained rather than "
    "converted into negative findings.",
)
_HIGH_GRADE_MIN_CONTROLS: Final = 6
_MODERATE_GRADE_MIN_CONTROLS: Final = 4


class M1207PlausibilityAuthorizationError(ValueError):
    """Raised when immutable upstream identity, consent or control gates deny execution."""

    def __init__(self, reason: str = "upstream controls do not authorize M12-07 execution") -> None:
        super().__init__(reason)


def _value(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1207_authorization(candidate: object) -> None:
    """Require all seven caller-declared upstream gates before evaluating controls."""

    context = (
        candidate.get("context")
        if isinstance(candidate, dict)
        else getattr(candidate, "context", None)
    )
    references = (
        context.get("references")
        if isinstance(context, dict)
        else getattr(context, "references", None)
    )
    if references is None:
        raise M1207PlausibilityAuthorizationError(  # noqa: TRY003
            "M12-07 requires all seven upstream control references"
        )
    expected = (
        ("approved_configuration", "accepted"),
        ("identity_lineage", "resolved"),
        ("provenance", "accepted"),
        ("consent", "granted"),
        ("quality", "accepted"),
        ("support", "accepted"),
        ("intended_use", "accepted"),
    )
    for role, allowed in expected:
        reference = (
            references.get(role)
            if isinstance(references, dict)
            else getattr(references, role, None)
        )
        state_value = (
            reference.get("state")
            if isinstance(reference, dict)
            else getattr(reference, "state", None)
        )
        state = _value(state_value) if reference is not None else None
        if state != allowed:
            raise M1207PlausibilityAuthorizationError(  # noqa: TRY003
                f"M12-07 upstream control {role} is not authorized"
            )


def _validated_request(request: object) -> AdjudicateBiomarkerPanelPlausibilityRequest:
    preflight_m1207_authorization(request)
    validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
    return _REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(validated.model_dump(mode="json")),
        strict=True,
    )


def _evaluate_control(control: PlausibilityControl) -> ControlEvaluation:
    outcome = control.declared_outcome
    observed = control.declared_observed_direction
    expected = control.expected_direction
    evidence = control.required_evidence
    control_id = control.control_id
    criterion = control.criterion
    if outcome is None:
        return ControlEvaluation(
            control_id=control_id,
            outcome=ControlOutcome.NOT_EVALUABLE,
            observed_direction=observed,
            rationale="No caller-declared control outcome was supplied; safe abstention applies.",
            evidence=evidence,
        )
    if outcome is ControlOutcome.PASSED and expected is not None:
        if observed is None:
            return ControlEvaluation(
                control_id=control_id,
                outcome=ControlOutcome.NOT_EVALUABLE,
                rationale="Expected direction was declared without an observed direction.",
                evidence=evidence,
            )
        if observed.casefold() != expected.casefold():
            return ControlEvaluation(
                control_id=control_id,
                outcome=ControlOutcome.FAILED,
                observed_direction=observed,
                rationale="Observed direction conflicts with the locked expected direction.",
                evidence=evidence,
            )
    rationale = {
        ControlOutcome.PASSED: f"Caller-declared control passed: {criterion}",
        ControlOutcome.FAILED: f"Caller-declared control failed: {criterion}",
        ControlOutcome.ABSTAINED: "Caller-declared control requested abstention.",
        ControlOutcome.NOT_EVALUABLE: "Caller-declared control is not evaluable.",
    }[outcome]
    return ControlEvaluation(
        control_id=control_id,
        outcome=outcome,
        observed_direction=observed,
        rationale=rationale,
        evidence=evidence,
    )


def _finding_for(evaluation: ControlEvaluation) -> PlausibilityFinding:
    code = (
        PlausibilityFindingCode.CONTROL_FAILED
        if evaluation.outcome in {ControlOutcome.FAILED, ControlOutcome.ABSTAINED}
        else PlausibilityFindingCode.CONTROL_NOT_EVALUABLE
    )
    return PlausibilityFinding(
        finding_id=f"finding.{evaluation.control_id}",
        code=code,
        message=evaluation.rationale,
        evidence=evaluation.evidence,
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _estimated(probability: float, rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=probability,
        rationale=rationale,
    )


def _uncertainty(*, adjudicated: bool) -> UncertaintyProfile:
    if not adjudicated:
        value = _not_estimable(
            "No safe estimate is released while a required control is unresolved."
        )
        return UncertaintyProfile(
            measurement=value,
            sampling=value,
            parameter=value,
            model_form=value,
            identification=value,
            support=value,
            transport=value,
            sensitivity_notes=_UNCERTAINTY_NOTES,
        )
    return UncertaintyProfile(
        measurement=_estimated(0.10, "Caller-declared assay controls passed."),
        sampling=_estimated(0.10, "No sampling shift was declared."),
        parameter=_estimated(
            0.15, "Provisional deterministic scoring has bounded parameter uncertainty."
        ),
        model_form=_estimated(0.20, "Provisional ABI does not freeze the advanced model family."),
        identification=_estimated(0.10, "Identity and lineage gates passed."),
        support=_estimated(0.10, "All required control observations passed."),
        transport=_estimated(0.20, "Transport domain is not independently established."),
        sensitivity_notes=_UNCERTAINTY_NOTES,
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
            state=str(reference.state.value),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(
    request: AdjudicateBiomarkerPanelPlausibilityRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = _control_records(request.context)
    input_digests = {
        request_digest,
        request.mechanism_inference_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
        *(item.evidence_digest for item in controls),
    }
    return ProvenanceRecord(
        activity_id=f"activity.m1207.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1207_MODULE_ID,
        module_version=M1207_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(input_digests)),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _top_level_evidence(
    request: AdjudicateBiomarkerPanelPlausibilityRequest,
) -> tuple[EvidenceReference, ...]:
    declared = tuple(item for control in request.controls for item in control.required_evidence)
    source = tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M12-07 source artifact.",
        )
        for artifact in request.source_artifacts
    )
    unique: dict[str, EvidenceReference] = {}
    for item in (*declared, *source):
        unique.setdefault(item.reference.artifact_id, item)
    return tuple(unique.values())


def _support(*, adjudicated: bool) -> SupportDecision:
    if adjudicated:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m1207.controls_passed",
            rationale="All caller-declared M12-07 controls passed without unresolved conflict.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m1207.safe_abstention",
        rationale="A required control or conflict prevents a supported plausibility grade.",
    )


def _result(
    request: AdjudicateBiomarkerPanelPlausibilityRequest,
) -> BiomarkerPanelPlausibilityAdjudicationResult:
    request_digest = canonical_request_digest(request)
    evaluations = tuple(_evaluate_control(control) for control in request.controls)
    blocking = tuple(
        evaluation for evaluation in evaluations if evaluation.outcome is not ControlOutcome.PASSED
    )
    conflicts = request.declared_conflicts
    adjudicated = not blocking and not conflicts
    grade = None
    if adjudicated:
        passed_count = len(evaluations)
        grade = (
            PlausibilityGrade.HIGH
            if passed_count >= _HIGH_GRADE_MIN_CONTROLS
            else PlausibilityGrade.MODERATE
            if passed_count >= _MODERATE_GRADE_MIN_CONTROLS
            else PlausibilityGrade.LOW
        )
    findings = tuple(_finding_for(evaluation) for evaluation in blocking)
    if conflicts:
        findings += tuple(
            PlausibilityFinding(
                finding_id=f"finding.{conflict.conflict_id}",
                code=PlausibilityFindingCode.UNRESOLVED_CONFLICT,
                message=conflict.description,
                evidence=conflict.evidence,
            )
            for conflict in conflicts
        )
    status = (
        PlausibilityAdjudicationStatus.ADJUDICATED
        if adjudicated
        else PlausibilityAdjudicationStatus.ABSTAINED
    )
    payload: dict[str, object] = {
        "output_type": "biomarker_panel_plausibility_adjudication",
        "result_id": f"result.m1207.{request_digest.removeprefix('sha256:')}",
        "result_version": M1207_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": status,
        "grade": grade,
        "evaluations": evaluations,
        "conflicts": conflicts,
        "findings": findings,
        "abstention_reason": None
        if adjudicated
        else "A required control is failed, not evaluable, abstained or in unresolved conflict.",
        "parent_target": "biomarker_panel",
        "emits_parent": False,
        "support_decision": _support(adjudicated=adjudicated),
        "uncertainty": _uncertainty(adjudicated=adjudicated),
        "provenance": _provenance(request, request_digest),
        "evidence": _top_level_evidence(request),
        "limitations": _LIMITATIONS,
        "human_review_required": not adjudicated,
    }
    typed_model = BiomarkerPanelPlausibilityAdjudicationResult.model_construct(
        **cast("dict[str, Any]", payload)
    )
    digest_payload = typed_model.model_dump(mode="json")
    digest_payload.pop("result_digest", None)
    result_digest = result_payload_digest(digest_payload)
    materialized = cast("dict[str, Any]", json.loads(canonical_json_bytes(payload)))
    materialized["result_digest"] = result_digest
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


class M1207PlausibilityAdjudicatorEngine:
    """Strict, deterministic and replay-closed M12-07 execution engine."""

    __slots__ = ()

    def adjudicate(self, request: object) -> BiomarkerPanelPlausibilityAdjudicationResult:
        return _result(_validated_request(request))

    def verify(
        self,
        request: object,
        result: object,
    ) -> BiomarkerPanelPlausibilityAdjudicationResult:
        validated_request = _validated_request(request)
        validated_result = _RESULT_ADAPTER.validate_python(result, strict=True)
        expected_request_digest = canonical_request_digest(validated_request)
        if validated_result.request_digest != expected_request_digest:
            raise ValueError(  # noqa: TRY003
                "M12-07 result request digest does not match request"
            )
        if canonical_json_bytes(
            validated_result.request.model_dump(mode="json")
        ) != canonical_json_bytes(validated_request.model_dump(mode="json")):
            raise ValueError("M12-07 result embeds a different request")  # noqa: TRY003
        expected = _result(validated_request)
        if expected.result_digest != validated_result.result_digest:
            raise ValueError("M12-07 result replay digest mismatch")  # noqa: TRY003
        return validated_result


def adjudicate_biomarker_panel_plausibility(
    request: object,
) -> BiomarkerPanelPlausibilityAdjudicationResult:
    """Stateless public M12-07 operation."""

    return M1207PlausibilityAdjudicatorEngine().adjudicate(request)


def verify_m1207_result(
    request: object,
    result: object,
) -> BiomarkerPanelPlausibilityAdjudicationResult:
    """Verify request binding and deterministic replay of one result."""

    return M1207PlausibilityAdjudicatorEngine().verify(request, result)


__all__ = [
    "M1207PlausibilityAdjudicatorEngine",
    "M1207PlausibilityAuthorizationError",
    "adjudicate_biomarker_panel_plausibility",
    "preflight_m1207_authorization",
    "verify_m1207_result",
]
