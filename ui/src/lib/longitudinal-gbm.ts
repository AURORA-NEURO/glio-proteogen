import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";

export const LONGITUDINAL_GBM_PROFILE_ID = "kncc-gbm-longitudinal-concordance/1.0.0";
export const LONGITUDINAL_ASSAY_SCHEMA_VERSION = "glio-proteogen.kncc-assay-compatibility-attestation/1.0.0";
export const LONGITUDINAL_ASSAY_PROFILE_ID = "kncc-pdc000514-tmt11-unshared-log2-ratio/1.0.0";
export const LONGITUDINAL_SOURCE_PROFILE_DIGEST = "sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3";

export type LongitudinalSupport = "supported" | "limited" | "abstained";

export type LongitudinalUncertainty = {
  state: string;
  standardError: number | null;
  varianceFraction: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type LongitudinalUncertaintyInteraction = {
  state: string;
  method: string;
  covariance: number | null;
  varianceContribution: number | null;
  combinedVariance: number | null;
  decompositionResidual: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type LongitudinalDriver = {
  geneSymbol: string;
  sourceGeneLabel: string;
  fromObservationId: string;
  toObservationId: string;
  standardizedDelta: number | null;
  coefficient: number | null;
  contribution: number | null;
  direction: string;
  reliabilityWeight: number | null;
  sourceFeatureSupport: number | null;
};

export type LongitudinalAblation = {
  kind: "source_processing" | "top_driver";
  label: string;
  support: string;
  scoreWithout: number | null;
  scoreDelta: number | null;
  classification: string;
  reason: string;
  omittedContribution: number | null;
};

export type LongitudinalTransition = {
  id: string;
  index: number;
  fromTimePointId: string;
  toTimePointId: string;
  support: LongitudinalSupport;
  classification: string;
  score: number | null;
  lower: number | null;
  upper: number | null;
  bootstrapReplicates: number;
  sharedActiveGenes: number;
  effectiveSampleSize: number | null;
  coverage: number | null;
  sourceSupportPercentile: number | null;
  measurementUncertainty: LongitudinalUncertainty;
  coefficientUncertainty: LongitudinalUncertainty;
  uncertaintyInteraction: LongitudinalUncertaintyInteraction;
  drivers: LongitudinalDriver[];
  ablations: LongitudinalAblation[];
  reasons: string[];
  raw: JsonObject;
};

export type PeltBoundaryEvidence = {
  index: number;
  leftTimePointId: string;
  rightTimePointId: string;
  costReduction: number | null;
  bootstrapFrequency: number | null;
};

export type PeltEvidence = {
  method: string;
  support: LongitudinalSupport;
  penalty: number | null;
  objective: number | null;
  bootstrapReplicates: number;
  boundaries: PeltBoundaryEvidence[];
  reason: string;
  raw: JsonObject;
};

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const GENE_SYMBOL = /^[A-Z0-9][A-Z0-9._/-]{0,31}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ACTIVE_STATES = new Set(["observed", "left_censored"]);
const EVIDENCE_STATES = new Set([...ACTIVE_STATES, "missing", "unsupported"]);
const SUPPORT_STATES = new Set<LongitudinalSupport>(["supported", "limited", "abstained"]);
const ROOT_FIELDS = new Set([
  "profile_id",
  "series_id",
  "assay_compatibility",
  "normalization_reference",
  "time_points",
  "bootstrap_replicates",
]);
const ASSAY_COMPATIBILITY_FIELDS = new Set([
  "schema_version",
  "compatibility_profile_id",
  "source_profile_content_digest",
  "assay",
  "quantification",
  "value_transformation",
  "log_base",
  "invariant_across_time_points",
  "attested_compatible",
]);
const REFERENCE_FIELDS = new Set([
  "reference_id",
  "binding_digest",
  "normalization_method",
  "abundance_scale",
  "invariant_across_time_points",
]);
const TIME_POINT_FIELDS = new Set([
  "time_point_id",
  "time_offset_days",
  "normalization_reference_digest",
  "observations",
]);
const OBSERVATION_FIELDS = new Set([
  "observation_id",
  "gene_symbol",
  "state",
  "log_abundance",
  "standard_error",
  "quality_weight",
  "provenance_digest",
]);

function hasOwn(source: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

function rejectUnknownFields(
  source: JsonObject,
  allowed: ReadonlySet<string>,
  path: string,
  errors: string[],
): void {
  const unknown = Object.keys(source).filter((key) => !allowed.has(key));
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function finiteNumber(
  source: JsonObject,
  key: string,
  path: string,
  minimum: number,
  maximum: number,
  errors: string[],
): number | null {
  const value = source[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    errors.push(`${path} must be a finite number within [${minimum}, ${maximum}] or null.`);
    return null;
  }
  return value;
}

function duplicates(values: string[]): string[] {
  return [...new Set(values.filter((value, index) => values.indexOf(value) !== index))];
}

function stringValues(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function validSupport(value: string): value is LongitudinalSupport {
  return SUPPORT_STATES.has(value as LongitudinalSupport);
}

export function longitudinalRequestStats(request: JsonObject): {
  timePoints: number;
  observations: number;
  active: number;
  genes: number;
} {
  const timePoints = arrayAt(request, ["time_points"]);
  const observations = timePoints.flatMap((point) => isJsonObject(point)
    ? arrayAt(point, ["observations"])
    : []);
  const genes = observations.flatMap((item) => isJsonObject(item) && typeof item.gene_symbol === "string"
    ? [item.gene_symbol]
    : []);
  return {
    timePoints: timePoints.length,
    observations: observations.length,
    active: observations.filter((item) => isJsonObject(item) && ACTIVE_STATES.has(String(item.state))).length,
    genes: new Set(genes).size,
  };
}

export function validateLongitudinalRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_FIELDS, "request", errors);
  if (hasOwn(request, "profile_id") && request.profile_id !== LONGITUDINAL_GBM_PROFILE_ID) {
    errors.push(`profile_id must equal ${LONGITUDINAL_GBM_PROFILE_ID}.`);
  }
  if (typeof request.series_id !== "string" || !IDENTIFIER.test(request.series_id)) {
    errors.push("series_id must be a valid identifier.");
  }

  const assayCompatibility = request.assay_compatibility;
  if (!isJsonObject(assayCompatibility)) {
    errors.push("assay_compatibility must be an explicit compatibility attestation object.");
  } else {
    rejectUnknownFields(assayCompatibility, ASSAY_COMPATIBILITY_FIELDS, "assay_compatibility", errors);
    const requiredFields: Array<[string, JsonValue]> = [
      ["schema_version", LONGITUDINAL_ASSAY_SCHEMA_VERSION],
      ["compatibility_profile_id", LONGITUDINAL_ASSAY_PROFILE_ID],
      ["source_profile_content_digest", LONGITUDINAL_SOURCE_PROFILE_DIGEST],
      ["assay", "tmt11_plexed_mass_spectrometry"],
      ["quantification", "unshared_peptide_protein_abundance_ratio"],
      ["value_transformation", "log2_ratio"],
      ["log_base", 2],
      ["invariant_across_time_points", true],
      ["attested_compatible", true],
    ];
    requiredFields.forEach(([field, expected]) => {
      if (!hasOwn(assayCompatibility, field) || assayCompatibility[field] !== expected) {
        errors.push(`assay_compatibility.${field} must exactly equal ${JSON.stringify(expected)}.`);
      }
    });
  }

  const reference = request.normalization_reference;
  let bindingDigest = "";
  if (!isJsonObject(reference)) {
    errors.push("normalization_reference must be an object.");
  } else {
    rejectUnknownFields(reference, REFERENCE_FIELDS, "normalization_reference", errors);
    if (typeof reference.reference_id !== "string" || !IDENTIFIER.test(reference.reference_id)) {
      errors.push("normalization_reference.reference_id must be a valid identifier.");
    }
    if (typeof reference.binding_digest !== "string" || !DIGEST.test(reference.binding_digest)) {
      errors.push("normalization_reference.binding_digest must be a lowercase sha256 digest.");
    } else bindingDigest = reference.binding_digest;
    if (typeof reference.normalization_method !== "string" || !reference.normalization_method.trim()) {
      errors.push("normalization_reference.normalization_method must be non-empty.");
    }
    if (hasOwn(reference, "abundance_scale") && reference.abundance_scale !== "caller_supplied_log2_protein_abundance_ratio") {
      errors.push("normalization_reference.abundance_scale must equal caller_supplied_log2_protein_abundance_ratio.");
    }
    if (hasOwn(reference, "invariant_across_time_points") && reference.invariant_across_time_points !== true) {
      errors.push("normalization_reference.invariant_across_time_points must be true.");
    }
  }

  const pointsValue = request.time_points;
  const points = Array.isArray(pointsValue) ? pointsValue : [];
  if (!Array.isArray(pointsValue)) errors.push("time_points must be an array.");
  if (points.length < 2 || points.length > 16) errors.push("time_points must contain 2 through 16 ordered entries.");

  const timePointIds: string[] = [];
  const observationIds: string[] = [];
  const offsets: number[] = [];
  let totalObservations = 0;
  points.forEach((pointValue, pointIndex) => {
    const path = `time_points[${pointIndex}]`;
    if (!isJsonObject(pointValue)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    rejectUnknownFields(pointValue, TIME_POINT_FIELDS, path, errors);
    if (typeof pointValue.time_point_id !== "string" || !IDENTIFIER.test(pointValue.time_point_id)) {
      errors.push(`${path}.time_point_id must be a valid identifier.`);
    } else timePointIds.push(pointValue.time_point_id);
    const offset = finiteNumber(pointValue, "time_offset_days", `${path}.time_offset_days`, 0, Number.MAX_SAFE_INTEGER, errors);
    if (offset !== null) offsets.push(offset);
    if (typeof pointValue.normalization_reference_digest !== "string" || !DIGEST.test(pointValue.normalization_reference_digest)) {
      errors.push(`${path}.normalization_reference_digest must be a lowercase sha256 digest.`);
    } else if (bindingDigest && pointValue.normalization_reference_digest !== bindingDigest) {
      errors.push(`${path}.normalization_reference_digest must match the invariant reference binding.`);
    }

    const observationsValue = pointValue.observations;
    const observations = Array.isArray(observationsValue) ? observationsValue : [];
    if (!Array.isArray(observationsValue)) errors.push(`${path}.observations must be an array.`);
    if (!observations.length || observations.length > 4_096) {
      errors.push(`${path}.observations must contain 1 through 4,096 entries.`);
    }
    totalObservations += observations.length;
    const pointGenes: string[] = [];
    observations.forEach((observationValue, observationIndex) => {
      const observationPath = `${path}.observations[${observationIndex}]`;
      if (!isJsonObject(observationValue)) {
        errors.push(`${observationPath} must be an object.`);
        return;
      }
      rejectUnknownFields(observationValue, OBSERVATION_FIELDS, observationPath, errors);
      if (typeof observationValue.observation_id !== "string" || !IDENTIFIER.test(observationValue.observation_id)) {
        errors.push(`${observationPath}.observation_id must be a valid identifier.`);
      } else observationIds.push(observationValue.observation_id);
      if (typeof observationValue.gene_symbol !== "string" || !GENE_SYMBOL.test(observationValue.gene_symbol)) {
        errors.push(`${observationPath}.gene_symbol must be a valid HGNC-style symbol.`);
      } else pointGenes.push(observationValue.gene_symbol);
      if (typeof observationValue.state !== "string" || !EVIDENCE_STATES.has(observationValue.state)) {
        errors.push(`${observationPath}.state must be one of: observed, left_censored, missing, unsupported.`);
      }
      if (typeof observationValue.provenance_digest !== "string" || !DIGEST.test(observationValue.provenance_digest)) {
        errors.push(`${observationPath}.provenance_digest must be a lowercase sha256 digest.`);
      }
      const abundance = finiteNumber(observationValue, "log_abundance", `${observationPath}.log_abundance`, -100, 100, errors);
      const standardError = finiteNumber(observationValue, "standard_error", `${observationPath}.standard_error`, 0, 20, errors);
      const quality = hasOwn(observationValue, "quality_weight")
        ? finiteNumber(observationValue, "quality_weight", `${observationPath}.quality_weight`, 0, 1, errors)
        : 1;
      const active = typeof observationValue.state === "string" && ACTIVE_STATES.has(observationValue.state);
      if (active && (abundance === null || standardError === null || standardError <= 0 || quality === null || quality <= 0)) {
        errors.push(`${observationPath} active evidence requires abundance, positive error, and positive quality.`);
      }
      if ((observationValue.state === "missing" || observationValue.state === "unsupported") && (abundance !== null || standardError !== null || quality !== 0)) {
        errors.push(`${observationPath} missing/unsupported evidence requires no abundance/error and zero quality.`);
      }
    });
    const duplicateGenes = duplicates(pointGenes);
    if (duplicateGenes.length) errors.push(`${path} contains duplicate gene symbols: ${duplicateGenes.join(", ")}.`);
  });

  if (totalObservations > 12_000) errors.push("The request exceeds the 12,000-observation series limit.");
  const duplicatePoints = duplicates(timePointIds);
  if (duplicatePoints.length) errors.push(`Duplicate time-point identifiers: ${duplicatePoints.join(", ")}.`);
  const duplicateObservations = duplicates(observationIds);
  if (duplicateObservations.length) errors.push(`Duplicate observation identifiers: ${duplicateObservations.join(", ")}.`);
  if (offsets.length === points.length && offsets.some((offset, index) => index > 0 && offsets[index - 1] >= offset)) {
    errors.push("time_points must be strictly increasing by time_offset_days in request order.");
  }
  const bootstrap = request.bootstrap_replicates;
  if (bootstrap !== undefined && (typeof bootstrap !== "number" || !Number.isInteger(bootstrap) || bootstrap < 32 || bootstrap > 256)) {
    errors.push("bootstrap_replicates must be an integer from 32 through 256.");
  }
  return errors;
}

function normalizeUncertainty(value: JsonObject | null): LongitudinalUncertainty {
  return {
    state: value ? textAt(value, ["state"], "not_estimable") : "not_estimable",
    standardError: value ? numberAt(value, ["standard_error"]) : null,
    varianceFraction: value ? numberAt(value, ["variance_fraction"]) : null,
    bootstrapReplicates: value ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0 : 0,
    reason: value ? textAt(value, ["reason"]) : "",
  };
}

function normalizeUncertaintyInteraction(value: JsonObject | null): LongitudinalUncertaintyInteraction {
  return {
    state: value ? textAt(value, ["state"], "not_estimable") : "not_estimable",
    method: value ? textAt(value, ["method"], "paired_bootstrap_covariance_identity_v1") : "paired_bootstrap_covariance_identity_v1",
    covariance: value ? numberAt(value, ["covariance"]) : null,
    varianceContribution: value ? numberAt(value, ["variance_contribution"]) : null,
    combinedVariance: value ? numberAt(value, ["combined_variance"]) : null,
    decompositionResidual: value ? numberAt(value, ["decomposition_residual"]) : null,
    bootstrapReplicates: value ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0 : 0,
    reason: value ? textAt(value, ["reason"]) : "",
  };
}

function normalizeDriver(value: JsonValue): LongitudinalDriver | null {
  if (!isJsonObject(value)) return null;
  const geneSymbol = textAt(value, ["gene_symbol"]);
  if (!geneSymbol) return null;
  return {
    geneSymbol,
    sourceGeneLabel: textAt(value, ["source_gene_label"], geneSymbol),
    fromObservationId: textAt(value, ["from_observation_id"]),
    toObservationId: textAt(value, ["to_observation_id"]),
    standardizedDelta: numberAt(value, ["standardized_delta"]),
    coefficient: numberAt(value, ["model_coefficient"]),
    contribution: numberAt(value, ["signed_contribution"]),
    direction: textAt(value, ["direction"], "indeterminate"),
    reliabilityWeight: numberAt(value, ["reliability_weight"]),
    sourceFeatureSupport: numberAt(value, ["source_feature_support"]),
  };
}

function normalizeAblation(value: JsonValue, kind: LongitudinalAblation["kind"]): LongitudinalAblation | null {
  if (!isJsonObject(value)) return null;
  const label = kind === "source_processing"
    ? textAt(value, ["comparison"], "source-processing alternative")
    : textAt(value, ["omitted_gene_symbol"], "top driver");
  return {
    kind,
    label,
    support: textAt(value, ["support"], "abstained"),
    scoreWithout: numberAt(value, ["score_without_component"]),
    scoreDelta: numberAt(value, ["score_delta"]),
    classification: textAt(value, ["classification_without_component"], "not_estimable"),
    reason: textAt(value, ["reason"]),
    omittedContribution: numberAt(value, ["omitted_signed_contribution"]),
  };
}

export function normalizeLongitudinalTransitions(result: JsonObject): LongitudinalTransition[] {
  return arrayAt(result, ["transitions"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const support = textAt(value, ["support"]);
    if (!validSupport(support)) return [];
    const sourceProcessing = arrayAt(value, ["source_processing_ablations"])
      .flatMap((item) => normalizeAblation(item, "source_processing") ?? []);
    const topDriver = arrayAt(value, ["top_driver_ablations"])
      .flatMap((item) => normalizeAblation(item, "top_driver") ?? []);
    return [{
      id: textAt(value, ["transition_id"], "unnamed-transition"),
      index: numberAt(value, ["transition_index"]) ?? 0,
      fromTimePointId: textAt(value, ["from_time_point_id"], "unknown-from"),
      toTimePointId: textAt(value, ["to_time_point_id"], "unknown-to"),
      support,
      classification: textAt(value, ["classification"], "not_estimable"),
      score: numberAt(value, ["score"]),
      lower: numberAt(value, ["lower_bound"]),
      upper: numberAt(value, ["upper_bound"]),
      bootstrapReplicates: numberAt(value, ["bootstrap_replicates_used"]) ?? 0,
      sharedActiveGenes: numberAt(value, ["shared_active_gene_count"]) ?? 0,
      effectiveSampleSize: numberAt(value, ["effective_sample_size"]),
      coverage: numberAt(value, ["coverage"]),
      sourceSupportPercentile: numberAt(value, ["source_support_percentile"]),
      measurementUncertainty: normalizeUncertainty(objectAt(value, ["measurement_uncertainty"])),
      coefficientUncertainty: normalizeUncertainty(objectAt(value, ["coefficient_uncertainty"])),
      uncertaintyInteraction: normalizeUncertaintyInteraction(objectAt(value, ["uncertainty_interaction"])),
      drivers: arrayAt(value, ["top_drivers"]).flatMap((item) => normalizeDriver(item) ?? []),
      ablations: [...sourceProcessing, ...topDriver],
      reasons: stringValues(value.abstention_reasons),
      raw: value,
    }];
  });
}

export function normalizePeltAnalysis(result: JsonObject): PeltEvidence | null {
  const value = objectAt(result, ["pelt_analysis"]);
  if (!value) return null;
  const support = textAt(value, ["support"]);
  if (!validSupport(support)) return null;
  return {
    method: textAt(value, ["method"], "unknown"),
    support,
    penalty: numberAt(value, ["penalty"]),
    objective: numberAt(value, ["objective_value"]),
    bootstrapReplicates: numberAt(value, ["bootstrap_replicates_used"]) ?? 0,
    boundaries: arrayAt(value, ["boundaries"]).flatMap((boundary) => {
      if (!isJsonObject(boundary)) return [];
      return [{
        index: numberAt(boundary, ["boundary_index"]) ?? 0,
        leftTimePointId: textAt(boundary, ["left_time_point_id"], "unknown-left"),
        rightTimePointId: textAt(boundary, ["right_time_point_id"], "unknown-right"),
        costReduction: numberAt(boundary, ["cost_reduction"]),
        bootstrapFrequency: numberAt(boundary, ["bootstrap_frequency"]),
      }];
    }),
    reason: textAt(value, ["reason"]),
    raw: value,
  };
}
