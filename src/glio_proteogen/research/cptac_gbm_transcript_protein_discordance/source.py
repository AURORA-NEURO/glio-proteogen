"""Private exact-snapshot staging for local discordance fitting."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Final, Iterator

from glio_proteogen.research.cptac_gbm_cis_dosage.source import HGNC_LOCK, TABLE_S2_LOCK

from .errors import DiscordanceSourceLockError

EXACT_SOURCE_LOCKS: Final = (TABLE_S2_LOCK, HGNC_LOCK)
_COPY_BLOCK_BYTES: Final = 4 * 1_024 * 1_024


@dataclass(frozen=True, slots=True)
class _StagedSources:
    table_s2: Path
    hgnc: Path


def _copy_exact_stream(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    expected_bytes: int,
    expected_sha256: str,
    block_bytes: int = _COPY_BLOCK_BYTES,
) -> None:
    """Copy at most the exact length plus one while hashing the staged snapshot."""

    digest = hashlib.sha256()
    copied = 0
    while copied <= expected_bytes:
        requested = min(block_bytes, expected_bytes + 1 - copied)
        chunk = source.read(requested)
        if not chunk:
            break
        copied += len(chunk)
        digest.update(chunk)
        destination.write(chunk)
    observed_digest = "sha256:" + digest.hexdigest()
    if copied != expected_bytes or observed_digest != expected_sha256:
        raise DiscordanceSourceLockError(
            "local discordance source changed or did not match its exact lock"
        )


def _stage_exact_file(
    source: Path,
    destination: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    try:
        with source.open("rb") as incoming, destination.open("xb") as staged:
            _copy_exact_stream(
                incoming,
                staged,
                expected_bytes=expected_bytes,
                expected_sha256=expected_sha256,
            )
            staged.flush()
            os.fsync(staged.fileno())
        destination.chmod(stat.S_IRUSR)
    except DiscordanceSourceLockError:
        raise
    except OSError as error:
        raise DiscordanceSourceLockError(
            "local discordance source could not be staged privately"
        ) from error


@contextmanager
def _stage_exact_sources(*, table_s2: Path, hgnc: Path) -> Iterator[_StagedSources]:
    """Yield immutable exact snapshots and remove them on every normal error path."""

    temporary = TemporaryDirectory(prefix=".cptac-gbm-discordance-stage-")
    root = Path(temporary.name)
    root.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    staged_s2 = root / "table-s2.xlsx"
    staged_hgnc = root / "hgnc.tsv"
    try:
        _stage_exact_file(
            table_s2,
            staged_s2,
            expected_bytes=TABLE_S2_LOCK.bytes,
            expected_sha256=TABLE_S2_LOCK.sha256,
        )
        _stage_exact_file(
            hgnc,
            staged_hgnc,
            expected_bytes=HGNC_LOCK.bytes,
            expected_sha256=HGNC_LOCK.sha256,
        )
        yield _StagedSources(table_s2=staged_s2, hgnc=staged_hgnc)
    finally:
        for staged_file in (staged_s2, staged_hgnc):
            if staged_file.exists():
                staged_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        temporary.cleanup()


__all__ = ["EXACT_SOURCE_LOCKS"]
