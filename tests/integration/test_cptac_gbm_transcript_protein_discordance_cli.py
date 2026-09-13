"""Local CLI integration for CPTAC GBM transcript--protein evidence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

from typer.testing import CliRunner

import glio_proteogen.adapters.cptac_gbm_transcript_protein_discordance as adapter
from glio_proteogen.adapters.cli import app as central_cli
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.artifact import (
    TranscriptProteinDiscordanceArtifact,
    build_artifact,
    write_artifact,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.contracts import (
    BootstrapEvidence,
    CohortArtifactSummary,
    DerivationStatus,
    FiniteSampleInterval,
    FoldConditionalEvidence,
    GeneDiscordanceStatistics,
    HeldOutModelMetrics,
    TranscriptProteinDiscordanceRequest,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.source import (
    EXACT_SOURCE_LOCKS,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_TYPER_USAGE_ERROR: Final = 2


def _interval(point: float, lower: float, upper: float) -> FiniteSampleInterval:
    return FiniteSampleInterval(
        point_estimate=point,
        lower=lower,
        upper=upper,
        replicates=128,
    )


def _aggregate_statistics() -> GeneDiscordanceStatistics:
    return GeneDiscordanceStatistics(
        full_model=HeldOutModelMetrics(
            n_oof=96,
            spearman=0.81,
            r2_vs_fold_train_median=0.62,
            mae=0.24,
            residual_mad=0.17,
        ),
        rna_only_r2=0.56,
        cnv_only_r2=0.21,
        delta_r2_vs_rna_only=0.06,
        delta_r2_vs_cnv_only=0.41,
        folds=FoldConditionalEvidence(
            valid_folds=5,
            converged_folds=5,
            conditional_rna_slope_median=0.91,
            conditional_rna_slope_mad=0.04,
            conditional_rna_sign_stability=1.0,
        ),
        bootstrap=BootstrapEvidence(
            requested_replicates=128,
            successful_replicates=128,
            full_r2=_interval(0.62, 0.48, 0.71),
            delta_r2_vs_rna_only=_interval(0.06, 0.01, 0.12),
            delta_r2_vs_cnv_only=_interval(0.41, 0.28, 0.52),
            mae=_interval(0.24, 0.19, 0.31),
            residual_mad=_interval(0.17, 0.12, 0.23),
            conditional_rna_slope=_interval(0.91, 0.72, 1.09),
            seed=7,
        ),
    )


def _trusted_aggregate_artifact(
    tmp_path: Path,
) -> tuple[TranscriptProteinDiscordanceArtifact, Path]:
    artifact = build_artifact(
        source_locks=EXACT_SOURCE_LOCKS,
        cohort=CohortArtifactSummary(
            exact_common_measurement_count=96,
            patient_group_count=96,
            common_gene_count=10_430,
            fitted_gene_count=1,
        ),
        attempted_gene_symbols=("EGFR",),
        gene_statistics={"EGFR": _aggregate_statistics()},
        derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
    )
    path = tmp_path / "discordance-artifact.json"
    write_artifact(path, artifact)
    return artifact, path


def test_profile_is_centrally_registered_but_has_no_http_router() -> None:
    runner = CliRunner()
    direct = runner.invoke(adapter.cli, ["profile"])
    assert direct.exit_code == 0
    profile = json.loads(direct.stdout)
    assert profile["public_cli_mounted"] is True
    assert profile["public_http_mounted"] is False
    assert profile["patient_measurement_input_permitted"] is False
    assert not hasattr(adapter, "router")

    central = runner.invoke(
        central_cli,
        ["cptac-gbm-transcript-protein-discordance", "profile"],
    )
    assert central.exit_code == 0
    assert json.loads(central.stdout) == profile


def test_fit_local_requires_and_forwards_explicit_repeatable_genes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table_s2 = tmp_path / "table-s2.xlsx"
    hgnc = tmp_path / "hgnc.tsv"
    table_s2.write_bytes(b"local-test-placeholder")
    hgnc.write_bytes(b"local-test-placeholder")
    output = tmp_path / "artifact.json"
    observed: dict[str, object] = {}

    def fake_fit_local_artifact(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        gene_symbols = kwargs["gene_symbols"]
        assert isinstance(gene_symbols, tuple)
        return {"fitted_gene_count": len(gene_symbols)}

    monkeypatch.setattr(adapter, "fit_local_artifact", fake_fit_local_artifact)
    runner = CliRunner()
    result = runner.invoke(
        adapter.cli,
        [
            "fit-local",
            "--table-s2",
            str(table_s2),
            "--hgnc",
            str(hgnc),
            "--output",
            str(output),
            "--gene",
            "TP53",
            "--gene",
            "EGFR",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"fitted_gene_count": 2}
    assert observed == {
        "table_s2": table_s2,
        "hgnc": hgnc,
        "output": output,
        "gene_symbols": ("TP53", "EGFR"),
    }

    missing_gene = runner.invoke(
        adapter.cli,
        [
            "fit-local",
            "--table-s2",
            str(table_s2),
            "--hgnc",
            str(hgnc),
            "--output",
            str(output),
        ],
    )
    assert missing_gene.exit_code == _TYPER_USAGE_ERROR


def test_cli_analyze_and_exact_replay_lifecycle(tmp_path: Path) -> None:
    artifact, artifact_path = _trusted_aggregate_artifact(tmp_path)
    request = TranscriptProteinDiscordanceRequest(
        query_id="discordance-cli-query",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("EGFR", "PTEN"),
    )
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))

    runner = CliRunner()
    analyzed = runner.invoke(
        adapter.cli,
        ["analyze", str(request_path), "--artifact", str(artifact_path)],
    )
    assert analyzed.exit_code == 0
    result = json.loads(analyzed.stdout)
    by_gene = {entry["gene_symbol"]: entry for entry in result["genes"]}
    assert by_gene["EGFR"]["pattern"] == "positive_conditional_rna_association"
    assert by_gene["EGFR"]["support"] == "limited"
    assert by_gene["PTEN"]["support"] == "abstained"
    assert result["patient_level_inference"] is False

    envelope_path = tmp_path / "replay.json"
    envelope_path.write_bytes(
        canonical_json_bytes(
            {
                "request": request.model_dump(mode="json"),
                "result": result,
            }
        )
    )
    replayed = runner.invoke(
        adapter.cli,
        ["verify", str(envelope_path), "--artifact", str(artifact_path)],
    )
    assert replayed.exit_code == 0
    verification = json.loads(replayed.stdout)
    assert verification["verified"] is True
    assert verification["semantic_match"] is True
