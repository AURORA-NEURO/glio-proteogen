import { arrayAt, isJsonObject, numberAt, objectAt, textAt, type JsonObject, type JsonValue } from "./research-state";

export const NEFTEL_PROFILE_ID = "neftel-bulk-protein-programs/1.0.0";

export type NeftelProgram = {
  id: string;
  kind: "source_meta_module" | "derived_program_family";
  support: "supported" | "limited" | "abstained";
  classification: string;
  agreement: string;
  sourcePrograms: string[];
  locationScore: number | null;
  locationLower: number | null;
  locationUpper: number | null;
  rankScore: number | null;
  pValue: number | null;
  qValue: number | null;
  activeCoverage: number;
  observedMarkers: number;
  eligibleMarkers: number;
  drivers: Array<{ symbol: string; effect: number; state: string; locationInfluence: number | null; rankInfluence: number | null }>;
  ablations: Array<{ family: string; removed: number; locationDelta: number | null; rankDelta: number | null }>;
  reasons: string[];
  raw: JsonObject;
};

const IDENTIFIER = /^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$/;
const GENE = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,31}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ROOT_FIELDS = new Set(["profile_id", "sample_id", "observations", "bootstrap_replicates", "permutation_replicates", "background_mode", "effect_scale", "effect_reference_id"]);
const OBSERVATION_FIELDS = new Set(["observation_id", "gene_symbol", "state", "standardized_effect", "standard_error", "quality_weight", "provenance_digest"]);
const ACTIVE_STATES = new Set(["observed", "left_censored"]);
const STATES = new Set([...ACTIVE_STATES, "missing", "unsupported"]);
const ALIASES: Readonly<Record<string, string>> = {
  C8orf4: "TCIM", ERO1L: "ERO1A", GPR56: "ADGRG1", H2AFZ: "H2AZ1",
  HIST1H4C: "H4C3", HMP19: "NSG2", HN1: "JPT1", HRASLS: "PLAAT1",
  KIAA0101: "PCLAF", LPPR1: "PLPPR1", METTL7B: "TMT1B", MLF1IP: "CENPU",
  PPAP2B: "PLPP3", SEPT3: "SEPTIN3", TMEM206: "PACC1", WARS: "WARS1",
};

function has(source: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

function unknownFields(source: JsonObject, allowed: ReadonlySet<string>, path: string, errors: string[]): void {
  const unknown = Object.keys(source).filter((key) => !allowed.has(key));
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function optionalNumber(source: JsonObject, key: string, path: string, minimum: number, maximum: number, errors: string[]): number | null {
  const value = source[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    errors.push(`${path} must be a finite number within [${minimum}, ${maximum}] or null.`);
    return null;
  }
  return value;
}

export function neftelRequestStats(request: JsonObject): { observations: number; active: number; programs: number } {
  const observations = arrayAt(request, ["observations"]);
  return {
    observations: observations.length,
    active: observations.filter((item) => isJsonObject(item) && ACTIVE_STATES.has(String(item.state))).length,
    programs: 13,
  };
}

export function validateNeftelRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  unknownFields(request, ROOT_FIELDS, "request", errors);
  if (has(request, "profile_id") && request.profile_id !== NEFTEL_PROFILE_ID) errors.push(`profile_id must equal ${NEFTEL_PROFILE_ID}.`);
  if (typeof request.sample_id !== "string" || !IDENTIFIER.test(request.sample_id)) errors.push("sample_id must be a valid identifier.");
  if (request.effect_scale !== "standardized_log2_abundance_contrast") errors.push("effect_scale must equal standardized_log2_abundance_contrast.");
  if (typeof request.effect_reference_id !== "string" || !IDENTIFIER.test(request.effect_reference_id)) errors.push("effect_reference_id must be a valid identifier.");
  if (has(request, "background_mode") && request.background_mode !== "request_observed_proteome") errors.push("background_mode must equal request_observed_proteome.");

  const values = request.observations;
  const observations = Array.isArray(values) ? values : [];
  if (!Array.isArray(values)) errors.push("observations must be an array.");
  if (!observations.length) errors.push("At least one protein observation is required.");
  if (observations.length > 4_096) errors.push("The request exceeds the 4,096-observation limit.");
  const ids: string[] = [];
  const symbols: string[] = [];
  observations.forEach((value, index) => {
    const path = `observations[${index}]`;
    if (!isJsonObject(value)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    unknownFields(value, OBSERVATION_FIELDS, path, errors);
    if (typeof value.observation_id !== "string" || !IDENTIFIER.test(value.observation_id)) errors.push(`${path}.observation_id must be a valid identifier.`);
    else ids.push(value.observation_id);
    if (typeof value.gene_symbol !== "string" || !GENE.test(value.gene_symbol)) errors.push(`${path}.gene_symbol must be a valid protein symbol.`);
    else symbols.push(ALIASES[value.gene_symbol] ?? value.gene_symbol);
    const state = value.state;
    if (typeof state !== "string" || !STATES.has(state)) errors.push(`${path}.state must be one of: observed, left_censored, missing, unsupported.`);
    if (typeof value.provenance_digest !== "string" || !DIGEST.test(value.provenance_digest)) errors.push(`${path}.provenance_digest must be a lowercase sha256 digest.`);
    const effect = optionalNumber(value, "standardized_effect", `${path}.standardized_effect`, -20, 20, errors);
    const error = optionalNumber(value, "standard_error", `${path}.standard_error`, 0, 20, errors);
    const declaredQuality = optionalNumber(value, "quality_weight", `${path}.quality_weight`, 0, 1, errors);
    const quality = declaredQuality ?? 1;
    const active = typeof state === "string" && ACTIVE_STATES.has(state);
    if (active && (effect === null || error === null || error <= 0 || quality === null || quality <= 0)) errors.push(`${path} active evidence requires an effect, positive error, and positive quality.`);
    if ((state === "missing" || state === "unsupported") && (effect !== null || error !== null || declaredQuality !== 0)) errors.push(`${path} missing/unsupported evidence requires no numeric values and zero quality.`);
  });
  const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
  if (duplicateIds.length) errors.push(`Duplicate observation identifiers: ${duplicateIds.join(", ")}.`);
  const duplicateSymbols = [...new Set(symbols.filter((symbol, index) => symbols.indexOf(symbol) !== index))];
  if (duplicateSymbols.length) errors.push(`Duplicate gene symbols after HGNC alias normalization: ${duplicateSymbols.join(", ")}.`);

  const bootstrap = request.bootstrap_replicates;
  if (has(request, "bootstrap_replicates") && (typeof bootstrap !== "number" || !Number.isInteger(bootstrap) || bootstrap < 16 || bootstrap > 256)) errors.push("bootstrap_replicates must be an integer from 16 through 256.");
  const permutations = request.permutation_replicates;
  if (has(request, "permutation_replicates") && (typeof permutations !== "number" || !Number.isInteger(permutations) || permutations < 64 || permutations > 2_048)) errors.push("permutation_replicates must be an integer from 64 through 2,048.");
  return errors;
}

function strings(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function normalizeNeftelPrograms(result: JsonObject): NeftelProgram[] {
  return arrayAt(result, ["program_evidence"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const kind = textAt(value, ["program_kind"]);
    const support = textAt(value, ["support"]);
    if ((kind !== "source_meta_module" && kind !== "derived_program_family") || (support !== "supported" && support !== "limited" && support !== "abstained")) return [];
    const location = objectAt(value, ["location"]);
    const rank = objectAt(value, ["rank_enrichment"]);
    const counts = objectAt(value, ["evidence_counts"]);
    return [{
      id: textAt(value, ["program_id"], "unnamed-program"), kind, support,
      classification: textAt(value, ["classification"], "not_estimable"),
      agreement: textAt(value, ["method_agreement"], "insufficient"),
      sourcePrograms: strings(value.source_programs),
      locationScore: location ? numberAt(location, ["score"]) : null,
      locationLower: location ? numberAt(location, ["lower_bound"]) : null,
      locationUpper: location ? numberAt(location, ["upper_bound"]) : null,
      rankScore: rank ? numberAt(rank, ["score"]) : null,
      pValue: rank ? numberAt(rank, ["p_value"]) : null,
      qValue: rank ? numberAt(rank, ["q_value"]) : null,
      activeCoverage: counts ? numberAt(counts, ["active_coverage"]) ?? 0 : 0,
      observedMarkers: counts ? numberAt(counts, ["observed_markers"]) ?? 0 : 0,
      eligibleMarkers: counts ? numberAt(counts, ["eligible_protein_markers"]) ?? 0 : 0,
      drivers: arrayAt(value, ["top_drivers"]).flatMap((driver) => isJsonObject(driver) ? [{
        symbol: textAt(driver, ["normalized_symbol"], "unknown"),
        effect: numberAt(driver, ["standardized_effect"]) ?? 0,
        state: textAt(driver, ["evidence_state"], "unknown"),
        locationInfluence: numberAt(driver, ["location_influence"]),
        rankInfluence: numberAt(driver, ["rank_influence"]),
      }] : []),
      ablations: arrayAt(value, ["marker_family_ablations"]).flatMap((ablation) => isJsonObject(ablation) ? [{
        family: textAt(ablation, ["omitted_family"], "unspecified"),
        removed: numberAt(ablation, ["markers_removed"]) ?? 0,
        locationDelta: numberAt(ablation, ["location_delta"]),
        rankDelta: numberAt(ablation, ["rank_delta"]),
      }] : []),
      reasons: strings(value.abstention_reasons), raw: value,
    } satisfies NeftelProgram];
  });
}
