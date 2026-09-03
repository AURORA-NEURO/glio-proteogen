import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";

export const MASTER_KINASE_PROFILE_ID = "sphinks-gbm-master-kinase-concordance/1.0.0";
export const MASTER_KINASE_SUBTYPES = ["GPM", "MTC", "NEU", "PPR"] as const;

export type MasterKinaseSubtype = typeof MASTER_KINASE_SUBTYPES[number];
export type MasterKinaseSupport = "supported" | "limited" | "abstained";

export type MasterKinaseDriver = {
  observationId: string;
  provenanceDigest: string;
  phosphositeId: string;
  effect: number | null;
  state: string;
  weight: number | null;
  locationInfluence: number | null;
  rankInfluence: number | null;
};

export type MasterKinaseAblation = {
  family: string;
  removed: number;
  locationDelta: number | null;
  rankDelta: number | null;
};

export type MasterKinaseEvidence = {
  id: string;
  sourceLabel: string;
  subtype: MasterKinaseSubtype;
  support: MasterKinaseSupport;
  classification: string;
  locationScore: number | null;
  lower: number | null;
  upper: number | null;
  rankScore: number | null;
  pValue: number | null;
  qValue: number | null;
  agreement: string;
  discordance: number | null;
  stability: number | null;
  sourceEdges: number;
  signatureSites: number;
  mappedSites: number;
  activeSites: number;
  coverage: number;
  effectiveSampleSize: number | null;
  bootstrapReplicates: number;
  bootstrapReplicatesSuccessful: number;
  bootstrapReplicatesRequested: number;
  rankBootstrapReplicates: number;
  rankBootstrapReplicatesSuccessful: number;
  rankBootstrapReplicatesRequested: number;
  permutationReplicates: number;
  drivers: MasterKinaseDriver[];
  ablations: MasterKinaseAblation[];
  reasons: string[];
  raw: JsonObject;
};

export type SubtypeKinaseDriver = {
  kinaseId: string;
  contribution: number | null;
  score: number | null;
  weight: number | null;
};

export type MasterKinaseSubtypeAblation = {
  kinaseId: string;
  scoreDelta: number | null;
};

export type MasterKinaseSubtypeEvidence = {
  id: MasterKinaseSubtype;
  support: MasterKinaseSupport;
  classification: string;
  score: number | null;
  lower: number | null;
  upper: number | null;
  effectiveSampleSize: number | null;
  bootstrapReplicates: number;
  bootstrapReplicatesSuccessful: number;
  bootstrapReplicatesRequested: number;
  memberKinases: string[];
  supportedMembers: number;
  estimatedMembers: number;
  discordance: number | null;
  stability: number | null;
  drivers: SubtypeKinaseDriver[];
  ablations: MasterKinaseSubtypeAblation[];
  reasons: string[];
  raw: JsonObject;
};

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const PHOSPHOSITE = /^[A-Za-z0-9][A-Za-z0-9._/+()\-]{0,127}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ROOT_FIELDS = new Set([
  "profile_id",
  "sample_id",
  "observations",
  "bootstrap_replicates",
  "permutation_replicates",
  "contrast_reference",
  "background_mode",
]);
const OBSERVATION_FIELDS = new Set([
  "observation_id",
  "phosphosite_id",
  "state",
  "standardized_effect",
  "standard_error",
  "quality_weight",
  "provenance_digest",
]);
const CONTRAST_FIELDS = new Set([
  "contrast_id",
  "numerator_label",
  "denominator_label",
  "scale",
]);
const ACTIVE_STATES = new Set(["observed", "left_censored"]);
const EVIDENCE_STATES = new Set([...ACTIVE_STATES, "missing", "unsupported"]);
const SUBTYPES = new Set<string>(MASTER_KINASE_SUBTYPES);

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

function validSupport(value: string): value is MasterKinaseSupport {
  return value === "supported" || value === "limited" || value === "abstained";
}

function validSubtype(value: string): value is MasterKinaseSubtype {
  return SUBTYPES.has(value);
}

export function masterKinaseRequestStats(request: JsonObject): {
  observations: number;
  active: number;
  phosphosites: number;
  signatures: number;
} {
  const observations = arrayAt(request, ["observations"]);
  const sites = observations.flatMap((item) => isJsonObject(item) && typeof item.phosphosite_id === "string"
    ? [item.phosphosite_id.trim()]
    : []);
  return {
    observations: observations.length,
    active: observations.filter((item) => isJsonObject(item) && ACTIVE_STATES.has(String(item.state))).length,
    phosphosites: new Set(sites).size,
    signatures: 24,
  };
}

export function validateMasterKinaseRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_FIELDS, "request", errors);

  if (hasOwn(request, "profile_id") && request.profile_id !== MASTER_KINASE_PROFILE_ID) {
    errors.push(`profile_id must equal ${MASTER_KINASE_PROFILE_ID}.`);
  }
  if (typeof request.sample_id !== "string" || !IDENTIFIER.test(request.sample_id)) {
    errors.push("sample_id must be a valid identifier.");
  }

  const values = request.observations;
  const observations = Array.isArray(values) ? values : [];
  if (!Array.isArray(values)) errors.push("observations must be an array.");
  if (!observations.length) errors.push("At least one phosphosite observation is required.");
  if (observations.length > 4_096) errors.push("The request exceeds the 4,096-observation limit.");

  const observationIds: string[] = [];
  const phosphositeIds: string[] = [];
  observations.forEach((value, index) => {
    const path = `observations[${index}]`;
    if (!isJsonObject(value)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    rejectUnknownFields(value, OBSERVATION_FIELDS, path, errors);
    if (typeof value.observation_id !== "string" || !IDENTIFIER.test(value.observation_id)) {
      errors.push(`${path}.observation_id must be a valid identifier.`);
    } else observationIds.push(value.observation_id);
    const phosphositeId = typeof value.phosphosite_id === "string" ? value.phosphosite_id.trim() : "";
    if (!PHOSPHOSITE.test(phosphositeId)) {
      errors.push(`${path}.phosphosite_id must be a valid source phosphosite identifier.`);
    } else phosphositeIds.push(phosphositeId);
    if (typeof value.state !== "string" || !EVIDENCE_STATES.has(value.state)) {
      errors.push(`${path}.state must be one of: observed, left_censored, missing, unsupported.`);
    }
    if (typeof value.provenance_digest !== "string" || !DIGEST.test(value.provenance_digest)) {
      errors.push(`${path}.provenance_digest must be a lowercase sha256 digest.`);
    }
    const effect = finiteNumber(value, "standardized_effect", `${path}.standardized_effect`, -20, 20, errors);
    const standardError = finiteNumber(value, "standard_error", `${path}.standard_error`, 0, 20, errors);
    const quality = hasOwn(value, "quality_weight")
      ? finiteNumber(value, "quality_weight", `${path}.quality_weight`, 0, 1, errors)
      : 1;
    const active = typeof value.state === "string" && ACTIVE_STATES.has(value.state);
    if (active && (effect === null || standardError === null || standardError <= 0 || quality === null || quality <= 0)) {
      errors.push(`${path} active evidence requires an effect, positive standard error, and positive quality weight.`);
    }
    if ((value.state === "missing" || value.state === "unsupported") && (effect !== null || standardError !== null || quality !== 0)) {
      errors.push(`${path} missing/unsupported evidence requires no numeric effect/error and zero quality weight.`);
    }
  });
  const duplicateObservations = duplicates(observationIds);
  if (duplicateObservations.length) errors.push(`Duplicate observation identifiers: ${duplicateObservations.join(", ")}.`);
  const duplicateSites = duplicates(phosphositeIds);
  if (duplicateSites.length) errors.push(`Duplicate phosphosite identifiers: ${duplicateSites.join(", ")}.`);

  const bootstrap = request.bootstrap_replicates;
  if (bootstrap !== undefined && (typeof bootstrap !== "number" || !Number.isInteger(bootstrap) || bootstrap < 16 || bootstrap > 256)) {
    errors.push("bootstrap_replicates must be an integer from 16 through 256.");
  }
  const permutations = request.permutation_replicates;
  if (permutations !== undefined && (typeof permutations !== "number" || !Number.isInteger(permutations) || permutations < 64 || permutations > 2_048)) {
    errors.push("permutation_replicates must be an integer from 64 through 2,048.");
  }

  const contrast = request.contrast_reference;
  if (!isJsonObject(contrast)) {
    errors.push("contrast_reference must be an object.");
  } else {
    rejectUnknownFields(contrast, CONTRAST_FIELDS, "contrast_reference", errors);
    if (typeof contrast.contrast_id !== "string" || !IDENTIFIER.test(contrast.contrast_id)) {
      errors.push("contrast_reference.contrast_id must be a valid identifier.");
    }
    for (const key of ["numerator_label", "denominator_label"] as const) {
      const value = contrast[key];
      if (typeof value !== "string" || value.length < 1 || value.length > 256) {
        errors.push(`contrast_reference.${key} must contain 1–256 characters.`);
      }
    }
    if (
      typeof contrast.numerator_label === "string" &&
      typeof contrast.denominator_label === "string" &&
      contrast.numerator_label === contrast.denominator_label
    ) errors.push("contrast_reference numerator and denominator labels must differ.");
    if (contrast.scale !== "caller_supplied_standardized_log2_contrast") {
      errors.push("contrast_reference.scale must equal caller_supplied_standardized_log2_contrast.");
    }
  }
  if (hasOwn(request, "background_mode") && request.background_mode !== "request_observed_pinned_table5a") {
    errors.push("background_mode must equal request_observed_pinned_table5a.");
  }
  return errors;
}

function normalizeDriver(value: JsonValue): MasterKinaseDriver | null {
  if (!isJsonObject(value)) return null;
  const phosphositeId = textAt(value, ["phosphosite_id", "site_id", "source_site_label"]);
  if (!phosphositeId) return null;
  return {
    observationId: textAt(value, ["observation_id"], "unknown-observation"),
    provenanceDigest: textAt(value, ["observation_provenance_digest"], ""),
    phosphositeId,
    effect: numberAt(value, ["standardized_effect", "effect"]),
    state: textAt(value, ["evidence_state", "state"], "unknown"),
    weight: numberAt(value, ["reliability_weight", "source_svm_weight", "combined_weight", "weight"]),
    locationInfluence: numberAt(value, ["location_influence", "location_contribution", "signed_contribution"]),
    rankInfluence: numberAt(value, ["rank_influence", "rank_contribution"]),
  };
}

function normalizeAblation(value: JsonValue): MasterKinaseAblation | null {
  if (!isJsonObject(value)) return null;
  const family = textAt(value, ["omitted_residue_stratum", "omitted_edge_family", "omitted_family", "family", "omitted"], "unspecified");
  return {
    family,
    removed: numberAt(value, ["unique_sites_removed", "source_edge_rows_removed", "edges_removed", "sites_removed", "removed_count", "markers_removed"]) ?? 0,
    locationDelta: numberAt(value, ["location_delta", "score_delta", "activity_delta"]),
    rankDelta: numberAt(value, ["rank_delta", "enrichment_delta"]),
  };
}

function methodInterval(source: JsonObject | null): { score: number | null; lower: number | null; upper: number | null } {
  return {
    score: source ? numberAt(source, ["score", "estimate", "activity"]) : null,
    lower: source ? numberAt(source, ["lower_bound", "lower", "interval_low"]) : null,
    upper: source ? numberAt(source, ["upper_bound", "upper", "interval_high"]) : null,
  };
}

export function normalizeMasterKinases(result: JsonObject): MasterKinaseEvidence[] {
  return arrayAt(result, ["kinase_evidence"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const subtype = textAt(value, ["source_subtype", "subtype"]);
    const support = textAt(value, ["support"]);
    if (!validSubtype(subtype) || !validSupport(support)) return [];
    const location = objectAt(value, ["location"]);
    const rank = objectAt(value, ["rank_enrichment"]);
    const counts = objectAt(value, ["evidence_counts"]);
    const interval = methodInterval(location);
    return [{
      id: textAt(value, ["kinase_id"], "unnamed-kinase"),
      sourceLabel: textAt(value, ["source_kinase_label"], textAt(value, ["kinase_id"], "unnamed")),
      subtype,
      support,
      classification: textAt(value, ["classification"], "not_estimable"),
      locationScore: interval.score,
      lower: interval.lower,
      upper: interval.upper,
      rankScore: rank ? numberAt(rank, ["score", "enrichment_score"]) : null,
      pValue: rank ? numberAt(rank, ["p_value"]) : null,
      qValue: rank ? numberAt(rank, ["q_value"]) : null,
      agreement: textAt(value, ["method_agreement"], "insufficient"),
      discordance: numberAt(value, ["discordance", "discordance_score"]),
      stability: numberAt(value, ["stability", "bootstrap_stability"]),
      sourceEdges: counts ? numberAt(counts, ["source_signature_edge_rows", "source_edges"]) ?? 0 : 0,
      signatureSites: counts ? numberAt(counts, ["signature_unique_sites", "unique_signature_sites"]) ?? 0 : 0,
      mappedSites: rank ? numberAt(rank, ["mapped_signature_sites"]) ?? 0 : 0,
      activeSites: counts
        ? (numberAt(counts, ["observed_signature_sites"]) ?? 0) + (numberAt(counts, ["left_censored_signature_sites"]) ?? 0)
        : 0,
      coverage: counts ? numberAt(counts, ["active_coverage", "coverage"]) ?? 0 : 0,
      effectiveSampleSize: location ? numberAt(location, ["effective_sample_size"]) : null,
      bootstrapReplicates: location ? numberAt(location, ["bootstrap_replicates_used"]) ?? 0 : 0,
      bootstrapReplicatesSuccessful: location ? numberAt(location, ["bootstrap_replicates_successful", "bootstrap_replicates_used"]) ?? 0 : 0,
      bootstrapReplicatesRequested: location ? numberAt(location, ["bootstrap_replicates_requested", "bootstrap_replicates_used"]) ?? 0 : 0,
      rankBootstrapReplicates: rank ? numberAt(rank, ["bootstrap_replicates_used"]) ?? 0 : 0,
      rankBootstrapReplicatesSuccessful: rank ? numberAt(rank, ["bootstrap_replicates_successful", "bootstrap_replicates_used"]) ?? 0 : 0,
      rankBootstrapReplicatesRequested: rank ? numberAt(rank, ["bootstrap_replicates_requested", "bootstrap_replicates_used"]) ?? 0 : 0,
      permutationReplicates: rank ? numberAt(rank, ["permutation_replicates_used"]) ?? 0 : 0,
      drivers: arrayAt(value, ["top_drivers"]).flatMap((item) => {
        const normalized = normalizeDriver(item);
        return normalized ? [normalized] : [];
      }),
      ablations: arrayAt(value, ["edge_ablations"]).flatMap((item) => {
        const normalized = normalizeAblation(item);
        return normalized ? [normalized] : [];
      }),
      reasons: stringValues(value.abstention_reasons),
      raw: value,
    } satisfies MasterKinaseEvidence];
  });
}

function normalizeSubtypeDriver(value: JsonValue): SubtypeKinaseDriver | null {
  if (!isJsonObject(value)) return null;
  const kinaseId = textAt(value, ["kinase_id"]);
  if (!kinaseId) return null;
  return {
    kinaseId,
    contribution: numberAt(value, ["influence", "contribution", "signed_contribution", "aggregate_contribution"]),
    score: numberAt(value, ["score", "location_score"]),
    weight: numberAt(value, ["aggregation_weight"]),
  };
}

function normalizeSubtypeAblation(value: JsonValue): MasterKinaseSubtypeAblation | null {
  if (!isJsonObject(value)) return null;
  const kinaseId = textAt(value, ["omitted_kinase_id"]);
  if (!kinaseId) return null;
  return { kinaseId, scoreDelta: numberAt(value, ["subtype_score_delta"]) };
}

export function normalizeMasterKinaseSubtypes(result: JsonObject): MasterKinaseSubtypeEvidence[] {
  return arrayAt(result, ["subtype_evidence"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const id = textAt(value, ["subtype_id"]);
    const support = textAt(value, ["support"]);
    if (!validSubtype(id) || !validSupport(support)) return [];
    const aggregate = objectAt(value, ["aggregate"]);
    const interval = methodInterval(aggregate);
    return [{
      id,
      support,
      classification: textAt(value, ["classification"], "not_estimable"),
      score: interval.score,
      lower: interval.lower,
      upper: interval.upper,
      effectiveSampleSize: aggregate ? numberAt(aggregate, ["effective_sample_size"]) : null,
      bootstrapReplicates: aggregate ? numberAt(aggregate, ["bootstrap_replicates_used"]) ?? 0 : 0,
      bootstrapReplicatesSuccessful: aggregate ? numberAt(aggregate, ["bootstrap_replicates_successful", "bootstrap_replicates_used"]) ?? 0 : 0,
      bootstrapReplicatesRequested: aggregate ? numberAt(aggregate, ["bootstrap_replicates_requested", "bootstrap_replicates_used"]) ?? 0 : 0,
      memberKinases: stringValues(value.member_kinases),
      supportedMembers: numberAt(value, ["supported_member_count"]) ?? 0,
      estimatedMembers: numberAt(value, ["estimated_member_count"]) ?? 0,
      discordance: numberAt(value, ["discordance", "discordance_score"]),
      stability: numberAt(value, ["stability", "bootstrap_stability"]),
      drivers: arrayAt(value, ["top_kinases"]).flatMap((item) => {
        const normalized = normalizeSubtypeDriver(item);
        return normalized ? [normalized] : [];
      }),
      ablations: arrayAt(value, ["subtype_ablations"]).flatMap((item) => {
        const normalized = normalizeSubtypeAblation(item);
        return normalized ? [normalized] : [];
      }),
      reasons: stringValues(value.abstention_reasons),
      raw: value,
    } satisfies MasterKinaseSubtypeEvidence];
  });
}
