"""JSON Schema 2020-12 exports for provisional M24-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06.v1 import (
    M2406_CONTRACT_VERSION,
    M2406_GATE,
    M2406_M2405_INPUT_MEDIA_TYPE,
    M2406_MAX_CANONICAL_REQUEST_BYTES,
    M2406_MODULE_ID,
    M2406_OUTPUT_MEDIA_TYPE,
    M2406_OWNER,
    M2406_PARENT,
    M2406_PROVISIONAL_ABI,
    M2406_SAFETY_CLASS,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeFinding,
    ChallengeScenario,
    RobustnessConfiguration,
    RobustnessObservation,
    RobustnessSurface,
    SafeFailureReport,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M24-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M2406_CONTRACT_VERSION
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
    "request": ChallengeBiomarkerPanelRobustnessRequest,
    "output": BiomarkerPanelRobustnessChallengeResult,
    "surface": RobustnessSurface,
    "scenario": ChallengeScenario,
    "observation": RobustnessObservation,
    "safe-failure": SafeFailureReport,
    "configuration": RobustnessConfiguration,
    "finding": ChallengeFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M24-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2406_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2406_OWNER,
        "safetyClass": M2406_SAFETY_CLASS,
        "gate": M2406_GATE,
        "strict": True,
        "provisionalAbi": M2406_PROVISIONAL_ABI,
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
        "parentTarget": M2406_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2406_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2406_M2405_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge_proteome_autoencoder",
        "alternateArchitecture": (
            "locked_offline_benchmark_harness_masked_proteome_foundation_model"
        ),
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2406_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M24-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
