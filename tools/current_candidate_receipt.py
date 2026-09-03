"""Generate and verify one strict receipt for the current release candidate."""

# ruff: noqa: PLC0415, PLR0913, PLR2004, T201, TC003, TRY003, TRY301

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from collections.abc import Mapping, Sequence
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path, PurePosixPath
from typing import Final, cast
from zipfile import BadZipFile, ZipFile

RECEIPT_SCHEMA: Final = "glio-proteogen/current-candidate-receipt/1.0.0"
REPOSITORY_ID: Final = "AURORA-NEURO/glio-proteogen"
SOURCE_DATE_EPOCH: Final = 315_532_800
_BUFFER_BYTES: Final = 1024 * 1024
_HEX_DIGITS: Final = frozenset("0123456789abcdef")


class CandidateReceiptError(ValueError):
    """The candidate artifacts or receipt are incomplete, unsafe, or inconsistent."""


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CandidateReceiptError("candidate receipt is not canonical JSON") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(_BUFFER_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise CandidateReceiptError("candidate artifact cannot be read") from error
    return digest.hexdigest()


def _files_identical(first: Path, second: Path) -> bool:
    try:
        if first.stat().st_size != second.stat().st_size:
            return False
        with first.open("rb") as left, second.open("rb") as right:
            while True:
                left_chunk = left.read(_BUFFER_BYTES)
                right_chunk = right.read(_BUFFER_BYTES)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError as error:
        raise CandidateReceiptError("candidate replay artifact cannot be read") from error


def _strict_json(path: Path) -> dict[str, object]:
    def reject_constant(_value: str) -> None:
        raise CandidateReceiptError("candidate receipt contains a non-finite number")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise CandidateReceiptError("candidate receipt contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except CandidateReceiptError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CandidateReceiptError("candidate receipt is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CandidateReceiptError("candidate receipt must be a JSON object")
    return cast("dict[str, object]", value)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise CandidateReceiptError(f"candidate receipt {label} must be an object")
    return cast("dict[str, object]", value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise CandidateReceiptError(f"candidate receipt {label} must be an array")
    return cast("list[object]", value)


def _require_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CandidateReceiptError(f"candidate receipt {label} fields are not exact")


def _valid_hex(value: object, *, prefix: str = "", digits: int = 64) -> bool:
    if not isinstance(value, str) or not value.startswith(prefix):
        return False
    suffix = value[len(prefix) :]
    return len(suffix) == digits and set(suffix) <= _HEX_DIGITS


def _validate_commit(value: object) -> str:
    if not _valid_hex(value, digits=40):
        raise CandidateReceiptError("candidate receipt source commit is invalid")
    return cast("str", value)


def _validate_member_name(name: object) -> str:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise CandidateReceiptError("candidate archive contains an invalid member name")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CandidateReceiptError("candidate archive contains an unsafe member path")
    return name


def member_inventory_digest(names: Sequence[str]) -> str:
    """Return the canonical SHA-256 for a sorted archive-member inventory."""

    return hashlib.sha256(_canonical_json_bytes(sorted(names))).hexdigest()


def _archive_members(path: Path, kind: str) -> list[str]:
    try:
        if kind == "wheel":
            if path.suffix != ".whl":
                raise CandidateReceiptError("candidate wheel does not have a .whl suffix")
            with ZipFile(path) as archive:
                raw_names = archive.namelist()
        elif kind == "sdist":
            if not path.name.endswith(".tar.gz"):
                raise CandidateReceiptError("candidate sdist does not have a .tar.gz suffix")
            with tarfile.open(path, "r:gz") as archive:
                raw_names = archive.getnames()
        else:
            raise CandidateReceiptError("candidate artifact kind is unsupported")
    except CandidateReceiptError:
        raise
    except (BadZipFile, OSError, tarfile.TarError) as error:
        raise CandidateReceiptError(f"candidate {kind} archive cannot be read") from error
    names = [_validate_member_name(name) for name in raw_names]
    if len(names) != len(set(names)):
        raise CandidateReceiptError(f"candidate {kind} archive contains duplicate members")
    return sorted(names)


def _metadata_identity(payload: bytes, label: str) -> tuple[str, str]:
    message = BytesParser(policy=email_policy).parsebytes(payload)
    name = message.get("Name")
    version = message.get("Version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise CandidateReceiptError(f"candidate {label} metadata identity is incomplete")
    return name, version


def _distribution_identity(wheel: Path, sdist: Path) -> dict[str, str]:
    try:
        with ZipFile(wheel) as archive:
            metadata_members = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_members) != 1:
                raise CandidateReceiptError("candidate wheel must contain one METADATA member")
            wheel_identity = _metadata_identity(
                archive.read(metadata_members[0]), "wheel"
            )
        with tarfile.open(sdist, "r:gz") as archive:
            package_members = [
                member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")
            ]
            if len(package_members) != 1:
                raise CandidateReceiptError("candidate sdist must contain one PKG-INFO member")
            stream = archive.extractfile(package_members[0])
            if stream is None:
                raise CandidateReceiptError("candidate sdist PKG-INFO cannot be read")
            sdist_identity = _metadata_identity(stream.read(), "sdist")
    except CandidateReceiptError:
        raise
    except (BadZipFile, KeyError, OSError, tarfile.TarError) as error:
        raise CandidateReceiptError("candidate distribution metadata cannot be read") from error
    if wheel_identity != sdist_identity:
        raise CandidateReceiptError("candidate wheel and sdist identities do not match")
    return {"name": wheel_identity[0], "version": wheel_identity[1]}


def _profile_identity() -> dict[str, str]:
    try:
        from glio_proteogen.research.proteogenomic_state import algorithm_profile

        profile = algorithm_profile()
    except Exception as error:
        raise CandidateReceiptError("candidate algorithm profile cannot be resolved") from error
    return {
        "algorithm_id": profile.algorithm_id,
        "algorithm_version": profile.algorithm_version,
        "demo_graph_digest": profile.demo_graph_digest,
        "numpy_version": profile.numpy_version,
        "profile_digest": profile.profile_digest,
        "profile_id": profile.profile_id,
    }


def _artifact_record(path: Path, kind: str) -> dict[str, object]:
    if not path.is_file():
        raise CandidateReceiptError(f"candidate {kind} artifact is missing")
    names = _archive_members(path, kind)
    return {
        "bytes": path.stat().st_size,
        "filename": path.name,
        "member_inventory": {
            "count": len(names),
            "members": names,
            "sha256": member_inventory_digest(names),
        },
        "members": len(names),
        "sha256": _sha256(path),
    }


def _build_hashes(wheel: Mapping[str, object], sdist: Mapping[str, object]) -> dict[str, object]:
    return {
        "sdist_sha256": sdist["sha256"],
        "wheel_sha256": wheel["sha256"],
    }


def build_receipt(
    wheel: Path,
    sdist: Path,
    replay_wheel: Path,
    replay_sdist: Path,
    *,
    source_commit: str,
    profile: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build one canonical receipt after proving the two distributions byte-identical."""

    commit = _validate_commit(source_commit)
    primary_wheel = _artifact_record(wheel, "wheel")
    primary_sdist = _artifact_record(sdist, "sdist")
    replay_wheel_record = _artifact_record(replay_wheel, "wheel")
    replay_sdist_record = _artifact_record(replay_sdist, "sdist")
    if (
        primary_wheel != replay_wheel_record
        or primary_sdist != replay_sdist_record
        or not _files_identical(wheel, replay_wheel)
        or not _files_identical(sdist, replay_sdist)
    ):
        raise CandidateReceiptError("candidate distribution builds are not byte-identical")
    observed_profile = dict(profile) if profile is not None else _profile_identity()
    payload: dict[str, object] = {
        "artifacts": {"sdist": primary_sdist, "wheel": primary_wheel},
        "distribution": _distribution_identity(wheel, sdist),
        "profile": observed_profile,
        "receipt_schema": RECEIPT_SCHEMA,
        "reproducibility": {
            "build_count": 2,
            "build_one": _build_hashes(primary_wheel, primary_sdist),
            "build_two": _build_hashes(replay_wheel_record, replay_sdist_record),
            "byte_identical": True,
            "source_date_epoch": SOURCE_DATE_EPOCH,
        },
        "source": {"commit": commit, "repository": REPOSITORY_ID},
    }
    payload["receipt_digest"] = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    """Write a canonical receipt once, refusing ambiguous overwrites."""

    try:
        with path.open("xb") as stream:
            stream.write(_canonical_json_bytes(receipt) + b"\n")
    except FileExistsError as error:
        raise CandidateReceiptError("candidate receipt output already exists") from error
    except OSError as error:
        raise CandidateReceiptError("candidate receipt output cannot be written") from error


def _verify_artifact_record(
    record: Mapping[str, object], path: Path, kind: str
) -> dict[str, object]:
    _require_keys(
        record,
        {"bytes", "filename", "member_inventory", "members", "sha256"},
        f"{kind} artifact",
    )
    observed = _artifact_record(path, kind)
    if dict(record) != observed:
        raise CandidateReceiptError(f"candidate receipt {kind} does not match artifact")
    return observed


def _verify_profile(
    value: Mapping[str, object], expected: Mapping[str, object] | None
) -> None:
    fields = {
        "algorithm_id",
        "algorithm_version",
        "demo_graph_digest",
        "numpy_version",
        "profile_digest",
        "profile_id",
    }
    _require_keys(value, fields, "profile")
    for field in fields:
        if not isinstance(value.get(field), str) or not value[field]:
            raise CandidateReceiptError("candidate receipt profile identity is incomplete")
    if not _valid_hex(value.get("profile_digest"), prefix="sha256:"):
        raise CandidateReceiptError("candidate receipt profile digest is invalid")
    if not _valid_hex(value.get("demo_graph_digest"), prefix="sha256:"):
        raise CandidateReceiptError("candidate receipt demo graph digest is invalid")
    observed = dict(expected) if expected is not None else _profile_identity()
    if dict(value) != observed:
        raise CandidateReceiptError("candidate receipt profile does not match runtime")


def _verify_inventory_shape(record: Mapping[str, object], label: str) -> None:
    inventory = _mapping(record.get("member_inventory"), f"{label} member inventory")
    _require_keys(inventory, {"count", "members", "sha256"}, f"{label} member inventory")
    raw_members = _sequence(inventory.get("members"), f"{label} member inventory members")
    members = [_validate_member_name(item) for item in raw_members]
    if members != sorted(members) or len(members) != len(set(members)):
        raise CandidateReceiptError(f"candidate receipt {label} member inventory is not canonical")
    if type(inventory.get("count")) is not int or inventory["count"] != len(members):
        raise CandidateReceiptError(f"candidate receipt {label} member count is invalid")
    if record.get("members") != len(members):
        raise CandidateReceiptError(f"candidate receipt {label} artifact count is invalid")
    if inventory.get("sha256") != member_inventory_digest(members):
        raise CandidateReceiptError(f"candidate receipt {label} inventory digest is invalid")


def verify_receipt(  # noqa: C901
    receipt_path: Path,
    wheel: Path,
    sdist: Path,
    *,
    replay_wheel: Path | None = None,
    replay_sdist: Path | None = None,
    expected_source_commit: str | None = None,
    expected_profile: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Strictly validate one receipt and bind it to the supplied candidate bytes."""

    receipt = _strict_json(receipt_path)
    _require_keys(
        receipt,
        {
            "artifacts",
            "distribution",
            "profile",
            "receipt_digest",
            "receipt_schema",
            "reproducibility",
            "source",
        },
        "root",
    )
    if receipt.get("receipt_schema") != RECEIPT_SCHEMA:
        raise CandidateReceiptError("candidate receipt schema is unsupported")
    digest = receipt.get("receipt_digest")
    if not _valid_hex(digest, prefix="sha256:"):
        raise CandidateReceiptError("candidate receipt digest is invalid")
    digest_payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    expected_digest = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(digest_payload)
    ).hexdigest()
    if digest != expected_digest:
        raise CandidateReceiptError("candidate receipt digest does not match content")

    source = _mapping(receipt.get("source"), "source")
    _require_keys(source, {"commit", "repository"}, "source")
    if source.get("repository") != REPOSITORY_ID:
        raise CandidateReceiptError("candidate receipt repository is unexpected")
    source_commit = _validate_commit(source.get("commit"))
    if expected_source_commit is not None and source_commit != _validate_commit(
        expected_source_commit
    ):
        raise CandidateReceiptError("candidate receipt source commit does not match checkout")

    profile = _mapping(receipt.get("profile"), "profile")
    _verify_profile(profile, expected_profile)
    distribution = _mapping(receipt.get("distribution"), "distribution")
    _require_keys(distribution, {"name", "version"}, "distribution")
    if distribution != _distribution_identity(wheel, sdist):
        raise CandidateReceiptError("candidate receipt distribution identity does not match")

    artifacts = _mapping(receipt.get("artifacts"), "artifacts")
    _require_keys(artifacts, {"sdist", "wheel"}, "artifacts")
    wheel_record = _mapping(artifacts.get("wheel"), "wheel artifact")
    sdist_record = _mapping(artifacts.get("sdist"), "sdist artifact")
    _verify_inventory_shape(wheel_record, "wheel")
    _verify_inventory_shape(sdist_record, "sdist")
    observed_wheel = _verify_artifact_record(wheel_record, wheel, "wheel")
    observed_sdist = _verify_artifact_record(sdist_record, sdist, "sdist")

    reproducibility = _mapping(receipt.get("reproducibility"), "reproducibility")
    _require_keys(
        reproducibility,
        {"build_count", "build_one", "build_two", "byte_identical", "source_date_epoch"},
        "reproducibility",
    )
    if (
        reproducibility.get("build_count") != 2
        or reproducibility.get("byte_identical") is not True
        or reproducibility.get("source_date_epoch") != SOURCE_DATE_EPOCH
    ):
        raise CandidateReceiptError("candidate receipt reproducibility policy is invalid")
    expected_hashes = _build_hashes(observed_wheel, observed_sdist)
    for label in ("build_one", "build_two"):
        hashes = _mapping(reproducibility.get(label), f"reproducibility {label}")
        _require_keys(hashes, {"sdist_sha256", "wheel_sha256"}, label)
        if hashes != expected_hashes:
            raise CandidateReceiptError("candidate receipt reproducibility hashes do not match")
    if (replay_wheel is None) != (replay_sdist is None):
        raise CandidateReceiptError("both replay artifacts must be supplied together")
    if replay_wheel is not None and replay_sdist is not None:
        replay_wheel_record = _artifact_record(replay_wheel, "wheel")
        replay_sdist_record = _artifact_record(replay_sdist, "sdist")
        if (
            replay_wheel_record != observed_wheel
            or replay_sdist_record != observed_sdist
            or not _files_identical(wheel, replay_wheel)
            or not _files_identical(sdist, replay_sdist)
        ):
            raise CandidateReceiptError("candidate replay artifacts are not byte-identical")
    return receipt


def artifact_receipt(receipt: Mapping[str, object], kind: str) -> dict[str, object]:
    """Return one already-validated artifact record for a semantic verifier."""

    artifacts = _mapping(receipt.get("artifacts"), "artifacts")
    if kind not in {"wheel", "sdist"}:
        raise CandidateReceiptError("candidate artifact kind is unsupported")
    return _mapping(artifacts.get(kind), f"{kind} artifact")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="emit a current-candidate receipt")
    verify = commands.add_parser("verify", help="verify a current-candidate receipt")
    for command in (generate, verify):
        command.add_argument("--wheel", type=Path, required=True)
        command.add_argument("--sdist", type=Path, required=True)
        command.add_argument("--replay-wheel", type=Path, required=True)
        command.add_argument("--replay-sdist", type=Path, required=True)
        command.add_argument("--source-commit", required=True)
    generate.add_argument("--output", type=Path, required=True)
    verify.add_argument("receipt", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run candidate receipt generation or verification with sanitized failures."""

    try:
        parsed = _parser().parse_args(arguments)
        if parsed.command == "generate":
            receipt = build_receipt(
                parsed.wheel,
                parsed.sdist,
                parsed.replay_wheel,
                parsed.replay_sdist,
                source_commit=parsed.source_commit,
            )
            write_receipt(parsed.output, receipt)
        elif parsed.command == "verify":
            verify_receipt(
                parsed.receipt,
                parsed.wheel,
                parsed.sdist,
                replay_wheel=parsed.replay_wheel,
                replay_sdist=parsed.replay_sdist,
                expected_source_commit=parsed.source_commit,
            )
        else:
            return 2
    except CandidateReceiptError as error:
        print(f"current candidate receipt failed: {error}", file=sys.stderr)
        return 1
    print(f"current candidate receipt {parsed.command} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RECEIPT_SCHEMA",
    "REPOSITORY_ID",
    "SOURCE_DATE_EPOCH",
    "CandidateReceiptError",
    "artifact_receipt",
    "build_receipt",
    "main",
    "member_inventory_digest",
    "verify_receipt",
    "write_receipt",
]
