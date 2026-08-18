"""Deterministic M22-08 evaluator over a frozen evidence-gate matrix."""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m22_08 import (
    M2208_DOSSIER_SHA256,
    M2208_DOSSIER_SLICE,
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ApprovalDecision,
    ApprovalRecord,
    BenchmarkOutcome,
    GateConfiguration,
    GateDecision,
    GateRequirement,
    PostReleaseObligation,
    RequirementCategory,
    ResidualRisk,
    RiskSeverity,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    M2208AuthorizationError,
    M2208EvidenceGateEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M22-08"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m22_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "pass_complete",
    "block_failed_requirement",
    "block_failed_benchmark",
    "block_open_critical_risk",
    "review_deferred_approval",
    "authorization_gate",
    "source_binding_boundary",
    "replay_tamper_determinism",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m2208_fixture": label})


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2208.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type="application/json",
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M22-08 evidence.",
        ),
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    decisions = {
        role: UpstreamDecisionReference(
            decision_id=f"decision.m2208.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}"),
        )
        for role in ("configuration", "provenance", "quality", "support", "intended-use")
    }
    return ContextReferences(
        approved_configuration=decisions["configuration"],
        identity_lineage=IdentityLineageReference(
            decision_id="decision.m2208.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=_digest("identity-binding"),
            evidence=_artifact("control-identity"),
        ),
        provenance=decisions["provenance"],
        consent=ConsentReference(
            decision_id="decision.m2208.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control-consent"),
        ),
        quality=decisions["quality"],
        support=decisions["support"],
        intended_use=decisions["intended-use"],
    )


def _requirements(*, failed: bool = False) -> tuple[GateRequirement, ...]:
    return tuple(
        GateRequirement(
            requirement_id=f"requirement.m2208.{category.value}",
            category=category,
            statement=f"{category.value} evidence is locked.",
            satisfied=not failed or category is not RequirementCategory.CLAIM_CEILING,
            evidence=_evidence(f"requirement-{category.value}"),
        )
        for category in RequirementCategory
    )


def _benchmarks(*, failed: bool = False) -> tuple[BenchmarkOutcome, ...]:
    return (
        BenchmarkOutcome(
            benchmark_id="benchmark.m2208.release",
            name="release-evaluator",
            metric_name="pass_rate",
            observed_value=0.5 if failed else 1.0,
            required_floor=0.95,
            passed=not failed,
            report_artifact=_artifact("benchmark-report"),
            evidence=_evidence("benchmark-evidence"),
        ),
    )


def _risks(*, critical_open: bool = False) -> tuple[ResidualRisk, ...]:
    return (
        ResidualRisk(
            risk_id="risk.m2208.review-only",
            severity=RiskSeverity.CRITICAL if critical_open else RiskSeverity.ROUTINE,
            statement="Research use remains bounded by evidence review.",
            mitigation="Require human review before release exception.",
            accepted=not critical_open,
            evidence=_evidence("risk-evidence"),
        ),
    )


def _approvals(*, deferred: bool = False) -> tuple[ApprovalRecord, ...]:
    return (
        ApprovalRecord(
            approval_id="approval.m2208.quality",
            approver_token="quality-reviewer",  # noqa: S106
            role="Quality engineering",
            decision=ApprovalDecision.DEFER if deferred else ApprovalDecision.APPROVE,
            signature_digest=_digest("quality-signature"),
            evidence=_evidence("approval-evidence"),
        ),
    )


def _obligations() -> tuple[PostReleaseObligation, ...]:
    return (
        PostReleaseObligation(
            obligation_id="obligation.m2208.monitor",
            owner="Quality engineering",
            trigger="new evidence or support boundary",
            action="reopen the gate and record review",
            evidence=_evidence("obligation-evidence"),
        ),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    failed_requirement: bool = False,
    failed_benchmark: bool = False,
    critical_open: bool = False,
    deferred_approval: bool = False,
) -> AdjudicateProteinRnaDiscordanceEvidenceGateRequest:
    proteome = _artifact("mass-spectrometry-proteome")
    genome = _artifact("genome-transcriptome")
    ptm = _artifact("ptm-annotations")
    upstream = _artifact("m2207-upstream-evidence")
    return AdjudicateProteinRnaDiscordanceEvidenceGateRequest(
        request_id="request.m2208.evaluator",
        context=ExecutionContext(
            request_id="request.m2208.evaluator",
            actor_id="actor.m2208.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        mass_spectrometry_proteome=proteome,
        genome_transcriptome=genome,
        ptm_annotations=ptm,
        upstream_evidence=upstream,
        requirements=_requirements(failed=failed_requirement),
        benchmarks=_benchmarks(failed=failed_benchmark),
        residual_risks=_risks(critical_open=critical_open),
        approvals=_approvals(deferred=deferred_approval),
        post_release_obligations=_obligations(),
        configuration=GateConfiguration(
            configuration_id="configuration.m2208.evaluator",
            version="1.0.0",
            evidence=_evidence("configuration"),
        ),
        source_artifacts=(proteome, genome, ptm, upstream),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def _has_decision(result: object, expected: GateDecision) -> bool:
    release_record = getattr(result, "release_record", None)
    return release_record is not None and release_record.decision is expected


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M22-08 fixture case IDs are not locked")
    engine = M2208EvidenceGateEngine()
    checks: list[EvalCheck] = []
    passed = engine.adjudicate(build_scenario_request())
    checks.append(
        EvalCheck(
            "pass_complete",
            _has_decision(passed, GateDecision.PASS),
            passed.status.value,
        )
    )
    blocked_requirement = engine.adjudicate(build_scenario_request(failed_requirement=True))
    checks.append(
        EvalCheck(
            "block_failed_requirement",
            _has_decision(blocked_requirement, GateDecision.BLOCK),
            blocked_requirement.status.value,
        )
    )
    blocked_benchmark = engine.adjudicate(build_scenario_request(failed_benchmark=True))
    checks.append(
        EvalCheck(
            "block_failed_benchmark",
            _has_decision(blocked_benchmark, GateDecision.BLOCK),
            blocked_benchmark.status.value,
        )
    )
    blocked_risk = engine.adjudicate(build_scenario_request(critical_open=True))
    checks.append(
        EvalCheck(
            "block_open_critical_risk",
            _has_decision(blocked_risk, GateDecision.BLOCK),
            blocked_risk.status.value,
        )
    )
    review = engine.adjudicate(build_scenario_request(deferred_approval=True))
    checks.append(
        EvalCheck(
            "review_deferred_approval",
            _has_decision(review, GateDecision.REVIEW_REQUIRED),
            review.status.value,
        )
    )
    try:
        engine.adjudicate(build_scenario_request(accepted=False))
    except M2208AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied controls rejected"))
    invalid_payload = build_scenario_request().model_dump(mode="python")
    invalid_payload["source_artifacts"] = invalid_payload["source_artifacts"][:-1]
    try:
        AdjudicateProteinRnaDiscordanceEvidenceGateRequest.model_validate(invalid_payload)
    except ValidationError:
        source_ok = True
    else:
        source_ok = False
    checks.append(
        EvalCheck("source_binding_boundary", source_ok, "declared inputs must be source-bound")
    )
    replay = engine.replay(passed)
    tampered = passed.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.replay(tampered)
    except ValueError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    repeat = engine.adjudicate(build_scenario_request())
    checks.append(
        EvalCheck(
            "replay_tamper_determinism",
            replay == passed and tamper_rejected and repeat == passed,
            passed.result_digest,
        )
    )
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2208_DOSSIER_SHA256,
        "dossier_slice": M2208_DOSSIER_SLICE,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(item.passed for item in checks),
        "total_cases": len(checks),
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail} for item in checks
        ],
        "passed": len(checks) == len(case_ids) and all(item.passed for item in checks),
        "schema_count": len(contract_json_schemas()),
        "request_digest": canonical_request_digest(build_scenario_request()),
        "uncertainty_dimensions": 7,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
