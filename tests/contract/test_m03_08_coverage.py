"""Focused defensive-boundary coverage for M03-08 release packaging."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

import pytest
from evals.m03_08.run import Scenario, build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_08 import (
    BuildProteinInferenceReleaseRequest,
    ExternalProteinInferenceSignature,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceParentComplexActivityReceipt,
    ProteinInferenceReleaseArtifactRole,
    ProteinInferenceReleaseResult,
    artifact_digest,
    normalized_artifact,
    result_payload_digest,
)
from glio_proteogen.contracts.m03_08 import v1 as release_contract
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
    ProteinInferenceReleaseAuthorizationError,
    ProteinInferenceReleaseInputError,
    ProteinInferenceReleaseInputErrorCode,
    build_protein_inference_release,
    build_protein_inference_release_manifest,
    preflight_protein_inference_release_authorization,
    verify_protein_inference_release,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    engine as release_engine,
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


def test_package_verifier_rejects_mutable_and_descriptor_mismatched_bytes(
    release_case: ReleaseCase,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None
    with pytest.raises(TypeError, match="immutable bytes"):
        verify_protein_inference_release(
            release_case.built.result,
            cast("bytes", bytearray(package)),
        )
    truncated = verify_protein_inference_release(release_case.built.result, package[:-1])
    assert truncated.reason_code is ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH


def test_package_verifier_binds_member_content_before_authenticity(
    release_case: ReleaseCase,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None
    members = list(inspect_canonical_ustar(package))
    first = members[0]
    assert first.content
    members[0] = PackageMember(
        path=first.path,
        content=bytes([first.content[0] ^ 1]) + first.content[1:],
    )
    hostile = build_canonical_ustar(tuple(members))
    result = _result_with_package_digest(release_case.built.result, hostile)
    verification = verify_protein_inference_release(result, hostile)
    assert verification.reason_code is ProteinInferencePackageVerificationReason.CONTENT_MISMATCH


def test_package_verifier_rejects_inventory_manifest_and_parent_mutations(
    release_case: ReleaseCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None
    members = list(inspect_canonical_ustar(package))
    first = members[0]
    members[0] = PackageMember(
        path=first.path[:-1] + ("x" if first.path[-1] != "x" else "y"),
        content=first.content,
    )
    inventory_package = build_canonical_ustar(tuple(members))
    inventory_result = _result_with_package_digest(release_case.built.result, inventory_package)
    inventory = verify_protein_inference_release(inventory_result, inventory_package)
    assert inventory.reason_code is ProteinInferencePackageVerificationReason.INVENTORY_MISMATCH
    original_manifest = cast(
        "Callable[[object], object]",
        vars(release_engine)["normalized_manifest"],
    )
    monkeypatch.setattr(release_engine, "normalized_manifest", lambda _manifest: {})
    manifest = verify_protein_inference_release(release_case.built.result, package)
    assert manifest.reason_code is ProteinInferencePackageVerificationReason.MANIFEST_MISMATCH
    monkeypatch.setattr(release_engine, "normalized_manifest", original_manifest)
    monkeypatch.setattr(release_engine, "_package_parent_receipt_is_bound", lambda *_args: False)
    parent = verify_protein_inference_release(release_case.built.result, package)
    assert parent.reason_code is ProteinInferencePackageVerificationReason.CONTENT_MISMATCH


def test_build_rejects_stage_mapping_and_result_mismatches(
    release_case: ReleaseCase,
) -> None:
    scenario = release_case.scenario
    missing = dict(scenario.stages)
    missing.pop(next(iter(missing)))
    with pytest.raises(ProteinInferenceReleaseInputError) as missing_error:
        build_protein_inference_release_manifest(scenario.request, scenario.artifacts, missing)
    assert missing_error.value.code is ProteinInferenceReleaseInputErrorCode.STAGE_MAPPING_MISMATCH
    wrong: dict[str, object] = dict(scenario.stages)
    module = next(iter(wrong))
    wrong[module] = object()
    with pytest.raises(ProteinInferenceReleaseInputError) as type_error:
        build_protein_inference_release_manifest(scenario.request, scenario.artifacts, wrong)
    assert type_error.value.code is ProteinInferenceReleaseInputErrorCode.STAGE_RESULT_MISMATCH
    altered: dict[str, object] = dict(scenario.stages)
    altered[module] = scenario.stages[module].model_copy(
        update={"result_digest": sha256_digest("altered-stage")}
    )
    with pytest.raises(ProteinInferenceReleaseInputError) as value_error:
        build_protein_inference_release_manifest(scenario.request, scenario.artifacts, altered)
    assert value_error.value.code is ProteinInferenceReleaseInputErrorCode.STAGE_RESULT_MISMATCH


def test_authorization_and_built_release_invariants_fail_closed(
    release_case: ReleaseCase,
) -> None:
    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        preflight_protein_inference_release_authorization(object())
    quarantined = build_protein_inference_release(
        release_case.scenario.request,
        release_case.scenario.artifacts,
        release_case.scenario.stages,
    )
    with pytest.raises(ValueError, match="package-byte presence"):
        BuiltProteinInferenceRelease(quarantined.result, b"unexpected")


def test_engine_private_member_boundary_returns_none_for_unknown_storage() -> None:
    member = cast("Callable[[object, str], object]", vars(release_engine)["_member"])
    assert member(object(), "missing") is None


def test_package_verifier_enforces_active_package_byte_cap(
    release_case: ReleaseCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = release_case.built.package_bytes
    assert package is not None
    monkeypatch.setattr(release_engine, "M0308_MAX_PACKAGE_BYTES", 0)
    verification = verify_protein_inference_release(release_case.built.result, package)
    assert verification.reason_code is ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH


@pytest.mark.parametrize(
    "mutation",
    [
        "context_digest",
        "policy_digest",
        "manifest_policy_digest",
        "manifest_identity_digest",
        "manifest_digest",
        "signature_statement",
        "request_digest",
        "support_rationale",
        "limitations",
        "result_identifier",
        "provenance_configuration",
        "provenance_inputs",
        "evidence_claim",
        "uncertainty_note",
    ],
)
def test_result_receipt_relationships_reject_single_field_forgery(  # noqa: C901, PLR0912
    release_case: ReleaseCase,
    mutation: str,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    wrong = sha256_digest(f"m03-08-forged-{mutation}")
    if mutation == "context_digest":
        payload["context_digest"] = wrong
    elif mutation == "policy_digest":
        payload["policy_digest"] = wrong
    elif mutation == "manifest_policy_digest":
        payload["manifest"]["policy_digest"] = wrong
    elif mutation == "manifest_identity_digest":
        payload["manifest"]["identity_resolution_digest"] = wrong
    elif mutation == "manifest_digest":
        payload["manifest_digest"] = wrong
    elif mutation == "signature_statement":
        payload["signature_verification"]["statement_digest"] = wrong
    elif mutation == "request_digest":
        payload["request_digest"] = wrong
    elif mutation == "support_rationale":
        payload["support"]["rationale"] = "forged support rationale"
    elif mutation == "limitations":
        payload["limitations"][0]["statement"] = "forged limitation"
    elif mutation == "result_identifier":
        payload["release_result_id"] = f"result.m0308.{'0' * 64}"
    elif mutation == "provenance_configuration":
        payload["provenance"]["configuration_digest"] = wrong
    elif mutation == "provenance_inputs":
        payload["provenance"]["input_digests"] = payload["provenance"]["input_digests"][:-1]
    elif mutation == "evidence_claim":
        payload["evidence"][0]["claim"] = "forged evidence claim"
    else:
        payload["uncertainty"]["sensitivity_notes"] = ()
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)


@pytest.mark.parametrize("member_kind", ["caller", "manifest", "receipt"])
def test_result_package_descriptor_rebinds_every_generated_and_caller_member(
    release_case: ReleaseCase,
    member_kind: str,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    members = payload["package_descriptor"]["members"]
    if member_kind == "caller":
        members[0]["digest"] = sha256_digest("forged-caller-member")
    else:
        path = (
            "META-INF/glio-proteogen-m03-08/reproducibility-manifest.json"
            if member_kind == "manifest"
            else "META-INF/glio-proteogen-m03-08/signature-verification.json"
        )
        next(item for item in members if item["path"] == path)["digest"] = sha256_digest(
            f"forged-{member_kind}"
        )
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)


def test_build_rejects_mapping_key_and_artifact_type_mismatches(
    release_case: ReleaseCase,
) -> None:
    scenario = release_case.scenario
    missing = dict(scenario.artifacts)
    missing.pop(next(iter(missing)))
    with pytest.raises(ProteinInferenceReleaseInputError) as missing_error:
        build_protein_inference_release_manifest(scenario.request, missing, scenario.stages)
    assert (
        missing_error.value.code is ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH
    )
    wrong_type: dict[str, object] = dict(scenario.artifacts)
    path = next(iter(wrong_type))
    wrong_type[path] = bytearray(cast("bytes", wrong_type[path]))
    with pytest.raises(ProteinInferenceReleaseInputError) as type_error:
        build_protein_inference_release_manifest(scenario.request, wrong_type, scenario.stages)
    assert type_error.value.code is ProteinInferenceReleaseInputErrorCode.ARTIFACT_TYPE_INVALID


class _VerifierIdFailure:
    @property
    def verifier_id(self) -> str:
        raise RuntimeError("verifier identity unavailable")  # noqa: TRY003


def test_verifier_identity_failure_quarantines_without_package(
    release_case: ReleaseCase,
) -> None:
    built = build_protein_inference_release(
        release_case.scenario.request,
        release_case.scenario.artifacts,
        release_case.scenario.stages,
        _VerifierIdFailure(),  # type: ignore[arg-type]
    )
    assert built.package_bytes is None
    assert built.result.signature_verification.reason_code.value == "verifier_unavailable"


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


@pytest.mark.parametrize("mutation", ["evidence_media", "artifact_alias", "canonical_limit"])
def test_request_projection_rejects_evidence_alias_and_ingress_mutations(
    release_case: ReleaseCase,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    payload = release_case.scenario.request.model_dump(mode="python")
    if mutation == "evidence_media":
        payload["policy"]["evidence"]["media_type"] = "Application/JSON"
    elif mutation == "artifact_alias":
        payload["artifacts"][1]["path"] = payload["artifacts"][0]["path"]
    else:
        monkeypatch.setattr(release_contract, "M0308_MAX_CANONICAL_REQUEST_BYTES", 0)
    with pytest.raises((ValidationError, ValueError)):
        BuildProteinInferenceReleaseRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize("mutation", ["alias", "missing_generated", "framing"])
def test_package_descriptor_projection_rejects_inventory_mutations(
    release_case: ReleaseCase,
    mutation: str,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    members = payload["package_descriptor"]["members"]
    if mutation == "alias":
        caller = next(item for item in members if item["role"] is not None)
        generated = [item for item in members if item["role"] is None]
        caller["path"] = generated[0]["path"]
    elif mutation == "missing_generated":
        generated = [item for item in members if item["role"] is None]
        members[0]["path"] = "metadata/missing-generated.json"
        members[0]["role"] = None
        generated[0]["path"] = "metadata/other-generated.json"
    else:
        payload["package_descriptor"]["byte_size"] += 1
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "mutation",
    ["stage_order", "signature_before_stage", "signature_after_context", "review_after_signature"],
)
def test_result_temporal_projection_rejects_signature_order_mutations(
    release_case: ReleaseCase,
    mutation: str,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    if mutation == "stage_order":
        payload["manifest"]["stages"][1]["generated_at"] = payload["manifest"]["stages"][0][
            "generated_at"
        ] - timedelta(seconds=1)
    elif mutation == "signature_before_stage":
        payload["signature"]["issued_at"] = payload["manifest"]["stages"][-1][
            "generated_at"
        ] - timedelta(seconds=1)
    elif mutation == "signature_after_context":
        payload["signature"]["issued_at"] = payload["context"]["occurred_at"] + timedelta(seconds=1)
    else:
        payload["policy"]["reviewed_at"] = payload["signature"]["issued_at"] + timedelta(seconds=1)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "mutation", ["manifest_identity", "manifest_intended_use", "controls", "consent"]
)
def test_result_projection_rejects_context_and_control_forgery(
    release_case: ReleaseCase,
    mutation: str,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    wrong = sha256_digest(f"m03-08-projection-{mutation}")
    if mutation == "manifest_identity":
        payload["manifest"]["identity_resolution_digest"] = wrong
    elif mutation == "manifest_intended_use":
        payload["manifest"]["intended_use_evidence_digest"] = wrong
    elif mutation == "controls":
        payload["provenance"]["control_decisions"][0]["evidence_digest"] = wrong
    else:
        payload["provenance"]["consent_evidence_digest"] = wrong
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)


def test_result_projection_rejects_uncertainty_and_digest_forgery(
    release_case: ReleaseCase,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    payload["uncertainty"]["measurement"]["rationale"] = "forged"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)
    digest_payload = release_case.built.result.model_dump(mode="python")
    digest_payload["result_digest"] = sha256_digest("wrong-result-digest")
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(digest_payload, strict=True)


def test_manifest_projection_rejects_duplicate_metadata_identifiers(
    release_case: ReleaseCase,
) -> None:
    payload = release_case.scenario.request.model_dump(mode="python")
    payload["software_versions"] = [
        *payload["software_versions"],
        payload["software_versions"][0].copy(),
    ]
    with pytest.raises((ValidationError, ValueError)):
        BuildProteinInferenceReleaseRequest.model_validate(payload, strict=True)


def test_release_result_identifier_shape_is_not_a_claimable_alias(
    release_case: ReleaseCase,
) -> None:
    payload = release_case.built.result.model_dump(mode="python")
    payload["release_result_id"] = "result.m0308.invalid"
    with pytest.raises((ValidationError, ValueError)):
        ProteinInferenceReleaseResult.model_validate(payload, strict=True)
