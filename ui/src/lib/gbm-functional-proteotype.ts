import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";

export const FUNCTIONAL_PROTEOTYPE_PROFILE_ID = "migliozzi-gbm-functional-proteotype/1.0.0";
export const FUNCTIONAL_PROTEOTYPE_AXES = ["GPM", "MTC", "NEU", "PPR"] as const;

export type FunctionalProteotypeAxis = typeof FUNCTIONAL_PROTEOTYPE_AXES[number];
export type FunctionalProteotypeSupport = "supported" | "limited" | "abstained";
export type FunctionalProteotypeClassification =
  | "source_aligned"
  | "source_opposed"
  | "neutral"
  | "indeterminate"
  | "not_estimable";

export type FunctionalProteotypeDriver = {
  observationId: string;
  geneSymbol: string;
  sourceProteinLabel: string;
  sourceRank: number;
  sourceRankQuartile: number;
  sourceMwwScore: number | null;
  evidenceState: string;
  valueRole: string;
  effect: number | null;
  reliabilityWeight: number | null;
  sourceLoading: number | null;
  signedContribution: number | null;
  absoluteContribution: number | null;
};

export type FunctionalProteotypeAblation = {
  kind: string;
  target: string;
  proteinsRemoved: number;
  support: FunctionalProteotypeSupport;
  baselineEstimate: number | null;
  estimate: number | null;
  delta: number | null;
  classification: FunctionalProteotypeClassification;
  reason: string;
};

export type FunctionalProteotypePathwayContext = {
  axis: FunctionalProteotypeAxis;
  sourceRank: number;
  pathwayName: string;
  sourceLogitNes: number | null;
  sourcePValue: number | null;
  sourceQValue: number | null;
  sampleInferenceStatus: "not_evaluated";
  interpretation: string;
};

export type FunctionalProteotypeEvidenceCounts = {
  sourceSignatureProteins: number;
  declared: number;
  observed: number;
  leftCensored: number;
  missing: number;
  unsupported: number;
  unreported: number;
  observedBackground: number;
  activeFraction: number;
};

export type FunctionalProteotypeAxisEvidence = {
  axis: FunctionalProteotypeAxis;
  support: FunctionalProteotypeSupport;
  classification: FunctionalProteotypeClassification;
  estimate: number | null;
  lower: number | null;
  upper: number | null;
  bootstrapReplicates: number;
  signatureObservedCount: number;
  complementObservedCount: number;
  uStatistic: number | null;
  rankBiserial: number | null;
  tieCorrection: number | null;
  pValue: number | null;
  qValue: number | null;
  permutationReplicates: number;
  counts: FunctionalProteotypeEvidenceCounts;
  effectiveSampleSize: number | null;
  stability: number | null;
  discordance: number | null;
  drivers: FunctionalProteotypeDriver[];
  ablations: FunctionalProteotypeAblation[];
  pathways: FunctionalProteotypePathwayContext[];
  reasons: string[];
  raw: JsonObject;
};

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const GENE_SYMBOL = /^[A-Za-z0-9][A-Za-z0-9.-]{0,31}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ROOT_FIELDS = new Set([
  "profile_id",
  "sample_id",
  "observations",
  "bootstrap_replicates",
  "permutation_replicates",
  "effect_scale",
  "effect_reference_id",
]);
const OBSERVATION_FIELDS = new Set([
  "observation_id",
  "gene_symbol",
  "state",
  "standardized_effect",
  "standard_error",
  "quality_weight",
  "provenance_digest",
]);
const ACTIVE_STATES = new Set(["observed", "left_censored"]);
const EVIDENCE_STATES = new Set([...ACTIVE_STATES, "missing", "unsupported"]);
const AXES = new Set<string>(FUNCTIONAL_PROTEOTYPE_AXES);
const SUPPORT = new Set<string>(["supported", "limited", "abstained"]);
const CLASSIFICATIONS = new Set<string>([
  "source_aligned",
  "source_opposed",
  "neutral",
  "indeterminate",
  "not_estimable",
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

function strings(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function isAxis(value: string): value is FunctionalProteotypeAxis {
  return AXES.has(value);
}

function isSupport(value: string): value is FunctionalProteotypeSupport {
  return SUPPORT.has(value);
}

function isClassification(value: string): value is FunctionalProteotypeClassification {
  return CLASSIFICATIONS.has(value);
}

export function functionalProteotypeRequestStats(request: JsonObject): {
  observations: number;
  active: number;
  observed: number;
  leftCensored: number;
  genes: number;
  axes: number;
} {
  const observations = arrayAt(request, ["observations"]);
  const genes = observations.flatMap((item) => isJsonObject(item) && typeof item.gene_symbol === "string"
    ? [item.gene_symbol.trim()]
    : []);
  return {
    observations: observations.length,
    active: observations.filter((item) => isJsonObject(item) && ACTIVE_STATES.has(String(item.state))).length,
    observed: observations.filter((item) => isJsonObject(item) && item.state === "observed").length,
    leftCensored: observations.filter((item) => isJsonObject(item) && item.state === "left_censored").length,
    genes: new Set(genes).size,
    axes: FUNCTIONAL_PROTEOTYPE_AXES.length,
  };
}

export function validateFunctionalProteotypeRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_FIELDS, "request", errors);

  if (hasOwn(request, "profile_id") && request.profile_id !== FUNCTIONAL_PROTEOTYPE_PROFILE_ID) {
    errors.push(`profile_id must equal ${FUNCTIONAL_PROTEOTYPE_PROFILE_ID}.`);
  }
  if (typeof request.sample_id !== "string" || !IDENTIFIER.test(request.sample_id)) {
    errors.push("sample_id must be a valid identifier.");
  }
  if (typeof request.effect_reference_id !== "string" || !IDENTIFIER.test(request.effect_reference_id)) {
    errors.push("effect_reference_id must be a valid identifier.");
  }
  if (
    hasOwn(request, "effect_scale") &&
    request.effect_scale !== "standardized_log2_abundance_contrast"
  ) {
    errors.push("effect_scale must equal standardized_log2_abundance_contrast.");
  }

  const values = request.observations;
  const observations = Array.isArray(values) ? values : [];
  if (!Array.isArray(values)) errors.push("observations must be an array.");
  if (!observations.length) errors.push("At least one protein observation is required.");
  if (observations.length > 4_096) errors.push("The request exceeds the 4,096-observation limit.");

  const observationIds: string[] = [];
  const geneSymbols: string[] = [];
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
    const geneSymbol = typeof value.gene_symbol === "string" ? value.gene_symbol.trim() : "";
    if (!GENE_SYMBOL.test(geneSymbol)) {
      errors.push(`${path}.gene_symbol must use valid gene-symbol syntax; exact Table 2d membership is enforced by the backend.`);
    } else geneSymbols.push(geneSymbol);
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
  const duplicateGenes = duplicates(geneSymbols);
  if (duplicateGenes.length) errors.push(`Duplicate gene symbols: ${duplicateGenes.join(", ")}.`);

  const bootstrap = request.bootstrap_replicates;
  if (bootstrap !== undefined && (typeof bootstrap !== "number" || !Number.isInteger(bootstrap) || bootstrap < 16 || bootstrap > 256)) {
    errors.push("bootstrap_replicates must be an integer from 16 through 256.");
  }
  const permutations = request.permutation_replicates;
  if (permutations !== undefined && (typeof permutations !== "number" || !Number.isInteger(permutations) || permutations < 64 || permutations > 2_048)) {
    errors.push("permutation_replicates must be an integer from 64 through 2,048.");
  }
  return errors;
}

function normalizeDriver(value: JsonValue): FunctionalProteotypeDriver | null {
  if (!isJsonObject(value)) return null;
  const geneSymbol = textAt(value, ["gene_symbol"]);
  if (!geneSymbol) return null;
  return {
    observationId: textAt(value, ["observation_id"], "unknown-observation"),
    geneSymbol,
    sourceProteinLabel: textAt(value, ["source_protein_label"], geneSymbol),
    sourceRank: numberAt(value, ["source_rank"]) ?? 0,
    sourceRankQuartile: numberAt(value, ["source_rank_quartile"]) ?? 0,
    sourceMwwScore: numberAt(value, ["source_mww_score"]),
    evidenceState: textAt(value, ["evidence_state"], "unknown"),
    valueRole: textAt(value, ["value_role"], "unknown"),
    effect: numberAt(value, ["standardized_effect"]),
    reliabilityWeight: numberAt(value, ["reliability_weight"]),
    sourceLoading: numberAt(value, ["source_loading"]),
    signedContribution: numberAt(value, ["signed_contribution"]),
    absoluteContribution: numberAt(value, ["absolute_contribution"]),
  };
}

function normalizeAblation(value: JsonValue): FunctionalProteotypeAblation | null {
  if (!isJsonObject(value)) return null;
  const support = textAt(value, ["support_after_ablation"]);
  const classification = textAt(value, ["classification_after_ablation"]);
  if (!isSupport(support) || !isClassification(classification)) return null;
  return {
    kind: textAt(value, ["kind"], "unspecified"),
    target: textAt(value, ["target"], "unspecified"),
    proteinsRemoved: numberAt(value, ["proteins_removed"]) ?? 0,
    support,
    baselineEstimate: numberAt(value, ["baseline_estimate"]),
    estimate: numberAt(value, ["ablated_estimate"]),
    delta: numberAt(value, ["estimate_delta"]),
    classification,
    reason: textAt(value, ["reason"]),
  };
}

function normalizePathway(
  value: JsonValue,
  expectedAxis: FunctionalProteotypeAxis,
): FunctionalProteotypePathwayContext | null {
  if (!isJsonObject(value)) return null;
  const axis = textAt(value, ["axis"]);
  const pathwayName = textAt(value, ["pathway_name"]);
  if (axis !== expectedAxis || !isAxis(axis) || !pathwayName || value.sample_inference_status !== "not_evaluated") return null;
  return {
    axis,
    sourceRank: numberAt(value, ["source_rank"]) ?? 0,
    pathwayName,
    sourceLogitNes: numberAt(value, ["source_logit_nes"]),
    sourcePValue: numberAt(value, ["source_p_value"]),
    sourceQValue: numberAt(value, ["source_q_value"]),
    sampleInferenceStatus: "not_evaluated",
    interpretation: textAt(value, ["interpretation"], "source_cohort_pathway_context_only"),
  };
}

function normalizeAxis(value: JsonValue): FunctionalProteotypeAxisEvidence | null {
  if (!isJsonObject(value)) return null;
  const axis = textAt(value, ["axis"]);
  const support = textAt(value, ["support"]);
  const classification = textAt(value, ["classification"]);
  if (!isAxis(axis) || !isSupport(support) || !isClassification(classification)) return null;
  const latent = objectAt(value, ["latent"]);
  const rank = objectAt(value, ["rank"]);
  const counts = objectAt(value, ["evidence_counts"]);
  return {
    axis,
    support,
    classification,
    estimate: latent ? numberAt(latent, ["estimate"]) : null,
    lower: latent ? numberAt(latent, ["lower_bound"]) : null,
    upper: latent ? numberAt(latent, ["upper_bound"]) : null,
    bootstrapReplicates: latent ? numberAt(latent, ["bootstrap_replicates_used"]) ?? 0 : 0,
    signatureObservedCount: rank ? numberAt(rank, ["signature_observed_count"]) ?? 0 : 0,
    complementObservedCount: rank ? numberAt(rank, ["complement_observed_count"]) ?? 0 : 0,
    uStatistic: rank ? numberAt(rank, ["u_statistic"]) : null,
    rankBiserial: rank ? numberAt(rank, ["rank_biserial"]) : null,
    tieCorrection: rank ? numberAt(rank, ["tie_correction"]) : null,
    pValue: rank ? numberAt(rank, ["empirical_p_value"]) : null,
    qValue: rank ? numberAt(rank, ["q_value"]) : null,
    permutationReplicates: rank ? numberAt(rank, ["permutation_replicates_used"]) ?? 0 : 0,
    counts: {
      sourceSignatureProteins: counts ? numberAt(counts, ["source_signature_proteins"]) ?? 150 : 150,
      declared: counts ? numberAt(counts, ["declared_signature_proteins"]) ?? 0 : 0,
      observed: counts ? numberAt(counts, ["observed_signature_proteins"]) ?? 0 : 0,
      leftCensored: counts ? numberAt(counts, ["left_censored_signature_proteins"]) ?? 0 : 0,
      missing: counts ? numberAt(counts, ["missing_signature_proteins"]) ?? 0 : 0,
      unsupported: counts ? numberAt(counts, ["unsupported_signature_proteins"]) ?? 0 : 0,
      unreported: counts ? numberAt(counts, ["unreported_signature_proteins"]) ?? 0 : 0,
      observedBackground: counts ? numberAt(counts, ["observed_background_proteins"]) ?? 0 : 0,
      activeFraction: counts ? numberAt(counts, ["active_signature_fraction"]) ?? 0 : 0,
    },
    effectiveSampleSize: numberAt(value, ["effective_sample_size"]),
    stability: numberAt(value, ["stability"]),
    discordance: numberAt(value, ["discordance"]),
    drivers: arrayAt(value, ["top_drivers"]).flatMap((item) => {
      const driver = normalizeDriver(item);
      return driver ? [driver] : [];
    }),
    ablations: arrayAt(value, ["ablations"]).flatMap((item) => {
      const ablation = normalizeAblation(item);
      return ablation ? [ablation] : [];
    }),
    pathways: arrayAt(value, ["source_cohort_pathway_context"]).flatMap((item) => {
      const pathway = normalizePathway(item, axis);
      return pathway ? [pathway] : [];
    }),
    reasons: strings(value.abstention_reasons),
    raw: value,
  };
}

export function normalizeFunctionalProteotypeAxes(result: JsonObject): FunctionalProteotypeAxisEvidence[] {
  const normalized = arrayAt(result, ["axis_evidence"]).flatMap((value) => {
    const axis = normalizeAxis(value);
    return axis ? [axis] : [];
  });
  return FUNCTIONAL_PROTEOTYPE_AXES.flatMap((axis) => {
    const evidence = normalized.find((item) => item.axis === axis);
    return evidence ? [evidence] : [];
  });
}
