"""Deterministic M04-04 fixed-point proteoform quality engine."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m04_03 import (
    ProteoformRawInputDisposition,
)
from glio_proteogen.contracts.m04_04 import (
    M0404_CONTRACT_VERSION,
    M0404_PARENT,
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityDisposition,
    ProteoformQualityMetricStatus,
    ProteoformQualityResult,
    expected_limitations,
    expected_uncertainty,
    quality_evidence_index,
    result_payload_digest,
)
from glio_proteogen.contracts.m04_04.v1 import (
    _derive_provenance,
    _expected_quality_bundle,
    _issue_raw_input_replay_capability,
    _validate_json_request_with_raw_capability,
    _validate_request_with_raw_capability,
    _validate_result_with_capability,
    _ValidatedRequestCapability,
)

_AUTHORIZATION_MESSAGE: Final = "proteoform quality computation requires accepted upstream controls"
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 250_000
_MAX_PLAIN_NODES: Final = 250_000
_MAX_PLAIN_BYTES: Final = 4 * 1024 * 1024


class ProteoformQualityAuthorizationError(PermissionError):
    """Authorization failed before upstream results or fact-ledger material were read."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-04 strict request values require exact string keys")


class _ForbiddenSafeFailureLedgerError(ValueError):
    def __init__(self) -> None:
        super().__init__("nonvalidated M04-03 input prohibits fact-ledger traversal")


class M0404ProteoformQualityEngine:
    """Compute one immutable four-role quality profile from governed aggregate facts."""

    __slots__ = ()

    def compute(self, request: object) -> ProteoformQualityResult:
        """Authorize, strictly replay, compute fixed-point metrics, and seal one result."""

        capability = _validated_request_capability(request)
        return _compute_result(capability)


def compute_proteoform_quality_metrics(request: object) -> ProteoformQualityResult:
    """Public stateless M04-04 operation."""

    return M0404ProteoformQualityEngine().compute(request)


def preflight_proteoform_quality_authorization(candidate: object) -> None:
    """Check seven exact controls without traversing upstream or ledger fields."""

    authorized = False
    try:
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        supported = (
            type(candidate) is ComputeProteoformQualityMetricsRequest or dict in candidate_mro
        )
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
        raise ProteoformQualityAuthorizationError from None
    if not authorized:
        raise ProteoformQualityAuthorizationError


def _validated_request_capability(candidate: object) -> _ValidatedRequestCapability:
    """Authorize and issue one exact contract-owned replay capability."""

    preflight_proteoform_quality_authorization(candidate)
    raw_candidate = _materialized_raw_candidate(candidate)
    raw_capability = _issue_raw_input_replay_capability(raw_candidate)
    _guard_safe_failure_ledger(candidate, raw_capability.result.disposition)
    materialized = _plain_value(candidate)
    return _validate_request_with_raw_capability(materialized, raw_capability)


def _validate_typed_request(candidate: object) -> ComputeProteoformQualityMetricsRequest:
    """Return the strict canonical request for the service validation boundary."""

    return _validated_request_capability(candidate).request


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ComputeProteoformQualityMetricsRequest:
    """Validate an already duplicate-free JSON boundary without premature ledger access."""

    preflight_proteoform_quality_authorization(candidate)
    raw_candidate = _materialized_raw_candidate(candidate)
    raw_capability = _issue_raw_input_replay_capability(raw_candidate)
    _guard_safe_failure_ledger(candidate, raw_capability.result.disposition)
    materialized = _plain_value(candidate)
    return _validate_json_request_with_raw_capability(
        serialized,
        materialized,
        raw_capability,
    ).request


def _materialized_raw_candidate(candidate: object) -> dict[str, object]:
    """Copy only the upstream result through built-ins before replaying it."""

    return {"raw_input_result": _plain_value(_member(candidate, "raw_input_result"))}


def _guard_safe_failure_ledger(
    candidate: object,
    disposition: ProteoformRawInputDisposition,
) -> None:
    """Reject a ledger capability without traversing it for nonvalidated upstream input."""

    if (
        disposition is not ProteoformRawInputDisposition.VALIDATED
        and _member(candidate, "fact_ledger") is not None
    ):
        raise _ForbiddenSafeFailureLedgerError


def _compute_result(
    capability: _ValidatedRequestCapability,
) -> ProteoformQualityResult:
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
        item.status is ProteoformQualityMetricStatus.WARNING and not item.required
        for item in metrics
    )
    payload: dict[str, object] = {
        "output_type": "proteoform_quality_profile",
        "result_id": f"result.m0404.{request_hash.removeprefix('sha256:')}",
        "result_version": M0404_CONTRACT_VERSION,
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
        "parent_target": M0404_PARENT,
        "emits_protein_rna_discordance": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "infers_glioma_specific_biology": False,
        "localizes_modification": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
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
            disposition is not ProteoformQualityDisposition.QUALIFIED or optional_warning
        ),
        "completed_at": request.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(payload)
    # Assemble without a second partial validation, then perform the one final strict
    # public replay over the complete immutable envelope.
    # Pydantic's generated signature cannot express a heterogeneous sealed payload map.
    assembled = ProteoformQualityResult.model_construct(**payload)  # type: ignore[arg-type]
    return _validate_result_with_capability(assembled, capability)


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


def _state_text(candidate: object) -> object:
    candidate_type = type(candidate)
    if candidate_type is str:
        return candidate
    candidate_mro = type.__getattribute__(candidate_type, "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _charge_plain_bytes(budget: list[int], value: str) -> None:
    """Bound caller-controlled UTF-8 strings before strict replay serialization."""

    budget[0] -= len(value.encode("utf-8")) + 2
    if budget[0] < 0:
        raise _InvalidPlainValueError


def _plain_value(  # noqa: C901, PLR0912 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
    _byte_budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    byte_budget = [_MAX_PLAIN_BYTES] if _byte_budget is None else _byte_budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if type(storage) is not dict or any(type(key) is not str for key in dict.keys(storage)):
            raise _InvalidPlainValueError
        if dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS:
            raise _InvalidPlainValueError
        result: dict[str, object] = {}
        for key in dict.keys(storage):
            key = cast("str", key)
            _charge_plain_bytes(byte_budget, key)
            result[key] = _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
        return result
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        result = {}
        for key in dict.keys(mapping):
            key = cast("str", key)
            _charge_plain_bytes(byte_budget, key)
            result[key] = _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
        return result
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return [
            _plain_value(
                item,
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(
                item,
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    if type(candidate) is str:
        _charge_plain_bytes(byte_budget, candidate)
    return candidate


__all__ = [
    "M0404ProteoformQualityEngine",
    "ProteoformQualityAuthorizationError",
    "compute_proteoform_quality_metrics",
    "preflight_proteoform_quality_authorization",
]
