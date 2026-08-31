import { describe, expect, it } from "vitest";

import {
  LONGITUDINAL_GBM_NEFTEL_PROGRAM_IDS,
  LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID,
  neftelEstimatedProgramCount,
  neftelProgramCount,
  neftelTransitionProfileDigest,
  neftelTransitionRequestDigest,
  neftelTransitionResultDigest,
  neftelSupportedProgramCount,
  neftelTransitionRequestStats,
  normalizeNeftelEvaluation,
  normalizeNeftelTransitions,
  validateNeftelTransitionProfile,
  validateNeftelTransitionProfileHeaders,
  validateNeftelTransitionRequest,
  validateNeftelTransitionResult,
  validateNeftelTransitionResultHeaders,
  validateNeftelTransitionResultProfileBinding,
  validateNeftelTransitionResultRequestBinding,
  validateNeftelTransitionVerification,
  validateNeftelTransitionVerificationHeaders,
} from "../../src/lib/longitudinal-gbm-neftel-transition";
import type { JsonObject } from "../../src/lib/research-state";
import {
  neftelTransitionAnalysis,
  neftelTransitionDemoRequest,
  neftelTransitionProfile,
  neftelTransitionVerification,
} from "../fixtures/longitudinal-gbm-neftel-transition";

function document(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

function reseal(value: JsonObject): JsonObject {
  value.result_digest = neftelTransitionResultDigest(value);
  return value;
}

function firstTransition(value: JsonObject): JsonObject {
  const transitions = value.transitions;
  if (!Array.isArray(transitions) || typeof transitions[0] !== "object" || transitions[0] === null || Array.isArray(transitions[0])) {
    throw new Error("fixture transition is unavailable");
  }
  return transitions[0] as JsonObject;
}

function firstProgram(value: JsonObject): JsonObject {
  const programs = firstTransition(value).programs;
  if (!Array.isArray(programs) || typeof programs[0] !== "object" || programs[0] === null || Array.isArray(programs[0])) {
    throw new Error("fixture program is unavailable");
  }
  return programs[0] as JsonObject;
}

function firstGlobal(value: JsonObject): JsonObject {
  const global = firstTransition(value).global_transition;
  if (typeof global !== "object" || global === null || Array.isArray(global)) {
    throw new Error("fixture global transition is unavailable");
  }
  return global as JsonObject;
}

function firstObservation(value: JsonObject): JsonObject {
  const points = value.time_points;
  const firstPoint = Array.isArray(points) ? points[0] : null;
  const observations = firstPoint && typeof firstPoint === "object" && !Array.isArray(firstPoint)
    ? (firstPoint as JsonObject).observations
    : null;
  const observation = Array.isArray(observations) ? observations[0] : null;
  if (typeof observation !== "object" || observation === null || Array.isArray(observation)) {
    throw new Error("fixture observation is unavailable");
  }
  return observation as JsonObject;
}

function firstUncertainty(value: JsonObject): JsonObject {
  const uncertainty = firstProgram(value).uncertainty;
  if (typeof uncertainty !== "object" || uncertainty === null || Array.isArray(uncertainty)) {
    throw new Error("fixture uncertainty is unavailable");
  }
  return uncertainty as JsonObject;
}

function firstContribution(value: JsonObject): JsonObject {
  const contributions = firstProgram(value).top_contributions;
  if (!Array.isArray(contributions) || typeof contributions[0] !== "object" || contributions[0] === null || Array.isArray(contributions[0])) {
    throw new Error("fixture contribution is unavailable");
  }
  return contributions[0] as JsonObject;
}

function firstAblations(value: JsonObject): JsonObject {
  const ablations = firstProgram(value).ablations;
  if (typeof ablations !== "object" || ablations === null || Array.isArray(ablations)) {
    throw new Error("fixture ablations are unavailable");
  }
  return ablations as JsonObject;
}

function firstAblation(value: JsonObject): JsonObject {
  const ablation = firstAblations(value).global_axis;
  if (typeof ablation !== "object" || ablation === null || Array.isArray(ablation)) {
    throw new Error("fixture global-axis ablation is unavailable");
  }
  return ablation as JsonObject;
}

describe("longitudinal GBM Neftel-transition lifecycle admission", () => {
  it("admits the generated backend profile, demo, result, headers, and replay closure", () => {
    const profile = document(neftelTransitionProfile);
    const request = document(neftelTransitionDemoRequest);
    const result = document(neftelTransitionAnalysis);
    const verification = document(neftelTransitionVerification);

    expect(validateNeftelTransitionProfile(profile)).toEqual([]);
    expect(validateNeftelTransitionProfileHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
    }), profile)).toEqual([]);
    expect(validateNeftelTransitionRequest(request)).toEqual([]);
    expect(validateNeftelTransitionResult(result)).toEqual([]);
    expect(validateNeftelTransitionResultRequestBinding(result, request)).toEqual([]);
    expect(validateNeftelTransitionResultProfileBinding(result, profile)).toEqual([]);
    expect(validateNeftelTransitionResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    }), result, request)).toEqual([]);
    expect(validateNeftelTransitionVerification(verification, result)).toEqual([]);
    expect(validateNeftelTransitionVerificationHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(verification.recomputed_request_digest),
      "X-GLIO-Result-Digest": String(verification.recomputed_result_digest),
    }), verification, profile)).toEqual([]);
  });

  it("recomputes the exact backend canonical result digest before admission", () => {
    const result = document(neftelTransitionAnalysis);
    expect(neftelTransitionResultDigest(result)).toBe(result.result_digest);
    expect(validateNeftelTransitionResult(result)).toEqual([]);

    const pythonFloatOracles: Array<[number, string]> = [
      [-0, "sha256:d9c5a30ac0f8ca6201bb23abbd767bd1b8f2cf2c1af7e660a17a626f799c06a1"],
      [0, "sha256:5e3e66b696098b4efc842d92ae12ffaa5835afb2256b08034f7f3aa464562712"],
      [1e-5, "sha256:2c5641aef7e8121735ba14653c4f3470ef5ea200d6bdb9f4cad9012a76a5f0b2"],
      [1e20, "sha256:a7e26a1f41fc74aae8a0d4e85ec7e11b6a1344b5fb97d8c37709f5ae4e3afc86"],
      [1.25e20, "sha256:12f8f723d3d4051798fe47ca564cd80bf5c6858f2ed2e6136c6db0904ad1bf56"],
      [1.25, "sha256:a6cfce9f586d10ca7998512eb8bedcdf6df2797c69183e4d27c3a27043cadf08"],
      [1_000, "sha256:aee2972925f2386107c484a81d87893434efc0ccb8dd6b8d08473788c0ea816c"],
    ];
    for (const [score, expected] of pythonFloatOracles) {
      expect(neftelTransitionResultDigest({ score })).toBe(expected);
    }
    expect(neftelTransitionResultDigest({ score: Number.NaN })).toMatch(
      /^sha256:[0-9a-f]{64}$/,
    );
  });

  it("recomputes exact Python-compatible profile and normalized-request digests", () => {
    const profile = document(neftelTransitionProfile);
    const request = document(neftelTransitionDemoRequest);
    const result = document(neftelTransitionAnalysis);
    expect(neftelTransitionProfileDigest(profile)).toBe(profile.profile_digest);
    expect(neftelTransitionRequestDigest(request)).toBe(result.request_digest);

    const reordered = document(request);
    const firstPoint = (reordered.time_points as JsonObject[])[0];
    (firstPoint.observations as unknown[]).reverse();
    expect(neftelTransitionRequestDigest(reordered)).toBe(result.request_digest);

    const defaulted = document(request);
    delete defaulted.profile_id;
    delete defaulted.bootstrap_replicates;
    expect(neftelTransitionRequestDigest(defaulted)).toBe(result.request_digest);
  });

  it("admits each exact interval-supported global classification", () => {
    const cases = [
      [0.4, 0.3, 0.5, "source_later_timepoint_aligned"],
      [-0.4, -0.5, -0.3, "source_earlier_timepoint_aligned"],
      [0.2, 0, 0.5, "indeterminate"],
    ] as const;
    for (const [score, lower, upper, classification] of cases) {
      const result = document(neftelTransitionAnalysis);
      Object.assign(firstGlobal(result), {
        classification,
        lower_bound: lower,
        score,
        upper_bound: upper,
      });
      reseal(result);
      expect(validateNeftelTransitionResult(result)).toEqual([]);
    }
  });

  it("preserves the exact eight-program topology and full generated request counts", () => {
    const request = document(neftelTransitionDemoRequest);
    const transitions = normalizeNeftelTransitions(document(neftelTransitionAnalysis));

    expect(neftelTransitionRequestStats(request)).toEqual({
      timePoints: 4,
      transitions: 3,
      observations: 1_024,
      active: 1_024,
      genes: 256,
    });
    expect(transitions).toHaveLength(3);
    for (const transition of transitions) {
      expect(transition.programs.map((program) => program.programId)).toEqual(
        LONGITUDINAL_GBM_NEFTEL_PROGRAM_IDS,
      );
      expect(transition.programs.every((program) => program.support === "limited")).toBe(true);
      expect(transition.global.admittedActiveGenes).toBeGreaterThanOrEqual(
        transition.global.informativeActiveGenes,
      );
      expect(transition.global.informativeActiveGenes).toBe(
        transition.global.observedCount + transition.global.bindingLeftCensoredCount,
      );
      expect(transition.global.admittedActiveGenes).toBe(
        transition.global.observedCount + transition.global.admittedLeftCensoredCount,
      );
      for (const program of transition.programs) {
        expect(program.admittedActiveFeatureCount).toBeGreaterThanOrEqual(
          program.activeFeatureCount,
        );
        expect(program.activeFeatureCount).toBe(
          program.observedCount + program.leftCensoredCount,
        );
        expect(program.admittedActiveFeatureCount).toBe(
          program.observedCount + program.admittedLeftCensoredCount,
        );
      }
    }
    expect(neftelProgramCount(transitions)).toBe(24);
    expect(neftelEstimatedProgramCount(transitions)).toBe(24);
    expect(neftelSupportedProgramCount(transitions)).toBe(0);
  });

  it("shows that fitted loadings lose to equal membership and keeps every program limited", () => {
    const evaluation = normalizeNeftelEvaluation(document(neftelTransitionProfile));
    expect(evaluation).toMatchObject({
      patientCount: 104,
      evaluationCount: 520,
      releaseGate: "limited_fitted_dictionary_not_preferred_to_equal_membership",
      individuallySupportedProgramCount: 0,
      jointVsGlobalIntervalSupportsPositiveGain: true,
      jointVsEqualIntervalSupportsPositiveGain: false,
      allLeaveProgramIntervalsCrossZero: true,
      equalMembershipMedianMae: 0.5177467313,
      jointMedianMae: 0.5754778047,
      jointVsEqualMedianGain: -0.105617713,
      patientClusterJointVsEqualInterval: [-0.1155036986, -0.0777444485],
    });
    expect(evaluation?.jointMedianMae ?? 0).toBeGreaterThan(evaluation?.equalMembershipMedianMae ?? 1);
  });
});

describe("longitudinal GBM Neftel-transition fail-closed behavior", () => {
  it("rejects stale profile receipts after interpretation or metric tampering", () => {
    const interpretation = document(neftelTransitionProfile);
    interpretation.interpretation = "cell_state_transition";
    expect(validateNeftelTransitionProfile(interpretation)).toEqual(expect.arrayContaining([
      "profile.profile_digest does not match the canonical profile payload.",
      "profile exceeds or differs from the admitted LIMITED claim ceiling.",
    ]));

    const evaluationInterpretation = document(neftelTransitionProfile);
    (evaluationInterpretation.evaluation as JsonObject).interpretation = "validated effect";
    expect(validateNeftelTransitionProfile(evaluationInterpretation)).toEqual(expect.arrayContaining([
      "profile.profile_digest does not match the canonical profile payload.",
      "profile evaluation does not preserve the admitted LIMITED release gate.",
    ]));

    const gain = document(neftelTransitionProfile);
    const evaluation = gain.evaluation as JsonObject;
    evaluation.joint_vs_global_median_relative_mae_gain =
      Number(evaluation.joint_vs_global_median_relative_mae_gain) + 0.0001;
    expect(validateNeftelTransitionProfile(gain)).toContain(
      "profile.profile_digest does not match the canonical profile payload.",
    );
  });

  it("rejects stale result and header request receipts after evidence tampering", () => {
    const request = document(neftelTransitionDemoRequest);
    const result = document(neftelTransitionAnalysis);
    firstObservation(request).log_abundance = Number(firstObservation(request).log_abundance) + 0.01;

    expect(validateNeftelTransitionResultRequestBinding(result, request)).toContain(
      "result.request_digest must match the canonical submitted request.",
    );
    expect(validateNeftelTransitionResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    }), result, request)).toContain(
      "X-GLIO-Request-Digest response header must match the admitted payload.",
    );
  });

  it("rejects stale receipts and otherwise well-shaped body tampering", () => {
    const bodyTampering = document(neftelTransitionAnalysis);
    bodyTampering.series_id = "tampered-series";
    expect(validateNeftelTransitionResult(bodyTampering)).toContain(
      "result.result_digest does not match the canonical result payload.",
    );

    const staleDigest = document(neftelTransitionAnalysis);
    staleDigest.result_digest = `sha256:${"0".repeat(64)}`;
    expect(validateNeftelTransitionResult(staleDigest)).toContain(
      "result.result_digest does not match the canonical result payload.",
    );
  });

  it("rejects cross-family and interval-inconsistent classification claims", () => {
    const foreignGlobal = document(neftelTransitionAnalysis);
    firstGlobal(foreignGlobal).classification = "conditionally_stable";
    reseal(foreignGlobal);
    expect(validateNeftelTransitionResult(foreignGlobal)).toContain(
      "result.transitions[0].global_transition.classification is invalid.",
    );

    const inconsistentGlobal = document(neftelTransitionAnalysis);
    firstGlobal(inconsistentGlobal).classification = "not_estimable";
    reseal(inconsistentGlobal);
    expect(validateNeftelTransitionResult(inconsistentGlobal)).toContain(
      "result.transitions[0].global_transition.classification must be supported by its 90% interval.",
    );

    const foreignProgram = document(neftelTransitionAnalysis);
    firstProgram(foreignProgram).classification = "stable";
    reseal(foreignProgram);
    expect(validateNeftelTransitionResult(foreignProgram)).toContain(
      "result.transitions[0].programs[0].classification is invalid.",
    );

    const inconsistentProgram = document(neftelTransitionAnalysis);
    firstProgram(inconsistentProgram).classification = "not_estimable";
    reseal(inconsistentProgram);
    expect(validateNeftelTransitionResult(inconsistentProgram)).toContain(
      "result.transitions[0].programs[0].classification must be supported by its 90% interval.",
    );
  });

  it("rejects negative uncertainty scales and closure residuals", () => {
    for (const field of [
      "measurement_standard_error",
      "fitted_model_standard_error",
      "combined_standard_error",
      "variance_closure_residual",
    ]) {
      const result = document(neftelTransitionAnalysis);
      firstUncertainty(result)[field] = -0.01;
      reseal(result);
      expect(validateNeftelTransitionResult(result)).toContain(
        `result.transitions[0].programs[0].uncertainty.${field} must be nonnegative.`,
      );
    }

    const validNegativeCovariance = document(neftelTransitionAnalysis);
    expect(Number(firstUncertainty(validNegativeCovariance).measurement_model_covariance)).toBeLessThan(0);
    expect(validateNeftelTransitionResult(validNegativeCovariance)).toEqual([]);
  });

  it("enforces admitted, informative exact, and binding-censor count closure", () => {
    const malformedGlobalInteger = document(neftelTransitionAnalysis);
    firstGlobal(malformedGlobalInteger).admitted_left_censored_count = 0.5;
    reseal(malformedGlobalInteger);
    expect(validateNeftelTransitionResult(malformedGlobalInteger)).toContain(
      "result.transitions[0].global_transition.admitted_left_censored_count must be an integer from 0 through 4096.",
    );

    const informativeGlobal = document(neftelTransitionAnalysis);
    firstGlobal(informativeGlobal).shared_active_gene_count = 249;
    reseal(informativeGlobal);
    expect(validateNeftelTransitionResult(informativeGlobal)).toContain(
      "result.transitions[0].global_transition informative global counts do not close.",
    );

    const admittedGlobal = document(neftelTransitionAnalysis);
    firstGlobal(admittedGlobal).admitted_active_gene_count = 251;
    reseal(admittedGlobal);
    expect(validateNeftelTransitionResult(admittedGlobal)).toContain(
      "result.transitions[0].global_transition admitted global counts do not close.",
    );

    const invertedGlobal = document(neftelTransitionAnalysis);
    Object.assign(firstGlobal(invertedGlobal), {
      admitted_active_gene_count: 249,
      admitted_left_censored_count: 1,
      left_censored_count: 2,
      observed_count: 248,
      shared_active_gene_count: 250,
    });
    reseal(invertedGlobal);
    expect(validateNeftelTransitionResult(invertedGlobal)).toContain(
      "result.transitions[0].global_transition informative global evidence cannot exceed admitted evidence.",
    );

    const informativeProgram = document(neftelTransitionAnalysis);
    firstProgram(informativeProgram).active_feature_count = 39;
    reseal(informativeProgram);
    expect(validateNeftelTransitionResult(informativeProgram)).toContain(
      "result.transitions[0].programs[0] active feature counts do not close.",
    );

    const admittedProgram = document(neftelTransitionAnalysis);
    firstProgram(admittedProgram).admitted_active_feature_count = 41;
    reseal(admittedProgram);
    expect(validateNeftelTransitionResult(admittedProgram)).toContain(
      "result.transitions[0].programs[0] admitted feature counts do not close.",
    );

    const invertedProgram = document(neftelTransitionAnalysis);
    Object.assign(firstProgram(invertedProgram), {
      active_feature_count: 40,
      admitted_active_feature_count: 39,
      admitted_left_censored_count: 1,
      left_censored_count: 2,
      observed_count: 38,
    });
    reseal(invertedProgram);
    expect(validateNeftelTransitionResult(invertedProgram)).toContain(
      "result.transitions[0].programs[0] informative program evidence cannot exceed admitted evidence.",
    );

    const impossibleUniqueCount = document(neftelTransitionAnalysis);
    firstProgram(impossibleUniqueCount).unique_active_gene_count = 41;
    reseal(impossibleUniqueCount);
    expect(validateNeftelTransitionResult(impossibleUniqueCount)).toContain(
      "result.transitions[0].programs[0].unique_active_gene_count cannot exceed informative features.",
    );
  });

  it("rejects foreign identities, extra fields, reordered programs, and elevated claims", () => {
    const request = document(neftelTransitionDemoRequest);
    request.profile_id = "latest";
    expect(validateNeftelTransitionRequest(request)).toContain(
      `profile_id must equal ${LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID}.`,
    );

    const profile = document(neftelTransitionProfile);
    profile.claim_ceiling = "neftel_cell_state_activity";
    profile.outcome_independent = true;
    (profile.programs as unknown[]).reverse();
    expect(validateNeftelTransitionProfile(profile)).toEqual(expect.arrayContaining([
      expect.stringContaining("unsupported fields"),
      expect.stringContaining("LIMITED claim ceiling"),
      expect.stringContaining("exact source program identity"),
    ]));

    const result = document(neftelTransitionAnalysis);
    result.output_semantics = "cell_state_transition";
    result.clinical_prediction = true;
    (firstTransition(result).programs as unknown[]).reverse();
    expect(validateNeftelTransitionResult(result)).toEqual(expect.arrayContaining([
      expect.stringContaining("unsupported fields"),
      expect.stringContaining("research boundary"),
      expect.stringContaining("exact Neftel Table S2 program order"),
    ]));
  });

  it("rejects a hidden equal-membership failure or an unsupported program claim", () => {
    const profile = document(neftelTransitionProfile);
    const evaluation = profile.evaluation as JsonObject;
    evaluation.release_gate = "promoted";
    evaluation.joint_vs_equal_patient_cluster_interval_supports_positive_gain = true;
    evaluation.individually_supported_program_count = 1;
    evaluation.joint_median_standardized_mae = 0.4;
    expect(validateNeftelTransitionProfile(profile)).toEqual(expect.arrayContaining([
      "profile evaluation does not preserve the admitted LIMITED release gate.",
      "profile must expose that fitted program loadings lose to equal membership.",
      "profile must not claim an individually supported Neftel program.",
    ]));
  });

  it("rejects forged request/profile/header/replay bindings", () => {
    const result = document(neftelTransitionAnalysis);
    const request = document(neftelTransitionDemoRequest);
    request.series_id = "foreign-series";
    expect(validateNeftelTransitionResultRequestBinding(result, request)).toContain(
      "result.series_id must match the submitted request.",
    );

    const profile = document(neftelTransitionProfile);
    profile.profile_digest = `sha256:${"0".repeat(64)}`;
    expect(validateNeftelTransitionResultProfileBinding(result, profile)).toContain(
      "result.profile_digest must match the admitted loaded profile.",
    );
    expect(validateNeftelTransitionResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": `sha256:${"0".repeat(64)}`,
    }), result)).toContain(
      "X-GLIO-Result-Digest response header must match the admitted payload.",
    );

    const verification = document(neftelTransitionVerification);
    verification.program_semantic_match = false;
    verification.verified = false;
    expect(validateNeftelTransitionVerification(verification, result)).toEqual(expect.arrayContaining([
      "verification semantic components must all be true.",
      "verification must affirm every digest and semantic check.",
    ]));
    expect(validateNeftelTransitionVerificationHeaders(new Headers(), verification, document(neftelTransitionProfile))).toHaveLength(3);
  });

  it("normalizes uncertainty, contributions, and every fitted sensitivity family", () => {
    const transitions = normalizeNeftelTransitions(document(neftelTransitionAnalysis));
    const first = transitions[0].programs[0];
    expect(first).toMatchObject({
      programId: "MES2",
      uncertainty: {
        state: "estimated",
        bootstrapReplicates: 64,
      },
    });
    expect(first.contributions[0]).toMatchObject({
      geneSymbol: "RPL21",
      direction: "conditional_source_earlier_timepoint_aligned",
    });
    expect(new Set(first.ablations.map((ablation) => ablation.kind))).toEqual(new Set([
      "global_axis",
      "source_processing",
      "degree_normalization",
      "unique_members",
      "leave_program_out",
      "overlapping_program",
      "top_contribution",
    ]));

    const sparse = document(neftelTransitionAnalysis);
    const program = firstProgram(sparse);
    program.top_contributions = [null, {}];
    program.ablations = {};
    program.uncertainty = {};
    const normalized = normalizeNeftelTransitions(sparse)[0].programs[0];
    expect(normalized.contributions).toEqual([]);
    expect(normalized.ablations).toEqual([]);
    expect(normalized.uncertainty).toMatchObject({
      state: "not_estimable",
      bootstrapReplicates: 0,
    });
  });

  it("rejects every malformed profile identity, lock, panel, and source-term family", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { delete value.algorithm_id; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.model_id = "foreign"; },
      (value) => { value.parent_feature_axis_model_id = "foreign"; },
      (value) => { value.parent_dependency_semantics = "runtime_delegation"; },
      (value) => { value.profile_digest = "bad"; },
      (value) => { value.numpy_version = "latest"; },
      (value) => { value.safety_class = "clinical"; },
      (value) => { value.claim_ceiling = "cell_state"; },
      (value) => { value.maximum_evidence_grade = "validated"; },
      (value) => { value.required_assay_compatibility = null; },
      (value) => { value.constants = null; },
      (value) => { value.limits = null; },
      (value) => { value.counts = null; },
      (value) => { value.digests = null; },
      (value) => { value.evaluation = null; },
      (value) => { (value.counts as JsonObject).source_patient_count = 103; },
      (value) => { (value.counts as JsonObject).program_count = 7; },
      (value) => { (value.counts as JsonObject).fitted_union_feature_count = 255; },
      (value) => { (value.counts as JsonObject).offline_bootstrap_draw_count = 127; },
      (value) => { (value.evaluation as JsonObject).validation_scope = "external"; },
      (value) => { (value.evaluation as JsonObject).patient_count = 103; },
      (value) => { (value.evaluation as JsonObject).evaluation_count = 519; },
      (value) => { (value.evaluation as JsonObject).release_gate = "promoted"; },
      (value) => { (value.evaluation as JsonObject).joint_vs_global_patient_cluster_interval_supports_positive_gain = false; },
      (value) => { (value.evaluation as JsonObject).joint_vs_equal_patient_cluster_interval_supports_positive_gain = true; },
      (value) => { (value.evaluation as JsonObject).all_leave_program_q05_q95_intervals_cross_zero = false; },
      (value) => { (value.evaluation as JsonObject).equal_membership_median_standardized_mae = null; },
      (value) => { (value.evaluation as JsonObject).joint_median_standardized_mae = null; },
      (value) => { (value.evaluation as JsonObject).joint_median_standardized_mae = 0.5; },
      (value) => { value.programs = null; },
      (value) => { value.programs = (value.programs as unknown[]).slice(0, 7) as never; },
      (value) => { (value.programs as unknown[])[0] = null; },
      (value) => { ((value.programs as JsonObject[])[0]).program_index = 1; },
      (value) => { ((value.programs as JsonObject[])[0]).domain_id = "foreign"; },
      (value) => { ((value.programs as JsonObject[])[0]).program_id = "foreign"; },
      (value) => { ((value.programs as JsonObject[])[0]).program_name = "foreign"; },
      (value) => { ((value.programs as JsonObject[])[0]).extra = true; },
      (value) => { delete ((value.programs as JsonObject[])[0]).source_member_count; },
      (value) => { value.source_terms = null; },
      (value) => { value.source_terms = []; },
      (value) => { value.source_terms = [""]; },
    ];
    for (const mutate of mutations) {
      const value = document(neftelTransitionProfile);
      mutate(value);
      expect(validateNeftelTransitionProfile(value).length).toBeGreaterThan(0);
    }
    expect(validateNeftelTransitionProfile({}).length).toBeGreaterThan(8);
    expect(validateNeftelTransitionProfileHeaders(new Headers(), document(neftelTransitionProfile))).not.toEqual([]);
  });

  it("rejects malformed result topology, global estimates, and provenance", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { delete value.algorithm_id; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.request_digest = "bad"; },
      (value) => { value.result_digest = "bad"; },
      (value) => { value.profile_digest = "bad"; },
      (value) => { value.output_semantics = "activity"; },
      (value) => { value.validation_scope = "external"; },
      (value) => { value.research_use_only = false; },
      (value) => { value.non_prescriptive = false; },
      (value) => { value.assay_compatibility = null; },
      (value) => { value.normalization_reference = null; },
      (value) => { value.time_point_ids = null; },
      (value) => { value.time_point_ids = ["T0"]; },
      (value) => { value.time_point_ids = Array.from({ length: 17 }, (_, index) => `T${index}`); },
      (value) => { value.time_point_ids = ["T0", "T0"]; },
      (value) => { value.time_point_ids = ["T0", ""]; },
      (value) => { value.transitions = null; },
      (value) => { value.transitions = []; },
      (value) => { (value.transitions as unknown[])[0] = null; },
      (value) => { firstTransition(value).extra = true; },
      (value) => { delete firstTransition(value).duration_days; },
      (value) => { firstTransition(value).transition_index = 1; },
      (value) => { firstTransition(value).from_time_point_id = "foreign"; },
      (value) => { firstTransition(value).to_time_point_id = "foreign"; },
      (value) => { firstTransition(value).duration_days = null; },
      (value) => { firstTransition(value).duration_days = 0; },
      (value) => { firstTransition(value).programs = null; },
      (value) => { firstTransition(value).programs = []; },
      (value) => { firstTransition(value).global_transition = null; },
      (value) => { firstGlobal(value).extra = true; },
      (value) => { delete firstGlobal(value).score; },
      (value) => { firstGlobal(value).output_semantics = "activity"; },
      (value) => { firstGlobal(value).support = null; },
      (value) => { firstGlobal(value).support = "unknown"; },
      (value) => { firstGlobal(value).interval_level = 0.95; },
      (value) => { firstGlobal(value).admitted_active_gene_count = null; },
      (value) => { firstGlobal(value).shared_active_gene_count = -1; },
      (value) => { firstGlobal(value).observed_count = 0.5; },
      (value) => { firstGlobal(value).left_censored_count = 4_097; },
      (value) => { firstGlobal(value).admitted_left_censored_count = null; },
      (value) => { firstGlobal(value).shared_active_gene_count = 249; },
      (value) => { firstGlobal(value).admitted_active_gene_count = 251; },
      (value) => { firstGlobal(value).abstention_reasons = null; },
      (value) => { firstGlobal(value).abstention_reasons = [""]; },
      (value) => { firstGlobal(value).abstention_reasons = Array.from({ length: 9 }, () => "limit"); },
      (value) => { firstGlobal(value).score = null; },
      (value) => { firstGlobal(value).lower_bound = null; },
      (value) => { firstGlobal(value).upper_bound = null; },
      (value) => { firstGlobal(value).lower_bound = 2; },
      (value) => { firstGlobal(value).upper_bound = -2; },
      (value) => { firstGlobal(value).bootstrap_replicates_used = 0; },
      (value) => { value.provenance = null; },
      (value) => { (value.provenance as JsonObject).engine = "foreign"; },
      (value) => { (value.provenance as JsonObject).source_patient_count = 103; },
      (value) => { (value.provenance as JsonObject).numpy_version = "latest"; },
      (value) => { (value.provenance as JsonObject).request_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).profile_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).evaluation_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).extra = true; },
      (value) => { delete (value.provenance as JsonObject).source_catalog_content_digest; },
      (value) => { value.limitations = null; },
      (value) => { value.limitations = []; },
      (value) => { value.limitations = Array.from({ length: 21 }, () => "limit"); },
      (value) => { value.limitations = ["", "a", "b", "c", "d", "e"]; },
    ];
    for (const mutate of mutations) {
      const value = document(neftelTransitionAnalysis);
      mutate(value);
      expect(validateNeftelTransitionResult(value).length).toBeGreaterThan(0);
    }

    const abstained = document(neftelTransitionAnalysis);
    Object.assign(firstGlobal(abstained), {
      support: "abstained",
      classification: "not_estimable",
      score: null,
      lower_bound: null,
      upper_bound: null,
      bootstrap_replicates_used: 0,
      abstention_reasons: ["not estimable"],
    });
    reseal(abstained);
    expect(validateNeftelTransitionResult(abstained)).toEqual([]);
    const abstainedMutations: Array<(value: JsonObject) => void> = [
      (value) => { firstGlobal(value).score = 0; },
      (value) => { firstGlobal(value).lower_bound = 0; },
      (value) => { firstGlobal(value).upper_bound = 0; },
      (value) => { firstGlobal(value).classification = "stable"; },
      (value) => { firstGlobal(value).bootstrap_replicates_used = 1; },
      (value) => { firstGlobal(value).abstention_reasons = []; },
    ];
    for (const mutate of abstainedMutations) {
      const value = document(abstained);
      mutate(value);
      expect(validateNeftelTransitionResult(value).length).toBeGreaterThan(0);
    }
    expect(validateNeftelTransitionResult({}).length).toBeGreaterThan(8);
  });

  it("rejects malformed program estimates, uncertainty, contributions, and ablations", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { (firstTransition(value).programs as unknown[])[0] = null; },
      (value) => { firstProgram(value).extra = true; },
      (value) => { delete firstProgram(value).program_name; },
      (value) => { firstProgram(value).program_index = 1; },
      (value) => { firstProgram(value).domain_id = "foreign"; },
      (value) => { firstProgram(value).program_id = "foreign"; },
      (value) => { firstProgram(value).program_name = "foreign"; },
      (value) => { firstProgram(value).output_semantics = "activity"; },
      (value) => { firstProgram(value).support = null; },
      (value) => { firstProgram(value).support = "unknown"; },
      (value) => { firstProgram(value).interval_level = 0.95; },
      (value) => { firstProgram(value).admitted_active_feature_count = null; },
      (value) => { firstProgram(value).active_feature_count = null; },
      (value) => { firstProgram(value).observed_count = -1; },
      (value) => { firstProgram(value).left_censored_count = 0.5; },
      (value) => { firstProgram(value).admitted_left_censored_count = 4_097; },
      (value) => { firstProgram(value).unique_active_gene_count = 4_097; },
      (value) => { firstProgram(value).active_feature_count = 41; },
      (value) => { firstProgram(value).admitted_active_feature_count = 41; },
      (value) => { firstProgram(value).uncertainty = null; },
      (value) => { firstUncertainty(value).extra = true; },
      (value) => { delete firstUncertainty(value).state; },
      (value) => { firstUncertainty(value).measurement_standard_error = null; },
      (value) => { firstUncertainty(value).fitted_model_standard_error = null; },
      (value) => { firstUncertainty(value).measurement_model_covariance = null; },
      (value) => { firstUncertainty(value).combined_standard_error = null; },
      (value) => { firstUncertainty(value).variance_closure_residual = null; },
      (value) => { firstUncertainty(value).bootstrap_replicates_used = 0; },
      (value) => { firstUncertainty(value).reason = "unexpected"; },
      (value) => { firstUncertainty(value).state = "unknown"; },
      (value) => { firstProgram(value).top_contributions = null; },
      (value) => { firstProgram(value).top_contributions = Array.from({ length: 11 }, () => null); },
      (value) => { (firstProgram(value).top_contributions as unknown[])[0] = null; },
      (value) => { firstContribution(value).extra = true; },
      (value) => { delete firstContribution(value).gene_symbol; },
      (value) => { firstContribution(value).from_provenance_digest = "bad"; },
      (value) => { firstContribution(value).to_provenance_digest = "bad"; },
      (value) => { firstContribution(value).from_state = "left_censored"; },
      (value) => { firstContribution(value).to_state = "left_censored"; },
      (value) => { firstContribution(value).value_semantics = "upper_bound"; },
      (value) => { firstContribution(value).reliability_weight = null; },
      (value) => { firstContribution(value).reliability_weight = 0; },
      (value) => { firstContribution(value).reliability_weight = 2; },
      (value) => { firstProgram(value).ablations = null; },
      (value) => { firstAblations(value).extra = true; },
      (value) => { delete firstAblations(value).global_axis; },
      (value) => { firstAblations(value).global_axis = 1; },
      (value) => { firstAblations(value).source_processing = null; },
      (value) => { firstAblations(value).overlap = null; },
      (value) => { firstAblations(value).top_contributions = null; },
      (value) => { firstAblations(value).source_processing = [null]; },
      (value) => { firstAblation(value).extra = true; },
      (value) => { delete firstAblation(value).component_kind; },
      (value) => { firstAblation(value).component_kind = null; },
      (value) => { firstAblation(value).component_kind = "unknown"; },
      (value) => { firstAblation(value).support = null; },
      (value) => { firstAblation(value).support = "unknown"; },
      (value) => { firstAblation(value).removed_feature_count = -1; },
      (value) => { firstAblation(value).conditional_score_without_component = null; },
      (value) => { firstAblation(value).score_delta = null; },
      (value) => { firstAblation(value).classification_without_component = "not_estimable"; },
      (value) => { firstProgram(value).abstention_reasons = null; },
      (value) => { firstProgram(value).abstention_reasons = [""]; },
      (value) => { firstProgram(value).abstention_reasons = Array.from({ length: 13 }, () => "limit"); },
      (value) => { firstProgram(value).score = null; },
      (value) => { firstProgram(value).lower_bound = null; },
      (value) => { firstProgram(value).upper_bound = null; },
      (value) => { firstProgram(value).lower_bound = 2; },
      (value) => { firstProgram(value).upper_bound = -2; },
      (value) => { firstProgram(value).abstention_reasons = []; },
    ];
    for (const mutate of mutations) {
      const value = document(neftelTransitionAnalysis);
      mutate(value);
      expect(validateNeftelTransitionResult(value).length).toBeGreaterThan(0);
    }

    const nullableScalarAblation = document(neftelTransitionAnalysis);
    firstAblations(nullableScalarAblation).global_axis = null;
    reseal(nullableScalarAblation);
    expect(validateNeftelTransitionResult(nullableScalarAblation)).toEqual([]);

    const notEstimableUncertainty = document(neftelTransitionAnalysis);
    Object.assign(firstUncertainty(notEstimableUncertainty), {
      state: "not_estimable",
      measurement_standard_error: null,
      fitted_model_standard_error: null,
      measurement_model_covariance: null,
      combined_standard_error: null,
      variance_closure_residual: null,
      bootstrap_replicates_used: 0,
      reason: "not estimable",
    });
    reseal(notEstimableUncertainty);
    expect(validateNeftelTransitionResult(notEstimableUncertainty)).toEqual([]);
    const uncertaintyMutations: Array<(value: JsonObject) => void> = [
      (value) => { firstUncertainty(value).measurement_standard_error = 1; },
      (value) => { firstUncertainty(value).fitted_model_standard_error = 1; },
      (value) => { firstUncertainty(value).measurement_model_covariance = 1; },
      (value) => { firstUncertainty(value).combined_standard_error = 1; },
      (value) => { firstUncertainty(value).variance_closure_residual = 1; },
      (value) => { firstUncertainty(value).bootstrap_replicates_used = 1; },
      (value) => { firstUncertainty(value).reason = null; },
      (value) => { firstUncertainty(value).reason = ""; },
    ];
    for (const mutate of uncertaintyMutations) {
      const value = document(notEstimableUncertainty);
      mutate(value);
      expect(validateNeftelTransitionResult(value).length).toBeGreaterThan(0);
    }

    const abstainedAblation = document(neftelTransitionAnalysis);
    Object.assign(firstAblation(abstainedAblation), {
      support: "abstained",
      conditional_score_without_component: null,
      score_delta: null,
      classification_without_component: "not_estimable",
      reason: "not estimable",
    });
    reseal(abstainedAblation);
    expect(validateNeftelTransitionResult(abstainedAblation)).toEqual([]);
    const ablationMutations: Array<(value: JsonObject) => void> = [
      (value) => { firstAblation(value).conditional_score_without_component = 0; },
      (value) => { firstAblation(value).score_delta = 0; },
      (value) => { firstAblation(value).classification_without_component = "conditionally_stable"; },
      (value) => { firstAblation(value).reason = null; },
      (value) => { firstAblation(value).reason = ""; },
    ];
    for (const mutate of ablationMutations) {
      const value = document(abstainedAblation);
      mutate(value);
      expect(validateNeftelTransitionResult(value).length).toBeGreaterThan(0);
    }

    const abstainedProgram = document(neftelTransitionAnalysis);
    Object.assign(firstProgram(abstainedProgram), {
      support: "abstained",
      classification: "not_estimable",
      score: null,
      lower_bound: null,
      upper_bound: null,
      abstention_reasons: ["not estimable"],
    });
    reseal(abstainedProgram);
    expect(validateNeftelTransitionResult(abstainedProgram)).toEqual([]);
    const programMutations: Array<(value: JsonObject) => void> = [
      (value) => { firstProgram(value).classification = "conditionally_stable"; },
      (value) => { firstProgram(value).score = 0; },
      (value) => { firstProgram(value).lower_bound = 0; },
      (value) => { firstProgram(value).upper_bound = 0; },
      (value) => { firstProgram(value).abstention_reasons = []; },
    ];
    for (const mutate of programMutations) {
      const value = document(abstainedProgram);
      mutate(value);
      expect(validateNeftelTransitionResult(value).length).toBeGreaterThan(0);
    }

    const supportedProgram = document(neftelTransitionAnalysis);
    firstProgram(supportedProgram).support = "supported";
    firstProgram(supportedProgram).abstention_reasons = [];
    expect(validateNeftelTransitionResult(supportedProgram)).toContain(
      "result.transitions[0].programs[0].support exceeds the lane-wide LIMITED evidence ceiling.",
    );

    const supportedGlobal = document(neftelTransitionAnalysis);
    firstGlobal(supportedGlobal).support = "supported";
    expect(validateNeftelTransitionResult(supportedGlobal)).toContain(
      "result.transitions[0].global_transition.support exceeds the lane-wide LIMITED evidence ceiling.",
    );
  });

  it("rejects every foreign request, profile-program, digest-header, and replay binding", () => {
    const result = document(neftelTransitionAnalysis);
    const requestMutations: Array<(value: JsonObject) => void> = [
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.assay_compatibility = null; },
      (value) => { value.normalization_reference = null; },
      (value) => { value.time_points = null; },
      (value) => { (value.time_points as unknown[])[0] = null; },
      (value) => { delete ((value.time_points as JsonObject[])[0]).time_point_id; },
      (value) => { ((value.time_points as JsonObject[])[0]).time_point_id = "foreign"; },
    ];
    for (const mutate of requestMutations) {
      const request = document(neftelTransitionDemoRequest);
      mutate(request);
      expect(validateNeftelTransitionResultRequestBinding(result, request).length).toBeGreaterThan(0);
    }
    const requestWithoutProfile = document(neftelTransitionDemoRequest);
    delete requestWithoutProfile.profile_id;
    expect(validateNeftelTransitionResultRequestBinding(result, requestWithoutProfile)).toEqual([]);
    const nonnumericBootstrap = document(neftelTransitionDemoRequest);
    nonnumericBootstrap.bootstrap_replicates = "64";
    expect(validateNeftelTransitionRequest(nonnumericBootstrap).length).toBeGreaterThan(0);
    const overBudget = document(neftelTransitionDemoRequest);
    overBudget.bootstrap_replicates = 256;
    overBudget.time_points = Array.from({ length: 16 }, () => (overBudget.time_points as JsonObject[])[0]);
    expect(validateNeftelTransitionRequest(overBudget)).toContain(
      "request exceeds the 4608 solver-work-unit limit: (time_points - 1) * (186 + 3 * bootstrap_replicates).",
    );

    const profileMutations: Array<(profile: JsonObject, result: JsonObject) => void> = [
      (profile) => { profile.profile_digest = `sha256:${"0".repeat(64)}`; },
      (profile, resultValue) => {
        const field = "evaluation_digest";
        (profile.digests as JsonObject)[field] = `sha256:${"0".repeat(64)}`;
        (resultValue.provenance as JsonObject)[field] = String((resultValue.provenance as JsonObject)[field]);
      },
      (_profile, resultValue) => { (resultValue.transitions as unknown[])[0] = null; },
      (_profile, resultValue) => { firstTransition(resultValue).programs = null; },
      (_profile, resultValue) => { (firstTransition(resultValue).programs as unknown[]).pop(); },
      (_profile, resultValue) => { (firstTransition(resultValue).programs as unknown[])[0] = null; },
      (profile, resultValue) => {
        (profile.programs as unknown[])[0] = null;
        (firstTransition(resultValue).programs as unknown[])[0] = null;
      },
      (_profile, resultValue) => { firstProgram(resultValue).program_index = 1; },
      (_profile, resultValue) => { firstProgram(resultValue).domain_id = "foreign"; },
      (_profile, resultValue) => { firstProgram(resultValue).program_id = "foreign"; },
      (_profile, resultValue) => { firstProgram(resultValue).program_name = "foreign"; },
    ];
    for (const mutate of profileMutations) {
      const profile = document(neftelTransitionProfile);
      const resultValue = document(neftelTransitionAnalysis);
      mutate(profile, resultValue);
      expect([
        ...validateNeftelTransitionResult(resultValue),
        ...validateNeftelTransitionResultProfileBinding(resultValue, profile),
      ].length).toBeGreaterThan(0);
    }
    const noDigests = document(neftelTransitionProfile);
    noDigests.digests = null;
    expect(validateNeftelTransitionResultProfileBinding(result, noDigests).length).toBeGreaterThan(0);
    const noProvenance = document(neftelTransitionAnalysis);
    noProvenance.provenance = null;
    expect(validateNeftelTransitionResultProfileBinding(noProvenance, document(neftelTransitionProfile))).toEqual([]);
    const noProfilePrograms = document(neftelTransitionProfile);
    noProfilePrograms.programs = null;
    expect(validateNeftelTransitionResultProfileBinding(result, noProfilePrograms).length).toBeGreaterThan(0);
    const noResultTransitions = document(neftelTransitionAnalysis);
    noResultTransitions.transitions = null;
    expect(validateNeftelTransitionResultProfileBinding(noResultTransitions, document(neftelTransitionProfile))).toEqual([]);

    expect(validateNeftelTransitionProfileHeaders(new Headers({
      "X-GLIO-Profile-Digest": `sha256:${"0".repeat(64)}`,
    }), document(neftelTransitionProfile))).toContain(
      "X-GLIO-Profile-Digest response header must match the admitted payload.",
    );
    expect(validateNeftelTransitionResultHeaders(new Headers(), result)).toHaveLength(3);
    expect(validateNeftelTransitionResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": "bad",
      "X-GLIO-Request-Digest": "bad",
      "X-GLIO-Result-Digest": "bad",
    }), result)).toHaveLength(3);

    const verificationMutations: Array<(value: JsonObject) => void> = [
      (value) => { delete value.message; },
      (value) => { value.extra = true; },
      (value) => { value.transition_topology_match = false; },
      (value) => { value.global_transition_semantic_match = false; },
      (value) => { value.program_semantic_match = false; },
      (value) => { value.uncertainty_semantic_match = false; },
      (value) => { value.ablation_semantic_match = false; },
      (value) => { value.provenance_match = false; },
      (value) => { value.document_semantic_match = false; },
      (value) => { value.verified = false; },
      (value) => { value.request_digest_match = false; },
      (value) => { value.profile_digest_match = false; },
      (value) => { value.result_digest_match = false; },
      (value) => { value.semantic_match = false; },
      (value) => { value.recomputed_request_digest = `sha256:${"0".repeat(64)}`; },
      (value) => { value.recomputed_result_digest = `sha256:${"0".repeat(64)}`; },
    ];
    for (const mutate of verificationMutations) {
      const value = document(neftelTransitionVerification);
      mutate(value);
      expect(validateNeftelTransitionVerification(value, result).length).toBeGreaterThan(0);
    }
  });

  it("uses fail-closed normalizer defaults for sparse and malformed nested records", () => {
    expect(normalizeNeftelTransitions({ transitions: null })).toEqual([]);
    expect(normalizeNeftelTransitions({ transitions: [null, {}] })).toEqual([
      expect.objectContaining({
        id: "unnamed-transition",
        index: 0,
        fromTimePointId: "unknown-from",
        toTimePointId: "unknown-to",
        durationDays: null,
        programs: [],
        global: {
          support: "abstained",
          classification: "not_estimable",
          score: null,
          lower: null,
          upper: null,
          admittedActiveGenes: 0,
          informativeActiveGenes: 0,
          observedCount: 0,
          bindingLeftCensoredCount: 0,
          admittedLeftCensoredCount: 0,
          coefficientMassCoverage: 0,
          effectiveSampleSize: null,
          bootstrapReplicates: 0,
          reasons: [],
        },
      }),
    ]);

    const sparse = {
      transitions: [{
        programs: [
          null,
          { support: "unknown", program_id: "MES2" },
          { support: "limited" },
          {
            support: "limited",
            program_id: "MES2",
            top_contributions: [null, {}, { gene_symbol: "" }, { gene_symbol: "EGFR" }],
            ablations: {
              global_axis: null,
              degree_normalization: { component_kind: "unknown", support: "limited" },
              unique_members: { component_kind: "global_axis", support: "unknown" },
              leave_program_out: {
                component_kind: "leave_program_out",
                support: "abstained",
              },
              source_processing: [],
              overlap: [],
              top_contributions: [],
            },
            uncertainty: {},
            abstention_reasons: ["limited", 1],
          },
        ],
        global_transition: {},
      }],
    } as JsonObject;
    const normalized = normalizeNeftelTransitions(sparse);
    expect(normalized[0].programs).toHaveLength(1);
    expect(normalized[0].programs[0]).toMatchObject({
      programIndex: 0,
      domainId: "MES2",
      programId: "MES2",
      programName: "MES2",
      support: "limited",
      classification: "not_estimable",
      score: null,
      sourceMemberCount: 0,
      mappedFeatureCount: 0,
      fittedFeatureCount: 0,
      admittedActiveFeatureCount: 0,
      activeFeatureCount: 0,
      observedCount: 0,
      leftCensoredCount: 0,
      admittedLeftCensoredCount: 0,
      coefficientMassCoverage: 0,
      uniqueActiveGeneCount: 0,
      uniqueCoefficientMass: 0,
      reconstructionImprovedFoldCount: 0,
      reconstructionEvaluableFoldCount: 0,
      overlapConfounded: false,
      contributions: [expect.objectContaining({
        geneSymbol: "EGFR",
        direction: "indeterminate",
      })],
      ablations: [expect.objectContaining({
        kind: "leave_program_out",
        support: "abstained",
        componentId: "unspecified-component",
        removedFeatureCount: 0,
      })],
      reasons: ["limited"],
      uncertainty: {
        state: "not_estimable",
        measurementStandardError: null,
        fittedModelStandardError: null,
        measurementModelCovariance: null,
        combinedStandardError: null,
        varianceClosureResidual: null,
        bootstrapReplicates: 0,
        reason: "",
      },
    });

    const whollySparseProgram = normalizeNeftelTransitions({
      transitions: [{
        programs: [{ support: "limited", program_id: "MES2" }],
      }],
    });
    expect(whollySparseProgram[0].programs[0]).toMatchObject({
      uncertainty: {
        state: "not_estimable",
        measurementStandardError: null,
        fittedModelStandardError: null,
        measurementModelCovariance: null,
        combinedStandardError: null,
        varianceClosureResidual: null,
        bootstrapReplicates: 0,
        reason: "",
      },
      ablations: [],
    });

    expect(normalizeNeftelEvaluation(null)).toBeNull();
    expect(normalizeNeftelEvaluation({})).toBeNull();
    expect(normalizeNeftelEvaluation({ evaluation: {
      patient_cluster_joint_vs_equal_median_gain_90_interval: ["bad", null],
    } })).toMatchObject({
      protocol: "not reported",
      validationScope: "not reported",
      interpretation: "not reported",
      patientCount: 0,
      evaluationCount: 0,
      patientClusterJointVsEqualInterval: [null, null],
      patientClusterBootstrapReplicates: 0,
      allPrimaryFitsConverged: false,
      allLeaveProgramIntervalsCrossZero: false,
      releaseGate: "not reported",
      individuallySupportedProgramCount: 0,
      jointVsGlobalIntervalSupportsPositiveGain: false,
      jointVsEqualIntervalSupportsPositiveGain: false,
    });
  });
});
