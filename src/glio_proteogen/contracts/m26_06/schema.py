"""JSON Schema 2020-12 exports for provisional M26-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_06.v1 import (
    M2606_CONTRACT_VERSION,
    M2606_GATE,
    M2606_M2605_INPUT_MEDIA_TYPE,
    M2606_MAX_CANONICAL_REQUEST_BYTES,
    M2606_MODULE_ID,
    M2606_OUTPUT_MEDIA_TYPE,
    M2606_OWNER,
    M2606_PARENT,
    M2606_PROVISIONAL_ABI,
    M2606_SAFETY_CLASS,
    AccessDecision,
    AuditEvent,
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
    SafeFailureReport,
    SecurityControlCheck,
    SecurityFinding,
    SecurityPostureRecord,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M26-06:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2606_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "access-decision",
    "audit-event",
    "posture",
    "control",
    "finding",
    "safe-failure",
]
_CONTRACTS: Final = {
    "request": EvaluateProteomicsSecurityAccessRequest,
    "output": ProteomicsSecurityAccessResult,
    "access-decision": AccessDecision,
    "audit-event": AuditEvent,
    "posture": SecurityPostureRecord,
    "control": SecurityControlCheck,
    "finding": SecurityFinding,
    "safe-failure": SafeFailureReport,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M26-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2606_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2606_OWNER,
        "safetyClass": M2606_SAFETY_CLASS,
        "gate": M2606_GATE,
        "strict": True,
        "provisionalAbi": M2606_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2606_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2606_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2606_M2605_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration_cross_attention_genome_protein",
        "alternateArchitecture": "modular_monolith_strict_boundaries_contrastive_protein_encoder",
        "fallbackArchitecture": "offline_signed_release_bundles_proteome_autoencoder",
        "leastPrivilegeRequired": True,
        "encryptionRequired": True,
        "secretsManagementRequired": True,
        "isolationRequired": True,
        "consentEnforcementRequired": True,
        "deIdentificationRequired": True,
        "auditRequired": True,
        "threatDetectionRequired": True,
        "accessDecisionRequired": True,
        "securityPostureRequired": True,
        "safeFailureRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2606_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M26-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
