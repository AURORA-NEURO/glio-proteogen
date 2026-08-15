"""Strict contract/schema smoke for the provisional M07-04 scaffold."""

from __future__ import annotations

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m07_04 import (
    M0704_OUTPUT_MEDIA_TYPE,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704ProbabilisticEstimatorEngine,
    M0704Service,
)

_EXPECTED_LOWER_BOUND = 1.0


def test_schema_inventory_is_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "configuration",
        "prior",
        "constraint",
        "posterior",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
        assert metadata["modelMetricsFrozen"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0704_OUTPUT_MEDIA_TYPE


def test_prior_posterior_and_runtime_import_smoke() -> None:
    prior = ProbabilisticPrior(
        prior_id="prior.m0704.smoke",
        version="1.0.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.0, 1.0),
    )
    posterior = PosteriorEstimate(
        feature_id="feature.m0704.smoke",
        kind=PosteriorEstimateKind.INTERVAL,
        unit="copy-number",
        estimate_value=2.0,
        lower_bound=_EXPECTED_LOWER_BOUND,
        upper_bound=3.0,
    )
    assert prior.parameters == (0.0, 1.0)
    assert posterior.lower_bound == _EXPECTED_LOWER_BOUND
    assert canonical_request_digest({"prior": prior.model_dump(mode="json")}).startswith(
        "sha256:"
    )
    assert M0704Service is not None
    assert M0704ProbabilisticEstimatorEngine is not None
