"""JSON Schema 2020-12 exports for provisional M12-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_04.v1 import (
    M1204_CONTRACT_VERSION,
    M1204_GATE,
    M1204_M1201_RESULT_MEDIA_TYPE,
    M1204_MAX_CANONICAL_REQUEST_BYTES,
    M1204_MODULE_ID,
    M1204_OUTPUT_MEDIA_TYPE,
    M1204_OWNER,
    M1204_PARENT,
    M1204_PROVISIONAL_ABI,
    M1204_SAFETY_CLASS,
    BiomarkerPanelMechanismInferenceResult,
    InferBiomarkerPanelMechanismRequest,
    MechanismEstimate,
    MechanismFinding,
    MechanismInferenceConfiguration,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M12-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M1204_CONTRACT_VERSION
ContractName = Literal["request", "output", "estimate", "configuration", "finding"]
_CONTRACTS: Final = {
    "request": InferBiomarkerPanelMechanismRequest,
    "output": BiomarkerPanelMechanismInferenceResult,
    "estimate": MechanismEstimate,
    "configuration": MechanismInferenceConfiguration,
    "finding": MechanismFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M12-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1204_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1204_OWNER,
        "safetyClass": M1204_SAFETY_CLASS,
        "gate": M1204_GATE,
        "strict": True,
        "provisionalAbi": M1204_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1204_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1204_OUTPUT_MEDIA_TYPE,
        "hypothesisInputMediaType": M1204_M1201_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "variant_peptide_graph",
        "alternateArchitecture": "ptm_aware_state_model",
        "fallbackArchitecture": "proteoform_probabilistic_model",
        "counterEvidenceRequired": True,
        "assumptionsAndAlternativesRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1204_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all five provisional M12-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
