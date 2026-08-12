"""Strict public-contract and tamper-closure checks for M02-07 support routing."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
from evals.m02_07.run import build_scenario_request
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m02_07 import (
    M0207_MAX_CANONICAL_REQUEST_BYTES,
    M0207_MAX_ENVELOPES,
    M0207_MAX_PLATFORM_IDS,
    DeclaredSupportFact,
    DeclaredSupportState,
    DimensionSupportDecision,
    IdentificationContextRole,
    IdentificationHarmonizationSupportReceipt,
    IdentificationSupportDimension,
    IdentificationSupportDisposition,
    IdentificationSupportEnvelope,
    IdentificationSupportPolicy,
    IdentificationSupportProfile,
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
    configuration_digest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    route_identification_support,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from glio_proteogen.contracts.m02_07.schema import ContractName

pytestmark = pytest.mark.contract

_SENTINEL_DIGEST = "sha256:" + ("0" * 64)
_FORGED_DIGEST = "sha256:" + ("1" * 64)


@cache
def _cached_request_payload() -> dict[str, Any]:
    return build_scenario_request().model_dump(mode="python")


def _request_payload() -> dict[str, Any]:
    return deepcopy(_cached_request_payload())


@cache
def _cached_result_payload() -> dict[str, Any]:
    result = route_identification_support(build_scenario_request())
    return result.model_dump(mode="python")


def _result_payload() -> dict[str, Any]:
    return deepcopy(_cached_result_payload())


def _put(mapping: dict[str, Any], key: str, value: object) -> object:
    mapping[key] = value
    return value


@pytest.mark.parametrize(
    "name",
    [
        "request",
        "output",
        "prerequisites",
        "profile",
        "policy",
        "declaration",
        "envelope",
        "abstention",
    ],
)
def test_all_public_schemas_are_strict_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == (
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-07:1.0.0:"
        f"{name}"
    )
    assert schema["additionalProperties"] is False
    metadata = {
        "moduleId": "GLIO-PROTEOGEN-M02-07",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
        "jointEnvelopeRequired": True,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0207_MAX_CANONICAL_REQUEST_BYTES
    assert schema["x-glio-contract"] == metadata
    Draft202012Validator.check_schema(schema)


def test_request_rejects_unknown_fields_and_primitive_coercion() -> None:
    values = _request_payload()
    values["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RouteIdentificationSupportRequest.model_validate(values, strict=True)

    policy = _request_payload()["policy"]
    policy["max_envelopes"] = "64"
    with pytest.raises(ValidationError, match="valid integer"):
        IdentificationSupportPolicy.model_validate(policy, strict=True)


@pytest.mark.parametrize(
    "field",
    [
        "assay_types",
        "specimen_terms",
        "disease_class_terms",
        "quality_statuses",
        "platform_ids",
        "reference_ids",
        "intended_use_terms",
        "required_context_roles",
    ],
)
def test_envelope_membership_sets_reject_duplicates(field: str) -> None:
    envelope = _request_payload()["profile"]["envelopes"][0]
    envelope[field] = (*envelope[field], envelope[field][0])

    with pytest.raises(ValidationError):
        IdentificationSupportEnvelope.model_validate(envelope, strict=True)


def test_envelope_requires_exactly_one_remediation_per_dimension() -> None:
    envelope = _request_payload()["profile"]["envelopes"][0]
    envelope["remediations"] = (
        *envelope["remediations"][:-1],
        envelope["remediations"][0],
    )

    with pytest.raises(ValidationError, match="one remediation for every dimension"):
        IdentificationSupportEnvelope.model_validate(envelope, strict=True)


def test_profile_rejects_duplicate_envelope_ids() -> None:
    profile = _request_payload()["profile"]
    profile["envelopes"] = (*profile["envelopes"], profile["envelopes"][0])

    with pytest.raises(ValidationError, match="identifiers must be unique"):
        IdentificationSupportProfile.model_validate(profile, strict=True)


@pytest.mark.parametrize(
    ("collection", "message"),
    [
        ("declared_facts", "exactly the four caller-declared dimensions"),
        ("context_receipts", "every identification context receipt"),
    ],
)
def test_request_rejects_duplicate_required_roles(collection: str, message: str) -> None:
    values = _request_payload()
    values[collection] = (*values[collection][:-1], values[collection][0])

    with pytest.raises(ValidationError, match=message):
        RouteIdentificationSupportRequest.model_validate(values, strict=True)


@pytest.mark.parametrize("collection", ["declared_facts", "context_receipts"])
def test_request_rejects_missing_required_roles(collection: str) -> None:
    values = _request_payload()
    values[collection] = values[collection][:-1]

    with pytest.raises(ValidationError, match="at least"):
        RouteIdentificationSupportRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("state", "values", "message"),
    [
        (DeclaredSupportState.OBSERVED, (), "requires at least one value"),
        (DeclaredSupportState.MISSING, ("specimen.ffpe",), "cannot carry values"),
        (DeclaredSupportState.UNKNOWN, ("specimen.ffpe",), "cannot carry values"),
    ],
)
def test_declared_fact_state_has_one_unambiguous_shape(
    state: DeclaredSupportState,
    values: tuple[str, ...],
    message: str,
) -> None:
    fact = _request_payload()["declared_facts"][0]
    fact.update(state=state, values=values)

    with pytest.raises(ValidationError, match=message):
        DeclaredSupportFact.model_validate(fact, strict=True)


@pytest.mark.parametrize(
    ("role", "state", "message"),
    [
        ("consent", ConsentState.REVOKED, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage"),
        ("quality", UpstreamDecisionState.REJECTED, "upstream controls"),
    ],
)
def test_request_requires_all_authorizing_controls(
    role: str,
    state: object,
    message: str,
) -> None:
    values = _request_payload()
    values["context"]["references"][role]["state"] = state

    with pytest.raises(ValidationError, match=message):
        RouteIdentificationSupportRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _put(
                value["context"]["references"]["approved_configuration"]["evidence"],
                "digest",
                _SENTINEL_DIGEST,
            ),
            "approved configuration does not bind",
        ),
        (
            lambda value: _put(
                value["context"]["references"]["identity_lineage"],
                "binding_digest",
                _SENTINEL_DIGEST,
            ),
            "identity control does not bind",
        ),
    ],
)
def test_request_configuration_and_identity_are_digest_bound(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _request_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        RouteIdentificationSupportRequest.model_validate(values, strict=True)


def test_profile_cannot_exceed_policy_capacity() -> None:
    values = _request_payload()
    template = values["profile"]["envelopes"][0]
    second = deepcopy(template)
    second["envelope_id"] = "envelope.m0207.capacity.second"
    values["profile"]["envelopes"] = (template, second)
    values["policy"]["max_envelopes"] = 1

    with pytest.raises(ValidationError, match="exceeds its policy envelope capacity"):
        RouteIdentificationSupportRequest.model_validate(values, strict=True)


def test_declared_static_capacity_limits_fail_closed() -> None:
    policy = _request_payload()["policy"]
    policy["max_envelopes"] = M0207_MAX_ENVELOPES + 1
    with pytest.raises(ValidationError, match="less than or equal"):
        IdentificationSupportPolicy.model_validate(policy, strict=True)

    policy = _request_payload()["policy"]
    policy["require_releasable_prerequisites"] = False
    with pytest.raises(ValidationError, match="Input should be True"):
        IdentificationSupportPolicy.model_validate(policy, strict=True)

    fact = _request_payload()["declared_facts"][0]
    fact["values"] = tuple(f"specimen.capacity.{index}" for index in range(65))
    with pytest.raises(ValidationError, match="at most 64 items"):
        DeclaredSupportFact.model_validate(fact, strict=True)

    fact = _request_payload()["declared_facts"][0]
    fact["evidence"] = tuple(
        {
            **fact["evidence"][0],
            "artifact_id": f"artifact.m0207.capacity.{index}",
            "digest": f"sha256:{index:064x}",
        }
        for index in range(17)
    )
    with pytest.raises(ValidationError, match="at most 16 items"):
        DeclaredSupportFact.model_validate(fact, strict=True)


def test_profile_hard_envelope_cap_is_enforced() -> None:
    profile = _request_payload()["profile"]
    template = profile["envelopes"][0]
    profile["envelopes"] = tuple(
        {**deepcopy(template), "envelope_id": f"envelope.m0207.capacity.{index:02d}"}
        for index in range(M0207_MAX_ENVELOPES + 1)
    )

    with pytest.raises(ValidationError, match="at most 64 items"):
        IdentificationSupportProfile.model_validate(profile, strict=True)


@pytest.mark.parametrize("platform_count", [65, 256, M0207_MAX_PLATFORM_IDS])
def test_large_harmonization_platform_receipts_route_to_typed_abstention(
    platform_count: int,
) -> None:
    values = _request_payload()
    values["prerequisites"]["harmonization"]["platform_ids"] = tuple(
        f"platform.capacity.{index:04d}" for index in range(platform_count)
    )
    request = RouteIdentificationSupportRequest.model_validate(values, strict=True)

    result = route_identification_support(request)
    platform = next(
        item
        for item in result.envelope_assessments[0].dimensions
        if item.dimension is IdentificationSupportDimension.PLATFORM
    )

    assert result.disposition is IdentificationSupportDisposition.ABSTAINED
    assert result.human_review_required is True
    assert platform.decision is DimensionSupportDecision.OUTSIDE_DOMAIN
    assert len(platform.values) == platform_count


def test_harmonization_receipt_rejects_more_than_2048_platforms() -> None:
    receipt = _request_payload()["prerequisites"]["harmonization"]
    receipt["platform_ids"] = tuple(
        f"platform.capacity.{index:04d}" for index in range(M0207_MAX_PLATFORM_IDS + 1)
    )

    with pytest.raises(ValidationError, match="at most 2048 items"):
        IdentificationHarmonizationSupportReceipt.model_validate(receipt, strict=True)


def test_canonical_ingress_byte_limit_is_enforced_after_relational_validation() -> None:
    request = build_scenario_request()
    template = request.profile.envelopes[0]

    def members(label: str, count: int) -> tuple[str, ...]:
        return tuple(f"{label}.{index:03d}.{'x' * 96}" for index in range(count))

    envelopes = tuple(
        template.model_copy(
            update={
                "envelope_id": f"envelope.m0207.ingress.{index:02d}",
                "assay_types": members(f"assay{index:02d}", 16),
                "specimen_terms": members(f"specimen{index:02d}", 64),
                "disease_class_terms": members(f"disease{index:02d}", 64),
                "platform_ids": members(f"platform{index:02d}", 256),
                "reference_ids": members(f"reference{index:02d}", 256),
                "intended_use_terms": members(f"use{index:02d}", 64),
            }
        )
        for index in range(M0207_MAX_ENVELOPES)
    )
    profile = IdentificationSupportProfile.model_validate(
        request.profile.model_copy(update={"envelopes": envelopes}).model_dump(mode="python"),
        strict=True,
    )
    configuration = configuration_digest(profile, request.policy)
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    oversized = request.model_copy(update={"context": context, "profile": profile})

    assert len(canonical_json_bytes(oversized)) > M0207_MAX_CANONICAL_REQUEST_BYTES
    with pytest.raises(ValidationError, match="canonical request exceeds"):
        RouteIdentificationSupportRequest.model_validate(
            oversized.model_dump(mode="python"),
            strict=True,
        )


def test_semantic_reordering_produces_full_result_equality() -> None:
    first = route_identification_support(build_scenario_request())
    reordered = route_identification_support(build_scenario_request("semantic_reorder_pair"))

    assert reordered == first


@pytest.mark.parametrize(
    ("role", "indeterminate", "unaffected"),
    [
        (
            IdentificationContextRole.GENOME_TRANSCRIPTOME,
            IdentificationSupportDimension.REFERENCE,
            IdentificationSupportDimension.INTENDED_USE,
        ),
        (
            IdentificationContextRole.PTM_ANNOTATIONS,
            IdentificationSupportDimension.REFERENCE,
            IdentificationSupportDimension.INTENDED_USE,
        ),
        (
            IdentificationContextRole.TREATMENT_HISTORY,
            IdentificationSupportDimension.INTENDED_USE,
            IdentificationSupportDimension.REFERENCE,
        ),
    ],
)
def test_context_receipts_gate_only_their_owned_dimension(
    role: IdentificationContextRole,
    indeterminate: IdentificationSupportDimension,
    unaffected: IdentificationSupportDimension,
) -> None:
    request = build_scenario_request()
    receipts = tuple(
        item.model_copy(update={"state": DeclaredSupportState.UNKNOWN})
        if item.role is role
        else item
        for item in request.context_receipts
    )
    changed = RouteIdentificationSupportRequest.model_validate(
        request.model_copy(update={"context_receipts": receipts}).model_dump(mode="python"),
        strict=True,
    )
    result = route_identification_support(changed)
    assessments = {
        item.dimension: item.decision for item in result.envelope_assessments[0].dimensions
    }

    assert assessments[indeterminate] is DimensionSupportDecision.INDETERMINATE
    assert assessments[unaffected] is DimensionSupportDecision.SUPPORTED


def test_emitted_result_round_trips_through_the_strict_output_contract() -> None:
    payload = _result_payload()
    reparsed = IdentificationSupportRouteResult.model_validate(payload, strict=True)

    assert reparsed.model_dump(mode="python") == payload


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _put(value["profile"], "profile_id", "profile.forged"),
            "approved configuration does not bind",
        ),
        (
            lambda value: _put(value["policy"], "policy_id", "policy.forged"),
            "approved configuration does not bind",
        ),
        (
            lambda value: _put(
                value["prerequisites"]["quality"]["artifact"],
                "artifact_id",
                "artifact.forged.quality",
            ),
            "prerequisite digest is inconsistent",
        ),
        (
            lambda value: _put(
                value["prerequisites"]["harmonization"]["artifact"],
                "artifact_id",
                "artifact.forged.harmonization",
            ),
            "prerequisite digest is inconsistent",
        ),
        (
            lambda value: _put(value["context"], "actor_id", "actor.forged"),
            "context digest is inconsistent",
        ),
        (
            lambda value: _put(
                value["declared_facts"][0]["evidence"][0],
                "artifact_id",
                "artifact.forged.fact",
            ),
            "request digest is inconsistent",
        ),
        (
            lambda value: _put(
                value["context_receipts"][0]["reference"],
                "artifact_id",
                "artifact.forged.context",
            ),
            "request digest is inconsistent",
        ),
        (
            lambda value: _put(
                value["envelope_assessments"][0]["dimensions"][0],
                "values",
                ("assay.forged",),
            ),
            "contradicts joint-envelope evaluation",
        ),
        (
            lambda value: _put(
                value["support"],
                "rationale",
                "Forged support rationale.",
            ),
            "support envelope contradicts disposition",
        ),
        (
            lambda value: _put(
                value["uncertainty"]["measurement"],
                "rationale",
                "Forged uncertainty rationale.",
            ),
            "uncertainty must remain deterministic",
        ),
        (
            lambda value: _put(
                value["provenance"]["control_decisions"][0],
                "decision_id",
                "decision.forged",
            ),
            "control decisions do not match",
        ),
        (
            lambda value: _put(
                value["provenance"],
                "input_digests",
                value["provenance"]["input_digests"][:-1],
            ),
            "exact unique input digest set",
        ),
        (
            lambda value: _put(value["evidence"][0], "claim", "Forged evidence claim."),
            "evidence index or authority-safe claims",
        ),
        (
            lambda value: _put(
                value["limitations"][0],
                "statement",
                "Forged limitation statement.",
            ),
            "requires both fixed limitations",
        ),
        (
            lambda value: _put(value, "result_digest", _FORGED_DIGEST),
            "result digest does not match",
        ),
        (
            lambda value: _put(value, "route_id", "route.m0207.forged"),
            "provenance is inconsistent",
        ),
        (
            lambda value: _put(value, "matched_envelope_ids", ()),
            "contradicts joint-envelope evaluation",
        ),
        (
            lambda value: _put(
                value,
                "disposition",
                IdentificationSupportDisposition.ABSTAINED,
            ),
            "disposition contradicts",
        ),
    ],
)
def test_result_forgery_fails_closed(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        IdentificationSupportRouteResult.model_validate(values, strict=True)
