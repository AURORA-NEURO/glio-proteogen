"""Deterministic robustness and OOD challenge runtime for provisional M24-06."""

from __future__ import annotations

from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06 import (
    M2406_CONTRACT_VERSION,
    M2406_MODULE_ID,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
    ChallengeDisposition,
    ChallengeFinding,
    ChallengeFindingCode,
    ChallengeKind,
    ChallengeScenario,
    ChallengeSeverity,
    OODBand,
    RobustnessObservation,
    RobustnessStatus,
    RobustnessSurface,
    SafeFailureReport,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import Limitation, SupportStatus
from glio_proteogen.kernel.strict_json import strict_json_loads

from .._m24_runtime_common import (
    AuthorizationError,
    evidence,
    preflight,
    provenance,
    support,
    uncertainty,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_challenges",
        statement=(
            "Challenge scenarios, perturbation labels, thresholds and source evidence are "
            "caller-declared; no raw assay or cohort bytes are traversed."
        ),
    ),
    Limitation(
        code="ood_not_biology",
        statement=(
            "OOD scores are deterministic robustness-screen values, not biological probability, "
            "clinical risk or glioma inference."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement="M24-06 remains 0.1.0-provisional pending Quality engineering confirmation.",
    ),
)


class M2406ReplayError(ValueError):
    """Raised when an M24-06 result fails semantic replay."""


def _result_id(request_digest: str) -> str:
    return "m2406.result." + request_digest.removeprefix("sha256:")


def _score(scenario_kind: ChallengeKind, severity: ChallengeSeverity) -> float:
    if scenario_kind is ChallengeKind.NOVEL_STATE:
        return 0.95
    return {
        ChallengeSeverity.ROUTINE: 0.15,
        ChallengeSeverity.MATERIAL: 0.55,
        ChallengeSeverity.CRITICAL: 0.9,
    }[severity]


def _band(score: float, threshold: float) -> OODBand:
    if score > threshold:
        return OODBand.OUT_OF_DOMAIN
    if score >= threshold * 0.75:
        return OODBand.BORDERLINE
    return OODBand.IN_DOMAIN


def _observation(
    scenario: ChallengeScenario,
    threshold: float,
) -> RobustnessObservation:
    score = _score(scenario.kind, scenario.severity)
    challenged = max(0.0, 1.0 - (score * 0.5))
    within = scenario.expected_disposition is ChallengeDisposition.WITHIN_ENVELOPE
    return RobustnessObservation(
        observation_id=f"m2406.observation.{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        metric="caller_declared_robustness_margin",
        baseline_value=1.0,
        challenged_value=challenged,
        envelope_lower=1.0 - threshold,
        envelope_upper=1.0,
        within_envelope=within,
        ood_score=score,
        ood_band=_band(score, threshold),
        disposition=scenario.expected_disposition,
        evidence=evidence(scenario.source_artifacts, "Caller-declared challenge evidence."),
    )


def _findings(
    request: ChallengeBiomarkerPanelRobustnessRequest,
) -> tuple[ChallengeFinding, ...]:
    findings: list[ChallengeFinding] = []
    required = set(request.configuration.required_challenge_kinds)
    present = {scenario.kind for scenario in request.scenarios}
    findings.extend(
        ChallengeFinding(
            finding_id=f"m2406.missing.{kind.value}",
            code=ChallengeFindingCode.INPUT_INCOMPLETE,
            message=f"Required challenge kind {kind.value} is missing.",
            evidence=evidence(request.source_artifacts, "Challenge completeness evidence."),
        )
        for kind in sorted(required - present, key=lambda value: value.value)
    )
    for scenario in request.scenarios:
        if (
            scenario.expected_disposition is ChallengeDisposition.WITHIN_ENVELOPE
            and _score(scenario.kind, scenario.severity) > request.configuration.ood_threshold
        ):
            findings.append(
                ChallengeFinding(
                    finding_id=f"m2406.ood.{scenario.scenario_id}",
                    code=ChallengeFindingCode.OOD_STATE,
                    message=(
                        f"{scenario.kind.value} exceeds the configured OOD threshold and "
                        "cannot be treated as within the robustness envelope."
                    ),
                    evidence=evidence(request.source_artifacts, "OOD threshold evidence."),
                )
            )
        if scenario.expected_disposition is ChallengeDisposition.ABSTAIN_UNSUPPORTED:
            code = ChallengeFindingCode.UNSUPPORTED_PERTURBATION
            message = f"{scenario.kind.value} is explicitly unsupported and must abstain."
        elif scenario.expected_disposition is ChallengeDisposition.REVIEW_REQUIRED:
            code = ChallengeFindingCode.ENVELOPE_EXCEEDED
            message = f"{scenario.kind.value} exceeds the caller-declared robustness envelope."
        else:
            continue
        findings.append(
            ChallengeFinding(
                finding_id=f"m2406.challenge.{scenario.scenario_id}",
                code=code,
                message=message,
                evidence=evidence(scenario.source_artifacts, "Challenge disposition evidence."),
            )
        )
    return tuple(findings)


class M2406RobustnessOODChallenger:
    """Challenge a declared surface while preserving safe abstention."""

    __slots__ = ()

    def evaluate(self, request: object) -> BiomarkerPanelRobustnessChallengeResult:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request)
            validated = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight(request, M2406_MODULE_ID)
            validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight(validated, M2406_MODULE_ID)
        canonical = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(validated), strict=True)
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        supported = not findings
        surface = None
        safe_failure = None
        if supported:
            observations = tuple(
                _observation(scenario, canonical.configuration.ood_threshold)
                for scenario in canonical.scenarios
            )
            surface = RobustnessSurface(
                surface_id=f"m2406.surface.{request_digest.removeprefix('sha256:')}",
                version=canonical.configuration.version,
                scenarios=canonical.scenarios,
                observations=observations,
                configuration=canonical.configuration,
                evidence=evidence(canonical.source_artifacts, "Robustness challenge evidence."),
            )
        else:
            safe_failure = SafeFailureReport(
                report_id=f"m2406.safe-failure.{request_digest.removeprefix('sha256:')}",
                version=canonical.configuration.version,
                trigger="unsupported, incomplete or out-of-envelope challenge material",
                action=(
                    "abstain and require human review; do not convert the challenge to "
                    "negative evidence"
                ),
                recovery_note="Supply all required supported challenge kinds and locked evidence.",
                evidence=evidence(canonical.source_artifacts, "Safe-failure evidence."),
            )
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_robustness_challenge",
            "result_id": _result_id(request_digest),
            "result_version": M2406_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + "0" * 64,
            "request": canonical,
            "status": RobustnessStatus.EVALUATED if supported else RobustnessStatus.ABSTAINED,
            "robustness_surface": surface,
            "safe_failure_report": safe_failure,
            "findings": findings,
            "abstention_reason": (
                None if supported else "M24-06 abstained pending robustness challenge review."
            ),
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": support(
                SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                "robustness_surface_evaluated" if supported else "robustness_review_required",
                (
                    "All required challenge kinds are represented by supported scenarios."
                    if supported
                    else (
                        "One or more challenge scenarios are unsupported, incomplete or "
                        "out of envelope."
                    )
                ),
            ),
            "uncertainty": uncertainty(M2406_MODULE_ID),
            "provenance": provenance(
                canonical.context,
                (canonical.upstream_result, *canonical.source_artifacts),
                request_digest,
                M2406_MODULE_ID,
                M2406_CONTRACT_VERSION,
                canonical_request_digest(canonical.configuration),
            ),
            "evidence": evidence(
                (canonical.upstream_result, *canonical.source_artifacts),
                "Robustness challenge source evidence.",
            ),
            "limitations": _LIMITATIONS,
            "human_review_required": not supported,
        }
        provisional = BiomarkerPanelRobustnessChallengeResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return BiomarkerPanelRobustnessChallengeResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self, result: BiomarkerPanelRobustnessChallengeResult
    ) -> BiomarkerPanelRobustnessChallengeResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2406ReplayError("M24-06 request digest mismatch")  # noqa: TRY003
        if result.result_id != _result_id(result.request_digest):
            raise M2406ReplayError("M24-06 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2406ReplayError("M24-06 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = BiomarkerPanelRobustnessChallengeResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.evaluate(replayed.request)
        except Exception as error:
            raise M2406ReplayError from error
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2406ReplayError("M24-06 semantic replay mismatch")  # noqa: TRY003
        return replayed


def challenge_biomarker_panel_robustness(
    request: object,
) -> BiomarkerPanelRobustnessChallengeResult:
    return M2406RobustnessOODChallenger().evaluate(request)


def preflight_m2406_authorization(candidate: object) -> None:
    preflight(candidate, M2406_MODULE_ID)


__all__ = [
    "AuthorizationError",
    "M2406ReplayError",
    "M2406RobustnessOODChallenger",
    "challenge_biomarker_panel_robustness",
    "preflight_m2406_authorization",
]
