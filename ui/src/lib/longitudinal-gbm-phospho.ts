import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";

export const LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID =
  "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0";
export const LONGITUDINAL_PHOSPHO_ASSAY_SCHEMA_VERSION =
  "glio-proteogen.kncc-phosphosite-assay-compatibility-attestation/1.0.0";
export const LONGITUDINAL_PHOSPHO_ASSAY_PROFILE_ID =
  "kncc-pdc000515-tmt11-phosphosite-log2-transition/1.0.0";
export const LONGITUDINAL_PHOSPHO_SOURCE_PROFILE_DIGEST =
  "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216";
export const LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST =
  "sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a";

export type PhosphoSupport = "supported" | "limited" | "abstained";

export type PhosphoUncertainty = {
  state: string;
  standardError: number | null;
  variance: number | null;
  varianceFraction: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type PhosphoUncertaintyInteraction = {
  state: string;
  method: string;
  standardError: number | null;
  variance: number | null;
  varianceFraction: number | null;
  measurementCoefficientCovariance: number | null;
  measurementInteractionCovariance: number | null;
  coefficientInteractionCovariance: number | null;
  varianceContribution: number | null;
  combinedVariance: number | null;
  decomposedVariance: number | null;
  decompositionResidual: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type PhosphoDriver = {
  phosphositeId: string;
  geneSymbol: string;
  hgncId: string;
  siteCardinality: number;
  composite: boolean;
  fromObservationId: string;
  toObservationId: string;
  standardizedDelta: number | null;
  coefficient: number | null;
  contribution: number | null;
  direction: string;
  reliability: number | null;
  sourcePairSupport: number | null;
  bootstrapStability: number | null;
  sphinksLabel: string;
  sphinksKinases: string[];
};

export type PhosphoCensoredBound = {
  phosphositeId: string;
  geneSymbol: string;
  semantics: string;
  standardizedBound: number | null;
  weightedBound: number | null;
};

export type PhosphoAblation = {
  kind: "feature_family" | "top_driver";
  label: string;
  omittedCount: number;
  support: string;
  scoreWithout: number | null;
  scoreDelta: number | null;
  classification: string;
  reason: string;
};

export type PhosphoTransition = {
  id: string;
  index: number;
  fromTimePointId: string;
  toTimePointId: string;
  support: PhosphoSupport;
  classification: string;
  score: number | null;
  lower: number | null;
  upper: number | null;
  bootstrapReplicates: number;
  exactFeatureCount: number;
  censoredFeatureCount: number;
  effectiveSampleSize: number | null;
  coefficientCoverage: number | null;
  sourcePairCoverageMean: number | null;
  measurementUncertainty: PhosphoUncertainty;
  coefficientUncertainty: PhosphoUncertainty;
  uncertaintyInteraction: PhosphoUncertaintyInteraction;
  drivers: PhosphoDriver[];
  censoredBounds: PhosphoCensoredBound[];
  ablations: PhosphoAblation[];
  reasons: string[];
  raw: JsonObject;
};

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const PHOSPHOSITE = /^ENSP[0-9]+\.[0-9]+:[sty][0-9]+(?:[sty][0-9]+){0,2}$/;
const GENE_SYMBOL = /^[A-Z0-9][A-Za-z0-9._/-]{0,31}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ACTIVE_STATES = new Set(["observed", "left_censored"]);
const EVIDENCE_STATES = new Set([...ACTIVE_STATES, "missing", "unsupported"]);
const SUPPORT_STATES = new Set<PhosphoSupport>(["supported", "limited", "abstained"]);
const ROOT_FIELDS = new Set([
  "profile_id",
  "series_id",
  "assay_compatibility",
  "normalization_reference",
  "time_points",
  "bootstrap_replicates",
]);
const ASSAY_FIELDS = new Set([
  "schema_version",
  "compatibility_profile_id",
  "source_profile_digest",
  "source_artifact_content_digest",
  "assay",
  "quantification",
  "value_transformation",
  "log_base",
  "feature_identity",
  "composite_site_policy",
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
  "phosphosite_id",
  "gene_symbol",
  "state",
  "log_abundance_ratio",
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

function validSupport(value: string): value is PhosphoSupport {
  return SUPPORT_STATES.has(value as PhosphoSupport);
}

export function longitudinalPhosphoRequestStats(request: JsonObject): {
  timePoints: number;
  observations: number;
  active: number;
  phosphosites: number;
} {
  const timePoints = arrayAt(request, ["time_points"]);
  const observations = timePoints.flatMap((point) => isJsonObject(point)
    ? arrayAt(point, ["observations"])
    : []);
  const sites = observations.flatMap((item) => (
    isJsonObject(item) && typeof item.phosphosite_id === "string" ? [item.phosphosite_id] : []
  ));
  return {
    timePoints: timePoints.length,
    observations: observations.length,
    active: observations.filter((item) => (
      isJsonObject(item) && ACTIVE_STATES.has(String(item.state))
    )).length,
    phosphosites: new Set(sites).size,
  };
}

export function validateLongitudinalPhosphoRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_FIELDS, "request", errors);
  if (hasOwn(request, "profile_id") && request.profile_id !== LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID) {
    errors.push(`profile_id must equal ${LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID}.`);
  }
  if (typeof request.series_id !== "string" || !IDENTIFIER.test(request.series_id)) {
    errors.push("series_id must be a valid identifier.");
  }

  const assay = request.assay_compatibility;
  if (!isJsonObject(assay)) {
    errors.push("assay_compatibility must be an explicit phosphosite compatibility attestation.");
  } else {
    rejectUnknownFields(assay, ASSAY_FIELDS, "assay_compatibility", errors);
    const required: Array<[string, JsonValue]> = [
      ["schema_version", LONGITUDINAL_PHOSPHO_ASSAY_SCHEMA_VERSION],
      ["compatibility_profile_id", LONGITUDINAL_PHOSPHO_ASSAY_PROFILE_ID],
      ["source_profile_digest", LONGITUDINAL_PHOSPHO_SOURCE_PROFILE_DIGEST],
      ["source_artifact_content_digest", LONGITUDINAL_PHOSPHO_ARTIFACT_DIGEST],
      ["assay", "tmt11_plexed_phosphoproteome_mass_spectrometry"],
      ["quantification", "phosphosite_sample_to_reference_abundance_ratio"],
      ["value_transformation", "log2_ratio"],
      ["log_base", 2],
      ["feature_identity", "exact_ensp_versioned_source_site_group"],
      ["composite_site_policy", "indivisible_source_site_group"],
      ["invariant_across_time_points", true],
      ["attested_compatible", true],
    ];
    required.forEach(([field, expected]) => {
      if (!hasOwn(assay, field) || assay[field] !== expected) {
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
    if (hasOwn(reference, "abundance_scale") && reference.abundance_scale !== "caller_supplied_log2_phosphosite_abundance_ratio") {
      errors.push("normalization_reference.abundance_scale must equal caller_supplied_log2_phosphosite_abundance_ratio.");
    }
    if (hasOwn(reference, "invariant_across_time_points") && reference.invariant_across_time_points !== true) {
      errors.push("normalization_reference.invariant_across_time_points must be true.");
    }
  }

  const rawPoints = request.time_points;
  const points = Array.isArray(rawPoints) ? rawPoints : [];
  if (!Array.isArray(rawPoints)) errors.push("time_points must be an array.");
  if (points.length < 2 || points.length > 16) {
    errors.push("time_points must contain 2 through 16 ordered entries.");
  }
  const timePointIds: string[] = [];
  const observationIds: string[] = [];
  const offsets: number[] = [];
  let totalObservations = 0;
  points.forEach((rawPoint, pointIndex) => {
    const path = `time_points[${pointIndex}]`;
    if (!isJsonObject(rawPoint)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    rejectUnknownFields(rawPoint, TIME_POINT_FIELDS, path, errors);
    if (typeof rawPoint.time_point_id !== "string" || !IDENTIFIER.test(rawPoint.time_point_id)) {
      errors.push(`${path}.time_point_id must be a valid identifier.`);
    } else timePointIds.push(rawPoint.time_point_id);
    const offset = finiteNumber(rawPoint, "time_offset_days", `${path}.time_offset_days`, 0, Number.MAX_SAFE_INTEGER, errors);
    if (offset !== null) offsets.push(offset);
    if (typeof rawPoint.normalization_reference_digest !== "string" || !DIGEST.test(rawPoint.normalization_reference_digest)) {
      errors.push(`${path}.normalization_reference_digest must be a lowercase sha256 digest.`);
    } else if (bindingDigest && rawPoint.normalization_reference_digest !== bindingDigest) {
      errors.push(`${path}.normalization_reference_digest must match the invariant reference binding.`);
    }

    const rawObservations = rawPoint.observations;
    const observations = Array.isArray(rawObservations) ? rawObservations : [];
    if (!Array.isArray(rawObservations)) errors.push(`${path}.observations must be an array.`);
    if (!observations.length || observations.length > 4_096) {
      errors.push(`${path}.observations must contain 1 through 4,096 entries.`);
    }
    totalObservations += observations.length;
    const pointSites: string[] = [];
    observations.forEach((rawObservation, observationIndex) => {
      const observationPath = `${path}.observations[${observationIndex}]`;
      if (!isJsonObject(rawObservation)) {
        errors.push(`${observationPath} must be an object.`);
        return;
      }
      rejectUnknownFields(rawObservation, OBSERVATION_FIELDS, observationPath, errors);
      if (typeof rawObservation.observation_id !== "string" || !IDENTIFIER.test(rawObservation.observation_id)) {
        errors.push(`${observationPath}.observation_id must be a valid identifier.`);
      } else observationIds.push(rawObservation.observation_id);
      if (typeof rawObservation.phosphosite_id !== "string" || !PHOSPHOSITE.test(rawObservation.phosphosite_id)) {
        errors.push(`${observationPath}.phosphosite_id must be an exact ENSP-versioned source site group.`);
      } else pointSites.push(rawObservation.phosphosite_id);
      if (typeof rawObservation.gene_symbol !== "string" || !GENE_SYMBOL.test(rawObservation.gene_symbol)) {
        errors.push(`${observationPath}.gene_symbol must be a valid HGNC symbol.`);
      }
      if (typeof rawObservation.state !== "string" || !EVIDENCE_STATES.has(rawObservation.state)) {
        errors.push(`${observationPath}.state must be observed, left_censored, missing, or unsupported.`);
      }
      if (typeof rawObservation.provenance_digest !== "string" || !DIGEST.test(rawObservation.provenance_digest)) {
        errors.push(`${observationPath}.provenance_digest must be a lowercase sha256 digest.`);
      }
      const abundance = finiteNumber(rawObservation, "log_abundance_ratio", `${observationPath}.log_abundance_ratio`, -100, 100, errors);
      const standardError = finiteNumber(rawObservation, "standard_error", `${observationPath}.standard_error`, 0, 20, errors);
      const quality = hasOwn(rawObservation, "quality_weight")
        ? finiteNumber(rawObservation, "quality_weight", `${observationPath}.quality_weight`, 0, 1, errors)
        : 1;
      const active = typeof rawObservation.state === "string" && ACTIVE_STATES.has(rawObservation.state);
      if (active && (abundance === null || standardError === null || standardError <= 0 || quality === null || quality <= 0)) {
        errors.push(`${observationPath} active evidence requires a value, positive error, and positive quality.`);
      }
      if (!active && (abundance !== null || standardError !== null || quality !== 0)) {
        errors.push(`${observationPath} missing/unsupported evidence requires no value/error and zero quality.`);
      }
    });
    const duplicateSites = duplicates(pointSites);
    if (duplicateSites.length) {
      errors.push(`${path} contains duplicate phosphosite groups: ${duplicateSites.join(", ")}.`);
    }
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
  if (bootstrap !== undefined && (typeof bootstrap !== "number" || !Number.isInteger(bootstrap) || bootstrap < 32 || bootstrap > 64)) {
    errors.push("bootstrap_replicates must be an integer from 32 through 64.");
  }
  return errors;
}

function normalizeUncertainty(value: JsonObject | null): PhosphoUncertainty {
  return {
    state: value ? textAt(value, ["state"], "not_estimable") : "not_estimable",
    standardError: value ? numberAt(value, ["standard_error"]) : null,
    variance: value ? numberAt(value, ["variance"]) : null,
    varianceFraction: value ? numberAt(value, ["variance_fraction"]) : null,
    bootstrapReplicates: value ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0 : 0,
    reason: value ? textAt(value, ["reason"]) : "",
  };
}

function normalizeInteraction(value: JsonObject | null): PhosphoUncertaintyInteraction {
  return {
    state: value ? textAt(value, ["state"], "not_estimable") : "not_estimable",
    method: value ? textAt(value, ["method"]) : "",
    standardError: value ? numberAt(value, ["interaction_standard_error"]) : null,
    variance: value ? numberAt(value, ["interaction_variance"]) : null,
    varianceFraction: value ? numberAt(value, ["interaction_variance_fraction"]) : null,
    measurementCoefficientCovariance: value ? numberAt(value, ["measurement_coefficient_covariance"]) : null,
    measurementInteractionCovariance: value ? numberAt(value, ["measurement_interaction_covariance"]) : null,
    coefficientInteractionCovariance: value ? numberAt(value, ["coefficient_interaction_covariance"]) : null,
    varianceContribution: value ? numberAt(value, ["variance_contribution"]) : null,
    combinedVariance: value ? numberAt(value, ["combined_variance"]) : null,
    decomposedVariance: value ? numberAt(value, ["decomposed_variance"]) : null,
    decompositionResidual: value ? numberAt(value, ["decomposition_residual"]) : null,
    bootstrapReplicates: value ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0 : 0,
    reason: value ? textAt(value, ["reason"]) : "",
  };
}

function normalizeDriver(value: JsonValue): PhosphoDriver | null {
  if (!isJsonObject(value)) return null;
  const phosphositeId = textAt(value, ["phosphosite_id"]);
  if (!phosphositeId) return null;
  return {
    phosphositeId,
    geneSymbol: textAt(value, ["gene_symbol"], "—"),
    hgncId: textAt(value, ["hgnc_id"]),
    siteCardinality: numberAt(value, ["site_cardinality"]) ?? 1,
    composite: value.composite_site_group === true,
    fromObservationId: textAt(value, ["from_observation_id"]),
    toObservationId: textAt(value, ["to_observation_id"]),
    standardizedDelta: numberAt(value, ["standardized_delta"]),
    coefficient: numberAt(value, ["model_coefficient"]),
    contribution: numberAt(value, ["signed_contribution"]),
    direction: textAt(value, ["direction"], "indeterminate"),
    reliability: numberAt(value, ["reliability_weight"]),
    sourcePairSupport: numberAt(value, ["source_pair_support"]),
    bootstrapStability: numberAt(value, ["bootstrap_selection_stability"]),
    sphinksLabel: textAt(value, ["sphinks_source_site_label"]),
    sphinksKinases: stringValues(value.sphinks_signature_kinases),
  };
}

function normalizeCensoredBound(value: JsonValue): PhosphoCensoredBound | null {
  if (!isJsonObject(value)) return null;
  const phosphositeId = textAt(value, ["phosphosite_id"]);
  if (!phosphositeId) return null;
  return {
    phosphositeId,
    geneSymbol: textAt(value, ["gene_symbol"], "—"),
    semantics: textAt(value, ["value_semantics"], "bound"),
    standardizedBound: numberAt(value, ["standardized_bound"]),
    weightedBound: numberAt(value, ["coefficient_weighted_bound"]),
  };
}

function normalizeAblation(value: JsonValue, kind: PhosphoAblation["kind"]): PhosphoAblation | null {
  if (!isJsonObject(value)) return null;
  const label = kind === "feature_family"
    ? textAt(value, ["component"], "feature family")
    : textAt(value, ["omitted_phosphosite_id"], "top phosphosite driver");
  return {
    kind,
    label,
    omittedCount: kind === "feature_family" ? numberAt(value, ["omitted_feature_count"]) ?? 0 : 1,
    support: textAt(value, ["support"], "abstained"),
    scoreWithout: numberAt(value, ["score_without_component"]),
    scoreDelta: numberAt(value, ["score_delta"]),
    classification: textAt(value, ["classification_without_component"], "not_estimable"),
    reason: textAt(value, ["reason"]),
  };
}

export function normalizeLongitudinalPhosphoTransitions(result: JsonObject): PhosphoTransition[] {
  return arrayAt(result, ["transitions"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const support = textAt(value, ["support"]);
    if (!validSupport(support)) return [];
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
      exactFeatureCount: numberAt(value, ["exact_feature_count"]) ?? 0,
      censoredFeatureCount: numberAt(value, ["censored_feature_count"]) ?? 0,
      effectiveSampleSize: numberAt(value, ["effective_sample_size"]),
      coefficientCoverage: numberAt(value, ["coefficient_weight_coverage"]),
      sourcePairCoverageMean: numberAt(value, ["source_pair_coverage_weighted_mean"]),
      measurementUncertainty: normalizeUncertainty(objectAt(value, ["measurement_uncertainty"])),
      coefficientUncertainty: normalizeUncertainty(objectAt(value, ["coefficient_uncertainty"])),
      uncertaintyInteraction: normalizeInteraction(objectAt(value, ["uncertainty_interaction"])),
      drivers: arrayAt(value, ["top_drivers"]).flatMap((item) => normalizeDriver(item) ?? []),
      censoredBounds: arrayAt(value, ["censored_bounds"]).flatMap((item) => normalizeCensoredBound(item) ?? []),
      ablations: [
        ...arrayAt(value, ["feature_family_ablations"]).flatMap((item) => normalizeAblation(item, "feature_family") ?? []),
        ...arrayAt(value, ["top_driver_ablations"]).flatMap((item) => normalizeAblation(item, "top_driver") ?? []),
      ],
      reasons: stringValues(value.abstention_reasons),
      raw: value,
    }];
  });
}

export function normalizePhosphoModelViews(result: JsonObject): Array<{
  view: string;
  support: string;
  reason: string;
}> {
  return arrayAt(result, ["model_views"]).flatMap((value) => isJsonObject(value) ? [{
    view: textAt(value, ["view"], "unknown"),
    support: textAt(value, ["support"], "not_fitted"),
    reason: textAt(value, ["reason"]),
  }] : []);
}
