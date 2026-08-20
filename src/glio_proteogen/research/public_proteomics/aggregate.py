"""Deterministic structural-evidence aggregation for research inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .formats import FastaStructure, MzIdentMlStructure, MzMlStructure
from .provenance import SourceManifest, sha256_digest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .pdc import PDCSnapshot

type StructuralSummary = FastaStructure | MzMlStructure | MzIdentMlStructure
_NO_CLAIMS: Final[tuple[str, ...]] = (
    "structural counts are not peptide, protein, proteoform, isoform, or abundance estimates",
    "source metadata and local format features are not evidence of glioma biology",
    "owner-confirmed module ABI and scientific validation are still required",
)


@dataclass(frozen=True, slots=True)
class FeatureRecord:
    """One provenance-checked local structural summary."""

    source_id: str
    format: str
    byte_length: int
    sha256: str
    attributes: tuple[tuple[str, int | str], ...]

    def __post_init__(self) -> None:
        if type(self.byte_length) is not int or self.byte_length < 0:
            raise ValueError("feature byte_length must be a non-negative integer")
        if type(self.attributes) is not tuple:
            raise TypeError("feature attributes must be a tuple")
        for item in self.attributes:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) not in (int, str)
            ):
                raise TypeError("feature attributes must contain string/integer pairs")

    def as_dict(self) -> dict[str, object]:
        return {
            "attributes": dict(self.attributes),
            "byte_length": self.byte_length,
            "format": self.format,
            "sha256": self.sha256,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class EvidenceAggregate:
    """Immutable, claim-free aggregation of metadata and structural features."""

    aggregate_id: str
    manifest_digest: str
    pdc_snapshot_digest: str
    feature_records: tuple[FeatureRecord, ...]
    structural_counts: tuple[tuple[str, int], ...]
    limitations: tuple[str, ...] = _NO_CLAIMS

    def as_dict(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "feature_records": [record.as_dict() for record in self.feature_records],
            "limitations": list(self.limitations),
            "manifest_digest": self.manifest_digest,
            "pdc_snapshot_digest": self.pdc_snapshot_digest,
            "structural_counts": dict(self.structural_counts),
        }

    @property
    def digest(self) -> str:
        return sha256_digest(self.as_dict())


def _feature_record(source_id: str, summary: StructuralSummary) -> FeatureRecord:
    values = summary.as_dict()
    format_name = values.pop("format")
    byte_length = values.pop("byte_length")
    digest = values.pop("sha256")
    if (
        not isinstance(format_name, str)
        or type(byte_length) is not int
        or byte_length < 0
        or not isinstance(digest, str)
    ):
        raise TypeError("structural summary has invalid identity fields")
    attributes: list[tuple[str, int | str]] = []
    for key, value in values.items():
        if isinstance(value, bool):
            raise TypeError(f"boolean structural attribute {key!r} is not supported")
        if type(value) is int or type(value) is str:
            attributes.append((key, value))
        elif isinstance(value, list):
            if any(isinstance(item, bool) for item in value):
                raise TypeError(f"boolean structural attribute {key!r} is not supported")
            attributes.append((key, str(value)))
        else:
            raise TypeError(f"unsupported structural attribute {key!r}")
    return FeatureRecord(
        source_id=source_id,
        format=format_name,
        byte_length=byte_length,
        sha256=digest,
        attributes=tuple(sorted(attributes)),
    )


def aggregate_evidence(
    manifest: SourceManifest,
    pdc_snapshot: PDCSnapshot,
    local_features: Mapping[str, StructuralSummary],
) -> EvidenceAggregate:
    """Join only manifest-matched sources and aggregate bounded structural counts."""

    source_by_id = {source.source_id: source for source in manifest.sources}
    pdc_ref = source_by_id.get(pdc_snapshot.source_reference.source_id)
    if pdc_ref is None or pdc_ref.as_dict() != pdc_snapshot.source_reference.as_dict():
        raise ValueError("PDC snapshot source is not exactly represented in the manifest")
    records: list[FeatureRecord] = []
    for source_id, summary in sorted(local_features.items()):
        reference = source_by_id.get(source_id)
        if reference is None:
            raise ValueError(f"local feature source {source_id!r} is not in the manifest")
        values = summary.as_dict()
        if (
            values.get("sha256") != reference.sha256
            or values.get("byte_length") != reference.byte_length
        ):
            raise ValueError(
                f"local feature source {source_id!r} does not match its manifest reference"
            )
        records.append(_feature_record(source_id, summary))
    counts: dict[str, int] = {
        "pdc_aliquots_count": pdc_snapshot.metadata.aliquots_count,
        "pdc_cases_count": pdc_snapshot.metadata.cases_count,
        "local_source_count": len(records),
    }
    for record in records:
        counts[f"{record.format}_byte_length"] = (
            counts.get(f"{record.format}_byte_length", 0) + record.byte_length
        )
    base = {
        "feature_records": [record.as_dict() for record in records],
        "manifest_digest": manifest.digest,
        "pdc_snapshot_digest": pdc_snapshot.digest,
        "structural_counts": dict(sorted(counts.items())),
    }
    return EvidenceAggregate(
        aggregate_id=sha256_digest(base),
        manifest_digest=manifest.digest,
        pdc_snapshot_digest=pdc_snapshot.digest,
        feature_records=tuple(records),
        structural_counts=tuple(sorted(counts.items())),
    )
