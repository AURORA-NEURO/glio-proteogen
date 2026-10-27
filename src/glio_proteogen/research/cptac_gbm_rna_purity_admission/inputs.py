"""Private, exact local input configuration; loading reads metadata only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn, SupportsIndex

from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock

from .contracts import MAX_CONTEXT_SOURCES, AdmissionError, require


class _Private:
    __slots__ = ()

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private admission inputs cannot be serialized")


@dataclass(frozen=True, slots=True)
class LockedInput(_Private):
    path: Path = field(repr=False)
    lock: SourceLock = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or type(self.lock) is not SourceLock:
            raise AdmissionError("locked input declaration is invalid")
        SourceLock(self.lock.bytes, self.lock.md5, self.lock.sha256)


@dataclass(frozen=True, slots=True)
class DiscoveryInputs(_Private):
    choices_path: Path = field(repr=False)
    choices_sha256: str = field(repr=False)
    map_bindings_path: Path = field(repr=False)
    map_bindings_sha256: str = field(repr=False)
    files_manifest_path: Path = field(repr=False)
    files_manifest_sha256: str = field(repr=False)
    hgnc_path: Path = field(repr=False)
    context_evidence: LockedInput | None = field(default=None, repr=False)
    context_sources: tuple[LockedInput, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.context_sources) is not tuple
            or len(self.context_sources) > MAX_CONTEXT_SOURCES
            or any(type(source) is not LockedInput for source in self.context_sources)
            or (
                self.context_evidence is not None and type(self.context_evidence) is not LockedInput
            )
            or (self.context_evidence is None and self.context_sources)
        ):
            raise AdmissionError("context source declarations are invalid")
        if any(not isinstance(path, Path) for path in self.input_paths):
            raise AdmissionError("admission input paths are invalid")
        try:
            for value in (
                self.choices_sha256,
                self.map_bindings_sha256,
                self.files_manifest_sha256,
            ):
                metadata._sha256(value)
        except ValueError:
            raise AdmissionError("admission metadata lock is invalid") from None
        if len({source.lock.sha256 for source in self.context_sources}) != len(
            self.context_sources
        ):
            raise AdmissionError("context source declarations are invalid")

    @property
    def input_paths(self) -> tuple[Path, ...]:
        return (
            self.choices_path,
            self.map_bindings_path,
            self.files_manifest_path,
            self.hgnc_path,
            *((self.context_evidence.path,) if self.context_evidence is not None else ()),
            *(source.path for source in self.context_sources),
        )


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise AdmissionError("admission configuration schema is invalid")
    return value


def _path(base: Path, value: object) -> Path:
    if type(value) is not str or not value or "://" in value or "\x00" in value:
        raise AdmissionError("admission configuration path is invalid")
    try:
        path = Path(value)
        result = (path if path.is_absolute() else base / path).resolve()
        if not path.is_absolute() and not result.is_relative_to(base.resolve()):
            raise AdmissionError("relative admission configuration path leaves its input root")
    except (OSError, ValueError):
        raise AdmissionError("admission configuration path is invalid") from None
    return result


def _locked(base: Path, value: object) -> LockedInput:
    row = _object(value, {"path", "bytes", "md5", "sha256"})
    try:
        lock = SourceLock(bytes=row["bytes"], md5=row["md5"], sha256=row["sha256"])  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise AdmissionError("context source lock is invalid") from None
    return LockedInput(_path(base, row["path"]), lock)


def load_inputs(path: Path, *, sha256: str) -> DiscoveryInputs:
    """Verify one closed private config; do not read measurements or clinical rows."""
    try:
        row = _object(
            metadata._read_json(path, sha256),
            {"schema_version", "discovery", "hgnc_path", "context_evidence", "context_sources"},
        )
        require(
            row["schema_version"] == "cptac-gbm-rna-purity-inputs/1.0.0",
            "admission configuration version is invalid",
        )
        selection = _object(
            row["discovery"],
            {
                "choices_path",
                "choices_sha256",
                "map_bindings_path",
                "map_bindings_sha256",
                "files_manifest_path",
                "files_manifest_sha256",
            },
        )
        sources = row["context_sources"]
        if type(sources) is not list or len(sources) > MAX_CONTEXT_SOURCES:
            raise AdmissionError("context source declarations are invalid")  # noqa: TRY301 -- sanitized parser boundary
        base = path.resolve().parent
        return DiscoveryInputs(
            choices_path=_path(base, selection["choices_path"]),
            choices_sha256=selection["choices_sha256"],  # type: ignore[arg-type]
            map_bindings_path=_path(base, selection["map_bindings_path"]),
            map_bindings_sha256=selection["map_bindings_sha256"],  # type: ignore[arg-type]
            files_manifest_path=_path(base, selection["files_manifest_path"]),
            files_manifest_sha256=selection["files_manifest_sha256"],  # type: ignore[arg-type]
            hgnc_path=_path(base, row["hgnc_path"]),
            context_evidence=None
            if row["context_evidence"] is None
            else _locked(base, row["context_evidence"]),
            context_sources=tuple(_locked(base, source) for source in sources),
        )
    except AdmissionError:
        raise
    except (TypeError, ValueError, OSError, RecursionError):
        raise AdmissionError("admission configuration was not accepted") from None


__all__ = ["DiscoveryInputs", "LockedInput", "load_inputs"]
