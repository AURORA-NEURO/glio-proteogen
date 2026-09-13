"""Focused contract/schema and closure invariants for provisional M08-03."""

import math

import pytest
from evals.m08_03.fixtures import request
from pydantic import ValidationError

from glio_proteogen.contracts.m08_03 import (
    M0803_GLIOMA_MODEL_FAMILY,
    M0803_OUTPUT_MEDIA_TYPE,
    M0803_PROVISIONAL_ABI,
    BaselineFindingCode,
    BaselineMethod,
    EstimateProteinSubtypeBaselineRequest,
    GliomaEvidenceState,
    GliomaProgram,
    GliomaProgramLabel,
    ProteinSubtypeBaselineEstimate,
    TypedBaselineObservation,
    TypedProgramState,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import EvidenceReference
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


def test_typed_observation_states_are_shape_closed() -> None:
    evidence = request().source_artifacts[0]
    reference = EvidenceReference(
        reference=evidence,
        role="evidence",
        claim="typed contract fixture",
    )
    observed = TypedBaselineObservation(
        observation_id="typed.observed",
        program=GliomaProgram.PROLIFERATION,
        standardized_effect=0.5,
        standard_error=0.2,
        evidence=(reference,),
    )
    censored = TypedBaselineObservation(
        observation_id="typed.censored",
        program=GliomaProgram.RTK_PI3K_AKT_MTOR,
        state=GliomaEvidenceState.LEFT_CENSORED,
        censoring_limit=-1.0,
        standard_error=0.3,
        evidence=(reference,),
    )
    assert observed.state is GliomaEvidenceState.OBSERVED
    assert censored.state is GliomaEvidenceState.LEFT_CENSORED
    with pytest.raises(ValidationError, match="requires effect and standard error"):
        TypedBaselineObservation(
            observation_id="typed.bad-observed",
            program=GliomaProgram.PROLIFERATION,
            standard_error=0.2,
            evidence=(reference,),
        )
    with pytest.raises(ValidationError, match="cannot carry values"):
        TypedBaselineObservation(
            observation_id="typed.bad-missing",
            program=GliomaProgram.PROLIFERATION,
            state=GliomaEvidenceState.MISSING,
            standardized_effect=0.1,
            evidence=(reference,),
        )
    with pytest.raises(ValidationError, match="must use the evidence role"):
        TypedBaselineObservation(
            observation_id="typed.bad-role",
            program=GliomaProgram.PROLIFERATION,
            standardized_effect=0.1,
            standard_error=0.2,
            evidence=(reference.model_copy(update={"role": "counter_evidence"}),),
        )


def test_typed_state_and_estimate_closures_reject_unsafe_shapes() -> None:
    with pytest.raises(ValidationError, match="interval must contain"):
        TypedProgramState(
            program=GliomaProgram.PROLIFERATION,
            state=0.5,
            lower_bound=0.6,
            upper_bound=0.4,
            label=GliomaProgramLabel.INDETERMINATE,
            evidence_count=1,
            stability=0.5,
        )
    with pytest.raises(ValidationError, match="bounded"):
        TypedProgramState(
            program=GliomaProgram.PROLIFERATION,
            state=1.2,
            lower_bound=0.0,
            upper_bound=1.2,
            label=GliomaProgramLabel.ACTIVATED,
            evidence_count=1,
            stability=0.5,
        )
    with pytest.raises(ValidationError, match="require a model family"):
        ProteinSubtypeBaselineEstimate(
            predicted_subtype="glioma",
            score=0.5,
            calibration_reference=request().configuration.uncertainty_artifact,
            program_states=(
                TypedProgramState(
                    program=GliomaProgram.PROLIFERATION,
                    state=0.0,
                    lower_bound=-0.1,
                    upper_bound=0.1,
                    label=GliomaProgramLabel.NEUTRAL,
                    evidence_count=1,
                    stability=0.9,
                ),
            ),
        )


def test_typed_request_rejects_duplicate_ids_and_wrong_replicate_limit() -> None:
    candidate = request()
    evidence = EvidenceReference(
        reference=candidate.source_artifacts[0],
        role="evidence",
        claim="typed contract fixture",
    )
    observation = TypedBaselineObservation(
        observation_id="typed.duplicate",
        program=GliomaProgram.PROLIFERATION,
        standardized_effect=0.2,
        standard_error=0.2,
        evidence=(evidence,),
    )
    with pytest.raises(ValidationError, match="observation ids must be unique"):
        EstimateProteinSubtypeBaselineRequest.model_validate(
            candidate.model_copy(update={"program_observations": (observation, observation)}),
            strict=True,
        )
    with pytest.raises(ValidationError):
        type(candidate.configuration).model_validate(
            candidate.configuration.model_dump(
                mode="python",
                round_trip=True,
                exclude_none=False,
            )
            | {"model_family": M0803_GLIOMA_MODEL_FAMILY, "bootstrap_replicates": 257},
            strict=True,
        )
