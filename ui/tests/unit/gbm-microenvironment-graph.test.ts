import { describe, expect, it } from "vitest";

import {
  GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID,
  microenvironmentGraphRequestStats,
  normalizeMicroenvironmentGraphResult,
  validateMicroenvironmentGraphProfile,
  validateMicroenvironmentGraphRequest,
} from "../../src/lib/gbm-microenvironment-graph";

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
    source_profile_digest: DIGEST,
    graph_profile_digest: DIGEST,
    topology_digest: DIGEST,
    projection_policy: "supported_bulk_programs_to_signed_microenvironment_graph_v1",
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
    expect(microenvironmentGraphRequestStats(request)).toEqual({ observations: 1, active: 1, programs: 5 });
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
    });
    expect(normalized.graphResult?.node_states).toHaveLength(1);
    expect(normalized.graphRequest?.nodes).toEqual([]);
    expect(normalized.sourcePrograms).toEqual([]);
  });
});
