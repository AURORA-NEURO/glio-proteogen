from __future__ import annotations

import json
from typing import cast

import numpy as np
import pytest

from glio_proteogen.research.gbm_master_kinases import (
    AnalysisSupport,
    GbmSubtype,
    MasterKinaseRequest,
    PhosphositeEvidenceState,
    PhosphositeObservation,
    ReplayVerificationRequest,
    StandardizedContrastReference,
    StateClassification,
    UnverifiedMasterKinaseResult,
    algorithm_profile,
    analyze_master_kinases,
    engine,
    synthetic_demo_request,
    verify_replay,
)
from glio_proteogen.research.gbm_master_kinases import profile as profile_module
from glio_proteogen.research.gbm_master_kinases.canonical import (
    demo_result_oracle_projection,
    sha256_digest,
)
from glio_proteogen.research.gbm_master_kinases.catalog import master_kinase_catalog
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

PROVENANCE = sha256_digest({"test": "master-kinase-engine"})


def _contrast() -> StandardizedContrastReference:
    return StandardizedContrastReference(
        contrast_id="engine.test.contrast",
        numerator_label="test case",
        denominator_label="test reference",
    )


def _observation(
    site: str,
    index: int,
    effect: float,
    *,
    state: PhosphositeEvidenceState = PhosphositeEvidenceState.OBSERVED,
) -> PhosphositeObservation:
    return PhosphositeObservation(
        observation_id=f"engine.obs.{index:04d}",
        phosphosite_id=site,
        state=state,
        standardized_effect=effect,
        standard_error=0.25,
        quality_weight=1.0,
        provenance_digest=PROVENANCE,
    )


def _request(
    observations: tuple[PhosphositeObservation, ...],
    sample_id: str,
) -> MasterKinaseRequest:
    return MasterKinaseRequest(
        sample_id=sample_id,
        observations=observations,
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=_contrast(),
    )


@pytest.fixture(scope="module")
def demo_lifecycle():
    request = synthetic_demo_request()
    result = analyze_master_kinases(request)
    return request, result


def test_demo_recovers_locked_directions_and_all_24_kinases(demo_lifecycle) -> None:
    request, result = demo_lifecycle
    assert len(request.observations) <= 4_096
    assert len(result.kinase_evidence) == 24
    assert len(result.subtype_evidence) == 4
    classifications = {item.subtype_id: item.classification for item in result.subtype_evidence}
    assert classifications == {
        GbmSubtype.GPM: StateClassification.ACTIVATED,
        GbmSubtype.MTC: StateClassification.SUPPRESSED,
        GbmSubtype.NEU: StateClassification.ACTIVATED,
        GbmSubtype.PPR: StateClassification.ACTIVATED,
    }
    phkg2 = next(item for item in result.kinase_evidence if item.kinase_id == "PHKG2")
    assert phkg2.classification is StateClassification.SUPPRESSED
    assert cast("float", phkg2.location.upper_bound) < -0.25
    assert all(item.rank_enrichment.p_value is not None for item in result.kinase_evidence)
    assert all(
        item.rank_enrichment.bootstrap_replicates_used == request.bootstrap_replicates
        for item in result.kinase_evidence
    )


def test_order_invariance_covers_request_seed_and_result_semantics(demo_lifecycle) -> None:
    request, result = demo_lifecycle
    reordered = request.model_copy(update={"observations": tuple(reversed(request.observations))})
    reordered_result = analyze_master_kinases(reordered)
    assert reordered.request_digest == request.request_digest
    assert reordered_result == result


def test_replay_verifies_exact_receipt_and_rejects_forgery(demo_lifecycle) -> None:
    request, result = demo_lifecycle
    verification = verify_replay(ReplayVerificationRequest(request=request, result=result))
    assert verification.verified
    forged_payload = result.model_dump(mode="json")
    forged_payload["sample_id"] = "forged.sample"
    forged = UnverifiedMasterKinaseResult.model_validate_json(json.dumps(forged_payload))
    rejected = verify_replay(ReplayVerificationRequest(request=request, result=forged))
    assert not rejected.verified
    assert not rejected.result_digest_match
    assert not rejected.semantic_match


def test_bh_uses_fixed_predeclared_24_kinase_family(demo_lifecycle) -> None:
    _request_value, result = demo_lifecycle
    p_values = {
        item.kinase_id: cast("float", item.rank_enrichment.p_value)
        for item in result.kinase_evidence
    }
    assert len(p_values) == 24
    independently_adjusted = engine._benjamini_hochberg(p_values)
    for item in result.kinase_evidence:
        assert cast("float", item.rank_enrichment.q_value) == pytest.approx(
            independently_adjusted[item.kinase_id], abs=2e-6
        )
        assert cast("float", item.rank_enrichment.q_value) >= cast(
            "float", item.rank_enrichment.p_value
        )


def test_one_sided_censor_only_counts_when_binding() -> None:
    catalog = master_kinase_catalog()
    master = next(item for item in catalog.masters if item.hgnc_symbol == "PRKCD")
    sites = tuple(
        dict.fromkeys(edge.source_site_label for edge in catalog.edges_by_kinase["PRKCD"])
    )[:5]
    nonbinding_request = _request(
        (
            *tuple(_observation(site, index, 1.0) for index, site in enumerate(sites[:4], start=1)),
            _observation(
                sites[4],
                5,
                10.0,
                state=PhosphositeEvidenceState.LEFT_CENSORED,
            ),
        ),
        "censor.nonbinding",
    )
    binding_request = nonbinding_request.model_copy(
        update={
            "sample_id": "censor.binding",
            "observations": (
                *nonbinding_request.observations[:-1],
                _observation(
                    sites[4],
                    5,
                    0.0,
                    state=PhosphositeEvidenceState.LEFT_CENSORED,
                ),
            ),
        }
    )
    nonbinding = next(
        item
        for item in analyze_master_kinases(nonbinding_request).kinase_evidence
        if item.kinase_id == master.hgnc_symbol
    )
    binding = next(
        item
        for item in analyze_master_kinases(binding_request).kinase_evidence
        if item.kinase_id == master.hgnc_symbol
    )
    assert nonbinding.evidence_counts.left_censored_signature_sites == 1
    assert nonbinding.evidence_counts.binding_left_censored_sites == 0
    assert nonbinding.location.support is AnalysisSupport.LIMITED
    assert binding.evidence_counts.binding_left_censored_sites == 1
    assert binding.location.support is AnalysisSupport.SUPPORTED


def test_repeated_source_rows_do_not_inflate_independent_site_support() -> None:
    catalog = master_kinase_catalog()
    master = next(item for item in catalog.masters if item.hgnc_symbol == "CSNK2A1")
    grouped: dict[str, list[object]] = {}
    for edge in catalog.edges_by_kinase[master.hgnc_symbol]:
        grouped.setdefault(edge.source_site_label, []).append(edge)
    repeated = next(site for site, edges in grouped.items() if len(edges) == 4)
    other_sites = tuple(site for site in grouped if site != repeated)[:2]
    request = _request(
        tuple(
            _observation(site, index, 0.8)
            for index, site in enumerate((repeated, *other_sites), start=1)
        ),
        "duplicate-row.noninflation",
    )
    result = analyze_master_kinases(request)
    kinase = next(item for item in result.kinase_evidence if item.kinase_id == master.hgnc_symbol)
    assert kinase.evidence_counts.observed_signature_sites == 3
    assert kinase.location.effective_sample_size <= 3.0
    repeated_driver = next(item for item in kinase.top_drivers if item.phosphosite_id == repeated)
    assert len(repeated_driver.source_edge_row_ids) == 4
    matching_observation = next(
        item for item in request.observations if item.phosphosite_id == repeated
    )
    assert repeated_driver.observation_id == matching_observation.observation_id
    assert repeated_driver.observation_provenance_digest == matching_observation.provenance_digest


def test_missing_and_unsupported_never_become_negative_evidence() -> None:
    request = MasterKinaseRequest(
        sample_id="inactive.only",
        observations=(
            PhosphositeObservation(
                observation_id="inactive.fake",
                phosphosite_id="FAKE-S1s",
                state=PhosphositeEvidenceState.UNSUPPORTED,
                quality_weight=0.0,
                provenance_digest=PROVENANCE,
            ),
        ),
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=_contrast(),
    )
    result = analyze_master_kinases(request)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.kinase_evidence)
    assert all(
        item.classification is StateClassification.NOT_ESTIMABLE for item in result.kinase_evidence
    )
    assert all(item.location.score is None for item in result.kinase_evidence)


def test_rank_abstains_when_a_residue_stratum_has_no_independent_competitors() -> None:
    catalog = master_kinase_catalog()
    master = next(item for item in catalog.masters if item.hgnc_symbol == "PRKCD")
    specs = engine._site_specs(master)
    ty = next(item for item in specs if item.residue_stratum == "TY")
    s_sites = tuple(item for item in specs if item.residue_stratum == "S")[:2]
    signature = (ty, *s_sites)
    signature_ids = {item.phosphosite_id for item in signature}
    background = tuple(
        site
        for site in sorted(catalog.background_labels - signature_ids)
        if engine._residue_stratum(site) == "S"
    )[:20]
    request = _request(
        tuple(
            _observation(site, index, 0.5 + index * 0.01)
            for index, site in enumerate(
                tuple(item.phosphosite_id for item in signature) + background,
                start=1,
            )
        ),
        "rank.residue-guard",
    )
    observations = engine._observation_map(request)
    rank = engine._rank_enrichment(specs, observations, engine._percentile_scores(observations))
    assert rank.support is AnalysisSupport.ABSTAINED
    assert "inadequate independent residue competitors for TY" in cast("str", rank.reason)


def test_small_numeric_oracles_and_extreme_weight_stability() -> None:
    assert engine._robust_scalar_location((1.0, 2.0, 3.0), (1.0, 1.0, 1.0)) == pytest.approx(
        2.0, abs=2e-6
    )
    assert engine._effective_sample_size((1e-250, 1e-250, 1e-250)) == pytest.approx(3.0)
    assert engine._benjamini_hochberg({"a": 0.01, "b": 0.04, "c": 0.03}) == pytest.approx(
        {"a": 0.03, "b": 0.04, "c": 0.04}
    )


def test_profile_binds_demo_catalog_numpy_and_constants() -> None:
    profile = algorithm_profile()
    catalog = master_kinase_catalog()
    demo_result = analyze_master_kinases(synthetic_demo_request())
    assert profile.demo_request_digest == synthetic_demo_request().request_digest
    assert profile.demo_result_oracle_digest == sha256_digest(
        demo_result_oracle_projection(demo_result)
    )
    assert profile.engine_source_digest == profile_module.computational_source_digest()
    assert profile.catalog_artifact_digest == catalog.artifact_digest
    assert profile.table5a_background_label_digest == catalog.background_label_digest
    assert profile.constants.duplicate_edge_policy == "mean_svm_probability_per_kinase_site_v1"
    assert profile.constants.minimum_residue_stratum_competitors == 3
    assert profile.constants.minimum_bootstrap_success_fraction == 0.8
    assert "observation_tuple" in profile.constants.rank_null_policy
    assert demo_result.provenance.engine_source_digest == profile.engine_source_digest
    assert demo_result.provenance.demo_result_oracle_digest == profile.demo_result_oracle_digest
    assert demo_result.provenance.source_article_doi == "10.1038/s43018-022-00510-x"
    assert demo_result.provenance.source_article_title == catalog.article_title
    assert demo_result.provenance.source_article_authors == catalog.article_authors
    assert demo_result.provenance.source_license == "CC-BY-4.0"
    assert demo_result.provenance.source_transformation_notice == catalog.transformation_notice
    assert demo_result.provenance.bootstrap_replicates_requested == (
        synthetic_demo_request().bootstrap_replicates
    )


def test_computational_source_digest_normalizes_cross_platform_line_endings() -> None:
    lf = b"first = 1\nsecond = 2\n"
    assert profile_module._normalized_python_source_digest(lf) == (
        profile_module._normalized_python_source_digest(lf.replace(b"\n", b"\r\n"))
    )
    assert profile_module._normalized_python_source_digest(lf) == (
        profile_module._normalized_python_source_digest(lf.replace(b"\n", b"\r"))
    )


def test_censored_limit_uncertainty_moves_both_directions_without_latent_reuse() -> None:
    site = next(iter(master_kinase_catalog().background_labels))
    observation = engine._Observation(
        "censored.limit",
        site,
        PhosphositeEvidenceState.LEFT_CENSORED,
        0.0,
        0.5,
        1.0,
        PROVENANCE,
        engine._residue_stratum(site),
    )
    rng = np.random.default_rng(7_321)
    limits = tuple(
        cast("float", engine._perturb_observations({site: observation}, rng)[site].effect)
        for _ in range(128)
    )
    assert min(limits) < 0.0 < max(limits)
    assert all(
        engine._perturb_observations({site: observation}, rng)[site].state
        is PhosphositeEvidenceState.LEFT_CENSORED
        for _ in range(4)
    )


def test_nominal_90_percent_location_intervals_have_locked_simulation_coverage() -> None:
    truth = 0.6
    standard_error = 0.5
    experiment_count = 200
    specs = tuple(engine._SiteSpec(f"SIM-S{index + 1}s", (), 0.9, "S") for index in range(8))
    covered = 0
    for experiment in range(experiment_count):
        data_rng = np.random.default_rng(40_000 + experiment)
        observations = {
            spec.phosphosite_id: engine._Observation(
                f"simulation.{index}",
                spec.phosphosite_id,
                PhosphositeEvidenceState.OBSERVED,
                float(data_rng.normal(truth, standard_error)),
                standard_error,
                1.0,
                PROVENANCE,
                "S",
            )
            for index, spec in enumerate(specs)
        }
        point = engine._robust_location(specs, observations)
        bootstrap_rng = np.random.default_rng(50_000 + experiment)
        samples = tuple(
            cast(
                "float",
                engine._robust_location(
                    specs,
                    engine._perturb_observations(observations, bootstrap_rng),
                ).score,
            )
            for _ in range(64)
        )
        lower, upper = engine._interval(cast("float", point.score), samples)
        covered += lower <= truth <= upper
    coverage = covered / experiment_count
    assert 0.85 <= coverage <= 0.95


def test_fixed24_bh_null_fdr_is_calibrated_with_heteroscedastic_observation_tuples() -> None:
    experiment_count = 200
    discovery_experiments = 0
    request = synthetic_demo_request().model_copy(update={"permutation_replicates": 256})
    for experiment in range(experiment_count):
        data_rng = np.random.default_rng(36_000 + experiment)
        standard_errors = np.asarray(
            [0.2 + 1.3 * ((index % 11) / 10) for index in range(240)],
            dtype=np.float64,
        )
        quality_weights = np.asarray(
            [0.35 + 0.65 * ((index % 7) / 6) for index in range(240)],
            dtype=np.float64,
        )
        data_rng.shuffle(standard_errors)
        data_rng.shuffle(quality_weights)
        observations: dict[str, engine._Observation] = {}
        for index, (standard_error, quality_weight) in enumerate(
            zip(standard_errors, quality_weights, strict=True)
        ):
            site = f"NULL-S{index + 1}s"
            observations[site] = engine._Observation(
                f"null.{experiment}.{index}",
                site,
                PhosphositeEvidenceState.OBSERVED,
                float(data_rng.normal(0.0, standard_error)),
                float(standard_error),
                float(quality_weight),
                PROVENANCE,
                "S",
            )
        percentiles = engine._percentile_scores(observations)
        ranks: dict[str, engine._RawRank] = {}
        for kinase_index in range(24):
            specs = tuple(
                engine._SiteSpec(
                    f"NULL-S{site_index + 1}s",
                    (),
                    0.84 + 0.03 * (member_index % 5),
                    "S",
                )
                for member_index, site_index in enumerate(
                    range(kinase_index * 5, kinase_index * 5 + 5)
                )
            )
            ranks[f"K{kinase_index:02d}"] = engine._rank_enrichment(
                specs,
                observations,
                percentiles,
            )
        nulls, _seed = engine._permutation_nulls(
            request,
            observations,
            ranks,
            computational_digest=sha256_digest({"null_experiment": experiment}),
            cancellation=None,
        )
        p_values = {
            identifier: (
                1.0
                + sum(abs(value) >= abs(cast("float", ranks[identifier].score)) for value in values)
            )
            / (len(values) + 1.0)
            for identifier, values in nulls.items()
        }
        q_values = engine._benjamini_hochberg(p_values)
        discovery_experiments += any(value <= 0.10 for value in q_values.values())
    global_null_fdr = discovery_experiments / experiment_count
    # BH controls the upper rate; discreteness and shared background make the
    # finite-permutation test conservative, so equality to alpha is not required.
    assert global_null_fdr <= 0.12


def test_pre_cancelled_analysis_stops_at_cooperative_checkpoint() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        analyze_master_kinases(synthetic_demo_request(), cancellation=cancellation)
