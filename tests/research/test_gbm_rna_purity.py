"""Scientific, integrity, and replay oracles for the GBMPurity NumPy port."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

import glio_proteogen.research.gbm_rna_purity.catalog as catalog_module
from glio_proteogen.research.gbm_rna_purity import (
    GbmRnaPurityReplayVerificationRequest,
    GbmRnaPurityRequest,
    PuritySupport,
    RawGeneCount,
    analyze_gbm_rna_purity,
    synthetic_demo_request,
    verify_gbm_rna_purity_replay,
)
from glio_proteogen.research.gbm_rna_purity.canonical import (
    canonical_json_bytes,
    canonical_request_digest,
    result_payload_digest,
    sha256_digest,
)
from glio_proteogen.research.gbm_rna_purity.catalog import gbm_rna_purity_catalog
from glio_proteogen.research.gbm_rna_purity.contracts import REQUIRED_CONTEXT
from glio_proteogen.research.gbm_rna_purity.errors import GbmRnaPurityArtifactError
from glio_proteogen.research.gbm_rna_purity.profile import algorithm_profile


def _request(
    counts: tuple[RawGeneCount, ...],
    *,
    sample_id: str = "fixture.gbm.rna",
) -> GbmRnaPurityRequest:
    return GbmRnaPurityRequest(
        sample_id=sample_id,
        context=REQUIRED_CONTEXT,
        counts_provenance_digest=sha256_digest({"fixture": "raw-counts"}),
        counts=counts,
    )


def _full_counts(mode: str) -> tuple[RawGeneCount, ...]:
    catalog = gbm_rna_purity_catalog()
    if mode == "ones":
        values = (1.0 for _ in catalog.feature_names)
    elif mode == "lengths":
        values = (float(value) for value in catalog.feature_lengths)
    else:  # pragma: no cover - test helper misuse
        raise AssertionError(mode)
    return tuple(
        RawGeneCount(gene_symbol=symbol, raw_count=value)
        for symbol, value in zip(catalog.feature_names, values, strict=True)
    )


def test_converted_artifact_and_profile_are_content_bound() -> None:
    catalog = gbm_rna_purity_catalog()
    payload = (
        files(catalog.__class__.__module__.rsplit(".", 1)[0])
        .joinpath("data/gbm_purity_mlp.v1.json")
        .read_bytes()
    )
    profile = algorithm_profile()

    assert len(catalog.feature_names) == 5_829
    assert catalog.content_digest == (
        "sha256:651fa1ea9100650d8b34cec3c980624e42bada1ec3ff9cfe23fdf13049585722"
    )
    assert "sha256:" + hashlib.sha256(payload).hexdigest() == (
        "sha256:2999d845c602c7b8b44d45c37a7f43bea57ad6a930af12f9c7b56cc221ffccc2"
    )
    assert profile.converted_artifact_digest == catalog.content_digest
    assert profile.converted_artifact_file_sha256 == catalog.artifact_digest
    assert profile.feature_order_digest == catalog.feature_order_digest
    assert profile.weight_tensor_digest == catalog.weight_tensor_digest
    assert profile.source_commit == "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950"
    assert profile.source_license == "MIT"


def test_runtime_rejects_even_a_self_consistent_artifact_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admitted model is pinned externally, not merely self-hashed."""

    payload = catalog_module._resource_bytes()
    document = json.loads(payload)
    document["provenance"]["transformation_notice"] += " substituted"
    digest_document = dict(document)
    digest_document.pop("content_digest")
    document["content_digest"] = sha256_digest(digest_document)
    substituted = canonical_json_bytes(document)

    catalog_module.gbm_rna_purity_catalog.cache_clear()
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: substituted)
    try:
        with pytest.raises(GbmRnaPurityArtifactError, match="file digest mismatch"):
            catalog_module.gbm_rna_purity_catalog()
    finally:
        catalog_module.gbm_rna_purity_catalog.cache_clear()


@pytest.mark.parametrize(
    ("mode", "upstream_torch_oracle"),
    [("ones", 0.042044490575790405), ("lengths", 0.10667085647583008)],
)
def test_numpy_forward_matches_locked_upstream_pytorch_oracles(
    mode: str,
    upstream_torch_oracle: float,
) -> None:
    result = analyze_gbm_rna_purity(_request(_full_counts(mode)))

    assert result.support is PuritySupport.SUPPORTED
    assert result.estimate is not None
    assert result.estimate.raw_unclipped_output == pytest.approx(
        upstream_torch_oracle,
        abs=5.0e-7,
    )
    assert result.diagnostics.network == "5829_to_32_relu_to_16_relu_to_1_linear_eval_mode"
    assert result.diagnostics.dropout_active is False
    assert result.explanation is not None
    assert result.explanation.reconstruction_absolute_error <= 5.0e-7


def test_demo_is_supported_deterministic_and_locally_explainable() -> None:
    request = synthetic_demo_request()
    left = analyze_gbm_rna_purity(request)
    right = analyze_gbm_rna_purity(request)

    assert request.sample_id == "synthetic-primary-idhwt-gbm-rna-purity-v1"
    assert left == right
    assert left.support is PuritySupport.SUPPORTED
    assert left.estimate is not None
    assert left.estimate.malignant_cell_fraction == pytest.approx(0.1324209, abs=1.0e-8)
    assert left.result_digest == result_payload_digest(left)
    assert left.explanation is not None
    assert len(left.explanation.top_gene_attributions) == 20
    assert left.diagnostics.hidden_trace is not None
    assert left.uncertainty_status == "not_available_in_published_single_model"


def test_published_overlap_gate_limits_then_abstains() -> None:
    catalog = gbm_rna_purity_catalog()
    limited_count = 4_664
    below_gate_count = 4_663

    limited = analyze_gbm_rna_purity(
        _request(
            tuple(
                RawGeneCount(
                    gene_symbol=catalog.feature_names[index],
                    raw_count=float(100 + index % 17),
                )
                for index in range(limited_count)
            )
        )
    )
    abstained = analyze_gbm_rna_purity(
        _request(
            tuple(
                RawGeneCount(
                    gene_symbol=catalog.feature_names[index],
                    raw_count=float(100 + index % 17),
                )
                for index in range(below_gate_count)
            )
        )
    )

    assert limited.coverage.coverage_fraction >= 0.80
    assert limited.support is PuritySupport.LIMITED
    assert limited.estimate is not None
    assert limited.estimate.raw_unclipped_output == pytest.approx(-0.1051009595, abs=5.0e-7)
    assert limited.estimate.malignant_cell_fraction == 0.0
    assert abstained.coverage.coverage_fraction < 0.80
    assert abstained.support is PuritySupport.ABSTAINED
    assert abstained.estimate is None
    assert abstained.explanation is None
    assert abstained.abstention_reasons == (
        "recognized model-gene coverage is below the published 80% inference gate",
    )


def test_zero_counts_abstain_without_entering_the_network() -> None:
    result = analyze_gbm_rna_purity(
        _request(_full_counts("ones")).model_copy(
            update={
                "counts": tuple(
                    item.model_copy(update={"raw_count": 0.0}) for item in _full_counts("ones")
                )
            }
        )
    )

    assert result.support is PuritySupport.ABSTAINED
    assert result.abstention_reasons == ("recognized model genes have zero total raw count",)
    assert result.diagnostics.finite_inference is False


def test_request_order_does_not_change_receipt_or_result() -> None:
    request = _request(_full_counts("ones"))
    reversed_request = request.model_copy(update={"counts": tuple(reversed(request.counts))})

    assert canonical_request_digest(request) == canonical_request_digest(reversed_request)
    assert analyze_gbm_rna_purity(request) == analyze_gbm_rna_purity(reversed_request)


def test_duplicate_and_negative_counts_fail_closed() -> None:
    row = RawGeneCount(gene_symbol="EGFR", raw_count=10.0)
    with pytest.raises(ValidationError, match="unique"):
        _request((row, row))
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        RawGeneCount(gene_symbol="EGFR", raw_count=-1.0)


def test_replay_detects_forged_result_digest() -> None:
    request = synthetic_demo_request()
    result = analyze_gbm_rna_purity(request)
    verified = verify_gbm_rna_purity_replay(
        GbmRnaPurityReplayVerificationRequest(request=request, result=result)
    )
    forged = result.model_dump(mode="python")
    forged["result_digest"] = "sha256:" + "0" * 64
    rejected = verify_gbm_rna_purity_replay(
        GbmRnaPurityReplayVerificationRequest.model_validate({"request": request, "result": forged})
    )

    assert verified.verified is True
    assert rejected.verified is False
    assert rejected.result_digest_match is False
