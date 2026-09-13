from __future__ import annotations

import hashlib
import io
import stat
from typing import TYPE_CHECKING

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

import glio_proteogen.research.cptac_gbm_cis_dosage as cptac_package
import glio_proteogen.research.cptac_gbm_cis_dosage.artifact as artifact_module
import glio_proteogen.research.cptac_gbm_cis_dosage.service as service_module
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_cis_dosage.artifact import (
    build_artifact,
    load_artifact,
    write_artifact,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.canonical import (
    artifact_content_digest,
    result_digest,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.contracts import (
    MAX_ARTIFACT_BYTES,
    CisDosageEvidenceRequest,
    CisDosageEvidenceResult,
    CisDosageProvenance,
    CohortArtifactSummary,
    DerivationStatus,
    EvidenceSupport,
    ExactSourceLock,
    GeneCisDosageEvidence,
    ReplayVerificationRequest,
    SourcePositiveFlag,
    TableS3SourceFlags,
    UnverifiedCisDosageEvidenceResult,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.errors import (
    ArtifactIntegrityError,
    FitNotEvaluableError,
    SourceLockError,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.fitter import (
    _assert_production_cohort_invariants,
    _fit_prepared_cohort_unverified,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.model import (
    fit_gene_cross_validated,
    gene_fit_document,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import PreparedCohort
from glio_proteogen.research.cptac_gbm_cis_dosage.profile import algorithm_profile
from glio_proteogen.research.cptac_gbm_cis_dosage.service import (
    analyze_cis_dosage_evidence,
    verify_cis_dosage_replay,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.source import (
    HGNC_LOCK,
    TABLE_S2_LOCK,
    TABLE_S3_LOCK,
    _copy_exact_stream,
    _stage_exact_file,
    verify_sources,
)

if TYPE_CHECKING:
    from pathlib import Path


def _synthetic_cohort() -> PreparedCohort:
    random = np.random.default_rng(4)
    sample_count = 75
    folds = np.arange(sample_count, dtype=np.int8) % 5
    cnv = random.choice([-2.0, -1.0, 0.0, 1.0, 2.0], sample_count)
    rna = 1.5 * cnv + random.normal(0.0, 0.3, sample_count)
    protein = 0.4 * cnv + 0.8 * rna + random.normal(0.0, 0.3, sample_count)
    return PreparedCohort(
        cnv={"EGFR": cnv.astype(np.float32)},
        rna={"EGFR": rna.astype(np.float32)},
        protein={"EGFR": protein.astype(np.float32)},
        folds=folds,
        common_genes=("EGFR",),
        exact_common_measurement_count=sample_count,
        patient_group_count=sample_count,
    )


def _artifact(tmp_path: Path):
    artifact = _fit_prepared_cohort_unverified(
        _synthetic_cohort(),
        source_locks=(TABLE_S2_LOCK, TABLE_S3_LOCK, HGNC_LOCK),
        table_s3_flags={"EGFR": (True, False)},
    )
    path = tmp_path / "local-artifact.json"
    write_artifact(path, artifact)
    return artifact, path


def test_robust_outer_fold_model_recovers_locked_synthetic_direction() -> None:
    cohort = _synthetic_cohort()
    fit = fit_gene_cross_validated(
        cohort.cnv["EGFR"], cohort.rna["EGFR"], cohort.protein["EGFR"], cohort.folds
    )
    assert fit is not None
    assert fit.rna_evidence_gate
    assert fit.protein_evidence_gate
    assert fit.coefficients["a_cnv_to_rna_median"] > 0
    assert fit.coefficients["b_rna_to_protein_given_cnv_median"] > 0
    assert fit.coefficients["indirect_sign_consistency"] == 1.0
    assert fit.coefficients["total_sign_consistency"] == 1.0
    assert fit.rna["r2_vs_fold_train_median"] > 0.8
    assert fit.protein["r2_vs_fold_train_median"] > 0.8


def test_artifact_is_compact_canonical_and_contains_no_patient_material(tmp_path: Path) -> None:
    artifact, path = _artifact(tmp_path)
    payload = path.read_bytes()
    assert len(payload) < MAX_ARTIFACT_BYTES
    assert payload == canonical_json_bytes(artifact)
    assert b"C3N-" not in payload and b"TCGA-" not in payload
    assert artifact.cohort.contains_patient_measurements is False
    assert artifact.cohort.contains_patient_identifiers_or_hashes is False
    loaded, _ = load_artifact(path)
    assert loaded == artifact


def test_artifact_read_is_bounded_by_one_byte_overflow_probe(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as stream:
        stream.seek(MAX_ARTIFACT_BYTES)
        stream.write(b"x")
    with pytest.raises(ArtifactIntegrityError, match="eight MiB"):
        load_artifact(oversized)


def test_continuously_growing_stream_is_stopped_at_limit_plus_one() -> None:
    class GrowingStream:
        def __init__(self) -> None:
            self.bytes_returned = 0
            self.largest_request = 0

        def read(self, size: int = -1) -> bytes:
            self.largest_request = max(self.largest_request, size)
            self.bytes_returned += size
            return b"x" * size

    stream = GrowingStream()
    with pytest.raises(ArtifactIntegrityError, match="eight MiB"):
        artifact_module._read_bounded_artifact_stream(stream)  # type: ignore[arg-type]
    assert stream.bytes_returned == MAX_ARTIFACT_BYTES + 1
    assert stream.largest_request == 64 * 1_024


def test_artifact_publication_refuses_existing_destination(tmp_path: Path) -> None:
    artifact = _fit_prepared_cohort_unverified(
        _synthetic_cohort(), source_locks=(TABLE_S2_LOCK, HGNC_LOCK)
    )
    destination = tmp_path / "existing.json"
    destination.write_bytes(b"caller-owned")
    with pytest.raises(ArtifactIntegrityError, match="overwrite"):
        write_artifact(destination, artifact)
    assert destination.read_bytes() == b"caller-owned"
    assert not tuple(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_artifact_publication_refuses_destination_created_during_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _fit_prepared_cohort_unverified(
        _synthetic_cohort(), source_locks=(TABLE_S2_LOCK, HGNC_LOCK)
    )
    destination = tmp_path / "raced.json"
    real_link = artifact_module.os.link

    def racing_link(source: Path, target: Path) -> None:
        target.write_bytes(b"racing-writer")
        real_link(source, target)

    monkeypatch.setattr(artifact_module.os, "link", racing_link)
    with pytest.raises(ArtifactIntegrityError, match="overwrite"):
        write_artifact(destination, artifact)
    assert destination.read_bytes() == b"racing-writer"
    assert not tuple(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_synthetic_artifact_is_explicitly_unverified_and_fails_closed(tmp_path: Path) -> None:
    artifact, path = _artifact(tmp_path)
    assert artifact.derivation_status is DerivationStatus.SYNTHETIC_UNVERIFIED
    request = CisDosageEvidenceRequest(
        query_id="query-1",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("TP53", "EGFR"),
    )
    with pytest.raises(ArtifactIntegrityError, match="not derived"):
        analyze_cis_dosage_evidence(request, artifact_path=path)
    flags = service_module._source_flags("EGFR", artifact)
    assert flags.cnv_rna is SourcePositiveFlag.REPORTED_POSITIVE
    assert flags.cnv_protein is SourcePositiveFlag.NOT_REPORTED_POSITIVE


def test_same_user_self_authored_fixture_exercises_positive_analyze_verify_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exercise service admission, not cross-user authenticity or production fitting."""

    cohort = _synthetic_cohort()
    fit = fit_gene_cross_validated(
        cohort.cnv["EGFR"], cohort.rna["EGFR"], cohort.protein["EGFR"], cohort.folds
    )
    assert fit is not None
    supported_record = gene_fit_document(fit)
    limited_record = dict(supported_record)
    limited_record["protein_evidence_gate"] = False
    gene_evidence = {
        "EGFR": supported_record,
        "PTEN": limited_record,
        **{f"ZTEST{index:05d}": supported_record for index in range(9_455)},
    }
    # This is a schema-valid, self-authored same-user fixture at the loader boundary.
    # Its self-hash is deliberately not treated as third-party source authenticity.
    artifact = build_artifact(
        source_locks=(TABLE_S2_LOCK, HGNC_LOCK),
        cohort=CohortArtifactSummary(
            exact_common_measurement_count=96,
            patient_group_count=96,
            common_gene_count=10_430,
            fitted_gene_count=9_457,
            table_s3_flags_included=False,
        ),
        gene_evidence=gene_evidence,
        derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
    )
    artifact_bytes = canonical_json_bytes(artifact)
    artifact_byte_digest = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    monkeypatch.setattr(
        service_module,
        "load_artifact",
        lambda _path: (artifact, artifact_byte_digest),
    )
    request = CisDosageEvidenceRequest(
        query_id="positive-service-lifecycle",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("TP53", "PTEN", "EGFR"),
    )
    result = analyze_cis_dosage_evidence(
        request,
        artifact_path=tmp_path / "injected-at-loader-boundary.json",
    )
    supports = {gene.gene_symbol: gene.support for gene in result.genes}
    assert supports == {
        "EGFR": EvidenceSupport.SUPPORTED,
        "PTEN": EvidenceSupport.LIMITED,
        "TP53": EvidenceSupport.ABSTAINED,
    }
    assert result.provenance.derivation_status is DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES

    provided = UnverifiedCisDosageEvidenceResult.model_validate_json(
        canonical_json_bytes(result), strict=True
    )
    verification = verify_cis_dosage_replay(
        ReplayVerificationRequest(request=request, result=provided),
        artifact_path=tmp_path / "injected-at-loader-boundary.json",
    )
    assert verification.verified
    assert verification.provided_result_digest_valid
    assert verification.recomputed_result_digest_match
    assert verification.semantic_match


def _verified_abstention_result(
    request: CisDosageEvidenceRequest,
) -> CisDosageEvidenceResult:
    profile = algorithm_profile()
    cohort = CohortArtifactSummary(
        exact_common_measurement_count=96,
        patient_group_count=96,
        common_gene_count=10_430,
        fitted_gene_count=9_457,
        table_s3_flags_included=False,
    )
    gene = GeneCisDosageEvidence(
        gene_symbol="EGFR",
        support=EvidenceSupport.ABSTAINED,
        table_s3_source_flags=TableS3SourceFlags(
            cnv_rna=SourcePositiveFlag.NOT_AVAILABLE,
            cnv_protein=SourcePositiveFlag.NOT_AVAILABLE,
        ),
        reasons=("Test-only abstention receipt carries no fitted biological evidence.",),
    )
    provenance = CisDosageProvenance(
        artifact_content_digest=request.artifact_content_digest,
        artifact_byte_digest="sha256:" + "2" * 64,
        profile_digest=profile.profile_digest,
        request_digest=request.request_digest,
        source_locks=(TABLE_S2_LOCK, HGNC_LOCK),
        cohort=cohort,
        derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
        numpy_version=profile.numpy_version,
    )
    draft = UnverifiedCisDosageEvidenceResult(
        query_id=request.query_id,
        profile_digest=profile.profile_digest,
        request_digest=request.request_digest,
        result_digest="sha256:" + "0" * 64,
        artifact_content_digest=request.artifact_content_digest,
        genes=(gene,),
        provenance=provenance,
        limitations=(
            "Test-only replay fixture.",
            "No fitted biological values are present.",
            "Not a scientific result.",
        ),
    )
    payload = draft.model_dump(mode="json")
    payload["result_digest"] = result_digest(payload)
    return CisDosageEvidenceResult.model_validate_json(canonical_json_bytes(payload), strict=True)


def test_replay_distinguishes_self_valid_digest_from_recomputed_equality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = CisDosageEvidenceRequest(
        query_id="query-2",
        artifact_content_digest="sha256:" + "3" * 64,
        gene_symbols=("EGFR",),
    )
    result = _verified_abstention_result(request)
    monkeypatch.setattr(service_module, "analyze_cis_dosage_evidence", lambda *_args, **_kw: result)
    provided = UnverifiedCisDosageEvidenceResult.model_validate_json(
        canonical_json_bytes(result), strict=True
    )
    verified = verify_cis_dosage_replay(
        ReplayVerificationRequest(request=request, result=provided),
        artifact_path=tmp_path / "not-read.json",
    )
    assert verified.verified
    assert verified.provided_result_digest_valid
    assert verified.recomputed_result_digest_match

    forged_payload = provided.model_dump(mode="json")
    forged_payload["result_digest"] = "sha256:" + "f" * 64
    forged = UnverifiedCisDosageEvidenceResult.model_validate_json(
        canonical_json_bytes(forged_payload), strict=True
    )
    rejected = verify_cis_dosage_replay(
        ReplayVerificationRequest(request=request, result=forged),
        artifact_path=tmp_path / "not-read.json",
    )
    assert not rejected.verified
    assert not rejected.provided_result_digest_valid
    assert not rejected.recomputed_result_digest_match
    assert not rejected.semantic_match

    divergent_payload = provided.model_dump(mode="json")
    divergent_payload["limitations"][0] = "Different but self-consistent receipt."
    divergent_payload["result_digest"] = result_digest(divergent_payload)
    divergent = UnverifiedCisDosageEvidenceResult.model_validate_json(
        canonical_json_bytes(divergent_payload), strict=True
    )
    divergent_check = verify_cis_dosage_replay(
        ReplayVerificationRequest(request=request, result=divergent),
        artifact_path=tmp_path / "not-read.json",
    )
    assert divergent_check.provided_result_digest_valid
    assert not divergent_check.recomputed_result_digest_match
    assert not divergent_check.semantic_match
    assert not divergent_check.verified


def test_artifact_tampering_fails_closed(tmp_path: Path) -> None:
    _, path = _artifact(tmp_path)
    payload = path.read_text(encoding="utf-8").replace("EGFR", "PTEN")
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="invalid"):
        load_artifact(path)


def test_verified_status_cannot_bypass_locked_production_counts(tmp_path: Path) -> None:
    cohort = _synthetic_cohort()
    fit = fit_gene_cross_validated(
        cohort.cnv["EGFR"], cohort.rna["EGFR"], cohort.protein["EGFR"], cohort.folds
    )
    assert fit is not None
    artifact = build_artifact(
        source_locks=(TABLE_S2_LOCK, HGNC_LOCK),
        cohort=CohortArtifactSummary(
            exact_common_measurement_count=75,
            patient_group_count=75,
            common_gene_count=1,
            fitted_gene_count=1,
            table_s3_flags_included=False,
        ),
        gene_evidence={"EGFR": gene_fit_document(fit)},
        derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
    )
    path = tmp_path / "wrong-counts.json"
    write_artifact(path, artifact)
    request = CisDosageEvidenceRequest(
        query_id="wrong-counts",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("EGFR",),
    )
    with pytest.raises(ArtifactIntegrityError, match="cohort invariants"):
        analyze_cis_dosage_evidence(request, artifact_path=path)


def test_profile_binds_exact_sources_and_local_only_claim_ceiling() -> None:
    profile = algorithm_profile()
    assert profile.public_http_mounted is False
    assert profile.redistribution_status == "local_only_terms_unverified"
    assert profile.claim_ceiling == "observational_cohort_association_not_causal"
    assert profile.numpy_version == "2.5.2"
    assert profile.constants.huber_k == 1.345
    assert profile.constants.maximum_irls_iterations == 30
    assert profile.constants.production_exact_common_measurements == 96
    assert profile.constants.production_patient_groups == 96
    assert profile.constants.production_common_genes == 10_430
    assert profile.constants.production_fitted_genes == 9_457
    assert profile.exact_source_locks == (TABLE_S2_LOCK, TABLE_S3_LOCK, HGNC_LOCK)
    assert profile.local_trust_boundary == "same_user_local_artifact_integrity_only"
    assert profile.cross_user_authenticity == "signed_manifest_required_not_provided"


def test_source_verifier_rejects_nonmatching_local_files(tmp_path: Path) -> None:
    s2 = tmp_path / "s2.xlsx"
    hgnc = tmp_path / "hgnc.tsv"
    s2.write_bytes(b"not-the-locked-workbook")
    hgnc.write_bytes(b"not-the-locked-hgnc-snapshot")
    result = verify_sources(table_s2=s2, hgnc=hgnc)
    assert not result.verified
    assert all(not item.verified for item in result.sources)


def test_prepared_synthetic_fitter_is_not_a_public_package_api() -> None:
    assert not hasattr(cptac_package, "fit_prepared_cohort")
    assert not hasattr(cptac_package, "fit_prepared_cohort_unverified")


def test_production_cohort_invariants_reject_synthetic_counts() -> None:
    with pytest.raises(FitNotEvaluableError, match="96-sample"):
        _assert_production_cohort_invariants(_synthetic_cohort())


def test_staged_snapshot_is_independent_of_later_source_swap(tmp_path: Path) -> None:
    content = b"exact-private-snapshot"
    lock = ExactSourceLock(
        source_id="synthetic-stage-test",
        sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        bytes=len(content),
        required_for_fit=True,
    )
    source = tmp_path / "source.bin"
    staged = tmp_path / "staged.bin"
    source.write_bytes(content)
    _stage_exact_file(source, staged, lock)
    source.write_bytes(b"swapped-after-staging")
    assert staged.read_bytes() == content
    staged.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_source_mutation_during_copy_fails_exact_digest_gate() -> None:
    expected = b"a" * 128
    lock = ExactSourceLock(
        source_id="synthetic-mutation-test",
        sha256="sha256:" + hashlib.sha256(expected).hexdigest(),
        bytes=len(expected),
        required_for_fit=True,
    )
    changed_midstream = io.BytesIO(b"a" * 64 + b"b" * 64)
    staged = io.BytesIO()
    with pytest.raises(SourceLockError, match="changed"):
        _copy_exact_stream(changed_midstream, staged, lock, block_bytes=64)


def test_duplicate_genes_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        CisDosageEvidenceRequest(
            query_id="duplicate-query",
            artifact_content_digest="sha256:" + "0" * 64,
            gene_symbols=("EGFR", "EGFR"),
        )


@pytest.mark.property
@given(st.permutations(("EGFR", "PTEN", "TP53", "CDKN2A")))
def test_request_digest_is_gene_order_invariant(order: list[str]) -> None:
    request = CisDosageEvidenceRequest(
        query_id="order-invariance",
        artifact_content_digest="sha256:" + "1" * 64,
        gene_symbols=tuple(order),
    )
    canonical = CisDosageEvidenceRequest(
        query_id="order-invariance",
        artifact_content_digest="sha256:" + "1" * 64,
        gene_symbols=("CDKN2A", "EGFR", "PTEN", "TP53"),
    )
    assert request.request_digest == canonical.request_digest


def test_convergence_gate_abstains_without_leaking_fit() -> None:
    cohort = _synthetic_cohort()
    fit = fit_gene_cross_validated(
        cohort.cnv["EGFR"], cohort.rna["EGFR"], cohort.protein["EGFR"], cohort.folds
    )
    assert fit is not None
    record = gene_fit_document(fit)
    coefficients = dict(record["coefficients"])
    coefficients["converged_protein_folds"] = 3
    record["coefficients"] = coefficients
    summary = CohortArtifactSummary(
        exact_common_measurement_count=75,
        patient_group_count=75,
        common_gene_count=1,
        fitted_gene_count=1,
        table_s3_flags_included=False,
    )
    artifact = build_artifact(
        source_locks=(TABLE_S2_LOCK, HGNC_LOCK),
        cohort=summary,
        gene_evidence={"EGFR": record},
        derivation_status=DerivationStatus.SYNTHETIC_UNVERIFIED,
    )
    evidence = service_module._gene_result("EGFR", artifact)
    assert evidence.support is EvidenceSupport.ABSTAINED
    assert evidence.coefficients is None


def test_artifact_content_digest_excludes_only_its_receipt_field(tmp_path: Path) -> None:
    artifact, _ = _artifact(tmp_path)
    document = artifact.model_dump(mode="json")
    assert artifact_content_digest(document) == artifact.artifact_content_digest
