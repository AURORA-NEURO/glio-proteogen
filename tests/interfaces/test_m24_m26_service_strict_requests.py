"""Adversarial strict-parser coverage for direct M24--M26 service seams."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode

if TYPE_CHECKING:
    from types import ModuleType


_SERVICE_CASES: tuple[tuple[str, str], ...] = (
    (
        "glio_proteogen.modules.c21_reference_material.m24_07_human_factors_operational_evaluator.service",
        "M2407Service",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_02_synthetic_truth_simulation_generator.service",
        "M2502Service",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.service",
        "M2503Service",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.service",
        "M2505Service",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_07_human_factors_operational_evaluator.service",
        "M2507Service",
    ),
)


@pytest.mark.parametrize(("module_name", "service_name"), _SERVICE_CASES)
def test_direct_service_rejects_duplicate_request_members(
    module_name: str,
    service_name: str,
) -> None:
    """The library seam must share the same unambiguous parser as API/plugin."""

    module: ModuleType = importlib.import_module(module_name)
    service = getattr(module, service_name)()

    with pytest.raises(StrictJsonError) as error:
        service.validate_request(b'{"request_id":"a","request_id":"b"}')

    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY
