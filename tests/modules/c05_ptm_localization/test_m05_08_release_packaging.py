"""Lifecycle, replay and safe-failure tests for the M05-08 runtime."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from glio_proteogen.contracts.m05_08 import (
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseDisposition,
    PtmLocalizationReleaseResult,
    PtmLocalizationReleaseVerification,
    PtmLocalizationSignatureVerificationReason,
    manifest_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.canonical_ustar import inspect_canonical_ustar, sha256_bytes
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging import (
    M0508Plugin,
    M0508PtmLocalizationReleaseEngine,
    M0508Service,
    PtmLocalizationReleaseAuthorizationError,
    PtmLocalizationReleaseInputError,
    PtmLocalizationReleaseSubmission,
    ValidatedM0508Request,
)
from tests.contract.test_m05_08_provisional import _request

_PACKAGE_MEMBER_COUNT = 4
_EXPECTED_VERIFIER_CALLS = 2


@dataclass
class _Verifier:
    verifier_id: str = "verifier.m0508.smoke"
    answer: bool = True

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    def verify(self, *, statement_digest: str, signature: object) -> bool:  # noqa: ARG002
        self.calls.append(statement_digest)
        return self.answer


def _valid_fixture() -> tuple[BuildPtmLocalizationReleaseRequest, dict[str, bytes]]:
    source = _request()
    content = b"variant-peptide-fixture"
    digest = sha256_bytes(content)
    artifact = source.artifacts[0].model_copy(
        update={
            "reference": source.artifacts[0].reference.model_copy(update={"digest": digest}),
            "declared_size": len(content),
        }
    )
    manifest = source.manifest.model_copy(update={"artifact_digests": (digest,)})
    signature = source.signature.model_copy(
        update={"claimed_manifest_digest": manifest_digest(manifest)}
    )
    payload = source.model_dump(mode="python")
    payload.update(artifacts=(artifact,), manifest=manifest, signature=signature)
    return BuildPtmLocalizationReleaseRequest.model_validate(payload, strict=True), {
        artifact.path: content
    }


def test_missing_verifier_quarantines_without_package_bytes() -> None:
    request, artifacts = _valid_fixture()
    built = M0508PtmLocalizationReleaseEngine().build(request, artifacts)

    assert built.package_bytes is None
    assert built.result.disposition is PtmLocalizationReleaseDisposition.QUARANTINED
    assert built.result.signature_verified is False
    assert built.result.signature_reason.value == "verifier_unavailable"
    assert built.result.quarantine_reasons


def test_approved_verifier_builds_canonical_package() -> None:
    request, artifacts = _valid_fixture()
    verifier = _Verifier()
    built = M0508PtmLocalizationReleaseEngine(verifier).build(request, artifacts)

    assert built.package_bytes is not None
    assert built.result.disposition is PtmLocalizationReleaseDisposition.RELEASED
    assert built.result.package_digest == sha256_bytes(built.package_bytes)
    assert built.result.package_member_count == _PACKAGE_MEMBER_COUNT
    assert len(verifier.calls) == 1
    assert [member.path for member in inspect_canonical_ustar(built.package_bytes)] == [
        "manifest/policy.json",
        "manifest/reproducibility.json",
        "manifest/signature.json",
        "parent/variant-peptide.json",
    ]


def test_package_replays_with_content_and_authenticity() -> None:
    request, artifacts = _valid_fixture()
    verifier = _Verifier()
    engine = M0508PtmLocalizationReleaseEngine(verifier)
    built = engine.build(request, artifacts)
    assert built.package_bytes is not None

    verification = engine.verify(built.result, built.package_bytes)

    assert verification == PtmLocalizationReleaseVerification(
        content_verified=True,
        authenticity_verified=True,
        verified=True,
        package_digest=built.result.package_digest,
        reason=PtmLocalizationSignatureVerificationReason.VERIFIED,
    )
    assert len(verifier.calls) == _EXPECTED_VERIFIER_CALLS


def test_package_tamper_is_reported_as_manifest_mismatch() -> None:
    request, artifacts = _valid_fixture()
    engine = M0508PtmLocalizationReleaseEngine(_Verifier())
    built = engine.build(request, artifacts)
    assert built.package_bytes is not None

    tampered = built.package_bytes[:-1] + bytes([built.package_bytes[-1] ^ 1])
    verification = engine.verify(built.result, tampered)

    assert verification.verified is False
    assert verification.content_verified is False
    assert verification.reason.value == "manifest_mismatch"


@pytest.mark.parametrize(
    ("name", "mapping", "message"),
    [
        ("missing", {}, "paths"),
        ("mutable", {"parent/variant-peptide.json": bytearray(b"x")}, "immutable"),
        ("size", {"parent/variant-peptide.json": b"x"}, "size"),
        ("digest", {"parent/variant-peptide.json": b"Xariant-peptide-fixture"}, "digest"),
    ],
)
def test_artifact_boundary_rejects_malformed_inputs(
    name: str,
    mapping: dict[str, object],
    message: str,
) -> None:
    del name
    request, _ = _valid_fixture()
    with pytest.raises(PtmLocalizationReleaseInputError, match=message):
        M0508PtmLocalizationReleaseEngine(_Verifier()).build(request, mapping)  # type: ignore[arg-type]


def test_unapproved_verifier_is_not_called() -> None:
    request, artifacts = _valid_fixture()
    verifier = _Verifier(verifier_id="verifier.not-allowed")

    built = M0508PtmLocalizationReleaseEngine(verifier).build(request, artifacts)

    assert built.result.disposition is PtmLocalizationReleaseDisposition.QUARANTINED
    assert verifier.calls == []
    assert built.package_bytes is None


def test_verifier_exception_fails_closed() -> None:
    class ExplodingVerifier(_Verifier):
        def verify(self, *, statement_digest: str, signature: object) -> bool:  # noqa: ARG002
            raise RuntimeError

    request, artifacts = _valid_fixture()
    built = M0508PtmLocalizationReleaseEngine(ExplodingVerifier()).build(request, artifacts)

    assert built.result.disposition is PtmLocalizationReleaseDisposition.QUARANTINED
    assert built.result.signature_reason.value == "verifier_rejected"
    assert built.package_bytes is None


def test_limited_support_quarantines_even_with_valid_signature() -> None:
    request, artifacts = _valid_fixture()
    manifest = request.manifest.model_copy(update={"support_status": SupportStatus.LIMITED})
    signature = request.signature.model_copy(
        update={"claimed_manifest_digest": manifest_digest(manifest)}
    )
    payload = request.model_dump(mode="python")
    payload.update(manifest=manifest, signature=signature)
    limited = BuildPtmLocalizationReleaseRequest.model_validate(payload, strict=True)

    built = M0508PtmLocalizationReleaseEngine(_Verifier()).build(limited, artifacts)

    assert built.result.disposition is PtmLocalizationReleaseDisposition.QUARANTINED
    assert any(
        item.code.value == "upstream_not_releasable"
        for item in built.result.quarantine_reasons
    )


def test_service_and_engine_return_same_manifest_and_package() -> None:
    request, artifacts = _valid_fixture()
    verifier = _Verifier()
    service = M0508Service(verifier=verifier)
    built = service.build(request, artifacts)

    assert service.manifest(request) == request.manifest
    assert built.result.request_digest == M0508PtmLocalizationReleaseEngine.request_digest(
        request
    )


def test_plugin_parse_once_and_run_token() -> None:
    request, artifacts = _valid_fixture()
    verifier = _Verifier()
    plugin = M0508Plugin(M0508Service(verifier=verifier))
    submission = PtmLocalizationReleaseSubmission(
        request=canonical_json_bytes(request.model_dump(mode="json")),
        artifacts_by_path=artifacts,
    )

    validated = plugin.validate(submission)
    built = plugin.run(validated)

    assert isinstance(validated, ValidatedM0508Request)
    assert validated.request == request
    assert built.result.disposition is PtmLocalizationReleaseDisposition.RELEASED


def test_plugin_rejects_unvalidated_execution_token() -> None:
    plugin = M0508Plugin()
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_rejects_duplicate_json_keys_before_validation() -> None:
    plugin = M0508Plugin()
    duplicate = b'{"context": {}, "context": {}}'
    submission = PtmLocalizationReleaseSubmission(duplicate, {})
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        plugin.validate(submission)


def test_engine_requires_explicit_artifact_map() -> None:
    request, _ = _valid_fixture()
    with pytest.raises(PtmLocalizationReleaseInputError, match="artifact map"):
        M0508PtmLocalizationReleaseEngine().execute(request)


def test_result_round_trips_strictly_after_package_build() -> None:
    request, artifacts = _valid_fixture()
    built = M0508PtmLocalizationReleaseEngine(_Verifier()).build(request, artifacts)
    encoded = canonical_json_bytes(built.result.model_dump(mode="json"))

    assert PtmLocalizationReleaseResult.model_validate_json(encoded, strict=True) == built.result


def test_authorization_denies_withheld_consent() -> None:
    request, _artifacts = _valid_fixture()
    refs = request.context.references
    consent = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    context = request.context.model_copy(
        update={"references": refs.model_copy(update={"consent": consent})}
    )
    payload = request.model_dump(mode="python")
    payload["context"] = context.model_dump(mode="python")
    denied = BuildPtmLocalizationReleaseRequest.model_validate(payload, strict=True)

    with pytest.raises(PtmLocalizationReleaseAuthorizationError):
        M0508PtmLocalizationReleaseEngine().validate_request(denied)
