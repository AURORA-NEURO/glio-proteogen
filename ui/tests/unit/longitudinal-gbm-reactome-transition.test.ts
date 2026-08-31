import { describe, expect, it } from "vitest";

import {
  LONGITUDINAL_GBM_REACTOME_PI3K_ID,
  LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  normalizeReactomeEvaluation,
  normalizeReactomeTransitions,
  reactomeEstimatedPathwayCount,
  reactomePathwayCount,
  reactomeSupportedPathwayCount,
  reactomeTransitionRequestStats,
  reactomeTransitionProfileDigest,
  reactomeTransitionRequestDigest,
  reactomeTransitionResultDigest,
  reactomeTransitionValueDigest,
  validateReactomeTransitionDemo,
  validateReactomeTransitionProfile,
  validateReactomeTransitionProfileHeaders,
  validateReactomeTransitionRequest,
  validateReactomeTransitionResult,
  validateReactomeTransitionResultHeaders,
  validateReactomeTransitionResultProfileBinding,
  validateReactomeTransitionResultRequestBinding,
  validateReactomeTransitionVerification,
  validateReactomeTransitionVerificationHeaders,
} from "../../src/lib/longitudinal-gbm-reactome-transition";
import type { JsonObject } from "../../src/lib/research-state";
import {
  reactomeTransitionAnalysisResult,
  reactomeTransitionDemoRequest,
  reactomeTransitionProfile,
  reactomeTransitionVerification,
} from "../fixtures/longitudinal-gbm-reactome-transition";

function document(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

const shaA = `sha256:${"a".repeat(64)}`;

function headers(values: Record<string, string>): Pick<Headers, "get"> {
  const normalized = new Map(
    Object.entries(values).map(([key, value]) => [key.toLowerCase(), value]),
  );
  return { get: (name: string) => normalized.get(name.toLowerCase()) ?? null };
}

function classification(lower: number, upper: number): string {
  if (lower > 0.25) return "conditional_source_recurrence_aligned";
  if (upper < -0.25) return "conditional_source_primary_aligned";
  if (lower >= -0.25 && upper <= 0.25) return "conditionally_stable";
  return "indeterminate";
}

function admittedDocuments(): {
  request: JsonObject;
  profile: JsonObject;
  result: JsonObject;
  verification: JsonObject;
} {
  const request = document(reactomeTransitionDemoRequest);
  const requestDigest = reactomeTransitionRequestDigest(request);
  const profile = document(reactomeTransitionProfile);
  profile.parent_feature_axis_model_id = "kncc-paired-protein-transition/1.0.0";
  profile.parent_dependency_semantics = "feature_axis_and_assay_binding_only_no_runtime_delegation";
  profile.required_assay_compatibility = document(request.assay_compatibility);
  profile.constants = {
    estimator: "global_adjusted_robust_conditional_coordinate_v1",
    missing_evidence_policy: "missing_and_unsupported_never_become_negative_v1",
    censoring_policy: "reported_limit_one_sided_bound_v1",
    output_semantics: "global_recurrence_concordance_and_conditional_pathway_concordance_only",
    huber_delta: 1.345,
    ridge_lambda: 1,
    global_ridge_multiplier: 0.25,
    damping: 0.7,
    solver_max_iterations: 200,
    solver_tolerance: 1e-9,
    maximum_condition_number: 25,
    interval_level: 0.9,
    aligned_threshold: 0.25,
    stable_threshold: 0.25,
    default_bootstrap_replicates: 64,
    supported_minimum_bootstrap_replicates: 64,
    minimum_bootstrap_replicates: 32,
    maximum_bootstrap_replicates: 256,
    offline_bootstrap_ensemble_size: 256,
    global_minimum_active_genes: 16,
    global_minimum_coefficient_mass: 0.25,
    global_minimum_effective_sample_size: 8,
    pathway_minimum_active_genes: 5,
    pathway_minimum_coefficient_mass: 0.5,
    pathway_minimum_effective_sample_size: 3,
    pathway_minimum_unique_genes: 3,
    pathway_minimum_unique_mass: 0.2,
    pathway_supported_minimum_stability: 0.8,
    request_reconstruction_gene_folds: 5,
    pathway_supported_required_evaluable_gene_folds: 5,
    pathway_supported_minimum_improved_gene_folds: 4,
    pathway_supported_minimum_reconstruction_gain: 0.01,
    pi3k_always_overlap_confounded: true,
    outer_fold_salt: "kncc-reactome-panel-outer-v1",
    gene_fold_salt: "kncc-reactome-gene-fold-v1",
    quantization_decimals: 8,
    solver_work_unit_formula: "(time_points - 1) * (186 + 3 * bootstrap_replicates)",
  };
  profile.limits = {
    min_time_points: 2,
    max_time_points: 16,
    max_observations_per_time_point: 4_096,
    max_total_observations: 12_000,
    fixed_pathway_count: 10,
    max_top_contributions: 10,
    max_overlap_ablations: 9,
    request_max_bytes: 2_097_152,
    result_max_bytes: 4_194_304,
    replay_max_bytes: 8_388_608,
    max_solver_work_units: 4_608,
  };
  profile.counts = {
    ...(profile.counts as JsonObject),
    excluded_candidate_count: 12,
    reactome_release: 97,
    outer_fold_count: 8,
    gene_fold_count: 5,
  };
  const digestFields = [
    "source_catalog_artifact_digest",
    "source_catalog_content_digest",
    "source_binding_digest",
    "selection_candidate_digest",
    "pathway_order_digest",
    "pathway_membership_digest",
    "gene_order_digest",
    "patient_order_rule_digest",
    "fitted_artifact_digest",
    "fitted_content_digest",
    "union_feature_digest",
    "reference_tensor_digest",
    "centering_scaling_digest",
    "reference_design_digest",
    "global_loading_digest",
    "conditional_loading_digest",
    "bootstrap_ensemble_digest",
    "training_recipe_digest",
    "fold_policy_digest",
    "source_processing_ablation_digest",
    "evaluation_digest",
    "input_contract_schema_digest",
    "engine_semantic_digest",
  ];
  profile.digests = Object.fromEntries(digestFields.map((field) => [field, shaA]));
  profile.evaluation = {
    ...(profile.evaluation as JsonObject),
    outer_design_condition_minimum: 4.9,
    outer_design_condition_maximum: 5.5,
    full_patient_nonconverged_count: 0,
    global_held_gene_nonconverged_count: 0,
    joint_held_gene_nonconverged_count: 0,
    leave_pathway_out_nonconverged_count: 0,
    leave_pathway_interval_count: 10,
  };
  profile.demo_id = request.series_id;
  profile.demo_request_digest = requestDigest;
  profile.demo_semantic_oracle_digest = shaA;
  profile.source_attribution = "Kim et al., Cancer Cell 2024, PDC000514; Reactome V97";
  profile.source_licenses = ["CC-BY-4.0", "Reactome CC0"];
  profile.source_transformation_notice = "De-identified fitted artifact; no patient matrix is bundled.";
  profile.interpretation = "global_adjusted_reactome_membership_coordinate_not_pathway_activation_or_flux";
  profile.maximum_evidence_grade = "limited_same_cohort_without_external_validation";
  profile.profile_digest = reactomeTransitionProfileDigest(profile);

  const result = document(reactomeTransitionAnalysisResult);
  result.profile_digest = profile.profile_digest;
  result.request_digest = requestDigest;
  const transitions = result.transitions as JsonObject[];
  const pathways = transitions[0].pathways as JsonObject[];
  for (const pathway of pathways) {
    pathway.classification = classification(
      pathway.lower_bound as number,
      pathway.upper_bound as number,
    );
  }
  const profileDigests = profile.digests as JsonObject;
  result.provenance = {
    ...(result.provenance as JsonObject),
    ...profileDigests,
    request_digest: requestDigest,
    profile_digest: profile.profile_digest,
    computational_digest: shaA,
    numerical_seed_digest: shaA,
    demo_semantic_oracle_digest: profile.demo_semantic_oracle_digest,
    assay_compatibility_digest: reactomeTransitionValueDigest(result.assay_compatibility),
    normalization_reference_digest: (result.normalization_reference as JsonObject).binding_digest,
    caller_evidence_set_digest: shaA,
    bootstrap_seed: 17,
  };
  result.limitations = [
    ...(result.limitations as string[]),
    "No external validation is claimed.",
    "No recurrence prediction is produced.",
    "No treatment recommendation is produced.",
  ];
  result.result_digest = reactomeTransitionResultDigest(result);

  const verification = document(reactomeTransitionVerification);
  verification.recomputed_request_digest = requestDigest;
  verification.recomputed_result_digest = result.result_digest;
  verification.message = "Replay exactly matches the deterministic conditional-concordance receipt.";
  return { request, profile, result, verification };
}

describe("longitudinal GBM Reactome request helpers", () => {
  it("reuses the strict KNCC longitudinal contract and reports transition statistics", () => {
    const request = document(reactomeTransitionDemoRequest);
    expect(validateReactomeTransitionRequest(request)).toEqual([]);
    expect(reactomeTransitionRequestStats(request)).toEqual({
      timePoints: 2,
      transitions: 1,
      observations: 12,
      active: 12,
      genes: 6,
    });
    expect(reactomeTransitionRequestStats({})).toEqual({
      timePoints: 0,
      transitions: 0,
      observations: 0,
      active: 0,
      genes: 0,
    });
  });

  it("rejects a foreign profile without mutating the parent-compatible validation result", () => {
    const request = document(reactomeTransitionDemoRequest);
    request.profile_id = "latest";
    const attestation = request.assay_compatibility as JsonObject;
    attestation.log_base = 10;
    expect(validateReactomeTransitionRequest(request)).toEqual(expect.arrayContaining([
      `profile_id must equal ${LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID}.`,
      "assay_compatibility.log_base must exactly equal 2.",
    ]));

    const optionalProfile = document(reactomeTransitionDemoRequest);
    delete optionalProfile.profile_id;
    expect(validateReactomeTransitionRequest(optionalProfile)).toEqual([]);
  });

  it("bounds the combined transition and bootstrap solver work", () => {
    const request = document(reactomeTransitionDemoRequest);
    const template = document((request.time_points as JsonObject[])[0]);
    request.time_points = Array.from({ length: 7 }, (_, pointIndex) => ({
      ...document(template),
      time_point_id: `audit.time.${pointIndex}`,
      time_offset_days: pointIndex * 30,
      observations: (template.observations as JsonObject[]).map((observation, observationIndex) => ({
        ...document(observation),
        observation_id: `audit.observation.${pointIndex}.${observationIndex}`,
      })),
    }));
    request.bootstrap_replicates = 194;
    expect(validateReactomeTransitionRequest(request)).toEqual([]);

    request.bootstrap_replicates = 195;
    expect(validateReactomeTransitionRequest(request)).toContain(
      "request exceeds the 4608 solver-work-unit limit: "
        + "(time_points - 1) * (186 + 3 * bootstrap_replicates).",
    );
  });
});

describe("longitudinal GBM Reactome wire admission", () => {
  it("admits one fully bound profile, demo, analysis, and replay receipt", () => {
    const { request, profile, result, verification } = admittedDocuments();
    expect(reactomeTransitionValueDigest({})).toBe(
      "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    );

    expect(validateReactomeTransitionProfile(profile)).toEqual([]);
    expect(validateReactomeTransitionProfileHeaders(headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
    }), profile)).toEqual([]);
    expect(validateReactomeTransitionDemo(request, headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(profile.demo_request_digest),
    }), profile)).toEqual([]);

    expect(validateReactomeTransitionResult(result)).toEqual([]);
    expect(validateReactomeTransitionResultRequestBinding(result, request)).toEqual([]);
    expect(validateReactomeTransitionResultProfileBinding(result, profile)).toEqual([]);
    expect(validateReactomeTransitionResultHeaders(headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    }), result, request)).toEqual([]);

    expect(validateReactomeTransitionVerification(verification, result, profile)).toEqual([]);
    expect(validateReactomeTransitionVerificationHeaders(headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(verification.recomputed_request_digest),
      "X-GLIO-Result-Digest": String(verification.recomputed_result_digest),
    }), verification, profile)).toEqual([]);
  });

  it("rejects forged documents and independently forged response headers", () => {
    const { request, profile, result } = admittedDocuments();
    const forgedProfile = document(profile);
    (forgedProfile.constants as JsonObject).aligned_threshold = 0.1;
    expect(validateReactomeTransitionProfile(forgedProfile)).toEqual(expect.arrayContaining([
      "profile.profile_digest does not match the canonical profile payload.",
      "profile.constants.aligned_threshold differs from the locked algorithm profile.",
    ]));

    expect(validateReactomeTransitionDemo(request, headers({
      "X-GLIO-Profile-Digest": shaA,
      "X-GLIO-Request-Digest": shaA,
    }), profile)).toEqual(expect.arrayContaining([
      "X-GLIO-Profile-Digest response header must match the admitted payload.",
      "X-GLIO-Request-Digest response header must match the admitted payload.",
    ]));

    const forgedResult = document(result);
    forgedResult.output_semantics = "pathway_activation";
    expect(validateReactomeTransitionResult(forgedResult)).toEqual(expect.arrayContaining([
      "result.result_digest does not match the canonical result payload.",
      "result semantics exceed or differ from the admitted research boundary.",
    ]));
    expect(validateReactomeTransitionResultHeaders(headers({
      "X-GLIO-Profile-Digest": shaA,
      "X-GLIO-Request-Digest": shaA,
      "X-GLIO-Result-Digest": shaA,
    }), result, request)).toEqual(expect.arrayContaining([
      "X-GLIO-Profile-Digest response header must match the admitted payload.",
      "X-GLIO-Request-Digest response header must match the admitted payload.",
      "X-GLIO-Result-Digest response header must match the admitted payload.",
    ]));
  });

  it("rejects a result bound to a different submitted series", () => {
    const { request, result } = admittedDocuments();
    const foreignRequest = document(request);
    foreignRequest.series_id = "synthetic.reactome.foreign-series";
    expect(validateReactomeTransitionResultRequestBinding(result, foreignRequest)).toEqual(
      expect.arrayContaining([
        "result.request_digest must match the canonical submitted request.",
        "result.series_id must match the submitted request.",
      ]),
    );
    expect(validateReactomeTransitionResultHeaders(headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    }), result, foreignRequest)).toContain(
      "X-GLIO-Request-Digest response header must match the admitted payload.",
    );
  });

  it("rejects false, malformed, and header-forged replay verification", () => {
    const { profile, result, verification } = admittedDocuments();
    const falseVerification = document(verification);
    for (const field of [
      "request_digest_match",
      "profile_digest_match",
      "result_digest_match",
      "transition_topology_match",
      "global_recurrence_semantic_match",
      "pathway_semantic_match",
      "uncertainty_semantic_match",
      "ablation_semantic_match",
      "provenance_match",
      "document_semantic_match",
      "semantic_match",
      "verified",
    ]) falseVerification[field] = false;
    expect(validateReactomeTransitionVerification(falseVerification, result, profile)).toContain(
      "verification must affirm every digest and semantic check.",
    );

    const malformedVerification = document(verification);
    malformedVerification.pathway_semantic_match = false;
    malformedVerification.message = "";
    expect(validateReactomeTransitionVerification(
      malformedVerification,
      result,
      profile,
    )).toEqual(expect.arrayContaining([
      "verification.semantic_match does not close its semantic checks.",
      "verification.verified does not close its digest and semantic checks.",
      "verification must affirm every digest and semantic check.",
      "verification.message must be non-empty.",
    ]));

    expect(validateReactomeTransitionVerificationHeaders(headers({
      "X-GLIO-Profile-Digest": shaA,
      "X-GLIO-Request-Digest": String(verification.recomputed_request_digest),
      "X-GLIO-Result-Digest": String(verification.recomputed_result_digest),
    }), verification, profile)).toContain(
      "X-GLIO-Profile-Digest response header must match the admitted payload.",
    );
  });
});

describe("longitudinal GBM Reactome result normalization", () => {
  it("normalizes global and all ten conditional coordinates without collapsing the three coordinate stages", () => {
    const transitions = normalizeReactomeTransitions(document(reactomeTransitionAnalysisResult));
    expect(transitions).toHaveLength(1);
    expect(transitions[0]).toMatchObject({
      id: "reactome.transition.0",
      fromTimePointId: "synthetic.reactome.baseline",
      toTimePointId: "synthetic.reactome.recurrence",
      durationDays: 180,
      global: {
        support: "supported",
        classification: "stable",
        score: -0.07,
        activeGenes: 1656,
        coefficientMassCoverage: 0.984,
      },
    });
    expect(transitions[0].pathways).toHaveLength(10);
    expect(transitions[0].pathways[0]).toMatchObject({
      panelIndex: 0,
      reactomeId: "R-HSA-177929",
      pathwayName: "Signaling by EGFR",
      unadjustedCoordinate: 0.51,
      globalAdjustment: -0.11,
      score: 0.62,
      reconstructionImprovedFoldCount: 4,
      reconstructionEvaluableFoldCount: 5,
      reconstructionMedianRelativeGain: 0.018,
    });
    expect(reactomePathwayCount(transitions)).toBe(10);
    expect(reactomeEstimatedPathwayCount(transitions)).toBe(10);
    expect(reactomeSupportedPathwayCount(transitions)).toBe(1);
  });

  it("keeps PI3K overlap confounding, uncertainty components, contributions, and every ablation family explicit", () => {
    const transition = normalizeReactomeTransitions(document(reactomeTransitionAnalysisResult))[0];
    const pi3k = transition.pathways.find((pathway) => pathway.reactomeId === LONGITUDINAL_GBM_REACTOME_PI3K_ID);
    expect(pi3k).toMatchObject({
      support: "limited",
      score: 1.11,
      overlapConfounded: true,
      uniqueActiveGeneCount: 0,
      uniqueCoefficientMass: 0,
      uncertainty: {
        state: "estimated",
        measurementStandardError: 0.12,
        fittedModelStandardError: 0.2,
        measurementModelCovariance: -0.0004,
        combinedStandardError: 0.23,
        bootstrapReplicates: 64,
      },
    });
    expect(pi3k?.reasons).toContain("PI3K/AKT is overlap-confounded in the fixed panel");
    expect(pi3k?.contributions[0]).toMatchObject({
      geneSymbol: "PIK3CA",
      unadjustedContribution: 0.21,
      globalAdjustmentContribution: 0.03,
      conditionalContribution: 0.18,
    });
    expect(pi3k?.ablations.map((item) => item.kind)).toEqual([
      "global_axis",
      "degree_normalization",
      "unique_members",
      "leave_pathway_out",
      "source_processing",
    ]);
    expect(pi3k?.ablations.find((item) => item.kind === "unique_members")).toMatchObject({
      support: "abstained",
      scoreWithout: null,
      classificationWithout: "not_estimable",
    });

    const pdgf = transition.pathways[1];
    expect(pdgf.reconstructionImprovedFoldCount).toBe(2);
    expect(pdgf.reconstructionEvaluableFoldCount).toBe(3);
    expect(pdgf.ablations.some((item) => item.kind === "overlapping_pathway")).toBe(true);
    expect(transition.pathways[0].ablations.some((item) => item.kind === "top_contribution")).toBe(true);
  });

  it("normalizes the locked same-cohort evidence ceiling instead of implying external validation", () => {
    const evaluation = normalizeReactomeEvaluation(document(reactomeTransitionProfile));
    expect(evaluation).toMatchObject({
      patientCount: 104,
      evaluationCount: 520,
      zeroPredictionMedianMae: 0.7108931329,
      globalOnlyMedianMae: 0.5622984198,
      jointMedianMae: 0.5554163035,
      medianRelativeMaeImprovement: 0.0120459348,
      evaluationImprovedFraction: 0.6653846154,
      conditionNumber: 5.2021989549,
      minimumOuterLoadingCosine: 0.9851914172,
      allPrimaryFitsConverged: true,
      allLeavePathwayIntervalsCrossZero: true,
    });
    expect(evaluation?.validationScope).toContain("not external validation");
    expect(evaluation?.patientClusterInterval).toEqual([0.0085182357, 0.0178616382]);
    expect(normalizeReactomeEvaluation(null)).toBeNull();
    expect(normalizeReactomeEvaluation({})).toBeNull();
  });

  it("fails closed on malformed result records while preserving inspectable abstention reasons", () => {
    const transitions = normalizeReactomeTransitions({ transitions: [
      null,
      {
        transition_id: "sparse",
        global_recurrence: { support: "unknown", abstention_reasons: ["global reason", 3] },
        pathways: [
          null,
          { support: "unknown", reactome_id: "R-HSA-1" },
          {
            support: "abstained",
            reactome_id: "R-HSA-177929",
            abstention_reasons: ["insufficient coverage", 7],
            top_contributions: [null, {}, { gene_symbol: "EGFR" }],
            ablations: {
              global_axis: { component_kind: "unknown", support: "limited" },
              source_processing: [null, { component_kind: "source_processing", support: "unknown" }],
              top_contributions: [{
                component_kind: "top_contribution",
                component_id: "EGFR",
                support: "abstained",
                classification_without_component: "not_estimable",
              }],
            },
          },
        ],
      },
    ] });
    expect(transitions).toHaveLength(1);
    expect(transitions[0].global).toMatchObject({ support: "abstained", score: null, reasons: ["global reason"] });
    expect(transitions[0].pathways).toHaveLength(1);
    expect(transitions[0].pathways[0]).toMatchObject({
      support: "abstained",
      score: null,
      reconstructionEvaluableFoldCount: 0,
      reasons: ["insufficient coverage"],
      uncertainty: { state: "not_estimable", measurementStandardError: null, bootstrapReplicates: 0 },
    });
    expect(transitions[0].pathways[0].contributions).toEqual([
      expect.objectContaining({ geneSymbol: "EGFR", conditionalContribution: null }),
    ]);
    expect(transitions[0].pathways[0].ablations).toEqual([
      expect.objectContaining({ kind: "top_contribution", support: "abstained" }),
    ]);
    expect(normalizeReactomeTransitions({ transitions: null })).toEqual([]);
  });

  it("applies fail-closed defaults when optional global, pathway, and evaluation fields are absent", () => {
    const transitions = normalizeReactomeTransitions({
      transitions: [{
        pathways: [{
          support: "limited",
          reactome_id: "R-HSA-SPARSE",
          uncertainty: {},
        }],
      }],
    });
    expect(transitions[0].global).toEqual({
      support: "abstained",
      classification: "not_estimable",
      score: null,
      lower: null,
      upper: null,
      activeGenes: 0,
      coefficientMassCoverage: 0,
      effectiveSampleSize: null,
      bootstrapReplicates: 0,
      reasons: [],
    });
    expect(transitions[0].pathways[0]).toMatchObject({
      ablations: [],
      reasons: [],
      uncertainty: { bootstrapReplicates: 0 },
    });
    expect(normalizeReactomeEvaluation({
      evaluation: {
        patient_cluster_median_improvement_90_interval: ["bad", null],
      },
    })).toMatchObject({
      patientCount: 0,
      evaluationCount: 0,
      patientClusterInterval: [null, null],
      patientClusterBootstrapReplicates: 0,
    });
  });
});
