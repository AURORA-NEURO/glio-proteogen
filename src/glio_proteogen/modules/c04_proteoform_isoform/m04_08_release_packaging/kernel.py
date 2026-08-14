"""M04-08-owned deterministic archive assembly independent of M04-07 semantics."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m04_08 import (
    M0408_ARCHIVE_MEMBER_COUNT,
    M0408_CALLER_ARTIFACT_COUNT,
    M0408_MANIFEST_PATH,
    M0408_MAX_ARTIFACT_BYTES,
    M0408_MAX_PACKAGE_BYTES,
    M0408_MAX_TOTAL_ARTIFACT_BYTES,
    M0408_SIGNATURE_RECEIPT_PATH,
    ProteoformReleaseArtifactRole,
    ProteoformReleaseMember,
    ProteoformReleasePackageDescriptor,
)
from glio_proteogen.kernel.canonical_ustar import (
    PackageAssemblyError,
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)


class ProteoformReleaseAssemblyError(ValueError):
    """An owned archive input or package violates the M04-08 profile."""

    @classmethod
    def invalid_input(cls) -> ProteoformReleaseAssemblyError:
        return cls("M04-08 archive inputs must use exact built-in immutable containers")

    @classmethod
    def invalid_inventory(cls) -> ProteoformReleaseAssemblyError:
        return cls("M04-08 archive inventory is not exact and role-closed")

    @classmethod
    def invalid_size(cls) -> ProteoformReleaseAssemblyError:
        return cls("M04-08 archive input or package exceeds its installed byte profile")

    @classmethod
    def invalid_package(cls) -> ProteoformReleaseAssemblyError:
        return cls("M04-08 package is not the exact canonical archive described by its receipt")


@dataclass(frozen=True, slots=True)
class ProteoformArchiveMemberInput:
    """One M04-08-owned package role paired with immutable canonical bytes."""

    path: str
    role: ProteoformReleaseArtifactRole
    content: bytes


def _exact_bytes(value: object) -> bytes:
    if type(value) is not bytes:
        raise ProteoformReleaseAssemblyError.invalid_input()
    return value


def build_release_archive(
    caller_members: tuple[ProteoformArchiveMemberInput, ...],
    *,
    manifest_bytes: bytes,
    signature_receipt_bytes: bytes,
    fixed_mtime: int = 0,
    file_mode: int = 0o644,
) -> tuple[bytes, ProteoformReleasePackageDescriptor]:
    """Assemble the exact ten-member package without interpreting stage content."""

    if type(caller_members) is not tuple or len(caller_members) != M0408_CALLER_ARTIFACT_COUNT:
        raise ProteoformReleaseAssemblyError.invalid_inventory()
    if any(type(item) is not ProteoformArchiveMemberInput for item in caller_members):
        raise ProteoformReleaseAssemblyError.invalid_input()
    caller_content = tuple(_exact_bytes(item.content) for item in caller_members)
    manifest_content = _exact_bytes(manifest_bytes)
    receipt_content = _exact_bytes(signature_receipt_bytes)
    if (
        any(not content or len(content) > M0408_MAX_ARTIFACT_BYTES for content in caller_content)
        or sum(map(len, caller_content)) > M0408_MAX_TOTAL_ARTIFACT_BYTES
        or not manifest_content
        or not receipt_content
        or len(manifest_content) > M0408_MAX_ARTIFACT_BYTES
        or len(receipt_content) > M0408_MAX_ARTIFACT_BYTES
    ):
        raise ProteoformReleaseAssemblyError.invalid_size()
    roles = tuple(item.role for item in caller_members)
    paths = tuple(item.path for item in caller_members)
    if (
        set(roles) != set(ProteoformReleaseArtifactRole)
        or len(set(roles)) != len(roles)
        or len(set(paths)) != len(paths)
        or len({path.casefold() for path in paths}) != len(paths)
    ):
        raise ProteoformReleaseAssemblyError.invalid_inventory()
    caller_receipts = tuple(
        ProteoformReleaseMember(
            path=item.path,
            byte_size=len(item.content),
            digest=sha256_bytes(item.content),
            role=item.role,
        )
        for item in caller_members
    )
    package_members = (
        *(PackageMember(path=item.path, content=item.content) for item in caller_members),
        PackageMember(path=M0408_MANIFEST_PATH, content=manifest_content),
        PackageMember(path=M0408_SIGNATURE_RECEIPT_PATH, content=receipt_content),
    )
    try:
        package_bytes = build_canonical_ustar(
            package_members,
            fixed_mtime=fixed_mtime,
            file_mode=file_mode,
        )
    except PackageAssemblyError as error:
        raise ProteoformReleaseAssemblyError.invalid_package() from error
    if len(package_bytes) > M0408_MAX_PACKAGE_BYTES:
        raise ProteoformReleaseAssemblyError.invalid_size()
    generated_receipts = (
        ProteoformReleaseMember(
            path=M0408_MANIFEST_PATH,
            byte_size=len(manifest_content),
            digest=sha256_bytes(manifest_content),
        ),
        ProteoformReleaseMember(
            path=M0408_SIGNATURE_RECEIPT_PATH,
            byte_size=len(receipt_content),
            digest=sha256_bytes(receipt_content),
        ),
    )
    descriptor = ProteoformReleasePackageDescriptor(
        byte_size=len(package_bytes),
        digest=sha256_bytes(package_bytes),
        members=(*caller_receipts, *generated_receipts),
    )
    return package_bytes, descriptor


def verify_release_archive(
    package_bytes: bytes,
    descriptor: ProteoformReleasePackageDescriptor,
) -> tuple[PackageMember, ...]:
    """Verify exact content, inventory, metadata, ordering, and canonical USTAR bytes."""

    content = _exact_bytes(package_bytes)
    if (
        not content
        or len(content) > M0408_MAX_PACKAGE_BYTES
        or descriptor.byte_size != len(content)
        or descriptor.digest != sha256_bytes(content)
        or descriptor.member_count != M0408_ARCHIVE_MEMBER_COUNT
    ):
        raise ProteoformReleaseAssemblyError.invalid_package()
    try:
        members = inspect_canonical_ustar(content)
    except PackageAssemblyError as error:
        raise ProteoformReleaseAssemblyError.invalid_package() from error
    if len(members) != M0408_ARCHIVE_MEMBER_COUNT:
        raise ProteoformReleaseAssemblyError.invalid_package()
    descriptor_by_path = {item.path: item for item in descriptor.members}
    if set(descriptor_by_path) != {item.path for item in members}:
        raise ProteoformReleaseAssemblyError.invalid_package()
    if any(
        receipt.byte_size != len(member.content) or receipt.digest != sha256_bytes(member.content)
        for member in members
        for receipt in (descriptor_by_path[member.path],)
    ):
        raise ProteoformReleaseAssemblyError.invalid_package()
    rebuilt = build_canonical_ustar(members)
    if rebuilt != content:
        raise ProteoformReleaseAssemblyError.invalid_package()
    return members


__all__ = [
    "ProteoformArchiveMemberInput",
    "ProteoformReleaseAssemblyError",
    "build_release_archive",
    "verify_release_archive",
]
