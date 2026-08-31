import { describe, expect, it } from "vitest";

import lockedProfile from "../fixtures/longitudinal-gbm-kinase-transition-profile.json";
import {
  LONGITUDINAL_GBM_KINASE_TRANSITION_INVENTORY,
  LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST,
  LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
  kinaseTransitionEstimatedCount,
  kinaseTransitionProfileDigest,
  kinaseTransitionRequestDigest,
  kinaseTransitionRequestStats,
  kinaseTransitionResultDigest,
  kinaseTransitionSignatureCount,
  kinaseTransitionValueDigest,
  normalizeKinaseTransitions,
  validateKinaseTransitionDemo,
  validateKinaseTransitionProfile,
  validateKinaseTransitionProfileHeaders,
  validateKinaseTransitionRequest,
  validateKinaseTransitionResult,
  validateKinaseTransitionResultHeaders,
  validateKinaseTransitionResultProfileBinding,
  validateKinaseTransitionResultRequestBinding,
  validateKinaseTransitionVerification,
  validateKinaseTransitionVerificationHeaders,
} from "../../src/lib/longitudinal-gbm-kinase-transition";
import type { JsonObject } from "../../src/lib/research-state";

const shaA = `sha256:${"a".repeat(64)}`;
const shaB = `sha256:${"b".repeat(64)}`;

function document(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

function headers(values: Record<string, string>): Pick<Headers, "get"> {
  const normalized = new Map(Object.entries(values).map(([key, value]) => [key.toLowerCase(), value]));
  return { get: (name: string) => normalized.get(name.toLowerCase()) ?? null };
}

function request(): JsonObject {
  const profile = document(lockedProfile);
  return {
    profile_id: LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
    series_id: "audit.kinase.series",
    assay_compatibility: profile.required_assay_compatibility,
    normalization_reference: {
      reference_id: "audit.reference",
      binding_digest: shaA,
      normalization_method: "caller supplied stable reference",
    },
    time_points: [0, 30].map((offset, index) => ({
      time_point_id: `audit.point.${index}`,
      time_offset_days: offset,
      normalization_reference_digest: shaA,
      observations: [{
        observation_id: `audit.observation.${index}`,
        phosphosite_id: "ENSP00000000001.1:s10",
        gene_symbol: "BRAF",
        state: "observed",
        log_abundance_ratio: index === 0 ? 0.1 : 0.4,
        standard_error: 0.1,
        quality_weight: 1,
        provenance_digest: index === 0 ? shaA : shaB,
      }],
    })),
    bootstrap_replicates: 64,
  };
}

function uncertainty(estimated: boolean): JsonObject {
  return estimated ? {
    state: "estimated",
    lower_bound: 0.1,
    upper_bound: 0.3,
    standard_error: 0.05,
    bootstrap_replicates_used: 64,
    reason: null,
  } : {
    state: "not_estimable",
    lower_bound: null,
    upper_bound: null,
    standard_error: null,
    bootstrap_replicates_used: 0,
    reason: "not selected",
  };
}

function driver(label = "BRAF:S10", contribution = 0.2): JsonObject {
  return {
    source_site_label: label,
    source_phosphosite_ids: [`ENSP00000000001.1:${label.toLowerCase().replace(":", "-")}`],
    stratum: "S/T",
    contains_composite_source_group: false,
    standardized_rank: 0.5,
    inverse_multiplicity: 1,
    adjusted_source_weight: 0.75,
    signed_contribution: contribution,
    paired_source_support: 88,
    paired_observation_ids: ["audit.observation.0", "audit.observation.1"],
    observation_provenance_digests: [shaA, shaB],
  };
}

function transition(): JsonObject {
  const kinases = LONGITUDINAL_GBM_KINASE_TRANSITION_INVENTORY.map((item) => {
    const [kinase, subtype, selectionState, sourceDirection] = item;
    const selected = selectionState !== "not_selected";
    return {
      kinase,
      subtype,
      selection_state: selectionState,
      support: selected ? "limited" : "abstained",
      source_direction: sourceDirection,
      source_enrichment: selected ? 1.2 : null,
      source_p_value: selected ? 0.01 : 0.2,
      source_q_value: selected ? 0.05 : 0.2,
      mapped_source_family_count: 12,
      observed_family_count: selected ? 10 : 0,
      source_weight_coverage: selected ? 0.8 : 0,
      outer_selection_frequency: selectionState === "selected_unstable" ? 0.6 : selected ? 0.9 : 0.1,
      bootstrap_selection_frequency: selectionState === "selected_unstable" ? 0.546875 : selected ? 0.9 : 0.1,
      bootstrap_direction_consistency: selected ? 0.9 : null,
      score: selected ? 0.2 : null,
      classification: selected ? "source_recurrence_aligned" : "not_estimable",
      uncertainty: uncertainty(selected),
      top_family_drivers: kinase === "BRAF"
        ? [driver("BRAF:S10", 0.2), driver("BRAF:S20", -0.1)]
        : [],
      reasons: [selected ? "same-assay evidence limits support" : "not selected"],
    };
  });
  const subtypes = (["GPM", "MTC", "NEU", "PPR"] as const).map((subtype) => {
    const selected = subtype === "NEU" ? 7 : subtype === "PPR" ? 5 : 0;
    return {
      subtype,
      selected_kinase_count: selected,
      estimable_kinase_count: selected,
      support: selected ? "limited" : "abstained",
      score: selected ? 0.2 : null,
      classification: selected ? "source_recurrence_aligned" : "not_estimable",
      uncertainty: uncertainty(selected > 0),
      reasons: [selected ? "same-assay evidence limits support" : "no selected kinase"],
    };
  });
  return {
    transition_id: "audit.transition.0",
    transition_index: 0,
    from_time_point_id: "audit.point.0",
    to_time_point_id: "audit.point.1",
    support: "limited",
    classification: "source_recurrence_aligned",
    score: 0.2,
    uncertainty: uncertainty(true),
    exact_source_row_count: 20,
    exact_family_count: 20,
    censored_family_count: 0,
    selected_kinase_count: 12,
    estimable_kinase_count: 12,
    kinase_signatures: kinases,
    subtype_signatures: subtypes,
    ablations: [
      "equal_kinase_instead_of_equal_subtype",
      "omit_composite_source_groups",
      "omit_inverse_multiplicity_correction",
    ].map((ablation) => ({
      ablation,
      support: "limited",
      score: 0.2,
      score_delta: 0,
      classification: "source_recurrence_aligned",
      reason: "sensitivity receipt",
    })),
    reasons: ["same-assay evidence limits support"],
  };
}

function result(submitted = request()): JsonObject {
  const profile = document(lockedProfile);
  const profileDigests = profile.digests as JsonObject;
  const normalizationReference = {
    ...(submitted.normalization_reference as JsonObject),
    abundance_scale: "caller_supplied_log2_phosphosite_abundance_ratio",
    invariant_across_time_points: true,
  };
  const value: JsonObject = {
    algorithm_id: "kncc-gbm-longitudinal-kinase-transition",
    algorithm_version: "1.0.0",
    profile_id: LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
    profile_digest: profile.profile_digest,
    request_digest: kinaseTransitionRequestDigest(submitted),
    result_digest: shaA,
    series_id: submitted.series_id,
    assay_compatibility: submitted.assay_compatibility,
    normalization_reference: normalizationReference,
    time_point_ids: ["audit.point.0", "audit.point.1"],
    transitions: [transition()],
    provenance: {
      engine: LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
      request_digest: kinaseTransitionRequestDigest(submitted),
      profile_digest: profile.profile_digest,
      fitted_artifact_content_digest: profileDigests.fitted_artifact_content_digest,
      fitted_artifact_byte_digest: profileDigests.fitted_artifact_byte_digest,
      bootstrap_ensemble_digest: profileDigests.bootstrap_ensemble_digest,
      engine_semantic_digest: profileDigests.engine_semantic_digest,
      assay_compatibility_digest: kinaseTransitionValueDigest(
        submitted.assay_compatibility as JsonObject,
      ),
      normalization_reference_digest: shaA,
      computational_digest: shaA,
      numerical_seed_digest: shaB,
      observation_source_digests: [shaA, shaB],
      source_attestation_state: "verified_exact_snapshots",
      source_provenance: profile.source_provenance,
      numpy_version: "2.5.2",
    },
    output_semantics: "SPHINKS_signature_transition_concordance_only",
    limitations: ["Same-cohort signature concordance is not biochemical kinase activity."],
    research_use_only: true,
    non_prescriptive: true,
    infers_kinase_activity: false,
    infers_biochemical_activity: false,
    makes_causal_claim: false,
    independent_evidence: false,
  };
  value.result_digest = kinaseTransitionResultDigest(value);
  return value;
}

function reseal(value: JsonObject): JsonObject {
  value.result_digest = kinaseTransitionResultDigest(value);
  return value;
}

function firstTransition(value: JsonObject): JsonObject {
  return (value.transitions as JsonObject[])[0];
}

function firstKinase(value: JsonObject, index = 0): JsonObject {
  return (firstTransition(value).kinase_signatures as JsonObject[])[index];
}

function firstSubtype(value: JsonObject, index = 0): JsonObject {
  return (firstTransition(value).subtype_signatures as JsonObject[])[index];
}

function firstAblation(value: JsonObject, index = 0): JsonObject {
  return (firstTransition(value).ablations as JsonObject[])[index];
}

function firstDriver(value: JsonObject, index = 0): JsonObject {
  return (firstKinase(value).top_family_drivers as JsonObject[])[index];
}

describe("longitudinal GBM kinase-transition trust boundary", () => {
  it("admits a fully linked result, profile binding, and exact result inventory", () => {
    const submitted = request();
    const profile = document(lockedProfile);
    const analysis = result(submitted);

    expect(validateKinaseTransitionResult(analysis)).toEqual([]);
    expect(validateKinaseTransitionResultRequestBinding(analysis, submitted)).toEqual([]);
    expect(validateKinaseTransitionResultProfileBinding(analysis, profile)).toEqual([]);
    expect(validateKinaseTransitionResultHeaders(headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(analysis.request_digest),
      "X-GLIO-Result-Digest": String(analysis.result_digest),
    }), analysis, submitted, profile)).toEqual([]);

    const transitions = normalizeKinaseTransitions(analysis);
    expect(transitions).toHaveLength(1);
    expect(kinaseTransitionEstimatedCount(transitions)).toBe(12);
    expect(kinaseTransitionSignatureCount(transitions)).toBe(24);
    expect(transitions[0].kinases[0].drivers.map((item) => item.sourceSiteLabel)).toEqual([
      "BRAF:S10",
      "BRAF:S20",
    ]);
  });

  it("pins the backend profile digest and canonical JSON implementation", () => {
    const profile = document(lockedProfile);
    expect(kinaseTransitionValueDigest({})).toBe("sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
    expect(kinaseTransitionProfileDigest(profile)).toBe(LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST);
    expect(validateKinaseTransitionProfile(profile)).toEqual([]);
    expect(validateKinaseTransitionProfileHeaders(headers({
      "X-GLIO-Profile-Digest": LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST,
    }), profile)).toEqual([]);

    const forged = document(profile);
    (forged.constants as JsonObject).alignment_threshold = 0.5;
    expect(validateKinaseTransitionProfile(forged)).toEqual(expect.arrayContaining([
      "profile.constants must match the version-locked inference policy.",
      "profile.profile_digest must match canonical profile content.",
    ]));
    expect(validateKinaseTransitionProfileHeaders(headers({ "X-GLIO-Profile-Digest": shaA }), profile)).toContain(
      `X-GLIO-Profile-Digest response header must equal ${LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST}.`,
    );
  });

  it("validates and canonicalizes the standalone 16-point-compatible request", () => {
    const value = request();
    expect(validateKinaseTransitionRequest(value)).toEqual([]);
    expect(kinaseTransitionRequestStats(value)).toEqual({
      timePoints: 2,
      transitions: 1,
      observations: 2,
      active: 2,
      phosphosites: 1,
    });
    const reordered = document(value);
    const points = reordered.time_points as JsonObject[];
    (points[0].observations as JsonObject[]).reverse();
    expect(kinaseTransitionRequestDigest(reordered)).toBe(kinaseTransitionRequestDigest(value));
  });

  it("normalizes the exact 24-hypothesis family without turning it into activity", () => {
    const transitions = normalizeKinaseTransitions({
      time_point_ids: ["audit.point.0", "audit.point.1"],
      transitions: [transition()],
    });
    expect(transitions).toHaveLength(1);
    expect(transitions[0].kinases).toHaveLength(24);
    expect(transitions[0].kinases.find((item) => item.kinase === "CHEK2")).toMatchObject({
      selectionState: "selected_unstable",
      support: "limited",
      bootstrapSelectionFrequency: 0.546875,
    });
    expect(transitions[0].subtypes.map((item) => [item.subtype, item.selectedKinases])).toEqual([
      ["GPM", 0], ["MTC", 0], ["NEU", 7], ["PPR", 5],
    ]);
  });

  it("rejects forged result headers and a result bound to another request", () => {
    const submitted = request();
    const result: JsonObject = {
      series_id: submitted.series_id,
      profile_id: LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
      profile_digest: LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST,
      request_digest: kinaseTransitionRequestDigest(submitted),
      assay_compatibility: submitted.assay_compatibility,
      normalization_reference: {
        ...(submitted.normalization_reference as JsonObject),
        abundance_scale: "caller_supplied_log2_phosphosite_abundance_ratio",
        invariant_across_time_points: true,
      },
      time_point_ids: ["audit.point.0", "audit.point.1"],
      provenance: { observation_source_digests: [shaA, shaB] },
    };
    result.result_digest = kinaseTransitionResultDigest(result);
    expect(validateKinaseTransitionResultRequestBinding(result, submitted)).toEqual([]);
    const foreign = document(submitted);
    foreign.series_id = "audit.foreign.series";
    expect(validateKinaseTransitionResultRequestBinding(result, foreign)).toEqual(expect.arrayContaining([
      "result.request_digest must match the canonical submitted request.",
      "result.series_id must match the submitted request.",
    ]));
    expect(validateKinaseTransitionResultHeaders(headers({
      "X-GLIO-Profile-Digest": shaA,
      "X-GLIO-Request-Digest": shaA,
      "X-GLIO-Result-Digest": shaA,
    }), result, submitted, document(lockedProfile))).toHaveLength(3);
  });

  it("rejects false, malformed, and header-forged replay claims", () => {
    const profile = document(lockedProfile);
    const result: JsonObject = { request_digest: shaA, result_digest: shaB, profile_digest: profile.profile_digest };
    const valid: JsonObject = {
      verified: true,
      request_digest_match: true,
      profile_digest_match: true,
      result_digest_match: true,
      transition_semantic_match: true,
      semantic_match: true,
      recomputed_request_digest: shaA,
      recomputed_result_digest: shaB,
      message: "Replay exactly matches the deterministic signature-transition receipt.",
    };
    expect(validateKinaseTransitionVerification(valid, result, profile)).toEqual([]);

    const falseReplay = document(valid);
    for (const key of ["verified", "request_digest_match", "profile_digest_match", "result_digest_match", "transition_semantic_match", "semantic_match"]) falseReplay[key] = false;
    expect(validateKinaseTransitionVerification(falseReplay, result, profile)).toContain(
      "verification did not exactly verify the admitted receipt.",
    );
    const malformed = document(valid);
    malformed.transition_semantic_match = false;
    malformed.message = "";
    expect(validateKinaseTransitionVerification(malformed, result, profile)).toEqual(expect.arrayContaining([
      "verification.semantic_match must close transition semantics.",
      "verification.verified must close every digest and semantic check.",
      "verification did not exactly verify the admitted receipt.",
      "verification.message must be non-empty.",
    ]));
    expect(validateKinaseTransitionVerificationHeaders(headers({
      "X-GLIO-Profile-Digest": shaA,
      "X-GLIO-Request-Digest": shaA,
      "X-GLIO-Result-Digest": shaB,
    }), valid, profile)).toContain(
      `X-GLIO-Profile-Digest response header must equal ${LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST}.`,
    );
  });
});

describe("longitudinal GBM kinase-transition exhaustive profile and request admission", () => {
  it("covers Python-compatible float serialization and request defaulting branches", () => {
    const digests = [
      -0,
      0,
      1e-5,
      1e20,
      1.25e20,
      1.25,
      -1.25,
      1_000,
      Number.NaN,
      Number.POSITIVE_INFINITY,
    ].map((score) => kinaseTransitionResultDigest({ score }));
    expect(digests.every((value) => /^sha256:[0-9a-f]{64}$/.test(value))).toBe(true);
    expect(new Set(digests).size).toBeGreaterThan(7);

    const defaulted = request();
    delete defaulted.profile_id;
    delete defaulted.bootstrap_replicates;
    const reference = defaulted.normalization_reference as JsonObject;
    delete reference.abundance_scale;
    delete reference.invariant_across_time_points;
    const firstPoint = (defaulted.time_points as JsonObject[])[0];
    const firstObservation = (firstPoint.observations as JsonObject[])[0];
    delete firstObservation.log_abundance_ratio;
    delete firstObservation.standard_error;
    delete firstObservation.quality_weight;
    (firstPoint.observations as unknown[]).push(
      null,
      {
        ...firstObservation,
        observation_id: "audit.observation.sorted-last",
        phosphosite_id: "ZZZ:S2",
      },
      {
        ...firstObservation,
        observation_id: "audit.observation.sorted-first",
        phosphosite_id: "AAA:S1",
      },
    );
    expect(kinaseTransitionRequestDigest(defaulted)).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(kinaseTransitionRequestDigest({
      normalization_reference: "malformed",
      time_points: "malformed",
    })).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(kinaseTransitionRequestDigest({
      normalization_reference: null,
      time_points: [null, { observations: null }],
    })).toMatch(/^sha256:[0-9a-f]{64}$/);

    const optionalProfile = request();
    delete optionalProfile.profile_id;
    expect(validateKinaseTransitionRequest(optionalProfile)).toEqual([]);
    const foreignProfile = request();
    foreignProfile.profile_id = "latest";
    expect(validateKinaseTransitionRequest(foreignProfile)).toContain(
      `profile_id must equal ${LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID}.`,
    );
  });

  it("rejects every mutable profile envelope and nested policy family", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { delete value.algorithm_id; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.model_id = "foreign"; },
      (value) => { value.required_assay_compatibility = null; },
      (value) => { value.constants = null; },
      (value) => { (value.constants as JsonObject).extra = true; },
      (value) => { delete (value.constants as JsonObject).alignment_threshold; },
      (value) => { (value.constants as JsonObject).alignment_threshold = 0.5; },
      (value) => { value.counts = null; },
      (value) => { (value.counts as JsonObject).extra = true; },
      (value) => { delete (value.counts as JsonObject).strict_patient_pairs; },
      (value) => { (value.counts as JsonObject).strict_patient_pairs = 87; },
      (value) => { value.digests = null; },
      (value) => { (value.digests as JsonObject).extra = shaA; },
      (value) => { delete (value.digests as JsonObject).engine_semantic_digest; },
      (value) => { (value.digests as JsonObject).engine_semantic_digest = "bad"; },
      (value) => { value.quality_gates = null; },
      (value) => { (value.quality_gates as JsonObject).extra = false; },
      (value) => { delete (value.quality_gates as JsonObject).output_policy; },
      (value) => { (value.quality_gates as JsonObject).output_policy = "supported"; },
      (value) => { value.source_provenance = null; },
      (value) => { (value.source_provenance as JsonObject).extra = "foreign"; },
      (value) => { delete (value.source_provenance as JsonObject).pdc_article_attribution; },
      (value) => { (value.source_provenance as JsonObject).pdc_article_attribution = ""; },
      (value) => { (value.source_provenance as JsonObject).pdc_license = "unknown"; },
      (value) => { (value.source_provenance as JsonObject).sphinks_license = "unknown"; },
      (value) => { (value.source_provenance as JsonObject).pdc_license_url = "http://example.test"; },
      (value) => { (value.source_provenance as JsonObject).sphinks_license_url = null; },
      (value) => { value.numpy_version = "2.0.0"; },
      (value) => { value.demo_id = "foreign"; },
      (value) => { value.demo_request_digest = shaA; },
      (value) => { value.demo_semantic_oracle_digest = shaA; },
      (value) => { value.source_attestation_state = "unverified"; },
      (value) => { value.safety_class = "clinical"; },
      (value) => { value.claim_ceiling = "kinase_activity"; },
      (value) => { value.profile_digest = shaA; },
    ];
    for (const mutate of mutations) {
      const profile = document(lockedProfile);
      mutate(profile);
      expect(validateKinaseTransitionProfile(profile).length).toBeGreaterThan(0);
    }
  });

  it("fails closed for malformed digest headers and demo bindings", () => {
    const profile = document(lockedProfile);
    const malformedProfile = document(profile);
    malformedProfile.profile_digest = "bad";
    expect(validateKinaseTransitionProfileHeaders(headers({}), malformedProfile)).toContain(
      "X-GLIO-Profile-Digest cannot be bound to a malformed expected digest.",
    );

    expect(validateKinaseTransitionDemo(request(), headers({}), profile)).toEqual(
      expect.arrayContaining([
        "demo request does not match the pinned demo digest.",
        "demo request digest must match the admitted profile.",
      ]),
    );
    const requestDigest = kinaseTransitionRequestDigest(request());
    expect(validateKinaseTransitionDemo(request(), headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": requestDigest,
    }), profile)).not.toEqual(expect.arrayContaining([
      expect.stringContaining("response header"),
    ]));
  });
});

describe("longitudinal GBM kinase-transition exhaustive result admission", () => {
  it("rejects malformed result envelopes, provenance, safety claims, and source receipts", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { delete value.algorithm_id; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.profile_digest = "bad"; },
      (value) => { value.request_digest = "bad"; },
      (value) => { value.result_digest = "bad"; },
      (value) => { value.series_id = ""; },
      (value) => { value.assay_compatibility = null; },
      (value) => { value.normalization_reference = null; },
      (value) => { value.time_point_ids = null; },
      (value) => { value.time_point_ids = ["only-one"]; },
      (value) => { value.time_point_ids = Array.from({ length: 17 }, (_, index) => `point.${index}`); },
      (value) => { value.time_point_ids = ["duplicate", "duplicate"]; },
      (value) => { value.transitions = null; },
      (value) => { value.transitions = []; },
      (value) => { value.provenance = null; },
      (value) => { (value.provenance as JsonObject).extra = true; },
      (value) => { delete (value.provenance as JsonObject).engine; },
      (value) => { (value.provenance as JsonObject).engine = "foreign"; },
      (value) => { (value.provenance as JsonObject).request_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).profile_digest = shaA; },
      (value) => { (value.provenance as JsonObject).computational_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).assay_compatibility_digest = shaA; },
      (value) => { (value.provenance as JsonObject).normalization_reference_digest = shaB; },
      (value) => { (value.provenance as JsonObject).observation_source_digests = null; },
      (value) => { (value.provenance as JsonObject).observation_source_digests = []; },
      (value) => { (value.provenance as JsonObject).observation_source_digests = ["bad"]; },
      (value) => { (value.provenance as JsonObject).observation_source_digests = [shaA, shaA]; },
      (value) => { (value.provenance as JsonObject).observation_source_digests = [shaB, shaA]; },
      (value) => { (value.provenance as JsonObject).source_attestation_state = "unverified"; },
      (value) => { (value.provenance as JsonObject).source_provenance = null; },
      (value) => { (value.provenance as JsonObject).numpy_version = "2.0.0"; },
      (value) => { value.output_semantics = "kinase_activity"; },
      (value) => { value.limitations = null; },
      (value) => { value.limitations = []; },
      (value) => { value.limitations = Array.from({ length: 17 }, () => "limit"); },
      (value) => { value.limitations = [""]; },
      (value) => { value.research_use_only = false; },
      (value) => { value.non_prescriptive = false; },
      (value) => { value.infers_kinase_activity = true; },
      (value) => { value.infers_biochemical_activity = true; },
      (value) => { value.makes_causal_claim = true; },
      (value) => { value.independent_evidence = true; },
    ];
    for (const mutate of mutations) {
      const value = result();
      mutate(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }
  });

  it("enforces transition topology, bounds, exact inventory lengths, and interval semantics", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { (value.transitions as unknown[])[0] = null; },
      (value) => { firstTransition(value).extra = true; },
      (value) => { delete firstTransition(value).transition_id; },
      (value) => { firstTransition(value).transition_id = ""; },
      (value) => { firstTransition(value).transition_index = 1; },
      (value) => { firstTransition(value).from_time_point_id = "foreign"; },
      (value) => { firstTransition(value).to_time_point_id = "foreign"; },
      (value) => { firstTransition(value).support = "supported"; },
      (value) => { firstTransition(value).classification = "activated"; },
      (value) => { firstTransition(value).score = Number.NaN; },
      (value) => { firstTransition(value).uncertainty = null; },
      (value) => { firstTransition(value).selected_kinase_count = 11; },
      (value) => { firstTransition(value).estimable_kinase_count = 11; },
      (value) => { firstTransition(value).reasons = null; },
      (value) => { firstTransition(value).reasons = [""]; },
      (value) => { firstTransition(value).reasons = Array.from({ length: 13 }, () => "limit"); },
      (value) => { firstTransition(value).reasons = []; },
      (value) => { firstTransition(value).kinase_signatures = null; },
      (value) => { (firstTransition(value).kinase_signatures as unknown[]).pop(); },
      (value) => { (firstTransition(value).kinase_signatures as unknown[]).push(null); },
      (value) => { firstTransition(value).subtype_signatures = null; },
      (value) => { (firstTransition(value).subtype_signatures as unknown[]).pop(); },
      (value) => { (firstTransition(value).subtype_signatures as unknown[]).push(null); },
      (value) => { firstTransition(value).ablations = null; },
      (value) => { (firstTransition(value).ablations as unknown[]).pop(); },
      (value) => { (firstTransition(value).ablations as unknown[]).push(null); },
      (value) => { firstSubtype(value, 2).estimable_kinase_count = 6; },
      (value) => { firstTransition(value).classification = "stable"; },
    ];
    for (const mutate of mutations) {
      const value = result();
      mutate(value);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }

    for (const [field, maximum] of [
      ["exact_source_row_count", 4_096],
      ["exact_family_count", 2_457],
      ["censored_family_count", 2_457],
      ["selected_kinase_count", 24],
      ["estimable_kinase_count", 24],
    ] as const) {
      for (const invalid of [-1, 0.5, maximum + 1]) {
        const value = result();
        firstTransition(value)[field] = invalid;
        reseal(value);
        expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
      }
    }

    for (const [score, lower, upper, classification] of [
      [0.2, 0.1, 0.3, "source_recurrence_aligned"],
      [-0.2, -0.3, -0.1, "reverse_aligned"],
      [0, -0.05, 0.05, "stable"],
      [0, -0.1, 0.1, "indeterminate"],
    ] as const) {
      const value = result();
      Object.assign(firstTransition(value), { score, classification });
      Object.assign(firstTransition(value).uncertainty as JsonObject, {
        lower_bound: lower,
        upper_bound: upper,
      });
      reseal(value);
      expect(validateKinaseTransitionResult(value)).toEqual([]);
    }

    const abstained = result();
    Object.assign(firstTransition(abstained), {
      support: "abstained",
      score: null,
      classification: "not_estimable",
      uncertainty: uncertainty(false),
      reasons: ["transition interval is not estimable"],
    });
    reseal(abstained);
    expect(validateKinaseTransitionResult(abstained)).toEqual([]);
  });

  it("rejects every malformed estimated and not-estimable uncertainty receipt", () => {
    const estimatedMutations: Array<(value: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { delete value.state; },
      (value) => { value.lower_bound = null; },
      (value) => { value.upper_bound = null; },
      (value) => { value.lower_bound = 2; value.upper_bound = 1; },
      (value) => { value.standard_error = null; },
      (value) => { value.standard_error = -1; },
      (value) => { value.bootstrap_replicates_used = 31; },
      (value) => { value.bootstrap_replicates_used = 65; },
      (value) => { value.bootstrap_replicates_used = 32.5; },
      (value) => { value.reason = "unexpected"; },
    ];
    for (const mutate of estimatedMutations) {
      const value = result();
      mutate(firstTransition(value).uncertainty as JsonObject);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }

    const notEstimableMutations: Array<(value: JsonObject) => void> = [
      (value) => { value.state = "unknown"; },
      (value) => { value.lower_bound = 0; },
      (value) => { value.upper_bound = 0; },
      (value) => { value.standard_error = 0; },
      (value) => { value.bootstrap_replicates_used = 1; },
      (value) => { value.reason = null; },
      (value) => { value.reason = ""; },
    ];
    for (const mutate of notEstimableMutations) {
      const value = result();
      mutate(firstKinase(value, 3).uncertainty as JsonObject);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }
  });
});

describe("longitudinal GBM kinase-transition nested scientific receipt admission", () => {
  it("rejects malformed kinase identities, probabilities, selection gates, and support closure", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { (firstTransition(value).kinase_signatures as unknown[])[0] = null; },
      (value) => { firstKinase(value).extra = true; },
      (value) => { delete firstKinase(value).kinase; },
      (value) => { firstKinase(value).kinase = "EGFR"; },
      (value) => { firstKinase(value).subtype = "GPM"; },
      (value) => { firstKinase(value).selection_state = "not_selected"; },
      (value) => { firstKinase(value).source_direction = "reverse_aligned"; },
      (value) => { firstKinase(value).support = "supported"; },
      (value) => { firstKinase(value).selection_state = "unknown"; },
      (value) => { firstKinase(value).source_direction = "unknown"; },
      (value) => { firstKinase(value).classification = "activated"; },
      (value) => { firstKinase(value).source_enrichment = Number.NaN; },
      (value) => { firstKinase(value).bootstrap_direction_consistency = 2; },
      (value) => { firstKinase(value).mapped_source_family_count = -1; },
      (value) => { firstKinase(value).mapped_source_family_count = 573; },
      (value) => { firstKinase(value).mapped_source_family_count = 0.5; },
      (value) => { firstKinase(value).observed_family_count = -1; },
      (value) => { firstKinase(value).observed_family_count = 573; },
      (value) => { firstKinase(value).score = Number.NaN; },
      (value) => { firstKinase(value).uncertainty = null; },
      (value) => { firstKinase(value).reasons = null; },
      (value) => { firstKinase(value).reasons = [""]; },
      (value) => { firstKinase(value).reasons = Array.from({ length: 9 }, () => "limit"); },
      (value) => { firstKinase(value).reasons = []; },
      (value) => { firstKinase(value).support = "abstained"; },
      (value) => { firstKinase(value, 3).support = "limited"; },
      (value) => { firstKinase(value).bootstrap_selection_frequency = 0.79; },
      (value) => { firstKinase(value, 4).bootstrap_selection_frequency = 0.8; },
      (value) => { firstKinase(value).source_q_value = 0.11; },
      (value) => { firstKinase(value, 3).source_q_value = 0.1; },
    ];
    for (const field of [
      "source_p_value",
      "source_q_value",
      "source_weight_coverage",
      "outer_selection_frequency",
      "bootstrap_selection_frequency",
    ] as const) {
      mutations.push(
        (value) => { firstKinase(value)[field] = -0.01; },
        (value) => { firstKinase(value)[field] = 1.01; },
        (value) => { firstKinase(value)[field] = null; },
      );
    }
    for (const mutate of mutations) {
      const value = result();
      mutate(value);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }

    const nullable = result();
    firstKinase(nullable).source_enrichment = null;
    firstKinase(nullable).bootstrap_direction_consistency = null;
    reseal(nullable);
    expect(validateKinaseTransitionResult(nullable)).toEqual([]);

    const reversed = result();
    const signatures = firstTransition(reversed).kinase_signatures as unknown[];
    [signatures[0], signatures[1]] = [signatures[1], signatures[0]];
    reseal(reversed);
    expect(validateKinaseTransitionResult(reversed).length).toBeGreaterThan(0);

    for (const [score, lower, upper, classification] of [
      [0.2, 0.1, 0.3, "source_recurrence_aligned"],
      [-0.2, -0.3, -0.1, "reverse_aligned"],
      [0, -0.05, 0.05, "stable"],
      [0, -0.1, 0.1, "indeterminate"],
    ] as const) {
      const value = result();
      Object.assign(firstKinase(value), { score, classification });
      Object.assign(firstKinase(value).uncertainty as JsonObject, {
        lower_bound: lower,
        upper_bound: upper,
      });
      reseal(value);
      expect(validateKinaseTransitionResult(value)).toEqual([]);
    }
  });

  it("rejects malformed source-family drivers and enforces deterministic driver ordering", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { firstKinase(value).top_family_drivers = null; },
      (value) => { firstKinase(value).top_family_drivers = Array.from({ length: 9 }, () => null); },
      (value) => { (firstKinase(value).top_family_drivers as unknown[])[0] = null; },
      (value) => { firstDriver(value).extra = true; },
      (value) => { delete firstDriver(value).source_site_label; },
      (value) => { firstDriver(value).source_site_label = ""; },
      (value) => { firstDriver(value).source_phosphosite_ids = null; },
      (value) => { firstDriver(value).source_phosphosite_ids = []; },
      (value) => { firstDriver(value).source_phosphosite_ids = Array.from({ length: 17 }, (_, index) => `site.${index}`); },
      (value) => { firstDriver(value).source_phosphosite_ids = ["duplicate", "duplicate"]; },
      (value) => { firstDriver(value).source_phosphosite_ids = [""]; },
      (value) => { firstDriver(value).stratum = ""; },
      (value) => { firstDriver(value).contains_composite_source_group = null; },
      (value) => { firstDriver(value).standardized_rank = null; },
      (value) => { firstDriver(value).standardized_rank = -1.01; },
      (value) => { firstDriver(value).standardized_rank = 1.01; },
      (value) => { firstDriver(value).inverse_multiplicity = null; },
      (value) => { firstDriver(value).inverse_multiplicity = 0; },
      (value) => { firstDriver(value).inverse_multiplicity = 1.01; },
      (value) => { firstDriver(value).adjusted_source_weight = null; },
      (value) => { firstDriver(value).adjusted_source_weight = 0; },
      (value) => { firstDriver(value).signed_contribution = null; },
      (value) => { firstDriver(value).paired_source_support = 52; },
      (value) => { firstDriver(value).paired_source_support = 89; },
      (value) => { firstDriver(value).paired_source_support = 53.5; },
      (value) => { firstDriver(value).paired_observation_ids = null; },
      (value) => { firstDriver(value).paired_observation_ids = ["only-one"]; },
      (value) => { firstDriver(value).paired_observation_ids = Array.from({ length: 33 }, (_, index) => `observation.${index}`); },
      (value) => { firstDriver(value).paired_observation_ids = ["", "valid"]; },
      (value) => { firstDriver(value).observation_provenance_digests = null; },
      (value) => { firstDriver(value).observation_provenance_digests = [shaA]; },
      (value) => { firstDriver(value).observation_provenance_digests = Array.from({ length: 33 }, () => shaA); },
      (value) => { firstDriver(value).observation_provenance_digests = [shaA, "bad"]; },
      (value) => { (firstKinase(value).top_family_drivers as unknown[]).reverse(); },
    ];
    for (const mutate of mutations) {
      const value = result();
      mutate(value);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }
  });

  it("rejects malformed subtype summaries and closes estimated subtype intervals", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { (firstTransition(value).subtype_signatures as unknown[])[0] = null; },
      (value) => { firstSubtype(value).extra = true; },
      (value) => { delete firstSubtype(value).subtype; },
      (value) => { firstSubtype(value).subtype = "NEU"; },
      (value) => { firstSubtype(value).selected_kinase_count = 1; },
      (value) => { firstSubtype(value, 2).estimable_kinase_count = -1; },
      (value) => { firstSubtype(value, 2).estimable_kinase_count = 8; },
      (value) => { firstSubtype(value, 2).estimable_kinase_count = 0.5; },
      (value) => { firstSubtype(value, 2).support = "supported"; },
      (value) => { firstSubtype(value, 2).classification = "activated"; },
      (value) => { firstSubtype(value, 2).score = Number.NaN; },
      (value) => { firstSubtype(value, 2).uncertainty = null; },
      (value) => { firstSubtype(value, 2).reasons = null; },
      (value) => { firstSubtype(value, 2).reasons = [""]; },
      (value) => { firstSubtype(value, 2).reasons = Array.from({ length: 9 }, () => "limit"); },
      (value) => { firstSubtype(value, 2).reasons = []; },
      (value) => { firstSubtype(value).support = "limited"; },
      (value) => { firstSubtype(value, 2).support = "abstained"; },
      (value) => { firstSubtype(value, 2).classification = "stable"; },
    ];
    for (const mutate of mutations) {
      const value = result();
      mutate(value);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }

    for (const [score, lower, upper, classification] of [
      [0.2, 0.1, 0.3, "source_recurrence_aligned"],
      [-0.2, -0.3, -0.1, "reverse_aligned"],
      [0, -0.05, 0.05, "stable"],
      [0, -0.1, 0.1, "indeterminate"],
    ] as const) {
      const value = result();
      Object.assign(firstSubtype(value, 2), { score, classification });
      Object.assign(firstSubtype(value, 2).uncertainty as JsonObject, {
        lower_bound: lower,
        upper_bound: upper,
      });
      reseal(value);
      expect(validateKinaseTransitionResult(value)).toEqual([]);
    }
  });

  it("rejects malformed ablations and closes every point-classification branch", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { (firstTransition(value).ablations as unknown[])[0] = null; },
      (value) => { firstAblation(value).extra = true; },
      (value) => { delete firstAblation(value).ablation; },
      (value) => { firstAblation(value).ablation = "foreign"; },
      (value) => { firstAblation(value).support = "supported"; },
      (value) => { firstAblation(value).score = Number.NaN; },
      (value) => { firstAblation(value).score_delta = Number.NaN; },
      (value) => { firstAblation(value).classification = "activated"; },
      (value) => { firstAblation(value).reason = ""; },
      (value) => { firstAblation(value).score = null; },
      (value) => { firstAblation(value).score_delta = null; },
      (value) => { firstAblation(value).classification = "stable"; },
      (value) => { firstAblation(value).support = "abstained"; },
    ];
    for (const mutate of mutations) {
      const value = result();
      mutate(value);
      reseal(value);
      expect(validateKinaseTransitionResult(value).length).toBeGreaterThan(0);
    }

    for (const [score, classification] of [
      [0.2, "source_recurrence_aligned"],
      [-0.2, "reverse_aligned"],
      [0, "stable"],
    ] as const) {
      const value = result();
      Object.assign(firstAblation(value), { score, classification });
      reseal(value);
      expect(validateKinaseTransitionResult(value)).toEqual([]);
    }

    const abstained = result();
    Object.assign(firstAblation(abstained), {
      support: "abstained",
      score: null,
      score_delta: null,
      classification: "not_estimable",
      reason: "ablation is not estimable",
    });
    reseal(abstained);
    expect(validateKinaseTransitionResult(abstained)).toEqual([]);
  });
});

describe("longitudinal GBM kinase-transition binding, replay, and fail-closed normalization", () => {
  it("rejects every foreign request and exact evidence-provenance mismatch", () => {
    const analysis = result();
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { value.series_id = "foreign"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.assay_compatibility = null; },
      (value) => { value.normalization_reference = null; },
      (value) => { value.time_points = null; },
      (value) => { (value.time_points as unknown[])[0] = null; },
      (value) => { delete ((value.time_points as JsonObject[])[0]).time_point_id; },
      (value) => { ((value.time_points as JsonObject[])[0]).time_point_id = "foreign"; },
      (value) => {
        const points = value.time_points as JsonObject[];
        (points[0].observations as JsonObject[])[0].provenance_digest = "bad";
      },
    ];
    for (const mutate of mutations) {
      const submitted = request();
      mutate(submitted);
      expect(validateKinaseTransitionResultRequestBinding(analysis, submitted).length).toBeGreaterThan(0);
    }

    const profileDefault = request();
    delete profileDefault.profile_id;
    expect(validateKinaseTransitionResultRequestBinding(analysis, profileDefault)).toEqual([]);

    const noProvenance = result();
    noProvenance.provenance = null;
    expect(validateKinaseTransitionResultRequestBinding(noProvenance, request())).toEqual([]);

    const malformedEvidenceRequest = request();
    malformedEvidenceRequest.time_points = [
      null,
      {
        time_point_id: "audit.point.1",
        observations: [null, { provenance_digest: "bad" }, { provenance_digest: shaA }],
      },
    ];
    expect(validateKinaseTransitionResultRequestBinding(analysis, malformedEvidenceRequest)).toContain(
      "result.provenance.observation_source_digests must exactly bind submitted evidence provenance.",
    );
  });

  it("rejects every profile/result artifact binding mismatch", () => {
    const profile = document(lockedProfile);
    const mutations: Array<(analysis: JsonObject, admitted: JsonObject) => void> = [
      (analysis) => { analysis.profile_digest = shaA; },
      (analysis) => { analysis.assay_compatibility = null; },
      (analysis) => { (analysis.provenance as JsonObject).fitted_artifact_content_digest = shaA; },
      (analysis) => { (analysis.provenance as JsonObject).fitted_artifact_byte_digest = shaA; },
      (analysis) => { (analysis.provenance as JsonObject).bootstrap_ensemble_digest = shaA; },
      (analysis) => { (analysis.provenance as JsonObject).engine_semantic_digest = shaA; },
      (analysis) => { (analysis.provenance as JsonObject).source_provenance = null; },
      (_analysis, admitted) => { admitted.digests = null; },
    ];
    for (const mutate of mutations) {
      const analysis = result();
      const admitted = document(profile);
      mutate(analysis, admitted);
      expect(validateKinaseTransitionResultProfileBinding(analysis, admitted).length).toBeGreaterThan(0);
    }

    const noProvenance = result();
    noProvenance.provenance = null;
    expect(validateKinaseTransitionResultProfileBinding(noProvenance, profile)).toEqual([]);
  });

  it("requires replay verification to close every Boolean, digest, semantic, and header check", () => {
    const profile = document(lockedProfile);
    const analysis = result();
    const valid: JsonObject = {
      verified: true,
      request_digest_match: true,
      profile_digest_match: true,
      result_digest_match: true,
      transition_semantic_match: true,
      semantic_match: true,
      recomputed_request_digest: analysis.request_digest,
      recomputed_result_digest: analysis.result_digest,
      message: "Replay exactly matches the deterministic transition receipt.",
    };
    expect(validateKinaseTransitionVerification(valid, analysis, profile)).toEqual([]);
    expect(validateKinaseTransitionVerificationHeaders(headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(valid.recomputed_request_digest),
      "X-GLIO-Result-Digest": String(valid.recomputed_result_digest),
    }), valid, profile)).toEqual([]);

    const mutations: Array<(verification: JsonObject, resultValue: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { delete value.message; },
      (value) => { value.verified = "true"; },
      (value) => { value.request_digest_match = "true"; },
      (value) => { value.profile_digest_match = "true"; },
      (value) => { value.result_digest_match = "true"; },
      (value) => { value.transition_semantic_match = "true"; },
      (value) => { value.semantic_match = "true"; },
      (value) => { value.transition_semantic_match = false; },
      (value) => { value.semantic_match = false; },
      (value) => { value.verified = false; },
      (value) => { value.request_digest_match = false; value.verified = false; },
      (value) => { value.profile_digest_match = false; value.verified = false; },
      (value) => { value.result_digest_match = false; value.verified = false; },
      (value) => { value.recomputed_request_digest = "bad"; },
      (value) => { value.recomputed_result_digest = "bad"; },
      (value) => { value.recomputed_request_digest = shaA; },
      (value) => { value.recomputed_result_digest = shaA; },
      (value, resultValue) => { resultValue.profile_digest = shaA; },
      (value) => { value.message = ""; },
    ];
    for (const mutate of mutations) {
      const verification = document(valid);
      const resultValue = document(analysis);
      mutate(verification, resultValue);
      expect(validateKinaseTransitionVerification(verification, resultValue, profile).length).toBeGreaterThan(0);
    }

    expect(validateKinaseTransitionVerificationHeaders(headers({}), valid, profile)).toHaveLength(3);
    const malformed = document(valid);
    malformed.recomputed_request_digest = "bad";
    malformed.recomputed_result_digest = "bad";
    const malformedProfile = document(profile);
    malformedProfile.profile_digest = "bad";
    expect(validateKinaseTransitionVerificationHeaders(headers({}), malformed, malformedProfile)).toEqual([
      "X-GLIO-Profile-Digest cannot be bound to a malformed expected digest.",
      "X-GLIO-Request-Digest cannot be bound to a malformed expected digest.",
      "X-GLIO-Result-Digest cannot be bound to a malformed expected digest.",
    ]);
  });

  it("returns no transition for malformed topology and conservative defaults for invalid scalars", () => {
    expect(normalizeKinaseTransitions({ time_point_ids: null, transitions: [] })).toEqual([]);
    expect(normalizeKinaseTransitions({
      time_point_ids: ["audit.point.0", "audit.point.1"],
      transitions: [null],
    })).toEqual([]);

    const sparse = result();
    firstTransition(sparse).score = null;
    firstTransition(sparse).exact_source_row_count = null;
    firstTransition(sparse).exact_family_count = null;
    firstTransition(sparse).censored_family_count = null;
    firstTransition(sparse).selected_kinase_count = null;
    firstTransition(sparse).estimable_kinase_count = null;
    firstKinase(sparse).source_enrichment = null;
    firstKinase(sparse).source_p_value = null;
    firstKinase(sparse).source_q_value = null;
    firstKinase(sparse).mapped_source_family_count = null;
    firstKinase(sparse).observed_family_count = null;
    firstKinase(sparse).source_weight_coverage = null;
    firstKinase(sparse).outer_selection_frequency = null;
    firstKinase(sparse).bootstrap_selection_frequency = null;
    firstKinase(sparse).bootstrap_direction_consistency = null;
    firstKinase(sparse).score = null;
    firstSubtype(sparse).selected_kinase_count = null;
    firstSubtype(sparse).estimable_kinase_count = null;
    firstAblation(sparse).reason = null;
    const normalized = normalizeKinaseTransitions(sparse);
    expect(normalized).toHaveLength(1);
    expect(normalized[0]).toMatchObject({
      score: null,
      exactSourceRows: 0,
      exactFamilies: 0,
      censoredFamilies: 0,
      selectedKinases: 0,
      estimableKinases: 0,
    });
    expect(normalized[0].kinases[0]).toMatchObject({
      sourceEnrichment: null,
      sourcePValue: null,
      sourceQValue: null,
      mappedSourceFamilies: 0,
      observedFamilies: 0,
      sourceWeightCoverage: null,
      outerSelectionFrequency: null,
      bootstrapSelectionFrequency: null,
      bootstrapDirectionConsistency: null,
      score: null,
    });
    expect(normalized[0].subtypes[0]).toMatchObject({
      selectedKinases: 0,
      estimableKinases: 0,
    });
    expect(normalized[0].ablations[0].reason).toBe("");
  });
});
