"""Focused defensive-boundary coverage for M03-08 release packaging."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import pytest
from evals.m03_08.run import Scenario, build_scenario

from glio_proteogen.contracts.m03_08 import (
    ExternalProteinInferenceSignature,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceParentComplexActivityReceipt,
    ProteinInferenceReleaseArtifactRole,
    ProteinInferenceReleaseResult,
    artifact_digest,
    normalized_artifact,
    result_payload_digest,
)
from glio_proteogen.contracts.m03_08.v1 import _validate_member_path
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import (
    PackageAssemblyError,
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    BuiltProteinInferenceRelease,
    ProteinInferenceReleaseInputError,
    ProteinInferenceReleaseInputErrorCode,
    build_protein_inference_release,
    build_protein_inference_release_manifest,
    verify_protein_inference_release,
)

pytestmark = pytest.mark.contract


@dataclass(frozen=True, slots=True)
class ReleaseCase:
    scenario: Scenario
    built: BuiltProteinInferenceRelease


@pytest.fixture(scope="module")
def release_case() -> ReleaseCase:
    scenario = build_scenario()
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    assert built.package_bytes is not None
    return ReleaseCase(scenario=scenario, built=built)


class _MappingReadError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("mapping boundary is unreadable")


class _KeysFailureMapping(Mapping[str, object]):
    """Mapping whose key inventory cannot be read."""

    def __getitem__(self, key: str) -> object:
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        raise _MappingReadError

    def __len__(self) -> int:
        return 0


class _GetitemFailureMapping(Mapping[str, object]):
    """Mapping with an exact key inventory but unreadable values."""

    def __init__(self, keys: tuple[str, ...]) -> None:
        self._keys = keys

    def __getitem__(self, key: str) -> object:
        del key
        raise _MappingReadError

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)


class _VerifierBoundaryError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("external verifier failed")


class _ExceptionalVerifier:
    def __init__(self, verifier_id: str) -> None:
        self._verifier_id = verifier_id

    @property
    def verifier_id(self) -> str:
        return self._verifier_id

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalProteinInferenceSignature,
    ) -> object:
        del statement_digest, signature
        raise _VerifierBoundaryError


class _NonBooleanVerifier(_ExceptionalVerifier):
    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalProteinInferenceSignature,
    ) -> object:
        del statement_digest, signature
        return 1


def _request_with_content(
    scenario: Scenario,
    path: str,
    content: bytes,
) -> tuple[object, dict[str, bytes]]:
    artifacts = []
    for artifact in scenario.request.artifacts:
        updated = artifact
        if artifact.path == path:
            updated = artifact.model_copy(
                update={
                    "declared_size": len(content),
                    "reference": artifact.reference.model_copy(
                        update={"digest": sha256_bytes(content)}
                    ),
                }
            )
        artifacts.append(updated)
    request = scenario.request.model_copy(update={"artifacts": tuple(artifacts)})
    supplied = dict(scenario.artifacts)
    supplied[path] = content
    return request, supplied


def _path_for_role(scenario: Scenario, role: ProteinInferenceReleaseArtifactRole) -> str:
    return next(item.path for item in scenario.request.artifacts if item.role is role)


def _result_with_package_digest(
    result: ProteinInferenceReleaseResult,
    package: bytes,
) -> ProteinInferenceReleaseResult:
    values = result.model_dump(mode="python")
    values["package_descriptor"]["digest"] = sha256_bytes(package)
    values["result_digest"] = result_payload_digest(values)
    return ProteinInferenceReleaseResult.model_validate(values, strict=True)


def test_artifact_digest_and_non_ascii_member_path_are_closed(
    release_case: ReleaseCase,
) -> None:
    artifact = release_case.scenario.request.artifacts[0]
    assert artifact_digest(artifact) == sha256_digest(normalized_artifact(artifact))
    with pytest.raises(ValueError, match="must be ASCII"):
        _validate_member_path("metadata/réceipt.json")


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        ("artifact", ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH),
        ("stage", ProteinInferenceReleaseInputErrorCode.STAGE_MAPPING_MISMATCH),
    ],
)
def test_mapping_key_inventory_exceptions_fail_closed(
    release_case: ReleaseCase,
    boundary: str,
    expected: ProteinInferenceReleaseInputErrorCode,
) -> None:
    scenario = release_case.scenario
    artifacts: Mapping[str, object] = scenario.artifacts
    stages: Mapping[str, object] = scenario.stages
    if boundary == "artifact":
        artifacts = _KeysFailureMapping()
    else:
        stages = _KeysFailureMapping()
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            scenario.request,
            artifacts,
            stages,
        )
    assert caught.value.code is expected


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        ("artifact", ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH),
        ("stage", ProteinInferenceReleaseInputErrorCode.STAGE_MAPPING_MISMATCH),
    ],
)
def test_mapping_value_exceptions_fail_closed(
    release_case: ReleaseCase,
    boundary: str,
    expected: ProteinInferenceReleaseInputErrorCode,
) -> None:
    scenario = release_case.scenario
    artifacts: Mapping[str, object] = scenario.artifacts
    stages: Mapping[str, object] = scenario.stages
    if boundary == "artifact":
        artifacts = _GetitemFailureMapping(tuple(scenario.artifacts))
    else:
        stages = _GetitemFailureMapping(tuple(scenario.stages))
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            scenario.request,
            artifacts,
            stages,
        )
    assert caught.value.code is expected


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("size", ProteinInferenceReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH),
        ("digest", ProteinInferenceReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH),
    ],
)
def test_artifact_byte_receipts_fail_closed(
    release_case: ReleaseCase,
    mutation: str,
    expected: ProteinInferenceReleaseInputErrorCode,
) -> None:
    scenario = release_case.scenario
    path, original = next(iter(scenario.artifacts.items()))
    supplied = dict(scenario.artifacts)
    if mutation == "size":
        supplied[path] = original + b"x"
    else:
        supplied[path] = bytes([original[0] ^ 1]) + original[1:]
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            scenario.request,
            supplied,
            scenario.stages,
        )
    assert caught.value.code is expected


def test_noncanonical_parent_json_is_rejected(release_case: ReleaseCase) -> None:
    scenario = release_case.scenario
    path = _path_for_role(
        scenario,
        ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF,
    )
    request, artifacts = _request_with_content(
        scenario,
        path,
        b" " + scenario.artifacts[path],
    )
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(request, artifacts, scenario.stages)
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.PARENT_JSON_INVALID


def test_parent_receipt_chain_mismatch_is_rejected(release_case: ReleaseCase) -> None:
    scenario = release_case.scenario
    path = _path_for_role(
        scenario,
        ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF,
    )
    receipt = ProteinInferenceParentComplexActivityReceipt.model_validate_json(
        scenario.artifacts[path],
        strict=True,
    )
    forged = receipt.model_copy(
        update={"support_route_result_digest": sha256_digest("wrong-support-route")}
    )
    request, artifacts = _request_with_content(
        scenario,
        path,
        canonical_json_bytes(forged),
    )
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(request, artifacts, scenario.stages)
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.CHAIN_MISMATCH


def test_noncanonical_stage_json_is_rejected(release_case: ReleaseCase) -> None:
    scenario = release_case.scenario
    path = _path_for_role(
        scenario,
        ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE,
    )
    request, artifacts = _request_with_content(
        scenario,
        path,
        b" " + scenario.artifacts[path],
    )
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(request, artifacts, scenario.stages)
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.STAGE_JSON_INVALID


@pytest.mark.parametrize("malformation", ["short_inventory", "corrupt_tar"])
def test_archive_preflight_rejects_bounded_malformed_packages(
    release_case: ReleaseCase,
    malformation: str,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None
    if malformation == "short_inventory":
        members = inspect_canonical_ustar(package)
        shortened = build_canonical_ustar(members[:-1])
        hostile = shortened + bytes(len(package) - len(shortened))
    else:
        hostile = b"x" * len(package)
    assert len(hostile) == len(package)
    result = _result_with_package_digest(release_case.built.result, hostile)
    verification = verify_protein_inference_release(result, hostile)
    assert verification.reason_code is ProteinInferencePackageVerificationReason.PACKAGE_INVALID


@pytest.mark.parametrize("failure", ["assembly_error", "different_bytes"])
def test_canonical_rebuild_failures_are_typed(
    release_case: ReleaseCase,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None

    def fail_rebuild(
        members: tuple[PackageMember, ...],
        *,
        fixed_mtime: int,
        file_mode: int,
    ) -> bytes:
        del members, fixed_mtime, file_mode
        raise PackageAssemblyError.invalid_archive()

    def change_rebuild(
        members: tuple[PackageMember, ...],
        *,
        fixed_mtime: int,
        file_mode: int,
    ) -> bytes:
        del members, fixed_mtime, file_mode
        return b"not-the-supplied-package"

    monkeypatch.setattr(
        "glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging."
        "engine.build_canonical_ustar",
        fail_rebuild if failure == "assembly_error" else change_rebuild,
    )
    verification = verify_protein_inference_release(release_case.built.result, package)
    expected = (
        ProteinInferencePackageVerificationReason.PACKAGE_INVALID
        if failure == "assembly_error"
        else ProteinInferencePackageVerificationReason.PACKAGE_NOT_CANONICAL
    )
    assert verification.reason_code is expected


@pytest.mark.parametrize("boundary", ["exception", "non_boolean"])
def test_verifier_runtime_boundaries_fail_closed(
    release_case: ReleaseCase,
    boundary: str,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None
    verifier_id = release_case.scenario.verifier.verifier_id
    verifier = (
        _ExceptionalVerifier(verifier_id)
        if boundary == "exception"
        else _NonBooleanVerifier(verifier_id)
    )
    verification = verify_protein_inference_release(
        release_case.built.result,
        package,
        verifier,
    )
    assert verification.reason_code is (
        ProteinInferencePackageVerificationReason.VERIFIER_UNAVAILABLE
    )
