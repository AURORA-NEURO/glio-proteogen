"""Deterministic M03-04 protein-inference evidence-graph quality engine."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m03_03 import ProteinInferenceAdmissionDisposition
from glio_proteogen.contracts.m03_04 import (
    M0304_CONTRACT_VERSION,
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    M0304_MAX_CANONICAL_RESULT_BYTES,
    M0304_ZERO_DIGEST,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityResult,
    canonical_request_digest,
    configuration_digest,
    expected_computation_receipt,
    expected_disposition,
    expected_limitations,
    expected_provenance,
    expected_quality_findings,
    expected_support,
    expected_uncertainty,
    normalized_request,
    policy_digest,
    quality_evidence_index,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.kernel import (
    compute_quality_metrics,
    matching_quality_profile,
    quality_ledger_bindings_close,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeProteinInferenceQualityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceQualityResult)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 250_000
_MAX_PLAIN_BYTES: Final = max(
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    M0304_MAX_CANONICAL_RESULT_BYTES,
)


class ProteinInferenceQualityAuthorizationError(ValueError):
    """Denied upstream controls detected before fact-ledger traversal."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize protein-inference quality computation")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-04 strict values require bounded built-in containers")


class M0304ProteinInferenceQualityEngine:
    """Compute one immutable protein-inference evidence-graph quality profile."""

    __slots__ = ()

    def compute(self, request: object) -> ProteinInferenceQualityResult:
        """Authorize, strictly reconstruct, evaluate, and self-validate one request."""

        preflight_protein_inference_quality_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)
        validated = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        return _compute_result(validated)


def compute_protein_inference_quality(request: object) -> ProteinInferenceQualityResult:
    """Public stateless M03-04 operation."""

    return M0304ProteinInferenceQualityEngine().compute(request)


def preflight_protein_inference_quality_authorization(candidate: object) -> None:
    """Check the seven control states without traversing the fact ledger."""

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
            _state(_member(_member(references, role), "state")) == state for role, state in expected
        )
    except Exception:  # noqa: BLE001 - hostile accessors collapse to one safe denial.
        raise ProteinInferenceQualityAuthorizationError from None
    if not authorized:
        raise ProteinInferenceQualityAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        if dict in candidate_mro:
            return dict.get(cast("dict[object, object]", candidate), field)
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _charge_plain_bytes(budget: list[int], value: str) -> None:
    """Bound caller-controlled strings before strict quality replay."""

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
    """Materialize only bounded built-in containers for direct M03-04 ingress."""

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


def _compute_result(
    request: ComputeProteinInferenceQualityRequest,
) -> ProteinInferenceQualityResult:
    """Compute only inside the exact supported, bound quality envelope."""

    receipt = request.raw_quality_receipt
    policy_supported = (
        receipt.upstream_disposition is ProteinInferenceAdmissionDisposition.VALIDATED
        and receipt.source_count <= request.policy.max_sources
        and receipt.lineage_artifact_count <= request.policy.max_lineage_artifacts
    )
    profile = matching_quality_profile(request) if policy_supported else None
    traversable = (
        policy_supported
        and request.fact_ledger is not None
        and quality_ledger_bindings_close(request)
        and profile is not None
    )
    metrics = compute_quality_metrics(request, profile) if traversable and profile else ()
    findings = expected_quality_findings(request, metrics)
    disposition = expected_disposition(request, metrics, findings)
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.policy)
    payload: dict[str, object] = {
        "output_type": "protein_inference_quality_profile",
        "result_id": f"result.m0304.{request_hash.removeprefix('sha256:')}",
        "result_version": M0304_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "result_digest": M0304_ZERO_DIGEST,
        "request": request,
        "receipt": expected_computation_receipt(request, disposition, profile),
        "metrics": metrics,
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
        "support": expected_support(disposition, metrics),
        "uncertainty": expected_uncertainty(disposition),
        "provenance": expected_provenance(request, disposition),
        "evidence": quality_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": (
            disposition is not ProteinInferenceQualityDisposition.QUALIFIED
            or any(
                not item.required and item.status is ProteinInferenceQualityMetricStatus.WARNING
                for item in metrics
            )
        ),
        "completed_at": request.context.occurred_at,
    }
    materialized = cast(
        "dict[str, Any]",
        # Trusted output is already bounded by its typed request and closed collections.
        json.loads(canonical_json_bytes(payload)),
    )
    materialized["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


__all__ = [
    "M0304ProteinInferenceQualityEngine",
    "ProteinInferenceQualityAuthorizationError",
    "compute_protein_inference_quality",
    "preflight_protein_inference_quality_authorization",
]
