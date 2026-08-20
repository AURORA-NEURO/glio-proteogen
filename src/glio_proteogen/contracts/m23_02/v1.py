"""Provisional M23-02 synthetic truth and simulation generator contracts.

The dossier requires analytically known and semi-synthetic fixtures spanning
normal, edge, missing, shifted, and adversarial cases.  The ABI is
provisional; generation is deterministic and unresolved inputs abstain.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m23_02.canonical import (
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
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
)

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 8000-8040. Owner confirmation and implementation details remain
# pending.
M2302_MODULE_ID: Final = "GLIO-PROTEOGEN-M23-02"
M2302_OPERATION: Final = "generate_variant_peptide_synthetic_truth"
M2302_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2302_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m23-02+json"
M2302_M2301_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m23-01+json"
M2302_PARENT: Final = "variant peptide"
M2302_OWNER: Final = "Platform engineering"
M2302_SAFETY_CLASS: Final = "S3"
M2302_GATE: Final = "G1"
M2302_PROVISIONAL_ABI: Final = True
M2302_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2302_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:8000-8040"
M2302_EVIDENCE_CLAIM: Final = (
    "Caller-declared M23-02 synthetic truth, simulation, fixture, and reproducibility evidence; "
    "issuer authority is not authenticated."
)
M2302_MAX_CASES: Final = 512
M2302_MAX_FEATURES: Final = 256
M2302_MAX_FIXTURE_LABELS: Final = 16
M2302_MAX_EVIDENCE: Final = 64
M2302_MAX_FINDINGS: Final = 64
M2302_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2302_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class FixtureKind(StrEnum):
    NORMAL = "normal"
    EDGE = "edge"
    MISSING = "missing"
    SHIFTED = "shifted"
    ADVERSARIAL = "adversarial"


class TruthRepresentation(StrEnum):
    ANALYTIC = "analytic"
    SEMI_SYNTHETIC = "semi_synthetic"


class GenerationStatus(StrEnum):
    GENERATED = "generated"
    ABSTAINED = "abstained"


class GeneratorFindingCode(StrEnum):
    FIXTURE_INCOMPLETE = "fixture_incomplete"
    UNSUPPORTED_PERTURBATION = "unsupported_perturbation"
    SEED_INVALID = "seed_invalid"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class SyntheticTruthCase(FrozenModel):
    case_id: Identifier
    fixture_kind: FixtureKind
    representation: TruthRepresentation
    seed: int = Field(ge=0)
    expected_features: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2302_MAX_FEATURES)
    truth_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2302_MAX_FEATURES)
    perturbations: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M2302_MAX_FIXTURE_LABELS)
    analytically_recoverable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2302_MAX_EVIDENCE)

    @model_validator(mode="after")
    def feature_truth_dimensions_match(self) -> SyntheticTruthCase:
        if len(self.expected_features) != len(self.truth_values):
            raise ValueError("synthetic truth features and values must have equal dimensions")
        return self


class GenerationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    generator_name: NonEmptyStr
    seed: int = Field(ge=0)
    requested_fixture_kinds: tuple[FixtureKind, ...] = Field(min_length=1, max_length=5)
    deterministic: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2302_MAX_EVIDENCE)

    @model_validator(mode="after")
    def fixture_kinds_are_unique(self) -> GenerationConfiguration:
        if len(set(self.requested_fixture_kinds)) != len(self.requested_fixture_kinds):
            raise ValueError("requested fixture kinds must be unique")
        if set(self.requested_fixture_kinds) != set(FixtureKind):
            raise ValueError(
                "configuration must request normal edge missing shifted and adversarial fixtures"
            )
        return self


class GenerationManifest(FrozenModel):
    manifest_id: Identifier
    version: SemanticVersion
    configuration: GenerationConfiguration
    case_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M2302_MAX_CASES)
    reproducibility_digest: Sha256Digest
    fixture_summary: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M2302_MAX_FIXTURE_LABELS
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2302_MAX_EVIDENCE)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> GenerationManifest:
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("manifest case ids must be unique")
        if self.reproducibility_digest == "sha256:" + ("0" * 64):
            raise ValueError("manifest reproducibility digest cannot be zero")
        return self


class SyntheticTruthCorpus(FrozenModel):
    corpus_id: Identifier
    version: SemanticVersion
    cases: tuple[SyntheticTruthCase, ...] = Field(min_length=1, max_length=M2302_MAX_CASES)
    manifest: GenerationManifest
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2302_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2302_MAX_EVIDENCE)

    @model_validator(mode="after")
    def corpus_is_closed(self) -> SyntheticTruthCorpus:
        case_ids = tuple(item.case_id for item in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("corpus case ids must be unique")
        if set(case_ids) != set(self.manifest.case_ids):
            raise ValueError("manifest must enumerate every corpus case")
        if self.manifest.version != self.version:
            raise ValueError("manifest and corpus versions must match")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("corpus source artifacts must be unique")
        return self


class GeneratorFinding(FrozenModel):
    finding_id: Identifier
    code: GeneratorFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2302_MAX_EVIDENCE)


class GenerateVariantPeptideSyntheticTruthRequest(FrozenModel):
    """Provisional request bound to the M23-01 transport result."""

    operation: Literal["generate_variant_peptide_synthetic_truth"] = M2302_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2302_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: GenerationConfiguration
    requested_case_count: int = Field(ge=1, le=M2302_MAX_CASES)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2302_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> GenerateVariantPeptideSyntheticTruthRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        if self.upstream_result.media_type != M2302_M2301_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M23-01 transport result")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        upstream_key = (
            self.upstream_result.artifact_id,
            self.upstream_result.version,
            self.upstream_result.digest,
            self.upstream_result.media_type,
        )
        if upstream_key not in set(source_keys):
            raise ValueError("request source artifacts must retain M23-01 evidence")
        return self


class VariantPeptideSyntheticTruthResult(FrozenModel):
    """Synthetic-truth corpus with explicit reproducibility and abstention."""

    output_type: Literal["variant_peptide_synthetic_truth"] = "variant_peptide_synthetic_truth"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2302_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: GenerateVariantPeptideSyntheticTruthRequest
    status: GenerationStatus
    corpus: SyntheticTruthCorpus | None = None
    manifest: GenerationManifest | None = None
    findings: tuple[GeneratorFinding, ...] = Field(default=(), max_length=M2302_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant peptide"] = M2302_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2302_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    def _provenance_is_closed(self) -> None:
        references = self.request.context.references
        expected_controls = tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
                subject_digest=getattr(decision, "binding_digest", None),
            )
            for role, decision in (
                (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
                (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
                (ControlRole.PROVENANCE, references.provenance),
                (ControlRole.CONSENT, references.consent),
                (ControlRole.QUALITY, references.quality),
                (ControlRole.SUPPORT, references.support),
                (ControlRole.INTENDED_USE, references.intended_use),
            )
        )
        provenance_bindings = (
            (
                self.provenance.activity_id,
                "m2302.activity." + self.request_digest.removeprefix("sha256:"),
                "activity identity",
            ),
            (self.provenance.actor_id, self.request.context.actor_id, "actor identity"),
            (self.provenance.module_id, M2302_MODULE_ID, "module identity"),
            (self.provenance.module_version, M2302_CONTRACT_VERSION, "module version"),
            (self.provenance.generated_at, self.request.context.occurred_at, "generated time"),
            (
                self.provenance.input_digests,
                tuple(
                    dict.fromkeys(
                        (
                            self.request_digest,
                            self.request.upstream_result.digest,
                            *(item.digest for item in self.request.source_artifacts),
                        )
                    )
                ),
                "input digests",
            ),
            (
                self.provenance.configuration_digest,
                self.request.configuration.evidence[0].reference.digest
                if self.request.configuration.evidence
                else self.request.source_artifacts[0].digest,
                "configuration digest",
            ),
            (
                self.provenance.consent_decision_id,
                references.consent.decision_id,
                "consent decision",
            ),
            (self.provenance.consent_state, references.consent.state, "consent state"),
            (
                self.provenance.consent_policy_version,
                references.consent.policy_version,
                "consent policy version",
            ),
            (
                self.provenance.consent_evidence_digest,
                references.consent.evidence.digest,
                "consent evidence",
            ),
            (self.provenance.control_decisions, expected_controls, "control decisions"),
        )
        for actual, expected, label in provenance_bindings:
            if actual != expected:
                raise ValueError(f"M23-02 provenance {label} does not bind the request")

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideSyntheticTruthResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result identifier must be derived from request digest")
        self._provenance_is_closed()
        if self.status is GenerationStatus.GENERATED:
            if (
                self.corpus is None
                or self.manifest is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("generated result requires a supported corpus and manifest")
        elif (
            self.corpus is not None
            or self.manifest is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no corpus and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2302_CONTRACT_VERSION",
    "M2302_DOSSIER_SHA256",
    "M2302_DOSSIER_SLICE",
    "M2302_EVIDENCE_CLAIM",
    "M2302_GATE",
    "M2302_M2301_INPUT_MEDIA_TYPE",
    "M2302_MAX_CANONICAL_REQUEST_BYTES",
    "M2302_MAX_CANONICAL_RESULT_BYTES",
    "M2302_MAX_CASES",
    "M2302_MAX_EVIDENCE",
    "M2302_MAX_FEATURES",
    "M2302_MAX_FINDINGS",
    "M2302_MAX_FIXTURE_LABELS",
    "M2302_MODULE_ID",
    "M2302_OPERATION",
    "M2302_OUTPUT_MEDIA_TYPE",
    "M2302_OWNER",
    "M2302_PARENT",
    "M2302_PROVISIONAL_ABI",
    "M2302_SAFETY_CLASS",
    "FixtureKind",
    "GenerateVariantPeptideSyntheticTruthRequest",
    "GenerationConfiguration",
    "GenerationManifest",
    "GenerationStatus",
    "GeneratorFinding",
    "GeneratorFindingCode",
    "SyntheticTruthCase",
    "SyntheticTruthCorpus",
    "TruthRepresentation",
    "VariantPeptideSyntheticTruthResult",
]
