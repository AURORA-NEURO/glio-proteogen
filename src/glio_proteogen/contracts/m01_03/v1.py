"""Strict public contracts for M01-03 raw-format ingestion.

The contract describes content-addressed sources and metadata-only parser results. Raw bytes,
filesystem paths, scientific measurements, and interpreted biological claims never enter an
M01-03 output model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m01_03.canonical import policy_digest, result_payload_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0103_MODULE_ID: Final = "GLIO-PROTEOGEN-M01-03"
M0103_CONTRACT_VERSION: Final = "1.0.0"
M0103_MAX_SOURCES: Final = 64
M0103_MAX_SOURCE_BYTES: Final = 268_435_456
M0103_MAX_DECODED_BYTES: Final = 536_870_912
M0103_MAX_DIAGNOSTICS_PER_SOURCE: Final = 128
M0103_RAW_LIMITATION_CODE: Final = "raw_ingestion_only"
M0103_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)

FormatVersion = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+(?:\.[0-9A-Za-z-]+){0,3}$",
    ),
]


class RawFormat(StrEnum):
    MZML = "mzML"
    MZIDENTML = "mzIdentML"
    MZTAB_M = "mzTab-M"
    FASTA = "FASTA"
    VCF = "VCF"
    GFF3 = "GFF3"


class Compression(StrEnum):
    NONE = "none"
    GZIP = "gzip"


class RawInputDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DiagnosticAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    REJECT = "reject"
    HUMAN_REVIEW = "human_review"


class RawSourceDescriptor(FrozenModel):
    """One immutable external artifact expected at the byte boundary."""

    source_id: Identifier
    artifact: ArtifactReference
    byte_length: int = Field(ge=0, le=M0103_MAX_SOURCE_BYTES)
    declared_format: RawFormat | None = None
    declared_version: FormatVersion | None = None
    declared_compression: Compression | None = None

    @model_validator(mode="after")
    def declaration_is_closed(self) -> RawSourceDescriptor:
        if self.declared_version is not None and self.declared_format is None:
            raise ValueError("declared version requires a declared format")
        return self


class RawIngestionPolicy(FrozenModel):
    """Explicit bounded policy selected before source bytes are read."""

    policy_id: Identifier
    version: SemanticVersion
    allowed_formats: tuple[RawFormat, ...] = Field(min_length=1, max_length=len(RawFormat))
    allowed_compressions: tuple[Compression, ...] = Field(
        min_length=1,
        max_length=len(Compression),
    )
    max_source_bytes: int = Field(gt=0, le=M0103_MAX_SOURCE_BYTES)
    max_decoded_bytes: int = Field(gt=0, le=M0103_MAX_DECODED_BYTES)
    max_sources: int = Field(gt=0, le=M0103_MAX_SOURCES)
    max_diagnostics_per_source: int = Field(
        gt=0,
        le=M0103_MAX_DIAGNOSTICS_PER_SOURCE,
    )
    require_checksum: Literal[True] = True

    @field_validator("allowed_formats", "allowed_compressions")
    @classmethod
    def allowed_values_are_unique(
        cls,
        values: tuple[RawFormat | Compression, ...],
    ) -> tuple[RawFormat | Compression, ...]:
        if len(values) != len(set(values)):
            raise ValueError("allowed policy values must be unique")
        return values


class IngestRawInputsRequest(FrozenModel):
    """Authorized metadata describing bytes supplied separately to the service."""

    operation: Literal["ingest_raw"] = "ingest_raw"
    contract_version: Literal["1.0.0"] = M0103_CONTRACT_VERSION
    context: ExecutionContext
    policy: RawIngestionPolicy
    sources: tuple[RawSourceDescriptor, ...] = Field(
        min_length=1,
        max_length=M0103_MAX_SOURCES,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_policy_bound(self) -> IngestRawInputsRequest:
        _require_authorized_context(self.context)
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("raw source identifiers must be unique")
        if len(self.sources) > self.policy.max_sources:
            raise ValueError("raw source count exceeds the active policy")
        if any(source.byte_length > self.policy.max_source_bytes for source in self.sources):
            raise ValueError("declared source size exceeds the active policy")
        if any(
            source.declared_format is not None
            and source.declared_format not in self.policy.allowed_formats
            for source in self.sources
        ):
            raise ValueError("declared source format is disabled by the active policy")
        if any(
            source.declared_compression is not None
            and source.declared_compression not in self.policy.allowed_compressions
            for source in self.sources
        ):
            raise ValueError("declared compression is disabled by the active policy")
        if self.context.references.approved_configuration.evidence.digest != policy_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the ingestion policy")
        return self


class DetectedRawFormat(FrozenModel):
    format: RawFormat
    version: FormatVersion | None = None
    compression: Compression
    media_type: Annotated[
        str,
        StringConstraints(
            min_length=3,
            max_length=127,
            pattern=r"^[a-z0-9][a-z0-9!#$&^_.+-]+/[a-z0-9][a-z0-9!#$&^_.+-]+$",
        ),
    ]


class ParseDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    code: Identifier
    severity: DiagnosticSeverity
    action: DiagnosticAction
    message: NonEmptyStr
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    evidence: tuple[ArtifactReference, ...] = Field(default=(), max_length=16)

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        evidence: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(evidence) != len(set(evidence)):
            raise ValueError("diagnostic evidence references must be unique")
        return evidence

    @model_validator(mode="after")
    def severity_matches_action(self) -> ParseDiagnostic:
        blocking_actions = {
            DiagnosticAction.QUARANTINE,
            DiagnosticAction.REJECT,
            DiagnosticAction.HUMAN_REVIEW,
        }
        blocking_severities = {DiagnosticSeverity.ERROR, DiagnosticSeverity.CRITICAL}
        if self.action in blocking_actions and self.severity not in blocking_severities:
            raise ValueError("blocking diagnostics require error or critical severity")
        return self


class ValidatedRawInputDescriptor(FrozenModel):
    """Metadata-only result for one source; no submitted bytes are retained."""

    source_id: Identifier
    source_digest: Sha256Digest
    source_size_bytes: int = Field(ge=0, le=M0103_MAX_SOURCE_BYTES)
    decoded_size_bytes: int = Field(ge=0, le=M0103_MAX_DECODED_BYTES)
    detected: DetectedRawFormat | None = None
    record_count: int = Field(ge=0, le=10_000_000_000)
    checksum_verified: bool
    structural_validation_passed: bool
    disposition: RawInputDisposition
    diagnostics: tuple[ParseDiagnostic, ...] = Field(
        default=(),
        max_length=M0103_MAX_DIAGNOSTICS_PER_SOURCE,
    )

    @field_validator("diagnostics")
    @classmethod
    def diagnostic_ids_are_unique(
        cls,
        diagnostics: tuple[ParseDiagnostic, ...],
    ) -> tuple[ParseDiagnostic, ...]:
        ids = [diagnostic.diagnostic_id for diagnostic in diagnostics]
        if len(ids) != len(set(ids)):
            raise ValueError("parse diagnostic identifiers must be unique")
        return diagnostics

    @model_validator(mode="after")
    def status_is_coherent(self) -> ValidatedRawInputDescriptor:
        blocking_actions = {
            DiagnosticAction.QUARANTINE,
            DiagnosticAction.REJECT,
            DiagnosticAction.HUMAN_REVIEW,
        }
        actions = {diagnostic.action for diagnostic in self.diagnostics}
        if self.disposition is RawInputDisposition.ACCEPTED:
            if (
                not self.checksum_verified
                or not self.structural_validation_passed
                or self.detected is None
                or actions & blocking_actions
            ):
                raise ValueError("accepted raw input must pass checksum and structural validation")
        elif not self.diagnostics or self.structural_validation_passed:
            raise ValueError("non-accepted raw input requires diagnostics and failed validation")
        if (
            DiagnosticAction.REJECT in actions
            and self.disposition is not RawInputDisposition.REJECTED
        ):
            raise ValueError("a rejection diagnostic requires rejected disposition")
        if self.disposition is RawInputDisposition.QUARANTINED and not actions & {
            DiagnosticAction.QUARANTINE,
            DiagnosticAction.HUMAN_REVIEW,
        }:
            raise ValueError("quarantined raw input requires a quarantine or review diagnostic")
        if self.disposition is RawInputDisposition.REJECTED and not any(
            diagnostic.action is DiagnosticAction.REJECT for diagnostic in self.diagnostics
        ):
            raise ValueError("rejected raw input requires a rejection diagnostic")
        return self


class RawIngestionResult(FrozenModel):
    output_type: Literal["raw_ingestion_result"] = "raw_ingestion_result"
    ingestion_id: Identifier
    result_version: Literal["1.0.0"] = M0103_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: RawInputDisposition
    raw_inputs: tuple[ValidatedRawInputDescriptor, ...] = Field(
        min_length=1,
        max_length=M0103_MAX_SOURCES,
    )
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=8,
        max_length=7 + M0103_MAX_SOURCES,
    )
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("raw_inputs")
    @classmethod
    def raw_source_results_are_unique(
        cls,
        raw_inputs: tuple[ValidatedRawInputDescriptor, ...],
    ) -> tuple[ValidatedRawInputDescriptor, ...]:
        source_ids = [raw_input.source_id for raw_input in raw_inputs]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("raw input results must have unique source identifiers")
        return raw_inputs

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        evidence: tuple[EvidenceReference, ...],
    ) -> tuple[EvidenceReference, ...]:
        if len(evidence) != len(set(evidence)):
            raise ValueError("ingestion evidence references must be unique")
        return evidence

    @field_validator("limitations")
    @classmethod
    def limitations_are_exact(
        cls,
        limitations: tuple[Limitation, ...],
    ) -> tuple[Limitation, ...]:
        codes = [limitation.code for limitation in limitations]
        if set(codes) != {M0103_RAW_LIMITATION_CODE, M0103_AUTHORITY_LIMITATION_CODE}:
            raise ValueError("raw ingestion result requires both module limitations")
        return limitations

    @model_validator(mode="after")
    def envelope_is_coherent_and_digest_bound(self) -> RawIngestionResult:
        expected_disposition = _result_disposition(self.raw_inputs)
        if self.disposition is not expected_disposition:
            raise ValueError("raw ingestion disposition contradicts source results")
        expected_support = {
            RawInputDisposition.ACCEPTED: (SupportStatus.LIMITED, "raw_input_validated"),
            RawInputDisposition.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                "raw_input_quarantined",
            ),
            RawInputDisposition.REJECTED: (SupportStatus.UNSUPPORTED, "raw_input_rejected"),
        }[self.disposition]
        if (self.support.status, self.support.reason_code) != expected_support:
            raise ValueError("raw ingestion support contradicts its disposition")
        if self.human_review_required is (self.disposition is RawInputDisposition.ACCEPTED):
            raise ValueError("human review flag contradicts raw ingestion disposition")
        expected_id = f"ingestion.m0103.{self.request_digest.removeprefix('sha256:')}"
        if self.ingestion_id != expected_id:
            raise ValueError("ingestion identifier does not bind its request digest")
        expected_activity_id = f"activity.m0103.{self.request_digest.removeprefix('sha256:')}"
        if self.provenance.activity_id != expected_activity_id:
            raise ValueError("ingestion provenance activity does not bind its request digest")
        if self.provenance.module_id != M0103_MODULE_ID:
            raise ValueError("ingestion provenance belongs to the wrong module")
        if self.provenance.module_version != self.result_version:
            raise ValueError("ingestion provenance version contradicts the result")
        if self.provenance.generated_at != self.completed_at:
            raise ValueError("ingestion provenance timestamp contradicts the result")
        if self.provenance.configuration_digest != self.policy_digest:
            raise ValueError("ingestion provenance configuration contradicts the policy")
        required_digests = {
            self.request_digest,
            self.policy_digest,
            *(raw_input.source_digest for raw_input in self.raw_inputs),
        }
        if not required_digests.issubset(self.provenance.input_digests):
            raise ValueError("ingestion provenance input digests are incomplete")
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("raw ingestion result digest does not match its content")
        return self


def _result_disposition(
    raw_inputs: tuple[ValidatedRawInputDescriptor, ...],
) -> RawInputDisposition:
    dispositions = {raw_input.disposition for raw_input in raw_inputs}
    if RawInputDisposition.REJECTED in dispositions:
        return RawInputDisposition.REJECTED
    if RawInputDisposition.QUARANTINED in dispositions:
        return RawInputDisposition.QUARANTINED
    return RawInputDisposition.ACCEPTED


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize raw ingestion")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before raw ingestion")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("every upstream control must accept raw ingestion")


__all__ = [
    "M0103_CONTRACT_VERSION",
    "M0103_MODULE_ID",
    "Compression",
    "DetectedRawFormat",
    "DiagnosticAction",
    "DiagnosticSeverity",
    "FormatVersion",
    "IngestRawInputsRequest",
    "ParseDiagnostic",
    "RawFormat",
    "RawIngestionPolicy",
    "RawIngestionResult",
    "RawInputDisposition",
    "RawSourceDescriptor",
    "ValidatedRawInputDescriptor",
]
