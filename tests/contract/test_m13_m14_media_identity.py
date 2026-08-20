"""Regression coverage for exact M13/M14 media identities and handoffs."""

from __future__ import annotations

import pytest
from evals.m13_04.run import build_scenario_request as build_m1304_request
from evals.m13_07.factory import build_request as build_m1307_request
from evals.m14_04.run import build_scenario_request as build_m1404_request

from glio_proteogen.contracts.m13_04 import (
    M1304_M1301_RESULT_MEDIA_TYPE,
    M1304_OUTPUT_MEDIA_TYPE,
    InferProteotypeMechanismRequest,
)
from glio_proteogen.contracts.m13_07 import (
    M1307_M1306_RESULT_MEDIA_TYPE,
    M1307_OUTPUT_MEDIA_TYPE,
    AdjudicateProteotypePlausibilityRequest,
)
from glio_proteogen.contracts.m14_01 import M1401_OUTPUT_MEDIA_TYPE
from glio_proteogen.contracts.m14_04 import (
    M1404_M1401_RESULT_MEDIA_TYPE,
    M1404_OUTPUT_MEDIA_TYPE,
    InferProteinSubtypeMechanismRequest,
)


def test_m13_m14_media_types_are_owned_by_the_declaring_module() -> None:
    assert M1304_OUTPUT_MEDIA_TYPE == "application/vnd.glio-proteogen.m13-04+json"
    assert M1304_M1301_RESULT_MEDIA_TYPE == "application/vnd.glio-proteogen.m13-01+json"
    assert M1307_OUTPUT_MEDIA_TYPE == "application/vnd.glio-proteogen.m13-07+json"
    assert M1307_M1306_RESULT_MEDIA_TYPE == "application/vnd.glio-proteogen.m13-06+json"
    assert M1401_OUTPUT_MEDIA_TYPE == "application/vnd.glio-proteogen.m14-01+json"
    assert M1404_OUTPUT_MEDIA_TYPE == "application/vnd.glio-proteogen.m14-04+json"
    assert M1404_M1401_RESULT_MEDIA_TYPE == "application/vnd.glio-proteogen.m14-01+json"


@pytest.mark.parametrize(
    ("factory", "model", "field", "wrong_media_type"),
    [
        (
            build_m1304_request,
            InferProteotypeMechanismRequest,
            "hypothesis_registry_result",
            "application/vnd.glio-proteogen.m11-01+json",
        ),
        (
            build_m1307_request,
            AdjudicateProteotypePlausibilityRequest,
            "mechanism_inference_result",
            "application/vnd.glio-proteogen.m11-04+json",
        ),
        (
            build_m1404_request,
            InferProteinSubtypeMechanismRequest,
            "hypothesis_registry_result",
            "application/vnd.glio-proteogen.m11-01+json",
        ),
    ],
)
def test_m13_m14_requests_reject_legacy_copy_pasted_media_types(
    factory: object,
    model: type[object],
    field: str,
    wrong_media_type: str,
) -> None:
    request = factory()  # type: ignore[operator]
    payload = request.model_dump(mode="python")
    payload[field]["media_type"] = wrong_media_type

    with pytest.raises(ValueError, match=r"provisional M13|provisional M14"):
        model.model_validate(payload, strict=True)  # type: ignore[attr-defined]
