"""Focused import/schema/safety smoke for provisional M09-04."""

from typing import Final

import pytest

from glio_proteogen.contracts.m09_04 import (
    M0904_OUTPUT_MEDIA_TYPE,
    PosteriorEstimate,
    PosteriorEstimateKind,
    contract_json_schemas,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_04_probabilistic_estimator as runtime,
)

_SCHEMA_COUNT: Final = 8


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0904_OUTPUT_MEDIA_TYPE


def test_posterior_shape_and_preflight_fail_closed() -> None:
    posterior = PosteriorEstimate(
        feature_id="complex.posterior",
        kind=PosteriorEstimateKind.INTERVAL,
        unit="activity",
        estimate_value=0.5,
        lower_bound=0.2,
        upper_bound=0.8,
    )
    assert posterior.lower_bound <= posterior.estimate_value <= posterior.upper_bound
    with pytest.raises(runtime.M0904AuthorizationError):
        runtime.preflight_m0904_authorization({"context": {"references": {}}})
    assert runtime.M0904Plugin(runtime.M0904Service()).descriptor().module_id == (
        "GLIO-PROTEOGEN-M09-04"
    )
