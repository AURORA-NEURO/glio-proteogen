"""Substantive ABI-independent closure tests for M04-08-owned regions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m04_08 import (
    M0408_MANIFEST_PATH,
    M0408_MAX_ARTIFACT_BYTES,
    M0408_MAX_PACKAGE_BYTES,
    M0408_SIGNATURE_RECEIPT_PATH,
    ExternalProteoformSignature,
    ProteoformParentDiscordanceReceipt,
    ProteoformReferenceVersion,
    ProteoformReleaseArtifact,
    ProteoformReleaseArtifactRole,
    ProteoformReleaseMember,
    ProteoformReleasePackageDescriptor,
    ProteoformReleasePolicy,
    ProteoformReleaseQuarantine,
    ProteoformReleaseQuarantineCode,
    ProteoformReproductionEvidence,
    ProteoformSignatureAlgorithm,
    ProteoformSignatureVerification,
    ProteoformSignatureVerificationReason,
    ProteoformSoftwareVersion,
    ProteoformStageModuleId,
    ProteoformStageProvenance,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import (
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    _verify_external_signature,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.kernel import (
    ProteoformArchiveMemberInput,
    ProteoformReleaseAssemblyError,
    build_release_archive,
    verify_release_archive,
)

_NOW: Final = datetime(2026, 1, 1, tzinfo=UTC)
_ROLE_PATHS: Final = {
    ProteoformReleaseArtifactRole.PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF: (
        "parent/protein-rna-discordance-handoff.json"
    ),
    ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE: (
        "stages/m04-01-protocol-conformance.json"
    ),
    ProteoformReleaseArtifactRole.M04_02_IDENTITY_LINEAGE: ("stages/m04-02-identity-lineage.json"),
    ProteoformReleaseArtifactRole.M04_03_RAW_INGESTION: "stages/m04-03-raw-ingestion.json",
    ProteoformReleaseArtifactRole.M04_04_QUALITY: "stages/m04-04-quality.json",
    ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION: (
        "stages/m04-05-artifact-detection.json"
    ),
    ProteoformReleaseArtifactRole.M04_06_HARMONIZATION: "stages/m04-06-harmonization.json",
    ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT: "stages/m04-07-upstream-result.json",
}


def _digest(label: str) -> str:
    return sha256_digest({"m0408_owned_test": label})


def _opaque(namespace: str, label: str) -> str:
    return f"{namespace}.{_digest(label).removeprefix('sha256:')}"


def _evidence(label: str, *, value_digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_opaque("evidence", label),
        version="1.0.0",
        digest=value_digest or _digest(f"evidence:{label}"),
        media_type="application/json",
    )


def _known_artifact() -> ProteoformReleaseArtifact:
    return ProteoformReleaseArtifact(
        path="stages/m04-05-artifact-detection.json",
        role=ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION,
        reference=ArtifactReference(
            artifact_id=f"result.m0405.{_digest('m0405-request').removeprefix('sha256:')}",
            version="1.0.0",
            digest=_digest("m0405-bytes"),
            media_type="application/vnd.glio-proteogen.m04-05+json",
        ),
        declared_size=10,
    )


def _strict_mutation(model: BaseModel, **updates: object) -> BaseModel:
    payload = model.model_dump(mode="json")
    payload.update(updates)
    return model.__class__.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"path": "stages/../escape.json"}, "canonical safe relative POSIX"),
        ({"path": "stages/m04-04-quality.json"}, "fixed canonical path"),
        ({"declared_size": 0}, "greater than 0"),
        ({"declared_size": M0408_MAX_ARTIFACT_BYTES + 1}, "less than or equal"),
        (
            {
                "reference": {
                    "artifact_id": f"result.m0405.{_digest('wrong').removeprefix('sha256:')}",
                    "version": "1.0.0",
                    "digest": _digest("m0405-bytes"),
                    "media_type": "application/vnd.glio-proteogen.m04-04+json",
                }
            },
            "contradicts its fixed role",
        ),
    ],
)
def test_owned_artifact_rejects_path_size_and_reference_mutations(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _strict_mutation(_known_artifact(), **updates)


def test_owned_software_reference_and_parent_receipts_are_opaque_and_non_inferential() -> None:
    software = ProteoformSoftwareVersion(
        software_id=_opaque("software", "packager"),
        version="1.0.0",
        build_digest=_digest("software-build"),
        evidence=_evidence("software"),
    )
    reference = ProteoformReferenceVersion(
        reference_id=_opaque("reference", "proteome"),
        build_id=_opaque("build", "proteome"),
        version="2026.1",
        digest=_digest("reference-build"),
        evidence=_evidence("reference"),
    )
    parent = ProteoformParentDiscordanceReceipt(
        identity_resolution_digest=_digest("identity"),
        intended_use_evidence_digest=_digest("intended-use"),
        terminal_routing_result_digest=_digest("routing"),
    )

    assert software.software_id.startswith("software.")
    assert reference.reference_id.startswith("reference.")
    assert parent.parent_target == "protein_rna_discordance"
    assert parent.emits_protein_rna_discordance is False
    with pytest.raises(ValidationError, match="opaque software"):
        _strict_mutation(software, software_id="software.named")
    with pytest.raises(ValidationError, match="opaque build"):
        _strict_mutation(reference, build_id="build.named")


def test_owned_reproduction_evidence_requires_all_dossier_receipts_and_unique_digests() -> None:
    labels = tuple(ProteoformReproductionEvidence.model_fields)
    values = {label: _evidence(label) for label in labels}

    evidence = ProteoformReproductionEvidence(**values)
    assert tuple(type(evidence).model_fields) == labels

    duplicate = dict(values)
    duplicate["rollback"] = duplicate["reviewer_signoff"]
    with pytest.raises(ValidationError, match="digests must be unique"):
        ProteoformReproductionEvidence(**duplicate)


def _policy() -> ProteoformReleasePolicy:
    return ProteoformReleasePolicy(
        policy_id=_opaque("policy", "release"),
        version="1.0.0",
        allowed_signature_algorithms=(
            ProteoformSignatureAlgorithm.RSA_PSS_SHA256,
            ProteoformSignatureAlgorithm.ED25519,
        ),
        allowed_verifier_ids=(
            _opaque("verifier", "secondary"),
            _opaque("verifier", "primary"),
        ),
        evidence=_evidence("policy"),
        reviewed_by=_opaque("reviewer", "release"),
        reviewed_at=_NOW,
    )


def test_owned_policy_canonicalizes_allowlists_and_rejects_duplicates() -> None:
    policy = _policy()
    assert policy.allowed_signature_algorithms == tuple(sorted(policy.allowed_signature_algorithms))
    assert policy.allowed_verifier_ids == tuple(sorted(policy.allowed_verifier_ids))

    payload = policy.model_dump(mode="json")
    payload["allowed_verifier_ids"] = [policy.allowed_verifier_ids[0]] * 2
    with pytest.raises(ValidationError, match="allowlists must be unique"):
        ProteoformReleasePolicy.model_validate_json(canonical_json_bytes(payload), strict=True)


def _signature(*, statement_digest: str | None = None) -> ExternalProteoformSignature:
    return ExternalProteoformSignature(
        signer_id=_opaque("signer", "release"),
        key_id=_opaque("key", "release"),
        algorithm=ProteoformSignatureAlgorithm.ED25519,
        claimed_statement_digest=statement_digest or _digest("statement"),
        signature_value="c2lnbmF0dXJl",
        issued_at=_NOW,
        evidence=_evidence("signature"),
    )


def test_owned_external_signature_rejects_named_ids_and_unsafe_value_syntax() -> None:
    signature = _signature()
    with pytest.raises(ValidationError, match="opaque signer"):
        _strict_mutation(signature, signer_id="signer.named")
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        _strict_mutation(signature, signature_value="not a signature")


def _stage(
    module: ProteoformStageModuleId = ProteoformStageModuleId.M04_06,
    *,
    disposition: str = "accepted",
    upstream: tuple[str, ...] = (),
) -> ProteoformStageProvenance:
    return ProteoformStageProvenance(
        module_id=module,
        module_version="1.0.0",
        result_digest=_digest(f"result:{module}"),
        request_digest=_digest(f"request:{module}"),
        byte_digest=_digest(f"bytes:{module}"),
        disposition=disposition,
        generated_at=_NOW,
        configuration_digest=_digest(f"configuration:{module}"),
        identity_resolution_digest=_digest("identity"),
        bound_upstream_result_digests=upstream,
        human_review_required=False,
    )


def test_owned_known_stage_vocabulary_version_and_digest_set_are_closed() -> None:
    stage = _stage(upstream=(_digest("z"), _digest("a")))
    assert stage.bound_upstream_result_digests == tuple(sorted(stage.bound_upstream_result_digests))
    with pytest.raises(ValidationError, match="disposition contradicts"):
        _stage(disposition="supported")
    with pytest.raises(ValidationError, match=r"exactly 1\.0\.0"):
        _strict_mutation(stage, module_version="1.0.1")
    with pytest.raises(ValidationError, match="must be unique"):
        _stage(upstream=(_digest("same"), _digest("same")))


def test_owned_m0407_stage_vocabulary_remains_sealed_until_real_binding() -> None:
    with pytest.raises(ValidationError, match="disposition contradicts its module"):
        _stage(ProteoformStageModuleId.M04_07, disposition="unbound")


def test_owned_signature_verification_and_quarantine_shapes_are_relational() -> None:
    verifier_id = _opaque("verifier", "primary")
    verification = ProteoformSignatureVerification(
        verifier_id=verifier_id,
        algorithm=ProteoformSignatureAlgorithm.ED25519,
        key_id=_opaque("key", "release"),
        statement_digest=_digest("statement"),
        verified=True,
        reason_code=ProteoformSignatureVerificationReason.VERIFIED,
    )
    quarantine = ProteoformReleaseQuarantine(
        code=ProteoformReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
        stage_module_id=ProteoformStageModuleId.M04_06,
        reason_code="stage_disposition_abstained",
        remediation_code="review_upstream_stage",
    )
    assert verification.verified is True
    assert quarantine.stage_module_id is ProteoformStageModuleId.M04_06
    with pytest.raises(ValidationError, match="verified state contradicts"):
        _strict_mutation(verification, verified=False)
    with pytest.raises(ValidationError, match="only upstream"):
        _strict_mutation(quarantine, stage_module_id=None)


def _caller_members() -> tuple[ProteoformArchiveMemberInput, ...]:
    return tuple(
        ProteoformArchiveMemberInput(
            path=_ROLE_PATHS[role],
            role=role,
            content=canonical_json_bytes({"role": role.value}),
        )
        for role in ProteoformReleaseArtifactRole
    )


def test_owned_canonical_ustar_is_deterministic_and_descriptor_closed() -> None:
    members = _caller_members()
    manifest = canonical_json_bytes({"manifest": "owned-scaffold"})
    receipt = canonical_json_bytes({"signature_verification": "owned-scaffold"})

    first_bytes, first_descriptor = build_release_archive(
        members,
        manifest_bytes=manifest,
        signature_receipt_bytes=receipt,
    )
    second_bytes, second_descriptor = build_release_archive(
        tuple(reversed(members)),
        manifest_bytes=manifest,
        signature_receipt_bytes=receipt,
    )

    assert first_bytes == second_bytes
    assert first_descriptor == second_descriptor
    assert first_descriptor.byte_size == len(first_bytes)
    assert first_descriptor.digest == sha256_bytes(first_bytes)
    inspected = verify_release_archive(first_bytes, first_descriptor)
    assert tuple(item.path for item in inspected) == tuple(sorted(item.path for item in inspected))
    assert {item.path for item in inspected} >= {
        M0408_MANIFEST_PATH,
        M0408_SIGNATURE_RECEIPT_PATH,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_role",
        "duplicate_role",
        "bytes_subclass",
        "oversize_manifest",
    ],
)
def test_owned_archive_assembly_rejects_invalid_inventory_and_containers(mutation: str) -> None:
    members = list(_caller_members())
    manifest: bytes = b"{}"
    if mutation == "missing_role":
        caller: object = tuple(members[:-1])
    elif mutation == "duplicate_role":
        members[-1] = members[0]
        caller = tuple(members)
    elif mutation == "bytes_subclass":

        class _Bytes(bytes):
            pass

        members[0] = ProteoformArchiveMemberInput(
            path=members[0].path,
            role=members[0].role,
            content=_Bytes(b"{}"),
        )
        caller = tuple(members)
    else:
        caller = tuple(members)
        manifest = b"x" * (M0408_MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(ProteoformReleaseAssemblyError):
        build_release_archive(
            caller,  # type: ignore[arg-type]
            manifest_bytes=manifest,
            signature_receipt_bytes=b"{}",
        )


def test_owned_archive_verification_rejects_tampering_and_noncanonical_metadata() -> None:
    package, descriptor = build_release_archive(
        _caller_members(),
        manifest_bytes=b"{}",
        signature_receipt_bytes=b"{}",
    )
    tampered = package[:-1] + bytes((package[-1] ^ 1,))
    with pytest.raises(ProteoformReleaseAssemblyError, match="not the exact canonical"):
        verify_release_archive(tampered, descriptor)

    inspected = inspect_canonical_ustar(package)
    noncanonical = build_canonical_ustar(inspected, fixed_mtime=1)
    noncanonical_descriptor = descriptor.model_copy(update={"digest": sha256_bytes(noncanonical)})
    with pytest.raises(ProteoformReleaseAssemblyError, match="not the exact canonical"):
        verify_release_archive(noncanonical, noncanonical_descriptor)


class _Verifier:
    def __init__(self, verifier_id: str, outcome: object) -> None:
        self._verifier_id = verifier_id
        self._outcome = outcome
        self.calls = 0

    @property
    def verifier_id(self) -> str:
        return self._verifier_id

    def verify(self, *, statement_digest: str, signature: ExternalProteoformSignature) -> object:
        del statement_digest, signature
        self.calls += 1
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class _HostileVerifierAccessError(RuntimeError):
    """The verifier boundary was accessed before it was authorized."""


class _HostileVerifier:
    touched = False

    @property
    def verifier_id(self) -> str:
        type(self).touched = True
        raise _HostileVerifierAccessError

    def verify(self, *, statement_digest: str, signature: ExternalProteoformSignature) -> object:
        del statement_digest, signature
        type(self).touched = True
        raise _HostileVerifierAccessError


def test_owned_external_verifier_short_circuits_unreleasable_chain_before_access() -> None:
    _HostileVerifier.touched = False
    receipt = _verify_external_signature(
        signature=_signature(),
        statement_digest=_digest("statement"),
        allowed_verifier_ids=(_opaque("verifier", "primary"),),
        chain_releasable=False,
        verifier=_HostileVerifier(),
    )
    assert receipt.reason_code is ProteoformSignatureVerificationReason.NOT_ATTEMPTED
    assert _HostileVerifier.touched is False


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (True, ProteoformSignatureVerificationReason.VERIFIED),
        (False, ProteoformSignatureVerificationReason.VERIFIER_REJECTED),
        (1, ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE),
        (
            RuntimeError("offline"),
            ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE,
        ),
    ],
)
def test_owned_external_verifier_records_exact_boolean_or_safe_failure(
    outcome: object,
    reason: ProteoformSignatureVerificationReason,
) -> None:
    verifier_id = _opaque("verifier", "primary")
    verifier = _Verifier(verifier_id, outcome)
    receipt = _verify_external_signature(
        signature=_signature(),
        statement_digest=_digest("statement"),
        allowed_verifier_ids=(verifier_id,),
        chain_releasable=True,
        verifier=verifier,
    )
    assert receipt.reason_code is reason
    assert receipt.verified is (reason is ProteoformSignatureVerificationReason.VERIFIED)
    assert verifier.calls == 1


def test_owned_external_verifier_rejects_statement_mismatch_and_disallowed_id() -> None:
    allowed = _opaque("verifier", "allowed")
    verifier = _Verifier(verifier_id=_opaque("verifier", "other"), outcome=True)
    mismatch = _verify_external_signature(
        signature=_signature(statement_digest=_digest("claimed")),
        statement_digest=_digest("actual"),
        allowed_verifier_ids=(allowed,),
        chain_releasable=True,
        verifier=verifier,
    )
    assert mismatch.reason_code is ProteoformSignatureVerificationReason.STATEMENT_MISMATCH
    assert verifier.calls == 0

    unavailable = _verify_external_signature(
        signature=_signature(),
        statement_digest=_digest("statement"),
        allowed_verifier_ids=(allowed,),
        chain_releasable=True,
        verifier=verifier,
    )
    assert unavailable.reason_code is ProteoformSignatureVerificationReason.VERIFIER_UNAVAILABLE
    assert verifier.calls == 0


def test_owned_descriptor_rejects_missing_generated_members_and_wrong_ustar_size() -> None:
    package, descriptor = build_release_archive(
        _caller_members(),
        manifest_bytes=b"{}",
        signature_receipt_bytes=b"{}",
    )
    assert len(package) <= M0408_MAX_PACKAGE_BYTES
    payload = descriptor.model_dump(mode="json")
    payload["members"] = [*payload["members"][:-1], payload["members"][0]]
    with pytest.raises(ValidationError):
        ProteoformReleasePackageDescriptor.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
    with pytest.raises(ValidationError, match="USTAR framing"):
        _strict_mutation(descriptor, byte_size=descriptor.byte_size - 1)


def test_owned_release_member_distinguishes_generated_and_caller_roles() -> None:
    caller = ProteoformReleaseMember(
        path="stages/m04-06-harmonization.json",
        byte_size=2,
        digest=_digest("caller"),
        role=ProteoformReleaseArtifactRole.M04_06_HARMONIZATION,
    )
    generated = ProteoformReleaseMember(
        path=M0408_MANIFEST_PATH,
        byte_size=2,
        digest=_digest("manifest"),
    )
    assert caller.role is not None
    assert generated.role is None
    with pytest.raises(ValidationError, match="distinct role shapes"):
        _strict_mutation(generated, role=ProteoformReleaseArtifactRole.M04_06_HARMONIZATION.value)


def test_owned_package_member_inspection_never_extracts_to_disk() -> None:
    package = build_canonical_ustar((PackageMember(path="safe/member.json", content=b"{}"),))
    members = inspect_canonical_ustar(package)
    assert members == (PackageMember(path="safe/member.json", content=b"{}"),)
