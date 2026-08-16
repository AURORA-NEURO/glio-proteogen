"""JSON Schema 2020-12 exports for provisional M24-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_08.v1 import (
    M2408_CONTRACT_VERSION,
    M2408_DOSSIER_SHA256,
    M2408_DOSSIER_SLICE,
    M2408_GATE,
    M2408_MAX_CANONICAL_REQUEST_BYTES,
    M2408_MODULE_ID,
    M2408_OUTPUT_MEDIA_TYPE,
    M2408_OWNER,
    M2408_PARENT,
    M2408_PROVISIONAL_ABI,
    M2408_SAFETY_CLASS,
    AdjudicateBiomarkerPanelEvidenceGateRequest,
    ApprovalRecord,
    BenchmarkOutcome,
    BiomarkerPanelEvidenceGateResult,
    GateConfiguration,
    GateFinding,
    GateRequirement,
    PostReleaseObligation,
    ResidualRisk,
    SignedReleaseRecord,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M24-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M2408_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "requirement",
    "benchmark",
    "risk",
    "approval",
    "release-record",
    "configuration",
    "obligation",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdjudicateBiomarkerPanelEvidenceGateRequest,
    "output": BiomarkerPanelEvidenceGateResult,
    "requirement": GateRequirement,
    "benchmark": BenchmarkOutcome,
    "risk": ResidualRisk,
    "approval": ApprovalRecord,
    "release-record": SignedReleaseRecord,
    "configuration": GateConfiguration,
    "obligation": PostReleaseObligation,
    "finding": GateFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M24-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2408_MODULE_ID,
        "dossierSha256": M2408_DOSSIER_SHA256,
        "dossierSlice": M2408_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2408_OWNER,
        "safetyClass": M2408_SAFETY_CLASS,
        "gate": M2408_GATE,
        "strict": True,
        "provisionalAbi": M2408_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2408_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2408_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "networkFactorHybridRequired": True,
        "bayesianModelAveragingAvailable": True,
        "baselineStackFallback": True,
        "bayesianModelAveragingRequired": True,
        "disagreementReviewRequired": True,
        "traceabilityRequired": True,
        "qualityControlsRequired": True,
        "riskControlsRequired": True,
        "benchmarkOutcomesRequired": True,
        "claimCeilingRequired": True,
        "residualRiskRequired": True,
        "approvalRequired": True,
        "postReleaseObligationsRequired": True,
        "signedReleaseRecordRequired": True,
        "noUnresolvedCriticalRequirements": True,
        "uncertaintyRequired": True,
        "humanReviewRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2408_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M24-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
