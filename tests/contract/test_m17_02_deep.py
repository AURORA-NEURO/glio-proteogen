"""Adversarial contract closure tests for provisional M17-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m17_02 import (
    AlignedEvidenceBundle,
    AlignmentAxis,
    AlignmentConfiguration,
    AlignmentPolicy,
    AlignmentStatus,
    AlignVariantPeptideCrossSourceEvidenceRequest,
    Discrepancy,
    DiscrepancyCode,
    SourceModality,
    SourceObservation,
    VariantPeptideCrossSourceAlignmentResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_02_cross_source_alignment_reconciliation as m1702,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_AXES = tuple(AlignmentAxis)


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1702": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label), role="evidence", claim="M17-02 contract evidence"
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m1702",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _policy(*, axes: tuple[AlignmentAxis, ...] = _AXES) -> AlignmentPolicy:
    return AlignmentPolicy(
        required_axes=axes,
        configuration=AlignmentConfiguration(
            configuration_id="configuration.m1702",
            version="1.0.0",
            method="typed deterministic cross-source alignment",
            model_reference=_artifact("model"),
            evidence=(_evidence("configuration"),),
        ),
    )


def _observation(
    observation_id: str, *, status: AlignmentStatus = AlignmentStatus.ALIGNED
) -> SourceObservation:
    return SourceObservation(
        observation_id=observation_id,
        modality=SourceModality.MASS_SPECTROMETRY_PROTEOME,
        sample_id="sample.001",
        time_key="baseline",
        territory="tumor",
        analyte="variant_peptide.V1",
        reference="GRCh38",
        biological_context="glioma",
        source_artifact=_artifact(observation_id),
        status=status,
        evidence=(_evidence(observation_id),),
    )


def _request(*, duplicate: bool = False) -> AlignVariantPeptideCrossSourceEvidenceRequest:
    observations = (_observation("observation.a"), _observation("observation.b"))
    if duplicate:
        observations = (observations[0], observations[0])
    return AlignVariantPeptideCrossSourceEvidenceRequest(
        request_id="request.m1702",
        context=_context(),
        observations=observations,
        policy=_policy(),
        source_artifacts=(_artifact("proteome"), _artifact("genome"), _artifact("transcriptome")),
    )


def test_policy_requires_all_seven_alignment_axes() -> None:
    with pytest.raises(ValidationError, match="all seven"):
        _policy(axes=_AXES[:-1])
    with pytest.raises(ValidationError, match="unique"):
        _policy(axes=(*_AXES, AlignmentAxis.SAMPLE))


def test_discrepancy_axis_and_review_state_are_closed() -> None:
    with pytest.raises(ValidationError, match="reviewable"):
        Discrepancy(
            discrepancy_id="discrepancy.sample",
            code=DiscrepancyCode.SAMPLE_MISMATCH,
            axis=AlignmentAxis.SAMPLE,
            observation_ids=("observation.a", "observation.b"),
            message="sample keys disagree",
            review_required=False,
        )
    with pytest.raises(ValidationError, match="match its alignment axis"):
        Discrepancy(
            discrepancy_id="discrepancy.sample",
            code=DiscrepancyCode.SAMPLE_MISMATCH,
            axis=AlignmentAxis.TIME,
            observation_ids=("observation.a", "observation.b"),
            message="sample keys disagree",
        )


def test_bundle_preserves_discrepancies_and_observation_membership() -> None:
    discrepancy = Discrepancy(
        discrepancy_id="discrepancy.sample",
        code=DiscrepancyCode.SAMPLE_MISMATCH,
        axis=AlignmentAxis.SAMPLE,
        observation_ids=("observation.a", "observation.b"),
        message="sample keys disagree",
    )
    with pytest.raises(ValidationError, match="cannot hide discrepancies"):
        AlignedEvidenceBundle(
            bundle_id="bundle.m1702",
            version="1.0.0",
            observations=(_observation("observation.a"), _observation("observation.b")),
            discrepancy_map=(discrepancy,),
            alignment_status=AlignmentStatus.ALIGNED,
            evidence=(_evidence("bundle"),),
        )
    with pytest.raises(ValidationError, match="belong to"):
        AlignedEvidenceBundle(
            bundle_id="bundle.m1702",
            version="1.0.0",
            observations=(_observation("observation.a"), _observation("observation.b")),
            discrepancy_map=(
                discrepancy.model_copy(update={"observation_ids": ("outside", "outside-2")}),
            ),
            alignment_status=AlignmentStatus.CONFLICTED,
            evidence=(_evidence("bundle"),),
        )


def test_request_observation_ids_are_unique() -> None:
    with pytest.raises(ValidationError, match="observation ids must be unique"):
        _request(duplicate=True)


def test_observation_and_bundle_closures_reject_hidden_or_duplicate_data() -> None:
    with pytest.raises(ValidationError, match="requires evidence"):
        SourceObservation.model_validate(
            _observation("observation.no-evidence").model_dump(mode="python") | {"evidence": ()}
        )
    with pytest.raises(ValidationError, match="observation ids must be unique"):
        AlignedEvidenceBundle(
            bundle_id="bundle.duplicate",
            version="1.0.0",
            observations=(_observation("observation.a"), _observation("observation.a")),
            alignment_status=AlignmentStatus.ALIGNED,
            evidence=(_evidence("bundle"),),
        )
    discrepancy = Discrepancy(
        discrepancy_id="discrepancy.sample",
        code=DiscrepancyCode.SAMPLE_MISMATCH,
        axis=AlignmentAxis.SAMPLE,
        observation_ids=("observation.a", "observation.b"),
        message="sample keys disagree",
    )
    with pytest.raises(ValidationError, match="discrepancy ids must be unique"):
        AlignedEvidenceBundle(
            bundle_id="bundle.duplicate-discrepancy",
            version="1.0.0",
            observations=(_observation("observation.a"), _observation("observation.b")),
            discrepancy_map=(discrepancy, discrepancy),
            alignment_status=AlignmentStatus.CONFLICTED,
            evidence=(_evidence("bundle"),),
        )
    with pytest.raises(ValidationError, match="requires an explicit"):
        AlignedEvidenceBundle(
            bundle_id="bundle.conflicted-empty",
            version="1.0.0",
            observations=(_observation("observation.a"), _observation("observation.b")),
            alignment_status=AlignmentStatus.CONFLICTED,
            evidence=(_evidence("bundle"),),
        )


def test_result_closure_rejects_identity_evidence_status_and_digest_mutations() -> None:
    result = m1702.M1702AlignmentEngine().export(_request())
    with pytest.raises(ValidationError, match="request digest does not bind"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"request_digest": sha256_digest("wrong")}
        )
    with pytest.raises(ValidationError, match="identifier must be derived"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"result_id": "result.wrong"}
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"evidence": ()}
        )
    discrepancy = Discrepancy(
        discrepancy_id="discrepancy.sample",
        code=DiscrepancyCode.SAMPLE_MISMATCH,
        axis=AlignmentAxis.SAMPLE,
        observation_ids=("observation.a", "observation.b"),
        message="sample keys disagree",
    )
    with pytest.raises(ValidationError, match="result discrepancy ids must be unique"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"discrepancy_map": (discrepancy, discrepancy)}
        )
    with pytest.raises(ValidationError, match="finding codes must be unique"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python")
            | {"findings": (result.findings[0], result.findings[0])}
        )
    with pytest.raises(ValidationError, match="reconciled result requires"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"human_review_required": True}
        )
    with pytest.raises(ValidationError, match="must match aligned bundle"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"discrepancy_map": (discrepancy,)}
        )
    conflicted = m1702.M1702AlignmentEngine().export(
        _request().model_copy(
            update={
                "observations": (
                    _observation("observation.a"),
                    _observation("observation.b").model_copy(update={"sample_id": "sample.002"}),
                )
            }
        )
    )
    with pytest.raises(ValidationError, match="abstained result requires"):
        VariantPeptideCrossSourceAlignmentResult.model_validate(
            conflicted.model_dump(mode="python") | {"aligned_bundle": result.aligned_bundle}
        )
    assert canonical_request_digest(result.request) == result.request_digest
