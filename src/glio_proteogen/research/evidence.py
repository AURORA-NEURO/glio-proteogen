"""Content-addressed aggregation of external-cohort and computed evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
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
class EvidenceRecord:
    evidence_id: str
    source: str
    kind: str
    payload: Mapping[str, object]
    digest: str

    @classmethod
    def create(
        cls, evidence_id: str, source: str, kind: str, payload: Mapping[str, object]
    ) -> EvidenceRecord:
        frozen = _freeze(payload)
        if not isinstance(frozen, Mapping):
            raise TypeError("evidence payload must be a mapping")
        raw = json.dumps(_thaw(frozen), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return cls(evidence_id, source, kind, frozen, sha256(raw).hexdigest())

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


def aggregate_evidence(records: tuple[EvidenceRecord, ...]) -> EvidenceBundle:
    if not records:
        raise ValueError("at least one evidence record is required")
    if len({record.evidence_id for record in records}) != len(records):
        raise ValueError("evidence IDs must be unique")
    for record in records:
        raw = json.dumps(record.payload_jsonable, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        if sha256(raw).hexdigest() != record.digest:
            raise ValueError("evidence record payload digest mismatch")
    ordered = tuple(sorted(records, key=lambda record: record.evidence_id))
    payload = [
        {
            "id": record.evidence_id,
            "source": record.source,
            "kind": record.kind,
            "digest": record.digest,
        }
        for record in ordered
    ]
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return EvidenceBundle(
        records=ordered,
        digest=digest,
        limitations=(
            "External evidence provenance is recorded but issuer truth is not authenticated.",
            "Computed spectra/search/quantification/inference objects require owner-approved production ABI.",
            "No clinical, disease, treatment, or mechanistic claim is emitted by this research layer.",
        ),
    )
