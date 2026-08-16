"""Adversarial closure tests for M20-02 negative-space behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_02 import (
    AlignmentDimension,
    AlignmentObservation,
    AlignmentObservationStatus,
    AlignProteinSubtypeSourcesRequest,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
)
from glio_proteogen.contracts.m20_02.canonical import canonical_request_digest
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


def test_conflict_and_not_evaluable_states_never_emit_supported_status() -> None:
    for state in (
        AlignmentObservationStatus.CONFLICTED,
        AlignmentObservationStatus.NOT_EVALUABLE,
    ):
        result = M2002Engine().resolve(_request(status=state))
        assert result.support_decision.status.value == "review_required"
        assert result.status.value == "abstained"
