"""Deterministic structural-evidence aggregation for research inputs."""

from __future__ import annotations

import re
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
_FORMAT_MEDIA_TYPES: Final[dict[str, frozenset[str]]] = {
    "fasta": frozenset(
        {"application/fasta", "application/octet-stream", "text/plain", "text/x-fasta"}
    ),
    "mzidentml": frozenset(
        {
            "application/mzidentml",
            "application/mzidentml+xml",
            "application/octet-stream",
            "application/xml",
            "text/xml",
        }
    ),
    "mzml": frozenset(
        {
            "application/mzml",
            "application/octet-stream",
            "application/xml",
            "application/x-mzml",
            "text/xml",
        }
    ),
}
_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_digest(value: object, field: str) -> None:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{field} must be lowercase sha256:<64 hex characters>")


@dataclass(frozen=True, slots=True)
class FeatureRecord:
    """One provenance-checked local structural summary."""

    source_id: str
    format: str
    byte_length: int
    sha256: str
    attributes: tuple[tuple[str, int | str], ...]

    def __post_init__(self) -> None:
        if type(self.source_id) is not str or not self.source_id.strip():
            raise ValueError("feature source_id must be non-empty text")
        if type(self.format) is not str or self.format not in _FORMAT_MEDIA_TYPES:
            raise ValueError("feature format is not supported")
        if type(self.byte_length) is not int or self.byte_length < 0:
            raise ValueError("feature byte_length must be a non-negative integer")
        _require_digest(self.sha256, "feature sha256")
        if type(self.attributes) is not tuple:
            raise TypeError("feature attributes must be a tuple")
        keys: list[str] = []
        for item in self.attributes:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) not in (int, str)
            ):
                raise TypeError("feature attributes must contain string/integer pairs")
            if not item[0].strip():
                raise ValueError("feature attribute names must be non-empty")
            keys.append(item[0])
        if len(keys) != len(set(keys)):
            raise ValueError("feature attributes must have unique names")
        if keys != sorted(keys):
            raise ValueError("feature attributes must be canonically ordered")

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

    def __post_init__(self) -> None:
        """Close the direct-construction path used by replay consumers.

        ``aggregate_evidence`` is the normal constructor, but this immutable
        receipt is also a public research type.  Without these checks a caller
        could serialize a structurally plausible receipt with a forged identity,
        silently collapsed feature keys, or counts that do not describe the
        recorded features.
        """

        _require_digest(self.aggregate_id, "aggregate_id")
        _require_digest(self.manifest_digest, "manifest_digest")
        _require_digest(self.pdc_snapshot_digest, "pdc_snapshot_digest")
        if type(self.feature_records) is not tuple or any(
            not isinstance(record, FeatureRecord) for record in self.feature_records
        ):
            raise TypeError("feature_records must be a tuple of FeatureRecord values")
        source_ids = tuple(record.source_id for record in self.feature_records)
        if source_ids != tuple(sorted(source_ids)):
            raise ValueError("feature_records must be canonically ordered")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("feature_records must have unique source ids")
        if type(self.structural_counts) is not tuple:
            raise TypeError("structural_counts must be a tuple")
        count_keys: list[str] = []
        for item in self.structural_counts:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0].strip()
                or type(item[1]) is not int
                or item[1] < 0
            ):
                raise TypeError("structural_counts must contain string/non-negative integer pairs")
            count_keys.append(item[0])
        if count_keys != sorted(count_keys):
            raise ValueError("structural_counts must be canonically ordered")
        if len(count_keys) != len(set(count_keys)):
            raise ValueError("structural_counts must have unique names")
        counts = dict(self.structural_counts)
        expected_counts: dict[str, int] = {
            "local_source_count": len(self.feature_records),
        }
        expected_counts.update(
            {
                "pdc_aliquots_count": counts.get("pdc_aliquots_count", -1),
                "pdc_cases_count": counts.get("pdc_cases_count", -1),
            }
        )
        for record in self.feature_records:
            key = f"{record.format}_byte_length"
            expected_counts[key] = expected_counts.get(key, 0) + record.byte_length
        if counts != expected_counts:
            raise ValueError("structural_counts do not match the feature records")
        if self.limitations != _NO_CLAIMS:
            raise ValueError("public-proteomics aggregate limitations are fixed")
        base = {
            "feature_records": [record.as_dict() for record in self.feature_records],
            "manifest_digest": self.manifest_digest,
            "pdc_snapshot_digest": self.pdc_snapshot_digest,
            "structural_counts": dict(self.structural_counts),
        }
        if self.aggregate_id != sha256_digest(base):
            raise ValueError("aggregate_id does not match the evidence projection")

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
    required_local_sources = {
        source.source_id
        for source in manifest.sources
        if source.source_id != pdc_snapshot.source_reference.source_id
    }
    missing_local_sources = required_local_sources.difference(local_features)
    if missing_local_sources:
        raise ValueError(
            "manifest local sources are missing structural features: "
            + ", ".join(sorted(missing_local_sources))
        )
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
        format_name = values.get("format")
        declared_media_type = reference.media_type.split(";", 1)[0].strip().lower()
        if not isinstance(format_name, str) or declared_media_type not in _FORMAT_MEDIA_TYPES.get(
            format_name, frozenset()
        ):
            raise ValueError(
                f"local feature source {source_id!r} media type does not match its format"
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
