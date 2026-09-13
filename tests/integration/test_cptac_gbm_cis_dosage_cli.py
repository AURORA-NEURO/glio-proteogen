from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
from typer.testing import CliRunner

import glio_proteogen.adapters.cptac_gbm_cis_dosage as adapter
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_cis_dosage.artifact import write_artifact
from glio_proteogen.research.cptac_gbm_cis_dosage.contracts import CisDosageEvidenceRequest
from glio_proteogen.research.cptac_gbm_cis_dosage.fitter import (
    _fit_prepared_cohort_unverified,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import PreparedCohort
from glio_proteogen.research.cptac_gbm_cis_dosage.source import HGNC_LOCK, TABLE_S2_LOCK

if TYPE_CHECKING:
    from pathlib import Path


def _local_artifact(tmp_path: Path):
    random = np.random.default_rng(41)
    count = 75
    cnv = random.choice([-2.0, -1.0, 0.0, 1.0, 2.0], count)
    rna = 1.4 * cnv + random.normal(0.0, 0.25, count)
    protein = 0.3 * cnv + 0.9 * rna + random.normal(0.0, 0.25, count)
    cohort = PreparedCohort(
        cnv={"EGFR": cnv.astype(np.float32)},
        rna={"EGFR": rna.astype(np.float32)},
        protein={"EGFR": protein.astype(np.float32)},
        folds=np.arange(count, dtype=np.int8) % 5,
        common_genes=("EGFR",),
        exact_common_measurement_count=count,
        patient_group_count=count,
    )
    artifact = _fit_prepared_cohort_unverified(cohort, source_locks=(TABLE_S2_LOCK, HGNC_LOCK))
    path = tmp_path / "artifact.json"
    write_artifact(path, artifact)
    return artifact, path


def test_isolated_cli_profile_and_synthetic_analysis_rejection(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = runner.invoke(adapter.cli, ["profile"])
    assert profile.exit_code == 0
    assert json.loads(profile.stdout)["public_http_mounted"] is False
    assert not hasattr(adapter, "router")

    artifact, artifact_path = _local_artifact(tmp_path)
    request = CisDosageEvidenceRequest(
        query_id="cli-query",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("EGFR",),
    )
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    analyzed = runner.invoke(
        adapter.cli,
        ["analyze", str(request_path), "--artifact", str(artifact_path)],
    )
    assert analyzed.exit_code != 0
    assert "failed safely" in analyzed.output
    verify_help = runner.invoke(adapter.cli, ["verify", "--help"])
    assert verify_help.exit_code == 0


def test_cli_verify_source_fails_closed_on_wrong_bytes(tmp_path: Path) -> None:
    runner = CliRunner()
    s2 = tmp_path / "s2.xlsx"
    hgnc = tmp_path / "hgnc.tsv"
    s2.write_bytes(b"wrong")
    hgnc.write_bytes(b"wrong")
    result = runner.invoke(
        adapter.cli,
        ["verify-source", "--table-s2", str(s2), "--hgnc", str(hgnc)],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["verified"] is False
