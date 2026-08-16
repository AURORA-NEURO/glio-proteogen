"""JSON Schema 2020-12 exports for provisional M17-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_03.v1 import (
    M1703_CONTRACT_VERSION,
    M1703_GATE,
    M1703_M1702_INPUT_MEDIA_TYPE,
    M1703_MAX_CANONICAL_REQUEST_BYTES,
    M1703_MODULE_ID,
    M1703_OUTPUT_MEDIA_TYPE,
    M1703_OWNER,
    M1703_PARENT,
    M1703_PROVISIONAL_ABI,
    M1703_SAFETY_CLASS,
    DisagreementRecord,
    FuseVariantPeptideEvidenceRequest,
    FusionConfiguration,
    FusionFinding,
    IntegratedEvidenceObject,
    SignedPropagationRecord,
    SourceContribution,
    VariantPeptideIntegratedEvidenceResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M17-03:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1703_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "integrated-evidence",
    "source-contribution",
    "disagreement",
    "propagation",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": FuseVariantPeptideEvidenceRequest,
    "output": VariantPeptideIntegratedEvidenceResult,
    "integrated-evidence": IntegratedEvidenceObject,
    "source-contribution": SourceContribution,
    "disagreement": DisagreementRecord,
    "propagation": SignedPropagationRecord,
    "configuration": FusionConfiguration,
    "finding": FusionFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M17-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1703_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1703_OWNER,
        "safetyClass": M1703_SAFETY_CLASS,
        "gate": M1703_GATE,
        "strict": True,
        "provisionalAbi": M1703_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "componentSpecificIntegration": True,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1703_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1703_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1703_M1702_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "protein_complex_graph",
        "alternateArchitecture": "stoichiometric_factorization",
        "fallbackArchitecture": "protein_complex_graph",
        "sourceAttributionRequired": True,
        "reliabilityRequired": True,
        "disagreementPreserved": True,
        "signedPropagationRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1703_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M17-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
