"""Executable evaluator for the provisional M10-05 integrator."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from glio_proteogen.contracts.m10_05 import (
    M1005_M1002_RESULT_MEDIA_TYPE,
    M1005_M1004_RESULT_MEDIA_TYPE,
    ConstraintHardness,
    ConstraintKind,
    IntegrateProteinRnaConstraintsRequest,
    MechanismConstraint,
    MechanismConstraintSet,
)
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
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_05_mechanism_constraint_integrator import (  # noqa: E501
    M1005ConstraintAuthorizationError,
    M1005ReplayVerificationError,
    M1005Service,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M10-05"
EVALUATOR_VERSION: Final = "0.1.0-provisional"
AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "3452-3495"


def _artifact(name: str, fill: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="0.1.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.UNKNOWN
    consent = ConsentState.GRANTED if accepted else ConsentState.UNKNOWN
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config.m1005",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("config", "1"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity.m1005",
            state=identity,
            policy_version="1.0.0",
            binding_digest=_artifact("identity", "2").digest,
            evidence=_artifact("identity", "2"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance.m1005",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("provenance", "3"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent.m1005",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("consent", "4"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality.m1005",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("quality", "5"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support.m1005",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("support", "6"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended.m1005",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("intended", "7"),
        ),
    )


def build_request(
    *,
    hard_expression: str = "always_true",
    soft_expression: str = "always_true",
    unknown_controls: bool = False,
) -> IntegrateProteinRnaConstraintsRequest:
    """Build a deterministic request with caller-declared opaque artifacts."""

    constraint_evidence = EvidenceReference(
        reference=_artifact("constraint-evidence", "a"),
        role="evidence",
        claim="caller-declared constraint expression",
    )
    constraint_set = MechanismConstraintSet(
        set_id="constraint-set.eval.m1005",
        version="0.1.0",
        reviewed_by="reviewer.m1005",
        constraints=(
            MechanismConstraint(
                constraint_id="constraint.hard.m1005",
                kind=ConstraintKind.BIOLOGICAL_PRIOR,
                hardness=ConstraintHardness.HARD,
                expression=hard_expression,
                feature_ids=("feature.pathway",),
                evidence=(constraint_evidence,),
            ),
            MechanismConstraint(
                constraint_id="constraint.soft.m1005",
                kind=ConstraintKind.ASSAY_PHYSICS,
                hardness=ConstraintHardness.SOFT,
                expression=soft_expression,
                feature_ids=("feature.pathway",),
                weight=0.4,
                evidence=(constraint_evidence,),
            ),
        ),
        evidence=(constraint_evidence,),
    )
    controls = _controls(accepted=not unknown_controls)
    return IntegrateProteinRnaConstraintsRequest(
        request_id="request.eval.m1005",
        context=ExecutionContext(
            request_id="request.eval.m1005",
            actor_id="actor.evaluator.m1005",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=controls,
        ),
        representation_result=_artifact("m1002.result", "8", M1005_M1002_RESULT_MEDIA_TYPE),
        constraint_set=constraint_set,
        advanced_estimator_result=_artifact("m1004.result", "9", M1005_M1004_RESULT_MEDIA_TYPE),
        feature_artifacts=(_artifact("feature.pathway", "b", "application/vnd.opaque+json"),),
    )


def _check(name: str, *, passed: bool, detail: str) -> dict[str, object]:
    return {"id": name, "passed": passed, "detail": detail}


def evaluate() -> dict[str, object]:
    service = M1005Service()
    checks: list[dict[str, object]] = []
    integrated = service.execute(build_request(soft_expression="always_false"))
    checks.append(
        _check(
            "soft_conflict_is_integrated_with_ablation",
            passed=(
                integrated.status.value == "integrated"
                and len(integrated.estimates) == 1
                and len(integrated.ablations) == 1
                and integrated.human_review_required
            ),
            detail="soft conflict is quantified without overriding a hard constraint",
        )
    )
    replay = service.verify(integrated)
    checks.append(
        _check(
            "integrated_replay_is_byte_stable",
            passed=replay.model_dump_json() == integrated.model_dump_json(),
            detail="exact request replay reproduces the integrated envelope",
        )
    )
    hard = service.execute(build_request(hard_expression="always_false"))
    checks.append(
        _check(
            "hard_violation_abstains",
            passed=(
                hard.status.value == "abstained"
                and not hard.estimates
                and hard.human_review_required
                and hard.support_decision.status.value == "review_required"
            ),
            detail="hard violations produce a typed reviewed safe failure",
        )
    )
    unknown = service.execute(build_request(hard_expression="caller_expression"))
    checks.append(
        _check(
            "unknown_expression_abstains",
            passed=unknown.status.value == "abstained" and not unknown.estimates,
            detail="outside-vocabulary expressions never receive heuristic interpretation",
        )
    )
    try:
        service.execute(build_request(unknown_controls=True))
    except M1005ConstraintAuthorizationError:
        controls_fail_closed = True
    else:
        controls_fail_closed = False
    checks.append(
        _check(
            "controls_fail_closed",
            passed=controls_fail_closed,
            detail="identity, consent, and quality controls are read before constraints",
        )
    )
    tampered = integrated.model_copy(update={"abstention_reason": "tampered"})
    try:
        service.verify(tampered)
    except M1005ReplayVerificationError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(
        _check(
            "tampered_result_rejected",
            passed=tamper_rejected,
            detail="changing a derived result region fails full replay verification",
        )
    )
    try:
        strict_json_loads('{"request_id":"a","request_id":"b"}')
    except StrictJsonError:
        duplicate_rejected = True
    else:
        duplicate_rejected = False
    checks.append(
        _check(
            "duplicate_json_keys_rejected",
            passed=duplicate_rejected,
            detail="strict JSON rejects duplicate keys before model traversal",
        )
    )
    try:
        IntegrateProteinRnaConstraintsRequest.model_validate(
            build_request().model_dump(mode="python")
            | {"representation_result": _artifact("wrong", "c")},
            strict=True,
        )
    except ValidationError:
        wrong_media_rejected = True
    else:
        wrong_media_rejected = False
    checks.append(
        _check(
            "wrong_upstream_media_rejected",
            passed=wrong_media_rejected,
            detail="representation and estimator handoffs remain explicitly bound",
        )
    )
    passed = all(item["passed"] is True for item in checks)
    return {
        "module_id": MODULE_ID,
        "evaluator_version": EVALUATOR_VERSION,
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "passed": passed,
        "checks": checks,
        "check_count": len(checks),
        "generated_at": "2026-01-01T00:00:00Z",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = evaluate()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_request", "evaluate", "main"]
