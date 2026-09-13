from __future__ import annotations

import hashlib
import inspect
import io
import json
import pickle
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from pydantic import ValidationError

import glio_proteogen.adapters.api as central_api
import glio_proteogen.research.cptac_gbm_transcript_protein_discordance as package
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_cis_dosage.ooxml import PreparedCohort
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    artifact as artifact_module,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    canonical as canonical_module,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    fitter,
    service,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    model as model_module,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    profile as profile_module,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    source as source_module,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.artifact import (
    TranscriptProteinDiscordanceArtifact,
    build_artifact,
    load_artifact,
    write_artifact,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.canonical import (
    artifact_content_digest,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.contracts import (
    BootstrapEvidence,
    CohortArtifactSummary,
    DerivationStatus,
    DiscordancePattern,
    EvidenceSupport,
    FoldConditionalEvidence,
    GeneDiscordanceStatistics,
    GeneTranscriptProteinEvidence,
    ReplayVerificationRequest,
    TranscriptProteinDiscordanceProfile,
    TranscriptProteinDiscordanceRequest,
    TranscriptProteinDiscordanceResult,
    UnverifiedTranscriptProteinDiscordanceResult,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.contracts import (
    FiniteSampleInterval as ContractInterval,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.errors import (
    DiscordanceArtifactIntegrityError,
    DiscordanceFitNotEvaluableError,
    DiscordanceInputError,
    DiscordanceSourceLockError,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.model import (
    DiscordanceFitConfiguration,
    TranscriptProteinDiscordanceDevelopmentFit,
    fit_transcript_protein_discordance_gene,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.profile import (
    algorithm_profile,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.source import (
    EXACT_SOURCE_LOCKS,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

REQUEST_DIGEST_A = "sha256:" + "a" * 64
REQUEST_DIGEST_B = "sha256:" + "b" * 64
TEST_CONFIGURATION = DiscordanceFitConfiguration(bootstrap_replicates=16)


def _synthetic_gene(
    conditional_rna_slope: float,
    *,
    seed: int = 20_260_830,
    count: int = 100,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    folds = (np.arange(count) % 5).astype(np.int8)
    cnv = rng.normal(size=count).astype(np.float64)
    rna = (0.8 * cnv + rng.normal(scale=0.7, size=count)).astype(np.float64)
    protein = (0.7 * cnv + conditional_rna_slope * rna + rng.normal(scale=0.22, size=count)).astype(
        np.float64
    )
    return cnv, rna, protein, folds


def _fit(
    conditional_rna_slope: float = 1.4,
    *,
    digest: str = REQUEST_DIGEST_A,
) -> TranscriptProteinDiscordanceDevelopmentFit:
    values = _synthetic_gene(conditional_rna_slope)
    result = fit_transcript_protein_discordance_gene(
        *values,
        request_digest=digest,
        configuration=TEST_CONFIGURATION,
    )
    assert result is not None
    return result


def _point_projection(fit: TranscriptProteinDiscordanceDevelopmentFit) -> tuple[object, ...]:
    summary = fit.summary
    return (
        summary.total_patient_groups,
        summary.complete_patient_groups,
        summary.oof_patient_groups,
        summary.valid_folds,
        summary.full_model,
        summary.rna_only,
        summary.cnv_only,
        summary.training_median,
        summary.delta_r2_vs_rna_only,
        summary.delta_r2_vs_cnv_only,
        summary.conditional_rna_slope_median,
        summary.conditional_rna_slope_mad,
        summary.conditional_rna_slope_sign_stability,
    )


def _synthetic_artifact() -> TranscriptProteinDiscordanceArtifact:
    fit = _fit()
    statistics = fitter._statistics(fit.summary)
    return build_artifact(
        source_locks=EXACT_SOURCE_LOCKS,
        cohort=CohortArtifactSummary(
            exact_common_measurement_count=100,
            patient_group_count=100,
            common_gene_count=1,
            fitted_gene_count=1,
        ),
        attempted_gene_symbols=("EGFR",),
        gene_statistics={"EGFR": statistics},
        derivation_status=DerivationStatus.SYNTHETIC_UNVERIFIED,
    )


@pytest.fixture(scope="module")
def synthetic_artifact() -> TranscriptProteinDiscordanceArtifact:
    return _synthetic_artifact()


def _service_statistics() -> GeneDiscordanceStatistics:
    cnv, rna, protein, folds = _synthetic_gene(1.4, count=96)
    fit = fit_transcript_protein_discordance_gene(
        cnv,
        rna,
        protein,
        folds,
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert fit is not None
    payload = fitter._statistics(fit.summary).model_dump(mode="python")
    payload["bootstrap"]["requested_replicates"] = 128
    payload["bootstrap"]["successful_replicates"] = 128
    for name in (
        "full_r2",
        "delta_r2_vs_rna_only",
        "delta_r2_vs_cnv_only",
        "mae",
        "residual_mad",
        "conditional_rna_slope",
    ):
        payload["bootstrap"][name]["replicates"] = 128
    return GeneDiscordanceStatistics.model_validate(payload, strict=True)


@pytest.fixture(scope="module")
def trusted_artifact() -> TranscriptProteinDiscordanceArtifact:
    return build_artifact(
        source_locks=EXACT_SOURCE_LOCKS,
        cohort=CohortArtifactSummary(
            exact_common_measurement_count=96,
            patient_group_count=96,
            common_gene_count=10_430,
            fitted_gene_count=1,
        ),
        attempted_gene_symbols=("EGFR", "PTEN"),
        gene_statistics={"EGFR": _service_statistics()},
        derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
    )


def _install_artifact_loader(
    monkeypatch: pytest.MonkeyPatch,
    artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    payload = canonical_json_bytes(artifact)
    monkeypatch.setattr(
        service,
        "load_artifact",
        lambda _path: (artifact, artifact_module.artifact_byte_digest(payload)),
    )


def _trusted_result(
    monkeypatch: pytest.MonkeyPatch,
    artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> tuple[TranscriptProteinDiscordanceRequest, TranscriptProteinDiscordanceResult]:
    _install_artifact_loader(monkeypatch, artifact)
    request = TranscriptProteinDiscordanceRequest(
        query_id="trusted-query",
        artifact_content_digest=artifact.artifact_content_digest,
        gene_symbols=("PTEN", "EGFR"),
    )
    return request, service.analyze_transcript_protein_discordance(
        request,
        artifact_path=tmp_path / "loader-boundary.json",
    )


@pytest.mark.parametrize(
    ("truth", "expected_pattern"),
    [
        (1.4, DiscordancePattern.POSITIVE_CONDITIONAL_RNA_ASSOCIATION),
        (-1.4, DiscordancePattern.INVERSE_CONDITIONAL_RNA_ASSOCIATION),
    ],
)
def test_synthetic_conditional_direction_and_incremental_signal_are_recovered(
    truth: float,
    expected_pattern: DiscordancePattern,
) -> None:
    fit = _fit(truth)
    summary = fit.summary
    slope = summary.bootstrap.conditional_rna_slope
    delta = summary.bootstrap.delta_r2_vs_cnv_only

    assert summary.valid_folds == 5
    assert summary.oof_patient_groups == 100
    assert summary.conditional_rna_slope_sign_stability == 1.0
    assert summary.conditional_rna_slope_median == pytest.approx(truth, abs=0.08)
    assert delta.lower > 0.0
    if truth > 0.0:
        assert slope.lower > 0.0
    else:
        assert slope.upper < 0.0
    assert service._pattern(fitter._statistics(summary)) is expected_pattern


def test_cnv_only_null_does_not_invent_incremental_rna_direction() -> None:
    fit = _fit(0.0)
    summary = fit.summary
    slope = summary.bootstrap.conditional_rna_slope
    delta = summary.bootstrap.delta_r2_vs_cnv_only

    assert abs(summary.conditional_rna_slope_median) < 0.05
    assert slope.lower <= 0.0 <= slope.upper
    assert delta.lower <= 0.0 <= delta.upper
    assert service._pattern(fitter._statistics(summary)) not in {
        DiscordancePattern.POSITIVE_CONDITIONAL_RNA_ASSOCIATION,
        DiscordancePattern.INVERSE_CONDITIONAL_RNA_ASSOCIATION,
    }


def test_bootstrap_is_exactly_deterministic_and_digest_only_changes_bootstrap() -> None:
    first = _fit()
    repeated = _fit()
    different_seed = _fit(digest=REQUEST_DIGEST_B)

    assert first.summary == repeated.summary
    assert first.fold_trace == repeated.fold_trace
    for name in (
        "observed_protein",
        "full_model",
        "rna_only",
        "cnv_only",
        "training_median",
        "full_model_residual",
    ):
        assert np.array_equal(
            getattr(first.transient_oof, name),
            getattr(repeated.transient_oof, name),
            equal_nan=True,
        )

    assert _point_projection(first) == _point_projection(different_seed)
    assert first.fold_trace == different_seed.fold_trace
    assert first.summary.bootstrap.seed != different_seed.summary.bootstrap.seed


def test_joint_row_order_is_point_invariant_and_bootstrap_invariant_when_fold_order_is_stable() -> (
    None
):
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    baseline = fit_transcript_protein_discordance_gene(
        cnv,
        rna,
        protein,
        folds,
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert baseline is not None

    grouped_order = np.argsort(folds, kind="stable")
    grouped = fit_transcript_protein_discordance_gene(
        cnv[grouped_order],
        rna[grouped_order],
        protein[grouped_order],
        folds[grouped_order],
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert grouped is not None
    assert grouped.summary == baseline.summary
    assert grouped.fold_trace == baseline.fold_trace

    arbitrary_order = np.random.default_rng(91).permutation(len(folds))
    permuted = fit_transcript_protein_discordance_gene(
        cnv[arbitrary_order],
        rna[arbitrary_order],
        protein[arbitrary_order],
        folds[arbitrary_order],
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert permuted is not None
    assert permuted.summary == baseline.summary
    assert permuted.fold_trace == baseline.fold_trace
    inverse_order = np.argsort(arbitrary_order)
    for name in (
        "observed_protein",
        "full_model",
        "rna_only",
        "cnv_only",
        "training_median",
        "full_model_residual",
    ):
        assert np.array_equal(
            getattr(permuted.transient_oof, name)[inverse_order],
            getattr(baseline.transient_oof, name),
            equal_nan=True,
        )


def test_nan_missingness_is_complete_case_not_zero_imputation() -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    missing = np.asarray([0, 11, 22, 33, 44, 50, 61, 72, 83, 94])
    rna_with_missing = rna.copy()
    rna_with_missing[missing] = np.nan
    with_missing = fit_transcript_protein_discordance_gene(
        cnv,
        rna_with_missing,
        protein,
        folds,
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert with_missing is not None
    complete = np.isfinite(rna_with_missing)
    prefiltered = fit_transcript_protein_discordance_gene(
        cnv[complete],
        rna_with_missing[complete],
        protein[complete],
        folds[complete],
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert prefiltered is not None

    assert with_missing.summary.total_patient_groups == 100
    assert prefiltered.summary.total_patient_groups == 90
    assert _point_projection(with_missing)[1:] == _point_projection(prefiltered)[1:]
    assert with_missing.summary.complete_patient_groups == 90
    assert with_missing.summary.oof_patient_groups == 90
    assert np.all(np.isnan(with_missing.transient_oof.observed_protein[missing]))
    assert with_missing.summary.conditional_rna_slope_median > 1.2


def test_one_missing_fold_is_explicit_but_two_missing_folds_abstain() -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    one_missing = protein.copy()
    one_missing[folds == 0] = np.nan
    accepted = fit_transcript_protein_discordance_gene(
        cnv,
        rna,
        one_missing,
        folds,
        request_digest=REQUEST_DIGEST_A,
        configuration=TEST_CONFIGURATION,
    )
    assert accepted is not None
    assert accepted.summary.valid_folds == 4
    assert not accepted.fold_trace[0].valid
    assert accepted.fold_trace[0].failure_reason == "insufficient held-out complete cases"

    two_missing = protein.copy()
    two_missing[np.isin(folds, (0, 1))] = np.nan
    assert (
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            two_missing,
            folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )
        is None
    )


@pytest.mark.parametrize("constant_field", ["cnv", "rna", "protein"])
def test_constant_axes_abstain_instead_of_emitting_a_formula_score(constant_field: str) -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    values = {"cnv": cnv, "rna": rna, "protein": protein}
    values[constant_field] = np.ones(len(folds), dtype=np.float64)
    assert (
        fit_transcript_protein_discordance_gene(
            values["cnv"],
            values["rna"],
            values["protein"],
            folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )
        is None
    )


@pytest.mark.parametrize(
    ("mutation", "error", "match"),
    [
        ("list", TypeError, "exact NumPy ndarray"),
        ("integer", TypeError, "float32 or float64"),
        ("rank", ValueError, "one-dimensional"),
        ("infinity", ValueError, "contains infinity"),
        ("unaligned", ValueError, "exactly aligned"),
        ("fold_dtype", TypeError, "one-dimensional int8"),
        ("fold_domain", ValueError, "every integer zero through four"),
        ("digest", ValueError, "canonical lowercase sha256"),
    ],
)
def test_numerical_input_types_shapes_domains_and_digest_are_strict(
    mutation: str,
    error: type[Exception],
    match: str,
) -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    digest = REQUEST_DIGEST_A
    if mutation == "list":
        cnv = cnv.tolist()  # type: ignore[assignment]
    elif mutation == "integer":
        rna = rna.astype(np.int64)
    elif mutation == "rank":
        protein = protein[:, None]
    elif mutation == "infinity":
        cnv[0] = np.inf
    elif mutation == "unaligned":
        protein = protein[:-1]
    elif mutation == "fold_dtype":
        folds = folds.astype(np.int64)
    elif mutation == "fold_domain":
        folds[folds == 4] = 3
    elif mutation == "digest":
        digest = "sha256:" + "A" * 64
    with pytest.raises(error, match=match):
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            protein,
            folds,
            request_digest=digest,
            configuration=TEST_CONFIGURATION,
        )


def test_development_fit_and_oof_arrays_cannot_be_serialized_or_mutated() -> None:
    fit = _fit()
    assert "observed_protein" not in repr(fit)
    assert "transient_oof=" not in repr(fit)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(fit)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(fit.transient_oof)
    for array in (
        fit.transient_oof.observed_protein,
        fit.transient_oof.full_model,
        fit.transient_oof.full_model_residual,
    ):
        assert not array.flags.writeable
        with pytest.raises(ValueError, match="WRITEABLE"):
            array.flags.writeable = True


def test_development_summary_maps_to_strict_contract_and_private_fitter_artifact() -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    fit = _fit()
    statistics = fitter._statistics(fit.summary)
    assert statistics.full_model.n_oof == 100
    assert statistics.bootstrap.requested_replicates == 16
    assert statistics.bootstrap.successful_replicates == 16

    cohort = PreparedCohort(
        cnv={"EGFR": cnv},
        rna={"EGFR": rna},
        protein={"EGFR": protein},
        folds=folds,
        common_genes=("EGFR",),
        exact_common_measurement_count=100,
        patient_group_count=100,
    )
    artifact = fitter._fit_prepared_cohort_unverified(
        cohort,
        gene_symbols=("EGFR",),
        source_locks=EXACT_SOURCE_LOCKS,
        configuration=TEST_CONFIGURATION,
    )
    assert artifact.derivation_status is DerivationStatus.SYNTHETIC_UNVERIFIED
    assert artifact.cohort.fitted_gene_count == 1
    assert artifact.genes[0].gene_symbol == "EGFR"
    assert artifact.genes[0].statistics.bootstrap.requested_replicates == 16

    with pytest.raises(DiscordanceInputError, match="absent"):
        fitter._fit_prepared_cohort_unverified(
            cohort,
            gene_symbols=("PTEN",),
            source_locks=EXACT_SOURCE_LOCKS,
            configuration=TEST_CONFIGURATION,
        )


def test_private_fitter_rejects_empty_duplicate_and_unfittable_gene_sets() -> None:
    with pytest.raises(DiscordanceInputError, match="between one and 256"):
        fitter._validated_genes(())
    with pytest.raises(DiscordanceInputError, match="unique"):
        fitter._validated_genes(("EGFR", "EGFR"))

    cnv, rna, _, folds = _synthetic_gene(1.4)
    cohort = PreparedCohort(
        cnv={"EGFR": cnv},
        rna={"EGFR": rna},
        protein={"EGFR": np.ones(len(folds), dtype=np.float64)},
        folds=folds,
        common_genes=("EGFR",),
        exact_common_measurement_count=100,
        patient_group_count=100,
    )
    with pytest.raises(DiscordanceFitNotEvaluableError, match="no requested genes"):
        fitter._fit_prepared_cohort_unverified(
            cohort,
            gene_symbols=("EGFR",),
            source_locks=EXACT_SOURCE_LOCKS,
            configuration=TEST_CONFIGURATION,
        )


def test_query_contract_forbids_patient_measurements_paths_and_duplicate_genes() -> None:
    payload: dict[str, Any] = {
        "query_id": "query-1",
        "artifact_content_digest": "sha256:" + "1" * 64,
        "gene_symbols": ("EGFR",),
    }
    for forbidden in ("rna", "protein", "cnv", "folds", "artifact_path", "patient_id"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            TranscriptProteinDiscordanceRequest.model_validate(
                {**payload, forbidden: [1.0]},
                strict=True,
            )
    with pytest.raises(ValidationError, match="unique"):
        TranscriptProteinDiscordanceRequest.model_validate(
            {**payload, "gene_symbols": ("EGFR", "EGFR")},
            strict=True,
        )
    assert set(TranscriptProteinDiscordanceRequest.model_fields) == {
        "profile_id",
        "query_id",
        "artifact_content_digest",
        "gene_symbols",
    }


def test_artifact_and_contract_are_aggregate_only_and_deidentified(
    synthetic_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    encoded = canonical_json_bytes(synthetic_artifact)
    document = json.loads(encoded)
    cohort = document["cohort"]

    assert cohort["contains_patient_measurements"] is False
    assert cohort["contains_sample_headers"] is False
    assert cohort["contains_patient_identifiers_or_hashes"] is False
    assert cohort["contains_fold_membership"] is False
    assert cohort["contains_oof_predictions_or_residuals"] is False
    for forbidden in (
        b"observed_protein",
        b"full_model_residual",
        b"transient_oof",
        b"fold_trace",
        b'"patient_identifier":',
        b'"patient_identifier_hash":',
        b'"sample_header":',
        b"bootstrap_draws",
    ):
        assert forbidden not in encoded

    forged = synthetic_artifact.cohort.model_dump(mode="python")
    forged["contains_patient_measurements"] = True
    with pytest.raises(ValidationError):
        CohortArtifactSummary.model_validate(forged, strict=True)
    assert not hasattr(package, "_fit_prepared_cohort_unverified")


def test_artifact_digest_canonical_round_trip_and_no_overwrite(
    tmp_path: Path,
    synthetic_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    path = tmp_path / "discordance.json"
    byte_digest, byte_count = write_artifact(path, synthetic_artifact)
    loaded, loaded_byte_digest = load_artifact(path)

    assert loaded == synthetic_artifact
    assert loaded_byte_digest == byte_digest
    assert byte_count == len(path.read_bytes())
    assert synthetic_artifact.artifact_content_digest == artifact_content_digest(synthetic_artifact)
    with pytest.raises(DiscordanceArtifactIntegrityError, match="refusing to overwrite"):
        write_artifact(path, synthetic_artifact)


def test_artifact_builder_canonicalizes_source_lock_order(
    synthetic_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    rebuilt = build_artifact(
        source_locks=tuple(reversed(EXACT_SOURCE_LOCKS)),
        cohort=synthetic_artifact.cohort,
        attempted_gene_symbols=synthetic_artifact.attempted_gene_symbols,
        gene_statistics={entry.gene_symbol: entry.statistics for entry in synthetic_artifact.genes},
        derivation_status=synthetic_artifact.derivation_status,
    )

    assert rebuilt == synthetic_artifact


def test_artifact_loader_rejects_noncanonical_and_content_tampered_bytes(
    tmp_path: Path,
    synthetic_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_bytes(canonical_json_bytes(synthetic_artifact) + b"\n")
    with pytest.raises(DiscordanceArtifactIntegrityError, match="canonical form"):
        load_artifact(noncanonical)

    tampered = tmp_path / "tampered.json"
    document = synthetic_artifact.model_dump(mode="json")
    document["cohort"]["patient_group_count"] = 99
    tampered.write_bytes(canonical_json_bytes(document))
    with pytest.raises(DiscordanceArtifactIntegrityError, match="unavailable or invalid"):
        load_artifact(tampered)


def test_bounded_artifact_reader_stops_at_limit_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EndlessStream:
        def __init__(self) -> None:
            self.requests: list[int] = []

        def read(self, size: int) -> bytes:
            self.requests.append(size)
            return b"x" * size

    stream = EndlessStream()
    monkeypatch.setattr(artifact_module, "MAX_ARTIFACT_BYTES", 64)
    with pytest.raises(DiscordanceArtifactIntegrityError, match="exceeds"):
        artifact_module._read_bounded_artifact_stream(stream)  # type: ignore[arg-type]
    assert stream.requests == [65]


def test_synthetic_artifact_can_never_cross_the_runtime_service_gate(
    tmp_path: Path,
    synthetic_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    path = tmp_path / "synthetic.json"
    write_artifact(path, synthetic_artifact)
    request = TranscriptProteinDiscordanceRequest(
        query_id="synthetic-rejection",
        artifact_content_digest=synthetic_artifact.artifact_content_digest,
        gene_symbols=("EGFR",),
    )
    with pytest.raises(DiscordanceArtifactIntegrityError, match="not derived"):
        service.analyze_transcript_protein_discordance(request, artifact_path=path)


def test_profile_is_source_bound_local_only_and_has_no_central_route(tmp_path: Path) -> None:
    profile = algorithm_profile()
    assert profile.numpy_version == "2.5.2"
    assert profile.constants.bootstrap_replicates == 128
    assert profile.constants.bootstrap_coverage == 0.9
    assert profile.exact_source_locks == EXACT_SOURCE_LOCKS
    assert profile.redistribution_status == "local_only_terms_unverified"
    assert profile.public_http_mounted is False
    assert profile.public_cli_mounted is True
    assert profile.local_artifact_query_available is True
    assert profile.patient_measurement_input_permitted is False
    assert profile.runtime_behavior == "cohort_gene_query_never_patient_scoring"
    assert profile.claim_ceiling == "limited_observational_cohort_pattern"
    assert profile.local_trust_boundary == "same_user_local_artifact_integrity_only"
    assert profile.cross_user_authenticity == "signed_manifest_required_not_provided"

    assert "cptac_gbm_transcript_protein_discordance" not in inspect.getsource(central_api)
    app = central_api.create_app(tmp_path / "events.sqlite3")
    assert not any(
        "cptac-gbm-transcript-protein-discordance" in getattr(route, "path", "")
        for route in app.routes
    )


def test_canonical_request_result_and_profile_receipts_are_content_bound(
    monkeypatch: pytest.MonkeyPatch,
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> None:
    request, result = _trusted_result(monkeypatch, trusted_artifact, tmp_path)
    reversed_document = request.model_dump(mode="json")
    reversed_document["gene_symbols"] = ["PTEN", "EGFR"]

    assert canonical_module.normalized_request(reversed_document)["gene_symbols"] == [
        "EGFR",
        "PTEN",
    ]
    assert canonical_module.normalized_request(request)["gene_symbols"] == ["EGFR", "PTEN"]
    assert canonical_module.request_digest(reversed_document) == request.request_digest
    assert canonical_module.result_digest(result) == result.result_digest
    assert (
        canonical_module.profile_digest(algorithm_profile()) == algorithm_profile().profile_digest
    )


def test_contract_validator_matrix_rejects_incoherent_aggregate_receipts(
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    statistics = trusted_artifact.genes[0].statistics
    interval = statistics.bootstrap.full_r2
    with pytest.raises(ValidationError, match="lower bound exceeds"):
        ContractInterval(
            point_estimate=0.0,
            lower=1.0,
            upper=-1.0,
            replicates=16,
        )
    with pytest.raises(ValidationError, match="every valid fold"):
        FoldConditionalEvidence(
            valid_folds=4,
            converged_folds=5,
            conditional_rna_slope_median=0.0,
            conditional_rna_slope_mad=0.0,
        )

    below_gate = statistics.bootstrap.model_dump(mode="python")
    below_gate["successful_replicates"] = 1
    for name in (
        "full_r2",
        "delta_r2_vs_rna_only",
        "delta_r2_vs_cnv_only",
        "mae",
        "residual_mad",
        "conditional_rna_slope",
    ):
        below_gate[name]["replicates"] = 1
    with pytest.raises(ValidationError, match="below the 80% gate"):
        BootstrapEvidence.model_validate(below_gate, strict=True)

    mismatched_interval = statistics.bootstrap.model_dump(mode="python")
    mismatched_interval["full_r2"]["replicates"] = 127
    with pytest.raises(ValidationError, match="every successful replicate"):
        BootstrapEvidence.model_validate(mismatched_interval, strict=True)

    contradiction = statistics.model_dump(mode="python")
    contradiction["delta_r2_vs_rna_only"] += 0.01
    with pytest.raises(ValidationError, match="RNA-only delta R2"):
        GeneDiscordanceStatistics.model_validate(contradiction, strict=True)
    contradiction = statistics.model_dump(mode="python")
    contradiction["delta_r2_vs_cnv_only"] += 0.01
    with pytest.raises(ValidationError, match="CNV-only delta R2"):
        GeneDiscordanceStatistics.model_validate(contradiction, strict=True)
    contradiction = statistics.model_dump(mode="python")
    contradiction["bootstrap"]["full_r2"]["point_estimate"] += 0.01
    with pytest.raises(ValidationError, match="bootstrap point estimates"):
        GeneDiscordanceStatistics.model_validate(contradiction, strict=True)

    with pytest.raises(ValidationError, match="abstained genes cannot carry"):
        GeneTranscriptProteinEvidence(
            gene_symbol="EGFR",
            support=EvidenceSupport.ABSTAINED,
            pattern=DiscordancePattern.INDETERMINATE,
            statistics=statistics,
            reasons=("abstained",),
        )
    with pytest.raises(ValidationError, match="limited genes require"):
        GeneTranscriptProteinEvidence(
            gene_symbol="EGFR",
            support=EvidenceSupport.LIMITED,
            reasons=("missing evidence",),
        )
    with pytest.raises(ValidationError, match="exceeds the common-gene universe"):
        CohortArtifactSummary(
            exact_common_measurement_count=96,
            patient_group_count=96,
            common_gene_count=1,
            fitted_gene_count=2,
        )
    assert interval.lower <= interval.upper


def test_contract_result_and_profile_digest_validators_reject_each_binding_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> None:
    _, result = _trusted_result(monkeypatch, trusted_artifact, tmp_path)
    base = result.model_dump(mode="python")
    mutations: tuple[tuple[str, Any], ...] = (
        ("profile_digest", "sha256:" + "1" * 64),
        ("request_digest", "sha256:" + "2" * 64),
        ("artifact_content_digest", "sha256:" + "3" * 64),
        ("genes", tuple(reversed(base["genes"]))),
        ("result_digest", "sha256:" + "4" * 64),
    )
    messages = (
        "profile digest does not match provenance",
        "request digest does not match provenance",
        "artifact digest does not match provenance",
        "result genes must be unique and sorted",
        "result digest does not match canonical content",
    )
    for (field, value), message in zip(mutations, messages, strict=True):
        payload = dict(base)
        payload[field] = value
        with pytest.raises(ValidationError, match=message):
            TranscriptProteinDiscordanceResult.model_validate(payload, strict=True)

    profile_payload = algorithm_profile().model_dump(mode="python")
    profile_payload["profile_digest"] = "sha256:" + "5" * 64
    with pytest.raises(ValidationError, match="profile digest does not match"):
        TranscriptProteinDiscordanceProfile.model_validate(profile_payload, strict=True)


def test_service_lifecycle_covers_supported_abstained_and_replay_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> None:
    request, result = _trusted_result(monkeypatch, trusted_artifact, tmp_path)
    assert tuple(item.gene_symbol for item in result.genes) == ("EGFR", "PTEN")
    assert result.genes[0].support is EvidenceSupport.LIMITED
    assert result.genes[1].support is EvidenceSupport.ABSTAINED

    provided = UnverifiedTranscriptProteinDiscordanceResult.model_validate(
        result.model_dump(mode="python"),
        strict=True,
    )
    verified = service.verify_transcript_protein_discordance_replay(
        ReplayVerificationRequest(request=request, result=provided),
        artifact_path=tmp_path / "loader-boundary.json",
    )
    assert verified.verified
    assert verified.message == "Exact local discordance-artifact replay verified."

    tampered_payload = provided.model_dump(mode="python")
    tampered_payload.update(
        {
            "profile_digest": "sha256:" + "1" * 64,
            "request_digest": "sha256:" + "2" * 64,
            "artifact_content_digest": "sha256:" + "3" * 64,
            "result_digest": "sha256:" + "4" * 64,
        }
    )
    tampered = UnverifiedTranscriptProteinDiscordanceResult.model_validate(
        tampered_payload,
        strict=True,
    )
    failed = service.verify_transcript_protein_discordance_replay(
        ReplayVerificationRequest(request=request, result=tampered),
        artifact_path=tmp_path / "loader-boundary.json",
    )
    assert not failed.verified
    assert not failed.request_digest_match
    assert not failed.profile_digest_match
    assert not failed.artifact_digest_match
    assert not failed.provided_result_digest_valid
    assert not failed.recomputed_result_digest_match
    assert not failed.semantic_match
    assert failed.message == "Replay verification failed one or more exact content checks."


def test_service_rejects_every_trusted_artifact_boundary_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> None:
    statistics = trusted_artifact.genes[0].statistics
    invalid_bootstrap = statistics.bootstrap.model_copy(update={"requested_replicates": 16})
    invalid_statistics = statistics.model_copy(update={"bootstrap": invalid_bootstrap})
    invalid_entry = trusted_artifact.genes[0].model_copy(update={"statistics": invalid_statistics})
    wrong_lock = EXACT_SOURCE_LOCKS[0].model_copy(update={"bytes": EXACT_SOURCE_LOCKS[0].bytes + 1})
    variants = (
        trusted_artifact.model_copy(update={"profile_digest": "sha256:" + "9" * 64}),
        trusted_artifact.model_copy(
            update={"derivation_status": DerivationStatus.SYNTHETIC_UNVERIFIED}
        ),
        trusted_artifact.model_copy(
            update={
                "cohort": trusted_artifact.cohort.model_copy(update={"patient_group_count": 95})
            }
        ),
        trusted_artifact.model_copy(update={"genes": (invalid_entry,)}),
        trusted_artifact.model_copy(update={"source_locks": (wrong_lock, EXACT_SOURCE_LOCKS[1])}),
    )
    messages = (
        "profile digest",
        "not derived",
        "cohort invariants",
        "bootstrap profile",
        "source locks",
    )
    for artifact, message in zip(variants, messages, strict=True):
        with pytest.raises(DiscordanceArtifactIntegrityError, match=message):
            service._validate_artifact(artifact)

    _install_artifact_loader(monkeypatch, trusted_artifact)
    wrong_request = TranscriptProteinDiscordanceRequest(
        query_id="wrong-artifact",
        artifact_content_digest="sha256:" + "8" * 64,
        gene_symbols=("EGFR",),
    )
    with pytest.raises(DiscordanceArtifactIntegrityError, match="request artifact digest"):
        service.analyze_transcript_protein_discordance(
            wrong_request,
            artifact_path=tmp_path / "loader-boundary.json",
        )


def test_service_pattern_and_reason_policy_is_exhaustive(
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    base = trusted_artifact.genes[0].statistics
    bootstrap = base.bootstrap
    positive_delta = bootstrap.delta_r2_vs_cnv_only.model_copy(update={"lower": 0.1, "upper": 0.4})
    positive_full = bootstrap.full_r2.model_copy(update={"lower": 0.1, "upper": 0.8})
    crossing_slope = bootstrap.conditional_rna_slope.model_copy(
        update={"lower": -0.1, "upper": 0.1}
    )
    inverse_slope = bootstrap.conditional_rna_slope.model_copy(
        update={"lower": -1.0, "upper": -0.1}
    )
    no_delta = bootstrap.delta_r2_vs_cnv_only.model_copy(update={"lower": -0.4, "upper": 0.0})
    crossing_delta = bootstrap.delta_r2_vs_cnv_only.model_copy(update={"lower": -0.1, "upper": 0.1})
    patterns = (
        service._pattern(base),
        service._pattern(
            base.model_copy(
                update={
                    "bootstrap": bootstrap.model_copy(
                        update={
                            "delta_r2_vs_cnv_only": positive_delta,
                            "conditional_rna_slope": inverse_slope,
                        }
                    )
                }
            )
        ),
        service._pattern(
            base.model_copy(
                update={
                    "bootstrap": bootstrap.model_copy(
                        update={
                            "full_r2": positive_full,
                            "delta_r2_vs_cnv_only": positive_delta,
                            "conditional_rna_slope": crossing_slope,
                        }
                    )
                }
            )
        ),
        service._pattern(
            base.model_copy(
                update={
                    "bootstrap": bootstrap.model_copy(update={"delta_r2_vs_cnv_only": no_delta})
                }
            )
        ),
        service._pattern(
            base.model_copy(
                update={
                    "bootstrap": bootstrap.model_copy(
                        update={"delta_r2_vs_cnv_only": crossing_delta}
                    )
                }
            )
        ),
    )
    assert patterns == tuple(DiscordancePattern)
    assert all(service._reason(pattern) for pattern in patterns)


def test_service_distinguishes_attempted_abstention_from_never_attempted_gene() -> None:
    attempted = service._gene_result("PTEN", {}, frozenset({"PTEN"}))
    unattempted = service._gene_result("NF1", {}, frozenset({"PTEN"}))

    assert attempted.support is EvidenceSupport.ABSTAINED
    assert "predeclared for local fitting" in attempted.reasons[0]
    assert "no fit cleared" in attempted.reasons[0]
    assert unattempted.support is EvidenceSupport.ABSTAINED
    assert "not predeclared" in unattempted.reasons[0]
    assert "no computation was attempted" in unattempted.reasons[0]


def test_artifact_model_validator_rejects_every_internal_binding_mismatch(
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
) -> None:
    duplicate_entry = (trusted_artifact.genes[0], trusted_artifact.genes[0])
    variants = (
        trusted_artifact.model_copy(update={"schema_version": "wrong"}),
        trusted_artifact.model_copy(update={"algorithm_id": "wrong"}),
        trusted_artifact.model_copy(update={"genes": duplicate_entry}),
        trusted_artifact.model_copy(update={"attempted_gene_symbols": ("PTEN", "EGFR")}),
        trusted_artifact.model_copy(update={"attempted_gene_symbols": ("PTEN",)}),
        trusted_artifact.model_copy(
            update={"cohort": trusted_artifact.cohort.model_copy(update={"fitted_gene_count": 2})}
        ),
        trusted_artifact.model_copy(
            update={"source_locks": (EXACT_SOURCE_LOCKS[0], EXACT_SOURCE_LOCKS[0])}
        ),
        trusted_artifact.model_copy(update={"source_locks": tuple(reversed(EXACT_SOURCE_LOCKS))}),
        trusted_artifact.model_copy(update={"artifact_content_digest": "sha256:" + "0" * 64}),
    )
    messages = (
        "schema is not supported",
        "algorithm identity",
        "genes must be unique and sorted",
        "attempted artifact genes must be unique and sorted",
        "subset of attempted genes",
        "fitted-gene count",
        "source locks must be unique",
        "source locks must be sorted",
        "content digest",
    )
    for artifact, message in zip(variants, messages, strict=True):
        with pytest.raises(ValueError, match=message):
            artifact.content_is_canonical_and_bound()


def test_artifact_builder_and_writer_fail_closed_on_schema_size_and_publish_errors(
    monkeypatch: pytest.MonkeyPatch,
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> None:
    class RejectingAdapter:
        @staticmethod
        def validate_json(*_args: object, **_kwargs: object) -> None:
            error = ValidationError.from_exception_data("synthetic rejection", [])
            raise error

    statistics = trusted_artifact.genes[0].statistics
    monkeypatch.setattr(artifact_module, "_ARTIFACT_ADAPTER", RejectingAdapter())
    with pytest.raises(DiscordanceArtifactIntegrityError, match="does not satisfy its schema"):
        build_artifact(
            source_locks=EXACT_SOURCE_LOCKS,
            cohort=trusted_artifact.cohort,
            attempted_gene_symbols=trusted_artifact.attempted_gene_symbols,
            gene_statistics={"EGFR": statistics},
            derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
        )
    monkeypatch.undo()

    monkeypatch.setattr(artifact_module, "MAX_ARTIFACT_BYTES", 1)
    with pytest.raises(DiscordanceArtifactIntegrityError, match=r"generated.*exceeds"):
        build_artifact(
            source_locks=EXACT_SOURCE_LOCKS,
            cohort=trusted_artifact.cohort,
            attempted_gene_symbols=trusted_artifact.attempted_gene_symbols,
            gene_statistics={"EGFR": statistics},
            derivation_status=DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES,
        )
    with pytest.raises(DiscordanceArtifactIntegrityError, match="artifact exceeds"):
        write_artifact(tmp_path / "too-large.json", trusted_artifact)
    monkeypatch.undo()

    def fail_link(_source: object, _destination: object) -> None:
        error = OSError("link denied")
        raise error

    monkeypatch.setattr(artifact_module.os, "link", fail_link)
    with pytest.raises(DiscordanceArtifactIntegrityError, match="published atomically"):
        write_artifact(tmp_path / "link-failure.json", trusted_artifact)
    assert not tuple(tmp_path.glob(".link-failure.json.*.tmp"))
    monkeypatch.undo()

    def fail_temporary_file(**_kwargs: object) -> object:
        raise OSError

    monkeypatch.setattr(artifact_module, "NamedTemporaryFile", fail_temporary_file)
    with pytest.raises(DiscordanceArtifactIntegrityError, match="published atomically"):
        write_artifact(tmp_path / "temporary-failure.json", trusted_artifact)


def test_artifact_loader_preserves_integrity_errors_and_sanitizes_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_integrity(_path: Path) -> bytes:
        error = DiscordanceArtifactIntegrityError("bounded read failed")
        raise error

    monkeypatch.setattr(artifact_module, "_read_artifact_bytes", fail_integrity)
    with pytest.raises(DiscordanceArtifactIntegrityError, match="bounded read failed"):
        load_artifact(tmp_path / "ignored.json")
    monkeypatch.undo()

    with pytest.raises(DiscordanceArtifactIntegrityError, match="unavailable or invalid"):
        load_artifact(tmp_path / "missing.json")


def test_exact_source_stream_copy_and_file_staging_are_bounded_and_content_locked(
    tmp_path: Path,
) -> None:
    payload = b"locked source bytes"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    destination = io.BytesIO()
    source_module._copy_exact_stream(
        io.BytesIO(payload),
        destination,
        expected_bytes=len(payload),
        expected_sha256=digest,
        block_bytes=3,
    )
    assert destination.getvalue() == payload

    for malformed, expected_bytes, expected_digest in (
        (payload[:-1], len(payload), digest),
        (payload + b"x", len(payload), digest),
        (payload, len(payload), "sha256:" + "0" * 64),
    ):
        with pytest.raises(DiscordanceSourceLockError, match="changed"):
            source_module._copy_exact_stream(
                io.BytesIO(malformed),
                io.BytesIO(),
                expected_bytes=expected_bytes,
                expected_sha256=expected_digest,
                block_bytes=4,
            )

    source_path = tmp_path / "source.bin"
    staged_path = tmp_path / "staged.bin"
    source_path.write_bytes(payload)
    source_module._stage_exact_file(
        source_path,
        staged_path,
        expected_bytes=len(payload),
        expected_sha256=digest,
    )
    assert staged_path.read_bytes() == payload
    staged_path.chmod(0o600)

    existing = tmp_path / "existing.bin"
    existing.write_bytes(b"occupied")
    with pytest.raises(DiscordanceSourceLockError, match="staged privately"):
        source_module._stage_exact_file(
            source_path,
            existing,
            expected_bytes=len(payload),
            expected_sha256=digest,
        )
    bad_stage = tmp_path / "bad-stage.bin"
    with pytest.raises(DiscordanceSourceLockError, match="changed"):
        source_module._stage_exact_file(
            source_path,
            bad_stage,
            expected_bytes=len(payload),
            expected_sha256="sha256:" + "0" * 64,
        )
    bad_stage.chmod(0o600)


def test_exact_source_context_is_private_and_cleans_partial_or_complete_stages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_stage(
        _source: Path,
        destination: Path,
        *,
        expected_bytes: int,
        expected_sha256: str,
    ) -> None:
        assert expected_bytes > 0
        assert expected_sha256.startswith("sha256:")
        destination.write_bytes(b"staged")

    monkeypatch.setattr(source_module, "_stage_exact_file", fake_stage)
    with source_module._stage_exact_sources(
        table_s2=tmp_path / "table.xlsx",
        hgnc=tmp_path / "hgnc.tsv",
    ) as staged:
        root = staged.table_s2.parent
        assert staged.table_s2.read_bytes() == b"staged"
        assert staged.hgnc.read_bytes() == b"staged"
    assert not root.exists()

    calls = 0

    def fail_second_stage(
        _source: Path,
        destination: Path,
        **_kwargs: object,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            error = DiscordanceSourceLockError("second source failed")
            raise error
        destination.write_bytes(b"partial")

    monkeypatch.setattr(source_module, "_stage_exact_file", fail_second_stage)
    with (
        pytest.raises(DiscordanceSourceLockError, match="second source failed"),
        source_module._stage_exact_sources(
            table_s2=tmp_path / "table.xlsx",
            hgnc=tmp_path / "hgnc.tsv",
        ),
    ):
        pytest.fail("the context must not yield after a source-lock failure")


def test_fitter_validates_symbols_production_shape_and_local_receipt_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    trusted_artifact: TranscriptProteinDiscordanceArtifact,
    tmp_path: Path,
) -> None:
    with pytest.raises(DiscordanceInputError, match="symbols are invalid"):
        fitter._validated_genes(["EGFR"])
    with pytest.raises(DiscordanceFitNotEvaluableError, match="96-patient-group"):
        fitter._assert_production_cohort_invariants(
            SimpleNamespace(
                exact_common_measurement_count=95,
                patient_group_count=96,
                common_genes=tuple(range(10_430)),
            )
        )
    with pytest.raises(DiscordanceFitNotEvaluableError, match="common-gene universe"):
        fitter._assert_production_cohort_invariants(
            SimpleNamespace(
                exact_common_measurement_count=96,
                patient_group_count=96,
                common_genes=("EGFR",),
            )
        )

    cohort = SimpleNamespace(
        exact_common_measurement_count=96,
        patient_group_count=96,
        common_genes=tuple(str(index) for index in range(10_430)),
    )
    fitter._assert_production_cohort_invariants(cohort)

    @contextmanager
    def fake_sources(**_kwargs: object) -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(table_s2=tmp_path / "table.xlsx", hgnc=tmp_path / "hgnc.tsv")

    monkeypatch.setattr(fitter, "_stage_exact_sources", fake_sources)
    monkeypatch.setattr(fitter, "prepare_cohort", lambda *_args: cohort)
    monkeypatch.setattr(fitter, "_fit_cohort", lambda *_args, **_kwargs: trusted_artifact)
    monkeypatch.setattr(
        fitter,
        "write_artifact",
        lambda *_args: ("sha256:" + "6" * 64, 1_234),
    )
    receipt = fitter.fit_local_artifact(
        table_s2=tmp_path / "table.xlsx",
        hgnc=tmp_path / "hgnc.tsv",
        output=tmp_path / "artifact.json",
        gene_symbols=("EGFR",),
    )
    assert receipt.artifact_content_digest == trusted_artifact.artifact_content_digest
    assert receipt.artifact_byte_digest == "sha256:" + "6" * 64
    assert receipt.artifact_bytes == 1_234


def test_profile_rejects_an_unpinned_numpy_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profile_module.np, "__version__", "0.0.0")
    with pytest.raises(RuntimeError, match=r"requires NumPy 2\.5\.2"):
        profile_module.algorithm_profile()


@pytest.mark.parametrize(
    ("updates", "error", "message"),
    [
        ({"fold_count": True}, TypeError, "exact integer"),
        ({"fold_count": 4}, ValueError, "exactly five folds"),
        ({"minimum_train_complete": 2}, ValueError, "minima"),
        ({"minimum_valid_folds": 0}, ValueError, "between one and five"),
        ({"minimum_oof": 2}, ValueError, "minimum_oof"),
        ({"bootstrap_replicates": 15}, ValueError, "between 16 and 256"),
        ({"minimum_bootstrap_success_fraction": 0.5}, ValueError, "fraction"),
        ({"minimum_bootstrap_success_fraction": float("nan")}, ValueError, "finite float"),
        ({"interval_level": 0.8}, ValueError, "90% interval"),
        ({"quantization_decimals": 7}, ValueError, "eight-decimal"),
        ({"maximum_patient_groups": 59}, ValueError, "patient-group bound"),
        ({"maximum_patient_groups": 10_001}, ValueError, "locked bound"),
    ],
)
def test_model_configuration_is_exact_and_bounded(
    updates: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        DiscordanceFitConfiguration(**updates)  # type: ignore[arg-type]


def test_model_metric_interval_and_bootstrap_dataclasses_fail_closed() -> None:
    valid_metric = model_module.MetricSummary(
        patient_groups=60,
        spearman=None,
        r2_vs_fold_train_median=0.0,
        mae=0.0,
        residual_mad=0.0,
    )
    metric_mutations = (
        ({"patient_groups": 2}, "at least three"),
        ({"spearman": 2.0}, "spearman"),
        ({"r2_vs_fold_train_median": float("inf")}, "finite float"),
        ({"mae": -1.0}, "mae cannot"),
        ({"residual_mad": -1.0}, "residual_mad cannot"),
    )
    for updates, message in metric_mutations:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(valid_metric, **updates)

    valid_interval = model_module.FiniteSampleInterval(
        point_estimate=0.0,
        lower=-1.0,
        upper=1.0,
        confidence_level=0.9,
        replicates=16,
    )
    interval_mutations = (
        ({"point_estimate": float("nan")}, "finite float"),
        ({"lower": 2.0}, "bounds are reversed"),
        ({"confidence_level": 0.8}, "locked 90%"),
        ({"replicates": 0}, "at least one"),
    )
    for updates, message in interval_mutations:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(valid_interval, **updates)

    bootstrap = _fit().summary.bootstrap
    bootstrap_mutations = (
        ({"seed": -1}, "unsigned 64-bit"),
        ({"replicates_successful": 17}, "successful <= requested"),
        ({"full_model_r2": object()}, "exact FiniteSampleInterval"),
        (
            {"full_model_r2": replace(bootstrap.full_model_r2, replicates=15)},
            "every bootstrap interval",
        ),
    )
    for updates, message in bootstrap_mutations:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(bootstrap, **updates)


def test_fold_trace_and_aggregate_summary_invariants_are_exhaustive() -> None:
    fit = _fit()
    trace = fit.fold_trace[0]
    trace_mutations = (
        ({"fold": 5}, "outside zero through four"),
        ({"training_complete": -1}, "training_complete cannot"),
        ({"held_out_complete": -1}, "held_out_complete cannot"),
        ({"full_iterations": 0}, "must be positive"),
        ({"full_converged": 1}, "exact Boolean"),
        ({"failure_reason": 1}, "exact string"),
        ({"conditional_rna_slope": float("inf")}, "finite float"),
        ({"full_converged": False}, "valid fold traces require"),
        ({"valid": False, "failure_reason": None}, "invalid fold traces require"),
    )
    for updates, message in trace_mutations:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(trace, **updates)

    summary = fit.summary
    type_mutations = (
        "full_model",
        "rna_only",
        "cnv_only",
        "training_median",
        "bootstrap",
    )
    for field_name in type_mutations:
        with pytest.raises(TypeError, match="must be an exact"):
            replace(summary, **{field_name: object()})
    with pytest.raises(ValueError, match="counts do not reconcile"):
        replace(summary, complete_patient_groups=2)
    with pytest.raises(ValueError, match="outside one through five"):
        replace(summary, valid_folds=0)
    with pytest.raises(ValueError, match="same OOF patient set"):
        replace(
            summary,
            full_model=replace(summary.full_model, patient_groups=99),
        )
    with pytest.raises(ValueError, match="finite float"):
        replace(summary, delta_r2_vs_rna_only=float("nan"))
    with pytest.raises(ValueError, match="slope_mad cannot"):
        replace(summary, conditional_rna_slope_mad=-1.0)
    with pytest.raises(ValueError, match="stability must lie"):
        replace(summary, conditional_rna_slope_sign_stability=2.0)


def _immutable_transient(
    observed: np.ndarray,
    full: np.ndarray,
    rna: np.ndarray,
    cnv: np.ndarray,
    null: np.ndarray,
) -> model_module.TransientOofPredictions:
    residual = observed - full
    return model_module.TransientOofPredictions(
        observed_protein=model_module._immutable_float_array(observed),
        full_model=model_module._immutable_float_array(full),
        rna_only=model_module._immutable_float_array(rna),
        cnv_only=model_module._immutable_float_array(cnv),
        training_median=model_module._immutable_float_array(null),
        full_model_residual=model_module._immutable_float_array(residual),
    )


def test_transient_oof_arrays_reject_type_shape_storage_support_and_residual_mismatches() -> None:
    fit = _fit()
    transient = fit.transient_oof
    with pytest.raises(TypeError, match="observed_protein must be"):
        replace(transient, observed_protein=[1.0])
    with pytest.raises(TypeError, match="full_model must be an exact ndarray"):
        replace(transient, full_model=[1.0] * transient.patient_groups)

    float32 = np.frombuffer(
        np.zeros(transient.patient_groups, dtype=np.float32).tobytes(),
        dtype=np.float32,
    )
    with pytest.raises(ValueError, match="one-dimensional float64"):
        replace(transient, full_model=float32)
    with pytest.raises(ValueError, match="immutable byte-backed"):
        replace(transient, full_model=np.array(transient.full_model, copy=True))

    infinite = np.array(transient.full_model, copy=True)
    infinite[0] = np.inf
    with pytest.raises(ValueError, match="cannot contain infinities"):
        replace(transient, full_model=model_module._immutable_float_array(infinite))

    different_mask = np.array(transient.full_model, copy=True)
    different_mask[0] = np.nan
    with pytest.raises(ValueError, match="one exact support mask"):
        replace(transient, full_model=model_module._immutable_float_array(different_mask))

    wrong_residual = np.array(transient.full_model_residual, copy=True)
    wrong_residual[0] += 1.0
    with pytest.raises(ValueError, match="does not exactly match"):
        replace(
            transient,
            full_model_residual=model_module._immutable_float_array(wrong_residual),
        )
    with pytest.raises(TypeError, match="cannot be serialized"):
        transient.__getstate__()


def test_development_fit_reconciles_types_traces_and_transient_counts() -> None:
    fit = _fit()
    with pytest.raises(TypeError, match="configuration must"):
        replace(fit, configuration=object())
    with pytest.raises(TypeError, match="summary must"):
        replace(fit, summary=object())
    with pytest.raises(TypeError, match="fold_trace must"):
        replace(fit, fold_trace=list(fit.fold_trace))
    with pytest.raises(TypeError, match="fold_trace must"):
        replace(fit, fold_trace=(object(), *fit.fold_trace[1:]))
    with pytest.raises(TypeError, match="transient_oof must"):
        replace(fit, transient_oof=object())
    with pytest.raises(ValueError, match="one trace per fold"):
        replace(fit, fold_trace=fit.fold_trace[:-1])
    reordered = (replace(fit.fold_trace[0], fold=1), *fit.fold_trace[1:])
    with pytest.raises(ValueError, match="sorted and complete"):
        replace(fit, fold_trace=reordered)
    with pytest.raises(ValueError, match="valid-fold counts differ"):
        replace(fit, summary=replace(fit.summary, valid_folds=4))

    arrays = fit.transient_oof
    shorter = _immutable_transient(
        arrays.observed_protein[:-1],
        arrays.full_model[:-1],
        arrays.rna_only[:-1],
        arrays.cnv_only[:-1],
        arrays.training_median[:-1],
    )
    with pytest.raises(ValueError, match="total patient counts differ"):
        replace(fit, transient_oof=shorter)

    observed = np.array(arrays.observed_protein, copy=True)
    full = np.array(arrays.full_model, copy=True)
    rna = np.array(arrays.rna_only, copy=True)
    cnv = np.array(arrays.cnv_only, copy=True)
    null = np.array(arrays.training_median, copy=True)
    for item in (observed, full, rna, cnv, null):
        item[0] = np.nan
    reduced_support = _immutable_transient(observed, full, rna, cnv, null)
    with pytest.raises(ValueError, match="OOF patient counts differ"):
        replace(fit, transient_oof=reduced_support)
    with pytest.raises(TypeError, match="cannot be serialized"):
        fit.__getstate__()


def test_private_rank_metric_slope_sign_and_interval_failure_paths() -> None:
    short = np.asarray([1.0, 2.0], dtype=np.float64)
    constant = np.ones(4, dtype=np.float64)
    varying = np.arange(4, dtype=np.float64)
    assert model_module._spearman(short, short) is None
    assert model_module._spearman(constant, varying) is None
    assert model_module._spearman(varying, constant) is None

    assert model_module._metrics(short, short, short) is None
    assert model_module._metrics(varying, varying, varying) is None
    with np.errstate(over="ignore", invalid="ignore"):
        assert (
            model_module._metrics(
                np.asarray([1.0, 2.0, 3.0]),
                np.full(3, 1e308),
                np.zeros(3),
            )
            is None
        )

    robust = model_module.RobustFit(
        x_center=np.zeros(2),
        x_scale=np.ones(2),
        y_center=0.0,
        y_scale=1.0,
        beta=np.zeros(3),
        converged=True,
        iterations=1,
    )
    assert model_module._raw_conditional_rna_slope(replace(robust, beta=np.zeros(2))) is None
    assert (
        model_module._raw_conditional_rna_slope(replace(robust, x_scale=np.asarray([0.0, 1.0])))
        is None
    )
    assert model_module._sign_stability(()) == 0.0
    assert model_module._sign_stability((1.0, -1.0)) == 0.0
    with pytest.raises(ValueError, match="finite bootstrap values"):
        model_module._finite_sample_interval([], 0.0)
    with pytest.raises(ValueError, match="finite bootstrap values"):
        model_module._finite_sample_interval([float("nan")], 0.0)


def test_locked_128_replicate_interval_uses_conventional_nearest_rank() -> None:
    interval = model_module._finite_sample_interval(
        [float(value) for value in range(1, 129)],
        64.5,
    )
    assert interval.replicates == 128
    assert interval.lower == 7.0
    assert interval.upper == 122.0


def test_public_fit_input_and_early_abstention_branches_are_explicit() -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    with pytest.raises(TypeError, match="configuration must"):
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            protein,
            folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="folds must be an exact"):
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            protein,
            folds.tolist(),  # type: ignore[arg-type]
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )

    small_folds = (np.arange(59) % 5).astype(np.int8)
    with pytest.raises(ValueError, match="smaller than the minimum"):
        fit_transcript_protein_discordance_gene(
            cnv[:59],
            rna[:59],
            protein[:59],
            small_folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )
    bounded = DiscordanceFitConfiguration(
        minimum_train_complete=3,
        minimum_oof=3,
        maximum_patient_groups=5,
        bootstrap_replicates=16,
    )
    with pytest.raises(ValueError, match="exceeds the patient-group bound"):
        fit_transcript_protein_discordance_gene(
            cnv[:10],
            rna[:10],
            protein[:10],
            (np.arange(10) % 5).astype(np.int8),
            request_digest=REQUEST_DIGEST_A,
            configuration=bounded,
        )

    too_missing = protein.copy()
    too_missing[:41] = np.nan
    assert (
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            too_missing,
            folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )
        is None
    )


def test_cross_fit_rejects_unrecoverable_slopes_nonfinite_predictions_and_low_oof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    monkeypatch.setattr(model_module, "_raw_conditional_rna_slope", lambda _fit: None)
    assert model_module._cross_fit(cnv, rna, protein, folds, TEST_CONFIGURATION) is None
    monkeypatch.undo()

    class NonFiniteFit:
        beta = np.asarray([0.0, 1.0, 0.0])
        x_scale = np.ones(2)
        y_scale = 1.0
        iterations = 1
        converged = True

        @staticmethod
        def predict(values: np.ndarray) -> np.ndarray:
            return np.full(len(values), np.nan)

    monkeypatch.setattr(model_module, "fit_huber", lambda *_args: NonFiniteFit())
    assert model_module._cross_fit(cnv, rna, protein, folds, TEST_CONFIGURATION) is None
    monkeypatch.undo()

    one_fold_missing = protein.copy()
    one_fold_missing[folds == 0] = np.nan
    high_oof = DiscordanceFitConfiguration(
        minimum_oof=90,
        bootstrap_replicates=16,
    )
    assert model_module._cross_fit(cnv, rna, one_fold_missing, folds, high_oof) is None


def test_point_summary_rejects_missing_metrics_misaligned_support_and_nonfinite_slopes() -> None:
    observed = np.asarray([1.0, 2.0, 4.0, 7.0, 11.0], dtype=np.float64)
    null = np.full(5, 4.0, dtype=np.float64)
    base = model_module._CrossFit(
        observed=observed,
        full=observed + 0.1,
        rna_only=observed + 0.2,
        cnv_only=observed + 0.3,
        null=null,
        slopes=(1.0, 1.1, 0.9, 1.2),
        trace=(),
    )
    insufficient = replace(base, full=np.asarray([1.0, 2.0, np.nan, np.nan, np.nan]))
    assert model_module._point_summary(insufficient, total=5, complete=5) is None

    misaligned = replace(base, full=np.asarray([np.nan, 2.1, 4.1, 7.1, 11.1]))
    assert model_module._point_summary(misaligned, total=5, complete=5) is None

    nonfinite_slope = replace(base, slopes=(float("nan"),))
    assert model_module._point_summary(nonfinite_slope, total=5, complete=5) is None


def test_bootstrap_and_public_fit_abstain_when_resampling_or_summary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, protein, folds = _synthetic_gene(1.4)
    cross_fit = model_module._cross_fit(cnv, rna, protein, folds, TEST_CONFIGURATION)
    assert cross_fit is not None
    point = model_module._point_summary(cross_fit, total=100, complete=100)
    assert point is not None

    monkeypatch.setattr(model_module, "_cross_fit", lambda *_args: None)
    assert (
        model_module._bootstrap(
            cnv,
            rna,
            protein,
            folds,
            point,
            REQUEST_DIGEST_A,
            TEST_CONFIGURATION,
        )
        is None
    )
    monkeypatch.undo()

    monkeypatch.setattr(model_module, "_cross_fit", lambda *_args: cross_fit)
    monkeypatch.setattr(model_module, "_point_summary", lambda *_args, **_kwargs: None)
    assert (
        model_module._bootstrap(
            cnv,
            rna,
            protein,
            folds,
            point,
            REQUEST_DIGEST_A,
            TEST_CONFIGURATION,
        )
        is None
    )
    monkeypatch.undo()

    monkeypatch.setattr(model_module, "_point_summary", lambda *_args, **_kwargs: None)
    assert (
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            protein,
            folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )
        is None
    )
    monkeypatch.undo()

    monkeypatch.setattr(model_module, "_bootstrap", lambda *_args, **_kwargs: None)
    assert (
        fit_transcript_protein_discordance_gene(
            cnv,
            rna,
            protein,
            folds,
            request_digest=REQUEST_DIGEST_A,
            configuration=TEST_CONFIGURATION,
        )
        is None
    )
