import { describe, expect, it } from "vitest";

import {
  LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST,
  LONGITUDINAL_PHOSPHO_ASSAY_PROFILE_ID,
  LONGITUDINAL_PHOSPHO_ASSAY_SCHEMA_VERSION,
  LONGITUDINAL_PHOSPHO_SOURCE_PROFILE_DIGEST,
  longitudinalPhosphoRequestStats,
  normalizeLongitudinalPhosphoTransitions,
  normalizePhosphoModelViews,
  validateLongitudinalPhosphoRequest,
} from "../../src/lib/longitudinal-gbm-phospho";
import type { JsonObject } from "../../src/lib/research-state";

const digest = (character: string) => `sha256:${character.repeat(64)}`;

function requestFixture(): JsonObject {
  const referenceDigest = digest("1");
  const observations = (point: number) => [{
    observation_id: `obs-${point}-a`,
    phosphosite_id: "ENSP00000354587.4:s473",
    gene_symbol: "AKT1",
    state: "observed",
    log_abundance_ratio: point * 0.4,
    standard_error: 0.08,
    quality_weight: 0.95,
    provenance_digest: digest(String(point + 2)),
  }];
  return {
    profile_id: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
    series_id: "synthetic-phospho-series",
    assay_compatibility: {
      schema_version: LONGITUDINAL_PHOSPHO_ASSAY_SCHEMA_VERSION,
      compatibility_profile_id: LONGITUDINAL_PHOSPHO_ASSAY_PROFILE_ID,
      source_profile_digest: LONGITUDINAL_PHOSPHO_SOURCE_PROFILE_DIGEST,
      source_artifact_content_digest: LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST,
      assay: "tmt11_plexed_phosphoproteome_mass_spectrometry",
      quantification: "phosphosite_sample_to_reference_abundance_ratio",
      value_transformation: "log2_ratio",
      log_base: 2,
      feature_identity: "exact_ensp_versioned_source_site_group",
      composite_site_policy: "indivisible_source_site_group",
      invariant_across_time_points: true,
      attested_compatible: true,
    },
    normalization_reference: {
      reference_id: "synthetic-bridge",
      binding_digest: referenceDigest,
      normalization_method: "fixed sample-to-reference bridge",
      abundance_scale: "caller_supplied_log2_phosphosite_abundance_ratio",
      invariant_across_time_points: true,
    },
    time_points: [
      { time_point_id: "p0", time_offset_days: 0, normalization_reference_digest: referenceDigest, observations: observations(0) },
      { time_point_id: "p1", time_offset_days: 90, normalization_reference_digest: referenceDigest, observations: observations(1) },
    ],
    bootstrap_replicates: 64,
  };
}

function cloneRequest(): JsonObject {
  return structuredClone(requestFixture());
}

function observationFixture(index: number, point = 0): JsonObject {
  return {
    observation_id: `obs-${point}-${index}`,
    phosphosite_id: `ENSP${String(index + 1).padStart(11, "0")}.1:s1`,
    gene_symbol: "AKT1",
    state: "observed",
    log_abundance_ratio: 0.1,
    standard_error: 0.1,
    quality_weight: 1,
    provenance_digest: digest("a"),
  };
}

describe("longitudinal phosphosite request validation", () => {
  it("accepts the exact assay-bound request and reports site statistics", () => {
    const request = requestFixture();
    expect(validateLongitudinalPhosphoRequest(request)).toEqual([]);
    expect(longitudinalPhosphoRequestStats(request)).toEqual({
      timePoints: 2,
      observations: 2,
      active: 2,
      phosphosites: 1,
    });
  });

  it("fails closed on assay drift, unknown fields, duplicates, and unsupported-as-numeric", () => {
    const request = requestFixture();
    const assay = request.assay_compatibility as JsonObject;
    assay.source_artifact_content_digest = digest("f");
    assay.hidden_override = true;
    const points = request.time_points as JsonObject[];
    const first = points[0].observations as JsonObject[];
    first.push({ ...first[0], observation_id: "obs-duplicate" });
    const second = points[1].observations as JsonObject[];
    second[0] = {
      ...second[0],
      state: "unsupported",
      quality_weight: 0,
    };
    request.bootstrap_replicates = 65;

    const errors = validateLongitudinalPhosphoRequest(request).join("\n");
    expect(errors).toContain("source_artifact_content_digest must exactly equal");
    expect(errors).toContain("unsupported fields: hidden_override");
    expect(errors).toContain("duplicate phosphosite groups");
    expect(errors).toContain("missing/unsupported evidence requires no value/error and zero quality");
    expect(errors).toContain("integer from 32 through 64");
  });

  it("rejects invalid source-site identity, reference drift, and unordered points", () => {
    const request = requestFixture();
    const points = request.time_points as JsonObject[];
    points[0].time_offset_days = 90;
    points[1].time_offset_days = 10;
    points[1].normalization_reference_digest = digest("9");
    const observations = points[1].observations as JsonObject[];
    observations[0].phosphosite_id = "AKT1:S473";

    const errors = validateLongitudinalPhosphoRequest(request).join("\n");
    expect(errors).toContain("exact ENSP-versioned source site group");
    expect(errors).toContain("must match the invariant reference binding");
    expect(errors).toContain("strictly increasing");
  });

  it("covers malformed root, assay, reference, and statistics shapes", () => {
    expect(longitudinalPhosphoRequestStats({
      time_points: [
        null,
        {
          observations: [
            null,
            { phosphosite_id: 7, state: "unsupported" },
            { phosphosite_id: "ENSP00000000001.1:s1", state: "missing" },
          ],
        },
      ],
    })).toEqual({ timePoints: 2, observations: 3, active: 0, phosphosites: 1 });
    expect(longitudinalPhosphoRequestStats({})).toEqual({
      timePoints: 0,
      observations: 0,
      active: 0,
      phosphosites: 0,
    });

    const malformed: JsonObject = {
      unexpected: true,
      profile_id: "wrong-profile",
      series_id: 7,
      assay_compatibility: null,
      normalization_reference: null,
      time_points: null,
      bootstrap_replicates: "64",
    };
    const malformedErrors = validateLongitudinalPhosphoRequest(malformed).join("\n");
    expect(malformedErrors).toContain("request contains unsupported fields");
    expect(malformedErrors).toContain("profile_id must equal");
    expect(malformedErrors).toContain("series_id must be a valid identifier");
    expect(malformedErrors).toContain("explicit phosphosite compatibility attestation");
    expect(malformedErrors).toContain("normalization_reference must be an object");
    expect(malformedErrors).toContain("time_points must be an array");

    const attestationDrift = cloneRequest();
    delete attestationDrift.profile_id;
    const assay = attestationDrift.assay_compatibility as JsonObject;
    Object.keys(assay).forEach((field, index) => {
      if (index % 2 === 0) delete assay[field];
      else assay[field] = null;
    });
    assay.extra = "closed";
    const driftErrors = validateLongitudinalPhosphoRequest(attestationDrift).join("\n");
    expect(driftErrors).toContain("assay_compatibility contains unsupported fields: extra");
    expect(driftErrors).toContain("schema_version must exactly equal");
    expect(driftErrors).toContain("attested_compatible must exactly equal");

    const invalidReference = cloneRequest();
    invalidReference.normalization_reference = {
      reference_id: "9bad",
      binding_digest: "SHA256:not-lowercase",
      normalization_method: " ",
      abundance_scale: "linear",
      invariant_across_time_points: false,
      extra: true,
    };
    const referenceErrors = validateLongitudinalPhosphoRequest(invalidReference).join("\n");
    expect(referenceErrors).toContain("normalization_reference contains unsupported fields");
    expect(referenceErrors).toContain("reference_id must be a valid identifier");
    expect(referenceErrors).toContain("binding_digest must be a lowercase sha256 digest");
    expect(referenceErrors).toContain("normalization_method must be non-empty");
    expect(referenceErrors).toContain("abundance_scale must equal");
    expect(referenceErrors).toContain("invariant_across_time_points must be true");

    const optionalDefaults = cloneRequest();
    delete optionalDefaults.bootstrap_replicates;
    const reference = optionalDefaults.normalization_reference as JsonObject;
    delete reference.abundance_scale;
    delete reference.invariant_across_time_points;
    const points = optionalDefaults.time_points as JsonObject[];
    for (const point of points) {
      const observation = (point.observations as JsonObject[])[0];
      delete observation.quality_weight;
    }
    expect(validateLongitudinalPhosphoRequest(optionalDefaults)).toEqual([]);
  });

  it("covers malformed time points, observations, numeric bounds, and duplicate identities", () => {
    const malformedPoints = cloneRequest();
    const points = malformedPoints.time_points as JsonObject[];
    points[0] = null as unknown as JsonObject;
    points[1] = {
      extra: true,
      time_point_id: "1bad",
      time_offset_days: null,
      normalization_reference_digest: "bad",
      observations: null,
    };
    const pointErrors = validateLongitudinalPhosphoRequest(malformedPoints).join("\n");
    expect(pointErrors).toContain("time_points[0] must be an object");
    expect(pointErrors).toContain("time_points[1] contains unsupported fields");
    expect(pointErrors).toContain("observations must be an array");
    expect(pointErrors).toContain("observations must contain 1 through 4,096 entries");

    const malformedObservations = cloneRequest();
    const malformedPoint = (malformedObservations.time_points as JsonObject[])[0];
    malformedPoint.observations = [
      null,
      {
        unexpected: true,
        observation_id: 1,
        phosphosite_id: 2,
        gene_symbol: "?",
        state: "invented",
        log_abundance_ratio: Number.NaN,
        standard_error: -1,
        quality_weight: 2,
        provenance_digest: "bad",
      },
      {
        ...observationFixture(10),
        observation_id: "obs-active-zero",
        log_abundance_ratio: null,
        standard_error: 0,
        quality_weight: null,
      },
      {
        ...observationFixture(11),
        observation_id: "obs-above",
        log_abundance_ratio: 101,
        standard_error: 21,
        quality_weight: -0.1,
      },
      {
        ...observationFixture(12),
        observation_id: "obs-below",
        log_abundance_ratio: -101,
        standard_error: Number.POSITIVE_INFINITY,
        quality_weight: "high",
      },
      {
        ...observationFixture(13),
        observation_id: "obs-missing-valid",
        state: "missing",
        log_abundance_ratio: null,
        standard_error: null,
        quality_weight: 0,
      },
      {
        ...observationFixture(14),
        observation_id: "obs-unsupported-default-quality",
        state: "unsupported",
        log_abundance_ratio: null,
        standard_error: null,
        quality_weight: undefined,
      },
    ];
    const observationErrors = validateLongitudinalPhosphoRequest(malformedObservations).join("\n");
    expect(observationErrors).toContain("observations[0] must be an object");
    expect(observationErrors).toContain("contains unsupported fields: unexpected");
    expect(observationErrors).toContain("must be a finite number within [-100, 100] or null");
    expect(observationErrors).toContain("active evidence requires a value");
    expect(observationErrors).toContain("missing/unsupported evidence requires no value/error and zero quality");

    const duplicates = cloneRequest();
    const duplicatePoints = duplicates.time_points as JsonObject[];
    duplicatePoints[1].time_point_id = duplicatePoints[0].time_point_id;
    const first = (duplicatePoints[0].observations as JsonObject[])[0];
    const second = (duplicatePoints[1].observations as JsonObject[])[0];
    second.observation_id = first.observation_id;
    const duplicateErrors = validateLongitudinalPhosphoRequest(duplicates).join("\n");
    expect(duplicateErrors).toContain("Duplicate time-point identifiers");
    expect(duplicateErrors).toContain("Duplicate observation identifiers");

    for (const invalidBootstrap of [31, 64.5, 65]) {
      const request = cloneRequest();
      request.bootstrap_replicates = invalidBootstrap;
      expect(validateLongitudinalPhosphoRequest(request).join("\n")).toContain(
        "bootstrap_replicates must be an integer",
      );
    }
  });

  it("enforces per-point and whole-series cardinality ceilings", () => {
    const tooManyPoints = cloneRequest();
    const templatePoint = (tooManyPoints.time_points as JsonObject[])[0];
    tooManyPoints.time_points = Array.from({ length: 17 }, (_, index) => ({
      ...structuredClone(templatePoint),
      time_point_id: `p${index}`,
      time_offset_days: index,
      observations: [observationFixture(index, index)],
    }));
    expect(validateLongitudinalPhosphoRequest(tooManyPoints).join("\n")).toContain(
      "2 through 16 ordered entries",
    );

    const oversized = cloneRequest();
    const oversizedPoints = (oversized.time_points as JsonObject[]).map((point, pointIndex) => ({
      ...point,
      time_offset_days: pointIndex,
      observations: Array.from({ length: 4_097 }, (_, index) => observationFixture(index, pointIndex)),
    }));
    oversizedPoints.push({
      ...structuredClone(oversizedPoints[0]),
      time_point_id: "p2",
      time_offset_days: 2,
      observations: Array.from({ length: 4_097 }, (_, index) => observationFixture(index, 2)),
    });
    oversized.time_points = oversizedPoints;
    const errors = validateLongitudinalPhosphoRequest(oversized).join("\n");
    expect(errors).toContain("observations must contain 1 through 4,096 entries");
    expect(errors).toContain("12,000-observation series limit");
  });
});

describe("longitudinal phosphosite result normalization", () => {
  it("retains covariance closure, SPHINKS annotations, censored bounds, and ablations", () => {
    const result: JsonObject = {
      transitions: [{
        transition_id: "transition-0",
        transition_index: 0,
        from_time_point_id: "p0",
        to_time_point_id: "p1",
        support: "limited",
        classification: "source_recurrence_aligned",
        score: 0.72,
        lower_bound: 0.42,
        upper_bound: 0.95,
        bootstrap_replicates_used: 64,
        exact_feature_count: 31,
        censored_feature_count: 1,
        effective_sample_size: 29.4,
        coefficient_weight_coverage: 0.97,
        source_pair_coverage_weighted_mean: 0.81,
        measurement_uncertainty: { state: "estimated", standard_error: 0.04, variance: 0.0016, variance_fraction: 0.2, bootstrap_replicates_used: 64 },
        coefficient_uncertainty: { state: "estimated", standard_error: 0.09, variance: 0.0081, variance_fraction: 0.6, bootstrap_replicates_used: 64 },
        uncertainty_interaction: {
          state: "estimated",
          method: "paired_full_model_bootstrap_interaction_decomposition_v1",
          interaction_standard_error: 0.03,
          interaction_variance: 0.0009,
          interaction_variance_fraction: 0.2,
          measurement_coefficient_covariance: -0.0002,
          measurement_interaction_covariance: 0.0001,
          coefficient_interaction_covariance: -0.00005,
          variance_contribution: 0.0006,
          combined_variance: 0.0103,
          decomposed_variance: 0.0103,
          decomposition_residual: 0,
          bootstrap_replicates_used: 64,
        },
        top_drivers: [{
          phosphosite_id: "ENSP00000354587.4:s473",
          gene_symbol: "AKT1",
          hgnc_id: "HGNC:391",
          site_cardinality: 1,
          composite_site_group: false,
          from_observation_id: "obs-0-a",
          to_observation_id: "obs-1-a",
          standardized_delta: 0.8,
          model_coefficient: 0.1,
          signed_contribution: 0.08,
          direction: "source_recurrence_aligned",
          reliability_weight: 0.95,
          source_pair_support: 80,
          bootstrap_selection_stability: 0.5,
          sphinks_source_site_label: "AKT1_S473",
          sphinks_signature_kinases: ["AKT1"],
        }],
        censored_bounds: [{ phosphosite_id: "ENSP00000354587.4:s474", gene_symbol: "AKT1", value_semantics: "upper_bound", standardized_bound: 0.3, coefficient_weighted_bound: -0.02 }],
        feature_family_ablations: [{ component: "exact_sphinks_crosswalk_sites", omitted_feature_count: 4, support: "limited", score_without_component: 0.6, score_delta: 0.12, classification_without_component: "source_recurrence_aligned", reason: "source gate" }],
        top_driver_ablations: [{ omitted_phosphosite_id: "ENSP00000354587.4:s473", support: "limited", score_without_component: 0.64, score_delta: 0.08, classification_without_component: "source_recurrence_aligned", reason: "source gate" }],
        abstention_reasons: ["source gate"],
      }],
      model_views: [
        { view: "raw_phosphosite_transition", support: "fitted", reason: "fitted" },
        { view: "occupancy_like", support: "not_fitted", reason: "not fitted" },
      ],
    };

    const [transition] = normalizeLongitudinalPhosphoTransitions(result);
    expect(transition.uncertaintyInteraction.measurementCoefficientCovariance).toBe(-0.0002);
    expect(transition.uncertaintyInteraction.decompositionResidual).toBe(0);
    expect(transition.drivers[0].sphinksKinases).toEqual(["AKT1"]);
    expect(transition.censoredBounds[0].semantics).toBe("upper_bound");
    expect(transition.ablations.map((item) => item.kind)).toEqual(["feature_family", "top_driver"]);
    expect(normalizePhosphoModelViews(result)).toHaveLength(2);
  });

  it("filters malformed result members and exercises every normalization default", () => {
    const result: JsonObject = {
      transitions: [
        null,
        { support: "invented" },
        {
          support: "abstained",
          measurement_uncertainty: null,
          coefficient_uncertainty: {},
          uncertainty_interaction: null,
          top_drivers: [
            null,
            {},
            {
              phosphosite_id: "ENSP00000000001.1:s1",
              composite_site_group: true,
              sphinks_signature_kinases: ["AKT1", 7, null],
            },
          ],
          censored_bounds: [
            null,
            {},
            { phosphosite_id: "ENSP00000000002.1:s2" },
          ],
          feature_family_ablations: [
            null,
            {},
          ],
          top_driver_ablations: [
            null,
            {},
          ],
          abstention_reasons: ["no overlap", 3],
        },
        {
          support: "limited",
          uncertainty_interaction: {},
          top_drivers: [{
            phosphosite_id: "ENSP00000000003.1:s3",
            sphinks_signature_kinases: "AKT1",
          }],
          abstention_reasons: "not-an-array",
        },
      ],
      model_views: [null, {}, { view: "occupancy_like", support: "not_fitted", reason: "none" }],
    };

    const [transition, interactionFallback] = normalizeLongitudinalPhosphoTransitions(result);
    expect(transition).toMatchObject({
      id: "unnamed-transition",
      index: 0,
      fromTimePointId: "unknown-from",
      toTimePointId: "unknown-to",
      support: "abstained",
      classification: "not_estimable",
      score: null,
      lower: null,
      upper: null,
      bootstrapReplicates: 0,
      exactFeatureCount: 0,
      censoredFeatureCount: 0,
      effectiveSampleSize: null,
      coefficientCoverage: null,
      sourcePairCoverageMean: null,
      reasons: ["no overlap"],
    });
    expect(transition.measurementUncertainty).toEqual({
      state: "not_estimable",
      standardError: null,
      variance: null,
      varianceFraction: null,
      bootstrapReplicates: 0,
      reason: "",
    });
    expect(transition.coefficientUncertainty.bootstrapReplicates).toBe(0);
    expect(transition.uncertaintyInteraction).toMatchObject({
      state: "not_estimable",
      method: "",
      standardError: null,
      combinedVariance: null,
      bootstrapReplicates: 0,
      reason: "",
    });
    expect(interactionFallback.uncertaintyInteraction.bootstrapReplicates).toBe(0);
    expect(interactionFallback.drivers[0].sphinksKinases).toEqual([]);
    expect(interactionFallback.reasons).toEqual([]);
    expect(transition.drivers).toHaveLength(1);
    expect(transition.drivers[0]).toMatchObject({
      geneSymbol: "—",
      siteCardinality: 1,
      composite: true,
      direction: "indeterminate",
      sphinksKinases: ["AKT1"],
    });
    expect(transition.censoredBounds).toEqual([expect.objectContaining({
      geneSymbol: "—",
      semantics: "bound",
      standardizedBound: null,
      weightedBound: null,
    })]);
    expect(transition.ablations).toEqual([
      expect.objectContaining({
        kind: "feature_family",
        label: "feature family",
        omittedCount: 0,
        support: "abstained",
      }),
      expect.objectContaining({
        kind: "top_driver",
        label: "top phosphosite driver",
        omittedCount: 1,
        classification: "not_estimable",
      }),
    ]);
    expect(normalizePhosphoModelViews(result)).toEqual([
      { view: "unknown", support: "not_fitted", reason: "" },
      { view: "occupancy_like", support: "not_fitted", reason: "none" },
    ]);
    expect(normalizeLongitudinalPhosphoTransitions({})).toEqual([]);
    expect(normalizePhosphoModelViews({})).toEqual([]);
  });
});
