"""Immutable source identity and replicate-independence evidence for cohorts.

This module is research-only.  It records which bytes were analysed and whether
the caller considers each row biological, technical, or unknown.  It never infers
sample identity, case/control status, or biological independence from a filename,
PDC label, or measured value.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pdc import PdcSourceReceipt
    from .pipeline import ResearchRunRequest
    from .public_proteomics.pdc import PDCSnapshot

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REPLICATE_KINDS = frozenset({"biological", "technical", "unknown"})
_SOURCE_KINDS = frozenset({"local", "pdc"})
MAX_BINDINGS = 32

__all__ = ["CohortSourceBinding", "CohortSourceManifest"]


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


def _digest(value: str, field: str) -> str:
    if type(value) is not str or not _HEX64.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class CohortSourceBinding:
    """One caller-declared acquisition/source binding for a cohort row."""

    sample_id: str
    source_kind: str
    source_id: str
    source_sha256: str
    source_size: int
    replicate_kind: str = "unknown"
    acquisition_id: str | None = None
    declared_aliquot_id: str | None = None
    pdc_study_id: str | None = None
    pdc_file_name: str | None = None
    pdc_file_locator: str | None = None
    catalog_response_sha256: str | None = None
    receipt_digest: str | None = None
    metadata_snapshot_digest: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.sample_id, "sample_id")
        _opaque(self.source_id, "source_id")
        if self.source_kind not in _SOURCE_KINDS:
            raise ValueError("source_kind must be local or pdc")
        if self.replicate_kind not in _REPLICATE_KINDS:
            raise ValueError("replicate_kind must be biological, technical, or unknown")
        _digest(self.source_sha256, "source_sha256")
        if type(self.source_size) is not int or self.source_size <= 0:
            raise ValueError("source_size must be a positive integer")
        for value, field in (
            (self.acquisition_id, "acquisition_id"),
            (self.declared_aliquot_id, "declared_aliquot_id"),
            (self.pdc_study_id, "pdc_study_id"),
            (self.pdc_file_name, "pdc_file_name"),
            (self.pdc_file_locator, "pdc_file_locator"),
        ):
            if value is not None:
                _opaque(value, field)
        for value, field in (
            (self.catalog_response_sha256, "catalog_response_sha256"),
            (self.receipt_digest, "receipt_digest"),
            (self.metadata_snapshot_digest, "metadata_snapshot_digest"),
        ):
            if value is not None:
                _digest(value, field)
        pdc_values = (
            self.pdc_study_id,
            self.pdc_file_name,
            self.pdc_file_locator,
            self.catalog_response_sha256,
            self.receipt_digest,
        )
        if self.source_kind == "pdc" and any(value is None for value in pdc_values):
            raise ValueError("PDC bindings require file, study, catalog, and receipt identity")
        if self.source_kind == "local" and any(value is not None for value in pdc_values):
            raise ValueError("local bindings cannot carry PDC file identity")

    @classmethod
    def from_request(
        cls,
        request: ResearchRunRequest,
        *,
        replicate_kind: str = "unknown",
        acquisition_id: str | None = None,
        declared_aliquot_id: str | None = None,
        metadata_snapshot_digest: str | None = None,
    ) -> CohortSourceBinding:
        """Construct an explicit binding from already snapshotted request bytes."""

        if not isinstance(request.mzml_source, bytes):
            raise TypeError("ResearchRunRequest must contain snapshotted mzML bytes")
        source_sha256 = sha256(request.mzml_source).hexdigest()
        receipt = request.external_pdc_receipt
        if receipt is None:
            return cls(
                sample_id=request.sample_id,
                source_kind="local",
                source_id=f"local:{request.sample_id}",
                source_sha256=source_sha256,
                source_size=len(request.mzml_source),
                replicate_kind=replicate_kind,
                acquisition_id=acquisition_id,
                declared_aliquot_id=declared_aliquot_id,
                metadata_snapshot_digest=metadata_snapshot_digest,
            )
        return cls(
            sample_id=request.sample_id,
            source_kind="pdc",
            source_id=receipt.source_reference.source_id,
            source_sha256=source_sha256,
            source_size=len(request.mzml_source),
            replicate_kind=replicate_kind,
            acquisition_id=acquisition_id,
            declared_aliquot_id=declared_aliquot_id,
            pdc_study_id=receipt.file.study_id,
            pdc_file_name=receipt.file.file_name,
            pdc_file_locator=receipt.file.location,
            catalog_response_sha256=receipt.response_sha256,
            receipt_digest=receipt.digest,
            metadata_snapshot_digest=metadata_snapshot_digest,
        )

    @classmethod
    def from_pdc_receipt(
        cls,
        request: ResearchRunRequest,
        receipt: PdcSourceReceipt,
        *,
        replicate_kind: str = "unknown",
        acquisition_id: str | None = None,
        declared_aliquot_id: str | None = None,
        metadata_snapshot: PDCSnapshot | None = None,
    ) -> CohortSourceBinding:
        """Bind one request to a receipt and optionally a study metadata snapshot."""

        if request.external_pdc_receipt != receipt:
            raise ValueError("request and source binding receipt do not match")
        if metadata_snapshot is not None:
            if metadata_snapshot.metadata.pdc_study_id != receipt.file.study_id:
                raise ValueError("PDC metadata snapshot study does not match the file receipt")
            metadata_digest = metadata_snapshot.digest.removeprefix("sha256:")
        else:
            metadata_digest = None
        return cls.from_request(
            request,
            replicate_kind=replicate_kind,
            acquisition_id=acquisition_id,
            declared_aliquot_id=declared_aliquot_id,
            metadata_snapshot_digest=metadata_digest,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "acquisition_id": self.acquisition_id,
            "catalog_response_sha256": self.catalog_response_sha256,
            "declared_aliquot_id": self.declared_aliquot_id,
            "metadata_snapshot_digest": self.metadata_snapshot_digest,
            "pdc_file_locator": self.pdc_file_locator,
            "pdc_file_name": self.pdc_file_name,
            "pdc_study_id": self.pdc_study_id,
            "receipt_digest": self.receipt_digest,
            "replicate_kind": self.replicate_kind,
            "sample_id": self.sample_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_sha256": self.source_sha256,
            "source_size": self.source_size,
        }

    @property
    def source_identity(self) -> tuple[str, int]:
        """Identity used to detect reused bytes, independent of caller labels."""

        return self.source_sha256, self.source_size

    @property
    def digest(self) -> str:
        return sha256(
            json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CohortSourceManifest:
    """Canonical one-binding-per-sample source manifest."""

    bindings: tuple[CohortSourceBinding, ...]

    def __post_init__(self) -> None:
        if type(self.bindings) is not tuple:
            raise TypeError("bindings must be a tuple of CohortSourceBinding values")
        if not 2 <= len(self.bindings) <= MAX_BINDINGS:
            raise ValueError("source binding count is outside the cohort bounds")
        if any(not isinstance(binding, CohortSourceBinding) for binding in self.bindings):
            raise TypeError("bindings must contain CohortSourceBinding values")
        sample_ids = tuple(binding.sample_id for binding in self.bindings)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("source bindings must have unique sample IDs")

    @classmethod
    def from_requests(
        cls,
        requests: tuple[ResearchRunRequest, ...],
        *,
        replicate_kinds: dict[str, str] | None = None,
    ) -> CohortSourceManifest:
        kinds = replicate_kinds or {}
        return cls(
            tuple(
                CohortSourceBinding.from_request(
                    request, replicate_kind=kinds.get(request.sample_id, "unknown")
                )
                for request in requests
            )
        )

    def for_sample(self, sample_id: str) -> CohortSourceBinding:
        matches = tuple(binding for binding in self.bindings if binding.sample_id == sample_id)
        if len(matches) != 1:
            raise ValueError(f"source manifest has no unique binding for {sample_id!r}")
        return matches[0]

    def sorted_bindings(self) -> tuple[CohortSourceBinding, ...]:
        return tuple(sorted(self.bindings, key=lambda binding: binding.sample_id))

    def as_dict(self) -> dict[str, object]:
        return {"bindings": [binding.as_dict() for binding in self.sorted_bindings()]}

    @property
    def digest(self) -> str:
        return sha256(
            json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def source_identity_counts(self, sample_ids: tuple[str, ...]) -> dict[str, int]:
        bindings = tuple(self.for_sample(sample_id) for sample_id in sample_ids)
        unique = {binding.source_identity for binding in bindings}
        return {
            "rows": len(bindings),
            "unique_sources": len(unique),
            "duplicate_sources": len(bindings) - len(unique),
            "biological": sum(binding.replicate_kind == "biological" for binding in bindings),
            "technical": sum(binding.replicate_kind == "technical" for binding in bindings),
            "unknown": sum(binding.replicate_kind == "unknown" for binding in bindings),
        }

    def validate_against_samples(
        self,
        sample_ids: tuple[str, ...],
        requests: tuple[ResearchRunRequest, ...],
        observed_mzml_sha256: tuple[str, ...],
    ) -> None:
        if sample_ids != tuple(request.sample_id for request in requests):
            raise ValueError("source manifest sample order does not match cohort samples")
        if len(observed_mzml_sha256) != len(requests):
            raise ValueError("source manifest observation count does not match cohort samples")
        for sample_id, request, observed in zip(
            sample_ids, requests, observed_mzml_sha256, strict=True
        ):
            binding = self.for_sample(sample_id)
            if binding.source_sha256 != observed:
                raise ValueError("source manifest mzML digest does not match the run result")
            if not isinstance(request.mzml_source, bytes) or binding.source_size != len(
                request.mzml_source
            ):
                raise ValueError("source manifest size does not match request bytes")
            if request.external_pdc_receipt is None and binding.source_kind != "local":
                raise ValueError("local request has a non-local source binding")
            if request.external_pdc_receipt is not None:
                receipt = request.external_pdc_receipt
                if binding.source_id != receipt.source_reference.source_id:
                    raise ValueError("source manifest source ID does not match the receipt")
                if binding.receipt_digest != receipt.digest:
                    raise ValueError("source manifest receipt does not match the run request")
                if binding.catalog_response_sha256 != receipt.response_sha256:
                    raise ValueError("source manifest catalog response does not match the receipt")
                if binding.pdc_file_locator != receipt.file.location:
                    raise ValueError("source manifest PDC locator does not match the receipt")
                if binding.pdc_file_name != receipt.file.file_name:
                    raise ValueError("source manifest PDC file does not match the receipt")
                if binding.pdc_study_id != receipt.file.study_id:
                    raise ValueError("source manifest PDC study does not match the receipt")

    def validate_independence(self) -> None:
        by_identity: dict[tuple[str, int], list[CohortSourceBinding]] = {}
        biological = tuple(item for item in self.bindings if item.replicate_kind == "biological")
        for binding in self.bindings:
            by_identity.setdefault(binding.source_identity, []).append(binding)
        for values in by_identity.values():
            if sum(item.replicate_kind == "biological" for item in values) > 1:
                raise ValueError(
                    "duplicate source identity cannot be used as biological replicates"
                )
        for field in ("declared_aliquot_id", "acquisition_id"):
            values = tuple(getattr(item, field) for item in biological)
            present = tuple(value for value in values if value is not None)
            if len(present) != len(set(present)):
                raise ValueError(f"duplicate {field} cannot be used as biological replicates")
