"""Provisional M26-01 registry and configuration service contracts.

M26-01 owns immutable registration and active configuration resolution beneath
the Proteomics standards registry. The ABI is inferred from dossier lines
9036-9076 and remains provisional pending Computational biology confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m26_01.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from dossier lines 9036-9076.
M2601_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-01"
M2601_OPERATION: Final = "register_protein_subtype_registry"
M2601_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2601_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-01+json"
M2601_PARENT: Final = "protein subtype"
M2601_OWNER: Final = "Computational biology"
M2601_SAFETY_CLASS: Final = "S3"
M2601_GATE: Final = "G0"
M2601_PROVISIONAL_ABI: Final = True
M2601_MAX_ENTRIES: Final = 128
M2601_MAX_HISTORY: Final = 512
M2601_MAX_BINDINGS: Final = 16
M2601_MAX_EVIDENCE: Final = 64
M2601_MAX_FINDINGS: Final = 64
M2601_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2601_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2601_EVIDENCE_CLAIM: Final = (
    "Caller-declared M26-01 registry, immutable-history, active-configuration "
    "and compatibility material; issuer authority is not authenticated."
)


class RegistryEntryKind(StrEnum):
    MODULE = "module"
    DATA = "data"
    ASSAY = "assay"
    MODEL = "model"
    REFERENCE = "reference"
    POLICY = "policy"
    INTENDED_USE = "intended_use"


class RegistryEntryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    QUARANTINED = "quarantined"


class RegistryEventType(StrEnum):
    REGISTER = "register"
    ACTIVATE = "activate"
    SUPERSEDE = "supersede"
    REVOKE = "revoke"
    QUARANTINE = "quarantine"


class RegistryStatus(StrEnum):
    REGISTERED = "registered"
    ABSTAINED = "abstained"


class RegistryFindingCode(StrEnum):
    UNREGISTERED_ENTRY = "unregistered_entry"
    INCOMPATIBLE_CONFIGURATION = "incompatible_configuration"
    HISTORY_GAP = "history_gap"
    QUARANTINED_INPUT = "quarantined_input"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class RegistryEntry(FrozenModel):
    """One immutable versioned registry entry."""

    entry_id: Identifier
    kind: RegistryEntryKind
    name: NonEmptyStr
    version: SemanticVersion
    artifact: ArtifactReference
    owner: Identifier
    status: RegistryEntryStatus
    immutable: Literal[True] = True
    compatibility_digest: Sha256Digest | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)


class RegistryHistoryEvent(FrozenModel):
    """Append-only event preserving every registry transition."""

    event_id: Identifier
    entry_id: Identifier
    event_type: RegistryEventType
    prior_digest: Sha256Digest | None = None
    new_digest: Sha256Digest
    actor_id: Identifier
    occurred_at: AwareDatetime
    reason: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def transition_has_prior_when_required(self) -> RegistryHistoryEvent:
        if self.event_type is RegistryEventType.REGISTER and self.prior_digest is not None:
            raise ValueError("register events cannot carry a prior digest")
        if self.event_type is not RegistryEventType.REGISTER and self.prior_digest is None:
            raise ValueError("registry transitions require a prior digest")
        return self


class ConfigurationBinding(FrozenModel):
    """A typed registry entry selected by an active configuration."""

    binding_id: Identifier
    kind: RegistryEntryKind
    entry_id: Identifier
    required: Literal[True] = True
    compatibility_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)


class ActiveConfiguration(FrozenModel):
    """Locked selection of approved entries for runtime resolution."""

    configuration_id: Identifier
    version: SemanticVersion
    bindings: tuple[ConfigurationBinding, ...] = Field(min_length=7, max_length=M2601_MAX_BINDINGS)
    approved_by: Identifier
    configuration_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_registry_kinds_are_bound(self) -> ActiveConfiguration:
        kinds = tuple(item.kind for item in self.bindings)
        binding_ids = tuple(item.binding_id for item in self.bindings)
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("active configuration binding ids must be unique")
        if len(kinds) != len(set(kinds)):
            raise ValueError("active configuration kinds must be unique")
        if set(kinds) != set(RegistryEntryKind):
            raise ValueError("active configuration must bind every registry entry kind")
        return self


class RegistryRecord(FrozenModel):
    """Versioned registry projection with a complete immutable history."""

    registry_id: Identifier
    version: SemanticVersion
    entries: tuple[RegistryEntry, ...] = Field(min_length=7, max_length=M2601_MAX_ENTRIES)
    history: tuple[RegistryHistoryEvent, ...] = Field(min_length=1, max_length=M2601_MAX_HISTORY)
    lock_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)

    @model_validator(mode="after")
    def record_is_closed(self) -> RegistryRecord:
        entry_ids = tuple(item.entry_id for item in self.entries)
        event_ids = tuple(item.event_id for item in self.history)
        known = set(entry_ids)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("registry entry ids must be unique")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("registry history event ids must be unique")
        if any(item.entry_id not in known for item in self.history):
            raise ValueError("registry history references an unknown entry")
        if not any(item.event_type is RegistryEventType.REGISTER for item in self.history):
            raise ValueError("registry history must contain a registration event")
        return self


class RegistryFinding(FrozenModel):
    finding_id: Identifier
    code: RegistryFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)


class RegisterProteinSubtypeRegistryRequest(FrozenModel):
    """Provisional request for a versioned registry and active configuration."""

    operation: Literal["register_protein_subtype_registry"] = M2601_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2601_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    registry_id: Identifier
    registry_version: SemanticVersion
    entries: tuple[RegistryEntry, ...] = Field(min_length=7, max_length=M2601_MAX_ENTRIES)
    history: tuple[RegistryHistoryEvent, ...] = Field(min_length=1, max_length=M2601_MAX_HISTORY)
    active_configuration: ActiveConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2601_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> RegisterProteinSubtypeRegistryRequest:
        entry_ids = tuple(item.entry_id for item in self.entries)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("request registry entry ids must be unique")
        known = set(entry_ids)
        if any(item.entry_id not in known for item in self.history):
            raise ValueError("request history references an unknown entry")
        if any(item.entry_id not in known for item in self.active_configuration.bindings):
            raise ValueError("active configuration references an unknown entry")
        entries_by_id = {item.entry_id: item for item in self.entries}
        if any(
            entries_by_id[item.entry_id].kind is not item.kind
            for item in self.active_configuration.bindings
        ):
            raise ValueError("active configuration kind does not match registered entry")
        if {
            item.kind
            for item in self.entries
            if item.entry_id in {binding.entry_id for binding in self.active_configuration.bindings}
        } != set(RegistryEntryKind):
            raise ValueError("active configuration must bind registered entries of every kind")
        return self


class ProteinSubtypeRegistryResult(FrozenModel):
    """Registered immutable history plus active configuration with safe abstention."""

    output_type: Literal["protein_subtype_registry"] = "protein_subtype_registry"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2601_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RegisterProteinSubtypeRegistryRequest
    status: RegistryStatus
    registry: RegistryRecord | None = None
    active_configuration: ActiveConfiguration | None = None
    findings: tuple[RegistryFinding, ...] = Field(default=(), max_length=M2601_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2601_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2601_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeRegistryResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.status is RegistryStatus.REGISTERED:
            if (
                self.registry is None
                or self.active_configuration is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("registered result requires supported registry and configuration")
        elif (
            self.registry is not None
            or self.active_configuration is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no registry and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2601_CONTRACT_VERSION",
    "M2601_EVIDENCE_CLAIM",
    "M2601_GATE",
    "M2601_MAX_BINDINGS",
    "M2601_MAX_CANONICAL_REQUEST_BYTES",
    "M2601_MAX_CANONICAL_RESULT_BYTES",
    "M2601_MAX_ENTRIES",
    "M2601_MAX_EVIDENCE",
    "M2601_MAX_FINDINGS",
    "M2601_MAX_HISTORY",
    "M2601_MODULE_ID",
    "M2601_OPERATION",
    "M2601_OUTPUT_MEDIA_TYPE",
    "M2601_OWNER",
    "M2601_PARENT",
    "M2601_PROVISIONAL_ABI",
    "M2601_SAFETY_CLASS",
    "ActiveConfiguration",
    "ConfigurationBinding",
    "ProteinSubtypeRegistryResult",
    "RegisterProteinSubtypeRegistryRequest",
    "RegistryEntry",
    "RegistryEntryKind",
    "RegistryEntryStatus",
    "RegistryEventType",
    "RegistryFinding",
    "RegistryFindingCode",
    "RegistryHistoryEvent",
    "RegistryRecord",
    "RegistryStatus",
]
