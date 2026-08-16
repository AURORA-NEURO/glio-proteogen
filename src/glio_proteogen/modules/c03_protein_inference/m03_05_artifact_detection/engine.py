"""Deterministic M03-05 protein-inference artifact detector."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityDisposition
from glio_proteogen.contracts.m03_05 import (
    M0305_CONTRACT_VERSION,
    M0305_ZERO_DIGEST,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactDisposition,
    artifact_evidence_index,
    canonical_request_digest,
    configuration_digest,
    expected_artifact_findings,
    expected_artifact_posteriors,
    expected_computation_receipt,
    expected_contamination_flags,
    expected_disposition,
    expected_exclusion_mask,
    expected_limitations,
    expected_provenance,
    expected_signal_scores,
    expected_support,
    expected_uncertainty,
    normalized_request,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_REQUEST_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceArtifactDetectionResult)


class ProteinInferenceArtifactAuthorizationError(ValueError):
    """Denied upstream controls detected before evidence-ledger traversal."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize protein-inference artifact detection")


class M0305ProteinInferenceArtifactEngine:
    """Compute one immutable artifact posterior and exclusion-mask closure."""

    __slots__ = ()

    def detect(self, request: object) -> ProteinInferenceArtifactDetectionResult:
        """Authorize, reconstruct, detect, and self-validate one request."""

        preflight_protein_inference_artifact_authorization(request)
        candidate = prepare_artifact_request_candidate(request)
        validated = _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        validated = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        return _detect_result(validated)


def detect_protein_inference_artifacts(
    request: object,
) -> ProteinInferenceArtifactDetectionResult:
    """Public stateless M03-05 operation."""

    return M0305ProteinInferenceArtifactEngine().detect(request)


def preflight_protein_inference_artifact_authorization(candidate: object) -> None:
    """Check seven controls without traversing the evidence ledger."""

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
    except Exception:  # noqa: BLE001 - hostile accessors collapse to safe denial.
        raise ProteinInferenceArtifactAuthorizationError from None
    if not authorized:
        raise ProteinInferenceArtifactAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def prepare_artifact_request_candidate(candidate: object) -> object:
    """Drop an untrusted ledger when shallow metadata already proves safe failure."""

    if type(candidate) is not dict:
        return candidate
    try:
        receipt = candidate.get("quality_receipt")
        policy = candidate.get("policy")
        disposition = _state(_member(receipt, "quality_disposition"))
        source_count = _member(receipt, "source_count")
        claim_count = _member(receipt, "claim_count")
        max_sources = _member(policy, "max_sources")
        max_claims = _member(policy, "max_claims")
    except Exception:  # noqa: BLE001 - strict reconstruction handles malformed metadata.
        return candidate
    known_upstream_failure = disposition in {"rejected", "quarantined", "abstained"}
    qualified_shape_excess = (
        disposition == "qualified"
        and type(source_count) is int
        and type(claim_count) is int
        and type(max_sources) is int
        and type(max_claims) is int
        and (source_count > max_sources or claim_count > max_claims)
    )
    if not known_upstream_failure and not qualified_shape_excess:
        return candidate
    sanitized = candidate.copy()
    sanitized["evidence_ledger"] = None
    return sanitized


def _detect_result(
    request: DetectProteinInferenceArtifactsRequest,
) -> ProteinInferenceArtifactDetectionResult:
    receipt = request.quality_receipt
    ledger = request.evidence_ledger
    traversable_shape = (
        receipt.quality_disposition is ProteinInferenceQualityDisposition.QUALIFIED
        and receipt.source_count <= request.policy.max_sources
        and receipt.claim_count <= request.policy.max_claims
        and ledger is not None
        and len(ledger.units) <= request.policy.max_units
    )
    scores = expected_signal_scores(request) if traversable_shape else ()
    posteriors = expected_artifact_posteriors(scores)
    flags = expected_contamination_flags(scores)
    mask = expected_exclusion_mask(posteriors)
    findings = expected_artifact_findings(request, scores, flags)
    disposition = expected_disposition(request, scores, findings)
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.policy)
    payload: dict[str, object] = {
        "output_type": "protein_inference_artifact_mask",
        "result_id": f"result.m0305.{request_hash.removeprefix('sha256:')}",
        "result_version": M0305_CONTRACT_VERSION,
        "request_digest": request_hash,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "result_digest": M0305_ZERO_DIGEST,
        "request": request,
        "receipt": expected_computation_receipt(request, disposition),
        "signal_scores": scores,
        "artifact_posteriors": posteriors,
        "contamination_flags": flags,
        "exclusion_mask": mask,
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
        "provenance": expected_provenance(request, disposition),
        "evidence": artifact_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": (disposition is not ProteinInferenceArtifactDisposition.CLEARED),
        "completed_at": request.context.occurred_at,
    }
    materialized = cast(
        "dict[str, Any]",
        # Trusted output is bounded by the typed request and closed collections.
        json.loads(canonical_json_bytes(payload)),
    )
    materialized["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


__all__ = [
    "M0305ProteinInferenceArtifactEngine",
    "ProteinInferenceArtifactAuthorizationError",
    "detect_protein_inference_artifacts",
    "preflight_protein_inference_artifact_authorization",
    "prepare_artifact_request_candidate",
]
