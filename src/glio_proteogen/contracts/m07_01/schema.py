"""JSON Schema 2020-12 exports for provisional M07-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_01.v1 import (
    M0701_CONTRACT_VERSION,
    M0701_GATE,
    M0701_MAX_CANONICAL_REQUEST_BYTES,
    M0701_MODULE_ID,
    M0701_OUTPUT_MEDIA_TYPE,
    M0701_OWNER,
    M0701_PARENT,
    M0701_PROVISIONAL_ABI,
    M0701_SAFETY_CLASS,
    CopyNumberFeatureDefinition,
    CopyNumberFeatureValue,
    CopyNumberInvariant,
    CopyNumberInvariantResult,
    CopyNumberMigrationRule,
    FormalCopyNumberStateSchema,
    ValidateCopyNumberStateRequest,
    ValidateCopyNumberStateResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-01:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0701_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "schema",
    "feature-definition",
    "feature-value",
    "invariant",
    "invariant-result",
    "migration",
]
_CONTRACTS: Final = {
    "request": ValidateCopyNumberStateRequest,
    "output": ValidateCopyNumberStateResult,
    "schema": FormalCopyNumberStateSchema,
    "feature-definition": CopyNumberFeatureDefinition,
    "feature-value": CopyNumberFeatureValue,
    "invariant": CopyNumberInvariant,
    "invariant-result": CopyNumberInvariantResult,
    "migration": CopyNumberMigrationRule,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict schema; this inventory is not frozen ABI."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0701_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0701_OWNER,
        "safetyClass": M0701_SAFETY_CLASS,
        "gate": M0701_GATE,
        "strict": True,
        "provisionalAbi": M0701_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "provisionalLimits": True,
        "featureCatalogueFrozen": False,
        "migrationRulesFrozen": False,
        "externalContentTraversal": False,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "kinaseActivityInference": False,
        "parentTarget": M0701_PARENT,
        "outputMediaType": M0701_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0701_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
