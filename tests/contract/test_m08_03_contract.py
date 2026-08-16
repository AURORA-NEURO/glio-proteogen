"""Focused contract/schema and closure invariants for provisional M08-03."""

import math

import pytest
from evals.m08_03.fixtures import request
from pydantic import ValidationError

from glio_proteogen.contracts.m08_03 import (
    M0803_OUTPUT_MEDIA_TYPE,
    M0803_PROVISIONAL_ABI,
    BaselineFindingCode,
    BaselineMethod,
    EstimateProteinSubtypeBaselineRequest,
    contract_json_schemas,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    M0803Service,
)

_SCHEMA_COUNT = 6


def test_provisional_schemas_require_locked_baseline_evidence() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["benchmarkEvidenceRequired"] for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0803_OUTPUT_MEDIA_TYPE
    assert M0803_PROVISIONAL_ABI is True


def test_baseline_method_options_are_explicit_and_non_treatment() -> None:
    assert tuple(BaselineMethod) == (
        BaselineMethod.STATISTICAL_RULE_BASED,
        BaselineMethod.PATHWAY_ACTIVITY_NETWORK,
        BaselineMethod.SELECTIVE_ENSEMBLE_COMPLEX_GRAPH,
    )


def test_request_rejects_reused_locked_configuration_artifact() -> None:
    candidate = request()
    configuration = candidate.configuration.model_copy(
        update={"tuning_artifact": candidate.configuration.preprocessing_artifact}
    )
    with pytest.raises(ValidationError, match="configuration artifacts must be distinct"):
        EstimateProteinSubtypeBaselineRequest.model_validate(
            candidate.model_copy(update={"configuration": configuration}), strict=True
        )


def test_feature_values_are_finite_and_strict() -> None:
    candidate = request()
    feature = candidate.features[0].model_copy(update={"value": math.nan})
    with pytest.raises(ValidationError):
        EstimateProteinSubtypeBaselineRequest.model_validate(
            candidate.model_copy(update={"features": (feature, *candidate.features[1:])}),
            strict=True,
        )


def test_result_closure_rejects_duplicate_diagnostics_and_estimated_findings() -> None:
    result = M0803Service().execute(request())
    duplicate = result.model_copy(
        update={"diagnostics": (*result.diagnostics, result.diagnostics[0])}
    )
    with pytest.raises(ValidationError, match="diagnostics must have unique"):
        type(result).model_validate(duplicate, strict=True)
    with_finding = result.model_copy(update={"findings": (BaselineFindingCode.OUT_OF_DOMAIN,)})
    with pytest.raises(ValidationError, match="estimated result requires"):
        type(result).model_validate(with_finding, strict=True)


def test_abstention_closure_requires_review_and_finding() -> None:
    result = M0803Service().execute(request(source_name="source.unsupported.ood"))
    no_review = result.model_copy(update={"human_review_required": False})
    with pytest.raises(ValidationError, match="abstained result requires"):
        type(result).model_validate(no_review, strict=True)
    no_finding = result.model_copy(update={"findings": ()})
    with pytest.raises(ValidationError, match="abstained result requires"):
        type(result).model_validate(no_finding, strict=True)
