"""Fixture-bound evaluator for M13-02 context stratification."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from glio_proteogen.contracts.m13_02 import (
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    MechanismCandidate,
    StratifierConfiguration,
    StratifierPolicy,
    StratifyProteotypeContextRequest,
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
from glio_proteogen.modules.c11_protein_native_subtype.m13_02_context_subtype_stratifier import (
    M1302AuthorizationError,
    compute_proteotype_context,
    verify_context_result,
)

MODULE_ID = "GLIO-PROTEOGEN-M13-02"
FIXTURE_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m13_02" / "scenarios.json"


def _artifact(name: str, letter: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + letter * 64,
        media_type="application/json",
    )


def _request(case_id: str) -> StratifyProteotypeContextRequest:
    evidence_artifact = _artifact("context-observations", "d")
    evidence = EvidenceReference(
        reference=evidence_artifact,
        role="evidence",
        claim="Caller-declared context observation",
    )
    statuses = (
        {
            "supported_context": (ContextObservationStatus.SUPPORTED,) * 2,
            "limited_context": (
                ContextObservationStatus.LIMITED,
                ContextObservationStatus.SUPPORTED,
            ),
            "unresolved_context": (
                ContextObservationStatus.UNRESOLVED,
                ContextObservationStatus.SUPPORTED,
            ),
            "conflicted_context": (
                ContextObservationStatus.CONFLICTED,
                ContextObservationStatus.SUPPORTED,
            ),
            "missing_required_dimension": (ContextObservationStatus.SUPPORTED,),
        }[case_id]
        if case_id not in {"denied_control", "tampered_result"}
        else (
            ContextObservationStatus.SUPPORTED,
            ContextObservationStatus.SUPPORTED,
        )
    )
    values: tuple[tuple[ContextDimension, str], ...] = (
        (ContextDimension.SUBTYPE, "IDH-mutant astrocytoma"),
        (ContextDimension.PLATFORM, "LC-MS"),
    )
    if case_id == "missing_required_dimension":
        values = values[:1]
    observations = tuple(
        ContextObservation(
            observation_id=f"observation-{index}",
            dimension=dimension,
            value=value,
            normalized_value=(
                value.lower() if status is not ContextObservationStatus.UNRESOLVED else None
            ),
            status=status,
            source_artifact=evidence_artifact,
            evidence=(evidence,),
        )
        for index, ((dimension, value), status) in enumerate(zip(values, statuses, strict=True), 1)
    )
    configuration = StratifierConfiguration(
        configuration_id="config-m1302",
        version="1.0.0",
        method="caller-declared-context-rule",
        model_reference=_artifact("m1302-config", "e"),
        evidence=(evidence,),
    )
    candidate = MechanismCandidate(
        mechanism_id="mechanism.context.subtype",
        label="Subtype-context mechanism route",
        required_dimensions=(ContextDimension.SUBTYPE,),
        rationale="Requires supported subtype context only; no kinase state is inferred.",
        evidence=(evidence,),
    )
    context = _context(denied=case_id == "denied_control")
    if case_id == "missing_required_dimension":
        observations = observations[:1]
    return StratifyProteotypeContextRequest(
        request_id="request-m1302",
        context=context,
        variant_peptide_result=_artifact("variant-peptide-result", "f"),
        policy=StratifierPolicy(
            required_dimensions=(ContextDimension.SUBTYPE, ContextDimension.PLATFORM),
            configuration=configuration,
        ),
        observations=observations,
        mechanism_candidates=(candidate,),
        source_artifacts=(evidence_artifact,),
    )


def _context(*, denied: bool) -> ExecutionContext:
    evidence = _artifact("control-evidence", "b")
    accepted = UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED

    def upstream(name: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=name,
            state=accepted,
            policy_version="1.0.0",
            evidence=evidence,
        )

    return ExecutionContext(
        request_id="request-m1302",
        actor_id="actor-m1302",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=upstream("configuration-decision"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=IdentityLineageState.UNRESOLVED if denied else IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "c" * 64,
                evidence=evidence,
            ),
            provenance=upstream("provenance-decision"),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.WITHHELD if denied else ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=upstream("quality-decision"),
            support=upstream("support-decision"),
            intended_use=upstream("intended-use-decision"),
        ),
    )


def _load_fixture() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def run_evaluator() -> dict[str, object]:
    """Run every declared fixture scenario and return deterministic evidence."""

    fixture = _load_fixture()
    fixture_digest = sha256_digest(fixture)
    cases: list[dict[str, object]] = []
    for declaration in fixture["cases"]:
        case_id = str(declaration["case_id"])
        expected = str(declaration["expected"])
        if case_id == "tampered_result":
            result = compute_proteotype_context(_request("supported_context"))
            tampered = result.model_copy(update={"findings": ()})
            actual = "replay_rejected" if not verify_context_result(tampered) else "replay_accepted"
        else:
            try:
                result = compute_proteotype_context(_request(case_id))
            except M1302AuthorizationError:
                actual = "authorization_error"
            else:
                actual = result.status.value
        cases.append(
            {
                "case_id": case_id,
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
            }
        )
    passed = sum(bool(item["passed"]) for item in cases)
    return {
        "module_id": MODULE_ID,
        "fixture_id": fixture["fixture_id"],
        "fixture_digest": fixture_digest,
        "declared_cases": len(cases),
        "executed_cases": len(cases),
        "passed_cases": passed,
        "all_passed": passed == len(cases),
        "cases": cases,
    }


if __name__ == "__main__":
    import sys

    sys.stdout.write(json.dumps(run_evaluator(), indent=2, sort_keys=True) + "\n")
