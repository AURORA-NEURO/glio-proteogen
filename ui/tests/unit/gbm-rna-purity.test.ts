import { describe, expect, it } from "vitest";

import {
  GBM_RNA_PURITY_CONTEXT,
  GBM_RNA_PURITY_MODEL_FEATURE_COUNT,
  GBM_RNA_PURITY_PROFILE_ID,
  gbmRnaPurityRequestStats,
  normalizeGbmRnaPurityResult,
  validateGbmRnaPurityRequest,
} from "../../src/lib/gbm-rna-purity";
import type { JsonObject } from "../../src/lib/research-state";

const digest = `sha256:${"a".repeat(64)}`;
const valid: JsonObject = {
  schema_version: "glio-proteogen.gbm-rna-purity-request/1.0.0",
  sample_id: "synthetic.primary.idhwt.gbm",
  profile_id: GBM_RNA_PURITY_PROFILE_ID,
  context: { ...GBM_RNA_PURITY_CONTEXT },
  counts_provenance_digest: digest,
  counts: [
    { gene_symbol: "EGFR", raw_count: 1200 },
    { gene_symbol: "PTEN", raw_count: 0 },
    { gene_symbol: "CDKN2A", raw_count: 45.5 },
  ],
};

function supportedResult(): JsonObject {
  return {
    support: "supported",
    coverage: {
      model_feature_count: 5829,
      supplied_gene_count: 5831,
      recognized_model_gene_count: 5829,
      missing_model_gene_count: 0,
      ignored_non_model_gene_count: 2,
      nonzero_model_gene_count: 5800,
      coverage_fraction: 1,
      recognized_raw_count_sum: 9916184,
      missing_gene_policy: "source_parity_zero_fill_after_80_percent_gate",
    },
    estimate: {
      malignant_cell_fraction: 0.1324209,
      raw_unclipped_output: 0.1324209,
      clipping_state: "none",
      model_output_semantics: "published_GBMPurity_estimated_malignant_cell_fraction",
    },
    diagnostics: {
      preprocessing: "source_order_zero_fill_then_RPK_share_times_1e4_then_log2_plus_1",
      network: "5829_to_32_relu_to_16_relu_to_1_linear_eval_mode",
      dropout_active: false,
      inference_dtype: "float32",
      finite_inference: true,
      transformed_input_sum: 7578.01257993,
      transformed_input_maximum: 4.3257575,
      hidden_trace: {
        first_layer_active_nodes: 10,
        second_layer_active_nodes: 5,
        activation_pattern_digest: digest,
      },
    },
    explanation: {
      method: "exact_active_relu_path_decomposition",
      top_gene_attributions: [
        {
          rank: 1,
          gene_symbol: "NOSTRIN",
          transformed_expression: 1.69146812,
          local_gradient: -0.0056269,
          raw_output_contribution: -0.00951772,
          direction: "lowers_raw_estimate",
        },
        {
          rank: 2,
          gene_symbol: "GPR157",
          transformed_expression: 1.63651955,
          local_gradient: 0.00579154,
          raw_output_contribution: 0.00947797,
          direction: "raises_raw_estimate",
        },
      ],
      all_gene_contribution_sum: 0.26437496,
      active_path_bias_contribution: -0.13195424,
      reconstructed_raw_output: 0.13242073,
      reconstruction_absolute_error: 1.7e-7,
      clipping_changes_local_interpretation: false,
      interpretation: "local_piecewise_linear_attribution_not_causal_gene_importance",
    },
    uncertainty_status: "not_available_in_published_single_model",
    uncertainty_reason: "The published release contains one fitted MLP and no calibrated ensemble.",
    provenance: {
      source_repository: "https://github.com/scmpht/GBMPurity",
      source_commit: "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950",
      source_model_sha256: digest,
      article_doi: "10.1093/neuonc/noaf026",
    },
    abstention_reasons: [],
  };
}

describe("GBMPurity raw-count request helpers", () => {
  it("mirrors the exact disease/assay attestation and reports request statistics", () => {
    expect(validateGbmRnaPurityRequest(valid)).toEqual([]);
    expect(gbmRnaPurityRequestStats(valid)).toEqual({
      suppliedGenes: 3,
      uniqueGenes: 3,
      nonzeroGenes: 2,
      totalRawCount: 1245.5,
    });

    const withoutDefaults = { ...valid };
    delete withoutDefaults.schema_version;
    delete withoutDefaults.profile_id;
    expect(validateGbmRnaPurityRequest(withoutDefaults)).toEqual([]);
  });

  it("rejects context drift, malformed raw counts, unknown fields, and duplicate genes", () => {
    const errors = validateGbmRnaPurityRequest({
      ...valid,
      profile_id: "latest",
      sample_id: "bad id",
      counts_provenance_digest: "forged",
      extra: true,
      context: {
        ...GBM_RNA_PURITY_CONTEXT,
        disease_context: "lower_grade_glioma",
        batch_corrected: true,
        extra: true,
      },
      counts: [
        { gene_symbol: "EGFR", raw_count: -1, extra: true },
        { gene_symbol: "EGFR", raw_count: Number.POSITIVE_INFINITY },
        { gene_symbol: "bad symbol", raw_count: 2 },
        null,
      ],
    });
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: extra.",
      `profile_id must equal ${GBM_RNA_PURITY_PROFILE_ID}.`,
      "sample_id must be a valid identifier.",
      "counts_provenance_digest must be a lowercase sha256 digest.",
      "context contains unsupported fields: extra.",
      "context.disease_context must equal \"primary_IDH_wildtype_glioblastoma\".",
      "context.batch_corrected must equal false.",
      "counts[0] contains unsupported fields: extra.",
      "counts[0].raw_count must be a finite number within [0, 1e15].",
      "counts[1].raw_count must be a finite number within [0, 1e15].",
      "counts[2].gene_symbol must use the source-compatible gene-symbol syntax.",
      "counts[3] must be an object.",
      "Duplicate gene symbols: EGFR. Counts are never summed implicitly.",
    ]));
  });

  it("requires a bounded raw-count array and the full context object", () => {
    expect(validateGbmRnaPurityRequest({ counts: {} })).toEqual(expect.arrayContaining([
      "sample_id must be a valid identifier.",
      "counts_provenance_digest must be a lowercase sha256 digest.",
      "context must be the exact primary IDH-wildtype GBM bulk-RNA attestation object.",
      "counts must be an array.",
      "At least one raw gene count is required.",
    ]));

    const oversized = Array.from({ length: 40_001 }, (_, index) => ({ gene_symbol: `G${index}`, raw_count: 0 }));
    expect(validateGbmRnaPurityRequest({ ...valid, counts: oversized })).toContain("The request exceeds the 40,000-gene limit.");
  });
});

describe("GBMPurity result normalization", () => {
  it("preserves coverage, clipping, hidden activations, and exact local contributions", () => {
    const evidence = normalizeGbmRnaPurityResult(supportedResult());
    expect(evidence).not.toBeNull();
    expect(evidence?.support).toBe("supported");
    expect(evidence?.coverage).toMatchObject({
      modelFeatureCount: GBM_RNA_PURITY_MODEL_FEATURE_COUNT,
      recognizedModelGeneCount: 5829,
      ignoredNonModelGeneCount: 2,
      coverageFraction: 1,
    });
    expect(evidence?.estimate).toEqual({
      malignantCellFraction: 0.1324209,
      rawUnclippedOutput: 0.1324209,
      clippingState: "none",
      outputSemantics: "published_GBMPurity_estimated_malignant_cell_fraction",
    });
    expect(evidence?.diagnostics).toMatchObject({
      firstLayerActiveNodes: 10,
      secondLayerActiveNodes: 5,
      dropoutActive: false,
      finiteInference: true,
      activationPatternDigest: digest,
    });
    expect(evidence?.explanation?.attributions).toEqual([
      expect.objectContaining({ rank: 1, geneSymbol: "NOSTRIN", direction: "lowers_raw_estimate", rawOutputContribution: -0.00951772 }),
      expect.objectContaining({ rank: 2, geneSymbol: "GPR157", direction: "raises_raw_estimate", rawOutputContribution: 0.00947797 }),
    ]);
    expect(evidence?.explanation).toMatchObject({
      reconstructedRawOutput: 0.13242073,
      reconstructionAbsoluteError: 1.7e-7,
      clippingChangesLocalInterpretation: false,
    });
    expect(evidence?.uncertaintyStatus).toBe("not_available_in_published_single_model");
  });

  it("preserves an abstention without inventing an estimate or explanation", () => {
    const abstained = supportedResult();
    abstained.support = "abstained";
    abstained.estimate = null;
    abstained.explanation = null;
    abstained.abstention_reasons = ["Exact model-gene overlap is below the published 80% minimum."];
    const evidence = normalizeGbmRnaPurityResult(abstained);
    expect(evidence).toMatchObject({
      support: "abstained",
      estimate: null,
      explanation: null,
      abstentionReasons: ["Exact model-gene overlap is below the published 80% minimum."],
    });
  });

  it("rejects result documents without the core support, coverage, or diagnostic structure", () => {
    expect(normalizeGbmRnaPurityResult({})).toBeNull();
    expect(normalizeGbmRnaPurityResult({ support: "unknown", coverage: {}, diagnostics: {} })).toBeNull();
    expect(normalizeGbmRnaPurityResult({ support: "supported", diagnostics: {} })).toBeNull();
  });

  it("normalizes sparse limited evidence with conservative numeric and trace defaults", () => {
    const evidence = normalizeGbmRnaPurityResult({
      support: "limited",
      coverage: {},
      diagnostics: {},
      estimate: {},
      explanation: { top_gene_attributions: [null, {}] },
    });

    expect(evidence).toMatchObject({
      support: "limited",
      coverage: {
        modelFeatureCount: GBM_RNA_PURITY_MODEL_FEATURE_COUNT,
        suppliedGeneCount: 0,
        recognizedModelGeneCount: 0,
        missingModelGeneCount: 0,
        ignoredNonModelGeneCount: 0,
        nonzeroModelGeneCount: 0,
        coverageFraction: 0,
        recognizedRawCountSum: 0,
        missingGenePolicy: "not reported",
      },
      estimate: null,
      diagnostics: {
        preprocessing: "not reported",
        network: "not reported",
        dropoutActive: false,
        inferenceDtype: "not reported",
        finiteInference: false,
        transformedInputSum: 0,
        transformedInputMaximum: 0,
        firstLayerActiveNodes: null,
        secondLayerActiveNodes: null,
        activationPatternDigest: "",
      },
      explanation: {
        method: "not reported",
        attributions: [],
        allGeneContributionSum: 0,
        activePathBiasContribution: 0,
        reconstructedRawOutput: 0,
        reconstructionAbsoluteError: 0,
        clippingChangesLocalInterpretation: false,
        interpretation: "not reported",
      },
      uncertaintyStatus: "not reported",
      uncertaintyReason: "No uncertainty statement was returned.",
      abstentionReasons: [],
      provenance: null,
    });
  });
});
