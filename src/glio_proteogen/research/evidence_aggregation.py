"""Bounded, provenance-first aggregation of caller-declared external evidence.

This module is intentionally descriptive.  It aggregates independent evidence
receipts without pooling numerical estimates, inferring a disease label, or
turning a caller-declared direction into a biological conclusion.  A source
may support, contradict, remain inconclusive, or explicitly abstain from a
caller-declared claim.  Every observation keeps its own source identity and
content hash so disagreement cannot be hidden by a summary count.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256

from .evidence import (
    EvidenceBundle,
    EvidenceQuality,
    EvidenceRecord,
    aggregate_evidence,
    verify_evidence_bundle,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DIRECTIONS = frozenset({"supports", "contradicts", "inconclusive", "abstained"})
_SOURCE_KINDS = frozenset({"pdc_cohort", "local_fixture", "external_catalog"})
_AGGREGATE_STATUSES = frozenset(
    {
        "consistent_support",
        "consistent_contradiction",
        "mixed_direction",
        "inconclusive",
        "abstained_insufficient_independence",
        "abstained_source_conflict",
        "abstained_observation",
    }
)
MAX_OBSERVATIONS = 128


def _opaque(value: str, field: str, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field} must be a bounded opaque identifier")
    return value


def _sha256(value: str, field: str) -> str:
    normalized = value.removeprefix("sha256:") if isinstance(value, str) else ""
    if not _HEX64.fullmatch(normalized):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return normalized


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _source_identity(item: ExternalEvidenceObservation) -> tuple[str, int]:
    """Return the immutable receipt identity used for independence counting."""

    return item.source_sha256.removeprefix("sha256:"), item.source_size


@dataclass(frozen=True, slots=True)
class ExternalEvidenceObservation:
    """One source-bound, caller-declared observation about one opaque claim.

    ``direction`` is a descriptive assertion supplied by the caller or source
    adapter.  The aggregator never derives it from protein names, disease
    metadata, measured values, or a study title.
    """

    evidence_id: str
    claim_id: str
    source_id: str
    study_id: str
    source_kind: str
    direction: str
    source_sha256: str
    source_size: int
    method_id: str
    cohort_size: int | None = None
    limitation: str = ""

    def __post_init__(self) -> None:
        for value, field in (
            (self.evidence_id, "evidence_id"),
            (self.claim_id, "claim_id"),
            (self.source_id, "source_id"),
            (self.study_id, "study_id"),
            (self.method_id, "method_id"),
        ):
            _opaque(value, field)
        if self.source_kind not in _SOURCE_KINDS:
            raise ValueError("source_kind is not supported")
        if self.direction not in _DIRECTIONS:
            raise ValueError("direction is not supported")
        _sha256(self.source_sha256, "source_sha256")
        if type(self.source_size) is not int or self.source_size <= 0:
            raise ValueError("source_size must be a positive integer")
        if self.cohort_size is not None and (
            type(self.cohort_size) is not int or not 1 <= self.cohort_size <= 1_000_000
        ):
            raise ValueError("cohort_size is outside the bounded range")
        if (
            type(self.limitation) is not str
            or len(self.limitation) > 256
            or self.limitation != self.limitation.strip()
            or any(ord(character) < 32 for character in self.limitation)
        ):
            raise ValueError("limitation must be bounded single-line text")
        if self.direction == "abstained" and not self.limitation:
            raise ValueError("abstained observations require a limitation")
        if self.direction != "abstained" and self.limitation:
            raise ValueError("non-abstained observations cannot carry a limitation")

    def as_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "cohort_size": self.cohort_size,
            "direction": self.direction,
            "evidence_id": self.evidence_id,
            "limitation": self.limitation,
            "method_id": self.method_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_sha256": "sha256:" + self.source_sha256.removeprefix("sha256:"),
            "source_size": self.source_size,
            "study_id": self.study_id,
        }

    @property
    def digest(self) -> str:
        return sha256(_canonical(self.as_dict())).hexdigest()


def _derive_observation_projection(
    observations: tuple[ExternalEvidenceObservation, ...],
) -> tuple[
    tuple[ExternalEvidenceObservation, ...],
    dict[tuple[str, int], set[str]],
    dict[tuple[str, int], set[str]],
    tuple[str, ...],
    dict[str, int],
]:
    """Derive the canonical observation projection used by construction/replay.

    Keeping this projection shared by the public aggregator and the immutable
    aggregate constructor prevents a caller from constructing a structurally
    valid object whose counts, status, or source representatives disagree with
    its observation ledger.
    """

    if type(observations) is not tuple or not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise ValueError("observations must be a bounded tuple")
    if any(not isinstance(item, ExternalEvidenceObservation) for item in observations):
        raise TypeError("observations must contain ExternalEvidenceObservation values")
    ordered = tuple(sorted(observations, key=lambda item: item.evidence_id))
    if len({item.evidence_id for item in ordered}) != len(ordered):
        raise ValueError("evidence IDs must be unique")
    if len({item.claim_id for item in ordered}) != 1:
        raise ValueError("all observations must address one claim")

    source_id_identities: dict[str, set[tuple[str, int]]] = {}
    source_directions: dict[tuple[str, int], set[str]] = {}
    identity_sources: dict[tuple[str, int], set[str]] = {}
    for item in ordered:
        identity = _source_identity(item)
        source_id_identities.setdefault(item.source_id, set()).add(identity)
        source_directions.setdefault(identity, set()).add(item.direction)
        identity_sources.setdefault(identity, set()).add(item.source_id)
    if any(len(identities) > 1 for identities in source_id_identities.values()):
        raise ValueError("source IDs must bind one receipt identity")

    independent_source_ids = tuple(
        sorted(min(source_ids) for source_ids in identity_sources.values())
    )
    counts = {
        direction: sum(item.direction == direction for item in ordered) for direction in _DIRECTIONS
    }
    return ordered, source_directions, identity_sources, independent_source_ids, counts


def _aggregate_limitations(
    identity_sources: dict[tuple[str, int], set[str]], status: str
) -> tuple[str, ...]:
    limitations: tuple[str, ...] = (
        "External directions are caller-declared and issuer truth is not authenticated.",
        "Independent source count is bound to source SHA-256 and byte size; it is a provenance gate, not statistical power or biological confidence.",
        "This research aggregation performs no numerical fusion and emits no clinical or disease claim.",
    )
    if any(len(source_ids) > 1 for source_ids in identity_sources.values()):
        limitations = (
            *limitations,
            "Multiple source IDs share one receipt identity and count as one independent source.",
        )
    if status in {
        "abstained_observation",
        "abstained_source_conflict",
        "abstained_insufficient_independence",
    }:
        limitations = (*limitations, f"Aggregation status is {status}.")
    return limitations


def _aggregate_digest(
    *,
    claim_id: str,
    observations: tuple[ExternalEvidenceObservation, ...],
    counts: dict[str, int],
    evidence_bundle: EvidenceBundle,
    independent_source_ids: tuple[str, ...],
    minimum_independent_sources: int,
    status: str,
) -> str:
    payload = {
        "claim_id": claim_id,
        "counts": counts,
        "evidence_bundle_digest": evidence_bundle.digest,
        "independent_source_ids": independent_source_ids,
        "minimum_independent_sources": minimum_independent_sources,
        "observation_digests": [item.digest for item in observations],
        "status": status,
    }
    return sha256(_canonical(payload)).hexdigest()


def _validate_ledger_projection(
    *,
    claim_id: str,
    observations: tuple[ExternalEvidenceObservation, ...],
    status: str,
    independent_source_count: int,
    evidence_bundle: EvidenceBundle,
) -> int:
    """Validate that an aggregate carries its own matching ledger receipt."""

    verify_evidence_bundle(evidence_bundle)
    if len(evidence_bundle.records) != 1:
        raise ValueError("external aggregate evidence bundle must contain one ledger record")
    record = evidence_bundle.records[0]
    expected_payload: dict[str, object] = {
        "claim_id": claim_id,
        "minimum_independent_sources": None,
        "observations": [item.as_dict() for item in observations],
        "status": status,
    }
    if (
        record.evidence_id != "external-evidence-ledger"
        or record.source != "claim:" + claim_id
        or record.kind != "external.evidence.ledger.v1"
    ):
        raise ValueError("external aggregate evidence bundle is not the claim ledger")
    payload = record.payload_jsonable
    minimum = payload.get("minimum_independent_sources")
    if type(minimum) is not int or not 1 <= minimum <= 32:
        raise ValueError("external aggregate ledger has an invalid independence threshold")
    expected_payload["minimum_independent_sources"] = minimum
    if payload != expected_payload:
        raise ValueError("external aggregate ledger does not match observations")
    expected_quality = EvidenceQuality(
        status="abstained" if status.startswith("abstained_") else "computed",
        auditability=1.0,
        completeness=0.0 if status.startswith("abstained_") else 1.0,
        independent_sources=independent_source_count,
        basis="external_receipt_direction_ledger_without_numerical_fusion",
    )
    if record.quality != expected_quality:
        raise ValueError("external aggregate ledger quality does not match projection")
    return minimum


@dataclass(frozen=True, slots=True)
class ExternalEvidenceAggregate:
    """Replay-bound descriptive aggregation with no numerical pooling."""

    claim_id: str
    observations: tuple[ExternalEvidenceObservation, ...]
    status: str
    independent_source_ids: tuple[str, ...]
    support_count: int
    contradiction_count: int
    inconclusive_count: int
    abstained_count: int
    evidence_bundle: EvidenceBundle
    digest: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _opaque(self.claim_id, "claim_id")
        if self.status not in _AGGREGATE_STATUSES:
            raise ValueError("aggregate status is not supported")
        if type(self.observations) is not tuple or not self.observations:
            raise ValueError("aggregate requires observations")
        if any(not isinstance(item, ExternalEvidenceObservation) for item in self.observations):
            raise TypeError("observations must contain ExternalEvidenceObservation values")
        if tuple(sorted(self.observations, key=lambda item: item.evidence_id)) != self.observations:
            raise ValueError("observations must be canonically ordered")
        if tuple(sorted(self.independent_source_ids)) != self.independent_source_ids:
            raise ValueError("independent sources must be canonically ordered")
        if len(self.independent_source_ids) != len(set(self.independent_source_ids)):
            raise ValueError("independent source IDs must be unique")
        for value, field in (
            (self.support_count, "support_count"),
            (self.contradiction_count, "contradiction_count"),
            (self.inconclusive_count, "inconclusive_count"),
            (self.abstained_count, "abstained_count"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if sum(
            (
                self.support_count,
                self.contradiction_count,
                self.inconclusive_count,
                self.abstained_count,
            )
        ) != len(self.observations):
            raise ValueError("aggregate direction counts do not match observations")
        if not _HEX64.fullmatch(self.digest):
            raise ValueError("aggregate digest must be a lowercase SHA-256")
        if not self.limitations or any(not item for item in self.limitations):
            raise ValueError("aggregate limitations must be non-empty")
        (
            ordered,
            source_directions,
            identity_sources,
            independent_source_ids,
            counts,
        ) = _derive_observation_projection(self.observations)
        if any(item.claim_id != self.claim_id for item in ordered):
            raise ValueError("aggregate claim does not match observations")
        if self.independent_source_ids != independent_source_ids:
            raise ValueError("aggregate independent sources do not match receipt identities")
        expected_counts = {
            "support_count": counts["supports"],
            "contradiction_count": counts["contradicts"],
            "inconclusive_count": counts["inconclusive"],
            "abstained_count": counts["abstained"],
        }
        if any(getattr(self, field) != value for field, value in expected_counts.items()):
            raise ValueError("aggregate direction counts do not match observations")
        minimum = _validate_ledger_projection(
            claim_id=self.claim_id,
            observations=ordered,
            status=self.status,
            independent_source_count=len(independent_source_ids),
            evidence_bundle=self.evidence_bundle,
        )
        expected_status = _status(ordered, source_directions, len(independent_source_ids), minimum)
        if self.status != expected_status:
            raise ValueError("aggregate status does not match observations")
        if self.limitations != _aggregate_limitations(identity_sources, self.status):
            raise ValueError("aggregate limitations do not match observations")
        expected_digest = _aggregate_digest(
            claim_id=self.claim_id,
            observations=ordered,
            counts=counts,
            evidence_bundle=self.evidence_bundle,
            independent_source_ids=independent_source_ids,
            minimum_independent_sources=minimum,
            status=self.status,
        )
        if self.digest != expected_digest:
            raise ValueError("aggregate digest does not match evidence projection")

    def as_dict(self) -> dict[str, object]:
        return {
            "abstained_count": self.abstained_count,
            "claim_id": self.claim_id,
            "contradiction_count": self.contradiction_count,
            "digest": self.digest,
            "evidence_bundle": self.evidence_bundle.as_dict(),
            "inconclusive_count": self.inconclusive_count,
            "independent_source_ids": list(self.independent_source_ids),
            "limitations": list(self.limitations),
            "observations": [item.as_dict() for item in self.observations],
            "status": self.status,
            "support_count": self.support_count,
        }


def _status(
    observations: tuple[ExternalEvidenceObservation, ...],
    source_directions: dict[tuple[str, int], set[str]],
    independent_count: int,
    minimum: int,
) -> str:
    status = "mixed_direction"
    if any(item.direction == "abstained" for item in observations):
        status = "abstained_observation"
    elif any(len(directions) > 1 for directions in source_directions.values()):
        status = "abstained_source_conflict"
    elif independent_count < minimum:
        status = "abstained_insufficient_independence"
    else:
        directions = {item.direction for item in observations}
        status = {
            frozenset({"supports"}): "consistent_support",
            frozenset({"contradicts"}): "consistent_contradiction",
            frozenset({"inconclusive"}): "inconclusive",
        }.get(frozenset(directions), "mixed_direction")
    return status


def aggregate_external_evidence(
    observations: tuple[ExternalEvidenceObservation, ...],
    *,
    minimum_independent_sources: int = 2,
) -> ExternalEvidenceAggregate:
    """Aggregate independent external receipts while preserving disagreement.

    No estimate, p-value, posterior, effect size, or pooled numerical statistic
    is produced.  ``minimum_independent_sources`` is a support gate only; it is
    not a claim of statistical power or biological validity.
    """

    if type(minimum_independent_sources) is not int or not 1 <= minimum_independent_sources <= 32:
        raise ValueError("minimum independent source count is outside the bounded range")
    (
        ordered,
        source_directions,
        identity_sources,
        independent_source_ids,
        counts,
    ) = _derive_observation_projection(observations)
    status = _status(
        ordered, source_directions, len(independent_source_ids), minimum_independent_sources
    )
    limitations = _aggregate_limitations(identity_sources, status)
    quality_status = "abstained" if status.startswith("abstained_") else "computed"
    quality = EvidenceQuality(
        status=quality_status,
        auditability=1.0,
        completeness=0.0 if status.startswith("abstained_") else 1.0,
        independent_sources=len(independent_source_ids),
        basis="external_receipt_direction_ledger_without_numerical_fusion",
    )
    ledger = EvidenceRecord.create(
        "external-evidence-ledger",
        "claim:" + ordered[0].claim_id,
        "external.evidence.ledger.v1",
        {
            "claim_id": ordered[0].claim_id,
            "minimum_independent_sources": minimum_independent_sources,
            "observations": [item.as_dict() for item in ordered],
            "status": status,
        },
        quality=quality,
    )
    bundle = aggregate_evidence((ledger,))
    digest = _aggregate_digest(
        claim_id=ordered[0].claim_id,
        observations=ordered,
        counts=counts,
        evidence_bundle=bundle,
        independent_source_ids=independent_source_ids,
        minimum_independent_sources=minimum_independent_sources,
        status=status,
    )
    return ExternalEvidenceAggregate(
        claim_id=ordered[0].claim_id,
        observations=ordered,
        status=status,
        independent_source_ids=independent_source_ids,
        support_count=counts["supports"],
        contradiction_count=counts["contradicts"],
        inconclusive_count=counts["inconclusive"],
        abstained_count=counts["abstained"],
        evidence_bundle=bundle,
        digest=digest,
        limitations=limitations,
    )


def replay_external_evidence(
    observations: tuple[ExternalEvidenceObservation, ...],
    expected: ExternalEvidenceAggregate,
    *,
    minimum_independent_sources: int = 2,
) -> ExternalEvidenceAggregate:
    """Recompute a descriptive aggregate and reject a changed receipt."""

    if not isinstance(expected, ExternalEvidenceAggregate):
        raise TypeError("expected must be an ExternalEvidenceAggregate")
    observed = aggregate_external_evidence(
        observations, minimum_independent_sources=minimum_independent_sources
    )
    if observed.digest != expected.digest or observed.as_dict() != expected.as_dict():
        raise ValueError("external evidence replay or digest verification failed")
    return observed


__all__ = [
    "ExternalEvidenceAggregate",
    "ExternalEvidenceObservation",
    "aggregate_external_evidence",
    "replay_external_evidence",
]
