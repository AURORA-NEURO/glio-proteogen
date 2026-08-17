"""Replay the locked M02-05 synthetic identification-artifact corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, TypedDict, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m02_05 import (
    ArtifactClass,
    ArtifactRule,
    Comparison,
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
    IdentificationArtifactPolicy,
    IdentificationArtifactProfile,
    IdentificationSignalObservation,
    IdentificationSignalState,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    IdentificationArtifactAuthorizationError,
    detect_identification_artifacts,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-05"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_05" / "scenarios.json"
EXPECTED_SCENARIO_IDS: Final = (
    "conformant_clean",
    "seven_class_seeded",
    "clean_zero_false_exclusion",
    "missing_required_signal",
    "unsupported_ood_signal",
    "multi_class_deduplicated_mask",
    "order_determinism",
    "consent_denied_preflight",
)
EXPECTED_CLASS_COUNT: Final = 7
TRIGGERED_POSTERIOR: Final = 0.95
CLEAR_POSTERIOR: Final = 0.01


class Criteria(TypedDict):
    seeded_sensitivity_minimum: float
    clean_false_exclusion_maximum: float


class Scenario(TypedDict):
    id: str
    mutation: str
    expected_disposition: str
    expected_flag_count: int
    seeded_pairs: list[list[str]]
    clean_target_ids: list[str]
    not_evaluable_pairs: list[list[str]]
    expected_excluded_target_ids: list[str]
    expected_review_target_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    contract_version: str
    data_classification: str
    claims_ceiling: str
    criteria: Criteria
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0205.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0205": label}),
        media_type="application/json",
    )


def _rules(
    optional_signal_classes: set[ArtifactClass] | None = None,
) -> tuple[ArtifactRule, ...]:
    optional = optional_signal_classes or set()
    return tuple(
        ArtifactRule(
            rule_id=f"rule.m0205.{artifact_class.value}",
            version="1.0.0",
            artifact_class=artifact_class,
            signal_id=f"signal.m0205.{artifact_class.value}",
            comparison=Comparison.GREATER_THAN_OR_EQUAL,
            threshold=0.8,
            unit="fraction",
            posterior_if_triggered=TRIGGERED_POSTERIOR,
            posterior_if_clear=CLEAR_POSTERIOR,
            required_signal=artifact_class not in optional,
        )
        for artifact_class in ArtifactClass
    )


def _policy() -> IdentificationArtifactPolicy:
    return IdentificationArtifactPolicy(
        policy_id="policy.m0205.identification-artifact-v1",
        version="1.0.0",
        review_threshold=0.5,
        exclusion_threshold=0.9,
    )


def _profile(rules: tuple[ArtifactRule, ...]) -> IdentificationArtifactProfile:
    return IdentificationArtifactProfile(
        profile_id="profile.m0205.identification-artifact-v1",
        version="1.0.0",
        required_rule_ids=tuple(rule.rule_id for rule in rules),
        evidence=_artifact("detector-profile"),
    )


def _context(configuration: str) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0205.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{role}", digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0205",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 21, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0205.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0205": "identity-lineage"}),
                evidence=_artifact("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0205.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _signals(
    rules: tuple[ArtifactRule, ...],
    targets: tuple[str, ...],
    *,
    seeded: set[tuple[str, ArtifactClass]],
    missing: set[tuple[str, ArtifactClass]],
    unsupported: set[tuple[str, ArtifactClass]],
) -> tuple[IdentificationSignalObservation, ...]:
    values: list[IdentificationSignalObservation] = []
    for target_id in targets:
        for rule in rules:
            key = (target_id, rule.artifact_class)
            state = (
                IdentificationSignalState.MISSING
                if key in missing
                else IdentificationSignalState.UNSUPPORTED
                if key in unsupported
                else IdentificationSignalState.OBSERVED
            )
            values.append(
                IdentificationSignalObservation(
                    target_id=target_id,
                    signal_id=rule.signal_id,
                    state=state,
                    value=(
                        TRIGGERED_POSTERIOR
                        if state is IdentificationSignalState.OBSERVED and key in seeded
                        else 0.1
                        if state is IdentificationSignalState.OBSERVED
                        else None
                    ),
                    unit=("fraction" if state is IdentificationSignalState.OBSERVED else None),
                    evidence=(
                        _artifact(f"signal.{target_id}.{rule.artifact_class.value}.primary"),
                        _artifact(f"signal.{target_id}.{rule.artifact_class.value}.audit"),
                    ),
                )
            )
    return tuple(values)


def _request_for(
    targets: tuple[str, ...],
    *,
    seeded: set[tuple[str, ArtifactClass]] | None = None,
    missing: set[tuple[str, ArtifactClass]] | None = None,
    unsupported: set[tuple[str, ArtifactClass]] | None = None,
    optional_signal_classes: set[ArtifactClass] | None = None,
) -> DetectIdentificationArtifactsRequest:
    rules = _rules(optional_signal_classes)
    policy = _policy()
    profile = _profile(rules)
    return DetectIdentificationArtifactsRequest(
        context=_context(configuration_digest(profile, policy, rules)),
        detector_profile=profile,
        policy=policy,
        rules=rules,
        signals=_signals(
            rules,
            targets,
            seeded=seeded or set(),
            missing=missing or set(),
            unsupported=unsupported or set(),
        ),
    )


_SEVEN_CLASS_SEEDS: Final = {
    ("target.seeded.alpha", ArtifactClass.TECHNICAL),
    ("target.seeded.alpha", ArtifactClass.CONTAMINATION),
    ("target.seeded.beta", ArtifactClass.BARCODE_INDEX),
    ("target.seeded.beta", ArtifactClass.BATCH),
    ("target.seeded.gamma", ArtifactClass.LOW_COMPLEXITY),
    ("target.seeded.gamma", ArtifactClass.MAPPING),
    ("target.seeded.delta", ArtifactClass.CONTEXT_FALSE_POSITIVE),
}
_SEVEN_CLASS_TARGETS: Final = tuple(sorted({item[0] for item in _SEVEN_CLASS_SEEDS}))
_CLEAN_TARGETS: Final = tuple(f"target.clean.{index:02d}" for index in range(1, 5))


def build_scenario_request(
    mutation: str = "clean_single",
) -> DetectIdentificationArtifactsRequest:
    """Build one deterministic synthetic request from the public contract."""

    targets: tuple[str, ...]
    seeded: set[tuple[str, ArtifactClass]]
    missing: set[tuple[str, ArtifactClass]]
    unsupported: set[tuple[str, ArtifactClass]]
    optional_signal_classes: set[ArtifactClass]
    if mutation in {"clean_single", "withheld_consent_hostile_signals"}:
        targets = ("target.clean.single",)
        seeded = set()
        missing = set()
        unsupported = set()
        optional_signal_classes = set()
    elif mutation == "seven_class_seeded":
        targets = _SEVEN_CLASS_TARGETS
        seeded = set(_SEVEN_CLASS_SEEDS)
        missing = set()
        unsupported = set()
        optional_signal_classes = set()
    elif mutation == "clean_batch":
        targets = _CLEAN_TARGETS
        seeded = set()
        missing = set()
        unsupported = set()
        optional_signal_classes = set()
    elif mutation == "missing_required":
        targets = ("target.missing",)
        seeded = set()
        missing = {("target.missing", ArtifactClass.TECHNICAL)}
        unsupported = set()
        optional_signal_classes = set()
    elif mutation == "unsupported_ood":
        targets = ("target.ood",)
        seeded = set()
        missing = set()
        unsupported = {("target.ood", ArtifactClass.CONTAMINATION)}
        optional_signal_classes = {ArtifactClass.CONTAMINATION}
    elif mutation == "multi_class":
        targets = ("target.multi",)
        seeded = {
            ("target.multi", ArtifactClass.CONTAMINATION),
            ("target.multi", ArtifactClass.BARCODE_INDEX),
        }
        missing = set()
        unsupported = set()
        optional_signal_classes = set()
    elif mutation == "order_determinism":
        targets = ("target.order.seeded", "target.order.clean")
        seeded = {("target.order.seeded", ArtifactClass.TECHNICAL)}
        missing = set()
        unsupported = set()
        optional_signal_classes = set()
    else:
        raise ValueError(mutation)
    return _request_for(
        targets,
        seeded=seeded,
        missing=missing,
        unsupported=unsupported,
        optional_signal_classes=optional_signal_classes,
    )


def _reordered(
    request: DetectIdentificationArtifactsRequest,
) -> DetectIdentificationArtifactsRequest:
    signals = tuple(
        signal.model_copy(update={"evidence": tuple(reversed(signal.evidence))})
        for signal in reversed(request.signals)
    )
    return request.model_copy(
        update={
            "detector_profile": request.detector_profile.model_copy(
                update={
                    "required_rule_ids": tuple(reversed(request.detector_profile.required_rule_ids))
                }
            ),
            "rules": tuple(reversed(request.rules)),
            "signals": signals,
        }
    )


def _pairs(values: list[list[str]]) -> set[tuple[str, str]]:
    return {(value[0], value[1]) for value in values}


def _flag_expectations(
    result: IdentificationArtifactDetectionResult,
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
            expected = ("estimated", CLEAR_POSTERIOR, "clear")
        actual = (
            flag.posterior.state.value,
            flag.posterior.value,
            flag.disposition.value,
        )
        if actual != expected:
            return False
    return {flag.artifact_class for flag in result.flags} == set(ArtifactClass)


def _rates(
    result: IdentificationArtifactDetectionResult,
    scenario: Scenario,
) -> tuple[float | None, float | None]:
    seeded = _pairs(scenario["seeded_pairs"])
    excluded_pairs = {
        (flag.target_id, flag.artifact_class.value)
        for flag in result.flags
        if flag.disposition.value == "exclude"
    }
    sensitivity = len(seeded & excluded_pairs) / len(seeded) if seeded else None
    clean = set(scenario["clean_target_ids"])
    false_excluded = clean.intersection(result.exclusion_mask.excluded_target_ids)
    false_exclusion = len(false_excluded) / len(clean) if clean else None
    return sensitivity, false_exclusion


def _result_check(scenario: Scenario, criteria: Criteria) -> tuple[EvalCheck, dict[str, object]]:
    request = build_scenario_request(scenario["mutation"])
    result = detect_identification_artifacts(request)
    sensitivity, false_exclusion = _rates(result, scenario)
    order_equal = True
    if scenario["mutation"] == "order_determinism":
        replay = detect_identification_artifacts(_reordered(request))
        order_equal = result == replay and result.model_dump_json() == replay.model_dump_json()
    expected_support = (
        "limited" if scenario["expected_disposition"] == "accepted" else "review_required"
    )
    passed = (
        result.disposition.value == scenario["expected_disposition"]
        and result.support.status.value == expected_support
        and result.parent_target == "protein_subtype"
        and result.exclusion_mask.excluded_target_ids
        == tuple(scenario["expected_excluded_target_ids"])
        and result.exclusion_mask.review_target_ids == tuple(scenario["expected_review_target_ids"])
        and _flag_expectations(result, scenario)
        and order_equal
        and (sensitivity is None or sensitivity >= criteria["seeded_sensitivity_minimum"])
        and (
            false_exclusion is None or false_exclusion <= criteria["clean_false_exclusion_maximum"]
        )
    )
    return (
        EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=passed,
            detail=(
                f"disposition={result.disposition.value};flags={len(result.flags)};"
                f"excluded={len(result.exclusion_mask.excluded_target_ids)};"
                f"sensitivity={sensitivity};false_exclusion={false_exclusion};"
                f"order_equal={order_equal}"
            ),
        ),
        cast("dict[str, object]", result.model_dump(mode="json")),
    )


class _UnreadableSignals:
    _ITER_MESSAGE = "signals were traversed before authorization"
    _LEN_MESSAGE = "signals were sized before authorization"

    def __iter__(self) -> object:
        raise AssertionError(self._ITER_MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._LEN_MESSAGE)


def _consent_check(scenario: Scenario) -> EvalCheck:
    request = build_scenario_request(scenario["mutation"])
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["signals"] = _UnreadableSignals()
    try:
        detect_identification_artifacts(payload)
    except AssertionError as error:
        return EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=False,
            detail=str(error),
        )
    except IdentificationArtifactAuthorizationError:
        return EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=scenario["expected_disposition"] == "boundary_rejected",
            detail="authorization_denied_before_signal_traversal",
        )
    return EvalCheck(
        name=f"scenario.{scenario['id']}",
        passed=False,
        detail="withheld consent was not rejected",
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _boundary_check(results: list[dict[str, object]]) -> EvalCheck:
    forbidden_keys = {
        "detector_profile",
        "kinase_activity",
        "omics_fusion",
        "peptide_rows",
        "policy",
        "protein_subtype_score",
        "proteotype",
        "raw_assay_rows",
        "raw_payload",
        "raw_spectra",
        "rules",
        "scientific_interpretation",
        "signals",
        "treatment_recommendation",
        "upstream_mutations",
    }
    leaked_keys = sorted(_all_keys(results) & forbidden_keys)
    rendered = canonical_json_bytes(results).decode("utf-8")
    leaked_values = [
        value
        for value in ("MPEPTIDE", "SYNTHETIC_SAMPLE", "synthetic-spectrum-1")
        if value in rendered
    ]
    passed = not leaked_keys and not leaked_values
    return EvalCheck(
        name="boundary.closed_identification_artifact_output",
        passed=passed,
        detail=(
            "no raw payload or prohibited scientific/clinical claims"
            if passed
            else f"keys={','.join(leaked_keys)};values={','.join(leaked_values)}"
        ),
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _corpus_check(corpus: Corpus) -> EvalCheck:
    scenario_ids = tuple(item["id"] for item in corpus["scenarios"])
    seeded_scenario = next(
        item for item in corpus["scenarios"] if item["id"] == "seven_class_seeded"
    )
    seeded_classes = {pair[1] for pair in seeded_scenario["seeded_pairs"]}
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["contract_version"] == "1.0.0"
        and corpus["data_classification"] == "synthetic_nonclinical"
        and corpus["claims_ceiling"] == "deterministic_synthetic_fixture_regression_only"
        and scenario_ids == EXPECTED_SCENARIO_IDS
        and len(ArtifactClass) == EXPECTED_CLASS_COUNT
        and len(seeded_scenario["seeded_pairs"]) == EXPECTED_CLASS_COUNT
        and seeded_classes == {artifact_class.value for artifact_class in ArtifactClass}
    )
    return EvalCheck(
        name="corpus.locked_eight_synthetic_scenarios",
        passed=passed,
        detail=f"scenario_count={len(corpus['scenarios'])};class_count={len(ArtifactClass)}",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks = [_corpus_check(corpus)]
    results: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        if scenario["mutation"] == "withheld_consent_hostile_signals":
            checks.append(_consent_check(scenario))
        else:
            check, result = _result_check(scenario, corpus["criteria"])
            checks.append(check)
            results.append(result)
    checks.append(_boundary_check(results))
    passed = all(item.passed for item in checks)
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_count": len(corpus["scenarios"]),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(item) for item in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
