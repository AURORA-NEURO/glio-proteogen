"""Contract and schema gates for provisional M16-07."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m16_07 import (
    CompatibilityReport,
    CompatibilityStatus,
    DownstreamField,
    ExportConfiguration,
    ExportPolicy,
    FieldSupportStatus,
    SignedDownstreamContract,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1607": label}),
        media_type=media_type,
    )


def _field(label: str, owner: str = "owner.proteogenomic") -> DownstreamField:
    return DownstreamField(
        field_id=f"field.{label}",
        name=label,
        value_type="string",
        owner=owner,
        support_status=FieldSupportStatus.SUPPORTED,
        source_artifact=_artifact(label),
    )


def _configuration() -> ExportConfiguration:
    return ExportConfiguration(
        configuration_id="configuration.export",
        version="1.0.0",
        method="typed signed export",
        signature_reference=_artifact("signature"),
    )


def _policy() -> ExportPolicy:
    return ExportPolicy(
        consumer_id="consumer.review",
        allowed_owner="owner.proteogenomic",
        required_media_type="application/json",
        configuration=_configuration(),
    )


def test_m1607_schemas_are_complete_and_provisional() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 8
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["provisionalAbi"] is True
    assert metadata["versionedImmutableRequired"] is True
    assert metadata["consentAwareRequired"] is True
    assert metadata["ownershipSemanticsRequired"] is True


def test_signed_contract_requires_compatible_consumer_and_explicit_ownership() -> None:
    field = _field("proteotype")
    compatibility = CompatibilityReport(
        report_id="compatibility.report",
        version="1.0.0",
        status=CompatibilityStatus.COMPATIBLE,
        consumer_id="consumer.review",
        accepted_field_ids=(field.field_id,),
        reasons=("schema and ownership match",),
    )
    signed = SignedDownstreamContract(
        contract_id="contract.export",
        version="1.0.0",
        consumer_id="consumer.review",
        fields=(field,),
        ownership=(field.owner,),
        compatibility=compatibility,
        signature=_artifact("signature"),
        signature_algorithm="sha256-caller-declared",
        evidence=(
            EvidenceReference(
                reference=_artifact("signature"), role="evidence", claim="signed export"
            ),
        ),
    )
    assert signed.immutable is True
    assert signed.compatibility.accepted_field_ids == (field.field_id,)

    with pytest.raises(ValidationError, match="consumer must match"):
        SignedDownstreamContract.model_validate(
            signed.model_dump(mode="python")
            | {"compatibility": compatibility.model_copy(update={"consumer_id": "consumer.other"})}
        )
    with pytest.raises(ValidationError, match="ownership must be explicit"):
        SignedDownstreamContract.model_validate(
            signed.model_dump(mode="python") | {"ownership": ("owner.other",)}
        )
