"""Fail-closed common-plugin scaffold for M04-08 release packaging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from glio_proteogen.contracts.m04_08 import M0408DependencyUnavailableError
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    BuiltProteoformRelease,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.service import (
        M0408Service,
    )

_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-08",
    title="Provenance and release packaging",
    version="1.0.0",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "private keys, signing secrets, or release-authority claims",
        "protein-RNA discordance, proteoform, proteotype, subtype, or kinase inference",
        "generic all-omics fusion or direct treatment recommendation",
        "mutation, relabeling, or disagreement erasure in upstream evidence",
        "missing or unsupported evidence interpreted as negative",
    ),
)


@dataclass(frozen=True, slots=True)
class ProteoformReleaseSubmission:
    request: object
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _UnavailableValidationToken:
    """Unconstructable-by-API marker while the M04-07 ABI is unavailable."""


def _dependency_error(phase: str) -> M0408DependencyUnavailableError:
    return M0408DependencyUnavailableError(
        f"M04-08 plugin {phase} awaits the exact frozen M04-07 public ABI"
    )


class M0408Plugin(ModulePlugin[object, _UnavailableValidationToken, BuiltProteoformRelease]):
    """Publish metadata while refusing guessed validation or execution."""

    __slots__ = ("_service",)

    def __init__(self, service: M0408Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> _UnavailableValidationToken:
        del request
        raise _dependency_error("validation")

    def run(self, request: _UnavailableValidationToken) -> BuiltProteoformRelease:
        del request
        raise _dependency_error("execution")


__all__ = ["M0408Plugin", "ProteoformReleaseSubmission"]
