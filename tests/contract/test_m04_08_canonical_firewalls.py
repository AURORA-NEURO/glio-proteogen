"""Canonicalization, archive, and fail-closed firewall coverage for M04-08."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m04_08 import (
    M0408_MANIFEST_PATH,
    BuildProteoformReleaseRequest,
    ExternalProteoformSignature,
    M0408DependencyUnavailableError,
    ProteoformPackageVerificationReason,
    ProteoformReleaseArtifact,
    ProteoformReleaseArtifactRole,
    ProteoformReleaseDisposition,
    ProteoformReleaseMember,
    ProteoformReleasePackageDescriptor,
    ProteoformReleaseResult,
    ProteoformReleaseVerification,
    ProteoformReproducibilityManifest,
    ProteoformSignatureAlgorithm,
    ProteoformSignatureVerification,
    ProteoformSignatureVerificationReason,
    ProteoformSoftwareVersion,
    ProteoformStageModuleId,
    artifact_digest,
    canonical_request_digest,
    context_digest,
    manifest_digest,
    normalized_artifact,
    normalized_manifest,
    normalized_policy,
    normalized_reproduction_evidence,
    normalized_request,
    normalized_result,
    normalized_result_payload,
    opaque_release_identifier,
    policy_digest,
    reproduction_evidence_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.contracts.m04_08.v1 import (
    _bind_m0407_contract,
    _require_authorized_context,
    _validate_context_opacity,
    _validate_member_path,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import (
    PackageAssemblyError,
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    M0408Plugin,
    M0408Service,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    kernel as release_kernel,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    BuiltProteoformRelease,
    _BuiltReleaseInvariantError,
    _verify_external_signature,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.kernel import (
    ProteoformArchiveMemberInput,
    ProteoformReleaseAssemblyError,
    build_release_archive,
    verify_release_archive,
)


def _digest(label: str) -> str:
    return sha256_digest({"m0408_firewall_test": label})


def _opaque(namespace: str, label: str) -> str:
    return f"{namespace}.{_digest(label).removeprefix('sha256:')}"


def _evidence(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_opaque("evidence", label),
        version="1.0.0",
        digest=_digest(f"evidence:{label}"),
        media_type=media_type,
    )


def _authorized_context() -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=_opaque("decision", label),
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_evidence(f"decision:{label}"),
        )

    return ExecutionContext(
        request_id=_opaque("request", "authorized"),
        actor_id=_opaque("actor", "authorized"),
        occurred_at=datetime(2026, 8, 14, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id=_opaque("decision", "identity"),
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_evidence("decision:identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id=_opaque("decision", "consent"),
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_evidence("decision:consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def test_canonical_helpers_sort_owned_sets_without_mutating_callers() -> None:
    artifact = {"path": "z.json", "role": "z", "reference": {"digest": _digest("z")}}
    policy = {
        "allowed_signature_algorithms": ["rsa_pss_sha256", "ed25519"],
        "allowed_verifier_ids": ["verifier.z", "verifier.a"],
        "policy_id": "policy.test",
    }
    reproduction = {"rollback": {"digest": _digest("rollback")}}
    manifest = {
        "artifacts": [{"path": "z"}, {"path": "a"}],
        "stages": [
            {
                "module_id": "GLIO-PROTEOGEN-M04-01",
                "bound_upstream_result_digests": [_digest("z"), _digest("a")],
            }
        ],
        "software_versions": [{"software_id": "software.z"}, {"software_id": "software.a"}],
        "reference_versions": [{"reference_id": "reference.z"}, {"reference_id": "reference.a"}],
    }
    request = {
        "artifacts": [artifact, {"path": "a.json", "role": "a"}],
        "software_versions": manifest["software_versions"],
        "reference_versions": manifest["reference_versions"],
        "reproduction_evidence": reproduction,
        "policy": policy,
    }
    result = {
        "result_digest": _digest("placeholder"),
        "policy": policy,
        "manifest": manifest,
        "quarantine_reasons": [{"reason": "z"}, {"reason": "a"}],
        "package_descriptor": {
            "members": [{"path": "z"}, {"path": "a"}],
        },
        "provenance": {
            "input_digests": [_digest("z"), _digest("a")],
            "control_decisions": [{"role": "z"}, {"role": "a"}],
        },
        "evidence": [{"claim": "z"}, {"claim": "a"}],
        "limitations": [{"code": "z"}, {"code": "a"}],
    }
    original_request = canonical_json_bytes(request)

    assert normalized_artifact(artifact) == artifact
    artifact_model = _evidence("canonical-model")
    assert normalized_artifact(artifact_model) == artifact_model.model_dump(
        mode="python", by_alias=True, exclude_none=False
    )
    assert artifact_digest(artifact) == sha256_digest(artifact)
    assert normalized_policy(policy)["allowed_signature_algorithms"] == [
        "ed25519",
        "rsa_pss_sha256",
    ]
    assert policy_digest(policy) == sha256_digest(normalized_policy(policy))
    assert normalized_reproduction_evidence(reproduction) == reproduction
    assert reproduction_evidence_digest(reproduction) == sha256_digest(reproduction)
    assert context_digest({"context": "owned"}) == sha256_digest({"context": "owned"})
    normalized_manifest_value = normalized_manifest(manifest)
    normalized_artifacts = cast("list[dict[str, object]]", normalized_manifest_value["artifacts"])
    normalized_stages = cast("list[dict[str, object]]", normalized_manifest_value["stages"])
    source_stages = cast("list[dict[str, object]]", manifest["stages"])
    assert normalized_artifacts[0]["path"] == "a"
    assert normalized_stages[0]["bound_upstream_result_digests"] == sorted(
        cast("list[str]", source_stages[0]["bound_upstream_result_digests"])
    )
    assert manifest_digest(manifest) == sha256_digest(normalized_manifest_value)
    assert canonical_request_digest(request) == sha256_digest(normalized_request(request))
    normalized_result_value = normalized_result_payload(result)
    assert "result_digest" not in normalized_result_value
    assert normalized_result(result) == normalized_result_value
    assert result_payload_digest(result) == sha256_digest(normalized_result_value)
    assert (
        normalized_result_payload({**result, "package_descriptor": None})["package_descriptor"]
        is None
    )
    assert canonical_json_bytes(request) == original_request


def test_signing_statement_is_domain_separated_and_binds_every_owned_receipt() -> None:
    values = {
        "active_manifest_digest": _digest("manifest"),
        "active_policy_digest": _digest("policy"),
        "release_id": _opaque("release", "release"),
        "release_version": "1.0.0",
        "identity_resolution_digest": _digest("identity"),
        "intended_use_evidence_digest": _digest("intended-use"),
        "terminal_routing_result_digest": _digest("routing"),
    }
    first = signing_statement_digest(**values)
    assert first == signing_statement_digest(**values)
    for field in (
        "active_manifest_digest",
        "active_policy_digest",
        "identity_resolution_digest",
        "intended_use_evidence_digest",
        "terminal_routing_result_digest",
    ):
        mutated = dict(values)
        mutated[field] = _digest(f"mutated:{field}")
        assert signing_statement_digest(**mutated) != first


@pytest.mark.parametrize(
    "arguments",
    [
        {"media_type": "Application/JSON"},
        {"artifact_id_prefix": "Result.M0407."},
        {"dispositions": frozenset()},
        {
            "dispositions": frozenset({"one"}),
            "releasable_dispositions": frozenset({"other"}),
        },
    ],
)
def test_unfrozen_m0407_binding_rejects_invalid_inputs_without_installing(
    arguments: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "artifact_id_pattern": r"^result\.m0407\.[0-9a-f]{64}$",
        "artifact_id_prefix": "result.m0407.",
        "media_type": "application/vnd.glio-proteogen.m04-07+json",
        "dispositions": frozenset({"supported", "abstained"}),
        "releasable_dispositions": frozenset({"supported"}),
        "direct_upstream_modules": (ProteoformStageModuleId.M04_06,),
    }
    values.update(arguments)
    with pytest.raises(ValueError, match="M04-07"):
        _bind_m0407_contract(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    [
        "évidence.json",
        "/absolute.json",
        "C:drive.json",
        "folder\\member.json",
        "folder/../member.json",
        f"{'n' * 101}.json",
        f"{'p' * 156}/member.json",
    ],
)
def test_member_path_firewall_rejects_non_ascii_absolute_alias_and_ustar_overflow(
    path: str,
) -> None:
    with pytest.raises(ValueError, match="release member path"):
        _validate_member_path(path)


def test_artifact_reserved_namespace_and_member_role_path_are_fail_closed() -> None:
    with pytest.raises(ValidationError, match="reserved M04-08 namespace"):
        ProteoformReleaseArtifact(
            path=M0408_MANIFEST_PATH,
            role=ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE,
            reference=_evidence("reserved-artifact"),
            declared_size=2,
        )
    with pytest.raises(ValidationError, match="fixed canonical path"):
        ProteoformReleaseMember(
            path="stages/m04-05-artifact-detection.json",
            byte_size=2,
            digest=_digest("wrong-role-path"),
            role=ProteoformReleaseArtifactRole.M04_06_HARMONIZATION,
        )


def test_dependency_independent_field_validators_are_strict_and_canonical() -> None:
    release_id = _opaque("release", "validator")
    result_id = _opaque("result", "m0408-validator")
    result_id = f"result.m0408.{result_id.rsplit('.', maxsplit=1)[1]}"
    assert BuildProteoformReleaseRequest.release_is_opaque(release_id) == release_id
    assert ProteoformReproducibilityManifest.release_is_opaque(release_id) == release_id
    assert ProteoformReleaseResult.result_id_has_exact_shape(result_id) == result_id
    with pytest.raises(ValueError, match="opaque release"):
        BuildProteoformReleaseRequest.release_is_opaque("release.named")
    with pytest.raises(ValueError, match="opaque release"):
        ProteoformReproducibilityManifest.release_is_opaque("release.named")
    with pytest.raises(ValueError, match="opaque M04-08 result"):
        ProteoformReleaseResult.result_id_has_exact_shape("result.m0408.named")

    values = ({"sort": "z"}, {"sort": "a"})
    expected = tuple(sorted(values, key=canonical_json_bytes))
    assert BuildProteoformReleaseRequest.records_are_canonical(values) == expected
    assert ProteoformReproducibilityManifest.records_are_canonical(values) == expected
    assert ProteoformReleaseResult.result_collections_are_canonical(values) == expected


def test_opaque_namespace_and_owned_evidence_media_type_are_strict() -> None:
    with pytest.raises(ValueError, match="namespace is not canonical"):
        opaque_release_identifier("Release-ID", {"release": 1})
    with pytest.raises(ValidationError, match="lowercase type/subtype"):
        ProteoformSoftwareVersion(
            software_id=_opaque("software", "packager"),
            version="1.0.0",
            build_digest=_digest("build"),
            evidence=_evidence("software", media_type="Application/JSON"),
        )


def _signature() -> ExternalProteoformSignature:
    return ExternalProteoformSignature(
        signer_id=_opaque("signer", "release"),
        key_id=_opaque("key", "release"),
        algorithm=ProteoformSignatureAlgorithm.ED25519,
        claimed_statement_digest=_digest("statement"),
        signature_value="c2lnbmF0dXJl",
        issued_at=datetime(2026, 1, 1, tzinfo=UTC),
        evidence=_evidence("signature"),
    )


class _VerifierPropertyError(RuntimeError):
    """The injected verifier failed while exposing its identifier."""


class _PropertyFailureVerifier:
    @property
    def verifier_id(self) -> str:
        raise _VerifierPropertyError

    def verify(self, *, statement_digest: str, signature: ExternalProteoformSignature) -> object:
        del statement_digest, signature
        return True


class _NonStringIdVerifier:
    @property
    def verifier_id(self) -> str:
        return cast("str", 7)

    def verify(self, *, statement_digest: str, signature: ExternalProteoformSignature) -> object:
        del statement_digest, signature
        return True


@pytest.mark.parametrize("verifier", [_PropertyFailureVerifier(), _NonStringIdVerifier(), None])
def test_external_verifier_identifier_failures_are_typed_unavailable(verifier: object) -> None:
    receipt = _verify_external_signature(
        signature=_signature(),
        statement_digest=_digest("statement"),
        allowed_verifier_ids=(_opaque("verifier", "allowed"),),
        chain_releasable=True,
        verifier=verifier,  # type: ignore[arg-type]
    )
    assert receipt.reason_code is ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE


def test_external_verifier_rejects_non_tuple_allowlist_and_non_boolean_chain_state() -> None:
    for allowed, chain in (
        (cast("tuple[str, ...]", ["verifier.invalid"]), True),
        ((_opaque("verifier", "allowed"),), cast("bool", 1)),
    ):
        receipt = _verify_external_signature(
            signature=_signature(),
            statement_digest=_digest("statement"),
            allowed_verifier_ids=allowed,
            chain_releasable=chain,
            verifier=None,
        )
        expected = (
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE
            if type(allowed) is not tuple
            else ProteoformSignatureVerificationReason.NOT_ATTEMPTED
        )
        assert receipt.reason_code is expected


def _caller_members() -> tuple[ProteoformArchiveMemberInput, ...]:
    paths = (
        "parent/protein-rna-discordance-handoff.json",
        "stages/m04-01-protocol-conformance.json",
        "stages/m04-02-identity-lineage.json",
        "stages/m04-03-raw-ingestion.json",
        "stages/m04-04-quality.json",
        "stages/m04-05-artifact-detection.json",
        "stages/m04-06-harmonization.json",
        "stages/m04-07-upstream-result.json",
    )
    return tuple(
        ProteoformArchiveMemberInput(
            path=path,
            role=role,
            content=canonical_json_bytes({"role": role.value}),
        )
        for role, path in zip(ProteoformReleaseArtifactRole, paths, strict=True)
    )


def _archive() -> tuple[bytes, ProteoformReleasePackageDescriptor]:
    return build_release_archive(
        _caller_members(),
        manifest_bytes=b"{}",
        signature_receipt_bytes=b"{}",
    )


def test_archive_assembly_wraps_kernel_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> bytes:
        del args, kwargs
        raise PackageAssemblyError.invalid_archive()

    monkeypatch.setattr(release_kernel, "build_canonical_ustar", fail)
    with pytest.raises(ProteoformReleaseAssemblyError, match="not the exact"):
        build_release_archive(
            _caller_members(),
            manifest_bytes=b"{}",
            signature_receipt_bytes=b"{}",
        )


def test_archive_verification_rejects_invalid_tar_member_count_path_and_digest() -> None:
    package, descriptor = _archive()

    malformed = b"not-a-tar"
    malformed_descriptor = descriptor.model_copy(
        update={"byte_size": len(malformed), "digest": sha256_bytes(malformed)}
    )
    with pytest.raises(ProteoformReleaseAssemblyError):
        verify_release_archive(malformed, malformed_descriptor)

    one_member = build_canonical_ustar((PackageMember(path="only.json", content=b"{}"),))
    one_descriptor = descriptor.model_copy(
        update={"byte_size": len(one_member), "digest": sha256_bytes(one_member)}
    )
    with pytest.raises(ProteoformReleaseAssemblyError):
        verify_release_archive(one_member, one_descriptor)

    members = list(inspect_canonical_ustar(package))
    members[0] = PackageMember(path="different.json", content=members[0].content)
    different_path = build_canonical_ustar(tuple(members))
    path_descriptor = descriptor.model_copy(
        update={"byte_size": len(different_path), "digest": sha256_bytes(different_path)}
    )
    with pytest.raises(ProteoformReleaseAssemblyError):
        verify_release_archive(different_path, path_descriptor)

    receipts = list(descriptor.members)
    receipts[0] = receipts[0].model_copy(update={"digest": _digest("wrong-member")})
    digest_descriptor = descriptor.model_copy(update={"members": tuple(receipts)})
    with pytest.raises(ProteoformReleaseAssemblyError):
        verify_release_archive(package, digest_descriptor)


def test_descriptor_defensive_inventory_rejects_forged_nested_instances() -> None:
    _, descriptor = _archive()
    members = list(descriptor.members)
    manifest_index = next(
        index for index, member in enumerate(members) if member.path == M0408_MANIFEST_PATH
    )
    members[manifest_index] = members[manifest_index].model_copy(
        update={"path": "META-INF/glio-proteogen-m04-08/other.json"}
    )
    missing_generated = descriptor.model_copy(update={"members": tuple(members)})
    with pytest.raises(ValueError, match="both generated members"):
        missing_generated.inventory_is_exact_and_unique()  # type: ignore[operator]

    members = list(descriptor.members)
    caller_index = next(index for index, member in enumerate(members) if member.role is not None)
    members[caller_index] = members[caller_index].model_copy(update={"role": None})
    missing_role = descriptor.model_copy(update={"members": tuple(members)})
    with pytest.raises(ValueError, match="every caller artifact role"):
        missing_role.inventory_is_exact_and_unique()  # type: ignore[operator]


def test_archive_rejects_exact_container_and_empty_generated_member_failures() -> None:
    members = _caller_members()
    invalid_member_tuple = (object(), *members[1:])
    with pytest.raises(ProteoformReleaseAssemblyError, match="exact built-in"):
        build_release_archive(
            invalid_member_tuple,  # type: ignore[arg-type]
            manifest_bytes=b"{}",
            signature_receipt_bytes=b"{}",
        )
    for manifest, receipt in ((b"", b"{}"), (b"{}", b"")):
        with pytest.raises(ProteoformReleaseAssemblyError, match="byte profile"):
            build_release_archive(
                members,
                manifest_bytes=manifest,
                signature_receipt_bytes=receipt,
            )


def test_archive_assembly_enforces_the_package_ceiling_after_canonical_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release_kernel, "M0408_MAX_PACKAGE_BYTES", 1)
    with pytest.raises(ProteoformReleaseAssemblyError, match="byte profile"):
        build_release_archive(
            _caller_members(),
            manifest_bytes=b"{}",
            signature_receipt_bytes=b"{}",
        )


def test_service_facade_preserves_fail_closed_runtime_boundary() -> None:
    service = M0408Service()
    for operation in (
        lambda: service.execute(object(), {}, {}),
        lambda: service.manifest(object(), {}, {}),
        lambda: service.verify(object(), b""),
    ):
        with pytest.raises(RuntimeError, match="exact frozen M04-07"):
            operation()

    plugin = M0408Plugin(service)
    with pytest.raises(M0408DependencyUnavailableError, match="frozen M04-07"):
        plugin.run(object())  # type: ignore[arg-type]


class _ResultStub:
    def __init__(self, disposition: ProteoformReleaseDisposition) -> None:
        self.disposition = disposition


def test_built_release_dataclass_enforces_package_byte_presence() -> None:
    released = cast("object", _ResultStub(ProteoformReleaseDisposition.RELEASED))
    quarantined = cast("object", _ResultStub(ProteoformReleaseDisposition.QUARANTINED))
    BuiltProteoformRelease(result=released, package_bytes=b"package")  # type: ignore[arg-type]
    BuiltProteoformRelease(result=quarantined, package_bytes=None)  # type: ignore[arg-type]
    with pytest.raises(_BuiltReleaseInvariantError):
        BuiltProteoformRelease(result=released, package_bytes=None)  # type: ignore[arg-type]


def _signature_receipt(*, verified: bool) -> ProteoformSignatureVerification:
    return ProteoformSignatureVerification(
        verifier_id=_opaque("verifier", "primary") if verified else None,
        algorithm=ProteoformSignatureAlgorithm.ED25519,
        key_id=_opaque("key", "release"),
        statement_digest=_digest("statement"),
        verified=verified,
        reason_code=(
            ProteoformSignatureVerificationReason.VERIFIED
            if verified
            else ProteoformSignatureVerificationReason.NOT_ATTEMPTED
        ),
    )


def test_package_verification_model_closes_content_authenticity_and_reason() -> None:
    verified = ProteoformReleaseVerification(
        content_verified=True,
        authenticity_verified=True,
        verified=True,
        package_digest=_digest("package"),
        manifest_digest=_digest("manifest"),
        member_count=10,
        signature_verification=_signature_receipt(verified=True),
        reason_code=ProteoformPackageVerificationReason.VERIFIED,
    )
    assert verified.verified is True
    payload = verified.model_dump(mode="json")
    mutations = (
        {"authenticity_verified": False},
        {"verified": False},
        {"reason_code": ProteoformPackageVerificationReason.PACKAGE_INVALID.value},
        {"package_digest": None},
        {"manifest_digest": None},
        {"member_count": 9},
    )
    for update in mutations:
        candidate = {**payload, **update}
        with pytest.raises(ValidationError):
            ProteoformReleaseVerification.model_validate_json(
                canonical_json_bytes(candidate), strict=True
            )

    failed = ProteoformReleaseVerification(
        content_verified=False,
        authenticity_verified=False,
        verified=False,
        member_count=0,
        signature_verification=_signature_receipt(verified=False),
        reason_code=ProteoformPackageVerificationReason.PACKAGE_INVALID,
    )
    assert failed.verified is False


def test_signature_verification_requires_verifier_id_only_for_attempted_outcomes() -> None:
    base = _signature_receipt(verified=False).model_dump(mode="json")
    for update in (
        {
            "reason_code": ProteoformSignatureVerificationReason.VERIFIER_REJECTED.value,
            "verifier_id": None,
        },
        {
            "reason_code": ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE.value,
            "verifier_id": _opaque("verifier", "unexpected"),
        },
    ):
        with pytest.raises(ValidationError, match="verifier identifier"):
            ProteoformSignatureVerification.model_validate_json(
                canonical_json_bytes({**base, **update}), strict=True
            )


def test_manifest_path_constant_is_reserved_owned_namespace() -> None:
    assert M0408_MANIFEST_PATH.startswith("META-INF/glio-proteogen-m04-08/")


def _context_with_reference_update(
    context: ExecutionContext,
    role: str,
    update: dict[str, object],
) -> ExecutionContext:
    reference = getattr(context.references, role)
    references = context.references.model_copy(update={role: reference.model_copy(update=update)})
    return context.model_copy(update={"references": references})


def test_context_authorization_accepts_only_every_explicit_authority_grant() -> None:
    context = _authorized_context()
    _require_authorized_context(context)
    _validate_context_opacity(context)

    for consent_state in (
        ConsentState.WITHHELD,
        ConsentState.REVOKED,
        ConsentState.UNKNOWN,
    ):
        denied = _context_with_reference_update(context, "consent", {"state": consent_state})
        with pytest.raises(ValueError, match="consent does not authorize"):
            _require_authorized_context(denied)

    for identity_state in (
        IdentityLineageState.UNRESOLVED,
        IdentityLineageState.CONFLICTED,
    ):
        unresolved = _context_with_reference_update(
            context, "identity_lineage", {"state": identity_state}
        )
        with pytest.raises(ValueError, match="identity lineage is not resolved"):
            _require_authorized_context(unresolved)

    for role in (
        "approved_configuration",
        "provenance",
        "quality",
        "support",
        "intended_use",
    ):
        for upstream_state in (
            UpstreamDecisionState.REJECTED,
            UpstreamDecisionState.UNKNOWN,
        ):
            rejected = _context_with_reference_update(context, role, {"state": upstream_state})
            with pytest.raises(ValueError, match="upstream controls do not authorize"):
                _require_authorized_context(rejected)


def test_context_opacity_rejects_named_ids_and_unowned_control_evidence() -> None:
    context = _authorized_context()
    for field in ("request_id", "actor_id"):
        named = context.model_copy(update={field: f"{field.removesuffix('_id')}.named"})
        with pytest.raises(ValueError, match="identifier must be an opaque"):
            _validate_context_opacity(named)

    for role in (
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ):
        named = _context_with_reference_update(context, role, {"decision_id": "decision.named"})
        with pytest.raises(ValueError, match="opaque decision digest alias"):
            _validate_context_opacity(named)

    wrong_id = _context_with_reference_update(
        context,
        "approved_configuration",
        {"evidence": _evidence("wrong-id").model_copy(update={"artifact_id": "record.named"})},
    )
    with pytest.raises(ValueError, match="opaque evidence digest alias"):
        _validate_context_opacity(wrong_id)

    wrong_media = _context_with_reference_update(
        context,
        "intended_use",
        {"evidence": _evidence("wrong-media", media_type="Application/JSON")},
    )
    with pytest.raises(ValueError, match="lowercase type/subtype syntax"):
        _validate_context_opacity(wrong_media)
