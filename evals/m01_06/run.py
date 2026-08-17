"""Replay the locked M01-06 harmonization fixture and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict, cast

from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m01_06 import (
    BiologicalInvariant,
    DiagnosticStatus,
    FactorLevel,
    HarmonizationObservation,
    HarmonizationPolicy,
    HarmonizationProfile,
    HarmonizationResult,
    HarmonizationStage,
    HarmonizeObservationsRequest,
    InvariantKind,
    ObservationState,
    ShiftState,
    TechnicalFactor,
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
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization import (
    harmonize_observations,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-06"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_06" / "scenarios.json"
EXPECTED_SCENARIO_COUNT: Final = 6
UNIT: Final = "log2_intensity"
BATCH_SHIFT: Final = 4.0
PLATFORM_SHIFT: Final = 2.0
DEFAULT_CAP: Final = 10.0
_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeObservationsRequest)


class Expected(TypedDict):
    outcome: Literal["result", "validation_rejected"]
    disposition: str | None
    support: str | None
    technical_spread_reduced: NotRequired[bool]
    protected_direction_retained: NotRequired[bool]
    protected_rank_retained: NotRequired[bool]
    missing_count: NotRequired[int]
    censored_count: NotRequired[int]
    reason: NotRequired[str]


class Scenario(TypedDict):
    case_id: str
    request_case: str
    expected: Expected


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
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
        digest=digest or sha256_digest({"m0106": label}),
        media_type="application/json",
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
        request_id="request.synthetic.m0106",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0106": "identity-binding"}),
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


def _levels(batch: str, platform: str) -> tuple[FactorLevel, ...]:
    return (
        FactorLevel(factor=TechnicalFactor.BATCH, level_id=batch),
        FactorLevel(factor=TechnicalFactor.PLATFORM, level_id=platform),
    )


def _observation(  # noqa: PLR0913, PLR0917 - mirrors the public observation.
    sample: str,
    feature: str,
    group: str,
    batch: str,
    platform: str,
    value: float | None,
    *,
    state: ObservationState = ObservationState.OBSERVED,
) -> HarmonizationObservation:
    return HarmonizationObservation(
        sample_id=sample,
        feature_id=feature,
        group_id=group,
        state=state,
        value=value,
        unit=UNIT,
        detection_limit=1.0 if state is ObservationState.BELOW_DETECTION_LIMIT else None,
        factor_levels=_levels(batch, platform),
        evidence=(_artifact(f"{sample}.{feature}"),),
    )


_COMBINATIONS: Final = (
    ("rr", "batch.reference", "platform.reference", 0.0),
    ("sr", "batch.shifted", "platform.reference", BATCH_SHIFT),
    ("rs", "batch.reference", "platform.shifted", PLATFORM_SHIFT),
    (
        "ss",
        "batch.shifted",
        "platform.shifted",
        BATCH_SHIFT + PLATFORM_SHIFT,
    ),
)


def _base_observations(*, add_absent: bool = False) -> tuple[HarmonizationObservation, ...]:
    values: list[HarmonizationObservation] = []
    for suffix, batch, platform, offset in _COMBINATIONS:
        control = f"control.{suffix}"
        values.extend(
            (
                _observation(control, "control.a", "group.control", batch, platform, 10 + offset),
                _observation(control, "control.b", "group.control", batch, platform, 20 + offset),
            )
        )
        for group, direction in (("group.low", 5.0), ("group.high", 9.0)):
            sample = f"biology.{group.removeprefix('group.')}.{suffix}"
            values.extend(
                (
                    _observation(
                        sample,
                        "biology.direction",
                        group,
                        batch,
                        platform,
                        direction + offset,
                    ),
                    _observation(
                        sample,
                        "biology.rank.low",
                        group,
                        batch,
                        platform,
                        3.0 + offset,
                    ),
                    _observation(
                        sample,
                        "biology.rank.high",
                        group,
                        batch,
                        platform,
                        7.0 + offset,
                    ),
                )
            )
    if add_absent:
        values.extend(
            (
                _observation(
                    "biology.low.rr",
                    "aux.missing",
                    "group.low",
                    "batch.reference",
                    "platform.reference",
                    None,
                    state=ObservationState.MISSING,
                ),
                _observation(
                    "biology.high.ss",
                    "aux.censored",
                    "group.high",
                    "batch.shifted",
                    "platform.shifted",
                    None,
                    state=ObservationState.BELOW_DETECTION_LIMIT,
                ),
            )
        )
    return tuple(values)


def _invariants() -> tuple[BiologicalInvariant, ...]:
    return (
        BiologicalInvariant(
            invariant_id="invariant.direction",
            kind=InvariantKind.DIRECTION,
            feature_ids=("biology.direction",),
            group_ids=("group.low", "group.high"),
        ),
        BiologicalInvariant(
            invariant_id="invariant.rank",
            kind=InvariantKind.RANK,
            feature_ids=("biology.rank.low", "biology.rank.high"),
            group_ids=("group.low",),
        ),
    )


def _profile(observations: tuple[HarmonizationObservation, ...]) -> HarmonizationProfile:
    controls = tuple(
        sorted({item.sample_id for item in observations if item.sample_id.startswith("control.")})
    )
    return HarmonizationProfile(
        profile_id="profile.synthetic.harmonization",
        version="1.0.0",
        stages=(
            HarmonizationStage(
                stage_id="stage.batch",
                ordinal=1,
                factor=TechnicalFactor.BATCH,
                reference_level_id="batch.reference",
                control_sample_ids=controls,
                control_feature_ids=("control.a", "control.b"),
            ),
            HarmonizationStage(
                stage_id="stage.platform",
                ordinal=2,
                factor=TechnicalFactor.PLATFORM,
                reference_level_id="platform.reference",
                control_sample_ids=controls,
                control_feature_ids=("control.a", "control.b"),
            ),
        ),
        evidence=_artifact("harmonization-profile"),
    )


def _request(  # noqa: PLR0913 - scenario builder exposes policy boundaries.
    observations: tuple[HarmonizationObservation, ...],
    *,
    cap: float = DEFAULT_CAP,
    minimum: int = 2,
    technical_tolerance: float = 0.0,
    biological_tolerance: float = 0.0,
    invariants: tuple[BiologicalInvariant, ...] | None = None,
) -> HarmonizeObservationsRequest:
    protected = _invariants() if invariants is None else invariants
    profile = _profile(observations)
    policy = HarmonizationPolicy(
        policy_id="policy.synthetic.harmonization",
        version="1.0.0",
        max_absolute_shift=cap,
        min_controls_per_level=minimum,
        technical_effect_tolerance=technical_tolerance,
        biological_invariant_tolerance=biological_tolerance,
    )
    return HarmonizeObservationsRequest(
        context=_context(configuration_digest(profile, policy, protected)),
        profile=profile,
        policy=policy,
        observations=observations,
        biological_invariants=protected,
    )


def _invariant_violation_request() -> HarmonizeObservationsRequest:
    values = list(_base_observations())
    values = [
        item.model_copy(
            update={
                "group_id": (
                    "group.low"
                    if item.sample_id.endswith(("rr", "rs"))
                    else "group.high"
                )
            }
        )
        if item.feature_id == "biology.direction"
        else item
        for item in values
    ]
    return _request(tuple(values))


def build_scenario_request(request_case: str) -> HarmonizeObservationsRequest:
    """Build one deterministic synthetic request for eval reuse."""

    if request_case in {"supported", "consent_denied"}:
        return _request(_base_observations())
    if request_case == "missing_censored":
        return _request(_base_observations(add_absent=True))
    if request_case == "insufficient_controls":
        return _request(_base_observations(), minimum=5)
    if request_case == "capped_shift":
        return _request(_base_observations(), cap=1.0)
    if request_case == "invariant_violation":
        return _invariant_violation_request()
    raise ValueError(request_case)


def _reordered(request: HarmonizeObservationsRequest) -> HarmonizeObservationsRequest:
    profile = request.profile.model_copy(
        update={
            "stages": tuple(
                stage.model_copy(
                    update={
                        "control_sample_ids": tuple(reversed(stage.control_sample_ids)),
                        "control_feature_ids": tuple(reversed(stage.control_feature_ids)),
                    }
                )
                for stage in request.profile.stages
            )
        }
    )
    return request.model_copy(
        update={
            "profile": profile,
            "observations": tuple(
                item.model_copy(update={"factor_levels": tuple(reversed(item.factor_levels))})
                for item in reversed(request.observations)
            ),
            "biological_invariants": tuple(reversed(request.biological_invariants)),
        }
    )


def _retained(result: HarmonizationResult, kind: InvariantKind) -> bool:
    matching = [
        item for item in result.biological_invariant_diagnostics if item.kind is kind
    ]
    return bool(matching) and all(
        item.status is DiagnosticStatus.PASSED
        and item.before_score is not None
        and item.after_score is not None
        and math.isclose(item.before_score, item.after_score, abs_tol=item.tolerance)
        for item in matching
    )


def _reason_matches(result: HarmonizationResult, reason: str | None) -> bool:
    if reason is None:
        return True
    if reason == "insufficient_controls":
        return any(
            shift.state is ShiftState.NOT_EVALUABLE
            for stage in result.transformation_manifest.stages
            for shift in stage.level_shifts
        )
    if reason == "shift_capped":
        return any(
            shift.state is ShiftState.CAPPED
            for stage in result.transformation_manifest.stages
            for shift in stage.level_shifts
        ) and any(item.capped for item in result.technical_effect_diagnostics)
    if reason == "invariant_violation":
        return any(
            item.status is DiagnosticStatus.FAILED
            for item in result.biological_invariant_diagnostics
        )
    return False


def _result_check(scenario: Scenario) -> tuple[EvalCheck, dict[str, object]]:
    expected = scenario["expected"]
    request = build_scenario_request(scenario["request_case"])
    result = harmonize_observations(request)
    replay = harmonize_observations(_reordered(request))
    reduced = all(
        item.before_spread is not None
        and item.after_spread is not None
        and item.after_spread < item.before_spread
        for item in result.technical_effect_diagnostics
    )
    missing = sum(item.state is ObservationState.MISSING for item in result.values)
    censored = sum(
        item.state is ObservationState.BELOW_DETECTION_LIMIT for item in result.values
    )
    passed = (
        result == replay
        and result.disposition.value == expected["disposition"]
        and result.support.status.value == expected["support"]
        and (
            "technical_spread_reduced" not in expected
            or reduced is expected["technical_spread_reduced"]
        )
        and (
            "protected_direction_retained" not in expected
            or _retained(result, InvariantKind.DIRECTION)
            is expected["protected_direction_retained"]
        )
        and (
            "protected_rank_retained" not in expected
            or _retained(result, InvariantKind.RANK)
            is expected["protected_rank_retained"]
        )
        and missing == expected.get("missing_count", missing)
        and censored == expected.get("censored_count", censored)
        and _reason_matches(result, expected.get("reason"))
    )
    detail = (
        f"disposition={result.disposition.value};values={len(result.values)};"
        f"reduced={reduced};direction={_retained(result, InvariantKind.DIRECTION)};"
        f"rank={_retained(result, InvariantKind.RANK)};missing={missing};"
        f"censored={censored};order_equal={result == replay}"
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
        "generic_omics_fusion",
        "kinase_activity",
        "proteotype",
        "raw_payload",
        "raw_spectra",
        "treatment_recommendation",
        "upstream_mutations",
    }
    leaked = sorted(_all_keys(results).intersection(forbidden))
    return EvalCheck(
        "boundary.harmonization_output_only",
        not leaked,
        "closed harmonization output" if not leaked else f"forbidden={','.join(leaked)}",
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _checks(corpus: Corpus) -> tuple[list[EvalCheck], list[dict[str, object]]]:
    checks: list[EvalCheck] = []
    results: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        if scenario["expected"]["outcome"] == "validation_rejected":
            rejected = _consent_rejected()
            checks.append(
                EvalCheck(
                    f"scenario.{scenario['case_id']}",
                    rejected,
                    "strict request validation rejected consent" if rejected else "not rejected",
                )
            )
        else:
            check, serialized = _result_check(scenario)
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
        and corpus["claims_ceiling"]
        == "deterministic_fixture_regression_not_cohort_validation"
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
