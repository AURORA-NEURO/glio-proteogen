"""Strict contract/schema smoke for the provisional M06-04 scaffold."""

from __future__ import annotations

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m06_04 import (
    M0604_OUTPUT_MEDIA_TYPE,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604ProbabilisticEstimatorEngine,
    M0604Service,
)

_EXPECTED_LOWER_BOUND = 0.5


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
        assert metadata["calibrationFrozen"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0604_OUTPUT_MEDIA_TYPE


def test_prior_posterior_and_runtime_import_smoke() -> None:
    prior = ProbabilisticPrior(
        prior_id="prior.m0604.smoke",
        version="1.0.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.0, 1.0),
    )
    posterior = PosteriorEstimate(
        feature_id="feature.m0604.smoke",
        kind=PosteriorEstimateKind.INTERVAL,
        unit="abundance",
        estimate_value=1.0,
        lower_bound=0.5,
        upper_bound=1.5,
    )
    assert prior.parameters == (0.0, 1.0)
    assert posterior.lower_bound == _EXPECTED_LOWER_BOUND
    assert canonical_request_digest({"prior": prior.model_dump(mode="json")}).startswith("sha256:")
    assert M0604Service is not None
    assert M0604ProbabilisticEstimatorEngine is not None
