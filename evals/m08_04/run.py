"""Executable M08-04 evaluator and replay/tamper harness."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m08_04 import (
    M0804_BASELINE_MEDIA_TYPE,
    EstimateTranscriptProteinProbabilisticRequest,
    EstimatorConstraint,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticFeatureObservation,
    ProbabilisticFeatureState,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
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
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_04_probabilistic_estimator as m0804_runtime,
)

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = _ROOT / "tests" / "fixtures" / "m08_04" / "scenarios.json"


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=sha256_digest({"artifact": name}),
        media_type=media_type,
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context(consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0804-eval",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("evidence.identity"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def build_request(
    case: str = "observed",
    family: ProbabilisticEstimatorFamily = ProbabilisticEstimatorFamily.LEARNED,
) -> EstimateTranscriptProteinProbabilisticRequest:
    """Build fixed synthetic requests; no raw spectra or external content is read."""

    config = ProbabilisticEstimatorConfiguration(
        configuration_id="configuration.m0804-eval",
        version="1.0.0",
        estimator_family=family,
        objective="locked.posterior.log-loss",
        priors=(
            ProbabilisticPrior(
                prior_id="prior.discordance",
                version="1.0.0",
                kind=ProbabilisticPriorKind.NORMAL,
                parameters=(0.25, 0.1),
            ),
        ),
        constraints=(
            EstimatorConstraint(
                constraint_id="constraint.isoform",
                expression="isoform_mass >= 0",
                hard=True,
            ),
        ),
        optimizer="deterministic.coordinate-descent",
        seed=17,
        max_iterations=100,
        reference=_artifact("reference.posterior"),
    )
    features: tuple[ProbabilisticFeatureObservation, ...] = (
        ProbabilisticFeatureObservation(
            feature_id="discordance.log-ratio",
            state=(
                ProbabilisticFeatureState.MISSING
                if case == "missing"
                else ProbabilisticFeatureState.OBSERVED
            ),
            unit="ratio",
            value=None if case == "missing" else 0.8,
            isoform_id="isoform.a",
            weight=1.0,
        ),
        ProbabilisticFeatureObservation(
            feature_id="discordance.ptm-shift",
            state=ProbabilisticFeatureState.OBSERVED,
            unit="ratio",
            value=-0.2,
            isoform_id="isoform.b",
            weight=2.0,
        ),
    )
    source = "source.ood-domain" if case == "ood" else "source.proteome"
    consent = ConsentState.WITHHELD if case == "withheld" else ConsentState.GRANTED
    return EstimateTranscriptProteinProbabilisticRequest(
        request_id="request.m0804-eval",
        context=_context(consent),
        baseline_result=_artifact("baseline.m0803", M0804_BASELINE_MEDIA_TYPE),
        configuration=config,
        feature_observations=features,
        source_artifacts=(_artifact(source), _artifact("source.transcriptome")),
    )


def _scenario(name: str, request: EstimateTranscriptProteinProbabilisticRequest) -> dict[str, Any]:
    service = m0804_runtime.M0804Service()
    if name == "withheld-consent":
        try:
            service.execute(request)
        except m0804_runtime.M0804AuthorizationError:
            return {"name": name, "observed": "authorization_error", "passed": True}
        return {"name": name, "observed": "unexpected_execution", "passed": False}
    result = service.execute(request)
    expected = (
        "estimated"
        if name.startswith("observed") or name.endswith("architecture")
        else "abstained"
    )
    return {
        "name": name,
        "observed": result.status.value,
        "support": result.support_decision.status.value,
        "expected": expected,
        "passed": result.status.value == expected,
    }


def evaluate_replay_and_tamper() -> dict[str, bool]:
    service = m0804_runtime.M0804Service()
    request = build_request()
    result = service.execute(request)
    replay = service.replay(request, result) == result
    tamper = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.verify(tamper)
    except ValueError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    return {"replay": replay, "tamper_rejected": tamper_rejected}


def evaluate() -> dict[str, Any]:
    scenarios = (
        _scenario("observed-learned", build_request()),
        _scenario(
            "mechanism-guided-architecture",
            build_request(family=ProbabilisticEstimatorFamily.MECHANISM_GUIDED),
        ),
        _scenario(
            "proteoform-architecture",
            build_request(family=ProbabilisticEstimatorFamily.PROTEOFORM_PROBABILISTIC),
        ),
        _scenario("missing-feature-abstain", build_request("missing")),
        _scenario("out-of-domain-abstain", build_request("ood")),
        _scenario("withheld-consent", build_request("withheld")),
    )
    replay = evaluate_replay_and_tamper()
    return {
        "module": "GLIO-PROTEOGEN-M08-04",
        "contract_version": "0.1.0-provisional",
        "authority": {
            "sha256": "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181",
            "lines": "2688-2731",
        },
        "scenarios": scenarios,
        "replay_and_tamper": replay,
        "passed": all(item["passed"] for item in scenarios) and all(replay.values()),
    }


def main() -> None:
    print(json.dumps(evaluate(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
