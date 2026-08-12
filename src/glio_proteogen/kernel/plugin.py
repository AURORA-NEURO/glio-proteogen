"""Minimal plugin ABI used by the first and all future bounded modules."""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar, runtime_checkable

from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, SemanticVersion

RequestT = TypeVar("RequestT", contravariant=True)
ResponseT = TypeVar("ResponseT", covariant=True)
ValidatedT = TypeVar("ValidatedT")


class ModuleDescriptor(FrozenModel):
    module_id: str
    title: NonEmptyStr
    version: SemanticVersion
    owner: NonEmptyStr
    safety_class: str
    gate: str
    prohibited_outputs: tuple[NonEmptyStr, ...]


@runtime_checkable
class ModulePlugin(Protocol, Generic[RequestT, ValidatedT, ResponseT]):
    """A module validates first, then executes only its validated request type."""

    def descriptor(self) -> ModuleDescriptor: ...

    def validate(self, request: RequestT) -> ValidatedT: ...

    def run(self, request: ValidatedT) -> ResponseT: ...
