"""Adversarial capability-boundary checks for every M06 plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    M0603Plugin,
    M0603Service,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.plugin import (
    ValidatedM0603Request,
)
from glio_proteogen.modules.c06_protein_abundance import (
    m06_02_representation_feature_constructor as m0602_module,
)
from glio_proteogen.modules.c06_protein_abundance import (
    m06_04_probabilistic_advanced_estimator as m0604_module,
)
from glio_proteogen.modules.c06_protein_abundance import (
    m06_05_mechanism_constraint_integrator as m0605_module,
)
from glio_proteogen.modules.c06_protein_abundance import (
    m06_07_calibration_selective_prediction as m0607_module,
)
from glio_proteogen.modules.c06_protein_abundance import (
    m06_08_evidence_explanation_publisher as m0608_module,
)
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    M0601Plugin,
    M0601Service,
)
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema.plugin import (
    M0601Submission,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    M0602Plugin,
)
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604Plugin,
    M0604Service,
)
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    M0605Plugin,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition import (
    M0606Plugin,
    M0606Service,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.plugin import (
    ValidatedM0606Request,
)
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    M0607Plugin,
)
from glio_proteogen.modules.c06_protein_abundance.m06_08_evidence_explanation_publisher import (
    M0608Plugin,
    M0608Service,
)
from tests.contract.test_m06_01_hardening import _request as m0601_request
from tests.contract.test_m06_04_hardening import _request as m0604_request
from tests.integration.test_m06_03_runtime import _request as m0603_request
from tests.modules.c06_protein_abundance.test_m06_02_representation_constructor import (
    _request as m0602_request,
)
from tests.modules.c06_protein_abundance.test_m06_05_constraint_integrator import (
    _request as m0605_request,
)
from tests.modules.c06_protein_abundance.test_m06_07_calibration import (
    _request as m0607_request,
)


def _m0601() -> tuple[Any, Any]:
    plugin = M0601Plugin(M0601Service())
    return plugin, plugin.validate(M0601Submission(m0601_request()))


def _m0602() -> tuple[Any, Any]:
    plugin = M0602Plugin()
    return plugin, plugin.validate(m0602_module.RepresentationSubmission(m0602_request()))


def _m0603() -> tuple[Any, Any]:
    plugin = M0603Plugin(M0603Service())
    return plugin, plugin.validate(m0603_request())


def _m0604() -> tuple[Any, Any]:
    plugin = M0604Plugin(M0604Service())
    return plugin, plugin.validate(m0604_module.M0604Submission(m0604_request()))


def _m0605() -> tuple[Any, Any]:
    plugin = M0605Plugin()
    return plugin, plugin.validate(m0605_module.ConstraintIntegrationSubmission(m0605_request()))


def _m0607() -> tuple[Any, Any]:
    plugin = M0607Plugin()
    return plugin, plugin.validate(m0607_module.CalibrationSubmission(m0607_request()))


@pytest.mark.parametrize(
    "factory",
    [_m0601, _m0602, _m0603, _m0604, _m0605, _m0607],
    ids=["m06-01", "m06-02", "m06-03", "m06-04", "m06-05", "m06-07"],
)
def test_issued_tokens_are_instance_bound_and_mutation_detected(
    factory: Callable[[], tuple[Any, Any]],
) -> None:
    plugin, token = factory()

    other_plugin, _ = factory()
    with pytest.raises(TypeError, match="validated request token"):
        other_plugin.run(token)

    forged = type(token)(request=token.request, _seal=getattr(token, "_seal", None))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)

    object.__setattr__(token, "request", token.request.model_copy(deep=True))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_existing_sealed_m0603_token_is_not_cross_instance_reusable() -> None:
    first, token = _m0603()
    second, _ = _m0603()

    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)
    assert isinstance(token, ValidatedM0603Request)
    assert first.run(first.validate(m0603_request())) is not None


def test_existing_sealed_m0606_and_m0608_tokens_remain_strict_types() -> None:
    # Their full valid fixtures are covered in the module suites; these checks
    # ensure forged dataclass instances cannot cross the strict type boundary.
    forged_06 = ValidatedM0606Request(request=object(), _seal=object())
    forged_08 = m0608_module.ValidatedM0608Request(request=object(), _seal=object())
    plugin_06 = M0606Plugin(M0606Service())
    plugin_08 = M0608Plugin(M0608Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin_06.run(forged_06)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validated request token"):
        plugin_08.run(forged_08)  # type: ignore[arg-type]
