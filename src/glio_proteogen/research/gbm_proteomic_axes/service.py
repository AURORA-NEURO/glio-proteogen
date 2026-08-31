"""Stateless service facade for published GBM proteomic-axis inference."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import cast

import numpy as np

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import computational_request_digest, request_digest, result_digest
from .contracts import (
    MAX_JSON_SAFE_INTEGER,
    MAX_TOP_DRIVERS,
    MIN_OBSERVED_MODEL_FEATURES,
    SUPPORTED_COVERAGE_FRACTION,
    SUPPORTED_SIGNATURE_IDS,
    GbmEvidenceSummary,
    GbmFeatureDriver,
    GbmNormalizationSummary,
    GbmProteinEvidenceState,
    GbmProteinMeasurement,
    GbmProteomicAxesProvenance,
    GbmProteomicAxesRequest,
    GbmProteomicAxesResult,
    GbmReplayVerificationRequest,
    GbmReplayVerificationResult,
    GbmSignatureEstimate,
    GbmSignatureSupport,
)
from .data.predictor import PredictionResult, SignaturePrediction, feature_names, predict_axes
from .profile import algorithm_profile, signature_display_name

_LIMITATIONS = (
    "Research use only: scores are not diagnostic, prognostic, treatment-selection, or clinical-decision outputs.",
    "The models estimate bulk-tissue proteomic signature activation and do not identify cell fractions, patient subtypes, or single-cell states.",
    "The published model fills every unmeasured model feature with numeric zero; this convention is not evidence of biological absence or suppression.",
    "Left-censored LFQ upper limits are preserved in the receipt but excluded from point prediction; they are not converted into negative observations.",
    "Coverage labels and the 32-feature abstention floor are repository safety policies, not validated biological or clinical thresholds.",
    "Bootstrap intervals propagate caller-supplied log2 measurement error only; they do not cover sampling, model-form, cohort-shift, or biological uncertainty.",
    "The source study and bundled demo concern glioblastoma research; results must not be generalized to other glioma entities without independent validation.",
)


def _selected_signatures(request: GbmProteomicAxesRequest) -> tuple[str, ...]:
    if not request.signature_ids:
        return SUPPORTED_SIGNATURE_IDS
    requested = frozenset(request.signature_ids)
    return tuple(signature_id for signature_id in SUPPORTED_SIGNATURE_IDS if signature_id in requested)


def _observed_abundances(request: GbmProteomicAxesRequest) -> dict[str, float]:
    return {
        item.gene_symbol: cast("float", item.lfq_intensity)
        for item in request.measurements
        if item.state is GbmProteinEvidenceState.OBSERVED
    }


def _seed_from_digest(digest: str) -> int:
    return int(digest.removeprefix("sha256:")[:16], 16) % (MAX_JSON_SAFE_INTEGER + 1)


def _evidence_summary(
    request: GbmProteomicAxesRequest,
    model_features: frozenset[str],
) -> GbmEvidenceSummary:
    counts = Counter(item.state for item in request.measurements)
    observed = tuple(
        item for item in request.measurements if item.state is GbmProteinEvidenceState.OBSERVED
    )
    observed_model = sum(item.gene_symbol in model_features for item in observed)
    return GbmEvidenceSummary(
        total_measurements=len(request.measurements),
        observed=counts[GbmProteinEvidenceState.OBSERVED],
        left_censored=counts[GbmProteinEvidenceState.LEFT_CENSORED],
        missing=counts[GbmProteinEvidenceState.MISSING],
        unsupported=counts[GbmProteinEvidenceState.UNSUPPORTED],
        observed_model_features=observed_model,
        observed_non_model_features=len(observed) - observed_model,
        observations_with_standard_error=sum(
            item.log2_standard_error is not None for item in observed
        ),
    )


def _support(prediction: SignaturePrediction) -> GbmSignatureSupport:
    if prediction.observed_feature_count < MIN_OBSERVED_MODEL_FEATURES:
        return GbmSignatureSupport.ABSTAINED
    fraction = prediction.observed_feature_count / prediction.model_feature_count
    if fraction >= SUPPORTED_COVERAGE_FRACTION:
        return GbmSignatureSupport.SUPPORTED
    return GbmSignatureSupport.LIMITED


def _driver_rows(
    prediction: SignaturePrediction,
    declared_by_gene: Mapping[str, GbmProteinMeasurement],
) -> tuple[GbmFeatureDriver, ...]:
    ranked = sorted(
        (
            (gene_symbol, float(contribution))
            for gene_symbol, contribution in prediction.contributions.items()
            if float(contribution) != 0.0
        ),
        key=lambda item: (-abs(item[1]), item[0]),
    )
    rows: list[GbmFeatureDriver] = []
    for gene_symbol, contribution in ranked[:MAX_TOP_DRIVERS]:
        declaration = declared_by_gene.get(gene_symbol)
        is_observed = (
            declaration is not None
            and declaration.state is GbmProteinEvidenceState.OBSERVED
        )
        rows.append(
            GbmFeatureDriver(
                gene_symbol=gene_symbol,
                signed_contribution=contribution,
                absolute_contribution=abs(contribution),
                declared_state=None if declaration is None else declaration.state,
                model_input_source="observed_lfq" if is_observed else "published_zero_fill",
            )
        )
    return tuple(rows)


def _bootstrap_scores(
    request: GbmProteomicAxesRequest,
    selected: tuple[str, ...],
    observed: Mapping[str, float],
    seed: int,
    cancellation: CancellationContext | None,
) -> dict[str, tuple[float, ...]]:
    if request.bootstrap_replicates == 0:
        return {}
    errors = {
        item.gene_symbol: item.log2_standard_error
        for item in request.measurements
        if item.state is GbmProteinEvidenceState.OBSERVED
        and item.log2_standard_error is not None
    }
    if not errors:
        return {}
    rng = np.random.default_rng(seed)
    genes = tuple(sorted(observed))
    log2_values = {gene: float(np.log2(observed[gene])) for gene in genes}
    samples: dict[str, list[float]] = {signature_id: [] for signature_id in selected}
    for _ in range(request.bootstrap_replicates):
        checkpoint(cancellation)
        perturbed: dict[str, float] = {}
        for gene in genes:
            standard_error = errors.get(gene)
            noise = 0.0 if standard_error is None else float(rng.normal(0.0, standard_error))
            log2_lfq = min(60.0, max(-30.0, log2_values[gene] + noise))
            perturbed[gene] = float(np.exp2(log2_lfq))
        replicate = predict_axes(perturbed, selected)
        for signature_id in selected:
            samples[signature_id].append(
                float(replicate.signatures[signature_id].unrounded_score)
            )
    checkpoint(cancellation)
    return {key: tuple(values) for key, values in samples.items()}


def _interval(
    score: float,
    values: tuple[float, ...] | None,
) -> tuple[float | None, float | None, int]:
    if not values:
        return None, None, 0
    lower, upper = np.quantile(np.asarray(values, dtype=np.float64), [0.05, 0.95])
    # Percentile intervals need not mathematically contain the point estimate. The
    # receipt interval is conservatively expanded so it never contradicts its score.
    bounded_lower = min(round(float(lower), 6), score)
    bounded_upper = max(round(float(upper), 6), score)
    return bounded_lower, bounded_upper, len(values)


def _abstained_signature(
    signature_id: str,
    *,
    observed_feature_count: int,
    model_feature_count: int,
    reason: str,
) -> GbmSignatureEstimate:
    missing = model_feature_count - observed_feature_count
    return GbmSignatureEstimate(
        signature_id=signature_id,
        display_name=signature_display_name(signature_id),
        support=GbmSignatureSupport.ABSTAINED,
        model_feature_count=model_feature_count,
        observed_feature_count=observed_feature_count,
        observed_feature_fraction=observed_feature_count / model_feature_count,
        missing_feature_count=missing,
        missing_feature_ratio=missing / model_feature_count,
        bootstrap_replicates_used=0,
        abstention_reason=reason,
    )


def _signature_rows(
    request: GbmProteomicAxesRequest,
    point: PredictionResult | None,
    selected: tuple[str, ...],
    bootstrap: Mapping[str, tuple[float, ...]],
) -> tuple[GbmSignatureEstimate, ...]:
    if point is None:
        model_feature_count = len(feature_names(selected[0]))
        return tuple(
            _abstained_signature(
                signature_id,
                observed_feature_count=0,
                model_feature_count=model_feature_count,
                reason="No observed positive LFQ measurement intersects the published model.",
            )
            for signature_id in selected
        )
    declared_by_gene = {item.gene_symbol: item for item in request.measurements}
    rows: list[GbmSignatureEstimate] = []
    for signature_id in selected:
        prediction = point.signatures[signature_id]
        support = _support(prediction)
        if support is GbmSignatureSupport.ABSTAINED:
            rows.append(
                _abstained_signature(
                    signature_id,
                    observed_feature_count=prediction.observed_feature_count,
                    model_feature_count=prediction.model_feature_count,
                    reason=(
                        "Observed model coverage is below the profile floor of "
                        f"{MIN_OBSERVED_MODEL_FEATURES} features."
                    ),
                )
            )
            continue
        published_score = float(prediction.score)
        lower, upper, replicates_used = _interval(
            published_score, bootstrap.get(signature_id)
        )
        observed_fraction = prediction.observed_feature_count / prediction.model_feature_count
        rows.append(
            GbmSignatureEstimate(
                signature_id=signature_id,
                display_name=signature_display_name(signature_id),
                support=support,
                published_score=published_score,
                lower_bound=lower,
                upper_bound=upper,
                model_intercept=float(prediction.intercept),
                model_feature_count=prediction.model_feature_count,
                observed_feature_count=prediction.observed_feature_count,
                observed_feature_fraction=observed_fraction,
                missing_feature_count=prediction.missing_feature_count,
                missing_feature_ratio=float(prediction.missing_feature_ratio),
                bootstrap_replicates_used=replicates_used,
                top_feature_drivers=_driver_rows(prediction, declared_by_gene),
            )
        )
    return tuple(rows)


def analyze_gbm_proteomic_axes(
    request: GbmProteomicAxesRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmProteomicAxesResult:
    """Run published signature models without persisting input or output."""

    checkpoint(cancellation)
    profile = algorithm_profile()
    selected = _selected_signatures(request)
    common_features = frozenset(feature_names(selected[0]))
    observed = _observed_abundances(request)
    evidence = _evidence_summary(request, common_features)
    canonical_request = request_digest(request)
    computational = computational_request_digest(request)
    seed = _seed_from_digest(computational)

    point = predict_axes(observed, selected) if observed else None
    bootstrap = (
        _bootstrap_scores(request, selected, observed, seed, cancellation)
        if point is not None
        and point.signatures[selected[0]].observed_feature_count
        >= MIN_OBSERVED_MODEL_FEATURES
        else {}
    )
    signatures = _signature_rows(request, point, selected, bootstrap)
    normalization = GbmNormalizationSummary(
        geometric_mean=None if point is None else float(point.geometric_mean),
        normalization_factor=None if point is None else float(point.normalization_factor),
        positive_input_proteins=len(observed),
    )
    provenance = GbmProteomicAxesProvenance(
        profile_digest=profile.profile_digest,
        request_digest=canonical_request,
        computational_digest=computational,
        deterministic_seed=seed,
        numpy_version=profile.numpy_version,
        source_repository_url=profile.source.repository_url,
        source_commit=profile.source.repository_commit,
        original_model_digest=profile.source.original_model_digest,
        converted_artifact_digest=profile.source.converted_artifact_digest,
        observation_source_digests=tuple(
            item.provenance_digest
            for item in sorted(request.measurements, key=lambda item: item.gene_symbol)
        ),
    )
    payload = {
        "algorithm_id": "gbm-proteomic-axes",
        "algorithm_version": "1.0.0",
        "profile_id": "gbm-proteomic-axes/1.0.0",
        "profile_digest": profile.profile_digest,
        "request_digest": canonical_request,
        "result_digest": "sha256:" + "0" * 64,
        "sample_id": request.sample_id,
        "normalization": normalization,
        "evidence": evidence,
        "signatures": signatures,
        "provenance": provenance,
        "limitations": _LIMITATIONS,
        "research_use_only": True,
        "non_prescriptive": True,
    }
    result = GbmProteomicAxesResult.model_validate(
        {**payload, "result_digest": result_digest(payload)}
    )
    checkpoint(cancellation)
    return result


def verify_gbm_proteomic_axes_replay(
    verification: GbmReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmReplayVerificationResult:
    """Recompute a request and compare the complete content-bound receipt."""

    provided = verification.result
    checkpoint(cancellation)
    current_profile = algorithm_profile()
    canonical_request = request_digest(verification.request)
    recomputed = analyze_gbm_proteomic_axes(
        verification.request,
        cancellation=cancellation,
    )
    request_match = (
        provided.request_digest == canonical_request
        and recomputed.request_digest == canonical_request
    )
    profile_match = (
        provided.profile_digest == current_profile.profile_digest
        and recomputed.profile_digest == provided.profile_digest
    )
    model_source_match = (
        provided.provenance.source_commit == current_profile.source.repository_commit
        and provided.provenance.original_model_digest
        == current_profile.source.original_model_digest
        and provided.provenance.converted_artifact_digest
        == current_profile.source.converted_artifact_digest
    )
    payload_match = (
        provided.result_digest == result_digest(provided)
        and provided.result_digest == recomputed.result_digest
    )
    semantic_match = provided.model_dump(
        mode="json", exclude={"result_digest"}
    ) == recomputed.model_dump(mode="json", exclude={"result_digest"})
    verified = all(
        (request_match, profile_match, model_source_match, payload_match, semantic_match)
    )
    checkpoint(cancellation)
    return GbmReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        model_source_match=model_source_match,
        result_digest_match=payload_match,
        semantic_match=semantic_match,
        provided_result_digest=provided.result_digest,
        recomputed_result_digest=recomputed.result_digest,
        recomputed_request_digest=canonical_request,
        message=(
            "Replay exactly matches the deterministic published-model receipt."
            if verified
            else "Replay differs from the supplied receipt; no result claims are accepted."
        ),
    )


__all__ = ["analyze_gbm_proteomic_axes", "verify_gbm_proteomic_axes_replay"]
