import {
  LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST,
  LONGITUDINAL_PHOSPHO_ASSAY_PROFILE_ID,
  LONGITUDINAL_PHOSPHO_ASSAY_SCHEMA_VERSION,
  LONGITUDINAL_PHOSPHO_SOURCE_PROFILE_DIGEST,
} from "../../src/lib/longitudinal-gbm-phospho";

const digest = (character: string) => `sha256:${character.at(-1)?.repeat(64) ?? "0".repeat(64)}`;
const referenceDigest = digest("1");
const requestDigest = digest("2");
const resultDigest = digest("3");
const profileDigest = digest("4");

const sites = [
  { id: "ENSP00000354587.4:s473", gene: "AKT1" },
  { id: "ENSP00000350283.5:s9s15", gene: "GSK3B" },
  { id: "ENSP00000362680.3:y705", gene: "STAT3" },
];

export const phosphoDemoRequest = {
  profile_id: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  series_id: "synthetic-kncc-longitudinal-phosphosite-series-v1",
  assay_compatibility: {
    schema_version: LONGITUDINAL_PHOSPHO_ASSAY_SCHEMA_VERSION,
    compatibility_profile_id: LONGITUDINAL_PHOSPHO_ASSAY_PROFILE_ID,
    source_profile_digest: LONGITUDINAL_PHOSPHO_SOURCE_PROFILE_DIGEST,
    source_artifact_content_digest: LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST,
    assay: "tmt11_plexed_phosphoproteome_mass_spectrometry",
    quantification: "phosphosite_sample_to_reference_abundance_ratio",
    value_transformation: "log2_ratio",
    log_base: 2,
    feature_identity: "exact_ensp_versioned_source_site_group",
    composite_site_policy: "indivisible_source_site_group",
    invariant_across_time_points: true,
    attested_compatible: true,
  },
  normalization_reference: {
    reference_id: "synthetic-tmt11-bridge",
    binding_digest: referenceDigest,
    normalization_method: "synthetic fixed TMT11 sample-to-reference log2 ratio",
    abundance_scale: "caller_supplied_log2_phosphosite_abundance_ratio",
    invariant_across_time_points: true,
  },
  time_points: [0, 91, 247, 461].map((offset, point) => ({
    time_point_id: `synthetic-p${point}`,
    time_offset_days: offset,
    normalization_reference_digest: referenceDigest,
    observations: sites.map((site, index) => ({
      observation_id: `demo-p${point}-f${index}`,
      phosphosite_id: site.id,
      gene_symbol: site.gene,
      state: point === 3 && index === 2 ? "left_censored" : "observed",
      log_abundance_ratio: [0, 0.8, 0.15, 0.16][point] + index * 0.02,
      standard_error: 0.08 + index * 0.01,
      quality_weight: 0.95,
      provenance_digest: digest(String(5 + point + index)),
    })),
  })),
  bootstrap_replicates: 64,
};

export const phosphoProfile = {
  algorithm_id: "kncc-gbm-longitudinal-phosphosite-concordance",
  algorithm_version: "1.0.0",
  profile_id: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  profile_digest: profileDigest,
  constants: {
    alignment_threshold: 0.25,
    stable_threshold: 0.05,
    maximum_bootstrap_replicates: 64,
  },
  counts: {
    source_feature_count: 24_015,
    eligible_feature_count: 4_225,
    selected_feature_count: 32,
    strict_pair_count: 88,
    frozen_bootstrap_replicate_count: 64,
  },
  quality_gates: {
    selection_stability_passed: true,
    bootstrap_full_refit_passed: true,
    bootstrap_feature_selection_stability_passed: false,
    bootstrap_calibration_passed: false,
  },
  source_attestation_state: "verified_exact_snapshots",
  safety_class: "research_use_only",
};

function uncertainty(variance: number) {
  return {
    state: "estimated",
    standard_error: Math.sqrt(variance),
    variance,
    variance_fraction: 0.3,
    bootstrap_replicates_used: 64,
  };
}

function transition(index: number, score: number, classification: string) {
  return {
    transition_id: `transition-${index}`,
    transition_index: index,
    from_time_point_id: `synthetic-p${index}`,
    to_time_point_id: `synthetic-p${index + 1}`,
    support: "limited",
    classification,
    score,
    lower_bound: score - 0.12,
    upper_bound: score + 0.12,
    interval_level: 0.9,
    bootstrap_replicates_used: 64,
    exact_feature_count: 31,
    censored_feature_count: index === 2 ? 1 : 0,
    effective_sample_size: 28.5,
    coefficient_weight_coverage: 0.97,
    source_pair_coverage_weighted_mean: 0.82,
    measurement_uncertainty: uncertainty(0.0016),
    coefficient_uncertainty: uncertainty(0.0081),
    uncertainty_interaction: {
      state: "estimated",
      method: "paired_full_model_bootstrap_interaction_decomposition_v1",
      interaction_standard_error: 0.03,
      interaction_variance: 0.0009,
      interaction_variance_fraction: 0.2,
      measurement_coefficient_covariance: -0.0002,
      measurement_interaction_covariance: 0.0001,
      coefficient_interaction_covariance: -0.00005,
      variance_contribution: 0.0006,
      combined_variance: 0.0103,
      decomposed_variance: 0.0103,
      decomposition_residual: 0,
      bootstrap_replicates_used: 64,
    },
    top_drivers: [{
      phosphosite_id: sites[0].id,
      gene_symbol: sites[0].gene,
      hgnc_id: "HGNC:391",
      site_cardinality: 1,
      composite_site_group: false,
      from_observation_id: `demo-p${index}-f0`,
      to_observation_id: `demo-p${index + 1}-f0`,
      standardized_delta: score,
      model_coefficient: 0.12,
      signed_contribution: score * 0.12,
      direction: score >= 0 ? "source_recurrence_aligned" : "reverse_aligned",
      reliability_weight: 0.95,
      source_pair_support: 83,
      bootstrap_selection_stability: 0.48,
      sphinks_source_site_label: "AKT1_S473",
      sphinks_signature_kinases: ["AKT1", "MTOR"],
    }],
    censored_bounds: index === 2 ? [{
      phosphosite_id: sites[2].id,
      gene_symbol: sites[2].gene,
      value_semantics: "upper_bound",
      standardized_bound: 0.22,
      coefficient_weighted_bound: -0.015,
      from_observation_id: "demo-p2-f2",
      to_observation_id: "demo-p3-f2",
    }] : [],
    feature_family_ablations: [{
      component: "exact_sphinks_crosswalk_sites",
      omitted_feature_count: 5,
      support: "limited",
      score_without_component: score - 0.08,
      score_delta: 0.08,
      classification_without_component: classification,
      reason: "source quality gates cap support",
    }],
    top_driver_ablations: [{
      omitted_phosphosite_id: sites[0].id,
      omitted_signed_contribution: score * 0.12,
      support: "limited",
      score_without_component: score - 0.05,
      score_delta: 0.05,
      classification_without_component: classification,
      reason: "source quality gates cap support",
    }],
    abstention_reasons: ["bootstrap feature-selection stability and interval calibration are not affirmatively bound"],
  };
}

export const phosphoAnalysisResult = {
  algorithm_id: "kncc-gbm-longitudinal-phosphosite-concordance",
  algorithm_version: "1.0.0",
  profile_id: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  profile_digest: profileDigest,
  request_digest: requestDigest,
  result_digest: resultDigest,
  series_id: phosphoDemoRequest.series_id,
  assay_compatibility: phosphoDemoRequest.assay_compatibility,
  normalization_reference: phosphoDemoRequest.normalization_reference,
  time_point_ids: phosphoDemoRequest.time_points.map((point) => point.time_point_id),
  transitions: [
    transition(0, 0.81, "source_recurrence_aligned"),
    transition(1, -0.66, "reverse_aligned"),
    transition(2, 0.01, "stable"),
  ],
  model_views: [
    { view: "raw_phosphosite_transition", support: "fitted", reason: "the frozen PDC000515 raw phosphosite transition axis is fitted" },
    { view: "occupancy_like", support: "not_fitted", reason: "cognate-protein adjustment is not fitted" },
    { view: "protein_phosphosite_fusion", support: "not_fitted", reason: "cross-assay fusion is not fitted" },
  ],
  provenance: {
    source_artifact_content_digest: LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST,
    source_artifact_byte_digest: digest("a"),
    source_attestation_state: "verified_exact_snapshots",
    sphinks_crosswalk_provenance: {
      source_name: "SPHINKS",
      article_attribution: "Migliozzi et al.",
      article_doi: "10.1038/s43018-022-00510-x",
      license: "CC-BY-4.0",
      transformation_notice: "Adapted exact identity annotation only; no kinase inference.",
    },
  },
  limitations: [
    "Research use only; not diagnostic, prognostic, prescriptive, or clinically validated.",
    "Featurewise-independent Gaussian measurement perturbations cannot represent shared-reference, TMT, or batch covariance.",
  ],
  research_use_only: true,
  non_prescriptive: true,
  infers_kinase_activity: false,
};

export const phosphoVerification = {
  verified: true,
  request_digest_match: true,
  profile_digest_match: true,
  result_digest_match: true,
  transition_semantic_match: true,
  view_semantic_match: true,
  semantic_match: true,
  recomputed_request_digest: requestDigest,
  recomputed_result_digest: resultDigest,
  message: "replay verified",
};
