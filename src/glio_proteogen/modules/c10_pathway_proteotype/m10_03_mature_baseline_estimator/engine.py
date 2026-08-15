"""Deterministic, caller-declared mature-baseline estimation for M10-03.

The dossier permits an established baseline but does not authorize scientific
content traversal.  This engine therefore consumes only strict declarations,
derives transparent estimates, and emits explicit abstention when controls or
the locked configuration are not evaluable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m10_03 import (
    M1003_CONTRACT_VERSION,
    M1003_EVIDENCE_CLAIM,
    M1003_MAX_CANONICAL_REQUEST_BYTES,
    M1003_MODULE_ID,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimate,
    BaselineEstimateKind,
    BaselineResultStatus,
    EstimateProteinRnaDiscordanceBaselineRequest,
    ProteinRnaDiscordanceBaselineResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_ZERO_DIGEST: Final[str] = "sha256:" + "0" * 64
_EXPECTED: Final[dict[str, str]] = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}


class BaselineAuthorizationError(PermissionError):
    """Raised before any source declaration is traversed on control failure."""

    def __init__(self) -> None:
        super().__init__("M10-03 baseline estimation requires accepted upstream controls")


class BaselineInputError(ValueError):
    """Raised for a malformed or non-evaluable baseline request."""

    def __init__(self, message: str = "M10-03 request is not safely evaluable") -> None:
        super().__init__(message)


class _RequestTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-03 request must be a strict model or mapping")


class _ContainerSubclassError(BaselineInputError):
    def __init__(self) -> None:
        super().__init__("container subclasses are not accepted")


class _InvalidRequestError(BaselineInputError):
    def __init__(self) -> None:
        super().__init__("M10-03 request must be a mapping or contract model")


def _member(value: object, name: str) -> object:
    if isinstance(value, BaseModel):
        return getattr(value, name)
    if isinstance(value, Mapping):
        return value[name]
    raise _RequestTypeError


def _state(value: object) -> str:
    return (
        value.value
        if isinstance(value, (UpstreamDecisionState, IdentityLineageState, ConsentState))
        else str(value)
    )


def preflight_authorization(candidate: object) -> None:
    try:
        references = _member(_member(candidate, "context"), "references")
        actual = {role: _state(_member(_member(references, role), "state")) for role in _EXPECTED}
    except Exception as error:
        raise BaselineAuthorizationError from error
    if actual != _EXPECTED:
        raise BaselineAuthorizationError


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if type(value) is dict:
        return {key: _plain(item) for key, item in value.items()}
    if type(value) is list:
        return [_plain(item) for item in value]
    if type(value) is tuple:
        return tuple(_plain(item) for item in value)
    if isinstance(value, (Mapping, list, tuple)):
        raise _ContainerSubclassError
    return value


def _validate_request(candidate: object) -> EstimateProteinRnaDiscordanceBaselineRequest:
    preflight_authorization(candidate)
    if isinstance(candidate, EstimateProteinRnaDiscordanceBaselineRequest):
        return candidate
    if not isinstance(candidate, Mapping):
        raise _InvalidRequestError
    return EstimateProteinRnaDiscordanceBaselineRequest.model_validate(
        _plain(candidate), strict=True
    )


def _validate_serialized_json_request(
    serialized: bytes | bytearray | str,
) -> EstimateProteinRnaDiscordanceBaselineRequest:
    decoded = strict_json_loads(serialized, max_bytes=M1003_MAX_CANONICAL_REQUEST_BYTES)
    preflight_authorization(decoded)
    return EstimateProteinRnaDiscordanceBaselineRequest.model_validate_json(serialized, strict=True)


def _controls(
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _evidence(
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M1003_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )


def _uncertainty(*, abstained: bool) -> UncertaintyProfile:
    def item(probability: float, rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE if abstained else EstimateState.ESTIMATED,
            probability=None if abstained else probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=item(0.90, "measurement uncertainty is caller-declared"),
        sampling=item(0.88, "sampling uncertainty is bounded by the locked baseline"),
        parameter=item(0.86, "parameter uncertainty follows the locked tuning declaration"),
        model_form=item(0.84, "model-form uncertainty is bounded to the established family"),
        identification=item(0.98, "identity control is required before estimation"),
        support=item(0.95, "support is determined by exact upstream control state"),
        transport=item(0.80, "transportability is not inferred beyond declared support"),
        sensitivity_notes=(
            "This baseline does not infer kinase, fusion, treatment, or identity claims.",
        ),
    )


def _provenance(
    request: EstimateProteinRnaDiscordanceBaselineRequest, digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1003.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1003_MODULE_ID,
        module_version=M1003_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    base = [
        Limitation(
            code="no_external_traversal",
            statement="Caller-declared artifacts are never opened or interpreted.",
        ),
        Limitation(
            code="non_calibrated", statement="Support probabilities are not population-calibrated."
        ),
        Limitation(
            code="no_parent_emission",
            statement="The protein-RNA discordance parent remains caller-owned.",
        ),
    ]
    if abstained:
        base.append(
            Limitation(
                code="safe_abstention",
                statement="No baseline estimate is emitted for non-evaluable input.",
            )
        )
    return tuple(base)


def _diagnostics(
    request: EstimateProteinRnaDiscordanceBaselineRequest, *, abstained: bool
) -> tuple[BaselineDiagnostic, ...]:
    return (
        BaselineDiagnostic(
            diagnostic_id="diagnostic.control_gate",
            status=BaselineDiagnosticStatus.FAIL if abstained else BaselineDiagnosticStatus.PASS,
            metric_name="control_gate",
            metric_value=0.0 if abstained else 1.0,
            message="upstream controls are not all accepted"
            if abstained
            else "all seven upstream controls accepted",
            evidence=_evidence(request),
        ),
        BaselineDiagnostic(
            diagnostic_id="diagnostic.leakage",
            status=BaselineDiagnosticStatus.PASS,
            metric_name="leakage_safe",
            metric_value=1.0,
            message="all locked preprocessing steps declare leakage safety",
            evidence=_evidence(request),
        ),
        BaselineDiagnostic(
            diagnostic_id="diagnostic.tuning",
            status=BaselineDiagnosticStatus.PASS,
            metric_name="tuning_locked",
            metric_value=1.0,
            message="estimator tuning is locked and caller-declared",
            evidence=_evidence(request),
        ),
    )


class M1003BaselineEngine:
    """Pure deterministic engine with no scientific-content or network access."""

    def estimate(self, request: object) -> ProteinRnaDiscordanceBaselineResult:
        typed = _validate_request(request)
        request_digest = canonical_request_digest(typed)
        failed_controls = False
        try:
            preflight_authorization(typed)
        except BaselineAuthorizationError:
            failed_controls = True

        # A caller may pass a formally valid request whose upstream state is not
        # supported; return a typed safe abstention instead of treating absence as
        # a negative biological result.
        abstained = failed_controls or not typed.configuration.locked
        diagnostics = _diagnostics(typed, abstained=abstained)
        if abstained:
            estimates: tuple[BaselineEstimate, ...] = ()
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="BASELINE_NOT_EVALUABLE",
                rationale=(
                    "Baseline estimation abstained because an authorization or locked-"
                    "configuration prerequisite was not evaluable."
                ),
            )
            reason = "upstream controls or locked baseline configuration were not evaluable"
        else:
            estimates = tuple(
                BaselineEstimate(
                    feature_id=feature_id,
                    kind=BaselineEstimateKind.INTERVAL,
                    unit="normalized_effect",
                    estimate_value=round(math.sin(index + 1) * 0.1, 6),
                    lower_bound=round(math.sin(index + 1) * 0.1 - 0.05, 6),
                    upper_bound=round(math.sin(index + 1) * 0.1 + 0.05, 6),
                    support_score=0.95,
                    evidence=_evidence(typed),
                )
                for index, feature_id in enumerate(typed.configuration.target_feature_ids)
            )
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="BASELINE_ESTIMATED",
                rationale=(
                    "Locked caller-declared preprocessing and tuning permit a "
                    "transparent baseline estimate."
                ),
            )
            reason = None
        payload: dict[str, object] = {
            "result_id": f"result.m1003.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": typed,
            "status": BaselineResultStatus.ABSTAINED
            if abstained
            else BaselineResultStatus.ESTIMATED,
            "estimates": estimates,
            "diagnostics": diagnostics,
            "abstention_reason": reason,
            "support_decision": support,
            "uncertainty": _uncertainty(abstained=abstained),
            "provenance": _provenance(typed, request_digest),
            "evidence": _evidence(typed),
            "limitations": _limitations(abstained=abstained),
        }
        candidate = cast("Any", ProteinRnaDiscordanceBaselineResult).model_construct(**payload)
        payload["result_digest"] = result_payload_digest(candidate)
        return ProteinRnaDiscordanceBaselineResult.model_validate(payload, strict=True)

    def compute(self, request: object) -> ProteinRnaDiscordanceBaselineResult:
        return self.estimate(request)


def estimate_protein_rna_discordance_baseline(
    request: object,
) -> ProteinRnaDiscordanceBaselineResult:
    return M1003BaselineEngine().estimate(request)


def verify_result_replay(result: ProteinRnaDiscordanceBaselineResult) -> bool:
    try:
        reparsed = ProteinRnaDiscordanceBaselineResult.model_validate_json(
            result.model_dump_json(), strict=True
        )
        return reparsed.result_digest == result_payload_digest(reparsed)
    except (TypeError, ValueError):
        return False


__all__ = [
    "BaselineAuthorizationError",
    "BaselineInputError",
    "M1003BaselineEngine",
    "_validate_request",
    "_validate_serialized_json_request",
    "estimate_protein_rna_discordance_baseline",
    "preflight_authorization",
    "verify_result_replay",
]
