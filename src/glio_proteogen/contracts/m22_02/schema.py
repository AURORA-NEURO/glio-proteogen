"""JSON Schema 2020-12 exports for provisional M22-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_02.v1 import (
    M2202_CONTRACT_VERSION,
    M2202_DOSSIER_SHA256,
    M2202_DOSSIER_SLICE,
    M2202_EVIDENCE_CLAIM,
    M2202_GATE,
    M2202_M2201_INPUT_MEDIA_TYPE,
    M2202_MAX_CANONICAL_REQUEST_BYTES,
    M2202_MODULE_ID,
    M2202_OUTPUT_MEDIA_TYPE,
    M2202_OWNER,
    M2202_PARENT,
    M2202_PROVISIONAL_ABI,
    M2202_SAFETY_CLASS,
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    GeneratorFinding,
    ProteinRnaDiscordanceSyntheticTruthResult,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M22-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M2202_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "corpus",
    "case",
    "manifest",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    "output": ProteinRnaDiscordanceSyntheticTruthResult,
    "corpus": SyntheticTruthCorpus,
    "case": SyntheticTruthCase,
    "manifest": GenerationManifest,
    "configuration": GenerationConfiguration,
    "finding": GeneratorFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M22-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2202_MODULE_ID,
        "dossierSha256": M2202_DOSSIER_SHA256,
        "dossierSlice": M2202_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2202_OWNER,
        "safetyClass": M2202_SAFETY_CLASS,
        "gate": M2202_GATE,
        "strict": True,
        "provisionalAbi": M2202_PROVISIONAL_ABI,
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
        "parentTarget": M2202_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2202_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2202_M2201_INPUT_MEDIA_TYPE,
        "primaryArchitecture": (
            "distributed_simulation_continuous_challenge_mixed_effects_cohort_model"
        ),
        "alternateArchitecture": (
            "locked_offline_benchmark_harness_transcript_protein_residual_model"
        ),
        "fallbackArchitecture": "independent_dual_run_validation_cn_to_protein_regression",
        "analyticallyKnownFixturesRequired": True,
        "semiSyntheticFixturesRequired": True,
        "normalEdgeMissingShiftedAdversarialCoverage": True,
        "deterministicSeedRequired": True,
        "reproducibilityManifestRequired": True,
        "independentRecoveryChecksRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
        "evidenceClaim": M2202_EVIDENCE_CLAIM,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2202_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M22-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
