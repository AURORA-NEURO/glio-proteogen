"""Genuine M13-01 hypothesis-registry scenarios and evaluator."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m13_01 import (
    BiologicalHypothesis,
    CompetingExplanation,
    EvidenceTier,
    FalsificationRule,
    RegisterProteotypeHypothesesRequest,
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
from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_01_biological_hypothesis_registry as m1301_runtime,
)

_ROOT: Final = Path(__file__).parents[2]
_FIXTURE: Final = _ROOT / "tests" / "fixtures" / "m13_01" / "scenarios.json"
_INVALID_FIXTURE: Final = "M13-01 fixture scenarios must be a list"


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m1301.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1301": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M13-01 registry evidence.",
    )


def _context() -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m1301.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}"),
        )

    return ExecutionContext(
        request_id="request.synthetic.m1301",
        actor_id="actor.synthetic.m1301",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m1301.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"identity": "synthetic-m1301"}),
                evidence=_artifact("control-identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m1301.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _hypothesis(
    identifier: str,
    *,
    statement: str = "supported",
    failure_condition: str = "passed",
) -> BiologicalHypothesis:
    return BiologicalHypothesis(
        hypothesis_id=f"hypothesis.synthetic.m1301.{identifier}",
        version="1.0.0",
        statement=statement,
        mechanism_class="caller_declared_proteotype_mechanism",
        target_ids=(f"target.synthetic.m1301.{identifier}",),
        competing_explanations=(
            CompetingExplanation(
                explanation_id=f"explanation.synthetic.m1301.{identifier}",
                statement="An orthogonal mechanism remains possible.",
                distinction="Requires a distinct evidence tier.",
                required_evidence=(_evidence(f"alternative-{identifier}"),),
            ),
        ),
        falsification_rules=(
            FalsificationRule(
                rule_id=f"rule.synthetic.m1301.{identifier}",
                criterion="Caller-declared falsification criterion.",
                failure_condition=failure_condition,
                required_evidence=(_evidence(f"rule-{identifier}"),),
                prohibited_interpretation="No kinase or treatment inference.",
            ),
        ),
        evidence_tiers=(
            EvidenceTier(
                tier=1,
                label="direct",
                rationale="Direct caller-declared evidence only.",
                evidence=(_evidence(f"tier-{identifier}"),),
            ),
        ),
        prohibited_interpretations=("kinase activity", "treatment recommendation"),
        evidence=(_evidence(f"hypothesis-{identifier}"),),
    )


def build_scenario_request(
    case_id: str = "supported_registry",
) -> RegisterProteotypeHypothesesRequest:
    settings = {
        "supported_registry": ("supported", "passed"),
        "refuted_hypothesis": ("refuted", "passed"),
        "unknown_hypothesis": ("novel_outcome", "passed"),
        "failed_falsification": ("supported", "failed"),
        "unknown_falsification": ("supported", "unresolved"),
        "multiple_supported": ("supported", "passed"),
    }
    statement, failure = settings.get(case_id, ("supported", "passed"))
    hypotheses: tuple[BiologicalHypothesis, ...] = (
        _hypothesis(case_id, statement=statement, failure_condition=failure),
    )
    if case_id == "multiple_supported":
        hypotheses = (
            *hypotheses,
            _hypothesis("second", statement="true", failure_condition="pass"),
        )
    return RegisterProteotypeHypothesesRequest(
        request_id=f"request.synthetic.m1301.{case_id}",
        context=_context().model_copy(update={"request_id": f"request.synthetic.m1301.{case_id}"}),
        registry_version="1.0.0",
        hypotheses=hypotheses,
        reviewer_id="reviewer.synthetic.m1301",
        source_artifacts=(_artifact(f"source-{case_id}"),),
    )


def fixture_cases() -> tuple[dict[str, object], ...]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    if not isinstance(scenarios, list):
        raise TypeError(_INVALID_FIXTURE)
    return tuple(item for item in scenarios if isinstance(item, dict))


def run_evaluator() -> dict[str, object]:
    engine = m1301_runtime.M1301HypothesisEngine()
    outcomes: list[dict[str, object]] = []
    for scenario in fixture_cases():
        case_id = str(scenario["case_id"])
        expected = str(scenario["expected"])
        if case_id == "denied_control":
            base = build_scenario_request()
            denied_consent = base.context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
            denied_references = base.context.references.model_copy(
                update={"consent": denied_consent}
            )
            denied = base.model_copy(
                update={
                    "context": base.context.model_copy(update={"references": denied_references})
                }
            )
            try:
                engine.register(denied)
            except m1301_runtime.M1301HypothesisAuthorizationError:
                actual = "authorization_rejected"
            else:
                actual = "unexpected_success"
        else:
            result = engine.register(build_scenario_request(case_id))
            actual = result.status.value
            if case_id == "supported_registry":
                engine.verify(result)
        outcomes.append({"case_id": case_id, "expected": expected, "actual": actual})
    if any(item["expected"] != item["actual"] for item in outcomes):
        raise AssertionError
    return {
        "module_id": "GLIO-PROTEOGEN-M13-01",
        "passed": True,
        "declared": len(outcomes),
        "executed": len(outcomes),
        "failed": [],
        "outcomes": outcomes,
        "fixture_digest": sha256_digest({"scenarios": fixture_cases()}),
    }


__all__ = ["build_scenario_request", "fixture_cases", "run_evaluator"]
