"""Replay the locked M01-04 quality-metric matrix and emit JSON evidence."""

from __future__ import annotations

import argparse
import copy
import json
import math
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

from glio_proteogen.contracts.m01_04 import (
    AnalyteLevel,
    AssayProfile,
    AssayType,
    Computation,
    ComputeQualityMetricsRequest,
    MetricCategory,
    MetricDefinition,
    MetricState,
    Observation,
    QualityComputationPolicy,
    QualityProfile,
    policy_digest,
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
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics import (
    compute_quality_profile,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-04"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_04" / "scenarios.json"
_REQUEST_ADAPTER: Final = TypeAdapter(ComputeQualityMetricsRequest)
EXPECTED_SCENARIO_COUNT: Final = 7


class ExpectedResult(TypedDict):
    outcome: Literal["profile", "validation_rejected"]
    disposition: str | None
    support: str | None
    metrics: list[list[object]]


class Scenario(TypedDict):
    case_id: str
    request_case: str
    expected: ExpectedResult


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
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
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/json",
    )


def _policy(*, require_complete: bool = True) -> QualityComputationPolicy:
    return QualityComputationPolicy(
        policy_id="policy.synthetic.quality",
        version="1.0.0",
        enabled_categories=tuple(MetricCategory),
        require_complete_profile=require_complete,
        quarantine_on_warning=False,
    )


def _context(policy: QualityComputationPolicy) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0104",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", policy_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"fixture": "identity-binding"}),
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


def _observation(
    identifier: str,
    *,
    value: float | bool | None,
    state: MetricState = MetricState.OBSERVED,
    unit: str | None = "%",
    detection_limit: float | None = None,
) -> Observation:
    return Observation(
        observation_id=identifier,
        state=state,
        value=value,
        unit=unit,
        detection_limit=detection_limit,
        evidence=(_artifact(identifier),),
    )


def _definition(  # noqa: PLR0913 - mirrors the compact public definition.
    identifier: str,
    computation: Computation,
    observations: tuple[str, ...],
    *,
    category: MetricCategory,
    unit: str | None,
    reference: float | bool | None = None,
    pass_minimum: float | None = None,
    pass_maximum: float | None = None,
    warning_minimum: float | None = None,
    warning_maximum: float | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metric_id=identifier,
        version="1.0.0",
        category=category,
        computation=computation,
        unit=unit,
        observation_ids=observations,
        reference_value=reference,
        pass_minimum=pass_minimum,
        pass_maximum=pass_maximum,
        warning_minimum=warning_minimum,
        warning_maximum=warning_maximum,
    )


def _request(
    definitions: tuple[MetricDefinition, ...],
    observations: tuple[Observation, ...],
    *,
    required: tuple[str, ...] | None = None,
    require_complete: bool = True,
) -> ComputeQualityMetricsRequest:
    policy = _policy(require_complete=require_complete)
    return ComputeQualityMetricsRequest(
        context=_context(policy),
        assay_profile=AssayProfile(
            profile_id="assay.synthetic.dia",
            version="1.0.0",
            assay_type=AssayType.DIA,
            analyte_level=AnalyteLevel.PROTEIN,
            required_metric_ids=required or tuple(item.metric_id for item in definitions),
            evidence=_artifact("assay-profile"),
        ),
        policy=policy,
        metric_definitions=definitions,
        observations=observations,
    )


def _complete_request() -> ComputeQualityMetricsRequest:
    definitions = (
        _definition(
            "metric.coverage", Computation.RATIO, ("coverage.hit", "coverage.total"),
            category=MetricCategory.COVERAGE, unit="count", pass_minimum=0.8,
            warning_minimum=0.7,
        ),
        _definition(
            "metric.detection", Computation.DETECTION_MARGIN, ("signal",),
            category=MetricCategory.DETECTION_LIMIT, unit="ng", reference=2.0,
            pass_minimum=3.0, warning_minimum=2.0,
        ),
        _definition(
            "metric.completeness", Computation.RATIO,
            ("complete.hit", "complete.total"), category=MetricCategory.COMPLETENESS,
            unit="count", pass_minimum=0.9, warning_minimum=0.8,
        ),
        _definition(
            "metric.control", Computation.RELATIVE_ERROR, ("control",),
            category=MetricCategory.CONTROL_MATERIAL, unit="ng", reference=10.0,
            pass_maximum=0.1, warning_maximum=0.2,
        ),
        _definition(
            "metric.sample-context", Computation.BOOLEAN_MATCH, ("context",),
            category=MetricCategory.SAMPLE_CONTEXT, unit=None, reference=True,
            pass_minimum=1.0, warning_minimum=1.0,
        ),
    )
    observations = (
        _observation("coverage.hit", value=90.0, unit="count"),
        _observation("coverage.total", value=100.0, unit="count"),
        _observation("signal", value=8.0, unit="ng"),
        _observation("complete.hit", value=95.0, unit="count"),
        _observation("complete.total", value=100.0, unit="count"),
        _observation("control", value=9.5, unit="ng"),
        _observation("context", value=True, unit=None),
    )
    return _request(definitions, observations)


def _optional_missing_request() -> ComputeQualityMetricsRequest:
    definitions = (
        _definition(
            "metric.required", Computation.DIRECT, ("required",),
            category=MetricCategory.ASSAY_QUALITY, unit="%", pass_minimum=0.8,
            warning_minimum=0.7,
        ),
        _definition(
            "metric.optional-missing", Computation.DIRECT, ("missing",),
            category=MetricCategory.COMPLETENESS, unit="%", pass_minimum=0.8,
            warning_minimum=0.7,
        ),
        _definition(
            "metric.below-detection", Computation.DETECTION_MARGIN, ("below",),
            category=MetricCategory.DETECTION_LIMIT, unit="ng", reference=2.0,
            pass_minimum=3.0, warning_minimum=2.0,
        ),
    )
    observations = (
        _observation("required", value=0.9),
        _observation("missing", value=None, state=MetricState.MISSING),
        _observation(
            "below", value=None, state=MetricState.BELOW_DETECTION, unit="ng",
            detection_limit=2.0,
        ),
    )
    return _request(
        definitions,
        observations,
        required=("metric.required",),
        require_complete=False,
    )


def _required_missing_request() -> ComputeQualityMetricsRequest:
    definition = _definition(
        "metric.required", Computation.DIRECT, ("missing",),
        category=MetricCategory.COMPLETENESS, unit="%", pass_minimum=0.8,
        warning_minimum=0.7,
    )
    return _request(
        (definition,),
        (_observation("missing", value=None, state=MetricState.MISSING),),
    )


def _control_failure_request() -> ComputeQualityMetricsRequest:
    definitions = (
        _definition(
            "metric.control-failure", Computation.RELATIVE_ERROR, ("control",),
            category=MetricCategory.CONTROL_MATERIAL, unit="ng", reference=10.0,
            pass_maximum=0.1, warning_maximum=0.2,
        ),
        _definition(
            "metric.detection-failure", Computation.DETECTION_MARGIN, ("signal",),
            category=MetricCategory.DETECTION_LIMIT, unit="ng", reference=2.0,
            pass_minimum=3.0, warning_minimum=2.0,
        ),
    )
    return _request(
        definitions,
        (
            _observation("control", value=6.0, unit="ng"),
            _observation("signal", value=2.0, unit="ng"),
        ),
    )


def _context_mismatch_request() -> ComputeQualityMetricsRequest:
    definition = _definition(
        "metric.sample-context", Computation.BOOLEAN_MATCH, ("context",),
        category=MetricCategory.SAMPLE_CONTEXT, unit=None, reference=True,
        pass_minimum=1.0, warning_minimum=1.0,
    )
    return _request((definition,), (_observation("context", value=False, unit=None),))


_VALID_BUILDERS: Final = {
    "complete": _complete_request,
    "optional_missing": _optional_missing_request,
    "required_missing": _required_missing_request,
    "control_failure": _control_failure_request,
    "context_mismatch": _context_mismatch_request,
}


def build_scenario_request(request_case: str) -> ComputeQualityMetricsRequest:
    """Build a deterministic synthetic request for eval and benchmark reuse."""

    builder = _VALID_BUILDERS.get(request_case)
    if builder is None:
        raise ValueError(request_case)
    return builder()


def _metric_rows(profile: QualityProfile) -> list[list[object]]:
    return [
        [item.metric_id, item.state.value, item.status.value, item.value, item.unit]
        for item in profile.metrics
    ]


def _matches_number(actual: object, expected: object) -> bool:
    if isinstance(actual, float) and isinstance(expected, float):
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    return actual == expected


def _rows_match(actual: list[list[object]], expected: list[list[object]]) -> bool:
    return len(actual) == len(expected) and all(
        len(left) == len(right)
        and all(
            _matches_number(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
        for left, right in zip(actual, expected, strict=True)
    )


def _validation_rejected(case: str) -> bool:
    payload = copy.deepcopy(_complete_request().model_dump(mode="python"))
    if case == "unknown_assay":
        payload["assay_profile"]["assay_type"] = "vendor_x"
    elif case == "consent_denied":
        payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    else:
        return False
    try:
        _REQUEST_ADAPTER.validate_python(payload, strict=True)
    except ValidationError:
        return True
    return False


def _profile_check(scenario: Scenario) -> tuple[EvalCheck, dict[str, object]]:
    request = build_scenario_request(scenario["request_case"])
    profile = compute_quality_profile(request)
    reordered = request.model_copy(
        update={
            "metric_definitions": tuple(reversed(request.metric_definitions)),
            "observations": tuple(reversed(request.observations)),
        }
    )
    replay = compute_quality_profile(reordered)
    expected = scenario["expected"]
    rows = _metric_rows(profile)
    passed = (
        profile == replay
        and profile.disposition.value == expected["disposition"]
        and profile.support.status.value == expected["support"]
        and _rows_match(rows, expected["metrics"])
    )
    return (
        EvalCheck(
            f"scenario.{scenario['case_id']}",
            passed,
            (
                f"disposition={profile.disposition.value};support={profile.support.status.value};"
                f"metrics={len(profile.metrics)};order_equal={profile == replay}"
            ),
        ),
        cast("dict[str, object]", profile.model_dump(mode="json")),
    )


def _scenario_checks(corpus: Corpus) -> tuple[list[EvalCheck], list[dict[str, object]]]:
    checks: list[EvalCheck] = []
    profiles: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        if scenario["expected"]["outcome"] == "validation_rejected":
            rejected = _validation_rejected(scenario["request_case"])
            checks.append(
                EvalCheck(
                    f"scenario.{scenario['case_id']}",
                    rejected,
                    "strict request validation rejected the input" if rejected else "not rejected",
                )
            )
        else:
            check, serialized = _profile_check(scenario)
            checks.append(check)
            profiles.append(serialized)
    return checks, profiles


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _boundary_check(profiles: list[dict[str, object]]) -> EvalCheck:
    forbidden = {
        "kinase_activity",
        "proteotype",
        "raw_assay_rows",
        "treatment_recommendation",
        "omics_fusion",
    }
    leaked = sorted(_all_keys(profiles).intersection(forbidden))
    return EvalCheck(
        "boundary.quality_profile_only",
        not leaked,
        "closed quality output" if not leaked else f"forbidden={','.join(leaked)}",
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
    checks, profiles = _scenario_checks(corpus)
    checks.append(_boundary_check(profiles))
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["data_classification"] == "synthetic_nonclinical"
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
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        args.output.write_text(serialized, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
