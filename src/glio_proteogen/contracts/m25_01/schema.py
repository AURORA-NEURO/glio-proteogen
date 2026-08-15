"""JSON Schema 2020-12 exports for provisional M25-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_01.v1 import (
    M2501_CONTRACT_VERSION,
    M2501_GATE,
    M2501_MAX_CANONICAL_REQUEST_BYTES,
    M2501_MODULE_ID,
    M2501_OUTPUT_MEDIA_TYPE,
    M2501_OWNER,
    M2501_PARENT,
    M2501_PROVISIONAL_ABI,
    M2501_SAFETY_CLASS,
    AdjudicationRecord,
    BenchmarkConfiguration,
    CurateProteotypeReferenceTruthRequest,
    CurationFinding,
    EndpointDefinition,
    InclusionDecision,
    ProteotypeReferenceTruthResult,
    ReferenceEntry,
    ReferenceTruthPackage,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M25-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M2501_CONTRACT_VERSION
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
    "request": CurateProteotypeReferenceTruthRequest,
    "output": ProteotypeReferenceTruthResult,
    "reference": ReferenceEntry,
    "endpoint": EndpointDefinition,
    "inclusion": InclusionDecision,
    "adjudication": AdjudicationRecord,
    "configuration": BenchmarkConfiguration,
    "package": ReferenceTruthPackage,
    "finding": CurationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M25-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2501_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2501_OWNER,
        "safetyClass": M2501_SAFETY_CLASS,
        "gate": M2501_GATE,
        "strict": True,
        "provisionalAbi": M2501_PROVISIONAL_ABI,
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
        "parentTarget": M2501_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2501_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "primaryMethod": "sparse_nmf",
        "alternateMethod": "sparse_nmf",
        "fallbackMethod": "pca_ica_baseline",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2501_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M25-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
