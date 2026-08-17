"""Run the locked synthetic M14-02 context stratification matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m14_02 import (
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    StratifierConfiguration,
    StratifierPolicy,
    StratifyProteinSubtypeContextRequest,
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
from glio_proteogen.modules.c14_microenvironment.m14_02_context_subtype_stratifier import (
    M1402AuthorizationError,
    M1402ContextStratifier,
)

MODULE_ID = "GLIO-PROTEOGEN-M14-02"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m14_02" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "curated_context_stratified",
    "bayesian_context_stratified",
    "state_space_context_stratified",
    "foundation_context_stratified",
    "unsupported_method_abstention",
    "conflict_abstention",
    "proxy_blocked",
    "replay_and_tamper",
    "authorization_gate",
)
_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1402-eval": label}),
        media_type=media_type,
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def build_scenario_request(
    method: str = "curated_rule",
    *,
    accepted: bool = True,
    status: ContextObservationStatus = ContextObservationStatus.SUPPORTED,
    proxy: bool = False,
) -> StratifyProteinSubtypeContextRequest:
    observations = tuple(
        ContextObservation(
            observation_id=f"observation.{dimension.value}",
            dimension=dimension,
            value="kinase activity"
            if proxy and dimension is ContextDimension.SUBTYPE
            else f"value-{dimension.value}",
            normalized_value=(
                None
                if status is ContextObservationStatus.UNRESOLVED
                else f"normalized-{dimension.value}"
            ),
            status=status,
            source_artifact=_artifact(f"observation.{dimension.value}"),
            evidence=(
                EvidenceReference(
                    reference=_artifact(f"observation.{dimension.value}"),
                    role="evidence",
                    claim="Locked synthetic M14-02 observation.",
                ),
            ),
        )
        for dimension in tuple(ContextDimension)
    )
    configuration = StratifierConfiguration(
        configuration_id="configuration.m1402",
        version="1.0.0",
        method=method,
        model_reference=_artifact("model"),
        evidence=(
            EvidenceReference(
                reference=_artifact("configuration"),
                role="evidence",
                claim="Locked synthetic M14-02 configuration.",
            ),
        ),
    )
    return StratifyProteinSubtypeContextRequest(
        request_id="request.m1402",
        context=ExecutionContext(
            request_id="request.m1402",
            actor_id="actor.evaluator",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        microenvironment_deconvolution_result=_artifact(
            "microenvironment", "application/vnd.glio-proteogen.m14-01+json"
        ),
        policy=StratifierPolicy(
            required_dimensions=tuple(ContextDimension), configuration=configuration
        ),
        observations=observations,
        source_artifacts=(_artifact("source"),),
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M14-02 fixture case IDs are not locked")
    engine = M1402ContextStratifier()
    checks: list[EvalCheck] = []
    for method, name in (
        ("curated_rule", "curated_context_stratified"),
        ("bayesian_graph", "bayesian_context_stratified"),
        ("state_space", "state_space_context_stratified"),
        ("foundation_assisted", "foundation_context_stratified"),
    ):
        result = engine.infer(build_scenario_request(method))
        checks.append(EvalCheck(name, result.status.value == "stratified", result.status.value))
    for name, request in (
        ("unsupported_method_abstention", build_scenario_request("unknown-method")),
        ("conflict_abstention", build_scenario_request(status=ContextObservationStatus.CONFLICTED)),
        ("proxy_blocked", build_scenario_request(proxy=True)),
    ):
        result = engine.infer(request)
        checks.append(EvalCheck(name, result.status.value == "abstained", result.status.value))
    replay = engine.infer(build_scenario_request())
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(EvalCheck("replay_and_tamper", tamper_rejected, "replay and tamper"))
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1402AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": sha256_digest(fixture),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": passed,
        "total_cases": len(checks),
        "passed": passed == len(checks),
        "checks": [asdict(item) for item in checks],
    }


def main() -> int:
    argparse.ArgumentParser().parse_args()
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
