"""Focused engine-boundary tests for M02-08 release packaging."""

from __future__ import annotations

import io
import tarfile
from collections.abc import Iterator, KeysView, Mapping
from dataclasses import dataclass

import pytest
from evals.m02_08.run import (
    MAX_METADATA_RECORDS,
    NONCRYPTO_ALGORITHM,
    NONCRYPTO_VERIFIER_ID,
    STAGE_MODULE_IDS,
    DeterministicNonCryptographicVerifier,
    IdentificationReleaseFixture,
    _max_metadata_fixture,
    _releasable_cross_chain_results,
    _reordered_fixture,
    _replace_parent_receipt_field,
    _replace_stage,
    _sign_fixture,
    _signed_fixture,
)
from pydantic import ValidationError

from glio_proteogen.contracts.m02_08 import (
    M0208_ARCHIVE_MEMBER_COUNT,
    BuildIdentificationQcReleaseRequest,
    ExternalIdentificationSignature,
    IdentificationPackageVerificationReason,
    IdentificationParentProteinSubtypeReceipt,
    IdentificationQcReleaseResult,
    IdentificationReleaseArtifactRole,
    IdentificationReleaseDisposition,
    IdentificationSignatureVerificationReason,
    policy_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import (
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    BuiltIdentificationRelease,
    IdentificationReleaseAuthorizationError,
    IdentificationReleaseInputError,
    IdentificationReleaseInputErrorCode,
    IdentificationReleaseSubmission,
    M0208Plugin,
    M0208Service,
    build_identification_release,
    build_identification_release_manifest,
    preflight_identification_release_authorization,
    verify_identification_release,
)
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    engine as release_engine,
)

pytestmark = pytest.mark.policy

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_POLICY_MEMBER_COUNT = 2
_MAPPING_ITERATION_UNEXPECTED = "mapping iteration was not expected"
_MAPPING_SIZING_UNEXPECTED = "mapping sizing was not expected"
_MAPPING_KEYS_UNAVAILABLE = "external mapping keys unavailable"
_INVALID_MODEL_ITERATION = "invalid model did not revalidate before mapping traversal"
_INVALID_MODEL_SIZING = "invalid model did not revalidate before mapping sizing"
_VERIFIER_ID_UNAVAILABLE = "external verifier identifier unavailable"
_VERIFICATION_UNAVAILABLE = "external verification unavailable"


@pytest.fixture(scope="module")
def signed_fixture() -> IdentificationReleaseFixture:
    return _signed_fixture()


@pytest.fixture(scope="module")
def released(
    signed_fixture: IdentificationReleaseFixture,
) -> BuiltIdentificationRelease:
    return build_identification_release(
        signed_fixture.request,
        signed_fixture.artifacts,
        signed_fixture.stages,
        DeterministicNonCryptographicVerifier(),
    )


class _KeysFail(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(_MAPPING_ITERATION_UNEXPECTED)

    def __len__(self) -> int:
        raise AssertionError(_MAPPING_SIZING_UNEXPECTED)

    def keys(self) -> KeysView[str]:
        raise OSError(_MAPPING_KEYS_UNAVAILABLE)


class _GetFail(Mapping[str, object]):
    def __init__(self, keys: tuple[str, ...]) -> None:
        self._keys = keys

    def __getitem__(self, key: str) -> object:
        raise OSError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)


class _TraversalTrap(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(_INVALID_MODEL_ITERATION)

    def __len__(self) -> int:
        raise AssertionError(_INVALID_MODEL_SIZING)


@dataclass(slots=True)
class _ExternalFailureVerifier:
    failure: str
    calls: int = 0

    @property
    def verifier_id(self) -> str:
        if self.failure == "identifier_exception":
            raise OSError(_VERIFIER_ID_UNAVAILABLE)
        return NONCRYPTO_VERIFIER_ID

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalIdentificationSignature,
    ) -> object:
        del statement_digest, signature
        self.calls += 1
        if self.failure == "verify_exception":
            raise OSError(_VERIFICATION_UNAVAILABLE)
        if self.failure == "non_boolean":
            return "verified"
        return True


def _artifact_path(
    fixture: IdentificationReleaseFixture,
    role: IdentificationReleaseArtifactRole,
) -> str:
    return next(item.path for item in fixture.request.artifacts if item.role is role)


def _replace_artifact_bytes(
    fixture: IdentificationReleaseFixture,
    path: str,
    content: bytes,
) -> IdentificationReleaseFixture:
    declarations = tuple(
        item.model_copy(
            update={
                "reference": item.reference.model_copy(
                    update={"digest": sha256_bytes(content)}
                ),
                "declared_size": len(content),
            }
        )
        if item.path == path
        else item
        for item in fixture.request.artifacts
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(update={"artifacts": declarations}).model_dump(
            mode="python"
        )
    )
    return IdentificationReleaseFixture(
        request=request,
        artifacts={**fixture.artifacts, path: content},
        stages=fixture.stages,
    )


def _rebind_package_descriptor(
    result: IdentificationQcReleaseResult,
    package_bytes: bytes,
) -> IdentificationQcReleaseResult:
    descriptor = result.package_descriptor
    assert descriptor is not None
    values = result.model_dump(mode="python")
    values["package_descriptor"] = descriptor.model_copy(
        update={
            "byte_size": len(package_bytes),
            "digest": sha256_bytes(package_bytes),
        }
    ).model_dump(mode="python")
    values["result_digest"] = _ZERO_DIGEST
    return IdentificationQcReleaseResult.model_validate(values, strict=True)


def _noncanonical_ustar(members: tuple[PackageMember, ...]) -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for member in reversed(members):
            info = tarfile.TarInfo(member.path)
            info.size = len(member.content)
            info.mtime = 1
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(member.content))
    return target.getvalue()


def _with_multi_member_policy(
    fixture: IdentificationReleaseFixture,
) -> IdentificationReleaseFixture:
    policy = fixture.request.policy.model_copy(
        update={
            "allowed_signature_algorithms": (
                NONCRYPTO_ALGORITHM,
                "eval-noncrypto-secondary-v1",
            ),
            "allowed_verifier_ids": (
                NONCRYPTO_VERIFIER_ID,
                "verifier.synthetic.m0208.secondary",
            ),
        }
    )
    references = fixture.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": policy_digest(policy)}
            )
        }
    )
    context = fixture.request.context.model_copy(
        update={
            "references": references.model_copy(
                update={"approved_configuration": approved}
            )
        }
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(
            update={"context": context, "policy": policy}
        ).model_dump(mode="python")
    )
    return _sign_fixture(IdentificationReleaseFixture(request, fixture.artifacts, fixture.stages))


def test_strict_parent_receipt_build_and_package_verify(
    signed_fixture: IdentificationReleaseFixture,
    released: BuiltIdentificationRelease,
) -> None:
    assert released.package_bytes is not None
    parent_path = _artifact_path(
        signed_fixture,
        IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE,
    )
    receipt = IdentificationParentProteinSubtypeReceipt.model_validate_json(
        signed_fixture.artifacts[parent_path],
        strict=True,
    )
    assert receipt.parent_target == "protein_subtype"
    assert receipt.subject_binding_digest == released.result.manifest.subject_binding_digest
    assert (
        receipt.intended_use_evidence_digest
        == released.result.manifest.intended_use_evidence_digest
    )

    verifier = DeterministicNonCryptographicVerifier()
    verification = verify_identification_release(
        released.result,
        released.package_bytes,
        verifier,
    )
    assert verification.verified
    assert verification.member_count == M0208_ARCHIVE_MEMBER_COUNT
    assert len(verifier.calls) == 1


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (
            "parent_target",
            "kinase_activity",
            IdentificationReleaseInputErrorCode.PARENT_JSON_INVALID,
        ),
        (
            "subject_binding_digest",
            sha256_digest("wrong-parent-subject"),
            IdentificationReleaseInputErrorCode.CHAIN_MISMATCH,
        ),
        (
            "intended_use_evidence_digest",
            sha256_digest("wrong-parent-intended-use"),
            IdentificationReleaseInputErrorCode.CHAIN_MISMATCH,
        ),
    ],
)
def test_strict_parent_receipt_mismatch_is_a_hard_error_before_verification(
    signed_fixture: IdentificationReleaseFixture,
    field: str,
    value: str,
    expected: IdentificationReleaseInputErrorCode,
) -> None:
    fixture = _replace_parent_receipt_field(signed_fixture, field, value)
    verifier = DeterministicNonCryptographicVerifier()
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            fixture.request,
            fixture.artifacts,
            fixture.stages,
            verifier,
        )
    assert caught.value.code is expected
    assert not verifier.calls


@pytest.mark.parametrize(
    ("boundary", "mapping_kind", "expected"),
    [
        (
            "artifacts",
            "keys",
            IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        (
            "artifacts",
            "get",
            IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        (
            "stages",
            "keys",
            IdentificationReleaseInputErrorCode.STAGE_MAPPING_MISMATCH,
        ),
        (
            "stages",
            "get",
            IdentificationReleaseInputErrorCode.STAGE_MAPPING_MISMATCH,
        ),
    ],
)
def test_authorized_hostile_mappings_fail_as_typed_input_errors(
    signed_fixture: IdentificationReleaseFixture,
    boundary: str,
    mapping_kind: str,
    expected: IdentificationReleaseInputErrorCode,
) -> None:
    expected_keys = (
        tuple(signed_fixture.artifacts)
        if boundary == "artifacts"
        else tuple(signed_fixture.stages)
    )
    hostile: Mapping[str, object] = (
        _KeysFail() if mapping_kind == "keys" else _GetFail(expected_keys)
    )
    artifacts: Mapping[str, object] = (
        hostile if boundary == "artifacts" else signed_fixture.artifacts
    )
    stages: Mapping[str, object] = (
        hostile if boundary == "stages" else signed_fixture.stages
    )
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            signed_fixture.request,
            artifacts,
            stages,
            DeterministicNonCryptographicVerifier(),
        )
    assert caught.value.code is expected


@pytest.mark.parametrize(
    ("failure", "expected_calls"),
    [
        ("identifier_exception", 0),
        ("verify_exception", 2),
        ("non_boolean", 2),
    ],
)
def test_external_verifier_failures_are_typed_and_never_emit_build_bytes(
    signed_fixture: IdentificationReleaseFixture,
    released: BuiltIdentificationRelease,
    failure: str,
    expected_calls: int,
) -> None:
    assert released.package_bytes is not None
    verifier = _ExternalFailureVerifier(failure)
    built = build_identification_release(
        signed_fixture.request,
        signed_fixture.artifacts,
        signed_fixture.stages,
        verifier,
    )
    assert built.package_bytes is None
    assert built.result.disposition is IdentificationReleaseDisposition.QUARANTINED
    assert (
        built.result.signature_verification.reason_code
        is IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE
    )

    verification = verify_identification_release(
        released.result,
        released.package_bytes,
        verifier,
    )
    assert verification.content_verified
    assert not verification.authenticity_verified
    assert verification.reason_code is IdentificationPackageVerificationReason.VERIFIER_UNAVAILABLE
    assert verifier.calls == expected_calls


def test_typed_hard_error_precedence_stops_before_later_boundaries(
    signed_fixture: IdentificationReleaseFixture,
) -> None:
    verifier = DeterministicNonCryptographicVerifier()
    wrong_type: dict[str, object] = dict(signed_fixture.artifacts)
    wrong_type[next(iter(wrong_type))] = "not immutable bytes"
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            signed_fixture.request,
            wrong_type,
            _KeysFail(),
            verifier,
        )
    assert caught.value.code is IdentificationReleaseInputErrorCode.ARTIFACT_TYPE_INVALID

    parent_path = _artifact_path(
        signed_fixture,
        IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE,
    )
    malformed_parent = _replace_artifact_bytes(signed_fixture, parent_path, b"{}")
    stage_path = _artifact_path(
        malformed_parent,
        IdentificationReleaseArtifactRole.M02_01_CONFORMANCE,
    )
    malformed_stage = _replace_artifact_bytes(malformed_parent, stage_path, b"{\n")
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            malformed_stage.request,
            malformed_stage.artifacts,
            malformed_stage.stages,
            verifier,
        )
    assert caught.value.code is IdentificationReleaseInputErrorCode.STAGE_JSON_INVALID

    alternate_identity = _releasable_cross_chain_results()[0]
    cross_chain = _replace_stage(
        malformed_parent,
        "GLIO-PROTEOGEN-M02-02",
        alternate_identity,
    )
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            cross_chain.request,
            cross_chain.artifacts,
            cross_chain.stages,
            verifier,
        )
    assert caught.value.code is IdentificationReleaseInputErrorCode.CHAIN_MISMATCH
    assert not verifier.calls


def test_package_verification_categories_are_distinct_and_precede_authenticity(
    released: BuiltIdentificationRelease,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = released.package_bytes
    assert package is not None
    result = released.result
    members = inspect_canonical_ustar(package)

    descriptor_mismatch = verify_identification_release(
        result,
        package + b"tamper",
        DeterministicNonCryptographicVerifier(),
    )

    invalid_bytes = b"not-a-tar-archive"
    package_invalid = verify_identification_release(
        _rebind_package_descriptor(result, invalid_bytes),
        invalid_bytes,
        DeterministicNonCryptographicVerifier(),
    )

    missing_member = build_canonical_ustar(members[:-1])
    inventory_mismatch = verify_identification_release(
        _rebind_package_descriptor(result, missing_member),
        missing_member,
        DeterministicNonCryptographicVerifier(),
    )

    changed = bytes([members[0].content[0] ^ 1]) + members[0].content[1:]
    changed_content = build_canonical_ustar(
        (PackageMember(members[0].path, changed), *members[1:])
    )
    content_mismatch = verify_identification_release(
        _rebind_package_descriptor(result, changed_content),
        changed_content,
        DeterministicNonCryptographicVerifier(),
    )

    noncanonical = _noncanonical_ustar(members)
    package_not_canonical = verify_identification_release(
        _rebind_package_descriptor(result, noncanonical),
        noncanonical,
        DeterministicNonCryptographicVerifier(),
    )

    monkeypatch.setattr(
        release_engine,
        "normalized_manifest",
        lambda _manifest: {"forced": "manifest-mismatch"},
    )
    manifest_mismatch = verify_identification_release(
        result,
        package,
        DeterministicNonCryptographicVerifier(),
    )

    assert (
        descriptor_mismatch.reason_code
        is IdentificationPackageVerificationReason.DESCRIPTOR_MISMATCH
    )
    assert package_invalid.reason_code is IdentificationPackageVerificationReason.PACKAGE_INVALID
    assert (
        inventory_mismatch.reason_code
        is IdentificationPackageVerificationReason.INVENTORY_MISMATCH
    )
    assert content_mismatch.reason_code is IdentificationPackageVerificationReason.CONTENT_MISMATCH
    assert (
        package_not_canonical.reason_code
        is IdentificationPackageVerificationReason.PACKAGE_NOT_CANONICAL
    )
    assert (
        manifest_mismatch.reason_code
        is IdentificationPackageVerificationReason.MANIFEST_MISMATCH
    )
    assert all(
        not item.content_verified
        and not item.authenticity_verified
        and item.signature_verification.reason_code
        is IdentificationSignatureVerificationReason.NOT_ATTEMPTED
        for item in (
            descriptor_mismatch,
            package_invalid,
            inventory_mismatch,
            content_mismatch,
            package_not_canonical,
            manifest_mismatch,
        )
    )


def test_package_parent_receipt_helper_is_strict(
    released: BuiltIdentificationRelease,
) -> None:
    package = released.package_bytes
    assert package is not None
    content = {item.path: item.content for item in inspect_canonical_ustar(package)}
    assert release_engine._package_parent_receipt_is_bound(released.result, content)

    parent_path = next(
        item.path
        for item in released.result.manifest.artifacts
        if item.role is IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE
    )
    malformed = {**content, parent_path: b"{}"}
    assert not release_engine._package_parent_receipt_is_bound(released.result, malformed)

    decoded = strict_json_loads(content[parent_path])
    assert isinstance(decoded, dict)
    decoded["subject_binding_digest"] = sha256_digest("forged-package-parent")
    mismatched = {**content, parent_path: canonical_json_bytes(decoded)}
    assert not release_engine._package_parent_receipt_is_bound(released.result, mismatched)


def test_release_and_quarantine_package_byte_invariant(
    signed_fixture: IdentificationReleaseFixture,
    released: BuiltIdentificationRelease,
) -> None:
    assert released.result.disposition is IdentificationReleaseDisposition.RELEASED
    assert released.package_bytes is not None
    quarantined = build_identification_release(
        signed_fixture.request,
        signed_fixture.artifacts,
        signed_fixture.stages,
        None,
    )
    assert quarantined.result.disposition is IdentificationReleaseDisposition.QUARANTINED
    assert quarantined.package_bytes is None

    with pytest.raises(ValueError, match="package-byte presence"):
        BuiltIdentificationRelease(result=released.result, package_bytes=None)
    with pytest.raises(ValueError, match="package-byte presence"):
        BuiltIdentificationRelease(result=quarantined.result, package_bytes=b"forbidden")
    with pytest.raises(TypeError, match="immutable bytes"):
        verify_identification_release(
            released.result,
            memoryview(released.package_bytes),  # type: ignore[arg-type]
            DeterministicNonCryptographicVerifier(),
        )


def test_public_engine_revalidates_model_construct_forgeries(
    signed_fixture: IdentificationReleaseFixture,
    released: BuiltIdentificationRelease,
) -> None:
    request_values = dict(signed_fixture.request.__dict__)
    request_values["artifacts"] = signed_fixture.request.artifacts[:-1]
    forged_request = BuildIdentificationQcReleaseRequest.model_construct(**request_values)
    with pytest.raises(ValidationError):
        build_identification_release(
            forged_request,
            _TraversalTrap(),
            _TraversalTrap(),
            DeterministicNonCryptographicVerifier(),
        )

    stage = signed_fixture.stages[STAGE_MODULE_IDS[3]]
    stage_values = dict(stage.__dict__)
    stage_values["result_digest"] = sha256_digest("forged-stage-result")
    forged_stage = stage.__class__.model_construct(**stage_values)
    forged_stages = {**signed_fixture.stages, STAGE_MODULE_IDS[3]: forged_stage}
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            signed_fixture.request,
            signed_fixture.artifacts,
            forged_stages,
            DeterministicNonCryptographicVerifier(),
        )
    assert caught.value.code is IdentificationReleaseInputErrorCode.STAGE_JSON_INVALID

    result_values = dict(released.result.__dict__)
    result_values["disposition"] = IdentificationReleaseDisposition.QUARANTINED
    forged_result = IdentificationQcReleaseResult.model_construct(**result_values)
    assert released.package_bytes is not None
    with pytest.raises(ValidationError):
        verify_identification_release(
            forged_result,
            released.package_bytes,
            DeterministicNonCryptographicVerifier(),
        )


def test_maximum_metadata_and_multi_member_sets_preserve_full_output_equality() -> None:
    fixture = _with_multi_member_policy(_max_metadata_fixture())
    reordered = _reordered_fixture(fixture)
    first = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        DeterministicNonCryptographicVerifier(),
    )
    second = build_identification_release(
        reordered.request,
        reordered.artifacts,
        reordered.stages,
        DeterministicNonCryptographicVerifier(),
    )
    assert len(fixture.request.software_versions) == MAX_METADATA_RECORDS
    assert len(fixture.request.reference_versions) == MAX_METADATA_RECORDS
    assert (
        len(fixture.request.policy.allowed_signature_algorithms) == _POLICY_MEMBER_COUNT
    )
    assert len(fixture.request.policy.allowed_verifier_ids) == _POLICY_MEMBER_COUNT
    assert first.result == second.result
    assert first.package_bytes == second.package_bytes
    assert first.result.result_digest == second.result.result_digest


def test_service_manifest_and_plugin_lifecycle_cover_both_submission_shapes(
    signed_fixture: IdentificationReleaseFixture,
) -> None:
    verifier = DeterministicNonCryptographicVerifier()
    service = M0208Service(verifier)
    manifest = service.build_manifest(
        signed_fixture.request,
        signed_fixture.artifacts,
        signed_fixture.stages,
    )
    assert manifest == build_identification_release_manifest(
        signed_fixture.request,
        signed_fixture.artifacts,
        signed_fixture.stages,
    )
    assert not verifier.calls

    plugin = M0208Plugin(service)
    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M02-08"
    assert descriptor.version == "1.0.0"
    assert descriptor.safety_class == "S2"
    assert descriptor.gate == "G1"
    assert descriptor.prohibited_outputs

    model_token = plugin.validate(
        IdentificationReleaseSubmission(
            signed_fixture.request,
            signed_fixture.artifacts,
            signed_fixture.stages,
        )
    )
    bytes_token = plugin.validate(
        IdentificationReleaseSubmission(
            signed_fixture.request.model_dump_json().encode(),
            signed_fixture.artifacts,
            signed_fixture.stages,
        )
    )
    assert model_token == bytes_token

    built = plugin.run(bytes_token)
    assert built.result.disposition is IdentificationReleaseDisposition.RELEASED
    assert built.package_bytes is not None
    assert len(verifier.calls) == 1


def test_plugin_rejects_unvalidated_submission_and_execution_tokens(
    signed_fixture: IdentificationReleaseFixture,
) -> None:
    plugin = M0208Plugin(M0208Service(DeterministicNonCryptographicVerifier()))

    with pytest.raises(TypeError, match="validation requires"):
        plugin.validate(signed_fixture.request)
    with pytest.raises(TypeError, match="execution requires"):
        plugin.run(object())  # type: ignore[arg-type]


def test_preflight_rejects_non_request_non_mapping_candidates() -> None:
    with pytest.raises(IdentificationReleaseAuthorizationError):
        preflight_identification_release_authorization(object())


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("artifact_set", IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH),
        ("artifact_size", IdentificationReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH),
        ("artifact_digest", IdentificationReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH),
        ("stage_set", IdentificationReleaseInputErrorCode.STAGE_MAPPING_MISMATCH),
        ("stage_result", IdentificationReleaseInputErrorCode.STAGE_RESULT_MISMATCH),
    ],
)
def test_exact_mapping_and_byte_boundary_errors_are_typed_before_verification(
    signed_fixture: IdentificationReleaseFixture,
    case: str,
    expected: IdentificationReleaseInputErrorCode,
) -> None:
    artifacts: dict[str, object] = dict(signed_fixture.artifacts)
    stages: dict[str, object] = dict(signed_fixture.stages)
    artifact_path = next(iter(artifacts))
    artifact_bytes = artifacts[artifact_path]
    assert isinstance(artifact_bytes, bytes)

    if case == "artifact_set":
        artifacts.pop(artifact_path)
    elif case == "artifact_size":
        artifacts[artifact_path] = artifact_bytes + b"x"
    elif case == "artifact_digest":
        artifacts[artifact_path] = bytes([artifact_bytes[0] ^ 1]) + artifact_bytes[1:]
    elif case == "stage_set":
        stages.pop(STAGE_MODULE_IDS[0])
    else:
        stages[STAGE_MODULE_IDS[1]] = _releasable_cross_chain_results()[0]

    verifier = DeterministicNonCryptographicVerifier()
    with pytest.raises(IdentificationReleaseInputError) as caught:
        build_identification_release(
            signed_fixture.request,
            artifacts,
            stages,
            verifier,
        )
    assert caught.value.code is expected
    assert not verifier.calls
