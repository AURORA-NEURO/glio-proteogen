"""JSON Schema 2020-12 exports for provisional M06-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_02.v1 import (
    M0602_CONTRACT_VERSION,
    M0602_GATE,
    M0602_MAX_CANONICAL_REQUEST_BYTES,
    M0602_MODULE_ID,
    M0602_OUTPUT_MEDIA_TYPE,
    M0602_OWNER,
    M0602_PARENT,
    M0602_PROVISIONAL_ABI,
    M0602_SAFETY_CLASS,
    BuildProteinRepresentationRequest,
    ConstructProteinRepresentationResult,
    ConstructProteinRepresentationVerification,
    FeatureLineageStep,
    RepresentationCovariate,
    RepresentationFeature,
    RepresentationMask,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-02:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0602_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature",
    "lineage",
    "mask",
    "covariate",
    "verification",
]
_CONTRACTS: Final = {
    "request": BuildProteinRepresentationRequest,
    "output": ConstructProteinRepresentationResult,
    "feature": RepresentationFeature,
    "lineage": FeatureLineageStep,
    "mask": RepresentationMask,
    "covariate": RepresentationCovariate,
    "verification": ConstructProteinRepresentationVerification,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict schema; this inventory is not frozen ABI."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0602_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0602_OWNER,
        "safetyClass": M0602_SAFETY_CLASS,
        "gate": M0602_GATE,
        "strict": True,
        "provisionalAbi": M0602_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "provisionalLimits": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "leakageSafeTransformations": True,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "kinaseActivityInference": False,
        "parentTarget": M0602_PARENT,
        "outputMediaType": M0602_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0602_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
