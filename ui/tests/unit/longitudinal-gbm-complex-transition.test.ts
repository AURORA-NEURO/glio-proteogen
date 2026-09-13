import { describe, expect, it } from "vitest";

import {
  LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID,
  complexEstimatedCount,
  complexResultCount,
  complexSupportedCount,
  complexTransitionRequestStats,
  normalizeComplexEvaluation,
  normalizeComplexTransitions,
  validateComplexTransitionProfile,
  validateComplexTransitionProfileHeaders,
  validateComplexTransitionRequest,
  validateComplexTransitionResult,
  validateComplexTransitionResultHeaders,
  validateComplexTransitionResultProfileBinding,
  validateComplexTransitionResultRequestBinding,
  validateComplexTransitionVerification,
  validateComplexTransitionVerificationHeaders,
} from "../../src/lib/longitudinal-gbm-complex-transition";
import type { JsonObject } from "../../src/lib/research-state";
import {
  complexTransitionAnalysis,
  complexTransitionDemoRequest,
  complexTransitionProfile,
  complexTransitionVerification,
} from "../fixtures/longitudinal-gbm-complex-transition";
import { reactomeTransitionDemoRequest } from "../fixtures/longitudinal-gbm-reactome-transition";

function document(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

function firstTransition(value: JsonObject): JsonObject {
  const transitions = value.transitions;
  if (!Array.isArray(transitions) || typeof transitions[0] !== "object" || transitions[0] === null || Array.isArray(transitions[0])) {
    throw new Error("fixture transition is unavailable");
  }
  return transitions[0] as JsonObject;
}

function firstComplex(value: JsonObject): JsonObject {
  const complexes = firstTransition(value).complexes;
  if (!Array.isArray(complexes) || typeof complexes[0] !== "object" || complexes[0] === null || Array.isArray(complexes[0])) {
    throw new Error("fixture complex is unavailable");
  }
  return complexes[0] as JsonObject;
}

function request(): JsonObject {
  const value = document(reactomeTransitionDemoRequest);
  value.profile_id = LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID;
  return value;
}

const result: JsonObject = {
  transitions: [
    null,
    {
      transition_id: "complex.transition.0",
      transition_index: 0,
      from_time_point_id: "synthetic.reactome.baseline",
      to_time_point_id: "synthetic.reactome.recurrence",
      duration_days: 180,
      complexes: [
        {
          complex_index: 1,
          domain_id: "pi3k_akt",
          reactome_id: "R-HSA-2",
          complex_name: "Second complex",
          family_id: "family-b",
          support: "abstained",
          classification: "not_estimable",
          active_member_count: 1,
          observed_member_count: 0,
          left_censored_member_count: 1,
          coefficient_mass_coverage: 0.2,
          uncertainty: null,
          limitations: ["insufficient member support", 7],
        },
        null,
        { support: "unknown", reactome_id: "R-HSA-3" },
        {
          complex_index: 0,
          domain_id: "egfr_erbb_signaling",
          reactome_id: "R-HSA-1",
          complex_name: "EGFR participant set",
          family_id: "family-a",
          support: "supported",
          classification: "source_recurrence_aligned",
          score: 0.61,
          lower_bound: 0.34,
          upper_bound: 0.82,
          active_member_count: 5,
          observed_member_count: 4,
          left_censored_member_count: 1,
          coefficient_mass_coverage: 0.91,
          effective_sample_size: 4.3,
          coherence: 0.88,
          discordance: 0.12,
          stability: 0.94,
          source_held_member_relative_gain: 0.2,
          source_direction_accuracy: 0.73,
          source_minimum_outer_loading_cosine: 0.92,
          uncertainty: {
            state: "estimated",
            measurement_standard_error: 0.11,
            fitted_model_standard_error: 0.18,
            measurement_model_covariance: -0.002,
            combined_standard_error: 0.2,
            variance_closure_residual: 0.000001,
            bootstrap_replicates_used: 64,
          },
          top_contributions: [
            null,
            {},
            {
              gene_symbol: "EGFR",
              standardized_delta: 0.8,
              member_loading: 0.5,
              reliability_weight: 0.9,
              contribution: 0.36,
              direction: "source_recurrence_aligned",
            },
          ],
          ablations: {
            source_processing: {
              component_kind: "source_processing",
              component_id: "ordinary-log",
              support: "supported",
              score_without_component: 0.57,
              score_delta: 0.04,
              classification_without_component: "source_recurrence_aligned",
              removed_member_count: 0,
            },
            uniform_member_loading: {
              component_kind: "uniform_member_loading",
              component_id: "uniform",
              support: "limited",
              score_without_component: 0.3,
              score_delta: 0.31,
              classification_without_component: "source_recurrence_aligned",
              removed_member_count: 0,
              reason: "loading sensitive",
            },
            top_member: { component_kind: "top_member", support: "unknown" },
            nested_family: null,
          },
          limitations: [],
        },
      ],
    },
  ],
};

describe("longitudinal GBM complex-transition request helpers", () => {
  it("reuses the exact KNCC longitudinal input contract", () => {
    const value = request();
    expect(validateComplexTransitionRequest(value)).toEqual([]);
    expect(complexTransitionRequestStats(value)).toEqual({
      timePoints: 2,
      transitions: 1,
      observations: 12,
      active: 12,
      genes: 6,
    });
    expect(complexTransitionRequestStats({})).toEqual({
      timePoints: 0,
      transitions: 0,
      observations: 0,
      active: 0,
      genes: 0,
    });
  });

  it("rejects foreign profiles and incompatible assay attestations", () => {
    const value = request();
    value.profile_id = "latest";
    (value.assay_compatibility as JsonObject).log_base = 10;
    expect(validateComplexTransitionRequest(value)).toEqual(expect.arrayContaining([
      `profile_id must equal ${LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID}.`,
      "assay_compatibility.log_base must exactly equal 2.",
    ]));
    const optional = request();
    delete optional.profile_id;
    expect(validateComplexTransitionRequest(optional)).toEqual([]);
  });
});

describe("longitudinal GBM complex-transition result normalization", () => {
  it("retains participant identity, censor counts, uncertainty, drivers, and ablations", () => {
    const transitions = normalizeComplexTransitions(result);
    expect(transitions).toHaveLength(1);
    expect(transitions[0]).toMatchObject({
      id: "complex.transition.0",
      fromTimePointId: "synthetic.reactome.baseline",
      toTimePointId: "synthetic.reactome.recurrence",
      durationDays: 180,
    });
    expect(transitions[0].complexes.map((item) => item.complexIndex)).toEqual([0, 1]);
    expect(transitions[0].complexes[0]).toMatchObject({
      reactomeId: "R-HSA-1",
      complexName: "EGFR participant set",
      support: "supported",
      score: 0.61,
      observedMemberCount: 4,
      leftCensoredMemberCount: 1,
      uncertainty: {
        measurementStandardError: 0.11,
        fittedModelStandardError: 0.18,
        measurementModelCovariance: -0.002,
        combinedStandardError: 0.2,
        bootstrapReplicates: 64,
      },
    });
    expect(transitions[0].complexes[0].contributions).toEqual([
      expect.objectContaining({ geneSymbol: "EGFR", contribution: 0.36 }),
    ]);
    expect(transitions[0].complexes[0].ablations.map((item) => item.kind)).toEqual([
      "source_processing",
      "uniform_member_loading",
    ]);
    expect(transitions[0].complexes[1]).toMatchObject({
      support: "abstained",
      score: null,
      reasons: ["insufficient member support"],
      uncertainty: {
        state: "not_estimable",
        measurementStandardError: null,
        bootstrapReplicates: 0,
      },
    });
    expect(complexResultCount(transitions)).toBe(2);
    expect(complexEstimatedCount(transitions)).toBe(1);
    expect(complexSupportedCount(transitions)).toBe(1);
  });

  it("fails closed on malformed transition and complex records", () => {
    expect(normalizeComplexTransitions({ transitions: null })).toEqual([]);
    expect(normalizeComplexTransitions({ transitions: [null, {
      complexes: [null, { support: "unknown", reactome_id: "R-HSA-9" }],
    }] })).toEqual([expect.objectContaining({
      id: "unnamed-transition",
      complexes: [],
    })]);
  });

  it("applies fail-closed defaults to sparse but structurally valid records", () => {
    const transitions = normalizeComplexTransitions({
      transitions: [{
        complexes: [{
          support: "limited",
          reactome_id: "R-HSA-SPARSE",
          uncertainty: {},
          ablations: {
            source_processing: {
              component_kind: "source_processing",
              support: "limited",
            },
          },
        }],
      }],
    });
    expect(transitions[0].complexes[0]).toMatchObject({
      complexIndex: 0,
      activeMemberCount: 0,
      observedMemberCount: 0,
      leftCensoredMemberCount: 0,
      coefficientMassCoverage: 0,
      reasons: [],
      uncertainty: { bootstrapReplicates: 0 },
      ablations: [expect.objectContaining({ removedMemberCount: 0 })],
    });

    expect(normalizeComplexEvaluation({
      evaluation: { patient_cluster_median_gain_90_interval: ["bad", null] },
    })).toMatchObject({
      patientCount: 0,
      evaluationCount: 0,
      patientClusterInterval: [null, null],
      nonconvergedReferenceFitCount: 0,
      nonconvergedOuterFitCount: 0,
    });
  });

  it("normalizes the locked same-cohort evaluation without implying external validation", () => {
    const profile: JsonObject = {
      evaluation: {
        validation_scope: "internal_patient_grouped_held_member_reconstruction",
        patient_count: 104,
        evaluation_count: 14_988,
        zero_transition_mean_standardized_mae: 0.9407301748,
        training_center_mean_standardized_mae: 0.8769685109,
        factor_model_mean_standardized_mae: 0.6989814224,
        mean_relative_gain_over_training_center: 0.2029572172,
        patient_cluster_median_gain_90_interval: [0.0990936656, 0.1805654575],
        held_member_direction_accuracy: 0.7255137443,
        minimum_outer_loading_cosine: 0.81,
        nonconverged_reference_fit_count: 0,
        nonconverged_outer_fit_count: 0,
        external_validation_performed: false,
      },
    };
    expect(normalizeComplexEvaluation(profile)).toMatchObject({
      patientCount: 104,
      evaluationCount: 14_988,
      factorModelMeanMae: 0.6989814224,
      trainingCenterMeanMae: 0.8769685109,
      meanRelativeGain: 0.2029572172,
      patientClusterInterval: [0.0990936656, 0.1805654575],
      directionAccuracy: 0.7255137443,
      externalValidationPerformed: false,
    });
    expect(normalizeComplexEvaluation(null)).toBeNull();
    expect(normalizeComplexEvaluation({})).toBeNull();
  });
});

describe("longitudinal GBM complex-transition receipt admission", () => {
  it("admits only the contract-valid profile, request-bound result, digest headers, and replay closure", () => {
    const profile = document(complexTransitionProfile);
    const request = document(complexTransitionDemoRequest);
    const analysis = document(complexTransitionAnalysis);
    const verification = document(complexTransitionVerification);
    expect(validateComplexTransitionProfile(profile)).toEqual([]);
    expect(validateComplexTransitionProfileHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
    }), profile)).toEqual([]);
    expect(validateComplexTransitionResult(analysis)).toEqual([]);
    expect(validateComplexTransitionResultRequestBinding(analysis, request)).toEqual([]);
    expect(validateComplexTransitionResultProfileBinding(analysis, profile)).toEqual([]);
    expect(validateComplexTransitionResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(analysis.profile_digest),
      "X-GLIO-Request-Digest": String(analysis.request_digest),
      "X-GLIO-Result-Digest": String(analysis.result_digest),
    }), analysis)).toEqual([]);
    expect(validateComplexTransitionVerification(verification, analysis, profile)).toEqual([]);
    expect(validateComplexTransitionVerificationHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(verification.authoritative_profile_digest),
      "X-GLIO-Request-Digest": String(verification.recomputed_request_digest),
      "X-GLIO-Result-Digest": String(verification.recomputed_result_digest),
    }), verification)).toEqual([]);
  });

  it("fails closed on elevated claims, foreign bindings, forged headers, and inconsistent replay flags", () => {
    const profile = document(complexTransitionProfile);
    profile.claim_ceiling = "complex_activity";
    profile.extra_claim = true;
    expect(validateComplexTransitionProfile(profile)).toEqual(expect.arrayContaining([
      expect.stringContaining("unsupported fields"),
      expect.stringContaining("claim_ceiling"),
    ]));

    const analysis = document(complexTransitionAnalysis);
    analysis.infers_complex_activity = true;
    analysis.output_semantics = "complex_activity";
    expect(validateComplexTransitionResult(analysis)).toEqual(expect.arrayContaining([
      "result.output_semantics is invalid.",
      "result.infers_complex_activity must be false.",
    ]));
    expect(validateComplexTransitionResultRequestBinding(
      document(complexTransitionAnalysis),
      { ...document(complexTransitionDemoRequest), series_id: "foreign-series" },
    )).toContain("result.series_id must match the submitted request.");
    expect(validateComplexTransitionResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(complexTransitionAnalysis.profile_digest),
      "X-GLIO-Request-Digest": `sha256:${"0".repeat(64)}`,
      "X-GLIO-Result-Digest": String(complexTransitionAnalysis.result_digest),
    }), document(complexTransitionAnalysis))).toContain(
      "X-GLIO-Request-Digest response header must match the admitted payload.",
    );

    const verification = document(complexTransitionVerification);
    verification.verified = false;
    expect(validateComplexTransitionVerification(
      verification,
      document(complexTransitionAnalysis),
      document(complexTransitionProfile),
    )).toContain("verification.verified does not close all digest and semantic checks.");
  });

  it("rejects malformed profile fields and participant-panel topology", () => {
    const invalidProfiles: Array<(value: JsonObject) => void> = [
      (value) => { delete value.algorithm_id; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.model_id = "foreign"; },
      (value) => { value.profile_digest = "sha256:no"; },
      (value) => { value.numpy_version = "latest"; },
      (value) => { value.research_use_only = false; },
      (value) => { value.non_prescriptive = false; },
      (value) => { value.required_assay_compatibility = null; },
      (value) => { value.constants = null; },
      (value) => { value.limits = null; },
      (value) => { value.counts = null; },
      (value) => { value.digests = null; },
      (value) => { value.evaluation = null; },
      (value) => { (value.counts as JsonObject).strict_patient_pair_count = 103; },
      (value) => { (value.counts as JsonObject).complex_count = 27; },
      (value) => { (value.counts as JsonObject).nested_family_count = 10; },
      (value) => { (value.counts as JsonObject).fitted_bootstrap_replicate_count = 127; },
      (value) => { (value.evaluation as JsonObject).validation_scope = "external"; },
      (value) => { (value.evaluation as JsonObject).patient_count = 103; },
      (value) => { (value.evaluation as JsonObject).external_validation_performed = true; },
      (value) => { value.complexes = null; },
      (value) => { value.complexes = (value.complexes as unknown[]).slice(0, 27) as never; },
      (value) => { (value.complexes as unknown[])[0] = null; },
      (value) => { ((value.complexes as JsonObject[])[0]).complex_index = 1; },
      (value) => { ((value.complexes as JsonObject[])[0]).reactome_id = "latest"; },
      (value) => { ((value.complexes as JsonObject[])[1]).reactome_id = ((value.complexes as JsonObject[])[0]).reactome_id; },
      (value) => { ((value.complexes as JsonObject[])[0]).mapped_member_count = 2; },
      (value) => { ((value.complexes as JsonObject[])[0]).fitted_member_count = 33; },
      (value) => { value.source_licenses = null; },
      (value) => { value.source_licenses = [""]; },
      (value) => { value.source_licenses = ["a"]; },
      (value) => { value.source_licenses = ["a", "b", "c", "d", "e"]; },
      (value) => { value.limitations = null; },
      (value) => { value.limitations = []; },
      (value) => { value.limitations = Array.from({ length: 25 }, () => "limit"); },
    ];
    for (const mutate of invalidProfiles) {
      const value = document(complexTransitionProfile);
      mutate(value);
      expect(validateComplexTransitionProfile(value).length).toBeGreaterThan(0);
    }
    expect(validateComplexTransitionProfile({}).length).toBeGreaterThan(10);
    expect(validateComplexTransitionProfileHeaders(new Headers(), document(complexTransitionProfile))).not.toEqual([]);
  });

  it("rejects malformed result topology, evidence, uncertainty, ablations, contributions, and provenance", () => {
    const invalidResults: Array<(value: JsonObject) => void> = [
      (value) => { delete value.profile_id; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.model_id = "foreign"; },
      (value) => { value.request_digest = "bad"; },
      (value) => { value.result_digest = "bad"; },
      (value) => { value.profile_digest = "bad"; },
      (value) => { value.source_catalog_digest = "bad"; },
      (value) => { value.fitted_model_digest = "bad"; },
      (value) => { value.computational_seed = -1; },
      (value) => { value.computational_seed = 0.5; },
      (value) => { value.research_use_only = false; },
      (value) => { value.non_prescriptive = false; },
      (value) => { value.infers_complex_assembly = true; },
      (value) => { value.infers_complex_activity = true; },
      (value) => { value.infers_stoichiometry = true; },
      (value) => { value.infers_essential_subunits = true; },
      (value) => { value.infers_causality = true; },
      (value) => { value.assay_compatibility = null; },
      (value) => { value.normalization_reference = null; },
      (value) => { value.time_point_ids = null; },
      (value) => { value.time_point_ids = ["only-one"]; },
      (value) => { value.time_point_ids = Array.from({ length: 17 }, (_, index) => `T${index}`); },
      (value) => { value.time_point_ids = ["T0", "T0"]; },
      (value) => { value.transitions = null; },
      (value) => { value.transitions = []; },
      (value) => { (value.transitions as unknown[])[0] = null; },
      (value) => { firstTransition(value).transition_index = 1; },
      (value) => { firstTransition(value).from_time_point_id = "foreign"; },
      (value) => { firstTransition(value).to_time_point_id = "foreign"; },
      (value) => { firstTransition(value).duration_days = null; },
      (value) => { firstTransition(value).duration_days = 0; },
      (value) => { firstTransition(value).complexes = null; },
      (value) => { firstTransition(value).complexes = []; },
      (value) => { firstTransition(value).complexes = Array.from({ length: 65 }, () => null); },
      (value) => { (firstTransition(value).complexes as unknown[])[0] = null; },
      (value) => { firstComplex(value).complex_index = 1; },
      (value) => { firstComplex(value).reactome_id = "bad"; },
      (value) => { firstComplex(value).output_semantics = "activity"; },
      (value) => { firstComplex(value).support = "unknown"; },
      (value) => { firstComplex(value).support = null; },
      (value) => { firstComplex(value).active_member_count = 33; },
      (value) => { firstComplex(value).observed_member_count = -1; },
      (value) => { firstComplex(value).left_censored_member_count = 0.5; },
      (value) => { firstComplex(value).active_member_count = 4; firstComplex(value).observed_member_count = 3; firstComplex(value).left_censored_member_count = 0; },
      (value) => { firstComplex(value).coefficient_mass_coverage = null; },
      (value) => { firstComplex(value).coefficient_mass_coverage = -1; },
      (value) => { firstComplex(value).coefficient_mass_coverage = 2; },
      (value) => { firstComplex(value).uncertainty = null; },
      (value) => { (firstComplex(value).uncertainty as JsonObject).state = "unknown"; },
      (value) => { (firstComplex(value).uncertainty as JsonObject).measurement_standard_error = null; },
      (value) => { (firstComplex(value).uncertainty as JsonObject).bootstrap_replicates_used = 0; },
      (value) => { (firstComplex(value).uncertainty as JsonObject).reason = "not allowed"; },
      (value) => { firstComplex(value).ablations = null; },
      (value) => { (firstComplex(value).ablations as JsonObject).source_processing = 1; },
      (value) => { ((firstComplex(value).ablations as JsonObject).source_processing as JsonObject).component_kind = "unknown"; },
      (value) => { ((firstComplex(value).ablations as JsonObject).source_processing as JsonObject).support = "unknown"; },
      (value) => { ((firstComplex(value).ablations as JsonObject).source_processing as JsonObject).support = null; },
      (value) => { ((firstComplex(value).ablations as JsonObject).source_processing as JsonObject).removed_member_count = 33; },
      (value) => { ((firstComplex(value).ablations as JsonObject).source_processing as JsonObject).score_delta = null; },
      (value) => { firstComplex(value).top_contributions = null; },
      (value) => { firstComplex(value).top_contributions = Array.from({ length: 9 }, () => null); },
      (value) => { (firstComplex(value).top_contributions as unknown[])[0] = null; },
      (value) => { ((firstComplex(value).top_contributions as JsonObject[])[0]).value_semantics = "bound"; },
      (value) => { ((firstComplex(value).top_contributions as JsonObject[])[0]).from_provenance_digest = "bad"; },
      (value) => { ((firstComplex(value).top_contributions as JsonObject[])[0]).to_provenance_digest = "bad"; },
      (value) => { ((firstComplex(value).top_contributions as JsonObject[])[0]).reliability_weight = 0; },
      (value) => { ((firstComplex(value).top_contributions as JsonObject[])[0]).reliability_weight = 2; },
      (value) => { firstComplex(value).limitations = null; },
      (value) => { firstComplex(value).limitations = Array.from({ length: 13 }, () => "limit"); },
      (value) => { firstComplex(value).score = null; },
      (value) => { firstComplex(value).lower_bound = (firstComplex(value).score as number) + 1; },
      (value) => { firstComplex(value).upper_bound = (firstComplex(value).score as number) - 1; },
      (value) => { firstComplex(value).interval_level = 0.95; },
      (value) => { firstComplex(value).solver_converged = false; },
      (value) => { firstComplex(value).solver_objective_monotone = false; },
      (value) => { (firstComplex(value).ablations as JsonObject).source_processing = null; },
      (value) => { (firstComplex(value).ablations as JsonObject).uniform_member_loading = null; },
      (value) => { value.provenance = null; },
      (value) => { (value.provenance as JsonObject).source_study_id = "foreign"; },
      (value) => { (value.provenance as JsonObject).source_patient_pair_count = 103; },
      (value) => { (value.provenance as JsonObject).reactome_release = 96; },
      (value) => { (value.provenance as JsonObject).validation_scope = "external"; },
      (value) => { (value.provenance as JsonObject).patient_level_data_packaged = true; },
      (value) => { (value.provenance as JsonObject).external_validation_performed = true; },
      (value) => { (value.provenance as JsonObject).training_recipe_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).source_catalog_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { value.limitations = null; },
      (value) => { value.limitations = []; },
      (value) => { value.limitations = Array.from({ length: 25 }, () => "limit"); },
    ];
    for (const mutate of invalidResults) {
      const value = document(complexTransitionAnalysis);
      mutate(value);
      expect(validateComplexTransitionResult(value).length).toBeGreaterThan(0);
    }

    const abstained = document(complexTransitionAnalysis);
    const complex = firstComplex(abstained);
    complex.support = "abstained";
    complex.classification = "not_estimable";
    complex.score = null;
    complex.lower_bound = null;
    complex.upper_bound = null;
    complex.limitations = ["one-sided-only evidence cannot identify a bounded coordinate"];
    complex.uncertainty = {
      state: "not_estimable",
      measurement_standard_error: null,
      fitted_model_standard_error: null,
      measurement_model_covariance: null,
      combined_standard_error: null,
      variance_closure_residual: null,
      bootstrap_replicates_used: 0,
      reason: "bounded coordinate is not identified",
    };
    expect(validateComplexTransitionResult(abstained)).toEqual([]);
    (complex.uncertainty as JsonObject).measurement_standard_error = 1;
    (complex.uncertainty as JsonObject).bootstrap_replicates_used = 1;
    (complex.uncertainty as JsonObject).reason = "";
    complex.classification = "stable";
    expect(validateComplexTransitionResult(abstained).length).toBeGreaterThan(2);

    const abstainedAblation = document(complexTransitionAnalysis);
    const sourceAblation = (firstComplex(abstainedAblation).ablations as JsonObject).source_processing as JsonObject;
    sourceAblation.support = "abstained";
    sourceAblation.score_without_component = null;
    sourceAblation.score_delta = null;
    sourceAblation.classification_without_component = "not_estimable";
    sourceAblation.reason = "not estimable";
    expect(validateComplexTransitionResult(abstainedAblation)).toEqual([]);
    sourceAblation.classification_without_component = "stable";
    expect(validateComplexTransitionResult(abstainedAblation).length).toBeGreaterThan(0);
    expect(validateComplexTransitionResult({}).length).toBeGreaterThan(10);
  });

  it("rejects foreign request/profile identities and every inconsistent replay binding", () => {
    const result = document(complexTransitionAnalysis);
    const requestMutations: Array<(value: JsonObject) => void> = [
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.assay_compatibility = null; },
      (value) => { value.normalization_reference = null; },
      (value) => { value.time_points = null; },
      (value) => { ((value.time_points as JsonObject[])[0]).time_point_id = "foreign"; },
      (value) => { (value.time_points as unknown[])[0] = null; },
    ];
    for (const mutate of requestMutations) {
      const requestValue = document(complexTransitionDemoRequest);
      mutate(requestValue);
      expect(validateComplexTransitionResultRequestBinding(result, requestValue).length).toBeGreaterThan(0);
    }

    const profileMutations: Array<(value: JsonObject, resultValue: JsonObject) => void> = [
      (value) => { value.profile_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { (value.digests as JsonObject).source_catalog_content_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { (value.digests as JsonObject).fitted_content_digest = `sha256:${"0".repeat(64)}`; },
      (_value, resultValue) => { (firstTransition(resultValue).complexes as unknown[]).pop(); },
      (_value, resultValue) => { (firstTransition(resultValue).complexes as unknown[])[0] = null; },
      (value, resultValue) => { (value.complexes as unknown[])[0] = null; (firstTransition(resultValue).complexes as unknown[])[0] = null; },
      (_value, resultValue) => { firstComplex(resultValue).reactome_id = "R-HSA-1"; },
      (_value, resultValue) => { firstComplex(resultValue).domain_id = "foreign"; },
      (_value, resultValue) => { firstComplex(resultValue).family_id = "foreign"; },
      (_value, resultValue) => { firstComplex(resultValue).complex_name = "foreign"; },
    ];
    for (const mutate of profileMutations) {
      const profileValue = document(complexTransitionProfile);
      const resultValue = document(complexTransitionAnalysis);
      mutate(profileValue, resultValue);
      expect([
        ...validateComplexTransitionResult(resultValue),
        ...validateComplexTransitionResultProfileBinding(resultValue, profileValue),
      ].length).toBeGreaterThan(0);
    }
    expect(validateComplexTransitionResultProfileBinding({}, document(complexTransitionProfile)).length).toBeGreaterThan(0);
    const profileWithoutPanel = document(complexTransitionProfile);
    profileWithoutPanel.complexes = null;
    expect(validateComplexTransitionResultProfileBinding(result, profileWithoutPanel).length).toBeGreaterThan(0);
    const resultWithoutTransitionObject = document(complexTransitionAnalysis);
    resultWithoutTransitionObject.transitions = [null];
    expect(validateComplexTransitionResultProfileBinding(resultWithoutTransitionObject, document(complexTransitionProfile))).toEqual([]);
    const resultWithoutComplexArray = document(complexTransitionAnalysis);
    firstTransition(resultWithoutComplexArray).complexes = null;
    expect(validateComplexTransitionResultProfileBinding(resultWithoutComplexArray, document(complexTransitionProfile))).toEqual([]);

    const malformedHeaders = [
      new Headers(),
      new Headers({
        "X-GLIO-Profile-Digest": "bad",
        "X-GLIO-Request-Digest": "bad",
        "X-GLIO-Result-Digest": "bad",
      }),
    ];
    for (const headers of malformedHeaders) expect(validateComplexTransitionResultHeaders(headers, result).length).toBe(3);

    const invalidVerifications: Array<(value: JsonObject) => void> = [
      (value) => { delete value.message; },
      (value) => { value.verified = "yes"; },
      (value) => { value.transition_topology_match = "yes"; },
      (value) => { value.transition_topology_match = false; },
      (value) => { value.semantic_match = false; },
      (value) => { value.request_digest_match = false; },
      (value) => { value.recomputed_request_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { value.recomputed_result_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { value.authoritative_profile_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { value.recomputed_request_digest = "bad"; },
      (value) => { value.recomputed_result_digest = "bad"; },
      (value) => { value.authoritative_profile_digest = "bad"; },
      (value) => { value.message = ""; },
    ];
    for (const mutate of invalidVerifications) {
      const verification = document(complexTransitionVerification);
      mutate(verification);
      expect(validateComplexTransitionVerification(
        verification,
        result,
        document(complexTransitionProfile),
      ).length).toBeGreaterThan(0);
    }
    expect(validateComplexTransitionVerificationHeaders(new Headers(), document(complexTransitionVerification)).length).toBe(3);
  });
});
