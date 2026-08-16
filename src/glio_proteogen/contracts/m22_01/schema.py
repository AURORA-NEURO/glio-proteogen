"""JSON Schema 2020-12 exports for provisional M22-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_01.v1 import (
    M2201_CONTRACT_VERSION,
    M2201_DOSSIER_SHA256,
    M2201_DOSSIER_SLICE,
    M2201_GATE,
    M2201_M2108_INPUT_MEDIA_TYPE,
    M2201_MAX_CANONICAL_REQUEST_BYTES,
    M2201_MODULE_ID,
    M2201_OUTPUT_MEDIA_TYPE,
    M2201_OWNER,
    M2201_PARENT,
    M2201_PROVISIONAL_ABI,
    M2201_SAFETY_CLASS,
    AdjudicationRecord,
    BenchmarkConfiguration,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
    CurationFinding,
    EndpointDefinition,
    InclusionDecision,
    ProteinRnaDiscordanceReferenceTruthResult,
    ReferenceEntry,
    ReferenceTruthPackage,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M22-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M2201_CONTRACT_VERSION
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
    "request": CurateProteinRnaDiscordanceReferenceTruthRequest,
    "output": ProteinRnaDiscordanceReferenceTruthResult,
    "reference": ReferenceEntry,
    "endpoint": EndpointDefinition,
    "inclusion": InclusionDecision,
    "adjudication": AdjudicationRecord,
    "configuration": BenchmarkConfiguration,
    "package": ReferenceTruthPackage,
    "finding": CurationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M22-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2201_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "dossierSha256": M2201_DOSSIER_SHA256,
        "dossierSlice": M2201_DOSSIER_SLICE,
        "owner": M2201_OWNER,
        "safetyClass": M2201_SAFETY_CLASS,
        "gate": M2201_GATE,
        "strict": True,
        "provisionalAbi": M2201_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2201_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2201_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2201_M2108_INPUT_MEDIA_TYPE,
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2201_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M22-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
