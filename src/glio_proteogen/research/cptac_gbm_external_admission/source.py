"""Bounded exact-byte reads for privately staged external research sources."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .contracts import MAX_SOURCE_BYTES, SourceLock, SourceVerificationError


def _regular_snapshot(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    if not stat.S_ISREG(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise SourceVerificationError("source must be a regular non-link file")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        # Windows Python 3.12 path stat retains deprecated creation-time ctime,
        # while descriptor stat reports change time. Birth time is comparable.
        getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns),
    )


def read_verified_source(path: str | Path, lock: SourceLock, *, max_bytes: int) -> bytes:
    """Return exactly the bytes hashed, from one bounded read of one opened file.

    Leaf links/reparse points, changed file metadata, and replaced path bindings are
    rejected. Both the pre/post descriptor snapshots and path binding must agree;
    no separately hashed path is subsequently reopened for parsing.
    """

    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_SOURCE_BYTES:
        raise SourceVerificationError("source read bound is invalid")
    if not isinstance(lock, SourceLock) or lock.bytes > max_bytes:
        raise SourceVerificationError("source lock exceeds the read bound")
    try:
        source_path = Path(path)
        before = _regular_snapshot(source_path.lstat())
        if before[2] != lock.bytes:
            raise SourceVerificationError("source byte count did not match its lock")  # noqa: TRY301
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source_path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened_metadata = os.fstat(source.fileno())
            opened = _regular_snapshot(opened_metadata)
            if opened != before:
                raise SourceVerificationError("source binding changed during verification")  # noqa: TRY301
            payload = source.read(lock.bytes + 1)
            after_metadata = os.fstat(source.fileno())
            after = _regular_snapshot(after_metadata)
        if (
            opened != after
            or opened_metadata.st_ctime_ns != after_metadata.st_ctime_ns
            or before != _regular_snapshot(source_path.lstat())
        ):
            raise SourceVerificationError("source binding changed during verification")  # noqa: TRY301
        if len(payload) != lock.bytes:
            raise SourceVerificationError("source byte count did not match its lock")  # noqa: TRY301
        if (
            hashlib.md5(payload, usedforsecurity=False).hexdigest() != lock.md5
            or hashlib.sha256(payload).hexdigest() != lock.sha256
        ):
            raise SourceVerificationError("source checksums did not match its lock")  # noqa: TRY301
    except SourceVerificationError:
        raise
    except (OSError, TypeError, ValueError):
        raise SourceVerificationError("source could not be read and verified") from None
    return payload


__all__ = ["SourceLock", "SourceVerificationError", "read_verified_source"]
