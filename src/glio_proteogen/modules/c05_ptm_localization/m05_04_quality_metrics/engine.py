"""Deterministic M05-04 fixed-point ptm_localization quality engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Final, cast
from weakref import ReferenceType, ref

from pydantic import BaseModel

from glio_proteogen.contracts.m05_03 import (
    PtmLocalizationRawInputDisposition,
    PtmLocalizationRawInputValidationResult,
)
from glio_proteogen.contracts.m05_04 import (
    M0504_CONTRACT_VERSION,
    M0504_PARENT,
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationQualityDisposition,
    PtmLocalizationQualityMetricStatus,
    PtmLocalizationQualityResult,
    expected_limitations,
    expected_uncertainty,
    normalized_raw_input_result,
    normalized_request,
    quality_evidence_index,
    result_payload_digest,
)
from glio_proteogen.contracts.m05_04.v1 import (
    _derive_provenance,
    _expected_quality_bundle,
    _issue_raw_input_replay_capability,
    _request_capability_is_issued,
    _validate_json_request_with_raw_capability,
    _validate_request_with_raw_capability,
    _validate_result_with_capability,
    _ValidatedRequestCapability,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_AUTHORIZATION_MESSAGE: Final = (
    "ptm_localization quality computation requires accepted upstream controls"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MAX_PLAIN_DEPTH: Final = 72
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 150_000
_MAX_PLAIN_SEQUENCE: Final = 4_096
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "raw_input_result",
        "policy",
        "fact_ledger",
        "supersedes_result_digest",
    }
)


@dataclass(frozen=True, slots=True)
class _IssuedM0504RequestSnapshot:
    """Weak admission memo bound to the exact request and M05-03 result identities."""

    source_ref: ReferenceType[ComputePtmLocalizationQualityMetricsRequest]
    source_raw_ref: ReferenceType[PtmLocalizationRawInputValidationResult]
    source_bytes: bytes
    source_raw_bytes: bytes
    capability: _ValidatedRequestCapability
    validated_request: ComputePtmLocalizationQualityMetricsRequest
    validated_bytes: bytes
    validated_raw_result: PtmLocalizationRawInputValidationResult
    validated_raw_bytes: bytes


_ISSUED_REQUESTS: Final[dict[int, _IssuedM0504RequestSnapshot]] = {}
_ISSUED_REQUESTS_LOCK: Final = Lock()


class PtmLocalizationQualityAuthorizationError(PermissionError):
    """Authorization failed before upstream results or fact-ledger material were read."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-04 strict request values require exact string keys")


class _ForbiddenSafeFailureLedgerError(ValueError):
    def __init__(self) -> None:
        super().__init__("nonvalidated M05-03 input prohibits fact-ledger traversal")


class M0504PtmLocalizationQualityEngine:
    """Compute one immutable four-role quality profile from governed aggregate facts."""

    __slots__ = ()

    def compute(self, request: object) -> PtmLocalizationQualityResult:
        """Authorize, strictly replay, compute fixed-point metrics, and seal one result."""

        capability = _validated_request_capability(request)
        return _compute_result(capability)


def compute_ptm_localization_quality_metrics(request: object) -> PtmLocalizationQualityResult:
    """Public stateless M05-04 operation."""

    return M0504PtmLocalizationQualityEngine().compute(request)


def preflight_ptm_localization_quality_authorization(candidate: object) -> None:
    """Check seven exact controls without traversing upstream or ledger fields."""

    authorized = False
    try:
        supported = type(candidate) in {ComputePtmLocalizationQualityMetricsRequest, dict}
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {
            role: _state_text(_member(_member(references, role), "state")) for role in expected
        }
        authorized = supported and states == expected
    except Exception:  # noqa: BLE001 - hostile caller objects fail closed.
        raise PtmLocalizationQualityAuthorizationError from None
    if not authorized:
        raise PtmLocalizationQualityAuthorizationError


def _validated_request_capability(candidate: object) -> _ValidatedRequestCapability:
    """Authorize and issue one exact contract-owned replay capability."""

    preflight_ptm_localization_quality_authorization(candidate)
    _validate_outer_request_shape(candidate)
    cached = _reuse_validated_request(candidate)
    if cached is not None:
        return cached
    raw_candidate = _materialized_raw_candidate(candidate)
    raw_capability = _issue_raw_input_replay_capability(raw_candidate)
    _guard_safe_failure_ledger(candidate, raw_capability.result.disposition)
    materialized = _plain_value(candidate)
    capability = _validate_request_with_raw_capability(materialized, raw_capability)
    _remember_validated_request(candidate, capability)
    return capability


def _validate_typed_request(candidate: object) -> ComputePtmLocalizationQualityMetricsRequest:
    """Return the strict canonical request for the service validation boundary."""

    return _validated_request_capability(candidate).request


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ComputePtmLocalizationQualityMetricsRequest:
    """Validate an already duplicate-free JSON boundary without premature ledger access."""

    return _validate_json_request_capability(candidate, serialized).request


def _validate_json_request_capability(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> _ValidatedRequestCapability:
    """Validate one duplicate-free JSON request and retain its sealed admission proof."""

    preflight_ptm_localization_quality_authorization(candidate)
    _validate_outer_request_shape(candidate)
    raw_candidate = _materialized_raw_candidate(candidate)
    raw_capability = _issue_raw_input_replay_capability(raw_candidate)
    _guard_safe_failure_ledger(candidate, raw_capability.result.disposition)
    materialized = _plain_value(candidate)
    return _validate_json_request_with_raw_capability(
        serialized,
        materialized,
        raw_capability,
    )


def _retire_issued_request(
    key: int,
    dead_ref: ReferenceType[ComputePtmLocalizationQualityMetricsRequest],
) -> None:
    with _ISSUED_REQUESTS_LOCK:
        current = _ISSUED_REQUESTS.get(key)
        if current is not None and current.source_ref is dead_ref:
            _ISSUED_REQUESTS.pop(key, None)


def _remember_validated_request(
    source: object,
    capability: _ValidatedRequestCapability,
) -> None:
    if type(source) is not ComputePtmLocalizationQualityMetricsRequest:
        return
    _validate_outer_request_shape(source)
    validated = capability.request
    _validate_outer_request_shape(validated)
    source_raw = object.__getattribute__(source, "raw_input_result")
    validated_raw = object.__getattribute__(validated, "raw_input_result")
    if (
        type(source_raw) is not PtmLocalizationRawInputValidationResult
        or type(validated_raw) is not PtmLocalizationRawInputValidationResult
    ):
        raise _InvalidPlainValueError
    key = id(source)
    source_ref = ref(source, lambda dead_ref: _retire_issued_request(key, dead_ref))
    snapshot = _IssuedM0504RequestSnapshot(
        source_ref=source_ref,
        source_raw_ref=ref(source_raw),
        source_bytes=canonical_json_bytes(normalized_request(source)),
        source_raw_bytes=canonical_json_bytes(normalized_raw_input_result(source_raw)),
        capability=capability,
        validated_request=validated,
        validated_bytes=canonical_json_bytes(normalized_request(validated)),
        validated_raw_result=validated_raw,
        validated_raw_bytes=canonical_json_bytes(normalized_raw_input_result(validated_raw)),
    )
    with _ISSUED_REQUESTS_LOCK:
        _ISSUED_REQUESTS[key] = snapshot


def _reuse_validated_request(candidate: object) -> _ValidatedRequestCapability | None:
    if type(candidate) is not ComputePtmLocalizationQualityMetricsRequest:
        return None
    key = id(candidate)
    with _ISSUED_REQUESTS_LOCK:
        snapshot = _ISSUED_REQUESTS.get(key)
    if snapshot is None or snapshot.source_ref() is not candidate:
        return None
    try:
        _validate_outer_request_shape(candidate)
        source_raw = object.__getattribute__(candidate, "raw_input_result")
        validated = snapshot.validated_request
        _validate_outer_request_shape(validated)
        valid = (
            snapshot.source_raw_ref() is source_raw
            and type(source_raw) is PtmLocalizationRawInputValidationResult
            and snapshot.capability.request is validated
            and _request_capability_is_issued(snapshot.capability)
            and validated.raw_input_result is snapshot.validated_raw_result
            and type(validated.raw_input_result) is PtmLocalizationRawInputValidationResult
            and canonical_json_bytes(normalized_request(candidate)) == snapshot.source_bytes
            and canonical_json_bytes(normalized_raw_input_result(source_raw))
            == snapshot.source_raw_bytes
            and canonical_json_bytes(normalized_request(validated)) == snapshot.validated_bytes
            and canonical_json_bytes(normalized_raw_input_result(validated.raw_input_result))
            == snapshot.validated_raw_bytes
        )
    except Exception:  # noqa: BLE001 - a stale private admission memo fails closed.
        valid = False
    if valid:
        return snapshot.capability
    with _ISSUED_REQUESTS_LOCK:
        if _ISSUED_REQUESTS.get(key) is snapshot:
            _ISSUED_REQUESTS.pop(key, None)
    return None


def _materialized_raw_candidate(candidate: object) -> dict[str, object]:
    """Copy only the upstream result through built-ins before replaying it."""

    return {"raw_input_result": _plain_value(_member(candidate, "raw_input_result"))}


def _guard_safe_failure_ledger(
    candidate: object,
    disposition: PtmLocalizationRawInputDisposition,
) -> None:
    """Reject a ledger capability without traversing it for nonvalidated upstream input."""

    if (
        disposition is not PtmLocalizationRawInputDisposition.VALIDATED
        and _member(candidate, "fact_ledger") is not None
    ):
        raise _ForbiddenSafeFailureLedgerError


def _compute_result(
    capability: _ValidatedRequestCapability,
) -> PtmLocalizationQualityResult:
    if type(capability) is not _ValidatedRequestCapability or not _request_capability_is_issued(
        capability
    ):
        raise _InvalidPlainValueError
    request = capability.request
    bundle = _expected_quality_bundle(request)
    metrics = bundle.metrics
    findings = bundle.findings
    disposition = bundle.disposition
    assay_quality = bundle.assay_quality
    receipt = bundle.receipt
    request_hash = capability.request_digest
    active_policy_hash = capability.policy_digest
    configuration_hash = capability.configuration_digest
    optional_warning = any(
        item.status is PtmLocalizationQualityMetricStatus.WARNING and not item.required
        for item in metrics
    )
    payload: dict[str, object] = {
        "output_type": "ptm_localization_quality_profile",
        "result_id": f"result.m0504.{request_hash.removeprefix('sha256:')}",
        "result_version": M0504_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": active_policy_hash,
        "configuration_digest": configuration_hash,
        "receipt_digest": receipt.receipt_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "receipt": receipt,
        "assay_quality": assay_quality,
        "findings": findings,
        "disposition": disposition,
        "parent_target": M0504_PARENT,
        "emits_variant_peptide": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_ptm_localization": False,
        "infers_isoform": False,
        "localizes_modification": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
        "persists_events": False,
        "support": bundle.support,
        "uncertainty": expected_uncertainty(),
        "provenance": _derive_provenance(
            request,
            metrics,
            receipt,
            request_hash=request_hash,
            policy_hash=active_policy_hash,
            config_hash=configuration_hash,
        ),
        "evidence": quality_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": (
            disposition is not PtmLocalizationQualityDisposition.QUALIFIED or optional_warning
        ),
        "completed_at": request.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(payload)
    # Assemble without a second partial validation, then perform the one final strict
    # public replay over the complete immutable envelope.
    # Pydantic's generated signature cannot express a heterogeneous sealed payload map.
    assembled = PtmLocalizationQualityResult.model_construct(**payload)  # type: ignore[arg-type]
    return _validate_result_with_capability(assembled, capability)


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if type(candidate) is dict:
        mapping = cast("dict[object, object]", candidate)
        _validate_plain_mapping(mapping)
        return dict.get(mapping, field)
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        return dict.get(storage, field)
    return None


def _validate_plain_mapping(mapping: dict[object, object]) -> None:
    if (
        type(mapping) is not dict
        or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
        or any(type(key) is not str for key in dict.keys(mapping))
    ):
        raise _InvalidPlainValueError


def _validate_outer_request_shape(candidate: object) -> None:
    if type(candidate) is ComputePtmLocalizationQualityMetricsRequest:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        if set(dict.keys(storage)) != _REQUEST_FIELDS:
            raise _InvalidPlainValueError
        return
    if type(candidate) is not dict:
        raise _InvalidPlainValueError
    mapping = cast("dict[object, object]", candidate)
    _validate_plain_mapping(mapping)
    if any(key not in _REQUEST_FIELDS for key in dict.keys(mapping)):
        raise _InvalidPlainValueError


def _state_text(candidate: object) -> object:
    candidate_type = type(candidate)
    if candidate_type is str:
        return candidate
    candidate_mro = type.__getattribute__(candidate_type, "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(  # noqa: C901 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        return {
            key: _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(storage)
        }
    if type(candidate) is dict:
        mapping = cast("dict[object, object]", candidate)
        _validate_plain_mapping(mapping)
        return {
            key: _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(mapping)
        }
    if type(candidate) is list:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if type(candidate) is tuple:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        if type(value) is not str:
            raise _InvalidPlainValueError
        return candidate
    if isinstance(candidate, Mapping) or (
        not isinstance(candidate, str) and isinstance(candidate, Sequence)
    ):
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M0504PtmLocalizationQualityEngine",
    "PtmLocalizationQualityAuthorizationError",
    "compute_ptm_localization_quality_metrics",
    "preflight_ptm_localization_quality_authorization",
]
