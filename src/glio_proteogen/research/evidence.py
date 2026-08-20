"""Content-addressed aggregation of external-cohort and computed evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from types import MappingProxyType

_QUALITY_STATUSES = frozenset({"computed", "verified", "declared", "abstained", "ungraded"})


def _validate_record_identity(value: str, field: str) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > 256
        or value != value.strip()
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field} must be a bounded non-empty identifier")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("evidence payload mapping keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, float) and not isfinite(value):
        raise TypeError("evidence payload floats must be finite")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError("evidence payload contains an unsupported value")


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EvidenceQuality:
    """Bounded auditability metadata for one research evidence record.

    ``auditability`` is deliberately not a probability of biological truth.  It
    describes how completely the record is tied to bytes, a deterministic
    computation, or an explicit caller declaration.  ``completeness`` describes
    whether the represented observation is complete (for example, zero missing
    matrix cells), and ``independent_sources`` is a caller-declared count of
    distinct source identities.  Keeping these dimensions explicit prevents a
    downstream consumer from mistaking a provenance score for scientific
    confidence.
    """

    status: str = "ungraded"
    auditability: float | None = None
    completeness: float | None = None
    independent_sources: int = 0
    basis: str = ""

    def __post_init__(self) -> None:
        if self.status not in _QUALITY_STATUSES:
            raise ValueError("quality status is not supported")
        for value, field in (
            (self.auditability, "auditability"),
            (self.completeness, "completeness"),
        ):
            if value is not None and (
                type(value) not in (int, float) or not isfinite(value) or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{field} must be a finite fraction")
        if self.status == "ungraded":
            if self.auditability is not None or self.completeness is not None or self.basis:
                raise ValueError("ungraded evidence cannot carry a quality assessment")
        elif (
            self.auditability is None
            or self.completeness is None
            or not self.basis
            or len(self.basis) > 256
            or self.basis != self.basis.strip()
            or any(character.isspace() or ord(character) < 32 for character in self.basis)
        ):
            raise ValueError(
                "scored evidence requires bounded auditability, completeness, and basis"
            )
        if type(self.independent_sources) is not int or not 0 <= self.independent_sources <= 32:
            raise ValueError("independent_sources is outside the bounded range")

    @property
    def weighted_score(self) -> float | None:
        if self.auditability is None or self.completeness is None:
            return None
        return self.auditability * self.completeness

    def as_dict(self) -> dict[str, object]:
        return {
            "auditability": self.auditability,
            "basis": self.basis,
            "completeness": self.completeness,
            "independent_sources": self.independent_sources,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class EvidenceQualitySummary:
    """Deterministic, non-clinical quality projection for an evidence bundle."""

    scored_records: int
    ungraded_records: int
    abstained_records: int
    independent_sources: int
    weighted_auditability: float | None
    weighted_completeness: float | None
    weighted_score: float | None
    quality_source_groups: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "abstained_records": self.abstained_records,
            "independent_sources": self.independent_sources,
            "quality_source_groups": self.quality_source_groups,
            "scored_records": self.scored_records,
            "ungraded_records": self.ungraded_records,
            "weighted_auditability": self.weighted_auditability,
            "weighted_completeness": self.weighted_completeness,
            "weighted_score": self.weighted_score,
        }


def _canonical_record_payload(record: EvidenceRecord) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidence_id": record.evidence_id,
        "kind": record.kind,
        "payload": record.payload_jsonable,
        "source": record.source,
    }
    if record.quality is not None:
        payload["quality"] = record.quality.as_dict()
    return payload


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    source: str
    kind: str
    payload: Mapping[str, object]
    digest: str
    quality: EvidenceQuality | None = None

    @classmethod
    def create(
        cls,
        evidence_id: str,
        source: str,
        kind: str,
        payload: Mapping[str, object],
        *,
        quality: EvidenceQuality | None = None,
    ) -> EvidenceRecord:
        _validate_record_identity(evidence_id, "evidence_id")
        _validate_record_identity(source, "source")
        _validate_record_identity(kind, "kind")
        frozen = _freeze(payload)
        if not isinstance(frozen, Mapping):
            raise TypeError("evidence payload must be a mapping")
        record = cls(evidence_id, source, kind, frozen, "", quality)
        canonical = _canonical_record_payload(record)
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return cls(evidence_id, source, kind, frozen, sha256(raw).hexdigest(), quality)

    @property
    def payload_jsonable(self) -> dict[str, object]:
        payload = _thaw(self.payload)
        if not isinstance(payload, dict):
            raise TypeError("evidence payload is not a mapping")
        return payload


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    records: tuple[EvidenceRecord, ...]
    digest: str
    limitations: tuple[str, ...]
    quality_summary: EvidenceQualitySummary | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the complete immutable receipt projection.

        The older bundle API exposed only the outer digest.  That made a caller
        unable to archive or independently verify the exact evidence records that
        contributed to a cohort result.  Keep the projection JSON-native and
        include each frozen payload so replay tooling can validate both inner and
        outer digests without reaching into private dataclass storage.
        """

        return {
            "digest": self.digest,
            "limitations": list(self.limitations),
            "quality_summary": (
                self.quality_summary.as_dict() if self.quality_summary is not None else None
            ),
            "records": [
                {
                    "digest": record.digest,
                    "evidence_id": record.evidence_id,
                    "kind": record.kind,
                    "payload": record.payload_jsonable,
                    "quality": record.quality.as_dict() if record.quality is not None else None,
                    "source": record.source,
                }
                for record in self.records
            ],
        }


def aggregate_evidence(records: tuple[EvidenceRecord, ...]) -> EvidenceBundle:
    if not records:
        raise ValueError("at least one evidence record is required")
    for record in records:
        _validate_record_identity(record.evidence_id, "evidence_id")
        _validate_record_identity(record.source, "source")
        _validate_record_identity(record.kind, "kind")
    if len({record.evidence_id for record in records}) != len(records):
        raise ValueError("evidence IDs must be unique")
    by_source_kind: dict[tuple[str, str], set[str]] = {}
    for record in records:
        by_source_kind.setdefault((record.source, record.kind), set()).add(record.digest)
    for record in records:
        raw = json.dumps(
            _canonical_record_payload(record), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if sha256(raw).hexdigest() != record.digest:
            raise ValueError("evidence record payload digest mismatch")
    if any(len(digests) > 1 for digests in by_source_kind.values()):
        raise ValueError("conflicting evidence records share a source and kind")
    ordered = tuple(sorted(records, key=lambda record: record.evidence_id))
    payload = [
        {
            "id": record.evidence_id,
            "source": record.source,
            "kind": record.kind,
            "digest": record.digest,
            "quality": record.quality.as_dict() if record.quality is not None else None,
        }
        for record in ordered
    ]
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    quality_records = tuple(
        record.quality
        for record in ordered
        if record.quality is not None and record.quality.status != "ungraded"
    )
    scored_count = len(quality_records)
    ungraded_count = len(ordered) - scored_count
    weighted_score: float | None = None
    weighted_auditability: float | None = None
    weighted_completeness: float | None = None
    independent_sources = max(
        (quality.independent_sources for quality in quality_records), default=0
    )
    quality_by_source: dict[str, list[EvidenceQuality]] = {}
    for record in ordered:
        if record.quality is not None and record.quality.status != "ungraded":
            quality_by_source.setdefault(record.source, []).append(record.quality)
    for source, source_quality in quality_by_source.items():
        if len({quality.independent_sources for quality in source_quality}) > 1:
            raise ValueError(
                "quality independent_sources conflict within evidence source " + source
            )
    if quality_records:
        # A producer may emit several projections (matrix, QC, provenance, or
        # contrast).  Average those projections within the producer and apply
        # its declared independent-source weight once.  Weighting every record
        # independently would let one producer inflate its influence merely by
        # emitting more derived views.
        grouped_quality = tuple(
            (
                source,
                tuple(source_quality),
                max(source_quality[0].independent_sources, 1),
            )
            for source, source_quality in sorted(quality_by_source.items())
        )
        weights = tuple(group[2] for group in grouped_quality)
        denominator = sum(weights)
        weighted_auditability = (
            sum(
                (
                    sum(
                        quality.auditability
                        for quality in source_quality
                        if quality.auditability is not None
                    )
                    / len(source_quality)
                )
                * weight
                for _, source_quality, weight in grouped_quality
            )
            / denominator
        )
        weighted_completeness = (
            sum(
                (
                    sum(
                        quality.completeness
                        for quality in source_quality
                        if quality.completeness is not None
                    )
                    / len(source_quality)
                )
                * weight
                for _, source_quality, weight in grouped_quality
            )
            / denominator
        )
        weighted_score = weighted_auditability * weighted_completeness
    summary = (
        EvidenceQualitySummary(
            scored_records=scored_count,
            ungraded_records=ungraded_count,
            abstained_records=sum(quality.status == "abstained" for quality in quality_records),
            independent_sources=independent_sources,
            weighted_auditability=weighted_auditability,
            weighted_completeness=weighted_completeness,
            weighted_score=weighted_score,
            quality_source_groups=len(quality_by_source),
        )
        if quality_records
        else None
    )
    return EvidenceBundle(
        records=ordered,
        digest=digest,
        limitations=(
            "External evidence provenance is recorded but issuer truth is not authenticated.",
            "Computed spectra/search/quantification/inference objects require owner-approved production ABI.",
            "No clinical, disease, treatment, or mechanistic claim is emitted by this research layer.",
        ),
        quality_summary=summary,
    )


def verify_evidence_bundle(bundle: EvidenceBundle) -> EvidenceBundle:
    """Recompute every inner and outer receipt in an archived evidence bundle.

    ``EvidenceRecord`` payloads are immutable, but the outer bundle also carries
    derived quality metadata and limitations.  Replaying only the records would
    leave those projections outside the verification boundary.  Recompute the
    canonical bundle and compare its complete JSON projection so a forged quality
    summary, limitations tuple, record ordering, or outer digest cannot be treated
    as valid research evidence.
    """

    if not isinstance(bundle, EvidenceBundle):
        raise TypeError("bundle must be an EvidenceBundle")
    observed = aggregate_evidence(bundle.records)
    if observed.as_dict() != bundle.as_dict():
        raise ValueError("evidence bundle digest or derived metadata is invalid")
    return observed
