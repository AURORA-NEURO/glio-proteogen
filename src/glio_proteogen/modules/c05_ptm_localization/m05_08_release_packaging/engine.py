"""Deterministic, quarantine-first M05-08 release-packaging engine.

The dossier requires immutable provenance and a signed reproducibility package.  The
signature verifier is deliberately injected; this module never owns signing keys and
never treats an unavailable verifier as a successful release.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Protocol

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_08 import (
    M0508_MAX_ARTIFACT_BYTES,
    M0508_MAX_PACKAGE_BYTES,
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseDisposition,
    PtmLocalizationReleaseManifest,
    PtmLocalizationReleasePolicy,
    PtmLocalizationReleaseQuarantine,
    PtmLocalizationReleaseQuarantineCode,
    PtmLocalizationReleaseResult,
    PtmLocalizationReleaseSignature,
    PtmLocalizationReleaseVerification,
    PtmLocalizationSignatureVerificationReason,
    canonical_request_digest,
    manifest_digest,
    policy_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.canonical_ustar import (
    PackageAssemblyError,
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
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
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_ADAPTER: Final = TypeAdapter(BuildPtmLocalizationReleaseRequest)
_RESULT_ADAPTER: Final = TypeAdapter(PtmLocalizationReleaseResult)
_MANIFEST_ADAPTER: Final = TypeAdapter(PtmLocalizationReleaseManifest)
_POLICY_ADAPTER: Final = TypeAdapter(PtmLocalizationReleasePolicy)
_SIGNATURE_ADAPTER: Final = TypeAdapter(PtmLocalizationReleaseSignature)
_MANIFEST_PATH: Final = "manifest/reproducibility.json"
_SIGNATURE_PATH: Final = "manifest/signature.json"
_POLICY_PATH: Final = "manifest/policy.json"


class PtmLocalizationReleaseAuthorizationError(PermissionError):
    """Raised before an unauthorized request can traverse caller artifacts."""

    def __init__(self) -> None:
        super().__init__("M05-08 authorization controls are not satisfied")


class _BuiltReleaseInvariantError(ValueError):
    def __init__(self) -> None:
        super().__init__("release/package closure")


class PtmLocalizationReleaseInputError(ValueError):
    """Raised for malformed bytes or an incomplete release input set."""

    _MESSAGES: Final = {
        "artifact_paths": "artifact paths do not exactly match request",
        "artifact_type": "artifact bytes must be immutable bytes",
        "artifact_size": "artifact size does not match declaration",
        "artifact_limit": "artifact exceeds byte limit",
        "artifact_digest": "artifact digest does not match reference",
        "package_assembly": "package assembly failed",
        "package_limit": "package exceeds byte limit",
        "artifact_map": "artifact map is required",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


class PtmLocalizationSignatureVerifier(Protocol):
    """Narrow authenticity seam; M05-08 never owns private signing material."""

    @property
    def verifier_id(self) -> str: ...

    def verify(
        self,
        *,
        statement_digest: str,
        signature: PtmLocalizationReleaseSignature,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class BuiltPtmLocalizationRelease:
    """Typed outcome and package bytes only when the release is approved."""

    result: PtmLocalizationReleaseResult
    package_bytes: bytes | None

    def __post_init__(self) -> None:
        released = self.result.disposition.value == "released"
        if released != (self.package_bytes is not None):
            raise _BuiltReleaseInvariantError


def preflight_ptm_localization_release_authorization(request: object) -> None:
    """Apply shared control gates before touching arbitrary caller objects."""

    if not isinstance(request, BuildPtmLocalizationReleaseRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise PtmLocalizationReleaseAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise PtmLocalizationReleaseAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise PtmLocalizationReleaseAuthorizationError


def _control_decisions(
    request: BuildPtmLocalizationReleaseRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    records: list[ControlDecisionRecord] = []
    for role, decision in decisions:
        subject = (
            refs.identity_lineage.binding_digest
            if role is ControlRole.IDENTITY_LINEAGE
            else None
        )
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
                subject_digest=subject,
            )
        )
    return tuple(records)


def _provenance(
    request: BuildPtmLocalizationReleaseRequest,
    request_digest: str,
    manifest: PtmLocalizationReleaseManifest,
) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {
                request_digest,
                manifest_digest(manifest),
                *(item.reference.digest for item in request.artifacts),
                *manifest.stage_result_digests,
            }
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.context.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M05-08",
        module_version="0.1.0-provisional",
        generated_at=datetime.now(UTC),
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: BuildPtmLocalizationReleaseRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item.reference, role="evidence", claim="release input")
        for item in request.artifacts
    ) + tuple(
        EvidenceReference(reference=item, role="evidence", claim="reproducibility evidence")
        for item in request.manifest.reproducibility_evidence
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement="M05-08 field names, limits and package profile remain provisional.",
        ),
        Limitation(
            code="no_kinase_ownership",
            statement="The package does not infer or own kinase activity.",
        ),
    )


def _quarantine(
    code: PtmLocalizationReleaseQuarantineCode,
    reason: str,
) -> PtmLocalizationReleaseQuarantine:
    remediation = {
        PtmLocalizationReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE: (
            "resolve upstream support and quality controls"
        ),
        PtmLocalizationReleaseQuarantineCode.SIGNATURE_UNVERIFIED: (
            "provide an approved verifier and valid signature"
        ),
        PtmLocalizationReleaseQuarantineCode.PROVENANCE_INCOMPLETE: (
            "supply complete immutable provenance evidence"
        ),
    }[code]
    return PtmLocalizationReleaseQuarantine(
        code=code,
        reason=reason,
        remediation=remediation,
    )


def _result(  # noqa: PLR0913 - each closure field is independently auditable.
    request: BuildPtmLocalizationReleaseRequest,
    *,
    signature_verified: bool,
    signature_reason: PtmLocalizationSignatureVerificationReason,
    package_digest: str | None,
    package_member_count: int,
    quarantine_reasons: tuple[PtmLocalizationReleaseQuarantine, ...],
) -> PtmLocalizationReleaseResult:
    released = not quarantine_reasons
    req_digest = canonical_request_digest(request)
    payload: dict[str, object] = {
        "release_result_id": f"result.{request.manifest.release_id}",
        "request_digest": req_digest,
        "manifest_digest": manifest_digest(request.manifest),
        "disposition": (
            PtmLocalizationReleaseDisposition.RELEASED
            if released
            else PtmLocalizationReleaseDisposition.QUARANTINED
        ),
        "signature_verified": signature_verified,
        "signature_reason": signature_reason,
        "package_digest": package_digest,
        "package_member_count": package_member_count,
        "support": SupportDecision(
            status=request.manifest.support_status,
            reason_code="manifest_support_status",
            rationale="support status is caller-owned and was not inferred by M05-08",
        ),
        "provenance": _provenance(request, req_digest, request.manifest),
        "evidence": _evidence(request),
        "limitations": _limitations(),
        "quarantine_reasons": quarantine_reasons,
        "human_review_required": not released,
        "completed_at": datetime.now(UTC),
        "result_digest": "sha256:" + "0" * 64,
    }
    constructed = PtmLocalizationReleaseResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(constructed)
    return PtmLocalizationReleaseResult.model_validate(payload, strict=True)


def _artifact_members(
    request: BuildPtmLocalizationReleaseRequest,
    artifacts_by_path: Mapping[str, bytes],
) -> tuple[PackageMember, ...]:
    expected = {item.path for item in request.artifacts}
    actual = set(artifacts_by_path)
    if expected != actual:
        raise PtmLocalizationReleaseInputError("artifact_paths")
    members: list[PackageMember] = []
    for artifact in request.artifacts:
        content = artifacts_by_path[artifact.path]
        if type(content) is not bytes:
            raise PtmLocalizationReleaseInputError("artifact_type")
        if len(content) != artifact.declared_size:
            raise PtmLocalizationReleaseInputError("artifact_size")
        if len(content) > M0508_MAX_ARTIFACT_BYTES:
            raise PtmLocalizationReleaseInputError("artifact_limit")
        if sha256_bytes(content) != artifact.reference.digest:
            raise PtmLocalizationReleaseInputError("artifact_digest")
        members.append(PackageMember(path=artifact.path, content=content))
    return tuple(members)


def _package_members(
    request: BuildPtmLocalizationReleaseRequest,
    artifacts_by_path: Mapping[str, bytes],
) -> tuple[PackageMember, ...]:
    artifact_members = _artifact_members(request, artifacts_by_path)
    manifest_bytes = canonical_json_bytes(request.manifest.model_dump(mode="json"))
    signature_bytes = canonical_json_bytes(request.signature.model_dump(mode="json"))
    policy_bytes = canonical_json_bytes(request.policy.model_dump(mode="json"))
    return (
        *artifact_members,
        PackageMember(_MANIFEST_PATH, manifest_bytes),
        PackageMember(_SIGNATURE_PATH, signature_bytes),
        PackageMember(_POLICY_PATH, policy_bytes),
    )


class M0508PtmLocalizationReleaseEngine:
    """Build, inspect and verify one immutable package without persistence."""

    __slots__ = ("_verifier",)

    def __init__(self, verifier: PtmLocalizationSignatureVerifier | None = None) -> None:
        self._verifier = verifier

    @staticmethod
    def validate_request(request: object) -> BuildPtmLocalizationReleaseRequest:
        preflight_ptm_localization_release_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    @staticmethod
    def manifest(request: object) -> PtmLocalizationReleaseManifest:
        return M0508PtmLocalizationReleaseEngine.validate_request(request).manifest

    @staticmethod
    def request_digest(request: object) -> str:
        return canonical_request_digest(M0508PtmLocalizationReleaseEngine.validate_request(request))

    @staticmethod
    def manifest_digest(request: object) -> str:
        return manifest_digest(M0508PtmLocalizationReleaseEngine.manifest(request))

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, bytes],
    ) -> BuiltPtmLocalizationRelease:
        typed = self.validate_request(request)
        members = _package_members(typed, artifacts_by_path)
        quarantine: list[PtmLocalizationReleaseQuarantine] = []
        if typed.manifest.support_status is not SupportStatus.SUPPORTED:
            quarantine.append(
                _quarantine(
                    PtmLocalizationReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
                    "caller-declared support status is not supported",
                )
            )
        statement = signing_statement_digest(
            active_manifest_digest=manifest_digest(typed.manifest),
            active_policy_digest=policy_digest(typed.policy),
            release_id=typed.manifest.release_id,
            release_version=typed.manifest.release_version,
        )
        verified = False
        reason = PtmLocalizationSignatureVerificationReason.VERIFIER_UNAVAILABLE
        if self._verifier is not None:
            if self._verifier.verifier_id not in typed.policy.allowed_verifier_ids:
                reason = PtmLocalizationSignatureVerificationReason.VERIFIER_REJECTED
            else:
                try:
                    verified = self._verifier.verify(
                        statement_digest=statement,
                        signature=typed.signature,
                    ) is True
                except Exception:  # noqa: BLE001 - verifier failure is a quarantine path.
                    verified = False
                    reason = PtmLocalizationSignatureVerificationReason.VERIFIER_REJECTED
                else:
                    reason = (
                        PtmLocalizationSignatureVerificationReason.VERIFIED
                        if verified
                        else PtmLocalizationSignatureVerificationReason.VERIFIER_REJECTED
                    )
        if not verified:
            quarantine.append(
                _quarantine(
                    PtmLocalizationReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
                    reason.value,
                )
            )
        package_bytes: bytes | None = None
        package_digest: str | None = None
        package_member_count = 0
        if not quarantine:
            try:
                package_bytes = build_canonical_ustar(members)
            except PackageAssemblyError as error:
                    raise PtmLocalizationReleaseInputError("package_assembly") from error
            if len(package_bytes) > M0508_MAX_PACKAGE_BYTES:
                raise PtmLocalizationReleaseInputError("package_limit")
            package_digest = sha256_bytes(package_bytes)
            package_member_count = len(members)
        result = _result(
            typed,
            signature_verified=verified,
            signature_reason=reason,
            package_digest=package_digest,
            package_member_count=package_member_count,
            quarantine_reasons=tuple(quarantine),
        )
        return BuiltPtmLocalizationRelease(result=result, package_bytes=package_bytes)

    def verify(self, result: object, package_bytes: bytes) -> PtmLocalizationReleaseVerification:
        typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        if typed.package_digest is None or typed.disposition.value != "released":
            return PtmLocalizationReleaseVerification(
                content_verified=False,
                authenticity_verified=False,
                verified=False,
                reason=PtmLocalizationSignatureVerificationReason.NOT_ATTEMPTED,
            )
        if type(package_bytes) is not bytes or len(package_bytes) > M0508_MAX_PACKAGE_BYTES:
            return PtmLocalizationReleaseVerification(
                content_verified=False,
                authenticity_verified=False,
                verified=False,
                reason=PtmLocalizationSignatureVerificationReason.MANIFEST_MISMATCH,
            )
        try:
            members = inspect_canonical_ustar(package_bytes)
        except PackageAssemblyError:
            return PtmLocalizationReleaseVerification(
                content_verified=False,
                authenticity_verified=False,
                verified=False,
                reason=PtmLocalizationSignatureVerificationReason.MANIFEST_MISMATCH,
            )
        content_verified = sha256_bytes(package_bytes) == typed.package_digest
        paths = {item.path for item in members}
        if (
            len(paths) != len(members)
            or _MANIFEST_PATH not in paths
            or _SIGNATURE_PATH not in paths
            or _POLICY_PATH not in paths
        ):
            content_verified = False
        policy: PtmLocalizationReleasePolicy | None = None
        signature: PtmLocalizationReleaseSignature | None = None
        parsed: PtmLocalizationReleaseManifest | None = None
        try:
            manifest_member = next(item for item in members if item.path == _MANIFEST_PATH)
            strict_json_loads(manifest_member.content)
            parsed = _MANIFEST_ADAPTER.validate_json(manifest_member.content, strict=True)
            content_verified = content_verified and manifest_digest(parsed) == typed.manifest_digest
            signature_member = next(item for item in members if item.path == _SIGNATURE_PATH)
            strict_json_loads(signature_member.content)
            signature = _SIGNATURE_ADAPTER.validate_json(signature_member.content, strict=True)
            content_verified = (
                content_verified
                and signature.claimed_manifest_digest == typed.manifest_digest
            )
            policy_member = next(item for item in members if item.path == _POLICY_PATH)
            strict_json_loads(policy_member.content)
            policy = _POLICY_ADAPTER.validate_json(policy_member.content, strict=True)
        except (StopIteration, StrictJsonError, ValueError, TypeError):
            content_verified = False
        authenticity_verified = False
        reason = PtmLocalizationSignatureVerificationReason.VERIFIER_UNAVAILABLE
        if content_verified and self._verifier is not None:
            if policy is None or signature is None or parsed is None:
                content_verified = False
                reason = PtmLocalizationSignatureVerificationReason.MANIFEST_MISMATCH
            else:
                statement = signing_statement_digest(
                    active_manifest_digest=typed.manifest_digest,
                    active_policy_digest=policy_digest(policy),
                    release_id=parsed.release_id,
                    release_version=parsed.release_version,
                )
                try:
                    authenticity_verified = (
                        self._verifier.verifier_id in policy.allowed_verifier_ids
                        and self._verifier.verify(
                            statement_digest=statement,
                            signature=signature,
                        )
                        is True
                    )
                except Exception:  # noqa: BLE001 - verifier failure is a safe failure.
                    authenticity_verified = False
                reason = (
                    PtmLocalizationSignatureVerificationReason.VERIFIED
                    if authenticity_verified
                    else PtmLocalizationSignatureVerificationReason.VERIFIER_REJECTED
                )
        elif not content_verified:
            reason = PtmLocalizationSignatureVerificationReason.MANIFEST_MISMATCH
        return PtmLocalizationReleaseVerification(
            content_verified=content_verified,
            authenticity_verified=authenticity_verified,
            verified=content_verified and authenticity_verified,
            package_digest=typed.package_digest if content_verified else None,
            reason=reason,
        )

    def execute(
        self,
        request: object,
        artifacts_by_path: Mapping[str, bytes] | None = None,
    ) -> BuiltPtmLocalizationRelease:
        """Build with an explicit artifact map; an omitted map fails closed."""

        if artifacts_by_path is None:
            raise PtmLocalizationReleaseInputError("artifact_map")
        return self.build(request, artifacts_by_path)


def build_ptm_localization_release_manifest(request: object) -> PtmLocalizationReleaseManifest:
    return M0508PtmLocalizationReleaseEngine.manifest(request)


__all__ = [
    "BuiltPtmLocalizationRelease",
    "M0508PtmLocalizationReleaseEngine",
    "PtmLocalizationReleaseAuthorizationError",
    "PtmLocalizationReleaseInputError",
    "PtmLocalizationSignatureVerifier",
    "build_ptm_localization_release_manifest",
    "preflight_ptm_localization_release_authorization",
]
