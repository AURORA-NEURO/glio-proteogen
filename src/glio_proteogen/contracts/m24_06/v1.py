"""Provisional M24-06 robustness, shift, and OOD challenge contracts.

The dossier requires missing-data, low-input, corruption, batch/platform/site
shift, artifact, and novel-state challenges for biomarker panel outputs.
Unsupported challenges abstain explicitly rather than becoming negative
findings; the ABI is provisional pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m24_06.canonical import (
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
# lines 8536-8576. Owner confirmation and implementation details remain
# pending.
M2406_MODULE_ID: Final = "GLIO-PROTEOGEN-M24-06"
M2406_OPERATION: Final = "challenge_biomarker_panel_robustness_surface"
M2406_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2406_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-06+json"
M2406_M2405_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-05+json"
M2406_PARENT: Final = "biomarker panel"
M2406_OWNER: Final = "Quality engineering"
M2406_SAFETY_CLASS: Final = "S3"
M2406_GATE: Final = "G3"
M2406_PROVISIONAL_ABI: Final = True
M2406_MAX_SCENARIOS: Final = 256
M2406_MAX_OBSERVATIONS: Final = 512
M2406_MAX_EVIDENCE: Final = 64
M2406_MAX_FINDINGS: Final = 64
M2406_MAX_CHALLENGE_KINDS: Final = 8
M2406_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2406_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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
        min_length=1, max_length=M2406_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2406_MAX_EVIDENCE)


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2406_MAX_EVIDENCE)

    @model_validator(mode="after")
    def envelope_bounds_are_ordered(self) -> RobustnessObservation:
        if (
            self.envelope_lower is not None
            and self.envelope_upper is not None
            and self.envelope_lower > self.envelope_upper
        ):
            raise ValueError("robustness envelope bounds must be ordered")
        if self.envelope_lower is not None and self.envelope_upper is not None:
            measured_within = self.envelope_lower <= self.challenged_value <= self.envelope_upper
            if self.within_envelope is not measured_within:
                raise ValueError("within-envelope flag must match challenged value")
        if self.disposition is ChallengeDisposition.WITHIN_ENVELOPE and not self.within_envelope:
            raise ValueError("within-envelope disposition requires an in-envelope observation")
        return self


class RobustnessConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_challenge_kinds: tuple[ChallengeKind, ...] = Field(
        min_length=M2406_MAX_CHALLENGE_KINDS, max_length=M2406_MAX_CHALLENGE_KINDS
    )
    ood_threshold: float = Field(ge=0.0, le=1.0)
    unsupported_abstention_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2406_MAX_EVIDENCE)

    @model_validator(mode="after")
    def challenge_kinds_are_unique(self) -> RobustnessConfiguration:
        if len(set(self.required_challenge_kinds)) != len(self.required_challenge_kinds):
            raise ValueError("required challenge kinds must be unique")
        return self


class RobustnessSurface(FrozenModel):
    surface_id: Identifier
    version: SemanticVersion
    scenarios: tuple[ChallengeScenario, ...] = Field(min_length=1, max_length=M2406_MAX_SCENARIOS)
    observations: tuple[RobustnessObservation, ...] = Field(
        min_length=1, max_length=M2406_MAX_OBSERVATIONS
    )
    configuration: RobustnessConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2406_MAX_EVIDENCE)

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
            expected_band = (
                OODBand.OUT_OF_DOMAIN
                if observation.ood_score > self.configuration.ood_threshold
                else (
                    OODBand.BORDERLINE
                    if observation.ood_score >= self.configuration.ood_threshold * 0.75
                    else OODBand.IN_DOMAIN
                )
            )
            if observation.ood_band is not expected_band:
                raise ValueError("observation OOD band must match score and threshold")
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2406_MAX_EVIDENCE)


class ChallengeFinding(FrozenModel):
    finding_id: Identifier
    code: ChallengeFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2406_MAX_EVIDENCE)


class ChallengeBiomarkerPanelRobustnessRequest(FrozenModel):
    """Provisional request bound to the M24-05 biomarker panel result."""

    operation: Literal["challenge_biomarker_panel_robustness_surface"] = M2406_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2406_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    scenarios: tuple[ChallengeScenario, ...] = Field(min_length=1, max_length=M2406_MAX_SCENARIOS)
    configuration: RobustnessConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2406_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ChallengeBiomarkerPanelRobustnessRequest:
        if self.upstream_result.media_type != M2406_M2405_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M24-05 biomarker panel result")
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("request scenario ids must be unique")
        return self


class BiomarkerPanelRobustnessChallengeResult(FrozenModel):
    """Robustness surface, OOD scores, and explicit safe-failure report."""

    output_type: Literal["biomarker_panel_robustness_challenge"] = (
        "biomarker_panel_robustness_challenge"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2406_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ChallengeBiomarkerPanelRobustnessRequest
    status: RobustnessStatus
    robustness_surface: RobustnessSurface | None = None
    safe_failure_report: SafeFailureReport | None = None
    findings: tuple[ChallengeFinding, ...] = Field(default=(), max_length=M2406_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M2406_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2406_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelRobustnessChallengeResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is RobustnessStatus.EVALUATED:
            if (
                self.robustness_surface is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported robustness surface")
        elif (
            self.robustness_surface is not None
            or self.abstention_reason is None
            or self.safe_failure_report is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2406_CONTRACT_VERSION",
    "M2406_GATE",
    "M2406_M2405_INPUT_MEDIA_TYPE",
    "M2406_MAX_CANONICAL_REQUEST_BYTES",
    "M2406_MAX_CANONICAL_RESULT_BYTES",
    "M2406_MAX_CHALLENGE_KINDS",
    "M2406_MAX_EVIDENCE",
    "M2406_MAX_FINDINGS",
    "M2406_MAX_OBSERVATIONS",
    "M2406_MAX_SCENARIOS",
    "M2406_MODULE_ID",
    "M2406_OPERATION",
    "M2406_OUTPUT_MEDIA_TYPE",
    "M2406_OWNER",
    "M2406_PARENT",
    "M2406_PROVISIONAL_ABI",
    "M2406_SAFETY_CLASS",
    "BiomarkerPanelRobustnessChallengeResult",
    "ChallengeBiomarkerPanelRobustnessRequest",
    "ChallengeDisposition",
    "ChallengeFinding",
    "ChallengeFindingCode",
    "ChallengeKind",
    "ChallengeScenario",
    "ChallengeSeverity",
    "OODBand",
    "RobustnessConfiguration",
    "RobustnessObservation",
    "RobustnessStatus",
    "RobustnessSurface",
    "SafeFailureReport",
]
