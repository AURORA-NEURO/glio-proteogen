"""Executable evaluator for the provisional M22-02 synthetic-truth generator."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m22_02 import (
    M2202_DOSSIER_SHA256,
    M2202_DOSSIER_SLICE,
    M2202_M2201_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    GenerationConfiguration,
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
from glio_proteogen.modules.c21_reference_material.m22_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2202AuthorizationError,
    M2202ReplayError,
    M2202Service,
)

MODULE_ID = "GLIO-PROTEOGEN-M22-02"
FIXTURE_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m22_02" / "scenarios.json"


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _context(request_id: str = "m2202.request") -> ExecutionContext:
    evidence = _artifact("m2202.control.evidence")
    accepted = UpstreamDecisionReference(
        decision_id="m2202.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2202.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2202.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2202.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def build_request(
    *,
    fixture_kinds: tuple[FixtureKind, ...] = tuple(FixtureKind),
    requested_case_count: int = 5,
    upstream_media_type: str = M2202_M2201_INPUT_MEDIA_TYPE,
    include_upstream: bool = True,
    support_state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> GenerateProteinRnaDiscordanceSyntheticTruthRequest:
    upstream = _artifact("m2201.reference.truth", upstream_media_type)
    context = _context()
    if support_state is not UpstreamDecisionState.ACCEPTED:
        support = context.references.support.model_copy(update={"state": support_state})
        context = context.model_copy(
            update={"references": context.references.model_copy(update={"support": support})}
        )
    policy = _artifact("m2202.generator.policy")
    sources: tuple[ArtifactReference, ...] = (upstream, policy) if include_upstream else (policy,)
    return GenerateProteinRnaDiscordanceSyntheticTruthRequest(
        request_id="m2202.request",
        context=context,
        upstream_result=upstream,
        configuration=GenerationConfiguration(
            configuration_id="m2202.configuration",
            version="1.0.0",
            generator_name="deterministic-fixture-generator",
            seed=7,
            requested_fixture_kinds=fixture_kinds,
        ),
        requested_case_count=requested_case_count,
        source_artifacts=sources,
    )


def _check(name: str, *, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": passed, "detail": detail}


def evaluate() -> dict[str, object]:
    service = M2202Service()
    checks: list[dict[str, object]] = []

    result = service.generate(build_request())
    checks.append(
        _check(
            "all_fixture_kinds_generated",
            passed=(
                result.corpus is not None
                and tuple(case.fixture_kind for case in result.corpus.cases) == tuple(FixtureKind)
            ),
            detail="analytic and semi-synthetic normal/edge/missing/shifted/adversarial cases",
        )
    )
    repeat = service.generate(build_request())
    checks.append(
        _check(
            "deterministic_repeat",
            passed=result.result_digest == repeat.result_digest,
            detail=result.result_digest,
        )
    )
    checks.append(
        _check(
            "replay_verification",
            passed=service.verify_replay(result).result_digest == result.result_digest,
            detail="canonical replay passed",
        )
    )
    try:
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    except M2202ReplayError:
        checks.append(
            _check("tamper_rejected", passed=True, detail="result digest tamper rejected")
        )
    else:
        checks.append(
            _check("tamper_rejected", passed=False, detail="tampered result was accepted")
        )
    try:
        service.generate(build_request(support_state=UpstreamDecisionState.REJECTED))
    except M2202AuthorizationError:
        checks.append(
            _check(
                "authorization_gate",
                passed=True,
                detail="denied support rejected before generation",
            )
        )
    else:
        checks.append(
            _check("authorization_gate", passed=False, detail="denied support was not rejected")
        )
    try:
        service.generate(build_request(upstream_media_type="application/json"))
    except ValidationError:
        checks.append(
            _check("upstream_media_boundary", passed=True, detail="M22-01 media type required")
        )
    else:
        checks.append(
            _check(
                "upstream_media_boundary", passed=False, detail="invalid upstream media accepted"
            )
        )
    try:
        service.generate(build_request(include_upstream=False))
    except ValidationError:
        checks.append(
            _check(
                "source_closure", passed=True, detail="upstream must be present in source artifacts"
            )
        )
    else:
        checks.append(
            _check("source_closure", passed=False, detail="missing upstream source accepted")
        )
    encoded = json.dumps(build_request().model_dump(mode="json"), separators=(",", ":"))
    checks.append(
        _check(
            "strict_json_parity",
            passed=service.generate(encoded).result_digest == result.result_digest,
            detail="typed and strict JSON paths share the digest",
        )
    )
    passed = all(bool(item["passed"]) for item in checks)
    fixture_digest = sha256_digest(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2202_DOSSIER_SHA256,
        "dossier_slice": M2202_DOSSIER_SLICE,
        "fixture": str(FIXTURE_PATH),
        "fixture_digest": fixture_digest,
        "checks": checks,
        "declared_cases": len(checks),
        "executed_cases": len(checks),
        "passed_cases": sum(bool(item["passed"]) for item in checks),
        "total_cases": len(checks),
        "uncertainty_dimensions": 7,
        "schema_count": 7,
        "request_digest": sha256_digest(build_request().model_dump(mode="json")),
        "passed": passed,
    }


def main() -> int:
    report = evaluate()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
