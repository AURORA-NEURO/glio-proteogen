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

  it("fails closed across every nested profile boundary", () => {
    const profileCases: Array<[
      label: string,
      mutate: (profile: JsonObject) => void,
      expected: string,
    ]> = [
      ["algorithm identity", (profile) => { profile.algorithm_id = "foreign"; },
        "profile algorithm/model identity is invalid."],
      ["parent identity", (profile) => { profile.parent_feature_axis_model_id = "foreign"; },
        "profile parent feature-axis dependency is invalid."],
      ["digest syntax", (profile) => { profile.profile_digest = "SHA256:BAD"; },
        "profile.profile_digest must be a lowercase sha256 digest."],
      ["numpy runtime", (profile) => { profile.numpy_version = "latest"; },
        "profile.numpy_version must equal the locked 2.5.2 runtime."],
      ["claim ceiling", (profile) => { profile.claim_ceiling = "clinical"; },
        "profile exceeds or differs from the admitted research claim ceiling."],
      ["assay object", (profile) => { profile.required_assay_compatibility = null; },
        "profile.required_assay_compatibility must be an object."],
      ["constants object", (profile) => { profile.constants = null; },
        "profile.constants must be an object."],
      ["locked constant", (profile) => {
        (profile.constants as JsonObject).huber_delta = 2;
      }, "profile.constants.huber_delta differs from the locked algorithm profile."],
      ["limits object", (profile) => { profile.limits = null; },
        "profile.limits must be an object."],
      ["locked limit", (profile) => {
        (profile.limits as JsonObject).fixed_pathway_count = 9;
      }, "profile.limits.fixed_pathway_count differs from the locked algorithm profile."],
      ["counts object", (profile) => { profile.counts = null; },
        "profile.counts must be an object."],
      ["locked count", (profile) => {
        (profile.counts as JsonObject).source_patient_count = 103;
      }, "profile.counts.source_patient_count is invalid."],
      ["global feature bound", (profile) => {
        (profile.counts as JsonObject).fitted_global_feature_count = 15;
      }, "profile.counts.fitted_global_feature_count is outside the source bound."],
      ["pathway feature bound", (profile) => {
        (profile.counts as JsonObject).fitted_pathway_feature_count = 4;
      }, "profile.counts.fitted_pathway_feature_count is outside the source bound."],
      ["digests object", (profile) => { profile.digests = null; },
        "profile.digests must be an object."],
      ["nested digest", (profile) => {
        (profile.digests as JsonObject).fold_policy_digest = "bad";
      }, "profile.digests.fold_policy_digest must be a sha256 digest."],
      ["evaluation object", (profile) => { profile.evaluation = null; },
        "profile.evaluation must be an object."],
      ["evaluation ceiling", (profile) => {
        (profile.evaluation as JsonObject).validation_scope = "external validation";
      }, "profile.evaluation exceeds or differs from the locked same-cohort evidence."],
      ["pathway panel", (profile) => { profile.pathways = []; },
        "profile.pathways must contain the exact ten-pathway panel."],
      ["pathway record", (profile) => {
        (profile.pathways as unknown[])[0] = null;
      }, "profile.pathways[0] must be an object."],
      ["pathway identity", (profile) => {
        ((profile.pathways as JsonObject[])[0]).reactome_id = "R-HSA-0";
      }, "profile.pathways[0] does not preserve the fixed Reactome V97 identity."],
      ["source member bound", (profile) => {
        ((profile.pathways as JsonObject[])[0]).source_member_count = 4;
      }, "profile.pathways[0].source_member_count is outside the contract bound."],
      ["unique member bound", (profile) => {
        ((profile.pathways as JsonObject[])[0]).unique_fitted_feature_count = -1;
      }, "profile.pathways[0].unique_fitted_feature_count is outside the contract bound."],
      ["PI3K confounding", (profile) => {
        ((profile.pathways as JsonObject[])[2]).overlap_confounded = false;
      }, "profile.pathways[2] must expose PI3K/AKT overlap confounding."],
      ["demo digest", (profile) => { profile.demo_request_digest = "bad"; },
        "profile.demo_request_digest must be a sha256 digest."],
      ["demo id", (profile) => { profile.demo_id = " "; },
        "profile.demo_id must be non-empty."],
      ["source attribution", (profile) => { profile.source_attribution = ""; },
        "profile.source_attribution must be non-empty."],
      ["transformation notice", (profile) => { profile.source_transformation_notice = null; },
        "profile.source_transformation_notice must be non-empty."],
      ["source licenses", (profile) => { profile.source_licenses = ["CC-BY-4.0"]; },
        "profile.source_licenses must contain 2 through 4 non-empty entries."],
    ];

    const { profile } = admittedDocuments();
    for (const [label, mutate, expected] of profileCases) {
      const candidate = document(profile);
      mutate(candidate);
      expect(validateReactomeTransitionProfile(candidate), label).toContain(expected);
    }

    expect(validateReactomeTransitionProfileHeaders(headers({}), profile)).toContain(
      "X-GLIO-Profile-Digest response header must be a lowercase sha256 digest.",
    );
  });

  it("fails closed across nested result estimates, uncertainty, evidence, and ablations", () => {
    type ResultMutation = (result: JsonObject) => void;
    const transition = (result: JsonObject): JsonObject =>
      (result.transitions as JsonObject[])[0];
    const global = (result: JsonObject): JsonObject =>
      transition(result).global_recurrence as JsonObject;
    const pathway = (result: JsonObject, index = 0): JsonObject =>
      (transition(result).pathways as JsonObject[])[index];
    const uncertainty = (result: JsonObject): JsonObject =>
      pathway(result).uncertainty as JsonObject;
    const contribution = (result: JsonObject): JsonObject =>
      (pathway(result).top_contributions as JsonObject[])[0];
    const ablation = (result: JsonObject): JsonObject =>
      (pathway(result).ablations as JsonObject).global_axis as JsonObject;

    const resultCases: Array<[
      label: string,
      mutate: ResultMutation,
      expected: string,
    ]> = [
      ["algorithm identity", (result) => { result.algorithm_version = "2.0.0"; },
        "result algorithm/profile identity is invalid."],
      ["digest syntax", (result) => { result.request_digest = "bad"; },
        "result.request_digest must be a sha256 digest."],
      ["claim ceiling", (result) => { result.research_use_only = false; },
        "result semantics exceed or differ from the admitted research boundary."],
      ["assay shape", (result) => { result.assay_compatibility = null; },
        "result.assay_compatibility must be an object."],
      ["normalization shape", (result) => { result.normalization_reference = []; },
        "result.normalization_reference must be an object."],
      ["time-point shape", (result) => { result.time_point_ids = ["same", "same"]; },
        "result.time_point_ids must contain 2 through 16 unique identifiers."],
      ["transition cardinality", (result) => { result.transitions = []; },
        "result.transitions must contain one entry per consecutive time-point pair."],
      ["transition object", (result) => {
        (result.transitions as unknown[])[0] = null;
      }, "result.transitions[0] must be an object."],
      ["transition topology", (result) => { transition(result).duration_days = 0; },
        "result.transitions[0] must bind consecutive ordered time points."],
      ["global object", (result) => { transition(result).global_recurrence = null; },
        "result.transitions[0].global_recurrence must be an object."],
      ["global semantics", (result) => { global(result).output_semantics = "activation"; },
        "result.transitions[0].global_recurrence.output_semantics is invalid."],
      ["global support", (result) => { global(result).support = "unknown"; },
        "result.transitions[0].global_recurrence.support is invalid."],
      ["global classification", (result) => { global(result).classification = "unknown"; },
        "result.transitions[0].global_recurrence.classification is invalid."],
      ["global interval level", (result) => { global(result).interval_level = 0.8; },
        "result.transitions[0].global_recurrence.interval_level must equal 0.9."],
      ["global active genes", (result) => { global(result).shared_active_gene_count = -1; },
        "result.transitions[0].global_recurrence.shared_active_gene_count must be 0 through 4096."],
      ["global mass", (result) => { global(result).coefficient_mass_coverage = 2; },
        "result.transitions[0].global_recurrence.coefficient_mass_coverage must be in [0,1]."],
      ["global effective sample", (result) => { global(result).effective_sample_size = -1; },
        "result.transitions[0].global_recurrence.effective_sample_size must be nonnegative."],
      ["global reasons", (result) => { global(result).abstention_reasons = [3]; },
        "result.transitions[0].global_recurrence.abstention_reasons must contain at most 8 strings."],
      ["global abstention", (result) => { global(result).support = "abstained"; },
        "result.transitions[0].global_recurrence abstention fields are inconsistent."],
      ["global estimate", (result) => { global(result).lower_bound = 1; },
        "result.transitions[0].global_recurrence requires a finite ordered estimate and bootstraps."],
      ["global interval classification", (result) => {
        global(result).classification = "source_recurrence_aligned";
      }, "result.transitions[0].global_recurrence.classification must be supported by its 90% interval."],
      ["global indeterminate interval", (result) => {
        global(result).score = 0;
        global(result).lower_bound = -0.3;
        global(result).upper_bound = 0.3;
        global(result).classification = "stable";
      }, "result.transitions[0].global_recurrence.classification must be supported by its 90% interval."],
      ["global gates", (result) => { global(result).shared_active_gene_count = 15; },
        "result.transitions[0].global_recurrence estimated output does not meet global support gates."],
      ["global supported reasons", (result) => {
        global(result).abstention_reasons = ["unexpected"];
      }, "result.transitions[0].global_recurrence supported output cannot carry limitation reasons."],
      ["global limited reason", (result) => {
        global(result).support = "limited";
      }, "result.transitions[0].global_recurrence LIMITED output requires a limitation reason."],
      ["pathway panel", (result) => { transition(result).pathways = []; },
        "result.transitions[0].pathways must contain the exact ten-pathway panel."],
      ["pathway object", (result) => {
        (transition(result).pathways as unknown[])[0] = null;
      }, "result.transitions[0].pathways[0] must be an object."],
      ["pathway identity", (result) => { pathway(result).panel_index = 8; },
        "result.transitions[0].pathways[0] does not preserve the fixed Reactome V97 pathway order."],
      ["pathway semantics", (result) => { pathway(result).output_semantics = "activation"; },
        "result.transitions[0].pathways[0].output_semantics is invalid."],
      ["pathway support", (result) => { pathway(result).support = "unknown"; },
        "result.transitions[0].pathways[0].support is invalid."],
      ["pathway classification", (result) => { pathway(result).classification = "unknown"; },
        "result.transitions[0].pathways[0].classification is invalid."],
      ["pathway interval", (result) => { pathway(result).interval_level = 0.8; },
        "result.transitions[0].pathways[0].interval_level must equal 0.9."],
      ["pathway count", (result) => { pathway(result).active_feature_count = -1; },
        "result.transitions[0].pathways[0].active_feature_count must be an integer from 0 through 4096."],
      ["pathway source count", (result) => { pathway(result).source_member_count = 4; },
        "result.transitions[0].pathways[0].source_member_count is outside the contract bound."],
      ["pathway fitted count", (result) => { pathway(result).fitted_feature_count = 0; },
        "result.transitions[0].pathways[0].fitted_feature_count must be 1 through 4096."],
      ["pathway count closure", (result) => { pathway(result).observed_count = 1; },
        "result.transitions[0].pathways[0] active feature counts do not close."],
      ["unique active count", (result) => { pathway(result).unique_active_gene_count = 4_097; },
        "result.transitions[0].pathways[0].unique_active_gene_count must be an integer from 0 through 4096."],
      ["unique active closure", (result) => { pathway(result).unique_active_gene_count = 39; },
        "result.transitions[0].pathways[0].unique_active_gene_count cannot exceed active features."],
      ["PI3K confounding", (result) => { pathway(result, 2).overlap_confounded = false; },
        "result.transitions[0].pathways[2] must expose PI3K/AKT overlap confounding."],
      ["uncertainty object", (result) => { pathway(result).uncertainty = null; },
        "result.transitions[0].pathways[0].uncertainty must be an object."],
      ["uncertainty finite", (result) => { uncertainty(result).combined_standard_error = null; },
        "result.transitions[0].pathways[0].uncertainty.combined_standard_error must be finite."],
      ["uncertainty nonnegative", (result) => { uncertainty(result).variance_closure_residual = -1; },
        "result.transitions[0].pathways[0].uncertainty.variance_closure_residual must be nonnegative."],
      ["uncertainty bootstrap", (result) => { uncertainty(result).bootstrap_replicates_used = 0; },
        "result.transitions[0].pathways[0].uncertainty.bootstrap_replicates_used must be 1 through 256."],
      ["uncertainty estimated reason", (result) => { uncertainty(result).reason = "bad"; },
        "result.transitions[0].pathways[0].uncertainty.reason must be null when estimated."],
      ["uncertainty abstention", (result) => {
        uncertainty(result).state = "not_estimable";
      }, "result.transitions[0].pathways[0].uncertainty.measurement_standard_error must be null."],
      ["uncertainty state", (result) => { uncertainty(result).state = "unknown"; },
        "result.transitions[0].pathways[0].uncertainty.state is invalid."],
      ["contribution list", (result) => { pathway(result).top_contributions = null; },
        "result.transitions[0].pathways[0].top_contributions must contain at most 10 entries."],
      ["contribution object", (result) => {
        (pathway(result).top_contributions as unknown[])[0] = null;
      }, "result.transitions[0].pathways[0].top_contributions[0] must be an object."],
      ["contribution digest", (result) => { contribution(result).from_provenance_digest = "bad"; },
        "result.transitions[0].pathways[0].top_contributions[0].from_provenance_digest must be a sha256 digest."],
      ["contribution state", (result) => { contribution(result).from_state = "missing"; },
        "result.transitions[0].pathways[0].top_contributions[0] must decompose an exact observed-to-observed delta."],
      ["contribution finite", (result) => { contribution(result).pathway_loading = null; },
        "result.transitions[0].pathways[0].top_contributions[0].pathway_loading must be finite."],
      ["contribution closure", (result) => { contribution(result).conditional_contribution = 0.17; },
        "result.transitions[0].pathways[0].top_contributions[0] conditional contribution does not close its decomposition."],
      ["contribution direction", (result) => {
        contribution(result).direction = "conditional_source_primary_aligned";
      }, "result.transitions[0].pathways[0].top_contributions[0].direction must match its nonzero conditional contribution."],
      ["contribution reliability", (result) => { contribution(result).reliability_weight = 0; },
        "result.transitions[0].pathways[0].top_contributions[0].reliability_weight must be in (0,1]."],
      ["ablations object", (result) => { pathway(result).ablations = null; },
        "result.transitions[0].pathways[0].ablations must be an object."],
      ["ablation object", (result) => {
        (pathway(result).ablations as JsonObject).global_axis = 3;
      }, "result.transitions[0].pathways[0].ablations.global_axis must be an object."],
      ["ablation kind", (result) => { ablation(result).component_kind = "unknown"; },
        "result.transitions[0].pathways[0].ablations.global_axis.component_kind is invalid."],
      ["ablation support", (result) => { ablation(result).support = "unknown"; },
        "result.transitions[0].pathways[0].ablations.global_axis.support is invalid."],
      ["ablation removed count", (result) => { ablation(result).removed_feature_count = -1; },
        "result.transitions[0].pathways[0].ablations.global_axis.removed_feature_count must be 0 through 4096."],
      ["ablation abstention", (result) => { ablation(result).support = "abstained"; },
        "result.transitions[0].pathways[0].ablations.global_axis abstention fields are inconsistent."],
      ["ablation estimate", (result) => {
        ablation(result).conditional_score_without_component = null;
      }, "result.transitions[0].pathways[0].ablations.global_axis requires finite estimated ablation fields."],
      ["supported ablation reason", (result) => { ablation(result).support = "supported"; },
        "result.transitions[0].pathways[0].ablations.global_axis supported ablation must not carry a reason."],
      ["limited ablation reason", (result) => { ablation(result).reason = ""; },
        "result.transitions[0].pathways[0].ablations.global_axis LIMITED ablation requires a reason."],
      ["ablation arrays", (result) => {
        (pathway(result).ablations as JsonObject).source_processing = null;
      }, "result.transitions[0].pathways[0].ablations.source_processing must be an array."],
      ["pathway reasons", (result) => { pathway(result).abstention_reasons = [3]; },
        "result.transitions[0].pathways[0].abstention_reasons must contain at most 12 strings."],
      ["pathway abstention", (result) => { pathway(result).support = "abstained"; },
        "result.transitions[0].pathways[0] abstention fields are inconsistent."],
      ["pathway estimate", (result) => { pathway(result).score = null; },
        "result.transitions[0].pathways[0] requires complete finite coordinates and diagnostics."],
      ["pathway interval classification", (result) => {
        pathway(result).classification = "conditionally_stable";
      }, "result.transitions[0].pathways[0].classification must be supported by its 90% interval."],
      ["pathway support gates", (result) => { pathway(result).coefficient_mass_coverage = 0.4; },
        "result.transitions[0].pathways[0] estimated output does not meet pathway support gates."],
      ["pathway attribution gates", (result) => { pathway(result).stability = 0.7; },
        "result.transitions[0].pathways[0] SUPPORTED output does not meet attribution gates."],
      ["limited pathway reason", (result) => {
        pathway(result).support = "limited";
      }, "result.transitions[0].pathways[0] LIMITED output requires an explicit limitation reason."],
      ["provenance object", (result) => { result.provenance = null; },
        "result.provenance must be an object."],
      ["provenance identity", (result) => {
        (result.provenance as JsonObject).source_patient_count = 1;
      }, "result provenance identity does not close with the receipt."],
      ["provenance digest", (result) => {
        (result.provenance as JsonObject).computational_digest = "bad";
      }, "result.provenance.computational_digest must be a sha256 digest."],
      ["provenance seed", (result) => {
        (result.provenance as JsonObject).bootstrap_seed = -1;
      }, "result.provenance.bootstrap_seed must be a safe non-negative integer."],
      ["assay digest binding", (result) => {
        (result.provenance as JsonObject).assay_compatibility_digest = shaA;
      }, "result.provenance.assay_compatibility_digest does not match the result."],
      ["normalization binding", (result) => {
        (result.provenance as JsonObject).normalization_reference_digest = shaA;
      }, "result.provenance.normalization_reference_digest does not match the result."],
      ["provenance licenses", (result) => {
        (result.provenance as JsonObject).source_licenses = ["only-one"];
      }, "result.provenance.source_licenses must contain 2 through 4 entries."],
      ["limitations", (result) => { result.limitations = ["too short"]; },
        "result.limitations must contain 6 through 20 non-empty entries."],
    ];

    const { result } = admittedDocuments();
    for (const [label, mutate, expected] of resultCases) {
      const candidate = document(result);
      mutate(candidate);
      expect(validateReactomeTransitionResult(candidate), label).toContain(expected);
    }
  });

  it("fails closed across demo, result, profile, and replay bindings", () => {
    const { request, profile, result, verification } = admittedDocuments();

    expect(validateReactomeTransitionDemo(request, headers({
      "X-GLIO-Request-Digest": String(profile.demo_request_digest),
    }), null)).toContain(
      "The admitted Reactome-transition profile is unavailable for demo binding.",
    );
    const foreignDemoProfile = document(profile);
    foreignDemoProfile.demo_id = "foreign";
    foreignDemoProfile.demo_request_digest = shaA;
    expect(validateReactomeTransitionDemo(request, headers({
      "X-GLIO-Profile-Digest": String(foreignDemoProfile.profile_digest),
      "X-GLIO-Request-Digest": String(profile.demo_request_digest),
    }), foreignDemoProfile)).toEqual(expect.arrayContaining([
      "The Reactome demo series_id must match the loaded profile.demo_id.",
      "The canonical Reactome demo request digest must match profile.demo_request_digest.",
    ]));

    const foreignRequest = document(request);
    foreignRequest.profile_id = "foreign";
    foreignRequest.assay_compatibility = { foreign: true };
    foreignRequest.normalization_reference = { foreign: true };
    foreignRequest.time_points = [null, { time_point_id: 3 }];
    expect(validateReactomeTransitionResultRequestBinding(result, foreignRequest)).toEqual(
      expect.arrayContaining([
        "result.profile_id must match the submitted request.",
        "result.assay_compatibility must exactly match the submitted request.",
        "result.normalization_reference must exactly match the submitted request.",
        "result.time_point_ids must exactly match the submitted request order.",
      ]),
    );

    const foreignProfile = document(profile);
    foreignProfile.profile_digest = shaA;
    foreignProfile.required_assay_compatibility = { foreign: true };
    (foreignProfile.digests as JsonObject).fold_policy_digest = `sha256:${"b".repeat(64)}`;
    ((foreignProfile.pathways as JsonObject[])[0]).pathway_name = "foreign";
    expect(validateReactomeTransitionResultProfileBinding(result, foreignProfile)).toEqual(
      expect.arrayContaining([
        "result.profile_digest must match the admitted loaded profile.",
        "result.assay_compatibility must match the loaded profile requirement.",
        "result.provenance.fold_policy_digest must match profile.digests.fold_policy_digest.",
        "result.transitions[0].pathways[0] does not match the loaded profile identity.",
      ]),
    );

    const malformedResult = document(result);
    (malformedResult.transitions as unknown[])[0] = null;
    expect(validateReactomeTransitionResultProfileBinding(malformedResult, profile)).toEqual([]);

    const malformedVerification = document(verification);
    malformedVerification.semantic_match = "true";
    malformedVerification.recomputed_request_digest = shaA;
    const foreignResult = document(result);
    foreignResult.profile_digest = shaA;
    expect(validateReactomeTransitionVerification(
      malformedVerification,
      foreignResult,
      profile,
    )).toEqual(expect.arrayContaining([
      "verification.semantic_match must be Boolean.",
      "verification.semantic_match does not close its semantic checks.",
      "verification recomputed digests must match the admitted receipt.",
      "verification result/profile binding does not match the admitted profile.",
    ]));

    expect(validateReactomeTransitionResultHeaders(headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    }), result)).toEqual([]);
    expect(validateReactomeTransitionVerificationHeaders(headers({}), verification, profile))
      .toEqual(expect.arrayContaining([
        "X-GLIO-Profile-Digest response header must be a lowercase sha256 digest.",
        "X-GLIO-Request-Digest response header must be a lowercase sha256 digest.",
        "X-GLIO-Result-Digest response header must be a lowercase sha256 digest.",
      ]));
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
