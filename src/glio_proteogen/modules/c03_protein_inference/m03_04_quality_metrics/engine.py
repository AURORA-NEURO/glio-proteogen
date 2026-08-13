"""Deterministic M03-04 protein-inference evidence-graph quality engine."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_03 import ProteinInferenceAdmissionDisposition
from glio_proteogen.contracts.m03_04 import (
    M0304_CONTRACT_VERSION,
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


class ProteinInferenceQualityAuthorizationError(ValueError):
    """Denied upstream controls detected before fact-ledger traversal."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize protein-inference quality computation")


class M0304ProteinInferenceQualityEngine:
    """Compute one immutable protein-inference evidence-graph quality profile."""

    __slots__ = ()

    def compute(self, request: object) -> ProteinInferenceQualityResult:
        """Authorize, strictly reconstruct, evaluate, and self-validate one request."""

        preflight_protein_inference_quality_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
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
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


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
