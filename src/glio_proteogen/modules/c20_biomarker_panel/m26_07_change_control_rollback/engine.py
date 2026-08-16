"""Deterministic, caller-declared M26-07 change-control runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, NoReturn

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_07 import (
    M2607_CONTRACT_VERSION,
    M2607_MODULE_ID,
    ChangeFinding,
    ChangeFindingCode,
    ChangePackage,
    ChangeStatus,
    ControlProteinSubtypeChangeRequest,
    ProteinSubtypeChangeControlResult,
    RolloutStage,
)
from glio_proteogen.contracts.m26_07.canonical import (
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
    ExecutionContext,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final[TypeAdapter[ControlProteinSubtypeChangeRequest]] = TypeAdapter(
    ControlProteinSubtypeChangeRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeChangeControlResult]] = TypeAdapter(
    ProteinSubtypeChangeControlResult
)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_EXPECTED_CONTROL_STATES: Final[dict[ControlRole, str]] = {
    ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
    ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.CONSENT: ConsentState.GRANTED.value,
    ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
}
_LIMITATIONS: Final = (
    Limitation(
        code="change_control_traceability_only",
        statement=(
            "M26-07 records caller-declared change controls and rollback evidence; it does not "
            "infer biological truth, identity, consent, treatment, or kinase state."
        ),
    ),
    Limitation(
        code="issuer_authority_unverified",
        statement=(
            "Caller-declared approvals and artifacts are retained but issuer authority "
            "is not authenticated."
        ),
    ),
    Limitation(
        code="provisional_release",
        statement=(
            "Promotion remains provisional until governed owner, rollout, and recovery review."
        ),
    ),
)


class M2607AuthorizationError(ValueError):
    """Caller-declared controls do not authorize change traversal."""

    def __init__(self) -> None:
        super().__init__(
            "M26-07 change control requires accepted configuration, resolved identity, granted "
            "consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2607ReplayError(ValueError):
    """A change-control result failed canonical replay verification."""

    def __init__(self) -> None:
        super().__init__("M26-07 change-control replay verification failed")


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2607_authorization(candidate: object) -> None:
    """Fail closed on all seven controls before examining change material."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        authorized = all(
            _state(_member(references, role.value)) == expected
            for role, expected in _EXPECTED_CONTROL_STATES.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2607AuthorizationError from None
    if not authorized:
        raise M2607AuthorizationError


def _evidence(request: ControlProteinSubtypeChangeRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M26-07 change-control evidence; issuer authority "
                "is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _findings(request: ControlProteinSubtypeChangeRequest) -> tuple[ChangeFinding, ...]:
    evidence = _evidence(request)
    findings: list[ChangeFinding] = []
    required = set(request.proposal.required_revalidation_ids)
    passed = {item.revalidation_id for item in request.revalidations if item.passed}
    findings.extend(
        ChangeFinding(
            finding_id=f"finding.m2607.revalidation.{missing}",
            code=ChangeFindingCode.REVALIDATION_REQUIRED,
            message=f"required revalidation {missing} has not passed",
            evidence=evidence,
        )
        for missing in sorted(required - passed)
    )
    findings.extend(
        ChangeFinding(
            finding_id=f"finding.m2607.failed.{item.revalidation_id}",
            code=ChangeFindingCode.REVALIDATION_REQUIRED,
            message=f"revalidation {item.revalidation_id} failed",
            evidence=evidence,
        )
        for item in request.revalidations
        if not item.passed
    )
    if not findings:
        findings.append(
            ChangeFinding(
                finding_id="finding.m2607.provisional-review",
                code=ChangeFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Provisional change-control ABI requires governed owner review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M26-07 does not estimate {dimension} uncertainty from change-control material."
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Change-control decisions are operational records, not biological estimates.",
            "Abstention never becomes negative evidence or a rollback authorization.",
        ),
    )


def _controls(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
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
            state=getattr(reference.state, "value", reference.state),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in values
    )


def _provenance(
    request: ControlProteinSubtypeChangeRequest,
    request_digest: str,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m2607.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2607_MODULE_ID,
        module_version=M2607_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted({request_digest, *(artifact.digest for artifact in request.source_artifacts)})
        ),
        configuration_digest=sha256_digest(
            {
                "module": M2607_MODULE_ID,
                "contract": M2607_CONTRACT_VERSION,
                "proposal": request.proposal.proposal_id,
                "stage": RolloutStage.STAGED.value,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _build_package(request: ControlProteinSubtypeChangeRequest) -> ChangePackage:
    package_payload = {
        "proposal": request.proposal,
        "revalidations": request.revalidations,
        "comparisons": request.comparisons,
        "rollback": request.rollback_point,
        "stage": RolloutStage.STAGED.value,
        "approved_by": request.context.actor_id,
    }
    return ChangePackage(
        package_id=f"package.m2607.{request.proposal.proposal_id}",
        version=request.proposal.proposed_version,
        proposal=request.proposal,
        revalidations=request.revalidations,
        comparisons=request.comparisons,
        rollout_stage=RolloutStage.STAGED,
        approved_by=request.context.actor_id,
        rollback_point=request.rollback_point,
        package_digest=sha256_digest(package_payload),
        evidence=_evidence(request),
    )


def _build_result(request: ControlProteinSubtypeChangeRequest) -> ProteinSubtypeChangeControlResult:
    request_digest = canonical_request_digest(request)
    findings = _findings(request)
    blocking = any(
        item.code in {ChangeFindingCode.REVALIDATION_REQUIRED, ChangeFindingCode.ROLLBACK_UNTESTED}
        for item in findings
    )
    controls = _controls(request.context)
    evidence = _evidence(request)
    package = None if blocking else _build_package(request)
    candidate: dict[str, Any] = {
        "output_type": "protein_subtype_change_control",
        "result_id": f"result.m2607.{request_digest.removeprefix('sha256:')}",
        "result_version": M2607_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": ChangeStatus.ABSTAINED if blocking else ChangeStatus.APPROVED,
        "change_package": package,
        "rollback_point": None if blocking else request.rollback_point,
        "findings": findings,
        "abstention_reason": (
            "Change promotion abstained because required revalidation or tested rollback "
            "evidence is missing."
            if blocking
            else None
        ),
        "parent_target": "protein subtype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED if blocking else SupportStatus.SUPPORTED,
            reason_code="change_control_abstained" if blocking else "change_control_supported",
            rationale=(
                "Required revalidation and tested rollback evidence are incomplete; no "
                "promotion is authorized."
                if blocking
                else "All caller-declared revalidation, comparison, approval, and rollback "
                "gates passed."
            ),
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_digest, controls),
        "evidence": evidence,
        "limitations": _LIMITATIONS,
        "human_review_required": True,
    }
    materialized = ProteinSubtypeChangeControlResult.model_construct(**candidate)
    payload = materialized.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M2607ChangeControlEngine:
    """Build one deterministic change-control result without I/O or learned inference."""

    __slots__ = ()

    def control(
        self, request: ControlProteinSubtypeChangeRequest
    ) -> ProteinSubtypeChangeControlResult:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2607_authorization(validated)
        return _build_result(validated)

    def verify(
        self, result: ProteinSubtypeChangeControlResult
    ) -> ProteinSubtypeChangeControlResult:
        return verify_change_control_result(result)


def control_protein_subtype_change_and_rollback(
    request: object,
) -> ProteinSubtypeChangeControlResult:
    """Public stateless M26-07 change-control entry point."""

    return M2607ChangeControlEngine().control(
        _REQUEST_ADAPTER.validate_python(request, strict=True)
    )


def _raise_replay() -> NoReturn:
    raise M2607ReplayError


def verify_change_control_result(
    result: ProteinSubtypeChangeControlResult,
) -> ProteinSubtypeChangeControlResult:
    """Verify canonical request, result ID, digest, and safe result closure."""

    try:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        if validated.request_digest != canonical_request_digest(validated.request):
            _raise_replay()
        expected_id = f"result.m2607.{validated.request_digest.removeprefix('sha256:')}"
        if validated.result_id != expected_id:
            _raise_replay()
        if validated.result_digest != result_payload_digest(validated):
            _raise_replay()
        expected = M2607ChangeControlEngine().control(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            _raise_replay()
    except M2607ReplayError:
        raise
    except (TypeError, ValueError, ValidationError) as error:
        raise M2607ReplayError from error
    return validated


__all__ = [
    "M2607AuthorizationError",
    "M2607ChangeControlEngine",
    "M2607ReplayError",
    "control_protein_subtype_change_and_rollback",
    "preflight_m2607_authorization",
    "verify_change_control_result",
]
