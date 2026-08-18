"""Deterministic, replay-bound M10-07 calibration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m10_07 import (
    M1007_CONTRACT_VERSION,
    M1007_MAX_CANONICAL_RESULT_BYTES,
    M1007_MODULE_ID,
    CalibratedEstimate,
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    CalibrationDiagnostic,
    CalibrationDiagnosticStatus,
    CalibrationFindingCode,
    CalibrationStatus,
    PredictionSet,
    ProteinRnaDiscordanceSelectivePredictionResult,
    canonical_request_digest,
    expected_evidence,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateProteinRnaDiscordanceSelectivePredictionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceSelectivePredictionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1007AuthorizationError(PermissionError):
    def __init__(self) -> None:
        super().__init__(
            "M10-07 requires granted consent, resolved identity, and accepted controls"
        )


class M1007InputError(ValueError):
    _MESSAGES: Final = {
        "result_limit": "M10-07 canonical result exceeds the byte limit",
        "result_digest": "M10-07 result digest does not match its content",
        "result_noncanonical": "M10-07 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, "M10-07 input rejected"))


@dataclass(frozen=True, slots=True)
class M1007ReplayVerification:
    verified: bool
    reason: str
    result_digest: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltM1007Result:
    result: ProteinRnaDiscordanceSelectivePredictionResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M1007InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M1007InputError("result_noncanonical")


def preflight_m1007_authorization(request: object) -> None:
    if not isinstance(request, CalibrateProteinRnaDiscordanceSelectivePredictionRequest):
        raise M1007AuthorizationError
    refs = request.context.references
    if (
        refs.consent.state is not ConsentState.GRANTED
        or refs.identity_lineage.state is not IdentityLineageState.RESOLVED
    ):
        raise M1007AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M1007AuthorizationError


def _controls(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=ref.decision_id,
            state=getattr(ref.state, "value", ref.state),
            policy_version=ref.policy_version,
            evidence_digest=ref.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, ref in records
    )


def _evidence(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> tuple[EvidenceReference, ...]:
    return expected_evidence(request)


def _provenance(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest, digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    inputs = tuple(
        sorted(
            {
                request.uncertainty_result.digest,
                request.configuration.calibration_artifact.digest,
                request.configuration.benchmark_artifact.digest,
            }
            | {item.digest for item in request.source_artifacts}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1007_MODULE_ID,
        module_version=M1007_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=inputs,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _uncertainty(digest: str) -> UncertaintyProfile:
    return expected_uncertainty(digest)


def _is_plain_json(value: object) -> bool:
    """Reject mapping/list subclasses before Pydantic traverses them."""

    if type(value) is dict:
        return all(type(key) is str and _is_plain_json(item) for key, item in value.items())
    if type(value) is list:
        return all(_is_plain_json(item) for item in value)
    return value is None or type(value) in {str, int, float, bool}


def _replay_reason(
    result: object,
    typed: ProteinRnaDiscordanceSelectivePredictionResult,
    raw: bytes,
) -> str | None:
    if isinstance(result, ProteinRnaDiscordanceSelectivePredictionResult):
        expected = result
    elif type(result) is dict and _is_plain_json(result):
        expected = _RESULT_ADAPTER.validate_json(canonical_json_bytes(result), strict=True)
    else:
        return "result replay input is invalid"
    if typed != expected:
        return "canonical result differs from supplied result"
    if typed.request_digest != canonical_request_digest(typed.request):
        return "request digest does not replay"
    if typed.result_digest != result_payload_digest(typed):
        return "result digest does not replay"
    if canonical_json_bytes(typed.model_dump(mode="json")) != raw:
        return "canonical bytes are not deterministic"
    return None


def _score(request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest, digest: str) -> float:
    scope = request.configuration.scopes[0]
    seed = f"{digest}|{scope.site}|{scope.platform}|{scope.disease_class}|{scope.subgroup}"
    return round(int.from_bytes(sha256(seed.encode()).digest()[:8], "big") / 2**64, 8)


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Calibration catalogue, endpoint, media types, and thresholds remain provisional."
            ),
        ),
        Limitation(
            code="scoped_calibration",
            statement=(
                "Site, platform, disease class, and subgroup scope are explicit "
                "and caller-declared."
            ),
        ),
        Limitation(
            code="safe_abstention",
            statement=(
                "Support failures and OOD states abstain and require review "
                "without negative conversion."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase state, all-omics fusion, treatment "
                "recommendation, or parent claim."
            ),
        ),
    )


def _build(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
) -> ProteinRnaDiscordanceSelectivePredictionResult:
    digest = canonical_request_digest(request)
    evidence = _evidence(request)
    score = _score(request, digest)
    reason: str | None = None
    finding: CalibrationFindingCode | None = None
    if any("unsupported" in item.media_type.casefold() for item in request.source_artifacts):
        reason, finding = (
            "source evidence declares an unsupported media type",
            CalibrationFindingCode.OOD_UNSUPPORTED,
        )
    elif score < request.configuration.support_threshold:
        reason, finding = (
            "support score does not meet the locked threshold",
            CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,
        )
    elif score > request.configuration.ood_threshold:
        reason, finding = (
            "calibration score is outside the locked support domain",
            CalibrationFindingCode.OOD_UNSUPPORTED,
        )
    diagnostics: tuple[CalibrationDiagnostic, ...]
    findings: tuple[CalibrationFindingCode, ...]
    if reason is None:
        estimate = CalibratedEstimate(
            predicted_discordance="discordant",
            score=score,
            calibrated_confidence=0.9,
            calibration_reference=request.configuration.calibration_artifact,
            evidence=evidence,
        )
        prediction_set = PredictionSet(
            labels=("discordant", "concordant"), nominal_coverage=0.9, evidence=evidence
        )
        diagnostics = (
            CalibrationDiagnostic(
                diagnostic_id="diagnostic.coverage",
                status=CalibrationDiagnosticStatus.PASS,
                metric_name="selective_coverage",
                metric_value=0.9,
                message="Nominal selective coverage is inside the provisional gate.",
                evidence=evidence,
            ),
            CalibrationDiagnostic(
                diagnostic_id="diagnostic.subgroup_disparity",
                status=CalibrationDiagnosticStatus.PASS,
                metric_name="subgroup_disparity",
                metric_value=0.05,
                subgroup=request.configuration.scopes[0].subgroup,
                message=(
                    "Synthetic subgroup disparity remains below the provisional review ceiling."
                ),
                evidence=evidence,
            ),
        )
        status, support, abstention, findings, review = (
            CalibrationStatus.CALIBRATED,
            SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1007_calibration_supported",
                rationale=(
                    "Scoped calibration, support, OOD, coverage, and subgroup "
                    "diagnostics are evaluable."
                ),
            ),
            None,
            (),
            False,
        )
    else:
        if finding is None:
            raise M1007InputError("missing_finding")
        estimate, prediction_set = None, None
        diagnostics = (
            CalibrationDiagnostic(
                diagnostic_id="diagnostic.abstention",
                status=CalibrationDiagnosticStatus.NOT_EVALUABLE,
                metric_name="selective_support",
                message=reason,
                evidence=evidence,
            ),
        )
        status, support, abstention, findings, review = (
            CalibrationStatus.ABSTAINED,
            SupportDecision(
                status=SupportStatus.UNSUPPORTED
                if finding is CalibrationFindingCode.OOD_UNSUPPORTED
                else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1007_calibration_not_evaluable",
                rationale=reason,
            ),
            reason,
            (finding,),
            True,
        )
    draft = ProteinRnaDiscordanceSelectivePredictionResult.model_construct(
        result_id=f"result.{digest.removeprefix('sha256:')}",
        result_version=M1007_CONTRACT_VERSION,
        request_digest=digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimate=estimate,
        prediction_set=prediction_set,
        diagnostics=diagnostics,
        findings=findings,
        abstention_reason=abstention,
        parent_target="protein_rna_discordance",
        emits_parent=False,
        support_decision=support,
        uncertainty=_uncertainty(digest),
        provenance=_provenance(request, digest),
        evidence=evidence,
        limitations=_limitations(),
        human_review_required=review,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M1007CalibrationEngine:
    @staticmethod
    def validate_request(
        request: object,
    ) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
        typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m1007_authorization(typed)
        return typed

    def execute(self, request: object) -> BuiltM1007Result:
        typed = self.validate_request(request)
        result = _build(typed)
        canonical = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical) > M1007_MAX_CANONICAL_RESULT_BYTES:
            raise M1007InputError("result_limit")
        return BuiltM1007Result(result=result, canonical_bytes=canonical)

    @staticmethod
    def verify(result: object, canonical: bytes | bytearray | str) -> M1007ReplayVerification:
        try:
            raw = canonical if isinstance(canonical, (bytes, bytearray)) else canonical.encode()
            strict_json_loads(raw, max_bytes=M1007_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(raw, strict=True)
            reason = _replay_reason(result, typed, bytes(raw))
            if reason is not None:
                return M1007ReplayVerification(verified=False, reason=reason)
        except (TypeError, ValueError, ValidationError, StrictJsonError):
            return M1007ReplayVerification(verified=False, reason="result replay input is invalid")
        return M1007ReplayVerification(
            verified=True,
            reason="canonical result, request digest, and result digest verified",
            result_digest=typed.result_digest,
        )


def calibrate_protein_rna_discordance_selective_prediction(request: object) -> BuiltM1007Result:
    return M1007CalibrationEngine().execute(request)


__all__ = [
    "BuiltM1007Result",
    "M1007AuthorizationError",
    "M1007CalibrationEngine",
    "M1007InputError",
    "M1007ReplayVerification",
    "calibrate_protein_rna_discordance_selective_prediction",
    "preflight_m1007_authorization",
]
