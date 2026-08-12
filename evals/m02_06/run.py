"""Replay the locked M02-06 synthetic identification-harmonization corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, TypedDict, cast

from evals.m02_01.run import build_scenario_request as build_m0201_request
from evals.m02_02.run import build_scenario_request as build_m0202_request
from evals.m02_03.run import build_scenario_submission as build_m0203_submission
from evals.m02_04.run import build_scenario_request as build_m0204_request
from evals.m02_05.run import build_scenario_request as build_m0205_request
from glio_proteogen.contracts.m02_05 import ArtifactClass
from glio_proteogen.contracts.m02_06 import (
    BiologicalControlInvariant,
    BiologicalInvariantKind,
    HarmonizationValueState,
    HarmonizeIdentificationEvidenceRequest,
    IdentificationAbundanceObservation,
    IdentificationFactorLevel,
    IdentificationHarmonizationPolicy,
    IdentificationHarmonizationPrerequisites,
    IdentificationHarmonizationProfile,
    IdentificationHarmonizationResult,
    IdentificationNormalizationStage,
    IdentificationTechnicalFactor,
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
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    evaluate_identity_bindings,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    evaluate_identification_raw_ingestion,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    compute_identification_quality,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    detect_identification_artifacts,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    IdentificationHarmonizationAuthorizationError,
    harmonize_identification_evidence,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-06"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_06" / "scenarios.json"
EXPECTED_SCENARIO_IDS: Final = (
    "eight_factor_reduction_with_protected_biology",
    "typed_nonobserved_state_fidelity",
    "m0205_exclusion_firewall",
    "insufficient_controls_abstain",
    "capped_shift_requires_review",
    "direction_control_violation",
    "rank_control_violation",
    "unacceptable_prerequisite_abstention",
    "full_output_semantic_order_equality",
    "consent_denied_before_hostile_observations",
)
EXPECTED_FACTOR_VALUES: Final = (
    "platform",
    "batch",
    "laboratory",
    "build",
    "depth",
    "purity",
    "composition",
    "preanalytic",
)
_FACTOR_MASKS: Final = (1, 2, 4, 8, 16, 32, 3, 5)
_TECHNICAL_OFFSETS: Final = (0.125, 0.16, 0.195, 0.23, 0.265, 0.30, 0.335, 0.37)
_BASELINE_GROUP_MASK: Final = 21
_DIRECTION_VIOLATION_GROUP_MASK: Final = 2
_RANK_VIOLATION_GROUP_MASK: Final = 5
_CONTROL_FEATURES: Final = ("feature.control.alpha", "feature.control.beta")
_BASE_TARGETS: Final = tuple(f"sample.{index:03d}" for index in range(64))
_EXCLUDED_TARGET: Final = "target.multi"
_UNIT: Final = "log2_abundance"
_INSUFFICIENT_STAGE_ORDINAL: Final = 2
_EXPECTED_DIRECTION_SCORE: Final = 0.75
_EXPECTED_RANK_SCORE: Final = 2.0


class StatusCounts(TypedDict):
    passed: int
    failed: int
    not_evaluable: int


class Criteria(TypedDict):
    technical_factor_count: int
    technical_spread_must_strictly_reduce: bool
    technical_after_spread_maximum: float
    protected_direction_count: int
    protected_rank_count: int
    state_fidelity_required: bool
    excluded_adjustment_count: int


class Scenario(TypedDict, total=False):
    id: str
    mutation: str
    expected_disposition: str
    expected_technical_statuses: StatusCounts
    expected_biological_statuses: StatusCounts
    expected_states: dict[str, int]
    expected_excluded_target_ids: list[str]
    expected_capped_shift_count_minimum: int
    expected_failed_invariant_kind: str
    expected_full_output_equal: bool


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


class _UnreadableObservations(Mapping[str, object]):
    """Hostile boundary object used to prove authorization ordering."""

    _MESSAGE = "observations were traversed before authorization"

    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0206.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0206": label}),
        media_type="application/json",
    )


@lru_cache(maxsize=4)
def _prerequisites(
    *,
    unacceptable: bool,
    excluded_target: bool,
) -> IdentificationHarmonizationPrerequisites:
    """Execute the five public upstream modules; never synthesize a receipt shell."""

    conformance = evaluate_conformance(
        build_m0201_request("missing_mandatory" if unacceptable else "canonical")
    )
    identity = evaluate_identity_bindings(build_m0202_request("canonical"))
    ingestion_submission = build_m0203_submission("none")
    ingestion = evaluate_identification_raw_ingestion(
        ingestion_submission.request,
        ingestion_submission.sources,
        ingestion_submission.filenames,
    )
    quality = compute_identification_quality(build_m0204_request("none"))
    seed = build_m0205_request("multi_class" if excluded_target else "clean_single")
    signals = tuple(
        template.model_copy(
            update={
                "target_id": target_id,
                "evidence": (
                    _artifact(f"m0205-signal.{target_id}.{template.signal_id}"),
                ),
            }
        )
        for target_id in (
            (*_BASE_TARGETS, _EXCLUDED_TARGET) if excluded_target else _BASE_TARGETS
        )
        for template in seed.signals[: len(ArtifactClass)]
    )
    if excluded_target:
        seeded_pairs = {
            (_EXCLUDED_TARGET, ArtifactClass.CONTAMINATION.value),
            (_EXCLUDED_TARGET, ArtifactClass.BARCODE_INDEX.value),
        }
        signals = tuple(
            item.model_copy(update={"value": 0.95})
            if (
                item.target_id,
                item.signal_id.removeprefix("signal.m0205."),
            )
            in seeded_pairs
            else item.model_copy(update={"value": 0.1})
            for item in signals
        )
    artifact_detection = detect_identification_artifacts(
        seed.model_copy(update={"signals": signals})
    )
    return IdentificationHarmonizationPrerequisites(
        conformance=conformance,
        identity=identity,
        ingestion=ingestion,
        quality=quality,
        artifact_detection=artifact_detection,
    )


def _context(
    configuration: str,
    identity_digest: str,
    mutation: str,
) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0206.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{role}", digest),
        )

    return ExecutionContext(
        request_id=f"request.synthetic.m0206.{mutation.replace('_', '.')}",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 22, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0206.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity_digest,
                evidence=_artifact("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0206.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _technical_levels(target_index: int) -> tuple[IdentificationFactorLevel, ...]:
    return tuple(
        IdentificationFactorLevel(
            factor=IdentificationTechnicalFactor(factor_value),
            level_id=(
                f"level.m0206.{factor_value}.comparison"
                if (target_index & mask).bit_count() % 2
                else f"level.m0206.{factor_value}.reference"
            ),
        )
        for factor_value, mask in zip(EXPECTED_FACTOR_VALUES, _FACTOR_MASKS, strict=True)
    )


def _group_id(target_index: int, feature_index: int, mutation: str) -> str:
    mask = (
        _DIRECTION_VIOLATION_GROUP_MASK
        if mutation == "direction_violation"
        else _RANK_VIOLATION_GROUP_MASK
        if mutation == "rank_violation" and feature_index == 1
        else _BASELINE_GROUP_MASK
    )
    return (
        "group.case"
        if (target_index & mask).bit_count() % 2
        else "group.baseline"
    )


def _observed_value(target_index: int, feature_index: int, mutation: str) -> float:
    biological_group = (target_index & _BASELINE_GROUP_MASK).bit_count() % 2
    technical = sum(
        offset
        for mask, offset in zip(_FACTOR_MASKS, _TECHNICAL_OFFSETS, strict=True)
        if (target_index & mask).bit_count() % 2
    )
    # Factor 6 is independent of the protected group partition; stress therefore changes the
    # technical level median without manufacturing a biological-control failure.
    capped_stress = (
        1.25
        if mutation == "capped_shift" and target_index & _FACTOR_MASKS[5]
        else 0.0
    )
    return 10.0 + (2.0 * feature_index) + (0.75 * biological_group) + technical + capped_stress


def _observations(mutation: str) -> tuple[IdentificationAbundanceObservation, ...]:
    observations: list[IdentificationAbundanceObservation] = []
    typed_states = {
        (0, 0): HarmonizationValueState.MISSING,
        (0, 1): HarmonizationValueState.CENSORED,
        (1, 0): HarmonizationValueState.NOT_APPLICABLE,
        (1, 1): HarmonizationValueState.UNSUPPORTED,
    }
    for target_index, target_id in enumerate(_BASE_TARGETS):
        levels = _technical_levels(target_index)
        for feature_index, feature_id in enumerate(_CONTROL_FEATURES):
            state = (
                typed_states.get((target_index, feature_index), HarmonizationValueState.OBSERVED)
                if mutation == "typed_nonobserved_states"
                else HarmonizationValueState.OBSERVED
            )
            observations.append(
                IdentificationAbundanceObservation(
                    target_id=target_id,
                    feature_id=feature_id,
                    biological_group_id=_group_id(target_index, feature_index, mutation),
                    state=state,
                    value=(
                        _observed_value(target_index, feature_index, mutation)
                        if state is HarmonizationValueState.OBSERVED
                        else None
                    ),
                    censoring_limit=(
                        5.5 if state is HarmonizationValueState.CENSORED else None
                    ),
                    unit=_UNIT,
                    factor_levels=levels,
                    evidence=(_artifact(f"observation.{target_id}.{feature_id}"),),
                )
            )
    if mutation == "upstream_excluded_target":
        levels = _technical_levels(63)
        observations.extend(
            IdentificationAbundanceObservation(
                target_id=_EXCLUDED_TARGET,
                feature_id=f"feature.excluded.{index:02d}",
                biological_group_id="group.baseline",
                state=HarmonizationValueState.OBSERVED,
                value=7.0 + index,
                unit=_UNIT,
                factor_levels=levels,
                evidence=(_artifact(f"observation.excluded.{index:02d}"),),
            )
            for index in range(8)
        )
    return tuple(observations)


def _profile(mutation: str) -> IdentificationHarmonizationProfile:
    stages: list[IdentificationNormalizationStage] = []
    for ordinal, factor_value in enumerate(EXPECTED_FACTOR_VALUES, start=1):
        controls = _BASE_TARGETS
        if mutation == "insufficient_controls" and ordinal == _INSUFFICIENT_STAGE_ORDINAL:
            # Both declared controls are comparison-level samples; the reference cannot train.
            controls = (_BASE_TARGETS[2], _BASE_TARGETS[3])
        stages.append(
            IdentificationNormalizationStage(
                stage_id=f"stage.m0206.{factor_value}",
                ordinal=ordinal,
                factor=IdentificationTechnicalFactor(factor_value),
                reference_level_id=f"level.m0206.{factor_value}.reference",
                control_target_ids=controls,
                control_feature_ids=_CONTROL_FEATURES,
            )
        )
    return IdentificationHarmonizationProfile(
        profile_id="profile.m0206.identification-harmonization-v1",
        version="1.0.0",
        stages=tuple(stages),
        evidence=_artifact("harmonization-profile"),
    )


def _policy() -> IdentificationHarmonizationPolicy:
    return IdentificationHarmonizationPolicy(
        policy_id="policy.m0206.identification-harmonization-v1",
        version="1.0.0",
        max_absolute_shift=1.0,
        min_controls_per_level=4,
        technical_effect_tolerance=0.000001,
        biological_invariant_tolerance=0.000001,
    )


def _biological_controls() -> tuple[BiologicalControlInvariant, ...]:
    return (
        BiologicalControlInvariant(
            invariant_id="invariant.m0206.protected-direction",
            kind=BiologicalInvariantKind.DIRECTION,
            feature_ids=(_CONTROL_FEATURES[0],),
            biological_group_ids=("group.baseline", "group.case"),
        ),
        BiologicalControlInvariant(
            invariant_id="invariant.m0206.protected-rank",
            kind=BiologicalInvariantKind.RANK,
            feature_ids=_CONTROL_FEATURES,
            biological_group_ids=("group.baseline",),
        ),
    )


def build_scenario_request(
    mutation: str = "conformant_eight_factor",
) -> HarmonizeIdentificationEvidenceRequest:
    """Build one deterministic scenario using genuine M02-01 through M02-05 results."""

    allowed = {
        "conformant_eight_factor",
        "typed_nonobserved_states",
        "upstream_excluded_target",
        "insufficient_controls",
        "capped_shift",
        "direction_violation",
        "rank_violation",
        "unacceptable_prerequisite",
        "semantic_reordering",
        "withheld_consent_hostile_observations",
    }
    if mutation not in allowed:
        raise ValueError(mutation)
    prerequisites = _prerequisites(
        unacceptable=mutation == "unacceptable_prerequisite",
        excluded_target=mutation == "upstream_excluded_target",
    )
    profile = _profile(mutation)
    policy = _policy()
    controls = _biological_controls()
    return HarmonizeIdentificationEvidenceRequest(
        context=_context(
            configuration_digest(profile, policy, controls),
            prerequisites.identity.result_digest,
            mutation,
        ),
        prerequisites=prerequisites,
        profile=profile,
        policy=policy,
        observations=_observations(mutation),
        biological_controls=controls,
    )


def build_representative_request() -> HarmonizeIdentificationEvidenceRequest:
    """Build the locked 128-observation request used by the public benchmark."""

    return build_scenario_request("conformant_eight_factor")


def _status_counts(values: object) -> StatusCounts:
    statuses = [str(item.status.value) for item in cast("tuple[Any, ...]", values)]
    return {
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed"),
        "not_evaluable": statuses.count("not_evaluable"),
    }


def _state_counts(result: IdentificationHarmonizationResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in result.values:
        value = item.output_state.value
        counts[value] = counts.get(value, 0) + 1
    return counts


def _semantic_reordering(
    request: HarmonizeIdentificationEvidenceRequest,
) -> HarmonizeIdentificationEvidenceRequest:
    return request.model_copy(
        update={
            "observations": tuple(reversed(request.observations)),
            "biological_controls": tuple(reversed(request.biological_controls)),
        }
    )


def _technical_acceptance(
    result: IdentificationHarmonizationResult,
    scenario: Scenario,
    criteria: Criteria,
) -> bool:
    diagnostics = result.technical_effect_diagnostics
    expected = scenario["expected_technical_statuses"]
    if _status_counts(diagnostics) != expected:
        return False
    for diagnostic in diagnostics:
        if diagnostic.status.value != "passed":
            continue
        before = diagnostic.before_spread
        after = diagnostic.after_spread
        if before is None or after is None:
            return False
        if criteria["technical_spread_must_strictly_reduce"] and not after < before:
            return False
        if after > criteria["technical_after_spread_maximum"]:
            return False
    return True


def _biological_acceptance(
    result: IdentificationHarmonizationResult,
    scenario: Scenario,
) -> bool:
    diagnostics = result.biological_invariant_diagnostics
    if _status_counts(diagnostics) != scenario["expected_biological_statuses"]:
        return False
    expected_kind = scenario.get("expected_failed_invariant_kind")
    failed_kinds = {
        item.kind.value for item in diagnostics if item.status.value == "failed"
    }
    return expected_kind is None or failed_kinds == {expected_kind}


def _state_fidelity(
    result: IdentificationHarmonizationResult,
    scenario: Scenario,
) -> bool:
    expected = scenario["expected_states"]
    actual = _state_counts(result)
    if any(actual.get(state, 0) != count for state, count in expected.items()):
        return False
    for value in result.values:
        if value.output_state.value == "observed":
            continue
        if value.harmonized_value is not None or value.applied_adjustments:
            return False
        if (
            value.output_state.value == "censored"
            and value.censoring_limit != value.input_censoring_limit
        ):
            return False
    return True


def _exact_conformant_evidence(result: IdentificationHarmonizationResult) -> bool:
    diagnostics = result.technical_effect_diagnostics
    if len(diagnostics) != len(EXPECTED_FACTOR_VALUES):
        return False
    expected_factors = set(EXPECTED_FACTOR_VALUES)
    if {item.factor.value for item in diagnostics} != expected_factors:
        return False
    for diagnostic in diagnostics:
        stage = next(
            item
            for item in result.transformation_manifest.stages
            if item.stage_id == diagnostic.stage_id
        )
        comparison = next(
            item for item in stage.level_shifts if item.level_id != stage.reference_level_id
        )
        if (
            diagnostic.before_spread is None
            or diagnostic.before_spread <= 0.0
            or diagnostic.after_spread != 0.0
            or comparison.estimated_shift is None
            or comparison.estimated_shift >= 0.0
            or comparison.applied_shift != comparison.estimated_shift
        ):
            return False
    biological = {item.kind.value: item for item in result.biological_invariant_diagnostics}
    return (
        biological["direction"].before_score
        == biological["direction"].after_score
        == _EXPECTED_DIRECTION_SCORE
        and biological["rank"].before_score
        == biological["rank"].after_score
        == _EXPECTED_RANK_SCORE
    )


def _exclusion_firewall(
    result: IdentificationHarmonizationResult,
    scenario: Scenario,
) -> bool:
    expected = set(scenario.get("expected_excluded_target_ids", []))
    if not expected:
        return True
    excluded = [item for item in result.values if item.sample_id in expected]
    if not excluded or any(
        item.output_state.value != "excluded"
        or item.harmonized_value is not None
        or item.applied_adjustments
        for item in excluded
    ):
        return False
    return all(
        not expected.intersection(stage.control_target_ids)
        for stage in result.transformation_manifest.stages
    )


def _capped_shift_count(result: IdentificationHarmonizationResult) -> int:
    return sum(
        shift.state.value == "capped"
        for stage in result.transformation_manifest.stages
        for shift in stage.level_shifts
    )


def _result_check(
    scenario: Scenario,
    criteria: Criteria,
) -> tuple[EvalCheck, IdentificationHarmonizationResult]:
    request = build_scenario_request(scenario["mutation"])
    result = harmonize_identification_evidence(request)
    order_equal = True
    if scenario.get("expected_full_output_equal"):
        replay = harmonize_identification_evidence(_semantic_reordering(request))
        order_equal = result == replay and result.model_dump_json() == replay.model_dump_json()
    capped_minimum = scenario.get("expected_capped_shift_count_minimum", 0)
    passed = (
        result.disposition.value == scenario["expected_disposition"]
        and _technical_acceptance(result, scenario, criteria)
        and _biological_acceptance(result, scenario)
        and _state_fidelity(result, scenario)
        and _exclusion_firewall(result, scenario)
        and _capped_shift_count(result) >= capped_minimum
        and order_equal
        and (
            scenario["mutation"] not in {"conformant_eight_factor", "semantic_reordering"}
            or _exact_conformant_evidence(result)
        )
    )
    return (
        EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=passed,
            detail=(
                f"disposition={result.disposition.value};values={len(result.values)};"
                f"technical={_status_counts(result.technical_effect_diagnostics)};"
                f"biological={_status_counts(result.biological_invariant_diagnostics)};"
                f"capped={_capped_shift_count(result)};order_equal={order_equal}"
            ),
        ),
        result,
    )


def _authorization_check(scenario: Scenario) -> EvalCheck:
    request = build_scenario_request("conformant_eight_factor")
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["observations"] = _UnreadableObservations()
    try:
        harmonize_identification_evidence(payload)
    except AssertionError as error:
        return EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=False,
            detail=str(error),
        )
    except IdentificationHarmonizationAuthorizationError:
        return EvalCheck(
            f"scenario.{scenario['id']}",
            scenario["expected_disposition"] == "boundary_rejected",
            "authorization_denied_before_observation_traversal",
        )
    return EvalCheck(
        name=f"scenario.{scenario['id']}",
        passed=False,
        detail="withheld consent was accepted",
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _boundary_check(results: list[dict[str, object]]) -> EvalCheck:
    forbidden_keys = {
        "kinase_activity",
        "omics_fusion",
        "peptide_rows",
        "protein_subtype_score",
        "proteotype",
        "raw_assay_rows",
        "raw_payload",
        "raw_spectra",
        "scientific_interpretation",
        "treatment_recommendation",
        "upstream_mutations",
    }
    leaked_keys = sorted(_all_keys(results) & forbidden_keys)
    rendered = canonical_json_bytes(results).decode("utf-8")
    leaked_values = [
        value
        for value in ("MPEPTIDE", "SYNTHETIC_PATIENT", "synthetic-spectrum")
        if value in rendered
    ]
    return EvalCheck(
        name="boundary.closed_identification_harmonization_output",
        passed=not leaked_keys and not leaked_values,
        detail=(
            "no raw payload or prohibited scientific/clinical ownership"
            if not leaked_keys and not leaked_values
            else f"keys={','.join(leaked_keys)};values={','.join(leaked_values)}"
        ),
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _corpus_check(corpus: Corpus) -> EvalCheck:
    ids = tuple(item["id"] for item in corpus["scenarios"])
    dispositions = {item["expected_disposition"] for item in corpus["scenarios"]}
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["contract_version"] == "1.0.0"
        and corpus["data_classification"] == "synthetic_nonclinical"
        and corpus["claims_ceiling"] == "deterministic_synthetic_fixture_regression_only"
        and ids == EXPECTED_SCENARIO_IDS
        and corpus["criteria"]["technical_factor_count"] == len(EXPECTED_FACTOR_VALUES)
        and dispositions == {"accepted", "abstained", "quarantined", "boundary_rejected"}
    )
    return EvalCheck(
        "corpus.locked_ten_harmonization_scenarios",
        passed,
        f"scenarios={len(ids)};factors={len(EXPECTED_FACTOR_VALUES)};dispositions={dispositions}",
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
        if scenario["mutation"] == "withheld_consent_hostile_observations":
            checks.append(_authorization_check(scenario))
            continue
        check, result = _result_check(scenario, corpus["criteria"])
        checks.append(check)
        results.append(cast("dict[str, object]", result.model_dump(mode="json")))
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
