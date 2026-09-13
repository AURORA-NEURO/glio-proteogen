# ruff: noqa: TRY003
"""Fingerprint the exact GBmap H5AD without admitting, copying, or parsing it.

The production entry point has no caller-overridable byte lock or repository
boundary. A separately reviewed SHA-256 may be compared, but even a match is
only evidence for a later source-admission review; this tool never grants model
or runtime admission.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapSourceAdmissionError
from glio_proteogen.research.gbmap_deconvolution.extraction import (
    ZENODO_SOURCE_BYTES,
    ZENODO_SOURCE_ID,
    ZENODO_SOURCE_MD5,
    ExactGbmapH5adLock,
    SourceFingerprint,
    fingerprint_gbmap_source,
)

RECEIPT_SCHEMA: Final = "gbmap-source-admission-receipt/1.0.0"
PRODUCTION_ARTIFACT_NAME: Final = "scarches_core_GBmap.h5ad"
_TEST_RECEIPT_SCHEMA: Final = "gbmap-source-admission-fixture-receipt/1.0.0-test-only"
_TEST_SOURCE_ID: Final = "gbmap-synthetic-fixture-no-source-identity"
_TEST_ARTIFACT_NAME: Final = "synthetic-fixture.h5ad"
_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_MD5_PATTERN: Final = re.compile(r"^[0-9a-f]{32}$")
_SAFE_SOURCE_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")
_SAFE_ARTIFACT_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_TEMP_PREFIX: Final = ".gbmap-source-receipt-"
_TEMP_SUFFIX: Final = ".tmp"

AdmissionState = Literal[
    "fingerprinted_not_admitted",
    "review_digest_matches_not_admitted",
    "review_digest_mismatch_not_admitted",
]
_ExistingReceiptState = Literal["missing", "identical", "different", "unavailable"]
_PublicationState = Literal["published", "conflict", "failed"]


@dataclass(frozen=True, slots=True)
class _SourceExpectation:
    expected_bytes: int
    expected_md5: str

    def __post_init__(self) -> None:
        if type(self.expected_bytes) is not int or self.expected_bytes <= 0:
            raise ValueError("expected_bytes must be an exact positive integer")
        if _MD5_PATTERN.fullmatch(self.expected_md5) is None:
            raise ValueError("expected_md5 must be canonical lowercase hexadecimal")


_PRODUCTION_EXPECTATION: Final = _SourceExpectation(
    expected_bytes=ZENODO_SOURCE_BYTES,
    expected_md5=ZENODO_SOURCE_MD5,
)


class _ReceiptBase(FrozenModel):
    """Shared closed evidence shape; concrete subclasses bind their identity."""

    schema_version: str = Field(min_length=1, max_length=128)
    receipt_digest: Sha256Digest
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,127}$")
    artifact_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
    source_bytes: int = Field(gt=0)
    source_md5: str = Field(pattern=r"^[0-9a-f]{32}$")
    source_sha256: Sha256Digest
    byte_size_match: Literal[True] = True
    official_md5_match: Literal[True] = True
    reviewed_sha256: Sha256Digest | None
    review_match: bool
    admission_state: AdmissionState
    admission_granted: Literal[False] = False
    source_path_retained: Literal[False] = False
    cell_level_material_retained: Literal[False] = False
    donor_identifiers_retained: Literal[False] = False
    raw_content_retained: Literal[False] = False

    @model_validator(mode="after")
    def evidence_is_consistent(self) -> Self:
        expected_match = (
            self.reviewed_sha256 is not None and self.reviewed_sha256 == self.source_sha256
        )
        if self.review_match is not expected_match:
            raise ValueError("review match does not reconcile with the supplied SHA-256")
        expected_state: AdmissionState
        if self.reviewed_sha256 is None:
            expected_state = "fingerprinted_not_admitted"
        elif expected_match:
            expected_state = "review_digest_matches_not_admitted"
        else:
            expected_state = "review_digest_mismatch_not_admitted"
        if self.admission_state != expected_state:
            raise ValueError("admission state does not reconcile with review evidence")
        payload = self.model_dump(mode="json", exclude={"receipt_digest"})
        if self.receipt_digest != sha256_digest(payload):
            raise ValueError("GBmap source receipt digest mismatch")
        return self


class GbmapSourceAdmissionReceipt(_ReceiptBase):
    """Production-identity fingerprint evidence that never grants admission."""

    @model_validator(mode="after")
    def production_identity_is_exact(self) -> Self:
        if (
            self.schema_version != RECEIPT_SCHEMA
            or self.source_id != ZENODO_SOURCE_ID
            or self.artifact_name != PRODUCTION_ARTIFACT_NAME
            or self.source_bytes != ZENODO_SOURCE_BYTES
            or self.source_md5 != ZENODO_SOURCE_MD5
        ):
            raise ValueError("production GBmap receipt identity differs from its immutable lock")
        return self


class _GbmapTestFixtureReceipt(_ReceiptBase):
    """Explicitly non-production receipt used only by bounded synthetic tests."""

    @model_validator(mode="after")
    def fixture_identity_is_nonproduction(self) -> Self:
        if (
            self.schema_version != _TEST_RECEIPT_SCHEMA
            or self.source_id != _TEST_SOURCE_ID
            or self.artifact_name != _TEST_ARTIFACT_NAME
        ):
            raise ValueError("synthetic fixture receipt identity is not test-only")
        return self


@dataclass(frozen=True, slots=True)
class _FingerprintEvidence:
    fingerprint: SourceFingerprint
    reviewed_sha256: Sha256Digest | None
    review_match: bool
    admission_state: AdmissionState


def _canonical_reviewed_digest(value: str | None) -> Sha256Digest | None:
    if value is None:
        return None
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise GbmapSourceAdmissionError(
            "reviewed SHA-256 must use canonical sha256:<64 lowercase hex> form"
        )
    return value


def _require_external_h5ad(source: Path, repository_root: Path) -> None:
    if source.suffix.lower() != ".h5ad":
        raise GbmapSourceAdmissionError("GBmap source must be an H5AD file")
    resolved_source: Path | None = None
    resolved_repository: Path | None = None
    try:
        resolved_source = source.resolve(strict=True)
        resolved_repository = repository_root.resolve(strict=True)
    except OSError:
        pass
    if resolved_source is None or resolved_repository is None:
        raise GbmapSourceAdmissionError("GBmap source boundary could not be verified")
    if resolved_source == resolved_repository or resolved_source.is_relative_to(
        resolved_repository
    ):
        raise GbmapSourceAdmissionError("GBmap H5AD must remain outside the repository")


def _fingerprint_or_none(source: Path) -> SourceFingerprint | None:
    try:
        return fingerprint_gbmap_source(source)
    except (GbmapSourceAdmissionError, OSError, TypeError, ValueError):
        return None


def _safe_fingerprint(source: Path) -> SourceFingerprint:
    fingerprint = _fingerprint_or_none(source)
    if fingerprint is None:
        raise GbmapSourceAdmissionError("GBmap source could not be safely fingerprinted")
    return fingerprint


def _capture_evidence(
    source: Path,
    *,
    reviewed_sha256: str | None,
    expectation: _SourceExpectation,
    repository_root: Path,
    lock_source_id: str,
) -> _FingerprintEvidence:
    _require_external_h5ad(source, repository_root)
    reviewed = _canonical_reviewed_digest(reviewed_sha256)
    fingerprint = _safe_fingerprint(source)
    if fingerprint.source_bytes != expectation.expected_bytes:
        raise GbmapSourceAdmissionError("GBmap source length does not match its exact lock")
    if fingerprint.md5 != expectation.expected_md5:
        raise GbmapSourceAdmissionError("GBmap source MD5 does not match its exact lock")

    review_match = False
    if reviewed is not None:
        reviewed_lock = ExactGbmapH5adLock(
            source_id=lock_source_id,
            expected_bytes=expectation.expected_bytes,
            md5=expectation.expected_md5,
            sha256=reviewed,
            sha256_independently_reviewed=True,
        )
        review_match = reviewed_lock.sha256 == fingerprint.sha256
    if reviewed is None:
        state: AdmissionState = "fingerprinted_not_admitted"
    elif review_match:
        state = "review_digest_matches_not_admitted"
    else:
        state = "review_digest_mismatch_not_admitted"
    return _FingerprintEvidence(
        fingerprint=fingerprint,
        reviewed_sha256=reviewed,
        review_match=review_match,
        admission_state=state,
    )


def _receipt_payload(
    evidence: _FingerprintEvidence,
    *,
    schema_version: str,
    source_id: str,
    artifact_name: str,
) -> dict[str, object]:
    if _SAFE_SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise ValueError("receipt source identity is not path-free canonical text")
    if _SAFE_ARTIFACT_PATTERN.fullmatch(artifact_name) is None:
        raise ValueError("receipt artifact identity is not path-free canonical text")
    return {
        "schema_version": schema_version,
        "source_id": source_id,
        "artifact_name": artifact_name,
        "source_bytes": evidence.fingerprint.source_bytes,
        "source_md5": evidence.fingerprint.md5,
        "source_sha256": evidence.fingerprint.sha256,
        "byte_size_match": True,
        "official_md5_match": True,
        "reviewed_sha256": evidence.reviewed_sha256,
        "review_match": evidence.review_match,
        "admission_state": evidence.admission_state,
        "admission_granted": False,
        "source_path_retained": False,
        "cell_level_material_retained": False,
        "donor_identifiers_retained": False,
        "raw_content_retained": False,
    }


def capture_source_receipt(
    source: Path,
    *,
    reviewed_sha256: str | None = None,
) -> GbmapSourceAdmissionReceipt:
    """Fingerprint only the immutable production source outside this repository."""

    if not isinstance(source, Path):
        raise GbmapSourceAdmissionError("source must be a pathlib path")
    evidence = _capture_evidence(
        source,
        reviewed_sha256=reviewed_sha256,
        expectation=_PRODUCTION_EXPECTATION,
        repository_root=_REPOSITORY_ROOT,
        lock_source_id=ZENODO_SOURCE_ID,
    )
    payload = _receipt_payload(
        evidence,
        schema_version=RECEIPT_SCHEMA,
        source_id=ZENODO_SOURCE_ID,
        artifact_name=PRODUCTION_ARTIFACT_NAME,
    )
    return GbmapSourceAdmissionReceipt.model_validate(
        {"receipt_digest": sha256_digest(payload), **payload},
        strict=True,
    )


def _capture_test_fixture_receipt(
    source: Path,
    *,
    expected_bytes: int,
    expected_md5: str,
    repository_root: Path,
    reviewed_sha256: str | None = None,
) -> _GbmapTestFixtureReceipt:
    """Test-only hook whose schema and source identity cannot mimic production."""

    if not isinstance(source, Path) or not isinstance(repository_root, Path):
        raise GbmapSourceAdmissionError("fixture paths must be pathlib paths")
    evidence = _capture_evidence(
        source,
        reviewed_sha256=reviewed_sha256,
        expectation=_SourceExpectation(
            expected_bytes=expected_bytes,
            expected_md5=expected_md5,
        ),
        repository_root=repository_root,
        lock_source_id=_TEST_SOURCE_ID,
    )
    payload = _receipt_payload(
        evidence,
        schema_version=_TEST_RECEIPT_SCHEMA,
        source_id=_TEST_SOURCE_ID,
        artifact_name=_TEST_ARTIFACT_NAME,
    )
    return _GbmapTestFixtureReceipt.model_validate(
        {"receipt_digest": sha256_digest(payload), **payload},
        strict=True,
    )


def canonical_receipt_bytes(receipt: _ReceiptBase) -> bytes:
    """Return compact, sorted UTF-8 JSON with one LF terminator."""

    if type(receipt) not in (GbmapSourceAdmissionReceipt, _GbmapTestFixtureReceipt):
        raise TypeError("receipt must be an exact GBmap fingerprint receipt")
    return canonical_json_bytes(receipt) + b"\n"


def _existing_receipt_state(destination: Path, payload: bytes) -> _ExistingReceiptState:
    info: os.stat_result | None = None
    try:
        info = destination.lstat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unavailable"
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    file_attributes = int(getattr(info, "st_file_attributes", 0))
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or (reparse_flag and file_attributes & reparse_flag)
        or info.st_size != len(payload)
    ):
        return "different"
    observed = _read_bytes_or_none(destination)
    if observed is None:
        return "unavailable"
    return "identical" if observed == payload else "different"


def _read_bytes_or_none(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _paths_overlap(destination: Path, source: Path) -> bool | None:
    resolved_destination: Path | None = None
    resolved_source: Path | None = None
    try:
        resolved_destination = destination.resolve(strict=False)
        resolved_source = source.resolve(strict=True)
    except OSError:
        pass
    if resolved_destination is None or resolved_source is None:
        return None
    return resolved_destination == resolved_source


def _create_temporary_receipt(parent: Path) -> tuple[int, Path] | None:
    try:
        descriptor, name = tempfile.mkstemp(
            dir=parent,
            prefix=_TEMP_PREFIX,
            suffix=_TEMP_SUFFIX,
        )
        return descriptor, Path(name)
    except OSError:
        return None


def _close_descriptor(descriptor: int) -> bool:
    try:
        os.close(descriptor)
    except OSError:
        return False
    return True


def _close_file(handle: BinaryIO) -> bool:
    try:
        handle.close()
    except OSError:
        return False
    return True


def _write_fsynced_receipt(descriptor: int, payload: bytes) -> bool:
    handle: BinaryIO | None = None
    write_succeeded = False
    try:
        handle = os.fdopen(descriptor, "wb")
        if handle.write(payload) == len(payload):
            handle.flush()
            os.fsync(handle.fileno())
            write_succeeded = True
    except OSError:
        write_succeeded = False
    finally:
        close_succeeded = _close_descriptor(descriptor) if handle is None else _close_file(handle)
    return write_succeeded and close_succeeded


def _atomic_link(temporary: Path, destination: Path) -> _PublicationState:
    try:
        os.link(temporary, destination)
    except FileExistsError:
        return "conflict"
    except OSError:
        return "failed"
    return "published"


def _clean_temporary(temporary: Path) -> bool:
    try:
        temporary.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _publish_new_receipt(destination: Path, payload: bytes) -> None:
    temporary_record = _create_temporary_receipt(destination.parent)
    if temporary_record is None:
        raise GbmapSourceAdmissionError("GBmap receipt temporary file could not be created")
    descriptor, temporary = temporary_record

    write_succeeded = False
    publication: _PublicationState = "failed"
    cleanup_succeeded = False
    try:
        write_succeeded = _write_fsynced_receipt(descriptor, payload)
        if write_succeeded:
            publication = _atomic_link(temporary, destination)
    finally:
        cleanup_succeeded = _clean_temporary(temporary)

    if not cleanup_succeeded:
        raise GbmapSourceAdmissionError("GBmap receipt temporary file could not be cleaned")
    if not write_succeeded:
        raise GbmapSourceAdmissionError("GBmap receipt temporary file could not be committed")
    if publication == "failed":
        raise GbmapSourceAdmissionError("GBmap receipt atomic publication failed")
    if publication == "conflict":
        existing = _existing_receipt_state(destination, payload)
        if existing == "identical":
            return
        if existing == "unavailable":
            raise GbmapSourceAdmissionError("existing GBmap receipt could not be verified")
        raise GbmapSourceAdmissionError("refusing to overwrite a different receipt")


def write_receipt(destination: Path, payload: bytes, *, source: Path) -> None:
    """Fsync a same-directory temporary and atomically publish without overwrite."""

    if not isinstance(destination, Path) or not isinstance(source, Path):
        raise GbmapSourceAdmissionError("receipt and source must be pathlib paths")
    if type(payload) is not bytes or not payload:
        raise GbmapSourceAdmissionError("receipt payload must be nonempty exact bytes")
    overlap = _paths_overlap(destination, source)
    if overlap is None:
        raise GbmapSourceAdmissionError("receipt destination boundary could not be verified")
    if overlap:
        raise GbmapSourceAdmissionError("receipt destination cannot replace the H5AD")

    parent_created = True
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        parent_created = False
    if not parent_created:
        raise GbmapSourceAdmissionError("GBmap receipt directory could not be prepared")

    existing = _existing_receipt_state(destination, payload)
    if existing == "identical":
        return
    if existing == "different":
        raise GbmapSourceAdmissionError("refusing to overwrite a different receipt")
    if existing == "unavailable":
        raise GbmapSourceAdmissionError("existing GBmap receipt could not be verified")
    _publish_new_receipt(destination, payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reviewed-sha256")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = capture_source_receipt(
            args.source,
            reviewed_sha256=args.reviewed_sha256,
        )
        payload = canonical_receipt_bytes(receipt)
        if args.output is not None:
            write_receipt(args.output, payload, source=args.source)
        sys.stdout.write(payload.decode("utf-8"))
    except GbmapSourceAdmissionError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    except (OSError, TypeError, ValueError):
        sys.stderr.write("GBmap source receipt operation failed\n")
        return 2
    return 0 if receipt.reviewed_sha256 is None or receipt.review_match else 3


if __name__ == "__main__":
    raise SystemExit(main())
