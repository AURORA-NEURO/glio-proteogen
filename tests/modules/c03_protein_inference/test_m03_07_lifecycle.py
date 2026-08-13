"""Focused M03-07 engine, receipt, service, and plugin lifecycle checks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy

import pytest
from evals.m03_07.run import build_scenario, build_scenario_request

from glio_proteogen.contracts.m03_07 import (
    M0307_ZERO_DIGEST,
    ProteinInferenceAbstentionCode,
    ProteinInferenceDeclaredSupportState,
    ProteinInferenceDimensionSupportDecision,
    ProteinInferenceSupportDimension,
    ProteinInferenceSupportDisposition,
    normalized_result,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    M0307Plugin,
    M0307Service,
    ProteinInferenceSupportAuthorizationError,
    ProteinInferenceSupportReceiptError,
    protein_inference_harmonization_support_receipt,
    protein_inference_quality_support_receipt,
    protein_inference_support_prerequisites,
    route_protein_inference_support,
)


def test_genuine_receipt_builders_reconstruct_exact_compact_chain() -> None:
    scenario = build_scenario()
    prerequisites = scenario.request.prerequisites

    assert prerequisites.quality_result == scenario.quality_result
    assert prerequisites.harmonization_result == scenario.harmonization_result
    assert (
        protein_inference_quality_support_receipt(scenario.quality_result) == prerequisites.quality
    )
    assert (
        protein_inference_harmonization_support_receipt(scenario.harmonization_result)
        == prerequisites.harmonization
    )
    assert (
        protein_inference_support_prerequisites(
            scenario.quality_result,
            scenario.harmonization_result,
        )
        == prerequisites
    )


def test_receipt_builders_reject_malformed_and_cross_chain_results() -> None:
    scenario = build_scenario()
    with pytest.raises(ProteinInferenceSupportReceiptError, match="M03-04 result"):
        protein_inference_quality_support_receipt({})
    with pytest.raises(ProteinInferenceSupportReceiptError, match="M03-06 result"):
        protein_inference_harmonization_support_receipt({})
    with pytest.raises(ProteinInferenceSupportReceiptError, match="M03-04 result"):
        protein_inference_quality_support_receipt(
            scenario.quality_result.model_copy(update={"result_digest": M0307_ZERO_DIGEST})
        )
    with pytest.raises(ProteinInferenceSupportReceiptError, match="M03-06 result"):
        protein_inference_harmonization_support_receipt(
            scenario.harmonization_result.model_copy(update={"result_digest": M0307_ZERO_DIGEST})
        )

    alternate_quality_request = scenario.quality_result.request.model_copy(
        update={"supersedes_result_digest": sha256_digest("prior-quality-result")}
    )
    alternate_quality = compute_protein_inference_quality(alternate_quality_request)
    with pytest.raises(ProteinInferenceSupportReceiptError, match="prerequisite chain"):
        protein_inference_support_prerequisites(
            alternate_quality,
            scenario.harmonization_result,
        )

    stale_projection = scenario.request.model_dump(mode="python")
    stale_projection["prerequisites"]["quality_result"] = alternate_quality
    with pytest.raises(ValueError, match="exact projection"):
        route_protein_inference_support(stale_projection)


def test_engine_service_and_plugin_replay_one_joint_envelope() -> None:
    request = build_scenario_request()
    direct = route_protein_inference_support(request)
    service = M0307Service().execute(request)
    plugin = M0307Plugin(M0307Service())
    token = plugin.validate(request.model_dump_json())
    plugin_result = plugin.run(token)

    assert direct == service == plugin_result
    assert direct.disposition is ProteinInferenceSupportDisposition.SUPPORTED
    assert len(direct.matched_envelope_ids) == 1
    assert len(direct.envelope_assessments) == 1
    assert not direct.abstention_reasons
    assert direct.human_review_required is False
    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M03-07"
    assert descriptor.owner == "Scientific engineering"


def test_plugin_rejects_unvalidated_execution_capability() -> None:
    plugin = M0307Plugin(M0307Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(build_scenario_request())  # type: ignore[arg-type]


class _HostilePrerequisites(Mapping[str, object]):
    _MESSAGE = "prerequisites were traversed"

    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def test_seven_control_denial_precedes_hostile_prerequisite_traversal() -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["prerequisites"] = _HostilePrerequisites()

    with pytest.raises(ProteinInferenceSupportAuthorizationError):
        M0307Service.validate_request(payload)
    with pytest.raises(ProteinInferenceSupportAuthorizationError):
        M0307Service().execute(payload)
    with pytest.raises(ProteinInferenceSupportAuthorizationError):
        M0307Plugin(M0307Service()).validate(payload)


@pytest.mark.parametrize(
    ("role", "denied_state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_each_control_independently_denies_before_route(
    role: str,
    denied_state: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][role]["state"] = denied_state

    with pytest.raises(ProteinInferenceSupportAuthorizationError):
        route_protein_inference_support(payload)


def test_preflight_rejects_arbitrary_mapping_accessors_without_touching_them() -> None:
    with pytest.raises(ProteinInferenceSupportAuthorizationError):
        M0307Service.validate_request(_HostilePrerequisites())


@pytest.mark.parametrize(
    ("state", "values", "decision", "code"),
    [
        (
            ProteinInferenceDeclaredSupportState.OBSERVED,
            ("specimen." + sha256_digest("outside").removeprefix("sha256:"),),
            ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN,
            ProteinInferenceAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
        ),
        (
            ProteinInferenceDeclaredSupportState.MISSING,
            (),
            ProteinInferenceDimensionSupportDecision.INDETERMINATE,
            ProteinInferenceAbstentionCode.DIMENSION_INDETERMINATE,
        ),
    ],
)
def test_outside_and_missing_declarations_remain_distinct_abstentions(
    state: ProteinInferenceDeclaredSupportState,
    values: tuple[str, ...],
    decision: ProteinInferenceDimensionSupportDecision,
    code: ProteinInferenceAbstentionCode,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    fact = next(
        item
        for item in payload["declared_facts"]
        if item["dimension"] is ProteinInferenceSupportDimension.SPECIMEN
    )
    fact["state"] = state
    fact["values"] = values

    result = route_protein_inference_support(payload)
    specimen = next(
        item
        for item in result.envelope_assessments[0].dimensions
        if item.dimension is ProteinInferenceSupportDimension.SPECIMEN
    )

    assert result.disposition is ProteinInferenceSupportDisposition.ABSTAINED
    assert specimen.decision is decision
    assert any(item.code is code for item in result.abstention_reasons)


def test_semantic_reorder_reconstructs_complete_result_equality() -> None:
    request = build_scenario_request()
    canonical = route_protein_inference_support(request)
    payload = deepcopy(request.model_dump(mode="python"))
    payload["declared_facts"] = tuple(reversed(payload["declared_facts"]))
    payload["context_receipts"] = tuple(reversed(payload["context_receipts"]))
    payload["profile"]["envelopes"] = tuple(reversed(payload["profile"]["envelopes"]))
    payload["profile"]["envelopes"][0]["remediations"] = tuple(
        reversed(payload["profile"]["envelopes"][0]["remediations"])
    )

    reordered = route_protein_inference_support(payload)

    assert reordered == canonical
    assert normalized_result(reordered) == normalized_result(canonical)
    assert canonical_json_bytes(reordered) == canonical_json_bytes(canonical)


def test_strict_plugin_json_rejects_unknown_members() -> None:
    payload = build_scenario_request().model_dump(mode="json")
    payload["unknown"] = True

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        M0307Plugin(M0307Service()).validate(payload)
