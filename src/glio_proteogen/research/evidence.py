"""Content-addressed aggregation of external-cohort and computed evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    source: str
    kind: str
    payload: dict[str, Any]
    digest: str

    @classmethod
    def create(
        cls, evidence_id: str, source: str, kind: str, payload: dict[str, Any]
    ) -> EvidenceRecord:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return cls(evidence_id, source, kind, payload, sha256(raw).hexdigest())


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
