"""JSON Schema 2020-12 exports for provisional M21-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_01.v1 import (
    M2101_CONTRACT_VERSION,
    M2101_GATE,
    M2101_MAX_CANONICAL_REQUEST_BYTES,
    M2101_MODULE_ID,
    M2101_OUTPUT_MEDIA_TYPE,
    M2101_OWNER,
    M2101_PARENT,
    M2101_PROVISIONAL_ABI,
    M2101_SAFETY_CLASS,
    AdjudicationRecord,
    BenchmarkConfiguration,
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
    CurationFinding,
    EndpointDefinition,
    InclusionDecision,
    ReferenceEntry,
    ReferenceTruthPackage,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M2101_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "reference",
    "endpoint",
    "inclusion",
    "adjudication",
    "configuration",
    "package",
    "finding",
]
_CONTRACTS: Final = {
    "request": CurateComplexActivityReferenceTruthRequest,
    "output": ComplexActivityReferenceTruthResult,
    "reference": ReferenceEntry,
    "endpoint": EndpointDefinition,
    "inclusion": InclusionDecision,
    "adjudication": AdjudicationRecord,
    "configuration": BenchmarkConfiguration,
    "package": ReferenceTruthPackage,
    "finding": CurationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2101_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2101_OWNER,
        "safetyClass": M2101_SAFETY_CLASS,
        "gate": M2101_GATE,
        "strict": True,
        "provisionalAbi": M2101_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M2101_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2101_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "referenceTruthRequired": True,
        "benchmarkPackageRequired": True,
        "controlsRequired": True,
        "adjudicationRequired": True,
        "endpointDefinitionRequired": True,
        "provenanceRequired": True,
        "inclusionAndChallengeSetRequired": True,
        "leakageAuditRequired": True,
        "lockProcedureRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2101_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M21-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
