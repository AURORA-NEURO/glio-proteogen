"""Exact NumPy inference for the published GBMPurity multilayer perceptron."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest, sha256_digest
from .catalog import GbmRnaPurityCatalog, gbm_rna_purity_catalog
from .contracts import (
    MINIMUM_MODEL_GENE_COVERAGE,
    SUPPORTED_MODEL_GENE_COVERAGE,
    TOP_ATTRIBUTION_LIMIT,
    AttributionDirection,
    ClippingState,
    GbmRnaPurityDiagnostics,
    GbmRnaPurityEstimate,
    GbmRnaPurityProvenance,
    GbmRnaPurityRequest,
    GbmRnaPurityResult,
    GeneLocalAttribution,
    HiddenActivationTrace,
    LocalLinearExplanation,
    ModelCoverage,
    PuritySupport,
    UnverifiedGbmRnaPurityResult,
    empty_result_digest,
)
from .errors import GbmRnaPurityInferenceError
from .profile import CONSTANTS, algorithm_profile

Float32Vector = NDArray[np.float32]
Float64Vector = NDArray[np.float64]

_LIMITATIONS: Final = (
    "Research-use-only estimate from a published single pretrained model; not clinical truth.",
    (
        "The intended population is primary IDH-wildtype glioblastoma bulk RNA-seq; "
        "other tumors, modalities, and preprocessing are out of scope."
    ),
    (
        "The output is one estimated malignant-cell fraction, not immune/stromal "
        "composition, spatial context, cell state, diagnosis, prognosis, or treatment response."
    ),
    (
        "Missing model genes are zero-filled only after the published 80% overlap gate; "
        "the source warns that missing genes tend to reduce estimates."
    ),
    (
        "The published artifact is one MLP, so this lane does not invent a bootstrap "
        "interval or calibrated predictive uncertainty."
    ),
    (
        "Local active-ReLU attributions explain this numerical forward pass only; they "
        "are not causal genes, biomarkers, or globally calibrated feature importance."
    ),
    "Input assay, sampling, RNA quality, library composition, and cohort shift remain limitations.",
)


@dataclass(frozen=True, slots=True)
class _ForwardPass:
    transformed: Float32Vector
    first_preactivation: Float32Vector
    first_activation: Float32Vector
    second_preactivation: Float32Vector
    second_activation: Float32Vector
    raw_output: float


def _q(value: float) -> float:
    result = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if result == 0.0 else result


def _validate_direct_request(request: GbmRnaPurityRequest) -> GbmRnaPurityRequest:
    """Protect direct Python callers that bypass normal Pydantic construction."""

    try:
        validated = GbmRnaPurityRequest.model_validate(
            request.model_dump(mode="python", warnings="none"),
            strict=True,
        )
    except (AttributeError, TypeError, ValueError):
        raise GbmRnaPurityInferenceError(
            "input does not satisfy the exact GBMPurity request contract"
        ) from None
    return validated


def _input_vector(
    request: GbmRnaPurityRequest,
    catalog: GbmRnaPurityCatalog,
) -> tuple[Float64Vector, ModelCoverage, PuritySupport, tuple[str, ...]]:
    supplied = {item.gene_symbol: item.raw_count for item in request.counts}
    recognized = catalog.feature_index.keys() & supplied.keys()
    values = np.zeros(len(catalog.feature_names), dtype=np.float64)
    for symbol in recognized:
        values[catalog.feature_index[symbol]] = supplied[symbol]
    recognized_count = len(recognized)
    missing_count = len(catalog.feature_names) - recognized_count
    ignored_count = len(supplied) - recognized_count
    coverage_fraction = recognized_count / len(catalog.feature_names)
    recognized_sum = float(np.sum(values, dtype=np.float64))
    coverage = ModelCoverage(
        supplied_gene_count=len(supplied),
        recognized_model_gene_count=recognized_count,
        missing_model_gene_count=missing_count,
        ignored_non_model_gene_count=ignored_count,
        nonzero_model_gene_count=int(np.count_nonzero(values)),
        coverage_fraction=coverage_fraction,
        recognized_raw_count_sum=recognized_sum,
    )
    reasons: list[str] = []
    if coverage_fraction < MINIMUM_MODEL_GENE_COVERAGE:
        reasons.append("recognized model-gene coverage is below the published 80% inference gate")
    if recognized_sum <= 0.0:
        reasons.append("recognized model genes have zero total raw count")
    if reasons:
        support = PuritySupport.ABSTAINED
    elif coverage_fraction < SUPPORTED_MODEL_GENE_COVERAGE:
        support = PuritySupport.LIMITED
    else:
        support = PuritySupport.SUPPORTED
    return values, coverage, support, tuple(reasons)


def _forward(values: Float64Vector, catalog: GbmRnaPurityCatalog) -> _ForwardPass:
    rpk = values / catalog.feature_lengths
    scale = float(np.sum(rpk, dtype=np.float64))
    if not math.isfinite(scale) or scale <= 0.0:
        raise GbmRnaPurityInferenceError("source-scaled TPM denominator is not positive")
    transformed64 = np.log2((rpk / scale) * CONSTANTS.preprocessing_scale + 1.0)
    if not np.all(np.isfinite(transformed64)):
        raise GbmRnaPurityInferenceError("source preprocessing produced non-finite values")
    transformed = np.asarray(transformed64, dtype=np.float32)
    parameters = catalog.parameters
    first_preactivation = np.asarray(
        parameters["fc1.weight"] @ transformed + parameters["fc1.bias"],
        dtype=np.float32,
    )
    first_activation = np.maximum(first_preactivation, np.float32(0.0))
    second_preactivation = np.asarray(
        parameters["fc2.weight"] @ first_activation + parameters["fc2.bias"],
        dtype=np.float32,
    )
    second_activation = np.maximum(second_preactivation, np.float32(0.0))
    raw_array = parameters["out.weight"] @ second_activation + parameters["out.bias"]
    raw_output = float(raw_array[0])
    arrays = (
        transformed,
        first_preactivation,
        first_activation,
        second_preactivation,
        second_activation,
        raw_array,
    )
    if not all(np.all(np.isfinite(array)) for array in arrays):
        raise GbmRnaPurityInferenceError("published MLP produced non-finite activations")
    return _ForwardPass(
        transformed=transformed,
        first_preactivation=first_preactivation,
        first_activation=first_activation,
        second_preactivation=second_preactivation,
        second_activation=second_activation,
        raw_output=raw_output,
    )


def _activation_trace(forward: _ForwardPass) -> HiddenActivationTrace:
    first_mask = forward.first_preactivation > 0.0
    second_mask = forward.second_preactivation > 0.0
    return HiddenActivationTrace(
        first_layer_active_nodes=int(np.count_nonzero(first_mask)),
        second_layer_active_nodes=int(np.count_nonzero(second_mask)),
        first_layer_activations=tuple(_q(value) for value in forward.first_activation),
        second_layer_activations=tuple(_q(value) for value in forward.second_activation),
        activation_pattern_digest=sha256_digest(
            {
                "first": first_mask.tolist(),
                "second": second_mask.tolist(),
            }
        ),
    )


def _direction(value: float) -> AttributionDirection:
    if value > 0.0:
        return AttributionDirection.RAISES_RAW_ESTIMATE
    if value < 0.0:
        return AttributionDirection.LOWERS_RAW_ESTIMATE
    return AttributionDirection.ZERO_LOCAL_CONTRIBUTION


def _explanation(
    forward: _ForwardPass,
    catalog: GbmRnaPurityCatalog,
    clipping_state: ClippingState,
) -> LocalLinearExplanation:
    """Decompose the exact affine map selected by this input's ReLU masks."""

    parameters = catalog.parameters
    first_mask = (forward.first_preactivation > 0.0).astype(np.float64)
    second_mask = (forward.second_preactivation > 0.0).astype(np.float64)
    out_weight = parameters["out.weight"][0].astype(np.float64)
    second_path = out_weight * second_mask
    first_path = (second_path @ parameters["fc2.weight"].astype(np.float64)) * first_mask
    gradient = first_path @ parameters["fc1.weight"].astype(np.float64)
    transformed = forward.transformed.astype(np.float64)
    contributions = gradient * transformed
    bias = (
        float(parameters["out.bias"][0])
        + float(second_path @ parameters["fc2.bias"].astype(np.float64))
        + float(first_path @ parameters["fc1.bias"].astype(np.float64))
    )
    contribution_sum = float(np.sum(contributions, dtype=np.float64))
    reconstructed = contribution_sum + bias
    error = abs(reconstructed - forward.raw_output)
    order = sorted(
        range(len(catalog.feature_names)),
        key=lambda index: (-abs(float(contributions[index])), catalog.feature_names[index]),
    )[:TOP_ATTRIBUTION_LIMIT]
    attributions = tuple(
        GeneLocalAttribution(
            rank=rank,
            gene_symbol=catalog.feature_names[index],
            transformed_expression=_q(transformed[index]),
            local_gradient=_q(gradient[index]),
            raw_output_contribution=_q(contributions[index]),
            direction=_direction(float(contributions[index])),
        )
        for rank, index in enumerate(order, start=1)
    )
    return LocalLinearExplanation(
        top_gene_attributions=attributions,
        all_gene_contribution_sum=_q(contribution_sum),
        active_path_bias_contribution=_q(bias),
        reconstructed_raw_output=_q(reconstructed),
        reconstruction_absolute_error=_q(error),
        clipping_changes_local_interpretation=clipping_state is not ClippingState.NONE,
    )


def _provenance(catalog: GbmRnaPurityCatalog) -> GbmRnaPurityProvenance:
    return GbmRnaPurityProvenance(
        source_repository="https://github.com/scmpht/GBMPurity",
        source_commit="af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950",
        source_model_sha256=(
            "sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7"
        ),
        source_gene_lengths_sha256=(
            "sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b"
        ),
        converted_artifact_digest=catalog.content_digest,
        converted_artifact_file_sha256=catalog.artifact_digest,
        feature_order_digest=catalog.feature_order_digest,
        weight_tensor_digest=catalog.weight_tensor_digest,
        source_license="MIT",
        source_license_sha256=(
            "sha256:3f0041f0cfe77a6f4153e1465b1590b744102d9e8948203bcb56d9b244367ef7"
        ),
        article_doi="10.1093/neuonc/noaf026",
        article_license="CC-BY-4.0",
        transformation_notice=catalog.transformation_notice,
    )


def analyze_gbm_rna_purity(
    request: GbmRnaPurityRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmRnaPurityResult:
    """Run the exact source preprocessing/MLP, or abstain before evaluation."""

    checkpoint(cancellation)
    request = _validate_direct_request(request)
    catalog = gbm_rna_purity_catalog()
    profile = algorithm_profile()
    digest = canonical_request_digest(request)
    values, coverage, support, abstention_reasons = _input_vector(request, catalog)
    checkpoint(cancellation)

    estimate: GbmRnaPurityEstimate | None = None
    explanation: LocalLinearExplanation | None = None
    if support is PuritySupport.ABSTAINED:
        diagnostics = GbmRnaPurityDiagnostics(
            finite_inference=False,
            transformed_input_sum=0.0,
            transformed_input_maximum=0.0,
            hidden_trace=None,
        )
    else:
        forward = _forward(values, catalog)
        clipped = min(1.0, max(0.0, forward.raw_output))
        if forward.raw_output < 0.0:
            clipping_state = ClippingState.LOWER_BOUND
        elif forward.raw_output > 1.0:
            clipping_state = ClippingState.UPPER_BOUND
        else:
            clipping_state = ClippingState.NONE
        estimate = GbmRnaPurityEstimate(
            malignant_cell_fraction=_q(clipped),
            raw_unclipped_output=_q(forward.raw_output),
            clipping_state=clipping_state,
        )
        explanation = _explanation(forward, catalog, clipping_state)
        diagnostics = GbmRnaPurityDiagnostics(
            finite_inference=True,
            transformed_input_sum=_q(float(np.sum(forward.transformed, dtype=np.float64))),
            transformed_input_maximum=_q(float(np.max(forward.transformed))),
            hidden_trace=_activation_trace(forward),
        )
    payload: dict[str, object] = {
        "sample_id": request.sample_id,
        "request_digest": digest,
        "profile_digest": profile.profile_digest,
        "result_digest": empty_result_digest(),
        "support": support,
        "coverage": coverage,
        "estimate": estimate,
        "diagnostics": diagnostics,
        "explanation": explanation,
        "uncertainty_reason": (
            "The published release contains one fitted MLP and no calibrated ensemble; "
            "GLIO-PROTEOGEN does not fabricate an interval."
        ),
        "provenance": _provenance(catalog),
        "abstention_reasons": abstention_reasons,
        "limitations": _LIMITATIONS,
    }
    unverified = UnverifiedGbmRnaPurityResult.model_validate(payload)
    payload = unverified.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(unverified)
    checkpoint(cancellation)
    return GbmRnaPurityResult.model_validate(payload)


__all__ = ["analyze_gbm_rna_purity"]
