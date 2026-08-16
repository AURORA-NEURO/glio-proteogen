"""Human-readable and automation-safe command-line interface."""

from __future__ import annotations

import ctypes
import json
import os
import stat
from ctypes import wintypes
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal, Never

import typer
import uvicorn
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.api import (
    _artifact_contract_schema,
    _contract_schema,
    _formal_state_contract_schema,
    _harmonization_contract_schema,
    _identification_artifact_contract_schema,
    _identification_contract_schema,
    _identification_harmonization_contract_schema,
    _identification_quality_contract_schema,
    _identification_raw_contract_schema,
    _identification_release_contract_schema,
    _identification_support_contract_schema,
    _identity_binding_contract_schema,
    _identity_contract_schema,
    _m0603_baseline_contract_schema,
    _m0606_uncertainty_contract_schema,
    _m0801_contract_schema,
    _m1306_contract_schema,
    _m1403_contract_schema,
    _m1405_contract_schema,
    _m1502_contract_schema,
    _probabilistic_estimator_contract_schema,
    _protein_inference_artifact_contract_schema,
    _protein_inference_harmonization_contract_schema,
    _protein_inference_lineage_contract_schema,
    _protein_inference_protocol_contract_schema,
    _protein_inference_quality_contract_schema,
    _protein_inference_raw_contract_schema,
    _protein_inference_release_contract_schema,
    _protein_inference_support_contract_schema,
    _proteoform_lineage_contract_schema,
    _proteoform_protocol_contract_schema,
    _proteoform_quality_contract_schema,
    _proteoform_raw_contract_schema,
    _quality_contract_schema,
    _raw_contract_schema,
    _release_packaging_contract_schema,
    _support_routing_contract_schema,
    create_app,
)
from glio_proteogen.adapters.limits import (
    MAX_REQUEST_BYTES,
    RequestBodyTooLargeError,
    read_bounded,
)
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    RegisterProtocolRequest,
)
from glio_proteogen.contracts.m01_02.v1 import ReconcileIdentityLineageRequest
from glio_proteogen.contracts.m01_04.v1 import ComputeQualityMetricsRequest
from glio_proteogen.contracts.m01_05.v1 import DetectArtifactsRequest
from glio_proteogen.contracts.m01_06.v1 import HarmonizeObservationsRequest
from glio_proteogen.contracts.m01_07.v1 import RouteSupportRequest
from glio_proteogen.contracts.m01_08.v1 import (
    BuildReleasePackageRequest,
    ReleaseDisposition,
    ReleasePackagingResult,
)
from glio_proteogen.contracts.m02_01.v1 import (
    ConformanceEvaluation as M0201ConformanceEvaluation,
)
from glio_proteogen.contracts.m02_01.v1 import EvaluateConformanceRequest
from glio_proteogen.contracts.m02_02.v1 import (
    IdentityBindingEvaluation,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.contracts.m02_03.v1 import (
    IdentificationRawIngestionResult,
    IngestIdentificationRawInputsRequest,
)
from glio_proteogen.contracts.m02_04.v1 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityProfile,
)
from glio_proteogen.contracts.m02_05.v1 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.contracts.m02_06.v1 import (
    HarmonizeIdentificationEvidenceRequest,
    IdentificationHarmonizationResult,
)
from glio_proteogen.contracts.m02_07.v1 import (
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)
from glio_proteogen.contracts.m02_08 import (
    BuildIdentificationQcReleaseRequest,
    IdentificationQcReleaseResult,
    IdentificationReleaseArtifactRole,
    IdentificationReleaseDisposition,
)
from glio_proteogen.contracts.m03_01.v1 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.contracts.m03_02.v1 import (
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
)
from glio_proteogen.contracts.m03_03 import (
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceRawAdmissionResult,
)
from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
)
from glio_proteogen.contracts.m03_05 import (
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.contracts.m03_06 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.contracts.m03_07 import (
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)
from glio_proteogen.contracts.m03_08 import (
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    BuildProteinInferenceReleaseRequest,
    ProteinInferenceReleaseArtifactRole,
    ProteinInferenceReleaseDisposition,
    ProteinInferenceReleaseResult,
)
from glio_proteogen.contracts.m04_01 import (
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteoformProtocolRequest,
)
from glio_proteogen.contracts.m04_02 import (
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.contracts.m04_03 import (
    M0403_MAX_CANONICAL_REQUEST_BYTES,
    M0403_MAX_DOCUMENT_BYTES,
    M0403_MAX_TOTAL_DOCUMENT_BYTES,
    IngestProteoformRawInputsRequest,
    ProteoformRawInputRole,
)
from glio_proteogen.contracts.m04_04 import (
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteoformQualityMetricsRequest,
)
from glio_proteogen.contracts.m06_01 import (
    M0601_MAX_CANONICAL_REQUEST_BYTES,
    ValidateFormalProteinStateRequest,
)
from glio_proteogen.contracts.m06_03 import (
    M0603_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceBaselineRequest,
)
from glio_proteogen.contracts.m06_04 import (
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceProbabilisticRequest,
)
from glio_proteogen.contracts.m06_06 import (
    M0606_MAX_CANONICAL_REQUEST_BYTES,
    DecomposeProteinAbundanceUncertaintyRequest,
)
from glio_proteogen.contracts.m08_01 import (
    M0801_MAX_CANONICAL_REQUEST_BYTES,
    ValidateTranscriptProteinStateRequest,
)
from glio_proteogen.contracts.m08_01 import ContractName as M0801ContractName
from glio_proteogen.contracts.m13_06 import (
    M1306_MAX_CANONICAL_REQUEST_BYTES,
    SimulateProteotypePerturbationRequest,
)
from glio_proteogen.contracts.m14_03 import (
    M1403_MAX_CANONICAL_REQUEST_BYTES,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
)
from glio_proteogen.contracts.m14_05 import (
    M1405_MAX_CANONICAL_REQUEST_BYTES,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
)
from glio_proteogen.contracts.m15_02 import (
    M1502_MAX_CANONICAL_REQUEST_BYTES,
    StratifyContextAndSubtypeRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    InvalidProtocolLookupError,
    M0101Service,
    M0101ServiceError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
    preflight_identity_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.service import (
    M0105Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.engine import (
    preflight_harmonization_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.service import (
    M0106Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.engine import (
    preflight_support_routing_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.service import (
    M0107Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging import (
    M0108Service,
    ReleasePackagingInputError,
    preflight_release_packaging_authorization,
    verify_release_package,
)
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
    preflight_conformance_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    evaluate_identity_bindings,
    preflight_identity_binding_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    IdentificationRawIngestionInputError,
    M0203Service,
    preflight_identification_raw_ingestion_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    M0204Service,
    preflight_identification_quality_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    M0205Service,
    preflight_identification_artifact_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    M0206Service,
    preflight_identification_harmonization_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    M0207Service,
    preflight_identification_support_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    IdentificationReleaseAuthorizationError,
    IdentificationReleaseInputError,
    M0208Service,
    preflight_identification_release_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Service,
    preflight_protein_inference_protocol_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    M0302Service,
    preflight_protein_identity_lineage_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    M0303Service,
    ProteinInferenceRawIngestionInputError,
    preflight_protein_inference_raw_ingestion_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    M0304Service,
    preflight_protein_inference_quality_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Service,
    preflight_protein_inference_artifact_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    M0306Service,
    preflight_protein_inference_harmonization_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    M0307Service,
    preflight_protein_inference_support_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    M0308Service,
    ProteinInferenceReleaseAuthorizationError,
    ProteinInferenceReleaseInputError,
    preflight_protein_inference_release_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Service,
    preflight_proteoform_protocol_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    M0402Service,
    preflight_proteoform_identity_lineage_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    M0403Service,
    ProteoformRawInputAuthorizationError,
    ProteoformRawInputError,
    preflight_proteoform_raw_input_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    M0404Service,
    ProteoformQualityAuthorizationError,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics.engine import (
    _validate_json_request as _validate_m0404_json_request,
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
    M0801FormalStateAuthorizationError,
    M0801Service,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.engine import (
    _validate_json_request as _validate_m0801_json_request,
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

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
protocol_app = typer.Typer(no_args_is_help=True, help="M01-01 protocol operations.")
app.add_typer(protocol_app, name="protocol")
identity_app = typer.Typer(no_args_is_help=True, help="M01-02 identity and lineage operations.")
app.add_typer(identity_app, name="identity")
raw_app = typer.Typer(no_args_is_help=True, help="M01-03 bounded raw-format ingestion.")
app.add_typer(raw_app, name="raw")
quality_app = typer.Typer(no_args_is_help=True, help="M01-04 deterministic quality metrics.")
app.add_typer(quality_app, name="quality")
artifact_app = typer.Typer(no_args_is_help=True, help="M01-05 deterministic artifact detection.")
app.add_typer(artifact_app, name="artifact")
harmonization_app = typer.Typer(
    no_args_is_help=True,
    help="M01-06 deterministic harmonization and normalization.",
)
app.add_typer(harmonization_app, name="harmonize")
support_routing_app = typer.Typer(
    no_args_is_help=True,
    help="M01-07 deterministic support and abstention routing.",
)
app.add_typer(support_routing_app, name="support")
release_packaging_app = typer.Typer(
    no_args_is_help=True,
    help="M01-08 deterministic provenance and release packaging.",
)
app.add_typer(release_packaging_app, name="release")
identification_app = typer.Typer(
    no_args_is_help=True,
    help="M02-01 peptide-identification protocol metadata conformance.",
)
app.add_typer(identification_app, name="identification")
binding_audit_app = typer.Typer(
    no_args_is_help=True,
    help="M02-02 peptide-identification identity-binding audit.",
)
app.add_typer(binding_audit_app, name="binding")
identification_raw_app = typer.Typer(
    no_args_is_help=True,
    help="M02-03 role-aware peptide-identification raw ingestion.",
)
app.add_typer(identification_raw_app, name="identification-raw")
identification_quality_app = typer.Typer(
    no_args_is_help=True,
    help="M02-04 deterministic peptide-identification quality metrics.",
)
app.add_typer(identification_quality_app, name="identification-quality")
identification_artifacts_app = typer.Typer(
    no_args_is_help=True,
    help="M02-05 deterministic peptide-identification artifact detection.",
)
app.add_typer(identification_artifacts_app, name="identification-artifacts")
identification_harmonization_app = typer.Typer(
    no_args_is_help=True,
    help="M02-06 peptide-identification harmonization and normalization.",
)
app.add_typer(identification_harmonization_app, name="identification-harmonization")
identification_support_app = typer.Typer(
    no_args_is_help=True,
    help="M02-07 joint-envelope peptide-identification support routing.",
)
app.add_typer(identification_support_app, name="identification-support")
identification_release_app = typer.Typer(
    no_args_is_help=True,
    help="M02-08 peptide-identification provenance and release packaging.",
)
app.add_typer(identification_release_app, name="identification-release")
protein_inference_protocol_app = typer.Typer(
    no_args_is_help=True,
    help="M03-01 protein-inference protocol conformance.",
)
app.add_typer(protein_inference_protocol_app, name="protein-inference-protocol")
protein_inference_lineage_app = typer.Typer(
    no_args_is_help=True,
    help="M03-02 protein-inference artifact identity-lineage reconciliation.",
)
app.add_typer(protein_inference_lineage_app, name="protein-inference-lineage")
protein_inference_raw_app = typer.Typer(
    no_args_is_help=True,
    help="M03-03 bounded protein-inference raw-source admission.",
)
app.add_typer(protein_inference_raw_app, name="protein-inference-raw")
protein_inference_quality_app = typer.Typer(
    no_args_is_help=True,
    help="M03-04 deterministic protein-inference evidence quality.",
)
app.add_typer(protein_inference_quality_app, name="protein-inference-quality")
protein_inference_artifacts_app = typer.Typer(
    no_args_is_help=True,
    help="M03-05 deterministic protein-inference artifact detection.",
)
app.add_typer(protein_inference_artifacts_app, name="protein-inference-artifacts")
protein_inference_harmonization_app = typer.Typer(
    no_args_is_help=True,
    help="M03-06 deterministic protein-inference support harmonization.",
)
app.add_typer(
    protein_inference_harmonization_app,
    name="protein-inference-harmonization",
)
protein_inference_support_app = typer.Typer(
    no_args_is_help=True,
    help="M03-07 deterministic protein-inference joint support routing.",
)
app.add_typer(protein_inference_support_app, name="protein-inference-support")
protein_inference_release_app = typer.Typer(
    no_args_is_help=True,
    help="M03-08 protein-inference provenance and release packaging.",
)
app.add_typer(protein_inference_release_app, name="protein-inference-release")
proteoform_protocol_app = typer.Typer(
    no_args_is_help=True,
    help="M04-01 proteoform/isoform protocol conformance.",
)
app.add_typer(proteoform_protocol_app, name="proteoform-protocol")
proteoform_lineage_app = typer.Typer(
    no_args_is_help=True,
    help="M04-02 proteoform artifact identity-lineage reconciliation.",
)
app.add_typer(proteoform_lineage_app, name="proteoform-lineage")
proteoform_raw_app = typer.Typer(
    no_args_is_help=True,
    help="M04-03 deterministic proteoform raw-manifest ingestion.",
)
app.add_typer(proteoform_raw_app, name="proteoform-raw")
proteoform_quality_app = typer.Typer(
    no_args_is_help=True,
    help="M04-04 deterministic aggregate proteoform quality metrics.",
)
app.add_typer(proteoform_quality_app, name="proteoform-quality")
m0801_app = typer.Typer(
    no_args_is_help=True,
    help="M08-01 provisional formal transcript-protein state validation.",
)
app.add_typer(m0801_app, name="transcript-protein-state")
formal_state_app = typer.Typer(
    no_args_is_help=True,
    help="M06-01 formal state and feature schema validation.",
)
app.add_typer(formal_state_app, name="formal-state")
m0603_baseline_app = typer.Typer(
    no_args_is_help=True,
    help="M06-03 provisional deterministic mature baseline estimation.",
)
app.add_typer(m0603_baseline_app, name="mature-baseline")
probabilistic_estimator_app = typer.Typer(
    no_args_is_help=True,
    help="M06-04 provisional probabilistic and advanced estimation.",
)
app.add_typer(probabilistic_estimator_app, name="probabilistic-estimator")
uncertainty_decomposition_app = typer.Typer(
    no_args_is_help=True,
    help="M06-06 provisional protein-abundance uncertainty decomposition.",
)
app.add_typer(uncertainty_decomposition_app, name="uncertainty-decomposition")
m1306_app = typer.Typer(
    no_args_is_help=True,
    help="M13-06 bounded variant-peptide perturbation sensitivity.",
)
app.add_typer(m1306_app, name="proteotype-sensitivity")
m1403_app = typer.Typer(
    no_args_is_help=True,
    help="M14-03 provisional caller-declared mechanistic feature construction.",
)
app.add_typer(m1403_app, name="mechanistic-features")
m1405_app = typer.Typer(
    no_args_is_help=True,
    help="M14-05 provisional longitudinal protein-subtype evolution.",
)
app.add_typer(m1405_app, name="longitudinal-evolution")
m1502_app = typer.Typer(
    no_args_is_help=True,
    help="M15-02 caller-declared context and subtype stratification.",
)
app.add_typer(m1502_app, name="context-stratifier")

_RESOLUTION_DIGEST_ADAPTER = TypeAdapter(Sha256Digest)
_IDENTIFICATION_RELEASE_STAGES = (
    (
        IdentificationReleaseArtifactRole.M02_01_CONFORMANCE,
        "GLIO-PROTEOGEN-M02-01",
        TypeAdapter(M0201ConformanceEvaluation),
    ),
    (
        IdentificationReleaseArtifactRole.M02_02_IDENTITY_LINEAGE,
        "GLIO-PROTEOGEN-M02-02",
        TypeAdapter(IdentityBindingEvaluation),
    ),
    (
        IdentificationReleaseArtifactRole.M02_03_RAW_INGESTION,
        "GLIO-PROTEOGEN-M02-03",
        TypeAdapter(IdentificationRawIngestionResult),
    ),
    (
        IdentificationReleaseArtifactRole.M02_04_QUALITY,
        "GLIO-PROTEOGEN-M02-04",
        TypeAdapter(IdentificationQualityProfile),
    ),
    (
        IdentificationReleaseArtifactRole.M02_05_ARTIFACT_DETECTION,
        "GLIO-PROTEOGEN-M02-05",
        TypeAdapter(IdentificationArtifactDetectionResult),
    ),
    (
        IdentificationReleaseArtifactRole.M02_06_HARMONIZATION,
        "GLIO-PROTEOGEN-M02-06",
        TypeAdapter(IdentificationHarmonizationResult),
    ),
    (
        IdentificationReleaseArtifactRole.M02_07_SUPPORT_ROUTE,
        "GLIO-PROTEOGEN-M02-07",
        TypeAdapter(IdentificationSupportRouteResult),
    ),
)
_PROTEIN_INFERENCE_RELEASE_STAGES = (
    (
        ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE,
        "GLIO-PROTEOGEN-M03-01",
        TypeAdapter(ProteinInferenceProtocolConformanceResult),
    ),
    (
        ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE,
        "GLIO-PROTEOGEN-M03-02",
        TypeAdapter(ProteinInferenceIdentityLineageResolution),
    ),
    (
        ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION,
        "GLIO-PROTEOGEN-M03-03",
        TypeAdapter(ProteinInferenceRawAdmissionResult),
    ),
    (
        ProteinInferenceReleaseArtifactRole.M03_04_QUALITY,
        "GLIO-PROTEOGEN-M03-04",
        TypeAdapter(ProteinInferenceQualityResult),
    ),
    (
        ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION,
        "GLIO-PROTEOGEN-M03-05",
        TypeAdapter(ProteinInferenceArtifactDetectionResult),
    ),
    (
        ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION,
        "GLIO-PROTEOGEN-M03-06",
        TypeAdapter(ProteinInferenceHarmonizationResult),
    ),
    (
        ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE,
        "GLIO-PROTEOGEN-M03-07",
        TypeAdapter(ProteinInferenceSupportRouteResult),
    ),
)

DatabaseOption = Annotated[
    Path,
    typer.Option("--database", "-d", help="Append-only SQLite event database."),
]
RequestArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
]
SourceDirectoryArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
]
OutputOption = Annotated[
    Path,
    typer.Option("--output", "-o", help="New canonical USTAR package path."),
]
UncheckedSourceDirectoryArgument = Annotated[
    Path,
    typer.Argument(file_okay=False, help="Closed directory containing declared artifacts."),
]
ProteoformRawSourceArgument = Annotated[
    str,
    typer.Argument(help="Unchecked directory containing four locked manifest files."),
]
ProteoformRawOutputOption = Annotated[
    str,
    typer.Option("--output", "-o", help="New M04-03 canonical result JSON path."),
]
ProteoformQualityOutputOption = Annotated[
    str,
    typer.Option("--output", "-o", help="New M04-04 canonical result JSON path."),
]
M0801OutputOption = Annotated[
    str,
    typer.Option("--output", "-o", help="New M08-01 canonical result JSON path."),
]
M0603BaselineOutputOption = Annotated[
    str,
    typer.Option("--output", "-o", help="New M06-03 canonical result JSON path."),
]
M0606UncertaintyOutputOption = Annotated[
    str,
    typer.Option("--output", "-o", help="New M06-06 canonical result JSON path."),
]
UncheckedPackageArgument = Annotated[
    Path,
    typer.Argument(file_okay=True, dir_okay=False, help="Canonical USTAR package."),
]


class _ReleaseFileError(ValueError):
    """A CLI filesystem boundary could not be read or written safely."""

    @classmethod
    def source_not_directory(cls) -> _ReleaseFileError:
        return cls("source is not a directory")

    @classmethod
    def symlink_source(cls) -> _ReleaseFileError:
        return cls("artifact source cannot traverse a symbolic link")

    @classmethod
    def non_regular_source(cls) -> _ReleaseFileError:
        return cls("artifact source must be a regular file below source")

    @classmethod
    def source_size_mismatch(cls) -> _ReleaseFileError:
        return cls("artifact source size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _ReleaseFileError:
        return cls("artifact source closure is unavailable")

    @classmethod
    def package_unavailable(cls) -> _ReleaseFileError:
        return cls("package is unavailable")

    @classmethod
    def package_size_mismatch(cls) -> _ReleaseFileError:
        return cls("package size contradicts its descriptor")

    @classmethod
    def output_unavailable(cls) -> _ReleaseFileError:
        return cls("package output must be a new writable file")


class _IdentificationRawFileError(ValueError):
    """A declared M02-03 source cannot be read through the safe directory boundary."""

    @classmethod
    def source_not_directory(cls) -> _IdentificationRawFileError:
        return cls("source directory is unavailable")

    @classmethod
    def symlink_source(cls) -> _IdentificationRawFileError:
        return cls("raw source cannot traverse a symbolic link")

    @classmethod
    def invalid_source_name(cls) -> _IdentificationRawFileError:
        return cls("raw source identifier is not a safe filename")

    @classmethod
    def non_regular_source(cls) -> _IdentificationRawFileError:
        return cls("raw source must be a regular file below source directory")

    @classmethod
    def source_size_mismatch(cls) -> _IdentificationRawFileError:
        return cls("raw source size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _IdentificationRawFileError:
        return cls("raw source is unavailable")


class _ProteinInferenceRawFileError(ValueError):
    """A declared M03-03 source violates the directory-backed CLI boundary."""

    @classmethod
    def source_not_directory(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference source directory is unavailable")

    @classmethod
    def linked_or_reparse_source(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source cannot be a link or reparse point")

    @classmethod
    def invalid_source_name(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference source identifier is not a safe filename")

    @classmethod
    def non_regular_source(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source must be a regular file")

    @classmethod
    def source_changed(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source changed during admission")

    @classmethod
    def source_size_mismatch(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _ProteinInferenceRawFileError:
        return cls("protein-inference raw source is unavailable")


class _ProteoformRawFileError(ValueError):
    """An M04-03 CLI path violates the exact snapshot-once filesystem boundary."""

    @classmethod
    def source_not_directory(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw source directory is unavailable")

    @classmethod
    def linked_or_reparse_source(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw source cannot be a link or reparse point")

    @classmethod
    def unexpected_entry(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw source must contain exactly four locked filenames")

    @classmethod
    def non_regular_source(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw source must contain only regular files")

    @classmethod
    def source_changed(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw source changed during ingestion")

    @classmethod
    def source_unavailable(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw source is unavailable")

    @classmethod
    def output_unavailable(cls) -> _ProteoformRawFileError:
        return cls("proteoform raw output must be a new regular file")


class _IdentificationReleaseFileError(ValueError):
    """A CLI path violates the closed M02-08 file or archive boundary."""

    @classmethod
    def source_not_directory(cls) -> _IdentificationReleaseFileError:
        return cls("release source directory is unavailable")

    @classmethod
    def linked_source(cls) -> _IdentificationReleaseFileError:
        return cls("release source cannot contain symbolic links or junctions")

    @classmethod
    def unexpected_entry(cls) -> _IdentificationReleaseFileError:
        return cls("release source must contain exactly the declared artifact paths")

    @classmethod
    def non_regular_source(cls) -> _IdentificationReleaseFileError:
        return cls("release artifacts must be regular files")

    @classmethod
    def source_size_mismatch(cls) -> _IdentificationReleaseFileError:
        return cls("release artifact size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _IdentificationReleaseFileError:
        return cls("release artifact source is unavailable")

    @classmethod
    def stage_invalid(cls) -> _IdentificationReleaseFileError:
        return cls("release stage artifact is not its exact strict result contract")

    @classmethod
    def package_unavailable(cls) -> _IdentificationReleaseFileError:
        return cls("identification release package is unavailable")

    @classmethod
    def package_size_mismatch(cls) -> _IdentificationReleaseFileError:
        return cls("identification release package size contradicts its descriptor")

    @classmethod
    def output_unavailable(cls) -> _IdentificationReleaseFileError:
        return cls("identification release output must be a new writable file")


class _ProteinInferenceReleaseFileError(ValueError):
    """An M03-08 CLI path violates the closed binary-safe filesystem boundary."""

    @classmethod
    def source_not_directory(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release source directory is unavailable")

    @classmethod
    def linked_source(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release source cannot contain links or reparse points")

    @classmethod
    def unexpected_entry(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release source must contain exactly declared paths")

    @classmethod
    def non_regular_source(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release artifacts must be regular files")

    @classmethod
    def source_changed(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release artifact changed during admission")

    @classmethod
    def source_size_mismatch(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release artifact size contradicts its declaration")

    @classmethod
    def source_unavailable(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release artifact source is unavailable")

    @classmethod
    def stage_invalid(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release stage is not its exact strict result contract")

    @classmethod
    def package_unavailable(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release package is unavailable")

    @classmethod
    def package_size_mismatch(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release package size contradicts its descriptor")

    @classmethod
    def package_changed(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release package changed during verification admission")

    @classmethod
    def output_unavailable(cls) -> _ProteinInferenceReleaseFileError:
        return cls("protein-inference release output must be a new unlinked writable file")


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


def _load_request[RequestT](  # noqa: C901, PLR0912 - one sanitized boundary normalizes all CLI failures.
    path: Path,
    adapter: TypeAdapter[RequestT],
    preflight: Callable[[object], None] | None = None,
    max_bytes: int = MAX_REQUEST_BYTES,
    json_validator: Callable[[object, bytes], RequestT] | None = None,
) -> RequestT:
    try:
        payload = (
            read_bounded(path)
            if max_bytes == MAX_REQUEST_BYTES
            else read_bounded(path, max_bytes=max_bytes)
        )
        decoded = strict_json_loads(payload, max_bytes=max_bytes)
        if preflight is not None:
            preflight(decoded)
        return (
            json_validator(decoded, payload)
            if json_validator is not None
            else adapter.validate_json(payload, strict=True)
        )
    except RequestBodyTooLargeError as error:
        typer.echo(f"invalid request: {error}", err=True)
        raise typer.Exit(code=2) from error
    except StrictJsonError as error:
        typer.echo(f"invalid request: {error} ({error.code.value})", err=True)
        raise typer.Exit(code=2) from error
    except ValidationError as error:
        details = canonical_json_bytes(sanitized_validation_errors(error)).decode("utf-8")
        typer.echo(f"invalid request: {details}", err=True)
        raise typer.Exit(code=2) from error
    except ProteoformRawInputAuthorizationError:
        raise
    except ProteoformQualityAuthorizationError:
        raise
    except M0801FormalStateAuthorizationError:
        raise
    except PtmBaselineAuthorizationError:
        raise
    except ProbabilisticEstimatorAuthorizationError:
        raise
    except M0606UncertaintyDecompositionAuthorizationError:
        raise
    except (TypeError, ValueError):
        if json_validator is not None:
            raise
        typer.echo("invalid request: unable to read or decode request document", err=True)
        raise typer.Exit(code=2) from None
    except OSError as error:
        typer.echo("invalid request: unable to read or decode request document", err=True)
        raise typer.Exit(code=2) from error


def _service(database: Path) -> M0101Service:
    return M0101Service(M0101EventStore(database))


def _identity_service(database: Path) -> M0102Service:
    return M0102Service(M0102EventStore(database))


def _load_release_files(
    request: BuildReleasePackageRequest,
    source_directory: Path,
) -> dict[str, bytes]:
    """Resolve declared POSIX paths beneath one directory and read their exact bytes."""

    root = _resolve_release_source(source_directory)
    if not root.is_dir():
        raise _ReleaseFileError.source_not_directory()
    files: dict[str, bytes] = {}
    for artifact in request.artifacts:
        parts = PurePosixPath(artifact.path).parts
        candidate = root.joinpath(*parts)
        cursor = root
        for part in parts:
            cursor /= part
            if cursor.is_symlink():
                raise _ReleaseFileError.symlink_source()
        resolved = _resolve_release_source(candidate)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise _ReleaseFileError.non_regular_source()
        content = _read_release_source(resolved, artifact.byte_size)
        files[artifact.path] = content
    return files


def _resolve_release_source(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise _ReleaseFileError.source_unavailable() from error


def _read_release_source(path: Path, expected_size: int) -> bytes:
    try:
        with path.open("rb") as stream:
            content = stream.read(expected_size + 1)
    except OSError as error:
        raise _ReleaseFileError.source_unavailable() from error
    if len(content) != expected_size:
        raise _ReleaseFileError.source_size_mismatch()
    return content


def _read_release_package(path: Path, expected_size: int) -> bytes:
    try:
        with path.open("rb") as stream:
            package_bytes = stream.read(expected_size + 1)
    except OSError as error:
        raise _ReleaseFileError.package_unavailable() from error
    if len(package_bytes) != expected_size:
        raise _ReleaseFileError.package_size_mismatch()
    return package_bytes


def _write_release_package(path: Path, package_bytes: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(package_bytes)
    except OSError as error:
        raise _ReleaseFileError.output_unavailable() from error


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _load_identification_release_inputs(
    request: BuildIdentificationQcReleaseRequest,
    source_directory: Path,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Read the exact declared tree and strictly reconstruct all seven stage results."""

    root = _resolve_identification_release_directory(source_directory)
    expected_paths = {item.path for item in request.artifacts}
    _validate_identification_release_tree(root, expected_paths)

    artifacts: dict[str, bytes] = {}
    by_role = {item.role: item for item in request.artifacts}
    for declaration in request.artifacts:
        candidate = root.joinpath(*PurePosixPath(declaration.path).parts)
        artifacts[declaration.path] = _read_identification_release_artifact(
            root,
            candidate,
            declaration.declared_size,
        )

    stages: dict[str, object] = {}
    for role, module_id, adapter in _IDENTIFICATION_RELEASE_STAGES:
        declaration = by_role[role]
        try:
            stages[module_id] = adapter.validate_json(
                artifacts[declaration.path],
                strict=True,
            )
        except ValidationError as error:
            raise _IdentificationReleaseFileError.stage_invalid() from error
    return artifacts, stages


def _validate_identification_release_tree(root: Path, expected_paths: set[str]) -> None:
    expected_directories = {
        parent.as_posix()
        for path in expected_paths
        for parent in PurePosixPath(path).parents
        if parent != PurePosixPath(".")
    }
    actual_paths: set[str] = set()
    try:
        entries = tuple(root.rglob("*"))
    except OSError as error:
        raise _IdentificationReleaseFileError.source_unavailable() from error
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        if _is_link_or_junction(entry):
            raise _IdentificationReleaseFileError.linked_source()
        if entry.is_dir():
            if relative not in expected_directories:
                raise _IdentificationReleaseFileError.unexpected_entry()
            continue
        if not entry.is_file():
            raise _IdentificationReleaseFileError.non_regular_source()
        if relative not in expected_paths:
            raise _IdentificationReleaseFileError.unexpected_entry()
        actual_paths.add(relative)
    if actual_paths != expected_paths:
        raise _IdentificationReleaseFileError.unexpected_entry()


def _resolve_identification_release_directory(source_directory: Path) -> Path:
    try:
        if _is_link_or_junction(source_directory):
            raise _IdentificationReleaseFileError.linked_source()
        root = source_directory.resolve(strict=True)
    except OSError as error:
        raise _IdentificationReleaseFileError.source_not_directory() from error
    if not root.is_dir():
        raise _IdentificationReleaseFileError.source_not_directory()
    return root


def _read_identification_release_artifact(
    root: Path,
    path: Path,
    expected_size: int,
) -> bytes:
    try:
        if _is_link_or_junction(path):
            raise _IdentificationReleaseFileError.linked_source()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise _IdentificationReleaseFileError.source_unavailable() from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise _IdentificationReleaseFileError.non_regular_source()
    try:
        with resolved.open("rb") as stream:
            content = stream.read(expected_size + 1)
    except OSError as error:
        raise _IdentificationReleaseFileError.source_unavailable() from error
    if len(content) != expected_size:
        raise _IdentificationReleaseFileError.source_size_mismatch()
    return content


def _read_identification_release_package(
    path: Path,
    result: IdentificationQcReleaseResult,
) -> bytes:
    descriptor = result.package_descriptor
    if descriptor is None:
        raise _IdentificationReleaseFileError.package_unavailable()
    try:
        if _is_link_or_junction(path):
            raise _IdentificationReleaseFileError.package_unavailable()
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise _IdentificationReleaseFileError.package_unavailable()
        with resolved.open("rb") as stream:
            content = stream.read(descriptor.byte_size + 1)
    except OSError as error:
        raise _IdentificationReleaseFileError.package_unavailable() from error
    if len(content) != descriptor.byte_size:
        raise _IdentificationReleaseFileError.package_size_mismatch()
    return content


def _write_identification_release_package(path: Path, package_bytes: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(package_bytes)
    except OSError as error:
        raise _IdentificationReleaseFileError.output_unavailable() from error


def _load_protein_inference_release_inputs(
    request: BuildProteinInferenceReleaseRequest,
    source_directory: Path,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Read the exact declared tree once and reconstruct all seven strict stage results."""

    root = _resolve_protein_inference_release_directory(source_directory)
    expected_paths = {item.path for item in request.artifacts}
    _validate_protein_inference_release_tree(root, expected_paths)
    artifacts: dict[str, bytes] = {}
    by_role = {item.role: item for item in request.artifacts}
    for declaration in request.artifacts:
        candidate = root.joinpath(*PurePosixPath(declaration.path).parts)
        artifacts[declaration.path] = _read_protein_inference_release_artifact(
            root,
            candidate,
            declaration.declared_size,
        )
    _validate_protein_inference_release_tree(root, expected_paths)

    stages: dict[str, object] = {}
    for role, module_id, adapter in _PROTEIN_INFERENCE_RELEASE_STAGES:
        declaration = by_role[role]
        try:
            stages[module_id] = adapter.validate_json(
                artifacts[declaration.path],
                strict=True,
            )
        except ValidationError as error:
            raise _ProteinInferenceReleaseFileError.stage_invalid() from error
    return artifacts, stages


def _resolve_protein_inference_release_directory(source_directory: Path) -> Path:
    try:
        if _is_protein_inference_release_reparse(source_directory):
            raise _ProteinInferenceReleaseFileError.linked_source()
        root = source_directory.resolve(strict=True)
    except _ProteinInferenceReleaseFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceReleaseFileError.source_not_directory() from error
    if not root.is_dir():
        raise _ProteinInferenceReleaseFileError.source_not_directory()
    return root


def _validate_protein_inference_release_tree(  # noqa: C901 - ordered hostile-tree checks.
    root: Path,
    expected_paths: set[str],
) -> None:
    expected_directories = {
        parent.as_posix()
        for path in expected_paths
        for parent in PurePosixPath(path).parents
        if parent != PurePosixPath(".")
    }
    actual_paths: set[str] = set()
    try:
        entries = tuple(root.rglob("*"))
    except OSError as error:
        raise _ProteinInferenceReleaseFileError.source_unavailable() from error
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        try:
            linked = _is_protein_inference_release_reparse(entry)
        except OSError as error:
            raise _ProteinInferenceReleaseFileError.source_unavailable() from error
        if linked:
            raise _ProteinInferenceReleaseFileError.linked_source()
        if entry.is_dir():
            if relative not in expected_directories:
                raise _ProteinInferenceReleaseFileError.unexpected_entry()
            continue
        try:
            received = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise _ProteinInferenceReleaseFileError.source_unavailable() from error
        if not stat.S_ISREG(received.st_mode):
            raise _ProteinInferenceReleaseFileError.non_regular_source()
        if relative not in expected_paths:
            raise _ProteinInferenceReleaseFileError.unexpected_entry()
        actual_paths.add(relative)
    if actual_paths != expected_paths:
        raise _ProteinInferenceReleaseFileError.unexpected_entry()


def _read_protein_inference_release_artifact(  # noqa: C901,PLR0912 - TOCTOU boundary.
    root: Path,
    candidate: Path,
    expected_size: int,
) -> bytes:
    if not candidate.is_relative_to(root):
        raise _ProteinInferenceReleaseFileError.non_regular_source()
    cursor = root
    for part in candidate.relative_to(root).parts[:-1]:
        cursor /= part
        try:
            if _is_protein_inference_release_reparse(cursor) or not cursor.is_dir():
                raise _ProteinInferenceReleaseFileError.linked_source()
        except OSError as error:
            raise _ProteinInferenceReleaseFileError.source_unavailable() from error
    try:
        if _is_protein_inference_release_reparse(candidate):
            raise _ProteinInferenceReleaseFileError.linked_source()
        before = candidate.stat(follow_symlinks=False)
    except _ProteinInferenceReleaseFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceReleaseFileError.source_unavailable() from error
    if not stat.S_ISREG(before.st_mode):
        raise _ProteinInferenceReleaseFileError.non_regular_source()
    if before.st_size != expected_size:
        raise _ProteinInferenceReleaseFileError.source_size_mismatch()
    try:
        with candidate.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _same_file_receipt(before, opened) or not stat.S_ISREG(opened.st_mode):
                raise _ProteinInferenceReleaseFileError.source_changed()
            content = stream.read(expected_size + 1)
            after = os.fstat(stream.fileno())
        current = candidate.stat(follow_symlinks=False)
    except _ProteinInferenceReleaseFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceReleaseFileError.source_unavailable() from error
    if not _same_file_receipt(opened, after) or not _same_file_receipt(after, current):
        raise _ProteinInferenceReleaseFileError.source_changed()
    if len(content) != expected_size:
        raise _ProteinInferenceReleaseFileError.source_size_mismatch()
    return content


def _read_protein_inference_release_package(
    path: Path,
    result: ProteinInferenceReleaseResult,
) -> bytes:
    descriptor = result.package_descriptor
    if descriptor is None:
        raise _ProteinInferenceReleaseFileError.package_unavailable()
    try:
        if _is_protein_inference_release_reparse(path):
            raise _ProteinInferenceReleaseFileError.package_unavailable()
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise _ProteinInferenceReleaseFileError.package_unavailable()
        if before.st_size != descriptor.byte_size:
            raise _ProteinInferenceReleaseFileError.package_size_mismatch()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _same_file_receipt(before, opened) or not stat.S_ISREG(opened.st_mode):
                raise _ProteinInferenceReleaseFileError.package_changed()
            content = stream.read(descriptor.byte_size + 1)
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
    except _ProteinInferenceReleaseFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceReleaseFileError.package_unavailable() from error
    if not _same_file_receipt(opened, after) or not _same_file_receipt(after, current):
        raise _ProteinInferenceReleaseFileError.package_changed()
    if len(content) != descriptor.byte_size:
        raise _ProteinInferenceReleaseFileError.package_size_mismatch()
    return content


def _write_protein_inference_release_package(path: Path, package_bytes: bytes) -> None:
    try:
        if path.exists() or _is_protein_inference_release_reparse(path):
            raise _ProteinInferenceReleaseFileError.output_unavailable()
        for parent in (path.parent, *path.parent.parents):
            if parent.exists() and _is_protein_inference_release_reparse(parent):
                raise _ProteinInferenceReleaseFileError.output_unavailable()
        with path.open("xb") as stream:
            stream.write(package_bytes)
    except _ProteinInferenceReleaseFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceReleaseFileError.output_unavailable() from error


def _is_protein_inference_release_reparse(path: Path) -> bool:
    try:
        received = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(received, "st_file_attributes", 0)
    return path.is_symlink() or path.is_junction() or bool(file_attributes & reparse_flag)


def _load_identification_raw_files(
    request: IngestIdentificationRawInputsRequest,
    source_directory: Path,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """Map each exact source identifier to one same-named regular file below a directory."""

    root = _resolve_identification_raw_directory(source_directory)
    payloads: dict[str, bytes] = {}
    filenames: dict[str, str] = {}
    for item in request.sources:
        descriptor = item.source
        payloads[descriptor.source_id] = _read_identification_raw_source(
            root,
            descriptor.source_id,
            descriptor.byte_length,
        )
        filenames[descriptor.source_id] = descriptor.source_id
    return payloads, filenames


def _resolve_identification_raw_directory(source_directory: Path) -> Path:
    try:
        if source_directory.is_symlink():
            raise _IdentificationRawFileError.symlink_source()
        root = source_directory.resolve(strict=True)
    except OSError as error:
        raise _IdentificationRawFileError.source_not_directory() from error
    if not root.is_dir():
        raise _IdentificationRawFileError.source_not_directory()
    return root


def _read_identification_raw_source(root: Path, source_id: str, expected_size: int) -> bytes:
    if ":" in source_id or Path(source_id).name != source_id or source_id in {".", ".."}:
        raise _IdentificationRawFileError.invalid_source_name()
    candidate = root / source_id
    if candidate.is_symlink():
        raise _IdentificationRawFileError.symlink_source()
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise _IdentificationRawFileError.source_unavailable() from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise _IdentificationRawFileError.non_regular_source()
    try:
        with resolved.open("rb") as stream:
            payload = stream.read(expected_size + 1)
    except OSError as error:
        raise _IdentificationRawFileError.source_unavailable() from error
    if len(payload) != expected_size:
        raise _IdentificationRawFileError.source_size_mismatch()
    return payload


def _load_protein_inference_raw_files(
    request: IngestProteinInferenceRawInputsRequest,
    source_directory: Path,
) -> dict[str, bytes]:
    """Validate the complete literal-basename mapping, then read each file exactly once."""

    root = _resolve_protein_inference_raw_directory(source_directory)
    candidates: list[tuple[str, Path, os.stat_result]] = []
    for declaration in sorted(request.sources, key=lambda item: item.source_id):
        _validate_protein_inference_source_name(declaration.source_id)
        candidate = root / declaration.source_id
        before = _protein_inference_source_stat(candidate)
        if before.st_size != declaration.byte_length:
            raise _ProteinInferenceRawFileError.source_size_mismatch()
        candidates.append((declaration.source_id, candidate, before))

    payloads: dict[str, bytes] = {}
    for source_id, candidate, before in candidates:
        try:
            with candidate.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if not _same_file_receipt(before, opened) or not stat.S_ISREG(opened.st_mode):
                    raise _ProteinInferenceRawFileError.source_changed()
                payload = stream.read(before.st_size + 1)
                after = os.fstat(stream.fileno())
        except _ProteinInferenceRawFileError:
            raise
        except OSError as error:
            raise _ProteinInferenceRawFileError.source_unavailable() from error
        if not _same_file_receipt(opened, after):
            raise _ProteinInferenceRawFileError.source_changed()
        if len(payload) != before.st_size:
            raise _ProteinInferenceRawFileError.source_size_mismatch()
        payloads[source_id] = payload
    return payloads


def _resolve_protein_inference_raw_directory(source_directory: Path) -> Path:
    try:
        if _is_reparse_path(source_directory):
            raise _ProteinInferenceRawFileError.linked_or_reparse_source()
        root = source_directory.resolve(strict=True)
    except _ProteinInferenceRawFileError:
        raise
    except OSError as error:
        raise _ProteinInferenceRawFileError.source_not_directory() from error
    if not root.is_dir():
        raise _ProteinInferenceRawFileError.source_not_directory()
    return root


def _validate_protein_inference_source_name(source_id: str) -> None:
    if (
        not source_id
        or source_id in {".", ".."}
        or ":" in source_id
        or "/" in source_id
        or "\\" in source_id
        or Path(source_id).name != source_id
        or source_id.rstrip(" .") != source_id
        or _is_windows_device_name(source_id)
    ):
        raise _ProteinInferenceRawFileError.invalid_source_name()


def _is_windows_device_name(source_id: str) -> bool:
    stem = source_id.split(".", 1)[0].casefold()
    return stem in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }


def _is_reparse_path(path: Path) -> bool:
    try:
        attributes = path.lstat()
    except OSError as error:
        raise _ProteinInferenceRawFileError.source_unavailable() from error
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(attributes, "st_file_attributes", 0)
    return path.is_symlink() or path.is_junction() or bool(file_attributes & reparse_flag)


def _protein_inference_source_stat(path: Path) -> os.stat_result:
    if _is_reparse_path(path):
        raise _ProteinInferenceRawFileError.linked_or_reparse_source()
    try:
        received = path.stat(follow_symlinks=False)
    except OSError as error:
        raise _ProteinInferenceRawFileError.source_unavailable() from error
    if not stat.S_ISREG(received.st_mode):
        raise _ProteinInferenceRawFileError.non_regular_source()
    return received


def _same_file_receipt(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


_PROTEOFORM_RAW_FILENAMES = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: ("mass-spectrometry-proteome.json"),
    ProteoformRawInputRole.GENOME: "genome.json",
    ProteoformRawInputRole.TRANSCRIPTOME: "transcriptome.json",
    ProteoformRawInputRole.PTM_ANNOTATIONS: "ptm-annotations.json",
}


def _load_proteoform_raw_files(  # noqa: C901, PLR0912, PLR0915 - explicit firewall.
    source_directory: Path,
    request: IngestProteoformRawInputsRequest,
) -> dict[ProteoformRawInputRole, bytes]:
    """Snapshot the four locked M04-03 manifest files exactly once."""

    try:
        lexical = source_directory.absolute()
        for component in (lexical, *lexical.parents):
            if component.exists() and _is_protein_inference_release_reparse(component):
                raise _ProteoformRawFileError.linked_or_reparse_source()
        root = source_directory.resolve(strict=True)
    except _ProteoformRawFileError:
        raise
    except (OSError, ValueError) as error:
        raise _ProteoformRawFileError.source_not_directory() from error
    try:
        root_before = root.stat(follow_symlinks=False)
    except (OSError, ValueError) as error:
        raise _ProteoformRawFileError.source_not_directory() from error
    if not stat.S_ISDIR(root_before.st_mode):
        raise _ProteoformRawFileError.source_not_directory()

    expected_names = set(_PROTEOFORM_RAW_FILENAMES.values())
    try:
        entries = tuple(root.iterdir())
    except (OSError, ValueError) as error:
        raise _ProteoformRawFileError.source_unavailable() from error
    if {entry.name for entry in entries} != expected_names:
        raise _ProteoformRawFileError.unexpected_entry()

    artifacts_by_role = {artifact.role: artifact for artifact in request.artifacts}
    if set(artifacts_by_role) != set(ProteoformRawInputRole):
        raise _ProteoformRawFileError.unexpected_entry()

    receipts: dict[ProteoformRawInputRole, tuple[Path, os.stat_result]] = {}
    total_size = 0
    for role, filename in _PROTEOFORM_RAW_FILENAMES.items():
        candidate = root / filename
        if _is_protein_inference_release_reparse(candidate):
            raise _ProteoformRawFileError.linked_or_reparse_source()
        try:
            before = candidate.stat(follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode):
                raise _ProteoformRawFileError.non_regular_source()
            artifact = artifacts_by_role[role]
            matching_parser = next(
                (
                    parser
                    for parser in request.policy.approved_parsers
                    if parser.role is role
                    and parser.format is artifact.format
                    and parser.format_version == artifact.format_version
                    and parser.parser_version == artifact.parser_version
                ),
                None,
            )
            active_limit = min(
                request.policy.max_document_bytes,
                M0403_MAX_DOCUMENT_BYTES,
                *((matching_parser.max_document_bytes,) if matching_parser is not None else ()),
            )
            total_size += before.st_size
            if (
                before.st_size != artifact.declared_size_bytes
                or before.st_size > active_limit
                or total_size > min(request.policy.max_total_bytes, M0403_MAX_TOTAL_DOCUMENT_BYTES)
            ):
                raise _ProteoformRawFileError.source_unavailable()
            receipts[role] = (candidate, before)
        except _ProteoformRawFileError:
            raise
        except (OSError, ValueError) as error:
            raise _ProteoformRawFileError.source_unavailable() from error

    snapshots: dict[ProteoformRawInputRole, bytes] = {}
    for role, (candidate, before) in receipts.items():
        try:
            with candidate.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if not _same_file_receipt(before, opened) or not stat.S_ISREG(opened.st_mode):
                    raise _ProteoformRawFileError.source_changed()
                payload = stream.read(before.st_size + 1)
                after = os.fstat(stream.fileno())
            current = candidate.stat(follow_symlinks=False)
        except _ProteoformRawFileError:
            raise
        except (OSError, ValueError) as error:
            raise _ProteoformRawFileError.source_unavailable() from error
        if not _same_file_receipt(opened, after) or not _same_file_receipt(after, current):
            raise _ProteoformRawFileError.source_changed()
        if len(payload) != before.st_size:
            raise _ProteoformRawFileError.source_changed()
        snapshots[role] = payload

    try:
        root_after = root.stat(follow_symlinks=False)
        final_entries = tuple(root.iterdir())
        final_tree_is_closed = {entry.name for entry in final_entries} == expected_names and all(
            not _is_protein_inference_release_reparse(entry)
            and stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode)
            for entry in final_entries
        )
        final_members_are_unchanged = all(
            not _is_protein_inference_release_reparse(candidate)
            and _same_file_receipt(before, candidate.stat(follow_symlinks=False))
            for candidate, before in receipts.values()
        )
    except (OSError, ValueError) as error:
        raise _ProteoformRawFileError.source_unavailable() from error
    if (
        not _same_file_receipt(root_before, root_after)
        or not final_tree_is_closed
        or not final_members_are_unchanged
    ):
        raise _ProteoformRawFileError.source_changed()
    return snapshots


_WINDOWS_FILE_ATTRIBUTE_DIRECTORY = 0x10
_WINDOWS_FILE_ATTRIBUTE_NORMAL = 0x80
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_WINDOWS_FILE_LIST_DIRECTORY = 0x0001
_WINDOWS_FILE_READ_DATA = 0x0001
_WINDOWS_FILE_WRITE_DATA = 0x0002
_WINDOWS_FILE_TRAVERSE = 0x0020
_WINDOWS_FILE_READ_ATTRIBUTES = 0x0080
_WINDOWS_DELETE = 0x00010000
_WINDOWS_SYNCHRONIZE = 0x00100000
_WINDOWS_DIRECTORY_ACCESS = (
    _WINDOWS_FILE_LIST_DIRECTORY
    | _WINDOWS_FILE_TRAVERSE
    | _WINDOWS_FILE_READ_ATTRIBUTES
    | _WINDOWS_SYNCHRONIZE
)
_WINDOWS_OUTPUT_ACCESS = (
    _WINDOWS_FILE_READ_DATA
    | _WINDOWS_FILE_WRITE_DATA
    | _WINDOWS_FILE_READ_ATTRIBUTES
    | _WINDOWS_DELETE
    | _WINDOWS_SYNCHRONIZE
)
_WINDOWS_SHARE_ALL = 0x0007
_WINDOWS_SHARE_READ_DELETE = 0x0005
_WINDOWS_FILE_OPEN = 0x0001
_WINDOWS_FILE_CREATE = 0x0002
_WINDOWS_FILE_DIRECTORY_FILE = 0x0001
_WINDOWS_FILE_NON_DIRECTORY_FILE = 0x0040
_WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT = 0x0020
_WINDOWS_FILE_OPEN_REPARSE_POINT = 0x00200000
_WINDOWS_DIRECTORY_OPTIONS = (
    _WINDOWS_FILE_DIRECTORY_FILE
    | _WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
    | _WINDOWS_FILE_OPEN_REPARSE_POINT
)
_WINDOWS_FILE_OPTIONS = (
    _WINDOWS_FILE_NON_DIRECTORY_FILE
    | _WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
    | _WINDOWS_FILE_OPEN_REPARSE_POINT
)
_WINDOWS_OBJECT_CASE_INSENSITIVE = 0x0040
_WINDOWS_OPEN_EXISTING = 0x0003
_WINDOWS_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WINDOWS_FILE_RENAME_INFORMATION = 10
_WINDOWS_FILE_DISPOSITION_INFO = 4
_WINDOWS_MAX_WRITE = 0xFFFFFFFF
_WINDOWS_MAX_COMPONENT_BYTES = 0xFFFC
_PROTEOFORM_RAW_POSIX_DIR_FD_SUPPORTED = all(
    call in os.supports_dir_fd for call in (os.open, os.stat, os.link, os.unlink)
)


class _WindowsUnicodeString(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.USHORT),
        ("maximum_length", wintypes.USHORT),
        ("buffer", wintypes.LPWSTR),
    ]


class _WindowsObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.ULONG),
        ("root_directory", wintypes.HANDLE),
        ("object_name", ctypes.POINTER(_WindowsUnicodeString)),
        ("attributes", wintypes.ULONG),
        ("security_descriptor", wintypes.LPVOID),
        ("security_quality_of_service", wintypes.LPVOID),
    ]


class _WindowsIoStatusBlock(ctypes.Structure):
    _fields_ = [
        ("status_or_pointer", ctypes.c_void_p),
        ("information", ctypes.c_size_t),
    ]


class _WindowsRenameInformation(ctypes.Structure):
    _fields_ = [
        ("replace_if_exists", wintypes.BOOLEAN),
        ("root_directory", wintypes.HANDLE),
        ("file_name_length", wintypes.ULONG),
    ]


class _WindowsDispositionInformation(ctypes.Structure):
    _fields_ = [
        ("delete_file", wintypes.BOOLEAN),
    ]


class _WindowsByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("file_attributes", wintypes.DWORD),
        ("creation_time", wintypes.FILETIME),
        ("last_access_time", wintypes.FILETIME),
        ("last_write_time", wintypes.FILETIME),
        ("volume_serial_number", wintypes.DWORD),
        ("file_size_high", wintypes.DWORD),
        ("file_size_low", wintypes.DWORD),
        ("number_of_links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD),
        ("file_index_low", wintypes.DWORD),
    ]


_WINDOWS_RENAME_NAME_OFFSET = _WindowsRenameInformation.file_name_length.offset + ctypes.sizeof(
    wintypes.ULONG
)


def _write_proteoform_raw_result(path: Path, payload: bytes) -> None:
    """Atomically publish one new file through a non-reparse directory anchor."""

    try:
        absolute = path.absolute()
        if not absolute.name or absolute.name in {".", ".."}:
            raise _ProteoformRawFileError.output_unavailable()
        if os.name == "nt":
            _write_proteoform_raw_result_windows(absolute, payload)
        else:
            _write_proteoform_raw_result_posix(absolute, payload)
    except _ProteoformRawFileError:
        raise
    except (OSError, ValueError) as error:
        raise _ProteoformRawFileError.output_unavailable() from error


def _write_proteoform_raw_result_posix(  # noqa: C901, PLR0912, PLR0915
    path: Path,
    payload: bytes,
) -> None:
    """Publish with openat-style operations rooted in the opened parent inode."""

    if not _PROTEOFORM_RAW_POSIX_DIR_FD_SUPPORTED:
        _raise_anchored_output_error()
    parent_descriptor, final_name = _open_proteoform_raw_posix_parent(path)
    temporary_name = f".m0403-{os.urandom(16).hex()}.tmp"
    temporary_descriptor: int | None = None
    written: os.stat_result | None = None
    committed = False
    cleanup_error: OSError | None = None
    try:
        try:
            os.stat(final_name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise _ProteoformRawFileError.output_unavailable()
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | _required_posix_open_flag("O_NOFOLLOW")
            | _required_posix_open_flag("O_CLOEXEC")
        )
        temporary_descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(temporary_descriptor)
        if not stat.S_ISREG(opened.st_mode):
            _raise_anchored_output_error()
        written = opened
        _write_proteoform_raw_descriptor(temporary_descriptor, payload)
        written = os.fstat(temporary_descriptor)
        if not _same_file_identity(opened, written):
            _raise_anchored_output_error()
        named_temporary = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not _same_file_receipt(written, named_temporary):
            _raise_anchored_output_error()
        os.link(
            temporary_name,
            final_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not _proteoform_raw_posix_parent_is_current(path, parent_descriptor):
            _raise_anchored_output_error()
        received = os.stat(
            final_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not _same_file_receipt(written, received):
            _raise_anchored_output_error()
        os.unlink(temporary_name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        committed = True
    finally:
        if not committed and written is not None:
            try:
                _unlink_proteoform_raw_posix_name_if_owned(
                    parent_descriptor,
                    final_name,
                    written,
                )
                _unlink_proteoform_raw_posix_name_if_owned(
                    parent_descriptor,
                    temporary_name,
                    written,
                )
                os.fsync(parent_descriptor)
            except OSError as error:
                cleanup_error = error
        if temporary_descriptor is not None:
            try:
                os.close(temporary_descriptor)
            except OSError as error:
                cleanup_error = cleanup_error or error
        try:
            os.close(parent_descriptor)
        except OSError as error:
            cleanup_error = cleanup_error or error
        if cleanup_error is not None:
            raise cleanup_error


def _open_proteoform_raw_posix_parent(path: Path) -> tuple[int, str]:
    directory_flags = (
        os.O_RDONLY
        | _required_posix_open_flag("O_DIRECTORY")
        | _required_posix_open_flag("O_NOFOLLOW")
        | _required_posix_open_flag("O_CLOEXEC")
    )
    current = os.open(path.anchor, directory_flags)
    try:
        for component in path.parts[1:-1]:
            candidate = os.open(
                component,
                directory_flags,
                dir_fd=current,
            )
            try:
                received = os.fstat(candidate)
                if not stat.S_ISDIR(received.st_mode):
                    _raise_anchored_output_error()
            except BaseException:
                os.close(candidate)
                raise
            os.close(current)
            current = candidate
        parent = os.fstat(current)
        if not stat.S_ISDIR(parent.st_mode):
            _raise_anchored_output_error()
        return current, path.name  # noqa: TRY300
    except BaseException:
        os.close(current)
        raise


def _proteoform_raw_posix_parent_is_current(path: Path, expected: int) -> bool:
    try:
        received, _ = _open_proteoform_raw_posix_parent(path)
    except OSError:
        return False
    try:
        return _same_file_identity(os.fstat(expected), os.fstat(received))
    finally:
        os.close(received)


def _unlink_proteoform_raw_posix_name_if_owned(
    parent_descriptor: int,
    name: str,
    expected: os.stat_result,
) -> None:
    try:
        received = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if _same_file_identity(expected, received):
        os.unlink(name, dir_fd=parent_descriptor)


def _write_proteoform_raw_descriptor(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            _raise_anchored_output_error()
        remaining = remaining[written:]
    os.fsync(descriptor)


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _required_posix_open_flag(name: str) -> int:
    received = vars(os).get(name)
    if not isinstance(received, int):
        _raise_anchored_output_error()
    return received


def _raise_anchored_output_error() -> Never:
    raise OSError


# The aggregate coverage gate runs on Ubuntu. This native publisher is exercised by the
# dedicated Windows M04-03 interface job, so its function suites are excluded from that
# single-platform aggregate instead of being reported as structurally unreachable misses.
def _write_proteoform_raw_result_windows(  # pragma: no cover
    path: Path,
    payload: bytes,
) -> None:
    """Publish by native handle-relative create and rename under one parent handle."""

    parent_handle, final_name = _open_proteoform_raw_windows_parent(path)
    parent_receipt = _windows_file_receipt(parent_handle, directory=True)
    temporary_name = f".m0403-{os.urandom(16).hex()}.tmp"
    output_handle: int | None = None
    output_receipt: tuple[int, int] | None = None
    committed = False
    cleanup_error: OSError | None = None
    try:
        output_handle = _windows_nt_create_relative(
            parent_handle,
            temporary_name,
            desired_access=_WINDOWS_OUTPUT_ACCESS,
            share_access=_WINDOWS_SHARE_READ_DELETE,
            disposition=_WINDOWS_FILE_CREATE,
            options=_WINDOWS_FILE_OPTIONS,
        )
        output_receipt = _windows_file_receipt(output_handle, directory=False)
        _write_proteoform_raw_windows_handle(output_handle, payload)
        if _windows_file_receipt(output_handle, directory=False) != output_receipt:
            _raise_anchored_output_error()
        _windows_rename_proteoform_raw_output(
            output_handle,
            parent_handle,
            final_name,
        )
        received_parent, received_name = _open_proteoform_raw_windows_parent(path)
        try:
            if (
                received_name != final_name
                or _windows_file_receipt(received_parent, directory=True) != parent_receipt
            ):
                _raise_anchored_output_error()
        finally:
            _windows_close_handle(received_parent)
        received_output = _windows_nt_create_relative(
            parent_handle,
            final_name,
            desired_access=_WINDOWS_FILE_READ_ATTRIBUTES | _WINDOWS_SYNCHRONIZE,
            disposition=_WINDOWS_FILE_OPEN,
            options=_WINDOWS_FILE_OPTIONS,
        )
        try:
            if _windows_file_receipt(received_output, directory=False) != output_receipt:
                _raise_anchored_output_error()
        finally:
            _windows_close_handle(received_output)
        committed = True
    finally:
        if output_handle is not None and not committed:
            try:
                _windows_mark_output_for_deletion(output_handle)
            except OSError as error:
                cleanup_error = error
        if output_handle is not None:
            try:
                _windows_close_handle(output_handle)
            except OSError as error:
                cleanup_error = cleanup_error or error
        try:
            _windows_close_handle(parent_handle)
        except OSError as error:
            cleanup_error = cleanup_error or error
        if cleanup_error is not None:
            raise cleanup_error


def _open_proteoform_raw_windows_parent(  # pragma: no cover
    path: Path,
) -> tuple[int, str]:
    current = _windows_open_root(path.anchor)
    try:
        for component in path.parts[1:-1]:
            candidate = _windows_nt_create_relative(
                current,
                component,
                desired_access=_WINDOWS_DIRECTORY_ACCESS,
                disposition=_WINDOWS_FILE_OPEN,
                options=_WINDOWS_DIRECTORY_OPTIONS,
            )
            try:
                _windows_file_receipt(candidate, directory=True)
            except BaseException:
                _windows_close_handle(candidate)
                raise
            _windows_close_handle(current)
            current = candidate
        _windows_file_receipt(current, directory=True)
        return current, path.name  # noqa: TRY300
    except BaseException:
        _windows_close_handle(current)
        raise


def _windows_open_root(anchor: str) -> int:  # pragma: no cover
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    received = create_file(
        _windows_extended_path(anchor),
        _WINDOWS_DIRECTORY_ACCESS,
        _WINDOWS_SHARE_ALL,
        None,
        _WINDOWS_OPEN_EXISTING,
        _WINDOWS_FILE_FLAG_BACKUP_SEMANTICS | _WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if received in {None, invalid_handle}:
        raise _windows_last_error()
    handle = int(received)
    try:
        _windows_file_receipt(handle, directory=True)
    except BaseException:
        _windows_close_handle(handle)
        raise
    return handle


def _windows_nt_create_relative(  # noqa: PLR0913 - mirrors NtCreateFile policy.  # pragma: no cover
    root_handle: int,
    name: str,
    *,
    desired_access: int,
    share_access: int = _WINDOWS_SHARE_ALL,
    disposition: int,
    options: int,
) -> int:
    if (
        not name
        or name in {".", ".."}
        or "\\" in name
        or "/" in name
        or ":" in name
        or "\x00" in name
    ):
        _raise_anchored_output_error()
    encoded_length = len(name.encode("utf-16-le"))
    if encoded_length > _WINDOWS_MAX_COMPONENT_BYTES:
        _raise_anchored_output_error()
    name_buffer = ctypes.create_unicode_buffer(name)
    unicode_name = _WindowsUnicodeString(
        encoded_length,
        encoded_length + ctypes.sizeof(wintypes.WCHAR),
        ctypes.cast(name_buffer, wintypes.LPWSTR),
    )
    attributes = _WindowsObjectAttributes(
        ctypes.sizeof(_WindowsObjectAttributes),
        wintypes.HANDLE(root_handle),
        ctypes.pointer(unicode_name),
        _WINDOWS_OBJECT_CASE_INSENSITIVE,
        None,
        None,
    )
    io_status = _WindowsIoStatusBlock()
    received = wintypes.HANDLE()
    ntdll = ctypes.WinDLL("ntdll")
    nt_create_file = ntdll.NtCreateFile
    nt_create_file.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(_WindowsObjectAttributes),
        ctypes.POINTER(_WindowsIoStatusBlock),
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    nt_create_file.restype = wintypes.LONG
    status = int(
        nt_create_file(
            ctypes.byref(received),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            _WINDOWS_FILE_ATTRIBUTE_NORMAL,
            share_access,
            disposition,
            options,
            None,
            0,
        )
    )
    if status < 0:
        raise _windows_ntstatus_error(status)
    if received.value is None:
        _raise_anchored_output_error()
    return int(received.value)


def _windows_rename_proteoform_raw_output(  # pragma: no cover
    output_handle: int,
    parent_handle: int,
    final_name: str,
) -> None:
    encoded_name = final_name.encode("utf-16-le")
    buffer = ctypes.create_string_buffer(_WINDOWS_RENAME_NAME_OFFSET + len(encoded_name))
    rename = _WindowsRenameInformation.from_buffer(buffer)
    rename.replace_if_exists = False
    rename.root_directory = wintypes.HANDLE(parent_handle)
    rename.file_name_length = len(encoded_name)
    ctypes.memmove(
        ctypes.addressof(buffer) + _WINDOWS_RENAME_NAME_OFFSET,
        encoded_name,
        len(encoded_name),
    )
    io_status = _WindowsIoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll")
    nt_set_information_file = ntdll.NtSetInformationFile
    nt_set_information_file.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_WindowsIoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    nt_set_information_file.restype = wintypes.LONG
    status = int(
        nt_set_information_file(
            wintypes.HANDLE(output_handle),
            ctypes.byref(io_status),
            buffer,
            len(buffer),
            _WINDOWS_FILE_RENAME_INFORMATION,
        )
    )
    if status < 0:
        raise _windows_ntstatus_error(status)


def _write_proteoform_raw_windows_handle(  # pragma: no cover
    handle: int,
    payload: bytes,
) -> None:
    if len(payload) > _WINDOWS_MAX_WRITE:
        _raise_anchored_output_error()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    write_file = kernel32.WriteFile
    write_file.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    write_file.restype = wintypes.BOOL
    if payload:
        buffer = ctypes.create_string_buffer(payload, len(payload))
        written = wintypes.DWORD()
        if not write_file(
            wintypes.HANDLE(handle),
            buffer,
            len(payload),
            ctypes.byref(written),
            None,
        ):
            raise _windows_last_error()
        if written.value != len(payload):
            _raise_anchored_output_error()
    flush_file = kernel32.FlushFileBuffers
    flush_file.argtypes = [wintypes.HANDLE]
    flush_file.restype = wintypes.BOOL
    if not flush_file(wintypes.HANDLE(handle)):
        raise _windows_last_error()


def _windows_mark_output_for_deletion(handle: int) -> None:  # pragma: no cover
    disposition = _WindowsDispositionInformation()
    disposition.delete_file = True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    set_information.restype = wintypes.BOOL
    if not set_information(
        wintypes.HANDLE(handle),
        _WINDOWS_FILE_DISPOSITION_INFO,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise _windows_last_error()


def _windows_file_receipt(  # pragma: no cover
    handle: int,
    *,
    directory: bool,
) -> tuple[int, int]:
    information = _WindowsByHandleFileInformation()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_WindowsByHandleFileInformation),
    ]
    get_information.restype = wintypes.BOOL
    if not get_information(wintypes.HANDLE(handle), ctypes.byref(information)):
        raise _windows_last_error()
    attributes = int(information.file_attributes)
    received_directory = bool(attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY)
    if received_directory is not directory or attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT:
        _raise_anchored_output_error()
    identifier = (int(information.file_index_high) << 32) | int(information.file_index_low)
    return int(information.volume_serial_number), identifier


def _windows_close_handle(handle: int) -> None:  # pragma: no cover
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    if not close_handle(wintypes.HANDLE(handle)):
        raise _windows_last_error()


def _windows_extended_path(path: str) -> str:  # pragma: no cover
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return f"\\\\?\\UNC\\{path[2:]}"
    return f"\\\\?\\{path}"


def _windows_last_error() -> OSError:  # pragma: no cover
    received = ctypes.get_last_error()
    code = int(received)
    return OSError(code, f"Windows error {code}")


def _windows_ntstatus_error(status: int) -> OSError:  # pragma: no cover
    ntdll = ctypes.WinDLL("ntdll")
    convert = ntdll.RtlNtStatusToDosError
    convert.argtypes = [wintypes.LONG]
    convert.restype = wintypes.ULONG
    code = int(convert(status))
    return OSError(code, f"Windows error {code}")


@protocol_app.command("register")
def register_protocol(request: RequestArgument, database: DatabaseOption) -> None:
    """Register an immutable protocol specification."""

    parsed = _load_request(request, TypeAdapter(RegisterProtocolRequest))
    try:
        with _service(database) as service:
            _emit(service.register(parsed))
    except M0101ServiceError as error:
        typer.echo(f"registration failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("evaluate")
def evaluate_metadata(request: RequestArgument, database: DatabaseOption) -> None:
    """Evaluate metadata without mutating the submitted evidence."""

    parsed = _load_request(request, TypeAdapter(EvaluateMetadataRequest))
    try:
        with _service(database) as service:
            _emit(service.evaluate(parsed))
    except M0101ServiceError as error:
        typer.echo(f"evaluation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("get")
def get_protocol(
    schema_id: Annotated[str, typer.Argument(help="Protocol schema identifier.")],
    version: Annotated[str, typer.Argument(help="Exact semantic version.")],
    database: DatabaseOption,
) -> None:
    """Retrieve the original content-addressed registration receipt."""

    try:
        with _service(database) as service:
            _emit(service.get_protocol(schema_id, version))
    except InvalidProtocolLookupError as error:
        typer.echo(f"invalid lookup: {error}", err=True)
        raise typer.Exit(code=2) from error
    except M0101ServiceError as error:
        typer.echo(f"lookup failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("verify-ledger")
def verify_ledger(database: DatabaseOption) -> None:
    """Verify every link and payload digest in the append-only event chain."""

    try:
        with _service(database) as service:
            result = service.verify_event_chain()
            _emit(result)
            if not result.valid:
                raise typer.Exit(code=1)
    except M0101ServiceError as error:
        typer.echo(f"verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("reconcile")
def reconcile_identity_lineage(request: RequestArgument, database: DatabaseOption) -> None:
    """Reconcile explicit identity assertions and lineage without relabeling inputs."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ReconcileIdentityLineageRequest),
            preflight_identity_authorization,
        )
        with _identity_service(database) as service:
            _emit(service.execute(parsed))
    except (IdentityLineageAuthorizationError, M0102EventStoreError) as error:
        typer.echo(f"reconciliation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("get")
def get_identity_resolution(
    resolution_digest: Annotated[str, typer.Argument(help="Exact resolution digest.")],
    database: DatabaseOption,
) -> None:
    """Retrieve and revalidate an immutable identity-lineage resolution."""

    try:
        validated_digest = _RESOLUTION_DIGEST_ADAPTER.validate_python(
            resolution_digest,
            strict=True,
        )
    except ValidationError as error:
        typer.echo("invalid lookup: resolution digest is invalid", err=True)
        raise typer.Exit(code=2) from error
    try:
        with _identity_service(database) as service:
            _emit(service.get_resolution(validated_digest))
    except M0102EventStoreError as error:
        typer.echo(f"lookup failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("verify-ledger")
def verify_identity_ledger(database: DatabaseOption) -> None:
    """Verify the M01-02 append-only identity-resolution event chain."""

    try:
        with _identity_service(database) as service:
            result = service.verify_event_chain()
            _emit(result)
            if not result.valid:
                raise typer.Exit(code=1)
    except M0102EventStoreError as error:
        typer.echo(f"verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("export-schema")
def export_identity_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "entity", "operation", "resolution"],
        typer.Argument(help="M01-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-02 contract for agents and tools."""

    typer.echo(json.dumps(_identity_contract_schema(contract), indent=2, sort_keys=True))


@raw_app.command("inspect")
def inspect_raw_input(
    source: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    source_id: Annotated[str, typer.Option("--source-id", help="Opaque source identifier.")],
    expected_sha256: Annotated[
        str | None,
        typer.Option("--sha256", help="Optional SHA-256 digest of the transported bytes."),
    ] = None,
) -> None:
    """Inspect one bounded file and emit metadata only; source content is never echoed."""

    try:
        validated_source_id = TypeAdapter(Identifier).validate_python(source_id, strict=True)
        with source.open("rb") as stream:
            result = parse_raw_input(
                stream,
                source_id=validated_source_id,
                filename=source.name,
                expected_sha256=expected_sha256,
            )
    except ValidationError as error:
        typer.echo("invalid source identifier", err=True)
        raise typer.Exit(code=2) from error
    except OSError as error:
        typer.echo("inspection failed: unable to read source", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "accepted":
        raise typer.Exit(code=1)


@raw_app.command("export-schema")
def export_raw_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "source", "raw_input", "diagnostic"],
        typer.Argument(help="M01-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-03 contract for agents and tools."""

    typer.echo(json.dumps(_raw_contract_schema(contract), indent=2, sort_keys=True))


@quality_app.command("compute")
def compute_quality_metrics(request: RequestArgument) -> None:
    """Compute one deterministic typed quality profile."""

    parsed = _load_request(request, TypeAdapter(ComputeQualityMetricsRequest))
    _emit(M0104Service().execute(parsed))


@quality_app.command("export-schema")
def export_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "assay_profile",
            "metric_definition",
            "observation",
            "quality_metric",
        ],
        typer.Argument(help="M01-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-04 contract for agents and tools."""

    typer.echo(json.dumps(_quality_contract_schema(contract), indent=2, sort_keys=True))


@artifact_app.command("detect")
def detect_artifacts(request: RequestArgument) -> None:
    """Run one configured deterministic artifact screen."""

    parsed = _load_request(request, TypeAdapter(DetectArtifactsRequest))
    _emit(M0105Service().execute(parsed))


@artifact_app.command("export-schema")
def export_artifact_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "profile", "rule", "signal", "flag"],
        typer.Argument(help="M01-05 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-05 contract for agents and tools."""

    typer.echo(json.dumps(_artifact_contract_schema(contract), indent=2, sort_keys=True))


@harmonization_app.command("run")
def run_harmonization(request: RequestArgument) -> None:
    """Apply one authorized, configured technical harmonization."""

    parsed = _load_request(
        request,
        TypeAdapter(HarmonizeObservationsRequest),
        preflight_harmonization_authorization,
    )
    _emit(M0106Service().execute(parsed))


@harmonization_app.command("export-schema")
def export_harmonization_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "invariant",
            "value",
            "transformation",
        ],
        typer.Argument(help="M01-06 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-06 contract for agents and tools."""

    typer.echo(json.dumps(_harmonization_contract_schema(contract), indent=2, sort_keys=True))


@support_routing_app.command("route")
def run_support_routing(request: RequestArgument) -> None:
    """Route one authorized request through a declared support domain."""

    parsed = _load_request(
        request,
        TypeAdapter(RouteSupportRequest),
        preflight_support_routing_authorization,
    )
    _emit(M0107Service().execute(parsed))


@support_routing_app.command("export-schema")
def export_support_routing_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "criterion",
            "evidence",
            "assessment",
        ],
        typer.Argument(help="M01-07 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-07 contract for agents and tools."""

    typer.echo(json.dumps(_support_routing_contract_schema(contract), indent=2, sort_keys=True))


@release_packaging_app.command("export-schema")
def export_release_packaging_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "manifest"],
        typer.Argument(help="M01-08 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-08 contract for agents and tools."""

    typer.echo(json.dumps(_release_packaging_contract_schema(contract), indent=2, sort_keys=True))


@identification_app.command("validate-metadata")
def validate_identification_metadata(request: RequestArgument) -> None:
    """Validate metadata against one exact protocol schema and conformance profile."""

    parsed = _load_request(
        request,
        TypeAdapter(EvaluateConformanceRequest),
        preflight_conformance_authorization,
    )
    _emit(evaluate_conformance(parsed))


@identification_app.command("export-schema")
def export_identification_schema(
    contract: Annotated[
        Literal["request", "output", "schema", "profile", "observation"],
        typer.Argument(help="M02-01 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-01 contract for agents and tools."""

    typer.echo(json.dumps(_identification_contract_schema(contract), indent=2, sort_keys=True))


@binding_audit_app.command("audit")
def audit_identity_bindings(request: RequestArgument) -> None:
    """Audit bindings against one immutable upstream identity resolution."""

    parsed = _load_request(
        request,
        TypeAdapter(ValidateIdentityBindingsRequest),
        preflight_identity_binding_authorization,
    )
    _emit(evaluate_identity_bindings(parsed))


@binding_audit_app.command("export-schema")
def export_identity_binding_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "binding", "finding"],
        typer.Argument(help="M02-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-02 contract for agents and tools."""

    typer.echo(json.dumps(_identity_binding_contract_schema(contract), indent=2, sort_keys=True))


@identification_raw_app.command("ingest")
def ingest_identification_raw_inputs(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
) -> None:
    """Ingest exact same-named source files from one symlink-free directory."""

    parsed = _load_request(
        request,
        TypeAdapter(IngestIdentificationRawInputsRequest),
        preflight_identification_raw_ingestion_authorization,
    )
    try:
        sources, filenames = _load_identification_raw_files(parsed, source_directory)
        result = M0203Service().execute(parsed, sources, filenames)
    except (IdentificationRawIngestionInputError, _IdentificationRawFileError) as error:
        typer.echo(f"identification raw ingestion failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "accepted":
        raise typer.Exit(code=1)


@identification_raw_app.command("export-schema")
def export_identification_raw_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "source",
            "role_requirement",
            "bundle_diagnostic",
        ],
        typer.Argument(help="M02-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-03 contract for agents and tools."""

    typer.echo(json.dumps(_identification_raw_contract_schema(contract), indent=2, sort_keys=True))


@identification_quality_app.command("export-schema")
def export_identification_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "assay_profile",
            "policy",
            "threshold",
            "observation",
            "metric",
        ],
        typer.Argument(help="M02-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-04 contract for agents and tools."""

    typer.echo(
        json.dumps(_identification_quality_contract_schema(contract), indent=2, sort_keys=True)
    )


@identification_quality_app.command("compute")
def compute_identification_quality(request: RequestArgument) -> None:
    """Compute one authorized deterministic identification-quality profile."""

    parsed = _load_request(
        request,
        TypeAdapter(ComputeIdentificationQualityRequest),
        preflight_identification_quality_authorization,
    )
    _emit(M0204Service().execute(parsed))


@identification_artifacts_app.command("export-schema")
def export_identification_artifact_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "profile",
            "policy",
            "signal",
            "flag",
            "evaluation",
        ],
        typer.Argument(help="M02-05 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-05 contract for agents and tools."""

    typer.echo(
        json.dumps(_identification_artifact_contract_schema(contract), indent=2, sort_keys=True)
    )


@identification_artifacts_app.command("detect")
def detect_identification_artifacts(request: RequestArgument) -> None:
    """Detect configured technical artifacts in authorized identification evidence."""

    parsed = _load_request(
        request,
        TypeAdapter(DetectIdentificationArtifactsRequest),
        preflight_identification_artifact_authorization,
    )
    _emit(M0205Service().execute(parsed))


@identification_harmonization_app.command("export-schema")
def export_identification_harmonization_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "prerequisites",
            "profile",
            "policy",
            "observation",
            "value",
            "manifest",
        ],
        typer.Argument(help="M02-06 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-06 contract for agents and tools."""

    typer.echo(
        json.dumps(
            _identification_harmonization_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@identification_harmonization_app.command("harmonize")
def harmonize_identification(request: RequestArgument) -> None:
    """Harmonize authorized aggregate identification evidence."""

    parsed = _load_request(
        request,
        TypeAdapter(HarmonizeIdentificationEvidenceRequest),
        preflight_identification_harmonization_authorization,
    )
    _emit(M0206Service().execute(parsed))


@identification_support_app.command("export-schema")
def export_identification_support_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "prerequisites",
            "profile",
            "policy",
            "declaration",
            "envelope",
            "abstention",
        ],
        typer.Argument(help="M02-07 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-07 contract for agents and tools."""

    typer.echo(
        json.dumps(
            _identification_support_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@identification_support_app.command("route")
def route_identification_support(request: RequestArgument) -> None:
    """Route authorized identification evidence through whole support envelopes."""

    parsed = _load_request(
        request,
        TypeAdapter(RouteIdentificationSupportRequest),
        preflight_identification_support_authorization,
    )
    _emit(M0207Service().execute(parsed))


@identification_release_app.command("export-schema")
def export_identification_release_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "artifact",
            "manifest",
            "verification",
            "signature",
        ],
        typer.Argument(help="M02-08 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M02-08 identification release contract."""

    typer.echo(
        json.dumps(
            _identification_release_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@identification_release_app.command("build")
def build_identification_release_archive(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
    output: OutputOption,
) -> None:
    """Validate a closed release; without an injected verifier this quarantines safely."""

    parsed = _load_request(
        request,
        TypeAdapter(BuildIdentificationQcReleaseRequest),
        preflight_identification_release_authorization,
    )
    try:
        artifacts, stages = _load_identification_release_inputs(parsed, source_directory)
        built = M0208Service().build(parsed, artifacts, stages)
        if built.package_bytes is not None:
            _write_identification_release_package(output, built.package_bytes)
    except (
        IdentificationReleaseAuthorizationError,
        IdentificationReleaseInputError,
        _IdentificationReleaseFileError,
    ) as error:
        typer.echo(f"identification release build failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    _emit(built.result)
    if built.result.disposition is not IdentificationReleaseDisposition.RELEASED:
        raise typer.Exit(code=1)


@identification_release_app.command("verify")
def verify_identification_release_archive(
    result: RequestArgument,
    package: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Verify archive structure and content; authenticity needs an injected verifier."""

    parsed = _load_request(result, TypeAdapter(IdentificationQcReleaseResult))
    try:
        package_bytes = _read_identification_release_package(package, parsed)
        verification = M0208Service().verify(parsed, package_bytes)
    except _IdentificationReleaseFileError as error:
        typer.echo(f"identification release verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(verification)
    if not verification.verified:
        raise typer.Exit(code=1)


@release_packaging_app.command("build")
def build_release_archive(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
    output: OutputOption,
) -> None:
    """Build and publish one externally authorized canonical release package."""

    parsed = _load_request(
        request,
        TypeAdapter(BuildReleasePackageRequest),
        preflight_release_packaging_authorization,
    )
    try:
        built = M0108Service().execute(parsed, _load_release_files(parsed, source_directory))
        if built.result.disposition is ReleaseDisposition.RELEASED:
            _write_release_package(output, built.package_bytes)
    except (ReleasePackagingInputError, _ReleaseFileError) as error:
        typer.echo(f"release build failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    _emit(built.result)
    if built.result.disposition is not ReleaseDisposition.RELEASED:
        raise typer.Exit(code=1)


@release_packaging_app.command("verify")
def verify_release_archive(
    result: RequestArgument,
    package: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Verify package bytes against one typed M01-08 release result."""

    parsed = _load_request(result, TypeAdapter(ReleasePackagingResult))
    try:
        package_bytes = _read_release_package(package, parsed.package.byte_size)
    except _ReleaseFileError as error:
        typer.echo(f"release verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    verification = verify_release_package(parsed, package_bytes)
    _emit(verification)
    if not verification.verified:
        raise typer.Exit(code=1)


@protein_inference_protocol_app.command("export-schema")
def export_protein_inference_protocol_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "protocol",
            "profile",
            "search-space",
            "ambiguity",
            "receipt",
        ],
        typer.Argument(help="M03-01 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference protocol contract."""

    typer.echo(
        json.dumps(
            _protein_inference_protocol_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_protocol_app.command("validate")
def validate_protein_inference_protocol(request: RequestArgument) -> None:
    """Validate one authorized protein-inference protocol against its reviewed profile."""

    parsed = _load_request(
        request,
        TypeAdapter(EvaluateProteinInferenceProtocolRequest),
        preflight_protein_inference_protocol_authorization,
    )
    _emit(M0301Service().execute(parsed))


@protein_inference_lineage_app.command("export-schema")
def export_protein_inference_lineage_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "artifact-claim",
            "derivation",
            "cn-receipt",
            "graph",
            "receipt",
        ],
        typer.Argument(help="M03-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference lineage contract."""

    typer.echo(
        json.dumps(
            _protein_inference_lineage_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_lineage_app.command("reconcile")
def reconcile_protein_inference_lineage(request: RequestArgument) -> None:
    """Reconcile governed protein-inference artifact lineage without relabeling."""

    parsed = _load_request(
        request,
        TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest),
        preflight_protein_identity_lineage_authorization,
    )
    _emit(M0302Service().execute(parsed))


@protein_inference_raw_app.command("export-schema")
def export_protein_inference_raw_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "source",
            "protocol-receipt",
            "lineage-receipt",
            "raw-input",
            "receipt",
        ],
        typer.Argument(help="M03-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference raw-admission contract."""

    typer.echo(
        json.dumps(
            _protein_inference_raw_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_raw_app.command("ingest")
def ingest_protein_inference_raw_inputs(
    request: RequestArgument,
    source_directory: SourceDirectoryArgument,
) -> None:
    """Ingest exact same-named, non-reparse source files from one directory."""

    parsed = _load_request(
        request,
        TypeAdapter(IngestProteinInferenceRawInputsRequest),
        preflight_protein_inference_raw_ingestion_authorization,
    )
    try:
        sources = _load_protein_inference_raw_files(parsed, source_directory)
        result = M0303Service().execute(parsed, sources)
    except (
        ProteinInferenceRawIngestionInputError,
        _ProteinInferenceRawFileError,
    ) as error:
        typer.echo(f"protein-inference raw ingestion failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "validated":
        raise typer.Exit(code=1)


@protein_inference_quality_app.command("export-schema")
def export_protein_inference_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "threshold",
            "raw-quality-receipt",
            "fact-ledger",
            "metric",
            "finding",
        ],
        typer.Argument(help="M03-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference quality contract."""

    typer.echo(
        json.dumps(
            _protein_inference_quality_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_quality_app.command("compute")
def compute_protein_inference_quality(request: RequestArgument) -> None:
    """Compute one authorized metadata-only protein-inference quality result."""

    parsed = _load_request(
        request,
        TypeAdapter(ComputeProteinInferenceQualityRequest),
        preflight_protein_inference_quality_authorization,
        M0304_MAX_CANONICAL_REQUEST_BYTES,
    )
    _emit(M0304Service().execute(parsed))


@protein_inference_artifacts_app.command("export-schema")
def export_protein_inference_artifact_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "threshold",
            "quality-receipt",
            "evidence-ledger",
            "evidence-unit",
            "signal-score",
            "posterior",
            "contamination-flag",
            "exclusion-mask",
            "finding",
        ],
        typer.Argument(help="M03-05 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference artifact contract."""

    typer.echo(
        json.dumps(
            _protein_inference_artifact_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_artifacts_app.command("detect")
def detect_protein_inference_artifacts(request: RequestArgument) -> None:
    """Detect exact categorical artifacts from one metadata-only evidence ledger."""

    parsed = _load_request(
        request,
        TypeAdapter(DetectProteinInferenceArtifactsRequest),
        preflight_protein_inference_artifact_authorization,
        M0305_MAX_CANONICAL_REQUEST_BYTES,
    )
    _emit(M0305Service().execute(parsed))


@protein_inference_harmonization_app.command("export-schema")
def export_protein_inference_harmonization_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "profile",
            "stage",
            "artifact-receipt",
            "unit-receipt",
            "support-ledger",
            "observation",
            "invariant",
            "analysis",
            "value",
            "transformation-manifest",
            "finding",
        ],
        typer.Argument(help="M03-06 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference harmonization contract."""

    typer.echo(
        json.dumps(
            _protein_inference_harmonization_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_harmonization_app.command("harmonize")
def harmonize_protein_inference_support(request: RequestArgument) -> None:
    """Harmonize one authorized metadata-only protein-inference support ledger."""

    parsed = _load_request(
        request,
        TypeAdapter(HarmonizeProteinInferenceSupportRequest),
        preflight_protein_inference_harmonization_authorization,
        M0306_MAX_CANONICAL_REQUEST_BYTES,
    )
    _emit(M0306Service().execute(parsed))


@protein_inference_support_app.command("export-schema")
def export_protein_inference_support_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "prerequisites",
            "quality-receipt",
            "harmonization-receipt",
            "fact",
            "context-receipt",
            "profile",
            "policy",
            "envelope",
            "remediation",
            "dimension-assessment",
            "envelope-assessment",
            "abstention",
        ],
        typer.Argument(help="M03-07 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable protein-inference support contract."""

    typer.echo(
        json.dumps(
            _protein_inference_support_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@protein_inference_support_app.command("route")
def route_protein_inference_support(request: RequestArgument) -> None:
    """Route one authorized protein-inference declaration against joint envelopes."""

    parsed = _load_request(
        request,
        TypeAdapter(RouteProteinInferenceSupportRequest),
        preflight_protein_inference_support_authorization,
        M0307_MAX_CANONICAL_REQUEST_BYTES,
    )
    _emit(M0307Service().execute(parsed))


@protein_inference_release_app.command("export-schema")
def export_protein_inference_release_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "artifact",
            "manifest",
            "verification",
            "signature",
        ],
        typer.Argument(help="M03-08 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M03-08 protein-inference release contract."""

    typer.echo(
        json.dumps(
            _protein_inference_release_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@proteoform_protocol_app.command("export-schema")
def export_proteoform_protocol_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "protocol",
            "profile",
            "reference-bundle",
            "reference-cardinality",
            "coordinate-policy",
            "evidence-eligibility-policy",
            "isoform-discrimination-policy",
            "modification-localization-policy",
            "quantification-policy",
            "discordance-handoff",
            "receipt",
        ],
        typer.Argument(help="M04-01 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable proteoform protocol contract."""

    typer.echo(
        json.dumps(
            _proteoform_protocol_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@proteoform_protocol_app.command("validate")
def validate_proteoform_protocol(request: RequestArgument) -> None:
    """Validate one authorized proteoform protocol against its reviewed profile."""

    parsed = _load_request(
        request,
        TypeAdapter(EvaluateProteoformProtocolRequest),
        preflight_proteoform_protocol_authorization,
        M0401_MAX_CANONICAL_REQUEST_BYTES,
    )
    _emit(M0401Service().execute(parsed))


@proteoform_lineage_app.command("export-schema")
def export_proteoform_lineage_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "artifact-claim",
            "derivation",
            "graph",
            "finding",
            "receipt",
        ],
        typer.Argument(help="M04-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable proteoform identity-lineage contract."""

    typer.echo(
        json.dumps(
            _proteoform_lineage_contract_schema(contract),
            indent=2,
            sort_keys=True,
        )
    )


@proteoform_lineage_app.command("reconcile")
def reconcile_proteoform_lineage(request: RequestArgument) -> None:
    """Reconcile one authorized proteoform artifact-lineage request."""

    parsed = _load_request(
        request,
        TypeAdapter(ReconcileProteoformIdentityLineageRequest),
        preflight_proteoform_identity_lineage_authorization,
        M0402_MAX_CANONICAL_REQUEST_BYTES,
    )
    _emit(M0402Service().execute(parsed))


@proteoform_raw_app.command("export-schema")
def export_proteoform_raw_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "parser-profile",
            "input-artifact",
            "proteome-document",
            "genome-document",
            "transcriptome-document",
            "ptm-document",
            "validated-input",
            "diagnostic",
            "receipt",
        ],
        typer.Argument(help="M04-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable proteoform raw-ingestion contract."""

    typer.echo(json.dumps(_proteoform_raw_contract_schema(contract), indent=2, sort_keys=True))


@proteoform_raw_app.command("ingest")
def ingest_proteoform_raw_inputs(
    request: RequestArgument,
    source_directory: ProteoformRawSourceArgument,
    output: ProteoformRawOutputOption,
) -> None:
    """Ingest four locked canonical manifest files and publish one new result."""

    try:
        try:
            parsed = _load_request(
                request,
                TypeAdapter(IngestProteoformRawInputsRequest),
                preflight_proteoform_raw_input_authorization,
                M0403_MAX_CANONICAL_REQUEST_BYTES,
            )
            source_path = Path(source_directory)
            output_path = Path(output)
        except ProteoformRawInputAuthorizationError as error:
            typer.echo(f"proteoform raw ingestion failed: {error}", err=True)
            raise typer.Exit(code=2) from error
        sources = (
            _load_proteoform_raw_files(source_path, parsed)
            if parsed.lineage_result.disposition.value == "reconciled"
            else {}
        )
        result = M0403Service().execute(parsed, sources)
        _write_proteoform_raw_result(
            output_path, canonical_json_bytes(result.model_dump(mode="json"))
        )
    except (
        ProteoformRawInputAuthorizationError,
        ProteoformRawInputError,
        _ProteoformRawFileError,
    ) as error:
        typer.echo(f"proteoform raw ingestion failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if result.disposition.value != "validated":
        raise typer.Exit(code=1)


@proteoform_quality_app.command("export-schema")
def export_proteoform_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "threshold",
            "assay-profile",
            "fact-counts",
            "fact-states",
            "role-facts",
            "fact-ledger",
            "metric",
            "assay-quality",
            "finding",
            "receipt",
        ],
        typer.Argument(help="M04-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable proteoform quality contract."""

    typer.echo(json.dumps(_proteoform_quality_contract_schema(contract), indent=2, sort_keys=True))


@proteoform_quality_app.command("compute")
def compute_proteoform_quality_metrics(
    request: RequestArgument,
    output: ProteoformQualityOutputOption,
) -> None:
    """Compute reviewed fixed-point quality metrics and publish one new result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ComputeProteoformQualityMetricsRequest),
            None,
            M0404_MAX_CANONICAL_REQUEST_BYTES,
            _validate_m0404_json_request,
        )
        result = M0404Service().execute(parsed)
        _write_proteoform_raw_result(
            Path(output), canonical_json_bytes(result.model_dump(mode="json"))
        )
    except ProteoformQualityAuthorizationError as error:
        typer.echo(f"proteoform quality computation failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"proteoform quality computation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m0801_app.command("export-schema")
def export_m0801_schema(contract: M0801ContractName) -> None:
    """Export one provisional M08-01 JSON Schema 2020-12 contract."""

    typer.echo(json.dumps(_m0801_contract_schema(contract), indent=2, sort_keys=True))


@m0801_app.command("validate")
def validate_m0801_state(
    request: RequestArgument,
    output: M0801OutputOption,
) -> None:
    """Validate one formal transcript-protein state and publish a canonical result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ValidateTranscriptProteinStateRequest),
            None,
            M0801_MAX_CANONICAL_REQUEST_BYTES,
            _validate_m0801_json_request,
        )
        result = M0801Service().execute(parsed)
        _write_proteoform_raw_result(
            Path(output), canonical_json_bytes(result.model_dump(mode="json"))
        )
    except M0801FormalStateAuthorizationError as error:
        typer.echo(f"transcript-protein state validation failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"transcript-protein state validation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@formal_state_app.command("export-schema")
def export_formal_state_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "schema",
            "feature-definition",
            "feature-value",
            "invariant",
            "invariant-result",
            "migration",
        ],
        typer.Argument(help="M06-01 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable formal-state contract."""

    typer.echo(json.dumps(_formal_state_contract_schema(contract), indent=2, sort_keys=True))


@formal_state_app.command("validate")
def validate_formal_state_request(request: RequestArgument) -> None:
    """Validate one formal-state request and execute its closed invariants."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ValidateFormalProteinStateRequest),
            preflight_formal_state_authorization,
            M0601_MAX_CANONICAL_REQUEST_BYTES,
        )
        _emit(M0601Service().execute(parsed))
    except (TypeError, ValueError) as error:
        typer.echo(f"formal-state validation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m0603_baseline_app.command("export-schema")
def export_m0603_baseline_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "configuration",
            "preprocessing-policy",
            "tuning-record",
            "estimate",
            "diagnostic",
        ],
        typer.Argument(help="M06-03 provisional public contract to export."),
    ],
) -> None:
    """Export one provisional M06-03 JSON Schema 2020-12 contract."""

    _emit(_m0603_baseline_contract_schema(contract))


@m0603_baseline_app.command("estimate")
def estimate_m0603_baseline(
    request: RequestArgument,
    output: M0603BaselineOutputOption,
) -> None:
    """Estimate transparent baseline values and publish one canonical result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(EstimateProteinAbundanceBaselineRequest),
            None,
            M0603_MAX_CANONICAL_REQUEST_BYTES,
            _validate_m0603_json_request,
        )
        result = M0603Service()._execute_validated(parsed)
        _write_proteoform_raw_result(
            Path(output), canonical_json_bytes(result.model_dump(mode="json"))
        )
    except PtmBaselineAuthorizationError as error:
        typer.echo(f"m06-03 baseline estimation denied: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"m06-03 baseline estimation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@probabilistic_estimator_app.command("export-schema")
def export_probabilistic_estimator_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "configuration",
            "prior",
            "constraint",
            "posterior",
            "diagnostic",
        ],
        typer.Argument(help="M06-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable provisional M06-04 contract."""

    _emit(_probabilistic_estimator_contract_schema(contract))


@probabilistic_estimator_app.command("estimate")
def estimate_probabilistic_abundance(request: RequestArgument) -> None:
    """Run the strict M06-04 proxy and print a typed estimate or abstention."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(EstimateProteinAbundanceProbabilisticRequest),
            preflight_probabilistic_estimator_authorization,
            M0604_MAX_CANONICAL_REQUEST_BYTES,
        )
        _emit(M0604Service().estimate(parsed))
    except ProbabilisticEstimatorAuthorizationError as error:
        typer.echo(f"probabilistic estimation denied: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"probabilistic estimation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@uncertainty_decomposition_app.command("export-schema")
def export_m0606_uncertainty_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "component",
            "decomposition",
            "sensitivity-envelope",
            "policy",
            "finding",
        ],
        typer.Argument(help="M06-06 provisional contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable provisional M06-06 contract."""

    _emit(_m0606_uncertainty_contract_schema(contract))


@uncertainty_decomposition_app.command("decompose")
def decompose_m0606_uncertainty(
    request: RequestArgument,
    output: M0606UncertaintyOutputOption,
) -> None:
    """Decompose uncertainty and publish a safe provisional result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(DecomposeProteinAbundanceUncertaintyRequest),
            None,
            M0606_MAX_CANONICAL_REQUEST_BYTES,
            _validate_m0606_json_request,
        )
        result = M0606Service().execute(parsed)
        _write_proteoform_raw_result(
            Path(output), canonical_json_bytes(result.model_dump(mode="json"))
        )
    except M0606UncertaintyDecompositionAuthorizationError as error:
        typer.echo(f"M06-06 uncertainty decomposition failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"M06-06 uncertainty decomposition failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1403_app.command("export-schema")
def export_m1403_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "feature-object",
            "feature",
            "lineage",
            "relation",
            "configuration",
            "diagnostic",
        ],
        typer.Argument(help="M14-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable M14-03 feature contract."""

    typer.echo(json.dumps(_m1403_contract_schema(contract), indent=2, sort_keys=True))


@m1403_app.command("construct")
def construct_m1403_features(request: RequestArgument) -> None:
    """Construct caller-declared mechanistic feature metadata and emit one sealed result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ConstructProteinSubtypeMechanisticFeaturesRequest),
            m1403_module.preflight_m1403_authorization,
            M1403_MAX_CANONICAL_REQUEST_BYTES,
        )
        _emit(m1403_module.M1403Service().execute(parsed))
    except m1403_module.M1403AuthorizationError as error:
        typer.echo(f"M14-03 feature construction failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"M14-03 feature construction failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1405_app.command("export-schema")
def export_m1405_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "trajectory",
            "state",
            "evidence",
            "configuration",
            "diagnostic",
        ],
        typer.Argument(help="M14-05 contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one strict provisional M14-05 schema."""

    typer.echo(json.dumps(_m1405_contract_schema(contract), indent=2, sort_keys=True))


@m1405_app.command("infer")
def infer_m1405(request: RequestArgument) -> None:
    """Replay an ordered M14-05 request into a bounded trajectory result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ModelProteinSubtypeLongitudinalEvolutionRequest),
            m1405_module.preflight_m1405_authorization,
            M1405_MAX_CANONICAL_REQUEST_BYTES,
        )
        _emit(m1405_module.M1405Service().execute(parsed))
    except m1405_module.M1405AuthorizationError as error:
        typer.echo(f"M14-05 longitudinal evolution failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"M14-05 longitudinal evolution failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1502_app.command("export-schema")
def export_m1502_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "attribute",
            "mechanism",
            "profile",
            "evaluation",
            "finding",
        ],
        typer.Argument(help="M15-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable provisional M15-02 contract."""

    typer.echo(json.dumps(_m1502_contract_schema(contract), indent=2, sort_keys=True))


@m1502_app.command("stratify")
def stratify_m1502(request: RequestArgument) -> None:
    """Replay caller-declared context and applicable mechanisms safely."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(StratifyContextAndSubtypeRequest),
            m1502_module.preflight_m1502_authorization,
            M1502_MAX_CANONICAL_REQUEST_BYTES,
        )
        _emit(m1502_module.M1502Service().execute(parsed))
    except m1502_module.M1502AuthorizationError as error:
        typer.echo(f"context stratification authorization failed: {error}", err=True)
        raise typer.Exit(code=2) from error


@m1306_app.command("export-schema")
def export_m1306_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "scenario",
            "response",
            "sensitivity-surface",
            "configuration",
            "policy",
            "finding",
        ],
        typer.Argument(help="M13-06 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export one machine-readable M13-06 perturbation contract."""

    typer.echo(json.dumps(_m1306_contract_schema(contract), indent=2, sort_keys=True))


@m1306_app.command("simulate")
def simulate_m1306(request: RequestArgument) -> None:
    """Replay bounded variant-peptide perturbations and emit one sealed result."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(SimulateProteotypePerturbationRequest),
            preflight_m1306_authorization,
            M1306_MAX_CANONICAL_REQUEST_BYTES,
        )
        _emit(M1306Service().execute(parsed))
    except M1306AuthorizationError as error:
        typer.echo(f"M13-06 perturbation simulation failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"M13-06 perturbation simulation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protein_inference_release_app.command("build")
def build_protein_inference_release_archive(
    request: RequestArgument,
    source_directory: UncheckedSourceDirectoryArgument,
    output: OutputOption,
) -> None:
    """Validate a closed release; the default verifier-free CLI quarantines safely."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(BuildProteinInferenceReleaseRequest),
            preflight_protein_inference_release_authorization,
            M0308_MAX_CANONICAL_REQUEST_BYTES,
        )
        artifacts, stages = _load_protein_inference_release_inputs(parsed, source_directory)
        built = M0308Service().build(parsed, artifacts, stages)
        if built.package_bytes is not None:
            _write_protein_inference_release_package(output, built.package_bytes)
    except (
        ProteinInferenceReleaseAuthorizationError,
        ProteinInferenceReleaseInputError,
        _ProteinInferenceReleaseFileError,
    ) as error:
        typer.echo(f"protein-inference release build failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    _emit(built.result)
    if built.result.disposition is not ProteinInferenceReleaseDisposition.RELEASED:
        raise typer.Exit(code=1)


@protein_inference_release_app.command("verify")
def verify_protein_inference_release_archive(
    result: RequestArgument,
    package: UncheckedPackageArgument,
) -> None:
    """Verify archive content; authenticity remains unavailable without injection."""

    parsed = _load_request(
        result,
        TypeAdapter(ProteinInferenceReleaseResult),
        max_bytes=M0308_MAX_CANONICAL_REQUEST_BYTES,
    )
    try:
        package_bytes = _read_protein_inference_release_package(package, parsed)
        verification = M0308Service().verify(parsed, package_bytes)
    except _ProteinInferenceReleaseFileError as error:
        typer.echo(f"protein-inference release verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _emit(verification)
    if not verification.verified:
        raise typer.Exit(code=1)


@app.command("export-schema")
def export_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "register-request",
            "evaluate-request",
            "protocol-schema",
            "metadata-document",
            "protocol-receipt",
            "conformance-profile",
        ],
        typer.Argument(help="Public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable public contract for agents and tools."""

    typer.echo(json.dumps(_contract_schema(contract), indent=2, sort_keys=True))


@app.command("serve")
def serve(
    database: DatabaseOption,
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65_535, help="Bind port.")] = 8000,
) -> None:
    """Run the typed research API."""

    uvicorn.run(create_app(database), host=host, port=port)


if __name__ == "__main__":
    app()
