"""Small deterministic USTAR assembly kernel for M01-08."""

from __future__ import annotations

import hashlib
import io
import tarfile
from dataclasses import dataclass


class PackageAssemblyError(ValueError):
    """Canonical package bytes or members violate the closed archive profile."""

    @classmethod
    def duplicate_paths(cls) -> PackageAssemblyError:
        return cls("package member paths must be unique")

    @classmethod
    def non_regular(cls) -> PackageAssemblyError:
        return cls("package contains a non-regular member")

    @classmethod
    def missing_content(cls) -> PackageAssemblyError:
        return cls("package member content is unavailable")

    @classmethod
    def invalid_archive(cls) -> PackageAssemblyError:
        return cls("invalid canonical USTAR package")


@dataclass(frozen=True, slots=True)
class PackageMember:
    """One already-validated canonical member and its immutable bytes."""

    path: str
    content: bytes


def sha256_bytes(content: bytes) -> str:
    """Return the repository's tagged SHA-256 representation."""

    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def build_canonical_ustar(
    members: tuple[PackageMember, ...],
    *,
    fixed_mtime: int = 0,
    file_mode: int = 0o644,
) -> bytes:
    """Assemble sorted regular-file members with fixed USTAR metadata."""

    ordered = tuple(sorted(members, key=lambda item: item.path))
    paths = tuple(item.path for item in ordered)
    if len(paths) != len(set(paths)):
        raise PackageAssemblyError.duplicate_paths()

    target = io.BytesIO()
    try:
        with tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for member in ordered:
                info = tarfile.TarInfo(member.path)
                info.size = len(member.content)
                info.mtime = fixed_mtime
                info.mode = file_mode
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.type = tarfile.REGTYPE
                archive.addfile(info, io.BytesIO(member.content))
    except (ValueError, UnicodeError) as error:
        raise PackageAssemblyError.invalid_archive() from error
    return target.getvalue()


def inspect_canonical_ustar(package_bytes: bytes) -> tuple[PackageMember, ...]:
    """Read regular USTAR members without extracting them to a filesystem."""

    members: list[PackageMember] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(package_bytes), mode="r:") as archive:
            for info in archive.getmembers():
                if not info.isfile():
                    raise PackageAssemblyError.non_regular()
                source = archive.extractfile(info)
                if source is None:
                    raise PackageAssemblyError.missing_content()
                members.append(PackageMember(path=info.name, content=source.read()))
    except (tarfile.TarError, OSError) as error:
        raise PackageAssemblyError.invalid_archive() from error
    return tuple(members)


__all__ = [
    "PackageAssemblyError",
    "PackageMember",
    "build_canonical_ustar",
    "inspect_canonical_ustar",
    "sha256_bytes",
]
