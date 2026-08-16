"""Deterministic M16-01 evaluator over frozen upstream compatibility scenarios."""

# ruff: noqa: TRY003, T201

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m16_01 import (
    CompatibilityStatus,
    ResolveProteinRnaDiscordanceUpstreamRequest,
    ResolverConfiguration,
    ResolverPolicy,
    ResolverStatus,
    UpstreamCandidate,
    UpstreamObjectKind,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c16_protein_rna_discordance.m16_01_upstream_contract_resolver import (
    M1601AuthorizationError,
    M1601UpstreamContractResolverEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M16-01"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m16_01" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "resolved_supported",
    "version_mismatch_abstention",
    "media_mismatch_abstention",
    "missing_required_kind_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _digest(label: str) -> str:
    return sha256_digest({"m1601_fixture": label})


def _artifact(
    label: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=_digest(label),
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
            binding_digest=_digest("identity.binding"),
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
            decision_id="decision.intended-use",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended-use"),
        ),
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Frozen caller-declared M16-01 resolver evidence.",
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.9,
        rationale="Typed compatibility evidence is explicit.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Version and media types remain caller-declared.",),
    )


def _candidate(
    kind: UpstreamObjectKind,
    *,
    label: str,
    version: str = "1.0.0",
    media_type: str | None = None,
    required_media_type: str | None = None,
) -> UpstreamCandidate:
    media = media_type or f"application/vnd.glio-proteogen.{label}+json"
    return UpstreamCandidate(
        candidate_id=f"candidate.{label}",
        kind=kind,
        artifact=_artifact(label, media),
        contract_version=version,
        required_media_type=required_media_type or media,
        declared_consent=True,
        declared_support=True,
        declared_provenance=True,
        evidence=_evidence(f"evidence.{label}"),
    )


def build_scenario_request(
    *,
    accepted: bool = True,
    candidates: tuple[UpstreamCandidate, ...] | None = None,
    required_kinds: tuple[UpstreamObjectKind, ...] | None = None,
) -> ResolveProteinRnaDiscordanceUpstreamRequest:
    if candidates is None:
        candidates = (
            _candidate(
                UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME, label="mass-spectrometry-proteome"
            ),
            _candidate(UpstreamObjectKind.GENOME_TRANSCRIPTOME, label="genome-transcriptome"),
            _candidate(UpstreamObjectKind.PTM_ANNOTATION, label="ptm-annotation"),
        )
    configuration = ResolverConfiguration(
        configuration_id="configuration.m1601",
        version="1.0.0",
        method="typed_service_oriented_integration",
        policy_reference=_artifact("policy", "application/vnd.glio-proteogen.policy+json"),
        evidence=_evidence("configuration"),
    )
    policy = ResolverPolicy(
        required_kinds=required_kinds
        or (
            UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
            UpstreamObjectKind.GENOME_TRANSCRIPTOME,
            UpstreamObjectKind.PTM_ANNOTATION,
        ),
        configuration=configuration,
    )
    return ResolveProteinRnaDiscordanceUpstreamRequest(
        request_id="request.m1601",
        context=ExecutionContext(
            request_id="request.m1601",
            actor_id="actor.evaluator",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        candidates=candidates,
        policy=policy,
        source_artifacts=(_artifact("source-proteome"), _artifact("source-transcriptome")),
    )


def fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, object]:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M16-01 fixture case IDs are not locked")
    engine = M1601UpstreamContractResolverEngine()
    checks: list[EvalCheck] = []
    resolved = engine.infer(build_scenario_request())
    checks.append(
        EvalCheck(
            "resolved_supported",
            resolved.status is ResolverStatus.RESOLVED
            and resolved.bundle is not None
            and resolved.compatibility_report.status is CompatibilityStatus.ACCEPTED,
            resolved.status.value,
        )
    )
    mismatch = _candidate(
        UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
        label="mass-spectrometry-proteome",
        version="2.0.0",
    )
    version_result = engine.infer(build_scenario_request(candidates=(mismatch,)))
    checks.append(
        EvalCheck(
            "version_mismatch_abstention",
            version_result.status is ResolverStatus.ABSTAINED,
            version_result.abstention_reason or "",
        )
    )
    media = _candidate(
        UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
        label="mass-spectrometry-proteome",
        media_type="application/octet-stream",
        required_media_type="application/vnd.glio-proteogen.mass+json",
    )
    media_result = engine.infer(build_scenario_request(candidates=(media,)))
    checks.append(
        EvalCheck(
            "media_mismatch_abstention",
            media_result.status is ResolverStatus.ABSTAINED,
            media_result.abstention_reason or "",
        )
    )
    missing = build_scenario_request(
        candidates=(
            _candidate(
                UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME, label="mass-spectrometry-proteome"
            ),
        )
    )
    missing_result = engine.infer(missing)
    checks.append(
        EvalCheck(
            "missing_required_kind_abstention",
            missing_result.status is ResolverStatus.ABSTAINED,
            missing_result.abstention_reason or "",
        )
    )
    replay = engine.infer(build_scenario_request())
    replay_ok = engine.verify(replay) == replay
    tampered = replay.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        engine.verify(tampered)
    except Exception:  # noqa: BLE001
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append(
        EvalCheck("replay_and_tamper", replay_ok and tamper_rejected, "replay and tamper")
    )
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1601AuthorizationError:
        authorization_ok = True
    else:
        authorization_ok = False
    checks.append(EvalCheck("authorization_gate", authorization_ok, "denied controls rejected"))
    return {
        "module_id": MODULE_ID,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": fixture_digest(),
        "case_ids": list(case_ids),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": sum(item.passed for item in checks),
        "total_cases": len(checks),
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail} for item in checks
        ],
        "passed": len(checks) == len(case_ids) and all(item.passed for item in checks),
        "schema_count": len(contract_json_schemas()),
        "request_digest": canonical_request_digest(build_scenario_request()),
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))
