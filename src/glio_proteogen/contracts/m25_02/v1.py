"""Provisional M25-02 synthetic truth and simulation generator contracts.

The dossier requires deterministic analytic and semi-synthetic fixtures for
normal, edge, missing, shifted, and adversarial cases. Unsupported or
unresolved inputs abstain explicitly; this ABI remains provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m25_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 8720-8760. Owner confirmation and implementation details remain
# pending.
M2502_MODULE_ID: Final = "GLIO-PROTEOGEN-M25-02"
M2502_OPERATION: Final = "generate_proteotype_synthetic_truth"
M2502_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2502_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-02+json"
M2502_M2501_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-01+json"
M2502_PARENT: Final = "proteotype"
M2502_OWNER: Final = "Computational biology"
M2502_SAFETY_CLASS: Final = "S3"
M2502_GATE: Final = "G1"
M2502_PROVISIONAL_ABI: Final = True
M2502_MAX_CASES: Final = 512
M2502_MAX_FEATURES: Final = 256
M2502_MAX_FIXTURE_LABELS: Final = 16
M2502_MAX_EVIDENCE: Final = 64
M2502_MAX_FINDINGS: Final = 64
M2502_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2502_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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
    expected_features: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M2502_MAX_FEATURES
    )
    truth_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2502_MAX_FEATURES)
    perturbations: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M2502_MAX_FIXTURE_LABELS)
    analytically_recoverable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2502_MAX_EVIDENCE)


class GenerationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    generator_name: NonEmptyStr
    seed: int = Field(ge=0)
    requested_fixture_kinds: tuple[FixtureKind, ...] = Field(min_length=1, max_length=5)
    deterministic: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2502_MAX_EVIDENCE)

    @model_validator(mode="after")
    def fixture_kinds_are_unique(self) -> GenerationConfiguration:
        if len(set(self.requested_fixture_kinds)) != len(self.requested_fixture_kinds):
            raise ValueError("requested fixture kinds must be unique")
        return self


class GenerationManifest(FrozenModel):
    manifest_id: Identifier
    version: SemanticVersion
    configuration: GenerationConfiguration
    case_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M2502_MAX_CASES)
    reproducibility_digest: Sha256Digest
    fixture_summary: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M2502_MAX_FIXTURE_LABELS
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2502_MAX_EVIDENCE)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> GenerationManifest:
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("manifest case ids must be unique")
        return self


class SyntheticTruthCorpus(FrozenModel):
    corpus_id: Identifier
    version: SemanticVersion
    cases: tuple[SyntheticTruthCase, ...] = Field(min_length=1, max_length=M2502_MAX_CASES)
    manifest: GenerationManifest
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2502_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2502_MAX_EVIDENCE)

    @model_validator(mode="after")
    def corpus_is_closed(self) -> SyntheticTruthCorpus:
        case_ids = tuple(item.case_id for item in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("corpus case ids must be unique")
        if set(case_ids) != set(self.manifest.case_ids):
            raise ValueError("manifest must enumerate every corpus case")
        return self


class GeneratorFinding(FrozenModel):
    finding_id: Identifier
    code: GeneratorFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2502_MAX_EVIDENCE)


class GenerateProteotypeSyntheticTruthRequest(FrozenModel):
    """Provisional request bound to the M25-01 stability result."""

    operation: Literal["generate_proteotype_synthetic_truth"] = M2502_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2502_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: GenerationConfiguration
    requested_case_count: int = Field(ge=1, le=M2502_MAX_CASES)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2502_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> GenerateProteotypeSyntheticTruthRequest:
        if self.upstream_result.media_type != M2502_M2501_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M25-01 stability result")
        return self


class ProteotypeSyntheticTruthResult(FrozenModel):
    """Synthetic-truth corpus with reproducibility and explicit abstention."""

    output_type: Literal["proteotype_synthetic_truth"] = "proteotype_synthetic_truth"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2502_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: GenerateProteotypeSyntheticTruthRequest
    status: GenerationStatus
    corpus: SyntheticTruthCorpus | None = None
    manifest: GenerationManifest | None = None
    findings: tuple[GeneratorFinding, ...] = Field(default=(), max_length=M2502_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M2502_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2502_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeSyntheticTruthResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is GenerationStatus.GENERATED:
            if (
                self.corpus is None
                or self.manifest is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("generated result requires a supported corpus and manifest")
        elif (
            self.corpus is not None
            or self.manifest is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no corpus and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2502_CONTRACT_VERSION",
    "M2502_GATE",
    "M2502_M2501_INPUT_MEDIA_TYPE",
    "M2502_MAX_CANONICAL_REQUEST_BYTES",
    "M2502_MAX_CANONICAL_RESULT_BYTES",
    "M2502_MAX_CASES",
    "M2502_MAX_EVIDENCE",
    "M2502_MAX_FEATURES",
    "M2502_MAX_FINDINGS",
    "M2502_MAX_FIXTURE_LABELS",
    "M2502_MODULE_ID",
    "M2502_OPERATION",
    "M2502_OUTPUT_MEDIA_TYPE",
    "M2502_OWNER",
    "M2502_PARENT",
    "M2502_PROVISIONAL_ABI",
    "M2502_SAFETY_CLASS",
    "FixtureKind",
    "GenerateProteotypeSyntheticTruthRequest",
    "GenerationConfiguration",
    "GenerationManifest",
    "GenerationStatus",
    "GeneratorFinding",
    "GeneratorFindingCode",
    "ProteotypeSyntheticTruthResult",
    "SyntheticTruthCase",
    "SyntheticTruthCorpus",
    "TruthRepresentation",
]
