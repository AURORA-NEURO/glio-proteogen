"""Strict contract/schema smoke for the provisional M06-02 scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m06_02 import (
    M0602_OUTPUT_MEDIA_TYPE,
    BuildProteinRepresentationRequest,
    ConstructProteinRepresentationVerification,
    FeatureLineageRole,
    FeatureLineageStep,
    RepresentationCovariate,
    RepresentationFeature,
    RepresentationFeatureKind,
    RepresentationMask,
    RepresentationObservationState,
    RepresentationReplayReason,
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
    assert tuple(schemas) == (
        "request",
        "output",
        "feature",
        "lineage",
        "mask",
        "covariate",
        "verification",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
    output_schema = schemas["output"]
    output_metadata = cast("dict[str, object]", output_schema["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M0602_OUTPUT_MEDIA_TYPE


def test_strict_request_and_canonical_digest_smoke() -> None:
    request = _request()
    service = M0602Service()
    assert service.validate_request(request.model_dump(mode="python")) == request
    assert canonical_request_digest(request) == canonical_request_digest(request.model_copy())
    assert service.validate_request(request) == request


def _rebuild(model: Any, **updates: object) -> Any:
    payload = model.model_dump(mode="python")
    payload.update(updates)
    return type(model).model_validate(payload, strict=True)


def test_lineage_rejects_duplicate_output_ids() -> None:
    with pytest.raises(ValidationError, match="lineage output feature ids"):
        _rebuild(
            _request().lineage[0],
            output_feature_ids=("feature.protein-abundance", "feature.protein-abundance"),
        )


@pytest.mark.parametrize(
    ("kind", "updates", "message"),
    [
        (RepresentationFeatureKind.SCALAR, {"vector": (1.0,)}, "scalar_value"),
        (RepresentationFeatureKind.VECTOR, {"scalar_value": 1.5}, "vector"),
        (RepresentationFeatureKind.CATEGORICAL, {"scalar_value": 1.5}, "category"),
    ],
)
def test_observed_feature_requires_kind_value(
    kind: RepresentationFeatureKind,
    updates: dict[str, object],
    message: str,
) -> None:
    feature = _request().features[0]
    changes: dict[str, object] = {
        "kind": kind,
        "scalar_value": None,
        "vector": (),
        "category": None,
    }
    changes.update(updates)
    with pytest.raises(ValidationError, match=message):
        _rebuild(feature, **changes)


def test_non_observed_feature_cannot_carry_value() -> None:
    feature = _request().features[0]
    with pytest.raises(ValidationError, match="non-observed"):
        _rebuild(feature, state=RepresentationObservationState.MISSING)


def test_observed_feature_rejects_multiple_value_representations() -> None:
    feature = _request().features[0]
    with pytest.raises(ValidationError, match="exactly one"):
        _rebuild(feature, vector=(2.0,))


def test_request_rejects_duplicate_features_and_unbound_lineage() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="feature ids must be unique"):
        _rebuild(request, features=(request.features[0], request.features[0]))
    foreign_feature = _rebuild(request.features[0], lineage_id="lineage.foreign")
    with pytest.raises(ValidationError, match="every feature must bind"):
        _rebuild(request, features=(foreign_feature,))


def test_request_rejects_unknown_masks_and_duplicate_covariates() -> None:
    request = _request()
    mask = RepresentationMask(
        feature_id="feature.unknown",
        state=RepresentationObservationState.MISSING,
        reason="not observed",
    )
    with pytest.raises(ValidationError, match="unknown feature"):
        _rebuild(request, masks=(mask,))
    covariate = RepresentationCovariate(
        covariate_id="covariate.batch",
        version="1.0.0",
        unit="batch",
        value="A",
        source_digest=request.source_artifacts[0].digest,
    )
    with pytest.raises(ValidationError, match="covariate ids"):
        _rebuild(request, covariates=(covariate, covariate))


def test_request_rejects_undeclared_feature_source_digest() -> None:
    request = _request()
    feature = _rebuild(
        request.features[0],
        source_digest="sha256:" + "f" * 64,
    )
    with pytest.raises(ValidationError, match="source digest"):
        _rebuild(request, features=(feature,))


def test_replay_verification_flags_are_closed() -> None:
    with pytest.raises(ValidationError, match="verified must match"):
        ConstructProteinRepresentationVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest="sha256:" + "a" * 64,
            reason=RepresentationReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValidationError, match="failed replay"):
        ConstructProteinRepresentationVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest="sha256:" + "a" * 64,
            reason=RepresentationReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValidationError, match="verified must match replay reason"):
        ConstructProteinRepresentationVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            reason=RepresentationReplayReason.VERIFIED,
        )
    with pytest.raises(ValidationError, match="requires a result digest"):
        ConstructProteinRepresentationVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=RepresentationReplayReason.VERIFIED,
        )
