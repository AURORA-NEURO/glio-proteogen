"""Focused lifecycle checks for the M03-08 release-packaging runtime."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import NoReturn, cast

import pytest
from evals.m03_06 import run as m0306_evidence
from evals.m03_08 import run as m0308_evidence
from evals.m03_08.run import (
    DeterministicNonCryptographicVerifier,
    Scenario,
    build_scenario,
)

from glio_proteogen.contracts.m03_06 import configuration_digest
from glio_proteogen.contracts.m03_08 import (
    M0308_ARCHIVE_MEMBER_COUNT,
    M0308_MAX_PACKAGE_BYTES,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceReleaseDisposition,
    ProteinInferenceReleaseQuarantineCode,
    ProteinInferenceSignatureVerificationReason,
    ProteinInferenceStageModuleId,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.canonical_ustar import sha256_bytes
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    harmonize_protein_inference_support,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    M0308Plugin,
    M0308Service,
    ProteinInferenceReleaseAuthorizationError,
    ProteinInferenceReleaseInputError,
    ProteinInferenceReleaseInputErrorCode,
    ProteinInferenceReleaseSubmission,
    build_protein_inference_release,
    build_protein_inference_release_manifest,
    verify_protein_inference_release,
)

_BUILD_AND_VERIFY_CALL_COUNT = 2


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


class _TraversalTrap(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def _fail(self) -> NoReturn:
        self.traversals += 1
        raise _PrematureTraversalError

    def __getitem__(self, key: str) -> object:
        del key
        self._fail()

    def __iter__(self) -> Iterator[str]:
        self._fail()

    def __len__(self) -> int:  # noqa: PLE0303 - intentional hostile traversal trap.
        self._fail()


class _PrematureTraversalError(AssertionError):
    """A caller-controlled mapping was touched before authorization."""


class _HostileAccessor:
    def __init__(self) -> None:
        object.__setattr__(self, "touches", 0)

    def __getattribute__(self, field: str) -> object:
        if field == "touches":
            return object.__getattribute__(self, field)
        touches = object.__getattribute__(self, "touches")
        assert isinstance(touches, int)
        object.__setattr__(self, "touches", touches + 1)
        raise _PrematureTraversalError


class _VerifierBaseException(BaseException):
    """Sentinel proving injected verifier base exceptions are not swallowed."""


class _VerifierError(RuntimeError):
    """Sentinel proving ordinary injected verifier failures close safely."""


class _VerifierIdSubclass(str):
    """A hostile string subtype that must not cross the verifier boundary."""

    __slots__ = ()


class _BytesSubclass(bytes):
    __slots__ = ()


class _BoundaryVerifier:
    def __init__(self, boundary: str, verifier_id: str) -> None:
        self.boundary = boundary
        self._verifier_id = verifier_id
        self.id_accesses = 0
        self.verify_calls = 0

    @property
    def verifier_id(self) -> str:
        self.id_accesses += 1
        if self.boundary == "id_exception":
            raise _VerifierError
        if self.boundary == "id_base_exception":
            raise _VerifierBaseException
        if self.boundary == "id_subclass":
            return _VerifierIdSubclass(self._verifier_id)
        return self._verifier_id

    def verify(self, **_kwargs: object) -> object:
        self.verify_calls += 1
        if self.boundary == "verify_exception":
            raise _VerifierError
        if self.boundary == "verify_base_exception":
            raise _VerifierBaseException
        if self.boundary == "non_bool":
            return 1
        return self.boundary == "accepted"


def test_genuine_chain_builds_and_verifies_one_canonical_release(scenario: Scenario) -> None:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    assert built.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
    assert built.package_bytes is not None
    assert built.result.package_descriptor is not None
    assert built.result.package_descriptor.member_count == M0308_ARCHIVE_MEMBER_COUNT
    assert len(scenario.verifier.calls) == 1

    verified = verify_protein_inference_release(
        built.result,
        built.package_bytes,
        scenario.verifier,
    )
    assert verified.verified
    assert verified.content_verified
    assert verified.authenticity_verified
    assert verified.reason_code is ProteinInferencePackageVerificationReason.VERIFIED
    assert verified.member_count == M0308_ARCHIVE_MEMBER_COUNT
    assert len(scenario.verifier.calls) == _BUILD_AND_VERIFY_CALL_COUNT


def test_manifest_builder_is_deterministic_and_never_invokes_verifier(
    scenario: Scenario,
) -> None:
    verifier = DeterministicNonCryptographicVerifier()
    service = M0308Service(verifier)
    direct = build_protein_inference_release_manifest(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
    )
    assert (
        service.build_manifest(
            scenario.request,
            scenario.artifacts,
            scenario.stages,
        )
        == direct
    )
    assert not verifier.calls


def test_missing_verifier_quarantines_without_allocating_package_bytes(
    scenario: Scenario,
) -> None:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
    )
    assert built.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
    assert built.package_bytes is None
    assert built.result.package_descriptor is None
    assert (
        built.result.signature_verification.reason_code
        is ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE
    )


@pytest.mark.parametrize(
    ("boundary", "reason", "verify_calls", "package_state"),
    [
        (
            "id_exception",
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
            0,
            "absent",
        ),
        (
            "id_subclass",
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
            0,
            "absent",
        ),
        (
            "verify_exception",
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
            1,
            "absent",
        ),
        (
            "non_bool",
            ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE,
            1,
            "absent",
        ),
        (
            "rejected",
            ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED,
            1,
            "absent",
        ),
        (
            "accepted",
            ProteinInferenceSignatureVerificationReason.VERIFIED,
            1,
            "present",
        ),
    ],
)
def test_injected_verifier_fail_closed_boundaries_and_exact_call_counts(
    scenario: Scenario,
    boundary: str,
    reason: ProteinInferenceSignatureVerificationReason,
    verify_calls: int,
    package_state: str,
) -> None:
    verifier = _BoundaryVerifier(boundary, scenario.request.policy.allowed_verifier_ids[0])
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        verifier,
    )
    assert built.result.signature_verification.reason_code is reason
    assert ("present" if built.package_bytes is not None else "absent") == package_state
    assert verifier.id_accesses == 1
    assert verifier.verify_calls == verify_calls


@pytest.mark.parametrize("boundary", ["id_base_exception", "verify_base_exception"])
def test_injected_verifier_base_exceptions_propagate(
    scenario: Scenario,
    boundary: str,
) -> None:
    verifier = _BoundaryVerifier(boundary, scenario.request.policy.allowed_verifier_ids[0])
    with pytest.raises(_VerifierBaseException):
        build_protein_inference_release(
            scenario.request,
            scenario.artifacts,
            scenario.stages,
            verifier,
        )
    assert verifier.id_accesses == 1
    assert verifier.verify_calls == (boundary == "verify_base_exception")


def test_statement_mismatch_quarantines_before_verifier(scenario: Scenario) -> None:
    signature = scenario.request.signature.model_copy(
        update={"claimed_statement_digest": sha256_digest("wrong-m0308-statement")}
    )
    request = type(scenario.request).model_validate(
        scenario.request.model_copy(update={"signature": signature}).model_dump(mode="python"),
        strict=True,
    )
    verifier = DeterministicNonCryptographicVerifier()
    built = build_protein_inference_release(
        request,
        scenario.artifacts,
        scenario.stages,
        verifier,
    )
    assert built.package_bytes is None
    assert not verifier.calls
    assert (
        built.result.signature_verification.reason_code
        is ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH
    )


def test_genuine_post_analysis_m0306_quarantine_never_reaches_verifier() -> None:
    m0306 = m0306_evidence.build_scenario()
    policy = m0306.request.policy.model_copy(update={"max_absolute_shift_ppm": 1_000})
    references = m0306.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = m0306.request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    request = type(m0306.request).model_validate(
        {
            **m0306.request.model_dump(mode="python"),
            "context": context,
            "policy": policy,
        },
        strict=True,
    )
    harmonization = harmonize_protein_inference_support(request)
    assert harmonization.disposition.value == "quarantined"
    assert harmonization.analysis is not None
    assert harmonization.transformation_manifest is not None

    base = m0308_evidence.build_genuine_chain()
    chain = m0308_evidence._downstream_chain(
        protocol=base.protocol,
        identity=base.identity,
        ingestion=base.ingestion,
        quality=base.quality,
        artifact=base.artifact_detection,
        harmonization=harmonization,
        label="m0308-post-analysis-m0306-quarantine",
    )
    fixture = m0308_evidence._sign_fixture(m0308_evidence._unsigned_fixture(chain=chain))
    verifier = DeterministicNonCryptographicVerifier()
    built = build_protein_inference_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        verifier,
    )
    reason = next(
        item
        for item in built.result.quarantine_reasons
        if item.stage_module_id is ProteinInferenceStageModuleId.M03_06
    )
    assert built.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
    assert reason.code is ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE
    assert built.package_bytes is None
    assert built.result.package_descriptor is None
    assert not verifier.calls


def test_denied_control_precedes_both_hostile_mapping_traversals(scenario: Scenario) -> None:
    request = scenario.request.model_dump(mode="python")
    request["context"]["references"]["consent"]["state"] = "withheld"
    artifacts = _TraversalTrap()
    stages = _TraversalTrap()
    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        build_protein_inference_release(request, artifacts, stages)
    assert artifacts.traversals == stages.traversals == 0


def test_arbitrary_mapping_is_not_a_preflight_request() -> None:
    request = _TraversalTrap()
    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        build_protein_inference_release(request, _TraversalTrap(), _TraversalTrap())
    assert request.traversals == 0


def test_raw_dict_with_hostile_nested_context_is_denied_without_traversal() -> None:
    context = _TraversalTrap()
    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        build_protein_inference_release(
            {"context": context},
            _TraversalTrap(),
            _TraversalTrap(),
        )
    assert context.traversals == 0


@pytest.mark.parametrize("position", ["context", "reference"])
def test_raw_dict_hostile_accessors_are_denied_without_property_access(position: str) -> None:
    hostile = _HostileAccessor()
    candidate: dict[str, object]
    if position == "context":
        candidate = {"context": hostile}
    else:
        candidate = {"context": {"references": {"consent": hostile}}}
    with pytest.raises(ProteinInferenceReleaseAuthorizationError):
        build_protein_inference_release(candidate, _TraversalTrap(), _TraversalTrap())
    assert hostile.touches == 0


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        ("artifacts", ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH),
        ("stages", ProteinInferenceReleaseInputErrorCode.STAGE_MAPPING_MISMATCH),
    ],
)
def test_exact_mapping_sets_are_required(
    scenario: Scenario,
    boundary: str,
    expected: ProteinInferenceReleaseInputErrorCode,
) -> None:
    artifacts: dict[str, object] = dict(scenario.artifacts)
    stages: dict[str, object] = dict(scenario.stages)
    (artifacts if boundary == "artifacts" else stages).pop(
        next(iter(artifacts if boundary == "artifacts" else stages))
    )
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release(
            scenario.request,
            artifacts,
            stages,
            DeterministicNonCryptographicVerifier(),
        )
    assert caught.value.code is expected


@pytest.mark.parametrize("content", [bytearray(b"x"), _BytesSubclass(b"x")])
def test_artifact_boundary_requires_exact_immutable_bytes(
    scenario: Scenario,
    content: object,
) -> None:
    artifacts: dict[str, object] = dict(scenario.artifacts)
    artifacts[next(iter(artifacts))] = content
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            scenario.request,
            artifacts,
            scenario.stages,
        )
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.ARTIFACT_TYPE_INVALID


@pytest.mark.parametrize("content", [bytearray(b"x"), _BytesSubclass(b"x")])
def test_package_boundary_requires_exact_immutable_bytes(
    scenario: Scenario,
    content: object,
) -> None:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        DeterministicNonCryptographicVerifier(),
    )
    with pytest.raises(TypeError, match="immutable bytes"):
        verify_protein_inference_release(built.result, cast("bytes", content))


def test_invalid_supplied_stage_is_result_mismatch_not_json_failure(
    scenario: Scenario,
) -> None:
    stages: dict[str, object] = dict(scenario.stages)
    stages["GLIO-PROTEOGEN-M03-04"] = {}
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            scenario.request,
            scenario.artifacts,
            stages,
        )
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.STAGE_RESULT_MISMATCH


@pytest.mark.parametrize("forgery", ["model_construct", "wrong_type", "mismatch"])
def test_supplied_stage_object_boundary_rejects_forgeries_without_replay(
    scenario: Scenario,
    forgery: str,
) -> None:
    stages: dict[str, object] = dict(scenario.stages)
    module = "GLIO-PROTEOGEN-M03-04"
    stage = scenario.stages[module]
    if forgery == "model_construct":
        values = dict(stage.__dict__)
        values["result_digest"] = sha256_digest("forged-m0304-result")
        supplied: object = type(stage).model_construct(**values)
    elif forgery == "wrong_type":
        supplied = scenario.stages["GLIO-PROTEOGEN-M03-05"]
    else:
        supplied = stage.model_copy(
            update={"result_digest": sha256_digest("different-m0304-result")}
        )
    stages[module] = supplied
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            scenario.request,
            scenario.artifacts,
            stages,
        )
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.STAGE_RESULT_MISMATCH


@pytest.mark.parametrize("control", ["identity", "quality", "support"])
def test_manifest_only_path_rejects_request_control_masking(
    scenario: Scenario,
    control: str,
) -> None:
    references = scenario.request.context.references
    wrong = sha256_digest({"wrong_m0308_control": control})
    if control == "identity":
        update = {
            "identity_lineage": references.identity_lineage.model_copy(
                update={"binding_digest": wrong}
            )
        }
    else:
        reference = getattr(references, control)
        update = {
            control: reference.model_copy(
                update={"evidence": reference.evidence.model_copy(update={"digest": wrong})}
            )
        }
    context = scenario.request.context.model_copy(
        update={"references": references.model_copy(update=update)}
    )
    request = scenario.request.model_copy(update={"context": context})
    with pytest.raises(ProteinInferenceReleaseInputError) as caught:
        build_protein_inference_release_manifest(
            request,
            scenario.artifacts,
            scenario.stages,
        )
    assert caught.value.code is ProteinInferenceReleaseInputErrorCode.CHAIN_MISMATCH


def test_plugin_requires_submission_and_validated_execution_token(scenario: Scenario) -> None:
    verifier = DeterministicNonCryptographicVerifier()
    plugin = M0308Plugin(M0308Service(verifier))
    submission = ProteinInferenceReleaseSubmission(
        scenario.request.model_dump_json().encode(),
        scenario.artifacts,
        scenario.stages,
    )
    token = plugin.validate(submission)
    built = plugin.run(token)
    assert built.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
    assert plugin.descriptor().owner == "Computational biology"
    assert len(verifier.calls) == 1
    with pytest.raises(TypeError, match="validation requires"):
        plugin.validate(scenario.request)
    with pytest.raises(TypeError, match="execution requires"):
        plugin.run(object())  # type: ignore[arg-type]


def test_verification_rejects_oversize_before_hash_or_tar(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        DeterministicNonCryptographicVerifier(),
    )
    monkeypatch.setattr(
        "glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine.sha256_bytes",
        lambda _value: (_ for _ in ()).throw(AssertionError("hash traversed")),
    )
    monkeypatch.setattr(
        "glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine.inspect_canonical_ustar",
        lambda _value: (_ for _ in ()).throw(AssertionError("tar traversed")),
    )
    verification = verify_protein_inference_release(
        built.result,
        bytes(M0308_MAX_PACKAGE_BYTES + 1),
    )
    assert not verification.content_verified
    assert verification.reason_code is ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH
    assert (
        verification.signature_verification.reason_code
        is ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
    )


def test_archive_header_size_cap_precedes_shared_member_reads(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        DeterministicNonCryptographicVerifier(),
    )
    assert built.package_bytes is not None
    hostile = bytearray(built.package_bytes)
    hostile[124:136] = f"{M0308_MAX_PACKAGE_BYTES:o}".encode().rjust(11, b"0") + b"\0"
    hostile[148:156] = b"        "
    checksum = sum(hostile[:512])
    hostile[148:156] = f"{checksum:o}".encode().rjust(6, b"0") + b"\0 "
    package = bytes(hostile)
    descriptor = built.result.package_descriptor
    assert descriptor is not None
    forged_descriptor = descriptor.model_copy(
        update={
            "byte_size": len(package),
            "digest": sha256_bytes(package),
        }
    )
    payload = built.result.model_dump(mode="python")
    payload["package_descriptor"] = forged_descriptor.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(payload)
    result = type(built.result).model_validate(
        payload,
        strict=True,
    )
    monkeypatch.setattr(
        "glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine.inspect_canonical_ustar",
        lambda _value: (_ for _ in ()).throw(AssertionError("shared reader traversed")),
    )
    verification = verify_protein_inference_release(result, package)
    assert verification.reason_code is ProteinInferencePackageVerificationReason.PACKAGE_INVALID


def test_release_result_recursively_excludes_biological_canaries(scenario: Scenario) -> None:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        DeterministicNonCryptographicVerifier(),
    )
    serialized = json.dumps(
        built.result.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    for canary in (
        "MPEPTIDEK",
        "P12345",
        "ENSP00000354587",
        "chr7:140453136:A:T",
        "EGFRvIII",
        "patient-raw-001",
    ):
        assert canary not in serialized
