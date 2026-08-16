"""Deterministic M26-08 retirement and archive runtime.

The runtime is deliberately administrative: it does not traverse external content,
infer identity or consent, or turn missing evidence into a negative finding. It
evaluates only the typed, caller-declared retirement package and emits either a
closed executed package or an explicit abstention.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, NoReturn

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_08 import (
    M2608_CONTRACT_VERSION,
    M2608_MODULE_ID,
    ArchiveStatus,
    ProteinSubtypeRetirementResult,
    RetirementFinding,
    RetirementFindingCode,
    RetirementPackage,
    RetirementRunStatus,
    RetirementStatus,
    RetireProteinSubtypeServiceRequest,
)
from glio_proteogen.contracts.m26_08.canonical import (
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

_REQUEST_ADAPTER: Final[TypeAdapter[RetireProteinSubtypeServiceRequest]] = TypeAdapter(
    RetireProteinSubtypeServiceRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeRetirementResult]] = TypeAdapter(
    ProteinSubtypeRetirementResult
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
        code="retirement_traceability_only",
        statement=(
            "M26-08 records caller-declared retirement, migration, preservation, communication "
            "and archival evidence; it does not infer biological truth or service correctness."
        ),
    ),
    Limitation(
        code="issuer_authority_unverified",
        statement=(
            "Artifact references and acknowledgements are preserved without authenticating "
            "the authority of their issuer."
        ),
    ),
    Limitation(
        code="no_identity_or_consent_inference",
        statement=(
            "Identity, consent, treatment, kinase, all-omics and intended-use decisions are "
            "accepted only from typed upstream controls and never inferred here."
        ),
    ),
    Limitation(
        code="provisional_release",
        statement=(
            "The ABI and retirement policy remain provisional until the governed owner confirms "
            "the dossier-derived interface and release procedure."
        ),
    ),
)


class M2608AuthorizationError(ValueError):
    """Caller-declared controls do not authorize retirement evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M26-08 retirement requires accepted configuration, resolved identity, granted "
            "consent, and accepted provenance, quality, support, and intended-use controls"
        )


class M2608ReplayError(ValueError):
    """A retirement result failed canonical replay verification."""

    def __init__(self) -> None:
        super().__init__("M26-08 retirement replay verification failed")


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2608_authorization(candidate: object) -> None:
    """Fail closed on all seven upstream controls before reading retirement data."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        authorized = all(
            _state(_member(references, role.value)) == expected
            for role, expected in _EXPECTED_CONTROL_STATES.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2608AuthorizationError from None
    if not authorized:
        raise M2608AuthorizationError


def _evidence(request: RetireProteinSubtypeServiceRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M26-08 retirement, migration, preservation, communication "
                "and archival evidence; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _findings(request: RetireProteinSubtypeServiceRequest) -> tuple[RetirementFinding, ...]:  # noqa: C901
    evidence = _evidence(request)
    findings: list[RetirementFinding] = []

    def add(code: RetirementFindingCode, key: str, message: str) -> None:
        findings.append(
            RetirementFinding(
                finding_id=f"finding.m2608.{key}",
                code=code,
                message=message,
                evidence=evidence,
            )
        )

    for item in request.criteria:
        if not item.satisfied:
            add(
                RetirementFindingCode.CRITERION_UNSATISFIED,
                f"criterion.{item.criterion_id}",
                f"retirement criterion {item.criterion_id} is not satisfied",
            )
    for migration in request.migrations:
        if migration.status.value != "completed":
            add(
                RetirementFindingCode.DEPENDENCY_MIGRATION_INCOMPLETE,
                f"migration.{migration.migration_id}",
                f"dependency migration {migration.migration_id} is {migration.status.value}",
            )
    for preservation in request.preserved_evidence:
        if not preservation.retrievable:
            add(
                RetirementFindingCode.EVIDENCE_NOT_RETRIEVABLE,
                f"preservation.{preservation.preservation_id}",
                f"preserved evidence {preservation.preservation_id} is not retrievable",
            )
    for communication in request.communications:
        if not communication.acknowledged:
            add(
                RetirementFindingCode.COMMUNICATION_UNACKNOWLEDGED,
                f"communication.{communication.communication_id}",
                f"communication {communication.communication_id} has not been acknowledged",
            )
    if request.archive.status is not ArchiveStatus.VERIFIED or not request.archive.retrievable:
        add(
            RetirementFindingCode.ARCHIVE_UNVERIFIED,
            "archive",
            "long-term archive is not verified and retrievable",
        )
    for dependency in request.configuration.active_dependencies:
        add(
            RetirementFindingCode.ACTIVE_DEPENDENCY,
            f"active.{dependency}",
            f"active dependency {dependency} remains attached to the retiring service",
        )
    if not findings:
        findings.append(
            RetirementFinding(
                finding_id="finding.m2608.provisional-review",
                code=RetirementFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Provisional retirement ABI requires governed owner review.",
                evidence=evidence,
            )
        )
    return tuple(findings)


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M26-08 does not estimate {dimension} uncertainty from archival records.",
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
            "Retirement is an operational decision, not a biological estimate.",
            "Abstention is not evidence that a dependency, archive or source is negative.",
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
    request: RetireProteinSubtypeServiceRequest,
    request_digest: str,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m2608.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2608_MODULE_ID,
        module_version=M2608_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted({request_digest, *(artifact.digest for artifact in request.source_artifacts)})
        ),
        configuration_digest=sha256_digest(
            {
                "module": M2608_MODULE_ID,
                "contract": M2608_CONTRACT_VERSION,
                "configuration": request.configuration.configuration_id,
                "archive": request.archive.archive_id,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _build_package(request: RetireProteinSubtypeServiceRequest) -> RetirementPackage:
    package_payload = {
        "criteria": request.criteria,
        "migrations": request.migrations,
        "preserved_evidence": request.preserved_evidence,
        "communications": request.communications,
        "archive": request.archive,
        "configuration": request.configuration,
    }
    return RetirementPackage(
        package_id=f"package.m2608.{request.request_id}",
        version=request.configuration.version,
        status=RetirementStatus.EXECUTED,
        criteria=request.criteria,
        migrations=request.migrations,
        preserved_evidence=request.preserved_evidence,
        communications=request.communications,
        archive=request.archive,
        configuration=request.configuration,
        evidence=_evidence(request),
        package_digest=sha256_digest(package_payload),
    )


def _build_result(request: RetireProteinSubtypeServiceRequest) -> ProteinSubtypeRetirementResult:
    request_digest = canonical_request_digest(request)
    findings = _findings(request)
    blocking_codes = {
        RetirementFindingCode.CRITERION_UNSATISFIED,
        RetirementFindingCode.DEPENDENCY_MIGRATION_INCOMPLETE,
        RetirementFindingCode.EVIDENCE_NOT_RETRIEVABLE,
        RetirementFindingCode.COMMUNICATION_UNACKNOWLEDGED,
        RetirementFindingCode.ARCHIVE_UNVERIFIED,
        RetirementFindingCode.ACTIVE_DEPENDENCY,
    }
    blocking = any(item.code in blocking_codes for item in findings)
    controls = _controls(request.context)
    evidence = _evidence(request)
    package = None if blocking else _build_package(request)
    candidate: dict[str, Any] = {
        "output_type": "protein_subtype_retirement_package",
        "result_id": f"result.m2608.{request_digest.removeprefix('sha256:')}",
        "result_version": M2608_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": RetirementRunStatus.ABSTAINED if blocking else RetirementRunStatus.EXECUTED,
        "package": package,
        "findings": findings,
        "abstention_reason": (
            "Retirement abstained because one or more criteria, migration, evidence, "
            "communication, archive, or active-dependency gates failed."
            if blocking
            else None
        ),
        "parent_target": "protein subtype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED if blocking else SupportStatus.SUPPORTED,
            reason_code="retirement_abstained" if blocking else "retirement_supported",
            rationale=(
                "Retirement evidence is incomplete; no service retirement is authorized."
                if blocking
                else "All caller-declared retirement and archive gates passed."
            ),
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_digest, controls),
        "evidence": evidence,
        "limitations": _LIMITATIONS,
        "human_review_required": True,
    }
    materialized = ProteinSubtypeRetirementResult.model_construct(**candidate)
    payload = materialized.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M2608RetirementEngine:
    """Build one deterministic retirement result without I/O or learned inference."""

    __slots__ = ()

    def retire(self, request: RetireProteinSubtypeServiceRequest) -> ProteinSubtypeRetirementResult:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2608_authorization(validated)
        return _build_result(validated)

    def verify(self, result: ProteinSubtypeRetirementResult) -> ProteinSubtypeRetirementResult:
        return verify_retirement_result(result)


def retire_protein_subtype_service(request: object) -> ProteinSubtypeRetirementResult:
    """Public stateless M26-08 retirement entry point."""

    return M2608RetirementEngine().retire(_REQUEST_ADAPTER.validate_python(request, strict=True))


def _raise_replay() -> NoReturn:
    raise M2608ReplayError


def verify_retirement_result(
    result: ProteinSubtypeRetirementResult,
) -> ProteinSubtypeRetirementResult:
    """Verify canonical request, result identity, digest, and deterministic replay."""

    try:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        if validated.request_digest != canonical_request_digest(validated.request):
            _raise_replay()
        expected_id = f"result.m2608.{validated.request_digest.removeprefix('sha256:')}"
        if validated.result_id != expected_id:
            _raise_replay()
        if validated.result_digest != result_payload_digest(validated):
            _raise_replay()
        expected = M2608RetirementEngine().retire(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            _raise_replay()
    except M2608ReplayError:
        raise
    except (TypeError, ValueError, ValidationError) as error:
        raise M2608ReplayError from error
    return validated


__all__ = [
    "M2608AuthorizationError",
    "M2608ReplayError",
    "M2608RetirementEngine",
    "preflight_m2608_authorization",
    "retire_protein_subtype_service",
    "verify_retirement_result",
]
