"""Deterministic M04-05 event-sourced artifact detector."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m04_04 import (
    ProteoformQualityDisposition,
    ProteoformQualityResult,
)
from glio_proteogen.contracts.m04_05 import (
    M0405_CONTRACT_VERSION,
    M0405_DETECTOR_CLASS_COUNT,
    M0405_MAX_CANONICAL_REQUEST_BYTES,
    M0405_MAX_EVENT_EVIDENCE,
    M0405_MAX_EVENTS,
    M0405_MAX_PROFILES,
    M0405_PARENT,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactEvidenceLedgerBinding,
    ProteoformArtifactPolicy,
    canonical_request_digest,
    configuration_digest,
    expected_detection_bundle,
    expected_result_id,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m04_05.v1 import (
    _QUALITY_CAPABILITY_CONTEXT_KEY,
    _REQUEST_CAPABILITY_CONTEXT_KEY,
    _issue_quality_replay_capability,
    _issue_validated_request_capability,
    _ReplayedM0404Capability,
    _ValidatedM0405RequestCapability,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ExecutionContext

_AUTHORIZATION_MESSAGE: Final = "proteoform artifact detection requires accepted upstream controls"
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MISSING: Final = object()
_QUALITY_ADAPTER: Final = TypeAdapter(ProteoformQualityResult)
_POLICY_ADAPTER: Final = TypeAdapter(ProteoformArtifactPolicy)
_REQUEST_ADAPTER: Final = TypeAdapter(DetectProteoformArtifactsRequest)
_CONTEXT_ADAPTER: Final = TypeAdapter(ExecutionContext)
_LEDGER_ADAPTER: Final = TypeAdapter(ProteoformArtifactEvidenceLedger)
_LEDGER_BINDING_ADAPTER: Final = TypeAdapter(ProteoformArtifactEvidenceLedgerBinding)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 250_000
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "quality_result",
        "policy",
        "evidence_ledger",
        "supersedes_result_digest",
    }
)


class ProteoformArtifactAuthorizationError(PermissionError):
    """Authorization failed before upstream quality or artifact events were read."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class ProteoformArtifactInputError(ValueError):
    """An authorized request failed closed without reflecting caller content."""

    def __init__(self) -> None:
        super().__init__("M04-05 request failed strict validation")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-05 strict request values require exact built-in containers")


class _ForbiddenEvidenceLedgerError(ValueError):
    def __init__(self) -> None:
        super().__init__("M04-05 safe-failure or unsupported input prohibits ledger traversal")


class _SerializedRequestTooLargeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M04-05 canonical request exceeds its byte limit")


class M0405ProteoformArtifactEngine:
    """Replay one M04-04 result and deterministically reduce aggregate artifact events."""

    __slots__ = ()

    def detect(self, request: object) -> ProteoformArtifactDetectionResult:
        prepared = _prepare_artifact_request_candidate(request)
        validated = _validate_prepared_request(prepared)
        return self._detect_validated(validated)

    @staticmethod
    def _detect_validated(
        request: DetectProteoformArtifactsRequest,
    ) -> ProteoformArtifactDetectionResult:
        capability = _issue_validated_request_capability(request)
        return _compute_result(request, capability)


def detect_proteoform_artifacts(request: object) -> ProteoformArtifactDetectionResult:
    """Public stateless M04-05 operation."""

    return M0405ProteoformArtifactEngine().detect(request)


def preflight_proteoform_artifact_authorization(candidate: object) -> None:
    """Check all seven controls without touching the quality result or evidence ledger."""

    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if type(candidate) is not DetectProteoformArtifactsRequest and dict not in candidate_mro:
        raise ProteoformArtifactAuthorizationError
    try:
        context = _member(candidate, "context")
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
    except Exception:  # noqa: BLE001 - hostile ordinary exceptions fail closed.
        raise ProteoformArtifactAuthorizationError from None
    if states != expected:
        raise ProteoformArtifactAuthorizationError


def _prepare_artifact_request_candidate(
    candidate: object,
) -> tuple[dict[str, object], _ReplayedM0404Capability]:
    """Authorize, replay M04-04, select support, then and only then materialize the ledger."""

    preflight_proteoform_artifact_authorization(candidate)
    try:
        return _prepare_authorized_artifact_request_candidate(candidate)
    except (_ForbiddenEvidenceLedgerError, _InvalidPlainValueError):
        raise
    except Exception:  # noqa: BLE001 - caller content must never escape the library boundary.
        raise ProteoformArtifactInputError from None


def _prepare_authorized_artifact_request_candidate(
    candidate: object,
) -> tuple[dict[str, object], _ReplayedM0404Capability]:
    _validate_outer_request_shape(candidate)
    quality_raw = _member(candidate, "quality_result")
    policy_raw = _member(candidate, "policy")
    quality = _QUALITY_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(quality_raw)),
        strict=True,
    )
    quality_capability = _issue_quality_replay_capability(quality)
    _validate_policy_shape_before_copy(policy_raw)
    policy_candidate = (
        policy_raw if type(policy_raw) is ProteoformArtifactPolicy else _plain_value(policy_raw)
    )
    policy = _POLICY_ADAPTER.validate_json(
        canonical_json_bytes(policy_candidate),
        strict=True,
    )
    profile_supported = any(
        quality.result_version in profile.approved_quality_contract_versions
        and quality.configuration_digest in profile.approved_quality_configuration_digests
        for profile in policy.profiles
    )
    may_traverse = (
        quality.disposition is ProteoformQualityDisposition.QUALIFIED and profile_supported
    )
    ledger_raw = _member(candidate, "evidence_ledger")
    if not may_traverse and ledger_raw is not _MISSING and ledger_raw is not None:
        raise _ForbiddenEvidenceLedgerError
    ledger: object = None
    if may_traverse and ledger_raw is not _MISSING and ledger_raw is not None:
        declared_quality_digest = _member(ledger_raw, "quality_result_digest")
        if type(declared_quality_digest) is str and (
            declared_quality_digest == quality.result_digest
        ):
            _validate_ledger_shape_before_copy(ledger_raw)
            ledger_candidate = (
                ledger_raw
                if type(ledger_raw) is ProteoformArtifactEvidenceLedger
                else _plain_value(ledger_raw)
            )
            ledger = _LEDGER_ADAPTER.validate_json(
                canonical_json_bytes(ledger_candidate),
                strict=True,
            )
        else:
            ledger = _LEDGER_BINDING_ADAPTER.validate_json(
                canonical_json_bytes(_materialize_ledger_binding(ledger_raw)),
                strict=True,
            )
    context = _CONTEXT_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(_member(candidate, "context"))),
        strict=True,
    )
    payload: dict[str, object] = {
        "request_id": _plain_value(_member(candidate, "request_id")),
        "context": context,
        "quality_result": quality,
        "policy": policy,
        "evidence_ledger": ledger,
        "supersedes_result_digest": _optional_plain_member(
            candidate,
            "supersedes_result_digest",
        ),
    }
    operation = _member(candidate, "operation")
    contract_version = _member(candidate, "contract_version")
    if operation is not _MISSING:
        payload["operation"] = _plain_value(operation)
    if contract_version is not _MISSING:
        payload["contract_version"] = _plain_value(contract_version)
    return payload, quality_capability


def _validate_prepared_request(
    prepared: tuple[dict[str, object], _ReplayedM0404Capability],
) -> DetectProteoformArtifactsRequest:
    payload, quality_capability = prepared
    try:
        return _REQUEST_ADAPTER.validate_python(
            payload,
            strict=True,
            context={_QUALITY_CAPABILITY_CONTEXT_KEY: quality_capability},
        )
    except Exception:  # noqa: BLE001 - never reflect nested caller content.
        raise ProteoformArtifactInputError from None


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> DetectProteoformArtifactsRequest:
    serialized_size = (
        len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    )
    if serialized_size > M0405_MAX_CANONICAL_REQUEST_BYTES:
        raise _SerializedRequestTooLargeError
    return _validate_prepared_request(_prepare_artifact_request_candidate(candidate))


def _compute_result(
    request: DetectProteoformArtifactsRequest,
    capability: _ValidatedM0405RequestCapability,
) -> ProteoformArtifactDetectionResult:
    bundle = expected_detection_bundle(request)
    request_hash = canonical_request_digest(request)
    active_policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.policy)
    payload: dict[str, object] = {
        "output_type": "proteoform_artifact_contamination_assessment",
        "result_id": expected_result_id(request),
        "result_version": M0405_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": active_policy_hash,
        "configuration_digest": configuration_hash,
        "receipt_digest": bundle.receipt.receipt_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "receipt": bundle.receipt,
        "artifact_posteriors": bundle.artifact_posteriors,
        "contamination_flags": bundle.contamination_flags,
        "exclusion_mask": bundle.exclusion_mask,
        "findings": bundle.findings,
        "disposition": bundle.disposition,
        "parent_target": M0405_PARENT,
        "emits_protein_rna_discordance": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "localizes_modification": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
        "support": bundle.support,
        "uncertainty": bundle.uncertainty,
        "provenance": bundle.provenance,
        "evidence": bundle.evidence,
        "limitations": bundle.limitations,
        "human_review_required": bundle.human_review_required,
        "completed_at": request.context.occurred_at,
    }
    assembled = ProteoformArtifactDetectionResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(assembled)
    return ProteoformArtifactDetectionResult.model_validate(
        payload,
        strict=True,
        context={_REQUEST_CAPABILITY_CONTEXT_KEY: capability},
    )


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        return dict.__getitem__(mapping, field) if dict.__contains__(mapping, field) else _MISSING
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            raise _InvalidPlainValueError
        return dict.__getitem__(storage, field) if dict.__contains__(storage, field) else _MISSING
    return _MISSING


def _validate_outer_request_shape(candidate: object) -> None:
    if type(candidate) is DetectProteoformArtifactsRequest:
        return
    mapping = cast("dict[object, object]", candidate)
    if any(key not in _REQUEST_FIELDS for key in dict.keys(mapping)):
        raise ProteoformArtifactInputError


def _optional_plain_member(candidate: object, field: str) -> object:
    value = _member(candidate, field)
    return None if value is _MISSING else _plain_value(value)


def _materialize_ledger_binding(candidate: object) -> object:
    if type(candidate) is ProteoformArtifactEvidenceLedgerBinding:
        return candidate
    return {
        field: _plain_value(_member(candidate, field))
        for field in (
            "ledger_id",
            "version",
            "quality_result_digest",
            "recorded_at",
            "ledger_digest",
            "evidence",
        )
    }


def _built_in_sequence_length(candidate: object) -> int | None:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if list in candidate_mro:
        return list.__len__(cast("list[object]", candidate))
    if tuple in candidate_mro:
        return tuple.__len__(cast("tuple[object, ...]", candidate))
    return None


def _validate_policy_shape_before_copy(candidate: object) -> None:
    if type(candidate) is ProteoformArtifactPolicy:
        return
    profiles = _member(candidate, "profiles")
    profile_count = _built_in_sequence_length(profiles)
    if profile_count is not None and profile_count > M0405_MAX_PROFILES:
        raise _InvalidPlainValueError
    if profile_count is None:
        return
    profile_values = (
        list.__iter__(cast("list[object]", profiles))
        if list in type.__getattribute__(type(profiles), "__mro__")
        else tuple.__iter__(cast("tuple[object, ...]", profiles))
    )
    for profile in profile_values:
        threshold_count = _built_in_sequence_length(_member(profile, "thresholds"))
        if threshold_count is not None and threshold_count != M0405_DETECTOR_CLASS_COUNT:
            raise _InvalidPlainValueError


def _validate_ledger_shape_before_copy(candidate: object) -> None:
    if type(candidate) is ProteoformArtifactEvidenceLedger:
        return
    events = _member(candidate, "events")
    event_count = _built_in_sequence_length(events)
    if event_count is not None and event_count > M0405_MAX_EVENTS:
        raise _InvalidPlainValueError
    if event_count is None:
        return
    event_values = (
        list.__iter__(cast("list[object]", events))
        if list in type.__getattribute__(type(events), "__mro__")
        else tuple.__iter__(cast("tuple[object, ...]", events))
    )
    for event in event_values:
        evidence_count = _built_in_sequence_length(_member(event, "evidence"))
        if evidence_count is not None and evidence_count > M0405_MAX_EVENT_EVIDENCE:
            raise _InvalidPlainValueError


def _state_text(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
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
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(mapping)
        }
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > M0405_MAX_EVENTS:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > M0405_MAX_EVENTS:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M0405ProteoformArtifactEngine",
    "ProteoformArtifactAuthorizationError",
    "ProteoformArtifactInputError",
    "detect_proteoform_artifacts",
    "preflight_proteoform_artifact_authorization",
]
