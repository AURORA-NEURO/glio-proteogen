import { describe, expect, it } from "vitest";

import {
  GBM_RNA_COMPOSITION_PROFILE_ID,
  gbmRnaCompositionRequestStats,
  normalizeGbmMixtureResult,
  mixtureProvenance,
  validateGbmMixtureDemo,
  validateGbmMixtureProfile,
  validateGbmMixtureRequest,
  validateGbmMixtureResult,
  validateGbmMixtureResultHeaders,
  validateGbmMixtureVerification,
} from "../../src/lib/gbm-rna-composition";

const digest = "sha256:" + "a".repeat(64);
const request = {
  profile_id: GBM_RNA_COMPOSITION_PROFILE_ID,
  sample_id: "sample-1",
  feature_ids: ["EGFR", "SOX2"],
  counts: [80, 20],
  references: [{ reference_id: "malignant_gbm", signature: [0.8, 0.2] }],
  unknown_background: [0.5, 0.5],
  concentration: 100,
  lambda_mass: 0,
  lambda_shape: 0.03,
  initial_unknown_mass: 0.05,
  max_iterations: 500,
  source_digests: [digest],
  provenance_note: "caller supplied marker signatures",
};
const profile = {
  profile_id: GBM_RNA_COMPOSITION_PROFILE_ID,
  algorithm_id: "gbm-rna-composition",
  algorithm_version: "0.1.0",
  numpy_version: "2.5.2",
  execution_scope: "caller_supplied_reference_only",
  output_semantics: "rna_mixture_weights_with_unknown_mass",
  histologic_fraction_claim_permitted: false,
  clinical_use_permitted: false,
  solver: "dirichlet_multinomial_adaptive_unknown_simplex",
  max_features: 512,
  max_lineages: 32,
  max_iterations: 500,
  kkt_tolerance: 0.00001,
  l1_step_tolerance: 0.00001,
  relative_objective_tolerance: 1e-9,
  profile_digest: digest,
};
const result = {
  result_id: "result-sample-1",
  profile_id: GBM_RNA_COMPOSITION_PROFILE_ID,
  profile_digest: digest,
  request_digest: digest,
  result_digest: digest,
  sample_id: "sample-1",
  feature_ids: ["EGFR", "SOX2"],
  support: "limited",
  known_weights: [{ reference_id: "malignant_gbm", rna_weight: 0.9, rank: 1 }],
  unknown_gene_mass: [0.05, 0.05],
  fitted_probabilities: [0.8, 0.2],
  unknown_mass: 0.1,
  objective: 1,
  initial_objective: 2,
  iterations: 10,
  kkt_residual: 1e-7,
  signature_condition_number: 2,
  objective_trace: [2, 1],
  trace_digest: digest,
  ood: { ood_score: 0.1 },
  abstention_reason: null,
  source_digests: [digest],
  limitations: ["research only"],
};

describe("GBM RNA composition UI contract", () => {
  it("counts feature depth and caller references", () => {
    expect(gbmRnaCompositionRequestStats(request)).toEqual({ features: 2, nonzero: 2, references: 1, depth: 100 });
  });

  it("admits a profile, demo, result headers, and replay receipt", () => {
    expect(validateGbmMixtureProfile(profile)).toEqual([]);
    expect(validateGbmMixtureRequest(request)).toEqual([]);
    expect(validateGbmMixtureDemo(request, profile, { get: () => digest })).toEqual([]);
    expect(validateGbmMixtureResult(result, request, profile)).toEqual([]);
    expect(validateGbmMixtureResultHeaders({ get: () => digest }, result)).toEqual([]);
    expect(validateGbmMixtureVerification({ verified: true, request_digest: digest, result_digest: digest }, result, request, profile)).toEqual([]);
  });

  it("normalizes fitted weights, diagnostics, and unknown channel", () => {
    expect(normalizeGbmMixtureResult(result)).toMatchObject({ support: "limited", unknownMass: 0.1, objective: 1, trace: [2, 1], conditionNumber: 2 });
    expect(normalizeGbmMixtureResult(result).weights[0]).toMatchObject({ id: "malignant_gbm", weight: 0.9, rank: 1 });
  });

  it("rejects duplicate axes, malformed signatures, and unsupported receipts", () => {
    expect(validateGbmMixtureRequest({ ...request, feature_ids: ["EGFR", "EGFR"] }).length).toBeGreaterThan(0);
    expect(validateGbmMixtureRequest({ ...request, references: [{ reference_id: "malignant_gbm", signature: [1] }] }).length).toBeGreaterThan(0);
    expect(validateGbmMixtureProfile({ profile_id: "wrong" }).length).toBeGreaterThan(5);
    expect(validateGbmMixtureResult({ result_id: "x" }, null, null).length).toBeGreaterThan(5);
    expect(validateGbmMixtureResultHeaders({ get: () => null }, result)).toHaveLength(3);
    expect(validateGbmMixtureVerification({ verified: false, request_digest: "bad", result_digest: "bad", extra: true }, result, request, profile).length).toBeGreaterThan(2);
  });

  it("requires a demo request digest header when headers are supplied", () => {
    expect(validateGbmMixtureDemo(request, profile, { get: () => null })).toContain("demo response must expose a canonical request digest header.");
  });

  it("exercises fail-closed boundaries for every request dimension", () => {
    const invalid = {
      ...request,
      profile_id: "wrong",
      sample_id: "bad id",
      feature_ids: ["EGFR"],
      counts: [-1, null],
      unknown_background: [0.2],
      references: [null, { reference_id: "bad id", signature: [2, null] }],
      concentration: -1,
      lambda_mass: -1,
      lambda_shape: -1,
      initial_unknown_mass: 1,
      max_iterations: 0,
      source_digests: ["bad"],
      provenance_note: "",
    };
    expect(validateGbmMixtureRequest(invalid).length).toBeGreaterThan(10);
    expect(validateGbmMixtureRequest({ ...request, counts: [0, 0], unknown_background: [0.4, 0.4], references: [{ reference_id: "x", signature: [0.8, 0.8] }] }).length).toBeGreaterThan(0);
    expect(validateGbmMixtureRequest({ ...request, concentration: 0, unknown_background: [0, 1], references: [{ reference_id: "x", signature: [0, 1] }] }).length).toBeGreaterThan(0);
    expect(validateGbmMixtureRequest({ ...request, references: [] }).length).toBeGreaterThan(0);
    expect(validateGbmMixtureResult({ ...result, support: "limited", known_weights: [], unknown_gene_mass: [], fitted_probabilities: [], unknown_mass: 2 }, request, profile).length).toBeGreaterThan(0);
    expect(validateGbmMixtureResult({ ...result, support: "abstained", feature_ids: ["EGFR"], unknown_gene_mass: [], fitted_probabilities: [] }, request, profile).length).toBe(0);
    expect(normalizeGbmMixtureResult({ ...result, known_weights: [null], ood: null, objective_trace: [null] }).weights).toHaveLength(0);
    expect(mixtureProvenance({ provenance: { source: "caller" } })).toEqual({ source: "caller" });
    expect(mixtureProvenance({})).toBeNull();
  });
});
