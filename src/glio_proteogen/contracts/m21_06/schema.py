"""JSON Schema 2020-12 exports for provisional M21-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_06.v1 import (
    M2106_CONTRACT_VERSION,
    M2106_DOSSIER_SHA256,
    M2106_DOSSIER_SLICE,
    M2106_EVIDENCE_CLAIM,
    M2106_GATE,
    M2106_M2105_INPUT_MEDIA_TYPE,
    M2106_MAX_CANONICAL_REQUEST_BYTES,
    M2106_MODULE_ID,
    M2106_OUTPUT_MEDIA_TYPE,
    M2106_OWNER,
    M2106_PARENT,
    M2106_PROVISIONAL_ABI,
    M2106_SAFETY_CLASS,
    ChallengeComplexActivityRobustnessRequest,
    ChallengeFinding,
    ChallengeScenario,
    ComplexActivityRobustnessChallengeResult,
    RobustnessConfiguration,
    RobustnessObservation,
    RobustnessSurface,
    SafeFailureReport,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M2106_CONTRACT_VERSION
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
    "request": ChallengeComplexActivityRobustnessRequest,
    "output": ComplexActivityRobustnessChallengeResult,
    "surface": RobustnessSurface,
    "scenario": ChallengeScenario,
    "observation": RobustnessObservation,
    "safe-failure": SafeFailureReport,
    "configuration": RobustnessConfiguration,
    "finding": ChallengeFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2106_MODULE_ID,
        "dossierSha256": M2106_DOSSIER_SHA256,
        "dossierSlice": M2106_DOSSIER_SLICE,
        "evidenceClaim": M2106_EVIDENCE_CLAIM,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2106_OWNER,
        "safetyClass": M2106_SAFETY_CLASS,
        "gate": M2106_GATE,
        "strict": True,
        "provisionalAbi": M2106_PROVISIONAL_ABI,
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
        "parentTarget": M2106_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2106_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2106_M2105_INPUT_MEDIA_TYPE,
        "primaryArchitecture": (
            "distributed_simulation_continuous_challenge_cross_attention_genome_protein"
        ),
        "alternateArchitecture": "locked_offline_benchmark_harness_contrastive_protein_encoder",
        "fallbackArchitecture": "independent_dual_run_validation_proteome_autoencoder",
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
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2106_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M21-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
