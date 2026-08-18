"""Focused tests for the M01-08 deterministic archive kernel."""

from __future__ import annotations

import io
import tarfile

import pytest

from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging.kernel import (
    PackageMember,
    build_canonical_ustar,
    inspect_canonical_ustar,
    sha256_bytes,
)


def test_canonical_archive_is_order_independent() -> None:
    members = (
        PackageMember("results/c.txt", b"three\n"),
        PackageMember("metadata/a.json", b"{}\n"),
        PackageMember("tables/b.tsv", b"x\ty\n"),
    )

    first = build_canonical_ustar(members)
    replay = build_canonical_ustar(tuple(reversed(members)))

    assert first == replay
    assert sha256_bytes(first) == sha256_bytes(replay)
    assert inspect_canonical_ustar(first) == tuple(sorted(members, key=lambda item: item.path))


def test_duplicate_member_path_rejects() -> None:
    members = (PackageMember("same.txt", b"a"), PackageMember("same.txt", b"b"))

    with pytest.raises(ValueError, match="unique"):
        build_canonical_ustar(members)


def test_duplicate_archive_path_rejects() -> None:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for content in (b"a", b"b"):
            info = tarfile.TarInfo("same.txt")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))

    with pytest.raises(ValueError, match="unique"):
        inspect_canonical_ustar(target.getvalue())


def test_invalid_archive_rejects() -> None:
    with pytest.raises(ValueError, match="invalid canonical USTAR"):
        inspect_canonical_ustar(b"not a tar")
