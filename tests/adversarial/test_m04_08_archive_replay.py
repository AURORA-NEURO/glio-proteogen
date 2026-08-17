"""Adversarial archive replay checks for the M04-08 release boundary."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m04_08 import ProteoformReleaseArtifactRole
from glio_proteogen.kernel.canonical_ustar import sha256_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    ProteoformArchiveMemberInput,
    ProteoformReleaseAssemblyError,
    build_release_archive,
    verify_release_archive,
)

_ROLE_PATHS = {
    ProteoformReleaseArtifactRole.PARENT_PROTEIN_RNA_DISCORDANCE_HANDOFF: (
        "parent/protein-rna-discordance-handoff.json"
    ),
    ProteoformReleaseArtifactRole.M04_01_PROTOCOL_CONFORMANCE: (
        "stages/m04-01-protocol-conformance.json"
    ),
    ProteoformReleaseArtifactRole.M04_02_IDENTITY_LINEAGE: "stages/m04-02-identity-lineage.json",
    ProteoformReleaseArtifactRole.M04_03_RAW_INGESTION: "stages/m04-03-raw-ingestion.json",
    ProteoformReleaseArtifactRole.M04_04_QUALITY: "stages/m04-04-quality.json",
    ProteoformReleaseArtifactRole.M04_05_ARTIFACT_DETECTION: (
        "stages/m04-05-artifact-detection.json"
    ),
    ProteoformReleaseArtifactRole.M04_06_HARMONIZATION: "stages/m04-06-harmonization.json",
    ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT: "stages/m04-07-upstream-result.json",
}


def _members() -> tuple[ProteoformArchiveMemberInput, ...]:
    return tuple(
        ProteoformArchiveMemberInput(
            path=path,
            role=role,
            content=f'{{"role":"{role}"}}'.encode(),
        )
        for role, path in _ROLE_PATHS.items()
    )


def test_archive_replay_is_byte_exact_and_descriptor_closed() -> None:
    package, descriptor = build_release_archive(
        _members(), manifest_bytes=b"manifest", signature_receipt_bytes=b"receipt"
    )

    inspected = verify_release_archive(package, descriptor)

    assert len(inspected) == descriptor.member_count
    assert descriptor.digest == sha256_bytes(package)


def test_archive_replay_rejects_single_byte_tamper() -> None:
    package, descriptor = build_release_archive(
        _members(), manifest_bytes=b"manifest", signature_receipt_bytes=b"receipt"
    )
    tampered = bytearray(package)
    tampered[-513] ^= 1

    with pytest.raises(ProteoformReleaseAssemblyError, match="canonical archive"):
        verify_release_archive(bytes(tampered), descriptor)


def test_archive_replay_rejects_descriptor_digest_tamper() -> None:
    package, descriptor = build_release_archive(
        _members(), manifest_bytes=b"manifest", signature_receipt_bytes=b"receipt"
    )
    invalid_descriptor = descriptor.model_copy(update={"digest": "sha256:" + "0" * 64})

    with pytest.raises(ProteoformReleaseAssemblyError, match="canonical archive"):
        verify_release_archive(package, invalid_descriptor)
