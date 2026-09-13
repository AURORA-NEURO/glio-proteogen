import { describe, expect, it } from "vitest";

import {
  IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID,
  normalizePresentationCandidates,
  presentationRequestStats,
  presentationProvenance,
  validatePresentationDemo,
  validatePresentationProfile,
  validatePresentationRequest,
  validatePresentationResult,
  validatePresentationResultHeaders,
  validatePresentationVerification,
} from "../../src/lib/immunopeptidomic-presentation";

const digest = "sha256:" + "a".repeat(64);

const request = {
  profile_id: IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID,
  sample_id: "sample-1",
  hla_alleles: ["HLA-A*02:01"],
  peptides: [
    { peptide_id: "pep-1", sequence: "SLYNTVATL", source_gene: "EGFR", state: "observed", expression_effect: 1.2, expression_standard_error: 0.2, quality_weight: 0.9 },
    { peptide_id: "pep-2", sequence: "LLGRNSFEV", source_gene: "PDGFRA", state: "left_censored", detection_limit: -1.0, quality_weight: 0.8 },
  ],
  models: [{ allele: "HLA-A*02:01", model_digest: digest }],
  bootstrap_replicates: 64,
  source_digests: [digest],
  provenance_note: "caller model",
};

describe("glioma immunopeptidomic presentation UI contract", () => {
  it("counts informative peptides, alleles, and caller models", () => {
    expect(presentationRequestStats(request)).toEqual({ peptides: 2, informative: 2, alleles: 1, models: 1 });
  });

  it("rejects unsupported peptide evidence states carrying numeric values", () => {
    const invalid = { ...request, peptides: [{ ...request.peptides[0], state: "missing", expression_effect: 1 }] };
    expect(validatePresentationRequest(invalid)).toContain("request.peptides[0] missing evidence cannot carry numeric values.");
  });

  it("normalizes ranked candidates and preserves ablation explanations", () => {
    const candidates = normalizePresentationCandidates({ candidates: [{ peptide_id: "pep-1", sequence: "SLYNTVATL", source_gene: "EGFR", support: "supported", presentation_probability: 0.8, interval_low: 0.7, interval_high: 0.9, rank: 1, supported_alleles: [{}], top_drivers: ["binding:HLA-A*02:01"], ablations: [{ component: "binding", probability_delta: 0.3 }] }] });
    expect(candidates[0]).toMatchObject({ id: "pep-1", probability: 0.8, rank: 1, alleles: 1, drivers: ["binding:HLA-A*02:01"] });
    expect(candidates[0]?.ablations[0]?.delta).toBe(0.3);
  });

  it("admits the profile, demo, result headers, and replay receipt", () => {
    const profile = {
      profile_id: IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID,
      algorithm_id: "glioma-immunopeptidomic-presentation",
      algorithm_version: "0.1.0",
      numpy_version: "2.5.2",
      execution_scope: "caller_supplied_hla_model_only",
      score_model: "allele_pssm_processing_logit",
      binding_score_policy: "position_log_odds_sum_v1",
      allele_aggregation_policy: "independent_allele_noisy_or_v1",
      max_peptides: 256,
      max_alleles: 16,
      default_bootstrap_replicates: 64,
      clinical_use_permitted: false,
      treatment_recommendation_permitted: false,
      profile_digest: digest,
    };
    expect(validatePresentationProfile(profile)).toEqual([]);
    expect(validatePresentationDemo(request, profile)).toEqual([]);
    const result = {
      result_id: "presentation-sample-1",
      profile_id: IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID,
      profile_digest: digest,
      request_digest: digest,
      result_digest: digest,
      sample_id: "sample-1",
      support: "supported",
      candidates: [],
      supported_peptide_count: 0,
      supported_allele_count: 0,
      model_digests: [digest],
      bootstrap_replicates: 64,
      abstention_reason: null,
      limitations: ["research only"],
    };
    expect(validatePresentationResult(result, request, profile)).toEqual([]);
    expect(validatePresentationResultHeaders({ get: (name) => name === "X-GLIO-Profile-Digest" ? digest : name === "X-GLIO-Request-Digest" ? digest : digest }, result)).toEqual([]);
    expect(validatePresentationVerification({ verified: true, request_digest: digest, result_digest: digest }, result, request, profile)).toEqual([]);
  });

  it("fails closed for malformed profile, request, receipt, headers, and replay", () => {
    expect(validatePresentationProfile({ profile_id: "wrong" }).length).toBeGreaterThan(5);
    const malformed = { ...request, hla_alleles: ["bad", "bad"], peptides: [null, { peptide_id: "x", sequence: "bad", source_gene: "", state: "missing", expression_effect: 1, detection_limit: 1 }], models: [null, { allele: "bad" }], source_digests: ["bad"], provenance_note: "", bootstrap_replicates: 1.5 };
    expect(validatePresentationRequest(malformed).length).toBeGreaterThan(5);
    expect(validatePresentationResult({ result_id: "x" }, null, null).length).toBeGreaterThan(5);
    expect(validatePresentationResultHeaders({ get: () => null }, { profile_digest: digest, request_digest: digest, result_digest: digest }).length).toBe(3);
    expect(validatePresentationVerification({ verified: false, request_digest: "bad", result_digest: "bad", extra: true }, { profile_digest: digest, result_digest: digest }, request, { profile_digest: "other" }).length).toBeGreaterThan(3);
    expect(validatePresentationRequest({ peptides: [] }).length).toBeGreaterThan(0);
    expect(validatePresentationDemo(request, { profile_id: "other" }).length).toBeGreaterThan(0);
    expect(validatePresentationResult({ profile_digest: digest, sample_id: "other" }, request, { profile_digest: "other" }).length).toBeGreaterThan(0);
    expect(validatePresentationRequest({ ...request, peptides: [{ sequence: "SLYNTVATL", source_gene: "EGFR", state: "observed", detection_limit: 0 }, { peptide_id: "dup", sequence: "SLYNTVATL", source_gene: "EGFR", state: "weird" }, { peptide_id: "dup", sequence: "SLYNTVATL", source_gene: "EGFR", state: "left_censored", detection_limit: 0, expression_effect: 1 }], models: [{ allele: "HLA-B*07:02" }] }).length).toBeGreaterThan(4);
    expect(presentationProvenance({ provenance: { source: "caller" } })).toEqual({ source: "caller" });
    expect(presentationProvenance({})).toBeNull();
    expect(normalizePresentationCandidates({ candidates: [null, { peptide_id: "x", ablations: [null] }] })).toHaveLength(1);
  });
});
