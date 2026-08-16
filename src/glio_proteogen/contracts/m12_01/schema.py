"""JSON Schema 2020-12 exports for provisional M12-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_01.v1 import (
    M1201_CONTRACT_VERSION,
    M1201_GATE,
    M1201_MAX_CANONICAL_REQUEST_BYTES,
    M1201_MODULE_ID,
    M1201_OUTPUT_MEDIA_TYPE,
    M1201_OWNER,
    M1201_PARENT,
    M1201_PROVISIONAL_ABI,
    M1201_SAFETY_CLASS,
    BiologicalHypothesis,
    BiomarkerPanelHypothesisRegistryResult,
    CompetingExplanation,
    EvidenceTier,
    FalsificationEvaluation,
    FalsificationRule,
    HypothesisEvaluation,
    HypothesisFinding,
    HypothesisRegistry,
    RegisterBiomarkerPanelHypothesesRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M12-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1201_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "hypothesis",
    "competing-explanation",
    "falsification-rule",
    "evidence-tier",
    "registry",
    "evaluation",
    "falsification-evaluation",
    "finding",
]
_CONTRACTS: Final = {
    "request": RegisterBiomarkerPanelHypothesesRequest,
    "output": BiomarkerPanelHypothesisRegistryResult,
    "hypothesis": BiologicalHypothesis,
    "competing-explanation": CompetingExplanation,
    "falsification-rule": FalsificationRule,
    "evidence-tier": EvidenceTier,
    "registry": HypothesisRegistry,
    "evaluation": HypothesisEvaluation,
    "falsification-evaluation": FalsificationEvaluation,
    "finding": HypothesisFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M12-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1201_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1201_OWNER,
        "safetyClass": M1201_SAFETY_CLASS,
        "gate": M1201_GATE,
        "strict": True,
        "provisionalAbi": M1201_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1201_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1201_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_factor_analysis",
        "alternateArchitecture": "pca_ica_baseline",
        "fallbackArchitecture": "orthogonal_consensus_negative_control",
        "competingExplanationsRequired": True,
        "falsificationRulesRequired": True,
        "evidenceTiersRequired": True,
        "prohibitedInterpretationsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1201_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M12-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
