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
  LONGITUDINAL_GBM_PROFILE_ID,
  longitudinalRequestStats,
  validateLongitudinalRequest,
} from "./longitudinal-gbm";

export const LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID =
  "kncc-neftel-program-transition/1.0.0";
export const LONGITUDINAL_GBM_NEFTEL_TRANSITION_MODEL_ID =
  "kncc-neftel-program-transition-model/1.0.0";
export const LONGITUDINAL_GBM_NEFTEL_PROGRAM_COUNT = 8;
export const LONGITUDINAL_GBM_NEFTEL_PROGRAM_IDS = [
  "MES2",
  "MES1",
  "AC",
  "OPC",
  "NPC1",
  "NPC2",
  "G1/S",
  "G2/M",
] as const;
export const LONGITUDINAL_GBM_NEFTEL_MAX_SOLVER_WORK_UNITS = 4_608;

export type NeftelTransitionSupport = "supported" | "limited" | "abstained";

export type NeftelRequestStats = {
  timePoints: number;
  transitions: number;
  observations: number;
  active: number;
  genes: number;
};

export type NeftelGlobalConcordance = {
  support: NeftelTransitionSupport;
  classification: string;
  score: number | null;
  lower: number | null;
  upper: number | null;
  admittedActiveGenes: number;
  informativeActiveGenes: number;
  observedCount: number;
  bindingLeftCensoredCount: number;
  admittedLeftCensoredCount: number;
  coefficientMassCoverage: number;
  effectiveSampleSize: number | null;
  bootstrapReplicates: number;
  reasons: string[];
};

export type NeftelUncertainty = {
  state: string;
  measurementStandardError: number | null;
  fittedModelStandardError: number | null;
  measurementModelCovariance: number | null;
  combinedStandardError: number | null;
  varianceClosureResidual: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type NeftelContribution = {
  geneSymbol: string;
  fromObservationId: string;
  toObservationId: string;
  standardizedDelta: number | null;
  programLoading: number | null;
  globalLoading: number | null;
  unadjustedContribution: number | null;
  globalAdjustmentContribution: number | null;
  conditionalContribution: number | null;
  direction: string;
  reliabilityWeight: number | null;
};

export type NeftelAblationKind =
  | "global_axis"
  | "source_processing"
  | "degree_normalization"
  | "unique_members"
  | "leave_program_out"
  | "overlapping_program"
  | "top_contribution";

export type NeftelAblation = {
  kind: NeftelAblationKind;
  componentId: string;
  support: NeftelTransitionSupport;
  scoreWithout: number | null;
  scoreDelta: number | null;
  classificationWithout: string;
  removedFeatureCount: number;
  reason: string;
};

export type NeftelProgramConcordance = {
  programIndex: number;
  domainId: string;
  programId: string;
  programName: string;
  support: NeftelTransitionSupport;
  classification: string;
  score: number | null;
  lower: number | null;
  upper: number | null;
  unadjustedCoordinate: number | null;
  globalAdjustment: number | null;
  sourceMemberCount: number;
  mappedFeatureCount: number;
  fittedFeatureCount: number;
  admittedActiveFeatureCount: number;
  activeFeatureCount: number;
  observedCount: number;
  leftCensoredCount: number;
  admittedLeftCensoredCount: number;
  coefficientMassCoverage: number;
  uniqueActiveGeneCount: number;
  uniqueCoefficientMass: number;
  effectiveSampleSize: number | null;
  reconstructionImprovedFoldCount: number;
  reconstructionEvaluableFoldCount: number;
  reconstructionMedianRelativeGain: number | null;
  stability: number | null;
  discordance: number | null;
  overlapConfounded: boolean;
  uncertainty: NeftelUncertainty;
  contributions: NeftelContribution[];
  ablations: NeftelAblation[];
  reasons: string[];
  raw: JsonObject;
};

export type NeftelConditionalTransition = {
  id: string;
  index: number;
  fromTimePointId: string;
  toTimePointId: string;
  durationDays: number | null;
  global: NeftelGlobalConcordance;
  programs: NeftelProgramConcordance[];
  raw: JsonObject;
};

export type NeftelEvaluationSummary = {
  protocol: string;
  validationScope: string;
  interpretation: string;
  patientCount: number;
  evaluationCount: number;
  zeroPredictionMedianMae: number | null;
  globalOnlyMedianMae: number | null;
  equalMembershipMedianMae: number | null;
  jointMedianMae: number | null;
  jointVsGlobalMedianGain: number | null;
  jointVsEqualMedianGain: number | null;
  jointVsEqualImprovedFraction: number | null;
  patientClusterJointVsGlobalGain: number | null;
  patientClusterJointVsEqualGain: number | null;
  patientClusterJointVsEqualInterval: [number | null, number | null];
  patientClusterBootstrapReplicates: number;
  conditionNumber: number | null;
  minimumOuterLoadingCosine: number | null;
  allPrimaryFitsConverged: boolean;
  allLeaveProgramIntervalsCrossZero: boolean;
  releaseGate: string;
  individuallySupportedProgramCount: number;
  jointVsGlobalIntervalSupportsPositiveGain: boolean;
  jointVsEqualIntervalSupportsPositiveGain: boolean;
};

const SUPPORT_VALUES = new Set<NeftelTransitionSupport>([
  "supported",
  "limited",
  "abstained",
]);
const GLOBAL_CLASSIFICATIONS = new Set([
  "source_later_timepoint_aligned",
  "source_earlier_timepoint_aligned",
  "stable",
  "indeterminate",
  "not_estimable",
]);
const PROGRAM_CLASSIFICATIONS = new Set([
  "conditional_source_later_timepoint_aligned",
  "conditional_source_earlier_timepoint_aligned",
  "conditionally_stable",
  "indeterminate",
  "not_estimable",
]);
const PROFILE_INTERPRETATION =
  "global_adjusted_neftel_program_coordinate_not_recurrence_prediction_evolution_"
  + "subtype_deconvolution_or_activation";
const EVALUATION_INTERPRETATION =
  "aggregate metrics compare a fitted conditional program dictionary with zero, "
  + "global-only, and equal-membership baselines; individual program evidence is "
  + "limited to its held-marker removal interval";
const PROFILE_CLAIM_CEILING =
  "paired_source_cohort_bulk_protein_program_transition_concordance_only";
const ABLATION_KINDS = new Set<NeftelAblationKind>([
  "global_axis",
  "source_processing",
  "degree_normalization",
  "unique_members",
  "leave_program_out",
  "overlapping_program",
  "top_contribution",
]);
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const RESULT_FLOAT_FIELDS = new Set([
  "coefficient_mass_coverage",
  "combined_standard_error",
  "conditional_contribution",
  "conditional_score_without_component",
  "discordance",
  "duration_days",
  "effective_sample_size",
  "fitted_model_standard_error",
  "global_adjustment",
  "global_adjustment_contribution",
  "global_loading",
  "interval_level",
  "lower_bound",
  "measurement_model_covariance",
  "measurement_standard_error",
  "program_loading",
  "reliability_weight",
  "request_reconstruction_median_relative_gain",
  "score",
  "score_delta",
  "stability",
  "standardized_delta",
  "unadjusted_contribution",
  "unadjusted_program_coordinate",
  "unique_coefficient_mass",
  "upper_bound",
  "variance_closure_residual",
]);
const REQUEST_FLOAT_FIELDS = new Set([
  "log_abundance",
  "quality_weight",
  "standard_error",
  "time_offset_days",
]);
const PROFILE_FLOAT_FIELDS = new Set([
  "aligned_threshold",
  "censor_binding_tolerance",
  "damping",
  "equal_membership_median_standardized_mae",
  "equal_membership_reference_design_condition_number",
  "global_minimum_coefficient_mass",
  "global_minimum_effective_sample_size",
  "global_only_median_standardized_mae",
  "global_ridge_multiplier",
  "huber_delta",
  "interval_level",
  "joint_median_standardized_mae",
  "joint_vs_equal_evaluation_improved_fraction",
  "joint_vs_equal_median_relative_mae_gain",
  "joint_vs_global_evaluation_improved_fraction",
  "joint_vs_global_median_relative_mae_gain",
  "maximum_condition_number",
  "minimum_evidence_reliability",
  "minimum_outer_loading_cosine",
  "outer_design_condition_maximum",
  "outer_design_condition_minimum",
  "outer_equal_membership_condition_maximum",
  "outer_equal_membership_condition_minimum",
  "patient_cluster_joint_vs_equal_median_gain",
  "patient_cluster_joint_vs_equal_median_gain_90_interval",
  "patient_cluster_joint_vs_global_median_gain",
  "patient_cluster_joint_vs_global_median_gain_90_interval",
  "program_minimum_coefficient_mass",
  "program_minimum_effective_sample_size",
  "program_minimum_unique_mass",
  "program_supported_minimum_reconstruction_gain",
  "program_supported_minimum_stability",
  "reference_design_condition_number",
  "ridge_lambda",
  "solver_tolerance",
  "stable_threshold",
  "zero_prediction_median_standardized_mae",
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
  0x6a09e667,
  0xbb67ae85,
  0x3c6ef372,
  0xa54ff53a,
  0x510e527f,
  0x9b05688c,
  0x1f83d9ab,
  0x5be0cd19,
]);
const RESULT_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "profile_digest",
  "request_digest",
  "result_digest",
  "series_id",
  "assay_compatibility",
  "normalization_reference",
  "time_point_ids",
  "transitions",
  "provenance",
  "output_semantics",
  "validation_scope",
  "limitations",
  "research_use_only",
  "non_prescriptive",
]);
const TRANSITION_FIELDS = new Set([
  "transition_id",
  "transition_index",
  "from_time_point_id",
  "to_time_point_id",
  "duration_days",
  "global_transition",
  "programs",
]);
const GLOBAL_FIELDS = new Set([
  "output_semantics",
  "support",
  "classification",
  "score",
  "lower_bound",
  "upper_bound",
  "interval_level",
  "admitted_active_gene_count",
  "shared_active_gene_count",
  "observed_count",
  "left_censored_count",
  "admitted_left_censored_count",
  "coefficient_mass_coverage",
  "effective_sample_size",
  "bootstrap_replicates_used",
  "abstention_reasons",
]);
const PROGRAM_FIELDS = new Set([
  "program_index",
  "domain_id",
  "program_id",
  "program_name",
  "output_semantics",
  "support",
  "classification",
  "score",
  "lower_bound",
  "upper_bound",
  "unadjusted_program_coordinate",
  "global_adjustment",
  "interval_level",
  "source_member_count",
  "mapped_feature_count",
  "fitted_feature_count",
  "admitted_active_feature_count",
  "active_feature_count",
  "observed_count",
  "left_censored_count",
  "admitted_left_censored_count",
  "coefficient_mass_coverage",
  "unique_active_gene_count",
  "unique_coefficient_mass",
  "effective_sample_size",
  "request_reconstruction_evaluable_fold_count",
  "request_reconstruction_improved_fold_count",
  "request_reconstruction_median_relative_gain",
  "stability",
  "discordance",
  "overlap_confounded",
  "uncertainty",
  "top_contributions",
  "ablations",
  "abstention_reasons",
]);
const UNCERTAINTY_FIELDS = new Set([
  "state",
  "measurement_standard_error",
  "fitted_model_standard_error",
  "measurement_model_covariance",
  "combined_standard_error",
  "variance_closure_residual",
  "bootstrap_replicates_used",
  "reason",
]);
const CONTRIBUTION_FIELDS = new Set([
  "gene_symbol",
  "from_observation_id",
  "to_observation_id",
  "from_provenance_digest",
  "to_provenance_digest",
  "from_state",
  "to_state",
  "value_semantics",
  "standardized_delta",
  "program_loading",
  "global_loading",
  "unadjusted_contribution",
  "global_adjustment_contribution",
  "conditional_contribution",
  "direction",
  "reliability_weight",
]);
const ABLATIONS_FIELDS = new Set([
  "global_axis",
  "source_processing",
  "degree_normalization",
  "unique_members",
  "leave_program_out",
  "overlap",
  "top_contributions",
]);
const ABLATION_FIELDS = new Set([
  "component_kind",
  "component_id",
  "support",
  "conditional_score_without_component",
  "score_delta",
  "classification_without_component",
  "removed_feature_count",
  "reason",
]);
const PROFILE_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "model_id",
  "parent_feature_axis_model_id",
  "parent_dependency_semantics",
  "required_assay_compatibility",
  "constants",
  "limits",
  "counts",
  "digests",
  "evaluation",
  "programs",
  "numpy_version",
  "demo_id",
  "demo_request_digest",
  "demo_semantic_oracle_digest",
  "source_attribution",
  "source_terms",
  "source_transformation_notice",
  "profile_digest",
  "safety_class",
  "claim_ceiling",
  "interpretation",
  "maximum_evidence_grade",
]);
const PROFILE_PROGRAM_FIELDS = new Set([
  "program_index",
  "domain_id",
  "program_id",
  "program_name",
  "source_member_count",
  "mapped_feature_count",
  "eligible_feature_count",
  "fitted_feature_count",
  "unique_fitted_feature_count",
  "overlap_confounded",
]);
const PROVENANCE_FIELDS = new Set([
  "engine",
  "request_digest",
  "profile_digest",
  "computational_digest",
  "numerical_seed_digest",
  "source_catalog_artifact_digest",
  "source_catalog_content_digest",
  "source_binding_digest",
  "fitted_source_catalog_binding_digest",
  "neftel_source_program_digest",
  "program_inventory_digest",
  "program_order_digest",
  "program_membership_digest",
  "membership_degree_digest",
  "gene_order_digest",
  "patient_order_rule_digest",
  "fitted_artifact_digest",
  "fitted_content_digest",
  "union_feature_digest",
  "reference_tensor_digest",
  "centering_scaling_digest",
  "reference_design_digest",
  "equal_membership_design_digest",
  "global_loading_digest",
  "conditional_loading_digest",
  "bootstrap_ensemble_digest",
  "bootstrap_seed_namespace_digest",
  "training_recipe_digest",
  "fold_policy_digest",
  "source_processing_ablation_digest",
  "evaluation_digest",
  "input_contract_schema_digest",
  "engine_semantic_digest",
  "demo_semantic_oracle_digest",
  "assay_compatibility_digest",
  "normalization_reference_digest",
  "caller_evidence_set_digest",
  "numpy_version",
  "bootstrap_seed",
  "source_patient_count",
  "source_attribution",
  "source_terms",
  "source_transformation_notice",
]);
const VERIFICATION_FIELDS = new Set([
  "verified",
  "request_digest_match",
  "profile_digest_match",
  "result_digest_match",
  "transition_topology_match",
  "global_transition_semantic_match",
  "program_semantic_match",
  "uncertainty_semantic_match",
  "ablation_semantic_match",
  "provenance_match",
  "document_semantic_match",
  "semantic_match",
  "recomputed_request_digest",
  "recomputed_result_digest",
  "message",
]);

type HeaderReader = Pick<Headers, "get">;

function exactFields(
  value: JsonObject,
  expected: ReadonlySet<string>,
  path: string,
  errors: string[],
): void {
  const unknown = Object.keys(value).filter((key) => !expected.has(key));
  const missing = [...expected].filter(
    (key) => !Object.prototype.hasOwnProperty.call(value, key),
  );
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
}

function strings(value: JsonValue | undefined): string[] | null {
  if (
    !Array.isArray(value)
    || value.some((item) => typeof item !== "string" || !item.trim())
  ) return null;
  return value as string[];
}

function finite(value: JsonValue | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function integer(
  value: JsonValue | undefined,
  minimum: number,
  maximum: number,
): value is number {
  return finite(value)
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum;
}

function digest(value: JsonValue | undefined): value is string {
  return typeof value === "string" && DIGEST.test(value);
}

function canonicalJson(value: JsonValue): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isJsonObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
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
      const sigma0 = rotateRight(before15, 7)
        ^ rotateRight(before15, 18)
        ^ (before15 >>> 3);
      const sigma1 = rotateRight(before2, 17)
        ^ rotateRight(before2, 19)
        ^ (before2 >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temporary1 = (
        h + sum1 + choice + SHA256_CONSTANTS[index] + words[index]
      ) >>> 0;
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
  return [...hash]
    .map((value) => value.toString(16).padStart(8, "0"))
    .join("");
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
  const exponent = Number.parseInt(sourceExponent, 10)
    + integralDigits
    - firstNonzero
    - 1;

  if (exponent < -4 || exponent >= 16) {
    const fraction = digits.length > 1 ? `.${digits.slice(1)}` : "";
    const exponentSign = exponent >= 0 ? "+" : "-";
    const exponentDigits = Math.abs(exponent).toString().padStart(2, "0");
    return `${sign}${digits[0]}${fraction}e${exponentSign}${exponentDigits}`;
  }
  if (exponent < 0) {
    return `${sign}0.${"0".repeat(-exponent - 1)}${digits}`;
  }
  const trailingZeroCount = exponent + 1 - digits.length;
  if (trailingZeroCount >= 0) {
    return `${sign}${digits}${"0".repeat(trailingZeroCount)}.0`;
  }
  const splitAt = exponent + 1;
  return `${sign}${digits.slice(0, splitAt)}.${digits.slice(splitAt)}`;
}

function canonicalResultJson(value: JsonValue, parentKey = ""): string {
  if (typeof value === "number" && RESULT_FLOAT_FIELDS.has(parentKey)) {
    return pythonFloatJson(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalResultJson(item)).join(",")}]`;
  }
  if (isJsonObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalResultJson(value[key], key)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function canonicalTypedJson(
  value: JsonValue,
  floatFields: ReadonlySet<string>,
  parentKey = "",
): string {
  if (typeof value === "number" && floatFields.has(parentKey)) {
    return pythonFloatJson(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalTypedJson(item, floatFields, parentKey)).join(",")}]`;
  }
  if (isJsonObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalTypedJson(value[key], floatFields, key)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function neftelTransitionResultDigest(result: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(result).filter(([key]) => key !== "result_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalResultJson(payload))}`;
}

function defaultedObservation(value: JsonValue): JsonValue {
  if (!isJsonObject(value)) return value;
  return {
    ...value,
    log_abundance: Object.prototype.hasOwnProperty.call(value, "log_abundance")
      ? value.log_abundance
      : null,
    standard_error: Object.prototype.hasOwnProperty.call(value, "standard_error")
      ? value.standard_error
      : null,
    quality_weight: Object.prototype.hasOwnProperty.call(value, "quality_weight")
      ? value.quality_weight
      : 1,
  };
}

function normalizedRequestForDigest(request: JsonObject): JsonObject {
  const reference = isJsonObject(request.normalization_reference)
    ? {
      ...request.normalization_reference,
      abundance_scale: request.normalization_reference.abundance_scale
        ?? "caller_supplied_log2_protein_abundance_ratio",
      invariant_across_time_points:
        request.normalization_reference.invariant_across_time_points ?? true,
    }
    : request.normalization_reference;
  const timePoints = Array.isArray(request.time_points)
    ? request.time_points.map((value) => {
      if (!isJsonObject(value) || !Array.isArray(value.observations)) return value;
      const observations = value.observations
        .map(defaultedObservation)
        .sort((left, right) => {
          if (!isJsonObject(left) || !isJsonObject(right)) return 0;
          const leftKey = `${String(left.gene_symbol)}\u0000${String(left.observation_id)}`;
          const rightKey = `${String(right.gene_symbol)}\u0000${String(right.observation_id)}`;
          return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
        });
      return { ...value, observations };
    })
    : request.time_points;
  return {
    ...request,
    profile_id: request.profile_id ?? LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID,
    normalization_reference: reference,
    time_points: timePoints,
    bootstrap_replicates: request.bootstrap_replicates ?? 64,
  };
}

export function neftelTransitionRequestDigest(request: JsonObject): string {
  const normalized = normalizedRequestForDigest(request);
  return `sha256:${sha256Hex(canonicalTypedJson(normalized, REQUEST_FLOAT_FIELDS))}`;
}

export function neftelTransitionProfileDigest(profile: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(profile).filter(([key]) => key !== "profile_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalTypedJson(payload, PROFILE_FLOAT_FIELDS))}`;
}

function expectedGlobalClassification(lower: number, upper: number): string {
  if (lower > 0.25) return "source_later_timepoint_aligned";
  if (upper < -0.25) return "source_earlier_timepoint_aligned";
  if (lower >= -0.25 && upper <= 0.25) return "stable";
  return "indeterminate";
}

function expectedProgramClassification(lower: number, upper: number): string {
  if (lower > 0.25) return "conditional_source_later_timepoint_aligned";
  if (upper < -0.25) return "conditional_source_earlier_timepoint_aligned";
  if (lower >= -0.25 && upper <= 0.25) return "conditionally_stable";
  return "indeterminate";
}

function sameJson(
  left: JsonValue | undefined,
  right: JsonValue | undefined,
): boolean {
  return left !== undefined
    && right !== undefined
    && canonicalJson(left) === canonicalJson(right);
}

function validateUncertainty(
  value: JsonValue | undefined,
  path: string,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, UNCERTAINTY_FIELDS, path, errors);
  const statistics = [
    "measurement_standard_error",
    "fitted_model_standard_error",
    "measurement_model_covariance",
    "combined_standard_error",
    "variance_closure_residual",
  ];
  if (value.state === "estimated") {
    statistics.forEach((field) => {
      if (!finite(value[field])) errors.push(`${path}.${field} must be finite.`);
    });
    for (const field of [
      "measurement_standard_error",
      "fitted_model_standard_error",
      "combined_standard_error",
      "variance_closure_residual",
    ] as const) {
      if (finite(value[field]) && value[field] < 0) {
        errors.push(`${path}.${field} must be nonnegative.`);
      }
    }
    if (!integer(value.bootstrap_replicates_used, 1, 256)) {
      errors.push(`${path}.bootstrap_replicates_used must be 1 through 256.`);
    }
    if (value.reason !== null) errors.push(`${path}.reason must be null when estimated.`);
  } else if (value.state === "not_estimable") {
    statistics.forEach((field) => {
      if (value[field] !== null) errors.push(`${path}.${field} must be null.`);
    });
    if (
      value.bootstrap_replicates_used !== 0
      || typeof value.reason !== "string"
      || !value.reason.trim()
    ) errors.push(`${path} must carry zero replicates and an abstention reason.`);
  } else errors.push(`${path}.state is invalid.`);
}

function validateAblation(
  value: JsonValue,
  path: string,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, ABLATION_FIELDS, path, errors);
  const kind = typeof value.component_kind === "string"
    ? ablationKind(value.component_kind)
    : null;
  const support = typeof value.support === "string"
    ? supportValue(value.support)
    : null;
  if (!kind) errors.push(`${path}.component_kind is invalid.`);
  if (!support) errors.push(`${path}.support is invalid.`);
  if (!integer(value.removed_feature_count, 0, 4_096)) {
    errors.push(`${path}.removed_feature_count must be 0 through 4096.`);
  }
  if (support === "abstained") {
    if (
      value.conditional_score_without_component !== null
      || value.score_delta !== null
      || value.classification_without_component !== "not_estimable"
      || typeof value.reason !== "string"
      || !value.reason.trim()
    ) errors.push(`${path} abstention fields are inconsistent.`);
  } else if (support) {
    if (
      !finite(value.conditional_score_without_component)
      || !finite(value.score_delta)
      || value.classification_without_component === "not_estimable"
    ) errors.push(`${path} requires finite estimated ablation fields.`);
  }
}

function validateGlobal(
  value: JsonValue | undefined,
  path: string,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, GLOBAL_FIELDS, path, errors);
  if (value.output_semantics !== "global_transition_concordance") {
    errors.push(`${path}.output_semantics is invalid.`);
  }
  const support = typeof value.support === "string"
    ? supportValue(value.support)
    : null;
  const classification = typeof value.classification === "string"
    && GLOBAL_CLASSIFICATIONS.has(value.classification)
    ? value.classification
    : null;
  if (!support) errors.push(`${path}.support is invalid.`);
  if (!classification) errors.push(`${path}.classification is invalid.`);
  if (support === "supported") {
    errors.push(`${path}.support exceeds the lane-wide LIMITED evidence ceiling.`);
  }
  if (value.interval_level !== 0.9) errors.push(`${path}.interval_level must equal 0.9.`);
  for (const field of [
    "admitted_active_gene_count",
    "shared_active_gene_count",
    "observed_count",
    "left_censored_count",
    "admitted_left_censored_count",
  ] as const) {
    if (!integer(value[field], 0, 4_096)) {
      errors.push(`${path}.${field} must be an integer from 0 through 4096.`);
    }
  }
  if (
    integer(value.shared_active_gene_count, 0, 4_096)
    && integer(value.observed_count, 0, 4_096)
    && integer(value.left_censored_count, 0, 4_096)
    && value.shared_active_gene_count !== value.observed_count + value.left_censored_count
  ) errors.push(`${path} informative global counts do not close.`);
  if (
    integer(value.admitted_active_gene_count, 0, 4_096)
    && integer(value.observed_count, 0, 4_096)
    && integer(value.admitted_left_censored_count, 0, 4_096)
    && value.admitted_active_gene_count
      !== value.observed_count + value.admitted_left_censored_count
  ) errors.push(`${path} admitted global counts do not close.`);
  if (
    integer(value.admitted_active_gene_count, 0, 4_096)
    && integer(value.shared_active_gene_count, 0, 4_096)
    && integer(value.admitted_left_censored_count, 0, 4_096)
    && integer(value.left_censored_count, 0, 4_096)
    && (
      value.admitted_active_gene_count < value.shared_active_gene_count
      || value.admitted_left_censored_count < value.left_censored_count
    )
  ) errors.push(`${path} informative global evidence cannot exceed admitted evidence.`);
  const reasons = strings(value.abstention_reasons);
  if (!reasons || reasons.length > 8) {
    errors.push(`${path}.abstention_reasons must contain at most 8 strings.`);
  }
  if (support === "abstained") {
    if (
      value.score !== null
      || value.lower_bound !== null
      || value.upper_bound !== null
      || value.classification !== "not_estimable"
      || value.bootstrap_replicates_used !== 0
      || !reasons?.length
    ) errors.push(`${path} abstention fields are inconsistent.`);
  } else if (support) {
    const score = value.score;
    const lower = value.lower_bound;
    const upper = value.upper_bound;
    const ordered = finite(score)
      && finite(lower)
      && finite(upper)
      && lower <= score
      && score <= upper;
    if (!ordered || !integer(value.bootstrap_replicates_used, 1, 256)) {
      errors.push(`${path} requires a finite ordered estimate and bootstraps.`);
    }
    if (
      ordered
      && classification
      && finite(lower)
      && finite(upper)
      && classification !== expectedGlobalClassification(lower, upper)
    ) errors.push(`${path}.classification must be supported by its 90% interval.`);
  }
}

function validateContribution(
  value: JsonValue,
  path: string,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, CONTRIBUTION_FIELDS, path, errors);
  for (const field of ["from_provenance_digest", "to_provenance_digest"] as const) {
    if (!digest(value[field])) errors.push(`${path}.${field} must be a sha256 digest.`);
  }
  if (
    value.from_state !== "observed"
    || value.to_state !== "observed"
    || value.value_semantics !== "exact_delta"
  ) errors.push(`${path} must decompose an exact observed-to-observed delta.`);
  if (
    !finite(value.reliability_weight)
    || value.reliability_weight <= 0
    || value.reliability_weight > 1
  ) errors.push(`${path}.reliability_weight must be in (0,1].`);
}

function validateProgram(
  value: JsonValue,
  expectedIndex: number,
  path: string,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, PROGRAM_FIELDS, path, errors);
  const expectedId = LONGITUDINAL_GBM_NEFTEL_PROGRAM_IDS[expectedIndex];
  if (
    value.program_index !== expectedIndex
    || value.domain_id !== "neftel_table_s2"
    || value.program_id !== expectedId
    || value.program_name !== expectedId
  ) errors.push(`${path} does not preserve the exact Neftel Table S2 program order.`);
  if (value.output_semantics !== "conditional_program_concordance") {
    errors.push(`${path}.output_semantics is invalid.`);
  }
  const support = typeof value.support === "string"
    ? supportValue(value.support)
    : null;
  const classification = typeof value.classification === "string"
    && PROGRAM_CLASSIFICATIONS.has(value.classification)
    ? value.classification
    : null;
  if (!support) errors.push(`${path}.support is invalid.`);
  if (!classification) errors.push(`${path}.classification is invalid.`);
  if (support === "supported") {
    errors.push(`${path}.support exceeds the lane-wide LIMITED evidence ceiling.`);
  }
  if (value.interval_level !== 0.9) errors.push(`${path}.interval_level must equal 0.9.`);
  for (const field of [
    "admitted_active_feature_count",
    "active_feature_count",
    "observed_count",
    "left_censored_count",
    "admitted_left_censored_count",
    "unique_active_gene_count",
  ] as const) {
    if (!integer(value[field], 0, 4_096)) {
      errors.push(`${path}.${field} must be an integer from 0 through 4096.`);
    }
  }
  if (
    integer(value.active_feature_count, 0, 4_096)
    && integer(value.observed_count, 0, 4_096)
    && integer(value.left_censored_count, 0, 4_096)
    && value.observed_count + value.left_censored_count !== value.active_feature_count
  ) errors.push(`${path} active feature counts do not close.`);
  if (
    integer(value.admitted_active_feature_count, 0, 4_096)
    && integer(value.observed_count, 0, 4_096)
    && integer(value.admitted_left_censored_count, 0, 4_096)
    && value.admitted_active_feature_count
      !== value.observed_count + value.admitted_left_censored_count
  ) errors.push(`${path} admitted feature counts do not close.`);
  if (
    integer(value.admitted_active_feature_count, 0, 4_096)
    && integer(value.active_feature_count, 0, 4_096)
    && integer(value.admitted_left_censored_count, 0, 4_096)
    && integer(value.left_censored_count, 0, 4_096)
    && (
      value.admitted_active_feature_count < value.active_feature_count
      || value.admitted_left_censored_count < value.left_censored_count
    )
  ) errors.push(`${path} informative program evidence cannot exceed admitted evidence.`);
  if (
    integer(value.unique_active_gene_count, 0, 4_096)
    && integer(value.active_feature_count, 0, 4_096)
    && value.unique_active_gene_count > value.active_feature_count
  ) errors.push(`${path}.unique_active_gene_count cannot exceed informative features.`);
  validateUncertainty(value.uncertainty, `${path}.uncertainty`, errors);
  const contributions = Array.isArray(value.top_contributions)
    ? value.top_contributions
    : null;
  if (!contributions || contributions.length > 10) {
    errors.push(`${path}.top_contributions must contain at most 10 entries.`);
  } else contributions.forEach((item, index) => {
    validateContribution(item, `${path}.top_contributions[${index}]`, errors);
  });
  const ablations = value.ablations;
  if (!isJsonObject(ablations)) errors.push(`${path}.ablations must be an object.`);
  else {
    exactFields(ablations, ABLATIONS_FIELDS, `${path}.ablations`, errors);
    for (const field of [
      "global_axis",
      "degree_normalization",
      "unique_members",
      "leave_program_out",
    ] as const) {
      const item = ablations[field];
      if (item !== null) validateAblation(item, `${path}.ablations.${field}`, errors);
    }
    for (const field of ["source_processing", "overlap", "top_contributions"] as const) {
      const items = Array.isArray(ablations[field]) ? ablations[field] : null;
      if (!items) errors.push(`${path}.ablations.${field} must be an array.`);
      else items.forEach((item, index) => {
        validateAblation(item, `${path}.ablations.${field}[${index}]`, errors);
      });
    }
  }
  const reasons = strings(value.abstention_reasons);
  if (!reasons || reasons.length > 12) {
    errors.push(`${path}.abstention_reasons must contain at most 12 strings.`);
  }
  if (support === "abstained") {
    if (
      value.classification !== "not_estimable"
      || value.score !== null
      || value.lower_bound !== null
      || value.upper_bound !== null
      || !reasons?.length
    ) errors.push(`${path} abstention fields are inconsistent.`);
  } else if (support) {
    const score = value.score;
    const lower = value.lower_bound;
    const upper = value.upper_bound;
    const ordered = finite(score)
      && finite(lower)
      && finite(upper)
      && lower <= score
      && score <= upper;
    if (!ordered) errors.push(`${path} requires a finite ordered estimate interval.`);
    if (
      ordered
      && classification
      && finite(lower)
      && finite(upper)
      && classification !== expectedProgramClassification(lower, upper)
    ) errors.push(`${path}.classification must be supported by its 90% interval.`);
    if (support === "limited" && !reasons?.length) {
      errors.push(`${path} LIMITED output requires an explicit limitation reason.`);
    }
  }
}

function stringValues(value: JsonValue | undefined): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function supportValue(value: string): NeftelTransitionSupport | null {
  return SUPPORT_VALUES.has(value as NeftelTransitionSupport)
    ? (value as NeftelTransitionSupport)
    : null;
}

function ablationKind(value: string): NeftelAblationKind | null {
  return ABLATION_KINDS.has(value as NeftelAblationKind)
    ? (value as NeftelAblationKind)
    : null;
}

export function neftelTransitionRequestStats(request: JsonObject): NeftelRequestStats {
  const stats = longitudinalRequestStats(request);
  return {
    ...stats,
    transitions: Math.max(0, stats.timePoints - 1),
  };
}

export function validateNeftelTransitionRequest(request: JsonObject): string[] {
  const profileErrors = request.profile_id === undefined
    || request.profile_id === LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID
    ? []
    : [`profile_id must equal ${LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID}.`];
  const parentCompatibleRequest: JsonObject = {
    ...request,
    profile_id: LONGITUDINAL_GBM_PROFILE_ID,
  };
  const stats = neftelTransitionRequestStats(request);
  const bootstrapReplicates = request.bootstrap_replicates;
  const workErrors = typeof bootstrapReplicates === "number"
    && Number.isInteger(bootstrapReplicates)
    && bootstrapReplicates >= 32
    && bootstrapReplicates <= 256
    && stats.transitions * (186 + 3 * bootstrapReplicates)
      > LONGITUDINAL_GBM_NEFTEL_MAX_SOLVER_WORK_UNITS
    ? [
      "request exceeds the 4608 solver-work-unit limit: "
        + "(time_points - 1) * (186 + 3 * bootstrap_replicates).",
    ]
    : [];
  return [
    ...profileErrors,
    ...validateLongitudinalRequest(parentCompatibleRequest),
    ...workErrors,
  ];
}

export function validateNeftelTransitionProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (
    profile.algorithm_id !== "kncc-neftel-program-transition"
    || profile.algorithm_version !== "1.0.0"
    || profile.profile_id !== LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID
    || profile.model_id !== LONGITUDINAL_GBM_NEFTEL_TRANSITION_MODEL_ID
  ) errors.push("profile algorithm/model identity is invalid.");
  if (
    profile.parent_feature_axis_model_id !== "kncc-paired-protein-transition/1.0.0"
    || profile.parent_dependency_semantics
      !== "feature_axis_and_assay_binding_only_no_runtime_delegation"
  ) errors.push("profile parent feature-axis dependency is invalid.");
  if (!digest(profile.profile_digest)) {
    errors.push("profile.profile_digest must be a lowercase sha256 digest.");
  } else if (profile.profile_digest !== neftelTransitionProfileDigest(profile)) {
    errors.push("profile.profile_digest does not match the canonical profile payload.");
  }
  if (profile.numpy_version !== "2.5.2") {
    errors.push("profile.numpy_version must equal the locked 2.5.2 runtime.");
  }
  if (
    profile.safety_class !== "research_use_only"
    || profile.claim_ceiling !== PROFILE_CLAIM_CEILING
    || profile.interpretation !== PROFILE_INTERPRETATION
    || profile.maximum_evidence_grade
      !== "limited_same_cohort_without_external_validation"
  ) errors.push("profile exceeds or differs from the admitted LIMITED claim ceiling.");
  for (const field of [
    "required_assay_compatibility",
    "constants",
    "limits",
    "counts",
    "digests",
    "evaluation",
  ] as const) {
    if (!isJsonObject(profile[field])) errors.push(`profile.${field} must be an object.`);
  }
  const counts = objectAt(profile, ["counts"]);
  if (counts && (
    counts.source_patient_count !== 104
    || counts.program_count !== LONGITUDINAL_GBM_NEFTEL_PROGRAM_COUNT
    || counts.fitted_union_feature_count !== 256
    || counts.offline_bootstrap_draw_count !== 128
  )) errors.push("profile counts do not match the locked 104-pair, 8-program fitted model.");
  const evaluation = objectAt(profile, ["evaluation"]);
  if (evaluation) {
    if (
      evaluation.validation_scope
        !== "same-cohort held-marker reconstruction; not external validation"
      || evaluation.interpretation !== EVALUATION_INTERPRETATION
      || evaluation.patient_count !== 104
      || evaluation.evaluation_count !== 520
      || evaluation.release_gate
        !== "limited_fitted_dictionary_not_preferred_to_equal_membership"
      || evaluation.joint_vs_global_patient_cluster_interval_supports_positive_gain
        !== true
      || evaluation.joint_vs_equal_patient_cluster_interval_supports_positive_gain
        !== false
      || evaluation.all_leave_program_q05_q95_intervals_cross_zero !== true
    ) errors.push("profile evaluation does not preserve the admitted LIMITED release gate.");
    if (
      !finite(evaluation.equal_membership_median_standardized_mae)
      || !finite(evaluation.joint_median_standardized_mae)
      || evaluation.joint_median_standardized_mae
        <= evaluation.equal_membership_median_standardized_mae
    ) errors.push("profile must expose that fitted program loadings lose to equal membership.");
    if (evaluation.individually_supported_program_count !== 0) {
      errors.push("profile must not claim an individually supported Neftel program.");
    }
  }
  const programs = Array.isArray(profile.programs) ? profile.programs : null;
  if (!programs || programs.length !== LONGITUDINAL_GBM_NEFTEL_PROGRAM_COUNT) {
    errors.push("profile.programs must contain the 8 exact Neftel Table S2 programs.");
  } else programs.forEach((item, index) => {
    const path = `profile.programs[${index}]`;
    if (!isJsonObject(item)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    exactFields(item, PROFILE_PROGRAM_FIELDS, path, errors);
    const expectedId = LONGITUDINAL_GBM_NEFTEL_PROGRAM_IDS[index];
    if (
      item.program_index !== index
      || item.domain_id !== "neftel_table_s2"
      || item.program_id !== expectedId
      || item.program_name !== expectedId
    ) errors.push(`${path} does not preserve the exact source program identity.`);
  });
  if (!strings(profile.source_terms)?.length) {
    errors.push("profile.source_terms must contain source-use terms.");
  }
  return errors;
}

export function validateNeftelTransitionResult(result: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (
    result.algorithm_id !== "kncc-neftel-program-transition"
    || result.algorithm_version !== "1.0.0"
    || result.profile_id !== LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID
  ) errors.push("result algorithm/profile identity is invalid.");
  for (const field of ["request_digest", "result_digest", "profile_digest"] as const) {
    if (!digest(result[field])) errors.push(`result.${field} must be a sha256 digest.`);
  }
  if (
    digest(result.result_digest)
    && result.result_digest !== neftelTransitionResultDigest(result)
  ) errors.push("result.result_digest does not match the canonical result payload.");
  if (
    result.output_semantics
      !== "global_transition_concordance_and_conditional_program_concordance_only"
    || result.validation_scope
      !== "same_cohort_patient_grouped_evaluation_not_external_validation"
    || result.research_use_only !== true
    || result.non_prescriptive !== true
  ) errors.push("result semantics exceed or differ from the admitted research boundary.");
  if (!isJsonObject(result.assay_compatibility)) {
    errors.push("result.assay_compatibility must be an object.");
  }
  if (!isJsonObject(result.normalization_reference)) {
    errors.push("result.normalization_reference must be an object.");
  }
  const timePointIds = strings(result.time_point_ids);
  if (
    !timePointIds
    || timePointIds.length < 2
    || timePointIds.length > 16
    || new Set(timePointIds).size !== timePointIds.length
  ) errors.push("result.time_point_ids must contain 2 through 16 unique identifiers.");
  const transitions = Array.isArray(result.transitions) ? result.transitions : null;
  if (!transitions || !timePointIds || transitions.length !== timePointIds.length - 1) {
    errors.push("result.transitions must contain one adjacent transition per time-point pair.");
  } else transitions.forEach((item, index) => {
    const path = `result.transitions[${index}]`;
    if (!isJsonObject(item)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    exactFields(item, TRANSITION_FIELDS, path, errors);
    if (
      item.transition_index !== index
      || item.from_time_point_id !== timePointIds[index]
      || item.to_time_point_id !== timePointIds[index + 1]
      || !finite(item.duration_days)
      || item.duration_days <= 0
    ) errors.push(`${path} does not match the ordered time-point topology.`);
    validateGlobal(item.global_transition, `${path}.global_transition`, errors);
    const programs = Array.isArray(item.programs) ? item.programs : null;
    if (!programs || programs.length !== LONGITUDINAL_GBM_NEFTEL_PROGRAM_COUNT) {
      errors.push(`${path}.programs must contain all 8 exact source programs.`);
    } else programs.forEach((program, programIndex) => {
      validateProgram(program, programIndex, `${path}.programs[${programIndex}]`, errors);
    });
  });
  const provenance = objectAt(result, ["provenance"]);
  if (!provenance) errors.push("result.provenance must be an object.");
  else {
    exactFields(provenance, PROVENANCE_FIELDS, "result.provenance", errors);
    if (
      provenance.engine !== LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID
      || provenance.source_patient_count !== 104
      || provenance.numpy_version !== "2.5.2"
      || provenance.request_digest !== result.request_digest
      || provenance.profile_digest !== result.profile_digest
    ) errors.push("result provenance identity does not close with the receipt.");
    for (const field of PROVENANCE_FIELDS) {
      if (field.endsWith("_digest") && !digest(provenance[field])) {
        errors.push(`result.provenance.${field} must be a sha256 digest.`);
      }
    }
  }
  const limitations = strings(result.limitations);
  if (!limitations || limitations.length < 6 || limitations.length > 20) {
    errors.push("result.limitations must contain 6 through 20 non-empty entries.");
  }
  return errors;
}

export function validateNeftelTransitionResultRequestBinding(
  result: JsonObject,
  request: JsonObject,
): string[] {
  const errors: string[] = [];
  const recomputedRequestDigest = neftelTransitionRequestDigest(request);
  if (result.request_digest !== recomputedRequestDigest) {
    errors.push("result.request_digest must match the canonical submitted request.");
  }
  if (result.series_id !== request.series_id) {
    errors.push("result.series_id must match the submitted request.");
  }
  if (request.profile_id !== undefined && result.profile_id !== request.profile_id) {
    errors.push("result.profile_id must match the submitted request.");
  }
  if (!sameJson(result.assay_compatibility, request.assay_compatibility)) {
    errors.push("result.assay_compatibility must exactly match the submitted request.");
  }
  if (!sameJson(result.normalization_reference, request.normalization_reference)) {
    errors.push("result.normalization_reference must exactly match the submitted request.");
  }
  const points = Array.isArray(request.time_points) ? request.time_points : [];
  const pointIds = points.flatMap((item) => (
    isJsonObject(item) && typeof item.time_point_id === "string"
      ? [item.time_point_id]
      : []
  ));
  if (!sameJson(result.time_point_ids, pointIds)) {
    errors.push("result.time_point_ids must exactly match the submitted request order.");
  }
  return errors;
}

export function validateNeftelTransitionResultProfileBinding(
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors = validateNeftelTransitionProfile(profile);
  if (result.profile_digest !== profile.profile_digest) {
    errors.push("result.profile_digest must match the admitted loaded profile.");
  }
  const digests = objectAt(profile, ["digests"]);
  const provenance = objectAt(result, ["provenance"]);
  if (digests && provenance) {
    for (const field of Object.keys(digests)) {
      if (field in provenance && provenance[field] !== digests[field]) {
        errors.push(`result.provenance.${field} must match profile.digests.${field}.`);
      }
    }
  }
  const profilePrograms = Array.isArray(profile.programs) ? profile.programs : [];
  const transitions = Array.isArray(result.transitions) ? result.transitions : [];
  transitions.forEach((transition, transitionIndex) => {
    if (!isJsonObject(transition) || !Array.isArray(transition.programs)) return;
    if (transition.programs.length !== profilePrograms.length) {
      errors.push(`result.transitions[${transitionIndex}] must contain every profile program.`);
      return;
    }
    transition.programs.forEach((program, index) => {
      const expected = profilePrograms[index];
      if (!isJsonObject(program) || !isJsonObject(expected)) return;
      if (
        program.program_index !== expected.program_index
        || program.domain_id !== expected.domain_id
        || program.program_id !== expected.program_id
        || program.program_name !== expected.program_name
      ) errors.push(`result.transitions[${transitionIndex}].programs[${index}] does not match the loaded profile identity.`);
    });
  });
  return errors;
}

function validateDigestHeader(
  headers: HeaderReader,
  name: string,
  expected: JsonValue | undefined,
  errors: string[],
): void {
  const value = headers.get(name);
  if (!digest(value ?? undefined)) {
    errors.push(`${name} response header must be a lowercase sha256 digest.`);
  } else if (value !== expected) {
    errors.push(`${name} response header must match the admitted payload.`);
  }
}

export function validateNeftelTransitionProfileHeaders(
  headers: HeaderReader,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  return errors;
}

export function validateNeftelTransitionResultHeaders(
  headers: HeaderReader,
  result: JsonObject,
  request?: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", result.profile_digest, errors);
  validateDigestHeader(
    headers,
    "X-GLIO-Request-Digest",
    request ? neftelTransitionRequestDigest(request) : result.request_digest,
    errors,
  );
  validateDigestHeader(headers, "X-GLIO-Result-Digest", result.result_digest, errors);
  return errors;
}

export function validateNeftelTransitionVerification(
  verification: JsonObject,
  result: JsonObject,
): string[] {
  const errors: string[] = [];
  exactFields(verification, VERIFICATION_FIELDS, "verification", errors);
  const semanticFields = [
    "transition_topology_match",
    "global_transition_semantic_match",
    "program_semantic_match",
    "uncertainty_semantic_match",
    "ablation_semantic_match",
    "provenance_match",
    "document_semantic_match",
  ];
  if (semanticFields.some((field) => verification[field] !== true)) {
    errors.push("verification semantic components must all be true.");
  }
  if (
    verification.verified !== true
    || verification.request_digest_match !== true
    || verification.profile_digest_match !== true
    || verification.result_digest_match !== true
    || verification.semantic_match !== true
  ) errors.push("verification must affirm every digest and semantic check.");
  if (
    verification.recomputed_request_digest !== result.request_digest
    || verification.recomputed_result_digest !== result.result_digest
  ) errors.push("verification recomputed digests must match the admitted receipt.");
  return errors;
}

export function validateNeftelTransitionVerificationHeaders(
  headers: HeaderReader,
  verification: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  validateDigestHeader(
    headers,
    "X-GLIO-Request-Digest",
    verification.recomputed_request_digest,
    errors,
  );
  validateDigestHeader(
    headers,
    "X-GLIO-Result-Digest",
    verification.recomputed_result_digest,
    errors,
  );
  return errors;
}

function normalizeUncertainty(value: JsonObject | null): NeftelUncertainty {
  return {
    state: value ? textAt(value, ["state"], "not_estimable") : "not_estimable",
    measurementStandardError: value ? numberAt(value, ["measurement_standard_error"]) : null,
    fittedModelStandardError: value ? numberAt(value, ["fitted_model_standard_error"]) : null,
    measurementModelCovariance: value ? numberAt(value, ["measurement_model_covariance"]) : null,
    combinedStandardError: value ? numberAt(value, ["combined_standard_error"]) : null,
    varianceClosureResidual: value ? numberAt(value, ["variance_closure_residual"]) : null,
    bootstrapReplicates: value ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0 : 0,
    reason: value ? textAt(value, ["reason"]) : "",
  };
}

function normalizeContribution(value: JsonValue): NeftelContribution | null {
  if (!isJsonObject(value)) return null;
  const geneSymbol = textAt(value, ["gene_symbol"]);
  if (!geneSymbol) return null;
  return {
    geneSymbol,
    fromObservationId: textAt(value, ["from_observation_id"]),
    toObservationId: textAt(value, ["to_observation_id"]),
    standardizedDelta: numberAt(value, ["standardized_delta"]),
    programLoading: numberAt(value, ["program_loading"]),
    globalLoading: numberAt(value, ["global_loading"]),
    unadjustedContribution: numberAt(value, ["unadjusted_contribution"]),
    globalAdjustmentContribution: numberAt(value, ["global_adjustment_contribution"]),
    conditionalContribution: numberAt(value, ["conditional_contribution"]),
    direction: textAt(value, ["direction"], "indeterminate"),
    reliabilityWeight: numberAt(value, ["reliability_weight"]),
  };
}

function normalizeAblation(value: JsonValue): NeftelAblation | null {
  if (!isJsonObject(value)) return null;
  const kind = ablationKind(textAt(value, ["component_kind"]));
  const support = supportValue(textAt(value, ["support"]));
  if (!kind || !support) return null;
  return {
    kind,
    componentId: textAt(value, ["component_id"], "unspecified-component"),
    support,
    scoreWithout: numberAt(value, ["conditional_score_without_component"]),
    scoreDelta: numberAt(value, ["score_delta"]),
    classificationWithout: textAt(value, ["classification_without_component"], "not_estimable"),
    removedFeatureCount: numberAt(value, ["removed_feature_count"]) ?? 0,
    reason: textAt(value, ["reason"]),
  };
}

function normalizeProgram(value: JsonValue): NeftelProgramConcordance | null {
  if (!isJsonObject(value)) return null;
  const support = supportValue(textAt(value, ["support"]));
  const programId = textAt(value, ["program_id"]);
  if (!support || !programId) return null;
  const ablations = objectAt(value, ["ablations"]);
  const scalarAblations = ablations
    ? [
      ablations.global_axis,
      ablations.degree_normalization,
      ablations.unique_members,
      ablations.leave_program_out,
    ]
    : [];
  const arrayAblations = ablations
    ? [
      ...arrayAt(ablations, ["source_processing"]),
      ...arrayAt(ablations, ["overlap"]),
      ...arrayAt(ablations, ["top_contributions"]),
    ]
    : [];
  return {
    programIndex: numberAt(value, ["program_index"]) ?? 0,
    domainId: textAt(value, ["domain_id"], programId),
    programId,
    programName: textAt(value, ["program_name"], programId),
    support,
    classification: textAt(value, ["classification"], "not_estimable"),
    score: numberAt(value, ["score"]),
    lower: numberAt(value, ["lower_bound"]),
    upper: numberAt(value, ["upper_bound"]),
    unadjustedCoordinate: numberAt(value, ["unadjusted_program_coordinate"]),
    globalAdjustment: numberAt(value, ["global_adjustment"]),
    sourceMemberCount: numberAt(value, ["source_member_count"]) ?? 0,
    mappedFeatureCount: numberAt(value, ["mapped_feature_count"]) ?? 0,
    fittedFeatureCount: numberAt(value, ["fitted_feature_count"]) ?? 0,
    admittedActiveFeatureCount: numberAt(value, ["admitted_active_feature_count"]) ?? 0,
    activeFeatureCount: numberAt(value, ["active_feature_count"]) ?? 0,
    observedCount: numberAt(value, ["observed_count"]) ?? 0,
    leftCensoredCount: numberAt(value, ["left_censored_count"]) ?? 0,
    admittedLeftCensoredCount: numberAt(value, ["admitted_left_censored_count"]) ?? 0,
    coefficientMassCoverage: numberAt(value, ["coefficient_mass_coverage"]) ?? 0,
    uniqueActiveGeneCount: numberAt(value, ["unique_active_gene_count"]) ?? 0,
    uniqueCoefficientMass: numberAt(value, ["unique_coefficient_mass"]) ?? 0,
    effectiveSampleSize: numberAt(value, ["effective_sample_size"]),
    reconstructionImprovedFoldCount: numberAt(value, ["request_reconstruction_improved_fold_count"]) ?? 0,
    reconstructionEvaluableFoldCount: numberAt(value, ["request_reconstruction_evaluable_fold_count"]) ?? 0,
    reconstructionMedianRelativeGain: numberAt(value, ["request_reconstruction_median_relative_gain"]),
    stability: numberAt(value, ["stability"]),
    discordance: numberAt(value, ["discordance"]),
    overlapConfounded: value.overlap_confounded === true,
    uncertainty: normalizeUncertainty(objectAt(value, ["uncertainty"])),
    contributions: arrayAt(value, ["top_contributions"])
      .flatMap((item) => normalizeContribution(item) ?? []),
    ablations: [...scalarAblations, ...arrayAblations]
      .flatMap((item) => normalizeAblation(item as JsonValue) ?? []),
    reasons: stringValues(value.abstention_reasons),
    raw: value,
  };
}

function normalizeGlobal(value: JsonObject | null): NeftelGlobalConcordance {
  const support = supportValue(value ? textAt(value, ["support"]) : "") ?? "abstained";
  return {
    support,
    classification: value ? textAt(value, ["classification"], "not_estimable") : "not_estimable",
    score: value ? numberAt(value, ["score"]) : null,
    lower: value ? numberAt(value, ["lower_bound"]) : null,
    upper: value ? numberAt(value, ["upper_bound"]) : null,
    admittedActiveGenes: value ? numberAt(value, ["admitted_active_gene_count"]) ?? 0 : 0,
    informativeActiveGenes: value ? numberAt(value, ["shared_active_gene_count"]) ?? 0 : 0,
    observedCount: value ? numberAt(value, ["observed_count"]) ?? 0 : 0,
    bindingLeftCensoredCount: value ? numberAt(value, ["left_censored_count"]) ?? 0 : 0,
    admittedLeftCensoredCount:
      value ? numberAt(value, ["admitted_left_censored_count"]) ?? 0 : 0,
    coefficientMassCoverage: value ? numberAt(value, ["coefficient_mass_coverage"]) ?? 0 : 0,
    effectiveSampleSize: value ? numberAt(value, ["effective_sample_size"]) : null,
    bootstrapReplicates: value ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0 : 0,
    reasons: value ? stringValues(value.abstention_reasons) : [],
  };
}

export function normalizeNeftelTransitions(result: JsonObject): NeftelConditionalTransition[] {
  return arrayAt(result, ["transitions"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const programs = arrayAt(value, ["programs"])
      .flatMap((item) => normalizeProgram(item) ?? [])
      .sort((left, right) => left.programIndex - right.programIndex);
    return [{
      id: textAt(value, ["transition_id"], "unnamed-transition"),
      index: numberAt(value, ["transition_index"]) ?? 0,
      fromTimePointId: textAt(value, ["from_time_point_id"], "unknown-from"),
      toTimePointId: textAt(value, ["to_time_point_id"], "unknown-to"),
      durationDays: numberAt(value, ["duration_days"]),
      global: normalizeGlobal(objectAt(value, ["global_transition"])),
      programs,
      raw: value,
    }];
  });
}

export function normalizeNeftelEvaluation(profile: JsonObject | null): NeftelEvaluationSummary | null {
  const value = profile ? objectAt(profile, ["evaluation"]) : null;
  if (!value) return null;
  const interval = arrayAt(value, ["patient_cluster_joint_vs_equal_median_gain_90_interval"]);
  return {
    protocol: textAt(value, ["protocol"], "not reported"),
    validationScope: textAt(value, ["validation_scope"], "not reported"),
    interpretation: textAt(value, ["interpretation"], "not reported"),
    patientCount: numberAt(value, ["patient_count"]) ?? 0,
    evaluationCount: numberAt(value, ["evaluation_count"]) ?? 0,
    zeroPredictionMedianMae: numberAt(value, ["zero_prediction_median_standardized_mae"]),
    globalOnlyMedianMae: numberAt(value, ["global_only_median_standardized_mae"]),
    equalMembershipMedianMae: numberAt(value, ["equal_membership_median_standardized_mae"]),
    jointMedianMae: numberAt(value, ["joint_median_standardized_mae"]),
    jointVsGlobalMedianGain: numberAt(value, ["joint_vs_global_median_relative_mae_gain"]),
    jointVsEqualMedianGain: numberAt(value, ["joint_vs_equal_median_relative_mae_gain"]),
    jointVsEqualImprovedFraction: numberAt(value, ["joint_vs_equal_evaluation_improved_fraction"]),
    patientClusterJointVsGlobalGain: numberAt(value, ["patient_cluster_joint_vs_global_median_gain"]),
    patientClusterJointVsEqualGain: numberAt(value, ["patient_cluster_joint_vs_equal_median_gain"]),
    patientClusterJointVsEqualInterval: [
      typeof interval[0] === "number" && Number.isFinite(interval[0]) ? interval[0] : null,
      typeof interval[1] === "number" && Number.isFinite(interval[1]) ? interval[1] : null,
    ],
    patientClusterBootstrapReplicates: numberAt(value, ["patient_cluster_bootstrap_replicates"]) ?? 0,
    conditionNumber: numberAt(value, ["reference_design_condition_number"]),
    minimumOuterLoadingCosine: numberAt(value, ["minimum_outer_loading_cosine"]),
    allPrimaryFitsConverged: value.all_primary_solver_fits_converged === true,
    allLeaveProgramIntervalsCrossZero:
      value.all_leave_program_q05_q95_intervals_cross_zero === true,
    releaseGate: textAt(value, ["release_gate"], "not reported"),
    individuallySupportedProgramCount:
      numberAt(value, ["individually_supported_program_count"]) ?? 0,
    jointVsGlobalIntervalSupportsPositiveGain:
      value.joint_vs_global_patient_cluster_interval_supports_positive_gain === true,
    jointVsEqualIntervalSupportsPositiveGain:
      value.joint_vs_equal_patient_cluster_interval_supports_positive_gain === true,
  };
}

export function neftelProgramCount(transitions: NeftelConditionalTransition[]): number {
  return transitions.reduce((count, transition) => count + transition.programs.length, 0);
}

export function neftelSupportedProgramCount(transitions: NeftelConditionalTransition[]): number {
  return transitions.reduce(
    (count, transition) => count + transition.programs.filter((program) => program.support === "supported").length,
    0,
  );
}

export function neftelEstimatedProgramCount(transitions: NeftelConditionalTransition[]): number {
  return transitions.reduce(
    (count, transition) => count + transition.programs.filter((program) => program.score !== null).length,
    0,
  );
}
