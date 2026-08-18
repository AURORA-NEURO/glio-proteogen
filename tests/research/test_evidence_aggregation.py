"""Adversarial tests for descriptive external-evidence aggregation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from glio_proteogen.research import (
    ExternalEvidenceAggregate,
    ExternalEvidenceObservation,
    aggregate_external_evidence,
    replay_external_evidence,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _observation(
    evidence_id: str,
    source_id: str,
    direction: str = "supports",
    *,
    source_sha256: str = _HASH_A,
    limitation: str = "",
) -> ExternalEvidenceObservation:
    return ExternalEvidenceObservation(
        evidence_id=evidence_id,
        claim_id="caller-claim-1",
        source_id=source_id,
        study_id="PDC000204",
        source_kind="pdc_cohort",
        direction=direction,
        source_sha256=source_sha256,
        source_size=1024,
        method_id="caller-method-v1",
        cohort_size=12,
        limitation=limitation,
    )


def test_consistent_support_requires_independent_sources_and_preserves_ledger() -> None:
    result = aggregate_external_evidence(
        (_observation("e2", "source-b"), _observation("e1", "source-a"))
    )
    assert result.status == "consistent_support"
    assert result.independent_source_ids == ("source-a", "source-b")
    assert result.support_count == 2
    assert result.contradiction_count == 0
    assert result.evidence_bundle.records[0].payload_jsonable["claim_id"] == "caller-claim-1"
    assert result.evidence_bundle.quality_summary is not None
    assert result.evidence_bundle.quality_summary.independent_sources == 2
    assert result.digest == aggregate_external_evidence(tuple(reversed(result.observations))).digest


def test_source_order_does_not_change_digest_or_observation_order() -> None:
    first = _observation("e1", "source-a", source_sha256=_HASH_A)
    second = _observation("e2", "source-b", source_sha256=_HASH_B)
    forward = aggregate_external_evidence((first, second))
    reverse = aggregate_external_evidence((second, first))
    assert forward.digest == reverse.digest
    assert tuple(item.evidence_id for item in forward.observations) == ("e1", "e2")


def test_mixed_direction_is_visible_and_never_collapsed_to_support() -> None:
    result = aggregate_external_evidence(
        (
            _observation("e1", "source-a", "supports"),
            _observation("e2", "source-b", "contradicts"),
        )
    )
    assert result.status == "mixed_direction"
    assert result.support_count == 1
    assert result.contradiction_count == 1
    assert result.as_dict()["status"] == "mixed_direction"


def test_inconclusive_is_not_support() -> None:
    result = aggregate_external_evidence(
        (
            _observation("e1", "source-a", "inconclusive"),
            _observation("e2", "source-b", "inconclusive"),
        )
    )
    assert result.status == "inconclusive"
    assert result.inconclusive_count == 2
    assert result.support_count == 0


def test_insufficient_independence_abstains_even_when_rows_support() -> None:
    result = aggregate_external_evidence(
        (_observation("e1", "same-source"), _observation("e2", "same-source"))
    )
    assert result.status == "abstained_insufficient_independence"
    assert result.independent_source_ids == ("same-source",)
    assert result.support_count == 2
    assert any("statistical power" in item for item in result.limitations)


def test_same_source_direction_conflict_abstains_before_independence_gate() -> None:
    result = aggregate_external_evidence(
        (
            _observation("e1", "same-source", "supports"),
            _observation("e2", "same-source", "contradicts"),
            _observation("e3", "other-source", "supports"),
        )
    )
    assert result.status == "abstained_source_conflict"
    assert result.independent_source_ids == ("other-source", "same-source")


def test_explicit_abstention_requires_limitation_and_surfaces_status() -> None:
    with pytest.raises(ValueError, match="limitation"):
        _observation("e1", "source-a", "abstained")
    result = aggregate_external_evidence(
        (
            _observation("e1", "source-a", "abstained", limitation="missing source receipt"),
            _observation("e2", "source-b", "supports"),
        )
    )
    assert result.status == "abstained_observation"
    assert result.abstained_count == 1
    assert result.evidence_bundle.quality_summary is not None
    assert result.evidence_bundle.quality_summary.abstained_records == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evidence_id", "", "opaque"),
        ("source_id", "source id", "opaque"),
        ("source_kind", "unknown", "source_kind"),
        ("direction", "positive", "direction"),
        ("source_sha256", "A" * 64, "lowercase"),
        ("source_size", 0, "source_size"),
        ("cohort_size", 0, "cohort_size"),
    ],
)
def test_observation_schema_rejects_unbounded_or_ambiguous_values(
    field: str, value: object, message: str
) -> None:
    values: dict[str, object] = {
        "evidence_id": "e1",
        "claim_id": "caller-claim-1",
        "source_id": "source-a",
        "study_id": "PDC000204",
        "source_kind": "pdc_cohort",
        "direction": "supports",
        "source_sha256": _HASH_A,
        "source_size": 1024,
        "method_id": "method-v1",
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        ExternalEvidenceObservation(**values)  # type: ignore[arg-type]


def test_claims_cannot_be_combined_and_ids_cannot_be_repeated() -> None:
    different_claim = replace(_observation("e2", "source-b"), claim_id="other-claim")
    with pytest.raises(ValueError, match="one claim"):
        aggregate_external_evidence((_observation("e1", "source-a"), different_claim))
    with pytest.raises(ValueError, match="unique"):
        aggregate_external_evidence(
            (_observation("e1", "source-a"), _observation("e1", "source-b"))
        )


def test_replay_rejects_changed_direction_source_hash_and_threshold() -> None:
    observations = (_observation("e1", "source-a"), _observation("e2", "source-b"))
    result = aggregate_external_evidence(observations)
    assert replay_external_evidence(observations, result).digest == result.digest
    changed_direction = replace(observations[1], direction="contradicts")
    with pytest.raises(ValueError, match="replay"):
        replay_external_evidence((observations[0], changed_direction), result)
    changed_hash = replace(observations[1], source_sha256=_HASH_B)
    with pytest.raises(ValueError, match="replay"):
        replay_external_evidence((observations[0], changed_hash), result)
    with pytest.raises(ValueError, match="replay"):
        replay_external_evidence(observations, result, minimum_independent_sources=3)


def test_aggregate_is_no_numerical_fusion() -> None:
    result = aggregate_external_evidence(
        (
            _observation("e1", "source-a"),
            _observation("e2", "source-b"),
        )
    )
    serialized = result.as_dict()
    assert "estimate" not in serialized
    assert "p_value" not in serialized
    assert "posterior" not in serialized
    assert "effect_size" not in serialized
    assert any("no numerical fusion" in item for item in result.limitations)


def test_observation_limitation_is_bounded_and_non_abstained_is_closed() -> None:
    with pytest.raises(ValueError, match="single-line"):
        _observation("e1", "source-a", "abstained", limitation="line\nbreak")
    with pytest.raises(ValueError, match="non-abstained"):
        _observation("e1", "source-a", limitation="not allowed")


def test_aggregate_input_bounds_and_types_are_closed() -> None:
    with pytest.raises(ValueError, match="bounded tuple"):
        aggregate_external_evidence([])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="minimum independent"):
        aggregate_external_evidence(
            (_observation("e1", "source-a"),), minimum_independent_sources=0
        )
    with pytest.raises(TypeError, match="ExternalEvidenceObservation"):
        aggregate_external_evidence((object(),))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="expected"):
        replay_external_evidence((_observation("e1", "source-a"),), object())  # type: ignore[arg-type]


def test_aggregate_projection_rejects_forged_structural_fields() -> None:
    result = aggregate_external_evidence(
        (_observation("e1", "source-a"), _observation("e2", "source-b"))
    )
    invalid = (
        ("status", "not-a-status", "status"),
        ("observations", (), "observations"),
        ("observations", tuple(reversed(result.observations)), "canonically ordered"),
        ("independent_source_ids", ("source-b", "source-a"), "canonically ordered"),
        ("independent_source_ids", ("source-a", "source-a"), "unique"),
        ("support_count", -1, "non-negative"),
        ("support_count", 3, "counts"),
        ("digest", "a" * 63, "SHA-256"),
        ("limitations", (), "limitations"),
    )
    for field, value, message in invalid:
        with pytest.raises(ValueError, match=message):
            replace(result, **cast("Any", {field: value}))


def test_aggregate_type_is_immutable_and_rejects_non_observations() -> None:
    result = aggregate_external_evidence(
        (_observation("e1", "source-a"), _observation("e2", "source-b"))
    )
    with pytest.raises(AttributeError):
        result.status = "mixed_direction"  # type: ignore[misc]
    with pytest.raises(TypeError, match="ExternalEvidenceObservation"):
        aggregate_external_evidence((_observation("e1", "source-a"), object()))  # type: ignore[arg-type]


def test_external_aggregate_constructor_is_closed_for_count_and_bundle_shape() -> None:
    result = aggregate_external_evidence(
        (_observation("e1", "source-a"), _observation("e2", "source-b"))
    )
    values = {
        "claim_id": result.claim_id,
        "observations": result.observations,
        "status": result.status,
        "independent_source_ids": result.independent_source_ids,
        "support_count": result.support_count,
        "contradiction_count": result.contradiction_count,
        "inconclusive_count": result.inconclusive_count,
        "abstained_count": result.abstained_count,
        "evidence_bundle": result.evidence_bundle,
        "digest": result.digest,
        "limitations": result.limitations,
    }
    values["support_count"] = 1
    values["contradiction_count"] = 1
    values["inconclusive_count"] = 1
    with pytest.raises(ValueError, match="counts"):
        ExternalEvidenceAggregate(**values)  # type: ignore[arg-type]
