"""Replay the locked M01-05 artifact-detection corpus and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    ArtifactDetectionPolicy,
    ArtifactDetectionResult,
    ArtifactRule,
    Comparison,
    DetectArtifactsRequest,
    DetectorProfile,
    SignalObservation,
    SignalState,
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
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection import (
    detect_artifacts,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-05"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_05" / "scenarios.json"
EXPECTED_CLASS_COUNT: Final = 7
EXPECTED_SCENARIO_COUNT: Final = 4
TRIGGERED_POSTERIOR: Final = 0.95
DEFAULT_CLEAR_POSTERIOR: Final = 0.01
TECHNICAL_CLEAR_POSTERIOR: Final = 0.02
_REQUEST_ADAPTER: Final = TypeAdapter(DetectArtifactsRequest)


class Criteria(TypedDict):
    seeded_sensitivity_minimum: float
    clean_false_exclusion_maximum: float


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "validation_rejected"]
    expected_disposition: str | None
    expected_support: str | None
    expected_flag_count: int
    seeded_pairs: list[list[str]]
    clean_target_ids: list[str]
    not_evaluable_pairs: list[list[str]]
    excluded_target_ids: list[str]
    review_target_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    criteria: Criteria
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
        digest=digest or sha256_digest({"m0105": label}),
        media_type="application/json",
    )


def _rules() -> tuple[ArtifactRule, ...]:
    rules: list[ArtifactRule] = []
    for artifact_class in ArtifactClass:
        suffixes = ("primary", "confirmatory") if artifact_class is ArtifactClass.TECHNICAL else (
            "primary",
        )
        rules.extend(
            ArtifactRule(
                rule_id=f"rule.{artifact_class.value}.{suffix}",
                version="1.0.0",
                artifact_class=artifact_class,
                signal_id=f"signal.{artifact_class.value}.{suffix}",
                comparison=Comparison.GREATER_THAN_OR_EQUAL,
                threshold=0.8,
                unit="fraction",
                posterior_if_triggered=(
                    0.7
                    if artifact_class is ArtifactClass.TECHNICAL and suffix == "primary"
                    else TRIGGERED_POSTERIOR
                ),
                posterior_if_clear=(
                    TECHNICAL_CLEAR_POSTERIOR
                    if artifact_class is ArtifactClass.TECHNICAL and suffix == "confirmatory"
                    else DEFAULT_CLEAR_POSTERIOR
                ),
            )
            for suffix in suffixes
        )
    return tuple(rules)


def _policy() -> ArtifactDetectionPolicy:
    return ArtifactDetectionPolicy(
        policy_id="policy.synthetic.artifact-detection",
        version="1.0.0",
        review_threshold=0.5,
        exclusion_threshold=0.9,
        enabled_classes=tuple(ArtifactClass),
    )


def _profile(rules: tuple[ArtifactRule, ...]) -> DetectorProfile:
    return DetectorProfile(
        profile_id="profile.synthetic.artifact-detection",
        version="1.0.0",
        required_rule_ids=tuple(rule.rule_id for rule in rules),
        evidence=_artifact("detector-profile"),
    )


def _context(configuration: str) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0105",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0105": "identity-binding"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _signals(
    rules: tuple[ArtifactRule, ...],
    targets: tuple[str, ...],
    seeded: set[tuple[str, ArtifactClass]],
    missing: set[tuple[str, ArtifactClass]],
) -> tuple[SignalObservation, ...]:
    values: list[SignalObservation] = []
    for target_id in targets:
        for rule in rules:
            is_missing = (target_id, rule.artifact_class) in missing
            values.append(
                SignalObservation(
                    target_id=target_id,
                    signal_id=rule.signal_id,
                    state=SignalState.MISSING if is_missing else SignalState.OBSERVED,
                    value=(
                        None
                        if is_missing
                        else 0.9
                        if (target_id, rule.artifact_class) in seeded
                        else 0.1
                    ),
                    unit="fraction",
                    evidence=_artifact_evidence(target_id, rule.signal_id),
                )
            )
    return tuple(values)


def _artifact_evidence(target_id: str, signal_id: str) -> tuple[ArtifactReference, ...]:
    label = f"{target_id.removeprefix('target.')}.{signal_id.removeprefix('signal.')}"
    return (_artifact(label),)


_SEEDED: Final = {
    ("target.seeded.alpha", ArtifactClass.TECHNICAL),
    ("target.seeded.alpha", ArtifactClass.CONTAMINATION),
    ("target.seeded.beta", ArtifactClass.BARCODE_INDEX),
    ("target.seeded.beta", ArtifactClass.BATCH),
    ("target.seeded.gamma", ArtifactClass.LOW_COMPLEXITY),
    ("target.seeded.gamma", ArtifactClass.MAPPING),
    ("target.seeded.delta", ArtifactClass.CONTEXT_FALSE_POSITIVE),
}
_SEEDED_TARGETS: Final = tuple(sorted({target for target, _ in _SEEDED}))
_CLEAN_TARGETS: Final = tuple(f"target.clean.{index:02d}" for index in range(1, 5))


def _request_for(
    targets: tuple[str, ...],
    *,
    seeded: set[tuple[str, ArtifactClass]] | None = None,
    missing: set[tuple[str, ArtifactClass]] | None = None,
) -> DetectArtifactsRequest:
    rules = _rules()
    policy = _policy()
    profile = _profile(rules)
    return DetectArtifactsRequest(
        context=_context(configuration_digest(profile, policy, rules)),
        detector_profile=profile,
        policy=policy,
        rules=rules,
        signals=_signals(rules, targets, seeded or set(), missing or set()),
    )


def build_scenario_request(request_case: str) -> DetectArtifactsRequest:
    """Build a deterministic synthetic request for eval and benchmark reuse."""

    if request_case == "seeded_batch":
        return _request_for((*_SEEDED_TARGETS, *_CLEAN_TARGETS), seeded=set(_SEEDED))
    if request_case in {"clean", "consent_denied"}:
        return _request_for(("target.clean.single",))
    if request_case == "missing_required":
        return _request_for(
            ("target.missing",),
            missing={("target.missing", ArtifactClass.TECHNICAL)},
        )
    raise ValueError(request_case)


def _pairs(values: list[list[str]]) -> set[tuple[str, str]]:
    return {(pair[0], pair[1]) for pair in values}


def _reordered(request: DetectArtifactsRequest) -> DetectArtifactsRequest:
    return request.model_copy(
        update={
            "detector_profile": request.detector_profile.model_copy(
                update={
                    "required_rule_ids": tuple(
                        reversed(request.detector_profile.required_rule_ids)
                    )
                }
            ),
            "policy": request.policy.model_copy(
                update={"enabled_classes": tuple(reversed(request.policy.enabled_classes))}
            ),
            "rules": tuple(reversed(request.rules)),
            "signals": tuple(reversed(request.signals)),
        }
    )


def _clear_posterior(artifact_class: ArtifactClass) -> float:
    return (
        TECHNICAL_CLEAR_POSTERIOR
        if artifact_class is ArtifactClass.TECHNICAL
        else DEFAULT_CLEAR_POSTERIOR
    )


def _flag_expectations(
    result: ArtifactDetectionResult,
    scenario: Scenario,
) -> bool:
    seeded = _pairs(scenario["seeded_pairs"])
    not_evaluable = _pairs(scenario["not_evaluable_pairs"])
    if len(result.flags) != scenario["expected_flag_count"]:
        return False
    for flag in result.flags:
        key = (flag.target_id, flag.artifact_class.value)
        expected: tuple[str, float | None, str]
        if key in seeded:
            expected = ("estimated", TRIGGERED_POSTERIOR, "exclude")
        elif key in not_evaluable:
            expected = ("not_evaluable", None, "not_evaluable")
        else:
            expected = ("estimated", _clear_posterior(flag.artifact_class), "clear")
        actual = (flag.posterior.state.value, flag.posterior.value, flag.disposition.value)
        if actual != expected:
            return False
    return {flag.artifact_class for flag in result.flags} == set(ArtifactClass)


def _rates(
    result: ArtifactDetectionResult,
    scenario: Scenario,
) -> tuple[float | None, float | None]:
    seeded = _pairs(scenario["seeded_pairs"])
    detected = {
        (flag.target_id, flag.artifact_class.value)
        for flag in result.flags
        if flag.disposition.value == "exclude"
    }
    sensitivity = len(seeded & detected) / len(seeded) if seeded else None
    clean = set(scenario["clean_target_ids"])
    false_excluded = clean.intersection(result.exclusion_mask.excluded_target_ids)
    false_exclusion = len(false_excluded) / len(clean) if clean else None
    return sensitivity, false_exclusion


def _profile_check(scenario: Scenario, criteria: Criteria) -> tuple[EvalCheck, dict[str, object]]:
    request = build_scenario_request(scenario["request_case"])
    result = detect_artifacts(request)
    replay = detect_artifacts(_reordered(request))
    sensitivity, false_exclusion = _rates(result, scenario)
    rates_pass = (
        (sensitivity is None or sensitivity >= criteria["seeded_sensitivity_minimum"])
        and (
            false_exclusion is None
            or false_exclusion <= criteria["clean_false_exclusion_maximum"]
        )
    )
    passed = (
        result == replay
        and result.disposition.value == scenario["expected_disposition"]
        and result.support.status.value == scenario["expected_support"]
        and result.exclusion_mask.excluded_target_ids
        == tuple(scenario["excluded_target_ids"])
        and result.exclusion_mask.review_target_ids == tuple(scenario["review_target_ids"])
        and _flag_expectations(result, scenario)
        and rates_pass
    )
    detail = (
        f"disposition={result.disposition.value};flags={len(result.flags)};"
        f"excluded={len(result.exclusion_mask.excluded_target_ids)};"
        f"sensitivity={sensitivity};false_exclusion={false_exclusion};"
        f"order_equal={result == replay}"
    )
    return (
        EvalCheck(f"scenario.{scenario['case_id']}", passed, detail),
        cast("dict[str, object]", result.model_dump(mode="json")),
    )


def _consent_rejected() -> bool:
    request = build_scenario_request("consent_denied")
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    try:
        _REQUEST_ADAPTER.validate_python(payload, strict=True)
    except ValidationError:
        return True
    return False


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _boundary_check(results: list[dict[str, object]]) -> EvalCheck:
    forbidden = {
        "kinase_activity",
        "omics_fusion",
        "proteotype",
        "raw_measurements",
        "raw_payload",
        "treatment_recommendation",
        "upstream_mutations",
    }
    leaked = sorted(_all_keys(results).intersection(forbidden))
    return EvalCheck(
        "boundary.artifact_output_only",
        not leaked,
        "closed artifact output" if not leaked else f"forbidden={','.join(leaked)}",
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _checks(corpus: Corpus) -> tuple[list[EvalCheck], list[dict[str, object]]]:
    checks: list[EvalCheck] = []
    results: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        if scenario["outcome"] == "validation_rejected":
            rejected = _consent_rejected()
            checks.append(
                EvalCheck(
                    f"scenario.{scenario['case_id']}",
                    rejected,
                    "strict request validation rejected consent" if rejected else "not rejected",
                )
            )
        else:
            check, serialized = _profile_check(scenario, corpus["criteria"])
            checks.append(check)
            results.append(serialized)
    return checks, results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks, results = _checks(corpus)
    checks.append(_boundary_check(results))
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["data_classification"] == "synthetic_nonclinical"
        and len(ArtifactClass) == EXPECTED_CLASS_COUNT
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
