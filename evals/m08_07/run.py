"""Deterministic evaluator for the M08-07 calibration/selective gates."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m08_07 import (
    M0807_UNCERTAINTY_MEDIA_TYPE,
    CalibrationCandidate,
    CalibrationConfiguration,
    CalibrationMethod,
    CalibrationScope,
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
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_07_calibration_selective_prediction import (
    M0807Plugin,
    M0807Service,
)


def artifact(index: int, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m0807.{index}",
        version="1.0.0",
        digest=f"sha256:{index:064x}",
        media_type=media_type,
    )


def build_request(candidate: CalibrationCandidate | None = None):
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact(11),
    )
    context = ExecutionContext(
        request_id="context.m0807",
        actor_id="actor.evaluator",
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=artifact(12),
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact(13),
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )
    return {
        "request_id": "request.m0807",
        "context": context,
        "uncertainty_result": artifact(20, M0807_UNCERTAINTY_MEDIA_TYPE),
        "configuration": CalibrationConfiguration(
            configuration_id="configuration.m0807",
            version="1.0.0",
            method=CalibrationMethod.CONFORMAL,
            scopes=(
                CalibrationScope(
                    site="site-a",
                    platform="platform-a",
                    disease_class="glioma",
                    subgroup="all",
                ),
            ),
            support_threshold=0.8,
            ood_threshold=0.2,
            calibration_artifact=artifact(30),
            benchmark_artifact=artifact(31),
        ),
        "source_artifacts": (artifact(21),),
        "candidate": candidate,
    }


def candidate(**overrides: object) -> CalibrationCandidate:
    values: dict[str, object] = {
        "site": "site-a",
        "platform": "platform-a",
        "disease_class": "glioma",
        "subgroup": "all",
        "predicted_subtype": "subtype_a",
        "score": 0.8,
        "calibrated_confidence": 0.9,
        "labels": ("subtype_a", "subtype_b"),
        "observed_coverage": 0.9,
        "calibration_error": 0.05,
        "support_score": 0.95,
        "ood_score": 0.05,
        "subgroup_disparity": 0.03,
    }
    values.update(overrides)
    return CalibrationCandidate(**values)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    scenarios: dict[str, bool]
    statuses: dict[str, str]
    passed: bool


def run_evaluation() -> EvaluationReport:
    service = M0807Service()
    scenarios: dict[str, bool] = {}
    statuses: dict[str, str] = {}

    supported = service.execute(build_request(candidate()))
    scenarios["supported_candidate"] = supported.status.value == "calibrated"
    statuses["supported_candidate"] = supported.status.value

    missing = service.execute(build_request())
    scenarios["missing_candidate_abstention"] = (
        missing.status.value == "abstained" and missing.support_decision.status.value == "review_required"
    )
    statuses["missing_candidate_abstention"] = missing.status.value

    unsupported = service.execute(build_request(candidate(support_score=0.1)))
    scenarios["support_threshold_abstention"] = (
        unsupported.status.value == "abstained"
        and unsupported.support_decision.status.value == "unsupported"
    )
    statuses["support_threshold_abstention"] = unsupported.status.value

    ood = service.execute(build_request(candidate(ood_score=0.9)))
    scenarios["ood_abstention"] = ood.findings == ("ood_unsupported",)
    statuses["ood_abstention"] = ood.status.value

    coverage = service.execute(build_request(candidate(observed_coverage=0.5)))
    scenarios["coverage_review"] = coverage.support_decision.status.value == "review_required"
    statuses["coverage_review"] = coverage.status.value

    scenarios["replay"] = service.verify(supported, supported.request)
    tampered = supported.model_dump(mode="json")
    tampered["status"] = "abstained"
    scenarios["tamper_rejected"] = not service.verify(tampered, supported.request)

    plugin = M0807Plugin(service)
    token = plugin.validate(supported.request.model_dump_json())
    plugin_result = plugin.run(token)
    scenarios["plugin_parity"] = plugin_result == supported

    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M08-07",
        contract_version="0.1.0-provisional",
        scenarios=scenarios,
        statuses=statuses,
        passed=all(scenarios.values()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["EvaluationReport", "artifact", "build_request", "candidate", "main", "run_evaluation"]


if __name__ == "__main__":
    raise SystemExit(main())

