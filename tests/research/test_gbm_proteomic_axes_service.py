"""Contracts, scientific wrapper semantics, and replay for GBM proteomic axes."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbm_proteomic_axes import (
    SUPPORTED_SIGNATURE_IDS,
    GbmProteinEvidenceState,
    GbmProteinMeasurement,
    GbmProteomicAxesRequest,
    GbmReplayVerificationRequest,
    GbmSignatureSupport,
    UnverifiedGbmProteomicAxesResult,
    algorithm_profile,
    analyze_gbm_proteomic_axes,
    computational_request_digest,
    synthetic_demo_request,
    verify_gbm_proteomic_axes_replay,
)
from glio_proteogen.research.gbm_proteomic_axes.data.predictor import (
    MODEL_FEATURE_COUNT,
    feature_names,
    predict_axes,
)

_DATA = (
    Path(__file__).parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "gbm_proteomic_axes"
    / "data"
)
_SOURCE_DIGEST = sha256_digest({"fixture": "gbm-axes-service"})
_EXPECTED_SAMPLE_1 = {
    "SWEET_KRAS_TARGETS_UP": -0.5897,
    "HALLMARK_MYC_TARGETS_V1": -0.3933,
    "WINTER_HYPOXIA_UP": -0.1878,
    "VERHAAK_GLIOBLASTOMA_MESENCHYMAL": -1.0937,
    "VERHAAK_GLIOBLASTOMA_NEURAL": 0.9894,
    "VERHAAK_GLIOBLASTOMA_PRONEURAL": 0.8723,
    "EGFR_UP.V1_UP": -1.2940,
}


def _measurement(
    symbol: str,
    state: GbmProteinEvidenceState,
    *,
    intensity: float | None = None,
    upper_limit: float | None = None,
    standard_error: float | None = None,
) -> GbmProteinMeasurement:
    return GbmProteinMeasurement(
        gene_symbol=symbol,
        state=state,
        lfq_intensity=intensity,
        lfq_upper_limit=upper_limit,
        log2_standard_error=standard_error,
        provenance_digest=_SOURCE_DIGEST,
    )


def _oracle_request(*, non_model: float | None = None) -> GbmProteomicAxesRequest:
    fixture = json.loads(
        gzip.decompress((_DATA / "diamandis_sample_proteomics_v1.json.gz").read_bytes())
    )
    values = fixture["samples"]["sample_1"]
    measurements = [
        _measurement(symbol, GbmProteinEvidenceState.OBSERVED, intensity=float(value))
        for symbol, value in zip(fixture["gene_symbols"], values, strict=True)
        if value > 0
    ]
    if non_model is not None:
        measurements.append(
            _measurement(
                "ZZZNONMODEL",
                GbmProteinEvidenceState.OBSERVED,
                intensity=non_model,
            )
        )
    return GbmProteomicAxesRequest(
        sample_id="diamandis.oracle.sample1",
        measurements=tuple(measurements),
        bootstrap_replicates=0,
    )


def test_profile_is_namespaced_source_bound_and_importable() -> None:
    profile = algorithm_profile()
    assert profile.profile_id == "gbm-proteomic-axes/1.0.0"
    assert profile.numpy_version == "2.5.2"
    assert profile.source.original_model_digest.startswith("sha256:")
    assert profile.source.converted_artifact_digest.startswith("sha256:")
    assert profile.source.repository_commit == "8d8c5725a82ef9505562e25fe2c5ea19fe608195"
    assert tuple(item.signature_id for item in profile.signatures) == SUPPORTED_SIGNATURE_IDS
    assert profile.constants.missing_feature_interpretation == "not_biological_absence"
    assert profile.limits.max_measurements == 8_192
    assert profile.limits.max_request_bytes == 2_097_152


def test_every_exact_upstream_model_feature_is_contract_valid() -> None:
    model_features = feature_names(SUPPORTED_SIGNATURE_IDS[0])
    assert len(model_features) == MODEL_FEATURE_COUNT
    for symbol in model_features:
        measurement = _measurement(symbol, GbmProteinEvidenceState.MISSING)
        assert measurement.gene_symbol == symbol
    assert "C11orf54" in model_features


def test_evidence_states_are_explicit_and_numeric_fields_are_closed() -> None:
    _measurement("EGFR", GbmProteinEvidenceState.OBSERVED, intensity=1.0)
    _measurement("CA9", GbmProteinEvidenceState.LEFT_CENSORED, upper_limit=0.1)
    _measurement("PTEN", GbmProteinEvidenceState.MISSING)
    _measurement("NF1", GbmProteinEvidenceState.UNSUPPORTED)

    with pytest.raises(ValidationError, match="requires LFQ intensity"):
        _measurement("EGFR", GbmProteinEvidenceState.OBSERVED)
    with pytest.raises(ValidationError, match="upper limit"):
        _measurement(
            "CA9",
            GbmProteinEvidenceState.LEFT_CENSORED,
            intensity=1.0,
        )
    with pytest.raises(ValidationError, match="cannot carry numeric"):
        _measurement("PTEN", GbmProteinEvidenceState.MISSING, intensity=1.0)
    with pytest.raises(ValidationError, match="greater than 0"):
        _measurement("EGFR", GbmProteinEvidenceState.OBSERVED, intensity=0.0)


def test_request_rejects_duplicate_symbols_signatures_and_ambiguous_bootstraps() -> None:
    observed = _measurement("EGFR", GbmProteinEvidenceState.OBSERVED, intensity=1.0)
    with pytest.raises(ValidationError, match="gene symbols must be unique"):
        GbmProteomicAxesRequest(
            sample_id="duplicate.symbol",
            measurements=(observed, observed),
        )
    with pytest.raises(ValidationError, match="signature identifiers must be unique"):
        GbmProteomicAxesRequest(
            sample_id="duplicate.signature",
            measurements=(observed,),
            signature_ids=("EGFR_UP.V1_UP", "EGFR_UP.V1_UP"),
        )
    with pytest.raises(ValidationError, match="unsupported signature"):
        GbmProteomicAxesRequest(
            sample_id="unknown.signature",
            measurements=(observed,),
            signature_ids=("NOT_A_MODEL",),
        )
    with pytest.raises(ValidationError, match="zero or at least eight"):
        GbmProteomicAxesRequest(
            sample_id="bad.bootstrap",
            measurements=(observed,),
            bootstrap_replicates=7,
        )


def test_service_matches_published_oracle_without_zero_measurement_coercion() -> None:
    request = _oracle_request()
    result = analyze_gbm_proteomic_axes(request)
    observed = {item.gene_symbol: item.lfq_intensity for item in request.measurements}
    direct = predict_axes(observed)

    assert len(request.measurements) == 3_450
    assert result.normalization.geometric_mean == direct.geometric_mean
    assert result.normalization.normalization_factor == direct.normalization_factor
    assert result.evidence.observed_model_features == 2_934
    assert result.evidence.observed_non_model_features == 516
    assert result.evidence.missing == 0
    for estimate in result.signatures:
        assert estimate.support is GbmSignatureSupport.SUPPORTED
        assert estimate.published_score == _EXPECTED_SAMPLE_1[estimate.signature_id]
        assert estimate.published_score == direct.signatures[estimate.signature_id].score
        assert estimate.observed_feature_count == 2_934
        assert estimate.missing_feature_ratio == pytest.approx(91 / 3_025)
        assert all(
            driver.contribution_semantics == "summed_tree_path_not_causal_or_shap"
            for driver in estimate.top_feature_drivers
        )


def test_non_model_positive_protein_changes_normalization_exactly_like_upstream() -> None:
    request = _oracle_request(non_model=1.0)
    result = analyze_gbm_proteomic_axes(request)
    observed = {item.gene_symbol: item.lfq_intensity for item in request.measurements}
    direct = predict_axes(observed)
    baseline = analyze_gbm_proteomic_axes(_oracle_request())

    assert result.normalization.geometric_mean == direct.geometric_mean
    assert result.normalization.normalization_factor == direct.normalization_factor
    assert result.normalization.geometric_mean != baseline.normalization.geometric_mean
    observed_scores = {item.signature_id: item.published_score for item in result.signatures}
    direct_scores = {name: item.score for name, item in direct.signatures.items()}
    baseline_scores = {item.signature_id: item.published_score for item in baseline.signatures}
    assert observed_scores == direct_scores
    assert observed_scores != baseline_scores
    assert result.evidence.observed_non_model_features == 517


def test_inactive_evidence_changes_receipt_but_not_numerics_or_rng_domain() -> None:
    base = synthetic_demo_request().model_copy(update={"bootstrap_replicates": 8})
    available = [
        symbol
        for symbol in feature_names(SUPPORTED_SIGNATURE_IDS[0])
        if symbol not in {item.gene_symbol for item in base.measurements}
    ]
    first = base.model_copy(
        update={
            "measurements": (
                *base.measurements,
                _measurement(available[0], GbmProteinEvidenceState.MISSING),
            )
        }
    )
    second = base.model_copy(
        update={
            "measurements": (
                *base.measurements,
                _measurement(available[1], GbmProteinEvidenceState.UNSUPPORTED),
            )
        }
    )
    first_result = analyze_gbm_proteomic_axes(first)
    second_result = analyze_gbm_proteomic_axes(second)

    assert computational_request_digest(first) == computational_request_digest(second)
    assert first.request_digest != second.request_digest
    assert first_result.provenance.deterministic_seed == second_result.provenance.deterministic_seed
    assert first_result.normalization == second_result.normalization
    assert first_result.signatures == second_result.signatures
    assert first_result.result_digest != second_result.result_digest


def test_low_coverage_abstains_and_left_censor_never_becomes_negative() -> None:
    request = GbmProteomicAxesRequest(
        sample_id="low.coverage",
        measurements=(
            _measurement("EGFR", GbmProteinEvidenceState.OBSERVED, intensity=2_000_000.0),
            _measurement(
                "CA9",
                GbmProteinEvidenceState.LEFT_CENSORED,
                upper_limit=100_000.0,
            ),
            _measurement("PTEN", GbmProteinEvidenceState.MISSING),
            _measurement("NF1", GbmProteinEvidenceState.UNSUPPORTED),
        ),
        signature_ids=("EGFR_UP.V1_UP",),
        bootstrap_replicates=0,
    )
    result = analyze_gbm_proteomic_axes(request)
    estimate = result.signatures[0]
    assert estimate.support is GbmSignatureSupport.ABSTAINED
    assert estimate.published_score is None
    assert estimate.lower_bound is None
    assert estimate.top_feature_drivers == ()
    assert result.evidence.left_censored == 1
    assert result.evidence.absent_feature_semantics == (
        "published_zero_fill_not_biological_absence"
    )


def test_all_inactive_evidence_abstains_without_fabricating_normalization() -> None:
    request = GbmProteomicAxesRequest(
        sample_id="inactive.only",
        measurements=(
            _measurement(
                "CA9",
                GbmProteinEvidenceState.LEFT_CENSORED,
                upper_limit=100_000.0,
            ),
            _measurement("PTEN", GbmProteinEvidenceState.MISSING),
            _measurement("NF1", GbmProteinEvidenceState.UNSUPPORTED),
        ),
        signature_ids=("EGFR_UP.V1_UP",),
        bootstrap_replicates=8,
    )
    result = analyze_gbm_proteomic_axes(request)
    assert result.normalization.geometric_mean is None
    assert result.normalization.normalization_factor is None
    assert result.normalization.positive_input_proteins == 0
    assert result.signatures[0].support is GbmSignatureSupport.ABSTAINED
    assert "No observed positive LFQ" in result.signatures[0].abstention_reason


def test_requested_bootstrap_without_standard_errors_makes_no_interval_claim() -> None:
    demo = synthetic_demo_request()
    measurements = tuple(
        item.model_copy(update={"log2_standard_error": None})
        if item.state is GbmProteinEvidenceState.OBSERVED
        else item
        for item in demo.measurements
    )
    request = demo.model_copy(
        update={"measurements": measurements, "bootstrap_replicates": 8}
    )
    result = analyze_gbm_proteomic_axes(request)
    assert all(item.bootstrap_replicates_used == 0 for item in result.signatures)
    assert all(item.lower_bound is None and item.upper_bound is None for item in result.signatures)


def test_deterministic_replay_accepts_exact_and_rejects_forged_receipts() -> None:
    request = synthetic_demo_request().model_copy(update={"bootstrap_replicates": 8})
    result = analyze_gbm_proteomic_axes(request)
    verification = verify_gbm_proteomic_axes_replay(
        GbmReplayVerificationRequest(request=request, result=result)
    )
    assert verification.verified is True

    forged_document = result.model_dump(mode="json")
    forged_document["result_digest"] = "sha256:" + "f" * 64
    forged = UnverifiedGbmProteomicAxesResult.model_validate_json(json.dumps(forged_document))
    rejected = verify_gbm_proteomic_axes_replay(
        GbmReplayVerificationRequest(request=request, result=forged)
    )
    assert rejected.verified is False
    assert rejected.result_digest_match is False


def test_input_order_is_semantically_and_numerically_invariant() -> None:
    request = synthetic_demo_request().model_copy(update={"bootstrap_replicates": 8})
    reversed_request = request.model_copy(
        update={"measurements": tuple(reversed(request.measurements))}
    )
    assert request.request_digest == reversed_request.request_digest
    assert analyze_gbm_proteomic_axes(request) == analyze_gbm_proteomic_axes(reversed_request)

    selected = request.model_copy(
        update={
            "signature_ids": (
                "EGFR_UP.V1_UP",
                "SWEET_KRAS_TARGETS_UP",
            )
        }
    )
    selected_reversed = selected.model_copy(
        update={"signature_ids": tuple(reversed(selected.signature_ids))}
    )
    assert selected.request_digest == selected_reversed.request_digest
    assert analyze_gbm_proteomic_axes(selected) == analyze_gbm_proteomic_axes(
        selected_reversed
    )
