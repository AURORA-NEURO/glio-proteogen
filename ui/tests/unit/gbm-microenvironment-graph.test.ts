import { describe, expect, it } from "vitest";

import {
  GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
  microenvironmentGraphRequestStats,
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

function profile(): Record<string, unknown> {
  return {
    profile_id: GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
    algorithm_id: "gbm-microenvironment-graph",
    algorithm_version: "1.0.0",
    source_engine: "neftel-bulk-protein-programs/1.0.0",
    graph_engine: "glio-ecgi/1.0.0",
    auxiliary_source_engine: "gbm-proteomic-axes/1.0.0",
    source_profile_digest: DIGEST,
    graph_profile_digest: DIGEST,
    topology_digest: DIGEST,
    projection_policy: "supported_bulk_programs_to_signed_microenvironment_graph_v1",
    auxiliary_projection_policy: "independent_published_gbm_axes_as_secondary_observations_v1",
    supported_source_families: ["mesenchymal_like", "oligodendrocyte_progenitor_like"],
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
    };
    expect(validateMicroenvironmentGraphRequest(request)).toEqual([]);
    expect(microenvironmentGraphRequestStats(request)).toEqual({ observations: 1, active: 1, programs: 7 });
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
      graph_replay_match: true,
      result_digest_match: true,
      semantic_match: true,
      recomputed_request_digest: result.request_digest,
      recomputed_result_digest: result.result_digest,
      message: "bridge replay matches",
    };
    expect(validateMicroenvironmentGraphVerification(verification, result, request, bridgeProfile)).toEqual([]);
  });
});
