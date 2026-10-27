"""Strict replay binding of captured private specimen/file metadata.

Caller-supplied digests prove byte integrity, not GDC/PDC issuer authenticity.
Captured specimen joins are checked for internal consistency, not independently
re-established from official ancestry endpoints by this local loader.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, Mapping, NoReturn, SupportsIndex, cast

from .contracts import MAX_SOURCE_BYTES, SourceLock
from .protein import PROTEIN_LOCK, SAMPLE_MAP_LOCK

PROFILE_ID: Final = "cptac-gbm-confirmatory-metadata-plan/1.0.0"
MAX_PLAN_BYTES: Final = 2_000_000
_CANDIDATES: Final = 56
_UUID: Final = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_SHA: Final = re.compile(r"[0-9a-f]{64}")
_MD5: Final = re.compile(r"[0-9a-f]{32}")
_CHANNELS: Final = frozenset(
    ("127N", "127C", "128N", "128C", "129N", "129C", "130N", "130C", "131N", "131C")
)
_CHOICE_STATUS: Final = (
    "metadata-and-exact-sample-map candidates only; no measurement/scale/clinical admission"
)
Workflow = Literal["STAR - Counts", "AscatNGS"]


class AdmissionPlanError(ValueError):
    """A sanitized local metadata-plan rejection without source identifiers."""


class _Transient:
    __slots__ = ()

    def __getstate__(self) -> NoReturn:
        raise TypeError("private admission bindings cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private admission bindings cannot be serialized")


@dataclass(frozen=True, slots=True)
class CandidateBinding(_Transient):
    case_submitter_id: str = field(repr=False)
    sample_submitter_id: str = field(repr=False)
    gdc_sample_uuid: str = field(repr=False)
    protein_aliquot_submitter_id: str = field(repr=False)
    protein_aliquot_uuid: str = field(repr=False)
    rna_file_id: str = field(repr=False)
    cnv_file_id: str = field(repr=False)

    def __getstate__(self) -> NoReturn:
        _Transient.__getstate__(self)

    @property
    def metadata_candidate_not_admitted(self) -> Literal[True]:
        return True


@dataclass(frozen=True, slots=True)
class AssayInputBinding(_Transient):
    relative_path: str = field(repr=False)
    lock: SourceLock
    workflow: Workflow

    def __getstate__(self) -> NoReturn:
        _Transient.__getstate__(self)


@dataclass(frozen=True, slots=True)
class ExternalAdmissionReceipt:
    profile_id: str
    choices_sha256: str
    files_manifest_sha256: str
    candidate_count: int
    rna_file_count: int
    cnv_file_count: int
    paired_file_count: int
    manifest_verified_bytes: int
    metadata_candidate_not_admitted: bool
    issuer_authentication: bool
    eligibility_admitted: bool
    measurement_bytes_reverified: bool
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExternalAdmissionPlan(_Transient):
    candidates: tuple[CandidateBinding, ...] = field(repr=False)
    files: Mapping[str, AssayInputBinding] = field(repr=False)
    receipt: ExternalAdmissionReceipt

    def __getstate__(self) -> NoReturn:
        _Transient.__getstate__(self)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))

    @property
    def protein_aliquots(self) -> tuple[str, ...]:
        return tuple(candidate.protein_aliquot_submitter_id for candidate in self.candidates)


def _fail() -> NoReturn:
    raise AdmissionPlanError("captured admission metadata was not accepted")


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise AdmissionPlanError("plan digest must be raw lowercase SHA-256")
    return value


def _text(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum or value.strip() != value:
        _fail()
    return value


def _uuid(value: object) -> str:
    text = _text(value)
    if _UUID.fullmatch(text) is None:
        _fail()
    return text


def _integer(value: object, *, minimum: int = 0, maximum: int = MAX_SOURCE_BYTES) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _record(value: object, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        _fail()
    return cast("dict[str, object]", value)


def _records(value: object, count: int) -> list[object]:
    if type(value) is not list or len(value) != count:
        _fail()
    return value


def _check_json(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        _fail()
    if isinstance(value, str):
        if len(value) > 4_096 or any(not character.isprintable() for character in value):
            _fail()
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_json(key, depth=depth + 1)
            _check_json(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_json(item, depth=depth + 1)
    elif value is not None and type(value) not in (int, bool):
        _fail()


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionPlanError("plan JSON contains duplicate keys")
        result[key] = value
    return result


def _invalid_number(_value: str) -> NoReturn:
    raise AdmissionPlanError("plan JSON numbers must be finite integers")


def _snapshot(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    if not stat.S_ISREG(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise AdmissionPlanError("plan inputs must be regular non-link files")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns),
    )


def _read_json(path: Path, expected_sha256: str) -> object:
    _sha256(expected_sha256)
    try:
        before = _snapshot(path.lstat())
        if not 1 <= before[2] <= MAX_PLAN_BYTES:
            raise AdmissionPlanError("plan input exceeds its bounded JSON size")  # noqa: TRY301
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _snapshot(opened) != before:
                raise AdmissionPlanError("plan input binding changed")  # noqa: TRY301
            payload = stream.read(MAX_PLAN_BYTES + 1)
            after = os.fstat(stream.fileno())
        if (
            _snapshot(after) != before
            or opened.st_ctime_ns != after.st_ctime_ns
            or _snapshot(path.lstat()) != before
            or len(payload) != before[2]
        ):
            raise AdmissionPlanError("plan input binding changed")  # noqa: TRY301
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise AdmissionPlanError("plan input checksum did not match")  # noqa: TRY301
        decoded: object = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_json_pairs,
            parse_constant=_invalid_number,
            parse_float=_invalid_number,
        )
        _check_json(decoded)
    except AdmissionPlanError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        raise AdmissionPlanError("plan input could not be read and decoded") from None
    return decoded


def _pdc_sources(value: object) -> None:
    known_locks = {
        (PROTEIN_LOCK.bytes, PROTEIN_LOCK.md5),
        (SAMPLE_MAP_LOCK.bytes, SAMPLE_MAP_LOCK.md5),
    }
    observed: set[tuple[int, str]] = set()
    ids: set[str] = set()
    studies: set[str] = set()
    for item in _records(value, 3):
        row = _record(
            item,
            {
                "data_category",
                "file_id",
                "file_name",
                "file_size",
                "file_type",
                "md5sum",
                "pdc_study_id",
                "study_id",
            },
        )
        file_id = _uuid(row["file_id"])
        if (
            file_id in ids
            or row["data_category"] != "Protein Assembly"
            or row["file_type"] != "Text"
            or row["pdc_study_id"] != "PDC000446"
        ):
            _fail()
        ids.add(file_id)
        studies.add(_uuid(row["study_id"]))
        _text(row["file_name"], maximum=512)
        length = _text(row["file_size"])
        md5 = _text(row["md5sum"])
        if re.fullmatch(r"[1-9][0-9]{0,8}", length) is None or _MD5.fullmatch(md5) is None:
            _fail()
        observed.add((_integer(int(length), minimum=1), md5))
    if len(studies) != 1 or not known_locks.issubset(observed):
        _fail()


def _choice_files(value: object, count: int) -> dict[str, tuple[int, str, Workflow]]:
    result: dict[str, tuple[int, str, Workflow]] = {}
    for item in _records(value, 2 * count):
        row = _record(
            item, {"access", "assay", "file_id", "file_name", "file_size", "md5sum", "workflow"}
        )
        file_id = _uuid(row["file_id"])
        workflow = row["workflow"]
        assay = row["assay"]
        if (
            file_id in result
            or row["access"] != "open"
            or (assay, workflow) not in (("RNA", "STAR - Counts"), ("gene_CNV", "AscatNGS"))
        ):
            _fail()
        _text(row["file_name"], maximum=512)
        length = _integer(row["file_size"], minimum=1)
        md5 = _text(row["md5sum"])
        if _MD5.fullmatch(md5) is None:
            _fail()
        result[file_id] = (length, md5, cast("Workflow", workflow))
    return result


def _candidate_bindings(
    value: object, count: int, choices: Mapping[str, tuple[int, str, Workflow]]
) -> tuple[CandidateBinding, ...]:
    bindings: list[CandidateBinding] = []
    seen: list[set[str]] = [set() for _ in range(5)]
    seen_files: set[str] = set()
    seen_channels: set[tuple[int, str]] = set()
    for item in _records(value, count):
        row = _record(
            item,
            {
                "GDC_sample_uuid",
                "PDC_protein_aliquot_submitter_id",
                "PDC_protein_aliquot_uuid",
                "RNA_file_id",
                "case_submitter_id",
                "exact_once_in_sample_map",
                "gene_CNV_file_id",
                "metadata_candidate_not_admitted",
                "sample_map_occurrences",
                "sample_submitter_id",
            },
        )
        if (
            row["exact_once_in_sample_map"] is not True
            or row["metadata_candidate_not_admitted"] is not True
        ):
            _fail()
        occurrence = _record(
            _records(row["sample_map_occurrences"], 1)[0], {"channel", "plex_index"}
        )
        channel = _text(occurrence["channel"])
        plex = _integer(occurrence["plex_index"], maximum=14)
        if channel not in _CHANNELS or (plex, channel) in seen_channels:
            _fail()
        seen_channels.add((plex, channel))
        binding = CandidateBinding(
            case_submitter_id=_text(row["case_submitter_id"]),
            sample_submitter_id=_text(row["sample_submitter_id"]),
            gdc_sample_uuid=_uuid(row["GDC_sample_uuid"]),
            protein_aliquot_submitter_id=_text(row["PDC_protein_aliquot_submitter_id"]),
            protein_aliquot_uuid=_uuid(row["PDC_protein_aliquot_uuid"]),
            rna_file_id=_uuid(row["RNA_file_id"]),
            cnv_file_id=_uuid(row["gene_CNV_file_id"]),
        )
        identifiers = (
            binding.case_submitter_id,
            binding.sample_submitter_id,
            binding.gdc_sample_uuid,
            binding.protein_aliquot_submitter_id,
            binding.protein_aliquot_uuid,
        )
        for seen_values, identifier in zip(seen, identifiers, strict=True):
            if identifier in seen_values:
                _fail()
            seen_values.add(identifier)
        for file_id, workflow in (
            (binding.rna_file_id, "STAR - Counts"),
            (binding.cnv_file_id, "AscatNGS"),
        ):
            if file_id in seen_files or file_id not in choices or choices[file_id][2] != workflow:
                _fail()
            seen_files.add(file_id)
        bindings.append(binding)
    if seen_files != set(choices):
        _fail()
    return tuple(
        sorted(
            bindings,
            key=lambda row: (row.case_submitter_id, row.sample_submitter_id, row.gdc_sample_uuid),
        )
    )


def _manifest_files(
    value: object, choices: Mapping[str, tuple[int, str, Workflow]]
) -> dict[str, AssayInputBinding]:
    result: dict[str, AssayInputBinding] = {}
    for item in _records(value, len(choices)):
        row = _record(
            item,
            {
                "bytes",
                "file_id",
                "md5",
                "official_size_and_md5_verified",
                "relative_path",
                "sha256",
                "workflow",
            },
        )
        file_id = _uuid(row["file_id"])
        if (
            file_id in result
            or file_id not in choices
            or row["official_size_and_md5_verified"] is not True
        ):
            _fail()
        length, md5, workflow = choices[file_id]
        if (
            row["relative_path"] != file_id + ".bin"
            or row["workflow"] != workflow
            or row["bytes"] != length
            or type(row["bytes"]) is not int
            or row["md5"] != md5
        ):
            _fail()
        result[file_id] = AssayInputBinding(
            relative_path=file_id + ".bin",
            lock=SourceLock(bytes=length, md5=md5, sha256=_sha256(row["sha256"])),
            workflow=workflow,
        )
    if set(result) != set(choices):
        _fail()
    return dict(sorted(result.items()))


def _decode_plan(
    choices: object,
    manifest: object,
    *,
    choices_sha256: str,
    files_manifest_sha256: str,
    candidate_count: int,
) -> ExternalAdmissionPlan:
    """Private pure fixture seam; public production admission has a fixed cohort."""

    _sha256(choices_sha256)
    _sha256(files_manifest_sha256)
    _integer(candidate_count, minimum=1, maximum=_CANDIDATES)
    _check_json(choices)
    _check_json(manifest)
    choice = _record(
        choices,
        {
            "GDC_candidate_file_choices",
            "PDC_candidate_source_files",
            "candidate_count",
            "measurement_downloaded",
            "sample_map_matched_candidate_rows",
            "status",
            "withheld_count_absent_from_map",
        },
    )
    downloaded = _record(
        manifest,
        {
            "failures",
            "files",
            "model_fits",
            "official_size_and_md5_verified_files",
            "redistribution_status",
            "requested_files",
            "schema",
            "selected_specimens",
            "source_plan_sha256",
            "verified_bytes",
        },
    )
    if (
        choice["status"] != _CHOICE_STATUS
        or choice["measurement_downloaded"] is not False
        or _integer(choice["candidate_count"]) != candidate_count
    ):
        _fail()
    _integer(choice["withheld_count_absent_from_map"], maximum=4_096)
    _pdc_sources(choice["PDC_candidate_source_files"])
    choice_files = _choice_files(choice["GDC_candidate_file_choices"], candidate_count)
    candidates = _candidate_bindings(
        choice["sample_map_matched_candidate_rows"], candidate_count, choice_files
    )
    if (
        downloaded["schema"] != "frozen-confirmatory-GDC-downloads/1.0.0"
        or downloaded["source_plan_sha256"] != choices_sha256
        or downloaded["model_fits"] is not False
        or downloaded["redistribution_status"] != "local_only_terms_unverified"
        or downloaded["failures"] != []
    ):
        _fail()
    for name, expected in (
        ("selected_specimens", candidate_count),
        ("requested_files", 2 * candidate_count),
        ("official_size_and_md5_verified_files", 2 * candidate_count),
    ):
        if _integer(downloaded[name]) != expected:
            _fail()
    files = _manifest_files(downloaded["files"], choice_files)
    total_bytes = sum(binding.lock.bytes for binding in files.values())
    if (
        _integer(downloaded["verified_bytes"], maximum=2 * _CANDIDATES * MAX_SOURCE_BYTES)
        != total_bytes
    ):
        _fail()
    receipt = ExternalAdmissionReceipt(
        profile_id=PROFILE_ID,
        choices_sha256=choices_sha256,
        files_manifest_sha256=files_manifest_sha256,
        candidate_count=candidate_count,
        rna_file_count=candidate_count,
        cnv_file_count=candidate_count,
        paired_file_count=2 * candidate_count,
        manifest_verified_bytes=total_bytes,
        metadata_candidate_not_admitted=True,
        issuer_authentication=False,
        eligibility_admitted=False,
        measurement_bytes_reverified=False,
        limitations=(
            "Caller-supplied digests establish byte integrity and replay binding, not GDC/PDC issuer authenticity.",
            "Specimen and aliquot joins are captured metadata assertions; this loader does not re-prove official ancestry.",
            "Metadata candidates are not clinical, scale, or measurement eligibility admission.",
            "Local measurement bytes require independent checksum verification by the assay readers.",
        ),
    )
    return ExternalAdmissionPlan(candidates=candidates, files=files, receipt=receipt)


def load_admission_plan(
    *,
    choices_path: Path,
    choices_sha256: str,
    files_manifest_path: Path,
    files_manifest_sha256: str,
) -> ExternalAdmissionPlan:
    """Load the fixed 56-candidate/112-file local replay plan without network calls."""

    _sha256(choices_sha256)
    _sha256(files_manifest_sha256)
    try:
        plan = _decode_plan(
            _read_json(choices_path, choices_sha256),
            _read_json(files_manifest_path, files_manifest_sha256),
            choices_sha256=choices_sha256,
            files_manifest_sha256=files_manifest_sha256,
            candidate_count=_CANDIDATES,
        )
        for binding in plan.files.values():
            metadata = _snapshot((files_manifest_path.parent / binding.relative_path).lstat())
            if metadata[2] != binding.lock.bytes:
                raise AdmissionPlanError("local assay byte count did not match its metadata")  # noqa: TRY301
    except AdmissionPlanError:
        raise
    except (OSError, TypeError, ValueError, RecursionError):
        raise AdmissionPlanError("captured admission metadata was not accepted") from None
    return plan


__all__ = [
    "MAX_PLAN_BYTES",
    "PROFILE_ID",
    "AdmissionPlanError",
    "AssayInputBinding",
    "CandidateBinding",
    "ExternalAdmissionPlan",
    "ExternalAdmissionReceipt",
    "load_admission_plan",
]
