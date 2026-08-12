"""Strict public contracts for M02-03 identification raw-input ingestion."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m01_03 import (
    DiagnosticAction,
    DiagnosticSeverity,
    ParseDiagnostic,
    RawFormat,
    RawIngestionPolicy,
    RawInputDisposition,
    RawSourceDescriptor,
    ValidatedRawInputDescriptor,
)
from glio_proteogen.contracts.m02_03.canonical import (
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlRole,
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
    UpstreamDecisionState,
)

M0203_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-03"
M0203_CONTRACT_VERSION: Final = "1.0.0"
M0203_MAX_SOURCES: Final = 64
M0203_INGESTION_LIMITATION_CODE: Final = "identification_raw_ingestion_only"
M0203_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


class RawInputRole(StrEnum):
    SPECTRA = "spectra"
    PEPTIDE_IDENTIFICATIONS = "peptide_identifications"
    SEQUENCE_DATABASE = "sequence_database"
    GENOMIC_VARIANTS = "genomic_variants"
    TRANSCRIPT_ANNOTATIONS = "transcript_annotations"
    PTM_ANNOTATIONS = "ptm_annotations"


class RoleRequirement(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class BundleDiagnosticCode(StrEnum):
    REQUIRED_ROLE_MISSING = "required_role_missing"
    ROLE_CARDINALITY_MISMATCH = "role_cardinality_mismatch"
    ROLE_FORMAT_MISMATCH = "role_format_mismatch"


_MESSAGE_BY_CODE: Final = {
    BundleDiagnosticCode.REQUIRED_ROLE_MISSING: "A required raw-input role is missing.",
    BundleDiagnosticCode.ROLE_CARDINALITY_MISMATCH: (
        "A raw-input role violates its source cardinality."
    ),
    BundleDiagnosticCode.ROLE_FORMAT_MISMATCH: (
        "Detected content is not allowed for its raw-input role."
    ),
}


class RoleFormatRequirement(FrozenModel):
    role: RawInputRole
    requirement: RoleRequirement
    allowed_formats: tuple[RawFormat, ...] = Field(min_length=1, max_length=len(RawFormat))
    min_sources: int = Field(ge=0, le=M0203_MAX_SOURCES)
    max_sources: int = Field(gt=0, le=M0203_MAX_SOURCES)

    @model_validator(mode="after")
    def requirement_is_closed(self) -> RoleFormatRequirement:
        if len(self.allowed_formats) != len(set(self.allowed_formats)):
            raise ValueError("role formats must be unique")
        if self.min_sources > self.max_sources:
            raise ValueError("role minimum cannot exceed its maximum")
        if self.requirement is RoleRequirement.REQUIRED and self.min_sources < 1:
            raise ValueError("required roles must require at least one source")
        if self.requirement is RoleRequirement.OPTIONAL and self.min_sources != 0:
            raise ValueError("optional roles must permit zero sources")
        return self


class IdentificationRawSource(FrozenModel):
    role: RawInputRole
    source: RawSourceDescriptor


class IdentificationIngestionPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    base_policy: RawIngestionPolicy
    role_requirements: tuple[RoleFormatRequirement, ...] = Field(
        min_length=1,
        max_length=len(RawInputRole),
    )

    @model_validator(mode="after")
    def role_policy_is_closed(self) -> IdentificationIngestionPolicy:
        roles = [item.role for item in self.role_requirements]
        if len(roles) != len(set(roles)):
            raise ValueError("role requirements must have unique roles")
        if set(roles) != set(RawInputRole):
            raise ValueError("policy must explicitly govern every raw-input role")
        allowed = set(self.base_policy.allowed_formats)
        if any(not set(item.allowed_formats).issubset(allowed) for item in self.role_requirements):
            raise ValueError("role formats must be enabled by the base ingestion policy")
        if any(item.max_sources > self.base_policy.max_sources for item in self.role_requirements):
            raise ValueError("role source maximum exceeds the base policy")
        return self


class IngestIdentificationRawInputsRequest(FrozenModel):
    operation: Literal["ingest_identification_raw"] = "ingest_identification_raw"
    contract_version: Literal["1.0.0"] = M0203_CONTRACT_VERSION
    context: ExecutionContext
    policy: IdentificationIngestionPolicy
    sources: tuple[IdentificationRawSource, ...] = Field(
        min_length=1,
        max_length=M0203_MAX_SOURCES,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_policy_bound(self) -> IngestIdentificationRawInputsRequest:
        _require_authorized_context(self.context)
        source_ids = [item.source.source_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("identification raw source identifiers must be unique")
        if len(self.sources) > self.policy.base_policy.max_sources:
            raise ValueError("source count exceeds the base ingestion policy")
        requirements = {item.role: item for item in self.policy.role_requirements}
        for item in self.sources:
            source = item.source
            if source.byte_length > self.policy.base_policy.max_source_bytes:
                raise ValueError("declared source size exceeds the base ingestion policy")
            if source.declared_format is not None and source.declared_format not in requirements[
                item.role
            ].allowed_formats:
                raise ValueError("declared format is not allowed for the raw-input role")
            if source.declared_compression is not None and source.declared_compression not in (
                self.policy.base_policy.allowed_compressions
            ):
                raise ValueError("declared compression is disabled by the base policy")
        if self.context.references.approved_configuration.evidence.digest != configuration_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the ingestion policy")
        return self


class BundleDiagnostic(FrozenModel):
    code: BundleDiagnosticCode
    role: RawInputRole
    source_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0203_MAX_SOURCES)
    severity: Literal[DiagnosticSeverity.ERROR] = DiagnosticSeverity.ERROR
    action: Literal[DiagnosticAction.QUARANTINE] = DiagnosticAction.QUARANTINE
    message: NonEmptyStr

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_unique(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("bundle diagnostic source identifiers must be unique")
        return values

    @model_validator(mode="after")
    def diagnostic_is_fixed(self) -> BundleDiagnostic:
        if self.message != _MESSAGE_BY_CODE[self.code]:
            raise ValueError("bundle diagnostic message contradicts its code")
        if self.code is BundleDiagnosticCode.REQUIRED_ROLE_MISSING and self.source_ids:
            raise ValueError("missing-role diagnostics cannot reference sources")
        if self.code is not BundleDiagnosticCode.REQUIRED_ROLE_MISSING and not self.source_ids:
            raise ValueError("role diagnostics must reference their affected sources")
        return self


class ValidatedIdentificationRawInput(FrozenModel):
    role: RawInputRole
    raw_input: ValidatedRawInputDescriptor


class IdentificationRawIngestionResult(FrozenModel):
    output_type: Literal["identification_raw_ingestion_result"] = (
        "identification_raw_ingestion_result"
    )
    ingestion_id: Identifier
    result_version: Literal["1.0.0"] = M0203_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: RawInputDisposition
    raw_inputs: tuple[ValidatedIdentificationRawInput, ...] = Field(
        min_length=1,
        max_length=M0203_MAX_SOURCES,
    )
    bundle_diagnostics: tuple[BundleDiagnostic, ...] = Field(default=(), max_length=32)
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=8, max_length=71)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(  # noqa: PLR0912 - explicit envelope closure.
        self,
    ) -> IdentificationRawIngestionResult:
        source_ids = [item.raw_input.source_id for item in self.raw_inputs]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("validated raw inputs must have unique source identifiers")
        role_by_source = {
            item.raw_input.source_id: item.role for item in self.raw_inputs
        }
        if len(self.bundle_diagnostics) != len(set(self.bundle_diagnostics)):
            raise ValueError("bundle diagnostics must be unique")
        known_sources = set(source_ids)
        if any(
            not set(item.source_ids).issubset(known_sources)
            for item in self.bundle_diagnostics
        ):
            raise ValueError("bundle diagnostic references an unknown source")
        if any(
            any(role_by_source[source_id] is not item.role for source_id in item.source_ids)
            for item in self.bundle_diagnostics
        ):
            raise ValueError("bundle diagnostic source roles contradict the diagnostic role")
        expected = _result_disposition(self.raw_inputs, self.bundle_diagnostics)
        if self.disposition is not expected:
            raise ValueError("result disposition contradicts raw inputs and bundle diagnostics")
        support = {
            RawInputDisposition.ACCEPTED: (
                SupportStatus.LIMITED,
                "identification_raw_inputs_validated",
                False,
            ),
            RawInputDisposition.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                "identification_raw_inputs_quarantined",
                True,
            ),
            RawInputDisposition.REJECTED: (
                SupportStatus.UNSUPPORTED,
                "identification_raw_inputs_rejected",
                True,
            ),
        }[self.disposition]
        if (self.support.status, self.support.reason_code, self.human_review_required) != support:
            raise ValueError("result support contradicts its disposition")
        suffix = self.request_digest.removeprefix("sha256:")
        if self.ingestion_id != f"ingestion.m0203.{suffix}":
            raise ValueError("ingestion identifier does not bind its request")
        if self.provenance.activity_id != f"activity.m0203.{suffix}":
            raise ValueError("provenance activity does not bind its request")
        if (
            self.provenance.module_id != M0203_MODULE_ID
            or self.provenance.module_version != self.result_version
            or self.provenance.generated_at != self.completed_at
            or self.provenance.configuration_digest != self.configuration_digest
        ):
            raise ValueError("identification ingestion provenance is inconsistent")
        required = {
            self.request_digest,
            self.policy_digest,
            self.configuration_digest,
            *(item.raw_input.source_digest for item in self.raw_inputs),
            *(item.evidence_digest for item in self.provenance.control_decisions),
        }
        if not required.issubset(self.provenance.input_digests):
            raise ValueError("identification ingestion provenance inputs are incomplete")
        _validate_controls_and_evidence(self)
        if {item.code for item in self.limitations} != {
            M0203_INGESTION_LIMITATION_CODE,
            M0203_AUTHORITY_LIMITATION_CODE,
        }:
            raise ValueError("identification ingestion requires both limitation codes")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("identification ingestion evidence must be unique")
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("identification ingestion result digest does not match its content")
        return self


def _result_disposition(
    raw_inputs: tuple[ValidatedIdentificationRawInput, ...],
    diagnostics: tuple[BundleDiagnostic, ...],
) -> RawInputDisposition:
    dispositions = {item.raw_input.disposition for item in raw_inputs}
    if RawInputDisposition.REJECTED in dispositions:
        return RawInputDisposition.REJECTED
    if diagnostics or RawInputDisposition.QUARANTINED in dispositions:
        return RawInputDisposition.QUARANTINED
    return RawInputDisposition.ACCEPTED


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize identification raw ingestion")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every generic upstream control must accept identification ingestion")


def _validate_controls_and_evidence(result: IdentificationRawIngestionResult) -> None:
    provenance = result.provenance
    controls = {item.role: item for item in provenance.control_decisions}
    expected_states = {
        ControlRole.APPROVED_CONFIGURATION: "accepted",
        ControlRole.IDENTITY_LINEAGE: "resolved",
        ControlRole.PROVENANCE: "accepted",
        ControlRole.CONSENT: "granted",
        ControlRole.QUALITY: "accepted",
        ControlRole.SUPPORT: "accepted",
        ControlRole.INTENDED_USE: "accepted",
    }
    if {role: item.state for role, item in controls.items()} != expected_states:
        raise ValueError("identification ingestion control states are inconsistent")
    configuration = controls[ControlRole.APPROVED_CONFIGURATION]
    consent = controls[ControlRole.CONSENT]
    if configuration.evidence_digest != result.configuration_digest:
        raise ValueError("approved configuration evidence does not bind the result")
    if (
        provenance.consent_decision_id,
        provenance.consent_state.value,
        provenance.consent_policy_version,
        provenance.consent_evidence_digest,
    ) != (
        consent.decision_id,
        consent.state,
        consent.policy_version,
        consent.evidence_digest,
    ):
        raise ValueError("consent provenance contradicts its control record")
    evidence_digests = {item.reference.digest for item in result.evidence}
    if not {item.evidence_digest for item in provenance.control_decisions}.issubset(
        evidence_digests
    ):
        raise ValueError("result evidence does not cover every upstream control")


__all__ = [
    "M0203_AUTHORITY_LIMITATION_CODE",
    "M0203_CONTRACT_VERSION",
    "M0203_INGESTION_LIMITATION_CODE",
    "M0203_MAX_SOURCES",
    "M0203_MODULE_ID",
    "BundleDiagnostic",
    "BundleDiagnosticCode",
    "IdentificationIngestionPolicy",
    "IdentificationRawIngestionResult",
    "IdentificationRawSource",
    "IngestIdentificationRawInputsRequest",
    "ParseDiagnostic",
    "RawFormat",
    "RawIngestionPolicy",
    "RawInputDisposition",
    "RawInputRole",
    "RawSourceDescriptor",
    "RoleFormatRequirement",
    "RoleRequirement",
    "ValidatedIdentificationRawInput",
    "ValidatedRawInputDescriptor",
]
