"""Scientific and safety tests for the caller-owned GBM mixture runtime."""

from __future__ import annotations

import math

import pytest

from glio_proteogen.research.gbmap_deconvolution.runtime import (
    GbmMixtureProfile,
    GbmMixtureRequest,
    analyze_gbm_mixture,
    mixture_profile,
    synthetic_gbm_mixture_request,
    verify_gbm_mixture_replay,
)


def test_synthetic_gbm_mixture_is_real_count_native_fit_and_replays() -> None:
    request = synthetic_gbm_mixture_request()
    result = analyze_gbm_mixture(request)

    assert result.support == "limited"
    assert result.unknown_mass is not None
    assert 0.0 < result.unknown_mass < 1.0
    assert result.ood is not None
    assert result.ood.selected_count_depth == sum(request.counts)
    assert math.isfinite(result.ood.normalized_dm_deviance)
    assert math.isfinite(result.ood.aitchison_residual)
    known_total = sum(item.rna_weight for item in result.known_weights) + result.unknown_mass
    assert known_total == pytest.approx(1.0, abs=1e-8)
    assert verify_gbm_mixture_replay(request, result)


def test_input_order_is_canonicalized_without_changing_the_fit() -> None:
    original = synthetic_gbm_mixture_request()
    permutation = (7, 2, 5, 0, 6, 4, 1, 3)
    shuffled = original.model_copy(
        update={
            "feature_ids": tuple(original.feature_ids[index] for index in permutation),
            "counts": tuple(original.counts[index] for index in permutation),
            "unknown_background": tuple(
                original.unknown_background[index] for index in permutation
            ),
            "references": tuple(
                reference.model_copy(
                    update={
                        "signature": tuple(reference.signature[index] for index in permutation)
                    }
                )
                for reference in reversed(original.references)
            ),
        }
    )

    assert shuffled.request_digest == original.request_digest
    assert analyze_gbm_mixture(shuffled).model_dump(mode="json") == analyze_gbm_mixture(
        original
    ).model_dump(mode="json")


def test_profile_binds_constants_and_forbids_histologic_claims() -> None:
    profile = mixture_profile()
    assert profile.output_semantics == "rna_mixture_weights_with_unknown_mass"
    assert profile.histologic_fraction_claim_permitted is False
    assert profile.clinical_use_permitted is False
    with pytest.raises(ValueError, match="profile digest"):
        GbmMixtureProfile(profile_digest="sha256:" + "0" * 64)


def test_nonidentifiable_reference_signatures_are_rejected() -> None:
    request = synthetic_gbm_mixture_request()
    duplicate = request.references[0].model_copy(update={"reference_id": "duplicate"})
    payload = request.model_dump(mode="python")
    payload["references"] = (request.references[0], duplicate)
    with pytest.raises(ValueError, match="not identifiable"):
        GbmMixtureRequest.model_validate(payload, strict=True)


def test_solver_nonconvergence_abstains_without_negative_composition() -> None:
    request = synthetic_gbm_mixture_request().model_copy(update={"max_iterations": 1})
    result = analyze_gbm_mixture(request)

    assert result.support == "abstained"
    assert result.abstention_reason is not None
    assert result.known_weights == ()
    assert result.unknown_gene_mass == ()
    assert verify_gbm_mixture_replay(request, result)
