from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np
import pytest

import glio_proteogen.research.cptac_gbm_transcript_protein_discordance.service as service_module
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.artifact import (
    TranscriptProteinDiscordanceArtifact,
    build_artifact,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.contracts import (
    CohortArtifactSummary,
    DerivationStatus,
    DiscordancePattern,
    EvidenceSupport,
    ReplayVerificationRequest,
    TranscriptProteinDiscordanceRequest,
    UnverifiedTranscriptProteinDiscordanceResult,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.errors import (
    DiscordanceArtifactIntegrityError,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.fitter import (
    _statistics,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.model import (
    fit_transcript_protein_discordance_gene,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.service import (
    analyze_transcript_protein_discordance,
    verify_transcript_protein_discordance_replay,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.source import (
    EXACT_SOURCE_LOCKS,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def locally_verified_artifact() -> TranscriptProteinDiscordanceArtifact:
    random = np.random.default_rng(7103)
    patient_groups = 96
    cnv = random.normal(size=patient_groups).astype(np.float32)
    rna = (0.75 * cnv + random.normal(0.0, 0.35, patient_groups)).astype(np.float32)
    protein = (1.15 * rna + 0.10 * cnv + random.normal(0.0, 0.20, patient_groups)).astype(
        np.float32
    )
    folds = (np.arange(patient_groups) % 5).astype(np.int8)
    fit = fit_transcript_protein_discordance_gene(
        cnv,
        rna,
        protein,
        folds,
        request_digest="sha256:" + "7" * 64,
    )
    assert fit is not None
    return build_artifact(
        source_locks=EXACT_SOURCE_LOCKS,
        cohort=CohortArtifactSummary(
            exact_common_measurement_count=96,
            patient_group_count=96,
            common_gene_count=10_430,
            fitted_gene_count=1,
        ),
        attempted_gene_symbols=("EGFR",),
        gene_statistics={"EGFR": _statistics(fit.summary)},
        derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
    )


def _install_artifact_at_loader_boundary(
    monkeypatch: pytest.MonkeyPatch,
    artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    payload = canonical_json_bytes(artifact)
    byte_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(service_module, "load_artifact", lambda _path: (artifact, byte_digest))


def test_local_cohort_query_and_exact_replay_lifecycle(
    locally_verified_artifact: TranscriptProteinDiscordanceArtifact,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = locally_verified_artifact
    _install_artifact_at_loader_boundary(monkeypatch, artifact)
    request = TranscriptProteinDiscordanceRequest(
        query_id="cptac-gbm-cohort-query",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("PTEN", "EGFR"),
    )

    result = analyze_transcript_protein_discordance(
        request,
        artifact_path=tmp_path / "loader-boundary-fixture.json",
    )

    assert tuple(item.gene_symbol for item in result.genes) == ("EGFR", "PTEN")
    egfr, pten = result.genes
    assert egfr.support is EvidenceSupport.LIMITED
    assert egfr.pattern is DiscordancePattern.POSITIVE_CONDITIONAL_RNA_ASSOCIATION
    assert egfr.statistics is not None
    assert egfr.statistics.bootstrap.requested_replicates == 128
    assert pten.support is EvidenceSupport.ABSTAINED
    assert pten.statistics is None
    assert "not predeclared" in pten.reasons[0]
    assert result.maximum_support == "limited"
    assert not result.patient_level_inference
    assert "iProFun reproduction" in " ".join(result.limitations)

    provided = UnverifiedTranscriptProteinDiscordanceResult.model_validate_json(
        canonical_json_bytes(result),
        strict=True,
    )
    verification = verify_transcript_protein_discordance_replay(
        ReplayVerificationRequest(request=request, result=provided),
        artifact_path=tmp_path / "loader-boundary-fixture.json",
    )
    assert verification.verified
    assert verification.provided_result_digest_valid
    assert verification.semantic_match


def test_query_rejects_an_artifact_content_digest_mismatch(
    locally_verified_artifact: TranscriptProteinDiscordanceArtifact,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_artifact_at_loader_boundary(monkeypatch, locally_verified_artifact)
    request = TranscriptProteinDiscordanceRequest(
        query_id="wrong-artifact",
        artifact_content_digest="sha256:" + "8" * 64,
        gene_symbols=("EGFR",),
    )

    with pytest.raises(
        DiscordanceArtifactIntegrityError,
        match="request artifact digest does not match",
    ):
        analyze_transcript_protein_discordance(
            request,
            artifact_path=tmp_path / "loader-boundary-fixture.json",
        )
