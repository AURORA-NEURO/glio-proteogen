"""Deterministic M04-06 proteoform support harmonization engine."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m04_05 import (
    ProteoformArtifactDetectionResult,
    ProteoformArtifactDisposition,
)
from glio_proteogen.contracts.m04_06 import (
    M0406_CONTRACT_VERSION,
    HarmonizeProteoformAnalysisRequest,
    ProteoformArtifactEvaluationState,
    ProteoformArtifactHarmonizationReceipt,
    ProteoformHarmonizationDisposition,
    ProteoformHarmonizationPolicy,
    ProteoformHarmonizationResult,
    ProteoformSupportLedger,
    artifact_harmonization_receipt,
    canonical_request_digest,
    configuration_digest,
    expected_computation_receipt,
    expected_disposition,
    expected_harmonization_findings,
    expected_limitations,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    harmonization_evidence_index,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ExecutionContext
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization.kernel import (
    M0406ProteoformHarmonizationKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeProteoformAnalysisRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteoformHarmonizationResult)
_CONTEXT_ADAPTER: Final = TypeAdapter(ExecutionContext)
_ARTIFACT_RESULT_ADAPTER: Final = TypeAdapter(ProteoformArtifactDetectionResult)
_ARTIFACT_RECEIPT_ADAPTER: Final = TypeAdapter(ProteoformArtifactHarmonizationReceipt)
_POLICY_ADAPTER: Final = TypeAdapter(ProteoformHarmonizationPolicy)
_LEDGER_ADAPTER: Final = TypeAdapter(ProteoformSupportLedger)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MISSING: Final = object()
_MAX_PLAIN_DEPTH: Final = 96
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 4096
_MAX_PLAIN_NODES: Final = 500_000


class ProteoformHarmonizationAuthorizationError(ValueError):
    """Denied controls detected before receipt or support-ledger traversal."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize proteoform support harmonization")


class _ArtifactReceiptMismatchError(ValueError):
    def __init__(self) -> None:
        super().__init__("artifact receipt must replay the exact embedded M04-05 result")


class M0406ProteoformHarmonizationEngine:
    """Produce one immutable, replay-closed fixed-point harmonization result."""

    __slots__ = ("_kernel",)

    def __init__(
        self,
        kernel: M0406ProteoformHarmonizationKernel | None = None,
    ) -> None:
        self._kernel = kernel or M0406ProteoformHarmonizationKernel()

    def harmonize(self, request: object) -> ProteoformHarmonizationResult:
        """Authorize, reconstruct, harmonize, and self-validate one request."""

        validated = _validate_prepared_request(_prepare_harmonization_request_candidate(request))
        return self._harmonize_validated(validated)

    def _harmonize_validated(
        self,
        request: HarmonizeProteoformAnalysisRequest,
    ) -> ProteoformHarmonizationResult:
        """Execute one request issued by this module's strict validation boundary."""

        return _harmonization_result(request, self._kernel)


def harmonize_proteoform_analysis(
    request: object,
) -> ProteoformHarmonizationResult:
    """Public stateless M04-06 operation."""

    return M0406ProteoformHarmonizationEngine().harmonize(request)


def preflight_proteoform_harmonization_authorization(candidate: object) -> None:
    """Check seven controls without traversing the receipt or support ledger."""

    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if type(candidate) is not HarmonizeProteoformAnalysisRequest and dict not in candidate_mro:
        raise ProteoformHarmonizationAuthorizationError
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
        raise ProteoformHarmonizationAuthorizationError from None
    if states != expected:
        raise ProteoformHarmonizationAuthorizationError


def _validate_json_request(
    candidate: object,
    _raw_payload: bytes | bytearray | str,
) -> HarmonizeProteoformAnalysisRequest:
    """Validate an already strict-decoded JSON object exactly once."""

    return _validate_prepared_request(_prepare_harmonization_request_candidate(candidate))


def _prepare_harmonization_request_candidate(candidate: object) -> dict[str, object]:
    """Replay M04-05 and policy metadata before materializing the support ledger."""

    preflight_proteoform_harmonization_authorization(candidate)
    artifact_result = _ARTIFACT_RESULT_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(_member(candidate, "artifact_result"))),
        strict=True,
    )
    derived_receipt = artifact_harmonization_receipt(artifact_result)
    supplied_receipt = _ARTIFACT_RECEIPT_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(_member(candidate, "artifact_receipt"))),
        strict=True,
    )
    if supplied_receipt != derived_receipt:
        raise _ArtifactReceiptMismatchError
    policy = _POLICY_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(_member(candidate, "policy"))),
        strict=True,
    )
    context = _CONTEXT_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(_member(candidate, "context"))),
        strict=True,
    )
    may_traverse_ledger = (
        derived_receipt.evaluation_state is ProteoformArtifactEvaluationState.COMPLETE
        and derived_receipt.artifact_disposition is ProteoformArtifactDisposition.CLEARED
        and derived_receipt.target_count <= policy.max_targets
    )
    ledger: ProteoformSupportLedger | None = None
    if may_traverse_ledger:
        ledger_raw = _member(candidate, "support_ledger")
        if ledger_raw is not _MISSING and ledger_raw is not None:
            ledger = _LEDGER_ADAPTER.validate_json(
                canonical_json_bytes(_plain_value(ledger_raw)),
                strict=True,
            )
    payload: dict[str, object] = {
        "context": context,
        "artifact_result": artifact_result,
        "artifact_receipt": derived_receipt,
        "support_ledger": ledger,
        "policy": policy,
        "supersedes_result_digest": _optional_plain_member(
            candidate,
            "supersedes_result_digest",
        ),
    }
    for field in ("operation", "contract_version"):
        value = _member(candidate, field)
        if value is not _MISSING:
            payload[field] = _plain_value(value)
    return payload


def _validate_prepared_request(
    candidate: dict[str, object],
) -> HarmonizeProteoformAnalysisRequest:
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
    elif BaseModel in candidate_mro:
        mapping = cast(
            "dict[object, object]",
            object.__getattribute__(candidate, "__dict__"),
        )
    else:
        return _MISSING
    if (
        type(mapping) is not dict
        or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
        or any(type(key) is not str for key in dict.keys(mapping))
    ):
        raise _InvalidPlainValueError
    return dict.__getitem__(mapping, field) if dict.__contains__(mapping, field) else _MISSING


def _optional_plain_member(candidate: object, field: str) -> object:
    value = _member(candidate, field)
    return None if value is _MISSING else _plain_value(value)


def _state_text(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-06 strict request values require exact built-in containers")


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
        storage = cast(
            "dict[object, object]",
            object.__getattribute__(candidate, "__dict__"),
        )
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
        if (
            type(mapping) is not dict
            or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(mapping))
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
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    return candidate


def _harmonization_result(
    request: HarmonizeProteoformAnalysisRequest,
    kernel: M0406ProteoformHarmonizationKernel,
) -> ProteoformHarmonizationResult:
    execution = kernel.harmonize(request)
    findings = expected_harmonization_findings(
        request,
        execution.transformation_manifest,
        execution.technical_effect_diagnostics,
        execution.invariant_diagnostics,
    )
    disposition = expected_disposition(request, findings)
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.policy)
    payload: dict[str, object] = {
        "output_type": "proteoform_harmonized_analysis",
        "result_id": f"result.m0406.{request_hash.removeprefix('sha256:')}",
        "result_version": M0406_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "receipt": expected_computation_receipt(
            request,
            disposition,
            execution.analysis,
            execution.transformation_manifest,
        ),
        "analysis": execution.analysis,
        "transformation_manifest": execution.transformation_manifest,
        "technical_effect_diagnostics": execution.technical_effect_diagnostics,
        "invariant_diagnostics": execution.invariant_diagnostics,
        "findings": findings,
        "disposition": disposition,
        "parent_target": "protein_rna_discordance",
        "emits_protein_rna_discordance": False,
        "infers_identity": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_kinase_activity": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(disposition),
        "provenance": expected_provenance(request),
        "evidence": harmonization_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": (disposition is not ProteoformHarmonizationDisposition.ACCEPTED),
        "completed_at": request.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(
        ProteoformHarmonizationResult.model_construct(**payload)  # type: ignore[arg-type]
    )
    materialized = cast(
        "dict[str, Any]",
        # Trusted output is bounded by the typed request and its closed collections.
        json.loads(canonical_json_bytes(payload)),
    )
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


__all__ = [
    "M0406ProteoformHarmonizationEngine",
    "ProteoformHarmonizationAuthorizationError",
    "harmonize_proteoform_analysis",
    "preflight_proteoform_harmonization_authorization",
]
