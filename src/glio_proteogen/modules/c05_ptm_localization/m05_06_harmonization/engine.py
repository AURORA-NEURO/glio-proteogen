"""Deterministic provisional M05-06 PTM-localization harmonization engine."""

# Provisional boundary has deliberately verbose fail-closed diagnostics.
# ruff: noqa: E501, PLR2004, TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_05 import (
    M0505_CONTRACT_VERSION,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationEvidenceUnitKind,
)
from glio_proteogen.contracts.m05_06 import (
    M0506_CONTRACT_VERSION,
    M0506_EVIDENCE_CLAIM,
    M0506_OUTPUT_MEDIA_TYPE,
    M0506_PARENT,
    M0506_ZERO_DIGEST,
    HarmonizePtmLocalizationAnalysisRequest,
    PtmLocalizationArtifactAction,
    PtmLocalizationArtifactEvaluationState,
    PtmLocalizationArtifactHarmonizationReceipt,
    PtmLocalizationArtifactTargetReceipt,
    PtmLocalizationArtifactTargetState,
    PtmLocalizationHarmonizationComputationReceipt,
    PtmLocalizationHarmonizationDisposition,
    PtmLocalizationHarmonizationFinding,
    PtmLocalizationHarmonizationFindingAction,
    PtmLocalizationHarmonizationFindingCode,
    PtmLocalizationHarmonizationPolicy,
    PtmLocalizationHarmonizationProfile,
    PtmLocalizationHarmonizationResult,
    expected_provenance,
    opaque_harmonization_identifier,
)
from glio_proteogen.contracts.m05_06.canonical import (
    artifact_receipt_digest,
    canonical_request_digest,
    computation_receipt_digest,
    configuration_digest,
    policy_digest,
    result_payload_digest,
    target_binding_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.kernel import (
    M0506PtmLocalizationHarmonizationKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizePtmLocalizationAnalysisRequest)
_RESULT_ADAPTER: Final = TypeAdapter(PtmLocalizationHarmonizationResult)


class PtmLocalizationHarmonizationAuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M05-06 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_ptm_localization_harmonization_authorization(candidate: object) -> None:
    """Check seven controls before opening the complete M05-05 result or ledger."""

    if not isinstance(candidate, Mapping) and not isinstance(
        candidate, HarmonizePtmLocalizationAnalysisRequest
    ):
        raise PtmLocalizationHarmonizationAuthorizationError
    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise PtmLocalizationHarmonizationAuthorizationError from None
    if states != expected:
        raise PtmLocalizationHarmonizationAuthorizationError


def _safe_candidate(candidate: object) -> object:
    """Remove a caller ledger before deep traversal when upstream already failed."""

    if not isinstance(candidate, dict):
        return candidate
    artifact = candidate.get("artifact_result")
    disposition = _state(_member(artifact, "disposition"))
    if disposition not in {
        PtmLocalizationArtifactDisposition.CLEARED.value,
        PtmLocalizationArtifactDisposition.CLEARED,
        None,
    }:
        sanitized = dict(candidate)
        sanitized["support_ledger"] = None
        return sanitized
    return candidate


def _target_projection(result: object) -> tuple[PtmLocalizationArtifactTargetReceipt, ...]:
    """Project all seven M05-05 posteriors for each target without dropping detail."""

    posteriors = cast("tuple[object, ...]", _member(result, "artifact_posteriors"))
    flags = cast("tuple[object, ...]", _member(result, "contamination_flags"))
    exclusions = cast("tuple[object, ...]", _member(result, "exclusion_mask"))
    grouped: dict[str, list[object]] = {}
    for posterior in posteriors:
        target_id = cast("str", _member(posterior, "target_id"))
        grouped.setdefault(target_id, []).append(posterior)
    excluded = {cast("str", _member(item, "target_id")) for item in exclusions}
    flags_by_target: dict[str, list[str]] = {}
    for flag in flags:
        target_id = cast("str", _member(flag, "target_id"))
        flags_by_target.setdefault(target_id, []).append(cast("str", _member(flag, "flag_id")))
    projections: list[PtmLocalizationArtifactTargetReceipt] = []
    for target_id, values in sorted(grouped.items()):
        if len(values) != 7:
            raise ValueError("M05-05 target projection requires all seven detector posteriors")
        states = {_state(_member(value, "state")) for value in values}
        observations = {_state(_member(value, "observation_state")) for value in values}
        if target_id in excluded or "detected" in states:
            target_state = PtmLocalizationArtifactTargetState.EXCLUDED
            action = PtmLocalizationArtifactAction.EXCLUDE
        elif "suspected" in states or flags_by_target.get(target_id):
            target_state = PtmLocalizationArtifactTargetState.REVIEW
            action = PtmLocalizationArtifactAction.REVIEW
        elif "indeterminate" in states or "observed" not in observations:
            target_state = PtmLocalizationArtifactTargetState.INDETERMINATE
            action = PtmLocalizationArtifactAction.REVIEW
        else:
            target_state = PtmLocalizationArtifactTargetState.CLEAR
            action = PtmLocalizationArtifactAction.RETAIN
        digests = tuple(sorted(cast("str", _member(value, "posterior_digest")) for value in values))
        unit_kind = cast("PtmLocalizationEvidenceUnitKind", _member(values[0], "unit_kind"))
        projections.append(
            PtmLocalizationArtifactTargetReceipt(
                target_id=target_id,
                unit_kind=unit_kind,
                target_state=target_state,
                action=action,
                posterior_digests=digests,
                posterior_binding_digest=sha256_digest(digests),
                contamination_flag_ids=tuple(sorted(flags_by_target.get(target_id, ()))),
                excluded=target_state is PtmLocalizationArtifactTargetState.EXCLUDED,
            )
        )
    return tuple(projections)


def artifact_harmonization_receipt(
    result: object,
) -> PtmLocalizationArtifactHarmonizationReceipt:
    """Build the exact M05-05 replay receipt consumed by M05-06."""

    projections = _target_projection(result)
    request = _member(result, "request")
    upstream_receipt = _member(result, "receipt")
    disposition = _member(result, "disposition")
    result_digest = cast("str", _member(result, "result_digest"))
    request_digest = cast("str", _member(result, "request_digest"))
    raw_input = _member(request, "raw_input_result")
    payload: dict[str, object] = {
        "artifact_reference": ArtifactReference(
            artifact_id=cast("str", _member(result, "result_id")),
            version=cast("str", _member(result, "result_version")),
            digest=result_digest,
            media_type=M0506_OUTPUT_MEDIA_TYPE.replace("m05-06", "m05-05"),
        ),
        "artifact_result_digest": result_digest,
        "artifact_request_digest": request_digest,
        "artifact_disposition": disposition,
        "artifact_support_status": _member(_member(result, "support"), "status"),
        "artifact_human_review_required": _member(result, "human_review_required"),
        "artifact_completed_at": _member(result, "completed_at"),
        "quality_result_digest": _member(_member(request, "quality_result_digest"), "__str__")
        if False
        else _member(request, "quality_result_digest"),
        "identity_resolution_digest": _member(request, "identity_resolution_digest"),
        "raw_input_receipt_digest": _member(request, "raw_input_receipt_digest"),
        "evaluation_state": (
            PtmLocalizationArtifactEvaluationState.COMPLETE
            if disposition is PtmLocalizationArtifactDisposition.CLEARED
            else PtmLocalizationArtifactEvaluationState.NOT_EVALUABLE
        ),
        "target_count": len(projections),
        "targets": projections,
        "target_binding_digest": target_binding_digest(projections),
        "receipt_digest": M0506_ZERO_DIGEST,
    }
    # Keep the complete M05-05 receipt fields as a consistency check; no raw
    # payload is copied into M05-06.
    if upstream_receipt is None or raw_input is None:
        raise ValueError("M05-05 result is missing its complete receipt")
    constructed = PtmLocalizationArtifactHarmonizationReceipt.model_construct(
        **payload,  # type: ignore[arg-type]
    )
    payload["receipt_digest"] = artifact_receipt_digest(constructed)
    return PtmLocalizationArtifactHarmonizationReceipt.model_validate(payload, strict=True)


def _finding(
    code: PtmLocalizationHarmonizationFindingCode,
    request_digest: str,
    targets: tuple[str, ...] = (),
) -> PtmLocalizationHarmonizationFinding:
    return PtmLocalizationHarmonizationFinding(
        finding_id=opaque_harmonization_identifier(
            "evidence", {"code": code.value, "request": request_digest, "targets": targets}
        ),
        code=code,
        action={
            PtmLocalizationHarmonizationFindingCode.UPSTREAM_QUARANTINED: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
            PtmLocalizationHarmonizationFindingCode.UPSTREAM_ABSTAINED: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
            PtmLocalizationHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
            PtmLocalizationHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
        }.get(code, PtmLocalizationHarmonizationFindingAction.QUARANTINE),
        message=code.value.replace("_", " ").capitalize() + ".",
        target_ids=targets,
    )


def _profile(
    policy: PtmLocalizationHarmonizationPolicy,
) -> PtmLocalizationHarmonizationProfile | None:
    return next(
        (
            profile
            for profile in policy.profiles
            if M0505_CONTRACT_VERSION in profile.approved_artifact_contract_versions
        ),
        None,
    )


def _evidence(request: HarmonizePtmLocalizationAnalysisRequest) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    controls = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
    )
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M0506_EVIDENCE_CLAIM)
        for reference in controls
    )


def _support(disposition: PtmLocalizationHarmonizationDisposition) -> SupportDecision:
    return {
        PtmLocalizationHarmonizationDisposition.ACCEPTED: SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="ptm_localization_harmonization_accepted",
            rationale="The provisional deterministic transform completed on M05-05-cleared support.",
        ),
        PtmLocalizationHarmonizationDisposition.QUARANTINED: SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="ptm_localization_harmonization_quarantined",
            rationale="Upstream artifact review or a binding conflict prevents release.",
        ),
        PtmLocalizationHarmonizationDisposition.ABSTAINED: SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="ptm_localization_harmonization_abstained",
            rationale="The upstream result or support coordinate is not safely evaluable.",
        ),
    }[disposition]


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="ptm_localization_harmonization_only",
            statement="Output is limited to bounded PTM support-coordinate harmonization.",
        ),
        Limitation(
            code="support_coordinate_not_probability",
            statement="Support coordinates are not abundance values or calibrated probabilities.",
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement="The M05-06 ABI is provisional pending owner confirmation.",
        ),
    )


def _prepare(candidate: object) -> object:
    preflight_ptm_localization_harmonization_authorization(candidate)
    return _safe_candidate(candidate)


class M0506PtmLocalizationHarmonizationEngine:
    """Replay M05-05 and harmonize only caller-declared, cleared support."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0506PtmLocalizationHarmonizationKernel | None = None) -> None:
        self._kernel = kernel or M0506PtmLocalizationHarmonizationKernel()

    def harmonize(self, request: object) -> PtmLocalizationHarmonizationResult:
        prepared = _prepare(request)
        validated = _REQUEST_ADAPTER.validate_python(prepared, strict=True)
        expected_receipt = artifact_harmonization_receipt(validated.artifact_result)
        if validated.artifact_receipt != expected_receipt:
            raise ValueError("artifact receipt must replay the exact full M05-05 result")
        return self._result(validated)

    def _result(
        self,
        request: HarmonizePtmLocalizationAnalysisRequest,
    ) -> PtmLocalizationHarmonizationResult:
        request_hash = canonical_request_digest(request)
        policy_hash = policy_digest(request.policy)
        config_hash = configuration_digest(request.policy)
        upstream = request.artifact_result.disposition
        findings: tuple[PtmLocalizationHarmonizationFinding, ...] = ()
        disposition = PtmLocalizationHarmonizationDisposition.ACCEPTED
        execution = None
        profile = _profile(request.policy)
        if upstream is PtmLocalizationArtifactDisposition.QUARANTINED:
            disposition = PtmLocalizationHarmonizationDisposition.QUARANTINED
            findings = (
                _finding(
                    PtmLocalizationHarmonizationFindingCode.UPSTREAM_QUARANTINED, request_hash
                ),
            )
        elif upstream is PtmLocalizationArtifactDisposition.ABSTAINED:
            disposition = PtmLocalizationHarmonizationDisposition.ABSTAINED
            findings = (
                _finding(PtmLocalizationHarmonizationFindingCode.UPSTREAM_ABSTAINED, request_hash),
            )
        elif profile is None:
            disposition = PtmLocalizationHarmonizationDisposition.ABSTAINED
            findings = (
                _finding(
                    PtmLocalizationHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED,
                    request_hash,
                ),
            )
        elif request.support_ledger is None:
            disposition = PtmLocalizationHarmonizationDisposition.ABSTAINED
            findings = (
                _finding(
                    PtmLocalizationHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE,
                    request_hash,
                ),
            )
        else:
            execution = self._kernel.harmonize(
                request.support_ledger,
                request.policy,
                profile_digest=sha256_digest(profile),
                policy_digest=policy_hash,
                configuration_digest=config_hash,
            )
        profile_hash = sha256_digest(profile) if profile is not None else None
        analysis = execution.analysis if execution else None
        manifest = execution.transformation_manifest if execution else None
        analysis_hash = analysis.analysis_digest if analysis else None
        manifest_hash = manifest.manifest_digest if manifest else None
        receipt_payload: dict[str, object] = {
            "artifact_result_digest": request.artifact_result.result_digest,
            "artifact_receipt_digest": request.artifact_receipt.receipt_digest,
            "policy_digest": policy_hash,
            "configuration_digest": config_hash,
            "profile_digest": profile_hash,
            "analysis_digest": analysis_hash,
            "transformation_manifest_digest": manifest_hash,
            "finding_codes": tuple(item.code for item in findings),
            "disposition": disposition,
            "receipt_digest": M0506_ZERO_DIGEST,
        }
        receipt_constructed = PtmLocalizationHarmonizationComputationReceipt.model_construct(
            **receipt_payload,  # type: ignore[arg-type]
        )
        receipt_payload["receipt_digest"] = computation_receipt_digest(receipt_constructed)
        receipt = PtmLocalizationHarmonizationComputationReceipt.model_validate(
            receipt_payload, strict=True
        )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0506_CONTRACT_VERSION,
            "request_digest": request_hash,
            "policy_digest": policy_hash,
            "configuration_digest": config_hash,
            "result_digest": M0506_ZERO_DIGEST,
            "request": request,
            "receipt": receipt,
            "analysis": analysis,
            "transformation_manifest": manifest,
            "technical_effect_diagnostics": execution.technical_effect_diagnostics
            if execution
            else (),
            "invariant_diagnostics": execution.invariant_diagnostics if execution else (),
            "findings": findings,
            "disposition": disposition,
            "parent_target": M0506_PARENT,
            "support": _support(disposition),
            "uncertainty": __import__(
                "glio_proteogen.contracts.m05_06", fromlist=["expected_uncertainty"]
            ).expected_uncertainty(),
            "provenance": expected_provenance(
                request,
                request_hash,
                config_hash,
                tuple(
                    item
                    for item in (
                        request.artifact_result.result_digest,
                        request.artifact_receipt.receipt_digest,
                        request.support_ledger.ledger_digest if request.support_ledger else None,
                        profile_hash,
                    )
                    if item is not None
                ),
            ),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": disposition
            is not PtmLocalizationHarmonizationDisposition.ACCEPTED,
            "completed_at": request.context.occurred_at,
        }
        result_constructed = PtmLocalizationHarmonizationResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(result_constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def harmonize_ptm_localization_analysis(request: object) -> PtmLocalizationHarmonizationResult:
    """Public provisional M05-06 operation."""

    return M0506PtmLocalizationHarmonizationEngine().harmonize(request)


__all__ = [
    "M0506PtmLocalizationHarmonizationEngine",
    "PtmLocalizationHarmonizationAuthorizationError",
    "artifact_harmonization_receipt",
    "harmonize_ptm_localization_analysis",
    "preflight_ptm_localization_harmonization_authorization",
]
