"""Run the locked deterministic M12-08 mechanism dossier evaluation matrix."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m12_08 import (
    M1208_M1207_INPUT_MEDIA_TYPE,
    AssembleBiomarkerPanelMechanismDossierRequest,
    MechanismDossierConfiguration,
    MechanismDossierStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_08_mechanism_evidence_dossier import (  # noqa: E501
    M1208AuthorizationError,
    M1208MechanismEvidenceEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-08"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m12_08" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "bayesian_graph_dossier",
    "network_factor_dossier",
    "curated_rule_dossier",
    "orthogonal_consensus_dossier",
    "unsupported_architecture_abstention",
    "unsafe_upstream_abstention",
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
        digest=sha256_digest({"m1208-eval": label}),
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
    model_family: str = "bayesian_graph_baseline_stack",
    *,
    accepted: bool = True,
    upstream_label: str = "m1207-result",
) -> AssembleBiomarkerPanelMechanismDossierRequest:
    configuration = MechanismDossierConfiguration(
        configuration_id="configuration.m1208-eval",
        version="1.0.0",
        model_family=model_family,
        source_manifest=(_artifact("configuration-manifest"),),
    )
    return AssembleBiomarkerPanelMechanismDossierRequest(
        request_id="request.m1208-eval",
        context=ExecutionContext(
            request_id="request.m1208-eval",
            actor_id="actor.evaluator",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        upstream_result=_artifact(upstream_label, M1208_M1207_INPUT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(_artifact("source.proteome"), _artifact("source.genome")),
    )


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M12-08 fixture case IDs are not locked")
    engine = M1208MechanismEvidenceEngine()
    checks: list[EvalCheck] = []
    families = (
        ("bayesian_graph_dossier", "bayesian_graph_baseline_stack"),
        ("network_factor_dossier", "network_factor_hybrid"),
        ("curated_rule_dossier", "curated_rule_enrichment"),
        ("orthogonal_consensus_dossier", "orthogonal_consensus_baseline_stack"),
    )
    for name, family in families:
        result = engine.infer(build_scenario_request(family))
        checks.append(
            EvalCheck(
                name,
                result.status is MechanismDossierStatus.READY and result.dossier is not None,
                result.status.value,
            )
        )
    unsupported = engine.infer(build_scenario_request("foundation_assisted"))
    checks.append(
        EvalCheck(
            "unsupported_architecture_abstention",
            unsupported.status is MechanismDossierStatus.ABSTAINED
            and unsupported.dossier is None
            and unsupported.human_review_required,
            unsupported.status.value,
        )
    )
    unsafe = engine.infer(build_scenario_request(upstream_label="m1207-ood"))
    checks.append(
        EvalCheck(
            "unsafe_upstream_abstention",
            unsafe.status is MechanismDossierStatus.ABSTAINED and unsafe.dossier is None,
            unsafe.status.value,
        )
    )
    replay = engine.verify(engine.infer(build_scenario_request("network_factor_hybrid")))
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck(
            "replay_and_tamper",
            replay.status is MechanismDossierStatus.READY and tamper_rejected,
            "replay and tamper",
        )
    )
    denied = False
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1208AuthorizationError:
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    report = run_evaluator()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
