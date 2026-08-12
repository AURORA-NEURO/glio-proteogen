"""Contract-facing deterministic release packager for M01-08."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_08 import (
    BuildReleasePackageRequest,
    PackageVerification,
    ReleaseDisposition,
    ReleasePackageDescriptor,
    ReleasePackagingResult,
    ReproducibilityManifest,
    canonical_request_digest,
    configuration_digest,
    manifest_digest,
    policy_digest,
)
from glio_proteogen.contracts.m01_08.v1 import (
    M0108_AUTHORITY_LIMITATION_CODE,
    M0108_CONTRACT_VERSION,
    M0108_MODULE_ID,
    M0108_PACKAGE_LIMITATION_CODE,
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
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging.kernel import (
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)

_REQUEST_ADAPTER: Final[TypeAdapter[BuildReleasePackageRequest]] = TypeAdapter(
    BuildReleasePackageRequest
)
_LIMITATIONS: Final = (
    Limitation(
        code=M0108_PACKAGE_LIMITATION_CODE,
        statement=(
            "This result establishes deterministic byte packaging only; it does not validate "
            "scientific results or qualify a supply chain."
        ),
    ),
    Limitation(
        code=M0108_AUTHORITY_LIMITATION_CODE,
        statement=(
            "The external signature receipt is digest-bound but its signer, key, and authority "
            "are not authenticated by M01-08."
        ),
    ),
)


class ReleasePackagingAuthorizationError(ValueError):
    """Authorization failed before artifact mappings or bytes were accessed."""

    def __init__(self) -> None:
        super().__init__("release packaging requires accepted upstream authorization states")


class ReleasePackagingInputError(ValueError):
    """Artifact mapping closure, size, or digest contradicts its declaration."""

    @classmethod
    def set_mismatch(cls) -> ReleasePackagingInputError:
        return cls("artifact byte mapping must close exactly")

    @classmethod
    def invalid_content(cls) -> ReleasePackagingInputError:
        return cls("artifact content must be immutable bytes")

    @classmethod
    def size_mismatch(cls) -> ReleasePackagingInputError:
        return cls("artifact byte size contradicts its declaration")

    @classmethod
    def digest_mismatch(cls) -> ReleasePackagingInputError:
        return cls("artifact digest contradicts its declaration")


@dataclass(frozen=True, slots=True)
class BuiltReleasePackage:
    """Typed metadata result plus separately controlled canonical archive bytes."""

    result: ReleasePackagingResult
    package_bytes: bytes


class M0108ReleasePackager:
    """Build and verify canonical USTAR packages without persistence or signing."""

    __slots__ = ()

    def build(  # noqa: C901 - one linear validation/build decision pipeline.
        self,
        request: BuildReleasePackageRequest,
        files: Mapping[str, bytes],
    ) -> BuiltReleasePackage:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_release_packaging_authorization(validated)
        expected_paths = {item.path for item in validated.artifacts}
        if not isinstance(files, Mapping) or set(files) != expected_paths:
            raise ReleasePackagingInputError.set_mismatch()

        members: list[PackageMember] = []
        for artifact in sorted(validated.artifacts, key=lambda item: item.path):
            content = files[artifact.path]
            if not isinstance(content, bytes):
                raise ReleasePackagingInputError.invalid_content()
            if len(content) != artifact.byte_size:
                raise ReleasePackagingInputError.size_mismatch()
            if sha256_bytes(content) != artifact.source.digest:
                raise ReleasePackagingInputError.digest_mismatch()
            members.append(PackageMember(artifact.path, content))

        manifest = _manifest(validated)
        manifest_hash = manifest_digest(manifest)
        package_bytes = build_canonical_ustar(
            tuple(members),
            fixed_mtime=validated.policy.fixed_mtime,
            file_mode=validated.policy.file_mode,
        )
        package = ReleasePackageDescriptor(
            byte_size=len(package_bytes),
            digest=sha256_bytes(package_bytes),
            artifact_count=len(members),
        )
        receipt = validated.signature_receipt
        reason: str | None = None
        if any(item.state.value != "accepted" for item in validated.decisions):
            reason = "upstream_decision_not_accepted"
        elif receipt is None:
            reason = "signature_receipt_missing"
        elif receipt.algorithm not in validated.policy.allowed_signature_algorithms:
            reason = "signature_algorithm_not_allowed"
        elif receipt.package_digest != package.digest or receipt.manifest_digest != manifest_hash:
            reason = "signature_receipt_mismatch"
        disposition = (
            ReleaseDisposition.RELEASED if reason is None else ReleaseDisposition.QUARANTINED
        )
        request_hash = canonical_request_digest(validated)
        policy_hash = policy_digest(validated.policy)
        result = ReleasePackagingResult(
            packaging_id=f"packaging.m0108.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            policy_digest=policy_hash,
            disposition=disposition,
            package=package,
            manifest=manifest,
            manifest_digest=manifest_hash,
            signature_receipt=receipt,
            quarantine_reason=reason,
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(validated, request_hash, policy_hash),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is ReleaseDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )
        if not self.verify(result, package_bytes).verified:
            raise ReleasePackagingInputError.invalid_content()
        return BuiltReleasePackage(result=result, package_bytes=package_bytes)

    def verify(
        self,
        result: ReleasePackagingResult,
        package_bytes: bytes,
    ) -> PackageVerification:
        package_hash = sha256_bytes(package_bytes)
        if package_hash != result.package.digest or len(package_bytes) != result.package.byte_size:
            return _verification(result, package_hash, 0, "package_digest_mismatch")
        try:
            members = inspect_canonical_ustar(package_bytes)
        except ValueError:
            return _verification(result, package_hash, 0, "package_archive_invalid")
        expected = {item.path: item for item in result.manifest.artifacts}
        if {item.path for item in members} != set(expected):
            return _verification(result, package_hash, len(members), "artifact_path_mismatch")
        for member in members:
            declared = expected[member.path]
            if (
                len(member.content) != declared.byte_size
                or sha256_bytes(member.content) != declared.source.digest
            ):
                return _verification(result, package_hash, len(members), "artifact_digest_mismatch")
        rebuilt = build_canonical_ustar(
            members,
            fixed_mtime=result.manifest.fixed_mtime,
            file_mode=result.manifest.file_mode,
        )
        if rebuilt != package_bytes:
            return _verification(result, package_hash, len(members), "package_not_canonical")
        verified = (
            manifest_digest(result.manifest) == result.manifest_digest
            and len(members) == result.package.artifact_count
        )
        return _verification(
            result,
            package_hash,
            len(members),
            None if verified else "manifest_mismatch",
        )


def build_release_package(
    request: BuildReleasePackageRequest,
    files: Mapping[str, bytes],
) -> BuiltReleasePackage:
    return M0108ReleasePackager().build(request, files)


def verify_release_package(
    result: ReleasePackagingResult,
    package_bytes: bytes,
) -> PackageVerification:
    return M0108ReleasePackager().verify(result, package_bytes)


def preflight_release_packaging_authorization(candidate: object) -> None:
    context = candidate.context if isinstance(candidate, BuildReleasePackageRequest) else (
        candidate.get("context") if isinstance(candidate, Mapping) else None
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
    if any(_value(_value(references, role), "state") != state for role, state in expected.items()):
        raise ReleasePackagingAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _manifest(request: BuildReleasePackageRequest) -> ReproducibilityManifest:
    return ReproducibilityManifest(
        release_id=request.release_id,
        release_version=request.release_version,
        artifacts=tuple(sorted(request.artifacts, key=lambda item: item.path)),
        software_versions=tuple(
            sorted(request.software_versions, key=lambda item: item.software_id)
        ),
        reference_versions=tuple(
            sorted(request.reference_versions, key=lambda item: item.reference_id)
        ),
        transformations=tuple(
            sorted(request.transformations, key=lambda item: (item.ordinal, item.step_id))
        ),
        decisions=tuple(sorted(request.decisions, key=lambda item: item.kind.value)),
        numerical_tolerances=tuple(
            sorted(request.numerical_tolerances, key=lambda item: item.tolerance_id)
        ),
        policy_digest=policy_digest(request.policy),
        archive_format=request.policy.archive_format,
        fixed_mtime=request.policy.fixed_mtime,
        file_mode=request.policy.file_mode,
    )


def _verification(
    result: ReleasePackagingResult,
    package_hash: str,
    artifact_count: int,
    reason: str | None,
) -> PackageVerification:
    return PackageVerification(
        verified=reason is None,
        package_digest=package_hash,
        manifest_digest=result.manifest_digest,
        artifact_count=artifact_count,
        reason_code=reason,
    )


def _support(disposition: ReleaseDisposition) -> SupportDecision:
    if disposition is ReleaseDisposition.RELEASED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="package_released",
            rationale="Artifact bytes and declared manifests are deterministic and receipt-bound.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="package_quarantined",
        rationale="The package requires an externally governed signature receipt review.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("Packaging does not estimate measurement uncertainty."),
        sampling=_not_estimable("Packaging does not estimate sampling uncertainty."),
        parameter=_not_estimable("The deterministic packager fits no parameters."),
        model_form=_not_estimable("No learned model is used."),
        identification=_not_estimable("Declared digests bind bytes; authorship is not inferred."),
        support=_not_estimable("Receipt binding is a deterministic state."),
        transport=_not_estimable("External supply-chain trust is not assessed."),
    )


def _controls(request: BuildReleasePackageRequest) -> tuple[ControlDecisionRecord, ...]:
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
    request: BuildReleasePackageRequest,
    request_hash: str,
    policy_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m0108.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0108_MODULE_ID,
        module_version=M0108_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    policy_hash,
                    *(item.source.digest for item in request.artifacts),
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_digest(request.policy),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(request: BuildReleasePackageRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: tuple[ArtifactReference, ...] = (
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
        *(item.source for item in request.artifacts),
        *(item.evidence for item in request.software_versions),
        *(item.evidence for item in request.reference_versions),
        *(item.evidence for item in request.transformations),
        *(item.evidence for item in request.decisions),
        *((request.signature_receipt.evidence,) if request.signature_receipt else ()),
    )
    return tuple(
        EvidenceReference(
            reference=item,
            role="evidence",
            claim="Caller-declared content-addressed release-packaging evidence.",
        )
        for item in sorted(set(artifacts), key=canonical_json_bytes)
    )


__all__ = [
    "BuiltReleasePackage",
    "M0108ReleasePackager",
    "ReleasePackagingAuthorizationError",
    "ReleasePackagingInputError",
    "build_release_package",
    "preflight_release_packaging_authorization",
    "verify_release_package",
]
