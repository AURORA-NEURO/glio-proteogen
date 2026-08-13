"""Independent adversarial freeze audit for M04-01."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import timedelta
from typing import Any, cast

import pytest
from evals.m04_01.run import build_scenario_request
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m04_01 import (
    EvaluateProteoformProtocolRequest,
    ModificationLocalizationPolicy,
    ProteinRnaDiscordanceHandoffRequirements,
    ProteoformEvidenceEligibilityPolicy,
    ProteoformProtocolConformanceResult,
    ProteoformProtocolConformanceStatus,
    ProteoformProtocolFindingState,
    ProteoformProtocolReceipt,
    ProteoformProtocolSchema,
    ProteoformProtocolSection,
    ReviewedProteoformConformanceProfile,
    contract_json_schema,
    preflight_authorized,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Plugin,
    M0401Service,
    ProteoformProtocolAuthorizationError,
    evaluate_proteoform_protocol,
    preflight_proteoform_protocol_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    engine as engine_module,
)
from tests.contract.test_m04_01_contract import build_request, build_result

type ResultPayload = dict[str, Any]
type ResultMutator = Callable[[ResultPayload], None]


def _nested(payload: ResultPayload, field: str) -> dict[str, Any]:
    return cast("dict[str, Any]", payload[field])


def _items(payload: ResultPayload, field: str) -> tuple[dict[str, Any], ...]:
    return cast("tuple[dict[str, Any], ...]", payload[field])


def _forge_receipt(payload: ResultPayload) -> None:
    receipt = _nested(payload, "receipt")
    receipt["reference_bundle_digest"] = sha256_digest("audit-forged-receipt")
    receipt["receipt_digest"] = receipt_digest(receipt)


def _forge_finding(payload: ResultPayload) -> None:
    _items(payload, "findings")[0]["reason_code"] = "forged_reason"


def _forge_envelope(payload: ResultPayload) -> None:
    payload["status"] = ProteoformProtocolConformanceStatus.NONCONFORMANT


def _forge_uncertainty(payload: ResultPayload) -> None:
    uncertainty = _nested(payload, "uncertainty")
    cast("dict[str, Any]", uncertainty["measurement"])["rationale"] = "forged uncertainty"


def _forge_provenance(payload: ResultPayload) -> None:
    _nested(payload, "provenance")["activity_id"] = "activity.forged"


def _forge_evidence(payload: ResultPayload) -> None:
    _items(payload, "evidence")[0]["claim"] = "forged evidence claim"


def _forge_limitation(payload: ResultPayload) -> None:
    _items(payload, "limitations")[0]["statement"] = "forged limitation"


def _forge_time(payload: ResultPayload) -> None:
    payload["completed_at"] = payload["completed_at"] + timedelta(microseconds=1)


def _stale_result_digest(payload: ResultPayload) -> None:
    payload["result_digest"] = sha256_digest("audit-stale-result")


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutator", "message", "digest_mode"),
    [
        (_forge_receipt, "receipt contradicts", "resign"),
        (_forge_finding, "findings contradict", "resign"),
        (_forge_envelope, "support envelope contradicts", "resign"),
        (_forge_uncertainty, "uncertainty exceeds", "resign"),
        (_forge_provenance, "provenance contradicts", "resign"),
        (_forge_evidence, "evidence index contradicts", "resign"),
        (_forge_limitation, "limitations exceed", "resign"),
        (_forge_time, "completion time", "resign"),
        (_stale_result_digest, "result digest does not match", "stale"),
    ],
)
def test_resigned_result_forgery_reaches_every_exact_replay_guard(
    mutator: ResultMutator,
    message: str,
    digest_mode: str,
) -> None:
    payload = deepcopy(build_result().model_dump(mode="python"))
    mutator(payload)
    if digest_mode == "resign":
        payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match=message):
        ProteoformProtocolConformanceResult.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "model", "message"),
    [
        (
            ("evidence_eligibility", "eligible_evidence_classes"),
            ProteoformEvidenceEligibilityPolicy,
            "eligible evidence classes must be unique",
        ),
        (
            ("modification_localization", "declared_states"),
            ModificationLocalizationPolicy,
            "all four explicit states",
        ),
        (
            ("discordance_handoff", "required_receipt_roles"),
            ProteinRnaDiscordanceHandoffRequirements,
            "every receipt role",
        ),
        (
            ("required_identity_keys",),
            ProteoformProtocolSchema,
            "every mandatory proteoform identity key",
        ),
        (
            ("declared_unresolved_states",),
            ProteoformProtocolSchema,
            "every governed unresolved state",
        ),
    ],
)
def test_exact_protocol_vocabularies_reject_same_length_conflation(
    path: tuple[str, ...],
    model: type[Any],
    message: str,
) -> None:
    protocol = build_request().protocol_schema
    if len(path) == 1:
        payload = protocol.model_dump(mode="python")
    else:
        payload = cast("dict[str, Any]", getattr(protocol, path[0]).model_dump(mode="python"))
    field = path[-1]
    values = list(cast("tuple[object, ...]", payload[field]))
    values[-1] = values[0]
    payload[field] = tuple(values)
    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload, strict=True)


@pytest.mark.contract
def test_profile_rejects_distinct_digests_under_one_bundle_identity() -> None:
    payload = build_request().conformance_profile.model_dump(mode="python")
    original = cast(
        "tuple[dict[str, Any], ...]",
        payload["approved_reference_bundles"],
    )[0]
    alternate = deepcopy(original)
    alternate["bundle_digest"] = sha256_digest("alternate")
    payload["approved_reference_bundles"] = (original, alternate)
    with pytest.raises(ValidationError, match="bundle identities must be unique"):
        ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("profile_pin", "does not pin"),
        ("review_time", "cannot postdate"),
        ("configuration", "does not bind"),
        ("control_digest", "distinct evidence digests"),
        ("cross_role_evidence", "exactly 21 distinct"),
    ],
)
def test_request_relational_forgery_matrix_reaches_exact_guard(
    mutation: str,
    message: str,
) -> None:
    payload = deepcopy(build_request().model_dump(mode="python"))
    profile = cast("dict[str, Any]", payload["conformance_profile"])
    context = cast("dict[str, Any]", payload["context"])
    references = cast("dict[str, Any]", context["references"])
    protocol = cast("dict[str, Any]", payload["protocol_schema"])
    if mutation == "profile_pin":
        profile["protocol_schema_digest"] = sha256_digest("stale-profile-pin")
    elif mutation == "review_time":
        profile["reviewed_at"] = context["occurred_at"] + timedelta(microseconds=1)
    elif mutation == "configuration":
        configuration = cast("dict[str, Any]", references["approved_configuration"])
        evidence = cast("dict[str, Any]", configuration["evidence"])
        evidence["digest"] = sha256_digest("stale-configuration")
    elif mutation == "control_digest":
        provenance = cast("dict[str, Any]", references["provenance"])
        quality = cast("dict[str, Any]", references["quality"])
        provenance_evidence = cast("dict[str, Any]", provenance["evidence"])
        quality_evidence = cast("dict[str, Any]", quality["evidence"])
        provenance_evidence["digest"] = quality_evidence["digest"]
    else:
        quality = cast("dict[str, Any]", references["quality"])
        quality_evidence = cast("dict[str, Any]", quality["evidence"])
        reference_bundle = cast("dict[str, Any]", protocol["reference_bundle"])
        genome = cast("dict[str, Any]", reference_bundle["genome_reference"])
        quality_evidence["artifact_id"] = genome["artifact_id"]
        quality_evidence["digest"] = genome["digest"]
    with pytest.raises(ValidationError, match=message):
        EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_contract_preflight_supports_typed_context_and_fails_closed() -> None:
    request = build_request()
    preflight_authorized(request)
    preflight_authorized({"context": request.context})
    denied_quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_references = request.context.references.model_copy(update={"quality": denied_quality})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": denied_references})}
    )
    with pytest.raises(ValueError, match="not authorized"):
        preflight_authorized(denied)
    with pytest.raises(ValueError, match="strict request object"):
        preflight_authorized(object())
    with pytest.raises(ValueError, match="accepted upstream controls"):
        preflight_authorized({"context": {"references": {}}})


@pytest.mark.contract
def test_runtime_preflight_catches_exception_and_plain_json_shape_is_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_request()

    def fail_closed(_candidate: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(engine_module, "preflight_authorized", fail_closed)
    with pytest.raises(ProteoformProtocolAuthorizationError):
        preflight_proteoform_protocol_authorization(request)
    monkeypatch.undo()
    assert evaluate_proteoform_protocol(request.model_dump(mode="python")) == (
        evaluate_proteoform_protocol(request)
    )


@pytest.mark.contract
def test_max_shape_semantic_reorder_and_all_public_schemas_replay() -> None:
    request = build_scenario_request("maximum_profile_shape_conforms")
    canonical_result = evaluate_proteoform_protocol(request)
    expected_section_order = tuple(ProteoformProtocolSection)
    assert tuple(item.section for item in canonical_result.findings) == expected_section_order
    assert tuple(item.section for item in canonical_result.receipt.sections) == (
        expected_section_order
    )
    payload = canonical_result.model_dump(mode="json")
    request_payload = cast("dict[str, Any]", payload["request"])
    protocol = cast("dict[str, Any]", request_payload["protocol_schema"])
    profile = cast("dict[str, Any]", request_payload["conformance_profile"])
    for field in (
        "required_identity_keys",
        "declared_unresolved_states",
    ):
        cast("list[object]", protocol[field]).reverse()
    for policy, field in (
        ("evidence_eligibility", "eligible_evidence_classes"),
        ("isoform_discrimination", "accepted_discriminators"),
        ("modification_localization", "declared_states"),
        ("discordance_handoff", "required_receipt_roles"),
    ):
        cast("list[object]", cast("dict[str, Any]", protocol[policy])[field]).reverse()
    for field in (
        "approved_applicabilities",
        "approved_reference_bundles",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabularies",
        "approved_unit_system_versions",
        "approved_coordinate_profiles",
        "approved_quantification_pairs",
        "approved_evidence_classes",
        "approved_labile_modification_handlings",
        "approved_isoform_discriminators",
    ):
        cast("list[object]", profile[field]).reverse()
    for field in ("findings", "evidence", "limitations"):
        cast("list[object]", payload[field]).reverse()
    cast("list[object]", cast("dict[str, Any]", payload["receipt"])["sections"]).reverse()
    provenance = cast("dict[str, Any]", payload["provenance"])
    cast("list[object]", provenance["input_digests"]).reverse()
    cast("list[object]", provenance["control_decisions"]).reverse()
    uncertainty = cast("dict[str, Any]", payload["uncertainty"])
    cast("list[object]", uncertainty["sensitivity_notes"]).reverse()
    reordered = ProteoformProtocolConformanceResult.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert reordered == canonical_result

    schema_values = {
        "request": request,
        "output": canonical_result,
        "protocol": request.protocol_schema,
        "profile": request.conformance_profile,
        "reference-bundle": request.protocol_schema.reference_bundle,
        "reference-cardinality": request.protocol_schema.reference_bundle.cardinality,
        "coordinate-policy": request.protocol_schema.coordinate_policy,
        "evidence-eligibility-policy": request.protocol_schema.evidence_eligibility,
        "isoform-discrimination-policy": request.protocol_schema.isoform_discrimination,
        "modification-localization-policy": request.protocol_schema.modification_localization,
        "quantification-policy": request.protocol_schema.quantification,
        "discordance-handoff": request.protocol_schema.discordance_handoff,
        "receipt": canonical_result.receipt,
    }
    for name, value in schema_values.items():
        Draft202012Validator(contract_json_schema(cast("Any", name))).validate(
            value.model_dump(mode="json")
        )

    service = M0401Service()
    plugin = M0401Plugin(service)
    assert plugin.run(plugin.validate(request)) == canonical_result
    assert len(canonical_json_bytes(request)) < 4 * 1024 * 1024


@pytest.mark.contract
def test_standalone_receipt_failure_state_requires_quarantine() -> None:
    payload = deepcopy(build_result().receipt.model_dump(mode="python"))
    sections = cast("tuple[dict[str, Any], ...]", payload["sections"])
    sections[0]["state"] = ProteoformProtocolFindingState.FAIL
    payload["receipt_digest"] = receipt_digest(payload)
    with pytest.raises(ValidationError, match="disposition contradicts section states"):
        ProteoformProtocolReceipt.model_validate(payload, strict=True)
