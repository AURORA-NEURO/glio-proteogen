"""Deterministic M03-03 protein-inference raw-source admission engine."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any, BinaryIO, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_03 import (
    M0303_CONTRACT_VERSION,
    M0303_ZERO_DIGEST,
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceParseDiagnostic,
    ProteinInferenceRawAdmissionResult,
    ValidatedProteinInferenceRawInput,
    admission_evidence_index,
    canonical_request_digest,
    configuration_digest,
    expected_admission_receipt,
    expected_disposition,
    expected_limitations,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    expected_upstream_diagnostics,
    normalized_request,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion.parser import (
    cross_source_diagnostics,
    diagnostic,
    parse_source,
)

type RawInputSource = bytes | bytearray | memoryview | BinaryIO

_REQUEST_ADAPTER: Final = TypeAdapter(IngestProteinInferenceRawInputsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceRawAdmissionResult)
_AUTHORIZATION_MESSAGE: Final = (
    "protein-inference raw ingestion requires accepted upstream controls"
)


class ProteinInferenceRawIngestionAuthorizationError(RuntimeError):
    """Authorization failed before request or source-mapping traversal."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class ProteinInferenceRawIngestionInputErrorCode(StrEnum):
    SOURCE_SET_MISMATCH = "source_set_mismatch"
    SOURCE_TYPE_INVALID = "source_type_invalid"
    SOURCE_READ_FAILED = "source_read_failed"
    TOTAL_SOURCE_LIMIT_EXCEEDED = "total_source_limit_exceeded"


class ProteinInferenceRawIngestionInputError(ValueError):
    """Stable, content-free source boundary failure."""

    def __init__(self, code: ProteinInferenceRawIngestionInputErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class M0303ProteinInferenceRawIngestionEngine:
    """Validate an authorized, content-addressed protein-inference source capsule."""

    __slots__ = ()

    def ingest(
        self,
        request: object,
        sources: Mapping[str, RawInputSource],
    ) -> ProteinInferenceRawAdmissionResult:
        """Authorize, strictly reconstruct, snapshot, parse, close, and self-validate."""

        preflight_protein_inference_raw_ingestion_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        validated = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        safe_diagnostics = expected_upstream_diagnostics(validated)
        if safe_diagnostics:
            return _result(validated, (), safe_diagnostics)

        payloads = prepare_protein_inference_raw_inputs(validated, sources)
        parsed = tuple(
            parse_source(validated, source, payloads[source.source_id])
            for source in sorted(validated.sources, key=canonical_json_bytes)
        )
        diagnostics = [item for parsed_item in parsed for item in parsed_item.output.diagnostics]
        diagnostics.extend(cross_source_diagnostics(validated, parsed))
        if sum(item.output.decoded_size_bytes for item in parsed) > (
            validated.policy.max_total_decoded_bytes
        ):
            diagnostics.append(
                diagnostic(
                    ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED,
                    tuple(item.output.source_id for item in parsed),
                )
            )
        raw_inputs = tuple(item.output for item in parsed)
        return _result(validated, raw_inputs, tuple(diagnostics))


def ingest_protein_inference_raw_inputs(
    request: object,
    sources: Mapping[str, RawInputSource],
) -> ProteinInferenceRawAdmissionResult:
    """Public stateless M03-03 operation."""

    return M0303ProteinInferenceRawIngestionEngine().ingest(request, sources)


def preflight_protein_inference_raw_ingestion_authorization(candidate: object) -> None:
    """Check exactly seven control states, suppressing Exception but not BaseException."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = (
            ("approved_configuration", "accepted"),
            ("identity_lineage", "resolved"),
            ("provenance", "accepted"),
            ("consent", "granted"),
            ("quality", "accepted"),
            ("support", "accepted"),
            ("intended_use", "accepted"),
        )
        authorized = all(
            _state(_member(_member(references, role), "state")) == value for role, value in expected
        )
    except Exception:  # noqa: BLE001 - hostile mapping failures become one closed outcome.
        raise ProteinInferenceRawIngestionAuthorizationError from None
    if not authorized:
        raise ProteinInferenceRawIngestionAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def prepare_protein_inference_raw_inputs(
    request: IngestProteinInferenceRawInputsRequest,
    sources: Mapping[str, RawInputSource],
) -> Mapping[str, bytes]:
    """Close the mapping, then read each source once in canonical declaration order."""

    expected = {item.source_id for item in request.sources}
    if not isinstance(sources, Mapping):
        raise ProteinInferenceRawIngestionInputError(
            ProteinInferenceRawIngestionInputErrorCode.SOURCE_SET_MISMATCH
        )
    try:
        supplied = _bounded_source_ids(sources, expected)
    except Exception:  # noqa: BLE001 - sanitize hostile Mapping implementation failures.
        raise ProteinInferenceRawIngestionInputError(
            ProteinInferenceRawIngestionInputErrorCode.SOURCE_SET_MISMATCH
        ) from None
    if supplied != expected:
        raise ProteinInferenceRawIngestionInputError(
            ProteinInferenceRawIngestionInputErrorCode.SOURCE_SET_MISMATCH
        )

    payloads: dict[str, bytes] = {}
    total = 0
    for declaration in sorted(request.sources, key=canonical_json_bytes):
        try:
            source = sources[declaration.source_id]
        except Exception:  # noqa: BLE001 - never expose a hostile mapping's submitted content.
            raise ProteinInferenceRawIngestionInputError(
                ProteinInferenceRawIngestionInputErrorCode.SOURCE_READ_FAILED
            ) from None
        snapshot = _snapshot_source(source, request.policy.max_source_bytes)
        payloads[declaration.source_id] = snapshot
        total += len(snapshot)
    if total > request.policy.max_total_source_bytes:
        raise ProteinInferenceRawIngestionInputError(
            ProteinInferenceRawIngestionInputErrorCode.TOTAL_SOURCE_LIMIT_EXCEEDED
        )
    return MappingProxyType(payloads)


def _bounded_source_ids(
    sources: Mapping[str, RawInputSource],
    expected: set[str],
) -> set[str]:
    """Read only enough mapping keys to prove exact source-set equality.

    The caller owns this mapping, so it may contain an arbitrarily large or
    non-terminating iterator.  The request contract caps declarations at 64;
    one additional key is enough to reject an oversized mapping without
    materializing its entire key set.
    """

    supplied: set[str] = set()
    iterator = iter(sources)
    for _ in range(len(expected) + 1):
        try:
            source_id = next(iterator)
        except StopIteration:
            break
        if not isinstance(source_id, str) or source_id in supplied:
            raise ValueError
        supplied.add(source_id)
        if len(supplied) > len(expected):
            raise ValueError
    return supplied


def _snapshot_source(source: RawInputSource, limit: int) -> bytes:
    if isinstance(source, bytes):
        return source[: limit + 1]
    if isinstance(source, bytearray | memoryview):
        return bytes(source[: limit + 1])
    reader = getattr(source, "read", None)
    if not callable(reader):
        raise ProteinInferenceRawIngestionInputError(
            ProteinInferenceRawIngestionInputErrorCode.SOURCE_TYPE_INVALID
        )
    chunks: list[bytes] = []
    remaining = limit + 1
    try:
        while remaining:
            chunk = reader(min(64 * 1024, remaining))
            if not isinstance(chunk, bytes):
                raise ProteinInferenceRawIngestionInputError(  # noqa: TRY301
                    ProteinInferenceRawIngestionInputErrorCode.SOURCE_TYPE_INVALID
                )
            if not chunk:
                break
            bounded = chunk[:remaining]
            chunks.append(bounded)
            remaining -= len(bounded)
    except ProteinInferenceRawIngestionInputError:
        raise
    except Exception:  # noqa: BLE001 - hostile stream errors never echo content.
        raise ProteinInferenceRawIngestionInputError(
            ProteinInferenceRawIngestionInputErrorCode.SOURCE_READ_FAILED
        ) from None
    return b"".join(chunks)


def _result(
    request: IngestProteinInferenceRawInputsRequest,
    raw_inputs: tuple[ValidatedProteinInferenceRawInput, ...],
    diagnostics: tuple[ProteinInferenceParseDiagnostic, ...],
) -> ProteinInferenceRawAdmissionResult:
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.policy)
    ordered_inputs = tuple(sorted(raw_inputs, key=canonical_json_bytes))
    ordered_diagnostics = tuple(sorted(set(diagnostics), key=canonical_json_bytes))
    disposition = expected_disposition(ordered_diagnostics)
    payload: dict[str, object] = {
        "output_type": "protein_inference_raw_admission_result",
        "result_id": f"result.m0303.{request_hash.removeprefix('sha256:')}",
        "result_version": M0303_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "result_digest": M0303_ZERO_DIGEST,
        "request": request,
        "receipt": expected_admission_receipt(request, disposition),
        "raw_inputs": ordered_inputs,
        "diagnostics": ordered_diagnostics,
        "disposition": disposition,
        "parent_target": "complex_activity",
        "emits_complex_activity": False,
        "infers_identity": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "infers_glioma_specific_biology": False,
        "infers_kinase_activity": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(request, request_hash),
        "evidence": admission_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": disposition is not ProteinInferenceAdmissionDisposition.VALIDATED,
        "completed_at": request.context.occurred_at,
    }
    materialized = cast(
        "dict[str, Any]",
        # Trusted internal output may exceed the public request parser cap.
        json.loads(canonical_json_bytes(payload)),
    )
    materialized["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


__all__ = [
    "M0303ProteinInferenceRawIngestionEngine",
    "ProteinInferenceRawIngestionAuthorizationError",
    "ProteinInferenceRawIngestionInputError",
    "ProteinInferenceRawIngestionInputErrorCode",
    "RawInputSource",
    "ingest_protein_inference_raw_inputs",
    "preflight_protein_inference_raw_ingestion_authorization",
    "prepare_protein_inference_raw_inputs",
]
