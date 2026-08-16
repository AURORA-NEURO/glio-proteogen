"""JSON Schema 2020-12 exports for provisional M13-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_06.v1 import (
    M1306_CONTRACT_VERSION,
    M1306_GATE,
    M1306_MAX_CANONICAL_REQUEST_BYTES,
    M1306_MODULE_ID,
    M1306_OUTPUT_MEDIA_TYPE,
    M1306_OWNER,
    M1306_PARENT,
    M1306_PROVISIONAL_ABI,
    M1306_SAFETY_CLASS,
    PerturbationFinding,
    PerturbationPolicy,
    PerturbationResponse,
    PerturbationScenario,
    ProteotypePerturbationSensitivityResult,
    SensitivitySurface,
    SimulateProteotypePerturbationRequest,
    SimulatorConfiguration,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M13-06:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1306_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "scenario",
    "response",
    "sensitivity-surface",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": SimulateProteotypePerturbationRequest,
    "output": ProteotypePerturbationSensitivityResult,
    "scenario": PerturbationScenario,
    "response": PerturbationResponse,
    "sensitivity-surface": SensitivitySurface,
    "configuration": SimulatorConfiguration,
    "policy": PerturbationPolicy,
    "finding": PerturbationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M13-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1306_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1306_OWNER,
        "safetyClass": M1306_SAFETY_CLASS,
        "gate": M1306_GATE,
        "strict": True,
        "provisionalAbi": M1306_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "mutationRelabeling": False,
        "disagreementErasure": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M1306_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1306_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_graph_state_space_mechanistic_foundation_assisted",
        "alternateArchitecture": "curated_rule_enrichment_cross_attention",
        "fallbackArchitecture": "orthogonal_consensus_negative_control",
        "boundedPerturbationRequired": True,
        "negativeControlRequired": True,
        "assumptionsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1306_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M13-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
