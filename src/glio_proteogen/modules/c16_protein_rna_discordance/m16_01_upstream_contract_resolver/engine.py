"""Deterministic, authorization-first M16-01 upstream resolver."""

# The resolver keeps protocol diagnostics explicit and readable.
# ruff: noqa: E501, PERF401

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_01 import (
    M1601_CONTRACT_VERSION,
    M1601_MODULE_ID,
    CompatibilityIssue,
    CompatibilityIssueCode,
    CompatibilityReport,
    CompatibilityStatus,
    ProteinRnaDiscordanceUpstreamResolutionResult,
    ResolveProteinRnaDiscordanceUpstreamRequest,
    ResolverFinding,
    ResolverStatus,
    ValidatedUpstreamBundle,
    canonical_request_digest,
    result_payload_digest,
)
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

_REQUEST_ADAPTER: Final = TypeAdapter(ResolveProteinRnaDiscordanceUpstreamRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceUpstreamResolutionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1601AuthorizationError(PermissionError):
    """Caller controls do not authorize upstream resolution."""

    def __init__(self) -> None:
        super().__init__(
            "M16-01 requires accepted controls, resolved identity, and granted consent"
        )


class M1601ReplayVerificationError(ValueError):
    """A resolver result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M16-01 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1601_authorization(candidate: object) -> None:
    """Check all seven controls before traversing candidate material."""

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
    except Exception:  # noqa: BLE001
        raise M1601AuthorizationError from None
    if states != expected:
        raise M1601AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1601_authorization(candidate)
    return candidate


def _evidence(
    request: ResolveProteinRnaDiscordanceUpstreamRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        *request.source_artifacts,
        request.policy.configuration.policy_reference,
        *[item.reference for item in request.policy.configuration.evidence],
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    for candidate in request.candidates:
        artifacts.extend(item.reference for item in candidate.evidence)
        artifacts.append(candidate.artifact)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M16-01 compatibility, consent, support and provenance material.",
        )
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, supported: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Typed candidate compatibility and all seven controls are explicit."
            if supported
            else "One or more candidate, compatibility, or control conditions are unresolved."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Version and media-type compatibility are caller-declared and not issuer-authenticated.",
            "Unsupported or missing evidence is never converted into a negative finding.",
        ),
    )


def _provenance(
    request: ResolveProteinRnaDiscordanceUpstreamRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in controls
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1601_MODULE_ID,
        module_version=M1601_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            *(candidate.artifact.digest for candidate in request.candidates),
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _evaluate(
    request: ResolveProteinRnaDiscordanceUpstreamRequest,
) -> tuple[bool, tuple[CompatibilityIssue, ...]]:
    issues: list[CompatibilityIssue] = []
    expected_version = request.policy.configuration.version
    for candidate in request.candidates:
        code: CompatibilityIssueCode | None = None
        message = ""
        if candidate.contract_version != expected_version:
            code = CompatibilityIssueCode.VERSION_MISMATCH
            message = (
                "Candidate contract version is incompatible with the locked resolver configuration."
            )
        elif candidate.artifact.media_type != candidate.required_media_type:
            code = CompatibilityIssueCode.MEDIA_TYPE_MISMATCH
            message = (
                "Candidate artifact media type does not match its declared required media type."
            )
        if code is not None:
            issues.append(
                CompatibilityIssue(
                    issue_id=f"issue.{candidate.candidate_id}",
                    code=code,
                    candidate_id=candidate.candidate_id,
                    message=message,
                    blocking=True,
                    evidence=candidate.evidence,
                )
            )
    required = set(request.policy.required_kinds)
    present = {candidate.kind for candidate in request.candidates}
    for kind in sorted(required - present, key=lambda item: item.value):
        issues.append(
            CompatibilityIssue(
                issue_id=f"issue.missing.{kind.value}",
                code=CompatibilityIssueCode.SUPPORT_MISSING,
                message=f"Required upstream kind {kind.value} is missing.",
                blocking=True,
                evidence=request.policy.configuration.evidence,
            )
        )
    return not issues, tuple(issues)


def _report(
    request: ResolveProteinRnaDiscordanceUpstreamRequest,
    evidence: tuple[EvidenceReference, ...],
    issues: tuple[CompatibilityIssue, ...],
) -> CompatibilityReport:
    issue_ids = {issue.candidate_id for issue in issues if issue.candidate_id is not None}
    accepted = tuple(
        candidate.candidate_id
        for candidate in request.candidates
        if candidate.candidate_id not in issue_ids
    )
    return CompatibilityReport(
        report_id="report.m1601",
        version=request.policy.configuration.version,
        status=CompatibilityStatus.ACCEPTED if not issues else CompatibilityStatus.REVIEW_REQUIRED,
        accepted_candidate_ids=accepted,
        issues=issues,
        all_rejections_typed=True,
        auditable=True,
        evidence=evidence,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_controls",
            statement="Candidate versions, media types, controls, and evidence are caller-declared.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement="No kinase activity, all-omics fusion, treatment recommendation, or identity inference is emitted.",
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No validated upstream bundle is published outside the compatibility domain.",
            )
        )
    return tuple(values)


class M1601UpstreamContractResolverEngine:
    """Resolve typed upstream candidates without mutating or dereferencing them."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: ResolveProteinRnaDiscordanceUpstreamRequest
    ) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, issues = _evaluate(request)
        report = _report(request, evidence, issues)
        bundle = (
            ValidatedUpstreamBundle(
                bundle_id="bundle.m1601",
                version=request.policy.configuration.version,
                accepted_candidates=request.candidates,
                compatibility_report=report,
                consent_preserved=True,
                provenance_preserved=True,
                uncertainty_preserved=True,
                evidence=evidence,
            )
            if supported
            else None
        )
        findings = tuple(
            ResolverFinding(
                finding_id=f"finding.{issue.issue_id}",
                code=issue.code,
                message=issue.message,
                evidence=issue.evidence,
            )
            for issue in issues
        )
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_upstream_resolution",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1601_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": ResolverStatus.RESOLVED if supported else ResolverStatus.ABSTAINED,
            "bundle": bundle,
            "compatibility_report": report,
            "findings": findings,
            "abstention_reason": None
            if supported
            else "Upstream candidates are not safely compatible with the locked resolver policy.",
            "parent_target": "protein_rna_discordance",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1601_compatibility_supported"
                if supported
                else "m1601_compatibility_abstained",
                rationale="All required candidates are version- and media-type compatible."
                if supported
                else "Compatibility is unresolved; review is required before acceptance.",
            ),
            "uncertainty": _uncertainty(supported=supported),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinRnaDiscordanceUpstreamResolutionResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1601ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1601ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1601ReplayVerificationError
        return validated


def resolve_protein_rna_discordance_upstream_contracts(
    request: object,
) -> ProteinRnaDiscordanceUpstreamResolutionResult:
    """Public provisional M16-01 operation."""

    return M1601UpstreamContractResolverEngine().infer(request)


__all__ = [
    "M1601AuthorizationError",
    "M1601ReplayVerificationError",
    "M1601UpstreamContractResolverEngine",
    "preflight_m1601_authorization",
    "resolve_protein_rna_discordance_upstream_contracts",
]
