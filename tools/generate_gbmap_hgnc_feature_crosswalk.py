"""Generate the public GBmap-to-HGNC feature crosswalk from locked sources.

This maintainer-only command authenticates the exact 8.98 GB GBmap H5AD on a
held handle before and after reading ``var/_index``.  It separately authenticates
the exact HGNC complete-set snapshot.  The output contains feature identities and
source provenance only: never expression values, donor data, or model parameters.
"""

# ruff: noqa: T201, TRY003, TRY301

from __future__ import annotations

import argparse
import hashlib
import importlib
import os
import stat
import sys
from pathlib import Path
from typing import IO, TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import ModuleType

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_deconvolution.feature_identity import (
    GBMAP_SOURCE_SHA256,
    HGNC_ROW_COUNT,
    HGNC_SOURCE_BYTES,
    HGNC_SOURCE_ID,
    HGNC_SOURCE_SHA256,
    PRODUCTION_FEATURE_COUNT,
    GbmapFeatureIdentityCrosswalk,
    build_feature_identity_crosswalk,
    parse_hgnc_complete_set,
)
from glio_proteogen.research.gbmap_deconvolution.profile import development_profile
from tools.capture_gbmap_source_admission import write_receipt
from tools.fit_gbmap_development_candidate import (
    GbmapDevelopmentFitDriverError,
    _capture_source_snapshot,
    _open_source_guard,
    _privacy_call,
    _require_source_unchanged,
)

EXPECTED_H5PY_VERSION: Final = "3.16.0"
HASH_BLOCK_BYTES: Final = 4 * 1024 * 1024
MAX_SYMBOL_LENGTH: Final = 256
_REPARSE_ATTRIBUTE: Final = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class GbmapFeatureIdentityGeneratorError(ValueError):
    """Sanitized maintainer-facing feature identity generation failure."""


def _require_acknowledgements(
    *,
    reviewed_source_digests: bool,
    feature_identity_only: bool,
) -> None:
    if reviewed_source_digests is not True:
        raise GbmapFeatureIdentityGeneratorError(
            "explicit reviewed-source-digest acknowledgement is required"
        )
    if feature_identity_only is not True:
        raise GbmapFeatureIdentityGeneratorError(
            "explicit feature-identity-only acknowledgement is required"
        )


def _hash_held_h5ad(handle: IO[bytes]) -> tuple[int, str, str]:
    handle.seek(0)
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    length = 0
    while True:
        block = handle.read(HASH_BLOCK_BYTES)
        if not block:
            break
        if type(block) is not bytes:
            raise GbmapFeatureIdentityGeneratorError("GBmap source produced non-byte content")
        length += len(block)
        md5.update(block)
        sha256.update(block)
    return length, md5.hexdigest(), "sha256:" + sha256.hexdigest()


def _require_exact_gbmap_fingerprint(value: tuple[int, str, str]) -> None:
    expectation = development_profile().source
    if value != (
        expectation.expected_bytes,
        expectation.source_md5,
        GBMAP_SOURCE_SHA256,
    ):
        raise GbmapFeatureIdentityGeneratorError("GBmap H5AD does not match the reviewed lock")


def _decode_feature(value: object) -> str:
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GbmapFeatureIdentityGeneratorError(
                "GBmap feature identifiers are not UTF-8"
            ) from exc
    elif isinstance(value, str):
        text = value
    else:
        raise GbmapFeatureIdentityGeneratorError("GBmap feature identifiers must be scalar text")
    if not text or text != text.strip() or len(text) > MAX_SYMBOL_LENGTH:
        raise GbmapFeatureIdentityGeneratorError("GBmap feature identifier is not canonical")
    return text


def _read_feature_symbols(handle: IO[bytes]) -> tuple[str, ...]:
    try:
        h5py: ModuleType = importlib.import_module("h5py")
    except ImportError as exc:
        raise GbmapFeatureIdentityGeneratorError("h5py is required") from exc
    if h5py.__version__ != EXPECTED_H5PY_VERSION:
        raise GbmapFeatureIdentityGeneratorError("feature generation requires h5py 3.16.0")
    handle.seek(0)
    try:
        with h5py.File(handle, "r", driver="fileobj") as h5:
            if "var/_index" not in h5:
                raise GbmapFeatureIdentityGeneratorError("GBmap H5AD is missing var/_index")
            dataset = h5["var/_index"]
            if not isinstance(dataset, h5py.Dataset) or dataset.shape != (
                PRODUCTION_FEATURE_COUNT,
            ):
                raise GbmapFeatureIdentityGeneratorError(
                    "GBmap feature vector differs from the reviewed structure"
                )
            raw = dataset[:]
    except GbmapFeatureIdentityGeneratorError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise GbmapFeatureIdentityGeneratorError("GBmap feature vector could not be read") from exc
    symbols = tuple(_decode_feature(value) for value in raw)
    if len(symbols) != len(set(symbols)):
        raise GbmapFeatureIdentityGeneratorError("GBmap feature identifiers are not unique")
    return symbols


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_ATTRIBUTE)


def _read_locked_hgnc(path: Path) -> bytes:
    if not isinstance(path, Path):
        raise GbmapFeatureIdentityGeneratorError("HGNC source must be a pathlib Path")
    try:
        before = os.lstat(path)
        if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
            raise GbmapFeatureIdentityGeneratorError(
                "HGNC source must be a regular non-reparse file"
            )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ):
                raise GbmapFeatureIdentityGeneratorError("HGNC source changed while it was opened")
            raw = handle.read(HGNC_SOURCE_BYTES + 1)
            final = os.fstat(handle.fileno())
        after = os.lstat(path)
    except GbmapFeatureIdentityGeneratorError:
        raise
    except OSError as exc:
        raise GbmapFeatureIdentityGeneratorError("HGNC source could not be read") from exc

    def identity(info: os.stat_result) -> tuple[int, int, int, int]:
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    if identity(before) != identity(final) or identity(before) != identity(after):
        raise GbmapFeatureIdentityGeneratorError("HGNC source identity changed during reading")
    if len(raw) != HGNC_SOURCE_BYTES:
        raise GbmapFeatureIdentityGeneratorError("HGNC source byte length differs from its lock")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if digest != HGNC_SOURCE_SHA256:
        raise GbmapFeatureIdentityGeneratorError("HGNC source digest differs from its lock")
    return raw


def generate_crosswalk(
    gbmap_h5ad: Path,
    hgnc_tsv: Path,
    *,
    reviewed_source_digests: bool,
    feature_identity_only: bool,
) -> GbmapFeatureIdentityCrosswalk:
    """Authenticate both sources and build the deterministic public crosswalk."""

    _require_acknowledgements(
        reviewed_source_digests=reviewed_source_digests,
        feature_identity_only=feature_identity_only,
    )
    snapshot = _privacy_call(
        "GBmap source could not be inspected safely",
        lambda: _capture_source_snapshot(gbmap_h5ad),
    )
    with _privacy_call(
        "GBmap source guard could not be opened safely",
        lambda: _open_source_guard(snapshot),
    ) as guard:
        first = _privacy_call(
            "GBmap source could not be authenticated",
            lambda: _hash_held_h5ad(guard),
        )
        _require_exact_gbmap_fingerprint(first)
        symbols = _privacy_call(
            "GBmap feature identities could not be read",
            lambda: _read_feature_symbols(guard),
        )
        second = _privacy_call(
            "GBmap source could not be reauthenticated",
            lambda: _hash_held_h5ad(guard),
        )
        _require_exact_gbmap_fingerprint(second)
        if first != second:
            raise GbmapFeatureIdentityGeneratorError(
                "GBmap source changed during feature extraction"
            )
        after = _privacy_call(
            "GBmap source could not be re-inspected safely",
            lambda: _capture_source_snapshot(gbmap_h5ad),
        )
        _privacy_call(
            "GBmap source identity changed during feature extraction",
            lambda: _require_source_unchanged(snapshot, after, guard),
        )

    raw_hgnc = _read_locked_hgnc(hgnc_tsv)
    records = parse_hgnc_complete_set(raw_hgnc)
    if len(records) != HGNC_ROW_COUNT:
        raise GbmapFeatureIdentityGeneratorError("HGNC row count differs from its lock")
    return build_feature_identity_crosswalk(
        symbols,
        records,
        gbmap_source_sha256=GBMAP_SOURCE_SHA256,
        hgnc_source_sha256=HGNC_SOURCE_SHA256,
        hgnc_source_bytes=HGNC_SOURCE_BYTES,
        hgnc_source_id=HGNC_SOURCE_ID,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbmap-h5ad", required=True, type=Path)
    parser.add_argument("--hgnc-tsv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--acknowledge-reviewed-source-digests", action="store_true")
    parser.add_argument("--acknowledge-feature-identity-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        crosswalk = generate_crosswalk(
            cast("Path", args.gbmap_h5ad),
            cast("Path", args.hgnc_tsv),
            reviewed_source_digests=cast("bool", args.acknowledge_reviewed_source_digests),
            feature_identity_only=cast("bool", args.acknowledge_feature_identity_only),
        )
        payload = canonical_json_bytes(crosswalk.model_dump(mode="json"))
        write_receipt(cast("Path", args.output), payload, source=cast("Path", args.gbmap_h5ad))
        print(
            canonical_json_bytes(
                {
                    "content_digest": crosswalk.content_digest,
                    "counts": crosswalk.counts.model_dump(mode="json"),
                    "output_bytes": len(payload),
                    "runtime_mount_permitted": False,
                }
            ).decode("utf-8")
        )
    except (GbmapDevelopmentFitDriverError, GbmapFeatureIdentityGeneratorError, ValueError):
        print("GBmap HGNC feature crosswalk generation failed closed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
