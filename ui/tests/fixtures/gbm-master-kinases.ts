const sourceDigest = `sha256:${"3".repeat(64)}`;
// Browser-oriented payloads retain the current locked pre-release receipt identities.
const profileDigest = "sha256:bbd25777ede1c62d1cd662cae55be2fb3f2f0bfb6680eb68dbe84a22ebb5e964";
const requestDigest = "sha256:eefee0655f9cfc2f80145f639deca4d397d69106e38dd3f6b70ae44d877d013b";
const resultDigest = "sha256:d915a6077a4c4caf47953762a012e4baf075f4dc0c9046da88e7569849b48276";
const engineSourceDigest = "sha256:553dcc86716fb4a325aeb2b8bb4de54c1650544a74e81c7f42cce4890feac8ed";
const demoResultOracleDigest = "sha256:4422b04b101b76beba530e0cb61f52ac4f89f805a3d5b75c04d0326a46762238";

export const masterKinaseDemo = {
  profile_id: "sphinks-gbm-master-kinase-concordance/1.0.0",
  sample_id: "synthetic-sphinks-gbm-master-kinase-concordance-v1",
  observations: [
    { observation_id: "demo.signature.01.01", phosphosite_id: "ARHGAP15-S43s", state: "observed", standardized_effect: 1.1, standard_error: 0.28, quality_weight: 0.95, provenance_digest: sourceDigest },
    { observation_id: "demo.signature.01.02", phosphosite_id: "HMGN1-S7s", state: "observed", standardized_effect: 1.145, standard_error: 0.28, quality_weight: 0.95, provenance_digest: sourceDigest },
    { observation_id: "demo.signature.01.03", phosphosite_id: "BAD-S118s", state: "left_censored", standardized_effect: 1.19, standard_error: 0.28, quality_weight: 0.95, provenance_digest: sourceDigest },
    { observation_id: "demo.background.001", phosphosite_id: "VIM-S419s", state: "observed", standardized_effect: -0.7, standard_error: 0.34, quality_weight: 0.9, provenance_digest: sourceDigest },
    { observation_id: "demo.explicit-missing", phosphosite_id: "PSTPIP1-S377s", state: "missing", standardized_effect: null, standard_error: null, quality_weight: 0, provenance_digest: sourceDigest },
  ],
  bootstrap_replicates: 16,
  permutation_replicates: 64,
  contrast_reference: {
    contrast_id: "synthetic.glioma-like.contrast.v1",
    numerator_label: "synthetic glioma-like state",
    denominator_label: "synthetic reference state",
    scale: "caller_supplied_standardized_log2_contrast",
  },
  background_mode: "request_observed_pinned_table5a",
};

export const masterKinaseProfile = {
  algorithm_id: "sphinks-gbm-master-kinase-concordance",
  algorithm_version: "1.0.0",
  profile_id: "sphinks-gbm-master-kinase-concordance/1.0.0",
  constants: {
    location_estimator: "collapsed_site_one_sided_huber_bisection_v2",
    duplicate_edge_policy: "mean_svm_probability_per_kinase_site_v1",
    rank_estimator: "residue_stratified_competitive_weighted_rank_v2",
    bootstrap_policy: "request_digest_seeded_normal_and_symmetric_limit_v2",
    subtype_pooling_policy: "robust_source_mww_weighted_complete_tracks_v2",
    rank_null_policy: "two_sided_residue_stratified_observation_tuple_permutation_fixed24_bh_v2",
    work_budget_policy: "active_background_membership_replicate_units_v1",
    huber_delta: 1.345,
    standard_error_floor: 0.25,
    location_ridge: 1e-6,
    location_solver_iterations: 32,
    location_search_bound: 20,
    activation_threshold: 0.25,
    minimum_location_sites: 3,
    rank_q_threshold: 0.1,
    supported_minimum_sites: 5,
    supported_minimum_observed_sites: 3,
    supported_minimum_coverage: 0.02,
    supported_minimum_effective_sample_size: 4,
    minimum_rank_signature_sites: 3,
    minimum_rank_background: 20,
    supported_minimum_rank_background: 64,
    minimum_residue_stratum_competitors: 3,
    interval_lower_quantile: 0.05,
    interval_upper_quantile: 0.95,
    minimum_bootstrap_success_fraction: 0.8,
    quantization_decimals: 6,
    random_seed_bytes: 8,
    default_bootstrap_replicates: 64,
    default_permutation_replicates: 256,
    subtype_minimum_estimated_kinases: 2,
    subtype_minimum_estimated_fraction: 0.5,
    subtype_minimum_supported_kinases: 2,
    max_computational_work_units: 14_000_000,
    work_active_observation_bootstrap_weight: 2,
    work_observed_background_bootstrap_weight: 12,
    work_active_membership_bootstrap_weight: 32,
    work_observed_membership_bootstrap_weight: 2,
    work_observed_membership_permutation_weight: 1,
    work_fixed_hypothesis_permutation_overhead: 384,
  },
  numpy_version: "2.5.2",
  catalog_content_digest: `sha256:${"a".repeat(64)}`,
  catalog_artifact_digest: `sha256:${"b".repeat(64)}`,
  source_workbook_digest: `sha256:${"8".repeat(64)}`,
  table5a_background_tuple_digest: `sha256:${"1".repeat(64)}`,
  table5a_background_label_digest: `sha256:${"4".repeat(64)}`,
  table5d_signature_edge_digest: `sha256:${"2".repeat(64)}`,
  table5e_master_kinase_digest: `sha256:${"c".repeat(64)}`,
  kinase_alias_digest: `sha256:${"7".repeat(64)}`,
  engine_source_digest: engineSourceDigest,
  demo_id: masterKinaseDemo.sample_id,
  demo_request_digest: requestDigest,
  demo_result_oracle_digest: demoResultOracleDigest,
  source_attribution: "Migliozzi et al., Integrative multi-omics networks identify PKCδ and DNA-PK as master kinases of glioblastoma subtypes and guide targeted cancer therapy",
  source_license: "CC-BY-4.0",
  source_license_url: "https://creativecommons.org/licenses/by/4.0/",
  source_transformation_notice: "Adapted projection of Supplementary Tables 5a, 5d, and 5e into canonical JSON with a closed HGNC mapping; the concordance estimator is newly authored and is not SPHINKS/MK.",
  profile_digest: profileDigest,
  safety_class: "research_use_only",
  interpretation: "independent_signature_concordance_non_prescriptive",
};

const kinaseCatalog = [
  ["PRKCD", "PKCD", "GPM"], ["VRK2", "VRK2", "GPM"], ["MAPK13", "P38D", "GPM"],
  ["SYK", "SYK", "GPM"], ["MAPKAPK2", "MK-2", "GPM"], ["PRKAA1", "AMPKA1", "GPM"],
  ["MKNK1", "MNK1", "GPM"], ["IKBKB", "IKKB", "GPM"], ["RPS6KB2", "S6K2", "GPM"],
  ["PHKG2", "PHKG2", "MTC"],
  ["GSK3B", "GSK3B", "NEU"], ["PRKCE", "PKCE", "NEU"], ["PAK3", "PAK3", "NEU"],
  ["PAK1", "PAK1", "NEU"], ["MAPK10", "JNK3", "NEU"], ["TTBK2", "TTBK2", "NEU"], ["BRAF", "BRAF", "NEU"],
  ["CHEK2", "CHK2", "PPR"], ["CDK2", "CDK2", "PPR"], ["PRKDC", "DNAPK", "PPR"],
  ["CDK6", "CDK6", "PPR"], ["CSNK2A1", "CK2A1", "PPR"], ["CDK1", "CDK1", "PPR"], ["RAF1", "RAF1", "PPR"],
] as const;

const subtypeScore = { GPM: 1.014197, MTC: -0.833423, NEU: 0.666944, PPR: 1.246541 } as const;
const subtypeMembers = (subtype: string) => kinaseCatalog.filter((entry) => entry[2] === subtype).map((entry) => entry[0]);

export const masterKinaseAnalysis = {
  algorithm_id: "sphinks-gbm-master-kinase-concordance",
  algorithm_version: "1.0.0",
  profile_id: masterKinaseProfile.profile_id,
  profile_digest: profileDigest,
  request_digest: requestDigest,
  result_digest: resultDigest,
  sample_id: masterKinaseDemo.sample_id,
  contrast_reference: masterKinaseDemo.contrast_reference,
  kinase_evidence: kinaseCatalog.map(([kinaseId, sourceLabel, subtype], index) => {
    const base = subtypeScore[subtype];
    const score = kinaseId === "PRKCD" ? 1.055445 : Number((base + ((index % 5) - 2) * 0.014).toFixed(6));
    const rankScore = subtype === "MTC" ? -0.781066 : subtype === "NEU" ? -0.218048 : subtype === "PPR" ? 0.677143 : 0.172408;
    return {
      kinase_id: kinaseId,
      source_kinase_label: sourceLabel,
      source_subtype: subtype,
      support: "supported",
      classification: subtype === "MTC" ? "suppressed" : "activated",
      source_reference: { kinase_activity_mww_score: 1.7, log2fc_activity_subtype_vs_others: 0.31, p_value: 0.0001 },
      location: { support: "supported", score, lower_bound: Number((score - 0.08).toFixed(6)), upper_bound: Number((score + 0.09).toFixed(6)), effective_sample_size: 12 + index, bootstrap_replicates_requested: 16, bootstrap_replicates_successful: 16, bootstrap_replicates_used: 16, reason: null },
      rank_enrichment: { support: "supported", score: rankScore, lower_bound: rankScore - 0.08, upper_bound: rankScore + 0.08, effective_sample_size: 12 + index, mapped_signature_sites: 12 + index, observed_background_sites: 232, bootstrap_replicates_requested: 16, bootstrap_replicates_successful: 16, bootstrap_replicates_used: 16, permutation_replicates_used: 64, null_standard_deviation: 0.11, p_value: 0.015385, q_value: 0.033566, reason: null },
      method_agreement: subtype === "NEU" ? "discordant" : "concordant",
      discordance: subtype === "NEU" ? 0.073948 : 0,
      stability: 1,
      evidence_counts: { source_signature_edge_rows: 34 + index, signature_unique_sites: 30 + index, repeated_source_edge_rows: 4, observed_signature_sites: 12 + index, left_censored_signature_sites: index === 0 ? 1 : 0, binding_left_censored_sites: index === 0 ? 1 : 0, explicitly_missing_signature_sites: 0, unsupported_signature_sites: 0, unreported_signature_sites: 18, active_coverage: Math.min(1, (13 + index) / (30 + index)), observed_background_sites: 232 },
      top_drivers: [{ observation_id: `demo.driver.${String(index + 1).padStart(2, "0")}`, observation_provenance_digest: sourceDigest, phosphosite_id: index === 0 ? "MAPK1-T185tY187y" : `${kinaseId}-S${index + 11}s`, source_edge_row_ids: [`table5d:${subtype}:${String(index + 1).padStart(5, "0")}`], evidence_state: "observed", value_role: "observed_point", standardized_effect: index === 0 ? -0.76 : score, source_svm_weight: 0.91, reliability_weight: 6.1, location_influence: 0.42, rank_influence: 0.08 }],
      edge_ablations: [{ omitted_residue_stratum: "S", source_edge_rows_removed: 20 + index, unique_sites_removed: 18 + index, location_delta: 0.018147, rank_delta: -0.040283 }],
      abstention_reasons: [],
    };
  }),
  subtype_evidence: (["GPM", "MTC", "NEU", "PPR"] as const).map((subtype) => {
    const members = subtypeMembers(subtype);
    const score = subtypeScore[subtype];
    const limited = subtype === "MTC";
    return {
      subtype_id: subtype,
      support: limited ? "limited" : "supported",
      classification: subtype === "MTC" ? "suppressed" : "activated",
      aggregate: { support: limited ? "limited" : "supported", score, lower_bound: score - 0.08, upper_bound: score + 0.08, effective_sample_size: limited ? 1 : members.length - 1, bootstrap_replicates_requested: 16, bootstrap_replicates_successful: 16, bootstrap_replicates_used: 16, reason: limited ? "fewer than two independently estimated member kinases" : null },
      member_kinases: members,
      supported_member_count: members.length,
      estimated_member_count: members.length,
      discordance: 0,
      stability: 1,
      top_kinases: members.slice(0, 3).map((kinaseId, index) => ({ kinase_id: kinaseId, score: score + index * 0.01, aggregation_weight: 1 / members.length, influence: (index - 1) * 0.004 })),
      subtype_ablations: members.map((kinaseId, index) => ({ omitted_kinase_id: kinaseId, subtype_score_delta: limited ? null : (index - 2) * 0.001 })),
      abstention_reasons: limited ? ["fewer than two independently estimated member kinases"] : [],
    };
  }),
  provenance: { engine: masterKinaseProfile.profile_id, request_digest: requestDigest, profile_digest: profileDigest, catalog_content_digest: masterKinaseProfile.catalog_content_digest, catalog_artifact_digest: masterKinaseProfile.catalog_artifact_digest, source_workbook_digest: masterKinaseProfile.source_workbook_digest, table5a_background_tuple_digest: masterKinaseProfile.table5a_background_tuple_digest, table5a_background_label_digest: masterKinaseProfile.table5a_background_label_digest, table5d_signature_edge_digest: masterKinaseProfile.table5d_signature_edge_digest, table5e_master_kinase_digest: masterKinaseProfile.table5e_master_kinase_digest, kinase_alias_digest: masterKinaseProfile.kinase_alias_digest, engine_source_digest: engineSourceDigest, demo_result_oracle_digest: demoResultOracleDigest, numpy_version: "2.5.2", computational_digest: `sha256:${"9".repeat(64)}`, bootstrap_seed: 7986687065979358, permutation_seed: 6473331048370278, bootstrap_replicates_requested: 16, permutation_replicates_requested: 64, observation_source_digests: [sourceDigest], source_article_doi: "10.1038/s43018-022-00510-x", source_article_title: "Integrative multi-omics networks identify PKCδ and DNA-PK as master kinases of glioblastoma subtypes and guide targeted cancer therapy", source_article_authors: "Migliozzi et al.", source_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC9970878/", source_license: "CC-BY-4.0", source_license_url: "https://creativecommons.org/licenses/by/4.0/", source_transformation_notice: "Adapted projection of Supplementary Tables 5a, 5d, and 5e into canonical JSON with a closed HGNC mapping; the concordance estimator is newly authored and is not SPHINKS/MK." },
  output_semantics: "independent_signature_concordance_evidence",
  limitations: [
    "This is an independent GLIO-PROTEOGEN signature-concordance engine, not a port or retraining of SPHINKS/MK.",
    "Scores are not calibrated kinase activities, subtype probabilities, causal estimates, diagnoses, or treatment guidance.",
  ],
  research_use_only: true,
  non_prescriptive: true,
};

export const masterKinaseVerification = {
  verified: true,
  request_digest_match: true,
  profile_digest_match: true,
  result_digest_match: true,
  semantic_match: true,
  recomputed_request_digest: requestDigest,
  recomputed_result_digest: resultDigest,
  message: "Replay exactly matches the deterministic signature-concordance receipt.",
};
