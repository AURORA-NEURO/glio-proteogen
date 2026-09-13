"""Defensive validation and interpretation branches for Neftel programs."""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from glio_proteogen.research.neftel_protein_programs import (
    AnalysisSupport,
    ExactProgramId,
    MethodAgreement,
    MethodEstimate,
    ProgramClassification,
    ProgramEvidence,
    ProteinEvidenceState,
    ProteinProgramObservation,
    ProteinProgramRequest,
    ProteinProgramResult,
    RankEnrichmentEstimate,
    analyze_neftel_protein_programs,
)
from glio_proteogen.research.neftel_protein_programs import catalog as catalog_module
from glio_proteogen.research.neftel_protein_programs import profile as profile_module
from glio_proteogen.research.neftel_protein_programs.canonical import (
    result_payload_digest,
    sha256_digest,
)
from glio_proteogen.research.neftel_protein_programs.engine import (
    _effective_sample_size,
    _hybrid_interpretation,
    _location_classification,
    _method_estimate,
    _RawEstimate,
)

SOURCE_DIGEST = sha256_digest("neftel-adversarial-source")


def _non_marker_background_symbols(count: int) -> tuple[str, ...]:
    catalog = catalog_module.marker_catalog()
    marker_symbols = {
        marker.normalized_symbol
        for markers in catalog.programs.values()
        for marker in markers
    }
    return tuple(sorted(catalog.protein_background_symbols - marker_symbols)[:count])


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "table_source",
        "hgnc_source",
        "program_order",
        "marker_count",
        "unknown_program",
        "rank",
        "unsupported_inventory",
        "source_program_content",
    ],
)
def test_runtime_catalog_fails_closed_on_tampering(monkeypatch, mutation: str) -> None:
    original = json.loads(catalog_module._resource_bytes())
    document = copy.deepcopy(original)
    expected_order = catalog_module.EXPECTED_PROGRAM_ORDER
    if mutation == "schema":
        document["schema_version"] = "forged"
    elif mutation == "table_source":
        document["source"]["source_sha256"] = sha256_digest("forged-table")
    elif mutation == "hgnc_source":
        document["normalization"]["authority_sha256"] = sha256_digest("forged-hgnc")
    elif mutation == "program_order":
        document["programs"] = list(reversed(document["programs"]))
    elif mutation == "marker_count":
        document["programs"][0]["markers"].pop()
    elif mutation == "unknown_program":
        document["programs"][0]["program_id"] = "UNKNOWN"
        expected_order = ("UNKNOWN", *expected_order[1:])
    elif mutation == "rank":
        document["programs"][0]["markers"][0]["rank"] = 2
    elif mutation == "unsupported_inventory":
        document["normalization"]["unsupported_non_protein_loci"].append("FORGED")
    else:
        document["programs"][0]["markers"][0]["raw_symbol"] = "FORGED"
    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    with monkeypatch.context() as context:
        context.setattr(catalog_module, "_resource_bytes", lambda: encoded)
        context.setattr(catalog_module, "EXPECTED_PROGRAM_ORDER", expected_order)
        catalog_module.marker_catalog.cache_clear()
        with pytest.raises(RuntimeError):
            catalog_module.marker_catalog()
    catalog_module.marker_catalog.cache_clear()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "state": ProteinEvidenceState.OBSERVED,
            "quality_weight": 1.0,
        },
        {
            "state": ProteinEvidenceState.OBSERVED,
            "standardized_effect": 1.0,
            "standard_error": 0.2,
            "quality_weight": 0.0,
        },
        {
            "state": ProteinEvidenceState.MISSING,
            "quality_weight": 1.0,
        },
    ],
)
def test_observation_state_contract_fails_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProteinProgramObservation(
            observation_id="obs.invalid",
            gene_symbol="CST3",
            provenance_digest=SOURCE_DIGEST,
            **payload,
        )


def test_request_rejects_duplicate_observation_identifiers() -> None:
    first = ProteinProgramObservation(
        observation_id="obs.duplicate",
        gene_symbol="CST3",
        state=ProteinEvidenceState.OBSERVED,
        standardized_effect=1.0,
        standard_error=0.2,
        quality_weight=1.0,
        provenance_digest=SOURCE_DIGEST,
    )
    second = first.model_copy(update={"gene_symbol": "S100B"})
    with pytest.raises(ValidationError, match="identifiers"):
        ProteinProgramRequest(
            sample_id="sample.duplicate",
            observations=(first, second),
            bootstrap_replicates=16,
            permutation_replicates=64,
            effect_scale="standardized_log2_abundance_contrast",
            effect_reference_id="reference.control",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "support": AnalysisSupport.ABSTAINED,
            "score": 0.0,
            "effective_sample_size": 0.0,
            "bootstrap_replicates_used": 0,
            "reason": "invalid numeric abstention",
        },
        {
            "support": AnalysisSupport.SUPPORTED,
            "effective_sample_size": 8.0,
            "bootstrap_replicates_used": 16,
        },
        {
            "support": AnalysisSupport.SUPPORTED,
            "score": 0.0,
            "lower_bound": -0.1,
            "upper_bound": 0.1,
            "effective_sample_size": 8.0,
            "bootstrap_replicates_used": 16,
            "reason": "invalid supported reason",
        },
        {
            "support": AnalysisSupport.LIMITED,
            "score": 0.0,
            "lower_bound": -0.1,
            "upper_bound": 0.1,
            "effective_sample_size": 5.0,
            "bootstrap_replicates_used": 16,
        },
        {
            "support": AnalysisSupport.SUPPORTED,
            "score": 2.0,
            "lower_bound": -0.1,
            "upper_bound": 0.1,
            "effective_sample_size": 8.0,
            "bootstrap_replicates_used": 16,
        },
    ],
)
def test_method_interval_contract_fails_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MethodEstimate(**payload)


def test_rank_null_contract_fails_closed() -> None:
    abstained = {
        "support": AnalysisSupport.ABSTAINED,
        "effective_sample_size": 0.0,
        "bootstrap_replicates_used": 0,
        "reason": "no evidence",
    }
    with pytest.raises(ValidationError, match="null statistics"):
        RankEnrichmentEstimate(
            **abstained,
            permutation_replicates_used=0,
            p_value=1.0,
        )
    with pytest.raises(ValidationError, match="zero permutations"):
        RankEnrichmentEstimate(**abstained, permutation_replicates_used=64)
    with pytest.raises(ValidationError, match="requires permutation"):
        RankEnrichmentEstimate(
            support=AnalysisSupport.SUPPORTED,
            score=0.2,
            lower_bound=0.1,
            upper_bound=0.3,
            effective_sample_size=10.0,
            bootstrap_replicates_used=16,
            permutation_replicates_used=64,
        )


def _method(
    support: AnalysisSupport,
    lower: float | None,
    upper: float | None,
    *,
    score: float | None = None,
) -> MethodEstimate:
    return MethodEstimate(
        support=support,
        score=score,
        lower_bound=lower,
        upper_bound=upper,
        effective_sample_size=0.0 if support is AnalysisSupport.ABSTAINED else 10.0,
        bootstrap_replicates_used=0 if support is AnalysisSupport.ABSTAINED else 16,
        reason="no evidence" if support is AnalysisSupport.ABSTAINED else None,
    )


def _rank(
    support: AnalysisSupport,
    lower: float | None,
    upper: float | None,
    *,
    score: float | None = None,
    q_value: float | None = 0.01,
) -> RankEnrichmentEstimate:
    return RankEnrichmentEstimate(
        **_method(support, lower, upper, score=score).model_dump(mode="python"),
        permutation_replicates_used=0 if support is AnalysisSupport.ABSTAINED else 64,
        null_standard_deviation=None if support is AnalysisSupport.ABSTAINED else 0.1,
        p_value=None if support is AnalysisSupport.ABSTAINED else 0.01,
        q_value=None if support is AnalysisSupport.ABSTAINED else q_value,
    )


@pytest.mark.parametrize(
    ("location", "rank", "expected"),
    [
        (
            _method(AnalysisSupport.ABSTAINED, None, None),
            _rank(AnalysisSupport.SUPPORTED, 0.1, 0.3, score=0.2),
            (
                AnalysisSupport.LIMITED,
                ProgramClassification.INDETERMINATE,
                MethodAgreement.SINGLE_METHOD,
            ),
        ),
        (
            _method(AnalysisSupport.SUPPORTED, 0.5, 0.8, score=0.6),
            _rank(AnalysisSupport.ABSTAINED, None, None, q_value=None),
            (
                AnalysisSupport.LIMITED,
                ProgramClassification.ACTIVATED,
                MethodAgreement.SINGLE_METHOD,
            ),
        ),
        (
            _method(AnalysisSupport.SUPPORTED, 0.5, 0.8, score=0.6),
            _rank(AnalysisSupport.SUPPORTED, -0.4, -0.1, score=-0.2),
            (
                AnalysisSupport.LIMITED,
                ProgramClassification.INDETERMINATE,
                MethodAgreement.DISCORDANT,
            ),
        ),
        (
            _method(AnalysisSupport.SUPPORTED, 0.5, 0.8, score=0.6),
            _rank(AnalysisSupport.SUPPORTED, -0.1, 0.2, score=0.05),
            (
                AnalysisSupport.LIMITED,
                ProgramClassification.INDETERMINATE,
                MethodAgreement.UNCERTAIN,
            ),
        ),
        (
            _method(AnalysisSupport.SUPPORTED, -0.1, 0.1, score=0.0),
            _rank(AnalysisSupport.SUPPORTED, -0.05, 0.05, score=0.0, q_value=1.0),
            (AnalysisSupport.SUPPORTED, ProgramClassification.NEUTRAL, MethodAgreement.CONCORDANT),
        ),
        (
            _method(AnalysisSupport.SUPPORTED, 0.5, 0.8, score=0.6),
            _rank(AnalysisSupport.SUPPORTED, 0.1, 0.3, score=0.2, q_value=0.5),
            (AnalysisSupport.LIMITED, ProgramClassification.ACTIVATED, MethodAgreement.CONCORDANT),
        ),
    ],
)
def test_hybrid_interpretation_branches(
    location: MethodEstimate,
    rank: RankEnrichmentEstimate,
    expected: tuple[AnalysisSupport, ProgramClassification, MethodAgreement],
) -> None:
    assert _hybrid_interpretation(location, rank) == expected


def test_internal_estimate_rejects_missing_bootstrap_rows() -> None:
    raw = _RawEstimate(
        support=AnalysisSupport.SUPPORTED,
        score=1.0,
        effective_sample_size=10.0,
        reason=None,
    )
    with pytest.raises(RuntimeError, match="bootstrap"):
        _method_estimate(raw, [])


def test_result_contract_rejects_forged_receipt_and_duplicate_programs() -> None:
    observations = tuple(
        ProteinProgramObservation(
            observation_id=f"obs.{index}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=float(index) / 10.0,
            standard_error=0.3,
            quality_weight=1.0,
            provenance_digest=SOURCE_DIGEST,
        )
        for index, symbol in enumerate(_non_marker_background_symbols(20))
    )
    request = ProteinProgramRequest(
        sample_id="sample.forgery",
        observations=observations,
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id="reference.control",
    )
    result = analyze_neftel_protein_programs(request)
    document = result.model_dump(mode="json")
    invalid_program = copy.deepcopy(document["program_evidence"][0])
    invalid_program["classification"] = ProgramClassification.ACTIVATED
    with pytest.raises(ValidationError, match="not_estimable"):
        ProgramEvidence.model_validate_json(json.dumps(invalid_program))
    invalid_program["classification"] = ProgramClassification.NOT_ESTIMABLE
    invalid_program["abstention_reasons"] = []
    with pytest.raises(ValidationError, match="require reasons"):
        ProgramEvidence.model_validate_json(json.dumps(invalid_program))
    estimated_program = copy.deepcopy(document["program_evidence"][0])
    estimated_program["support"] = AnalysisSupport.LIMITED
    with pytest.raises(ValidationError, match="estimated programs"):
        ProgramEvidence.model_validate_json(json.dumps(estimated_program))
    for field, value, message in (
        ("profile_digest", sha256_digest("wrong-profile"), "profile digest"),
        ("request_digest", sha256_digest("wrong-request"), "request digest"),
        ("result_digest", sha256_digest("wrong-result"), "result digest"),
    ):
        forged = copy.deepcopy(document)
        forged[field] = value
        with pytest.raises(ValidationError, match=message):
            ProteinProgramResult.model_validate_json(json.dumps(forged))
    duplicate = copy.deepcopy(document)
    duplicate["program_evidence"][-1]["program_id"] = duplicate["program_evidence"][0][
        "program_id"
    ]
    duplicate["result_digest"] = result_payload_digest(duplicate)
    with pytest.raises(ValidationError, match="unique"):
        ProteinProgramResult.model_validate_json(json.dumps(duplicate))


def test_profile_rejects_unpinned_numpy(monkeypatch) -> None:
    with monkeypatch.context() as context:
        context.setattr(profile_module.np, "__version__", "0.0.0")
        with pytest.raises(RuntimeError, match=r"NumPy 2\.5\.2"):
            profile_module.algorithm_profile()


def test_single_observation_rank_and_indeterminate_location_helpers() -> None:
    one_observation = ProteinProgramObservation(
        observation_id="obs.single",
        gene_symbol=_non_marker_background_symbols(1)[0],
        state=ProteinEvidenceState.OBSERVED,
        standardized_effect=0.0,
        standard_error=0.3,
        quality_weight=1.0,
        provenance_digest=SOURCE_DIGEST,
    )
    request = ProteinProgramRequest(
        sample_id="sample.single",
        observations=(one_observation,),
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id="reference.control",
    )
    result = analyze_neftel_protein_programs(request)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.program_evidence)
    wide = _method(AnalysisSupport.SUPPORTED, -0.5, 0.5, score=0.0)
    assert _location_classification(wide) is ProgramClassification.INDETERMINATE


def _ac_support_request(
    *,
    observed_count: int,
    observed_quality: float = 1.0,
    censored_count: int = 0,
    censored_effect: float = 20.0,
) -> ProteinProgramRequest:
    marker_symbols = tuple(
        marker.normalized_symbol
        for marker in catalog_module.marker_catalog().programs["AC"]
        if marker.protein_eligible
    )
    observations = [
        ProteinProgramObservation(
            observation_id=f"obs.marker.{index}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=1.0,
            standard_error=0.3,
            quality_weight=observed_quality,
            provenance_digest=SOURCE_DIGEST,
        )
        for index, symbol in enumerate(marker_symbols[:observed_count])
    ]
    observations.extend(
        ProteinProgramObservation(
            observation_id=f"obs.censored.{index}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.LEFT_CENSORED,
            standardized_effect=censored_effect,
            standard_error=0.3,
            quality_weight=observed_quality,
            provenance_digest=SOURCE_DIGEST,
        )
        for index, symbol in enumerate(
            marker_symbols[observed_count : observed_count + censored_count]
        )
    )
    background_symbols = _non_marker_background_symbols(25)
    observations.extend(
        ProteinProgramObservation(
            observation_id=f"obs.background.{index}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=-1.0 + index * 0.05,
            standard_error=0.3,
            quality_weight=1.0,
            provenance_digest=SOURCE_DIGEST,
        )
        for index, symbol in enumerate(background_symbols)
    )
    return ProteinProgramRequest(
        sample_id="sample.numeric-hardening",
        observations=tuple(observations),
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id="reference.control",
    )


def _ac_evidence(request: ProteinProgramRequest) -> ProgramEvidence:
    result = analyze_neftel_protein_programs(request)
    return next(
        item for item in result.program_evidence if item.program_id is ExactProgramId.AC
    )


def test_effective_sample_size_is_stable_for_tiny_and_rescaled_weights() -> None:
    weights = (0.25, 0.5, 1.0, 2.0)
    expected = _effective_sample_size(weights)
    assert _effective_sample_size(tuple(weight * 1e-200 for weight in weights)) == pytest.approx(
        expected
    )
    assert _effective_sample_size((5e-324, 5e-324, 5e-324)) == 3.0


def test_tiny_positive_quality_produces_valid_positive_driver_reliability() -> None:
    evidence = _ac_evidence(
        _ac_support_request(observed_count=12, observed_quality=1e-8)
    )
    assert evidence.location.effective_sample_size == 12.0
    assert evidence.top_drivers
    assert all(driver.reliability_weight > 0.0 for driver in evidence.top_drivers)


def test_nonbinding_censored_limits_cannot_promote_location_support() -> None:
    evidence = _ac_evidence(
        _ac_support_request(
            observed_count=5,
            censored_count=10,
            censored_effect=20.0,
        )
    )
    assert evidence.location.support is AnalysisSupport.LIMITED
    assert evidence.location.effective_sample_size == 5.0
    assert evidence.location.reason is not None
    assert "nonbinding left-censored limits excluded from support gate" in evidence.location.reason
    assert evidence.evidence_counts.observed_markers == 5
    assert evidence.evidence_counts.left_censored_markers == 10


def test_binding_censored_limits_can_contribute_to_location_support() -> None:
    evidence = _ac_evidence(
        _ac_support_request(
            observed_count=5,
            censored_count=10,
            censored_effect=0.9,
        )
    )
    assert evidence.location.support is AnalysisSupport.SUPPORTED
    assert evidence.location.effective_sample_size == 15.0
    assert evidence.location.score is not None
    assert evidence.location.score > 0.9
    assert evidence.location.reason is None
