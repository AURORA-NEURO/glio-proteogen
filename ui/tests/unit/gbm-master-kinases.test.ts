import { describe, expect, it } from "vitest";

import {
  MASTER_KINASE_PROFILE_ID,
  masterKinaseRequestStats,
  normalizeMasterKinases,
  normalizeMasterKinaseSubtypes,
  validateMasterKinaseRequest,
} from "../../src/lib/gbm-master-kinases";
import type { JsonObject } from "../../src/lib/research-state";
import { masterKinaseAnalysis, masterKinaseDemo } from "../fixtures/gbm-master-kinases";

const digest = `sha256:${"a".repeat(64)}`;
const fixtureSourceDigest = `sha256:${"3".repeat(64)}`;
const valid: JsonObject = {
  profile_id: MASTER_KINASE_PROFILE_ID,
  sample_id: "synthetic.master.kinases",
  observations: [
    { observation_id: "obs.one", phosphosite_id: "ARHGAP15-S43s", state: "observed", standardized_effect: 1.1, standard_error: 0.3, provenance_digest: digest },
    { observation_id: "obs.two", phosphosite_id: "MAPK1-T185tY187y", state: "left_censored", standardized_effect: -0.4, standard_error: 0.4, quality_weight: 0.8, provenance_digest: digest },
    { observation_id: "obs.three", phosphosite_id: "VIM-S419s", state: "missing", quality_weight: 0, provenance_digest: digest },
    { observation_id: "obs.four", phosphosite_id: "PSTPIP1-S377s", state: "unsupported", quality_weight: 0, provenance_digest: digest },
  ],
  bootstrap_replicates: 16,
  permutation_replicates: 64,
  contrast_reference: {
    contrast_id: "synthetic.reference.v1",
    numerator_label: "glioma-like contrast",
    denominator_label: "reference contrast",
    scale: "caller_supplied_standardized_log2_contrast",
  },
  background_mode: "request_observed_pinned_table5a",
};

describe("GBM master-kinase request helpers", () => {
  it("validates explicit evidence, Pydantic defaults, and bounded request statistics", () => {
    expect(validateMasterKinaseRequest(valid)).toEqual([]);
    const withoutDefaults = { ...valid };
    delete withoutDefaults.profile_id;
    delete withoutDefaults.bootstrap_replicates;
    delete withoutDefaults.permutation_replicates;
    delete withoutDefaults.background_mode;
    expect(validateMasterKinaseRequest(withoutDefaults)).toEqual([]);
    expect(masterKinaseRequestStats(valid)).toEqual({ observations: 4, active: 2, phosphosites: 4, signatures: 24 });
    expect(masterKinaseRequestStats({})).toEqual({ observations: 0, active: 0, phosphosites: 0, signatures: 24 });
    expect(masterKinaseRequestStats(masterKinaseDemo as unknown as JsonObject)).toMatchObject({ observations: 5, active: 4, signatures: 24 });
  });

  it("rejects malformed roots, numerical bounds, contrast semantics, and transport contract values", () => {
    const errors = validateMasterKinaseRequest({
      profile_id: "latest",
      sample_id: 2,
      observations: [null],
      bootstrap_replicates: 15,
      permutation_replicates: 63,
      contrast_reference: {
        contrast_id: "1-invalid",
        numerator_label: "",
        denominator_label: "x".repeat(257),
        scale: "raw",
        extra: true,
      },
      background_mode: "cohort",
      unknown: true,
    });
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: unknown.",
      `profile_id must equal ${MASTER_KINASE_PROFILE_ID}.`,
      "sample_id must be a valid identifier.",
      "observations[0] must be an object.",
      "bootstrap_replicates must be an integer from 16 through 256.",
      "permutation_replicates must be an integer from 64 through 2,048.",
      "contrast_reference contains unsupported fields: extra.",
      "contrast_reference.contrast_id must be a valid identifier.",
      "contrast_reference.numerator_label must contain 1–256 characters.",
      "contrast_reference.denominator_label must contain 1–256 characters.",
      "contrast_reference.scale must equal caller_supplied_standardized_log2_contrast.",
      "background_mode must equal request_observed_pinned_table5a.",
    ]));
    expect(validateMasterKinaseRequest({ observations: {}, contrast_reference: null })).toEqual(expect.arrayContaining([
      "observations must be an array.",
      "At least one phosphosite observation is required.",
      "contrast_reference must be an object.",
    ]));
    expect(validateMasterKinaseRequest({ ...valid, observations: Array.from({ length: 4_097 }, () => null) })).toContain("The request exceeds the 4,096-observation limit.");
    expect(validateMasterKinaseRequest({ ...valid, contrast_reference: { ...valid.contrast_reference as JsonObject, numerator_label: "same", denominator_label: "same" } })).toContain("contrast_reference numerator and denominator labels must differ.");
  });

  it("enforces exact IDs, site syntax, evidence-state numbers, digests, and uniqueness", () => {
    const errors = validateMasterKinaseRequest({
      ...valid,
      observations: [
        { observation_id: "bad id", phosphosite_id: "?", state: "detected", standardized_effect: 21, standard_error: 0, quality_weight: 2, provenance_digest: "bad", extra: true },
        { observation_id: "obs.duplicate", phosphosite_id: "BAD-S118s", state: "observed", provenance_digest: digest },
        { observation_id: "obs.duplicate", phosphosite_id: "BAD-S118s", state: "missing", standardized_effect: -1, standard_error: 0.3, provenance_digest: digest },
      ],
    });
    expect(errors).toEqual(expect.arrayContaining([
      "observations[0] contains unsupported fields: extra.",
      "observations[0].observation_id must be a valid identifier.",
      "observations[0].phosphosite_id must be a valid source phosphosite identifier.",
      "observations[0].state must be one of: observed, left_censored, missing, unsupported.",
      "observations[0].provenance_digest must be a lowercase sha256 digest.",
      "observations[0].standardized_effect must be a finite number within [-20, 20] or null.",
      "observations[0].quality_weight must be a finite number within [0, 1] or null.",
      "observations[1] active evidence requires an effect, positive standard error, and positive quality weight.",
      "observations[2] missing/unsupported evidence requires no numeric effect/error and zero quality weight.",
      "Duplicate observation identifiers: obs.duplicate.",
      "Duplicate phosphosite identifiers: BAD-S118s.",
    ]));
    const overlongSite = `A${"S".repeat(128)}`;
    expect(validateMasterKinaseRequest({ ...valid, observations: [{ ...valid.observations![0] as JsonObject, phosphosite_id: overlongSite }] })).toContain("observations[0].phosphosite_id must be a valid source phosphosite identifier.");
  });
});

describe("GBM master-kinase result normalization", () => {
  it("normalizes all 24 grouped kinase signatures with rank, support, coverage, ESS, drivers, and residue ablations", () => {
    const kinases = normalizeMasterKinases(masterKinaseAnalysis as unknown as JsonObject);
    expect(kinases).toHaveLength(24);
    expect(kinases.filter((item) => item.subtype === "GPM")).toHaveLength(9);
    expect(kinases.filter((item) => item.subtype === "MTC")).toHaveLength(1);
    expect(kinases.filter((item) => item.subtype === "NEU")).toHaveLength(7);
    expect(kinases.filter((item) => item.subtype === "PPR")).toHaveLength(7);
    expect(kinases[0]).toMatchObject({ id: "PRKCD", sourceLabel: "PKCD", support: "supported", locationScore: 1.055445, rankScore: 0.172408, qValue: 0.033566, activeSites: 13, mappedSites: 12, effectiveSampleSize: 12, bootstrapReplicates: 16, bootstrapReplicatesSuccessful: 16, bootstrapReplicatesRequested: 16, rankBootstrapReplicates: 16, rankBootstrapReplicatesSuccessful: 16, rankBootstrapReplicatesRequested: 16, permutationReplicates: 64 });
    expect(kinases[0].drivers[0]).toEqual({ observationId: "demo.driver.01", provenanceDigest: fixtureSourceDigest, phosphositeId: "MAPK1-T185tY187y", effect: -0.76, state: "observed", weight: 6.1, locationInfluence: 0.42, rankInfluence: 0.08 });
    expect(kinases[0].ablations[0]).toEqual({ family: "S", removed: 18, locationDelta: 0.018147, rankDelta: -0.040283 });
  });

  it("normalizes four subtype aggregates, weighted drivers, and leave-one-kinase-out ablations", () => {
    const subtypes = normalizeMasterKinaseSubtypes(masterKinaseAnalysis as unknown as JsonObject);
    expect(subtypes).toHaveLength(4);
    expect(subtypes[0]).toMatchObject({ id: "GPM", support: "supported", score: 1.014197, supportedMembers: 9, estimatedMembers: 9, bootstrapReplicates: 16, bootstrapReplicatesSuccessful: 16, bootstrapReplicatesRequested: 16 });
    expect(subtypes[0].drivers[0]).toMatchObject({ kinaseId: "PRKCD", score: 1.014197, weight: 1 / 9, contribution: -0.004 });
    expect(subtypes[0].ablations[0]).toEqual({ kinaseId: "PRKCD", scoreDelta: -0.002 });
    expect(subtypes[1]).toMatchObject({ id: "MTC", support: "limited", effectiveSampleSize: 1 });
    expect(subtypes[1].reasons).toEqual(["fewer than two independently estimated member kinases"]);
  });

  it("drops malformed result entries instead of inventing kinase or subtype identities", () => {
    expect(normalizeMasterKinases({ kinase_evidence: [null, { kinase_id: "X", source_subtype: "OTHER", support: "supported" }, { kinase_id: "Y", source_subtype: "GPM", support: "unknown" }] })).toEqual([]);
    expect(normalizeMasterKinaseSubtypes({ subtype_evidence: [null, { subtype_id: "OTHER", support: "supported" }] })).toEqual([]);
  });

  it("keeps sparse and partially malformed result payloads explicit without fabricating estimates", () => {
    expect(masterKinaseRequestStats({ observations: [null, { phosphosite_id: 3, state: "missing" }, { phosphosite_id: " SITE-S1s ", state: "observed" }] })).toEqual({ observations: 3, active: 1, phosphosites: 1, signatures: 24 });
    const sparseKinases = normalizeMasterKinases({ kinase_evidence: [{
      source_subtype: "GPM",
      support: "limited",
      top_drivers: [null, {}],
      edge_ablations: [null, {}],
      abstention_reasons: null,
    }] });
    expect(sparseKinases).toHaveLength(1);
    expect(sparseKinases[0]).toMatchObject({ id: "unnamed-kinase", sourceLabel: "unnamed", locationScore: null, rankScore: null, sourceEdges: 0, signatureSites: 0, mappedSites: 0, activeSites: 0, coverage: 0, effectiveSampleSize: null, bootstrapReplicates: 0, rankBootstrapReplicates: 0, permutationReplicates: 0, drivers: [], reasons: [] });
    expect(sparseKinases[0].ablations).toEqual([{ family: "unspecified", removed: 0, locationDelta: null, rankDelta: null }]);

    const sparseSubtypes = normalizeMasterKinaseSubtypes({ subtype_evidence: [{
      subtype_id: "GPM",
      support: "limited",
      member_kinases: null,
      top_kinases: [null, {}],
      subtype_ablations: [null, {}],
      abstention_reasons: null,
    }] });
    expect(sparseSubtypes).toHaveLength(1);
    expect(sparseSubtypes[0]).toMatchObject({ id: "GPM", score: null, lower: null, upper: null, effectiveSampleSize: null, bootstrapReplicates: 0, memberKinases: [], supportedMembers: 0, estimatedMembers: 0, drivers: [], ablations: [], reasons: [] });
  });
});
