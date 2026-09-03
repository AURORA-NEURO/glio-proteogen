import {
  LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  reactomeTransitionProfileDigest,
  reactomeTransitionRequestDigest,
  reactomeTransitionResultDigest,
  reactomeTransitionValueDigest,
} from "../../src/lib/longitudinal-gbm-reactome-transition";
import type { JsonObject } from "../../src/lib/research-state";
import {
  LONGITUDINAL_ASSAY_PROFILE_ID,
  LONGITUDINAL_ASSAY_SCHEMA_VERSION,
  LONGITUDINAL_SOURCE_PROFILE_DIGEST,
} from "../../src/lib/longitudinal-gbm";

const digest = `sha256:${"a".repeat(64)}`;
const requestDigest = `sha256:${"b".repeat(64)}`;
const resultDigest = `sha256:${"c".repeat(64)}`;
const normalizationDigest = `sha256:${"d".repeat(64)}`;

const genes = ["EGFR", "PDGFRA", "PIK3CA", "MTOR", "MAPK1", "HIF1A"] as const;
const pointIds = ["synthetic.reactome.baseline", "synthetic.reactome.recurrence"] as const;

export const reactomeTransitionDemoRequest = {
  profile_id: LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  series_id: "synthetic-kncc-reactome-conditional-transition-v1",
  assay_compatibility: {
    schema_version: LONGITUDINAL_ASSAY_SCHEMA_VERSION,
    compatibility_profile_id: LONGITUDINAL_ASSAY_PROFILE_ID,
    source_profile_content_digest: LONGITUDINAL_SOURCE_PROFILE_DIGEST,
    assay: "tmt11_plexed_mass_spectrometry",
    quantification: "unshared_peptide_protein_abundance_ratio",
    value_transformation: "log2_ratio",
    log_base: 2,
    invariant_across_time_points: true,
    attested_compatible: true,
  },
  normalization_reference: {
    reference_id: "synthetic.kncc.reactome.log2.reference.v1",
    binding_digest: normalizationDigest,
    normalization_method: "synthetic invariant log2 protein-abundance reference",
    abundance_scale: "caller_supplied_log2_protein_abundance_ratio",
    invariant_across_time_points: true,
  },
  time_points: pointIds.map((timePointId, pointIndex) => ({
    time_point_id: timePointId,
    time_offset_days: pointIndex * 180,
    normalization_reference_digest: normalizationDigest,
    observations: genes.map((geneSymbol, geneIndex) => ({
      observation_id: `reactome.demo.${pointIndex}.${geneIndex}`,
      gene_symbol: geneSymbol,
      state: pointIndex === 0 && geneIndex === 5 ? "left_censored" : "observed",
      log_abundance: 10 + geneIndex * 0.2 + pointIndex * (geneIndex < 4 ? 0.8 : -0.3),
      standard_error: 0.04 + geneIndex * 0.005,
      quality_weight: 0.92,
      provenance_digest: digest,
    })),
  })),
  bootstrap_replicates: 64,
};

const pathwayCatalog = [
  ["receptor_egfr", "R-HSA-177929", "Signaling by EGFR"],
  ["receptor_pdgf", "R-HSA-186797", "Signaling by PDGF"],
  ["second_messenger_pi3k_akt", "R-HSA-198203", "PI3K/AKT activation"],
  ["mtor_signaling", "R-HSA-165159", "MTOR signalling"],
  ["mapk_cascades", "R-HSA-5683057", "MAPK family signaling cascades"],
  ["cell_cycle", "R-HSA-1640170", "Cell Cycle"],
  ["dna_repair", "R-HSA-73894", "DNA Repair"],
  ["hypoxia_response", "R-HSA-1234174", "Cellular response to hypoxia"],
  ["extracellular_matrix", "R-HSA-1474244", "Extracellular matrix organization"],
  ["innate_immune_system", "R-HSA-168249", "Innate Immune System"],
] as const;

function ablation(
  componentKind: string,
  componentId: string,
  score: number,
  index: number,
  support = "limited",
) {
  const abstained = support === "abstained";
  return {
    component_kind: componentKind,
    component_id: componentId,
    support,
    conditional_score_without_component: abstained ? null : score - 0.04 * (index + 1),
    score_delta: abstained ? null : 0.04 * (index + 1),
    classification_without_component: abstained ? "not_estimable" : "indeterminate",
    removed_feature_count: componentKind === "unique_members" ? 4 : 0,
    reason: abstained
      ? "insufficient unique evidence for an estimable ablation"
      : "point sensitivity only; no ablation-specific bootstrap calibration",
  };
}

function pathway(panelIndex: number) {
  const [domainId, reactomeId, pathwayName] = pathwayCatalog[panelIndex];
  const pi3k = reactomeId === "R-HSA-198203";
  const score = pi3k ? 1.11 : Number((0.62 - panelIndex * 0.12).toFixed(3));
  const supported = panelIndex === 0;
  const evaluable = panelIndex === 1 ? 3 : 5;
  const classification = score > 0.25
    ? "conditional_source_recurrence_aligned"
    : score < -0.25
      ? "conditional_source_primary_aligned"
      : "conditionally_stable";
  const contributionGene = genes[panelIndex % genes.length];
  return {
    panel_index: panelIndex,
    domain_id: domainId,
    reactome_id: reactomeId,
    pathway_name: pathwayName,
    output_semantics: "conditional_pathway_concordance",
    support: supported ? "supported" : "limited",
    classification,
    score,
    lower_bound: score - 0.08,
    upper_bound: score + 0.08,
    unadjusted_pathway_coordinate: score - 0.11,
    global_adjustment: -0.11,
    interval_level: 0.9,
    source_member_count: pi3k ? 9 : 53 + panelIndex * 10,
    mapped_feature_count: pi3k ? 7 : 42 + panelIndex,
    fitted_feature_count: pi3k ? 7 : 40 + panelIndex,
    active_feature_count: pi3k ? 7 : 38 + panelIndex,
    observed_count: pi3k ? 7 : 37 + panelIndex,
    left_censored_count: pi3k ? 0 : 1,
    coefficient_mass_coverage: pi3k ? 1 : 0.91,
    unique_active_gene_count: pi3k ? 0 : 8,
    unique_coefficient_mass: pi3k ? 0 : 0.31,
    effective_sample_size: pi3k ? 4.23 : 22.4,
    request_reconstruction_improved_fold_count: panelIndex === 1 ? 2 : 4,
    request_reconstruction_evaluable_fold_count: evaluable,
    request_reconstruction_median_relative_gain: panelIndex === 1 ? 0.006 : 0.018,
    stability: pi3k ? 0.984 : 0.91,
    discordance: pi3k ? 0.119 : 0.14,
    overlap_confounded: pi3k,
    uncertainty: {
      state: "estimated",
      measurement_standard_error: 0.12,
      fitted_model_standard_error: 0.2,
      measurement_model_covariance: -0.0004,
      combined_standard_error: 0.23,
      variance_closure_residual: 0.0002,
      bootstrap_replicates_used: 64,
      reason: null,
    },
    top_contributions: [{
      gene_symbol: contributionGene,
      from_observation_id: `reactome.demo.0.${panelIndex % genes.length}`,
      to_observation_id: `reactome.demo.1.${panelIndex % genes.length}`,
      from_provenance_digest: digest,
      to_provenance_digest: digest,
      from_state: "observed",
      to_state: "observed",
      value_semantics: "exact_delta",
      standardized_delta: 0.82,
      pathway_loading: 0.31,
      global_loading: 0.04,
      unadjusted_contribution: 0.21,
      global_adjustment_contribution: 0.03,
      conditional_contribution: 0.18,
      direction: "conditional_source_recurrence_aligned",
      reliability_weight: 0.93,
    }],
    ablations: {
      global_axis: ablation("global_axis", "global_recurrence", score, 0),
      source_processing: [ablation("source_processing", "ordinary_log_source_measure", score, 1)],
      degree_normalization: ablation("degree_normalization", "no_shared_gene_degree_normalization", score, 2),
      unique_members: ablation("unique_members", reactomeId, score, 3, pi3k ? "abstained" : "limited"),
      leave_pathway_out: ablation("leave_pathway_out", reactomeId, score, 4),
      overlap: panelIndex === 1
        ? [ablation("overlapping_pathway", "R-HSA-177929", score, 5)]
        : [],
      top_contributions: panelIndex === 0
        ? [ablation("top_contribution", contributionGene, score, 6)]
        : [],
    },
    abstention_reasons: supported
      ? []
      : pi3k
        ? [
          "fewer than three active unique pathway members",
          "PI3K/AKT is overlap-confounded in the fixed panel",
        ]
        : ["the request-specific reconstruction gate was not fully supported"],
  };
}

export const reactomeTransitionAnalysisResult = {
  algorithm_id: "kncc-reactome-conditional-transition",
  algorithm_version: "1.0.0",
  profile_id: LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  profile_digest: digest,
  request_digest: requestDigest,
  result_digest: resultDigest,
  series_id: reactomeTransitionDemoRequest.series_id,
  assay_compatibility: reactomeTransitionDemoRequest.assay_compatibility,
  normalization_reference: reactomeTransitionDemoRequest.normalization_reference,
  time_point_ids: pointIds,
  transitions: [{
    transition_id: "reactome.transition.0",
    transition_index: 0,
    from_time_point_id: pointIds[0],
    to_time_point_id: pointIds[1],
    duration_days: 180,
    global_recurrence: {
      output_semantics: "global_recurrence_concordance",
      support: "supported",
      classification: "stable",
      score: -0.07,
      lower_bound: -0.14,
      upper_bound: 0.03,
      interval_level: 0.9,
      shared_active_gene_count: 1656,
      coefficient_mass_coverage: 0.984,
      effective_sample_size: 1172.28,
      bootstrap_replicates_used: 64,
      abstention_reasons: [],
    },
    pathways: pathwayCatalog.map((_, index) => pathway(index)),
  }],
  provenance: {
    engine: LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
    request_digest: requestDigest,
    profile_digest: digest,
    computational_digest: digest,
    numerical_seed_digest: digest,
    source_catalog_content_digest: digest,
    pathway_membership_digest: digest,
    pathway_order_digest: digest,
    fitted_content_digest: digest,
    reference_design_digest: digest,
    bootstrap_ensemble_digest: digest,
    engine_semantic_digest: digest,
    source_patient_count: 104,
    source_attribution: "Kim et al., Cancer Cell 2024, PDC000514; Reactome V97",
    source_licenses: ["CC-BY-4.0", "Reactome CC0"],
    source_transformation_notice: "De-identified fitted artifact; no raw patient matrices or identifiers redistributed.",
    numpy_version: "2.5.2",
  },
  output_semantics: "global_recurrence_concordance_and_conditional_pathway_concordance_only",
  validation_scope: "same_cohort_patient_grouped_evaluation_not_external_validation",
  limitations: [
    "Research-use-only same-cohort protein-transition concordance; not clinical evidence.",
    "Reactome membership does not establish pathway activation, flux, or causality.",
    "PI3K/AKT has no unique fixed-panel member and remains overlap-confounded.",
  ],
  research_use_only: true,
  non_prescriptive: true,
};

export const reactomeTransitionProfile = {
  algorithm_id: "kncc-reactome-conditional-transition",
  algorithm_version: "1.0.0",
  profile_id: LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  model_id: "kncc-reactome-conditional-transition-model/1.0.0",
  constants: {
    default_bootstrap_replicates: 64,
    maximum_bootstrap_replicates: 256,
    aligned_threshold: 0.25,
    stable_threshold: 0.25,
  },
  limits: { maximum_bootstrap_replicates: 256, fixed_pathway_count: 10 },
  counts: {
    source_patient_count: 104,
    source_gene_count: 11312,
    pathway_count: 10,
    fitted_global_feature_count: 1872,
    fitted_pathway_feature_count: 1872,
    offline_bootstrap_draw_count: 256,
  },
  digests: {
    source_catalog_content_digest: digest,
    pathway_membership_digest: digest,
    pathway_order_digest: digest,
    fitted_content_digest: digest,
    reference_design_digest: digest,
    bootstrap_ensemble_digest: digest,
  },
  evaluation: {
    protocol: "eight deterministic held-patient folds with all source statistics and loadings refit; five deterministic held-gene folds within each held patient",
    validation_scope: "same-cohort reconstruction; not external validation",
    interpretation: "the joint dictionary has a modest collective reconstruction advantage; individual pathway attribution is not established by cohort-level removal",
    patient_count: 104,
    evaluation_count: 520,
    zero_prediction_median_standardized_mae: 0.7108931329,
    global_only_median_standardized_mae: 0.5622984198,
    joint_median_standardized_mae: 0.5554163035,
    median_relative_mae_improvement: 0.0120459348,
    evaluation_improved_fraction: 0.6653846154,
    patient_cluster_median_improvement: 0.0129728555,
    patient_cluster_median_improvement_90_interval: [0.0085182357, 0.0178616382],
    patient_cluster_bootstrap_replicates: 20000,
    reference_design_condition_number: 5.2021989549,
    minimum_outer_loading_cosine: 0.9851914172,
    all_primary_solver_fits_converged: true,
    all_leave_pathway_q05_q95_intervals_cross_zero: true,
  },
  pathways: pathwayCatalog.map(([domainId, reactomeId, pathwayName], panelIndex) => ({
    panel_index: panelIndex,
    domain_id: domainId,
    reactome_id: reactomeId,
    pathway_name: pathwayName,
    source_member_count: reactomeId === "R-HSA-198203" ? 9 : 53,
    mapped_feature_count: reactomeId === "R-HSA-198203" ? 7 : 42,
    eligible_feature_count: reactomeId === "R-HSA-198203" ? 7 : 40,
    fitted_feature_count: reactomeId === "R-HSA-198203" ? 7 : 42,
    unique_fitted_feature_count: reactomeId === "R-HSA-198203" ? 0 : 10,
    overlap_confounded: reactomeId === "R-HSA-198203",
  })),
  numpy_version: "2.5.2",
  profile_digest: digest,
  safety_class: "research_use_only",
  claim_ceiling: "conditional_source_cohort_transition_concordance_only",
};

export const reactomeTransitionVerification = {
  verified: true,
  request_digest_match: true,
  profile_digest_match: true,
  result_digest_match: true,
  transition_topology_match: true,
  global_recurrence_semantic_match: true,
  pathway_semantic_match: true,
  uncertainty_semantic_match: true,
  ablation_semantic_match: true,
  provenance_match: true,
  document_semantic_match: true,
  semantic_match: true,
  recomputed_request_digest: requestDigest,
  recomputed_result_digest: resultDigest,
  message: "Deterministic replay verified.",
};

function cloneDocument(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

function intervalClassification(lower: number, upper: number): string {
  if (lower > 0.25) return "conditional_source_recurrence_aligned";
  if (upper < -0.25) return "conditional_source_primary_aligned";
  if (lower >= -0.25 && upper <= 0.25) return "conditionally_stable";
  return "indeterminate";
}

/** Build one internally digest-bound wire fixture for strict browser admission. */
export function admittedReactomeTransitionDocuments(): {
  request: JsonObject;
  profile: JsonObject;
  result: JsonObject;
  verification: JsonObject;
} {
  const request = cloneDocument(reactomeTransitionDemoRequest);
  const canonicalRequestDigest = reactomeTransitionRequestDigest(request);
  const profile = cloneDocument(reactomeTransitionProfile);
  profile.parent_feature_axis_model_id = "kncc-paired-protein-transition/1.0.0";
  profile.parent_dependency_semantics =
    "feature_axis_and_assay_binding_only_no_runtime_delegation";
  profile.required_assay_compatibility = cloneDocument(request.assay_compatibility);
  profile.constants = {
    estimator: "global_adjusted_robust_conditional_coordinate_v1",
    missing_evidence_policy: "missing_and_unsupported_never_become_negative_v1",
    censoring_policy: "reported_limit_one_sided_bound_v1",
    output_semantics: "global_recurrence_concordance_and_conditional_pathway_concordance_only",
    huber_delta: 1.345,
    ridge_lambda: 1,
    global_ridge_multiplier: 0.25,
    damping: 0.7,
    solver_max_iterations: 200,
    solver_tolerance: 1e-9,
    maximum_condition_number: 25,
    interval_level: 0.9,
    aligned_threshold: 0.25,
    stable_threshold: 0.25,
    default_bootstrap_replicates: 64,
    supported_minimum_bootstrap_replicates: 64,
    minimum_bootstrap_replicates: 32,
    maximum_bootstrap_replicates: 256,
    offline_bootstrap_ensemble_size: 256,
    global_minimum_active_genes: 16,
    global_minimum_coefficient_mass: 0.25,
    global_minimum_effective_sample_size: 8,
    pathway_minimum_active_genes: 5,
    pathway_minimum_coefficient_mass: 0.5,
    pathway_minimum_effective_sample_size: 3,
    pathway_minimum_unique_genes: 3,
    pathway_minimum_unique_mass: 0.2,
    pathway_supported_minimum_stability: 0.8,
    request_reconstruction_gene_folds: 5,
    pathway_supported_required_evaluable_gene_folds: 5,
    pathway_supported_minimum_improved_gene_folds: 4,
    pathway_supported_minimum_reconstruction_gain: 0.01,
    pi3k_always_overlap_confounded: true,
    outer_fold_salt: "kncc-reactome-panel-outer-v1",
    gene_fold_salt: "kncc-reactome-gene-fold-v1",
    quantization_decimals: 8,
    solver_work_unit_formula: "(time_points - 1) * (186 + 3 * bootstrap_replicates)",
  };
  profile.limits = {
    min_time_points: 2,
    max_time_points: 16,
    max_observations_per_time_point: 4_096,
    max_total_observations: 12_000,
    fixed_pathway_count: 10,
    max_top_contributions: 10,
    max_overlap_ablations: 9,
    request_max_bytes: 2_097_152,
    result_max_bytes: 4_194_304,
    replay_max_bytes: 8_388_608,
    max_solver_work_units: 4_608,
  };
  profile.counts = {
    ...(profile.counts as JsonObject),
    excluded_candidate_count: 12,
    reactome_release: 97,
    outer_fold_count: 8,
    gene_fold_count: 5,
  };
  const digestFields = [
    "source_catalog_artifact_digest",
    "source_catalog_content_digest",
    "source_binding_digest",
    "selection_candidate_digest",
    "pathway_order_digest",
    "pathway_membership_digest",
    "gene_order_digest",
    "patient_order_rule_digest",
    "fitted_artifact_digest",
    "fitted_content_digest",
    "union_feature_digest",
    "reference_tensor_digest",
    "centering_scaling_digest",
    "reference_design_digest",
    "global_loading_digest",
    "conditional_loading_digest",
    "bootstrap_ensemble_digest",
    "training_recipe_digest",
    "fold_policy_digest",
    "source_processing_ablation_digest",
    "evaluation_digest",
    "input_contract_schema_digest",
    "engine_semantic_digest",
  ];
  profile.digests = Object.fromEntries(digestFields.map((field) => [field, digest]));
  profile.evaluation = {
    ...(profile.evaluation as JsonObject),
    outer_design_condition_minimum: 4.9,
    outer_design_condition_maximum: 5.5,
    full_patient_nonconverged_count: 0,
    global_held_gene_nonconverged_count: 0,
    joint_held_gene_nonconverged_count: 0,
    leave_pathway_out_nonconverged_count: 0,
    leave_pathway_interval_count: 10,
  };
  profile.demo_id = request.series_id;
  profile.demo_request_digest = canonicalRequestDigest;
  profile.demo_semantic_oracle_digest = digest;
  profile.source_attribution = "Kim et al., Cancer Cell 2024, PDC000514; Reactome V97";
  profile.source_licenses = ["CC-BY-4.0", "Reactome CC0"];
  profile.source_transformation_notice =
    "De-identified fitted artifact; no patient matrix is bundled.";
  profile.interpretation =
    "global_adjusted_reactome_membership_coordinate_not_pathway_activation_or_flux";
  profile.maximum_evidence_grade = "limited_same_cohort_without_external_validation";
  profile.profile_digest = reactomeTransitionProfileDigest(profile);

  const result = cloneDocument(reactomeTransitionAnalysisResult);
  result.profile_digest = profile.profile_digest;
  result.request_digest = canonicalRequestDigest;
  for (const pathwayResult of (result.transitions as JsonObject[])[0].pathways as JsonObject[]) {
    pathwayResult.classification = intervalClassification(
      pathwayResult.lower_bound as number,
      pathwayResult.upper_bound as number,
    );
  }
  const profileDigests = profile.digests as JsonObject;
  result.provenance = {
    ...(result.provenance as JsonObject),
    ...profileDigests,
    request_digest: canonicalRequestDigest,
    profile_digest: profile.profile_digest,
    computational_digest: digest,
    numerical_seed_digest: digest,
    demo_semantic_oracle_digest: profile.demo_semantic_oracle_digest,
    assay_compatibility_digest: reactomeTransitionValueDigest(result.assay_compatibility),
    normalization_reference_digest: (result.normalization_reference as JsonObject).binding_digest,
    caller_evidence_set_digest: digest,
    bootstrap_seed: 17,
  };
  result.limitations = [
    ...(result.limitations as string[]),
    "No external validation is claimed.",
    "No recurrence prediction is produced.",
    "No treatment recommendation is produced.",
  ];
  result.result_digest = reactomeTransitionResultDigest(result);

  const verification = cloneDocument(reactomeTransitionVerification);
  verification.recomputed_request_digest = canonicalRequestDigest;
  verification.recomputed_result_digest = result.result_digest;
  verification.message =
    "Replay exactly matches the deterministic conditional-concordance receipt.";
  return { request, profile, result, verification };
}
