"""M12-02 context and subtype stratifier scenarios and evaluator."""

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

from glio_proteogen.contracts.m12_02 import (
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    ContextStratifierConfiguration,
    ContextStratifierPolicy,
    StratifyBiomarkerPanelContextRequest,
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
from glio_proteogen.modules.c12_driver_to_protein_consequence import (
    m12_02_context_subtype_stratifier as m1202_runtime,
)

_ROOT: Final = Path(__file__).parents[2]
_FIXTURE: Final = _ROOT / "tests" / "fixtures" / "m12_02" / "scenarios.json"
_INVALID_FIXTURE: Final = "M12-02 fixture scenarios must be a list"
_DIMENSION_VALUES: Final = {
    ContextDimension.DISEASE_CLASS: "glioma",
    ContextDimension.SUBTYPE: "mesenchymal",
    ContextDimension.AGE: "adult",
    ContextDimension.TERRITORY: "brain",
    ContextDimension.TREATMENT_ERA: "modern",
    ContextDimension.SPECIMEN: "tumor",
    ContextDimension.PLATFORM: "mass-spectrometry",
    ContextDimension.BIOLOGICAL_CONTEXT: "immune",
}


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m1202.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1202": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M12-02 context evidence.",
    )


def _context(case_id: str) -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m1202.{case_id}.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{case_id}-{role}"),
        )

    return ExecutionContext(
        request_id=f"request.synthetic.m1202.{case_id}",
        actor_id="actor.synthetic.m1202",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id=f"decision.synthetic.m1202.{case_id}.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"identity": case_id}),
                evidence=_artifact(f"control-{case_id}-identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id=f"decision.synthetic.m1202.{case_id}.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact(f"control-{case_id}-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _observation(
    case_id: str,
    dimension: ContextDimension,
    index: int,
    *,
    status: ContextObservationStatus = ContextObservationStatus.SUPPORTED,
    value: str | None = None,
) -> ContextObservation:
    return ContextObservation(
        observation_id=f"observation.synthetic.m1202.{case_id}.{index}",
        dimension=dimension,
        value=value or _DIMENSION_VALUES[dimension],
        normalized_value=(value or _DIMENSION_VALUES[dimension]).lower(),
        status=status,
        source_artifact=_artifact(f"observation-source-{case_id}-{index}"),
        evidence=(_evidence(f"observation-{case_id}-{index}"),),
    )


def build_scenario_request(
    case_id: str = "supported_full",
) -> StratifyBiomarkerPanelContextRequest:
    observations = tuple(
        _observation(case_id, dimension, index)
        for index, dimension in enumerate(ContextDimension, start=1)
    )
    if case_id == "missing_platform":
        observations = tuple(
            observation
            for observation in observations
            if observation.dimension is not ContextDimension.PLATFORM
        )
    elif case_id == "conflicted_subtype":
        observations = (
            *observations,
            _observation(case_id, ContextDimension.SUBTYPE, 99, value="proneural"),
        )
    elif case_id == "limited_territory":
        observations = tuple(
            observation.model_copy(update={"status": ContextObservationStatus.LIMITED})
            if observation.dimension is ContextDimension.TERRITORY
            else observation
            for observation in observations
        )
    configuration = ContextStratifierConfiguration(
        configuration_id=f"configuration.synthetic.m1202.{case_id}",
        version="1.0.0",
        method="curated_context_rules",
        model_reference=_artifact(f"model-{case_id}"),
        evidence=(_evidence(f"configuration-{case_id}"),),
    )
    required_dimensions = tuple(ContextDimension)
    if case_id == "incomplete_policy":
        required_dimensions = tuple(
            dimension
            for dimension in ContextDimension
            if dimension is not ContextDimension.TREATMENT_ERA
        )
    return StratifyBiomarkerPanelContextRequest(
        request_id=f"request.synthetic.m1202.{case_id}",
        context=_context(case_id),
        driver_consequence_result=_artifact(f"upstream-{case_id}"),
        policy=ContextStratifierPolicy(
            required_dimensions=required_dimensions,
            configuration=configuration,
        ),
        observations=observations,
        source_artifacts=(_artifact(f"source-{case_id}"),),
    )


def fixture_cases() -> tuple[dict[str, object], ...]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    if not isinstance(scenarios, list):
        raise TypeError(_INVALID_FIXTURE)
    return tuple(item for item in scenarios if isinstance(item, dict))


def run_evaluator() -> dict[str, object]:
    engine = m1202_runtime.M1202ContextEngine()
    outcomes: list[dict[str, object]] = []
    for scenario in fixture_cases():
        case_id = str(scenario["case_id"])
        expected = str(scenario["expected"])
        if case_id == "denied_control":
            base = build_scenario_request()
            denied_support = base.context.references.support.model_copy(
                update={"state": UpstreamDecisionState.REJECTED}
            )
            denied_refs = base.context.references.model_copy(update={"support": denied_support})
            denied = base.model_copy(
                update={"context": base.context.model_copy(update={"references": denied_refs})}
            )
            try:
                engine.stratify(denied)
            except m1202_runtime.M1202ContextAuthorizationError:
                actual = "authorization_rejected"
            else:
                actual = "unexpected_success"
        else:
            result = engine.stratify(build_scenario_request(case_id))
            actual = result.status.value
            if case_id == "supported_full":
                engine.verify(result)
        outcomes.append({"case_id": case_id, "expected": expected, "actual": actual})
    if any(item["expected"] != item["actual"] for item in outcomes):
        raise AssertionError(outcomes)
    return {
        "module_id": "GLIO-PROTEOGEN-M12-02",
        "passed": True,
        "declared": len(outcomes),
        "executed": len(outcomes),
        "failed": [],
        "outcomes": outcomes,
        "fixture_digest": sha256_digest({"scenarios": fixture_cases()}),
    }


__all__ = ["build_scenario_request", "fixture_cases", "run_evaluator"]
