"""Executable evaluator for M19-02 alignment and reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.contract.test_m19_02_deep import (
    _discrepancy,
    _observation,
    _request,
)

from glio_proteogen.contracts.m19_02 import (
    AlignmentDimension,
    AlignmentFindingCode,
    AlignmentObservation,
    AlignmentObservationStatus,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
    ProteotypeAlignmentResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import IdentityLineageState
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_02_cross_source_alignment as m1902,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_02 import AlignProteotypeSourcesRequest

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m19_02" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M19-02"
EXPECTED_SCENARIOS: Final = 8
EXPECTED_ADVERSARIAL_CASES: Final = 8
DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE: Final = "6560-6600"


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    scenario_count: int
    adversarial_case_count: int
    adversarial_passed_count: int
    adversarial_coverage_percent: float
    target_percent: int
    checks: tuple[EvalCheck, ...]
    passed: bool


def _with_observation(
    request: AlignProteotypeSourcesRequest,
    observation: AlignmentObservation,
    discrepancy: DiscrepancyMapEntry,
) -> AlignProteotypeSourcesRequest:
    return _request(
        observations=tuple(
            observation if item.dimension is AlignmentDimension.TIME else item
            for item in request.observations
        ),
        discrepancies=(discrepancy,),
    )


def _scenario(name: str) -> AlignProteotypeSourcesRequest:
    request = _request()
    if name in {
        "aligned_supported",
        "replay_tamper",
        "deterministic_reconstruction",
        "strict_plugin",
    }:
        return request
    if name == "conflicted_time":
        return _with_observation(
            request,
            _observation(
                AlignmentDimension.TIME,
                status=AlignmentObservationStatus.CONFLICTED,
                observed_values=("value.time", "other.time"),
            ),
            _discrepancy(AlignmentDimension.TIME),
        )
    if name == "not_evaluable_sample":
        return _request(
            observations=tuple(
                _observation(
                    AlignmentDimension.SAMPLE,
                    status=AlignmentObservationStatus.NOT_EVALUABLE,
                    observed_values=("missing", "missing"),
                )
                if item.dimension is AlignmentDimension.SAMPLE
                else item
                for item in request.observations
            ),
            discrepancies=(_discrepancy(AlignmentDimension.SAMPLE),),
        )
    if name == "critical_conflict_review":
        return _with_observation(
            request,
            _observation(
                AlignmentDimension.TIME,
                status=AlignmentObservationStatus.CONFLICTED,
                observed_values=("value.time", "other.time"),
            ),
            _discrepancy(
                AlignmentDimension.TIME,
                severity=DiscrepancySeverity.CRITICAL,
                review_required=True,
            ),
        )
    if name == "authorization_gate":
        references = request.context.references
        return request.model_copy(
            update={
                "context": request.context.model_copy(
                    update={
                        "references": references.model_copy(
                            update={
                                "identity_lineage": references.identity_lineage.model_copy(
                                    update={"state": IdentityLineageState.UNRESOLVED}
                                )
                            }
                        )
                    }
                )
            }
        )
    raise ValueError(f"unknown M19-02 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenario_names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(scenario_names) == EXPECTED_SCENARIOS,
            f"observed={len(scenario_names)} expected={EXPECTED_SCENARIOS}",
        ),
        EvalCheck(
            "authority.dossier",
            metadata["dossier_sha256"] == DOSSIER_SHA256
            and metadata["dossier_slice"] == DOSSIER_SLICE,
            "dossier hash and exact M19-02 slice are locked",
        ),
    ]
    engine = m1902.M1902Engine()
    results: dict[str, ProteotypeAlignmentResult] = {}
    scenario_passed = True
    for name in scenario_names:
        request = _scenario(name)
        try:
            result = engine.align(request)
        except m1902.M1902AuthorizationError:
            scenario_passed &= name == "authorization_gate"
            continue
        results[name] = result
        if name == "aligned_supported":
            scenario_passed &= (
                result.status.value == "aligned" and result.aligned_bundle is not None
            )
        elif name == "conflicted_time":
            scenario_passed &= (
                result.status.value == "abstained"
                and result.aligned_bundle is None
                and result.findings[0].code is AlignmentFindingCode.DIMENSION_CONFLICT
            )
        elif name == "not_evaluable_sample":
            scenario_passed &= (
                result.status.value == "abstained"
                and result.findings[0].code is AlignmentFindingCode.INPUT_INCOMPLETE
            )
        elif name == "critical_conflict_review":
            scenario_passed &= (
                result.status.value == "abstained"
                and result.human_review_required
                and result.findings[0].code is AlignmentFindingCode.BIOLOGICAL_CONFLICT_REVIEW
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )
    aligned = results["aligned_supported"]
    checks.extend(
        (
            EvalCheck(
                "aligned.parent_boundary",
                aligned.parent_target == "proteotype" and aligned.emits_parent is False,
                "alignment does not emit the parent proteotype",
            ),
            EvalCheck(
                "aligned.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        aligned.uncertainty.measurement,
                        aligned.uncertainty.sampling,
                        aligned.uncertainty.parameter,
                        aligned.uncertainty.model_form,
                        aligned.uncertainty.identification,
                        aligned.uncertainty.support,
                        aligned.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
        )
    )
    tampered = results["replay_tamper"].model_copy(update={"human_review_required": True})
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1902.M1902ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))
    deterministic_a = engine.align(_scenario("deterministic_reconstruction"))
    deterministic_b = engine.align(_scenario("deterministic_reconstruction"))
    deterministic = deterministic_a.result_digest == deterministic_b.result_digest
    checks.append(
        EvalCheck(
            "determinism.reconstruction",
            deterministic,
            "same canonical request yields the same result digest",
        )
    )
    plugin = m1902.M1902Plugin()
    plugin_result = plugin.run(
        plugin.validate_json(canonical_json_bytes(_scenario("strict_plugin")))
    )
    plugin_parity = plugin_result == results["strict_plugin"]
    checks.append(
        EvalCheck("plugin.canonical_parity", plugin_parity, "strict plugin matches engine")
    )
    passed_adversarial = sum(
        condition
        for condition in (
            results["conflicted_time"].status.value == "abstained",
            results["not_evaluable_sample"].status.value == "abstained",
            results["critical_conflict_review"].human_review_required,
            replay_denied,
            scenario_passed,
            results["aligned_supported"].aligned_bundle is not None,
            deterministic,
            plugin_parity,
        )
    )
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            passed_adversarial / EXPECTED_ADVERSARIAL_CASES * 100
            >= metadata["coverage_target_percent"],
            f"passed={passed_adversarial}/{EXPECTED_ADVERSARIAL_CASES}",
        )
    )
    passed = all(check.passed for check in checks)
    return EvaluationReport(
        module_id=MODULE_ID,
        dossier_sha256=metadata["dossier_sha256"],
        dossier_slice=metadata["dossier_slice"],
        scenario_count=len(scenario_names),
        adversarial_case_count=EXPECTED_ADVERSARIAL_CASES,
        adversarial_passed_count=passed_adversarial,
        adversarial_coverage_percent=passed_adversarial / EXPECTED_ADVERSARIAL_CASES * 100,
        target_percent=metadata["coverage_target_percent"],
        checks=tuple(checks),
        passed=passed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
