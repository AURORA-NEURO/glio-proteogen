"""Executable evaluator for M19-01 typed upstream resolution."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from tests.contract.test_m19_01_deep import _candidate, _request

from glio_proteogen.contracts.m19_01 import (
    CompatibilityStatus,
    ResolverFindingCode,
    result_payload_digest,
)
from glio_proteogen.kernel.models import IdentityLineageState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_01_upstream_contract_resolver as m1901,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_01 import ResolveProteotypeUpstreamContractsRequest

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m19_01" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M19-01"
EXPECTED_SCENARIOS: Final = 9
EXPECTED_ADVERSARIAL_CASES: Final = 10
DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE: Final = "6516-6556"


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


def _scenario(name: str) -> ResolveProteotypeUpstreamContractsRequest:  # noqa: PLR0911
    accepted = _candidate("candidate.accepted")
    if name in {"validated_compatible", "replay_tamper", "deterministic_reconstruction"}:
        return _request((accepted,))
    if name == "mixed_review":
        return _request(
            (
                accepted,
                _candidate("candidate.rejected", compatibility=CompatibilityStatus.INCOMPATIBLE),
                _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),
            )
        )
    if name == "unknown_abstention":
        return _request(
            (_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),)
        )
    if name == "incompatible_abstention":
        return _request(
            (_candidate("candidate.incompatible", compatibility=CompatibilityStatus.INCOMPATIBLE),)
        )
    if name == "media_mismatch":
        candidate = accepted.model_copy(
            update={
                "candidate_id": "candidate.media",
                "artifact": accepted.artifact.model_copy(
                    update={"media_type": "application/octet-stream"}
                ),
            }
        )
        return _request((candidate,))
    if name == "version_mismatch":
        request = _request((accepted,))
        configuration = request.configuration.model_copy(
            update={
                "rules": (
                    request.configuration.rules[0].model_copy(update={"required_version": "2.0.0"}),
                )
            }
        )
        return request.model_copy(update={"configuration": configuration})
    if name == "identity_gate":
        request = _request((accepted,))
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
    raise ValueError(f"unknown M19-01 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenario_names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(scenario_names) == EXPECTED_SCENARIOS,
            f"observed={len(scenario_names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    engine = m1901.M1901Engine()
    scenario_passed = True
    results = {}
    for name in scenario_names:
        try:
            result = engine.resolve(_scenario(name))
        except m1901.M1901AuthorizationError:
            scenario_passed &= name == "identity_gate"
            continue
        results[name] = result
        if name == "validated_compatible":
            scenario_passed &= result.status.value == "validated" and result.bundle is not None
        elif name == "mixed_review":
            scenario_passed &= (
                result.compatibility_report.selected_candidate_ids == ("candidate.accepted",)
                and result.compatibility_report.rejected_candidate_ids == ("candidate.rejected",)
                and result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
                and result.human_review_required
                and result.status.value == "abstained"
            )
        elif name in {"unknown_abstention", "incompatible_abstention", "media_mismatch"}:
            scenario_passed &= (
                result.status.value == "abstained"
                and result.bundle is None
                and result.support_decision.status is SupportStatus.REVIEW_REQUIRED
            )
        elif name == "version_mismatch":
            scenario_passed &= (
                result.status.value == "abstained"
                and result.findings[0].code is ResolverFindingCode.INCOMPATIBLE_VERSION
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )
    mixed = results["mixed_review"]
    descriptor = m1901.M1901Plugin().descriptor
    checks.extend(
        (
            EvalCheck(
                "mixed.parent_boundary",
                mixed.parent_target == "proteotype" and mixed.emits_parent is False,
                "resolver does not emit the parent proteotype",
            ),
            EvalCheck(
                "mixed.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        mixed.uncertainty.measurement,
                        mixed.uncertainty.sampling,
                        mixed.uncertainty.parameter,
                        mixed.uncertainty.model_form,
                        mixed.uncertainty.identification,
                        mixed.uncertainty.support,
                        mixed.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
            EvalCheck(
                "authority.module_identity",
                descriptor.module_id == MODULE_ID
                and metadata["dossier_sha256"] == DOSSIER_SHA256
                and metadata["dossier_slice"] == DOSSIER_SLICE,
                "evaluator is bound to the permitted dossier authority slice",
            ),
            EvalCheck(
                "descriptor.boundaries",
                (
                    descriptor.parent_target == "proteotype"
                    and descriptor.owner == "Bioinformatics"
                    and descriptor.safety_class == "S2"
                    and descriptor.gate == "G0"
                    and descriptor.external_content_traversal is False
                    and descriptor.identity_inference is False
                    and descriptor.all_omics_fusion is False
                    and descriptor.kinase_activity is False
                    and descriptor.treatment_recommendation is False
                    and descriptor.unsupported_to_negative is False
                ),
                "plugin descriptor preserves scope and safety boundaries",
            ),
        )
    )
    tampered = results["replay_tamper"].model_copy(update={"human_review_required": True})
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1901.M1901ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))
    forged_payload = results["replay_tamper"].model_copy(update={"human_review_required": True})
    forged = forged_payload.model_copy(
        update={"result_digest": result_payload_digest(forged_payload)}
    )
    reconstruction_denied = False
    try:
        engine.replay(forged)
    except m1901.M1901ReplayError:
        reconstruction_denied = True
    checks.append(
        EvalCheck(
            "replay.reconstruction_denied",
            reconstruction_denied,
            "a forged payload cannot pass by recomputing its digest",
        )
    )
    deterministic_a = engine.resolve(_scenario("deterministic_reconstruction"))
    deterministic_b = engine.resolve(_scenario("deterministic_reconstruction"))
    deterministic = deterministic_a.result_digest == deterministic_b.result_digest
    checks.append(
        EvalCheck(
            "determinism.reconstruction",
            deterministic,
            "same canonical request yields the same result digest",
        )
    )
    passed_adversarial = sum(
        (
            int(results["unknown_abstention"].status.value == "abstained"),
            int(results["incompatible_abstention"].status.value == "abstained"),
            int(results["media_mismatch"].status.value == "abstained"),
            int(
                results["version_mismatch"].findings[0].code
                is ResolverFindingCode.INCOMPATIBLE_VERSION
            ),
            int(replay_denied),
            int(reconstruction_denied),
            int(scenario_passed),
            int(mixed.human_review_required),
            int(results["validated_compatible"].bundle is not None),
            int(deterministic),
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
