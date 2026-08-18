"""Replay the locked M02-02 synthetic identity-binding corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict, cast

from pydantic import TypeAdapter

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m01_02 import EntityKind, IdentityLineageResolution
from glio_proteogen.contracts.m02_02 import (
    BindingDisposition,
    BindingState,
    IdentificationArtifactBinding,
    IdentityBindingEvaluation,
    IdentityBindingPolicy,
    ScopedBindingToken,
    ValidateIdentityBindingsRequest,
    configuration_digest,
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
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    IdentityBindingAuthorizationError,
    evaluate_identity_bindings,
    preflight_identity_binding_authorization,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-02"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_02" / "scenarios.json"
UPSTREAM_RESOLVED_PATH: Final = (
    ROOT / "tests" / "fixtures" / "m02_02" / "upstream_resolved.json"
)
UPSTREAM_UNRESOLVED_PATH: Final = (
    ROOT / "tests" / "fixtures" / "m02_02" / "upstream_unresolved.json"
)
EXPECTED_SCENARIO_COUNT: Final = 8
_RESOLUTION_ADAPTER: Final = TypeAdapter(IdentityLineageResolution)


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "paired_result_and_authorization"]
    expected_disposition: str
    expected_finding_codes: list[str]
    must_not_emit_finding_codes: NotRequired[list[str]]
    different_scope_control_must_not_find: NotRequired[str]
    consent_denied_before_binding_traversal: NotRequired[bool]
    expected_authorization_reason: NotRequired[str]


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
    policy_id: str
    policy_version: str
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0202": label}),
        media_type="application/json",
    )


def _resolution(*, unresolved: bool = False) -> IdentityLineageResolution:
    path = UPSTREAM_UNRESOLVED_PATH if unresolved else UPSTREAM_RESOLVED_PATH
    return _RESOLUTION_ADAPTER.validate_json(path.read_bytes(), strict=True)


def _policy() -> IdentityBindingPolicy:
    return IdentityBindingPolicy(
        policy_id="policy.synthetic.peptide-identification-bindings",
        version="1.0.0",
        max_bindings=64,
        allowed_entity_kinds=(EntityKind.RUN, EntityKind.DERIVED_OBJECT),
        allowed_token_scope_ids=("scope.synthetic.primary", "scope.synthetic.secondary"),
        evidence=_artifact("binding.policy"),
    )


def _context(
    resolution: IdentityLineageResolution,
    policy: IdentityBindingPolicy,
) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{role}", digest),
        )

    identity_state = (
        IdentityLineageState.RESOLVED
        if resolution.decision.value == "resolved"
        else IdentityLineageState.UNRESOLVED
    )
    return ExecutionContext(
        request_id="request.synthetic.m0202",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted(
                "configuration",
                configuration_digest(policy),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity-lineage",
                state=identity_state,
                policy_version="1.0.0",
                binding_digest=resolution.resolution_digest,
                evidence=_artifact("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _binding(  # noqa: PLR0913 - compact fixture builder with explicit dimensions.
    resolution: IdentityLineageResolution,
    label: str,
    entity_id: str,
    *,
    state: BindingState = BindingState.BOUND,
    observed_subjects: tuple[str, ...] | None = None,
    scope_id: str = "scope.synthetic.primary",
    token_digest: str | None = None,
    content_digest: str | None = None,
    claimed_component_id: str | None = None,
) -> IdentificationArtifactBinding:
    node = next(item for item in resolution.graph.nodes if item.entity_id == entity_id)
    if state is BindingState.BOUND:
        return IdentificationArtifactBinding(
            binding_id=f"binding.synthetic.{label}",
            artifact=_artifact(
                f"binding.{label}",
                content_digest or sha256_digest({"content": label}),
            ),
            state=state,
            entity_id=node.entity_id,
            entity_kind=node.kind,
            component_id=claimed_component_id or node.component_id,
            observed_subject_component_ids=(
                observed_subjects
                if observed_subjects is not None
                else node.subject_component_ids
            ),
            scoped_token=ScopedBindingToken(
                scope_id=scope_id,
                token_digest=token_digest or sha256_digest({"token": label}),
            ),
            evidence=(_artifact(f"binding.{label}.evidence"),),
        )
    return IdentificationArtifactBinding(
        binding_id=f"binding.synthetic.{label}",
        artifact=_artifact(f"binding.{label}"),
        state=state,
        entity_id=node.entity_id,
        entity_kind=node.kind,
        component_id=claimed_component_id or node.component_id,
        evidence=(_artifact(f"binding.{label}.evidence"),),
    )


def _request(
    resolution: IdentityLineageResolution,
    bindings: tuple[IdentificationArtifactBinding, ...],
) -> ValidateIdentityBindingsRequest:
    policy = _policy()
    return ValidateIdentityBindingsRequest(
        context=_context(resolution, policy),
        identity_resolution=resolution,
        policy=policy,
        bindings=bindings,
    )


def build_scenario_request(request_case: str) -> ValidateIdentityBindingsRequest:
    """Build one deterministic strict request for eval and benchmark reuse."""

    resolution = _resolution(unresolved=request_case == "upstream_unresolved")
    run_a = "entity.synthetic.run.a"
    run_b = "entity.synthetic.run.b"
    derived_a = "entity.synthetic.derived.a"
    bindings: tuple[IdentificationArtifactBinding, ...]
    if request_case in {"canonical", "upstream_unresolved"}:
        bindings = (
            _binding(resolution, "run-a", run_a),
            _binding(resolution, "derived-a", derived_a),
        )
    elif request_case == "swap":
        run_b_component = next(
            item.component_id
            for item in resolution.graph.nodes
            if item.entity_id == run_b
        )
        bindings = (
            _binding(
                resolution,
                "run-a",
                run_a,
                claimed_component_id=run_b_component,
            ),
        )
    elif request_case == "token_collision":
        shared = sha256_digest({"token": "same-scope-collision"})
        bindings = (
            _binding(resolution, "run-a", run_a, token_digest=shared),
            _binding(resolution, "run-b", run_b, token_digest=shared),
        )
    elif request_case == "duplicate_content":
        shared = sha256_digest({"content": "duplicate-assignment"})
        bindings = (
            _binding(resolution, "run-a", run_a, content_digest=shared),
            _binding(resolution, "derived-a", derived_a, content_digest=shared),
        )
    elif request_case == "cross_patient":
        patient_ids = tuple(
            sorted(
                item.component_id
                for item in resolution.graph.nodes
                if item.kind is EntityKind.PATIENT
            )
        )
        bindings = (
            _binding(resolution, "run-a", run_a, observed_subjects=patient_ids),
        )
    elif request_case in {"unresolved", "unsupported"}:
        state = BindingState(request_case)
        bindings = (_binding(resolution, "run-a", run_a, state=state),)
    else:
        raise ValueError(request_case)
    return _request(resolution, bindings)


def different_scope_control_request() -> ValidateIdentityBindingsRequest:
    """Build the negative control for a same-digest, different-scope token pair."""

    resolution = _resolution()
    shared = sha256_digest({"token": "scope-isolated-control"})
    return _request(
        resolution,
        (
            _binding(
                resolution,
                "run-a",
                "entity.synthetic.run.a",
                token_digest=shared,
            ),
            _binding(
                resolution,
                "run-b",
                "entity.synthetic.run.b",
                scope_id="scope.synthetic.secondary",
                token_digest=shared,
            ),
        ),
    )


def _finding_codes(result: IdentityBindingEvaluation) -> set[str]:
    return {item.code.value for item in result.findings}


def _result_check(scenario: Scenario) -> tuple[EvalCheck, IdentityBindingEvaluation]:
    result = evaluate_identity_bindings(build_scenario_request(scenario["request_case"]))
    findings = _finding_codes(result)
    expected = set(scenario["expected_finding_codes"])
    forbidden = set(scenario.get("must_not_emit_finding_codes", []))
    passed = (
        result.disposition.value == scenario["expected_disposition"]
        and expected <= findings
        and not forbidden & findings
    )
    if "different_scope_control_must_not_find" in scenario:
        control = evaluate_identity_bindings(different_scope_control_request())
        passed = (
            passed
            and control.disposition is BindingDisposition.CONFORMANT
            and scenario["different_scope_control_must_not_find"]
            not in _finding_codes(control)
        )
    return (
        EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=passed,
            detail=(
                f"disposition={result.disposition.value};"
                f"findings={','.join(sorted(findings)) or 'none'}"
            ),
        ),
        result,
    )


def _authorization_check() -> EvalCheck:
    payload = build_scenario_request("canonical").model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["bindings"] = object()
    try:
        preflight_identity_binding_authorization(payload)
    except IdentityBindingAuthorizationError:
        return EvalCheck(
            name="authorization.consent_precedes_bindings",
            passed=True,
            detail="authorization_denied",
        )
    return EvalCheck(
        name="authorization.consent_precedes_bindings",
        passed=False,
        detail="authorization was not rejected",
    )


def _determinism_check() -> tuple[EvalCheck, IdentityBindingEvaluation]:
    request = build_scenario_request("canonical")
    replay = request.model_copy(
        update={
            "policy": request.policy.model_copy(
                update={
                    "allowed_entity_kinds": tuple(
                        reversed(request.policy.allowed_entity_kinds)
                    ),
                    "allowed_token_scope_ids": tuple(
                        reversed(request.policy.allowed_token_scope_ids)
                    ),
                }
            ),
            "bindings": tuple(reversed(request.bindings)),
        }
    )
    result = evaluate_identity_bindings(request)
    replay_result = evaluate_identity_bindings(replay)
    passed = result == replay_result and result.model_dump_json() == replay_result.model_dump_json()
    return (
        EvalCheck(
            name="determinism.semantic_order",
            passed=passed,
            detail=f"result_digest={result.result_digest}",
        ),
        result,
    )


def _privacy_check(results: list[IdentityBindingEvaluation]) -> EvalCheck:
    rendered = json.dumps(
        [item.model_dump(mode="json") for item in results],
        sort_keys=True,
    )
    forbidden_keys = {
        "medical_record_number",
        "raw_identifier",
        "raw_token",
        "scoped_token",
        "scope_id",
        "token_digest",
        "peptide_identification",
        "kinase_activity",
        "treatment_recommendation",
    }
    leaked = sorted(key for key in forbidden_keys if f'"{key}"' in rendered)
    token_canary = sha256_digest({"token": "same-scope-collision"})
    if token_canary in rendered:
        leaked.append("opaque_token_digest")
    return EvalCheck(
        name="boundary.closed_privacy_minimized_output",
        passed=not leaked,
        detail="closed typed output" if not leaked else f"forbidden={','.join(leaked)}",
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks: list[EvalCheck] = []
    results: list[IdentityBindingEvaluation] = []
    for scenario in corpus["scenarios"]:
        check, result = _result_check(scenario)
        checks.append(check)
        results.append(result)
        if scenario["outcome"] == "paired_result_and_authorization":
            checks.append(_authorization_check())
    deterministic, canonical_result = _determinism_check()
    checks.extend((deterministic, _privacy_check([*results, canonical_result])))
    passed = (
        corpus["module_id"] == MODULE_ID
        and len(corpus["scenarios"]) == EXPECTED_SCENARIO_COUNT
        and all(check.passed for check in checks)
    )
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_count": len(corpus["scenarios"]),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
