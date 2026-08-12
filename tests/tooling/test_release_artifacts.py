"""Release workflow and artifact-integrity policy tests."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest
from tools import verify_release_artifacts
from tools.verify_release_artifacts import (
    ReleaseArtifactError,
    verify_runtime_sbom,
    wheel_identity,
)

ROOT = Path(__file__).parents[2]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-evidence.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SECURITY_POLICY = ROOT / "SECURITY.md"
EVIDENCE_POLICY = ROOT / "docs" / "evidence" / "M01-01.md"
SHA256_HEX_LENGTH = 64
EXPECTED_RUNTIME_COMPONENTS = 2


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


def test_release_workflow_attests_only_after_reproducible_wheel_replay() -> None:
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
    assert "benchmark-json=evidence/m01-01-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-02-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-03-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-04-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-05-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-06-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-07-benchmark.json" in workflow
    assert "benchmark-json=evidence/m01-08-benchmark.json" in workflow
    assert "qualified" not in workflow.casefold()
    assert "reviewer approval" not in workflow.casefold()


def test_ci_records_eval_and_benchmark_evidence_for_all_modules() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    for module in (
        "m01_01",
        "m01_02",
        "m01_03",
        "m01_04",
        "m01_05",
        "m01_06",
        "m01_07",
        "m01_08",
    ):
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


def test_clean_wheel_smoke_checks_all_module_cli_schema_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    schema_ids = {
        ("export-schema", "protocol-schema"): (
            "urn:aurora-neuro:glio-proteogen:"
            "GLIO-PROTEOGEN-M01-01:1.0.0:protocol-schema"
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
    }

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
    monkeypatch.setattr(verify_release_artifacts.subprocess, "run", run)

    verify_release_artifacts._verify_console_script()

    assert calls == list(schema_ids)


def test_clean_wheel_smoke_rejects_wrong_m01_02_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "urn:aurora-neuro:glio-proteogen:"
            "GLIO-PROTEOGEN-M01-01:1.0.0:protocol-schema"
        ),
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
    monkeypatch.setattr(verify_release_artifacts.subprocess, "run", run)

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
