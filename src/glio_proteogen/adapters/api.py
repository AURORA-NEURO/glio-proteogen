"""FastAPI surface for the active pre-analytic module slices."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Final, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters import m1901 as m1901_adapter
from glio_proteogen.adapters import m1902 as m1902_adapter
from glio_proteogen.adapters import m1905 as m1905_adapter
from glio_proteogen.adapters import m2002 as m2002_adapter
from glio_proteogen.adapters import m2003 as m2003_adapter
from glio_proteogen.adapters import m2004 as m2004_adapter
from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES, RequestSizeLimitMiddleware
from glio_proteogen.contracts.m01_01.schema import (
    ContractName as M0101ContractName,
)
from glio_proteogen.contracts.m01_01.schema import (
    contract_json_schema as m0101_contract_json_schema,
)
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceProfile,
    EvaluateMetadataRequest,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)
from glio_proteogen.contracts.m01_02.schema import (
    ContractName as M0102ContractName,
)
from glio_proteogen.contracts.m01_02.schema import (
    contract_json_schema as m0102_contract_json_schema,
)
from glio_proteogen.contracts.m01_02.v1 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m01_03.schema import (
    ContractName as M0103ContractName,
)
from glio_proteogen.contracts.m01_03.schema import (
    contract_json_schema as m0103_contract_json_schema,
)
from glio_proteogen.contracts.m01_03.v1 import ValidatedRawInputDescriptor
from glio_proteogen.contracts.m01_04.schema import (
    ContractName as M0104ContractName,
)
from glio_proteogen.contracts.m01_04.schema import (
    contract_json_schema as m0104_contract_json_schema,
)
from glio_proteogen.contracts.m01_04.v1 import (
    ComputeQualityMetricsRequest,
    QualityProfile,
)
from glio_proteogen.contracts.m01_05.schema import (
    ContractName as M0105ContractName,
)
from glio_proteogen.contracts.m01_05.schema import (
    contract_json_schema as m0105_contract_json_schema,
)
from glio_proteogen.contracts.m01_05.v1 import (
    ArtifactDetectionResult,
    DetectArtifactsRequest,
)
from glio_proteogen.contracts.m01_06.schema import (
    ContractName as M0106ContractName,
)
from glio_proteogen.contracts.m01_06.schema import (
    contract_json_schema as m0106_contract_json_schema,
)
from glio_proteogen.contracts.m01_06.v1 import (
    HarmonizationResult,
    HarmonizeObservationsRequest,
)
from glio_proteogen.contracts.m01_07.schema import (
    ContractName as M0107ContractName,
)
from glio_proteogen.contracts.m01_07.schema import (
    contract_json_schema as m0107_contract_json_schema,
)
from glio_proteogen.contracts.m01_07.v1 import (
    RouteSupportRequest,
    SupportRoutingResult,
)
from glio_proteogen.contracts.m01_08.schema import (
    ContractName as M0108ContractName,
)
from glio_proteogen.contracts.m01_08.schema import (
    contract_json_schema as m0108_contract_json_schema,
)
from glio_proteogen.contracts.m02_01.schema import (
    ContractName as M0201ContractName,
)
from glio_proteogen.contracts.m02_01.schema import (
    contract_json_schema as m0201_contract_json_schema,
)
from glio_proteogen.contracts.m02_01.v1 import (
    ConformanceEvaluation as M0201ConformanceEvaluation,
)
from glio_proteogen.contracts.m02_01.v1 import EvaluateConformanceRequest
from glio_proteogen.contracts.m02_02.schema import (
    ContractName as M0202ContractName,
)
from glio_proteogen.contracts.m02_02.schema import (
    contract_json_schema as m0202_contract_json_schema,
)
from glio_proteogen.contracts.m02_02.v1 import (
    IdentityBindingEvaluation,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.contracts.m02_03.schema import (
    ContractName as M0203ContractName,
)
from glio_proteogen.contracts.m02_03.schema import (
    contract_json_schema as m0203_contract_json_schema,
)
from glio_proteogen.contracts.m02_04.schema import (
    ContractName as M0204ContractName,
)
from glio_proteogen.contracts.m02_04.schema import (
    contract_json_schema as m0204_contract_json_schema,
)
from glio_proteogen.contracts.m02_04.v1 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityProfile,
)
from glio_proteogen.contracts.m02_05.schema import (
    ContractName as M0205ContractName,
)
from glio_proteogen.contracts.m02_05.schema import (
    contract_json_schema as m0205_contract_json_schema,
)
from glio_proteogen.contracts.m02_05.v1 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.contracts.m02_06.schema import (
    ContractName as M0206ContractName,
)
from glio_proteogen.contracts.m02_06.schema import (
    contract_json_schema as m0206_contract_json_schema,
)
from glio_proteogen.contracts.m02_06.v1 import (
    HarmonizeIdentificationEvidenceRequest,
    IdentificationHarmonizationResult,
)
from glio_proteogen.contracts.m02_07.schema import (
    ContractName as M0207ContractName,
)
from glio_proteogen.contracts.m02_07.schema import (
    contract_json_schema as m0207_contract_json_schema,
)
from glio_proteogen.contracts.m02_07.v1 import (
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)
from glio_proteogen.contracts.m02_08.schema import (
    ContractName as M0208ContractName,
)
from glio_proteogen.contracts.m02_08.schema import (
    contract_json_schema as m0208_contract_json_schema,
)
from glio_proteogen.contracts.m03_01.schema import (
    ContractName as M0301ContractName,
)
from glio_proteogen.contracts.m03_01.schema import (
    contract_json_schema as m0301_contract_json_schema,
)
from glio_proteogen.contracts.m03_01.v1 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.contracts.m03_02.schema import (
    ContractName as M0302ContractName,
)
from glio_proteogen.contracts.m03_02.schema import (
    contract_json_schema as m0302_contract_json_schema,
)
from glio_proteogen.contracts.m03_02.v1 import (
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
)
from glio_proteogen.contracts.m03_03.schema import (
    ContractName as M0303ContractName,
)
from glio_proteogen.contracts.m03_03.schema import (
    contract_json_schema as m0303_contract_json_schema,
)
from glio_proteogen.contracts.m03_04.schema import (
    ContractName as M0304ContractName,
)
from glio_proteogen.contracts.m03_04.schema import (
    contract_json_schema as m0304_contract_json_schema,
)
from glio_proteogen.contracts.m03_04.v1 import (
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    M0304_MAX_CANONICAL_RESULT_BYTES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
)
from glio_proteogen.contracts.m03_05.schema import (
    ContractName as M0305ContractName,
)
from glio_proteogen.contracts.m03_05.schema import (
    contract_json_schema as m0305_contract_json_schema,
)
from glio_proteogen.contracts.m03_05.v1 import (
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    M0305_MAX_CANONICAL_RESULT_BYTES,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.contracts.m03_06.schema import (
    ContractName as M0306ContractName,
)
from glio_proteogen.contracts.m03_06.schema import (
    contract_json_schema as m0306_contract_json_schema,
)
from glio_proteogen.contracts.m03_06.v1 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MAX_CANONICAL_RESULT_BYTES,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.contracts.m03_07.schema import (
    ContractName as M0307ContractName,
)
from glio_proteogen.contracts.m03_07.schema import (
    contract_json_schema as m0307_contract_json_schema,
)
from glio_proteogen.contracts.m03_07.v1 import (
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    M0307_MAX_CANONICAL_RESULT_BYTES,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)
from glio_proteogen.contracts.m03_08.schema import (
    ContractName as M0308ContractName,
)
from glio_proteogen.contracts.m03_08.schema import (
    contract_json_schema as m0308_contract_json_schema,
)
from glio_proteogen.contracts.m04_01.schema import (
    ContractName as M0401ContractName,
)
from glio_proteogen.contracts.m04_01.schema import (
    contract_json_schema as m0401_contract_json_schema,
)
from glio_proteogen.contracts.m04_01.v1 import (
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteoformProtocolRequest,
    ProteoformProtocolConformanceResult,
)
from glio_proteogen.contracts.m04_02.schema import (
    ContractName as M0402ContractName,
)
from glio_proteogen.contracts.m04_02.schema import (
    contract_json_schema as m0402_contract_json_schema,
)
from glio_proteogen.contracts.m04_02.v1 import (
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformIdentityLineageResolution,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.contracts.m04_03.schema import (
    ContractName as M0403ContractName,
)
from glio_proteogen.contracts.m04_03.schema import (
    contract_json_schema as m0403_contract_json_schema,
)
from glio_proteogen.contracts.m04_04.schema import (
    ContractName as M0404ContractName,
)
from glio_proteogen.contracts.m04_04.schema import (
    contract_json_schema as m0404_contract_json_schema,
)
from glio_proteogen.contracts.m04_04.v1 import (
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityResult,
)
from glio_proteogen.contracts.m04_05.schema import (
    ContractName as M0405ContractName,
)
from glio_proteogen.contracts.m04_05.schema import (
    contract_json_schema as m0405_contract_json_schema,
)
from glio_proteogen.contracts.m04_05.v1 import (
    M0405_MAX_CANONICAL_REQUEST_BYTES,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
)
from glio_proteogen.contracts.m04_06.schema import (
    ContractName as M0406ContractName,
)
from glio_proteogen.contracts.m04_06.schema import (
    contract_json_schema as m0406_contract_json_schema,
)
from glio_proteogen.contracts.m04_06.v1 import (
    M0406_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizationResult,
)
from glio_proteogen.contracts.m04_07.schema import (
    ContractName as M0407ContractName,
)
from glio_proteogen.contracts.m04_07.schema import (
    contract_json_schema as m0407_contract_json_schema,
)
from glio_proteogen.contracts.m04_07.v1 import (
    M0407_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
)
from glio_proteogen.contracts.m04_08.schema import (
    ContractName as M0408ContractName,
)
from glio_proteogen.contracts.m04_08.schema import (
    contract_json_schema as m0408_contract_json_schema,
)
from glio_proteogen.contracts.m05_01.schema import (
    ContractName as M0501ContractName,
)
from glio_proteogen.contracts.m05_01.schema import (
    contract_json_schema as m0501_contract_json_schema,
)
from glio_proteogen.contracts.m05_01.v1 import (
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.contracts.m05_02.schema import (
    ContractName as M0502ContractName,
)
from glio_proteogen.contracts.m05_02.schema import (
    contract_json_schema as m0502_contract_json_schema,
)
from glio_proteogen.contracts.m05_02.v1 import (
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationIdentityLineageResolution,
    ReconcilePtmLocalizationIdentityLineageRequest,
)
from glio_proteogen.contracts.m05_03.schema import (
    ContractName as M0503ContractName,
)
from glio_proteogen.contracts.m05_03.schema import (
    contract_json_schema as m0503_contract_json_schema,
)
from glio_proteogen.contracts.m05_04.schema import (
    ContractName as M0504ContractName,
)
from glio_proteogen.contracts.m05_04.schema import (
    contract_json_schema as m0504_contract_json_schema,
)
from glio_proteogen.contracts.m05_04.v1 import (
    M0504_MAX_CANONICAL_REQUEST_BYTES,
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationQualityResult,
)
from glio_proteogen.contracts.m05_04.v1 import (
    _ValidatedRequestCapability as _ValidatedM0504RequestCapability,
)
from glio_proteogen.contracts.m05_05.schema import (
    ContractName as M0505ContractName,
)
from glio_proteogen.contracts.m05_05.schema import (
    contract_json_schema as m0505_contract_json_schema,
)
from glio_proteogen.contracts.m05_05.v1 import (
    M0505_MAX_CANONICAL_REQUEST_BYTES,
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactDetectionResult,
)
from glio_proteogen.contracts.m05_06.schema import (
    ContractName as M0506ContractName,
)
from glio_proteogen.contracts.m05_06.schema import (
    contract_json_schema as m0506_contract_json_schema,
)
from glio_proteogen.contracts.m05_06.v1 import (
    M0506_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizePtmLocalizationAnalysisRequest,
    PtmLocalizationHarmonizationResult,
)
from glio_proteogen.contracts.m05_07.schema import (
    ContractName as M0507ContractName,
)
from glio_proteogen.contracts.m05_07.schema import (
    contract_json_schema as m0507_contract_json_schema,
)
from glio_proteogen.contracts.m05_07.v1 import (
    M0507_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationSupportRouteResult,
    RoutePtmLocalizationSupportRequest,
)
from glio_proteogen.contracts.m06_01.schema import (
    ContractName as M0601ContractName,
)
from glio_proteogen.contracts.m06_01.schema import (
    contract_json_schema as m0601_contract_json_schema,
)
from glio_proteogen.contracts.m06_01.v1 import (
    M0601_MAX_CANONICAL_REQUEST_BYTES,
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
)
from glio_proteogen.contracts.m06_03.schema import (
    ContractName as M0603ContractName,
)
from glio_proteogen.contracts.m06_03.schema import (
    contract_json_schema as m0603_contract_json_schema,
)
from glio_proteogen.contracts.m06_03.v1 import (
    M0603_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceBaselineRequest,
    EstimateProteinAbundanceBaselineResult,
)
from glio_proteogen.contracts.m06_04.schema import (
    ContractName as M0604ContractName,
)
from glio_proteogen.contracts.m06_04.schema import (
    contract_json_schema as m0604_contract_json_schema,
)
from glio_proteogen.contracts.m06_04.v1 import (
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceProbabilisticRequest,
    EstimateProteinAbundanceProbabilisticResult,
)
from glio_proteogen.contracts.m06_06.schema import (
    ContractName as M0606ContractName,
)
from glio_proteogen.contracts.m06_06.schema import (
    contract_json_schema as m0606_contract_json_schema,
)
from glio_proteogen.contracts.m06_06.v1 import (
    M0606_MAX_CANONICAL_REQUEST_BYTES,
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
)
from glio_proteogen.contracts.m08_01.schema import (
    ContractName as M0801ContractName,
)
from glio_proteogen.contracts.m08_01.schema import (
    contract_json_schema as m0801_contract_json_schema,
)
from glio_proteogen.contracts.m08_01.v1 import (
    M0801_MAX_CANONICAL_REQUEST_BYTES,
    ValidateTranscriptProteinStateRequest,
    ValidateTranscriptProteinStateResult,
)
from glio_proteogen.contracts.m08_03.schema import (
    ContractName as M0803ContractName,
)
from glio_proteogen.contracts.m08_03.schema import (
    contract_json_schema as m0803_contract_json_schema,
)
from glio_proteogen.contracts.m08_03.v1 import (
    M0803_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinSubtypeBaselineRequest,
    ProteinSubtypeBaselineResult,
)
from glio_proteogen.contracts.m13_06.schema import ContractName as M1306ContractName
from glio_proteogen.contracts.m13_06.schema import (
    contract_json_schema as m1306_contract_json_schema,
)
from glio_proteogen.contracts.m13_06.v1 import (
    M1306_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypePerturbationSensitivityResult,
    SimulateProteotypePerturbationRequest,
)
from glio_proteogen.contracts.m14_03.schema import ContractName as M1403ContractName
from glio_proteogen.contracts.m14_03.schema import (
    contract_json_schema as m1403_contract_json_schema,
)
from glio_proteogen.contracts.m14_03.v1 import (
    M1403_MAX_CANONICAL_REQUEST_BYTES,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    ProteinSubtypeMechanisticFeatureResult,
)
from glio_proteogen.contracts.m14_05.schema import (
    ContractName as M1405ContractName,
)
from glio_proteogen.contracts.m14_05.schema import (
    contract_json_schema as m1405_contract_json_schema,
)
from glio_proteogen.contracts.m14_05.v1 import (
    M1405_MAX_CANONICAL_REQUEST_BYTES,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
)
from glio_proteogen.contracts.m15_02.schema import (
    ContractName as M1502ContractName,
)
from glio_proteogen.contracts.m15_02.schema import (
    contract_json_schema as m1502_contract_json_schema,
)
from glio_proteogen.contracts.m15_02.v1 import (
    M1502_MAX_CANONICAL_REQUEST_BYTES,
    LongitudinalRecurrenceContextStratificationResult,
    StratifyContextAndSubtypeRequest,
)
from glio_proteogen.contracts.m15_08.schema import (
    ContractName as M1508ContractName,
)
from glio_proteogen.contracts.m15_08.schema import (
    contract_json_schema as m1508_contract_json_schema,
)
from glio_proteogen.contracts.m15_08.v1 import (
    M1508_MAX_CANONICAL_REQUEST_BYTES,
    AssembleComplexActivityMechanismDossierRequest,
    ComplexActivityMechanismDossierResult,
)
from glio_proteogen.contracts.m16_03.schema import (
    ContractName as M1603ContractName,
)
from glio_proteogen.contracts.m16_03.schema import (
    contract_json_schema as m1603_contract_json_schema,
)
from glio_proteogen.contracts.m16_03.v1 import (
    M1603_MAX_CANONICAL_REQUEST_BYTES,
    FuseProteinRnaDiscordanceEvidenceRequest,
    ProteinRnaDiscordanceIntegratedEvidenceResult,
)
from glio_proteogen.contracts.m16_06.schema import (
    ContractName as M1606ContractName,
)
from glio_proteogen.contracts.m16_06.schema import (
    contract_json_schema as m1606_contract_json_schema,
)
from glio_proteogen.contracts.m16_06.v1 import (
    M1606_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteinRnaDiscordanceQueueRequest,
    ProteinRnaDiscordanceAdjudicationResult,
)
from glio_proteogen.contracts.m17_01.schema import (
    ContractName as M1701ContractName,
)
from glio_proteogen.contracts.m17_01.schema import (
    contract_json_schema as m1701_contract_json_schema,
)
from glio_proteogen.contracts.m17_01.v1 import (
    ResolveVariantPeptideUpstreamContractsRequest,
    VariantPeptideUpstreamResolutionResult,
)
from glio_proteogen.contracts.m17_04.schema import (
    ContractName as M1704ContractName,
)
from glio_proteogen.contracts.m17_04.schema import (
    contract_json_schema as m1704_contract_json_schema,
)
from glio_proteogen.contracts.m17_04.v1 import (
    AdaptVariantPeptideIntendedUseRequest,
    VariantPeptideIntendedUseAdapterResult,
)
from glio_proteogen.contracts.m17_08.schema import (
    ContractName as M1708ContractName,
)
from glio_proteogen.contracts.m17_08.schema import (
    contract_json_schema as m1708_contract_json_schema,
)
from glio_proteogen.contracts.m17_08.v1 import (
    M1708_MAX_CANONICAL_REQUEST_BYTES,
    MonitorVariantPeptideTranslationHealthRequest,
    VariantPeptideTranslationMonitoringResult,
)
from glio_proteogen.contracts.m18_03.schema import (
    ContractName as M1803ContractName,
)
from glio_proteogen.contracts.m18_03.schema import (
    contract_json_schema as m1803_contract_json_schema,
)
from glio_proteogen.contracts.m18_03.v1 import (
    M1803_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelIntegratedEvidenceResult,
    FuseBiomarkerPanelEvidenceRequest,
)
from glio_proteogen.contracts.m18_06.schema import (
    ContractName as M1806ContractName,
)
from glio_proteogen.contracts.m18_06.schema import (
    contract_json_schema as m1806_contract_json_schema,
)
from glio_proteogen.contracts.m18_06.v1 import (
    M1806_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateBiomarkerPanelQueueRequest,
    BiomarkerPanelAdjudicationResult,
)
from glio_proteogen.contracts.m18_08.schema import (
    ContractName as M1808ContractName,
)
from glio_proteogen.contracts.m18_08.schema import (
    contract_json_schema as m1808_contract_json_schema,
)
from glio_proteogen.contracts.m18_08.v1 import (
    M1808_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelTranslationMonitoringResult,
    MonitorBiomarkerPanelTranslationHealthRequest,
)
from glio_proteogen.contracts.m19_03.schema import (
    ContractName as M1903ContractName,
)
from glio_proteogen.contracts.m19_03.schema import (
    contract_json_schema as m1903_contract_json_schema,
)
from glio_proteogen.contracts.m19_03.v1 import (
    M1903_MAX_CANONICAL_REQUEST_BYTES,
    FuseProteotypeEvidenceRequest,
    ProteotypeIntegratedEvidenceResult,
)
from glio_proteogen.contracts.m19_04.schema import (
    ContractName as M1904ContractName,
)
from glio_proteogen.contracts.m19_04.schema import (
    contract_json_schema as m1904_contract_json_schema,
)
from glio_proteogen.contracts.m19_04.v1 import (
    M1904_MAX_CANONICAL_REQUEST_BYTES,
    AdaptProteotypeIntendedUseRequest,
    ProteotypeIntendedUseAdapterResult,
)
from glio_proteogen.contracts.m19_06.schema import (
    ContractName as M1906ContractName,
)
from glio_proteogen.contracts.m19_06.schema import (
    contract_json_schema as m1906_contract_json_schema,
)
from glio_proteogen.contracts.m19_06.v1 import (
    M1906_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteotypeQueueRequest,
    ProteotypeAdjudicationResult,
)
from glio_proteogen.contracts.m19_08.schema import (
    ContractName as M1908ContractName,
)
from glio_proteogen.contracts.m19_08.schema import (
    contract_json_schema as m1908_contract_json_schema,
)
from glio_proteogen.contracts.m19_08.v1 import (
    M1908_MAX_CANONICAL_REQUEST_BYTES,
    MonitorProteotypeTranslationHealthRequest,
    ProteotypeTranslationMonitoringResult,
)
from glio_proteogen.contracts.m20_01.schema import (
    ContractName as M2001ContractName,
)
from glio_proteogen.contracts.m20_01.schema import (
    contract_json_schema as m2001_contract_json_schema,
)
from glio_proteogen.contracts.m20_01.v1 import (
    M2001_MAX_CANONICAL_REQUEST_BYTES,
    M2001_MAX_CANONICAL_RESULT_BYTES,
    ProteinSubtypeUpstreamResolutionResult,
    ResolveProteinSubtypeUpstreamContractsRequest,
)
from glio_proteogen.contracts.m27_02.schema import (
    ContractName as M2702ContractName,
)
from glio_proteogen.contracts.m27_02.schema import (
    contract_json_schema as m2702_contract_json_schema,
)
from glio_proteogen.contracts.m27_02.v1 import (
    M2702_MAX_CANONICAL_REQUEST_BYTES,
    M2702_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityLineageResult,
    ResolveComplexActivityLineageRequest,
)
from glio_proteogen.kernel.models import Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainVerification,
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    ChainIntegrityError,
    ConsentAuthorizationError,
    IdempotencyConflictError,
    InvalidProtocolLookupError,
    M0101Service,
    PayloadTooLargeError,
    ProtocolNotFoundError,
    ProtocolSchemaValidationError,
    ProtocolVersionConflictError,
    UpstreamControlAuthorizationError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainIntegrityError as M0102ChainIntegrityError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainVerification as M0102ChainVerification,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    IdempotencyConflictError as M0102IdempotencyConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
    ResolutionNotFoundError,
    ResolutionSupersessionConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    PayloadTooLargeError as M0102PayloadTooLargeError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
    preflight_identity_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    IngestionLimits,
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.service import (
    M0105Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.engine import (
    HarmonizationAuthorizationError,
    preflight_harmonization_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.service import (
    M0106Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.engine import (
    SupportRoutingAuthorizationError,
    preflight_support_routing_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.service import (
    M0107Service,
)
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    ConformanceAuthorizationError,
    M0201ConformanceEvaluator,
    preflight_conformance_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    IdentityBindingAuthorizationError,
    M0202IdentityBindingEvaluator,
    preflight_identity_binding_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    IdentificationQualityAuthorizationError,
    M0204Service,
    preflight_identification_quality_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    IdentificationArtifactAuthorizationError,
    M0205Service,
    preflight_identification_artifact_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    IdentificationHarmonizationAuthorizationError,
    M0206Service,
    preflight_identification_harmonization_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    IdentificationSupportAuthorizationError,
    M0207Service,
    preflight_identification_support_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Service,
    ProteinInferenceProtocolAuthorizationError,
    preflight_protein_inference_protocol_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    M0302Service,
    ProteinIdentityLineageAuthorizationError,
    preflight_protein_identity_lineage_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    M0304Service,
    ProteinInferenceQualityAuthorizationError,
    preflight_protein_inference_quality_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Service,
    ProteinInferenceArtifactAuthorizationError,
    preflight_protein_inference_artifact_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    M0306Service,
    ProteinInferenceHarmonizationAuthorizationError,
    preflight_protein_inference_harmonization_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    M0307Service,
    ProteinInferenceSupportAuthorizationError,
    preflight_protein_inference_support_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Service,
    ProteoformProtocolAuthorizationError,
    preflight_proteoform_protocol_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    M0402Service,
    ProteoformIdentityLineageAuthorizationError,
    preflight_proteoform_identity_lineage_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    M0404Service,
    ProteoformQualityAuthorizationError,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics.engine import (
    _validate_json_request as _validate_m0404_json_request,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    M0405Service,
    ProteoformArtifactAuthorizationError,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection.engine import (
    _validate_json_request as _validate_m0405_json_request,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    M0406Service,
    ProteoformHarmonizationAuthorizationError,
    preflight_proteoform_harmonization_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization.engine import (
    _validate_json_request as _validate_m0406_json_request,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    M0407Service,
    ProteoformSupportAuthorizationError,
    preflight_proteoform_support_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router.engine import (
    _validate_json_request as _validate_m0407_json_request,
)
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    M0501Service,
    PtmLocalizationProtocolAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata.engine import (
    _validate_json_request as _validate_m0501_json_request,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    M0502Service,
    PtmLocalizationIdentityLineageAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage.engine import (
    _validate_json_request as _validate_m0502_json_request,
)
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics import (
    M0504Service,
    PtmLocalizationQualityAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics.engine import (
    _validate_json_request_capability as _validate_m0504_json_request_capability,
)
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    M0505Service,
    PtmLocalizationArtifactAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection.engine import (
    _validate_json_request as _validate_m0505_json_request,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Service,
    PtmLocalizationHarmonizationAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.engine import (
    _validate_json_request as _validate_m0506_json_request,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    M0507Service,
    PtmLocalizationSupportAuthorizationError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router.engine import (  # noqa: E501
    _validate_json_request as _validate_m0507_json_request,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.engine import (
    PtmBaselineAuthorizationError,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.engine import (
    _validate_json_request as _validate_m0603_json_request,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.service import (
    M0603Service,
)
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    FormalStateAuthorizationError,
    M0601Service,
    preflight_formal_state_authorization,
)
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604Service,
    ProbabilisticEstimatorAuthorizationError,
    preflight_probabilistic_estimator_authorization,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.engine import (
    M0606UncertaintyDecompositionAuthorizationError,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.engine import (
    _validate_json_request as _validate_m0606_json_request,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.service import (
    M0606Service,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state import (
    M0801Service,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state import (
    preflight_formal_state_authorization as preflight_m0801_authorization,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.engine import (
    M0801FormalStateAuthorizationError,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.engine import (
    _validate_json_request as _validate_m0801_json_request,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    M0803Service,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    preflight_baseline_authorization as preflight_m0803_authorization,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.engine import (
    M0803BaselineAuthorizationError,
)
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.engine import (
    _validate_json_request as _validate_m0803_json_request,
)
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity import (
    M1306AuthorizationError,
    M1306Service,
    preflight_m1306_authorization,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_03_mechanistic_feature_constructor as m1403_module,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_05_protein_subtype_evolution as m1405_module,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_02_context_subtype_stratifier as m1502_module,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_08_mechanism_evidence_dossier as m1508,
)
from glio_proteogen.modules.c16_kinophos_object_consumer import (
    M1606AuthorizationError,
    M1606Service,
    preflight_m1606_authorization,
)
from glio_proteogen.modules.c16_kinophos_object_consumer import (
    m16_03_fusion_aggregation_engine as m1603,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_01_upstream_contract_resolver as m1701_resolver,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_04_intended_use_adapter as m1704_adapter,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_08_translation_monitoring as m1708_monitoring,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_08_translation_monitoring_service as m1908_monitoring,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m20_01_upstream_contract_resolver as m2001_resolver,
)
from glio_proteogen.modules.c18_spatial_proteomics import (
    m18_08_translation_monitoring_service as m1808_monitoring,
)
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_03_fusion_aggregation as m1803_fusion,
)
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_06_reviewer_adjudication as m1806_adjudication,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence import (
    m19_06_reviewer_adjudication as m1906_adjudication,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_03_fusion_aggregation import (
    M1903AuthorizationError,
    M1903Service,
    preflight_m1903_authorization,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_04_intended_use_adapter import (
    M1904AuthorizationError,
    M1904ReplayError,
    M1904Service,
    preflight_m1904_authorization,
)
from glio_proteogen.modules.c20_biomarker_panel.m20_05_workflow_presentation_service import (
    api as m2005_adapter,
)
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import (
    M2702AuthorizationError,
    M2702ReplayError,
    M2702Service,
    preflight_m2702_authorization,
)

_REGISTER_ADAPTER: Final = TypeAdapter(RegisterProtocolRequest)
_EVALUATE_ADAPTER: Final = TypeAdapter(EvaluateMetadataRequest)
_RECONCILE_ADAPTER: Final = TypeAdapter(ReconcileIdentityLineageRequest)
_QUALITY_ADAPTER: Final = TypeAdapter(ComputeQualityMetricsRequest)
_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectArtifactsRequest)
_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeObservationsRequest)
_SUPPORT_ROUTING_ADAPTER: Final = TypeAdapter(RouteSupportRequest)
_M0201_CONFORMANCE_ADAPTER: Final = TypeAdapter(EvaluateConformanceRequest)
_M0202_BINDING_ADAPTER: Final = TypeAdapter(ValidateIdentityBindingsRequest)
_M0204_QUALITY_ADAPTER: Final = TypeAdapter(ComputeIdentificationQualityRequest)
_M0205_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectIdentificationArtifactsRequest)
_M0206_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeIdentificationEvidenceRequest)
_M0207_SUPPORT_ADAPTER: Final = TypeAdapter(RouteIdentificationSupportRequest)
_M0301_PROTOCOL_ADAPTER: Final = TypeAdapter(EvaluateProteinInferenceProtocolRequest)
_M0302_LINEAGE_ADAPTER: Final = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)
_M0304_QUALITY_ADAPTER: Final = TypeAdapter(ComputeProteinInferenceQualityRequest)
_M0304_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceQualityResult)
_M0305_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)
_M0305_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceArtifactDetectionResult)
_M0306_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeProteinInferenceSupportRequest)
_M0306_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceHarmonizationResult)
_M0307_SUPPORT_ADAPTER: Final = TypeAdapter(RouteProteinInferenceSupportRequest)
_M0307_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceSupportRouteResult)
_M0401_PROTOCOL_ADAPTER: Final = TypeAdapter(EvaluateProteoformProtocolRequest)
_M0402_LINEAGE_ADAPTER: Final = TypeAdapter(ReconcileProteoformIdentityLineageRequest)
_M0404_QUALITY_ADAPTER: Final = TypeAdapter(ComputeProteoformQualityMetricsRequest)
_M0601_FORMAL_STATE_ADAPTER: Final = TypeAdapter(ValidateFormalProteinStateRequest)
_M0603_BASELINE_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceBaselineRequest)
_M0604_PROBABILISTIC_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceProbabilisticRequest)
_M0606_UNCERTAINTY_ADAPTER: Final = TypeAdapter(DecomposeProteinAbundanceUncertaintyRequest)
_M0801_FORMAL_STATE_ADAPTER: Final = TypeAdapter(ValidateTranscriptProteinStateRequest)
_M0803_BASELINE_ADAPTER: Final = TypeAdapter(EstimateProteinSubtypeBaselineRequest)
_M0405_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectProteoformArtifactsRequest)
_M0501_PROTOCOL_ADAPTER: Final = TypeAdapter(EvaluatePtmLocalizationProtocolRequest)
_M0505_ARTIFACT_ADAPTER: Final = TypeAdapter(DetectPtmLocalizationArtifactsRequest)
_M0506_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizePtmLocalizationAnalysisRequest)
_M0507_SUPPORT_ADAPTER: Final = TypeAdapter(RoutePtmLocalizationSupportRequest)
_M2702_REQUEST_ADAPTER: Final = TypeAdapter(ResolveComplexActivityLineageRequest)
_M2702_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityLineageResult)
_M1908_REQUEST_ADAPTER: Final = TypeAdapter(MonitorProteotypeTranslationHealthRequest)
_M1906_ADJUDICATION_ADAPTER: Final = TypeAdapter(AdjudicateProteotypeQueueRequest)
_M1904_REQUEST_ADAPTER: Final = TypeAdapter(AdaptProteotypeIntendedUseRequest)
_M1904_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeIntendedUseAdapterResult)
_M1903_ADAPTER: Final = TypeAdapter(FuseProteotypeEvidenceRequest)
_M1903_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeIntegratedEvidenceResult)
_M1808_REQUEST_ADAPTER: Final = TypeAdapter(MonitorBiomarkerPanelTranslationHealthRequest)
_M1806_ADJUDICATION_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelQueueRequest)
_M1803_REQUEST_ADAPTER: Final = TypeAdapter(FuseBiomarkerPanelEvidenceRequest)
_M1701_REQUEST_ADAPTER: Final = TypeAdapter(ResolveVariantPeptideUpstreamContractsRequest)
_M2001_REQUEST_ADAPTER: Final = TypeAdapter(ResolveProteinSubtypeUpstreamContractsRequest)
_M2001_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeUpstreamResolutionResult)
_M1704_REQUEST_ADAPTER: Final = TypeAdapter(AdaptVariantPeptideIntendedUseRequest)
_M1708_REQUEST_ADAPTER: Final = TypeAdapter(MonitorVariantPeptideTranslationHealthRequest)
_M1606_QUEUE_ADAPTER: Final = TypeAdapter(AdjudicateProteinRnaDiscordanceQueueRequest)
_M1603_FUSION_ADAPTER: Final = TypeAdapter(FuseProteinRnaDiscordanceEvidenceRequest)
_M1508_DOSSIER_ADAPTER: Final = TypeAdapter(AssembleComplexActivityMechanismDossierRequest)
_M1502_ADAPTER: Final = TypeAdapter(StratifyContextAndSubtypeRequest)
_M1405_ADAPTER: Final = TypeAdapter(ModelProteinSubtypeLongitudinalEvolutionRequest)
_M1403_ADAPTER: Final = TypeAdapter(ConstructProteinSubtypeMechanisticFeaturesRequest)
_M1306_ADAPTER: Final = TypeAdapter(SimulateProteotypePerturbationRequest)
_M0406_HARMONIZATION_ADAPTER: Final = TypeAdapter(HarmonizeProteoformAnalysisRequest)
_M0407_SUPPORT_ADAPTER: Final = TypeAdapter(RouteProteoformSupportRequest)
_M0502_LINEAGE_ADAPTER: Final = TypeAdapter(ReconcilePtmLocalizationIdentityLineageRequest)
_M0504_QUALITY_ADAPTER: Final = TypeAdapter(ComputePtmLocalizationQualityMetricsRequest)
_RESOLUTION_DIGEST_ADAPTER: Final = TypeAdapter(Sha256Digest)
_IDENTIFIER_ADAPTER: Final = TypeAdapter(Identifier)
_MAX_ADVISORY_FILENAME_BYTES: Final = 512
_MAX_CHECKSUM_TEXT_LENGTH: Final = 80
_RAW_API_LIMITS: Final = IngestionLimits(
    max_source_bytes=MAX_REQUEST_BYTES,
    max_decoded_bytes=MAX_REQUEST_BYTES * 4,
)


def _contract_schema(name: M0101ContractName) -> dict[str, object]:
    """Retain the original M01-01 schema helper used by the CLI."""

    return m0101_contract_json_schema(name)


def _identity_contract_schema(name: M0102ContractName) -> dict[str, object]:
    return m0102_contract_json_schema(name)


def _raw_contract_schema(name: M0103ContractName) -> dict[str, object]:
    return m0103_contract_json_schema(name)


def _quality_contract_schema(name: M0104ContractName) -> dict[str, object]:
    return m0104_contract_json_schema(name)


def _artifact_contract_schema(name: M0105ContractName) -> dict[str, object]:
    return m0105_contract_json_schema(name)


def _harmonization_contract_schema(name: M0106ContractName) -> dict[str, object]:
    return m0106_contract_json_schema(name)


def _support_routing_contract_schema(name: M0107ContractName) -> dict[str, object]:
    return m0107_contract_json_schema(name)


def _release_packaging_contract_schema(name: M0108ContractName) -> dict[str, object]:
    return m0108_contract_json_schema(name)


def _identification_contract_schema(name: M0201ContractName) -> dict[str, object]:
    return m0201_contract_json_schema(name)


def _identity_binding_contract_schema(name: M0202ContractName) -> dict[str, object]:
    return m0202_contract_json_schema(name)


def _identification_raw_contract_schema(name: M0203ContractName) -> dict[str, object]:
    return m0203_contract_json_schema(name)


def _identification_quality_contract_schema(name: M0204ContractName) -> dict[str, object]:
    return m0204_contract_json_schema(name)


def _identification_artifact_contract_schema(name: M0205ContractName) -> dict[str, object]:
    return m0205_contract_json_schema(name)


def _identification_harmonization_contract_schema(
    name: M0206ContractName,
) -> dict[str, object]:
    return m0206_contract_json_schema(name)


def _identification_support_contract_schema(
    name: M0207ContractName,
) -> dict[str, object]:
    return m0207_contract_json_schema(name)


def _identification_release_contract_schema(
    name: M0208ContractName,
) -> dict[str, object]:
    return m0208_contract_json_schema(name)


def _protein_inference_protocol_contract_schema(
    name: M0301ContractName,
) -> dict[str, object]:
    return m0301_contract_json_schema(name)


def _protein_inference_lineage_contract_schema(
    name: M0302ContractName,
) -> dict[str, object]:
    return m0302_contract_json_schema(name)


def _protein_inference_raw_contract_schema(
    name: M0303ContractName,
) -> dict[str, object]:
    return m0303_contract_json_schema(name)


def _protein_inference_quality_contract_schema(
    name: M0304ContractName,
) -> dict[str, object]:
    return m0304_contract_json_schema(name)


def _protein_inference_artifact_contract_schema(
    name: M0305ContractName,
) -> dict[str, object]:
    return m0305_contract_json_schema(name)


def _protein_inference_harmonization_contract_schema(
    name: M0306ContractName,
) -> dict[str, object]:
    return m0306_contract_json_schema(name)


def _protein_inference_support_contract_schema(
    name: M0307ContractName,
) -> dict[str, object]:
    return m0307_contract_json_schema(name)


def _protein_inference_release_contract_schema(
    name: M0308ContractName,
) -> dict[str, object]:
    return m0308_contract_json_schema(name)


def _proteoform_protocol_contract_schema(
    name: M0401ContractName,
) -> dict[str, object]:
    return m0401_contract_json_schema(name)


def _proteoform_lineage_contract_schema(
    name: M0402ContractName,
) -> dict[str, object]:
    return m0402_contract_json_schema(name)


def _proteoform_raw_contract_schema(
    name: M0403ContractName,
) -> dict[str, object]:
    return m0403_contract_json_schema(name)


def _proteoform_quality_contract_schema(
    name: M0404ContractName,
) -> dict[str, object]:
    return m0404_contract_json_schema(name)


def _formal_state_contract_schema(name: M0601ContractName) -> dict[str, object]:
    return m0601_contract_json_schema(name)


def _m0603_baseline_contract_schema(name: M0603ContractName) -> dict[str, object]:
    return m0603_contract_json_schema(name)


def _probabilistic_estimator_contract_schema(
    name: M0604ContractName,
) -> dict[str, object]:
    return m0604_contract_json_schema(name)


def _m0606_uncertainty_contract_schema(
    name: M0606ContractName,
) -> dict[str, object]:
    return m0606_contract_json_schema(name)


def _m0801_contract_schema(name: M0801ContractName) -> dict[str, object]:
    return m0801_contract_json_schema(name)


def _m0803_contract_schema(name: M0803ContractName) -> dict[str, object]:
    return m0803_contract_json_schema(name)


def _ptm_localization_protocol_contract_schema(
    name: M0501ContractName,
) -> dict[str, object]:
    return m0501_contract_json_schema(name)


def _proteoform_artifact_contract_schema(
    name: M0405ContractName,
) -> dict[str, object]:
    return m0405_contract_json_schema(name)


def _m2702_contract_schema(name: M2702ContractName) -> dict[str, object]:
    return m2702_contract_json_schema(name)


def _m1908_contract_schema(name: M1908ContractName) -> dict[str, object]:
    return m1908_contract_json_schema(name)


def _m1908_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1908_contract_json_schema("request")}},
        }
    }


def _m1906_contract_schema(name: M1906ContractName) -> dict[str, object]:
    return m1906_contract_json_schema(name)


def _m1903_contract_schema(name: M1903ContractName) -> dict[str, object]:
    return m1903_contract_json_schema(name)


def _m1808_contract_schema(name: M1808ContractName) -> dict[str, object]:
    return m1808_contract_json_schema(name)


def _m1806_contract_schema(name: M1806ContractName) -> dict[str, object]:
    return m1806_contract_json_schema(name)


def _m1803_contract_schema(name: M1803ContractName) -> dict[str, object]:
    return m1803_contract_json_schema(name)


def _m1701_contract_schema(name: M1701ContractName) -> dict[str, object]:
    return m1701_contract_json_schema(name)


def _m2001_contract_schema(name: M2001ContractName) -> dict[str, object]:
    return m2001_contract_json_schema(name)


def _m2001_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m2001_contract_json_schema("request")}},
        }
    }


def _m1704_contract_schema(name: M1704ContractName) -> dict[str, object]:
    return m1704_contract_json_schema(name)


def _m1708_contract_schema(name: M1708ContractName) -> dict[str, object]:
    return m1708_contract_json_schema(name)


def _m1606_contract_schema(name: M1606ContractName) -> dict[str, object]:
    return m1606_contract_json_schema(name)


def _m1603_contract_schema(name: M1603ContractName) -> dict[str, object]:
    return m1603_contract_json_schema(name)


def _m1508_contract_schema(name: M1508ContractName) -> dict[str, object]:
    return m1508_contract_json_schema(name)


def _m1502_contract_schema(name: M1502ContractName) -> dict[str, object]:
    return m1502_contract_json_schema(name)


def _m1405_contract_schema(name: M1405ContractName) -> dict[str, object]:
    return m1405_contract_json_schema(name)


def _m1403_contract_schema(name: M1403ContractName) -> dict[str, object]:
    return m1403_contract_json_schema(name)


def _m1306_contract_schema(name: M1306ContractName) -> dict[str, object]:
    return m1306_contract_json_schema(name)


def _proteoform_harmonization_contract_schema(
    name: M0406ContractName,
) -> dict[str, object]:
    return m0406_contract_json_schema(name)


def _proteoform_support_contract_schema(
    name: M0407ContractName,
) -> dict[str, object]:
    return m0407_contract_json_schema(name)


def _proteoform_release_contract_schema(
    name: M0408ContractName,
) -> dict[str, object]:
    return m0408_contract_json_schema(name)


def _ptm_localization_lineage_contract_schema(
    name: M0502ContractName,
) -> dict[str, object]:
    return m0502_contract_json_schema(name)


def _ptm_localization_raw_contract_schema(
    name: M0503ContractName,
) -> dict[str, object]:
    return m0503_contract_json_schema(name)


def _ptm_localization_quality_contract_schema(
    name: M0504ContractName,
) -> dict[str, object]:
    return m0504_contract_json_schema(name)


def _ptm_localization_artifact_contract_schema(
    name: M0505ContractName,
) -> dict[str, object]:
    return m0505_contract_json_schema(name)


def _ptm_localization_harmonization_contract_schema(
    name: M0506ContractName,
) -> dict[str, object]:
    return m0506_contract_json_schema(name)


def _ptm_localization_support_contract_schema(
    name: M0507ContractName,
) -> dict[str, object]:
    return m0507_contract_json_schema(name)


def _request_body(name: M0101ContractName) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0101_contract_json_schema(name)}},
        }
    }


def _identity_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0102_contract_json_schema("request")}},
        }
    }


def _quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0104_contract_json_schema("request")}},
        }
    }


def _artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0105_contract_json_schema("request")}},
        }
    }


def _harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0106_contract_json_schema("request")}},
        }
    }


def _support_routing_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0107_contract_json_schema("request")}},
        }
    }


def _identification_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0201_contract_json_schema("request")}},
        }
    }


def _identity_binding_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0202_contract_json_schema("request")}},
        }
    }


def _identification_quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0204_contract_json_schema("request")}},
        }
    }


def _identification_artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0205_contract_json_schema("request")}},
        }
    }


def _identification_harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0206_contract_json_schema("request")}},
        }
    }


def _identification_support_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0207_contract_json_schema("request")}},
        }
    }


def _protein_inference_protocol_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0301_contract_json_schema("request")}},
        }
    }


def _protein_inference_lineage_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0302_contract_json_schema("request")}},
        }
    }


def _protein_inference_quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0304_contract_json_schema("request")}},
        }
    }


def _protein_inference_quality_result_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0304_contract_json_schema("output")}},
        }
    }


def _protein_inference_artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0305_contract_json_schema("request")}},
        }
    }


def _protein_inference_artifact_result_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0305_contract_json_schema("output")}},
        }
    }


def _protein_inference_harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0306_contract_json_schema("request")}},
        }
    }


def _protein_inference_harmonization_result_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0306_contract_json_schema("output")}},
        }
    }


def _protein_inference_support_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0307_contract_json_schema("request")}},
        }
    }


def _protein_inference_support_result_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0307_contract_json_schema("output")}},
        }
    }


def _proteoform_protocol_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0401_contract_json_schema("request")}},
        }
    }


def _proteoform_lineage_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0402_contract_json_schema("request")}},
        }
    }


def _proteoform_quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0404_contract_json_schema("request")}},
        }
    }


def _formal_state_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0601_contract_json_schema("request")}},
        }
    }


def _m0603_baseline_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0603_contract_json_schema("request")}},
        }
    }


def _probabilistic_estimator_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0604_contract_json_schema("request")}},
        }
    }


def _m0606_uncertainty_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0606_contract_json_schema("request")}},
        }
    }


def _m0801_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0801_contract_json_schema("request")}},
        }
    }


def _m0803_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0803_contract_json_schema("request")}},
        }
    }


def _ptm_localization_protocol_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0501_contract_json_schema("request")}},
        }
    }


def _proteoform_artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0405_contract_json_schema("request")}},
        }
    }


def _m2702_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m2702_contract_json_schema("request")}},
        }
    }


def _m1904_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1904_contract_json_schema("request")}},
        }
    }


def _m1903_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1903_contract_json_schema("request")}},
        }
    }


def _m1806_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1806_contract_json_schema("request")}},
        }
    }


def _m1803_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1803_contract_json_schema("request")}},
        }
    }


def _m1701_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1701_contract_json_schema("request")}},
        }
    }


def _m1704_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1704_contract_json_schema("request")}},
        }
    }


def _m1708_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1708_contract_json_schema("request")}},
        }
    }


def _m1606_queue_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1606_contract_json_schema("request")}},
        }
    }


def _m1502_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1502_contract_json_schema("request")}},
        }
    }


async def _m1606_queue_body(
    request: Request,
) -> AdjudicateProteinRnaDiscordanceQueueRequest:
    return await _strict_json_body(
        request,
        _M1606_QUEUE_ADAPTER,
        preflight_m1606_authorization,
        M1606_MAX_CANONICAL_REQUEST_BYTES,
    )


def _m1405_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1405_contract_json_schema("request")}},
        }
    }


def _m1403_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1403_contract_json_schema("request")}},
        }
    }


def _m1306_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1306_contract_json_schema("request")}},
        }
    }


def _proteoform_harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0406_contract_json_schema("request")}},
        }
    }


def _proteoform_support_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0407_contract_json_schema("request")}},
        }
    }


def _ptm_localization_lineage_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0502_contract_json_schema("request")}},
        }
    }


def _ptm_localization_quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0504_contract_json_schema("request")}},
        }
    }


def _ptm_localization_artifact_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0505_contract_json_schema("request")}},
        }
    }


def _ptm_localization_harmonization_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0506_contract_json_schema("request")}},
        }
    }


def _ptm_localization_support_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0507_contract_json_schema("request")}},
        }
    }


async def _strict_json_body[ModelT](
    request: Request,
    adapter: TypeAdapter[ModelT],
    preflight: Callable[[object], None] | None = None,
    max_bytes: int = MAX_REQUEST_BYTES,
    json_validator: Callable[[object, bytes], ModelT] | None = None,
) -> ModelT:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=max_bytes)
        if preflight is not None:
            preflight(decoded)
        return (
            json_validator(decoded, body)
            if json_validator is not None
            else adapter.validate_json(body, strict=True)
        )
    except StrictJsonError as error:
        details = [strict_json_error_detail(error, location_prefix=("body",))]
        raise RequestValidationError(details) from error
    except ValidationError as error:
        details = sanitized_validation_errors(error, location_prefix=("body",))
        raise RequestValidationError(details) from error
    except (TypeError, ValueError) as error:
        if json_validator is None:
            raise
        raise HTTPException(status_code=422, detail="strict request validation failed") from error


async def _register_body(request: Request) -> RegisterProtocolRequest:
    return await _strict_json_body(request, _REGISTER_ADAPTER)


async def _evaluate_body(request: Request) -> EvaluateMetadataRequest:
    return await _strict_json_body(request, _EVALUATE_ADAPTER)


async def _reconcile_body(request: Request) -> ReconcileIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _RECONCILE_ADAPTER,
        preflight_identity_authorization,
    )


async def _quality_body(request: Request) -> ComputeQualityMetricsRequest:
    return await _strict_json_body(request, _QUALITY_ADAPTER)


async def _artifact_body(request: Request) -> DetectArtifactsRequest:
    return await _strict_json_body(request, _ARTIFACT_ADAPTER)


async def _harmonization_body(request: Request) -> HarmonizeObservationsRequest:
    return await _strict_json_body(
        request,
        _HARMONIZATION_ADAPTER,
        preflight_harmonization_authorization,
    )


async def _support_routing_body(request: Request) -> RouteSupportRequest:
    return await _strict_json_body(
        request,
        _SUPPORT_ROUTING_ADAPTER,
        preflight_support_routing_authorization,
    )


async def _identification_body(request: Request) -> EvaluateConformanceRequest:
    return await _strict_json_body(
        request,
        _M0201_CONFORMANCE_ADAPTER,
        preflight_conformance_authorization,
    )


async def _identity_binding_body(request: Request) -> ValidateIdentityBindingsRequest:
    return await _strict_json_body(
        request,
        _M0202_BINDING_ADAPTER,
        preflight_identity_binding_authorization,
    )


async def _identification_quality_body(
    request: Request,
) -> ComputeIdentificationQualityRequest:
    return await _strict_json_body(
        request,
        _M0204_QUALITY_ADAPTER,
        preflight_identification_quality_authorization,
    )


async def _identification_artifact_body(
    request: Request,
) -> DetectIdentificationArtifactsRequest:
    return await _strict_json_body(
        request,
        _M0205_ARTIFACT_ADAPTER,
        preflight_identification_artifact_authorization,
    )


async def _identification_harmonization_body(
    request: Request,
) -> HarmonizeIdentificationEvidenceRequest:
    return await _strict_json_body(
        request,
        _M0206_HARMONIZATION_ADAPTER,
        preflight_identification_harmonization_authorization,
    )


async def _identification_support_body(
    request: Request,
) -> RouteIdentificationSupportRequest:
    return await _strict_json_body(
        request,
        _M0207_SUPPORT_ADAPTER,
        preflight_identification_support_authorization,
    )


async def _protein_inference_protocol_body(
    request: Request,
) -> EvaluateProteinInferenceProtocolRequest:
    return await _strict_json_body(
        request,
        _M0301_PROTOCOL_ADAPTER,
        preflight_protein_inference_protocol_authorization,
    )


async def _protein_inference_lineage_body(
    request: Request,
) -> ReconcileProteinInferenceIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _M0302_LINEAGE_ADAPTER,
        preflight_protein_identity_lineage_authorization,
    )


async def _protein_inference_quality_body(
    request: Request,
) -> ComputeProteinInferenceQualityRequest:
    return await _strict_json_body(
        request,
        _M0304_QUALITY_ADAPTER,
        preflight_protein_inference_quality_authorization,
        M0304_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_quality_result_body_parser(
    request: Request,
) -> ProteinInferenceQualityResult:
    return await _strict_json_body(
        request,
        _M0304_RESULT_ADAPTER,
        max_bytes=M0304_MAX_CANONICAL_RESULT_BYTES,
    )


async def _protein_inference_artifact_body(
    request: Request,
) -> DetectProteinInferenceArtifactsRequest:
    return await _strict_json_body(
        request,
        _M0305_ARTIFACT_ADAPTER,
        preflight_protein_inference_artifact_authorization,
        M0305_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_artifact_result_body_parser(
    request: Request,
) -> ProteinInferenceArtifactDetectionResult:
    return await _strict_json_body(
        request,
        _M0305_RESULT_ADAPTER,
        max_bytes=M0305_MAX_CANONICAL_RESULT_BYTES,
    )


async def _protein_inference_harmonization_body(
    request: Request,
) -> HarmonizeProteinInferenceSupportRequest:
    return await _strict_json_body(
        request,
        _M0306_HARMONIZATION_ADAPTER,
        preflight_protein_inference_harmonization_authorization,
        M0306_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_harmonization_result_body_parser(
    request: Request,
) -> ProteinInferenceHarmonizationResult:
    return await _strict_json_body(
        request,
        _M0306_RESULT_ADAPTER,
        max_bytes=M0306_MAX_CANONICAL_RESULT_BYTES,
    )


async def _protein_inference_support_body(
    request: Request,
) -> RouteProteinInferenceSupportRequest:
    return await _strict_json_body(
        request,
        _M0307_SUPPORT_ADAPTER,
        preflight_protein_inference_support_authorization,
        M0307_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _protein_inference_support_result_body_parser(
    request: Request,
) -> ProteinInferenceSupportRouteResult:
    return await _strict_json_body(
        request,
        _M0307_RESULT_ADAPTER,
        max_bytes=M0307_MAX_CANONICAL_RESULT_BYTES,
    )


async def _proteoform_protocol_body(
    request: Request,
) -> EvaluateProteoformProtocolRequest:
    return await _strict_json_body(
        request,
        _M0401_PROTOCOL_ADAPTER,
        preflight_proteoform_protocol_authorization,
        M0401_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _proteoform_lineage_body(
    request: Request,
) -> ReconcileProteoformIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _M0402_LINEAGE_ADAPTER,
        preflight_proteoform_identity_lineage_authorization,
        M0402_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1903_body(request: Request) -> FuseProteotypeEvidenceRequest:
    return await _strict_json_body(
        request,
        _M1903_ADAPTER,
        preflight_m1903_authorization,
        M1903_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1903_result_body(request: Request) -> ProteotypeIntegratedEvidenceResult:
    return await _strict_json_body(request, _M1903_RESULT_ADAPTER)


def _validate_m0404_json_request_for_api(
    candidate: object,
    serialized: bytes,
) -> ComputeProteoformQualityMetricsRequest:
    """Keep M04-04's sanitized legacy error envelope at the HTTP boundary."""

    try:
        return _validate_m0404_json_request(candidate, serialized)
    except ValidationError:
        # Preserve the shared boundary's sanitized structured validation envelope.
        # The generic ValueError guard below is reserved for hostile internal failures.
        raise
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="M04-04 request validation failed") from error


async def _proteoform_quality_body(
    request: Request,
) -> ComputeProteoformQualityMetricsRequest:
    return await _strict_json_body(
        request,
        _M0404_QUALITY_ADAPTER,
        None,
        M0404_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0404_json_request_for_api,
    )


async def _formal_state_body(request: Request) -> ValidateFormalProteinStateRequest:
    return await _strict_json_body(
        request,
        _M0601_FORMAL_STATE_ADAPTER,
        preflight_formal_state_authorization,
        M0601_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m0603_baseline_body(
    request: Request,
) -> EstimateProteinAbundanceBaselineRequest:
    return await _strict_json_body(
        request,
        _M0603_BASELINE_ADAPTER,
        None,
        M0603_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0603_json_request,
    )


async def _probabilistic_estimator_body(
    request: Request,
) -> EstimateProteinAbundanceProbabilisticRequest:
    return await _strict_json_body(
        request,
        _M0604_PROBABILISTIC_ADAPTER,
        preflight_probabilistic_estimator_authorization,
        M0604_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m0606_uncertainty_body(
    request: Request,
) -> DecomposeProteinAbundanceUncertaintyRequest:
    return await _strict_json_body(
        request,
        _M0606_UNCERTAINTY_ADAPTER,
        None,
        M0606_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0606_json_request,
    )


async def _m0801_body(request: Request) -> ValidateTranscriptProteinStateRequest:
    return await _strict_json_body(
        request,
        _M0801_FORMAL_STATE_ADAPTER,
        preflight_m0801_authorization,
        M0801_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0801_json_request,
    )


async def _m0803_body(request: Request) -> EstimateProteinSubtypeBaselineRequest:
    return await _strict_json_body(
        request,
        _M0803_BASELINE_ADAPTER,
        preflight_m0803_authorization,
        M0803_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0803_json_request,
    )


async def _proteoform_artifact_body(
    request: Request,
) -> DetectProteoformArtifactsRequest:
    return await _strict_json_body(
        request,
        _M0405_ARTIFACT_ADAPTER,
        None,
        M0405_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0405_json_request,
    )


async def _m1908_body(request: Request) -> MonitorProteotypeTranslationHealthRequest:
    return await _strict_json_body(
        request,
        _M1908_REQUEST_ADAPTER,
        m1908_monitoring.preflight_m1908_authorization,
        M1908_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1906_body(request: Request) -> AdjudicateProteotypeQueueRequest:
    return await _strict_json_body(
        request,
        _M1906_ADJUDICATION_ADAPTER,
        m1906_adjudication.preflight_m1906_authorization,
        M1906_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _ptm_localization_lineage_body(
    request: Request,
) -> ReconcilePtmLocalizationIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _M0502_LINEAGE_ADAPTER,
        None,
        M0502_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0502_json_request,
    )


async def _ptm_localization_artifact_body(
    request: Request,
) -> DetectPtmLocalizationArtifactsRequest:
    return await _strict_json_body(
        request,
        _M0505_ARTIFACT_ADAPTER,
        None,
        M0505_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0505_json_request,
    )


async def _ptm_localization_harmonization_body(
    request: Request,
) -> HarmonizePtmLocalizationAnalysisRequest:
    return await _strict_json_body(
        request,
        _M0506_HARMONIZATION_ADAPTER,
        None,
        M0506_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0506_json_request,
    )


async def _ptm_localization_support_body(
    request: Request,
) -> RoutePtmLocalizationSupportRequest:
    return await _strict_json_body(
        request,
        _M0507_SUPPORT_ADAPTER,
        None,
        M0507_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0507_json_request,
    )


async def _m1904_body(request: Request) -> AdaptProteotypeIntendedUseRequest:
    return await _strict_json_body(
        request,
        _M1904_REQUEST_ADAPTER,
        preflight_m1904_authorization,
        M1904_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1904_result_body(request: Request) -> ProteotypeIntendedUseAdapterResult:
    return await _strict_json_body(
        request,
        _M1904_RESULT_ADAPTER,
        max_bytes=M1904_MAX_CANONICAL_REQUEST_BYTES * 2,
    )


async def _m1808_body(
    request: Request,
) -> MonitorBiomarkerPanelTranslationHealthRequest:
    return await _strict_json_body(
        request,
        _M1808_REQUEST_ADAPTER,
        m1808_monitoring.preflight_m1808_authorization,
        M1808_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1806_body(request: Request) -> AdjudicateBiomarkerPanelQueueRequest:
    return await _strict_json_body(
        request,
        _M1806_ADJUDICATION_ADAPTER,
        m1806_adjudication.preflight_m1806_authorization,
        M1806_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1803_body(
    request: Request,
) -> FuseBiomarkerPanelEvidenceRequest:
    return await _strict_json_body(
        request,
        _M1803_REQUEST_ADAPTER,
        m1803_fusion.preflight_m1803_authorization,
        M1803_MAX_CANONICAL_REQUEST_BYTES,
    )


def _m1603_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1603_contract_json_schema("request")}},
        }
    }


def _m1508_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m1508_contract_json_schema("request")}},
        }
    }


async def _m1603_fusion_body(
    request: Request,
) -> FuseProteinRnaDiscordanceEvidenceRequest:
    return await _strict_json_body(
        request,
        _M1603_FUSION_ADAPTER,
        m1603.preflight_m1603_authorization,
        M1603_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1508_dossier_body(
    request: Request,
) -> AssembleComplexActivityMechanismDossierRequest:
    return await _strict_json_body(
        request,
        _M1508_DOSSIER_ADAPTER,
        m1508.preflight_m1508_authorization,
        M1508_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1502_body(request: Request) -> StratifyContextAndSubtypeRequest:
    return await _strict_json_body(
        request,
        _M1502_ADAPTER,
        m1502_module.preflight_m1502_authorization,
        M1502_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1405_body(
    request: Request,
) -> ModelProteinSubtypeLongitudinalEvolutionRequest:
    return await _strict_json_body(
        request,
        _M1405_ADAPTER,
        m1405_module.preflight_m1405_authorization,
        M1405_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1403_body(
    request: Request,
) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
    return await _strict_json_body(
        request,
        _M1403_ADAPTER,
        m1403_module.preflight_m1403_authorization,
        M1403_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1306_body(request: Request) -> SimulateProteotypePerturbationRequest:
    return await _strict_json_body(
        request,
        _M1306_ADAPTER,
        preflight_m1306_authorization,
        M1306_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m1701_body(
    request: Request,
) -> ResolveVariantPeptideUpstreamContractsRequest:
    return await _strict_json_body(
        request,
        _M1701_REQUEST_ADAPTER,
        m1701_resolver.preflight_m1701_authorization,
    )


async def _m2001_body(
    request: Request,
) -> ResolveProteinSubtypeUpstreamContractsRequest:
    return await _strict_json_body(
        request,
        _M2001_REQUEST_ADAPTER,
        m2001_resolver.preflight_m2001_authorization,
        M2001_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m2001_result_body(request: Request) -> ProteinSubtypeUpstreamResolutionResult:
    return await _strict_json_body(
        request,
        _M2001_RESULT_ADAPTER,
        max_bytes=M2001_MAX_CANONICAL_RESULT_BYTES,
    )


async def _m1704_body(
    request: Request,
) -> AdaptVariantPeptideIntendedUseRequest:
    return await _strict_json_body(
        request,
        _M1704_REQUEST_ADAPTER,
        m1704_adapter.preflight_m1704_authorization,
    )


async def _m1708_body(
    request: Request,
) -> MonitorVariantPeptideTranslationHealthRequest:
    return await _strict_json_body(
        request,
        _M1708_REQUEST_ADAPTER,
        m1708_monitoring.preflight_m1708_authorization,
        M1708_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m2702_request_body_dependency(
    request: Request,
) -> ResolveComplexActivityLineageRequest:
    return await _strict_json_body(
        request,
        _M2702_REQUEST_ADAPTER,
        preflight_m2702_authorization,
        M2702_MAX_CANONICAL_REQUEST_BYTES,
    )


async def _m2702_result_body_dependency(request: Request) -> ComplexActivityLineageResult:
    return await _strict_json_body(
        request,
        _M2702_RESULT_ADAPTER,
        None,
        M2702_MAX_CANONICAL_RESULT_BYTES,
    )


async def _proteoform_harmonization_body(
    request: Request,
) -> HarmonizeProteoformAnalysisRequest:
    return await _strict_json_body(
        request,
        _M0406_HARMONIZATION_ADAPTER,
        preflight_proteoform_harmonization_authorization,
        M0406_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0406_json_request,
    )


async def _ptm_localization_protocol_body(
    request: Request,
) -> EvaluatePtmLocalizationProtocolRequest:
    return await _strict_json_body(
        request,
        _M0501_PROTOCOL_ADAPTER,
        None,
        M0501_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0501_json_request,
    )


async def _ptm_localization_quality_body(
    request: Request,
) -> _ValidatedM0504RequestCapability:
    adapter = cast(
        "TypeAdapter[_ValidatedM0504RequestCapability]",
        _M0504_QUALITY_ADAPTER,
    )
    return await _strict_json_body(
        request,
        adapter,
        None,
        M0504_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0504_json_request_capability,
    )


async def _proteoform_support_body(
    request: Request,
) -> RouteProteoformSupportRequest:
    return await _strict_json_body(
        request,
        _M0407_SUPPORT_ADAPTER,
        preflight_proteoform_support_authorization,
        M0407_MAX_CANONICAL_REQUEST_BYTES,
        _validate_m0407_json_request,
    )


def create_app(database_path: Path) -> FastAPI:  # noqa: PLR0915 - central route composition.
    """Create an isolated API instance backed by one append-only event database."""

    store = M0101EventStore(database_path)
    service = M0101Service(store)
    identity_store = M0102EventStore(database_path)
    identity_service = M0102Service(identity_store)
    quality_service = M0104Service()
    artifact_service = M0105Service()
    harmonization_service = M0106Service()
    support_routing_service = M0107Service()
    identification_evaluator = M0201ConformanceEvaluator()
    identity_binding_evaluator = M0202IdentityBindingEvaluator()
    identification_quality_service = M0204Service()
    identification_artifact_service = M0205Service()
    identification_harmonization_service = M0206Service()
    identification_support_service = M0207Service()
    protein_inference_protocol_service = M0301Service()
    protein_inference_lineage_service = M0302Service()
    protein_inference_quality_service = M0304Service()
    protein_inference_artifact_service = M0305Service()
    protein_inference_harmonization_service = M0306Service()
    protein_inference_support_service = M0307Service()
    proteoform_protocol_service = M0401Service()
    proteoform_lineage_service = M0402Service()
    proteoform_quality_service = M0404Service()
    formal_state_service = M0601Service()
    m0603_service = M0603Service()
    probabilistic_estimator_service = M0604Service()
    m0606_service = M0606Service()
    m0801_service = M0801Service()
    m0803_service = M0803Service()
    proteoform_artifact_service = M0405Service()
    ptm_localization_protocol_service = M0501Service()
    m1908_service = m1908_monitoring.M1908Service()
    m1906_service = m1906_adjudication.M1906Service()
    m1904_service = M1904Service()
    m1903_service = M1903Service()
    m1808_service = m1808_monitoring.M1808Service()
    m1806_service = m1806_adjudication.M1806Service()
    m1803_service = m1803_fusion.M1803Service()
    m1606_queue_service = M1606Service()
    m1603_service = m1603.M1603Service()
    m1508_service = m1508.M1508Service()
    m1502_service = m1502_module.M1502Service()
    m1405_service = m1405_module.M1405Service()
    m1403_service = m1403_module.M1403Service()
    m1306_service = M1306Service()
    m1701_service = m1701_resolver.M1701Service()
    m2001_service = m2001_resolver.M2001Service()
    m1704_service = m1704_adapter.M1704Service()
    m1708_service = m1708_monitoring.M1708Service()
    m2702_service = M2702Service()
    proteoform_harmonization_service = M0406Service()
    proteoform_support_service = M0407Service()
    ptm_localization_lineage_service = M0502Service()
    ptm_localization_quality_service = M0504Service()
    ptm_localization_artifact_service = M0505Service()
    ptm_localization_harmonization_service = M0506Service()
    ptm_localization_support_service = M0507Service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        identity_service.close()
        service.close()

    app = FastAPI(
        title="GLIO-PROTEOGEN",
        version="0.1.0",
        description="Research-use-only preanalytic contracts and bounded evidence processing.",
        lifespan=lifespan,
    )
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=MAX_REQUEST_BYTES,
        result_max_bytes=M0305_MAX_CANONICAL_RESULT_BYTES,
    )
    # These provisional lanes ship strict standalone adapters as well as the
    # central API.  Include their routers here so a caller using the canonical
    # application does not silently lose an implemented module surface.
    for adapter in (
        m1901_adapter,
        m1902_adapter,
        m1905_adapter,
        m2002_adapter,
        m2003_adapter,
        m2004_adapter,
    ):
        # ``FastAPI.app.router`` is a Starlette ``Router`` rather than the
        # ``APIRouter`` accepted by ``include_router``. Passing it there
        # silently registers only an empty placeholder route. Reuse the
        # already-validated APIRoute objects so the canonical app exposes the
        # same strict handlers as each standalone adapter.
        app.router.routes.extend(
            route for route in adapter.app.routes if isinstance(route, APIRoute)
        )
    app.router.routes.extend(
        route for route in m2005_adapter.create_app().routes if isinstance(route, APIRoute)
    )

    @app.exception_handler(ProtocolNotFoundError)
    def not_found_handler(_request: Request, error: ProtocolNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ProtocolVersionConflictError)
    @app.exception_handler(IdempotencyConflictError)
    def conflict_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(PayloadTooLargeError)
    def payload_handler(_request: Request, error: PayloadTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(error)})

    @app.exception_handler(ConsentAuthorizationError)
    @app.exception_handler(UpstreamControlAuthorizationError)
    @app.exception_handler(SupportRoutingAuthorizationError)
    @app.exception_handler(ConformanceAuthorizationError)
    @app.exception_handler(IdentityBindingAuthorizationError)
    @app.exception_handler(IdentificationQualityAuthorizationError)
    @app.exception_handler(IdentificationArtifactAuthorizationError)
    @app.exception_handler(IdentificationHarmonizationAuthorizationError)
    @app.exception_handler(IdentificationSupportAuthorizationError)
    @app.exception_handler(ProteinInferenceProtocolAuthorizationError)
    @app.exception_handler(ProteinIdentityLineageAuthorizationError)
    @app.exception_handler(ProteinInferenceQualityAuthorizationError)
    @app.exception_handler(ProteinInferenceArtifactAuthorizationError)
    @app.exception_handler(ProteinInferenceHarmonizationAuthorizationError)
    @app.exception_handler(ProteinInferenceSupportAuthorizationError)
    @app.exception_handler(ProteoformProtocolAuthorizationError)
    @app.exception_handler(ProteoformIdentityLineageAuthorizationError)
    @app.exception_handler(ProteoformQualityAuthorizationError)
    @app.exception_handler(FormalStateAuthorizationError)
    @app.exception_handler(PtmBaselineAuthorizationError)
    @app.exception_handler(M0801FormalStateAuthorizationError)
    @app.exception_handler(M0803BaselineAuthorizationError)
    @app.exception_handler(ProbabilisticEstimatorAuthorizationError)
    @app.exception_handler(M0606UncertaintyDecompositionAuthorizationError)
    @app.exception_handler(PtmLocalizationProtocolAuthorizationError)
    @app.exception_handler(ProteoformArtifactAuthorizationError)
    @app.exception_handler(m1906_adjudication.M1906AuthorizationError)
    @app.exception_handler(M1904AuthorizationError)
    @app.exception_handler(M1903AuthorizationError)
    @app.exception_handler(m1908_monitoring.M1908AuthorizationError)
    @app.exception_handler(m1808_monitoring.M1808AuthorizationError)
    @app.exception_handler(m1806_adjudication.M1806AuthorizationError)
    @app.exception_handler(m1803_fusion.M1803AuthorizationError)
    @app.exception_handler(m1603.M1603AuthorizationError)
    @app.exception_handler(m1508.M1508AuthorizationError)
    @app.exception_handler(m1502_module.M1502AuthorizationError)
    @app.exception_handler(m1405_module.M1405AuthorizationError)
    @app.exception_handler(m1403_module.M1403AuthorizationError)
    @app.exception_handler(M1306AuthorizationError)
    @app.exception_handler(m1701_resolver.M1701AuthorizationError)
    @app.exception_handler(m2001_resolver.M2001AuthorizationError)
    @app.exception_handler(m1704_adapter.M1704AuthorizationError)
    @app.exception_handler(m1708_monitoring.M1708AuthorizationError)
    @app.exception_handler(M2702AuthorizationError)
    @app.exception_handler(ProteoformHarmonizationAuthorizationError)
    @app.exception_handler(ProteoformSupportAuthorizationError)
    @app.exception_handler(PtmLocalizationIdentityLineageAuthorizationError)
    @app.exception_handler(PtmLocalizationQualityAuthorizationError)
    @app.exception_handler(PtmLocalizationArtifactAuthorizationError)
    @app.exception_handler(PtmLocalizationHarmonizationAuthorizationError)
    @app.exception_handler(PtmLocalizationSupportAuthorizationError)
    def authorization_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(M1606AuthorizationError)
    def m1606_authorization_handler(
        _request: Request,
        error: M1606AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(InvalidProtocolLookupError)
    def lookup_input_handler(
        _request: Request,
        error: InvalidProtocolLookupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ProtocolSchemaValidationError)
    def schema_handler(
        _request: Request,
        error: ProtocolSchemaValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": str(error),
                "issues": [issue.model_dump(mode="json") for issue in error.issues],
            },
        )

    @app.exception_handler(ChainIntegrityError)
    def integrity_handler(_request: Request, error: ChainIntegrityError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(ResolutionNotFoundError)
    def identity_not_found_handler(
        _request: Request,
        error: ResolutionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(M0102IdempotencyConflictError)
    @app.exception_handler(ResolutionSupersessionConflictError)
    def identity_conflict_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(M0102PayloadTooLargeError)
    def identity_payload_handler(
        _request: Request,
        error: M0102PayloadTooLargeError,
    ) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(error)})

    @app.exception_handler(IdentityLineageAuthorizationError)
    def identity_authorization_handler(
        _request: Request,
        error: IdentityLineageAuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(HarmonizationAuthorizationError)
    def harmonization_authorization_handler(
        _request: Request,
        error: HarmonizationAuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(M0102ChainIntegrityError)
    @app.exception_handler(M0102EventStoreError)
    def identity_integrity_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/healthz", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "alive", "module": "GLIO-PROTEOGEN-M01-01"}

    @app.get("/readyz", response_model=ChainVerification, tags=["operations"])
    def readiness() -> ChainVerification:
        _require_valid_identity_chain(identity_service.verify_event_chain())
        return _require_valid_chain(service.verify_event_chain())

    @app.get("/v1/contracts/M01-01/{name}/schema", tags=["contracts"])
    def contract_schema(name: M0101ContractName) -> dict[str, object]:
        return _contract_schema(name)

    @app.get("/v1/contracts/M01-02/{name}/schema", tags=["contracts"])
    def identity_contract_schema(name: M0102ContractName) -> dict[str, object]:
        return _identity_contract_schema(name)

    @app.get("/v1/contracts/M01-03/{name}/schema", tags=["contracts"])
    def raw_contract_schema(name: M0103ContractName) -> dict[str, object]:
        return _raw_contract_schema(name)

    @app.get("/v1/contracts/M01-04/{name}/schema", tags=["contracts"])
    def quality_contract_schema(name: M0104ContractName) -> dict[str, object]:
        return _quality_contract_schema(name)

    @app.get("/v1/contracts/M01-05/{name}/schema", tags=["contracts"])
    def artifact_contract_schema(name: M0105ContractName) -> dict[str, object]:
        return _artifact_contract_schema(name)

    @app.get("/v1/contracts/M01-06/{name}/schema", tags=["contracts"])
    def harmonization_contract_schema(name: M0106ContractName) -> dict[str, object]:
        return _harmonization_contract_schema(name)

    @app.get("/v1/contracts/M01-07/{name}/schema", tags=["contracts"])
    def support_routing_contract_schema(name: M0107ContractName) -> dict[str, object]:
        return _support_routing_contract_schema(name)

    @app.get("/v1/contracts/M01-08/{name}/schema", tags=["contracts"])
    def release_packaging_contract_schema(name: M0108ContractName) -> dict[str, object]:
        return _release_packaging_contract_schema(name)

    @app.get("/v1/contracts/M02-01/{name}/schema", tags=["contracts"])
    def identification_contract_schema(name: M0201ContractName) -> dict[str, object]:
        return _identification_contract_schema(name)

    @app.post(
        "/v1/modules/M02-01/conformance",
        response_model=M0201ConformanceEvaluation,
        tags=["M02-01"],
        openapi_extra=_identification_request_body(),
    )
    def evaluate_identification_metadata(
        request: Annotated[EvaluateConformanceRequest, Depends(_identification_body)],
    ) -> M0201ConformanceEvaluation:
        return identification_evaluator.evaluate(request)

    @app.get("/v1/contracts/M02-02/{name}/schema", tags=["contracts"])
    def identity_binding_contract_schema(name: M0202ContractName) -> dict[str, object]:
        return _identity_binding_contract_schema(name)

    @app.get("/v1/contracts/M02-03/{name}/schema", tags=["contracts"])
    def identification_raw_contract_schema(name: M0203ContractName) -> dict[str, object]:
        return _identification_raw_contract_schema(name)

    @app.get("/v1/contracts/M02-04/{name}/schema", tags=["contracts"])
    def identification_quality_contract_schema(name: M0204ContractName) -> dict[str, object]:
        return _identification_quality_contract_schema(name)

    @app.get("/v1/contracts/M02-05/{name}/schema", tags=["contracts"])
    def identification_artifact_contract_schema(name: M0205ContractName) -> dict[str, object]:
        return _identification_artifact_contract_schema(name)

    @app.get("/v1/contracts/M02-06/{name}/schema", tags=["contracts"])
    def identification_harmonization_contract_schema(
        name: M0206ContractName,
    ) -> dict[str, object]:
        return _identification_harmonization_contract_schema(name)

    @app.get("/v1/contracts/M02-07/{name}/schema", tags=["contracts"])
    def identification_support_contract_schema(
        name: M0207ContractName,
    ) -> dict[str, object]:
        return _identification_support_contract_schema(name)

    @app.get("/v1/contracts/M02-08/{name}/schema", tags=["contracts"])
    def identification_release_contract_schema(
        name: M0208ContractName,
    ) -> dict[str, object]:
        return _identification_release_contract_schema(name)

    @app.get("/v1/contracts/M03-01/{name}/schema", tags=["contracts"])
    def protein_inference_protocol_contract_schema(
        name: M0301ContractName,
    ) -> dict[str, object]:
        return _protein_inference_protocol_contract_schema(name)

    @app.get("/v1/contracts/M03-02/{name}/schema", tags=["contracts"])
    def protein_inference_lineage_contract_schema(
        name: M0302ContractName,
    ) -> dict[str, object]:
        return _protein_inference_lineage_contract_schema(name)

    @app.get("/v1/contracts/M03-03/{name}/schema", tags=["contracts"])
    def protein_inference_raw_contract_schema(
        name: M0303ContractName,
    ) -> dict[str, object]:
        return _protein_inference_raw_contract_schema(name)

    @app.get("/v1/contracts/M03-04/{name}/schema", tags=["contracts"])
    def protein_inference_quality_contract_schema(
        name: M0304ContractName,
    ) -> dict[str, object]:
        return _protein_inference_quality_contract_schema(name)

    @app.get("/v1/contracts/M03-05/{name}/schema", tags=["contracts"])
    def protein_inference_artifact_contract_schema(
        name: M0305ContractName,
    ) -> dict[str, object]:
        return _protein_inference_artifact_contract_schema(name)

    @app.post(
        "/v1/modules/M03-05/artifacts",
        response_model=ProteinInferenceArtifactDetectionResult,
        tags=["M03-05"],
        openapi_extra=_protein_inference_artifact_request_body(),
    )
    def detect_protein_inference_artifacts(
        request: Annotated[
            DetectProteinInferenceArtifactsRequest,
            Depends(_protein_inference_artifact_body),
        ],
    ) -> ProteinInferenceArtifactDetectionResult:
        return protein_inference_artifact_service.execute(request)

    @app.post(
        "/v1/modules/M03-05/artifacts/verify",
        response_model=ProteinInferenceArtifactDetectionResult,
        tags=["M03-05"],
        openapi_extra=_protein_inference_artifact_result_body(),
    )
    def verify_protein_inference_artifacts(
        result: Annotated[
            ProteinInferenceArtifactDetectionResult,
            Depends(_protein_inference_artifact_result_body_parser),
        ],
    ) -> ProteinInferenceArtifactDetectionResult:
        return protein_inference_artifact_service.verify(result)

    @app.get("/v1/contracts/M03-06/{name}/schema", tags=["contracts"])
    def protein_inference_harmonization_contract_schema(
        name: M0306ContractName,
    ) -> dict[str, object]:
        return _protein_inference_harmonization_contract_schema(name)

    @app.post(
        "/v1/modules/M03-06/harmonization",
        response_model=ProteinInferenceHarmonizationResult,
        tags=["M03-06"],
        openapi_extra=_protein_inference_harmonization_request_body(),
    )
    def harmonize_protein_inference_support(
        request: Annotated[
            HarmonizeProteinInferenceSupportRequest,
            Depends(_protein_inference_harmonization_body),
        ],
    ) -> ProteinInferenceHarmonizationResult:
        return protein_inference_harmonization_service.execute(request)

    @app.post(
        "/v1/modules/M03-06/harmonization/verify",
        response_model=ProteinInferenceHarmonizationResult,
        tags=["M03-06"],
        openapi_extra=_protein_inference_harmonization_result_body(),
    )
    def verify_protein_inference_harmonization(
        result: Annotated[
            ProteinInferenceHarmonizationResult,
            Depends(_protein_inference_harmonization_result_body_parser),
        ],
    ) -> ProteinInferenceHarmonizationResult:
        return protein_inference_harmonization_service.verify(result)

    @app.get("/v1/contracts/M03-07/{name}/schema", tags=["contracts"])
    def protein_inference_support_contract_schema(
        name: M0307ContractName,
    ) -> dict[str, object]:
        return _protein_inference_support_contract_schema(name)

    @app.get("/v1/contracts/M03-08/{name}/schema", tags=["contracts"])
    def protein_inference_release_contract_schema(
        name: M0308ContractName,
    ) -> dict[str, object]:
        return _protein_inference_release_contract_schema(name)

    @app.get("/v1/contracts/M04-01/{name}/schema", tags=["contracts"])
    def proteoform_protocol_contract_schema(
        name: M0401ContractName,
    ) -> dict[str, object]:
        return _proteoform_protocol_contract_schema(name)

    @app.post(
        "/v1/modules/M04-01/protocol-conformance",
        response_model=ProteoformProtocolConformanceResult,
        tags=["M04-01"],
        openapi_extra=_proteoform_protocol_request_body(),
    )
    def evaluate_proteoform_protocol_conformance(
        request: Annotated[
            EvaluateProteoformProtocolRequest,
            Depends(_proteoform_protocol_body),
        ],
    ) -> ProteoformProtocolConformanceResult:
        return proteoform_protocol_service.execute(request)

    @app.get("/v1/contracts/M04-02/{name}/schema", tags=["contracts"])
    def proteoform_lineage_contract_schema(
        name: M0402ContractName,
    ) -> dict[str, object]:
        return _proteoform_lineage_contract_schema(name)

    @app.get("/v1/contracts/M04-03/{name}/schema", tags=["contracts"])
    def proteoform_raw_contract_schema(
        name: M0403ContractName,
    ) -> dict[str, object]:
        return _proteoform_raw_contract_schema(name)

    @app.get("/v1/contracts/M04-04/{name}/schema", tags=["contracts"])
    def proteoform_quality_contract_schema(
        name: M0404ContractName,
    ) -> dict[str, object]:
        return _proteoform_quality_contract_schema(name)

    @app.get("/v1/contracts/M04-05/{name}/schema", tags=["contracts"])
    def proteoform_artifact_contract_schema(
        name: M0405ContractName,
    ) -> dict[str, object]:
        return _proteoform_artifact_contract_schema(name)

    @app.get("/v1/contracts/M05-01/{name}/schema", tags=["contracts"])
    def ptm_localization_protocol_contract_schema(
        name: M0501ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_protocol_contract_schema(name)

    @app.post(
        "/v1/modules/M05-01/protocol-conformance",
        response_model=PtmLocalizationProtocolConformanceResult,
        tags=["M05-01"],
        openapi_extra=_ptm_localization_protocol_request_body(),
    )
    def evaluate_ptm_localization_protocol_conformance(
        request: Annotated[
            EvaluatePtmLocalizationProtocolRequest,
            Depends(_ptm_localization_protocol_body),
        ],
    ) -> PtmLocalizationProtocolConformanceResult:
        return ptm_localization_protocol_service._execute_validated(request)

    @app.get("/v1/contracts/M18-08/{name}/schema", tags=["contracts"])
    def m1808_contract_schema(name: M1808ContractName) -> dict[str, object]:
        return _m1808_contract_schema(name)

    @app.post(
        "/v1/modules/M18-08/translation-health",
        response_model=BiomarkerPanelTranslationMonitoringResult,
        tags=["M18-08"],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": m1808_contract_json_schema("request")}},
            }
        },
    )
    def monitor_m1808_translation_health(
        request: Annotated[
            MonitorBiomarkerPanelTranslationHealthRequest,
            Depends(_m1808_body),
        ],
    ) -> BiomarkerPanelTranslationMonitoringResult:
        return m1808_service.execute(request)

    @app.get("/v1/contracts/M18-06/{name}/schema", tags=["contracts"])
    def m1806_contract_schema(name: M1806ContractName) -> dict[str, object]:
        return _m1806_contract_schema(name)

    @app.post(
        "/v1/modules/M18-06/adjudication",
        response_model=BiomarkerPanelAdjudicationResult,
        tags=["M18-06"],
        openapi_extra=_m1806_request_body(),
    )
    def adjudicate_m1806_queue(
        request: Annotated[
            AdjudicateBiomarkerPanelQueueRequest,
            Depends(_m1806_body),
        ],
    ) -> BiomarkerPanelAdjudicationResult:
        return m1806_service.adjudicate(request)

    @app.get("/v1/contracts/M18-03/{name}/schema", tags=["contracts"])
    def m1803_contract_schema(name: M1803ContractName) -> dict[str, object]:
        return _m1803_contract_schema(name)

    @app.post(
        "/v1/modules/M18-03/fusion",
        response_model=BiomarkerPanelIntegratedEvidenceResult,
        tags=["M18-03"],
        openapi_extra=_m1803_request_body(),
    )
    def fuse_m1803_evidence(
        request: Annotated[
            FuseBiomarkerPanelEvidenceRequest,
            Depends(_m1803_body),
        ],
    ) -> BiomarkerPanelIntegratedEvidenceResult:
        return m1803_service.fuse(request)

    @app.get("/v1/contracts/M17-01/{name}/schema", tags=["contracts"])
    def m1701_contract_schema(name: M1701ContractName) -> dict[str, object]:
        return _m1701_contract_schema(name)

    @app.post(
        "/v1/modules/M17-01/upstream-contract-resolution",
        response_model=VariantPeptideUpstreamResolutionResult,
        tags=["M17-01"],
        openapi_extra=_m1701_request_body(),
    )
    def resolve_m1701_upstream_contracts(
        request: Annotated[
            ResolveVariantPeptideUpstreamContractsRequest,
            Depends(_m1701_body),
        ],
    ) -> VariantPeptideUpstreamResolutionResult:
        return m1701_service.resolve(request)

    @app.get("/v1/contracts/M20-01/{name}/schema", tags=["contracts"])
    def m2001_contract_schema(name: M2001ContractName) -> dict[str, object]:
        return _m2001_contract_schema(name)

    @app.post(
        "/v1/modules/M20-01/resolve",
        response_model=ProteinSubtypeUpstreamResolutionResult,
        tags=["M20-01"],
        openapi_extra=_m2001_request_body(),
    )
    def resolve_m2001_upstream_contracts(
        request: Annotated[
            ResolveProteinSubtypeUpstreamContractsRequest,
            Depends(_m2001_body),
        ],
    ) -> ProteinSubtypeUpstreamResolutionResult:
        return m2001_service.resolve(request)

    @app.post(
        "/v1/modules/M20-01/verify",
        response_model=ProteinSubtypeUpstreamResolutionResult,
        tags=["M20-01"],
    )
    def verify_m2001_upstream_contracts(
        result: Annotated[
            ProteinSubtypeUpstreamResolutionResult,
            Depends(_m2001_result_body),
        ],
    ) -> ProteinSubtypeUpstreamResolutionResult:
        return m2001_service.replay(result)

    @app.get("/v1/contracts/M17-04/{name}/schema", tags=["contracts"])
    def m1704_contract_schema(name: M1704ContractName) -> dict[str, object]:
        return _m1704_contract_schema(name)

    @app.post(
        "/v1/modules/M17-04/intended-use-adaptation",
        response_model=VariantPeptideIntendedUseAdapterResult,
        tags=["M17-04"],
        openapi_extra=_m1704_request_body(),
    )
    def adapt_m1704_intended_use(
        request: Annotated[
            AdaptVariantPeptideIntendedUseRequest,
            Depends(_m1704_body),
        ],
    ) -> VariantPeptideIntendedUseAdapterResult:
        return m1704_service.adapt(request)

    @app.get("/v1/contracts/M17-08/{name}/schema", tags=["contracts"])
    def m1708_contract_schema(name: M1708ContractName) -> dict[str, object]:
        return _m1708_contract_schema(name)

    @app.post(
        "/v1/modules/M17-08/translation-health",
        response_model=VariantPeptideTranslationMonitoringResult,
        tags=["M17-08"],
        openapi_extra=_m1708_request_body(),
    )
    def monitor_m1708_translation_health(
        request: Annotated[
            MonitorVariantPeptideTranslationHealthRequest,
            Depends(_m1708_body),
        ],
    ) -> VariantPeptideTranslationMonitoringResult:
        return m1708_service.monitor(request)

    @app.get("/v1/contracts/M16-06/{name}/schema", tags=["contracts"])
    def m1606_contract_schema(name: M1606ContractName) -> dict[str, object]:
        return _m1606_contract_schema(name)

    @app.post(
        "/v1/modules/M16-06/reviewer-discrepancy-adjudication",
        response_model=ProteinRnaDiscordanceAdjudicationResult,
        tags=["M16-06"],
        openapi_extra=_m1606_queue_request_body(),
    )
    def adjudicate_m1606_queue(
        request: Annotated[
            AdjudicateProteinRnaDiscordanceQueueRequest,
            Depends(_m1606_queue_body),
        ],
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        return m1606_queue_service.adjudicate(request)

    @app.get("/v1/contracts/M16-03/{name}/schema", tags=["contracts"])
    def m1603_contract_schema(name: M1603ContractName) -> dict[str, object]:
        return _m1603_contract_schema(name)

    @app.post(
        "/v1/modules/M16-03/fusion-aggregation",
        response_model=ProteinRnaDiscordanceIntegratedEvidenceResult,
        tags=["M16-03"],
        openapi_extra=_m1603_request_body(),
    )
    def fuse_m1603_evidence(
        request: Annotated[
            FuseProteinRnaDiscordanceEvidenceRequest,
            Depends(_m1603_fusion_body),
        ],
    ) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        return m1603_service.execute(request)

    @app.get("/v1/contracts/M15-08/{name}/schema", tags=["contracts"])
    def m1508_contract_schema(name: M1508ContractName) -> dict[str, object]:
        return _m1508_contract_schema(name)

    @app.post(
        "/v1/modules/M15-08/mechanism-evidence-dossier",
        response_model=ComplexActivityMechanismDossierResult,
        tags=["M15-08"],
        openapi_extra=_m1508_request_body(),
    )
    def assemble_m1508_dossier(
        request: Annotated[
            AssembleComplexActivityMechanismDossierRequest,
            Depends(_m1508_dossier_body),
        ],
    ) -> ComplexActivityMechanismDossierResult:
        return m1508_service.execute(request)

    @app.get("/v1/contracts/M15-02/{name}/schema", tags=["contracts"])
    def m1502_contract_schema(name: M1502ContractName) -> dict[str, object]:
        return _m1502_contract_schema(name)

    @app.post(
        "/v1/modules/M15-02/context-stratification",
        response_model=LongitudinalRecurrenceContextStratificationResult,
        tags=["M15-02"],
        openapi_extra=_m1502_request_body(),
    )
    def stratify_m1502_context(
        request: Annotated[
            StratifyContextAndSubtypeRequest,
            Depends(_m1502_body),
        ],
    ) -> LongitudinalRecurrenceContextStratificationResult:
        return m1502_service.execute(request)

    @app.post(
        "/v1/modules/M04-04/quality-metric-computation",
        response_model=ProteoformQualityResult,
        tags=["M04-04"],
        openapi_extra=_proteoform_quality_request_body(),
    )
    def compute_proteoform_quality(
        request: Annotated[
            ComputeProteoformQualityMetricsRequest,
            Depends(_proteoform_quality_body),
        ],
    ) -> ProteoformQualityResult:
        return proteoform_quality_service.execute(request)

    @app.get("/v1/contracts/M06-01/{name}/schema", tags=["contracts"])
    def formal_state_contract_schema(name: M0601ContractName) -> dict[str, object]:
        return _formal_state_contract_schema(name)

    @app.post(
        "/v1/modules/M06-01/formal-state-validation",
        response_model=ValidateFormalProteinStateResult,
        tags=["M06-01"],
        openapi_extra=_formal_state_request_body(),
    )
    def validate_formal_state(
        request: Annotated[
            ValidateFormalProteinStateRequest,
            Depends(_formal_state_body),
        ],
    ) -> ValidateFormalProteinStateResult:
        return formal_state_service.execute(request)

    @app.get("/v1/contracts/M06-03/{name}/schema", tags=["contracts"])
    def m0603_baseline_contract_schema(name: M0603ContractName) -> dict[str, object]:
        return _m0603_baseline_contract_schema(name)

    @app.post(
        "/v1/modules/M06-03/estimate",
        response_model=EstimateProteinAbundanceBaselineResult,
        tags=["M06-03"],
        openapi_extra=_m0603_baseline_request_body(),
    )
    def estimate_m0603_baseline(
        request: Annotated[
            EstimateProteinAbundanceBaselineRequest,
            Depends(_m0603_baseline_body),
        ],
    ) -> EstimateProteinAbundanceBaselineResult:
        return m0603_service._execute_validated(request)

    @app.get("/v1/contracts/M06-04/{name}/schema", tags=["contracts"])
    def probabilistic_estimator_contract_schema(name: M0604ContractName) -> dict[str, object]:
        return _probabilistic_estimator_contract_schema(name)

    @app.post(
        "/v1/modules/M06-04/probabilistic-estimation",
        response_model=EstimateProteinAbundanceProbabilisticResult,
        tags=["M06-04"],
        openapi_extra=_probabilistic_estimator_request_body(),
    )
    def estimate_probabilistic_abundance(
        request: Annotated[
            EstimateProteinAbundanceProbabilisticRequest,
            Depends(_probabilistic_estimator_body),
        ],
    ) -> EstimateProteinAbundanceProbabilisticResult:
        return probabilistic_estimator_service.estimate(request)

    @app.get("/v1/contracts/M06-06/{name}/schema", tags=["contracts"])
    def m0606_uncertainty_contract_schema(name: M0606ContractName) -> dict[str, object]:
        return _m0606_uncertainty_contract_schema(name)

    @app.post(
        "/v1/modules/M06-06/decompose",
        response_model=ProteinAbundanceUncertaintyDecompositionResult,
        tags=["M06-06"],
        openapi_extra=_m0606_uncertainty_request_body(),
    )
    def decompose_m0606_uncertainty(
        request: Annotated[
            DecomposeProteinAbundanceUncertaintyRequest,
            Depends(_m0606_uncertainty_body),
        ],
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        return m0606_service.execute(request)

    @app.get("/v1/contracts/M08-01/{name}/schema", tags=["contracts"])
    def m0801_contract_schema(name: M0801ContractName) -> dict[str, object]:
        return _m0801_contract_schema(name)

    @app.post(
        "/v1/modules/M08-01/formal-state-validation",
        response_model=ValidateTranscriptProteinStateResult,
        tags=["M08-01"],
        openapi_extra=_m0801_request_body(),
    )
    def validate_m0801_formal_state(
        request: Annotated[
            ValidateTranscriptProteinStateRequest,
            Depends(_m0801_body),
        ],
    ) -> ValidateTranscriptProteinStateResult:
        return m0801_service.execute(request)

    @app.get("/v1/contracts/M08-03/{name}/schema", tags=["contracts"])
    def m0803_contract_schema(name: M0803ContractName) -> dict[str, object]:
        return _m0803_contract_schema(name)

    @app.post(
        "/v1/modules/M08-03/baseline-estimate",
        response_model=ProteinSubtypeBaselineResult,
        tags=["M08-03"],
        openapi_extra=_m0803_request_body(),
    )
    def estimate_m0803_baseline(
        request: Annotated[
            EstimateProteinSubtypeBaselineRequest,
            Depends(_m0803_body),
        ],
    ) -> ProteinSubtypeBaselineResult:
        return m0803_service.execute(request)

    @app.get("/v1/contracts/M04-06/{name}/schema", tags=["contracts"])
    def proteoform_harmonization_contract_schema(
        name: M0406ContractName,
    ) -> dict[str, object]:
        return _proteoform_harmonization_contract_schema(name)

    @app.post(
        "/v1/modules/M04-06/harmonization",
        response_model=ProteoformHarmonizationResult,
        tags=["M04-06"],
        openapi_extra=_proteoform_harmonization_request_body(),
    )
    def harmonize_proteoform_analysis(
        request: Annotated[
            HarmonizeProteoformAnalysisRequest,
            Depends(_proteoform_harmonization_body),
        ],
    ) -> ProteoformHarmonizationResult:
        return proteoform_harmonization_service._execute_validated(request)

    @app.get("/v1/contracts/M04-07/{name}/schema", tags=["contracts"])
    def proteoform_support_contract_schema(
        name: M0407ContractName,
    ) -> dict[str, object]:
        return _proteoform_support_contract_schema(name)

    @app.post(
        "/v1/modules/M04-07/support-route",
        response_model=ProteoformSupportRouteResult,
        tags=["M04-07"],
        openapi_extra=_proteoform_support_request_body(),
    )
    def route_proteoform_support(
        request: Annotated[
            RouteProteoformSupportRequest,
            Depends(_proteoform_support_body),
        ],
    ) -> ProteoformSupportRouteResult:
        return proteoform_support_service._execute_validated(request)

    @app.get("/v1/contracts/M04-08/{name}/schema", tags=["contracts"])
    def proteoform_release_contract_schema(
        name: M0408ContractName,
    ) -> dict[str, object]:
        return _proteoform_release_contract_schema(name)

    @app.get("/v1/contracts/M05-02/{name}/schema", tags=["contracts"])
    def ptm_localization_lineage_contract_schema(
        name: M0502ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_lineage_contract_schema(name)

    @app.get("/v1/contracts/M05-03/{name}/schema", tags=["contracts"])
    def ptm_localization_raw_contract_schema(
        name: M0503ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_raw_contract_schema(name)

    @app.get("/v1/contracts/M05-04/{name}/schema", tags=["contracts"])
    def ptm_localization_quality_contract_schema(
        name: M0504ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_quality_contract_schema(name)

    @app.post(
        "/v1/modules/M05-04/quality-metric-computation",
        response_model=PtmLocalizationQualityResult,
        tags=["M05-04"],
        openapi_extra=_ptm_localization_quality_request_body(),
    )
    def compute_ptm_localization_quality(
        capability: Annotated[
            _ValidatedM0504RequestCapability,
            Depends(_ptm_localization_quality_body),
        ],
    ) -> PtmLocalizationQualityResult:
        return ptm_localization_quality_service._execute_validated(capability)

    @app.get("/v1/contracts/M05-05/{name}/schema", tags=["contracts"])
    def ptm_localization_artifact_contract_schema(
        name: M0505ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_artifact_contract_schema(name)

    @app.get("/v1/contracts/M05-06/{name}/schema", tags=["contracts"])
    def ptm_localization_harmonization_contract_schema(
        name: M0506ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_harmonization_contract_schema(name)

    @app.get("/v1/contracts/M05-07/{name}/schema", tags=["contracts"])
    def ptm_localization_support_contract_schema(
        name: M0507ContractName,
    ) -> dict[str, object]:
        return _ptm_localization_support_contract_schema(name)

    @app.post(
        "/v1/modules/M05-05/artifact-detection",
        response_model=PtmLocalizationArtifactDetectionResult,
        tags=["M05-05"],
        openapi_extra=_ptm_localization_artifact_request_body(),
    )
    def detect_ptm_localization_artifacts(
        request: Annotated[
            DetectPtmLocalizationArtifactsRequest,
            Depends(_ptm_localization_artifact_body),
        ],
    ) -> PtmLocalizationArtifactDetectionResult:
        return ptm_localization_artifact_service._execute_validated(request)

    @app.post(
        "/v1/modules/M05-06/harmonization",
        response_model=PtmLocalizationHarmonizationResult,
        tags=["M05-06"],
        openapi_extra=_ptm_localization_harmonization_request_body(),
    )
    def harmonize_ptm_localization_analysis(
        request: Annotated[
            HarmonizePtmLocalizationAnalysisRequest,
            Depends(_ptm_localization_harmonization_body),
        ],
    ) -> PtmLocalizationHarmonizationResult:
        return ptm_localization_harmonization_service._execute_validated(request)

    @app.post(
        "/v1/modules/M05-07/support-route",
        response_model=PtmLocalizationSupportRouteResult,
        tags=["M05-07"],
        openapi_extra=_ptm_localization_support_request_body(),
    )
    def route_ptm_localization_support(
        request: Annotated[
            RoutePtmLocalizationSupportRequest,
            Depends(_ptm_localization_support_body),
        ],
    ) -> PtmLocalizationSupportRouteResult:
        return ptm_localization_support_service._execute_validated(request)

    @app.post(
        "/v1/modules/M05-02/identity-lineage-reconciliation",
        response_model=PtmLocalizationIdentityLineageResolution,
        tags=["M05-02"],
        openapi_extra=_ptm_localization_lineage_request_body(),
    )
    def reconcile_ptm_localization_identity_lineage(
        request: Annotated[
            ReconcilePtmLocalizationIdentityLineageRequest,
            Depends(_ptm_localization_lineage_body),
        ],
    ) -> PtmLocalizationIdentityLineageResolution:
        return ptm_localization_lineage_service._execute_validated(request)

    @app.post(
        "/v1/modules/M04-05/artifact-detection",
        response_model=ProteoformArtifactDetectionResult,
        tags=["M04-05"],
        openapi_extra=_proteoform_artifact_request_body(),
    )
    def detect_proteoform_artifacts(
        request: Annotated[
            DetectProteoformArtifactsRequest,
            Depends(_proteoform_artifact_body),
        ],
    ) -> ProteoformArtifactDetectionResult:
        return proteoform_artifact_service._execute_validated(request)

    @app.get("/v1/contracts/M19-08/{name}/schema", tags=["contracts"])
    def m1908_contract_schema(name: M1908ContractName) -> dict[str, object]:
        return _m1908_contract_schema(name)

    @app.post(
        "/v1/modules/M19-08/translation-health",
        response_model=ProteotypeTranslationMonitoringResult,
        tags=["M19-08"],
        openapi_extra=_m1908_request_body(),
    )
    def monitor_m1908_translation_health(
        request: Annotated[
            MonitorProteotypeTranslationHealthRequest,
            Depends(_m1908_body),
        ],
    ) -> ProteotypeTranslationMonitoringResult:
        return m1908_service.execute(request)

    @app.get("/v1/contracts/M14-05/{name}/schema", tags=["contracts"])
    def m1405_contract_schema(name: M1405ContractName) -> dict[str, object]:
        return _m1405_contract_schema(name)

    @app.post(
        "/v1/modules/M14-05/longitudinal-evolution",
        response_model=ProteinSubtypeLongitudinalEvolutionResult,
        tags=["M14-05"],
        openapi_extra=_m1405_request_body(),
    )
    def infer_m1405_evolution(
        request: Annotated[
            ModelProteinSubtypeLongitudinalEvolutionRequest,
            Depends(_m1405_body),
        ],
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        return m1405_service.execute(request)

    @app.get("/v1/contracts/M14-03/{name}/schema", tags=["contracts"])
    def m1403_contract_schema(name: M1403ContractName) -> dict[str, object]:
        return _m1403_contract_schema(name)

    @app.post(
        "/v1/modules/M14-03/mechanistic-feature-construction",
        response_model=ProteinSubtypeMechanisticFeatureResult,
        tags=["M14-03"],
        openapi_extra=_m1403_request_body(),
    )
    def construct_m1403_features(
        request: Annotated[
            ConstructProteinSubtypeMechanisticFeaturesRequest,
            Depends(_m1403_body),
        ],
    ) -> ProteinSubtypeMechanisticFeatureResult:
        return m1403_service.execute(request)

    @app.get("/v1/contracts/M13-06/{name}/schema", tags=["contracts"])
    def m1306_contract_schema(name: M1306ContractName) -> dict[str, object]:
        return _m1306_contract_schema(name)

    @app.post(
        "/v1/modules/M13-06/perturbations",
        response_model=ProteotypePerturbationSensitivityResult,
        tags=["M13-06"],
        openapi_extra=_m1306_request_body(),
    )
    def simulate_m1306_perturbations(
        request: Annotated[
            SimulateProteotypePerturbationRequest,
            Depends(_m1306_body),
        ],
    ) -> ProteotypePerturbationSensitivityResult:
        return m1306_service.execute(request)

    @app.post(
        "/v1/modules/M04-02/identity-lineage-reconciliation",
        response_model=ProteoformIdentityLineageResolution,
        tags=["M04-02"],
        openapi_extra=_proteoform_lineage_request_body(),
    )
    def reconcile_proteoform_identity_lineage(
        request: Annotated[
            ReconcileProteoformIdentityLineageRequest,
            Depends(_proteoform_lineage_body),
        ],
    ) -> ProteoformIdentityLineageResolution:
        return proteoform_lineage_service.execute(request)

    @app.post(
        "/v1/modules/M03-07/support-route",
        response_model=ProteinInferenceSupportRouteResult,
        tags=["M03-07"],
        openapi_extra=_protein_inference_support_request_body(),
    )
    def route_protein_inference_support(
        request: Annotated[
            RouteProteinInferenceSupportRequest,
            Depends(_protein_inference_support_body),
        ],
    ) -> ProteinInferenceSupportRouteResult:
        return protein_inference_support_service.execute(request)

    @app.post(
        "/v1/modules/M03-07/support-route/verify",
        response_model=ProteinInferenceSupportRouteResult,
        tags=["M03-07"],
        openapi_extra=_protein_inference_support_result_body(),
    )
    def verify_protein_inference_support(
        result: Annotated[
            ProteinInferenceSupportRouteResult,
            Depends(_protein_inference_support_result_body_parser),
        ],
    ) -> ProteinInferenceSupportRouteResult:
        return protein_inference_support_service.verify(result)

    @app.post(
        "/v1/modules/M03-04/quality",
        response_model=ProteinInferenceQualityResult,
        tags=["M03-04"],
        openapi_extra=_protein_inference_quality_request_body(),
    )
    def compute_protein_inference_quality(
        request: Annotated[
            ComputeProteinInferenceQualityRequest,
            Depends(_protein_inference_quality_body),
        ],
    ) -> ProteinInferenceQualityResult:
        return protein_inference_quality_service.execute(request)

    @app.post(
        "/v1/modules/M03-04/quality/verify",
        response_model=ProteinInferenceQualityResult,
        tags=["M03-04"],
        openapi_extra=_protein_inference_quality_result_body(),
    )
    def verify_protein_inference_quality(
        result: Annotated[
            ProteinInferenceQualityResult,
            Depends(_protein_inference_quality_result_body_parser),
        ],
    ) -> ProteinInferenceQualityResult:
        return protein_inference_quality_service.verify(result)

    @app.post(
        "/v1/modules/M03-02/identity-lineage-reconciliation",
        response_model=ProteinInferenceIdentityLineageResolution,
        tags=["M03-02"],
        openapi_extra=_protein_inference_lineage_request_body(),
    )
    def reconcile_protein_inference_identity_lineage(
        request: Annotated[
            ReconcileProteinInferenceIdentityLineageRequest,
            Depends(_protein_inference_lineage_body),
        ],
    ) -> ProteinInferenceIdentityLineageResolution:
        return protein_inference_lineage_service.execute(request)

    @app.post(
        "/v1/modules/M03-01/protocol-conformance",
        response_model=ProteinInferenceProtocolConformanceResult,
        tags=["M03-01"],
        openapi_extra=_protein_inference_protocol_request_body(),
    )
    def evaluate_protein_inference_protocol_conformance(
        request: Annotated[
            EvaluateProteinInferenceProtocolRequest,
            Depends(_protein_inference_protocol_body),
        ],
    ) -> ProteinInferenceProtocolConformanceResult:
        return protein_inference_protocol_service.execute(request)

    @app.post(
        "/v1/modules/M02-07/support-route",
        response_model=IdentificationSupportRouteResult,
        tags=["M02-07"],
        openapi_extra=_identification_support_request_body(),
    )
    def route_identification_support(
        request: Annotated[
            RouteIdentificationSupportRequest,
            Depends(_identification_support_body),
        ],
    ) -> IdentificationSupportRouteResult:
        return identification_support_service.execute(request)

    @app.post(
        "/v1/modules/M02-06/harmonization",
        response_model=IdentificationHarmonizationResult,
        tags=["M02-06"],
        openapi_extra=_identification_harmonization_request_body(),
    )
    def harmonize_identification_evidence(
        request: Annotated[
            HarmonizeIdentificationEvidenceRequest,
            Depends(_identification_harmonization_body),
        ],
    ) -> IdentificationHarmonizationResult:
        return identification_harmonization_service.execute(request)

    @app.post(
        "/v1/modules/M02-05/artifacts",
        response_model=IdentificationArtifactDetectionResult,
        tags=["M02-05"],
        openapi_extra=_identification_artifact_request_body(),
    )
    def detect_identification_artifacts(
        request: Annotated[
            DetectIdentificationArtifactsRequest,
            Depends(_identification_artifact_body),
        ],
    ) -> IdentificationArtifactDetectionResult:
        return identification_artifact_service.execute(request)

    @app.post(
        "/v1/modules/M02-04/quality",
        response_model=IdentificationQualityProfile,
        tags=["M02-04"],
        openapi_extra=_identification_quality_request_body(),
    )
    def compute_identification_quality(
        request: Annotated[
            ComputeIdentificationQualityRequest,
            Depends(_identification_quality_body),
        ],
    ) -> IdentificationQualityProfile:
        return identification_quality_service.execute(request)

    @app.post(
        "/v1/modules/M02-02/audit-bindings",
        response_model=IdentityBindingEvaluation,
        tags=["M02-02"],
        openapi_extra=_identity_binding_request_body(),
    )
    def audit_identification_bindings(
        request: Annotated[ValidateIdentityBindingsRequest, Depends(_identity_binding_body)],
    ) -> IdentityBindingEvaluation:
        return identity_binding_evaluator.evaluate(request)

    @app.post(
        "/v1/modules/M01-07/route",
        response_model=SupportRoutingResult,
        tags=["M01-07"],
        openapi_extra=_support_routing_request_body(),
    )
    def route_support(
        request: Annotated[RouteSupportRequest, Depends(_support_routing_body)],
    ) -> SupportRoutingResult:
        return support_routing_service.execute(request)

    @app.post(
        "/v1/modules/M01-06/harmonize",
        response_model=HarmonizationResult,
        tags=["M01-06"],
        openapi_extra=_harmonization_request_body(),
    )
    def harmonize_observations(
        request: Annotated[HarmonizeObservationsRequest, Depends(_harmonization_body)],
    ) -> HarmonizationResult:
        return harmonization_service.execute(request)

    @app.post(
        "/v1/modules/M01-05/detect",
        response_model=ArtifactDetectionResult,
        tags=["M01-05"],
        openapi_extra=_artifact_request_body(),
    )
    def detect_artifacts(
        request: Annotated[DetectArtifactsRequest, Depends(_artifact_body)],
    ) -> ArtifactDetectionResult:
        return artifact_service.execute(request)

    @app.post(
        "/v1/modules/M01-04/quality",
        response_model=QualityProfile,
        tags=["M01-04"],
        openapi_extra=_quality_request_body(),
    )
    def compute_quality_metrics(
        request: Annotated[ComputeQualityMetricsRequest, Depends(_quality_body)],
    ) -> QualityProfile:
        return quality_service.execute(request)

    @app.post(
        "/v1/modules/M01-03/inspect",
        response_model=ValidatedRawInputDescriptor,
        tags=["M01-03"],
    )
    async def inspect_raw_input(
        request: Request,
        source_id: str,
        filename: str | None = None,
        expected_sha256: str | None = None,
    ) -> ValidatedRawInputDescriptor:
        """Inspect one bounded binary body without retaining or interpreting its records."""

        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type != "application/octet-stream":
            raise HTTPException(
                status_code=415,
                detail="content-type must be application/octet-stream",
            )
        if filename is not None and len(filename.encode("utf-8")) > _MAX_ADVISORY_FILENAME_BYTES:
            raise HTTPException(status_code=422, detail="filename is too long")
        if expected_sha256 is not None and len(expected_sha256) > _MAX_CHECKSUM_TEXT_LENGTH:
            raise HTTPException(status_code=422, detail="checksum is too long")
        try:
            validated_source_id = _IDENTIFIER_ADAPTER.validate_python(source_id, strict=True)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="source identifier is invalid") from error
        return parse_raw_input(
            await request.body(),
            source_id=validated_source_id,
            filename=filename,
            expected_sha256=expected_sha256,
            limits=_RAW_API_LIMITS,
        )

    @app.post(
        "/v1/modules/M01-01/protocols",
        response_model=ProtocolSchemaReceipt,
        tags=["M01-01"],
        openapi_extra=_request_body("register-request"),
    )
    def register_protocol(
        request: Annotated[RegisterProtocolRequest, Depends(_register_body)],
    ) -> ProtocolSchemaReceipt:
        return service.register(request)

    @app.post(
        "/v1/modules/M01-01/conformance",
        response_model=ConformanceProfile,
        tags=["M01-01"],
        openapi_extra=_request_body("evaluate-request"),
    )
    def evaluate_metadata(
        request: Annotated[EvaluateMetadataRequest, Depends(_evaluate_body)],
    ) -> ConformanceProfile:
        return service.evaluate(request)

    @app.get(
        "/v1/modules/M01-01/protocols/{schema_id}/{version}",
        response_model=ProtocolSchemaReceipt,
        tags=["M01-01"],
    )
    def get_protocol(
        schema_id: str,
        version: str,
    ) -> ProtocolSchemaReceipt:
        return service.get_protocol(schema_id, version)

    @app.get(
        "/v1/modules/M01-01/events/verify",
        response_model=ChainVerification,
        tags=["operations"],
    )
    def verify_events() -> ChainVerification:
        return _require_valid_chain(service.verify_event_chain())

    @app.post(
        "/v1/modules/M01-02/reconcile",
        response_model=IdentityLineageResolution,
        tags=["M01-02"],
        openapi_extra=_identity_request_body(),
    )
    def reconcile_identity_lineage(
        request: Annotated[ReconcileIdentityLineageRequest, Depends(_reconcile_body)],
    ) -> IdentityLineageResolution:
        return identity_service.execute(request)

    @app.get(
        "/v1/modules/M01-02/resolutions/{resolution_digest}",
        response_model=IdentityLineageResolution,
        tags=["M01-02"],
    )
    def get_identity_resolution(
        resolution_digest: str,
    ) -> IdentityLineageResolution:
        try:
            validated_digest = _RESOLUTION_DIGEST_ADAPTER.validate_python(
                resolution_digest,
                strict=True,
            )
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail="resolution digest is invalid",
            ) from error
        return identity_service.get_resolution(validated_digest)

    @app.get(
        "/v1/modules/M01-02/events/verify",
        response_model=M0102ChainVerification,
        tags=["operations"],
    )
    def verify_identity_events() -> M0102ChainVerification:
        return _require_valid_identity_chain(identity_service.verify_event_chain())

    @app.get("/v1/contracts/M19-06/{name}/schema", tags=["contracts"])
    def m1906_contract_schema(name: M1906ContractName) -> dict[str, object]:
        return _m1906_contract_schema(name)

    @app.post(
        "/v1/modules/M19-06/adjudication",
        response_model=ProteotypeAdjudicationResult,
        tags=["M19-06"],
    )
    def adjudicate_m1906(
        request: Annotated[AdjudicateProteotypeQueueRequest, Depends(_m1906_body)],
    ) -> ProteotypeAdjudicationResult:
        return m1906_service.adjudicate(request)

    @app.post(
        "/v1/modules/M19-06/adjudication/verify",
        response_model=ProteotypeAdjudicationResult,
        tags=["M19-06"],
    )
    async def verify_m1906(request: Request) -> ProteotypeAdjudicationResult:
        result = await _strict_json_body(
            request,
            TypeAdapter(ProteotypeAdjudicationResult),
            None,
            M1906_MAX_CANONICAL_REQUEST_BYTES * 2,
        )
        return m1906_service.replay(result)

    @app.get("/v1/contracts/M19-04/{name}/schema", tags=["contracts"])
    def m1904_contract_schema(name: M1904ContractName) -> dict[str, object]:
        return m1904_contract_json_schema(name)

    @app.post(
        "/v1/modules/M19-04/adapt",
        response_model=ProteotypeIntendedUseAdapterResult,
        tags=["M19-04"],
        openapi_extra=_m1904_request_body(),
    )
    def adapt_m1904_intended_use(
        request: Annotated[AdaptProteotypeIntendedUseRequest, Depends(_m1904_body)],
    ) -> ProteotypeIntendedUseAdapterResult:
        return m1904_service.adapt(request)

    @app.post(
        "/v1/modules/M19-04/verify",
        response_model=ProteotypeIntendedUseAdapterResult,
        tags=["M19-04"],
    )
    def verify_m1904_intended_use(
        result: Annotated[ProteotypeIntendedUseAdapterResult, Depends(_m1904_result_body)],
    ) -> ProteotypeIntendedUseAdapterResult:
        try:
            return m1904_service.replay(result)
        except M1904ReplayError as error:
            raise HTTPException(
                status_code=422,
                detail="M19-04 replay verification failed",
            ) from error

    @app.get("/v1/contracts/M19-03/{name}/schema", tags=["contracts"])
    def m1903_contract_schema(name: M1903ContractName) -> dict[str, object]:
        return _m1903_contract_schema(name)

    @app.post(
        "/v1/modules/M19-03/fusion",
        response_model=ProteotypeIntegratedEvidenceResult,
        tags=["M19-03"],
        openapi_extra=_m1903_request_body(),
    )
    def fuse_m1903_evidence(
        request: Annotated[FuseProteotypeEvidenceRequest, Depends(_m1903_body)],
    ) -> ProteotypeIntegratedEvidenceResult:
        return m1903_service.fuse(request)

    @app.post(
        "/v1/modules/M19-03/verify",
        response_model=ProteotypeIntegratedEvidenceResult,
        tags=["M19-03"],
    )
    def verify_m1903_evidence(
        result: Annotated[ProteotypeIntegratedEvidenceResult, Depends(_m1903_result_body)],
    ) -> ProteotypeIntegratedEvidenceResult:
        return m1903_service.replay(result)

    @app.get("/v1/contracts/M27-02/{name}/schema", tags=["contracts"])
    def m2702_contract_schema(name: M2702ContractName) -> dict[str, object]:
        return _m2702_contract_schema(name)

    @app.post(
        "/v1/modules/M27-02/lineage",
        response_model=ComplexActivityLineageResult,
        tags=["M27-02"],
        openapi_extra=_m2702_request_body(),
    )
    def resolve_m2702_lineage(
        request: Annotated[
            ResolveComplexActivityLineageRequest,
            Depends(_m2702_request_body_dependency),
        ],
    ) -> ComplexActivityLineageResult:
        return m2702_service.execute(request)

    @app.post(
        "/v1/modules/M27-02/verify",
        response_model=ComplexActivityLineageResult,
        tags=["M27-02"],
    )
    def verify_m2702_lineage(
        result: Annotated[ComplexActivityLineageResult, Depends(_m2702_result_body_dependency)],
    ) -> ComplexActivityLineageResult:
        try:
            return m2702_service.replay(result)
        except M2702ReplayError as error:
            raise HTTPException(
                status_code=422,
                detail="M27-02 replay verification failed",
            ) from error

    return app


def _require_valid_chain(verification: ChainVerification) -> ChainVerification:
    if not verification.valid:
        raise ChainIntegrityError(verification.reason or "event chain verification failed")
    return verification


def _require_valid_identity_chain(
    verification: M0102ChainVerification,
) -> M0102ChainVerification:
    if not verification.valid:
        raise M0102ChainIntegrityError(
            verification.reason or "identity event chain verification failed"
        )
    return verification
