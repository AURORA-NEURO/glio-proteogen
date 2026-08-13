"""Deterministic M03-07 protein-inference joint support-envelope router."""

from __future__ import annotations

import json
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityResult
from glio_proteogen.contracts.m03_06 import ProteinInferenceHarmonizationResult
from glio_proteogen.contracts.m03_07 import (
    M0307_CONTRACT_VERSION,
    M0307_ZERO_DIGEST,
    ProteinInferenceHarmonizationSupportReceipt,
    ProteinInferenceQualitySupportReceipt,
    ProteinInferenceSupportDisposition,
    ProteinInferenceSupportPrerequisites,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
    canonical_request_digest,
    configuration_digest,
    derive_support_route,
    expected_limitations,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    harmonization_support_receipt,
    policy_digest,
    preflight_authorized,
    profile_digest,
    quality_support_receipt,
    result_payload_digest,
    support_route_evidence_index,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_REQUEST_ADAPTER: Final = TypeAdapter(RouteProteinInferenceSupportRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceSupportRouteResult)


class ProteinInferenceSupportAuthorizationError(ValueError):
    """Denied controls detected before prerequisite or fact traversal."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize protein-inference support routing")


class ProteinInferenceSupportReceiptError(ValueError):
    """Strict upstream results cannot form one M03-07 prerequisite chain."""

    @classmethod
    def quality(cls) -> ProteinInferenceSupportReceiptError:
        return cls("M03-04 result cannot form a strict M03-07 quality receipt")

    @classmethod
    def harmonization(cls) -> ProteinInferenceSupportReceiptError:
        return cls("M03-06 result cannot form a strict M03-07 harmonization receipt")

    @classmethod
    def chain(cls) -> ProteinInferenceSupportReceiptError:
        return cls("M03-04 and M03-06 results do not form one M03-07 prerequisite chain")


class M0307ProteinInferenceSupportRouterEngine:
    """Produce one immutable replay-closed support-routing result."""

    __slots__ = ()

    def route(self, request: object) -> ProteinInferenceSupportRouteResult:
        """Authorize, strictly reconstruct, route, and self-validate one request."""

        preflight_protein_inference_support_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return _support_route_result(validated)


def route_protein_inference_support(request: object) -> ProteinInferenceSupportRouteResult:
    """Public stateless M03-07 operation."""

    return M0307ProteinInferenceSupportRouterEngine().route(request)


def preflight_protein_inference_support_authorization(candidate: object) -> None:
    """Check seven controls without traversing prerequisites or declared facts."""

    if not preflight_authorized(candidate):
        raise ProteinInferenceSupportAuthorizationError


def protein_inference_quality_support_receipt(
    result: object,
) -> ProteinInferenceQualitySupportReceipt:
    """Strictly project a genuine full M03-04 result to the M03-07 boundary."""

    try:
        validated = ProteinInferenceQualityResult.model_validate_json(
            canonical_json_bytes(result),
            strict=True,
        )
        return quality_support_receipt(validated)
    except (TypeError, ValueError) as error:
        raise ProteinInferenceSupportReceiptError.quality() from error


def protein_inference_harmonization_support_receipt(
    result: object,
) -> ProteinInferenceHarmonizationSupportReceipt:
    """Strictly project a genuine full M03-06 result to the M03-07 boundary."""

    try:
        validated = ProteinInferenceHarmonizationResult.model_validate_json(
            canonical_json_bytes(result),
            strict=True,
        )
        return harmonization_support_receipt(validated)
    except (TypeError, ValueError) as error:
        raise ProteinInferenceSupportReceiptError.harmonization() from error


def protein_inference_support_prerequisites(
    quality_result: object,
    harmonization_result: object,
) -> ProteinInferenceSupportPrerequisites:
    """Build one digest-, identity-, version-, and chronology-closed compact bundle."""

    try:
        return ProteinInferenceSupportPrerequisites(
            quality_result=ProteinInferenceQualityResult.model_validate_json(
                canonical_json_bytes(quality_result), strict=True
            ),
            harmonization_result=ProteinInferenceHarmonizationResult.model_validate_json(
                canonical_json_bytes(harmonization_result), strict=True
            ),
            quality=protein_inference_quality_support_receipt(quality_result),
            harmonization=protein_inference_harmonization_support_receipt(harmonization_result),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, ProteinInferenceSupportReceiptError):
            raise
        raise ProteinInferenceSupportReceiptError.chain() from error


def _support_route_result(
    request: RouteProteinInferenceSupportRequest,
) -> ProteinInferenceSupportRouteResult:
    assessments, matches, abstentions = derive_support_route(
        request.prerequisites,
        request.profile,
        request.declared_facts,
        request.context_receipts,
    )
    disposition = (
        ProteinInferenceSupportDisposition.SUPPORTED
        if matches
        else ProteinInferenceSupportDisposition.ABSTAINED
    )
    request_hash = canonical_request_digest(request)
    profile_hash = profile_digest(request.profile)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.profile, request.policy)
    payload: dict[str, object] = {
        "output_type": "protein_inference_support_route_result",
        "route_id": f"route.{request_hash.removeprefix('sha256:')}",
        "result_version": M0307_CONTRACT_VERSION,
        "request_digest": request_hash,
        "profile_digest": profile_hash,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "result_digest": M0307_ZERO_DIGEST,
        "request": request,
        "disposition": disposition,
        "matched_envelope_ids": matches,
        "envelope_assessments": assessments,
        "abstention_reasons": abstentions,
        "parent_target": "complex_activity",
        "emits_complex_activity": False,
        "infers_identity": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_kinase_activity": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(disposition),
        "provenance": expected_provenance(request),
        "evidence": support_route_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": disposition is ProteinInferenceSupportDisposition.ABSTAINED,
        "completed_at": request.context.occurred_at,
    }
    materialized = cast(
        "dict[str, Any]",
        json.loads(canonical_json_bytes(payload)),
    )
    materialized["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(materialized), strict=True)


__all__ = [
    "M0307ProteinInferenceSupportRouterEngine",
    "ProteinInferenceSupportAuthorizationError",
    "ProteinInferenceSupportReceiptError",
    "preflight_protein_inference_support_authorization",
    "protein_inference_harmonization_support_receipt",
    "protein_inference_quality_support_receipt",
    "protein_inference_support_prerequisites",
    "route_protein_inference_support",
]
