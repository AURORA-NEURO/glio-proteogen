import { describe, expect, it } from "vitest";

import {
  GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
  microenvironmentGraphRequestStats,
  microenvironmentSupportedFamilyCount,
  normalizeMicroenvironmentGraphResult,
  validateMicroenvironmentGraphProfile,
  validateMicroenvironmentGraphRequest,
  validateMicroenvironmentGraphDemo,
  validateMicroenvironmentGraphResult,
  validateMicroenvironmentGraphResultHeaders,
  validateMicroenvironmentGraphVerification,
} from "../../src/lib/gbm-microenvironment-graph";
import {
  algorithmProfile,
  analysisResult,
  demoRequest,
} from "../fixtures/proteogenomic-state";
import {
  neftelAnalysisResult,
  neftelDemoRequest,
} from "../fixtures/neftel-programs";
import {
  gbmAnalysisResult,
  gbmDemoRequest,
} from "../fixtures/gbm-proteomic-axes";

const DIGEST = `sha256:${"a".repeat(64)}`;

function sourceRequest(): Record<string, unknown> {
  return {
    profile_id: "neftel-bulk-protein-programs/1.0.0",
    sample_id: "sample-1",
    observations: [{
      observation_id: "obs-1",
      gene_symbol: "VIM",
      state: "observed",
      standardized_effect: 1.2,
      standard_error: 0.3,
      quality_weight: 0.9,
      provenance_digest: DIGEST,
    }],
    bootstrap_replicates: 16,
    permutation_replicates: 64,
    background_mode: "request_observed_proteome",
    effect_scale: "standardized_log2_abundance_contrast",
    effect_reference_id: "synthetic-v1",
  };
}

function compositionRequest(sampleId: string): Record<string, unknown> {
  return {
    profile_id: "gbm-rna-composition/0.1.0",
    sample_id: sampleId,
    feature_ids: ["EGFR", "PTPRC"],
    counts: [3, 2],
    references: [{ reference_id: "myeloid", signature: [0.8, 0.2] }],
    unknown_background: [0.5, 0.5],
    concentration: 10,
    lambda_mass: 0,
    lambda_shape: 0.1,
    initial_unknown_mass: 0.1,
    max_iterations: 20,
    bootstrap_replicates: 0,
    source_digests: [DIGEST],
    provenance_note: "caller supplied synthetic composition",
  };
}

function compositionResult(sampleId: string): Record<string, unknown> {
  return {
    result_id: "composition.result",
    profile_id: "gbm-rna-composition/0.1.0",
    profile_digest: DIGEST,
    request_digest: DIGEST,
    result_digest: DIGEST,
    sample_id: sampleId,
    feature_ids: ["EGFR", "PTPRC"],
    support: "limited",
    known_weights: [{ reference_id: "myeloid", rna_weight: 0.6, rank: 1 }],
    unknown_gene_mass: [0.1, 0.1],
    fitted_probabilities: [0.6, 0.4],
    unknown_mass: 0.2,
    unknown_mass_lower_bound: null,
    unknown_mass_upper_bound: null,
    bootstrap_replicates_used: 0,
    weight_intervals: [],
    objective: 1.2,
    initial_objective: 2.0,
    iterations: 4,
    kkt_residual: 0.0001,
    signature_condition_number: 2.5,
    objective_trace: [2.0, 1.2],
    trace_digest: DIGEST,
    ood: null,
    abstention_reason: null,
    source_digests: [DIGEST],
    limitations: ["synthetic composition child"],
  };
}

function profile(): Record<string, unknown> {
  return {
    profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
    algorithm_id: "gbm-microenvironment-graph",
    algorithm_version: "1.0.0",
    source_engine: "neftel-bulk-protein-programs/1.0.0",
    graph_engine: "glio-ecgi/1.0.0",
    auxiliary_source_engine: "gbm-proteomic-axes/1.0.0",
    composition_source_engine: "gbm-rna-composition/0.1.0",
    composition_source_profile_digest: DIGEST,
    source_profile_digest: DIGEST,
    graph_profile_digest: DIGEST,
    topology_digest: DIGEST,
    projection_policy: "bulk_program_location_and_rank_to_signed_gbm_state_graph_v3",
    auxiliary_projection_policy: "independent_published_gbm_axes_as_external_observations_v2",
    composition_projection_policy: "rna_composition_centered_log_ratio_to_all_channels_v1",
    projected_axis_signatures: [
      ["SWEET_KRAS_TARGETS_UP", "kras_targets"],
      ["HALLMARK_MYC_TARGETS_V1", "myc_targets"],
      ["WINTER_HYPOXIA_UP", "hypoxia"],
      ["VERHAAK_GLIOBLASTOMA_MESENCHYMAL", "mesenchymal"],
      ["VERHAAK_GLIOBLASTOMA_NEURAL", "neural"],
      ["VERHAAK_GLIOBLASTOMA_PRONEURAL", "proneural"],
      ["EGFR_UP.V1_UP", "egfr_targets"],
    ],
    auxiliary_standard_error_floor: 0.35,
    source_location_standard_error_floor: 0.05,
    source_rank_standard_error_floor: 0.10,
    source_location_quality_supported: 1.0,
    source_location_quality_limited: 0.5,
    source_rank_quality_supported: 0.85,
    source_rank_quality_limited: 0.40,
    composition_standard_error_floor: 0.25,
    composition_standard_error_cap: 20.0,
    composition_quality_weight: 0.75,
    composition_graph_reference_map: [["myeloid", "myeloid"], ["t_cell", "t_cell"], ["endothelial", "endothelial"]],
    supported_source_families: [
      "mesenchymal_like",
      "oligodendrocyte_progenitor_like",
      "neural_progenitor_like",
      "astrocyte_like",
      "cell_cycle",
    ],
    missing_families_are_not_negative: true,
    cell_fraction_claim_permitted: false,
    clinical_use_permitted: false,
    profile_digest: DIGEST,
  };
}

describe("GBM microenvironment graph UI contract", () => {
  it("validates a nested Neftel request and reports source statistics", () => {
    const request = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      sample_id: "sample-1",
      source_request: sourceRequest(),
      axis_request: null,
    };
    expect(validateMicroenvironmentGraphRequest(request)).toEqual([]);
    expect(microenvironmentGraphRequestStats(request)).toEqual({ observations: 1, active: 1, programs: 14 });
  });

  it("keeps the secondary axis receipt optional for source-only requests", () => {
    const request = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      sample_id: "sample-1",
      source_request: sourceRequest(),
    };
    expect(validateMicroenvironmentGraphRequest(request)).toEqual([]);
  });

  it("validates the optional count-native RNA composition child", () => {
    const request = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      sample_id: "sample-1",
      source_request: sourceRequest(),
      composition_request: compositionRequest("sample-1"),
    };
    expect(validateMicroenvironmentGraphRequest(request)).toEqual([]);
    expect(validateMicroenvironmentGraphRequest({
      ...request,
      composition_request: compositionRequest("other-sample"),
    }).join("\n")).toContain("composition_request.sample_id");
    expect(microenvironmentGraphRequestStats({ profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID, sample_id: "sample-1" })).toEqual({ observations: 0, active: 0, programs: 14 });
    expect(validateMicroenvironmentGraphRequest({
      ...request,
      composition_request: 42,
    }).join("\n")).toContain("composition_request must be an object");
  });

  it("rejects a mismatched nested sample and fails closed on profile policy", () => {
    const request = { profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID, sample_id: "sample-2", source_request: sourceRequest() };
    expect(validateMicroenvironmentGraphRequest(request).join("\n")).toContain("must match");
    expect(validateMicroenvironmentGraphProfile({ ...profile(), clinical_use_permitted: true }).join("\n")).toContain("forbid");
  });

  it("normalizes nested graph and source receipts without inventing a flat result", () => {
    const normalized = normalizeMicroenvironmentGraphResult({
      graph_result: { node_states: [{ node_id: "pathway.one", kind: "pathway", activity: 0.5, classification: "activated" }] },
      graph_request: { nodes: [], edges: [], observations: [] },
      source_result: { program_evidence: [] },
      axis_result: { signatures: gbmAnalysisResult.signatures },
    });
    expect(normalized.graphResult?.node_states).toHaveLength(1);
    expect(normalized.graphRequest?.nodes).toEqual([]);
    expect(normalized.sourcePrograms).toEqual([]);
    expect(normalized.axisSignatures).toHaveLength(7);
    expect(normalized.compositionResult).toBeNull();
  });

  it("admits the complete bridge receipt and replay envelope", () => {
    const request = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      sample_id: neftelDemoRequest.sample_id,
      source_request: neftelDemoRequest,
      axis_request: { ...gbmDemoRequest, sample_id: neftelDemoRequest.sample_id },
    };
    const bridgeProfile = {
      ...profile(),
      graph_profile_digest: algorithmProfile.profile_digest,
    };
    const result = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      profile_digest: bridgeProfile.profile_digest,
      request_digest: DIGEST,
      result_digest: DIGEST,
      sample_id: neftelDemoRequest.sample_id,
      source_result: neftelAnalysisResult,
      axis_result: { ...gbmAnalysisResult, sample_id: neftelDemoRequest.sample_id },
      graph_request: demoRequest,
      graph_result: { ...analysisResult, profile_digest: algorithmProfile.profile_digest },
      limitations: ["synthetic bridge evidence"],
      research_use_only: true,
      non_prescriptive: true,
    };
    expect(validateMicroenvironmentGraphDemo(request, bridgeProfile)).toEqual([]);
    expect(validateMicroenvironmentGraphResult(result, request, bridgeProfile)).toEqual([]);
    const { axis_result: _axisResult, ...sourceOnlyResult } = result;
    expect(validateMicroenvironmentGraphResult(sourceOnlyResult, request, bridgeProfile)).toEqual([]);
    expect(validateMicroenvironmentGraphResult({ ...sourceOnlyResult, axis_result: null }, request, bridgeProfile)).toEqual([]);
    expect(microenvironmentSupportedFamilyCount(neftelAnalysisResult)).toBe(1);
    const headers = { get: (name: string) => ({
      "X-GLIO-Profile-Digest": result.profile_digest,
      "X-GLIO-Request-Digest": result.request_digest,
      "X-GLIO-Result-Digest": result.result_digest,
    }[name] ?? null) };
    expect(validateMicroenvironmentGraphResultHeaders(headers, result)).toEqual([]);
    const verification = {
      verified: true,
      request_digest_match: true,
      source_replay_match: true,
      axis_replay_match: true,
      composition_replay_match: true,
      graph_replay_match: true,
      result_digest_match: true,
      semantic_match: true,
      recomputed_request_digest: result.request_digest,
      recomputed_result_digest: result.result_digest,
      message: "bridge replay matches",
    };
    expect(validateMicroenvironmentGraphVerification(verification, result, request, bridgeProfile)).toEqual([]);
  });

  it("preserves and validates the nested composition receipt and its abstention bindings", () => {
    const request = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      sample_id: "sample-1",
      source_request: sourceRequest(),
      composition_request: compositionRequest("sample-1"),
    };
    const bridgeProfile = { ...profile(), graph_profile_digest: algorithmProfile.profile_digest };
    const result = {
      profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
      profile_digest: bridgeProfile.profile_digest,
      request_digest: DIGEST,
      result_digest: DIGEST,
      sample_id: "sample-1",
      source_result: neftelAnalysisResult,
      graph_request: demoRequest,
      graph_result: { ...analysisResult, profile_digest: algorithmProfile.profile_digest },
      composition_result: compositionResult("sample-1"),
      limitations: ["synthetic bridge evidence"],
      research_use_only: true,
      non_prescriptive: true,
    };
    expect(validateMicroenvironmentGraphResult(result, request, bridgeProfile)).toEqual([]);
    expect(normalizeMicroenvironmentGraphResult(result).compositionResult?.sample_id).toBe("sample-1");
    expect(validateMicroenvironmentGraphResult({ ...result, composition_result: null }, request, bridgeProfile).join("\n")).toContain("composition_result is required");
    expect(validateMicroenvironmentGraphResult({ ...result, composition_result: compositionResult("sample-1") }, undefined, bridgeProfile).join("\n")).toContain("requires request.composition_request");
    expect(validateMicroenvironmentGraphResult({ ...result, composition_result: 7 }, request, bridgeProfile).join("\n")).toContain("must be an object");
    expect(validateMicroenvironmentGraphResult({ ...result, composition_result: { ...compositionResult("sample-1"), profile_digest: `sha256:${"b".repeat(64)}` } }, request, bridgeProfile).join("\n")).toContain("does not match profile.composition_source_profile_digest");
  });

  it("fails closed when a verified replay omits a nested composition match", () => {
    const request = { profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID, sample_id: "sample-1", source_request: sourceRequest() };
    const result = { sample_id: "sample-1", profile_digest: DIGEST };
    const verification = {
      verified: true,
      request_digest_match: true,
      source_replay_match: true,
      axis_replay_match: true,
      composition_replay_match: false,
      graph_replay_match: true,
      result_digest_match: true,
      semantic_match: true,
      recomputed_request_digest: DIGEST,
      recomputed_result_digest: DIGEST,
      message: "nested composition replay mismatch",
    };
    expect(validateMicroenvironmentGraphVerification(verification, result, request, profile()).join("\n")).toContain("requires every replay check");
  });
});
