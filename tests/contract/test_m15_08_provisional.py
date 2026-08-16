"""Focused contract/schema smoke for provisional M15-08."""

import pytest

from glio_proteogen.contracts.m15_08 import (
    M1508_DOSSIER_SHA256,
    M1508_DOSSIER_SLICE,
    M1508_OUTPUT_MEDIA_TYPE,
    M1508_PROVISIONAL_ABI,
    ClaimCeiling,
    MechanismEvidenceLink,
    MechanismEvidenceLinkKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_reconstructable_dossier_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["reconstructableChainRequired"] for schema in schemas.values()
    )
    assert all(schema["x-glio-contract"]["claimCeilingRequired"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["primaryArchitecture"] == "conformal_proteotype"
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "complex_activity"
        and schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m15-07+json")
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1508_OUTPUT_MEDIA_TYPE
    assert M1508_PROVISIONAL_ABI is True
    assert M1508_DOSSIER_SHA256 == (
        "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M1508_DOSSIER_SLICE.endswith(":5384-5424")
    assert all(
        schema["x-glio-contract"]["dossierSha256"] == M1508_DOSSIER_SHA256
        and schema["x-glio-contract"]["dossierSlice"] == M1508_DOSSIER_SLICE
        for schema in schemas.values()
    )


def test_chain_link_and_claim_ceiling_require_explicit_evidence() -> None:
    evidence = EvidenceReference(
        reference=ArtifactReference(
            artifact_id="artifact.mechanism",
            version="1.0.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared mechanism evidence.",
    )
    link = MechanismEvidenceLink(
        link_id="link.input",
        kind=MechanismEvidenceLinkKind.INPUT,
        assertion="Input evidence enters the mechanism chain.",
        predecessor_ids=("source.proteome",),
        evidence=(evidence,),
        assumptions=("Identity and provenance controls are caller-declared.",),
    )
    ceiling = ClaimCeiling(
        maximum_claim="Mechanistic association only.",
        prohibited_interpretations=("No treatment recommendation.",),
        rationale="Evidence does not establish intervention benefit.",
        evidence=(evidence,),
    )
    assert link.evidence
    assert ceiling.prohibited_interpretations
    with pytest.raises(ValueError, match="at least 1 item"):
        ClaimCeiling(
            maximum_claim="Unbounded claim.",
            prohibited_interpretations=(),
            rationale="Missing ceiling.",
            evidence=(evidence,),
        )
