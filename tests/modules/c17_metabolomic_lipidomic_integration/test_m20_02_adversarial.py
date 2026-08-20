"""Adversarial closure tests for M20-02 negative-space behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_02 import (
    AlignmentDimension,
    AlignmentFinding,
    AlignmentFindingCode,
    AlignmentObservation,
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteinSubtypeSourcesRequest,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
    ProteinSubtypeAlignmentResult,
)
from glio_proteogen.contracts.m20_02.canonical import canonical_request_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_02_cross_source_alignment_reconciliation import (  # noqa: E501
    M2002Engine,
)
from tests.modules.c17_metabolomic_lipidomic_integration.test_m20_02_engine import (
    _artifact,
    _evidence,
    _request,
)


def test_missing_dimension_abstains_without_constructing_partial_bundle() -> None:
    request = _request().model_copy(
        update={
            "observations": tuple(
                item
                for item in _request().observations
                if item.dimension is not AlignmentDimension.TIME
            )
        }
    )
    result = M2002Engine().resolve(request)
    assert result.aligned_bundle is None
    assert result.human_review_required is True
    assert result.findings == ()


def test_unresolved_critical_discrepancy_is_preserved_and_abstains() -> None:
    discrepancy = DiscrepancyMapEntry(
        discrepancy_id="discrepancy.reference",
        dimension=AlignmentDimension.REFERENCE,
        source_ids=("artifact.source-a", "artifact.source-b"),
        severity=DiscrepancySeverity.CRITICAL,
        description="caller-declared reference versions disagree",
        evidence=(_evidence("discrepancy.reference"),),
    )
    request = _request().model_copy(update={"discrepancies": (discrepancy,)})
    result = M2002Engine().resolve(request)
    assert result.aligned_bundle is None
    assert result.findings[0].code.value == "discrepancy_unresolved"


def test_wrong_upstream_media_type_is_rejected_before_runtime() -> None:
    with pytest.raises(ValidationError, match="bind the provisional M20-01"):
        AlignProteinSubtypeSourcesRequest(
            **_request().model_dump(mode="python")
            | {"upstream_result": _artifact("upstream-wrong", media_type="application/json")}
        )


def test_request_digest_is_stable_across_json_round_trip() -> None:
    request = _request()
    round_tripped = AlignProteinSubtypeSourcesRequest.model_validate_json(
        request.model_dump_json(), strict=True
    )
    assert canonical_request_digest(request) == canonical_request_digest(round_tripped)


def test_observation_duplicate_sources_are_rejected() -> None:
    with pytest.raises(ValidationError, match="source ids must be unique"):
        AlignmentObservation.model_validate(
            _request().observations[0].model_dump(mode="python")
            | {"source_ids": ("artifact.source-a", "artifact.source-a")},
            strict=True,
        )


def test_provenance_and_evidence_cover_nested_alignment_inputs() -> None:
    base = _request()
    nested_observation = base.observations[0].model_copy(
        update={"evidence": (_evidence("nested-observation"),)}
    )
    discrepancy = DiscrepancyMapEntry(
        discrepancy_id="discrepancy.nested",
        dimension=AlignmentDimension.REFERENCE,
        source_ids=("artifact.source-a", "artifact.source-b"),
        severity=DiscrepancySeverity.ROUTINE,
        description="Caller-declared routine discrepancy with explicit resolution.",
        resolution="accepted under locked reference policy",
        evidence=(_evidence("nested-discrepancy"),),
    )
    request = base.model_copy(
        update={
            "configuration": base.configuration.model_copy(
                update={"evidence": (_evidence("nested-configuration"),)}
            ),
            "observations": (nested_observation, *base.observations[1:]),
            "discrepancies": (discrepancy,),
        }
    )

    result = M2002Engine().resolve(request)
    nested_digests = {
        request.configuration.evidence[0].reference.digest,
        request.observations[0].evidence[0].reference.digest,
        request.discrepancies[0].evidence[0].reference.digest,
    }

    assert nested_digests <= set(result.provenance.input_digests)
    assert nested_digests <= {item.reference.digest for item in result.evidence}


def test_conflict_and_not_evaluable_states_never_emit_supported_status() -> None:
    for state in (
        AlignmentObservationStatus.CONFLICTED,
        AlignmentObservationStatus.NOT_EVALUABLE,
    ):
        result = M2002Engine().resolve(_request(status=state))
        assert result.support_decision.status.value == "review_required"
        assert result.status.value == "abstained"


def test_result_contract_rejects_identity_and_request_tampering() -> None:
    result = M2002Engine().resolve(_request())
    with pytest.raises(ValidationError, match="request digest"):
        ProteinSubtypeAlignmentResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64}).model_dump(
                mode="python"
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="result identifier"):
        ProteinSubtypeAlignmentResult.model_validate(
            result.model_copy(update={"result_id": "result.tampered"}).model_dump(mode="python"),
            strict=True,
        )
    with pytest.raises(ValidationError, match="result digest"):
        ProteinSubtypeAlignmentResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64}).model_dump(
                mode="python"
            ),
            strict=True,
        )


def test_result_contract_rejects_duplicate_findings_and_evidence() -> None:
    abstained = M2002Engine().resolve(_request(status=AlignmentObservationStatus.CONFLICTED))
    finding = AlignmentFinding(
        finding_id="finding.duplicate",
        code=AlignmentFindingCode.DIMENSION_CONFLICT,
        message="duplicate finding",
    )
    with pytest.raises(ValidationError, match="finding ids must be unique"):
        ProteinSubtypeAlignmentResult.model_validate(
            abstained.model_copy(update={"findings": (finding, finding)}).model_dump(mode="python"),
            strict=True,
        )
    aligned = M2002Engine().resolve(_request())
    duplicate_evidence = (aligned.evidence[0], aligned.evidence[0])
    with pytest.raises(ValidationError, match="evidence digests must be unique"):
        ProteinSubtypeAlignmentResult.model_validate(
            aligned.model_copy(update={"evidence": duplicate_evidence}).model_dump(mode="python"),
            strict=True,
        )


def test_result_contract_rejects_unsafe_aligned_and_abstained_closures() -> None:
    aligned = M2002Engine().resolve(_request())
    assert aligned.aligned_bundle is not None
    unsupported = aligned.support_decision.model_copy(
        update={"status": SupportStatus.REVIEW_REQUIRED}
    )
    with pytest.raises(ValidationError, match="supported evidence bundle"):
        ProteinSubtypeAlignmentResult.model_validate(
            aligned.model_copy(update={"support_decision": unsupported}).model_dump(mode="python"),
            strict=True,
        )
    conflicted_observation = aligned.aligned_bundle.observations[0].model_copy(
        update={"status": AlignmentObservationStatus.CONFLICTED}
    )
    conflicted_bundle = aligned.aligned_bundle.model_copy(
        update={"observations": (conflicted_observation, *aligned.aligned_bundle.observations[1:])}
    )
    with pytest.raises(ValidationError, match="conflicted observations"):
        ProteinSubtypeAlignmentResult.model_validate(
            aligned.model_copy(update={"aligned_bundle": conflicted_bundle}).model_dump(
                mode="python"
            ),
            strict=True,
        )
    unresolved = DiscrepancyMapEntry(
        discrepancy_id="discrepancy.material",
        dimension=AlignmentDimension.REFERENCE,
        source_ids=("artifact.source-a", "artifact.source-b"),
        severity=DiscrepancySeverity.MATERIAL,
        description="material discrepancy",
        evidence=(_evidence("material-discrepancy"),),
    )
    unresolved_bundle = aligned.aligned_bundle.model_copy(update={"discrepancies": (unresolved,)})
    with pytest.raises(ValidationError, match="every discrepancy"):
        ProteinSubtypeAlignmentResult.model_validate(
            aligned.model_copy(update={"aligned_bundle": unresolved_bundle}).model_dump(
                mode="python"
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="abstained result"):
        ProteinSubtypeAlignmentResult.model_validate(
            aligned.model_copy(update={"status": AlignmentStatus.ABSTAINED}).model_dump(
                mode="python"
            ),
            strict=True,
        )
