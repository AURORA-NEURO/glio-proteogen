"""Adversarial JSON, authorization and replay checks for M24-02/04/06."""

from __future__ import annotations

from typing import Any

import pytest

from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_generator as m2402,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_04_external_transport_evaluator as m2404,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_06_robustness_ood_challenge as m2406,
)


@pytest.mark.parametrize(
    ("plugin", "wrapper"),
    [
        (m2402.M2402Plugin(m2402.M2402Service()), m2402.SyntheticTruthSubmission),
        (m2404.M2404Plugin(m2404.M2404Service()), m2404.ExternalTransportSubmission),
        (m2406.M2406Plugin(m2406.M2406Service()), m2406.RobustnessSubmission),
    ],
)
def test_duplicate_keys_are_rejected_before_contract_validation(plugin: Any, wrapper: Any) -> None:
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(wrapper(b'{"request_id":"safe","request_id":"forged"}'))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


@pytest.mark.parametrize(
    "module",
    [m2402, m2404, m2406],
)
def test_hostile_control_mapping_fails_closed_before_material_walk(module: Any) -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(module.AuthorizationError):
        module.preflight_m2402_authorization(ExplodingMapping()) if module is m2402 else (
            module.preflight_m2404_authorization(ExplodingMapping())
            if module is m2404
            else module.preflight_m2406_authorization(ExplodingMapping())
        )
