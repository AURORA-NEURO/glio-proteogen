"""Frozen public-contract checks for GLIO-PROTEOGEN-M05-02."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import glio_proteogen.contracts.m05_02 as m0502
from glio_proteogen.contracts.m05_02 import (
    ApprovedPtmLocalizationLineageConfiguration,
    PtmLocalizationIdentityLineageFindingAction,
    PtmLocalizationIdentityLineageFindingCode,
    PtmLocalizationLineageArtifactRole,
    PtmLocalizationLineageDisposition,
    PtmLocalizationLineageEvidenceState,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "approved-configuration",
    "artifact-claim",
    "derivation",
    "graph",
    "finding",
    "receipt",
)


def _approved_configuration_payload() -> dict[str, object]:
    return {
        "configuration_id": f"configuration.{'1' * 64}",
        "protocol_result_version": "1.0.0",
        "configuration_digest": f"sha256:{'2' * 64}",
        "reference_bundle_digest": f"sha256:{'3' * 64}",
        "assay_specimen_policy_digest": f"sha256:{'4' * 64}",
        "evidence": {
            "artifact_id": f"evidence.{'5' * 64}",
            "version": "1.0.0",
            "digest": f"sha256:{'6' * 64}",
            "media_type": ("application/vnd.glio-proteogen.m05-02.approved-configuration+json"),
        },
    }


def test_schema_inventory_and_metadata_are_frozen() -> None:
    schemas = contract_json_schemas()

    assert tuple(schemas) == _SCHEMA_NAMES
    for name, schema in schemas.items():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-02:1.0.0:" + name
        )
        metadata = schema["x-glio-contract"]
        assert metadata["moduleId"] == "GLIO-PROTEOGEN-M05-02"
        assert metadata["contractVersion"] == "1.0.0"
        assert metadata["strict"] is True
        assert metadata["identityInference"] is False
        assert metadata["consentInference"] is False
        assert metadata["kinaseActivityInference"] is False
        assert metadata["variantPeptideEmission"] is False
        json.dumps(schema)
    assert contract_json_schema("request")["x-glio-contract"]["maxRequestBytes"] == 4 * 1024 * 1024


def test_closed_enum_values_match_the_frozen_abi() -> None:
    assert tuple(item.value for item in PtmLocalizationLineageArtifactRole) == (
        "mass_spectrometry_proteome_manifest",
        "genome_manifest",
        "transcriptome_manifest",
        "ptm_annotation_manifest",
        "variant_peptide_input_bundle",
    )
    assert tuple(item.value for item in PtmLocalizationLineageEvidenceState) == (
        "observed",
        "missing",
        "indeterminate",
        "unsupported",
        "redacted",
    )
    assert tuple(item.value for item in PtmLocalizationLineageDisposition) == (
        "reconciled",
        "quarantined",
        "abstained",
    )
    assert set(PtmLocalizationIdentityLineageFindingAction) == {
        PtmLocalizationIdentityLineageFindingAction.RECORD,
        PtmLocalizationIdentityLineageFindingAction.QUARANTINE,
        PtmLocalizationIdentityLineageFindingAction.ABSTAIN,
    }
    assert len(PtmLocalizationIdentityLineageFindingCode) == m0502.M0502_FINDING_CODE_COUNT


def test_approved_configuration_is_strict_owned_and_immutable() -> None:
    approved = ApprovedPtmLocalizationLineageConfiguration.model_validate(
        _approved_configuration_payload(), strict=True
    )
    assert isinstance(approved.evidence, ArtifactReference)
    with pytest.raises(ValidationError):
        approved.configuration_id = f"configuration.{'7' * 64}"  # type: ignore[misc]

    coerced = _approved_configuration_payload()
    coerced["protocol_result_version"] = 1
    with pytest.raises(ValidationError):
        ApprovedPtmLocalizationLineageConfiguration.model_validate(coerced, strict=True)

    reflected = _approved_configuration_payload()
    reflected_evidence = reflected["evidence"]
    assert isinstance(reflected_evidence, dict)
    reflected_evidence["artifact_id"] = "recursive-canary"
    with pytest.raises(ValidationError):
        ApprovedPtmLocalizationLineageConfiguration.model_validate(reflected, strict=True)


def test_private_digest_sentinel_is_not_public_abi() -> None:
    assert "M0502_ZERO_DIGEST" not in m0502.__all__
    assert not hasattr(m0502, "M0502_ZERO_DIGEST")
