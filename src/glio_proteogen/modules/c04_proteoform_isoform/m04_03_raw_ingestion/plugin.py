"""Strict validate-then-run plugin boundary for M04-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_03 import ProteoformRawInputValidationResult
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion.engine import (
    _contracts,
    _prepare_proteoform_raw_inputs,
    _PreparedProteoformRawInputs,
    preflight_proteoform_raw_input_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m04_03 import IngestProteoformRawInputsRequest
    from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion.service import (
        M0403Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-03",
    title="Proteoform raw input ingestion",
    version="1.0.0",
    owner="Clinical science",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "external scientific payloads, spectra, sequences, rows, or measurements",
        "identity, consent, protein, proteoform, PTM, or protein-RNA discordance inference",
        "kinase-state inference, all-omics fusion, treatment, or clinical recommendation",
        "upstream mutation, relabeling, deduplication, repair, or missing-as-negative use",
        "model execution, event persistence, or external authority authentication",
    ),
)


@dataclass(frozen=True, slots=True)
class M0403Submission:
    """Metadata request plus the separate four-role immutable manifest mapping."""

    request: object
    artifacts_by_role: object


@dataclass(frozen=True, slots=True)
class ValidatedM0403Request:
    """Opaque capability carrying a strict request and immutable parsed documents."""

    request: IngestProteoformRawInputsRequest
    _prepared: _PreparedProteoformRawInputs
    _seal: object


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-03 validation requires a raw-input submission")


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-03 execution requires a validated request token")


class M0403Plugin(ModulePlugin[object, ValidatedM0403Request, ProteoformRawInputValidationResult]):
    """Grant one immutable manifest-ingestion capability after strict validation."""

    __slots__ = ("_service",)

    def __init__(self, service: M0403Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: object) -> ValidatedM0403Request:
        if type(submission) is not M0403Submission:
            raise _InvalidSubmissionError
        typed = submission
        candidate = typed.request
        contracts = _contracts()
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(
                serialized,
                max_bytes=contracts.M0403_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_proteoform_raw_input_authorization(decoded)
            candidate = TypeAdapter(contracts.IngestProteoformRawInputsRequest).validate_json(
                serialized, strict=True
            )
        request = self._service.validate_request(candidate)
        if request.lineage_result.disposition.value != "reconciled":
            prepared = _PreparedProteoformRawInputs(snapshots=(), documents=())
        else:
            prepared = _prepare_proteoform_raw_inputs(request, typed.artifacts_by_role)
        return ValidatedM0403Request(
            request=request,
            _prepared=prepared,
            _seal=_TOKEN_SEAL,
        )

    def run(self, request: ValidatedM0403Request) -> ProteoformRawInputValidationResult:
        if type(request) is not ValidatedM0403Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service._execute_prepared(request.request, request._prepared)


__all__ = ["M0403Plugin", "M0403Submission", "ValidatedM0403Request"]
