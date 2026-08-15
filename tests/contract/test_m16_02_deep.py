"""Adversarial contract and provenance tests for M16-02."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m16_02 import (
    M1602_M1601_INPUT_MEDIA_TYPE,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentFindingCode,
    AlignmentLink,
    AlignmentLinkStatus,
    DiscrepancyResolutionStatus,
    DiscrepancySeverity,
    ProteinRnaDiscordanceAlignmentResult,
    ReconcileCrossSourceAlignmentRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_02_cross_source_alignment_reconciliation import (
    M1602AlignmentEngine,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1602": label}),
        media_type=media_type,
    )


def _context(*, accepted: bool = True) -> ExecutionContext:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ExecutionContext(
        request_id="request.m1602",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=identity,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _request(
    *, accepted: bool = True, label: str = "aligned"
) -> ReconcileCrossSourceAlignmentRequest:
    return ReconcileCrossSourceAlignmentRequest(
        request_id="request.m1602",
        context=_context(accepted=accepted),
        upstream_result=_artifact("upstream", M1602_M1601_INPUT_MEDIA_TYPE),
        configuration=AlignmentConfiguration(
            configuration_id=f"configuration.alignment.{label}",
            version="1.0.0",
            reference_artifact=_artifact("reference"),
            enabled_dimensions=tuple(AlignmentDimension),
            conflict_policy="locked reference precedence",
        ),
        source_artifacts=(_artifact("proteome"), _artifact("transcriptome"), _artifact("ptm")),
    )


def test_request_binding_and_source_identity_are_closed() -> None:
    request = _request()
    assert request.upstream_result.media_type == M1602_M1601_INPUT_MEDIA_TYPE
    duplicate = _artifact("proteome")
    with pytest.raises(ValidationError, match="source artifact references"):
        ReconcileCrossSourceAlignmentRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (*request.source_artifacts, duplicate)}
        )
    with pytest.raises(ValidationError, match="bind the provisional M16-01"):
        ReconcileCrossSourceAlignmentRequest.model_validate(
            request.model_dump(mode="python") | {"upstream_result": _artifact("wrong")}
        )


def test_alignment_link_rejects_duplicate_source_references() -> None:
    source = _artifact("source")
    with pytest.raises(ValidationError, match="source references must be unique"):
        AlignmentLink(
            link_id="link.invalid",
            dimensions=(AlignmentDimension.SAMPLE,),
            source_artifacts=(source, source),
            canonical_key="sample-1",
            observed_values=("sample-1",),
            status=AlignmentLinkStatus.ALIGNED,
        )


def test_uncertainty_and_provenance_expose_all_required_dimensions() -> None:
    request = _request()
    digest = sha256_digest(request.model_dump(mode="json"))
    uncertainty = expected_uncertainty(supported=True)
    assert uncertainty.transport.probability == 0.9
    metadata = cast("object", uncertainty)
    assert metadata is not None
    provenance = expected_provenance(request, digest)
    assert len(provenance.control_decisions) == 7
    assert provenance.configuration_digest == request.configuration.reference_artifact.digest


def test_result_closure_rejects_wrong_request_digest_and_missing_evidence() -> None:
    result = M1602AlignmentEngine().reconcile(_request())
    with pytest.raises(ValidationError, match="request digest"):
        ProteinRnaDiscordanceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"request_digest": sha256_digest("wrong")}
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        ProteinRnaDiscordanceAlignmentResult.model_validate(
            result.model_dump(mode="python") | {"evidence": ()}
        )


def test_bundle_closure_rejects_unknown_link_and_duplicate_findings() -> None:
    source = _artifact("source")
    bundle = AlignedEvidenceBundle(
        bundle_id="bundle.test",
        version="1.0.0",
        links=(
            AlignmentLink(
                link_id="link.test",
                dimensions=(AlignmentDimension.SAMPLE,),
                source_artifacts=(source,),
                canonical_key="sample-1",
                observed_values=("sample-1",),
                status=AlignmentLinkStatus.ALIGNED,
            ),
        ),
        configuration=AlignmentConfiguration(
            configuration_id="configuration.test",
            version="1.0.0",
            reference_artifact=_artifact("reference"),
            enabled_dimensions=(AlignmentDimension.SAMPLE,),
            conflict_policy="locked reference precedence",
        ),
    )
    with pytest.raises(ValidationError, match="unknown alignment link"):
        AlignedEvidenceBundle.model_validate(
            bundle.model_dump(mode="python")
            | {
                "discrepancies": (
                    {
                        "discrepancy_id": "discrepancy.unknown",
                        "dimensions": (AlignmentDimension.SAMPLE,),
                        "source_link_ids": ("link.missing",),
                        "description": "unknown link",
                        "severity": DiscrepancySeverity.WARNING,
                        "resolution_status": DiscrepancyResolutionStatus.OPEN,
                    },
                )
            }
        )
    result = M1602AlignmentEngine().reconcile(_request())
    with pytest.raises(ValidationError, match="finding codes must be unique"):
        ProteinRnaDiscordanceAlignmentResult.model_validate(
            result.model_dump(mode="python")
            | {
                "findings": (
                    AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                )
            }
        )
