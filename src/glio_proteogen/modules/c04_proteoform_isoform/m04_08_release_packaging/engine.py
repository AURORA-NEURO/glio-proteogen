"""ABI-independent M04-08 release-engine boundary.

The executable adapter remains deliberately sealed until M04-07 publishes its final public
contract. This module fixes the binary API shape without accepting guessed upstream objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from glio_proteogen.contracts.m04_08 import (
    ExternalProteoformSignature,
    M0408DependencyUnavailableError,
    ProteoformReleaseDisposition,
    ProteoformReleaseResult,
    ProteoformReleaseVerification,
    ProteoformReproducibilityManifest,
    ProteoformSignatureVerification,
    ProteoformSignatureVerificationReason,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class _BuiltReleaseInvariantError(ValueError):
    """A release disposition contradicted package-byte presence."""


class ProteoformSignatureVerifier(Protocol):
    """Narrow external authenticity boundary; M04-08 owns only the receipt."""

    @property
    def verifier_id(self) -> str: ...

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalProteoformSignature,
    ) -> object: ...


def _verification_receipt(
    signature: ExternalProteoformSignature,
    statement_digest: str,
    reason: ProteoformSignatureVerificationReason,
    *,
    verifier_id: str | None = None,
) -> ProteoformSignatureVerification:
    return ProteoformSignatureVerification(
        verifier_id=verifier_id,
        algorithm=signature.algorithm,
        key_id=signature.key_id,
        statement_digest=statement_digest,
        verified=reason is ProteoformSignatureVerificationReason.VERIFIED,
        reason_code=reason,
    )


def _safe_verifier_id(verifier: ProteoformSignatureVerifier | None) -> str | None:
    if verifier is None:
        return None
    try:
        value = verifier.verifier_id
    except Exception:  # noqa: BLE001 - fail closed across the injected verifier.
        return None
    return value if type(value) is str else None


def _verify_external_signature(  # noqa: PLR0911 - ordered fail-closed precedence.
    *,
    signature: ExternalProteoformSignature,
    statement_digest: str,
    allowed_verifier_ids: tuple[str, ...],
    chain_releasable: bool,
    verifier: ProteoformSignatureVerifier | None,
) -> ProteoformSignatureVerification:
    """Fail closed at the external verifier boundary without interpreting stage content."""

    if type(allowed_verifier_ids) is not tuple or any(
        type(item) is not str for item in allowed_verifier_ids
    ):
        return _verification_receipt(
            signature,
            statement_digest,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(chain_releasable) is not bool or not chain_releasable:
        return _verification_receipt(
            signature,
            statement_digest,
            ProteoformSignatureVerificationReason.NOT_ATTEMPTED,
        )
    if signature.claimed_statement_digest != statement_digest:
        return _verification_receipt(
            signature,
            statement_digest,
            ProteoformSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    verifier_id = _safe_verifier_id(verifier)
    if verifier is None or verifier_id not in allowed_verifier_ids:
        return _verification_receipt(
            signature,
            statement_digest,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    try:
        accepted = verifier.verify(
            statement_digest=statement_digest,
            signature=signature,
        )
    except Exception:  # noqa: BLE001 - fail closed across the injected verifier.
        return _verification_receipt(
            signature,
            statement_digest,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    if type(accepted) is not bool:
        return _verification_receipt(
            signature,
            statement_digest,
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        )
    return _verification_receipt(
        signature,
        statement_digest,
        (
            ProteoformSignatureVerificationReason.VERIFIED
            if accepted
            else ProteoformSignatureVerificationReason.VERIFIER_REJECTED
        ),
        verifier_id=verifier_id,
    )


@dataclass(frozen=True, slots=True)
class BuiltProteoformRelease:
    """Typed release outcome plus bytes only for a released package."""

    result: ProteoformReleaseResult
    package_bytes: bytes | None

    def __post_init__(self) -> None:
        released = self.result.disposition is ProteoformReleaseDisposition.RELEASED
        if released != (self.package_bytes is not None):
            raise _BuiltReleaseInvariantError


def _dependency_unavailable() -> M0408DependencyUnavailableError:
    return M0408DependencyUnavailableError(
        "M04-08 runtime is sealed until the exact frozen M04-07 result adapter is installed"
    )


class M0408ProteoformReleaseEngine:
    """Frozen runtime facade whose implementation awaits the genuine M04-07 adapter."""

    __slots__ = ("_verifier",)

    def __init__(self, verifier: ProteoformSignatureVerifier | None = None) -> None:
        self._verifier = verifier

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltProteoformRelease:
        del request, artifacts_by_path, stage_results_by_module
        raise _dependency_unavailable()

    def build_manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> ProteoformReproducibilityManifest:
        del request, artifacts_by_path, stage_results_by_module
        raise _dependency_unavailable()

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> ProteoformReleaseVerification:
        del result, package_bytes
        raise _dependency_unavailable()


def build_proteoform_release(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
    verifier: ProteoformSignatureVerifier | None = None,
) -> BuiltProteoformRelease:
    """Build a release after the final M04-07 adapter is installed."""

    return M0408ProteoformReleaseEngine(verifier).build(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def build_proteoform_release_manifest(
    request: object,
    artifacts_by_path: Mapping[str, object],
    stage_results_by_module: Mapping[str, object],
) -> ProteoformReproducibilityManifest:
    """Prepare the deterministic unsigned manifest after dependency freeze."""

    return M0408ProteoformReleaseEngine().build_manifest(
        request,
        artifacts_by_path,
        stage_results_by_module,
    )


def verify_proteoform_release(
    result: object,
    package_bytes: bytes,
    verifier: ProteoformSignatureVerifier | None = None,
) -> ProteoformReleaseVerification:
    """Verify package content and injected authenticity after dependency freeze."""

    return M0408ProteoformReleaseEngine(verifier).verify(result, package_bytes)


__all__ = [
    "BuiltProteoformRelease",
    "M0408ProteoformReleaseEngine",
    "ProteoformSignatureVerifier",
    "build_proteoform_release",
    "build_proteoform_release_manifest",
    "verify_proteoform_release",
]
