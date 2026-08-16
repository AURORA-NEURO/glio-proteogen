"""JSON Schema 2020-12 exports for provisional M22-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_06.v1 import (
    M2206_CONTRACT_VERSION,
    M2206_DOSSIER_SHA256,
    M2206_DOSSIER_SLICE,
    M2206_EVIDENCE_CLAIM,
    M2206_GATE,
    M2206_M2205_INPUT_MEDIA_TYPE,
    M2206_MAX_CANONICAL_REQUEST_BYTES,
    M2206_MODULE_ID,
    M2206_OUTPUT_MEDIA_TYPE,
    M2206_OWNER,
    M2206_PARENT,
    M2206_PROVISIONAL_ABI,
    M2206_SAFETY_CLASS,
    ChallengeFinding,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    ChallengeScenario,
    ProteinRnaDiscordanceRobustnessChallengeResult,
    RobustnessConfiguration,
    RobustnessObservation,
    RobustnessSurface,
    SafeFailureReport,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M22-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M2206_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "surface",
    "scenario",
    "observation",
    "safe-failure",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": ChallengeProteinRnaDiscordanceRobustnessRequest,
    "output": ProteinRnaDiscordanceRobustnessChallengeResult,
    "surface": RobustnessSurface,
    "scenario": ChallengeScenario,
    "observation": RobustnessObservation,
    "safe-failure": SafeFailureReport,
    "configuration": RobustnessConfiguration,
    "finding": ChallengeFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M22-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2206_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "dossierSha256": M2206_DOSSIER_SHA256,
        "dossierSlice": M2206_DOSSIER_SLICE,
        "owner": M2206_OWNER,
        "safetyClass": M2206_SAFETY_CLASS,
        "gate": M2206_GATE,
        "strict": True,
        "provisionalAbi": M2206_PROVISIONAL_ABI,
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
        "parentTarget": M2206_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2206_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2206_M2205_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_contrastive_protein_encoder",
        "alternateArchitecture": "offline_benchmark_proteome_autoencoder",
        "fallbackArchitecture": "independent_dual_run_proteome_autoencoder",
        "missingDataChallengeRequired": True,
        "lowInputChallengeRequired": True,
        "corruptionChallengeRequired": True,
        "batchPlatformSiteShiftRequired": True,
        "artifactChallengeRequired": True,
        "novelStateChallengeRequired": True,
        "robustnessSurfaceRequired": True,
        "oodScoreRequired": True,
        "safeFailureReportRequired": True,
        "unsupportedAbstentionRequired": True,
        "evidenceClaim": M2206_EVIDENCE_CLAIM,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2206_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M22-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
