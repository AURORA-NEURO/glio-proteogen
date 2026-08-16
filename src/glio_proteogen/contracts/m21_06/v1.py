"""Provisional M21-06 robustness, shift, and OOD challenge contracts.

The dossier requires missing-data, low-input, corruption, batch/platform/site
shift, artifact, and novel-state challenges.  Unsupported perturbations must
abstain; they never become a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m21_06.canonical import (
    canonical_request_digest,
    result_identifier,
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

# PROVISIONAL ABI: inferred solely from dossier lines 7456-7496.
M2106_MODULE_ID: Final = "GLIO-PROTEOGEN-M21-06"
M2106_OPERATION: Final = "challenge_complex_activity_robustness_surface"
M2106_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2106_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-06+json"
M2106_M2105_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-05+json"
M2106_PARENT: Final = "complex activity"
M2106_OWNER: Final = "Computational biology"
M2106_SAFETY_CLASS: Final = "S3"
M2106_GATE: Final = "G3"
M2106_PROVISIONAL_ABI: Final = True
M2106_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2106_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7456-7496"
M2106_EVIDENCE_CLAIM: Final = (
    "Caller-declared robustness, shift, perturbation and OOD challenge material; "
    "issuer authority is not authenticated."
)
M2106_MAX_SCENARIOS: Final = 256
M2106_MAX_OBSERVATIONS: Final = 512
M2106_MAX_EVIDENCE: Final = 64
M2106_MAX_FINDINGS: Final = 64
M2106_MAX_CHALLENGE_KINDS: Final = 8
M2106_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2106_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class ChallengeKind(StrEnum):
    MISSING_DATA = "missing_data"
    LOW_INPUT = "low_input"
    CORRUPTION = "corruption"
    BATCH_SHIFT = "batch_shift"
    PLATFORM_SHIFT = "platform_shift"
    SITE_SHIFT = "site_shift"
    ARTIFACT = "artifact"
    NOVEL_STATE = "novel_state"


class ChallengeSeverity(StrEnum):
    ROUTINE = "routine"
    MATERIAL = "material"
    CRITICAL = "critical"


class ChallengeDisposition(StrEnum):
    WITHIN_ENVELOPE = "within_envelope"
    REVIEW_REQUIRED = "review_required"
    ABSTAIN_UNSUPPORTED = "abstain_unsupported"


class OODBand(StrEnum):
    IN_DOMAIN = "in_domain"
    BORDERLINE = "borderline"
    OUT_OF_DOMAIN = "out_of_domain"
    NOT_EVALUABLE = "not_evaluable"


class RobustnessStatus(StrEnum):
    EVALUATED = "evaluated"
    ABSTAINED = "abstained"


class ChallengeFindingCode(StrEnum):
    ENVELOPE_EXCEEDED = "envelope_exceeded"
    OOD_STATE = "ood_state"
    INPUT_INCOMPLETE = "input_incomplete"
    UNSUPPORTED_PERTURBATION = "unsupported_perturbation"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ChallengeScenario(FrozenModel):
    scenario_id: Identifier
    kind: ChallengeKind
    severity: ChallengeSeverity
    perturbation: NonEmptyStr
    expected_disposition: ChallengeDisposition
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2106_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2106_MAX_EVIDENCE)


class RobustnessObservation(FrozenModel):
    observation_id: Identifier
    scenario_id: Identifier
    metric: NonEmptyStr
    baseline_value: float
    challenged_value: float
    envelope_lower: float | None = None
    envelope_upper: float | None = None
    within_envelope: bool
    ood_score: float = Field(ge=0.0, le=1.0)
    ood_band: OODBand
    disposition: ChallengeDisposition
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2106_MAX_EVIDENCE)

    @model_validator(mode="after")
    def envelope_bounds_are_ordered(self) -> RobustnessObservation:
        if (
            self.envelope_lower is not None
            and self.envelope_upper is not None
            and self.envelope_lower > self.envelope_upper
        ):
            raise ValueError("robustness envelope bounds must be ordered")
        if self.disposition is ChallengeDisposition.WITHIN_ENVELOPE and not self.within_envelope:
            raise ValueError("within-envelope disposition requires an in-envelope observation")
        return self


class RobustnessConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_challenge_kinds: tuple[ChallengeKind, ...] = Field(
        min_length=M2106_MAX_CHALLENGE_KINDS, max_length=M2106_MAX_CHALLENGE_KINDS
    )
    ood_threshold: float = Field(ge=0.0, le=1.0)
    unsupported_abstention_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2106_MAX_EVIDENCE)

    @model_validator(mode="after")
    def challenge_kinds_are_unique(self) -> RobustnessConfiguration:
        if len(set(self.required_challenge_kinds)) != len(self.required_challenge_kinds):
            raise ValueError("required challenge kinds must be unique")
        if set(self.required_challenge_kinds) != set(ChallengeKind):
            raise ValueError("configuration must require every locked challenge kind")
        return self


class RobustnessSurface(FrozenModel):
    surface_id: Identifier
    version: SemanticVersion
    scenarios: tuple[ChallengeScenario, ...] = Field(min_length=1, max_length=M2106_MAX_SCENARIOS)
    observations: tuple[RobustnessObservation, ...] = Field(
        min_length=1, max_length=M2106_MAX_OBSERVATIONS
    )
    configuration: RobustnessConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2106_MAX_EVIDENCE)

    @model_validator(mode="after")
    def surface_is_closed(self) -> RobustnessSurface:
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario ids must be unique")
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation ids must be unique")
        allowed = set(scenario_ids)
        if any(item.scenario_id not in allowed for item in self.observations):
            raise ValueError("observation references an unknown scenario")
        if {item.scenario_id for item in self.observations} != allowed:
            raise ValueError("robustness surface requires one observation for every scenario")
        scenario_by_id = {scenario.scenario_id: scenario for scenario in self.scenarios}
        for observation in self.observations:
            scenario = scenario_by_id[observation.scenario_id]
            if observation.disposition is not scenario.expected_disposition:
                raise ValueError("observation disposition must match scenario expectation")
            if observation.disposition is ChallengeDisposition.WITHIN_ENVELOPE and (
                observation.ood_band not in {OODBand.IN_DOMAIN, OODBand.BORDERLINE}
                or not observation.within_envelope
            ):
                raise ValueError("within-envelope observations must remain in supported OOD bands")
            if observation.disposition is ChallengeDisposition.ABSTAIN_UNSUPPORTED and (
                observation.ood_band not in {OODBand.OUT_OF_DOMAIN, OODBand.NOT_EVALUABLE}
                or observation.within_envelope
            ):
                raise ValueError("unsupported observations must be OOD or not evaluable")
        return self


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2106_MAX_EVIDENCE)


class ChallengeFinding(FrozenModel):
    finding_id: Identifier
    code: ChallengeFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2106_MAX_EVIDENCE)


class ChallengeComplexActivityRobustnessRequest(FrozenModel):
    """Provisional request bound to the M21-05 estimator result."""

    operation: Literal["challenge_complex_activity_robustness_surface"] = M2106_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2106_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    scenarios: tuple[ChallengeScenario, ...] = Field(min_length=1, max_length=M2106_MAX_SCENARIOS)
    configuration: RobustnessConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2106_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ChallengeComplexActivityRobustnessRequest:
        if self.upstream_result.media_type != M2106_M2105_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M21-05 estimator result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must equal request id")
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("request scenario ids must be unique")
        if {item.kind for item in self.scenarios} != set(
            self.configuration.required_challenge_kinds
        ):
            raise ValueError("request scenarios must cover the locked challenge configuration")
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
            raise ValueError("request source artifacts must include the M21-05 result")
        return self


class ComplexActivityRobustnessChallengeResult(FrozenModel):
    """Robustness surface, OOD scores, and explicit safe-failure report."""

    output_type: Literal["complex_activity_robustness_challenge"] = (
        "complex_activity_robustness_challenge"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2106_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ChallengeComplexActivityRobustnessRequest
    status: RobustnessStatus
    robustness_surface: RobustnessSurface | None = None
    safe_failure_report: SafeFailureReport | None = None
    findings: tuple[ChallengeFinding, ...] = Field(default=(), max_length=M2106_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2106_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2106_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityRobustnessChallengeResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id must be deterministically bound to the request")
        if self.provenance.module_id != M2106_MODULE_ID:
            raise ValueError("provenance module id must match M21-06")
        if self.request.upstream_result.digest not in self.provenance.input_digests:
            raise ValueError("provenance must include the upstream result digest")
        if self.status is RobustnessStatus.EVALUATED:
            if (
                self.robustness_surface is None
                or self.abstention_reason is not None
                or self.safe_failure_report is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported robustness surface")
            if self.robustness_surface.scenarios != self.request.scenarios:
                raise ValueError("evaluated surface scenarios must equal the request scenarios")
            if self.robustness_surface.configuration != self.request.configuration:
                raise ValueError(
                    "evaluated surface configuration must equal the request configuration"
                )
        elif (
            self.robustness_surface is not None
            or self.abstention_reason is None
            or self.safe_failure_report is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if len(self.findings) != len({finding.finding_id for finding in self.findings}):
            raise ValueError("result finding ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2106_CONTRACT_VERSION",
    "M2106_DOSSIER_SHA256",
    "M2106_DOSSIER_SLICE",
    "M2106_EVIDENCE_CLAIM",
    "M2106_GATE",
    "M2106_M2105_INPUT_MEDIA_TYPE",
    "M2106_MAX_CANONICAL_REQUEST_BYTES",
    "M2106_MAX_CANONICAL_RESULT_BYTES",
    "M2106_MAX_CHALLENGE_KINDS",
    "M2106_MAX_EVIDENCE",
    "M2106_MAX_FINDINGS",
    "M2106_MAX_OBSERVATIONS",
    "M2106_MAX_SCENARIOS",
    "M2106_MODULE_ID",
    "M2106_OPERATION",
    "M2106_OUTPUT_MEDIA_TYPE",
    "M2106_OWNER",
    "M2106_PARENT",
    "M2106_PROVISIONAL_ABI",
    "M2106_SAFETY_CLASS",
    "ChallengeComplexActivityRobustnessRequest",
    "ChallengeDisposition",
    "ChallengeFinding",
    "ChallengeFindingCode",
    "ChallengeKind",
    "ChallengeScenario",
    "ChallengeSeverity",
    "ComplexActivityRobustnessChallengeResult",
    "OODBand",
    "RobustnessConfiguration",
    "RobustnessObservation",
    "RobustnessStatus",
    "RobustnessSurface",
    "SafeFailureReport",
]
