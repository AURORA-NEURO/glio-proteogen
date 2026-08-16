"""Executable M10-01 evaluator for supported, unsafe, and replay paths."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m10_01 import (
    FormalProteinRnaDiscordanceStateSchema,
    ProteinRnaFeatureDefinition,
    ProteinRnaFeatureValue,
    ProteinRnaFeatureValueKind,
    ProteinRnaInvariant,
    ProteinRnaInvariantSeverity,
    ProteinRnaMissingness,
    ValidateProteinRnaDiscordanceStateRequest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema import (
    M1001AuthorizationError,
    M1001FormalStateEngine,
)

_DIGEST = "sha256:" + ("1" * 64)
_SCENARIOS = Path(__file__).with_name("scenarios.json")


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context() -> ExecutionContext:
    refs = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=_artifact("evidence.identity"),
        ),
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended_use"),
    )
    return ExecutionContext(
        request_id="request.m10-01-eval",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def make_request(
    expression: str = "protein.ratio >= 0.5",
    severity: str = "error",
    state: str = "observed",
) -> ValidateProteinRnaDiscordanceStateRequest:
    feature = ProteinRnaFeatureDefinition(
        feature_id="protein.ratio",
        version="1.0.0",
        value_kind=ProteinRnaFeatureValueKind.SCALAR,
        unit="ratio",
        allowed_missingness=(ProteinRnaMissingness.MISSING, ProteinRnaMissingness.OBSERVED),
        domain_lower=0.0,
        domain_upper=1.0,
    )
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.ratio",
        expression=expression,
        severity=ProteinRnaInvariantSeverity(severity),
        feature_ids=(feature.feature_id,),
    )
    schema = FormalProteinRnaDiscordanceStateSchema(
        schema_id="schema.protein-rna-eval",
        version="1.0.0",
        features=(feature,),
        invariants=(invariant,),
    )
    feature_state = ProteinRnaMissingness(state)
    return ValidateProteinRnaDiscordanceStateRequest(
        request_id="request.m10-01-eval",
        context=_context(),
        state_schema=schema,
        values=(
            ProteinRnaFeatureValue(
                feature_id=feature.feature_id,
                state=feature_state,
                unit=feature.unit,
                scalar_value=0.75 if feature_state is ProteinRnaMissingness.OBSERVED else None,
            ),
        ),
        source_artifacts=(_artifact("source.state"),),
    )


def evaluate() -> dict[str, Any]:
    """Run the frozen matrix and return machine-readable evidence."""

    scenarios = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    engine = M1001FormalStateEngine()
    checks: dict[str, bool] = {}
    for scenario in scenarios:
        request = make_request(scenario["expression"], scenario["severity"], scenario["state"])
        result = engine.execute(request).result
        checks[str(scenario["id"])] = result.status.value == scenario["expected"]
    supported = engine.execute(make_request())
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = supported.result.model_copy(update={"result_id": "result.tampered"})
    checks["replay"] = replay.verified
    checks["tamper_rejected"] = not engine.verify(tampered, supported.canonical_bytes).verified
    denied = make_request().model_copy(
        update={
            "context": _context().model_copy(
                update={
                    "references": _context().references.model_copy(
                        update={
                            "consent": _context().references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    try:
        engine.execute(denied)
    except M1001AuthorizationError:
        checks["authorization_fail_closed"] = True
    else:
        checks["authorization_fail_closed"] = False
    return {
        "module_id": "GLIO-PROTEOGEN-M10-01",
        "contract_version": "0.1.0-provisional",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "supported_status": supported.result.status.value,
        "supported_digest": supported.result.result_digest,
    }


def main() -> int:
    report = evaluate()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
