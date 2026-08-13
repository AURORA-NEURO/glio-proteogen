"""Deterministic M03-06 protein-inference support harmonization engine."""

from __future__ import annotations

import json
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_05 import ProteinInferenceArtifactDisposition
from glio_proteogen.contracts.m03_06 import (
    M0306_CONTRACT_VERSION,
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


class ProteinInferenceHarmonizationAuthorizationError(ValueError):
    """Denied controls detected before receipt or support-ledger traversal."""

    def __init__(self) -> None:
        super().__init__(
            "upstream controls do not authorize protein-inference support harmonization"
        )


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
        validated = _REQUEST_ADAPTER.validate_python(candidate, strict=True)
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
