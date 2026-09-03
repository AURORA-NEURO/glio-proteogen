import { describe, expect, it } from "vitest";

import {
  GBM_PROFILE_ID,
  GBM_SIGNATURE_IDS,
  gbmRequestStats,
  normalizeGbmSignatures,
  validateGbmRequest,
} from "../../src/lib/gbm-proteomic-axes";
import type { JsonObject } from "../../src/lib/research-state";

const digest = `sha256:${"a".repeat(64)}`;

const validRequest: JsonObject = {
  profile_id: GBM_PROFILE_ID,
  sample_id: "synthetic.gbm.001",
  measurements: [
    { gene_symbol: "EGFR", state: "observed", lfq_intensity: 12_500_000, log2_standard_error: 0.12, provenance_digest: digest },
    { gene_symbol: "PTEN", state: "left_censored", lfq_upper_limit: 10_000, provenance_digest: digest },
    { gene_symbol: "NF1", state: "missing", provenance_digest: digest },
    { gene_symbol: "PDGFRA", state: "unsupported", provenance_digest: digest },
  ],
  signature_ids: [GBM_SIGNATURE_IDS[0], GBM_SIGNATURE_IDS[2]],
  bootstrap_replicates: 8,
};

describe("GBM proteomic-axis request helpers", () => {
  it("accepts all explicit evidence states and reports request statistics", () => {
    expect(validateGbmRequest(validRequest)).toEqual([]);
    expect(gbmRequestStats(validRequest)).toEqual({ measurements: 4, observed: 1, signatures: 2 });
    expect(gbmRequestStats({ measurements: [] })).toEqual({ measurements: 0, observed: 0, signatures: 7 });
  });

  it("rejects malformed root fields and collection bounds", () => {
    const errors = validateGbmRequest({
      profile_id: "gbm-proteomic-axes/latest",
      sample_id: 7,
      measurements: {},
      signature_ids: "all",
      bootstrap_replicates: 7,
      unexpected: true,
    });
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: unexpected.",
      `profile_id must equal ${GBM_PROFILE_ID}.`,
      "sample_id must be a valid identifier (1–128 characters, beginning with a letter).",
      "measurements must be an array.",
      "At least one protein measurement is required.",
      "signature_ids must be an array.",
      "bootstrap_replicates must be zero or an integer from 8 through 256.",
    ]));
    expect(validateGbmRequest({ sample_id: "sample", measurements: Array.from({ length: 8_193 }, () => null) }))
      .toContain("The request exceeds the 8,192-measurement limit.");
  });

  it("rejects invalid measurement shapes, numbers, digests, and state semantics", () => {
    const errors = validateGbmRequest({
      sample_id: "sample",
      measurements: [
        null,
        {
          gene_symbol: "not_a_symbol",
          state: "detected",
          lfq_intensity: Number.POSITIVE_INFINITY,
          lfq_upper_limit: 0,
          log2_standard_error: 5,
          provenance_digest: "sha256:bad",
          unknown: true,
        },
        { gene_symbol: "EGFR", state: "observed", lfq_upper_limit: 2, provenance_digest: digest },
        { gene_symbol: "PTEN", state: "left_censored", lfq_intensity: 2, log2_standard_error: 0.1, provenance_digest: digest },
        { gene_symbol: "NF1", state: "missing", lfq_intensity: 3, provenance_digest: digest },
        { gene_symbol: "NF1", state: "unsupported", lfq_upper_limit: 4, provenance_digest: digest },
      ],
    });
    expect(errors).toEqual(expect.arrayContaining([
      "measurements[0] must be an object.",
      "measurements[1] contains unsupported fields: unknown.",
      "measurements[1].gene_symbol must be a canonical gene symbol of 1–32 characters.",
      "measurements[1].state must be one of: observed, left_censored, missing, unsupported.",
      "measurements[1].provenance_digest must be a lowercase sha256 digest.",
      "measurements[1].lfq_intensity must be a finite number or null.",
      "measurements[1].lfq_upper_limit must be within (0, 1000000000000000000].",
      "measurements[1].log2_standard_error must be within (0, 4].",
      "measurements[2] observed evidence requires LFQ intensity and no upper limit.",
      "measurements[3] left-censored evidence requires an LFQ upper limit only.",
      "measurements[4] missing/unsupported evidence cannot carry numeric LFQ values.",
      "measurements[5] missing/unsupported evidence cannot carry numeric LFQ values.",
      "Duplicate gene symbols: NF1.",
    ]));
  });

  it("enforces the exact seven-signature catalog and strict bootstrap count", () => {
    const errors = validateGbmRequest({
      ...validRequest,
      signature_ids: [
        GBM_SIGNATURE_IDS[0],
        GBM_SIGNATURE_IDS[0],
        "UNKNOWN_GBM_SIGNATURE",
        "1-invalid",
        GBM_SIGNATURE_IDS[1],
        GBM_SIGNATURE_IDS[2],
        GBM_SIGNATURE_IDS[3],
        GBM_SIGNATURE_IDS[4],
      ],
      bootstrap_replicates: 257,
    });
    expect(errors).toEqual(expect.arrayContaining([
      "The request exceeds the seven-signature limit.",
      "Duplicate signature identifiers: SWEET_KRAS_TARGETS_UP.",
      "signature_ids[2] is not a supported GBM signature.",
      "signature_ids[3] must be a valid identifier.",
      "bootstrap_replicates must be zero or an integer from 8 through 256.",
    ]));
    expect(validateGbmRequest({ ...validRequest, bootstrap_replicates: 0 })).toEqual([]);
  });
});

describe("GBM proteomic-axis result normalization", () => {
  it("normalizes supported, limited, and abstained signatures with typed drivers", () => {
    const signatures = normalizeGbmSignatures({
      signatures: [
        null,
        { signature_id: "ignored", support: "unknown" },
        {
          signature_id: GBM_SIGNATURE_IDS[0],
          display_name: "KRAS-like proteomic axis",
          support: "supported",
          published_score: 0.4123,
          lower_bound: 0.2,
          upper_bound: 0.6,
          model_feature_count: 3025,
          observed_feature_count: 1800,
          observed_feature_fraction: 1800 / 3025,
          missing_feature_count: 1225,
          missing_feature_ratio: 1225 / 3025,
          bootstrap_replicates_used: 64,
          top_feature_drivers: [
            null,
            { gene_symbol: "bad" },
            { gene_symbol: "EGFR", signed_contribution: 0.21, absolute_contribution: 0.21, declared_state: "observed", model_input_source: "observed_lfq" },
            { gene_symbol: "NF1", signed_contribution: -0.1, absolute_contribution: 0.1, declared_state: "not-declared", model_input_source: "published_zero_fill" },
            { gene_symbol: "PTEN", signed_contribution: 0.1, absolute_contribution: 0.1, model_input_source: "invalid" },
          ],
        },
        { signature_id: GBM_SIGNATURE_IDS[1], support: "limited" },
        { support: "abstained", abstention_reason: "insufficient coverage" },
      ],
    });

    expect(signatures).toHaveLength(3);
    expect(signatures[0]).toMatchObject({
      id: GBM_SIGNATURE_IDS[0],
      displayName: "KRAS-like proteomic axis",
      support: "supported",
      score: 0.4123,
      modelFeatureCount: 3025,
      observedFeatureCount: 1800,
      bootstrapReplicates: 64,
    });
    expect(signatures[0].drivers).toEqual([
      { geneSymbol: "EGFR", signedContribution: 0.21, absoluteContribution: 0.21, declaredState: "observed", inputSource: "observed_lfq" },
      { geneSymbol: "NF1", signedContribution: -0.1, absoluteContribution: 0.1, declaredState: null, inputSource: "published_zero_fill" },
    ]);
    expect(signatures[1]).toMatchObject({
      id: GBM_SIGNATURE_IDS[1],
      displayName: GBM_SIGNATURE_IDS[1],
      support: "limited",
      score: null,
      drivers: [],
    });
    expect(signatures[2]).toMatchObject({
      id: "unnamed-signature",
      displayName: "Unnamed signature",
      support: "abstained",
      abstentionReason: "insufficient coverage",
    });
  });
});
