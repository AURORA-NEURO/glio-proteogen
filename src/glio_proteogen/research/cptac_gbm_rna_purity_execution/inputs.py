"""Closed private declarations for source-qualified native RNA execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn, SupportsIndex

from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import (
    DiscoveryInputs,
    LockedInput,
    _locked,
    _object,
    _path,
)

from .contracts import ExecutionError, ExecutionPolicy, checked_policy

CLINICAL_ROLES = (
    "metadata_archive",
    "subtypes_archive",
    "pdc_biospecimens",
    "gdc_clinical",
    "pdc_status",
    "gdc_status",
)


@dataclass(frozen=True, slots=True, repr=False)
class ExecutionInputs:
    discovery: DiscoveryInputs = field(repr=False)
    gencode_gtf_path: Path = field(repr=False)
    gencode_hgnc_path: Path = field(repr=False)
    author_feature_path: Path = field(repr=False)
    clinical_sources: tuple[LockedInput, ...] = field(repr=False)
    processing_source: LockedInput = field(repr=False)
    policy: ExecutionPolicy

    def __post_init__(self) -> None:
        if (
            type(self.discovery) is not DiscoveryInputs
            or self.discovery.context_evidence is not None
            or self.discovery.context_sources
            or type(self.clinical_sources) is not tuple
            or len(self.clinical_sources) != len(CLINICAL_ROLES)
            or any(type(source) is not LockedInput for source in self.clinical_sources)
            or type(self.processing_source) is not LockedInput
            or any(not isinstance(path, Path) for path in self.reference_paths)
        ):
            raise ExecutionError("execution source declarations are invalid")
        DiscoveryInputs(
            **{name: getattr(self.discovery, name) for name in self.discovery.__dataclass_fields__}
        )
        for source in (*self.clinical_sources, self.processing_source):
            LockedInput(source.path, source.lock)
        checked_policy(self.policy)

    @property
    def reference_paths(self) -> tuple[Path, ...]:
        return self.gencode_gtf_path, self.gencode_hgnc_path, self.author_feature_path

    @property
    def input_paths(self) -> tuple[Path, ...]:
        return (
            *self.discovery.input_paths,
            *self.reference_paths,
            *(source.path for source in self.clinical_sources),
            self.processing_source.path,
        )

    def __repr__(self) -> str:
        return "<ExecutionInputs private>"

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private execution inputs cannot be serialized")


def load_inputs(path: Path, *, sha256: str) -> ExecutionInputs:
    """Verify the exact config before reading clinical or measurement payloads."""
    try:
        row = _object(
            metadata._read_json(path, sha256),
            {
                "schema_version",
                "discovery",
                "hgnc_path",
                "references",
                "clinical_sources",
                "processing_source",
                "policy",
            },
        )
        if row["schema_version"] != "cptac-gbm-rna-purity-execution-inputs/1.0.0":
            raise ExecutionError("execution configuration version is invalid")  # noqa: TRY301
        base = path.resolve().parent
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
        references = _object(row["references"], {"gencode_gtf", "gencode_hgnc", "author_features"})
        sources = _object(row["clinical_sources"], set(CLINICAL_ROLES))
        return ExecutionInputs(
            discovery=DiscoveryInputs(
                choices_path=_path(base, selection["choices_path"]),
                choices_sha256=selection["choices_sha256"],  # type: ignore[arg-type]
                map_bindings_path=_path(base, selection["map_bindings_path"]),
                map_bindings_sha256=selection["map_bindings_sha256"],  # type: ignore[arg-type]
                files_manifest_path=_path(base, selection["files_manifest_path"]),
                files_manifest_sha256=selection["files_manifest_sha256"],  # type: ignore[arg-type]
                hgnc_path=_path(base, row["hgnc_path"]),
            ),
            gencode_gtf_path=_path(base, references["gencode_gtf"]),
            gencode_hgnc_path=_path(base, references["gencode_hgnc"]),
            author_feature_path=_path(base, references["author_features"]),
            clinical_sources=tuple(_locked(base, sources[role]) for role in CLINICAL_ROLES),
            processing_source=_locked(base, row["processing_source"]),
            policy=ExecutionPolicy.model_validate(row["policy"], strict=True),
        )
    except ExecutionError:
        raise
    except (AttributeError, OSError, TypeError, ValueError, RecursionError):
        raise ExecutionError("execution configuration was not accepted") from None


__all__ = ["CLINICAL_ROLES", "ExecutionInputs", "load_inputs"]
