"""Adversarial checks for the M03-08 release-evidence verifier."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from tools.verify_m03_08_release import M0308ReleaseEvidenceError, verify_release

if TYPE_CHECKING:
    from pathlib import Path


def _evidence(tmp_path: Path) -> Path:
    directory = tmp_path / "evidence"
    directory.mkdir()
    checks = [{"name": f"case-{index}", "passed": True} for index in range(40)]
    (directory / "evaluation.json").write_text(
        json.dumps(
            {
                "module_id": "GLIO-PROTEOGEN-M03-08",
                "contract_version": "1.0.0",
                "status": "PASS",
                "declared_case_count": 38,
                "executed_case_count": 38,
                "passed_case_count": 38,
                "missing_case_ids": [],
                "extra_case_ids": [],
                "duplicate_declared_case_ids": [],
                "duplicate_executed_case_ids": [],
                "checks": checks,
            }
        ),
        encoding="utf-8",
    )
    (directory / "benchmark.json").write_text(
        json.dumps(
            {
                "module_id": "GLIO-PROTEOGEN-M03-08",
                "contract_version": "1.0.0",
                "passed": True,
                "workload": "public_build_exact_64_software_64_reference_shape",
                "software_version_count": 64,
                "reference_version_count": 64,
                "archive_member_count": 10,
                "mean_budget_ns": 2_000_000_000,
                "p95_budget_ns": 3_000_000_000,
                "mean_ns": 10,
                "p95_ns": 20,
            }
        ),
        encoding="utf-8",
    )
    (directory / "coverage.json").write_text(
        json.dumps({"totals": {"percent_covered": 96.0}}),
        encoding="utf-8",
    )
    (directory / "package.json").write_text(
        json.dumps(
            {
                "module_id": "GLIO-PROTEOGEN-M03-08",
                "contract_version": "1.0.0",
                "passed": True,
                "source_date_epoch": 315532800,
                "reproducible_builds": True,
                "isolated_import": True,
                "artifacts": [
                    {
                        "kind": "wheel",
                        "filename": "package.whl",
                        "size_bytes": 4,
                        "sha256": (
                            "3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7"
                        ),
                        "members": 1,
                    },
                    {
                        "kind": "sdist",
                        "filename": "package.tar.gz",
                        "size_bytes": 4,
                        "sha256": (
                            "3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7"
                        ),
                        "members": 1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_release_verifier_accepts_complete_receipts(tmp_path: Path) -> None:
    directory = _evidence(tmp_path)
    assert verify_release(directory) == {
        "module_id": "GLIO-PROTEOGEN-M03-08",
        "contract_version": "1.0.0",
        "passed": True,
        "evaluation_cases": 38,
        "coverage_percent": 96.0,
        "artifacts": ["wheel", "sdist"],
    }


@pytest.mark.parametrize(
    ("filename", "replacement"),
    [
        ("evaluation.json", '{"module_id":"GLIO-PROTEOGEN-M03-08", "module_id":"x"}'),
        ("benchmark.json", '{"module_id":"GLIO-PROTEOGEN-M03-08", "passed":NaN}'),
    ],
)
def test_release_verifier_rejects_ambiguous_json(
    tmp_path: Path,
    filename: str,
    replacement: str,
) -> None:
    directory = _evidence(tmp_path)
    (directory / filename).write_text(replacement, encoding="utf-8")
    with pytest.raises(M0308ReleaseEvidenceError):
        verify_release(directory)


def test_release_verifier_binds_external_artifact_bytes(tmp_path: Path) -> None:
    directory = _evidence(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "package.whl").write_bytes(b"good")
    (artifacts / "package.tar.gz").write_bytes(b"good")
    with pytest.raises(M0308ReleaseEvidenceError, match="digest mismatch"):
        verify_release(directory, artifacts)
