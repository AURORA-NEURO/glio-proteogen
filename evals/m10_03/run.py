"""Locked M10-03 evaluator matrix using caller-declared inputs only."""
# ruff: noqa: T201

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m10_03 import (
    M1003_BASELINE_MEDIA_TYPE,
    M1003_CONTRACT_VERSION,
    BaselineConfiguration,
    BaselineEstimatorFamily,
    BaselinePreprocessingStep,
    BaselineTuningSpec,
    EstimateProteinRnaDiscordanceBaselineRequest,
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
from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator import (
    BaselineAuthorizationError,
    estimate_protein_rna_discordance_baseline,
    verify_result_replay,
)

_THREE_TARGETS = 3
_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m10_03" / "scenarios.json"


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=f"sha256:{hashlib.sha256(name.encode()).hexdigest()}",
        media_type=media_type,
    )


def upstream(
    name: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=state,
        policy_version="1.0.0",
        evidence=artifact(f"evidence.{name}"),
    )


def build_scenario_request(
    *,
    state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
    family: BaselineEstimatorFamily = BaselineEstimatorFamily.ROBUST_LINEAR,
) -> EstimateProteinRnaDiscordanceBaselineRequest:
    return EstimateProteinRnaDiscordanceBaselineRequest(
        request_id="request.m1003.eval",
        context=ExecutionContext(
            request_id="request.m1003.eval",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
            references=ContextReferences(
                approved_configuration=upstream("configuration"),
                identity_lineage=IdentityLineageReference(
                    decision_id="decision.identity",
                    state=IdentityLineageState.RESOLVED,
                    policy_version="1.0.0",
                    binding_digest=artifact("identity").digest,
                    evidence=artifact("identity-control"),
                ),
                provenance=upstream("provenance"),
                consent=ConsentReference(
                    decision_id="decision.consent",
                    state=ConsentState.GRANTED,
                    policy_version="1.0.0",
                    evidence=artifact("consent-control"),
                ),
                quality=upstream("quality"),
                support=upstream("support", state),
                intended_use=upstream("intended-use"),
            ),
        ),
        formal_state_result=artifact("formal-state", M1003_BASELINE_MEDIA_TYPE),
        configuration=BaselineConfiguration(
            configuration_id="config.m1003.eval",
            version="1.0.0",
            estimator_family=family,
            target_feature_ids=("target.alpha", "target.beta", "target.gamma"),
            preprocessing=(
                BaselinePreprocessingStep(
                    sequence=1,
                    operation="robust-scale",
                    parameters_digest=artifact("preprocess").digest,
                ),
            ),
            tuning=BaselineTuningSpec(
                tuning_id="tuning.m1003.eval",
                protocol="locked-five-fold",
                objective="mean absolute error",
                folds=5,
                benchmark_artifact=artifact("benchmark"),
            ),
            uncertainty_method="reviewed-bootstrap",
            reference=artifact("baseline-reference"),
        ),
        source_artifacts=(artifact("source"),),
    )


def _fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(_FIXTURE.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, Any]:
    """Run the fixed M10-03 matrix and return fixture-bound evidence."""

    supported = estimate_protein_rna_discordance_baseline(build_scenario_request())
    scalar = estimate_protein_rna_discordance_baseline(
        build_scenario_request(family=BaselineEstimatorFamily.ESTABLISHED_STATISTICAL)
    )
    categorical = estimate_protein_rna_discordance_baseline(
        build_scenario_request(family=BaselineEstimatorFamily.RULE_BASED)
    )
    rejected = False
    try:
        estimate_protein_rna_discordance_baseline(
            build_scenario_request(state=UpstreamDecisionState.REJECTED)
        )
    except BaselineAuthorizationError:
        rejected = True
    tampered = supported.model_copy(update={"result_digest": artifact("tamper").digest})
    cases = {
        "supported_estimated": supported.status.value == "estimated",
        "three_targets": len(supported.estimates) == _THREE_TARGETS,
        "interval_shape": all(item.kind.value == "interval" for item in supported.estimates),
        "scalar_shape": all(item.kind.value == "scalar" for item in scalar.estimates),
        "categorical_shape": all(
            item.kind.value == "categorical" for item in categorical.estimates
        ),
        "replay_verified": verify_result_replay(supported),
        "tamper_rejected": not verify_result_replay(tampered),
        "parent_not_emitted": supported.emits_parent is False,
        "rejected_control": rejected,
        "locked_preprocessing": all(
            item.locked and item.leakage_safe
            for item in supported.request.configuration.preprocessing
        ),
        "locked_tuning": supported.request.configuration.tuning.locked,
    }
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    declared_ids = tuple(item["id"] for item in fixture["cases"])
    executed_ids = tuple(cases)
    return {
        "module": "GLIO-PROTEOGEN-M10-03",
        "contract_version": M1003_CONTRACT_VERSION,
        "fixture_digest": _fixture_digest(),
        "declared_case_ids": declared_ids,
        "executed_case_ids": executed_ids,
        "declared_cases": len(declared_ids),
        "executed_cases": len(executed_ids),
        "passed": all(cases.values()) and declared_ids == executed_ids,
        "cases": cases,
    }


def evaluate() -> dict[str, Any]:
    """Compatibility alias returning the complete evaluator report."""

    return run_evaluator()


def main() -> int:
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(report["cases"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
