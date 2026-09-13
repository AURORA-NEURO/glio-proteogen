import { describe, expect, it } from "vitest";

import {
  LONGITUDINAL_GBM_PROFILE_ID,
  longitudinalRequestStats,
  normalizeLongitudinalTransitions,
  normalizePeltAnalysis,
  validateLongitudinalRequest,
} from "../../src/lib/longitudinal-gbm";
import type { JsonObject } from "../../src/lib/research-state";
import {
  longitudinalAnalysisResult,
  longitudinalDemoRequest,
} from "../fixtures/longitudinal-gbm";

function document(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

function firstPoint(request: JsonObject): JsonObject {
  return (request.time_points as JsonObject[])[0];
}

function firstObservation(request: JsonObject): JsonObject {
  return (firstPoint(request).observations as JsonObject[])[0];
}

describe("longitudinal GBM request helpers", () => {
  it("validates the ordered, invariant-reference demo and reports series statistics", () => {
    const request = document(longitudinalDemoRequest);
    expect(validateLongitudinalRequest(request)).toEqual([]);
    expect(longitudinalRequestStats(request)).toEqual({
      timePoints: 4,
      observations: 16,
      active: 16,
      genes: 4,
    });
    expect(longitudinalRequestStats({})).toEqual({ timePoints: 0, observations: 0, active: 0, genes: 0 });
  });

  it("rejects wrong profiles, unknown fields, unordered time points, and broken reference bindings", () => {
    const request = document(longitudinalDemoRequest);
    request.profile_id = "latest";
    request.unknown = true;
    request.bootstrap_replicates = 31;
    const reference = request.normalization_reference as JsonObject;
    reference.abundance_scale = "caller_supplied_log_abundance";
    const points = request.time_points as JsonObject[];
    points[1].time_offset_days = 0;
    points[1].normalization_reference_digest = `sha256:${"f".repeat(64)}`;
    const errors = validateLongitudinalRequest(request);
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: unknown.",
      `profile_id must equal ${LONGITUDINAL_GBM_PROFILE_ID}.`,
      "time_points[1].normalization_reference_digest must match the invariant reference binding.",
      "time_points must be strictly increasing by time_offset_days in request order.",
      "bootstrap_replicates must be an integer from 32 through 256.",
      "normalization_reference.abundance_scale must equal caller_supplied_log2_protein_abundance_ratio.",
    ]));
  });

  it("fails closed on missing or forged assay/log-base/quantification attestations", () => {
    const missing = document(longitudinalDemoRequest);
    delete missing.assay_compatibility;
    expect(validateLongitudinalRequest(missing)).toContain(
      "assay_compatibility must be an explicit compatibility attestation object.",
    );

    const forged = document(longitudinalDemoRequest);
    const attestation = forged.assay_compatibility as JsonObject;
    attestation.assay = "label_free_mass_spectrometry";
    attestation.quantification = "total_peptide_abundance";
    attestation.value_transformation = "natural_log";
    attestation.log_base = Math.E;
    attestation.attested_compatible = false;
    attestation.extra = "unbound";
    expect(validateLongitudinalRequest(forged)).toEqual(expect.arrayContaining([
      "assay_compatibility contains unsupported fields: extra.",
      'assay_compatibility.assay must exactly equal "tmt11_plexed_mass_spectrometry".',
      'assay_compatibility.quantification must exactly equal "unshared_peptide_protein_abundance_ratio".',
      'assay_compatibility.value_transformation must exactly equal "log2_ratio".',
      "assay_compatibility.log_base must exactly equal 2.",
      "assay_compatibility.attested_compatible must exactly equal true.",
    ]));
  });

  it("preserves missing-state semantics and catches duplicate identities and invalid active evidence", () => {
    const request = document(longitudinalDemoRequest);
    const points = request.time_points as JsonObject[];
    const firstObservations = points[0].observations as JsonObject[];
    const secondObservations = points[1].observations as JsonObject[];
    firstObservations[0] = {
      ...firstObservations[0],
      state: "missing",
      log_abundance: null,
      standard_error: null,
      quality_weight: 0,
    };
    firstObservations[1].gene_symbol = firstObservations[0].gene_symbol;
    secondObservations[0].observation_id = firstObservations[0].observation_id;
    secondObservations[1].standard_error = null;
    const errors = validateLongitudinalRequest(request);
    expect(errors).toEqual(expect.arrayContaining([
      "time_points[0] contains duplicate gene symbols: EGFR.",
      "time_points[1].observations[1] active evidence requires abundance, positive error, and positive quality.",
      "Duplicate observation identifiers: demo.0.0.",
    ]));

    const badMissing = document(longitudinalDemoRequest);
    const badObservation = ((badMissing.time_points as JsonObject[])[0].observations as JsonObject[])[0];
    badObservation.state = "unsupported";
    badObservation.quality_weight = 1;
    expect(validateLongitudinalRequest(badMissing)).toContain(
      "time_points[0].observations[0] missing/unsupported evidence requires no abundance/error and zero quality.",
    );
  });

  it("rejects every malformed reference, time-point, observation, and numeric boundary", () => {
    const cases: Array<[string, (request: JsonObject) => void, string]> = [
      ["series identifier type", (request) => { request.series_id = 4; }, "series_id must be a valid identifier."],
      ["series identifier syntax", (request) => { request.series_id = " bad"; }, "series_id must be a valid identifier."],
      ["normalization object", (request) => { request.normalization_reference = null; }, "normalization_reference must be an object."],
      ["reference identifier type", (request) => { firstPoint(request); (request.normalization_reference as JsonObject).reference_id = 1; }, "normalization_reference.reference_id must be a valid identifier."],
      ["reference identifier syntax", (request) => { (request.normalization_reference as JsonObject).reference_id = "?"; }, "normalization_reference.reference_id must be a valid identifier."],
      ["reference digest type", (request) => { (request.normalization_reference as JsonObject).binding_digest = 7; }, "normalization_reference.binding_digest must be a lowercase sha256 digest."],
      ["reference digest syntax", (request) => { (request.normalization_reference as JsonObject).binding_digest = "SHA256:bad"; }, "normalization_reference.binding_digest must be a lowercase sha256 digest."],
      ["normalization method type", (request) => { (request.normalization_reference as JsonObject).normalization_method = false; }, "normalization_reference.normalization_method must be non-empty."],
      ["normalization method blank", (request) => { (request.normalization_reference as JsonObject).normalization_method = "  "; }, "normalization_reference.normalization_method must be non-empty."],
      ["reference invariant", (request) => { (request.normalization_reference as JsonObject).invariant_across_time_points = false; }, "normalization_reference.invariant_across_time_points must be true."],
      ["time-point collection", (request) => { request.time_points = null; }, "time_points must be an array."],
      ["too few time points", (request) => { request.time_points = []; }, "time_points must contain 2 through 16 ordered entries."],
      ["non-object time point", (request) => { (request.time_points as unknown[])[0] = null; }, "time_points[0] must be an object."],
      ["time-point unknown field", (request) => { firstPoint(request).extra = true; }, "time_points[0] contains unsupported fields: extra."],
      ["time-point identifier type", (request) => { firstPoint(request).time_point_id = 1; }, "time_points[0].time_point_id must be a valid identifier."],
      ["time-point identifier syntax", (request) => { firstPoint(request).time_point_id = "-bad"; }, "time_points[0].time_point_id must be a valid identifier."],
      ["negative time offset", (request) => { firstPoint(request).time_offset_days = -1; }, "time_points[0].time_offset_days must be a finite number"],
      ["non-finite time offset", (request) => { firstPoint(request).time_offset_days = Number.POSITIVE_INFINITY; }, "time_points[0].time_offset_days must be a finite number"],
      ["oversized time offset", (request) => { firstPoint(request).time_offset_days = Number.MAX_SAFE_INTEGER + 1; }, "time_points[0].time_offset_days must be a finite number"],
      ["time-point digest type", (request) => { firstPoint(request).normalization_reference_digest = 3; }, "time_points[0].normalization_reference_digest must be a lowercase sha256 digest."],
      ["time-point digest syntax", (request) => { firstPoint(request).normalization_reference_digest = "sha256:ABC"; }, "time_points[0].normalization_reference_digest must be a lowercase sha256 digest."],
      ["observation collection", (request) => { firstPoint(request).observations = null; }, "time_points[0].observations must be an array."],
      ["empty observations", (request) => { firstPoint(request).observations = []; }, "time_points[0].observations must contain 1 through 4,096 entries."],
      ["non-object observation", (request) => { (firstPoint(request).observations as unknown[])[0] = null; }, "time_points[0].observations[0] must be an object."],
      ["observation unknown field", (request) => { firstObservation(request).extra = 1; }, "time_points[0].observations[0] contains unsupported fields: extra."],
      ["observation identifier type", (request) => { firstObservation(request).observation_id = 1; }, "time_points[0].observations[0].observation_id must be a valid identifier."],
      ["observation identifier syntax", (request) => { firstObservation(request).observation_id = " bad"; }, "time_points[0].observations[0].observation_id must be a valid identifier."],
      ["gene symbol type", (request) => { firstObservation(request).gene_symbol = 1; }, "time_points[0].observations[0].gene_symbol must be a valid HGNC-style symbol."],
      ["gene symbol syntax", (request) => { firstObservation(request).gene_symbol = "egfr"; }, "time_points[0].observations[0].gene_symbol must be a valid HGNC-style symbol."],
      ["evidence state type", (request) => { firstObservation(request).state = 1; }, "time_points[0].observations[0].state must be one of"],
      ["evidence state value", (request) => { firstObservation(request).state = "negative"; }, "time_points[0].observations[0].state must be one of"],
      ["provenance type", (request) => { firstObservation(request).provenance_digest = 1; }, "time_points[0].observations[0].provenance_digest must be a lowercase sha256 digest."],
      ["provenance syntax", (request) => { firstObservation(request).provenance_digest = "sha256:no"; }, "time_points[0].observations[0].provenance_digest must be a lowercase sha256 digest."],
      ["abundance type", (request) => { firstObservation(request).log_abundance = "1"; }, "time_points[0].observations[0].log_abundance must be a finite number"],
      ["abundance below bound", (request) => { firstObservation(request).log_abundance = -101; }, "time_points[0].observations[0].log_abundance must be a finite number"],
      ["abundance above bound", (request) => { firstObservation(request).log_abundance = 101; }, "time_points[0].observations[0].log_abundance must be a finite number"],
      ["standard error above bound", (request) => { firstObservation(request).standard_error = 21; }, "time_points[0].observations[0].standard_error must be a finite number"],
      ["quality below bound", (request) => { firstObservation(request).quality_weight = -0.1; }, "time_points[0].observations[0].quality_weight must be a finite number"],
      ["quality above bound", (request) => { firstObservation(request).quality_weight = 1.1; }, "time_points[0].observations[0].quality_weight must be a finite number"],
      ["missing abundance", (request) => { firstObservation(request).log_abundance = null; }, "active evidence requires abundance, positive error, and positive quality."],
      ["zero standard error", (request) => { firstObservation(request).standard_error = 0; }, "active evidence requires abundance, positive error, and positive quality."],
      ["null quality", (request) => { firstObservation(request).quality_weight = null; }, "active evidence requires abundance, positive error, and positive quality."],
      ["zero quality", (request) => { firstObservation(request).quality_weight = 0; }, "active evidence requires abundance, positive error, and positive quality."],
      ["non-null unsupported abundance", (request) => { const observation = firstObservation(request); observation.state = "unsupported"; observation.standard_error = null; observation.quality_weight = 0; }, "missing/unsupported evidence requires no abundance/error and zero quality."],
      ["non-null missing error", (request) => { const observation = firstObservation(request); observation.state = "missing"; observation.log_abundance = null; observation.quality_weight = 0; }, "missing/unsupported evidence requires no abundance/error and zero quality."],
      ["nonzero missing quality", (request) => { const observation = firstObservation(request); observation.state = "missing"; observation.log_abundance = null; observation.standard_error = null; }, "missing/unsupported evidence requires no abundance/error and zero quality."],
      ["duplicate time point", (request) => { const points = request.time_points as JsonObject[]; points[1].time_point_id = points[0].time_point_id; }, "Duplicate time-point identifiers:"],
      ["bootstrap type", (request) => { request.bootstrap_replicates = "64"; }, "bootstrap_replicates must be an integer"],
      ["bootstrap fractional", (request) => { request.bootstrap_replicates = 64.5; }, "bootstrap_replicates must be an integer"],
      ["bootstrap upper bound", (request) => { request.bootstrap_replicates = 257; }, "bootstrap_replicates must be an integer"],
    ];

    cases.forEach(([label, mutate, expected]) => {
      const request = document(longitudinalDemoRequest);
      mutate(request);
      expect(validateLongitudinalRequest(request), label).toEqual(
        expect.arrayContaining([expect.stringContaining(expected)]),
      );
    });
  });

  it("enforces collection ceilings, attestation presence, and optional defaults", () => {
    const absentOptional = document(longitudinalDemoRequest);
    delete absentOptional.profile_id;
    delete absentOptional.bootstrap_replicates;
    const reference = absentOptional.normalization_reference as JsonObject;
    delete reference.abundance_scale;
    delete reference.invariant_across_time_points;
    delete firstObservation(absentOptional).quality_weight;
    expect(validateLongitudinalRequest(absentOptional)).toEqual([]);

    const missingAttestationField = document(longitudinalDemoRequest);
    delete (missingAttestationField.assay_compatibility as JsonObject).schema_version;
    expect(validateLongitudinalRequest(missingAttestationField)).toContain(
      'assay_compatibility.schema_version must exactly equal "glio-proteogen.kncc-assay-compatibility-attestation/1.0.0".',
    );

    const tooManyPoints = document(longitudinalDemoRequest);
    tooManyPoints.time_points = Array.from({ length: 17 }, (_, index) => ({
      time_point_id: `point.${index}`,
      time_offset_days: index,
      normalization_reference_digest: (tooManyPoints.normalization_reference as JsonObject).binding_digest,
      observations: [{
        observation_id: `observation.${index}`,
        gene_symbol: "EGFR",
        state: "observed",
        log_abundance: 0,
        standard_error: 0.1,
        provenance_digest: `sha256:${"a".repeat(64)}`,
      }],
    }));
    expect(validateLongitudinalRequest(tooManyPoints)).toContain(
      "time_points must contain 2 through 16 ordered entries.",
    );

    const tooManyAtPoint = document(longitudinalDemoRequest);
    firstPoint(tooManyAtPoint).observations = new Array(4_097) as never;
    expect(validateLongitudinalRequest(tooManyAtPoint)).toContain(
      "time_points[0].observations must contain 1 through 4,096 entries.",
    );

    const tooManyOverall = document(longitudinalDemoRequest);
    const points = tooManyOverall.time_points as JsonObject[];
    points.forEach((point) => { point.observations = new Array(4_000) as never; });
    expect(validateLongitudinalRequest(tooManyOverall)).toContain(
      "The request exceeds the 12,000-observation series limit.",
    );

    const missingOffset = document(longitudinalDemoRequest);
    firstPoint(missingOffset).time_offset_days = null;
    expect(validateLongitudinalRequest(missingOffset)).toEqual([]);
  });

  it("counts only typed genes and active evidence in malformed-but-inspectable drafts", () => {
    expect(longitudinalRequestStats({ time_points: [
      null,
      { observations: [null, { gene_symbol: 7, state: "observed" }, { gene_symbol: "EGFR", state: "missing" }, { gene_symbol: "EGFR", state: "left_censored" }] },
    ] })).toEqual({ timePoints: 2, observations: 4, active: 2, genes: 1 });
  });
});

describe("longitudinal GBM result normalization", () => {
  it("normalizes transitions, both uncertainty components, drivers, and both ablation families", () => {
    const transitions = normalizeLongitudinalTransitions(document(longitudinalAnalysisResult));
    expect(transitions).toHaveLength(3);
    expect(transitions[0]).toMatchObject({
      id: "transition.0",
      support: "limited",
      classification: "source_recurrence_aligned",
      score: 0.932,
      lower: 0.812,
      upper: 1.052,
      sharedActiveGenes: 4,
      effectiveSampleSize: 3.7,
      coverage: 0.84,
    });
    expect(transitions[0].measurementUncertainty).toMatchObject({ state: "estimated", standardError: 0.06, varianceFraction: 0.42, bootstrapReplicates: 32 });
    expect(transitions[0].coefficientUncertainty).toMatchObject({ state: "estimated", standardError: 0.08, varianceFraction: 0.58, bootstrapReplicates: 32 });
    expect(transitions[0].uncertaintyInteraction).toEqual({
      state: "estimated",
      method: "paired_bootstrap_covariance_identity_v1",
      covariance: -0.0005,
      varianceContribution: -0.001,
      combinedVariance: 0.009,
      decompositionResidual: 0,
      bootstrapReplicates: 32,
      reason: "",
    });
    expect(transitions[0].reasons).toEqual([
      "fewer than 64 estimable bootstrap projections for fully supported uncertainty",
    ]);
    expect(transitions[0].drivers[0]).toMatchObject({ geneSymbol: "EGFR", sourceGeneLabel: "EGFR", contribution: 0.57784, sourceFeatureSupport: 101 });
    expect(transitions[0].ablations.map((item) => item.kind)).toEqual(["source_processing", "top_driver"]);
    expect(transitions[0].ablations[0].label).toContain("ordinary Log");
    expect(transitions[0].ablations[1]).toMatchObject({ label: "EGFR", omittedContribution: 0.57784 });
  });

  it("normalizes duration-aware PELT abstention/limitations and rejects malformed support records", () => {
    const pelt = normalizePeltAnalysis(document(longitudinalAnalysisResult));
    expect(pelt).toMatchObject({
      method: "exact_pelt_duration_normalized_transition_rate_huber_v2",
      support: "limited",
      penalty: 1.25,
      objective: 35.76701909,
      bootstrapReplicates: 32,
    });
    expect(pelt?.boundaries).toEqual([]);
    expect(pelt?.reason).toContain("fewer than 64 joint bootstrap rate paths for full support");
    const boundaryResult = normalizePeltAnalysis({ pelt_analysis: {
      method: "exact_pelt_duration_normalized_transition_rate_huber_v2",
      support: "supported",
      penalty: 1.25,
      objective_value: 2.1,
      bootstrap_replicates_used: 64,
      boundaries: [{
        boundary_index: 2,
        left_time_point_id: "synthetic.followup.a",
        right_time_point_id: "synthetic.followup.b",
        cost_reduction: 0.7,
        bootstrap_frequency: 0.75,
      }],
    } });
    expect(boundaryResult?.boundaries).toEqual([{
      index: 2,
      leftTimePointId: "synthetic.followup.a",
      rightTimePointId: "synthetic.followup.b",
      costReduction: 0.7,
      bootstrapFrequency: 0.75,
    }]);
    expect(normalizePeltAnalysis({ pelt_analysis: { support: "unknown" } })).toBeNull();
    expect(normalizePeltAnalysis({})).toBeNull();
    expect(normalizeLongitudinalTransitions({ transitions: [null, { support: "unknown" }] })).toEqual([]);
  });

  it("uses explicit fail-closed defaults for sparse result records", () => {
    const transitions = normalizeLongitudinalTransitions({ transitions: [{
      support: "abstained",
      top_drivers: [null, {}, { gene_symbol: "EGFR" }],
      source_processing_ablations: [null, {}],
      top_driver_ablations: [null, {}],
      abstention_reasons: ["bounded reason", 7],
    }] });
    expect(transitions).toHaveLength(1);
    expect(transitions[0]).toMatchObject({
      id: "unnamed-transition",
      index: 0,
      fromTimePointId: "unknown-from",
      toTimePointId: "unknown-to",
      classification: "not_estimable",
      bootstrapReplicates: 0,
      sharedActiveGenes: 0,
      reasons: ["bounded reason"],
      measurementUncertainty: {
        state: "not_estimable",
        standardError: null,
        varianceFraction: null,
        bootstrapReplicates: 0,
        reason: "",
      },
      coefficientUncertainty: { state: "not_estimable" },
      uncertaintyInteraction: {
        state: "not_estimable",
        method: "paired_bootstrap_covariance_identity_v1",
        covariance: null,
        varianceContribution: null,
        combinedVariance: null,
        decompositionResidual: null,
        bootstrapReplicates: 0,
        reason: "",
      },
    });
    expect(transitions[0].drivers).toEqual([expect.objectContaining({
      geneSymbol: "EGFR",
      sourceGeneLabel: "EGFR",
      direction: "indeterminate",
    })]);
    expect(transitions[0].ablations).toEqual([
      expect.objectContaining({ kind: "source_processing", label: "source-processing alternative" }),
      expect.objectContaining({ kind: "top_driver", label: "top driver" }),
    ]);

    const emptyUncertainty = normalizeLongitudinalTransitions({ transitions: [{
      support: "abstained",
      measurement_uncertainty: {},
      coefficient_uncertainty: {},
      uncertainty_interaction: {},
    }] })[0];
    expect(emptyUncertainty.reasons).toEqual([]);
    expect(emptyUncertainty.measurementUncertainty.bootstrapReplicates).toBe(0);
    expect(emptyUncertainty.coefficientUncertainty.bootstrapReplicates).toBe(0);
    expect(emptyUncertainty.uncertaintyInteraction.bootstrapReplicates).toBe(0);

    const pelt = normalizePeltAnalysis({ pelt_analysis: {
      support: "abstained",
      boundaries: [null, {}],
    } });
    expect(pelt).toMatchObject({
      method: "unknown",
      support: "abstained",
      bootstrapReplicates: 0,
      boundaries: [{
        index: 0,
        leftTimePointId: "unknown-left",
        rightTimePointId: "unknown-right",
        costReduction: null,
        bootstrapFrequency: null,
      }],
      reason: "",
    });
  });
});
