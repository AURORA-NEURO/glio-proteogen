"""Representative qualification for the public M01-08 packager."""

from __future__ import annotations

import io
import tarfile
from typing import TYPE_CHECKING, cast

import pytest
from evals.m01_08.run import build_scenario
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_08 import (
    BuildReleasePackageRequest,
    DecisionState,
    ReleaseDisposition,
    ReleasePackagingResult,
)
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging import (
    M0108Plugin,
    M0108ReleasePackager,
    M0108Service,
    PackageMember,
    ReleasePackagingAuthorizationError,
    ReleasePackagingInputError,
    ReleasePackagingSubmission,
    ValidatedM0108Request,
    build_canonical_ustar,
    build_release_package,
    inspect_canonical_ustar,
    sha256_bytes,
    verify_release_package,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def test_canonical_package_replays_and_verifies() -> None:
    request, files = build_scenario("canonical")

    built = build_release_package(request, files)
    replay = M0108ReleasePackager().build(request, dict(reversed(tuple(files.items()))))

    assert built == replay
    assert built.result.disposition is ReleaseDisposition.RELEASED
    assert verify_release_package(built.result, built.package_bytes).verified


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("missing_receipt", "signature_receipt_missing"),
        ("mismatched_receipt", "signature_receipt_mismatch"),
    ],
)
def test_external_receipt_failure_quarantines(case: str, reason: str) -> None:
    request, files = build_scenario(case)

    built = M0108Service().execute(request, files)

    assert built.result.disposition is ReleaseDisposition.QUARANTINED
    assert built.result.quarantine_reason == reason
    assert built.result.human_review_required


def test_tampered_bytes_reject() -> None:
    request, files = build_scenario("tampered_byte")

    with pytest.raises(ReleasePackagingInputError, match="byte size"):
        build_release_package(request, files)


def test_authorization_rejects_before_file_mapping_access() -> None:
    request, _ = build_scenario("canonical")
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"

    class UnreadableFiles(dict[str, bytes]):
        def __iter__(self) -> Iterator[str]:
            raise AssertionError

    with pytest.raises(ReleasePackagingAuthorizationError):
        M0108Service().execute(payload, UnreadableFiles())


def test_verifier_detects_tampered_package() -> None:
    request, files = build_scenario("canonical")
    built = build_release_package(request, files)

    verification = verify_release_package(
        built.result,
        built.package_bytes[:-1] + bytes([built.package_bytes[-1] ^ 1]),
    )

    assert not verification.verified
    assert verification.reason_code == "package_digest_mismatch"


@pytest.mark.parametrize(
    "path",
    ["control\x00.txt", "m\u00e9tadata/run.json", f"{'a' * 101}.txt"],
)
def test_nonportable_ustar_paths_reject(path: str) -> None:
    request, _ = build_scenario("canonical")
    payload = request.model_dump(mode="python")
    payload["artifacts"][0]["path"] = path

    with pytest.raises(ValidationError):
        TypeAdapter(BuildReleasePackageRequest).validate_python(payload, strict=True)


@pytest.mark.parametrize("wire_kind", ["text", "bytes", "bytearray"])
def test_plugin_accepts_strict_raw_json_and_runs(wire_kind: str) -> None:
    request, files = build_scenario("canonical")
    raw: str | bytes | bytearray = request.model_dump_json()
    if wire_kind != "text":
        encoded = raw.encode() if isinstance(raw, str) else raw
        raw = encoded if wire_kind == "bytes" else bytearray(encoded)
    plugin = M0108Plugin(M0108Service())

    token = plugin.validate(ReleasePackagingSubmission(request=raw, files=files))
    built = plugin.run(token)

    assert built.result.disposition is ReleaseDisposition.RELEASED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M01-08"


def test_plugin_rejects_invalid_submission_files_and_execution_token() -> None:
    request, _ = build_scenario("canonical")
    plugin = M0108Plugin(M0108Service())

    with pytest.raises(TypeError):
        plugin.validate(object())
    with pytest.raises(TypeError):
        plugin.validate(
            ReleasePackagingSubmission(
                request=request,
                files=cast("dict[str, bytes]", object()),
            )
        )
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM0108Request", object()))


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("disallowed_algorithm", "signature_algorithm_not_allowed"),
        ("rejected_decision", "upstream_decision_not_accepted"),
    ],
)
def test_policy_or_upstream_release_failure_quarantines(case: str, reason: str) -> None:
    request, files = build_scenario("canonical")
    if case == "disallowed_algorithm":
        receipt = request.signature_receipt
        assert receipt is not None
        request = request.model_copy(
            update={"signature_receipt": receipt.model_copy(update={"algorithm": "rsa"})}
        )
    else:
        rejected = request.decisions[0].model_copy(update={"state": DecisionState.REJECTED})
        request = request.model_copy(update={"decisions": (rejected, request.decisions[1])})

    built = build_release_package(request, files)

    assert built.result.disposition is ReleaseDisposition.QUARANTINED
    assert built.result.quarantine_reason == reason


def _result_for_package(
    result: ReleasePackagingResult,
    package_bytes: bytes,
) -> ReleasePackagingResult:
    payload = result.model_dump(mode="python")
    digest = sha256_bytes(package_bytes)
    payload["package"]["digest"] = digest
    payload["package"]["byte_size"] = len(package_bytes)
    payload["signature_receipt"]["package_digest"] = digest
    payload["result_digest"] = "sha256:" + ("0" * 64)
    return ReleasePackagingResult.model_validate(payload, strict=True)


def test_verifier_rejects_noncanonical_archive_metadata() -> None:
    request, files = build_scenario("canonical")
    built = build_release_package(request, files)
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path, content in reversed(tuple(files.items())):
            info = tarfile.TarInfo(path)
            info.size = len(content)
            info.mtime = 123456
            info.mode = 0o777
            archive.addfile(info, io.BytesIO(content))
    package_bytes = target.getvalue()

    verification = verify_release_package(
        _result_for_package(built.result, package_bytes),
        package_bytes,
    )

    assert not verification.verified
    assert verification.reason_code == "package_not_canonical"


def test_verifier_rejects_manifest_path_mismatch() -> None:
    request, files = build_scenario("canonical")
    built = build_release_package(request, files)
    members = inspect_canonical_ustar(built.package_bytes)
    renamed = PackageMember(path="unexpected/result.bin", content=members[0].content)
    package_bytes = build_canonical_ustar(
        (renamed, *members[1:]),
        fixed_mtime=built.result.manifest.fixed_mtime,
        file_mode=built.result.manifest.file_mode,
    )

    verification = verify_release_package(
        _result_for_package(built.result, package_bytes),
        package_bytes,
    )

    assert not verification.verified
    assert verification.reason_code == "artifact_path_mismatch"
