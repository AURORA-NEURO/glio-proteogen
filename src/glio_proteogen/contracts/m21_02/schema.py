"""JSON Schema 2020-12 exports for provisional M21-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_02.v1 import (
    M2102_CONTRACT_VERSION,
    M2102_DOSSIER_SHA256,
    M2102_DOSSIER_SLICE,
    M2102_GATE,
    M2102_M2101_INPUT_MEDIA_TYPE,
    M2102_MAX_CANONICAL_REQUEST_BYTES,
    M2102_MODULE_ID,
    M2102_OUTPUT_MEDIA_TYPE,
    M2102_OWNER,
    M2102_PARENT,
    M2102_PROVISIONAL_ABI,
    M2102_SAFETY_CLASS,
    ComplexActivitySyntheticTruthResult,
    GenerateComplexActivitySyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    GeneratorFinding,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M2102_CONTRACT_VERSION
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
    "request": GenerateComplexActivitySyntheticTruthRequest,
    "output": ComplexActivitySyntheticTruthResult,
    "corpus": SyntheticTruthCorpus,
    "case": SyntheticTruthCase,
    "manifest": GenerationManifest,
    "configuration": GenerationConfiguration,
    "finding": GeneratorFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2102_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2102_OWNER,
        "safetyClass": M2102_SAFETY_CLASS,
        "gate": M2102_GATE,
        "strict": True,
        "provisionalAbi": M2102_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "dossierSha256": M2102_DOSSIER_SHA256,
        "dossierSlice": M2102_DOSSIER_SLICE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M2102_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2102_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2102_M2101_INPUT_MEDIA_TYPE,
        "primaryArchitecture": (
            "distributed_simulation_continuous_challenge_hierarchical_multilevel_regression"
        ),
        "alternateArchitecture": "locked_offline_benchmark_harness_mixed_effects_cohort_model",
        "fallbackArchitecture": "independent_dual_run_validation_cn_to_protein_regression",
        "analyticallyKnownFixturesRequired": True,
        "semiSyntheticFixturesRequired": True,
        "normalEdgeMissingShiftedAdversarialCoverage": True,
        "deterministicSeedRequired": True,
        "reproducibilityManifestRequired": True,
        "independentRecoveryChecksRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2102_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M21-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
