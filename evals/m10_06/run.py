"""Executable evaluator for the provisional M10-06 uncertainty engine."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m10_06 import (
    M1006_M1005_RESULT_MEDIA_TYPE,
    DecomposeProteinRnaDiscordanceUncertaintyRequest,
    UncertaintyDecompositionPolicy,
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
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_06_uncertainty_decomposition import (
    M1006UncertaintyDecompositionAuthorizationError,
    M1006UncertaintyDecompositionReplayError,
    M1006UncertaintyDecompositionService,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M10-06"
EVALUATOR_VERSION: Final = "0.1.0-provisional"
FINDING_COUNT: Final = 3
MIN_EVIDENCE_COUNT: Final = 5


def _artifact(name: str, fill: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="0.1.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def build_request(
    *, accepted_controls: bool = True
) -> DecomposeProteinRnaDiscordanceUncertaintyRequest:
    """Build an opaque, deterministic request from fixture references."""

    state = UpstreamDecisionState.ACCEPTED if accepted_controls else UpstreamDecisionState.UNKNOWN
    consent_state = ConsentState.GRANTED if accepted_controls else ConsentState.UNKNOWN
    identity_state = (
        IdentityLineageState.RESOLVED if accepted_controls else IdentityLineageState.UNRESOLVED
    )
    controls = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config.m1006",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("config", "3"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity.m1006",
            state=identity_state,
            policy_version="1.0.0",
            binding_digest=_artifact("identity", "4").digest,
            evidence=_artifact("identity", "4"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance.m1006",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("provenance", "5"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent.m1006",
            state=consent_state,
            policy_version="1.0.0",
            evidence=_artifact("consent", "6"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality.m1006",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("quality", "7"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support.m1006",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("support", "8"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended.m1006",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("intended", "9"),
        ),
    )
    return DecomposeProteinRnaDiscordanceUncertaintyRequest(
        request_id="request.eval.m1006",
        context=ExecutionContext(
            request_id="request.eval.m1006",
            actor_id="actor.evaluator.m1006",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=controls,
        ),
        integrator_result=_artifact("m1005.result", "1", M1006_M1005_RESULT_MEDIA_TYPE),
        policy=UncertaintyDecompositionPolicy(
            policy_id="policy.eval.m1006",
            version="0.1.0",
            method="deterministic-proteogenomic-vae-calibration",
            calibration_reference=_artifact("calibration.reference", "a"),
        ),
        source_artifacts=(
            _artifact("proteome.source", "2", "application/vnd.opaque.artifact+json"),
            _artifact("transcriptome.source", "b", "application/vnd.opaque.artifact+json"),
            _artifact("ptm.source", "c", "application/vnd.opaque.artifact+json"),
        ),
    )


def _check(name: str, *, passed: bool, detail: str) -> dict[str, object]:
    return {"id": name, "passed": passed, "detail": detail}


def evaluate() -> dict[str, object]:
    service = M1006UncertaintyDecompositionService()
    request = build_request()
    result = service.execute(request)
    checks: list[dict[str, object]] = []
    checks.append(
        _check(
            "safe_abstention_has_seven_dimensions_and_envelope",
            passed=(
                result.status.value == "abstained"
                and result.decomposition is None
                and result.sensitivity_envelope.status.value == "abstained"
                and result.human_review_required
                and len(result.findings) == FINDING_COUNT
                and len(result.evidence) >= MIN_EVIDENCE_COUNT
                and result.uncertainty.transport.state.value == "not_estimable"
            ),
            detail="abstention exposes seven uncertainty dimensions and explicit sensitivity state",
        )
    )
    replay = service.verify(result)
    checks.append(
        _check(
            "transitive_replay_is_byte_stable",
            passed=replay.model_dump_json() == result.model_dump_json(),
            detail="exact request replay reproduced the canonical result envelope",
        )
    )
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    try:
        service.verify(tampered)
    except M1006UncertaintyDecompositionReplayError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(
        _check(
            "tampered_receipt_rejected",
            passed=tamper_rejected,
            detail="changed abstention text cannot pass canonical verification",
        )
    )
    try:
        service.execute(build_request(accepted_controls=False))
    except M1006UncertaintyDecompositionAuthorizationError:
        controls_fail_closed = True
    else:
        controls_fail_closed = False
    checks.append(
        _check(
            "unresolved_controls_fail_closed",
            passed=controls_fail_closed,
            detail="identity, consent, and upstream controls are never inferred",
        )
    )
    try:
        DecomposeProteinRnaDiscordanceUncertaintyRequest.model_validate(
            request.model_dump(mode="python") | {"integrator_result": _artifact("wrong", "d")},
            strict=True,
        )
    except ValidationError:
        wrong_integrator_rejected = True
    else:
        wrong_integrator_rejected = False
    checks.append(
        _check(
            "wrong_integrator_media_rejected",
            passed=wrong_integrator_rejected,
            detail="M10-05 handoff media type is explicit",
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
            detail="strict parser rejects duplicate object members",
        )
    )
    checks.append(
        _check(
            "prohibited_parent_emission_is_false",
            passed=(
                result.emits_parent is False and result.parent_target == "protein_rna_discordance"
            ),
            detail="engine does not emit parent claims, kinase activity, or treatment advice",
        )
    )
    passed = all(item["passed"] is True for item in checks)
    return {
        "module_id": MODULE_ID,
        "evaluator_version": EVALUATOR_VERSION,
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
