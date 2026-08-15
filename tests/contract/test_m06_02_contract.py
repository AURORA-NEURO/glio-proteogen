"""Strict contract/schema smoke for the provisional M06-02 scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m06_02 import (
    M0602_OUTPUT_MEDIA_TYPE,
    BuildProteinRepresentationRequest,
    FeatureLineageRole,
    FeatureLineageStep,
    RepresentationFeature,
    RepresentationFeatureKind,
    RepresentationObservationState,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    M0602Service,
)


def _reference(label: str, digest_char: str = "a") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.m0602.{label}",
        version="1.0.0",
        digest=f"sha256:{digest_char * 64}",
        media_type="application/json",
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0602.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_reference(label),
    )


def _request() -> BuildProteinRepresentationRequest:
    context = ExecutionContext(
        request_id="request.m0602.smoke",
        actor_id="actor.m0602.smoke",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0602.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=f"sha256:{'b' * 64}",
                evidence=_reference("identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0602.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_reference("consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )
    source = _reference("proteome")
    lineage = FeatureLineageStep(
        lineage_id="lineage.m0602.source",
        role=FeatureLineageRole.SOURCE,
        operation="source-feature",
        transformation_version="1.0.0",
        input_digests=(source.digest,),
        output_feature_ids=("feature.protein-abundance",),
    )
    feature = RepresentationFeature(
        feature_id="feature.protein-abundance",
        version="1.0.0",
        kind=RepresentationFeatureKind.SCALAR,
        state=RepresentationObservationState.OBSERVED,
        unit="normalized-abundance",
        lineage_id=lineage.lineage_id,
        source_digest=source.digest,
        scalar_value=1.5,
    )
    return BuildProteinRepresentationRequest(
        request_id="request.m0602.smoke",
        context=context,
        source_artifacts=(source,),
        features=(feature,),
        lineage=(lineage,),
        configuration_digest=f"sha256:{'d' * 64}",
    )


def test_schema_inventory_is_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == ("request", "output", "feature", "lineage", "mask", "covariate")
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0602_OUTPUT_MEDIA_TYPE


def test_strict_request_and_canonical_digest_smoke() -> None:
    request = _request()
    service = M0602Service()
    assert service.validate_request(request.model_dump(mode="python")) == request
    assert canonical_request_digest(request) == canonical_request_digest(request.model_copy())
    with pytest.raises(NotImplementedError, match="ABI"):
        service.construct(request)
