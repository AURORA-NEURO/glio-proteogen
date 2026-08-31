import { NEFTEL_PROFILE_ID } from "../../src/lib/neftel-programs";

const digest = `sha256:${"7".repeat(64)}`;
const exactIds = ["MES2", "MES1", "AC", "OPC", "NPC1", "NPC2", "G1/S", "G2/M"] as const;
const familyIds = ["astrocyte_like", "oligodendrocyte_progenitor_like", "neural_progenitor_like", "mesenchymal_like", "cell_cycle"] as const;

export const neftelDemoRequest = {
  profile_id: NEFTEL_PROFILE_ID,
  sample_id: "synthetic-neftel-ac-program-v1",
  observations: Array.from({ length: 42 }, (_, index) => ({
    observation_id: `demo.protein.${String(index + 1).padStart(3, "0")}`,
    gene_symbol: index === 0 ? "EGFR" : index === 1 ? "PTEN" : `BGD${String(index + 1).padStart(3, "0")}`,
    state: "observed",
    standardized_effect: index < 12 ? 1.35 - index * 0.035 : -1.2 + index * 0.065,
    standard_error: index < 12 ? 0.3 : 0.35,
    quality_weight: index < 12 ? 0.95 : 0.9,
    provenance_digest: digest,
  })),
  bootstrap_replicates: 16,
  permutation_replicates: 64,
  background_mode: "request_observed_proteome",
  effect_scale: "standardized_log2_abundance_contrast",
  effect_reference_id: "synthetic.reference.v1",
};

function program(programId: string, kind: "source_meta_module" | "derived_program_family", supported: boolean) {
  const sourcePrograms = kind === "source_meta_module" ? [programId] : programId === "astrocyte_like" ? ["AC"] : ["MES1", "MES2"];
  return {
    program_id: programId,
    program_kind: kind,
    source_programs: sourcePrograms,
    support: supported ? "supported" : "abstained",
    classification: supported ? "activated" : "not_estimable",
    location: supported
      ? { support: "supported", score: 1.122499, lower_bound: 0.92, upper_bound: 1.31, effective_sample_size: 10.4, bootstrap_replicates_used: 16, reason: null }
      : { support: "abstained", score: null, lower_bound: null, upper_bound: null, effective_sample_size: 0, bootstrap_replicates_used: 0, reason: "insufficient exact marker coverage" },
    rank_enrichment: supported
      ? { support: "supported", score: 0.717949, lower_bound: 0.6, upper_bound: 0.82, effective_sample_size: 10.4, bootstrap_replicates_used: 16, reason: null, permutation_replicates_used: 64, null_standard_deviation: 0.1, p_value: 0.015385, q_value: 0.015385 }
      : { support: "abstained", score: null, lower_bound: null, upper_bound: null, effective_sample_size: 0, bootstrap_replicates_used: 0, reason: "insufficient rank-marker coverage", permutation_replicates_used: 0, null_standard_deviation: null, p_value: null, q_value: null },
    method_agreement: supported ? "concordant" : "insufficient",
    evidence_counts: { source_marker_count: 39, eligible_protein_markers: 39, catalog_non_protein_loci: 0, observed_markers: supported ? 12 : 0, left_censored_markers: 0, explicitly_missing_markers: 0, unsupported_markers: 0, unreported_markers: supported ? 27 : 39, active_coverage: supported ? 12 / 39 : 0, observed_background_proteins: 42 },
    top_drivers: supported ? [{ normalized_symbol: "EGFR", source_symbols: ["EGFR"], source_ranks: [1], evidence_state: "observed", value_role: "observed_point", standardized_effect: 1.35, reliability_weight: 0.95, location_influence: 0.24, rank_influence: 0.17 }] : [],
    marker_family_ablations: [{ omitted_family: sourcePrograms[0], markers_removed: supported ? 4 : 1, location_delta: supported ? -0.22 : null, rank_delta: supported ? -0.11 : null }],
    abstention_reasons: supported ? [] : ["fewer than five active protein markers; active marker coverage below 0.10"],
  };
}

export const neftelAnalysisResult = {
  algorithm_id: "neftel-bulk-protein-programs",
  algorithm_version: "1.0.0",
  profile_id: NEFTEL_PROFILE_ID,
  profile_digest: digest,
  request_digest: `sha256:${"8".repeat(64)}`,
  result_digest: `sha256:${"9".repeat(64)}`,
  sample_id: neftelDemoRequest.sample_id,
  program_evidence: [
    ...exactIds.map((id) => program(id, "source_meta_module", id === "AC")),
    ...familyIds.map((id) => program(id, "derived_program_family", id === "astrocyte_like")),
  ],
  provenance: {
    engine: NEFTEL_PROFILE_ID,
    request_digest: `sha256:${"8".repeat(64)}`,
    profile_digest: digest,
    catalog_content_digest: `sha256:${"a".repeat(64)}`,
    catalog_artifact_digest: `sha256:${"b".repeat(64)}`,
    exact_source_program_digest: `sha256:${"c".repeat(64)}`,
    table_s2_source_digest: `sha256:${"d".repeat(64)}`,
    hgnc_source_digest: `sha256:${"e".repeat(64)}`,
    numpy_version: "2.5.2",
    computational_digest: `sha256:${"f".repeat(64)}`,
    bootstrap_seed: 123,
    rank_permutation_seed: 456,
    observation_source_digests: [digest],
  },
  output_semantics: "bulk_protein_program_evidence",
  limitations: [
    "Bulk protein program evidence is not a cell fraction, subtype, diagnosis, or tumor-cell assignment.",
    "Non-tumor cells can contribute proteins assigned to source single-cell programs.",
    "Sparse evidence causes explicit abstention and is never interpreted as negative program evidence.",
  ],
  research_use_only: true,
  non_prescriptive: true,
};

export const neftelProfile = {
  algorithm_id: "neftel-bulk-protein-programs",
  algorithm_version: "1.0.0",
  profile_id: NEFTEL_PROFILE_ID,
  constants: { location_estimator: "one_sided_huber_location_bisection_v1", rank_estimator: "reliability_weighted_mean_percentile_rank_v1", activation_threshold: 0.25, rank_q_threshold: 0.1, supported_minimum_active_coverage: 0.3 },
  numpy_version: "2.5.2",
  catalog_content_digest: `sha256:${"a".repeat(64)}`,
  catalog_artifact_digest: `sha256:${"b".repeat(64)}`,
  exact_source_program_digest: `sha256:${"c".repeat(64)}`,
  table_s2_source_digest: `sha256:${"d".repeat(64)}`,
  hgnc_source_digest: `sha256:${"e".repeat(64)}`,
  profile_digest: digest,
  safety_class: "research_use_only",
  interpretation: "bulk_protein_program_evidence_non_prescriptive",
};

export const neftelVerification = {
  verified: true,
  request_digest_match: true,
  profile_digest_match: true,
  result_digest_match: true,
  semantic_match: true,
  recomputed_request_digest: neftelAnalysisResult.request_digest,
  recomputed_result_digest: neftelAnalysisResult.result_digest,
  message: "Replay exactly matches the deterministic Neftel protein-program receipt.",
};
