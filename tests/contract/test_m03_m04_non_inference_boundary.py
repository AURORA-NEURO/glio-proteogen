"""Adversarial closure for the M03/M04 biological-inference boundary."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m03_01.schema import contract_json_schema as m0301_schema
from glio_proteogen.contracts.m03_01.v1 import ProteinInferenceProtocolConformanceResult
from glio_proteogen.contracts.m03_02.schema import contract_json_schema as m0302_schema
from glio_proteogen.contracts.m03_02.v1 import ProteinInferenceIdentityLineageResolution
from glio_proteogen.contracts.m03_03.schema import contract_json_schema as m0303_schema
from glio_proteogen.contracts.m03_03.v1 import ProteinInferenceRawAdmissionResult
from glio_proteogen.contracts.m03_04.schema import contract_json_schema as m0304_schema
from glio_proteogen.contracts.m03_04.v1 import ProteinInferenceQualityResult
from glio_proteogen.contracts.m03_05.schema import contract_json_schema as m0305_schema
from glio_proteogen.contracts.m03_05.v1 import ProteinInferenceArtifactDetectionResult
from glio_proteogen.contracts.m03_06.schema import contract_json_schema as m0306_schema
from glio_proteogen.contracts.m03_06.v1 import ProteinInferenceHarmonizationResult
from glio_proteogen.contracts.m03_07.schema import contract_json_schema as m0307_schema
from glio_proteogen.contracts.m03_07.v1 import ProteinInferenceSupportRouteResult
from glio_proteogen.contracts.m03_08.schema import contract_json_schema as m0308_schema
from glio_proteogen.contracts.m03_08.v1 import ProteinInferenceReleaseResult
from glio_proteogen.contracts.m04_01.schema import contract_json_schema as m0401_schema
from glio_proteogen.contracts.m04_01.v1 import ProteoformProtocolConformanceResult
from glio_proteogen.contracts.m04_02.schema import contract_json_schema as m0402_schema
from glio_proteogen.contracts.m04_02.v1 import ProteoformIdentityLineageResolution
from glio_proteogen.contracts.m04_03.schema import contract_json_schema as m0403_schema
from glio_proteogen.contracts.m04_03.v1 import ProteoformRawInputValidationResult
from glio_proteogen.contracts.m04_04.schema import contract_json_schema as m0404_schema
from glio_proteogen.contracts.m04_04.v1 import ProteoformQualityResult
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Plugin,
    M0301Service,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Plugin,
    M0401Service,
)


_BOUNDARY_FIELDS = (
    "infers_protein",
    "infers_proteoform",
    "infers_isoform",
    "infers_glioma_specific_biology",
)
_RESULT_MODELS: tuple[type[BaseModel], ...] = (
    ProteinInferenceProtocolConformanceResult,
    ProteinInferenceIdentityLineageResolution,
    ProteinInferenceRawAdmissionResult,
    ProteinInferenceQualityResult,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceSupportRouteResult,
    ProteinInferenceReleaseResult,
    ProteoformProtocolConformanceResult,
    ProteoformIdentityLineageResolution,
    ProteoformRawInputValidationResult,
    ProteoformQualityResult,
)
_SCHEMA_FACTORIES = (
    m0301_schema,
    m0302_schema,
    m0303_schema,
    m0304_schema,
    m0305_schema,
    m0306_schema,
    m0307_schema,
    m0308_schema,
    m0401_schema,
    m0402_schema,
    m0403_schema,
    m0404_schema,
)


@pytest.mark.contract
def test_every_m03_m04_result_has_closed_false_inference_authority() -> None:
    for model in _RESULT_MODELS:
        for field in _BOUNDARY_FIELDS:
            assert field in model.model_fields, (model.__name__, field)
            assert model.model_fields[field].default is False


@pytest.mark.contract
@pytest.mark.parametrize("field", _BOUNDARY_FIELDS)
def test_true_boundary_claims_are_rejected_before_relational_validation(field: str) -> None:
    for model in _RESULT_MODELS:
        with pytest.raises(ValidationError) as caught:
            model.model_validate({field: True}, strict=True)
        assert any(
            error["loc"] == (field,) and error["type"] == "literal_error"
            for error in caught.value.errors()
        ), (model.__name__, field, caught.value.errors())


@pytest.mark.contract
def test_unknown_biological_claims_are_rejected_by_every_result_envelope() -> None:
    for model in _RESULT_MODELS:
        with pytest.raises(ValidationError) as caught:
            model.model_validate({"glioma_diagnosis": "positive"}, strict=True)
        assert any(error["type"] == "extra_forbidden" for error in caught.value.errors())


@pytest.mark.contract
def test_exported_output_schemas_publish_false_authority_and_const_properties() -> None:
    for schema_factory in _SCHEMA_FACTORIES:
        schema = schema_factory("output")
        metadata = schema["x-glio-contract"]
        properties = schema["properties"]
        assert isinstance(metadata, dict)
        assert isinstance(properties, dict)
        for field in _BOUNDARY_FIELDS:
            metadata_key = {
                "infers_protein": "proteinInference",
                "infers_proteoform": "proteoformInference",
                "infers_isoform": "isoformInference",
                "infers_glioma_specific_biology": "gliomaSpecificBiologyInference",
            }[field]
            assert metadata[metadata_key] is False
            assert properties[field]["const"] is False


@pytest.mark.contract
def test_plugin_request_boundaries_reject_inference_claims_before_execution() -> None:
    from evals.m03_01.run import build_scenario_request as build_m0301_request
    from evals.m04_01.run import build_scenario_request as build_m0401_request

    for request, plugin in (
        (build_m0301_request(), M0301Plugin(M0301Service())),
        (build_m0401_request(), M0401Plugin(M0401Service())),
    ):
        payload: dict[str, Any] = request.model_dump(mode="json")
        payload["infers_glioma_specific_biology"] = True
        with pytest.raises(ValidationError):
            plugin.validate(canonical_json_bytes(payload))
