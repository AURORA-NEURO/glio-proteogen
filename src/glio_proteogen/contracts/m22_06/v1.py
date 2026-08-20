"""Provisional M22-06 robustness, shift, and OOD challenge contracts.

The dossier describes a challenge engine beneath protein-RNA discordance.  It
must exercise missing data, low input, corruption, batch/platform/site shift,
artifact, and novel-state scenarios, while unsupported challenges abstain
explicitly instead of being treated as negative evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m22_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 7816-7856.  Owner confirmation and implementation details remain
# pending.
M2206_MODULE_ID: Final = "GLIO-PROTEOGEN-M22-06"
M2206_OPERATION: Final = "challenge_protein_rna_discordance_robustness_surface"
M2206_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2206_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-06+json"
M2206_M2205_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-05+json"
M2206_PARENT: Final = "protein-RNA discordance"
M2206_OWNER: Final = "Bioinformatics"
M2206_SAFETY_CLASS: Final = "S3"
M2206_GATE: Final = "G3"
M2206_PROVISIONAL_ABI: Final = True
M2206_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2206_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7816-7856"
M2206_MAX_SCENARIOS: Final = 256
M2206_MAX_OBSERVATIONS: Final = 512
M2206_MAX_EVIDENCE: Final = 64
M2206_MAX_FINDINGS: Final = 64
M2206_MAX_CHALLENGE_KINDS: Final = 8
M2206_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2206_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2206_EVIDENCE_CLAIM: Final = (
    "Caller-declared M22-06 robustness, shift, OOD, and safe-failure evidence; "
    "issuer authority is not authenticated."
)


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
        min_length=1, max_length=M2206_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2206_MAX_EVIDENCE)


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2206_MAX_EVIDENCE)

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
        min_length=M2206_MAX_CHALLENGE_KINDS, max_length=M2206_MAX_CHALLENGE_KINDS
    )
    ood_threshold: float = Field(ge=0.0, le=1.0)
    unsupported_abstention_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2206_MAX_EVIDENCE)

    @model_validator(mode="after")
    def challenge_kinds_are_unique(self) -> RobustnessConfiguration:
        if len(set(self.required_challenge_kinds)) != len(self.required_challenge_kinds):
            raise ValueError("required challenge kinds must be unique")
        return self


class RobustnessSurface(FrozenModel):
    surface_id: Identifier
    version: SemanticVersion
    scenarios: tuple[ChallengeScenario, ...] = Field(min_length=1, max_length=M2206_MAX_SCENARIOS)
    observations: tuple[RobustnessObservation, ...] = Field(
        min_length=1, max_length=M2206_MAX_OBSERVATIONS
    )
    configuration: RobustnessConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2206_MAX_EVIDENCE)

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
        required = set(self.configuration.required_challenge_kinds)
        present = {item.kind for item in self.scenarios}
        if present != required:
            raise ValueError("surface must include every configured challenge kind exactly")
        observed = {item.scenario_id for item in self.observations}
        if observed != allowed:
            raise ValueError("surface must include one or more observations for every scenario")
        return self


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2206_MAX_EVIDENCE)


class ChallengeFinding(FrozenModel):
    finding_id: Identifier
    code: ChallengeFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2206_MAX_EVIDENCE)


class ChallengeProteinRnaDiscordanceRobustnessRequest(FrozenModel):
    """Provisional request bound to the M22-05 discordance result."""

    operation: Literal["challenge_protein_rna_discordance_robustness_surface"] = M2206_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2206_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    scenarios: tuple[ChallengeScenario, ...] = Field(min_length=1, max_length=M2206_MAX_SCENARIOS)
    configuration: RobustnessConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2206_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ChallengeProteinRnaDiscordanceRobustnessRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        if self.upstream_result.media_type != M2206_M2205_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M22-05 discordance result")
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("request scenario ids must be unique")
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
            raise ValueError("request source artifacts must include M22-05 evidence")
        return self


def _provenance_binding_error(
    result: ProteinRnaDiscordanceRobustnessChallengeResult,
) -> str | None:
    request = result.request
    expected_inputs = tuple(
        dict.fromkeys(
            (
                canonical_request_digest(request),
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
            )
        )
    )
    expected_configuration = (
        request.configuration.evidence[0].reference.digest
        if request.configuration.evidence
        else request.source_artifacts[0].digest
    )
    provenance_checks = (
        (
            result.provenance.module_id == M2206_MODULE_ID,
            "result provenance module does not bind M22-06",
        ),
        (
            result.provenance.module_version == M2206_CONTRACT_VERSION,
            "result provenance version does not bind M22-06",
        ),
        (
            result.provenance.configuration_digest == expected_configuration,
            "result provenance configuration does not bind robustness policy",
        ),
        (
            result.provenance.input_digests == expected_inputs,
            "result provenance inputs do not bind request and source artifacts",
        ),
    )
    for bound, message in provenance_checks:
        if not bound:
            return message
    return None


class ProteinRnaDiscordanceRobustnessChallengeResult(FrozenModel):
    """Robustness surface, OOD scores, and explicit safe-failure report."""

    output_type: Literal["protein_rna_discordance_robustness_challenge"] = (
        "protein_rna_discordance_robustness_challenge"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2206_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ChallengeProteinRnaDiscordanceRobustnessRequest
    status: RobustnessStatus
    robustness_surface: RobustnessSurface | None = None
    safe_failure_report: SafeFailureReport | None = None
    findings: tuple[ChallengeFinding, ...] = Field(default=(), max_length=M2206_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein-RNA discordance"] = M2206_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2206_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result identifier must be derived from request digest")
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
        provenance_error = _provenance_binding_error(self)
        if provenance_error is not None:
            raise ValueError(provenance_error)
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2206_CONTRACT_VERSION",
    "M2206_DOSSIER_SHA256",
    "M2206_DOSSIER_SLICE",
    "M2206_EVIDENCE_CLAIM",
    "M2206_GATE",
    "M2206_M2205_INPUT_MEDIA_TYPE",
    "M2206_MAX_CANONICAL_REQUEST_BYTES",
    "M2206_MAX_CANONICAL_RESULT_BYTES",
    "M2206_MAX_CHALLENGE_KINDS",
    "M2206_MAX_EVIDENCE",
    "M2206_MAX_FINDINGS",
    "M2206_MAX_OBSERVATIONS",
    "M2206_MAX_SCENARIOS",
    "M2206_MODULE_ID",
    "M2206_OPERATION",
    "M2206_OUTPUT_MEDIA_TYPE",
    "M2206_OWNER",
    "M2206_PARENT",
    "M2206_PROVISIONAL_ABI",
    "M2206_SAFETY_CLASS",
    "ChallengeDisposition",
    "ChallengeFinding",
    "ChallengeFindingCode",
    "ChallengeKind",
    "ChallengeProteinRnaDiscordanceRobustnessRequest",
    "ChallengeScenario",
    "ChallengeSeverity",
    "OODBand",
    "ProteinRnaDiscordanceRobustnessChallengeResult",
    "RobustnessConfiguration",
    "RobustnessObservation",
    "RobustnessStatus",
    "RobustnessSurface",
    "SafeFailureReport",
]
