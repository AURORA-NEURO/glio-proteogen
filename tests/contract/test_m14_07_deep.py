"""Adversarial closure tests for the provisional M14-07 contract."""


from __future__ import annotations

from copy import deepcopy

import pytest

from glio_proteogen.contracts.m14_07 import (
    M1407_M1404_RESULT_MEDIA_TYPE,
    AdjudicateProteinSubtypePlausibilityRequest,
    ProteinSubtypePlausibilityAdjudicationResult,
    expected_uncertainty,
)
from glio_proteogen.modules.c14_microenvironment.m14_07_plausibility_negative_control_adjudicator import (  # noqa: E501
    M1407PlausibilityAdjudicator,
)
from tests.modules.c14_microenvironment.test_m14_07_engine import _request


def test_uncertainty_and_request_binding_cover_safe_false_paths() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.state.value == "estimated"
    assert abstained.measurement.state.value == "not_estimable"
    assert abstained.measurement.probability is None
    with pytest.raises(ValueError, match="bind"):
        AdjudicateProteinSubtypePlausibilityRequest.model_validate(
            _request().model_copy(
                update={
                    "mechanism_inference_result": _request().mechanism_inference_result.model_copy(
                        update={"media_type": "application/json"}
                    ),
                }
            ),
            strict=True,
        )


def test_result_validator_rejects_each_closed_world_mutation() -> None:
    engine = M1407PlausibilityAdjudicator()
    valid = engine.infer(_request())
    base = valid.model_dump(mode="python")
    conflict = engine.infer(_request(criterion="conflict: primary vs alternate"))
    conflict_payload = conflict.model_dump(mode="python")
    mutations: list[tuple[str, dict[str, object], str]] = []

    payload = deepcopy(base)
    payload["request_digest"] = "sha256:" + "a" * 64
    mutations.append(("request digest", payload, "request digest"))
    payload = deepcopy(base)
    payload["result_id"] = "result.wrong"
    mutations.append(("result id", payload, "result identifier"))
    payload = deepcopy(base)
    payload["evaluations"] = ()
    mutations.append(("evaluation closure", payload, "every control"))
    payload = deepcopy(conflict_payload)
    payload["conflicts"] = payload["conflicts"] + (payload["conflicts"][0],)
    mutations.append(("conflict uniqueness", payload, "conflict ids"))
    payload = deepcopy(conflict_payload)
    payload["findings"] = payload["findings"] + (payload["findings"][0],)
    mutations.append(("finding uniqueness", payload, "finding ids"))
    payload = deepcopy(base)
    payload["evidence"] = ()
    mutations.append(("evidence role", payload, "evidence references"))
    payload = deepcopy(base)
    payload["grade"] = None
    mutations.append(("adjudicated closure", payload, "adjudicated result"))
    payload = deepcopy(conflict_payload)
    payload["human_review_required"] = False
    mutations.append(("abstained closure", payload, "abstained result"))
    payload = deepcopy(base)
    payload["result_digest"] = "sha256:" + "b" * 64
    mutations.append(("result digest", payload, "result digest"))

    for _name, candidate, message in mutations:
        with pytest.raises(ValueError, match=message):
            ProteinSubtypePlausibilityAdjudicationResult.model_validate(candidate, strict=True)


def test_result_request_media_type_constant_remains_explicit() -> None:
    assert M1407_M1404_RESULT_MEDIA_TYPE.endswith("m14-04+json")
