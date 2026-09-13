"""Exact local source locks for CPTAC GBM cis-dosage fitting."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Final, Iterator

from .contracts import ExactSourceLock, SourceVerification, SourceVerificationResult
from .errors import SourceLockError

TABLE_S2_LOCK: Final = ExactSourceLock(
    source_id="cptac-gbm-table-s2",
    sha256="sha256:59c33b6140c88c394da50fd7461774233074dda12361df7989fe51b8b8e28a13",
    bytes=129_239_538,
    required_for_fit=True,
)
TABLE_S3_LOCK: Final = ExactSourceLock(
    source_id="cptac-gbm-table-s3",
    sha256="sha256:098b596756a84c4744b934f25dc5b9a1e49f992827e2d1223179dfb4655f08f5",
    bytes=357_622,
    required_for_fit=False,
)
HGNC_LOCK: Final = ExactSourceLock(
    source_id="hgnc-approved-snapshot",
    sha256="sha256:854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270",
    bytes=16_948_224,
    required_for_fit=True,
)
EXACT_SOURCE_LOCKS: Final = (TABLE_S2_LOCK, TABLE_S3_LOCK, HGNC_LOCK)
_COPY_BLOCK_BYTES: Final = 4 * 1_024 * 1_024


@dataclass(frozen=True, slots=True)
class _StagedSources:
    table_s2: Path
    hgnc: Path
    table_s3: Path | None


def _copy_exact_stream(
    source: BinaryIO,
    destination: BinaryIO,
    lock: ExactSourceLock,
    *,
    block_bytes: int = _COPY_BLOCK_BYTES,
) -> None:
    """Copy at most the expected bytes plus one while hashing the staged snapshot."""

    digest = hashlib.sha256()
    copied = 0
    while copied <= lock.bytes:
        requested = min(block_bytes, lock.bytes + 1 - copied)
        chunk = source.read(requested)
        if not chunk:
            break
        copied += len(chunk)
        digest.update(chunk)
        destination.write(chunk)
    observed_digest = "sha256:" + digest.hexdigest()
    if copied != lock.bytes or observed_digest != lock.sha256:
        raise SourceLockError("local source changed or did not match its exact lock while staging")


def _stage_exact_file(source: Path, destination: Path, lock: ExactSourceLock) -> None:
    try:
        with source.open("rb") as incoming, destination.open("xb") as staged:
            _copy_exact_stream(incoming, staged, lock)
            staged.flush()
            os.fsync(staged.fileno())
        destination.chmod(stat.S_IRUSR)
    except SourceLockError:
        raise
    except OSError as error:
        raise SourceLockError("local source could not be staged privately") from error


@contextmanager
def _stage_exact_sources(
    *,
    table_s2: Path,
    hgnc: Path,
    table_s3: Path | None,
) -> Iterator[_StagedSources]:
    """Yield private read-only exact snapshots and clean them on every exit path."""

    temporary = TemporaryDirectory(prefix=".cptac-gbm-cis-stage-")
    root = Path(temporary.name)
    root.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    staged_s2 = root / "table-s2.xlsx"
    staged_hgnc = root / "hgnc.tsv"
    staged_s3 = root / "table-s3.xlsx" if table_s3 is not None else None
    try:
        _stage_exact_file(table_s2, staged_s2, TABLE_S2_LOCK)
        _stage_exact_file(hgnc, staged_hgnc, HGNC_LOCK)
        if table_s3 is not None and staged_s3 is not None:
            _stage_exact_file(table_s3, staged_s3, TABLE_S3_LOCK)
        yield _StagedSources(table_s2=staged_s2, hgnc=staged_hgnc, table_s3=staged_s3)
    finally:
        for staged_file in (staged_s2, staged_hgnc, staged_s3):
            if staged_file is not None and staged_file.exists():
                staged_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        temporary.cleanup()


def sha256_file(path: Path, *, block_bytes: int = 4 * 1_024 * 1_024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_bytes):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def verify_one_source(path: Path, lock: ExactSourceLock) -> SourceVerification:
    observed_bytes = path.stat().st_size
    observed_digest = sha256_file(path)
    return SourceVerification(
        source_id=lock.source_id,
        expected_digest=lock.sha256,
        observed_digest=observed_digest,
        expected_bytes=lock.bytes,
        observed_bytes=observed_bytes,
        verified=observed_bytes == lock.bytes and observed_digest == lock.sha256,
    )


def verify_sources(
    *,
    table_s2: Path,
    hgnc: Path,
    table_s3: Path | None = None,
    raise_on_mismatch: bool = False,
) -> SourceVerificationResult:
    checks = [verify_one_source(table_s2, TABLE_S2_LOCK), verify_one_source(hgnc, HGNC_LOCK)]
    if table_s3 is not None:
        checks.append(verify_one_source(table_s3, TABLE_S3_LOCK))
    result = SourceVerificationResult(
        verified=all(check.verified for check in checks),
        sources=tuple(checks),
    )
    if raise_on_mismatch and not result.verified:
        raise SourceLockError("one or more local CPTAC/HGNC sources do not match exact locks")
    return result


__all__ = [
    "EXACT_SOURCE_LOCKS",
    "HGNC_LOCK",
    "TABLE_S2_LOCK",
    "TABLE_S3_LOCK",
    "sha256_file",
    "verify_one_source",
    "verify_sources",
]
