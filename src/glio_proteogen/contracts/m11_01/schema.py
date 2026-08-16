"""JSON Schema 2020-12 exports for provisional M11-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_01.v1 import (
    M1101_CONTRACT_VERSION,
    M1101_GATE,
    M1101_MAX_CANONICAL_REQUEST_BYTES,
    M1101_MODULE_ID,
    M1101_OUTPUT_MEDIA_TYPE,
    M1101_OWNER,
    M1101_PARENT,
    M1101_PROVISIONAL_ABI,
    M1101_SAFETY_CLASS,
    BiologicalHypothesis,
    CompetingExplanation,
    EvidenceTier,
    FalsificationEvaluation,
    FalsificationRule,
    HypothesisEvaluation,
    HypothesisFinding,
    HypothesisRegistry,
    RegisterVariantPeptideHypothesesRequest,
    VariantPeptideHypothesisRegistryResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M11-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1101_CONTRACT_VERSION
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
    "request": RegisterVariantPeptideHypothesesRequest,
    "output": VariantPeptideHypothesisRegistryResult,
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
    """Return one strict, metadata-only provisional M11-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1101_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1101_OWNER,
        "safetyClass": M1101_SAFETY_CLASS,
        "gate": M1101_GATE,
        "strict": True,
        "provisionalAbi": M1101_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1101_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1101_OUTPUT_MEDIA_TYPE,
        "competingExplanationsRequired": True,
        "falsificationRulesRequired": True,
        "evidenceTiersRequired": True,
        "prohibitedInterpretationsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1101_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M11-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
