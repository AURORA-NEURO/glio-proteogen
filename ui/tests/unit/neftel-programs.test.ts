import { describe, expect, it } from "vitest";

import { NEFTEL_PROFILE_ID, neftelRequestStats, normalizeNeftelPrograms, validateNeftelRequest } from "../../src/lib/neftel-programs";
import type { JsonObject } from "../../src/lib/research-state";

const digest = `sha256:${"a".repeat(64)}`;
const valid: JsonObject = {
  profile_id: NEFTEL_PROFILE_ID,
  sample_id: "synthetic.neftel",
  observations: [
    { observation_id: "obs.one", gene_symbol: "EGFR", state: "observed", standardized_effect: 1.1, standard_error: 0.3, provenance_digest: digest },
    { observation_id: "obs.two", gene_symbol: "PTEN", state: "left_censored", standardized_effect: -0.4, standard_error: 0.4, quality_weight: 0.8, provenance_digest: digest },
    { observation_id: "obs.three", gene_symbol: "NF1", state: "missing", quality_weight: 0, provenance_digest: digest },
    { observation_id: "obs.four", gene_symbol: "PDGFRA", state: "unsupported", quality_weight: 0, provenance_digest: digest },
  ],
  bootstrap_replicates: 16,
  permutation_replicates: 64,
  background_mode: "request_observed_proteome",
  effect_scale: "standardized_log2_abundance_contrast",
  effect_reference_id: "synthetic.reference.v1",
};

describe("Neftel request helpers", () => {
  it("validates explicit evidence and reports bounded request statistics", () => {
    expect(validateNeftelRequest(valid)).toEqual([]);
    expect(neftelRequestStats(valid)).toEqual({ observations: 4, active: 2, programs: 13 });
    expect(neftelRequestStats({})).toEqual({ observations: 0, active: 0, programs: 13 });
  });

  it("rejects malformed roots, bounds, and non-object observations", () => {
    const errors = validateNeftelRequest({
      profile_id: "latest",
      sample_id: 2,
      observations: [null],
      bootstrap_replicates: 15,
      permutation_replicates: 63,
      background_mode: "cohort",
      effect_scale: "raw",
      effect_reference_id: "1-invalid",
      unknown: true,
    });
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: unknown.",
      `profile_id must equal ${NEFTEL_PROFILE_ID}.`,
      "sample_id must be a valid identifier.",
      "effect_scale must equal standardized_log2_abundance_contrast.",
      "effect_reference_id must be a valid identifier.",
      "background_mode must equal request_observed_proteome.",
      "observations[0] must be an object.",
      "bootstrap_replicates must be an integer from 16 through 256.",
      "permutation_replicates must be an integer from 64 through 2,048.",
    ]));
    expect(validateNeftelRequest({ effect_scale: "standardized_log2_abundance_contrast", observations: {} })).toEqual(expect.arrayContaining([
      "observations must be an array.",
      "At least one protein observation is required.",
    ]));
    expect(validateNeftelRequest({ ...valid, observations: Array.from({ length: 4_097 }, () => null) })).toContain("The request exceeds the 4,096-observation limit.");
  });

  it("matches numeric, state, identity, digest, and HGNC alias invariants", () => {
    const errors = validateNeftelRequest({
      ...valid,
      observations: [
        { observation_id: "bad id", gene_symbol: "?", state: "detected", standardized_effect: 21, standard_error: -1, quality_weight: 2, provenance_digest: "bad", extra: true },
        { observation_id: "obs.duplicate", gene_symbol: "WARS", state: "observed", provenance_digest: digest },
        { observation_id: "obs.duplicate", gene_symbol: "WARS1", state: "missing", standardized_effect: -1, quality_weight: 1, provenance_digest: digest },
      ],
    });
    expect(errors).toEqual(expect.arrayContaining([
      "observations[0] contains unsupported fields: extra.",
      "observations[0].observation_id must be a valid identifier.",
      "observations[0].gene_symbol must be a valid protein symbol.",
      "observations[0].state must be one of: observed, left_censored, missing, unsupported.",
      "observations[0].provenance_digest must be a lowercase sha256 digest.",
      "observations[0].standardized_effect must be a finite number within [-20, 20] or null.",
      "observations[0].standard_error must be a finite number within [0, 20] or null.",
      "observations[0].quality_weight must be a finite number within [0, 1] or null.",
      "observations[1] active evidence requires an effect, positive error, and positive quality.",
      "observations[2] missing/unsupported evidence requires no numeric values and zero quality.",
      "Duplicate observation identifiers: obs.duplicate.",
      "Duplicate gene symbols after HGNC alias normalization: WARS1.",
    ]));
  });
});

describe("Neftel result normalization", () => {
  it("normalizes methods, counts, drivers, ablations, and abstentions", () => {
    const programs = normalizeNeftelPrograms({ program_evidence: [
      null,
      { program_id: "ignored", program_kind: "unknown", support: "supported" },
      {
        program_id: "AC", program_kind: "source_meta_module", source_programs: ["AC", 4], support: "supported", classification: "activated", method_agreement: "concordant",
        location: { score: 1.12, lower_bound: 0.9, upper_bound: 1.3 },
        rank_enrichment: { score: 0.72, p_value: 0.01, q_value: 0.02 },
        evidence_counts: { active_coverage: 0.31, observed_markers: 12, eligible_protein_markers: 39 },
        top_drivers: [null, { normalized_symbol: "EGFR", standardized_effect: 1.2, evidence_state: "observed", location_influence: 0.2, rank_influence: 0.1 }],
        marker_family_ablations: [null, { omitted_family: "AC", markers_removed: 4, location_delta: -0.2, rank_delta: -0.1 }],
        abstention_reasons: [],
      },
      { program_kind: "derived_program_family", support: "abstained", abstention_reasons: ["sparse", 7] },
    ] });
    expect(programs).toHaveLength(2);
    expect(programs[0]).toMatchObject({ id: "AC", support: "supported", locationScore: 1.12, rankScore: 0.72, qValue: 0.02, activeCoverage: 0.31, sourcePrograms: ["AC"] });
    expect(programs[0].drivers[0]).toEqual({ symbol: "EGFR", effect: 1.2, state: "observed", locationInfluence: 0.2, rankInfluence: 0.1 });
    expect(programs[0].ablations[0]).toEqual({ family: "AC", removed: 4, locationDelta: -0.2, rankDelta: -0.1 });
    expect(programs[1]).toMatchObject({ id: "unnamed-program", support: "abstained", classification: "not_estimable", reasons: ["sparse"] });
  });
});
