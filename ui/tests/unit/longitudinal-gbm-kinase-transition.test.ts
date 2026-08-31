import { describe, expect, it } from "vitest";

import lockedProfile from "../fixtures/longitudinal-gbm-kinase-transition-profile.json";
import {
  LONGITUDINAL_GBM_KINASE_TRANSITION_INVENTORY,
  LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST,
  LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
  kinaseTransitionProfileDigest,
  kinaseTransitionRequestDigest,
  kinaseTransitionRequestStats,
  kinaseTransitionResultDigest,
  kinaseTransitionValueDigest,
  normalizeKinaseTransitions,
  validateKinaseTransitionProfile,
  validateKinaseTransitionProfileHeaders,
  validateKinaseTransitionRequest,
  validateKinaseTransitionResultHeaders,
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
      top_family_drivers: [],
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

describe("longitudinal GBM kinase-transition trust boundary", () => {
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
