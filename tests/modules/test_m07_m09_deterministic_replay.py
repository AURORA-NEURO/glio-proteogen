"""Adversarial semantic replay checks for deterministic M07--M09 engines."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from glio_proteogen.contracts.m07_02 import result_payload_digest as digest_m0702
from glio_proteogen.contracts.m08_02 import result_payload_digest as digest_m0802
from glio_proteogen.contracts.m08_05 import result_payload_digest as digest_m0805
from glio_proteogen.contracts.m09_02 import result_payload_digest as digest_m0902
from glio_proteogen.contracts.m09_03 import result_payload_digest as digest_m0903
from glio_proteogen.contracts.m09_04 import result_payload_digest as digest_m0904
from glio_proteogen.contracts.m09_05 import result_payload_digest as digest_m0905
from glio_proteogen.modules.c07_copy_number.m07_02_representation_feature_constructor import (
    M0702RepresentationEngine,
)
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_02_representation_feature_constructor as m0802_module,
)
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_05_mechanism_constraint_integrator as m0805_module,
)
from glio_proteogen.modules.c09_complex_activity.m09_02_representation_feature_constructor import (
    M0902RepresentationConstructor,
)
from glio_proteogen.modules.c09_complex_activity.m09_03_mature_baseline_estimator import (
    M0903BaselineEstimator,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    M0905ConstraintIntegrator,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator import (
    M0904ProbabilisticEstimator,
)
from tests.modules.c07_copy_number.test_m07_02_representation import _request as request_m0702
from tests.modules.c08_transcript_protein_discordance.test_m08_02_representation import (
    _request as request_m0802,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_05_integrator import (
    _request as request_m0805,
)
from tests.modules.c09_complex_activity.test_m09_02_constructor import _request as request_m0902
from tests.modules.c09_complex_activity.test_m09_03_estimator import _request as request_m0903
from tests.modules.c09_complex_activity.test_m09_05_integrator import _request as request_m0905
from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import (
    _request as request_m0904,
)


@pytest.mark.parametrize(
    ("engine_factory", "request_factory", "digest"),
    [
        (M0702RepresentationEngine, request_m0702, digest_m0702),
        (m0802_module.M0802RepresentationEngine, request_m0802, digest_m0802),
        (M0902RepresentationConstructor, request_m0902, digest_m0902),
        (M0903BaselineEstimator, request_m0903, digest_m0903),
        (M0904ProbabilisticEstimator, request_m0904, digest_m0904),
    ],
)
def test_self_rehashed_limitations_cannot_bypass_semantic_replay(
    engine_factory: Callable[[], Any],
    request_factory: Callable[..., Any],
    digest: Callable[[Any], str],
) -> None:
    """A valid payload digest does not replace recomputation from the request."""

    request = request_factory()
    engine = engine_factory()
    build_method = next(
        getattr(engine, name) for name in ("construct", "build") if hasattr(engine, name)
    )
    built = build_method(request)
    result = built.result
    forged = result.model_copy(
        update={
            "limitations": (
                *result.limitations[:-1],
                result.limitations[-1].model_copy(update={"statement": "forged"}),
            )
        }
    )
    forged = forged.model_copy(update={"result_digest": digest(forged)})

    verification = engine.verify(forged)
    verified = verification if isinstance(verification, bool) else verification.verified
    assert verified is False


@pytest.mark.parametrize(
    ("engine_factory", "request_factory", "digest"),
    [
        (
            m0805_module.M0805ConstraintIntegrator,
            lambda: request_m0805("conservation_hold"),
            digest_m0805,
        ),
        (M0905ConstraintIntegrator, lambda: request_m0905("conservation_hold"), digest_m0905),
    ],
)
def test_self_rehashed_integrator_result_cannot_bypass_semantic_replay(
    engine_factory: Callable[[], Any],
    request_factory: Callable[[], Any],
    digest: Callable[[Any], str],
) -> None:
    """Constraint reports must be regenerated, not merely rehashed."""

    engine = engine_factory()
    built = engine.integrate(request_factory())
    result = built.result
    forged = result.model_copy(
        update={
            "limitations": (
                *result.limitations[:-1],
                result.limitations[-1].model_copy(update={"statement": "forged"}),
            )
        }
    )
    forged = forged.model_copy(update={"result_digest": digest(forged)})

    assert engine.verify(forged).verified is False
