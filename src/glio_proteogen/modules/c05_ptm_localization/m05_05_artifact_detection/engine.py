# ruff: noqa: E501, C901, PLR0911, PLR0913, PLR2004, SIM102, TRY300, TRY301

"""Deterministic M05-05 PTM-localization artifact detector.

The runtime deliberately operates on aggregate, caller-declared evidence events.  It
replays the complete M05-03 result at the boundary, validates the seven-control
context before opening nested payloads, and only traverses a complete evidence ledger
when the upstream quality disposition and reviewed detector profile agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m05_03 import PtmLocalizationRawInputValidationResult
from glio_proteogen.contracts.m05_05 import (
    M0505_CONTRACT_VERSION,
    M0505_EVIDENCE_CLAIM,
    M0505_MAX_CANONICAL_REQUEST_BYTES,
    M0505_PARENT,
    M0505_RATE_SCALE,
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactComputationReceipt,
    PtmLocalizationArtifactDetectionResult,
    PtmLocalizationArtifactDetectorClass,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationArtifactEvidenceEvent,
    PtmLocalizationArtifactEvidenceLedger,
    PtmLocalizationArtifactEvidenceLedgerBinding,
    PtmLocalizationArtifactFinding,
    PtmLocalizationArtifactFindingAction,
    PtmLocalizationArtifactFindingCode,
    PtmLocalizationArtifactObservationState,
    PtmLocalizationArtifactPolicy,
    PtmLocalizationArtifactPosterior,
    PtmLocalizationArtifactPosteriorState,
    PtmLocalizationArtifactProfile,
    PtmLocalizationArtifactSeverity,
    PtmLocalizationArtifactUpstreamDisposition,
    PtmLocalizationContaminationFlag,
    PtmLocalizationExclusionMaskEntry,
    PtmLocalizationExclusionReasonCode,
    canonical_request_digest,
    configuration_digest,
    contamination_flag_digest,
    event_digest,
    finding_identifier,
    policy_digest,
    posterior_digest,
    profile_digest,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_AUTHORIZATION_MESSAGE: Final = (
    "ptm_localization artifact detection requires accepted upstream controls"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MISSING: Final = object()
_MAX_PLAIN_DEPTH: Final = 80
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 300_000
_MAX_PLAIN_SEQUENCE: Final = 512
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "raw_input_result",
        "quality_result_digest",
        "quality_contract_version",
        "quality_configuration_digest",
        "quality_receipt_digest",
        "identity_resolution_digest",
        "raw_input_receipt_digest",
        "quality_disposition",
        "policy",
        "evidence_ledger",
        "supersedes_result_digest",
    }
)
_CONTAMINATION_CLASSES: Final = frozenset(
    {
        PtmLocalizationArtifactDetectorClass.CONTAMINATION,
        PtmLocalizationArtifactDetectorClass.BARCODE_INDEX,
    }
)
_QUALITY_RESULT_DISPOSITIONS: Final = frozenset(
    item.value for item in PtmLocalizationArtifactUpstreamDisposition
)

_REQUEST_ADAPTER: Final = TypeAdapter(DetectPtmLocalizationArtifactsRequest)
_RAW_RESULT_ADAPTER: Final = TypeAdapter(PtmLocalizationRawInputValidationResult)
_POLICY_ADAPTER: Final = TypeAdapter(PtmLocalizationArtifactPolicy)
_CONTEXT_ADAPTER: Final = TypeAdapter(ExecutionContext)
_LEDGER_ADAPTER: Final = TypeAdapter(PtmLocalizationArtifactEvidenceLedger)
_LEDGER_BINDING_ADAPTER: Final = TypeAdapter(PtmLocalizationArtifactEvidenceLedgerBinding)


class PtmLocalizationArtifactAuthorizationError(PermissionError):
    """Authorization failed before quality, raw result, or ledger traversal."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class PtmLocalizationArtifactInputError(ValueError):
    """A candidate request failed closed without reflecting caller payloads."""

    def __init__(self) -> None:
        super().__init__("M05-05 request failed strict validation")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-05 strict request values require exact built-in containers")


class _ForbiddenEvidenceLedgerError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-05 safe-failure or unsupported input prohibits ledger traversal")


class _SerializedRequestTooLargeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-05 canonical request exceeds its byte limit")


def preflight_ptm_localization_artifact_authorization(candidate: object) -> None:
    """Check all seven controls before opening governed nested request fields."""

    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if type(candidate) is not DetectPtmLocalizationArtifactsRequest and dict not in candidate_mro:
        raise PtmLocalizationArtifactAuthorizationError
    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {
            role: _state_text(_member(_member(references, role), "state")) for role in expected
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise PtmLocalizationArtifactAuthorizationError from None
    if states != expected:
        raise PtmLocalizationArtifactAuthorizationError


class M0505PtmLocalizationArtifactEngine:
    """Replay M05-03 and reduce a reviewed seven-class evidence ledger."""

    __slots__ = ()

    def detect(self, request: object) -> PtmLocalizationArtifactDetectionResult:
        prepared = _prepare_artifact_request_candidate(request)
        validated = _validate_prepared_request(prepared)
        return self._detect_validated(validated)

    @staticmethod
    def _detect_validated(
        request: DetectPtmLocalizationArtifactsRequest,
    ) -> PtmLocalizationArtifactDetectionResult:
        return _compute_result(request)


def detect_ptm_localization_artifacts(
    request: object,
) -> PtmLocalizationArtifactDetectionResult:
    """Public stateless M05-05 operation."""

    return M0505PtmLocalizationArtifactEngine().detect(request)


def _prepare_artifact_request_candidate(
    candidate: object,
) -> dict[str, object]:
    preflight_ptm_localization_artifact_authorization(candidate)
    try:
        _validate_outer_request_shape(candidate)
        raw_value = _member(candidate, "raw_input_result")
        raw_result = _RAW_RESULT_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(raw_value)), strict=True
        )
        policy_raw = _member(candidate, "policy")
        _validate_policy_shape_before_copy(policy_raw)
        policy_candidate = (
            policy_raw
            if type(policy_raw) is PtmLocalizationArtifactPolicy
            else _plain_value(policy_raw)
        )
        policy = _POLICY_ADAPTER.validate_json(canonical_json_bytes(policy_candidate), strict=True)
        context = _CONTEXT_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(_member(candidate, "context"))), strict=True
        )
        ledger_raw = _member(candidate, "evidence_ledger")
        quality_disposition = _member(candidate, "quality_disposition")
        quality_disposition_text = _state_text(quality_disposition)
        if quality_disposition_text not in _QUALITY_RESULT_DISPOSITIONS:
            raise PtmLocalizationArtifactInputError
        typed_quality_disposition = PtmLocalizationArtifactUpstreamDisposition(
            quality_disposition_text
        )
        profile_supported = (
            _matching_profile(
                policy,
                _member(candidate, "quality_contract_version"),
                _member(candidate, "quality_configuration_digest"),
            )
            is not None
        )
        may_traverse = (
            quality_disposition_text == PtmLocalizationArtifactUpstreamDisposition.QUALIFIED.value
            and profile_supported
            and ledger_raw is not _MISSING
            and ledger_raw is not None
        )
        if not may_traverse and ledger_raw is not _MISSING and ledger_raw is not None:
            # The contract itself rejects a ledger for safe-failure requests.  Keep this
            # explicit so a hostile caller cannot cause ledger traversal before that check.
            if (
                quality_disposition_text
                != PtmLocalizationArtifactUpstreamDisposition.QUALIFIED.value
            ):
                raise _ForbiddenEvidenceLedgerError
        ledger: object = None
        if may_traverse:
            if type(ledger_raw) is PtmLocalizationArtifactEvidenceLedgerBinding or (
                _member(ledger_raw, "events") is _MISSING
            ):
                ledger = _LEDGER_BINDING_ADAPTER.validate_json(
                    canonical_json_bytes(_materialize_ledger_binding(ledger_raw)), strict=True
                )
            else:
                declared_quality_digest = _member(ledger_raw, "quality_result_digest")
                _validate_ledger_shape_before_copy(ledger_raw)
                ledger_candidate = (
                    ledger_raw
                    if type(ledger_raw) is PtmLocalizationArtifactEvidenceLedger
                    else _plain_value(ledger_raw)
                )
                if declared_quality_digest == _member(candidate, "quality_result_digest"):
                    ledger = _LEDGER_ADAPTER.validate_json(
                        canonical_json_bytes(ledger_candidate), strict=True
                    )
                else:
                    ledger = _LEDGER_BINDING_ADAPTER.validate_json(
                        canonical_json_bytes(_materialize_ledger_binding(ledger_raw)), strict=True
                    )
        payload: dict[str, object] = {
            "request_id": _plain_value(_member(candidate, "request_id")),
            "context": context,
            "raw_input_result": raw_result,
            "quality_result_digest": _plain_value(_member(candidate, "quality_result_digest")),
            "quality_contract_version": _plain_value(
                _member(candidate, "quality_contract_version")
            ),
            "quality_configuration_digest": _plain_value(
                _member(candidate, "quality_configuration_digest")
            ),
            "quality_receipt_digest": _plain_value(_member(candidate, "quality_receipt_digest")),
            "identity_resolution_digest": _plain_value(
                _member(candidate, "identity_resolution_digest")
            ),
            "raw_input_receipt_digest": _plain_value(
                _member(candidate, "raw_input_receipt_digest")
            ),
            "quality_disposition": typed_quality_disposition,
            "policy": policy,
            "evidence_ledger": ledger,
            "supersedes_result_digest": _optional_plain_member(
                candidate, "supersedes_result_digest"
            ),
        }
        for field in ("operation", "contract_version"):
            value = _member(candidate, field)
            if value is not _MISSING:
                payload[field] = _plain_value(value)
        return payload
    except (_ForbiddenEvidenceLedgerError, _InvalidPlainValueError):
        raise
    except Exception:  # noqa: BLE001 - nested content never escapes this boundary.
        raise PtmLocalizationArtifactInputError from None


def _validate_prepared_request(payload: dict[str, object]) -> DetectPtmLocalizationArtifactsRequest:
    try:
        return _REQUEST_ADAPTER.validate_python(payload, strict=True)
    except Exception:  # noqa: BLE001
        raise PtmLocalizationArtifactInputError from None


def _validate_json_request(
    candidate: object, serialized: bytes | bytearray | str
) -> DetectPtmLocalizationArtifactsRequest:
    serialized_size = (
        len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    )
    if serialized_size > M0505_MAX_CANONICAL_REQUEST_BYTES:
        raise _SerializedRequestTooLargeError
    return _validate_prepared_request(_prepare_artifact_request_candidate(candidate))


def _matching_profile(
    policy: PtmLocalizationArtifactPolicy,
    quality_contract_version: object,
    quality_configuration_digest: object,
) -> PtmLocalizationArtifactProfile | None:
    if type(quality_contract_version) is not str or type(quality_configuration_digest) is not str:
        return None
    matches = tuple(
        profile
        for profile in policy.profiles
        if quality_contract_version in profile.approved_quality_contract_versions
        and quality_configuration_digest in profile.approved_quality_configuration_digests
    )
    return matches[0] if len(matches) == 1 else None


def _traversable(request: DetectPtmLocalizationArtifactsRequest) -> bool:
    ledger = request.evidence_ledger
    return (
        request.quality_disposition is PtmLocalizationArtifactUpstreamDisposition.QUALIFIED
        and _matching_profile(
            request.policy,
            request.quality_contract_version,
            request.quality_configuration_digest,
        )
        is not None
        and type(ledger) is PtmLocalizationArtifactEvidenceLedger
        and ledger.quality_result_digest == request.quality_result_digest
    )


def _event_evidence(event: PtmLocalizationArtifactEvidenceEvent) -> tuple[EvidenceReference, ...]:
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=reference,
                    role="evidence",
                    claim=M0505_EVIDENCE_CLAIM,
                )
                for reference in event.evidence
            ),
            key=canonical_json_bytes,
        )
    )


def _posterior_support(state: PtmLocalizationArtifactPosteriorState) -> SupportDecision:
    if state is PtmLocalizationArtifactPosteriorState.CLEAR:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0505.posterior.clear",
            rationale="Observed aggregate evidence remains below the reviewed threshold.",
        )
    if state in {
        PtmLocalizationArtifactPosteriorState.SUSPECTED,
        PtmLocalizationArtifactPosteriorState.DETECTED,
    }:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0505.posterior.artifact",
            rationale="Observed aggregate evidence meets a reviewed artifact threshold.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="m0505.posterior.indeterminate",
        rationale="Missing, unsupported, or out-of-domain evidence is not a negative finding.",
    )


def _expected_posteriors(
    request: DetectPtmLocalizationArtifactsRequest,
) -> tuple[PtmLocalizationArtifactPosterior, ...]:
    if not _traversable(request):
        return ()
    profile = _matching_profile(
        request.policy, request.quality_contract_version, request.quality_configuration_digest
    )
    ledger = request.evidence_ledger
    if profile is None or type(ledger) is not PtmLocalizationArtifactEvidenceLedger:
        return ()
    thresholds = {item.detector_class: item for item in profile.thresholds}
    output: list[PtmLocalizationArtifactPosterior] = []
    for event in ledger.events:
        score: int | None = None
        lower: int | None = None
        upper: int | None = None
        if event.observation_state is PtmLocalizationArtifactObservationState.OBSERVED:
            score = (
                event.supporting_count * M0505_RATE_SCALE + event.evaluated_count // 2
            ) // event.evaluated_count
            resolution = (M0505_RATE_SCALE + event.evaluated_count - 1) // event.evaluated_count
            lower = max(0, score - resolution)
            upper = min(M0505_RATE_SCALE, score + resolution)
            threshold = thresholds[event.detector_class]
            state = (
                PtmLocalizationArtifactPosteriorState.DETECTED
                if event.seeded_critical or score >= threshold.exclusion_threshold_ppm
                else PtmLocalizationArtifactPosteriorState.SUSPECTED
                if score >= threshold.review_threshold_ppm
                else PtmLocalizationArtifactPosteriorState.CLEAR
            )
        else:
            state = PtmLocalizationArtifactPosteriorState.INDETERMINATE
        payload: dict[str, object] = {
            "posterior_digest": _ZERO_DIGEST,
            "target_id": event.target_id,
            "unit_kind": event.unit_kind,
            "detector_class": event.detector_class,
            "observation_state": event.observation_state,
            "state": state,
            "posterior_ppm": score,
            "lower_bound_ppm": lower,
            "upper_bound_ppm": upper,
            "score_is_calibrated_probability": False,
            "support": _posterior_support(state),
            "evidence": _event_evidence(event),
        }
        constructed = PtmLocalizationArtifactPosterior.model_construct(**payload)  # type: ignore[arg-type]
        payload["posterior_digest"] = posterior_digest(constructed)
        output.append(PtmLocalizationArtifactPosterior.model_validate(payload, strict=True))
    return tuple(sorted(output, key=canonical_json_bytes))


def _expected_flags(
    posteriors: tuple[PtmLocalizationArtifactPosterior, ...],
) -> tuple[PtmLocalizationContaminationFlag, ...]:
    output: list[PtmLocalizationContaminationFlag] = []
    for posterior in posteriors:
        if posterior.detector_class not in _CONTAMINATION_CLASSES or posterior.state not in {
            PtmLocalizationArtifactPosteriorState.SUSPECTED,
            PtmLocalizationArtifactPosteriorState.DETECTED,
        }:
            continue
        digest = sha256_digest(
            {
                "module_id": "GLIO-PROTEOGEN-M05-05",
                "target_id": posterior.target_id,
                "detector_class": posterior.detector_class,
                "posterior_digest": posterior.posterior_digest,
            }
        ).removeprefix("sha256:")
        output.append(
            PtmLocalizationContaminationFlag(
                flag_id=f"flag.{digest}",
                target_id=posterior.target_id,
                detector_class=posterior.detector_class,
                posterior_digest=posterior.posterior_digest,
                severity=(
                    PtmLocalizationArtifactSeverity.EXCLUDE
                    if posterior.state is PtmLocalizationArtifactPosteriorState.DETECTED
                    else PtmLocalizationArtifactSeverity.REVIEW
                ),
                evidence=posterior.evidence,
                review_required=True,
            )
        )
    return tuple(sorted(output, key=canonical_json_bytes))


def _expected_exclusions(
    posteriors: tuple[PtmLocalizationArtifactPosterior, ...],
    flags: tuple[PtmLocalizationContaminationFlag, ...],
) -> tuple[PtmLocalizationExclusionMaskEntry, ...]:
    target_ids = sorted(
        {
            item.target_id
            for item in posteriors
            if item.state is PtmLocalizationArtifactPosteriorState.DETECTED
        }
    )
    output: list[PtmLocalizationExclusionMaskEntry] = []
    for target_id in target_ids:
        detected = tuple(
            item
            for item in posteriors
            if item.target_id == target_id
            and item.state is PtmLocalizationArtifactPosteriorState.DETECTED
        )
        digests = tuple(sorted(item.posterior_digest for item in detected))
        output.append(
            PtmLocalizationExclusionMaskEntry(
                target_id=target_id,
                triggering_posterior_digests=digests,
                triggering_flag_ids=tuple(
                    sorted(
                        flag.flag_id
                        for flag in flags
                        if flag.target_id == target_id and flag.posterior_digest in digests
                    )
                ),
                reason_code=PtmLocalizationExclusionReasonCode.CRITICAL_ARTIFACT_DETECTED,
                evidence=tuple(
                    sorted(
                        {evidence for item in detected for evidence in item.evidence},
                        key=canonical_json_bytes,
                    )
                ),
                review_required=True,
            )
        )
    return tuple(sorted(output, key=canonical_json_bytes))


def _finding(
    code: PtmLocalizationArtifactFindingCode,
    *,
    target_ids: tuple[str, ...] = (),
    detector_classes: tuple[PtmLocalizationArtifactDetectorClass, ...] = (),
) -> PtmLocalizationArtifactFinding:
    action = {
        PtmLocalizationArtifactFindingCode.UPSTREAM_QUARANTINED: PtmLocalizationArtifactFindingAction.QUARANTINE,
        PtmLocalizationArtifactFindingCode.UPSTREAM_ABSTAINED: PtmLocalizationArtifactFindingAction.ABSTAIN,
        PtmLocalizationArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH: PtmLocalizationArtifactFindingAction.QUARANTINE,
        PtmLocalizationArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED: PtmLocalizationArtifactFindingAction.ABSTAIN,
        PtmLocalizationArtifactFindingCode.EVIDENCE_MISSING: PtmLocalizationArtifactFindingAction.ABSTAIN,
        PtmLocalizationArtifactFindingCode.EVIDENCE_UNSUPPORTED: PtmLocalizationArtifactFindingAction.ABSTAIN,
        PtmLocalizationArtifactFindingCode.EVIDENCE_NOT_EVALUABLE: PtmLocalizationArtifactFindingAction.ABSTAIN,
        PtmLocalizationArtifactFindingCode.ARTIFACT_SUSPECTED: PtmLocalizationArtifactFindingAction.QUARANTINE,
        PtmLocalizationArtifactFindingCode.ARTIFACT_DETECTED: PtmLocalizationArtifactFindingAction.QUARANTINE,
        PtmLocalizationArtifactFindingCode.CONTAMINATION_FLAGGED: PtmLocalizationArtifactFindingAction.QUARANTINE,
    }[code]
    targets = tuple(sorted(set(target_ids)))
    classes = tuple(sorted(set(detector_classes)))
    return PtmLocalizationArtifactFinding(
        finding_id=finding_identifier(code, targets, classes),
        code=code,
        action=action,
        message=code.value.replace("_", " ").capitalize() + ".",
        target_ids=targets,
        detector_classes=classes,
    )


def _expected_findings(
    request: DetectPtmLocalizationArtifactsRequest,
    posteriors: tuple[PtmLocalizationArtifactPosterior, ...],
    flags: tuple[PtmLocalizationContaminationFlag, ...],
) -> tuple[PtmLocalizationArtifactFinding, ...]:
    if request.quality_disposition is PtmLocalizationArtifactUpstreamDisposition.QUARANTINED:
        return (_finding(PtmLocalizationArtifactFindingCode.UPSTREAM_QUARANTINED),)
    if request.quality_disposition is PtmLocalizationArtifactUpstreamDisposition.ABSTAINED:
        return (_finding(PtmLocalizationArtifactFindingCode.UPSTREAM_ABSTAINED),)
    profile = _matching_profile(
        request.policy, request.quality_contract_version, request.quality_configuration_digest
    )
    if profile is None:
        return (_finding(PtmLocalizationArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED),)
    if type(request.evidence_ledger) is PtmLocalizationArtifactEvidenceLedgerBinding:
        return (_finding(PtmLocalizationArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH),)
    required = {item.detector_class: item.required for item in profile.thresholds}
    grouped: dict[
        PtmLocalizationArtifactFindingCode,
        tuple[set[str], set[PtmLocalizationArtifactDetectorClass]],
    ] = {}

    def record(
        code: PtmLocalizationArtifactFindingCode, posterior: PtmLocalizationArtifactPosterior
    ) -> None:
        targets, classes = grouped.setdefault(code, (set(), set()))
        targets.add(posterior.target_id)
        classes.add(posterior.detector_class)

    for posterior in posteriors:
        if posterior.observation_state is PtmLocalizationArtifactObservationState.MISSING:
            record(PtmLocalizationArtifactFindingCode.EVIDENCE_MISSING, posterior)
        elif posterior.observation_state is PtmLocalizationArtifactObservationState.UNSUPPORTED:
            record(PtmLocalizationArtifactFindingCode.EVIDENCE_UNSUPPORTED, posterior)
        elif (
            posterior.observation_state is PtmLocalizationArtifactObservationState.NOT_APPLICABLE
            and required.get(posterior.detector_class, False)
        ):
            record(PtmLocalizationArtifactFindingCode.EVIDENCE_NOT_EVALUABLE, posterior)
        if posterior.state is PtmLocalizationArtifactPosteriorState.SUSPECTED:
            record(PtmLocalizationArtifactFindingCode.ARTIFACT_SUSPECTED, posterior)
        elif posterior.state is PtmLocalizationArtifactPosteriorState.DETECTED:
            record(PtmLocalizationArtifactFindingCode.ARTIFACT_DETECTED, posterior)
    if flags:
        grouped[PtmLocalizationArtifactFindingCode.CONTAMINATION_FLAGGED] = (
            {item.target_id for item in flags},
            {item.detector_class for item in flags},
        )
    return tuple(
        sorted(
            (
                _finding(code, target_ids=tuple(targets), detector_classes=tuple(classes))
                for code, (targets, classes) in grouped.items()
            ),
            key=canonical_json_bytes,
        )
    )


def _expected_disposition(
    request: DetectPtmLocalizationArtifactsRequest,
    posteriors: tuple[PtmLocalizationArtifactPosterior, ...],
) -> PtmLocalizationArtifactDisposition:
    if request.quality_disposition is PtmLocalizationArtifactUpstreamDisposition.QUARANTINED:
        return PtmLocalizationArtifactDisposition.QUARANTINED
    if request.quality_disposition is PtmLocalizationArtifactUpstreamDisposition.ABSTAINED:
        return PtmLocalizationArtifactDisposition.ABSTAINED
    profile = _matching_profile(
        request.policy, request.quality_contract_version, request.quality_configuration_digest
    )
    if profile is None:
        return PtmLocalizationArtifactDisposition.ABSTAINED
    if type(request.evidence_ledger) is PtmLocalizationArtifactEvidenceLedgerBinding:
        return PtmLocalizationArtifactDisposition.QUARANTINED
    if any(
        item.state
        in {
            PtmLocalizationArtifactPosteriorState.SUSPECTED,
            PtmLocalizationArtifactPosteriorState.DETECTED,
        }
        for item in posteriors
    ):
        return PtmLocalizationArtifactDisposition.QUARANTINED
    required = {item.detector_class: item.required for item in profile.thresholds}
    if any(
        item.observation_state
        in {
            PtmLocalizationArtifactObservationState.MISSING,
            PtmLocalizationArtifactObservationState.UNSUPPORTED,
        }
        or (
            item.observation_state is PtmLocalizationArtifactObservationState.NOT_APPLICABLE
            and required.get(item.detector_class, False)
        )
        for item in posteriors
    ):
        return PtmLocalizationArtifactDisposition.ABSTAINED
    return PtmLocalizationArtifactDisposition.CLEARED


def _expected_support(disposition: PtmLocalizationArtifactDisposition) -> SupportDecision:
    if disposition is PtmLocalizationArtifactDisposition.CLEARED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0505.detector.cleared",
            rationale="Every required artifact class is observed and below reviewed thresholds.",
        )
    if disposition is PtmLocalizationArtifactDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0505.detector.quarantined",
            rationale="Artifact evidence or a binding conflict requires quarantine and review.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="m0505.detector.abstained",
        rationale="Unsupported, missing, or out-of-domain evidence cannot support detection.",
    )


def _expected_uncertainty() -> UncertaintyProfile:
    rationales = (
        "Measurement uncertainty is not estimated from aggregate event counts.",
        "Sampling uncertainty is not estimated by this deterministic detector.",
        "No parameters are fitted by the reviewed threshold evaluator.",
        "No calibrated classifier or proteotype model is executed.",
        "PTM localization and identity remain outside this detector.",
        "Support uncertainty is represented by explicit abstention and review states.",
        "Transportability requires external assay-specific validation.",
    )
    estimates = tuple(
        UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=value)
        for value in rationales
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=tuple(
            sorted(
                (
                    "Missing and unsupported inputs remain typed; they never become negative findings.",
                    "Posterior ppm values are deterministic evidence fractions, not probabilities.",
                    "Novel or out-of-domain states abstain and require human review.",
                )
            )
        ),
    )


def _expected_controls(
    request: DetectPtmLocalizationArtifactsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions = (
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
    return tuple(sorted(decisions, key=canonical_json_bytes))


def _evidence_index(
    request: DetectPtmLocalizationArtifactsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
    ]
    profile = _matching_profile(
        request.policy, request.quality_contract_version, request.quality_configuration_digest
    )
    if profile is not None:
        artifacts.append(profile.evidence)
        artifacts.extend(item.evidence for item in profile.thresholds)
    if request.evidence_ledger is not None:
        artifacts.append(request.evidence_ledger.evidence)
    unique: dict[tuple[str, str], ArtifactReference] = {
        (item.artifact_id, item.version): item for item in artifacts
    }
    return tuple(
        sorted(
            (
                EvidenceReference(reference=item, role="evidence", claim=M0505_EVIDENCE_CLAIM)
                for item in unique.values()
            ),
            key=canonical_json_bytes,
        )
    )


def _expected_provenance(request: DetectPtmLocalizationArtifactsRequest) -> ProvenanceRecord:
    refs = request.context.references
    profile = _matching_profile(
        request.policy, request.quality_contract_version, request.quality_configuration_digest
    )
    digests = {
        canonical_request_digest(request),
        request.quality_result_digest,
        request.quality_receipt_digest,
        request.raw_input_receipt_digest,
        request.raw_input_result.result_digest,
        policy_digest(request.policy),
    }
    if profile is not None:
        digests.add(profile_digest(profile))
    if request.evidence_ledger is not None:
        digests.add(request.evidence_ledger.ledger_digest)
    if request.supersedes_result_digest is not None:
        digests.add(request.supersedes_result_digest)
    return ProvenanceRecord(
        activity_id=f"activity.m0505.{canonical_request_digest(request).removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M05-05",
        module_version=M0505_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(digests)),
        configuration_digest=configuration_digest(request.policy),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_expected_controls(request),
    )


def _expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="ptm_localization_artifact_mask_only",
                    statement="Output is limited to artifact posteriors, contamination flags, and exclusions.",
                ),
                Limitation(
                    code="evidence_score_not_probability",
                    statement="Posterior ppm fields are uncalibrated deterministic evidence fractions.",
                ),
                Limitation(
                    code="no_biological_or_clinical_inference",
                    statement="No identity, PTM localization, kinase, subtype, or treatment claim is made.",
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _expected_receipt(
    request: DetectPtmLocalizationArtifactsRequest,
    *,
    posteriors: tuple[PtmLocalizationArtifactPosterior, ...],
    flags: tuple[PtmLocalizationContaminationFlag, ...],
    exclusions: tuple[PtmLocalizationExclusionMaskEntry, ...],
    findings: tuple[PtmLocalizationArtifactFinding, ...],
    disposition: PtmLocalizationArtifactDisposition,
) -> PtmLocalizationArtifactComputationReceipt:
    profile = _matching_profile(
        request.policy, request.quality_contract_version, request.quality_configuration_digest
    )
    traversed = _traversable(request)
    ledger = request.evidence_ledger
    payload: dict[str, object] = {
        "quality_result_digest": request.quality_result_digest,
        "quality_contract_version": request.quality_contract_version,
        "quality_configuration_digest": request.quality_configuration_digest,
        "quality_receipt_digest": request.quality_receipt_digest,
        "identity_resolution_digest": request.identity_resolution_digest,
        "raw_input_receipt_digest": request.raw_input_receipt_digest,
        "detector_policy_digest": policy_digest(request.policy),
        "detector_configuration_digest": configuration_digest(request.policy),
        "selected_profile_digest": profile_digest(profile) if profile is not None else None,
        "evidence_ledger_digest": ledger.ledger_digest if ledger is not None else None,
        "event_digests": tuple(sorted(event_digest(item) for item in ledger.events))
        if traversed and type(ledger) is PtmLocalizationArtifactEvidenceLedger
        else (),
        "posterior_digests": tuple(item.posterior_digest for item in posteriors),
        "contamination_flag_digests": tuple(
            sorted(contamination_flag_digest(item) for item in flags)
        ),
        "excluded_target_ids": tuple(item.target_id for item in exclusions),
        "finding_codes": tuple(item.code for item in findings),
        "parent_target": M0505_PARENT,
        "emits_parent": False,
        "disposition": disposition,
        "receipt_digest": _ZERO_DIGEST,
    }
    constructed = PtmLocalizationArtifactComputationReceipt.model_construct(**payload)  # type: ignore[arg-type]
    payload["receipt_digest"] = receipt_digest(constructed)
    return PtmLocalizationArtifactComputationReceipt.model_validate(payload, strict=True)


def _compute_result(
    request: DetectPtmLocalizationArtifactsRequest,
) -> PtmLocalizationArtifactDetectionResult:
    posteriors = _expected_posteriors(request)
    flags = _expected_flags(posteriors)
    exclusions = _expected_exclusions(posteriors, flags)
    findings = _expected_findings(request, posteriors, flags)
    disposition = _expected_disposition(request, posteriors)
    receipt = _expected_receipt(
        request,
        posteriors=posteriors,
        flags=flags,
        exclusions=exclusions,
        findings=findings,
        disposition=disposition,
    )
    payload: dict[str, object] = {
        "output_type": "ptm_localization_artifact_contamination_assessment",
        "result_id": f"result.{canonical_request_digest(request).removeprefix('sha256:')}",
        "result_version": M0505_CONTRACT_VERSION,
        "request_digest": canonical_request_digest(request),
        "policy_digest": policy_digest(request.policy),
        "configuration_digest": configuration_digest(request.policy),
        "receipt_digest": receipt.receipt_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "receipt": receipt,
        "artifact_posteriors": posteriors,
        "contamination_flags": flags,
        "exclusion_mask": exclusions,
        "findings": findings,
        "disposition": disposition,
        "parent_target": M0505_PARENT,
        "emits_variant_peptide": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "localizes_modification": False,
        "infers_kinase_activity": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "support": _expected_support(disposition),
        "uncertainty": _expected_uncertainty(),
        "provenance": _expected_provenance(request),
        "evidence": _evidence_index(request),
        "limitations": _expected_limitations(),
        "human_review_required": (
            disposition is not PtmLocalizationArtifactDisposition.CLEARED
            or any(
                item.state is PtmLocalizationArtifactPosteriorState.INDETERMINATE
                for item in posteriors
            )
        ),
        "completed_at": request.context.occurred_at,
    }
    assembled = PtmLocalizationArtifactDetectionResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(assembled)
    return PtmLocalizationArtifactDetectionResult.model_validate(payload, strict=True)


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        return dict.__getitem__(mapping, field) if dict.__contains__(mapping, field) else _MISSING
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            raise _InvalidPlainValueError
        return dict.__getitem__(storage, field) if dict.__contains__(storage, field) else _MISSING
    return _MISSING


def _validate_outer_request_shape(candidate: object) -> None:
    if type(candidate) is DetectPtmLocalizationArtifactsRequest:
        return
    mapping = cast("dict[object, object]", candidate)
    if any(key not in _REQUEST_FIELDS for key in dict.keys(mapping)):
        raise PtmLocalizationArtifactInputError


def _optional_plain_member(candidate: object, field: str) -> object:
    value = _member(candidate, field)
    return None if value is _MISSING else _plain_value(value)


def _materialize_ledger_binding(candidate: object) -> object:
    if type(candidate) is PtmLocalizationArtifactEvidenceLedgerBinding:
        return candidate
    return {
        field: _plain_value(_member(candidate, field))
        for field in (
            "ledger_id",
            "version",
            "quality_result_digest",
            "quality_contract_version",
            "quality_configuration_digest",
            "quality_receipt_digest",
            "identity_resolution_digest",
            "raw_input_receipt_digest",
            "recorded_at",
            "ledger_digest",
            "evidence",
        )
    }


def _built_in_sequence_length(candidate: object) -> int | None:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if list in candidate_mro:
        return list.__len__(cast("list[object]", candidate))
    if tuple in candidate_mro:
        return tuple.__len__(cast("tuple[object, ...]", candidate))
    return None


def _validate_policy_shape_before_copy(candidate: object) -> None:
    if type(candidate) is PtmLocalizationArtifactPolicy:
        return
    profiles = _member(candidate, "profiles")
    count = _built_in_sequence_length(profiles)
    if count is not None and count > 16:
        raise _InvalidPlainValueError
    if count is None:
        return
    iterator = (
        list.__iter__(cast("list[object]", profiles))
        if list in type.__getattribute__(type(profiles), "__mro__")
        else tuple.__iter__(cast("tuple[object, ...]", profiles))
    )
    for profile in iterator:
        threshold_count = _built_in_sequence_length(_member(profile, "thresholds"))
        if threshold_count is not None and threshold_count != 7:
            raise _InvalidPlainValueError


def _validate_ledger_shape_before_copy(candidate: object) -> None:
    if type(candidate) is PtmLocalizationArtifactEvidenceLedger:
        return
    events = _member(candidate, "events")
    count = _built_in_sequence_length(events)
    if count is not None and count > 448:
        raise _InvalidPlainValueError
    if count is None:
        return
    iterator = (
        list.__iter__(cast("list[object]", events))
        if list in type.__getattribute__(type(events), "__mro__")
        else tuple.__iter__(cast("tuple[object, ...]", events))
    )
    for event in iterator:
        evidence_count = _built_in_sequence_length(_member(event, "evidence"))
        if evidence_count is not None and evidence_count > 8:
            raise _InvalidPlainValueError


def _state_text(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(candidate: object, *, _depth: int = 0, _budget: list[int] | None = None) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(dict.__getitem__(storage, key), _depth=_depth + 1, _budget=budget)
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(dict.__getitem__(mapping, key), _depth=_depth + 1, _budget=budget)
            for key in dict.keys(mapping)
        }
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M0505PtmLocalizationArtifactEngine",
    "PtmLocalizationArtifactAuthorizationError",
    "PtmLocalizationArtifactInputError",
    "_validate_json_request",
    "detect_ptm_localization_artifacts",
    "preflight_ptm_localization_artifact_authorization",
]
