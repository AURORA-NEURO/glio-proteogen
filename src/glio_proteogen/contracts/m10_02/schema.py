"""JSON Schema 2020-12 exports for provisional M10-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_02.v1 import (
    M1002_CONTRACT_VERSION,
    M1002_GATE,
    M1002_MAX_CANONICAL_REQUEST_BYTES,
    M1002_MODULE_ID,
    M1002_OUTPUT_MEDIA_TYPE,
    M1002_OWNER,
    M1002_PARENT,
    M1002_SAFETY_CLASS,
    AnalysisRepresentation,
    ConstructProteinRnaRepresentationRequest,
    CovariateDefinition,
    FeatureLineage,
    MaskPolicy,
    ProteinRnaRepresentationResult,
    RepresentationConfiguration,
    RepresentationDiagnostic,
    RepresentationFeature,
    ScalingPolicy,
    TransformationStep,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M10-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1002_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "representation",
    "feature",
    "lineage",
    "transformation",
    "scaling",
    "mask",
    "covariate",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": ConstructProteinRnaRepresentationRequest,
    "output": ProteinRnaRepresentationResult,
    "representation": AnalysisRepresentation,
    "feature": RepresentationFeature,
    "lineage": FeatureLineage,
    "transformation": TransformationStep,
    "scaling": ScalingPolicy,
    "mask": MaskPolicy,
    "covariate": CovariateDefinition,
    "configuration": RepresentationConfiguration,
    "diagnostic": RepresentationDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M10-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1002_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1002_OWNER,
        "safetyClass": M1002_SAFETY_CLASS,
        "gate": M1002_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1002_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1002_OUTPUT_MEDIA_TYPE,
        "formalStateInputMediaType": "application/vnd.glio-proteogen.m10-01+json",
        "featureLineageRequired": True,
        "leakageSafeTransformationsRequired": True,
        "scalingMaskCovariatesExplicit": True,
        "deterministicUnderLockedInput": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1002_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eleven provisional M10-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
