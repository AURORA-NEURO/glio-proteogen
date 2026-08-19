"""Deterministic M03-07 protein-inference joint support-envelope router."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityResult
from glio_proteogen.contracts.m03_06 import ProteinInferenceHarmonizationResult
from glio_proteogen.contracts.m03_07 import (
    M0307_CONTRACT_VERSION,
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    M0307_MAX_CANONICAL_RESULT_BYTES,
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
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 1_024
_MAX_PLAIN_NODES: Final = 250_000
_MAX_PLAIN_BYTES: Final = max(
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    M0307_MAX_CANONICAL_RESULT_BYTES,
)


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


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-07 strict values require bounded built-in containers")


class M0307ProteinInferenceSupportRouterEngine:
    """Produce one immutable replay-closed support-routing result."""

    __slots__ = ()

    def route(self, request: object) -> ProteinInferenceSupportRouteResult:
        """Authorize, strictly reconstruct, route, and self-validate one request."""

        preflight_protein_inference_support_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)
        return _support_route_result(validated)


def route_protein_inference_support(request: object) -> ProteinInferenceSupportRouteResult:
    """Public stateless M03-07 operation."""

    return M0307ProteinInferenceSupportRouterEngine().route(request)


def preflight_protein_inference_support_authorization(candidate: object) -> None:
    """Check seven controls without traversing prerequisites or declared facts."""

    if not preflight_authorized(candidate):
        raise ProteinInferenceSupportAuthorizationError


def _charge_plain_bytes(budget: list[int], value: str) -> None:
    """Bound caller-controlled strings before strict support replay."""

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
    """Materialize only bounded built-in containers for direct M03-07 ingress."""

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


def protein_inference_quality_support_receipt(
    result: object,
) -> ProteinInferenceQualitySupportReceipt:
    """Strictly project a genuine full M03-04 result to the M03-07 boundary."""

    try:
        validated = ProteinInferenceQualityResult.model_validate_json(
            canonical_json_bytes(_plain_value(result)),
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
            canonical_json_bytes(_plain_value(result)),
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
                canonical_json_bytes(_plain_value(quality_result)), strict=True
            ),
            harmonization_result=ProteinInferenceHarmonizationResult.model_validate_json(
                canonical_json_bytes(_plain_value(harmonization_result)), strict=True
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
        "infers_isoform": False,
        "infers_glioma_specific_biology": False,
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
