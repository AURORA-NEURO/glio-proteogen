"""JSON Schema 2020-12 exports for provisional M25-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_08.v1 import (
    M2508_CONTRACT_VERSION,
    M2508_DOSSIER_SHA256,
    M2508_DOSSIER_SLICE,
    M2508_GATE,
    M2508_M2506_INPUT_MEDIA_TYPE,
    M2508_M2507_INPUT_MEDIA_TYPE,
    M2508_MAX_CANONICAL_REQUEST_BYTES,
    M2508_MODULE_ID,
    M2508_OUTPUT_MEDIA_TYPE,
    M2508_OWNER,
    M2508_PARENT,
    M2508_PROVISIONAL_ABI,
    M2508_SAFETY_CLASS,
    AdjudicateProteotypeEvidenceGateRequest,
    ApprovalRecord,
    BenchmarkOutcome,
    GateConfiguration,
    GateFinding,
    GateRequirement,
    PostReleaseObligation,
    ProteotypeEvidenceGateResult,
    ResidualRisk,
    SignedReleaseRecord,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M25-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M2508_CONTRACT_VERSION
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
    "request": AdjudicateProteotypeEvidenceGateRequest,
    "output": ProteotypeEvidenceGateResult,
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
    """Return one strict, metadata-only provisional M25-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2508_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2508_OWNER,
        "safetyClass": M2508_SAFETY_CLASS,
        "gate": M2508_GATE,
        "strict": True,
        "provisionalAbi": M2508_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "dossierSha256": M2508_DOSSIER_SHA256,
        "dossierSlice": M2508_DOSSIER_SLICE,
        "declaredUpstreamMediaType": M2508_M2507_INPUT_MEDIA_TYPE,
        "mediaOnlyBoundary": M2508_M2506_INPUT_MEDIA_TYPE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2508_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2508_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "conformalProteotypeRequired": True,
        "baselineStackFallback": True,
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2508_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M25-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
