import { describe, expect, it } from "vitest";

import {
  FUNCTIONAL_PROTEOTYPE_AXES,
  FUNCTIONAL_PROTEOTYPE_PROFILE_ID,
  functionalProteotypeRequestStats,
  normalizeFunctionalProteotypeAxes,
  validateFunctionalProteotypeRequest,
} from "../../src/lib/gbm-functional-proteotype";
import type { JsonObject } from "../../src/lib/research-state";
import {
  functionalProteotypeAnalysis,
  functionalProteotypeDemo,
  functionalProteotypeProfile,
  functionalProteotypeVerification,
} from "../fixtures/gbm-functional-proteotype";

const digest = `sha256:${"a".repeat(64)}`;
const valid: JsonObject = {
  profile_id: FUNCTIONAL_PROTEOTYPE_PROFILE_ID,
  sample_id: "synthetic.functional.proteotype",
  effect_reference_id: "synthetic.bulk.reference.v1",
  effect_scale: "standardized_log2_abundance_contrast",
  observations: [
    { observation_id: "obs.one", gene_symbol: "CSTA", state: "observed", standardized_effect: 1.2, standard_error: 0.3, quality_weight: 0.9, provenance_digest: digest },
    { observation_id: "obs.two", gene_symbol: "PNPO", state: "left_censored", standardized_effect: -0.4, standard_error: 0.4, quality_weight: 0.8, provenance_digest: digest },
    { observation_id: "obs.three", gene_symbol: "CRHBP", state: "missing", quality_weight: 0, provenance_digest: digest },
    { observation_id: "obs.four", gene_symbol: "ZNF219", state: "unsupported", quality_weight: 0, provenance_digest: digest },
  ],
  bootstrap_replicates: 16,
  permutation_replicates: 64,
};

function axisEvidence(axis: string, estimate: number): JsonObject {
  return {
    axis,
    support: "supported",
    classification: estimate > 0.25 ? "source_aligned" : estimate < -0.25 ? "source_opposed" : "neutral",
    latent: {
      estimate,
      lower_bound: estimate - 0.2,
      upper_bound: estimate + 0.2,
      nominal_coverage: 0.9,
      bootstrap_replicates_used: 16,
    },
    rank: {
      signature_observed_count: 24,
      complement_observed_count: 72,
      u_statistic: 318,
      rank_biserial: estimate / 2,
      tie_correction: 0.98,
      null_standard_deviation: 0.2,
      empirical_p_value: 0.02,
      q_value: 0.04,
      permutation_replicates_used: 64,
    },
    evidence_counts: {
      source_signature_proteins: 150,
      declared_signature_proteins: 27,
      observed_signature_proteins: 24,
      left_censored_signature_proteins: 1,
      missing_signature_proteins: 1,
      unsupported_signature_proteins: 1,
      unreported_signature_proteins: 123,
      observed_background_proteins: 72,
      active_signature_fraction: 25 / 150,
    },
    effective_sample_size: 24.7,
    stability: 0.91,
    discordance: 0.08,
    top_drivers: [{
      observation_id: `driver.${axis}`,
      gene_symbol: "CSTA",
      source_protein_label: "CSTA",
      axis,
      source_rank: 4,
      source_rank_quartile: 1,
      source_mww_score: 3.8,
      evidence_state: "observed",
      value_role: "observed_point",
      standardized_effect: 1.2,
      reliability_weight: 4.3,
      source_loading: 0.7,
      signed_contribution: 3.61,
      absolute_contribution: 3.61,
    }],
    ablations: [{
      kind: "source_rank_quartile",
      target: "source_rank_quartile:1",
      proteins_removed: 25,
      support_after_ablation: "abstained",
      baseline_estimate: null,
      ablated_estimate: null,
      estimate_delta: null,
      classification_after_ablation: "not_estimable",
      reason: "Fewer than the exploratory minimum active signature proteins remain.",
    }],
    source_cohort_pathway_context: [{
      axis,
      source_rank: 1,
      pathway_name: `${axis} published pathway`,
      source_logit_nes: 1.7,
      source_p_value: 0.001,
      source_q_value: 0.003,
      sample_inference_status: "not_evaluated",
      interpretation: "source_cohort_pathway_context_only",
    }],
    abstention_reasons: [],
  };
}

describe("GBM functional-proteotype request helpers", () => {
  it("validates explicit evidence semantics, optional defaults, and request statistics", () => {
    expect(validateFunctionalProteotypeRequest(valid)).toEqual([]);
    const withoutDefaults = { ...valid };
    delete withoutDefaults.profile_id;
    delete withoutDefaults.effect_scale;
    delete withoutDefaults.bootstrap_replicates;
    delete withoutDefaults.permutation_replicates;
    expect(validateFunctionalProteotypeRequest(withoutDefaults)).toEqual([]);
    expect(functionalProteotypeRequestStats(valid)).toEqual({ observations: 4, active: 2, observed: 1, leftCensored: 1, genes: 4, axes: 4 });
    expect(functionalProteotypeRequestStats({})).toEqual({ observations: 0, active: 0, observed: 0, leftCensored: 0, genes: 0, axes: 4 });
  });

  it("rejects unknown fields, malformed roots, and bounded replicate violations", () => {
    const errors = validateFunctionalProteotypeRequest({
      profile_id: "latest",
      sample_id: 7,
      effect_reference_id: "bad id",
      effect_scale: "raw",
      observations: [null],
      bootstrap_replicates: 15,
      permutation_replicates: 2_049,
      unknown: true,
    });
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: unknown.",
      `profile_id must equal ${FUNCTIONAL_PROTEOTYPE_PROFILE_ID}.`,
      "sample_id must be a valid identifier.",
      "effect_reference_id must be a valid identifier.",
      "effect_scale must equal standardized_log2_abundance_contrast.",
      "observations[0] must be an object.",
      "bootstrap_replicates must be an integer from 16 through 256.",
      "permutation_replicates must be an integer from 64 through 2,048.",
    ]));
    expect(validateFunctionalProteotypeRequest({ observations: {} })).toEqual(expect.arrayContaining([
      "observations must be an array.",
      "At least one protein observation is required.",
    ]));
  });

  it("keeps missing and unsupported values non-numeric and enforces exact identity uniqueness", () => {
    const errors = validateFunctionalProteotypeRequest({
      ...valid,
      observations: [
        { observation_id: "bad id", gene_symbol: "bad_gene", state: "detected", standardized_effect: 21, standard_error: 0, quality_weight: 2, provenance_digest: "bad", extra: true },
        { observation_id: "obs.duplicate", gene_symbol: "VIM", state: "observed", provenance_digest: digest },
        { observation_id: "obs.duplicate", gene_symbol: "VIM", state: "missing", standardized_effect: -1, standard_error: 0.3, provenance_digest: digest },
      ],
    });
    expect(errors).toEqual(expect.arrayContaining([
      "observations[0] contains unsupported fields: extra.",
      "observations[0].observation_id must be a valid identifier.",
      "observations[0].gene_symbol must use valid gene-symbol syntax; exact Table 2d membership is enforced by the backend.",
      "observations[0].state must be one of: observed, left_censored, missing, unsupported.",
      "observations[0].provenance_digest must be a lowercase sha256 digest.",
      "observations[1] active evidence requires an effect, positive standard error, and positive quality weight.",
      "observations[2] missing/unsupported evidence requires no numeric effect/error and zero quality weight.",
      "Duplicate observation identifiers: obs.duplicate.",
      "Duplicate gene symbols: VIM.",
    ]));
  });
});

describe("GBM functional-proteotype result normalization", () => {
  it("keeps the browser lifecycle snapshot coherent with the exact admitted demo and engine support gates", () => {
    const demo = functionalProteotypeDemo as unknown as JsonObject;
    const result = functionalProteotypeAnalysis as unknown as JsonObject;
    expect(validateFunctionalProteotypeRequest(demo)).toEqual([]);
    expect(functionalProteotypeRequestStats(demo)).toEqual({ observations: 108, active: 100, observed: 96, leftCensored: 4, genes: 108, axes: 4 });
    expect(functionalProteotypeProfile.axes.map((axis) => ({ axis: axis.axis, signatures: axis.signature_protein_count, pathways: axis.pathway_count }))).toEqual([
      { axis: "GPM", signatures: 150, pathways: 243 },
      { axis: "MTC", signatures: 150, pathways: 107 },
      { axis: "NEU", signatures: 150, pathways: 272 },
      { axis: "PPR", signatures: 150, pathways: 204 },
    ]);
    expect(functionalProteotypeProfile.constants).toMatchObject({
      loading_policy: "source_mww_median_normalized_axis_loading_v1",
      censoring_loss: "one_sided_upper_bound_huber_hinge_v1",
      rank_null_policy: "source_rank_quartile_stratified_two_sided_bh_v1",
      top_driver_limit: 8,
      pathway_context_limit: 8,
    });
    expect(functionalProteotypeProfile.limits).toMatchObject({
      max_request_bytes: 2_097_152,
      max_result_bytes: 2_097_152,
      source_signature_proteins_total: 600,
      source_pathway_rows_total: 826,
    });
    expect(functionalProteotypeProfile).toMatchObject({
      source_article_doi: "10.1038/s43018-022-00510-x",
      source_license: "CC-BY-4.0",
      safety_class: "research_use_only",
      interpretation: "bulk_gbm_functional_proteotype_evidence_non_prescriptive",
    });

    expect(functionalProteotypeProfile.demo_id).toBe(functionalProteotypeDemo.sample_id);
    expect(functionalProteotypeProfile.profile_id).toBe(functionalProteotypeDemo.profile_id);
    expect(functionalProteotypeProfile.profile_id).toBe(functionalProteotypeAnalysis.profile_id);
    expect(functionalProteotypeDemo.sample_id).toBe(functionalProteotypeAnalysis.sample_id);
    expect(functionalProteotypeDemo.effect_reference_id).toBe(functionalProteotypeAnalysis.effect_reference_id);
    expect(functionalProteotypeProfile.demo_request_digest).toBe(functionalProteotypeAnalysis.request_digest);
    expect(functionalProteotypeProfile.profile_digest).toBe(functionalProteotypeAnalysis.profile_digest);
    expect(functionalProteotypeAnalysis.provenance.request_digest).toBe(functionalProteotypeAnalysis.request_digest);
    expect(functionalProteotypeAnalysis.provenance.profile_digest).toBe(functionalProteotypeProfile.profile_digest);
    for (const field of [
      "catalog_content_digest",
      "catalog_artifact_digest",
      "source_workbook_digest",
      "signature_catalog_digest",
      "pathway_catalog_digest",
      "engine_source_digest",
    ] as const) {
      expect(functionalProteotypeAnalysis.provenance[field]).toBe(functionalProteotypeProfile[field]);
    }
    expect(functionalProteotypeAnalysis.provenance.bootstrap_replicates_used).toBe(functionalProteotypeDemo.bootstrap_replicates);
    expect(functionalProteotypeAnalysis.provenance.permutation_replicates_used).toBe(functionalProteotypeDemo.permutation_replicates);
    expect(functionalProteotypeAnalysis.provenance.observation_source_digests).toEqual([
      ...new Set(functionalProteotypeDemo.observations.map((observation) => observation.provenance_digest)),
    ]);
    expect(functionalProteotypeAnalysis.output_semantics).toBe("bulk_gbm_functional_proteotype_evidence");

    expect(functionalProteotypeVerification).toMatchObject({
      verified: true,
      request_digest_match: true,
      profile_digest_match: true,
      result_digest_match: true,
      solver_trace_match: true,
      semantic_match: true,
      recomputed_request_digest: functionalProteotypeAnalysis.request_digest,
      provided_result_digest: functionalProteotypeAnalysis.result_digest,
      recomputed_result_digest: functionalProteotypeAnalysis.result_digest,
      provided_solver_trace_digest: functionalProteotypeAnalysis.solver.objective_trace_digest,
      recomputed_solver_trace_digest: functionalProteotypeAnalysis.solver.objective_trace_digest,
    });

    const axes = normalizeFunctionalProteotypeAxes(result);
    expect(axes).toHaveLength(4);
    expect(axes.every((axis) => axis.support === "supported")).toBe(true);
    expect(axes.reduce((sum, axis) => sum + (axis.estimate ?? 0), 0)).toBeCloseTo(0, 6);
    expect(functionalProteotypeAnalysis.solver.axis_coordinates.map((coordinate) => coordinate.axis)).toEqual(FUNCTIONAL_PROTEOTYPE_AXES);
    for (const axis of axes) {
      const declarations = functionalProteotypeDemo.observations.filter((observation) => observation.observation_id.startsWith(`demo.${axis.axis}.`));
      const observed = declarations.filter((observation) => observation.state === "observed").length;
      const leftCensored = declarations.filter((observation) => observation.state === "left_censored").length;
      expect(axis.counts).toMatchObject({ declared: declarations.length, observed, leftCensored, missing: 1, unsupported: 1, unreported: 123, observedBackground: 72 });
      expect(observed + leftCensored).toBeGreaterThanOrEqual(15);
      expect(axis.signatureObservedCount).toBe(observed);
      expect(axis.complementObservedCount).toBe(96 - observed);
      expect(functionalProteotypeAnalysis.solver.axis_coordinates.find((coordinate) => coordinate.axis === axis.axis)?.estimate).toBe(axis.estimate);
      const backendAxis = functionalProteotypeAnalysis.axis_evidence.find((item) => item.axis === axis.axis);
      expect(backendAxis?.top_drivers).toHaveLength(functionalProteotypeProfile.constants.top_driver_limit);
      expect(backendAxis?.ablations).toHaveLength(11);
      expect(backendAxis?.source_cohort_pathway_context).toHaveLength(functionalProteotypeProfile.constants.pathway_context_limit);
      expect(axis.drivers).toHaveLength(functionalProteotypeProfile.constants.top_driver_limit);
      expect(axis.drivers.every((driver) => driver.sourceLoading !== null)).toBe(true);
      expect(axis.ablations.filter((ablation) => ablation.support === "supported").every((ablation) => ablation.classification === "indeterminate")).toBe(true);
      expect(axis.ablations.map((ablation) => ablation.target)).toEqual(expect.arrayContaining([
        "source_rank_quartile:1",
        "evidence_state:observed",
        "evidence_state:left_censored",
        `top_driver:${axis.drivers[0].geneSymbol}`,
      ]));
      expect(axis.pathways.every((pathway) => pathway.sampleInferenceStatus === "not_evaluated")).toBe(true);
    }
    expect(functionalProteotypeAnalysis.emits_subtype_classification).toBe(false);
    expect(functionalProteotypeAnalysis.source_cohort_pathway_inference).toBe(false);
  });

  it("normalizes four ordered axes, intervals, independent q-values, drivers, ablations, and source-only pathways", () => {
    const result: JsonObject = {
      axis_evidence: [
        axisEvidence("PPR", -0.9),
        axisEvidence("GPM", 1.1),
        axisEvidence("NEU", -0.5),
        axisEvidence("MTC", 0.3),
      ],
    };
    const axes = normalizeFunctionalProteotypeAxes(result);
    expect(axes.map((item) => item.axis)).toEqual(FUNCTIONAL_PROTEOTYPE_AXES);
    expect(axes[0]).toMatchObject({ axis: "GPM", support: "supported", classification: "source_aligned", estimate: 1.1, bootstrapReplicates: 16, uStatistic: 318, rankBiserial: 0.55, pValue: 0.02, qValue: 0.04, permutationReplicates: 64, effectiveSampleSize: 24.7, stability: 0.91, discordance: 0.08 });
    expect(axes[0].lower).toBeCloseTo(0.9);
    expect(axes[0].upper).toBeCloseTo(1.3);
    expect(axes[0].counts).toMatchObject({ sourceSignatureProteins: 150, observed: 24, leftCensored: 1, missing: 1, unsupported: 1, unreported: 123, observedBackground: 72 });
    expect(axes[0].drivers[0]).toMatchObject({ geneSymbol: "CSTA", sourceRank: 4, sourceRankQuartile: 1, evidenceState: "observed", sourceLoading: 0.7, signedContribution: 3.61 });
    expect(axes[0].ablations[0]).toMatchObject({ kind: "source_rank_quartile", target: "source_rank_quartile:1", proteinsRemoved: 25, support: "abstained", delta: null });
    expect(axes[0].pathways[0]).toEqual({ axis: "GPM", sourceRank: 1, pathwayName: "GPM published pathway", sourceLogitNes: 1.7, sourcePValue: 0.001, sourceQValue: 0.003, sampleInferenceStatus: "not_evaluated", interpretation: "source_cohort_pathway_context_only" });
  });

  it("drops malformed axis identities and pathway rows instead of fabricating inference", () => {
    const validAxis = axisEvidence("GPM", 1.1);
    validAxis.source_cohort_pathway_context = [
      null,
      { axis: "GPM", pathway_name: "wrong status", sample_inference_status: "inferred" },
      { axis: "MTC", pathway_name: "wrong axis", sample_inference_status: "not_evaluated" },
    ];
    expect(normalizeFunctionalProteotypeAxes({ axis_evidence: [null, { axis: "OTHER", support: "supported", classification: "neutral" }, validAxis] })).toMatchObject([{ axis: "GPM", pathways: [] }]);
    expect(normalizeFunctionalProteotypeAxes({ axis_evidence: [{ axis: "GPM", support: "unknown", classification: "neutral" }] })).toEqual([]);
  });

  it("uses explicit sparse defaults without inventing drivers, ablations, or pathway inference", () => {
    const axes = normalizeFunctionalProteotypeAxes({
      axis_evidence: [
        {
          axis: "GPM",
          support: "supported",
          classification: "neutral",
          top_drivers: [null, {}, { gene_symbol: "EGFR" }],
          ablations: [
            null,
            {
              support_after_ablation: "unknown",
              classification_after_ablation: "neutral",
            },
            {
              support_after_ablation: "limited",
              classification_after_ablation: "indeterminate",
            },
          ],
          source_cohort_pathway_context: [{
            axis: "GPM",
            pathway_name: "source-only pathway",
            sample_inference_status: "not_evaluated",
          }],
        },
        {
          axis: "MTC",
          support: "limited",
          classification: "indeterminate",
          latent: {},
          rank: {},
          evidence_counts: {},
        },
      ],
    });

    expect(axes.map((axis) => axis.axis)).toEqual(["GPM", "MTC"]);
    for (const axis of axes) {
      expect(axis).toMatchObject({
        estimate: null,
        lower: null,
        upper: null,
        bootstrapReplicates: 0,
        signatureObservedCount: 0,
        complementObservedCount: 0,
        uStatistic: null,
        rankBiserial: null,
        tieCorrection: null,
        pValue: null,
        qValue: null,
        permutationReplicates: 0,
        counts: {
          sourceSignatureProteins: 150,
          declared: 0,
          observed: 0,
          leftCensored: 0,
          missing: 0,
          unsupported: 0,
          unreported: 0,
          observedBackground: 0,
          activeFraction: 0,
        },
        reasons: [],
      });
    }
    expect(axes[0].drivers).toEqual([expect.objectContaining({
      geneSymbol: "EGFR",
      sourceRank: 0,
      sourceRankQuartile: 0,
    })]);
    expect(axes[0].ablations).toEqual([expect.objectContaining({
      support: "limited",
      classification: "indeterminate",
      proteinsRemoved: 0,
    })]);
    expect(axes[0].pathways).toEqual([expect.objectContaining({
      pathwayName: "source-only pathway",
      sourceRank: 0,
      sampleInferenceStatus: "not_evaluated",
    })]);
    expect(axes[1]).toMatchObject({ drivers: [], ablations: [], pathways: [] });
  });
});
