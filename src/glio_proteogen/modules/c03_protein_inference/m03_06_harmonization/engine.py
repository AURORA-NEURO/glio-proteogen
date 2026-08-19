"""Deterministic M03-06 protein-inference support harmonization engine."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m03_05 import ProteinInferenceArtifactDisposition
from glio_proteogen.contracts.m03_06 import (
    M0306_CONTRACT_VERSION,
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MAX_OBSERVATIONS,
    M0306_ZERO_DIGEST,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceArtifactEvaluationState,
    ProteinInferenceHarmonizationDisposition,
    ProteinInferenceHarmonizationResult,
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
    normalized_request,
    policy_digest,
    preflight_authorized,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization.kernel import (
    M0306ProteinInferenceHarmonizationKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeProteinInferenceSupportRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceHarmonizationResult)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = M0306_MAX_OBSERVATIONS
_MAX_PLAIN_NODES: Final = 250_000
_MAX_PLAIN_BYTES: Final = M0306_MAX_CANONICAL_REQUEST_BYTES


class ProteinInferenceHarmonizationAuthorizationError(ValueError):
    """Denied controls detected before receipt or support-ledger traversal."""

    def __init__(self) -> None:
        super().__init__(
            "upstream controls do not authorize protein-inference support harmonization"
        )


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-06 strict request values require bounded built-in containers")


class M0306ProteinInferenceHarmonizationEngine:
    """Produce one immutable, replay-closed fixed-point harmonization result."""

    __slots__ = ("_kernel",)

    def __init__(
        self,
        kernel: M0306ProteinInferenceHarmonizationKernel | None = None,
    ) -> None:
        self._kernel = kernel or M0306ProteinInferenceHarmonizationKernel()

    def harmonize(self, request: object) -> ProteinInferenceHarmonizationResult:
        """Authorize, reconstruct, harmonize, and self-validate one request."""

        preflight_protein_inference_harmonization_authorization(request)
        candidate = prepare_harmonization_request_candidate(request)
        validated = _REQUEST_ADAPTER.validate_python(_plain_value(candidate), strict=True)
        validated = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        return _harmonization_result(validated, self._kernel)


def harmonize_protein_inference_support(
    request: object,
) -> ProteinInferenceHarmonizationResult:
    """Public stateless M03-06 operation."""

    return M0306ProteinInferenceHarmonizationEngine().harmonize(request)


def preflight_protein_inference_harmonization_authorization(candidate: object) -> None:
    """Check seven controls without traversing the receipt or support ledger."""

    if not preflight_authorized(candidate):
        raise ProteinInferenceHarmonizationAuthorizationError


def prepare_harmonization_request_candidate(candidate: object) -> object:
    """Drop an untrusted ledger when shallow metadata already proves safe failure."""

    if not isinstance(candidate, dict):
        return candidate
    try:
        receipt = dict.get(candidate, "artifact_receipt")
        policy = dict.get(candidate, "policy")
        evaluation_state = _state(_member(receipt, "evaluation_state"))
        disposition = _state(_member(receipt, "artifact_disposition"))
        unit_count = _member(receipt, "unit_count")
        max_units = _member(policy, "max_units")
    except Exception:  # noqa: BLE001 - strict reconstruction handles malformed metadata.
        return candidate
    shape_excess = (
        evaluation_state == ProteinInferenceArtifactEvaluationState.COMPLETE.value
        and type(unit_count) is int
        and type(max_units) is int
        and unit_count > max_units
    )
    known_upstream_failure = disposition in {
        ProteinInferenceArtifactDisposition.REJECTED.value,
        ProteinInferenceArtifactDisposition.QUARANTINED.value,
        ProteinInferenceArtifactDisposition.ABSTAINED.value,
    }
    if (
        evaluation_state != ProteinInferenceArtifactEvaluationState.NOT_EVALUABLE.value
        and not shape_excess
        and not known_upstream_failure
    ):
        return candidate
    sanitized = dict.copy(candidate)
    sanitized["support_ledger"] = None
    return sanitized


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, dict):
        return dict.get(candidate, field)
    return getattr(candidate, field, None)


def _charge_plain_bytes(budget: list[int], value: str) -> None:
    """Bound caller-controlled strings before strict request replay."""

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
    """Materialize only bounded built-in containers for direct Python ingress."""

    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    byte_budget = [_MAX_PLAIN_BYTES] if _byte_budget is None else _byte_budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        return candidate
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS:
            raise _InvalidPlainValueError
        result: dict[str, object] = {}
        for key in dict.keys(mapping):
            if type(key) is not str:
                raise _InvalidPlainValueError
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
    if Mapping in candidate_mro or isinstance(candidate, Mapping):
        raise _InvalidPlainValueError
    if type(candidate) is str:
        _charge_plain_bytes(byte_budget, candidate)
    return candidate


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _harmonization_result(
    request: HarmonizeProteinInferenceSupportRequest,
    kernel: M0306ProteinInferenceHarmonizationKernel,
) -> ProteinInferenceHarmonizationResult:
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
        "output_type": "protein_inference_harmonized_analysis",
        "result_id": f"result.m0306.{request_hash.removeprefix('sha256:')}",
        "result_version": M0306_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "result_digest": M0306_ZERO_DIGEST,
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
        "parent_target": "complex_activity",
        "emits_complex_activity": False,
        "infers_identity": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "infers_glioma_specific_biology": False,
        "infers_kinase_activity": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(disposition),
        "provenance": expected_provenance(request),
        "evidence": harmonization_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": (
            disposition is not ProteinInferenceHarmonizationDisposition.ACCEPTED
        ),
        "completed_at": request.context.occurred_at,
    }
    materialized = cast(
        "dict[str, Any]",
        # Trusted output is bounded by the typed request and its closed collections.
        json.loads(canonical_json_bytes(payload)),
    )
    materialized["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


__all__ = [
    "M0306ProteinInferenceHarmonizationEngine",
    "ProteinInferenceHarmonizationAuthorizationError",
    "harmonize_protein_inference_support",
    "preflight_protein_inference_harmonization_authorization",
    "prepare_harmonization_request_candidate",
]
