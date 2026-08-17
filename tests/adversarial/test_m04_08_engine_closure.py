"""Deep negative-path closure for the M04-08 engine and authorization seam."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Never, cast

import pytest
from evals.m04_08.run import _fixture

if TYPE_CHECKING:
    from collections.abc import Mapping

from glio_proteogen.contracts.m04_08 import (
    M0408_MAX_PACKAGE_BYTES,
    ProteoformReleaseResult,
    ProteoformSignatureVerificationReason,
)
from glio_proteogen.contracts.m04_08.v1 import (
    _require_authorized_context,
    _validate_context_opacity,
)
from glio_proteogen.kernel.canonical_ustar import (
    PackageAssemblyError,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    build_proteoform_release,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    engine as engine_module,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    ProteoformReleaseAuthorizationError,
    ProteoformReleaseInputError,
    ProteoformReleaseInputErrorCode,
    StageResult,
    _identity_subject,
    _member,
    _NonCanonicalArtifactError,
    _PackageBytesTypeError,
    _parse_stage_artifact,
    _require_canonical_artifact_bytes,
    _stage_context,
    _validate_caller_bytes,
    _validate_parent_receipt,
    _validate_stage_chain,
    _validate_stage_results,
    _verify_package,
    _verify_result_signature,
    preflight_proteoform_release_authorization,
)


class _ExplodingMappingError(RuntimeError):
    pass


class _ExplodingKeys(dict[str, object]):
    def keys(self) -> Never:
        raise _ExplodingMappingError


class _Verifier:
    def __init__(
        self,
        *,
        outcome: object = True,
        verifier_id: str = "verifier.m0408",
        raise_error: bool = False,
    ) -> None:
        self.outcome = outcome
        self._verifier_id = verifier_id
        self.raise_error = raise_error

    @property
    def verifier_id(self) -> str:
        return self._verifier_id

    def verify(self, **_kwargs: object) -> object:
        if self.raise_error:
            raise RuntimeError
        return self.outcome


class _ResultProxy:
    def __init__(self, base: object, descriptor: object) -> None:
        self._base = base
        self.package_descriptor = descriptor

    def __getattr__(self, name: str) -> object:
        return getattr(self._base, name)


def _descriptor_proxy(built: object, *, member_updates: dict[int, dict[str, object]]) -> object:
    result = cast("ProteoformReleaseResult", built)
    descriptor = result.package_descriptor
    assert descriptor is not None
    members = tuple(
        member.model_copy(update=member_updates.get(index, {}))
        for index, member in enumerate(descriptor.members)
    )
    return descriptor.model_copy(update={"members": members})


def test_engine_firewalls_cover_immutable_input_and_stage_mapping_paths() -> None:
    fixture = _fixture()
    request = fixture.request
    with pytest.raises(ProteoformReleaseInputError) as missing:
        _validate_caller_bytes(request, {})
    assert missing.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH

    extra = dict(fixture.artifacts)
    extra["extra.json"] = b"extra"
    with pytest.raises(ProteoformReleaseInputError) as extra_error:
        _validate_caller_bytes(request, extra)
    assert extra_error.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH

    wrong_type: dict[str, object] = dict(fixture.artifacts)
    wrong_type[next(iter(wrong_type))] = bytearray(b"not-bytes")
    with pytest.raises(ProteoformReleaseInputError) as type_error:
        _validate_caller_bytes(request, wrong_type)
    assert type_error.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_TYPE_INVALID

    wrong_size = dict(fixture.artifacts)
    first = next(iter(wrong_size))
    wrong_size[first] = wrong_size[first] + b"x"
    with pytest.raises(ProteoformReleaseInputError) as size_error:
        _validate_caller_bytes(request, wrong_size)
    assert size_error.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH

    wrong_digest = dict(fixture.artifacts)
    wrong_digest[first] = b"x" * len(wrong_digest[first])
    with pytest.raises(ProteoformReleaseInputError) as digest_error:
        _validate_caller_bytes(request, wrong_digest)
    assert digest_error.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH

    with pytest.raises(ProteoformReleaseInputError) as stage_error:
        _validate_stage_results(request, fixture.artifacts, {})
    assert stage_error.value.code is ProteoformReleaseInputErrorCode.STAGE_MAPPING_MISMATCH

    with pytest.raises(ProteoformReleaseInputError) as exploding:
        _validate_caller_bytes(request, cast("Mapping[str, object]", _ExplodingKeys()))
    assert exploding.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH

    malformed_artifacts = dict(fixture.artifacts)
    stage_path = next(path for path in malformed_artifacts if "m04-01" in path)
    malformed_artifacts[stage_path] = b"{}"
    with pytest.raises(ProteoformReleaseInputError) as json_error:
        _validate_stage_results(request, malformed_artifacts, fixture.stages)
    assert json_error.value.code is ProteoformReleaseInputErrorCode.STAGE_JSON_INVALID

    with pytest.raises(ProteoformReleaseAuthorizationError):
        preflight_proteoform_release_authorization(object())
    with pytest.raises(ProteoformReleaseAuthorizationError):
        preflight_proteoform_release_authorization({"context": {"references": {}}})


def test_engine_private_helpers_and_chain_fail_closed() -> None:
    fixture = _fixture()
    stages = cast("dict[str, StageResult]", dict(fixture.stages))
    first_module = "GLIO-PROTEOGEN-M04-01"
    bad_stages = dict(stages)
    bad_stages[first_module] = cast("StageResult", object())
    with pytest.raises(ProteoformReleaseInputError) as mismatch:
        _validate_stage_results(fixture.request, fixture.artifacts, bad_stages)
    assert mismatch.value.code is ProteoformReleaseInputErrorCode.STAGE_RESULT_MISMATCH

    broken_chain = dict(stages)
    m0402 = stages["GLIO-PROTEOGEN-M04-02"]
    broken_chain["GLIO-PROTEOGEN-M04-02"] = m0402.model_copy(
        update={"protocol_result_digest": "sha256:" + "0" * 64}
    )
    with pytest.raises(ProteoformReleaseInputError) as chain:
        _validate_stage_chain(fixture.request, broken_chain)
    assert chain.value.code is ProteoformReleaseInputErrorCode.CHAIN_MISMATCH

    with pytest.raises(ProteoformReleaseInputError):
        _identity_subject(
            cast("StageResult", SimpleNamespace(provenance=SimpleNamespace(control_decisions=())))
        )
    assert _member({"field": 1}, "field") == 1
    assert _member(SimpleNamespace(field=2), "field") is None
    assert _member(object(), "field") is None
    first = stages[first_module]
    assert _stage_context(first).request_id == first.request.context.request_id

    with pytest.raises(_NonCanonicalArtifactError):
        _require_canonical_artifact_bytes({"field": 1}, b"{}")
    with pytest.raises(_PackageBytesTypeError):
        _verify_package(
            cast("ProteoformReleaseResult", fixture.stages[first_module]),
            cast("bytes", bytearray(b"not-bytes")),
            None,
        )

    with pytest.raises(ProteoformReleaseInputError) as parent_error:
        _validate_parent_receipt(fixture.request, {next(iter(fixture.artifacts)): b"{}"}, stages)
    assert parent_error.value.code is ProteoformReleaseInputErrorCode.PARENT_JSON_INVALID


def test_engine_signature_and_mapping_exception_edges() -> None:
    fixture = _fixture()
    request = fixture.request
    artifacts = fixture.artifacts
    stages = fixture.stages
    with pytest.raises(ProteoformReleaseInputError) as get_error:
        _validate_caller_bytes(request, cast("Mapping[str, object]", _ExplodingGet(artifacts)))
    assert get_error.value.code is ProteoformReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH

    with pytest.raises(ProteoformReleaseInputError) as stage_keys:
        _validate_stage_results(request, artifacts, cast("Mapping[str, object]", _ExplodingKeys()))
    assert stage_keys.value.code is ProteoformReleaseInputErrorCode.STAGE_MAPPING_MISMATCH

    stage_map = cast("dict[str, StageResult]", dict(stages))
    stage_map.pop("GLIO-PROTEOGEN-M04-01")
    with pytest.raises(ProteoformReleaseInputError) as missing_stage:
        _validate_stage_results(request, artifacts, stage_map)
    assert missing_stage.value.code is ProteoformReleaseInputErrorCode.STAGE_MAPPING_MISMATCH

    valid_stage = cast("StageResult", stages["GLIO-PROTEOGEN-M04-01"])
    changed_stage = valid_stage.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    stage_map = cast("dict[str, StageResult]", dict(cast("Mapping[str, StageResult]", stages)))
    stage_map["GLIO-PROTEOGEN-M04-01"] = changed_stage
    with pytest.raises(ProteoformReleaseInputError) as stage_mismatch:
        _validate_stage_results(request, artifacts, stage_map)
    assert stage_mismatch.value.code is ProteoformReleaseInputErrorCode.STAGE_RESULT_MISMATCH

    statement_mismatch = request.model_copy(
        update={
            "signature": request.signature.model_copy(
                update={"claimed_statement_digest": "sha256:" + "0" * 64}
            )
        }
    )
    quarantined = build_proteoform_release(statement_mismatch, artifacts, stages)
    assert quarantined.package_bytes is None

    verifier_id = request.policy.allowed_verifier_ids[0]
    unavailable = build_proteoform_release(
        request, artifacts, stages, _Verifier(verifier_id="wrong")
    )
    assert unavailable.package_bytes is None
    raised = build_proteoform_release(
        request, artifacts, stages, _Verifier(verifier_id=verifier_id, raise_error=True)
    )
    assert raised.package_bytes is None
    non_bool = build_proteoform_release(
        request, artifacts, stages, _Verifier(verifier_id=verifier_id, outcome="yes")
    )
    assert non_bool.package_bytes is None


def test_replay_cache_is_byte_keyed_after_full_canonical_admission() -> None:
    fixture = _fixture()
    module = "GLIO-PROTEOGEN-M04-01"
    path = next(path for path in fixture.artifacts if "m04-01" in path)
    content = fixture.artifacts[path]
    _parse_stage_artifact.cache_clear()

    first = _parse_stage_artifact(module, content)
    second = _parse_stage_artifact(module, bytes(content))

    assert first is second
    assert first == fixture.stages[module]
    with pytest.raises(ValueError, match=r".*"):
        _parse_stage_artifact(module, content + b" ")


class _ExplodingGet(dict[str, object]):
    def __init__(self, source: Mapping[str, bytes]) -> None:
        super().__init__(source)

    def __getitem__(self, _key: str) -> object:
        raise RuntimeError


def test_package_verification_precedence_and_canonicality(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _fixture()
    verifier_id = fixture.request.policy.allowed_verifier_ids[0]
    built = build_proteoform_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        _Verifier(verifier_id=verifier_id),
    )
    assert built.package_bytes is not None
    package = built.package_bytes
    descriptor = built.result.package_descriptor
    assert descriptor is not None

    inventory = _descriptor_proxy(built.result, member_updates={0: {"path": "alias.json"}})
    inventory_result = cast("ProteoformReleaseResult", _ResultProxy(built.result, inventory))
    assert (
        _verify_package(inventory_result, package, None).reason_code.value == "inventory_mismatch"
    )

    content = _descriptor_proxy(built.result, member_updates={0: {"digest": "sha256:" + "0" * 64}})
    content_result = cast("ProteoformReleaseResult", _ResultProxy(built.result, content))
    assert _verify_package(content_result, package, None).reason_code.value == "content_mismatch"

    members = list(inspect_canonical_ustar(package))
    members[0] = members[0].__class__(path=members[0].path, content=b"tampered")
    rebuilt_package = build_canonical_ustar(tuple(members))
    changed_members = tuple(
        item.model_copy(
            update={"byte_size": len(member.content), "digest": sha256_bytes(member.content)}
        )
        for item, member in zip(descriptor.members, members, strict=True)
    )
    changed_descriptor = descriptor.model_copy(
        update={
            "byte_size": len(rebuilt_package),
            "digest": sha256_bytes(rebuilt_package),
            "members": changed_members,
        }
    )
    changed_result = cast("ProteoformReleaseResult", _ResultProxy(built.result, changed_descriptor))
    assert (
        _verify_package(changed_result, rebuilt_package, None).reason_code.value
        == "manifest_mismatch"
    )

    def raise_archive(_value: object) -> Never:
        raise PackageAssemblyError.invalid_archive()

    monkeypatch.setattr(engine_module, "inspect_canonical_ustar", raise_archive)
    assert _verify_package(built.result, package, None).reason_code.value == "package_invalid"

    monkeypatch.setattr(engine_module, "inspect_canonical_ustar", inspect_canonical_ustar)
    monkeypatch.setattr(engine_module, "build_canonical_ustar", lambda *_args, **_kwargs: b"wrong")
    assert _verify_package(built.result, package, None).reason_code.value == "package_not_canonical"


def test_package_and_signature_verification_reject_hostile_outcomes() -> None:
    fixture = _fixture()
    verifier_id = fixture.request.policy.allowed_verifier_ids[0]
    built = build_proteoform_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        _Verifier(outcome=True, verifier_id=verifier_id),
    )
    assert built.package_bytes is not None

    too_large = _verify_package(built.result, b"x" * (M0408_MAX_PACKAGE_BYTES + 1), None)
    assert too_large.reason_code.value == "descriptor_mismatch"
    short = _verify_package(built.result, b"x", None)
    assert short.reason_code.value == "descriptor_mismatch"

    assert _verify_result_signature(built.result, None).reason_code is (
        ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE
    )
    assert _verify_result_signature(
        built.result, _Verifier(outcome=False, verifier_id=verifier_id)
    ).reason_code is (ProteoformSignatureVerificationReason.VERIFIER_REJECTED)
    assert _verify_result_signature(
        built.result, _Verifier(outcome="yes", verifier_id=verifier_id)
    ).reason_code is (ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE)
    assert (
        _verify_result_signature(built.result, _Verifier(outcome=False, verifier_id="wrong"))
        is not None
    )

    mismatched = SimpleNamespace(
        signature=built.result.signature.model_copy(
            update={"claimed_statement_digest": "sha256:" + "0" * 64}
        ),
        signature_verification=built.result.signature_verification,
        policy=built.result.policy,
    )
    assert (
        _verify_result_signature(cast("ProteoformReleaseResult", mismatched), None).reason_code
        is ProteoformSignatureVerificationReason.STATEMENT_MISMATCH
    )

    _require_authorized_context(fixture.request.context)
    _validate_context_opacity(fixture.request.context)
