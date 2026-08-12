"""Replay the locked M02-04 synthetic identification-quality corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, cast

from glio_proteogen.contracts.m02_04 import (
    ComputeIdentificationQualityRequest,
    IdentificationAssayProfile,
    IdentificationAssayType,
    IdentificationQualityMetricCode,
    IdentificationQualityPolicy,
    IdentificationQualityProfile,
    MetricDirection,
    MetricObservation,
    MetricObservationState,
    MetricThreshold,
    configuration_digest,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
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
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    IdentificationQualityAuthorizationError,
    compute_identification_quality,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-04"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_04" / "scenarios.json"
EXPECTED_SCENARIO_COUNT: Final = 8
EXPECTED_SCENARIO_IDS: Final = (
    "conformant_supported_profile",
    "low_identification_coverage",
    "excessive_target_decoy_fdr",
    "precursor_mass_error_accuracy_failure",
    "required_observation_missing",
    "optional_censored_or_not_applicable",
    "control_material_and_sample_context_mismatch",
    "consent_denied_preflight",
)


class Scenario(TypedDict):
    id: str
    mutation: str
    expected_disposition: str
    expected_statuses: dict[str, str]


class Corpus(TypedDict):
    module_id: str
    contract_version: str
    data_classification: str
    claims_ceiling: str
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0204.{label}",
        version="1.0.0",
        digest=sha256_digest({"m0204": label}),
        media_type="application/json",
    )


def _thresholds(*, optional_mass_error: bool = False) -> tuple[MetricThreshold, ...]:
    values = {
        IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE: MetricThreshold(
            metric_code=IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE,
            direction=MetricDirection.HIGHER_IS_BETTER,
            pass_minimum=0.80,
            warning_minimum=0.70,
        ),
        IdentificationQualityMetricCode.TARGET_DECOY_FDR: MetricThreshold(
            metric_code=IdentificationQualityMetricCode.TARGET_DECOY_FDR,
            direction=MetricDirection.LOWER_IS_BETTER,
            pass_maximum=0.01,
            warning_maximum=0.02,
        ),
        IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY: MetricThreshold(
            metric_code=IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY,
            direction=MetricDirection.LOWER_IS_BETTER,
            required=not optional_mass_error,
            pass_maximum=5.0,
            warning_maximum=8.0,
        ),
        IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS: MetricThreshold(
            metric_code=IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS,
            direction=MetricDirection.HIGHER_IS_BETTER,
            pass_minimum=0.90,
            warning_minimum=0.80,
        ),
        IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY: MetricThreshold(
            metric_code=IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY,
            direction=MetricDirection.WITHIN_RANGE,
            pass_minimum=0.85,
            pass_maximum=1.15,
            warning_minimum=0.75,
            warning_maximum=1.25,
        ),
        IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH: MetricThreshold(
            metric_code=IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH,
            direction=MetricDirection.HIGHER_IS_BETTER,
            pass_minimum=1.0,
            warning_minimum=1.0,
        ),
    }
    return tuple(values[code] for code in IdentificationQualityMetricCode)


def _policy(*, optional_mass_error: bool = False) -> IdentificationQualityPolicy:
    return IdentificationQualityPolicy(
        policy_id="policy.synthetic.m0204.identification-quality",
        version="1.0.0",
        thresholds=_thresholds(optional_mass_error=optional_mass_error),
        quarantine_on_warning=False,
    )


def _context(policy: IdentificationQualityPolicy) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0204.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=ArtifactReference(
                artifact_id=f"artifact.synthetic.m0204.control.{role}",
                version="1.0.0",
                digest=digest or sha256_digest({"m0204-control": role}),
                media_type="application/json",
            ),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0204",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 20, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", configuration_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0204.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0204": "identity-lineage"}),
                evidence=_artifact("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0204.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _ratio(
    metric_code: IdentificationQualityMetricCode,
    numerator: float,
    denominator: float = 100.0,
) -> MetricObservation:
    return MetricObservation(
        metric_code=metric_code,
        state=MetricObservationState.OBSERVED,
        numerator=numerator,
        denominator=denominator,
        evidence=(_artifact(f"observation.{metric_code.value}"),),
    )


def _value(
    metric_code: IdentificationQualityMetricCode,
    *,
    value: float | bool,
) -> MetricObservation:
    return MetricObservation(
        metric_code=metric_code,
        state=MetricObservationState.OBSERVED,
        value=value,
        evidence=(_artifact(f"observation.{metric_code.value}"),),
    )


def _observations() -> list[MetricObservation]:
    code = IdentificationQualityMetricCode
    return [
        _ratio(code.IDENTIFICATION_COVERAGE, 90.0),
        _ratio(code.TARGET_DECOY_FDR, 0.5),
        _value(code.PRECURSOR_MASS_ERROR_ACCURACY, value=3.0),
        _ratio(code.IDENTIFICATION_COMPLETENESS, 95.0),
        _ratio(code.CONTROL_MATERIAL_RECOVERY, 100.0),
        _value(code.SAMPLE_CONTEXT_MATCH, value=True),
    ]


def _replacement(
    observations: list[MetricObservation],
    observation: MetricObservation,
) -> None:
    observations[observations.index(next(
        item for item in observations if item.metric_code is observation.metric_code
    ))] = observation


def build_scenario_request(
    mutation: str = "none",
) -> ComputeIdentificationQualityRequest:
    """Build one deterministic request using only the public contract."""

    optional_mass_error = mutation == "optional_censored_or_not_applicable"
    policy = _policy(optional_mass_error=optional_mass_error)
    observations = _observations()
    code = IdentificationQualityMetricCode
    if mutation == "low_identification_coverage":
        _replacement(observations, _ratio(code.IDENTIFICATION_COVERAGE, 60.0))
    elif mutation == "excessive_target_decoy_fdr":
        _replacement(observations, _ratio(code.TARGET_DECOY_FDR, 3.0))
    elif mutation == "precursor_mass_error_accuracy_failure":
        _replacement(
            observations,
            _value(code.PRECURSOR_MASS_ERROR_ACCURACY, value=12.0),
        )
    elif mutation == "required_observation_missing":
        _replacement(
            observations,
            MetricObservation(
                metric_code=code.IDENTIFICATION_COMPLETENESS,
                state=MetricObservationState.MISSING,
                evidence=(_artifact("observation.identification_completeness.missing"),),
            ),
        )
    elif mutation == "optional_censored_or_not_applicable":
        _replacement(
            observations,
            MetricObservation(
                metric_code=code.PRECURSOR_MASS_ERROR_ACCURACY,
                state=MetricObservationState.CENSORED,
                upper_bound=4.0,
                evidence=(_artifact("observation.mass-error.censored"),),
            ),
        )
    elif mutation == "control_material_and_sample_context_mismatch":
        _replacement(observations, _ratio(code.CONTROL_MATERIAL_RECOVERY, 60.0))
        _replacement(observations, _value(code.SAMPLE_CONTEXT_MATCH, value=False))
    elif mutation not in {"none", "withheld_consent_and_unreadable_observations"}:
        raise ValueError(mutation)
    return ComputeIdentificationQualityRequest(
        context=_context(policy),
        assay_profile=IdentificationAssayProfile(
            profile_id="assay.synthetic.m0204.dia",
            version="1.0.0",
            assay_type=IdentificationAssayType.DIA,
            target_decoy_strategy="concatenated_target_decoy",
            evidence=_artifact("assay-profile"),
        ),
        policy=policy,
        observations=tuple(observations),
    )


class _UnreadableObservations:
    _MESSAGE = "observations were traversed"

    def __iter__(self) -> Iterator[object]:
        raise AssertionError(self._MESSAGE)


def _status_map(profile: IdentificationQualityProfile) -> dict[str, str]:
    return {item.metric_code.value: item.status.value for item in profile.metrics}


def _scenario_check(
    scenario: Scenario,
) -> tuple[EvalCheck, IdentificationQualityProfile | None]:
    request = build_scenario_request(scenario["mutation"])
    if scenario["mutation"] == "withheld_consent_and_unreadable_observations":
        payload = request.model_dump(mode="python")
        payload["context"]["references"]["consent"]["state"] = "withheld"
        payload["observations"] = _UnreadableObservations()
        try:
            compute_identification_quality(payload)
        except IdentificationQualityAuthorizationError:
            return (
                EvalCheck(
                    name=f"scenario.{scenario['id']}",
                    passed=scenario["expected_disposition"] == "boundary_rejected",
                    detail="authorization_denied_before_observation_traversal",
                ),
                None,
            )
        return (
            EvalCheck(
                name=f"scenario.{scenario['id']}",
                passed=False,
                detail="authorization was not rejected",
            ),
            None,
        )
    profile = compute_identification_quality(request)
    statuses = _status_map(profile)
    passed = (
        profile.disposition.value == scenario["expected_disposition"]
        and all(
            statuses[code] == expected
            for code, expected in scenario["expected_statuses"].items()
        )
        and set(statuses) == {code.value for code in IdentificationQualityMetricCode}
    )
    return (
        EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=passed,
            detail=(
                f"disposition={profile.disposition.value};"
                f"statuses={','.join(f'{code}:{statuses[code]}' for code in sorted(statuses))}"
            ),
        ),
        profile,
    )


def _determinism_check() -> tuple[EvalCheck, IdentificationQualityProfile]:
    request = build_scenario_request()
    replay_request = request.model_copy(
        update={
            "policy": request.policy.model_copy(
                update={"thresholds": tuple(reversed(request.policy.thresholds))}
            ),
            "observations": tuple(reversed(request.observations)),
        }
    )
    direct = compute_identification_quality(request)
    replay = compute_identification_quality(replay_request)
    passed = direct == replay and direct.model_dump_json() == replay.model_dump_json()
    return (
        EvalCheck(
            name="determinism.full_output_semantic_order",
            passed=passed,
            detail=f"result_digest={direct.result_digest}",
        ),
        direct,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _privacy_check(profiles: list[IdentificationQualityProfile]) -> EvalCheck:
    values = [item.model_dump(mode="json") for item in profiles]
    forbidden_keys = {
        "kinase_activity",
        "omics_fusion",
        "peptide_rows",
        "protein_subtype_score",
        "proteotype",
        "raw_assay_rows",
        "raw_spectra",
        "scientific_interpretation",
        "treatment_recommendation",
    }
    leaked = sorted(_all_keys(values) & forbidden_keys)
    rendered = canonical_json_bytes(values).decode("utf-8")
    canaries = ("MPEPTIDE", "SYNTHETIC_SAMPLE", "synthetic-run-1")
    leaked_values = [item for item in canaries if item in rendered]
    passed = not leaked and not leaked_values
    return EvalCheck(
        name="boundary.closed_quality_profile_only",
        passed=passed,
        detail=(
            "no raw payload or prohibited scientific/clinical claims"
            if passed
            else f"keys={','.join(leaked)};values={','.join(leaked_values)}"
        ),
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _corpus_check(corpus: Corpus) -> EvalCheck:
    observed_ids = tuple(item["id"] for item in corpus["scenarios"])
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["contract_version"] == "1.0.0"
        and corpus["data_classification"] == "synthetic_nonclinical"
        and corpus["claims_ceiling"] == "deterministic_synthetic_reference_regression_only"
        and len(corpus["scenarios"]) == EXPECTED_SCENARIO_COUNT
        and observed_ids == EXPECTED_SCENARIO_IDS
    )
    return EvalCheck(
        name="corpus.locked_eight_synthetic_scenarios",
        passed=passed,
        detail=f"scenario_count={len(corpus['scenarios'])}",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks = [_corpus_check(corpus)]
    profiles: list[IdentificationQualityProfile] = []
    for scenario in corpus["scenarios"]:
        check, profile = _scenario_check(scenario)
        checks.append(check)
        if profile is not None:
            profiles.append(profile)
    determinism, canonical_profile = _determinism_check()
    checks.extend((determinism, _privacy_check([*profiles, canonical_profile])))
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
