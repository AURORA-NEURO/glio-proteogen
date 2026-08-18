"""Release workflow and artifact-integrity policy tests."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest
from tools.verify_release_artifacts import (
    ReleaseArtifactError,
    verify_m0403_evidence,
    verify_m0404_evidence,
    verify_m0405_evidence,
    verify_m0406_evidence,
    verify_m0407_evidence,
    verify_m0501_evidence,
    verify_m0502_evidence,
    verify_m0503_evidence,
    verify_runtime_sbom,
    wheel_identity,
)

from tools import verify_release_artifacts

ROOT = Path(__file__).parents[2]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-evidence.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = ROOT / "pyproject.toml"
SECURITY_POLICY = ROOT / "SECURITY.md"
EVIDENCE_POLICY = ROOT / "docs" / "evidence" / "M01-01.md"
SHA256_HEX_LENGTH = 64
EXPECTED_RUNTIME_COMPONENTS = 2
EXPECTED_MODULE_COUNT = 36
M0407_LOCKED_CHECK_NAMES = (
    "scenario.joint_supported",
    "scenario.outside_assay",
    "scenario.outside_specimen",
    "scenario.outside_disease_class",
    "scenario.outside_quality",
    "scenario.outside_completeness",
    "scenario.outside_platform",
    "scenario.outside_reference",
    "scenario.outside_intended_use",
    "scenario.missing_declared_fact",
    "scenario.unknown_declared_fact",
    "scenario.m0404_unreleasable",
    "scenario.m0406_unreleasable",
    "scenario.platform_extra_member",
    "scenario.reference_extra_member",
    "scenario.cross_envelope_composite",
    "scenario.canonical_order",
    "scenario.semantic_reorder",
    "scenario.consent_denied_hostile_evidence",
    "corpus.locked_inventory",
    "corpus.executable_coverage",
)


def test_m0502_evidence_verifier_requires_exact_corpus_shape_and_budgets(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m05-02-eval.json"
    benchmark = tmp_path / "m05-02-benchmark.json"
    group_counts = {
        "identity_and_lineage": 9,
        "artifact_anomaly_detection": 9,
        "safe_failure_and_support": 9,
        "authorization_firewall": 9,
        "strict_contract": 9,
        "dag_invariants": 9,
        "replay_and_privacy": 8,
        "uncertainty_recovery_interfaces": 8,
    }
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M05-02",
        "contract_version": "1.0.0",
        "declared_groups": 8,
        "group_case_counts": group_counts,
        "declared_cases": 70,
        "executed_cases": 70,
        "passed_cases": 70,
        "failed_cases": [],
        "passed": True,
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M05-02",
        "contract_version": "1.0.0",
        "workload": "maximum_reconciled_five_role_identity_lineage_graph",
        "timed_boundary": "reconcile_ptm_localization_identity_lineage_only",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "physical_entity_kind_count": 7,
        "artifact_role_count": 5,
        "artifact_claim_count": 5,
        "derivation_count": 1,
        "derivation_source_count": 4,
        "finding_count": 0,
        "request_bytes": 53_976,
        "result_bytes": 73_657,
        "request_digest": "sha256:" + ("a" * 64),
        "result_digest": "sha256:" + ("b" * 64),
        "mean_ns": 200_000_000.0,
        "p50_ns": 190_000_000.0,
        "p95_ns": 300_000_000,
        "maximum_ns": 350_000_000,
        "mean_budget_ns": 400_000_000,
        "p95_budget_ns": 750_000_000,
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0502_evidence(evaluation, benchmark)

    evaluation_report["group_case_counts"] = {**group_counts, "strict_contract": 8}
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="group closure"):
        verify_m0502_evidence(evaluation, benchmark)

    evaluation_report["group_case_counts"] = group_counts
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark_report["artifact_claim_count"] = 4
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="artifact_claim_count"):
        verify_m0502_evidence(evaluation, benchmark)

    benchmark_report["artifact_claim_count"] = 5
    benchmark_report["mean_ns"] = 400_000_001
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing budgets"):
        verify_m0502_evidence(evaluation, benchmark)


def test_sdist_excludes_generated_release_and_coverage_outputs() -> None:
    configuration = PYPROJECT.read_text(encoding="utf-8")
    sdist = configuration.split("[tool.hatch.build.targets.sdist]", maxsplit=1)[1].split(
        "[tool.pytest.ini_options]", maxsplit=1
    )[0]

    for generated_path in (
        '"/.coverage*"',
        '"/.tmp-*"',
        '"/dist-*"',
        '"/evidence"',
        '"/glio-proteogen-evidence.tar.gz"',
        '"/release-build-*"',
    ):
        assert generated_path in sdist


def _wheel(tmp_path: Path, *, name: str = "glio-proteogen", version: str = "0.1.0") -> Path:
    wheel = tmp_path / "glio_proteogen-0.1.0-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "glio_proteogen-0.1.0.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n",
        )
    return wheel


def _sbom(
    tmp_path: Path,
    *,
    root_name: str = "glio-proteogen",
    root_version: str = "0.1.0",
    component_names: tuple[str, ...] = ("fastapi", "pydantic"),
    include_root_edge: bool = True,
) -> Path:
    root_reference = "root-component"
    dependencies: list[dict[str, object]] = [
        {"ref": name, "dependsOn": []} for name in component_names
    ]
    if include_root_edge:
        dependencies.append({"ref": root_reference, "dependsOn": list(component_names)})
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "metadata": {
            "component": {
                "bom-ref": root_reference,
                "name": root_name,
                "type": "application",
                "version": root_version,
            }
        },
        "components": [
            {"bom-ref": name, "name": name, "type": "library", "version": "1.0"}
            for name in component_names
        ],
        "dependencies": dependencies,
    }
    path = tmp_path / "runtime-sbom.cdx.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_wheel_identity_comes_from_embedded_metadata(tmp_path: Path) -> None:
    identity = wheel_identity(_wheel(tmp_path))

    assert identity.name == "glio-proteogen"
    assert identity.version == "0.1.0"
    assert identity.filename.endswith(".whl")
    assert len(identity.sha256) == SHA256_HEX_LENGTH


def test_runtime_sbom_is_rooted_at_exact_wheel_and_excludes_dev_tools(
    tmp_path: Path,
) -> None:
    wheel = _wheel(tmp_path)
    summary = verify_runtime_sbom(_sbom(tmp_path), wheel)

    assert summary.root_name == "glio-proteogen"
    assert summary.root_version == "0.1.0"
    assert summary.component_count == EXPECTED_RUNTIME_COMPONENTS

    with pytest.raises(ReleaseArtifactError, match="does not match"):
        verify_runtime_sbom(_sbom(tmp_path, root_version="0.2.0"), wheel)
    with pytest.raises(ReleaseArtifactError, match="development-only"):
        verify_runtime_sbom(_sbom(tmp_path, component_names=("fastapi", "pytest")), wheel)
    with pytest.raises(ReleaseArtifactError, match="one root"):
        verify_runtime_sbom(_sbom(tmp_path, include_root_edge=False), wheel)


def test_m0403_evidence_verifier_requires_exact_corpus_and_budgets(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m04-03-eval.json"
    benchmark = tmp_path / "m04-03-benchmark.json"
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M04-03",
        "passed": True,
        "declared_case_count": 72,
        "executed_case_count": 72,
        "missing_case_ids": [],
        "extra_case_ids": [],
        "duplicated_case_ids": [],
        "checks": [{"name": f"scenario.case_{index}", "passed": True} for index in range(72)],
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M04-03",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "mean_ns": 400_000_000.0,
        "p95_ns": 600_000_000,
        "mean_budget_ns": 500_000_000,
        "p95_budget_ns": 750_000_000,
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0403_evidence(evaluation, benchmark)

    evaluation_report["executed_case_count"] = 71
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="executed_case_count"):
        verify_m0403_evidence(evaluation, benchmark)

    evaluation_report["executed_case_count"] = 72
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark_report["mean_ns"] = 500_000_001
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing budgets"):
        verify_m0403_evidence(evaluation, benchmark)


def test_m0404_evidence_verifier_requires_exact_corpus_shape_and_budgets(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m04-04-eval.json"
    benchmark = tmp_path / "m04-04-benchmark.json"
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M04-04",
        "passed": True,
        "declared_case_count": 72,
        "executed_case_count": 72,
        "missing_case_ids": [],
        "extra_case_ids": [],
        "duplicated_case_ids": [],
        "checks": [{"name": f"scenario.case_{index}", "passed": True} for index in range(72)],
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M04-04",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "role_count": 4,
        "profile_count": 32,
        "threshold_count": 256,
        "fact_count": 4,
        "metric_count": 32,
        "evidence_count": 45,
        "limitation_count": 3,
        "mean_ns": 400_000_000.0,
        "p95_ns": 600_000_000,
        "mean_budget_ns": 500_000_000,
        "p95_budget_ns": 750_000_000,
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0404_evidence(evaluation, benchmark)

    benchmark_report["threshold_count"] = 255
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="threshold_count"):
        verify_m0404_evidence(evaluation, benchmark)

    benchmark_report["threshold_count"] = 256
    benchmark_report["p95_ns"] = 750_000_001
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing budgets"):
        verify_m0404_evidence(evaluation, benchmark)


def test_m0405_evidence_verifier_locks_narrowed_support_and_maximum_shape(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m04-05-eval.json"
    benchmark = tmp_path / "m04-05-benchmark.json"
    checks = [{"name": f"scenario.case_{index}", "passed": True} for index in range(15)] + [
        {"name": f"replay.case_{index}", "passed": True} for index in range(15)
    ]
    checks.append({"name": "acceptance.non_calibrated_narrow_or_abstain", "passed": True})
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M04-05",
        "operation": "detect_proteoform_artifacts",
        "passed": True,
        "declared_case_count": 15,
        "executed_case_count": 15,
        "missing_case_ids": [],
        "extra_case_ids": [],
        "duplicated_case_ids": [],
        "seeded_sensitivity_ppm": 1_000_000,
        "false_exclusion_ppm": 0,
        "nominal_coverage_ppm": None,
        "coverage_disposition": ("non_calibrated_scores_with_typed_narrowing_or_abstention"),
        "checks": checks,
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M04-05",
        "contract_version": "1.0.0",
        "workload": "genuine M04-04 result plus the exact installed maximum aggregate ledger",
        "timed_boundary": "detect_proteoform_artifacts only",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "target_count": 64,
        "event_count": 448,
        "posterior_count": 448,
        "mean_ns": 1_500_000_000.0,
        "p50_ns": 1_400_000_000.0,
        "p95_ns": 2_500_000_000,
        "maximum_ns": 2_750_000_000,
        "mean_budget_ns": 2_000_000_000,
        "p95_budget_ns": 3_000_000_000,
        "request_digest": f"sha256:{'1' * 64}",
        "result_digest": f"sha256:{'2' * 64}",
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0405_evidence(evaluation, benchmark)

    evaluation_report["nominal_coverage_ppm"] = 900_000
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="unsupported nominal coverage"):
        verify_m0405_evidence(evaluation, benchmark)

    evaluation_report["nominal_coverage_ppm"] = None
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark_report["event_count"] = 447
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="event_count"):
        verify_m0405_evidence(evaluation, benchmark)


def test_m0406_evidence_verifier_locks_corpus_shape_and_installed_maximum(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m04-06-eval.json"
    benchmark = tmp_path / "m04-06-benchmark.json"
    checks = [{"name": f"scenario.case_{index}", "passed": True} for index in range(56)]
    checks.extend(
        (
            {"name": "corpus.locked_inventory", "passed": True},
            {"name": "corpus.executable_coverage", "passed": True},
        )
    )
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M04-06",
        "passed": True,
        "phase": "locked_executable_corpus",
        "declared_case_count": 56,
        "executed_case_count": 56,
        "missing_case_ids": [],
        "extra_case_ids": [],
        "checks": checks,
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M04-06",
        "contract_version": "1.0.0",
        "workload": "genuine_m0401_through_m0405_installed_max32_fixed_point_support_ledger",
        "timed_boundary": "harmonize_proteoform_analysis_only",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "target_count": 32,
        "observation_count": 32,
        "stage_count": 8,
        "invariant_count": 3,
        "mean_ns": 1_500_000_000.0,
        "p50_ns": 1_400_000_000.0,
        "p95_ns": 2_500_000_000,
        "maximum_ns": 2_750_000_000,
        "mean_budget_ns": 2_000_000_000,
        "p95_budget_ns": 3_000_000_000,
        "request_digest": f"sha256:{'3' * 64}",
        "result_digest": f"sha256:{'4' * 64}",
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0406_evidence(evaluation, benchmark)

    evaluation_report["phase"] = "unlocked"
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="wrong phase"):
        verify_m0406_evidence(evaluation, benchmark)

    evaluation_report["phase"] = "locked_executable_corpus"
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark_report["target_count"] = 31
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="target_count"):
        verify_m0406_evidence(evaluation, benchmark)


def test_m0501_evidence_verifier_requires_exact_corpus_shape_and_budgets(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m05-01-eval.json"
    benchmark = tmp_path / "m05-01-benchmark.json"
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M05-01",
        "contract_version": "1.0.0",
        "declared_groups": 8,
        "group_case_counts": {f"group_{index}": 5 for index in range(8)},
        "declared_cases": 40,
        "executed_cases": 40,
        "passed_cases": 40,
        "failed_cases": [],
        "passed": True,
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M05-01",
        "contract_version": "1.0.0",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "reference_bundle_count": 32,
        "approved_version_count": 16,
        "vocabulary_count": 16,
        "vocabulary_term_count": 12,
        "unit_policy_count": 6,
        "metadata_field_count": 8,
        "compatibility_rule_count": 32,
        "request_bytes": 50_014,
        "result_bytes": 66_750,
        "mean_ns": 1_000_000_000.0,
        "p95_ns": 2_000_000_000,
        "mean_budget_ns": 2_000_000_000,
        "p95_budget_ns": 3_000_000_000,
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0501_evidence(evaluation, benchmark)

    evaluation_report["passed_cases"] = 39
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="passed_cases"):
        verify_m0501_evidence(evaluation, benchmark)

    evaluation_report["passed_cases"] = 40
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark_report["reference_bundle_count"] = 31
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="reference_bundle_count"):
        verify_m0501_evidence(evaluation, benchmark)

    benchmark_report["reference_bundle_count"] = 32
    benchmark_report["mean_ns"] = 2_000_000_001
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing budgets"):
        verify_m0501_evidence(evaluation, benchmark)


def test_m0407_evidence_verifier_requires_exact_corpus_shape_and_budgets(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m04-07-eval.json"
    benchmark = tmp_path / "m04-07-benchmark.json"
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M04-07",
        "phase": "locked_executable_corpus",
        "passed": True,
        "declared_case_count": 19,
        "executed_case_count": 19,
        "missing_case_ids": [],
        "extra_case_ids": [],
        "checks": [{"name": name, "passed": True} for name in M0407_LOCKED_CHECK_NAMES],
    }
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M04-07",
        "contract_version": "1.0.0",
        "workload": "genuine_m0404_and_m0406_prepared_joint_support_envelope",
        "timed_boundary": "route_proteoform_support_only",
        "request_digest": "sha256:" + ("1" * SHA256_HEX_LENGTH),
        "result_digest": "sha256:" + ("2" * SHA256_HEX_LENGTH),
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "envelope_count": 1,
        "dimension_count": 8,
        "evidence_count": 18,
        "mean_ns": 1_500_000_000.0,
        "p50_ns": 1_400_000_000,
        "p95_ns": 2_500_000_000,
        "maximum_ns": 2_600_000_000,
        "mean_budget_ns": 2_000_000_000,
        "p95_budget_ns": 3_000_000_000,
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0407_evidence(evaluation, benchmark)

    evaluation_report["executed_case_count"] = 18
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="executed_case_count"):
        verify_m0407_evidence(evaluation, benchmark)

    evaluation_report["executed_case_count"] = 19
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark_report["evidence_count"] = 17
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="evidence_count"):
        verify_m0407_evidence(evaluation, benchmark)


def test_m0503_evidence_verifier_requires_exact_corpus_shape_and_budgets(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "m05-03-eval.json"
    benchmark = tmp_path / "m05-03-benchmark.json"
    fixture = ROOT / "tests" / "fixtures" / "m05_03" / "scenarios.json"
    fixture_bytes = fixture.read_bytes()
    fixture_payload = json.loads(fixture_bytes)
    case_ids = [
        case_id for group in fixture_payload["scenario_groups"] for case_id in group["case_ids"]
    ]
    evaluation_report = {
        "module_id": "GLIO-PROTEOGEN-M05-03",
        "phase": "locked_executable_corpus",
        "fixture_digest": f"sha256:{hashlib.sha256(fixture_bytes).hexdigest()}",
        "declared_case_count": 72,
        "executed_case_count": 72,
        "missing_case_ids": [],
        "extra_case_ids": [],
        "duplicated_case_ids": [],
        "checks": [
            {"name": "corpus.inventory", "passed": True, "detail": "locked inventory"},
            *(
                {"name": f"scenario.{case_id}", "passed": True, "detail": "substantive"}
                for case_id in case_ids
            ),
            {
                "name": "corpus.executable_coverage",
                "passed": True,
                "detail": "exact executable closure",
            },
        ],
        "passed": True,
    }
    samples = [200_000_000] * 25
    benchmark_report = {
        "module_id": "GLIO-PROTEOGEN-M05-03",
        "contract_version": "1.0.0",
        "workload": "genuine_four_modest_canonical_raw_manifest_documents",
        "timed_boundary": "ingest_ptm_localization_raw_inputs_only",
        "passed": True,
        "iterations": 25,
        "warmup_count": 1,
        "input_artifact_count": 4,
        "document_count": 4,
        "validated_input_count": 4,
        "diagnostic_count": 0,
        "evidence_count": 20,
        "limitation_count": 3,
        "request_bytes": 83_113,
        "result_bytes": 109_985,
        "request_digest": "sha256:55d852052b12e741cafd94a206c57b43d5e4c67601b41673d8bb75d467bd679c",
        "result_digest": "sha256:6d130299f1e37a82f9fb5f106c02cbce900b23e46c73b069497b68956da9219c",
        "samples_ns": samples,
        "mean_ns": 200_000_000.0,
        "p50_ns": 200_000_000,
        "p95_ns": 200_000_000,
        "maximum_ns": 200_000_000,
        "mean_budget_ns": 500_000_000,
        "p95_budget_ns": 750_000_000,
    }
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")

    verify_m0503_evidence(evaluation, benchmark, fixture)

    evaluation_report["executed_case_count"] = 71
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="executed_case_count"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    evaluation_report["executed_case_count"] = 72
    original_name = evaluation_report["checks"][1]["name"]
    evaluation_report["checks"][1]["name"] = "scenario.substituted_but_still_unique"
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="fixture scenario closure"):
        verify_m0503_evidence(evaluation, benchmark, fixture)
    evaluation_report["checks"][1]["name"] = original_name

    evaluation_report["checks"].append(
        {"name": "corpus.extra", "passed": True, "detail": "unlocked extra check"}
    )
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="fixture scenario closure"):
        verify_m0503_evidence(evaluation, benchmark, fixture)
    evaluation_report["checks"].pop()

    evaluation_report["fixture_digest"] = "sha256:" + ("f" * 64)
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="locked fixture"):
        verify_m0503_evidence(evaluation, benchmark, fixture)
    evaluation_report["fixture_digest"] = f"sha256:{hashlib.sha256(fixture_bytes).hexdigest()}"

    drifted_fixture = tmp_path / "drifted-scenarios.json"
    drifted_fixture.write_bytes(fixture_bytes + b"\n")
    evaluation.write_text(json.dumps(evaluation_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="fixture digest"):
        verify_m0503_evidence(evaluation, benchmark, drifted_fixture)

    benchmark_report["document_count"] = 3
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="document_count"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["document_count"] = 4
    benchmark_report["samples_ns"] = samples[:-1]
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing samples"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["samples_ns"] = [0, *samples[1:]]
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing samples"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["samples_ns"] = [True, *samples[1:]]
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing samples"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["samples_ns"] = [*samples, samples[-1]]
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing samples"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["samples_ns"] = samples
    benchmark_report["mean_ns"] = 200_000_001.0
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="disagrees with its samples"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["mean_ns"] = 200_000_000.0
    benchmark_report["request_digest"] = "sha256:" + ("a" * 64)
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="request digest"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["request_digest"] = (
        "sha256:55d852052b12e741cafd94a206c57b43d5e4c67601b41673d8bb75d467bd679c"
    )
    benchmark_report["result_digest"] = "sha256:" + ("b" * 64)
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="result digest"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["result_digest"] = (
        "sha256:6d130299f1e37a82f9fb5f106c02cbce900b23e46c73b069497b68956da9219c"
    )
    benchmark_report["result_bytes"] = 109_984
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="result_bytes"):
        verify_m0503_evidence(evaluation, benchmark, fixture)

    benchmark_report["result_bytes"] = 109_985
    benchmark_report.update(
        samples_ns=[800_000_000] * 25,
        mean_ns=800_000_000.0,
        p50_ns=800_000_000,
        p95_ns=800_000_000,
        maximum_ns=800_000_000,
    )
    benchmark.write_text(json.dumps(benchmark_report), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="timing budgets"):
        verify_m0503_evidence(evaluation, benchmark, fixture)


def test_release_workflow_attests_only_after_reproducible_wheel_replay() -> None:  # noqa: PLR0915
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    build = workflow.index("Build reproducible candidate distributions")
    install = workflow.index("Install and test the exact candidate wheel")
    sbom = workflow.index("Generate reproducible runtime SBOM from the wheel environment")
    attest = workflow.index("Attest candidate distribution provenance")
    assert build < install < sbom < attest
    assert "tools/release-sbom-requirements.txt" in workflow
    assert "sbom-tool-dependency-audit.json" in workflow
    assert "tools/release-build-requirements.txt" in workflow
    assert "build-tool-dependency-audit.json" in workflow
    assert "--no-build-isolation --offline" in workflow
    assert "uvx" not in workflow
    assert "--output-reproducible" in workflow
    assert 'PYTHON_VERSION: "3.12.13"' in workflow
    assert "verify_release_artifacts.py" in workflow
    assert "tools/verify_research_public_proteomics.py" in workflow
    assert "runtime-sbom" in workflow
    assert "--require-hashes" in workflow
    assert "--expected-tag" in workflow
    assert "full-environment-dependency-audit.json" in workflow
    assert "runtime-dependency-audit.json" in workflow
    assert "release-candidate-evidence" in workflow
    assert "evals.m01_01.run --output evidence/m01-01-eval.json" in workflow
    assert "evals.m01_02.run --output evidence/m01-02-eval.json" in workflow
    assert "evals.m01_03.run --output evidence/m01-03-eval.json" in workflow
    assert "evals.m01_04.run --output evidence/m01-04-eval.json" in workflow
    assert "evals.m01_05.run --output evidence/m01-05-eval.json" in workflow
    assert "evals.m01_06.run --output evidence/m01-06-eval.json" in workflow
    assert "evals.m01_07.run --output evidence/m01-07-eval.json" in workflow
    assert "evals.m01_08.run --output evidence/m01-08-eval.json" in workflow
    assert "evals.m02_01.run --output evidence/m02-01-eval.json" in workflow
    assert "evals.m02_02.run --output evidence/m02-02-eval.json" in workflow
    assert "evals.m02_03.run --output evidence/m02-03-eval.json" in workflow
    assert "evals.m02_04.run --output evidence/m02-04-eval.json" in workflow
    assert "evals.m02_05.run --output evidence/m02-05-eval.json" in workflow
    assert "evals.m02_06.run --output evidence/m02-06-eval.json" in workflow
    assert "evals.m02_07.run --output evidence/m02-07-eval.json" in workflow
    assert "evals.m02_08.run --output evidence/m02-08-eval.json" in workflow
    assert "evals.m03_01.run --output evidence/m03-01-eval.json" in workflow
    assert "evals.m03_02.run --output evidence/m03-02-eval.json" in workflow
    assert "evals.m03_03.run --output evidence/m03-03-eval.json" in workflow
    assert "evals.m03_04.run --output evidence/m03-04-eval.json" in workflow
    assert "evals.m03_05.run --output evidence/m03-05-eval.json" in workflow
    assert "evals.m03_06.run --output evidence/m03-06-eval.json" in workflow
    assert "evals.m03_07.run --output evidence/m03-07-eval.json" in workflow
    assert "evals.m03_08.run --output evidence/m03-08-eval.json" in workflow
    assert "evals.m04_01.run --output evidence/m04-01-eval.json" in workflow
    assert "evals.m04_02.run --output evidence/m04-02-eval.json" in workflow
    assert "evals.m04_03.run --output evidence/m04-03-eval.json" in workflow
    assert "evals.m04_04.run --output evidence/m04-04-eval.json" in workflow
    assert "evals.m04_05.run --output evidence/m04-05-eval.json" in workflow
    assert "evals.m04_06.run --output evidence/m04-06-eval.json" in workflow
    assert "evals.m05_01.run --output evidence/m05-01-eval.json" in workflow
    assert "evals.m04_07.run --output evidence/m04-07-eval.json" in workflow
    assert "evals.m05_02.run --output evidence/m05-02-eval.json" in workflow
    assert "evals.m05_03.run --output evidence/m05-03-eval.json" in workflow
    assert "evals.m05_06.run --output evidence/m05-06-eval.json" in workflow
    assert "benchmark-json=evidence/m01-01-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-02-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-03-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-04-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-05-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-06-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-07-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-08-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-01-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-02-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-03-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-04-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-05-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-06-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-07-benchmark.json" in workflow
    assert "benchmark-json=evidence/m02-08-benchmark.json" in workflow
    assert "benchmark-json=evidence/m03-01-benchmark.json" in workflow
    assert "evals.m03_02.benchmark --output evidence/m03-02-benchmark.json" in workflow
    assert "evals.m03_03.benchmark --output evidence/m03-03-benchmark.json" in workflow
    assert "evals.m03_04.benchmark --output evidence/m03-04-benchmark.json" in workflow
    assert "evals.m03_05.benchmark --output evidence/m03-05-benchmark.json" in workflow
    assert "evals.m03_06.benchmark --output evidence/m03-06-benchmark.json" in workflow
    assert "evals.m03_07.benchmark --output evidence/m03-07-benchmark.json" in workflow
    assert "evals.m03_08.benchmark --output evidence/m03-08-benchmark.json" in workflow
    assert "evals.m04_01.benchmark --output evidence/m04-01-benchmark.json" in workflow
    assert "evals.m04_02.benchmark --output evidence/m04-02-benchmark.json" in workflow
    assert "evals.m04_03.benchmark --output evidence/m04-03-benchmark.json" in workflow
    assert "verify_release_artifacts.py m04-03-evidence" in workflow
    assert "evals.m04_04.benchmark --output evidence/m04-04-benchmark.json" in workflow
    assert "verify_release_artifacts.py m04-04-evidence" in workflow
    assert "evals.m04_05.benchmark --output evidence/m04-05-benchmark.json" in workflow
    assert "verify_release_artifacts.py m04-05-evidence" in workflow
    assert "evals.m04_06.benchmark --output evidence/m04-06-benchmark.json" in workflow
    assert "verify_release_artifacts.py m04-06-evidence" in workflow
    assert "evals.m05_01.benchmark --output evidence/m05-01-benchmark.json" in workflow
    assert "verify_release_artifacts.py m05-01-evidence" in workflow
    assert "evals.m04_07.benchmark --output evidence/m04-07-benchmark.json" in workflow
    assert "verify_release_artifacts.py m04-07-evidence" in workflow
    assert "evals.m05_02.benchmark --output evidence/m05-02-benchmark.json" in workflow
    assert "verify_release_artifacts.py m05-02-evidence" in workflow
    assert "evals.m05_03.benchmark --output evidence/m05-03-benchmark.json" in workflow
    assert "evals.m05_06.benchmark --output evidence/m05-06-benchmark.json" in workflow
    assert "verify_release_artifacts.py m05-03-evidence" in workflow
    assert "tests/fixtures/m05_03/scenarios.json" in workflow
    assert "qualified" not in workflow.casefold()
    assert "reviewer approval" not in workflow.casefold()


def test_ci_records_eval_and_benchmark_evidence_for_all_modules() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    modules = (
        "m01_01",
        "m01_02",
        "m01_03",
        "m01_04",
        "m01_05",
        "m01_06",
        "m01_07",
        "m01_08",
        "m02_01",
        "m02_02",
        "m02_03",
        "m02_04",
        "m02_05",
        "m02_06",
        "m02_07",
        "m02_08",
        "m03_01",
        "m03_02",
        "m03_03",
        "m03_04",
        "m03_05",
        "m03_06",
        "m03_07",
        "m03_08",
        "m04_01",
        "m04_02",
        "m04_03",
        "m04_04",
        "m04_05",
        "m04_06",
        "m05_01",
        "m04_07",
        "m05_02",
        "m05_03",
        "m05_04",
        "m05_06",
    )
    assert len(modules) == EXPECTED_MODULE_COUNT
    for module in modules:
        artifact = module.replace("_", "-")
        assert f"evals.{module}.run --output {module}-eval.json" in workflow
        assert f"name: {artifact}-eval" in workflow
        assert f"name: {artifact}-benchmark" in workflow
    assert "benchmarks/m01_01_validation.py" in workflow
    assert "benchmark-json=m01_01-benchmark.json" in workflow
    assert "benchmarks/m01_02_identity_lineage.py" in workflow
    assert "benchmark-json=m01_02-benchmark.json" in workflow
    assert "benchmarks/m01_03_ingestion.py" in workflow
    assert "benchmark-json=m01_03-benchmark.json" in workflow
    assert "benchmarks/m01_04_quality_metrics.py" in workflow
    assert "benchmark-json=m01_04-benchmark.json" in workflow
    assert "benchmarks/m01_05_artifact_detection.py" in workflow
    assert "benchmark-json=m01_05-benchmark.json" in workflow
    assert "benchmarks/m01_06_harmonization.py" in workflow
    assert "benchmark-json=m01_06-benchmark.json" in workflow
    assert "benchmarks/m01_07_support_routing.py" in workflow
    assert "benchmark-json=m01_07-benchmark.json" in workflow
    assert "benchmarks/m01_08_release_packaging.py" in workflow
    assert "benchmark-json=m01_08-benchmark.json" in workflow
    assert "benchmarks/m02_01_metadata_validation.py" in workflow
    assert "benchmark-json=m02_01-benchmark.json" in workflow
    assert "benchmarks/m02_02_identity_bindings.py" in workflow
    assert "benchmark-json=m02_02-benchmark.json" in workflow
    assert "benchmarks/m02_03_identification_ingestion.py" in workflow
    assert "benchmark-json=m02_03-benchmark.json" in workflow
    assert "benchmarks/m02_04_quality_metrics.py" in workflow
    assert "benchmark-json=m02_04-benchmark.json" in workflow
    assert "benchmarks/m02_05_artifact_detection.py" in workflow
    assert "benchmark-json=m02_05-benchmark.json" in workflow
    assert "benchmarks/m02_06_harmonization.py" in workflow
    assert "benchmark-json=m02_06-benchmark.json" in workflow
    assert "benchmarks/m02_07_support_router.py" in workflow
    assert "benchmark-json=m02_07-benchmark.json" in workflow
    assert "benchmarks/m02_08_release_packaging.py" in workflow
    assert "benchmark-json=m02_08-benchmark.json" in workflow
    assert "benchmarks/m03_01_protocol_metadata.py" in workflow
    assert "benchmark-json=m03_01-benchmark.json" in workflow
    assert "evals.m03_02.benchmark --output m03_02-benchmark.json" in workflow
    assert "evals.m03_03.benchmark --output m03_03-benchmark.json" in workflow
    assert "evals.m03_04.benchmark --output m03_04-benchmark.json" in workflow
    assert "evals.m03_05.benchmark --output m03_05-benchmark.json" in workflow
    assert "evals.m03_06.benchmark --output m03_06-benchmark.json" in workflow
    assert "evals.m03_07.benchmark --output m03_07-benchmark.json" in workflow
    assert "evals.m03_08.benchmark --output m03_08-benchmark.json" in workflow
    for module in (
        "m04_01",
        "m04_02",
        "m04_03",
        "m04_04",
        "m04_05",
        "m04_06",
        "m05_01",
        "m04_07",
        "m05_02",
        "m05_03",
        "m05_04",
        "m05_06",
    ):
        assert f"evals.{module}.benchmark --output {module}-benchmark.json" in workflow


def test_ci_replays_public_proteomics_receipt_from_installed_wheel() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    replay = workflow.index("Replay from the built wheel in a clean environment")
    pipeline = workflow.index("tools/verify_research_pipeline.py", replay)
    public = workflow.index("tools/verify_research_public_proteomics.py", pipeline)
    assert pipeline < public
    assert 'docs/evidence/research-foundation/evaluation.json' in workflow[pipeline:public]
    assert '"$wheel" "$sdist"' in workflow[public:]


def test_ci_exercises_the_native_m04_03_windows_interface() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "windows-m04-03-interface" in workflow
    assert "tests/integration/test_m04_03_interfaces.py" in workflow
    assert "--no-cov" in workflow


def test_ci_exercises_the_native_m04_04_windows_interface() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "windows-m04-04-interface" in workflow
    assert "tests/integration/test_m04_04_interfaces.py" in workflow
    assert "--no-cov" in workflow


def test_ci_exercises_the_native_m04_05_windows_interface() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "windows-m04-05-interface" in workflow
    assert "tests/integration/test_m04_05_interfaces.py" in workflow
    assert "--no-cov" in workflow


def test_ci_exercises_the_native_m04_06_windows_interface() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "windows-m04-06-interface" in workflow
    assert "tests/integration/test_m04_06_interfaces.py" in workflow
    assert "--no-cov" in workflow


def test_ci_exercises_the_native_m05_01_windows_interface() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "windows-m05-01-interface" in workflow
    assert "tests/integration/test_m05_01_interfaces.py" in workflow
    assert "--no-cov" in workflow


def test_ci_exercises_the_native_m05_03_windows_interface() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "windows-m05-03-interface" in workflow
    assert "tests/integration/test_m05_03_interfaces.py" in workflow
    assert "--no-cov" in workflow


def test_clean_wheel_smoke_checks_all_module_cli_schema_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    schema_ids = {
        ("export-schema", "protocol-schema"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-01:1.0.0:protocol-schema"
        ),
        ("identity", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-02:1.0.0:request"
        ),
        ("raw", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-03:1.0.0:request"
        ),
        ("quality", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-04:1.0.0:request"
        ),
        ("artifact", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-05:1.0.0:request"
        ),
        ("harmonize", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-06:1.0.0:request"
        ),
        ("support", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-07:1.0.0:request"
        ),
        ("release", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-08:1.0.0:request"
        ),
        ("identification", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-01:1.0.0:request"
        ),
        ("binding", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-02:1.0.0:request"
        ),
        ("identification-raw", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-03:1.0.0:request"
        ),
        ("identification-quality", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-04:1.0.0:request"
        ),
        ("identification-artifacts", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-05:1.0.0:request"
        ),
        ("identification-harmonization", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-06:1.0.0:request"
        ),
        ("identification-support", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-07:1.0.0:request"
        ),
        ("identification-release", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-08:1.0.0:request"
        ),
        ("protein-inference-protocol", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-01:1.0.0:request"
        ),
        ("protein-inference-lineage", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-02:1.0.0:request"
        ),
        ("protein-inference-raw", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-03:1.0.0:request"
        ),
        ("protein-inference-quality", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-04:1.0.0:request"
        ),
        ("protein-inference-artifacts", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-05:1.0.0:request"
        ),
        ("protein-inference-harmonization", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-06:1.0.0:request"
        ),
        ("protein-inference-support", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-07:1.0.0:request"
        ),
        ("protein-inference-release", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-08:1.0.0:request"
        ),
        ("proteoform-protocol", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-01:1.0.0:request"
        ),
        ("proteoform-lineage", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-02:1.0.0:request"
        ),
        ("proteoform-raw", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-03:1.0.0:request"
        ),
        ("proteoform-quality", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-04:1.0.0:request"
        ),
        ("proteoform-artifacts", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-05:1.0.0:request"
        ),
        ("proteoform-harmonization", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-06:1.0.0:request"
        ),
        ("m05-01-export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-01:1.0.0:request"
        ),
        ("proteoform-support", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-07:1.0.0:request"
        ),
        ("m05-02-export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-02:1.0.0:request"
        ),
        ("ptm-localization-raw", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-03:1.0.0:request"
        ),
        ("ptm-localization-quality", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-04:1.0.0:request"
        ),
        ("ptm-localization-harmonization", "export-schema", "request"): (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-06:1.0.0-provisional:request"
        ),
    }
    assert len(schema_ids) == EXPECTED_MODULE_COUNT

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        arguments = tuple(command[1:])
        calls.append(arguments)
        payload = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": schema_ids[arguments],
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(
        verify_release_artifacts,
        "_installed_console_script",
        lambda: Path("/clean-environment/bin/glio-proteogen"),
    )
    monkeypatch.setattr(subprocess, "run", run)

    verify_release_artifacts._verify_console_script()

    assert calls == list(schema_ids)
    assert len(calls) == EXPECTED_MODULE_COUNT


def test_clean_wheel_smoke_rejects_wrong_m01_02_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-01:1.0.0:protocol-schema"),
    }

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(wrong_schema),
            stderr="",
        )

    monkeypatch.setattr(
        verify_release_artifacts,
        "_installed_console_script",
        lambda: Path("/clean-environment/bin/glio-proteogen"),
    )
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(ReleaseArtifactError, match="wrong contract"):
        verify_release_artifacts._verify_console_script()


def test_workflow_actions_are_commit_pinned_and_checkout_drops_credentials() -> None:
    workflows = (
        RELEASE_WORKFLOW.read_text(encoding="utf-8"),
        CI_WORKFLOW.read_text(encoding="utf-8"),
    )

    for workflow in workflows:
        action_lines = [
            line.strip() for line in workflow.splitlines() if line.lstrip().startswith("- uses:")
        ]
        assert action_lines
        for line in action_lines:
            action_reference = line.split("uses:", maxsplit=1)[1].split("#", maxsplit=1)[0].strip()
            _action, separator, revision = action_reference.rpartition("@")
            assert separator == "@"
            assert re.fullmatch(r"[0-9a-f]{40}", revision)

        checkout_count = workflow.count("uses: actions/checkout@")
        assert workflow.count("persist-credentials: false") == checkout_count


def test_integrity_policy_states_external_trust_and_review_boundaries() -> None:
    security = " ".join(SECURITY_POLICY.read_text(encoding="utf-8").split())
    evidence = " ".join(EVIDENCE_POLICY.read_text(encoding="utf-8").split())

    assert "not a signature or a secret-authenticated log" in security
    assert "fresh process cannot distinguish" in security
    assert "operating-system ACLs" in security
    assert "SQLite backup API" in security
    assert "never emits qualified evidence" in evidence
    assert "independently retained" in evidence
