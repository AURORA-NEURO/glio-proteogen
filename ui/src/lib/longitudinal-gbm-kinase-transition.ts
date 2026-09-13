import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";
import {
  LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  longitudinalPhosphoRequestStats,
  validateLongitudinalPhosphoRequest,
} from "./longitudinal-gbm-phospho";

export const LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID =
  "kncc-gbm-longitudinal-kinase-transition/1.0.0";
export const LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST =
  "sha256:6be719c54fdaf2be0f83cfe649bc9d394454e5eeb187108a0ce0c7feea9f471a";
export const LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_ID =
  "synthetic-kncc-sphinks-signature-transition-v1";
export const LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_DIGEST =
  "sha256:ebd847cc2c64174614757fd9e2bb5398be0153cc221f48dbfe16e2a33ce72074";
export const LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_ORACLE_DIGEST =
  "sha256:76d4fa939794142eb87f1483bbbaddbd62b1b7f2bb2ed206459f933c202a0077";

export type KinaseTransitionSupport = "limited" | "abstained";
export type KinaseTransitionSubtype = "GPM" | "MTC" | "NEU" | "PPR";

export type KinaseTransitionUncertainty = {
  state: "estimated" | "not_estimable";
  lower: number | null;
  upper: number | null;
  standardError: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type KinaseTransitionDriver = {
  sourceSiteLabel: string;
  sourcePhosphositeIds: string[];
  stratum: string;
  composite: boolean;
  standardizedRank: number | null;
  inverseMultiplicity: number | null;
  adjustedSourceWeight: number | null;
  contribution: number | null;
  pairedSourceSupport: number;
  observationIds: string[];
};

export type KinaseTransitionSignature = {
  kinase: string;
  subtype: KinaseTransitionSubtype;
  selectionState: "selected_core" | "selected_unstable" | "not_selected";
  support: KinaseTransitionSupport;
  sourceDirection: "source_recurrence_aligned" | "reverse_aligned" | "not_established";
  sourceEnrichment: number | null;
  sourcePValue: number | null;
  sourceQValue: number | null;
  mappedSourceFamilies: number;
  observedFamilies: number;
  sourceWeightCoverage: number | null;
  outerSelectionFrequency: number | null;
  bootstrapSelectionFrequency: number | null;
  bootstrapDirectionConsistency: number | null;
  score: number | null;
  classification: string;
  uncertainty: KinaseTransitionUncertainty;
  drivers: KinaseTransitionDriver[];
  reasons: string[];
};

export type KinaseTransitionSubtypeEvidence = {
  subtype: KinaseTransitionSubtype;
  selectedKinases: number;
  estimableKinases: number;
  support: KinaseTransitionSupport;
  score: number | null;
  classification: string;
  uncertainty: KinaseTransitionUncertainty;
  reasons: string[];
};

export type KinaseTransitionAblation = {
  kind: string;
  support: KinaseTransitionSupport;
  score: number | null;
  scoreDelta: number | null;
  classification: string;
  reason: string;
};

export type KinaseTransition = {
  id: string;
  index: number;
  fromTimePointId: string;
  toTimePointId: string;
  support: KinaseTransitionSupport;
  classification: string;
  score: number | null;
  uncertainty: KinaseTransitionUncertainty;
  exactSourceRows: number;
  exactFamilies: number;
  censoredFamilies: number;
  selectedKinases: number;
  estimableKinases: number;
  kinases: KinaseTransitionSignature[];
  subtypes: KinaseTransitionSubtypeEvidence[];
  ablations: KinaseTransitionAblation[];
  reasons: string[];
  raw: JsonObject;
};

export type KinaseTransitionRequestStats = {
  timePoints: number;
  transitions: number;
  observations: number;
  active: number;
  phosphosites: number;
};

export const LONGITUDINAL_GBM_KINASE_TRANSITION_SUBTYPES = [
  "GPM",
  "MTC",
  "NEU",
  "PPR",
] as const;

type KinaseInventoryItem = readonly [
  string,
  KinaseTransitionSubtype,
  "selected_core" | "selected_unstable" | "not_selected",
  "source_recurrence_aligned" | "reverse_aligned" | "not_established",
];

export const LONGITUDINAL_GBM_KINASE_TRANSITION_INVENTORY: readonly KinaseInventoryItem[] = [
  ["BRAF", "NEU", "selected_core", "source_recurrence_aligned"],
  ["CDK1", "PPR", "selected_core", "reverse_aligned"],
  ["CDK2", "PPR", "selected_core", "reverse_aligned"],
  ["CDK6", "PPR", "not_selected", "not_established"],
  ["CHEK2", "PPR", "selected_unstable", "reverse_aligned"],
  ["CSNK2A1", "PPR", "selected_core", "reverse_aligned"],
  ["GSK3B", "NEU", "selected_core", "source_recurrence_aligned"],
  ["IKBKB", "GPM", "not_selected", "not_established"],
  ["MAPK10", "NEU", "selected_core", "source_recurrence_aligned"],
  ["MAPK13", "GPM", "not_selected", "not_established"],
  ["MAPKAPK2", "GPM", "not_selected", "not_established"],
  ["MKNK1", "GPM", "not_selected", "not_established"],
  ["PAK1", "NEU", "selected_core", "source_recurrence_aligned"],
  ["PAK3", "NEU", "selected_core", "source_recurrence_aligned"],
  ["PHKG2", "MTC", "not_selected", "not_established"],
  ["PRKAA1", "GPM", "not_selected", "not_established"],
  ["PRKCD", "GPM", "not_selected", "not_established"],
  ["PRKCE", "NEU", "selected_core", "source_recurrence_aligned"],
  ["PRKDC", "PPR", "selected_core", "reverse_aligned"],
  ["RAF1", "PPR", "not_selected", "not_established"],
  ["RPS6KB2", "GPM", "not_selected", "not_established"],
  ["SYK", "GPM", "not_selected", "not_established"],
  ["TTBK2", "NEU", "selected_core", "source_recurrence_aligned"],
  ["VRK2", "GPM", "not_selected", "not_established"],
];

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const SUPPORTS = new Set(["limited", "abstained"]);
const CLASSIFICATIONS = new Set([
  "source_recurrence_aligned",
  "reverse_aligned",
  "stable",
  "indeterminate",
  "not_estimable",
]);
const SELECTION_STATES = new Set(["selected_core", "selected_unstable", "not_selected"]);
const SOURCE_DIRECTIONS = new Set([
  "source_recurrence_aligned",
  "reverse_aligned",
  "not_established",
]);
const ABLATION_ORDER = [
  "equal_kinase_instead_of_equal_subtype",
  "omit_composite_source_groups",
  "omit_inverse_multiplicity_correction",
] as const;

const REQUIRED_ASSAY: JsonObject = {
  schema_version: "glio-proteogen.kncc-phosphosite-assay-compatibility-attestation/1.0.0",
  compatibility_profile_id: "kncc-pdc000515-tmt11-phosphosite-log2-transition/1.0.0",
  source_profile_digest: "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216",
  source_artifact_content_digest: "sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a",
  assay: "tmt11_plexed_phosphoproteome_mass_spectrometry",
  quantification: "phosphosite_sample_to_reference_abundance_ratio",
  value_transformation: "log2_ratio",
  log_base: 2,
  feature_identity: "exact_ensp_versioned_source_site_group",
  composite_site_policy: "indivisible_source_site_group",
  invariant_across_time_points: true,
  attested_compatible: true,
};

const PROFILE_FIELDS = new Set([
  "algorithm_id", "algorithm_version", "profile_id", "model_id",
  "required_assay_compatibility", "constants", "counts", "digests", "quality_gates",
  "source_provenance", "numpy_version", "demo_id", "demo_request_digest",
  "demo_semantic_oracle_digest", "source_attestation_state", "safety_class",
  "claim_ceiling", "profile_digest",
]);
const CONSTANT_FIELDS = new Set([
  "hypothesis_family", "family_projection", "inverse_multiplicity_policy",
  "composite_site_policy", "missing_evidence_policy", "censoring_policy",
  "bootstrap_policy", "measurement_policy", "fdr_threshold", "minimum_kinase_families",
  "minimum_source_weight_coverage", "core_stability_threshold", "alignment_threshold",
  "maximum_top_drivers", "quantization_decimals",
]);
const COUNT_FIELDS = new Set([
  "strict_patient_pairs", "exact_crosswalk_pdc_rows", "unique_crosswalk_families",
  "duplicate_family_extra_pdc_rows", "signature_pdc_rows", "unique_signature_families",
  "release_eligible_background_families", "fixed_master_kinase_hypotheses",
  "full_fit_selected_kinases", "core_stable_selected_kinases", "patient_bootstrap_replicates",
]);
const DIGEST_FIELDS = new Set([
  "fitter_source_sha256", "fitted_artifact_content_digest", "fitted_artifact_byte_digest",
  "bootstrap_ensemble_digest", "pdc_phosphosite_artifact_content_digest",
  "pdc_phosphosite_source_profile_digest", "pdc_source_manifest_digest",
  "pdc_hgnc_mapping_digest", "pdc_sphinks_crosswalk_digest",
  "sphinks_catalog_artifact_digest", "sphinks_catalog_content_digest",
  "sphinks_background_tuple_digest", "sphinks_signature_edge_digest",
  "sphinks_master_kinase_digest", "sphinks_source_sha256", "engine_semantic_digest",
]);
const QUALITY_GATE_FIELDS = new Set([
  "same_assay_independent_evidence_gate_passed",
  "patient_bootstrap_full_refit_convergence_gate_passed",
  "patient_bootstrap_full_set_stability_gate_passed",
  "patient_bootstrap_interval_calibration_gate_passed",
  "output_policy",
]);
const SOURCE_PROVENANCE_FIELDS = new Set([
  "pdc_article_attribution", "pdc_license", "pdc_license_url", "pdc_transformation_notice",
  "sphinks_article_attribution", "sphinks_license", "sphinks_license_url",
  "sphinks_transformation_notice",
]);
const RESULT_FIELDS = new Set([
  "algorithm_id", "algorithm_version", "profile_id", "profile_digest", "request_digest",
  "result_digest", "series_id", "assay_compatibility", "normalization_reference",
  "time_point_ids", "transitions", "provenance", "output_semantics", "limitations",
  "research_use_only", "non_prescriptive", "infers_kinase_activity",
  "infers_biochemical_activity", "makes_causal_claim", "independent_evidence",
]);
const PROVENANCE_FIELDS = new Set([
  "engine", "request_digest", "profile_digest", "fitted_artifact_content_digest",
  "fitted_artifact_byte_digest", "bootstrap_ensemble_digest", "engine_semantic_digest",
  "assay_compatibility_digest", "normalization_reference_digest", "computational_digest",
  "numerical_seed_digest", "observation_source_digests", "source_attestation_state",
  "source_provenance", "numpy_version",
]);
const TRANSITION_FIELDS = new Set([
  "transition_id", "transition_index", "from_time_point_id", "to_time_point_id", "support",
  "classification", "score", "uncertainty", "exact_source_row_count", "exact_family_count",
  "censored_family_count", "selected_kinase_count", "estimable_kinase_count",
  "kinase_signatures", "subtype_signatures", "ablations", "reasons",
]);
const UNCERTAINTY_FIELDS = new Set([
  "state", "lower_bound", "upper_bound", "standard_error", "bootstrap_replicates_used", "reason",
]);
const KINASE_FIELDS = new Set([
  "kinase", "subtype", "selection_state", "support", "source_direction", "source_enrichment",
  "source_p_value", "source_q_value", "mapped_source_family_count", "observed_family_count",
  "source_weight_coverage", "outer_selection_frequency", "bootstrap_selection_frequency",
  "bootstrap_direction_consistency", "score", "classification", "uncertainty",
  "top_family_drivers", "reasons",
]);
const DRIVER_FIELDS = new Set([
  "source_site_label", "source_phosphosite_ids", "stratum", "contains_composite_source_group",
  "standardized_rank", "inverse_multiplicity", "adjusted_source_weight", "signed_contribution",
  "paired_source_support", "paired_observation_ids", "observation_provenance_digests",
]);
const SUBTYPE_FIELDS = new Set([
  "subtype", "selected_kinase_count", "estimable_kinase_count", "support", "score",
  "classification", "uncertainty", "reasons",
]);
const ABLATION_FIELDS = new Set([
  "ablation", "support", "score", "score_delta", "classification", "reason",
]);
const VERIFICATION_FIELDS = new Set([
  "verified", "request_digest_match", "profile_digest_match", "result_digest_match",
  "transition_semantic_match", "semantic_match", "recomputed_request_digest",
  "recomputed_result_digest", "message",
]);

const REQUEST_FLOAT_FIELDS = new Set([
  "time_offset_days", "log_abundance_ratio", "standard_error", "quality_weight",
]);
const PROFILE_FLOAT_FIELDS = new Set([
  "fdr_threshold", "minimum_source_weight_coverage", "core_stability_threshold",
  "alignment_threshold",
]);
const RESULT_FLOAT_FIELDS = new Set([
  "lower_bound", "upper_bound", "standard_error", "standardized_rank", "inverse_multiplicity",
  "adjusted_source_weight", "signed_contribution", "source_enrichment", "source_p_value",
  "source_q_value", "source_weight_coverage", "outer_selection_frequency",
  "bootstrap_selection_frequency", "bootstrap_direction_consistency", "score", "score_delta",
]);

const SHA256_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);
const SHA256_INITIAL = new Uint32Array([
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
  0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]);

type HeaderReader = Pick<Headers, "get">;

function exactFields(
  value: JsonObject,
  expected: ReadonlySet<string>,
  path: string,
  errors: string[],
): void {
  const unknown = Object.keys(value).filter((key) => !expected.has(key));
  const missing = [...expected].filter((key) => !Object.prototype.hasOwnProperty.call(value, key));
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
}

function finite(value: JsonValue | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function integer(value: JsonValue | undefined, minimum: number, maximum: number): value is number {
  return finite(value) && Number.isInteger(value) && value >= minimum && value <= maximum;
}

function digest(value: JsonValue | undefined): value is string {
  return typeof value === "string" && DIGEST.test(value);
}

function nonempty(value: JsonValue | undefined): value is string {
  return typeof value === "string" && Boolean(value.trim());
}

function strings(value: JsonValue | undefined): string[] | null {
  if (!Array.isArray(value) || value.some((item) => !nonempty(item))) return null;
  return value as string[];
}

function canonicalJson(value: JsonValue): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isJsonObject(value)) {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sameJson(left: JsonValue | undefined, right: JsonValue | undefined): boolean {
  return left !== undefined && right !== undefined && canonicalJson(left) === canonicalJson(right);
}

function rotateRight(value: number, places: number): number {
  return (value >>> places) | (value << (32 - places));
}

function sha256Hex(source: string): string {
  const input = new TextEncoder().encode(source);
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64;
  const bytes = new Uint8Array(paddedLength);
  bytes.set(input);
  bytes[input.length] = 0x80;
  const bitLength = input.length * 8;
  const view = new DataView(bytes.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x1_0000_0000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);
  const hash = new Uint32Array(SHA256_INITIAL);
  const words = new Uint32Array(64);
  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 64; index += 1) {
      const before15 = words[index - 15];
      const before2 = words[index - 2];
      const sigma0 = rotateRight(before15, 7) ^ rotateRight(before15, 18) ^ (before15 >>> 3);
      const sigma1 = rotateRight(before2, 17) ^ rotateRight(before2, 19) ^ (before2 >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temporary1 = (h + sum1 + choice + SHA256_CONSTANTS[index] + words[index]) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }
  return [...hash].map((value) => value.toString(16).padStart(8, "0")).join("");
}

function pythonFloatJson(value: number): string {
  if (!Number.isFinite(value)) return "null";
  if (value === 0) return Object.is(value, -0) ? "-0.0" : "0.0";
  const sign = value < 0 ? "-" : "";
  const source = Math.abs(value).toString().toLowerCase();
  const [mantissa, sourceExponent = "0"] = source.split("e");
  const decimalIndex = mantissa.indexOf(".");
  const integralDigits = decimalIndex === -1 ? mantissa.length : decimalIndex;
  const combined = mantissa.replace(".", "");
  const firstNonzero = combined.search(/[1-9]/);
  const digits = combined.slice(firstNonzero).replace(/0+$/, "");
  const exponent = Number.parseInt(sourceExponent, 10) + integralDigits - firstNonzero - 1;
  if (exponent < -4 || exponent >= 16) {
    const fraction = digits.length > 1 ? `.${digits.slice(1)}` : "";
    const exponentSign = exponent >= 0 ? "+" : "-";
    const exponentDigits = Math.abs(exponent).toString().padStart(2, "0");
    return `${sign}${digits[0]}${fraction}e${exponentSign}${exponentDigits}`;
  }
  if (exponent < 0) return `${sign}0.${"0".repeat(-exponent - 1)}${digits}`;
  const trailingZeroCount = exponent + 1 - digits.length;
  if (trailingZeroCount >= 0) return `${sign}${digits}${"0".repeat(trailingZeroCount)}.0`;
  const splitAt = exponent + 1;
  return `${sign}${digits.slice(0, splitAt)}.${digits.slice(splitAt)}`;
}

function canonicalTypedJson(
  value: JsonValue,
  floatFields: ReadonlySet<string>,
  parentKey = "",
): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalTypedJson(item, floatFields, parentKey)).join(",")}]`;
  }
  if (isJsonObject(value)) {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalTypedJson(value[key], floatFields, key)}`
    )).join(",")}}`;
  }
  if (typeof value === "number" && floatFields.has(parentKey)) return pythonFloatJson(value);
  return JSON.stringify(value);
}

function defaultedObservation(value: JsonValue): JsonValue {
  if (!isJsonObject(value)) return value;
  return {
    ...value,
    log_abundance_ratio: value.log_abundance_ratio ?? null,
    standard_error: value.standard_error ?? null,
    quality_weight: value.quality_weight ?? 1,
  };
}

function normalizedRequestForDigest(request: JsonObject): JsonObject {
  const reference = isJsonObject(request.normalization_reference)
    ? {
      ...request.normalization_reference,
      abundance_scale: request.normalization_reference.abundance_scale
        ?? "caller_supplied_log2_phosphosite_abundance_ratio",
      invariant_across_time_points:
        request.normalization_reference.invariant_across_time_points ?? true,
    }
    : request.normalization_reference;
  const timePoints = Array.isArray(request.time_points)
    ? request.time_points.map((point) => {
      if (!isJsonObject(point) || !Array.isArray(point.observations)) return point;
      const observations = point.observations.map(defaultedObservation).sort((left, right) => {
        if (!isJsonObject(left) || !isJsonObject(right)) return 0;
        const leftKey = `${String(left.phosphosite_id)}\u0000${String(left.observation_id)}`;
        const rightKey = `${String(right.phosphosite_id)}\u0000${String(right.observation_id)}`;
        return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
      });
      return { ...point, observations };
    })
    : request.time_points;
  return {
    ...request,
    profile_id: request.profile_id ?? LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
    normalization_reference: reference,
    time_points: timePoints,
    bootstrap_replicates: request.bootstrap_replicates ?? 64,
  };
}

export function kinaseTransitionRequestDigest(request: JsonObject): string {
  return `sha256:${sha256Hex(canonicalTypedJson(
    normalizedRequestForDigest(request),
    REQUEST_FLOAT_FIELDS,
  ))}`;
}

export function kinaseTransitionProfileDigest(profile: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(profile).filter(([key]) => key !== "profile_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalTypedJson(payload, PROFILE_FLOAT_FIELDS))}`;
}

export function kinaseTransitionResultDigest(result: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(result).filter(([key]) => key !== "result_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalTypedJson(payload, RESULT_FLOAT_FIELDS))}`;
}

export function kinaseTransitionValueDigest(value: JsonValue): string {
  return `sha256:${sha256Hex(canonicalJson(value))}`;
}

export function kinaseTransitionRequestStats(request: JsonObject): KinaseTransitionRequestStats {
  const stats = longitudinalPhosphoRequestStats(request);
  return { ...stats, transitions: Math.max(0, stats.timePoints - 1) };
}

export function validateKinaseTransitionRequest(request: JsonObject): string[] {
  const profileErrors = request.profile_id === undefined
    || request.profile_id === LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID
    ? []
    : [`profile_id must equal ${LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID}.`];
  return [
    ...profileErrors,
    ...validateLongitudinalPhosphoRequest({
      ...request,
      profile_id: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
    }),
  ];
}

function validNullableNumber(value: JsonValue | undefined): boolean {
  return value === null || finite(value);
}

function validProbability(value: JsonValue | undefined): boolean {
  return finite(value) && value >= 0 && value <= 1;
}

function validStringArray(
  value: JsonValue | undefined,
  minimum: number,
  maximum: number,
  predicate: (item: string) => boolean = (item) => Boolean(item.trim()),
): value is string[] {
  return Array.isArray(value)
    && value.length >= minimum
    && value.length <= maximum
    && value.every((item) => typeof item === "string" && predicate(item));
}

function unique(values: readonly string[]): boolean {
  return new Set(values).size === values.length;
}

function validateSourceProvenance(
  value: JsonValue | undefined,
  path: string,
  errors: string[],
): value is JsonObject {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return false;
  }
  exactFields(value, SOURCE_PROVENANCE_FIELDS, path, errors);
  for (const field of SOURCE_PROVENANCE_FIELDS) {
    if (!nonempty(value[field])) errors.push(`${path}.${field} must be non-empty.`);
  }
  if (value.pdc_license !== "CC-BY-4.0") errors.push(`${path}.pdc_license must equal CC-BY-4.0.`);
  if (value.sphinks_license !== "CC-BY-4.0") errors.push(`${path}.sphinks_license must equal CC-BY-4.0.`);
  for (const field of ["pdc_license_url", "sphinks_license_url"] as const) {
    if (typeof value[field] !== "string" || !value[field].startsWith("https://")) {
      errors.push(`${path}.${field} must be an https URL.`);
    }
  }
  return true;
}

function validateUncertainty(
  value: JsonValue | undefined,
  path: string,
  errors: string[],
): KinaseTransitionUncertainty | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, UNCERTAINTY_FIELDS, path, errors);
  if (value.state === "estimated") {
    if (
      !finite(value.lower_bound)
      || !finite(value.upper_bound)
      || value.lower_bound > value.upper_bound
      || !finite(value.standard_error)
      || value.standard_error < 0
      || !integer(value.bootstrap_replicates_used, 32, 64)
      || value.reason !== null
    ) {
      errors.push(`${path} must contain a closed finite 32-64 replicate estimated interval.`);
      return null;
    }
    return {
      state: "estimated",
      lower: value.lower_bound,
      upper: value.upper_bound,
      standardError: value.standard_error,
      bootstrapReplicates: value.bootstrap_replicates_used,
      reason: "",
    };
  }
  if (
    value.state !== "not_estimable"
    || value.lower_bound !== null
    || value.upper_bound !== null
    || value.standard_error !== null
    || value.bootstrap_replicates_used !== 0
    || !nonempty(value.reason)
  ) {
    errors.push(`${path} must be an estimated interval or an explicit not-estimable receipt.`);
    return null;
  }
  return {
    state: "not_estimable",
    lower: null,
    upper: null,
    standardError: null,
    bootstrapReplicates: 0,
    reason: value.reason,
  };
}

function intervalClassification(lower: number, upper: number): string {
  if (lower > 0.05) return "source_recurrence_aligned";
  if (upper < -0.05) return "reverse_aligned";
  if (lower >= -0.05 && upper <= 0.05) return "stable";
  return "indeterminate";
}

function pointClassification(score: number): string {
  if (score > 0.05) return "source_recurrence_aligned";
  if (score < -0.05) return "reverse_aligned";
  return "stable";
}

function validateDriver(
  value: JsonValue,
  path: string,
  errors: string[],
): KinaseTransitionDriver | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, DRIVER_FIELDS, path, errors);
  const sourceIds = strings(value.source_phosphosite_ids);
  const observationIds = strings(value.paired_observation_ids);
  const observationDigests = strings(value.observation_provenance_digests);
  if (
    !nonempty(value.source_site_label)
    || !sourceIds
    || sourceIds.length < 1
    || sourceIds.length > 16
    || !unique(sourceIds)
    || !nonempty(value.stratum)
    || typeof value.contains_composite_source_group !== "boolean"
    || !finite(value.standardized_rank)
    || value.standardized_rank < -1
    || value.standardized_rank > 1
    || !finite(value.inverse_multiplicity)
    || value.inverse_multiplicity <= 0
    || value.inverse_multiplicity > 1
    || !finite(value.adjusted_source_weight)
    || value.adjusted_source_weight <= 0
    || !finite(value.signed_contribution)
    || !integer(value.paired_source_support, 53, 88)
    || !observationIds
    || observationIds.length < 2
    || observationIds.length > 32
    || !observationDigests
    || observationDigests.length < 2
    || observationDigests.length > 32
    || observationDigests.some((item) => !DIGEST.test(item))
  ) {
    errors.push(`${path} is not a complete bounded source-family driver.`);
    return null;
  }
  return {
    sourceSiteLabel: value.source_site_label,
    sourcePhosphositeIds: sourceIds,
    stratum: value.stratum,
    composite: value.contains_composite_source_group,
    standardizedRank: value.standardized_rank,
    inverseMultiplicity: value.inverse_multiplicity,
    adjustedSourceWeight: value.adjusted_source_weight,
    contribution: value.signed_contribution,
    pairedSourceSupport: value.paired_source_support,
    observationIds,
  };
}

function validateKinaseSignature(
  value: JsonValue,
  expected: KinaseInventoryItem,
  path: string,
  errors: string[],
): KinaseTransitionSignature | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, KINASE_FIELDS, path, errors);
  const [kinase, subtype, selectionState, sourceDirection] = expected;
  if (
    value.kinase !== kinase
    || value.subtype !== subtype
    || value.selection_state !== selectionState
    || value.source_direction !== sourceDirection
  ) errors.push(`${path} must preserve the locked ${kinase} identity and source assignment.`);
  if (!SUPPORTS.has(String(value.support))) errors.push(`${path}.support must be limited or abstained.`);
  if (!SELECTION_STATES.has(String(value.selection_state))) errors.push(`${path}.selection_state is invalid.`);
  if (!SOURCE_DIRECTIONS.has(String(value.source_direction))) errors.push(`${path}.source_direction is invalid.`);
  if (!CLASSIFICATIONS.has(String(value.classification))) errors.push(`${path}.classification is invalid.`);
  if (!validNullableNumber(value.source_enrichment)) errors.push(`${path}.source_enrichment must be finite or null.`);
  for (const field of [
    "source_p_value", "source_q_value", "source_weight_coverage",
    "outer_selection_frequency", "bootstrap_selection_frequency",
  ] as const) {
    if (!validProbability(value[field])) errors.push(`${path}.${field} must be within [0,1].`);
  }
  if (value.bootstrap_direction_consistency !== null && !validProbability(value.bootstrap_direction_consistency)) {
    errors.push(`${path}.bootstrap_direction_consistency must be within [0,1] or null.`);
  }
  if (!integer(value.mapped_source_family_count, 0, 572)) errors.push(`${path}.mapped_source_family_count is invalid.`);
  if (!integer(value.observed_family_count, 0, 572)) errors.push(`${path}.observed_family_count is invalid.`);
  if (!validNullableNumber(value.score)) errors.push(`${path}.score must be finite or null.`);
  const uncertainty = validateUncertainty(value.uncertainty, `${path}.uncertainty`, errors);
  const reasons = validStringArray(value.reasons, 0, 8) ? value.reasons : null;
  if (!reasons) errors.push(`${path}.reasons must contain at most eight non-empty strings.`);
  const rawDrivers = Array.isArray(value.top_family_drivers) ? value.top_family_drivers : [];
  if (!Array.isArray(value.top_family_drivers) || rawDrivers.length > 8) {
    errors.push(`${path}.top_family_drivers must contain at most eight drivers.`);
  }
  const drivers = rawDrivers.flatMap((item, index) => (
    validateDriver(item, `${path}.top_family_drivers[${index}]`, errors) ?? []
  ));
  const sortedDrivers = [...drivers].sort((left, right) => (
    Math.abs(right.contribution ?? 0) - Math.abs(left.contribution ?? 0)
      || left.sourceSiteLabel.localeCompare(right.sourceSiteLabel)
  ));
  if (drivers.map((item) => item.sourceSiteLabel).join("|") !== sortedDrivers.map((item) => item.sourceSiteLabel).join("|")) {
    errors.push(`${path}.top_family_drivers must use descending absolute contribution order.`);
  }
  const abstained = value.support === "abstained";
  if (selectionState === "not_selected" && !abstained) errors.push(`${path} is not selected and must abstain.`);
  if (
    abstained
      ? value.score !== null || value.classification !== "not_estimable" || uncertainty?.state !== "not_estimable" || !reasons?.length
      : value.score === null || value.classification === "not_estimable" || uncertainty?.state !== "estimated" || !reasons?.length
  ) errors.push(`${path} support, score, interval, classification, and reasons do not close.`);
  if (!abstained && uncertainty?.state === "estimated" && value.classification !== intervalClassification(uncertainty.lower!, uncertainty.upper!)) {
    errors.push(`${path}.classification must be derived from its interval.`);
  }
  if (selectionState === "selected_core" && finite(value.bootstrap_selection_frequency) && value.bootstrap_selection_frequency < 0.8) {
    errors.push(`${path}.bootstrap_selection_frequency is below the core stability gate.`);
  }
  if (selectionState === "selected_unstable" && finite(value.bootstrap_selection_frequency) && value.bootstrap_selection_frequency >= 0.8) {
    errors.push(`${path}.bootstrap_selection_frequency must remain below the core stability gate.`);
  }
  if (selectionState !== "not_selected" && value.source_q_value !== null && finite(value.source_q_value) && value.source_q_value > 0.1) {
    errors.push(`${path}.source_q_value exceeds the locked selected-family FDR gate.`);
  }
  if (selectionState === "not_selected" && value.source_q_value !== null && finite(value.source_q_value) && value.source_q_value <= 0.1) {
    errors.push(`${path}.source_q_value conflicts with not-selected status.`);
  }
  if (!uncertainty || !reasons) return null;
  return {
    kinase,
    subtype,
    selectionState,
    support: value.support as KinaseTransitionSupport,
    sourceDirection,
    sourceEnrichment: finite(value.source_enrichment) ? value.source_enrichment : null,
    sourcePValue: finite(value.source_p_value) ? value.source_p_value : null,
    sourceQValue: finite(value.source_q_value) ? value.source_q_value : null,
    mappedSourceFamilies: finite(value.mapped_source_family_count) ? value.mapped_source_family_count : 0,
    observedFamilies: finite(value.observed_family_count) ? value.observed_family_count : 0,
    sourceWeightCoverage: finite(value.source_weight_coverage) ? value.source_weight_coverage : null,
    outerSelectionFrequency: finite(value.outer_selection_frequency) ? value.outer_selection_frequency : null,
    bootstrapSelectionFrequency: finite(value.bootstrap_selection_frequency) ? value.bootstrap_selection_frequency : null,
    bootstrapDirectionConsistency: finite(value.bootstrap_direction_consistency) ? value.bootstrap_direction_consistency : null,
    score: finite(value.score) ? value.score : null,
    classification: String(value.classification),
    uncertainty,
    drivers,
    reasons,
  };
}

function validateSubtypeSignature(
  value: JsonValue,
  subtype: KinaseTransitionSubtype,
  expectedSelected: number,
  path: string,
  errors: string[],
): KinaseTransitionSubtypeEvidence | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, SUBTYPE_FIELDS, path, errors);
  if (value.subtype !== subtype) errors.push(`${path}.subtype must equal ${subtype}.`);
  if (value.selected_kinase_count !== expectedSelected) errors.push(`${path}.selected_kinase_count must equal ${expectedSelected}.`);
  if (!integer(value.estimable_kinase_count, 0, expectedSelected)) errors.push(`${path}.estimable_kinase_count is invalid.`);
  if (!SUPPORTS.has(String(value.support))) errors.push(`${path}.support must be limited or abstained.`);
  if (!CLASSIFICATIONS.has(String(value.classification))) errors.push(`${path}.classification is invalid.`);
  if (!validNullableNumber(value.score)) errors.push(`${path}.score must be finite or null.`);
  const uncertainty = validateUncertainty(value.uncertainty, `${path}.uncertainty`, errors);
  const reasons = validStringArray(value.reasons, 0, 8) ? value.reasons : null;
  if (!reasons) errors.push(`${path}.reasons must contain at most eight non-empty strings.`);
  const abstained = value.support === "abstained";
  if (
    abstained
      ? value.score !== null || value.classification !== "not_estimable" || uncertainty?.state !== "not_estimable" || !reasons?.length
      : value.score === null || value.classification === "not_estimable" || uncertainty?.state !== "estimated" || !reasons?.length
  ) errors.push(`${path} support, score, interval, classification, and reasons do not close.`);
  if (!abstained && uncertainty?.state === "estimated" && value.classification !== intervalClassification(uncertainty.lower!, uncertainty.upper!)) {
    errors.push(`${path}.classification must be derived from its interval.`);
  }
  if (!uncertainty || !reasons) return null;
  return {
    subtype,
    selectedKinases: integer(value.selected_kinase_count, 0, 9) ? value.selected_kinase_count : 0,
    estimableKinases: integer(value.estimable_kinase_count, 0, 9) ? value.estimable_kinase_count : 0,
    support: value.support as KinaseTransitionSupport,
    score: finite(value.score) ? value.score : null,
    classification: String(value.classification),
    uncertainty,
    reasons,
  };
}

function validateAblation(
  value: JsonValue,
  expected: string,
  path: string,
  errors: string[],
): KinaseTransitionAblation | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, ABLATION_FIELDS, path, errors);
  if (value.ablation !== expected) errors.push(`${path}.ablation must equal ${expected}.`);
  if (!SUPPORTS.has(String(value.support))) errors.push(`${path}.support must be limited or abstained.`);
  if (!validNullableNumber(value.score) || !validNullableNumber(value.score_delta)) {
    errors.push(`${path} scores must be finite or null.`);
  }
  if (!CLASSIFICATIONS.has(String(value.classification)) || !nonempty(value.reason)) {
    errors.push(`${path} must contain a valid classification and reason.`);
  }
  if (
    value.support === "abstained"
      ? value.score !== null || value.score_delta !== null || value.classification !== "not_estimable"
      : value.score === null || value.score_delta === null || !finite(value.score) || value.classification !== pointClassification(value.score)
  ) errors.push(`${path} support and point classification do not close.`);
  return {
    kind: String(value.ablation),
    support: value.support as KinaseTransitionSupport,
    score: finite(value.score) ? value.score : null,
    scoreDelta: finite(value.score_delta) ? value.score_delta : null,
    classification: String(value.classification),
    reason: String(value.reason ?? ""),
  };
}

function validateTransition(
  value: JsonValue,
  index: number,
  timePointIds: string[],
  errors: string[],
): KinaseTransition | null {
  const path = `result.transitions[${index}]`;
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, TRANSITION_FIELDS, path, errors);
  if (!nonempty(value.transition_id)) errors.push(`${path}.transition_id must be non-empty.`);
  if (value.transition_index !== index) errors.push(`${path}.transition_index must equal ${index}.`);
  if (value.from_time_point_id !== timePointIds[index] || value.to_time_point_id !== timePointIds[index + 1]) {
    errors.push(`${path} endpoints must match consecutive result time points.`);
  }
  if (!SUPPORTS.has(String(value.support))) errors.push(`${path}.support must be limited or abstained.`);
  if (!CLASSIFICATIONS.has(String(value.classification))) errors.push(`${path}.classification is invalid.`);
  if (!validNullableNumber(value.score)) errors.push(`${path}.score must be finite or null.`);
  const uncertainty = validateUncertainty(value.uncertainty, `${path}.uncertainty`, errors);
  for (const [field, maximum] of [
    ["exact_source_row_count", 4_096], ["exact_family_count", 2_457],
    ["censored_family_count", 2_457], ["selected_kinase_count", 24],
    ["estimable_kinase_count", 24],
  ] as const) {
    if (!integer(value[field], 0, maximum)) errors.push(`${path}.${field} is outside its contract bounds.`);
  }
  if (value.selected_kinase_count !== 12) errors.push(`${path}.selected_kinase_count must equal the locked 12-kinase family.`);
  const reasons = validStringArray(value.reasons, 0, 12) ? value.reasons : null;
  if (!reasons) errors.push(`${path}.reasons must contain at most twelve non-empty strings.`);
  const rawKinases = Array.isArray(value.kinase_signatures) ? value.kinase_signatures : [];
  const rawSubtypes = Array.isArray(value.subtype_signatures) ? value.subtype_signatures : [];
  const rawAblations = Array.isArray(value.ablations) ? value.ablations : [];
  if (rawKinases.length !== 24) errors.push(`${path}.kinase_signatures must contain the 24 locked hypotheses.`);
  if (rawSubtypes.length !== 4) errors.push(`${path}.subtype_signatures must contain GPM, MTC, NEU, PPR in order.`);
  if (rawAblations.length !== 3) errors.push(`${path}.ablations must contain the three locked ablations in order.`);
  const kinases = rawKinases.flatMap((item, itemIndex) => {
    const expected = LONGITUDINAL_GBM_KINASE_TRANSITION_INVENTORY[itemIndex];
    return expected ? validateKinaseSignature(item, expected, `${path}.kinase_signatures[${itemIndex}]`, errors) ?? [] : [];
  });
  const selectedCounts = [0, 0, 7, 5];
  const subtypes = rawSubtypes.flatMap((item, itemIndex) => {
    const subtype = LONGITUDINAL_GBM_KINASE_TRANSITION_SUBTYPES[itemIndex];
    return subtype ? validateSubtypeSignature(item, subtype, selectedCounts[itemIndex], `${path}.subtype_signatures[${itemIndex}]`, errors) ?? [] : [];
  });
  const ablations = rawAblations.flatMap((item, itemIndex) => (
    validateAblation(item, ABLATION_ORDER[itemIndex] ?? "", `${path}.ablations[${itemIndex}]`, errors) ?? []
  ));
  const estimable = kinases.filter((item) => item.selectionState !== "not_selected" && item.score !== null).length;
  if (value.estimable_kinase_count !== estimable) errors.push(`${path}.estimable_kinase_count must equal its estimable selected signatures.`);
  const subtypeEstimable = subtypes.reduce((total, item) => total + item.estimableKinases, 0);
  if (subtypeEstimable !== estimable) errors.push(`${path}.subtype_signatures estimable counts must close to the transition count.`);
  const abstained = value.support === "abstained";
  if (
    abstained
      ? value.score !== null || value.classification !== "not_estimable" || uncertainty?.state !== "not_estimable" || !reasons?.length
      : value.score === null || value.classification === "not_estimable" || uncertainty?.state !== "estimated" || !reasons?.length
  ) errors.push(`${path} support, score, interval, classification, and reasons do not close.`);
  if (!abstained && uncertainty?.state === "estimated" && value.classification !== intervalClassification(uncertainty.lower!, uncertainty.upper!)) {
    errors.push(`${path}.classification must be derived from its interval.`);
  }
  if (!uncertainty || !reasons) return null;
  return {
    id: String(value.transition_id),
    index,
    fromTimePointId: String(value.from_time_point_id),
    toTimePointId: String(value.to_time_point_id),
    support: value.support as KinaseTransitionSupport,
    classification: String(value.classification),
    score: finite(value.score) ? value.score : null,
    uncertainty,
    exactSourceRows: finite(value.exact_source_row_count) ? value.exact_source_row_count : 0,
    exactFamilies: finite(value.exact_family_count) ? value.exact_family_count : 0,
    censoredFamilies: finite(value.censored_family_count) ? value.censored_family_count : 0,
    selectedKinases: finite(value.selected_kinase_count) ? value.selected_kinase_count : 0,
    estimableKinases: finite(value.estimable_kinase_count) ? value.estimable_kinase_count : 0,
    kinases,
    subtypes,
    ablations,
    reasons,
    raw: value,
  };
}

export function validateKinaseTransitionProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (profile.algorithm_id !== "kncc-gbm-longitudinal-kinase-transition") errors.push("profile.algorithm_id is invalid.");
  if (profile.algorithm_version !== "1.0.0") errors.push("profile.algorithm_version must equal 1.0.0.");
  if (profile.profile_id !== LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID) errors.push("profile.profile_id is invalid.");
  if (profile.model_id !== "kncc-pdc000515-sphinks-signature-transition/1.0.0") errors.push("profile.model_id is invalid.");
  if (!sameJson(profile.required_assay_compatibility, REQUIRED_ASSAY)) errors.push("profile.required_assay_compatibility must match the locked PDC000515 assay attestation.");
  const constants = objectAt(profile, ["constants"]);
  if (!constants) errors.push("profile.constants must be an object.");
  else {
    exactFields(constants, CONSTANT_FIELDS, "profile.constants", errors);
    const expected: JsonObject = {
      hypothesis_family: "fixed_24_sphinks_master_kinases_bh_v1",
      family_projection: "residue_stratified_rank_concordance_v1",
      inverse_multiplicity_policy: "global_selected_membership_inverse_count_v1",
      composite_site_policy: "source_composite_groups_indivisible_v1",
      missing_evidence_policy: "missing_and_unsupported_never_become_negative_v1",
      censoring_policy: "one_sided_bounds_retained_excluded_from_point_score_v1",
      bootstrap_policy: "exact_patient_refit_sparse_family_projection_v1",
      measurement_policy: "deterministic_independent_gaussian_reported_se_v1",
      fdr_threshold: 0.1,
      minimum_kinase_families: 3,
      minimum_source_weight_coverage: 0.25,
      core_stability_threshold: 0.8,
      alignment_threshold: 0.05,
      maximum_top_drivers: 8,
      quantization_decimals: 8,
    };
    if (!sameJson(constants, expected)) errors.push("profile.constants must match the version-locked inference policy.");
  }
  const counts = objectAt(profile, ["counts"]);
  if (!counts) errors.push("profile.counts must be an object.");
  else {
    exactFields(counts, COUNT_FIELDS, "profile.counts", errors);
    if (!sameJson(counts, {
      strict_patient_pairs: 88,
      exact_crosswalk_pdc_rows: 8_779,
      unique_crosswalk_families: 8_533,
      duplicate_family_extra_pdc_rows: 246,
      signature_pdc_rows: 608,
      unique_signature_families: 572,
      release_eligible_background_families: 2_457,
      fixed_master_kinase_hypotheses: 24,
      full_fit_selected_kinases: 12,
      core_stable_selected_kinases: 11,
      patient_bootstrap_replicates: 64,
    })) errors.push("profile.counts must match the locked source inventory.");
  }
  const digests = objectAt(profile, ["digests"]);
  if (!digests) errors.push("profile.digests must be an object.");
  else {
    exactFields(digests, DIGEST_FIELDS, "profile.digests", errors);
    for (const field of DIGEST_FIELDS) if (!digest(digests[field])) errors.push(`profile.digests.${field} must be a lowercase sha256 digest.`);
  }
  const gates = objectAt(profile, ["quality_gates"]);
  if (!gates) errors.push("profile.quality_gates must be an object.");
  else {
    exactFields(gates, QUALITY_GATE_FIELDS, "profile.quality_gates", errors);
    if (!sameJson(gates, {
      same_assay_independent_evidence_gate_passed: false,
      patient_bootstrap_full_refit_convergence_gate_passed: true,
      patient_bootstrap_full_set_stability_gate_passed: false,
      patient_bootstrap_interval_calibration_gate_passed: false,
      output_policy: "all_estimable_outputs_limited_otherwise_abstained",
    })) errors.push("profile.quality_gates must preserve the LIMITED release ceiling.");
  }
  validateSourceProvenance(profile.source_provenance, "profile.source_provenance", errors);
  if (profile.numpy_version !== "2.5.2") errors.push("profile.numpy_version must equal 2.5.2.");
  if (profile.demo_id !== LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_ID) errors.push("profile.demo_id is invalid.");
  if (profile.demo_request_digest !== LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_DIGEST) errors.push("profile.demo_request_digest is invalid.");
  if (profile.demo_semantic_oracle_digest !== LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_ORACLE_DIGEST) errors.push("profile.demo_semantic_oracle_digest is invalid.");
  if (profile.source_attestation_state !== "verified_exact_snapshots") errors.push("profile.source_attestation_state is invalid.");
  if (profile.safety_class !== "research_use_only") errors.push("profile.safety_class must remain research_use_only.");
  if (profile.claim_ceiling !== "SPHINKS_signature_transition_concordance_only") errors.push("profile.claim_ceiling exceeds the signature-concordance-only boundary.");
  if (profile.profile_digest !== LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_DIGEST) errors.push("profile.profile_digest is not the pinned release digest.");
  if (profile.profile_digest !== kinaseTransitionProfileDigest(profile)) errors.push("profile.profile_digest must match canonical profile content.");
  return errors;
}

export function validateKinaseTransitionResult(result: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (result.algorithm_id !== "kncc-gbm-longitudinal-kinase-transition") errors.push("result.algorithm_id is invalid.");
  if (result.algorithm_version !== "1.0.0") errors.push("result.algorithm_version must equal 1.0.0.");
  if (result.profile_id !== LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID) errors.push("result.profile_id is invalid.");
  for (const field of ["profile_digest", "request_digest", "result_digest"] as const) {
    if (!digest(result[field])) errors.push(`result.${field} must be a lowercase sha256 digest.`);
  }
  if (result.result_digest !== kinaseTransitionResultDigest(result)) errors.push("result.result_digest must match canonical result content.");
  if (!nonempty(result.series_id)) errors.push("result.series_id must be non-empty.");
  if (!sameJson(result.assay_compatibility, REQUIRED_ASSAY)) errors.push("result.assay_compatibility must match the locked assay attestation.");
  if (!isJsonObject(result.normalization_reference)) errors.push("result.normalization_reference must be an object.");
  const timePointIds = strings(result.time_point_ids);
  if (!timePointIds || timePointIds.length < 2 || timePointIds.length > 16 || !unique(timePointIds)) {
    errors.push("result.time_point_ids must contain 2 through 16 unique identifiers.");
  }
  const rawTransitions = Array.isArray(result.transitions) ? result.transitions : [];
  if (!timePointIds || rawTransitions.length !== Math.max(0, timePointIds.length - 1)) {
    errors.push("result.transitions must contain one transition per consecutive time-point pair.");
  }
  if (timePointIds) rawTransitions.forEach((item, index) => validateTransition(item, index, timePointIds, errors));
  const provenance = objectAt(result, ["provenance"]);
  if (!provenance) errors.push("result.provenance must be an object.");
  else {
    exactFields(provenance, PROVENANCE_FIELDS, "result.provenance", errors);
    if (provenance.engine !== LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID) errors.push("result.provenance.engine is invalid.");
    for (const field of [
      "request_digest", "profile_digest", "fitted_artifact_content_digest",
      "fitted_artifact_byte_digest", "bootstrap_ensemble_digest", "engine_semantic_digest",
      "assay_compatibility_digest", "normalization_reference_digest", "computational_digest",
      "numerical_seed_digest",
    ] as const) if (!digest(provenance[field])) errors.push(`result.provenance.${field} must be a lowercase sha256 digest.`);
    if (provenance.request_digest !== result.request_digest || provenance.profile_digest !== result.profile_digest) {
      errors.push("result request/profile digests must close to provenance.");
    }
    if (provenance.assay_compatibility_digest !== kinaseTransitionValueDigest(REQUIRED_ASSAY)) {
      errors.push("result.provenance.assay_compatibility_digest must bind the exact assay attestation.");
    }
    if (isJsonObject(result.normalization_reference) && provenance.normalization_reference_digest !== result.normalization_reference.binding_digest) {
      errors.push("result.provenance.normalization_reference_digest must match the returned binding digest.");
    }
    const sourceDigests = strings(provenance.observation_source_digests);
    if (!sourceDigests || !sourceDigests.length || sourceDigests.some((item) => !DIGEST.test(item)) || !unique(sourceDigests) || sourceDigests.join("|") !== [...sourceDigests].sort().join("|")) {
      errors.push("result.provenance.observation_source_digests must be non-empty sorted unique digests.");
    }
    if (provenance.source_attestation_state !== "verified_exact_snapshots") errors.push("result.provenance.source_attestation_state is invalid.");
    validateSourceProvenance(provenance.source_provenance, "result.provenance.source_provenance", errors);
    if (provenance.numpy_version !== "2.5.2") errors.push("result.provenance.numpy_version must equal 2.5.2.");
  }
  if (result.output_semantics !== "SPHINKS_signature_transition_concordance_only") errors.push("result.output_semantics exceeds the signature-concordance-only boundary.");
  if (!validStringArray(result.limitations, 1, 16)) errors.push("result.limitations must contain 1 through 16 non-empty strings.");
  if (result.research_use_only !== true || result.non_prescriptive !== true) errors.push("result must remain research-use-only and non-prescriptive.");
  for (const field of ["infers_kinase_activity", "infers_biochemical_activity", "makes_causal_claim", "independent_evidence"] as const) {
    if (result[field] !== false) errors.push(`result.${field} must remain false.`);
  }
  return errors;
}

function observationProvenanceDigests(request: JsonObject): string[] {
  const values = arrayAt(request, ["time_points"]).flatMap((point) => (
    isJsonObject(point) ? arrayAt(point, ["observations"]) : []
  )).flatMap((observation) => (
    isJsonObject(observation) && digest(observation.provenance_digest)
      ? [observation.provenance_digest]
      : []
  ));
  return [...new Set(values)].sort();
}

export function validateKinaseTransitionDemo(
  request: JsonObject,
  headers: HeaderReader,
  profile: JsonObject,
): string[] {
  const errors = [
    ...validateKinaseTransitionRequest(request),
    ...validateKinaseTransitionProfile(profile),
  ];
  const requestDigest = kinaseTransitionRequestDigest(request);
  if (requestDigest !== LONGITUDINAL_GBM_KINASE_TRANSITION_DEMO_DIGEST) errors.push("demo request does not match the pinned demo digest.");
  if (profile.demo_request_digest !== requestDigest) errors.push("demo request digest must match the admitted profile.");
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Request-Digest", requestDigest, errors);
  return errors;
}

export function validateKinaseTransitionResultRequestBinding(
  result: JsonObject,
  request: JsonObject,
): string[] {
  const errors: string[] = [];
  if (result.request_digest !== kinaseTransitionRequestDigest(request)) errors.push("result.request_digest must match the canonical submitted request.");
  if (result.series_id !== request.series_id) errors.push("result.series_id must match the submitted request.");
  if (result.profile_id !== (request.profile_id ?? LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID)) errors.push("result.profile_id must match the submitted request.");
  if (!sameJson(result.assay_compatibility, request.assay_compatibility)) errors.push("result.assay_compatibility must exactly match the submitted request.");
  const normalized = normalizedRequestForDigest(request);
  if (!sameJson(result.normalization_reference, normalized.normalization_reference)) errors.push("result.normalization_reference must exactly match the defaulted submitted request.");
  const requestIds = arrayAt(request, ["time_points"]).flatMap((item) => (
    isJsonObject(item) && typeof item.time_point_id === "string" ? [item.time_point_id] : []
  ));
  if (!sameJson(result.time_point_ids, requestIds)) errors.push("result.time_point_ids must match the submitted request order.");
  const provenance = objectAt(result, ["provenance"]);
  if (provenance && !sameJson(provenance.observation_source_digests, observationProvenanceDigests(request))) {
    errors.push("result.provenance.observation_source_digests must exactly bind submitted evidence provenance.");
  }
  return errors;
}

export function validateKinaseTransitionResultProfileBinding(
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors = validateKinaseTransitionProfile(profile);
  if (result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest must match the admitted profile.");
  if (!sameJson(result.assay_compatibility, profile.required_assay_compatibility)) errors.push("result assay compatibility must match the admitted profile.");
  const provenance = objectAt(result, ["provenance"]);
  const digests = objectAt(profile, ["digests"]);
  if (provenance && digests) {
    for (const field of ["fitted_artifact_content_digest", "fitted_artifact_byte_digest", "bootstrap_ensemble_digest", "engine_semantic_digest"] as const) {
      if (provenance[field] !== digests[field]) errors.push(`result.provenance.${field} must match the admitted profile.`);
    }
    if (!sameJson(provenance.source_provenance, profile.source_provenance)) errors.push("result source provenance must match the admitted profile.");
  }
  return errors;
}

function validateDigestHeader(
  headers: HeaderReader,
  name: string,
  expected: JsonValue | undefined,
  errors: string[],
): void {
  if (!digest(expected)) {
    errors.push(`${name} cannot be bound to a malformed expected digest.`);
    return;
  }
  if (headers.get(name) !== expected) errors.push(`${name} response header must equal ${expected}.`);
}

export function validateKinaseTransitionProfileHeaders(headers: HeaderReader, profile: JsonObject): string[] {
  const errors = validateKinaseTransitionProfile(profile);
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  return errors;
}

export function validateKinaseTransitionResultHeaders(
  headers: HeaderReader,
  result: JsonObject,
  request: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Request-Digest", kinaseTransitionRequestDigest(request), errors);
  validateDigestHeader(headers, "X-GLIO-Result-Digest", kinaseTransitionResultDigest(result), errors);
  return errors;
}

export function validateKinaseTransitionVerification(
  verification: JsonObject,
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors = validateKinaseTransitionProfile(profile);
  exactFields(verification, VERIFICATION_FIELDS, "verification", errors);
  const checks = [
    "request_digest_match", "profile_digest_match", "result_digest_match",
    "transition_semantic_match", "semantic_match",
  ] as const;
  for (const field of [...checks, "verified"] as const) {
    if (typeof verification[field] !== "boolean") errors.push(`verification.${field} must be Boolean.`);
  }
  const transitionSemantic = verification.transition_semantic_match === true;
  if (verification.semantic_match !== transitionSemantic) errors.push("verification.semantic_match must close transition semantics.");
  const closed = checks.every((field) => verification[field] === true);
  if (verification.verified !== closed) errors.push("verification.verified must close every digest and semantic check.");
  if (verification.verified !== true || !closed) errors.push("verification did not exactly verify the admitted receipt.");
  for (const field of ["recomputed_request_digest", "recomputed_result_digest"] as const) {
    if (!digest(verification[field])) errors.push(`verification.${field} must be a lowercase sha256 digest.`);
  }
  if (verification.recomputed_request_digest !== result.request_digest) errors.push("verification recomputed request digest must match the admitted result.");
  if (verification.recomputed_result_digest !== result.result_digest) errors.push("verification recomputed result digest must match the admitted result.");
  if (result.profile_digest !== profile.profile_digest) errors.push("verification result/profile binding is not authoritative.");
  if (!nonempty(verification.message)) errors.push("verification.message must be non-empty.");
  return errors;
}

export function validateKinaseTransitionVerificationHeaders(
  headers: HeaderReader,
  verification: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Request-Digest", verification.recomputed_request_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Result-Digest", verification.recomputed_result_digest, errors);
  return errors;
}

export function normalizeKinaseTransitions(result: JsonObject): KinaseTransition[] {
  const timePointIds = strings(result.time_point_ids);
  if (!timePointIds) return [];
  const ignoredErrors: string[] = [];
  return arrayAt(result, ["transitions"]).flatMap((item, index) => (
    validateTransition(item, index, timePointIds, ignoredErrors) ?? []
  ));
}

export function kinaseTransitionEstimatedCount(transitions: KinaseTransition[]): number {
  return transitions.reduce((total, transition) => total + transition.estimableKinases, 0);
}

export function kinaseTransitionSignatureCount(transitions: KinaseTransition[]): number {
  return transitions.reduce((total, transition) => total + transition.kinases.length, 0);
}
