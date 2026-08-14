"""Strict validate-then-run plugin boundary for M05-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_02 import PtmLocalizationIdentityLineageResolution
from glio_proteogen.contracts.m05_03 import PtmLocalizationRawInputValidationResult
from glio_proteogen.contracts.m05_03.v1 import _validate_exact_request_storage
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion.engine import (
    _contracts,
    _prepare_ptm_localization_raw_inputs,
    _PreparedPtmLocalizationRawInputs,
    _validate_json_request,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.contracts.m05_03 import IngestPtmLocalizationRawInputsRequest
    from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion.service import (
        M0503Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-03",
    title="PtmLocalization raw input ingestion",
    version="1.0.0",
    owner="Data engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "external scientific payloads, spectra, sequences, rows, or measurements",
        "identity, consent, protein, ptm_localization, PTM, or variant peptide inference",
        "kinase-state inference, all-omics fusion, treatment, or clinical recommendation",
        "upstream mutation, relabeling, deduplication, repair, or missing-as-negative use",
        "model execution, event persistence, or external authority authentication",
    ),
)


@dataclass(frozen=True, slots=True)
class M0503Submission:
    """Metadata request plus the separate four-role immutable manifest mapping."""

    request: object
    artifacts_by_role: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0503Request:
    """Opaque capability carrying a strict request and immutable parsed documents."""

    request: IngestPtmLocalizationRawInputsRequest
    _prepared: _PreparedPtmLocalizationRawInputs
    _seal: object


@dataclass(frozen=True, slots=True)
class _IssuedM0503TokenSnapshot:
    request: IngestPtmLocalizationRawInputsRequest
    request_bytes: bytes
    lineage_result: PtmLocalizationIdentityLineageResolution
    lineage_result_bytes: bytes
    prepared: _PreparedPtmLocalizationRawInputs
    snapshots: tuple[tuple[object, bytes], ...]
    documents: tuple[BaseModel, ...]
    document_bytes: tuple[bytes, ...]


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0503Request, _IssuedM0503TokenSnapshot]] = (
    WeakKeyDictionary()
)


def _token_is_issued(token: ValidatedM0503Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    try:
        request = object.__getattribute__(token, "request")
        prepared = object.__getattribute__(token, "_prepared")
        if (
            snapshot is None
            or type(request) is not _contracts().IngestPtmLocalizationRawInputsRequest
            or type(prepared) is not _PreparedPtmLocalizationRawInputs
            or snapshot.request is not request
            or snapshot.prepared is not prepared
        ):
            return False
        _validate_exact_request_storage(request)
        request_storage = object.__getattribute__(request, "__dict__")
        lineage_result = dict.__getitem__(request_storage, "lineage_result")
        if (
            type(lineage_result) is not PtmLocalizationIdentityLineageResolution
            or snapshot.lineage_result is not lineage_result
            or snapshot.lineage_result_bytes
            != canonical_json_bytes(_contracts().normalized_lineage_result(lineage_result))
            or snapshot.request_bytes
            != canonical_json_bytes(_contracts().normalized_request(request))
            or snapshot.snapshots is not prepared.snapshots
            or snapshot.documents is not prepared.documents
            or len(snapshot.documents) != len(snapshot.document_bytes)
        ):
            return False
        return all(
            snapshot.documents[index] is document
            and snapshot.document_bytes[index]
            == canonical_json_bytes(_contracts().normalized_document(document))
            for index, document in enumerate(prepared.documents)
        )
    except Exception:  # noqa: BLE001 - mutated or forged capabilities fail closed.
        return False


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-03 validation requires a raw-input submission")


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-03 execution requires a validated request token")


class M0503Plugin(
    ModulePlugin[object, ValidatedM0503Request, PtmLocalizationRawInputValidationResult]
):
    """Grant one immutable manifest-ingestion capability after strict validation."""

    __slots__ = ("_service",)

    def __init__(self, service: M0503Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: object) -> ValidatedM0503Request:
        if type(submission) is not M0503Submission:
            raise _InvalidSubmissionError
        typed = submission
        candidate = typed.request
        contracts = _contracts()
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(
                serialized,
                max_bytes=contracts.M0503_MAX_CANONICAL_REQUEST_BYTES,
            )
            request = _validate_json_request(decoded, serialized)
        else:
            request = self._service.validate_request(candidate)
        if request.lineage_result.disposition.value != "reconciled":
            prepared = _PreparedPtmLocalizationRawInputs(snapshots=(), documents=())
        else:
            prepared = _prepare_ptm_localization_raw_inputs(request, typed.artifacts_by_role)
        if type(request.lineage_result) is not PtmLocalizationIdentityLineageResolution:
            raise _InvalidExecutionTokenError
        token = ValidatedM0503Request(
            request=request,
            _prepared=prepared,
            _seal=_TOKEN_SEAL,
        )
        _ISSUED_TOKENS[token] = _IssuedM0503TokenSnapshot(
            request=request,
            request_bytes=canonical_json_bytes(contracts.normalized_request(request)),
            lineage_result=request.lineage_result,
            lineage_result_bytes=canonical_json_bytes(
                contracts.normalized_lineage_result(request.lineage_result)
            ),
            prepared=prepared,
            snapshots=prepared.snapshots,
            documents=prepared.documents,
            document_bytes=tuple(
                canonical_json_bytes(contracts.normalized_document(document))
                for document in prepared.documents
            ),
        )
        return token

    def run(self, request: ValidatedM0503Request) -> PtmLocalizationRawInputValidationResult:
        if (
            type(request) is not ValidatedM0503Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_prepared(request.request, request._prepared)


__all__ = ["M0503Plugin", "M0503Submission", "ValidatedM0503Request"]
