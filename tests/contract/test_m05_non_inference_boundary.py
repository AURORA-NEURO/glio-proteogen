"""Adversarial closure for the frozen M05 non-inference result boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from glio_proteogen.contracts.m05_01.v1 import (
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.contracts.m05_02.v1 import PtmLocalizationIdentityLineageResolution
from glio_proteogen.contracts.m05_03.v1 import PtmLocalizationRawInputValidationResult
from glio_proteogen.contracts.m05_04.v1 import PtmLocalizationQualityResult
from glio_proteogen.contracts.m05_05.v1 import PtmLocalizationArtifactDetectionResult
from glio_proteogen.kernel.models import NonInferenceResultModel

if TYPE_CHECKING:
    from pydantic import BaseModel


_RESULT_MODELS: tuple[type[BaseModel], ...] = (
    PtmLocalizationProtocolConformanceResult,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationRawInputValidationResult,
    PtmLocalizationQualityResult,
    PtmLocalizationArtifactDetectionResult,
)


@pytest.mark.contract
def test_every_frozen_m05_result_uses_recursive_non_inference_firewall() -> None:
    """M05-01..05 outputs must have the same tamper firewall as M03/M04 outputs."""

    assert all(issubclass(model, NonInferenceResultModel) for model in _RESULT_MODELS)


@pytest.mark.contract
def test_frozen_m05_result_authority_flags_remain_literal_false() -> None:
    expected = {
        "ptm_localization_protocol_conformance_result": {
            "emits_variant_peptide",
            "emits_proteogenomic_state",
            "emits_proteotype",
            "emits_protein_level_subtype",
            "localizes_ptm",
            "infers_kinase_activity",
            "performs_all_omics_fusion",
            "recommends_treatment",
            "mutates_upstream_evidence",
            "infers_identity_or_consent",
        },
        "ptm_localization_identity_lineage_resolution": {
            "emits_variant_peptide",
            "emits_proteogenomic_state",
            "emits_proteotype",
            "emits_protein_level_subtype",
            "infers_identity",
            "infers_consent",
            "infers_protein",
            "infers_ptm_localization",
            "infers_kinase_activity",
            "performs_cn_to_protein_regression",
            "performs_all_omics_fusion",
            "recommends_treatment",
            "mutates_upstream",
        },
        "ptm_localization_raw_input_validation_result": {
            "emits_variant_peptide",
            "emits_proteogenomic_state",
            "emits_proteotype",
            "emits_protein_level_subtype",
            "infers_identity",
            "infers_consent",
            "infers_protein",
            "infers_proteoform",
            "infers_ptm_localization",
            "infers_kinase_activity",
            "performs_cn_to_protein_regression",
            "performs_all_omics_fusion",
            "recommends_treatment",
            "mutates_upstream",
            "executes_model",
        },
        "ptm_localization_quality_profile": {
            "emits_variant_peptide",
            "emits_proteogenomic_state",
            "emits_proteotype",
            "emits_protein_level_subtype",
            "infers_identity",
            "infers_consent",
            "infers_protein",
            "infers_proteoform",
            "infers_ptm_localization",
            "infers_isoform",
            "localizes_modification",
            "infers_kinase_activity",
            "performs_cn_to_protein_regression",
            "performs_all_omics_fusion",
            "recommends_treatment",
            "mutates_upstream",
            "executes_model",
        },
        "ptm_localization_artifact_contamination_assessment": {
            "emits_variant_peptide",
            "emits_proteogenomic_state",
            "emits_proteotype",
            "emits_protein_level_subtype",
            "infers_identity",
            "infers_consent",
            "localizes_modification",
            "infers_kinase_activity",
            "performs_all_omics_fusion",
            "recommends_treatment",
            "mutates_upstream",
        },
    }
    for model in _RESULT_MODELS:
        fields = expected[model.model_fields["output_type"].default]
        assert fields <= model.model_fields.keys()
        assert all(model.model_fields[field].default is False for field in fields)
