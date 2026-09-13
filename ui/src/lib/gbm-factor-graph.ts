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
import {
  LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  normalizeReactomeTransitions,
  reactomeTransitionRequestStats,
  validateReactomeTransitionRequest,
} from "./longitudinal-gbm-reactome-transition";
import { sha256Hex } from "./topology-provenance";

export const GBM_FACTOR_GRAPH_PROFILE_ID =
  "glio-ecgi-kncc-gbm-transition/1.0.0";
export const GBM_FACTOR_GRAPH_MODEL_ID =
  "glio-ecgi-kncc-gbm-factor-graph/1.0.0";
export const GBM_FACTOR_GRAPH_DEMO_ID =
  "kncc-gbm-factor-graph-synthetic-model-derived-v1";
export const GBM_FACTOR_GRAPH_RELATIONSHIP =
  "independent_parallel_source_cohort_concordance_no_cross_modal_fusion";
export const GBM_FACTOR_GRAPH_TOPOLOGY_ID =
  "kncc-gbm-independent-two-block-factor-topology/1.0.0";
export const GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST =
  "sha256:d9baef8ce0b125a26f547edd0441e05c772249fcef3ab57b95d0eea0c777f9c7";
export const GBM_FACTOR_GRAPH_KINASE_PROFILE_ID =
  "kncc-gbm-longitudinal-kinase-transition/1.0.0";
export const GBM_FACTOR_GRAPH_NODE_COUNT = 41;
export const GBM_FACTOR_GRAPH_EDGE_COUNT = 39;
export const GBM_FACTOR_GRAPH_MAX_TIME_POINTS = 5;

export type FactorGraphBlock = "protein_reactome" | "phosphosite_sphinks";
export type FactorGraphNodeKind =
  | "computation_block"
  | "global_recurrence_factor"
  | "reactome_pathway_factor"
  | "kinase_signature_factor"
  | "subtype_signature_factor";

export type FactorGraphNode = {
  id: string;
  block: FactorGraphBlock;
  kind: FactorGraphNodeKind;
  biologicalIdentifier: string;
  label: string;
  childProfileId: string;
  learnedSemantics:
    | "child_source_cohort_fitted_coordinate"
    | "child_result_container_only";
};

export type FactorGraphContainmentEdge = {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  relationship: "contains";
  computationalRole: "annotation_only";
  numericalWeight: null;
};

export type FactorGraphTopology = {
  id: string;
  digest: string;
  nodes: FactorGraphNode[];
  containmentEdges: FactorGraphContainmentEdge[];
  numericalCrossBlockEdgeCount: 0;
  containmentEdgeRole: "annotation_only";
};

export type FactorGraphRequestStats = {
  reactomeTimePoints: number;
  reactomeActive: number;
  kinaseTimePoints: number;
  kinaseActive: number;
  childTransitions: number;
};

export type KinaseTransitionSupport = "limited" | "abstained";
export type KinaseSubtype = "GPM" | "MTC" | "NEU" | "PPR";

export type KinaseTransitionUncertainty = {
  state: "estimated" | "not_estimable";
  lower: number | null;
  upper: number | null;
  standardError: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type KinaseFamilyDriver = {
  sourceSiteLabel: string;
  sourcePhosphositeIds: string[];
  stratum: string;
  composite: boolean;
  standardizedRank: number;
  adjustedSourceWeight: number;
  contribution: number;
  pairedSourceSupport: number;
};

export type KinaseSignatureTransition = {
  kinase: string;
  subtype: KinaseSubtype;
  selectionState: "selected_core" | "selected_unstable" | "not_selected";
  support: KinaseTransitionSupport;
  sourceDirection: string;
  sourceEnrichment: number | null;
  sourcePValue: number;
  sourceQValue: number;
  mappedFamilies: number;
  observedFamilies: number;
  sourceWeightCoverage: number;
  outerSelectionFrequency: number;
  bootstrapSelectionFrequency: number;
  bootstrapDirectionConsistency: number | null;
  score: number | null;
  classification: string;
  uncertainty: KinaseTransitionUncertainty;
  drivers: KinaseFamilyDriver[];
  reasons: string[];
};

export type KinaseSubtypeTransition = {
  subtype: KinaseSubtype;
  selectedKinases: number;
  estimableKinases: number;
  support: KinaseTransitionSupport;
  score: number | null;
  classification: string;
  uncertainty: KinaseTransitionUncertainty;
  reasons: string[];
};

export type KinaseSignatureAblation = {
  kind:
    | "equal_kinase_instead_of_equal_subtype"
    | "omit_composite_source_groups"
    | "omit_inverse_multiplicity_correction";
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
  kinaseSignatures: KinaseSignatureTransition[];
  subtypeSignatures: KinaseSubtypeTransition[];
  ablations: KinaseSignatureAblation[];
  reasons: string[];
  raw: JsonObject;
};

export type NormalizedFactorGraphResult = {
  reactomeResult: JsonObject;
  kinaseResult: JsonObject;
  reactomeTransitions: ReturnType<typeof normalizeReactomeTransitions>;
  kinaseTransitions: KinaseTransition[];
};

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const KINASE = /^[A-Z0-9][A-Z0-9-]{0,31}$/;
const REACTOME_ID = /^R-HSA-[1-9][0-9]*$/;
const ROOT_REQUEST_FIELDS = new Set([
  "profile_id",
  "analysis_id",
  "relationship",
  "reactome_request",
  "kinase_request",
]);
const PROFILE_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "model_id",
  "relationship",
  "topology",
  "topology_digest",
  "reactome_child",
  "kinase_child",
  "source_inventory_digest",
  "numpy_version",
  "composition_semantic_digest",
  "limits",
  "counts",
  "demo_id",
  "demo_request_digest",
  "demo_semantic_oracle_digest",
  "source_attestation_state",
  "safety_class",
  "claim_ceiling",
  "research_use_only",
  "non_prescriptive",
  "independent_parallel_blocks",
  "cross_modal_fusion_performed",
  "no_numerical_cross_block_edges",
  "profile_digest",
]);
const PROFILE_CHILD_FIELDS = new Set([
  "block",
  "child_profile_id",
  "child_profile_digest",
  "source_digest",
  "fitted_digest",
  "bootstrap_digest",
  "evaluation_digest",
]);
const PROFILE_LIMIT_FIELDS = new Set([
  "minimum_time_points_per_child",
  "maximum_time_points_per_child",
  "maximum_request_bytes",
  "maximum_result_bytes",
  "maximum_replay_bytes",
  "maximum_numerical_cross_block_edges",
]);
const PROFILE_COUNT_FIELDS = new Set([
  "computation_blocks",
  "reactome_global_factors",
  "reactome_pathway_factors",
  "kinase_signature_factors",
  "subtype_signature_factors",
  "nodes",
  "annotation_only_containment_edges",
  "numerical_cross_block_edges",
]);
const RESULT_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "profile_digest",
  "topology_digest",
  "request_digest",
  "result_digest",
  "analysis_id",
  "relationship",
  "provenance",
  "limitations",
  "research_use_only",
  "non_prescriptive",
  "independent_parallel_blocks",
  "cross_modal_fusion_performed",
  "numerical_cross_block_edge_count",
  "reactome_result",
  "kinase_result",
]);
const PROVENANCE_FIELDS = new Set([
  "engine",
  "request_digest",
  "profile_digest",
  "topology_digest",
  "source_inventory_digest",
  "relationship",
  "reactome_child",
  "kinase_child",
  "numpy_version",
  "independent_parallel_blocks",
  "cross_modal_fusion_performed",
  "no_numerical_cross_block_edges",
]);
const CHILD_BINDING_FIELDS = new Set([
  "block",
  "child_profile_id",
  "child_profile_digest",
  "child_request_digest",
  "child_result_digest",
  "independently_computed",
]);
const REACTOME_RESULT_FIELDS = new Set([
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
const KINASE_RESULT_FIELDS = new Set([
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
  "limitations",
  "research_use_only",
  "non_prescriptive",
  "infers_kinase_activity",
  "infers_biochemical_activity",
  "makes_causal_claim",
  "independent_evidence",
]);
const TOPOLOGY_FIELDS = new Set([
  "topology_id",
  "nodes",
  "containment_edges",
  "cross_block_edges",
  "numerical_cross_block_edge_count",
  "containment_edge_role",
  "topology_digest",
]);
const NODE_FIELDS = new Set([
  "node_id",
  "block",
  "kind",
  "biological_identifier",
  "label",
  "child_profile_id",
  "learned_semantics",
]);
const EDGE_FIELDS = new Set([
  "edge_id",
  "source_node_id",
  "target_node_id",
  "relationship",
  "computational_role",
  "numerical_weight",
]);
const VERIFICATION_FIELDS = new Set([
  "verified",
  "request_digest_match",
  "profile_digest_match",
  "topology_digest_match",
  "source_inventory_digest_match",
  "result_digest_match",
  "reactome_child_verified",
  "kinase_child_verified",
  "independent_parallel_blocks_match",
  "no_cross_modal_fusion_match",
  "no_numerical_cross_block_edges_match",
  "provenance_match",
  "document_semantic_match",
  "semantic_match",
  "recomputed_request_digest",
  "recomputed_result_digest",
  "message",
]);
type HeaderReader = Pick<Headers, "get">;
const BLOCKS = new Set<FactorGraphBlock>(["protein_reactome", "phosphosite_sphinks"]);
const NODE_KINDS = new Set<FactorGraphNodeKind>([
  "computation_block",
  "global_recurrence_factor",
  "reactome_pathway_factor",
  "kinase_signature_factor",
  "subtype_signature_factor",
]);
const KINASE_SUPPORT = new Set<KinaseTransitionSupport>(["limited", "abstained"]);
const KINASE_SUBTYPES = new Set<KinaseSubtype>(["GPM", "MTC", "NEU", "PPR"]);
const KINASE_SELECTION = new Set(["selected_core", "selected_unstable", "not_selected"]);
const KINASE_ABLATIONS = new Set<KinaseSignatureAblation["kind"]>([
  "equal_kinase_instead_of_equal_subtype",
  "omit_composite_source_groups",
  "omit_inverse_multiplicity_correction",
]);
const KINASE_CLASSIFICATIONS = new Set([
  "source_recurrence_aligned",
  "reverse_aligned",
  "stable",
  "indeterminate",
  "not_estimable",
]);
const KINASE_DIRECTIONS = new Set([
  "source_recurrence_aligned",
  "reverse_aligned",
  "not_established",
]);
const KINASE_UNCERTAINTY_FIELDS = new Set([
  "state",
  "lower_bound",
  "upper_bound",
  "standard_error",
  "bootstrap_replicates_used",
  "reason",
]);
const KINASE_DRIVER_FIELDS = new Set([
  "source_site_label",
  "source_phosphosite_ids",
  "stratum",
  "contains_composite_source_group",
  "standardized_rank",
  "inverse_multiplicity",
  "adjusted_source_weight",
  "signed_contribution",
  "paired_source_support",
  "paired_observation_ids",
  "observation_provenance_digests",
]);
const KINASE_SIGNATURE_FIELDS = new Set([
  "kinase",
  "subtype",
  "selection_state",
  "support",
  "source_direction",
  "source_enrichment",
  "source_p_value",
  "source_q_value",
  "mapped_source_family_count",
  "observed_family_count",
  "source_weight_coverage",
  "outer_selection_frequency",
  "bootstrap_selection_frequency",
  "bootstrap_direction_consistency",
  "score",
  "classification",
  "uncertainty",
  "top_family_drivers",
  "reasons",
]);
const KINASE_SUBTYPE_FIELDS = new Set([
  "subtype",
  "selected_kinase_count",
  "estimable_kinase_count",
  "support",
  "score",
  "classification",
  "uncertainty",
  "reasons",
]);
const KINASE_SIGNATURE_ABLATION_FIELDS = new Set([
  "ablation",
  "support",
  "score",
  "score_delta",
  "classification",
  "reason",
]);
const KINASE_TRANSITION_FIELDS = new Set([
  "transition_id",
  "transition_index",
  "from_time_point_id",
  "to_time_point_id",
  "support",
  "classification",
  "score",
  "uncertainty",
  "exact_source_row_count",
  "exact_family_count",
  "censored_family_count",
  "selected_kinase_count",
  "estimable_kinase_count",
  "kinase_signatures",
  "subtype_signatures",
  "ablations",
  "reasons",
]);
const REACTOME_TRANSITION_FIELDS = new Set([
  "transition_id",
  "transition_index",
  "from_time_point_id",
  "to_time_point_id",
  "duration_days",
  "global_recurrence",
  "pathways",
]);
const REACTOME_GLOBAL_FIELDS = new Set([
  "output_semantics",
  "support",
  "classification",
  "score",
  "lower_bound",
  "upper_bound",
  "interval_level",
  "shared_active_gene_count",
  "coefficient_mass_coverage",
  "effective_sample_size",
  "bootstrap_replicates_used",
  "abstention_reasons",
]);
const REACTOME_PATHWAY_FIELDS = new Set([
  "panel_index",
  "domain_id",
  "reactome_id",
  "pathway_name",
  "output_semantics",
  "support",
  "classification",
  "score",
  "lower_bound",
  "upper_bound",
  "unadjusted_pathway_coordinate",
  "global_adjustment",
  "interval_level",
  "source_member_count",
  "mapped_feature_count",
  "fitted_feature_count",
  "active_feature_count",
  "observed_count",
  "left_censored_count",
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
const REACTOME_UNCERTAINTY_FIELDS = new Set([
  "state",
  "measurement_standard_error",
  "fitted_model_standard_error",
  "measurement_model_covariance",
  "combined_standard_error",
  "variance_closure_residual",
  "bootstrap_replicates_used",
  "reason",
]);
const REACTOME_CONTRIBUTION_FIELDS = new Set([
  "gene_symbol",
  "from_observation_id",
  "to_observation_id",
  "from_provenance_digest",
  "to_provenance_digest",
  "from_state",
  "to_state",
  "value_semantics",
  "standardized_delta",
  "pathway_loading",
  "global_loading",
  "unadjusted_contribution",
  "global_adjustment_contribution",
  "conditional_contribution",
  "direction",
  "reliability_weight",
]);
const REACTOME_ABLATION_FIELDS = new Set([
  "component_kind",
  "component_id",
  "support",
  "conditional_score_without_component",
  "score_delta",
  "classification_without_component",
  "removed_feature_count",
  "reason",
]);
const REACTOME_ABLATIONS_FIELDS = new Set([
  "global_axis",
  "source_processing",
  "degree_normalization",
  "unique_members",
  "leave_pathway_out",
  "overlap",
  "top_contributions",
]);
const FACTOR_GRAPH_REQUEST_FLOAT_FIELDS = new Set([
  "log_abundance",
  "log_abundance_ratio",
  "quality_weight",
  "standard_error",
  "time_offset_days",
]);
const FACTOR_GRAPH_RESULT_FLOAT_FIELDS = new Set([
  "adjusted_source_weight",
  "bootstrap_direction_consistency",
  "bootstrap_selection_frequency",
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
  "inverse_multiplicity",
  "lower_bound",
  "measurement_model_covariance",
  "measurement_standard_error",
  "outer_selection_frequency",
  "pathway_loading",
  "reliability_weight",
  "request_reconstruction_median_relative_gain",
  "score",
  "score_delta",
  "signed_contribution",
  "source_enrichment",
  "source_p_value",
  "source_q_value",
  "source_weight_coverage",
  "stability",
  "standard_error",
  "standardized_delta",
  "standardized_rank",
  "unadjusted_contribution",
  "unadjusted_pathway_coordinate",
  "unique_coefficient_mass",
  "upper_bound",
  "variance_closure_residual",
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

function exactFields(
  source: JsonObject,
  expected: ReadonlySet<string>,
  path: string,
  errors: string[],
): void {
  rejectUnknownFields(source, expected, path, errors);
  const missing = [...expected].filter((key) => !hasOwn(source, key));
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
}

function isDigest(value: JsonValue | undefined): value is string {
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

function defaultedFactorGraphObservation(
  value: JsonValue,
  abundanceField: "log_abundance" | "log_abundance_ratio",
): JsonValue {
  if (!isJsonObject(value)) return value;
  return {
    ...value,
    [abundanceField]: hasOwn(value, abundanceField) ? value[abundanceField] : null,
    standard_error: hasOwn(value, "standard_error") ? value.standard_error : null,
    quality_weight: hasOwn(value, "quality_weight") ? value.quality_weight : 1,
  };
}

function normalizedFactorGraphChildRequest(
  value: JsonValue | undefined,
  modality: "reactome" | "kinase",
): JsonValue {
  if (!isJsonObject(value)) return value ?? null;
  const profileId = modality === "reactome"
    ? LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID
    : GBM_FACTOR_GRAPH_KINASE_PROFILE_ID;
  const abundanceScale = modality === "reactome"
    ? "caller_supplied_log2_protein_abundance_ratio"
    : "caller_supplied_log2_phosphosite_abundance_ratio";
  const abundanceField = modality === "reactome"
    ? "log_abundance"
    : "log_abundance_ratio";
  const identityField = modality === "reactome" ? "gene_symbol" : "phosphosite_id";
  const normalizationReference = isJsonObject(value.normalization_reference)
    ? {
      ...value.normalization_reference,
      abundance_scale: value.normalization_reference.abundance_scale ?? abundanceScale,
      invariant_across_time_points:
        value.normalization_reference.invariant_across_time_points ?? true,
    }
    : value.normalization_reference;
  const timePoints = Array.isArray(value.time_points)
    ? value.time_points.map((timePoint) => {
      if (!isJsonObject(timePoint) || !Array.isArray(timePoint.observations)) return timePoint;
      const observations = timePoint.observations
        .map((observation) => defaultedFactorGraphObservation(observation, abundanceField))
        .sort((left, right) => {
          if (!isJsonObject(left) || !isJsonObject(right)) return 0;
          const leftKey = `${String(left[identityField])}\u0000${String(left.observation_id)}`;
          const rightKey = `${String(right[identityField])}\u0000${String(right.observation_id)}`;
          return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
        });
      return { ...timePoint, observations };
    })
    : value.time_points;
  return {
    ...value,
    profile_id: value.profile_id ?? profileId,
    normalization_reference: normalizationReference,
    time_points: timePoints,
    bootstrap_replicates: value.bootstrap_replicates ?? 64,
  };
}

function normalizedFactorGraphRequest(request: JsonObject): JsonObject {
  return {
    ...request,
    profile_id: request.profile_id ?? GBM_FACTOR_GRAPH_PROFILE_ID,
    relationship: request.relationship ?? GBM_FACTOR_GRAPH_RELATIONSHIP,
    reactome_request: normalizedFactorGraphChildRequest(request.reactome_request, "reactome"),
    kinase_request: normalizedFactorGraphChildRequest(request.kinase_request, "kinase"),
  };
}

export function factorGraphRequestDigest(request: JsonObject): string {
  return `sha256:${sha256Hex(canonicalTypedJson(
    normalizedFactorGraphRequest(request),
    FACTOR_GRAPH_REQUEST_FLOAT_FIELDS,
  ))}`;
}

export function factorGraphProfileDigest(profile: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(profile).filter(([key]) => key !== "profile_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalJson(payload))}`;
}

export function factorGraphResultDigest(result: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(result).filter(([key]) => key !== "result_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalTypedJson(
    payload,
    FACTOR_GRAPH_RESULT_FLOAT_FIELDS,
  ))}`;
}

export function factorGraphChildResultDigest(result: JsonObject): string {
  const payload = Object.fromEntries(
    Object.entries(result).filter(([key]) => key !== "result_digest"),
  ) as JsonObject;
  return `sha256:${sha256Hex(canonicalTypedJson(
    payload,
    FACTOR_GRAPH_RESULT_FLOAT_FIELDS,
  ))}`;
}

function sameJson(left: JsonValue | undefined, right: JsonValue | undefined): boolean {
  return left !== undefined
    && right !== undefined
    && canonicalJson(left) === canonicalJson(right);
}

function prefixed(path: string, errors: string[]): string[] {
  return errors.map((error) => {
    if (error.startsWith("request ")) return `${path}${error.slice("request".length)}`;
    if (/^[A-Za-z_]+(?:\[|\.|\s)/.test(error)) return `${path}.${error}`;
    return `${path}: ${error}`;
  });
}

function stringValues(value: JsonValue | undefined): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function integerAt(
  source: JsonObject,
  key: string,
  minimum: number,
  maximum: number,
): number | null {
  const value = source[key];
  return typeof value === "number"
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum
    ? value
    : null;
}

function unique(values: string[]): boolean {
  return new Set(values).size === values.length;
}

function exactShape(source: JsonObject, fields: ReadonlySet<string>): boolean {
  return Object.keys(source).every((field) => fields.has(field))
    && [...fields].every((field) => hasOwn(source, field));
}

function nonEmptyText(value: JsonValue | undefined): value is string {
  return typeof value === "string"
    && [...value].length >= 1
    && [...value].length <= 512
    && value.trim() === value
    && value.trim().length > 0;
}

function exactStringArray(
  value: JsonValue | undefined,
  minimum: number,
  maximum: number,
  predicate: (item: string) => boolean,
): value is string[] {
  return Array.isArray(value)
    && value.length >= minimum
    && value.length <= maximum
    && value.every((item) => typeof item === "string" && predicate(item));
}

function validBlock(value: string): value is FactorGraphBlock {
  return BLOCKS.has(value as FactorGraphBlock);
}

function validNodeKind(value: string): value is FactorGraphNodeKind {
  return NODE_KINDS.has(value as FactorGraphNodeKind);
}

function expectedBlockForNodeKind(
  kind: FactorGraphNodeKind,
  computationBlock: FactorGraphBlock,
): FactorGraphBlock {
  switch (kind) {
    case "computation_block":
      return computationBlock;
    case "global_recurrence_factor":
    case "reactome_pathway_factor":
      return "protein_reactome";
    case "kinase_signature_factor":
    case "subtype_signature_factor":
      return "phosphosite_sphinks";
  }
}

function validKinaseSupport(value: string): value is KinaseTransitionSupport {
  return KINASE_SUPPORT.has(value as KinaseTransitionSupport);
}

function validKinaseSubtype(value: string): value is KinaseSubtype {
  return KINASE_SUBTYPES.has(value as KinaseSubtype);
}

function validProbability(value: number | null): value is number {
  return value !== null && value >= 0 && value <= 1;
}

function childTimePointCount(value: JsonObject): number {
  return arrayAt(value, ["time_points"]).length;
}

export function factorGraphRequestStats(request: JsonObject): FactorGraphRequestStats {
  const reactomeRequest = objectAt(request, ["reactome_request"]);
  const kinaseRequest = objectAt(request, ["kinase_request"]);
  const reactome = reactomeRequest
    ? reactomeTransitionRequestStats(reactomeRequest)
    : { timePoints: 0, transitions: 0, active: 0 };
  const kinase = kinaseRequest
    ? longitudinalPhosphoRequestStats(kinaseRequest)
    : { timePoints: 0, active: 0 };
  return {
    reactomeTimePoints: reactome.timePoints,
    reactomeActive: reactome.active,
    kinaseTimePoints: kinase.timePoints,
    kinaseActive: kinase.active,
    childTransitions: reactome.transitions + Math.max(0, kinase.timePoints - 1),
  };
}

export function validateFactorGraphKinaseRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  if (hasOwn(request, "profile_id") && request.profile_id !== GBM_FACTOR_GRAPH_KINASE_PROFILE_ID) {
    errors.push(`profile_id must equal ${GBM_FACTOR_GRAPH_KINASE_PROFILE_ID}.`);
  }
  const compatibleRequest: JsonObject = {
    ...request,
    profile_id: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  };
  errors.push(...validateLongitudinalPhosphoRequest(compatibleRequest));
  const timePoints = childTimePointCount(request);
  if (timePoints > GBM_FACTOR_GRAPH_MAX_TIME_POINTS) {
    errors.push(`time_points must contain at most ${GBM_FACTOR_GRAPH_MAX_TIME_POINTS} entries in the factor-graph lane.`);
  }
  return errors;
}

export function validateFactorGraphRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_REQUEST_FIELDS, "request", errors);
  if (hasOwn(request, "profile_id") && request.profile_id !== GBM_FACTOR_GRAPH_PROFILE_ID) {
    errors.push(`profile_id must equal ${GBM_FACTOR_GRAPH_PROFILE_ID}.`);
  }
  if (typeof request.analysis_id !== "string" || !IDENTIFIER.test(request.analysis_id)) {
    errors.push("analysis_id must be a valid identifier.");
  }
  if (hasOwn(request, "relationship") && request.relationship !== GBM_FACTOR_GRAPH_RELATIONSHIP) {
    errors.push(`relationship must equal ${GBM_FACTOR_GRAPH_RELATIONSHIP}.`);
  }

  const reactome = request.reactome_request;
  if (!isJsonObject(reactome)) {
    errors.push("reactome_request must be an object.");
  } else {
    const childErrors = reactome.profile_id === undefined
      || reactome.profile_id === LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID
      ? []
      : [`profile_id must equal ${LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID}.`];
    const compatibleReactome: JsonObject = {
      ...reactome,
      profile_id: LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
    };
    childErrors.push(...validateReactomeTransitionRequest(compatibleReactome));
    if (childTimePointCount(reactome) > GBM_FACTOR_GRAPH_MAX_TIME_POINTS) {
      childErrors.push(`time_points must contain at most ${GBM_FACTOR_GRAPH_MAX_TIME_POINTS} entries in the factor-graph lane.`);
    }
    errors.push(...prefixed("reactome_request", childErrors));
  }

  const kinase = request.kinase_request;
  if (!isJsonObject(kinase)) {
    errors.push("kinase_request must be an object.");
  } else {
    errors.push(...prefixed("kinase_request", validateFactorGraphKinaseRequest(kinase)));
  }
  return errors;
}

function normalizeTopologyNode(value: JsonValue): FactorGraphNode | null {
  if (!isJsonObject(value)) return null;
  if (Object.keys(value).some((key) => !NODE_FIELDS.has(key))) return null;
  const id = textAt(value, ["node_id"]);
  const block = textAt(value, ["block"]);
  const kind = textAt(value, ["kind"]);
  const biologicalIdentifier = textAt(value, ["biological_identifier"]);
  const label = textAt(value, ["label"]);
  const childProfileId = textAt(value, ["child_profile_id"]);
  const learnedSemantics = textAt(value, ["learned_semantics"]);
  if (
    !IDENTIFIER.test(id)
    || !validBlock(block)
    || !validNodeKind(kind)
    || !biologicalIdentifier
    || !label
    || !childProfileId
    || (learnedSemantics !== "child_source_cohort_fitted_coordinate"
      && learnedSemantics !== "child_result_container_only")
  ) return null;
  const expectedChild = block === "protein_reactome"
    ? LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID
    : GBM_FACTOR_GRAPH_KINASE_PROFILE_ID;
  if (childProfileId !== expectedChild) return null;
  const expectedBlock = expectedBlockForNodeKind(kind, block);
  if (block !== expectedBlock) return null;
  if (
    (kind === "computation_block") !== (learnedSemantics === "child_result_container_only")
  ) return null;
  if (kind === "reactome_pathway_factor" && !REACTOME_ID.test(biologicalIdentifier)) return null;
  if (kind === "kinase_signature_factor" && !KINASE.test(biologicalIdentifier)) return null;
  if (kind === "subtype_signature_factor" && !validKinaseSubtype(biologicalIdentifier)) return null;
  return {
    id,
    block,
    kind,
    biologicalIdentifier,
    label,
    childProfileId,
    learnedSemantics,
  };
}

function normalizeTopologyEdge(value: JsonValue): FactorGraphContainmentEdge | null {
  if (!isJsonObject(value)) return null;
  if (Object.keys(value).some((key) => !EDGE_FIELDS.has(key))) return null;
  const id = textAt(value, ["edge_id"]);
  const sourceNodeId = textAt(value, ["source_node_id"]);
  const targetNodeId = textAt(value, ["target_node_id"]);
  if (
    !IDENTIFIER.test(id)
    || !IDENTIFIER.test(sourceNodeId)
    || !IDENTIFIER.test(targetNodeId)
    || value.relationship !== "contains"
    || value.computational_role !== "annotation_only"
    || value.numerical_weight !== null
  ) return null;
  return {
    id,
    sourceNodeId,
    targetNodeId,
    relationship: "contains",
    computationalRole: "annotation_only",
    numericalWeight: null,
  };
}

export function normalizeFactorGraphTopology(profile: JsonObject | null): FactorGraphTopology | null {
  if (!profile) return null;
  const value = objectAt(profile, ["topology"]) ?? profile;
  if (Object.keys(value).some((key) => !TOPOLOGY_FIELDS.has(key))) return null;
  if (
    value.topology_id !== GBM_FACTOR_GRAPH_TOPOLOGY_ID
    || value.containment_edge_role !== "annotation_only"
    || value.numerical_cross_block_edge_count !== 0
    || arrayAt(value, ["cross_block_edges"]).length !== 0
    || value.topology_digest !== GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST
  ) return null;
  if (hasOwn(profile, "topology_digest") && profile.topology_digest !== value.topology_digest) return null;
  const rawNodes = arrayAt(value, ["nodes"]);
  const rawEdges = arrayAt(value, ["containment_edges"]);
  if (rawNodes.length !== GBM_FACTOR_GRAPH_NODE_COUNT || rawEdges.length !== GBM_FACTOR_GRAPH_EDGE_COUNT) return null;
  const nodes = rawNodes.flatMap((item) => normalizeTopologyNode(item) ?? []);
  const edges = rawEdges.flatMap((item) => normalizeTopologyEdge(item) ?? []);
  if (nodes.length !== rawNodes.length || edges.length !== rawEdges.length) return null;
  if (!unique(nodes.map((node) => node.id)) || !unique(edges.map((edge) => edge.id))) return null;

  const expectedCounts: Record<FactorGraphNodeKind, number> = {
    computation_block: 2,
    global_recurrence_factor: 1,
    reactome_pathway_factor: 10,
    kinase_signature_factor: 24,
    subtype_signature_factor: 4,
  };
  if (Object.entries(expectedCounts).some(([kind, expected]) =>
    nodes.filter((node) => node.kind === kind).length !== expected)) return null;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const blockNodes = nodes.filter((node) => node.kind === "computation_block");
  if (!unique(blockNodes.map((node) => node.block))) return null;
  const targets = new Set<string>();
  for (const edge of edges) {
    const source = nodeById.get(edge.sourceNodeId);
    const target = nodeById.get(edge.targetNodeId);
    if (
      !source
      || !target
      || source.kind !== "computation_block"
      || target.kind === "computation_block"
      || source.block !== target.block
      || targets.has(target.id)
    ) return null;
    targets.add(target.id);
  }
  if (nodes.some((node) => node.kind !== "computation_block" && !targets.has(node.id))) return null;
  return {
    id: GBM_FACTOR_GRAPH_TOPOLOGY_ID,
    digest: value.topology_digest,
    nodes,
    containmentEdges: edges,
    numericalCrossBlockEdgeCount: 0,
    containmentEdgeRole: "annotation_only",
  };
}

function validateProfileChildBinding(
  value: JsonValue | undefined,
  path: string,
  block: FactorGraphBlock,
  childProfileId: string,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, PROFILE_CHILD_FIELDS, path, errors);
  if (value.block !== block) errors.push(`${path}.block must equal ${block}.`);
  if (value.child_profile_id !== childProfileId) {
    errors.push(`${path}.child_profile_id must equal ${childProfileId}.`);
  }
  for (const field of [
    "child_profile_digest",
    "source_digest",
    "fitted_digest",
    "bootstrap_digest",
    "evaluation_digest",
  ] as const) {
    if (!isDigest(value[field])) {
      errors.push(`${path}.${field} must be a lowercase sha256 digest.`);
    }
  }
}

export function validateFactorGraphProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (
    profile.algorithm_id !== "glio-ecgi-kncc-gbm-transition"
    || profile.algorithm_version !== "1.0.0"
    || profile.profile_id !== GBM_FACTOR_GRAPH_PROFILE_ID
    || profile.model_id !== GBM_FACTOR_GRAPH_MODEL_ID
  ) errors.push("profile algorithm/model identity is invalid.");
  if (profile.relationship !== GBM_FACTOR_GRAPH_RELATIONSHIP) {
    errors.push(`profile.relationship must equal ${GBM_FACTOR_GRAPH_RELATIONSHIP}.`);
  }
  for (const field of [
    "profile_digest",
    "topology_digest",
    "source_inventory_digest",
    "composition_semantic_digest",
    "demo_request_digest",
    "demo_semantic_oracle_digest",
  ] as const) {
    if (!isDigest(profile[field])) {
      errors.push(`profile.${field} must be a lowercase sha256 digest.`);
    }
  }
  if (
    isDigest(profile.profile_digest)
    && profile.profile_digest !== factorGraphProfileDigest(profile)
  ) {
    errors.push("profile.profile_digest must match canonical profile content.");
  }
  if (!normalizeFactorGraphTopology(profile)) {
    errors.push("profile topology was not admitted by the version-locked factor topology validator.");
  }
  validateProfileChildBinding(
    profile.reactome_child,
    "profile.reactome_child",
    "protein_reactome",
    LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
    errors,
  );
  validateProfileChildBinding(
    profile.kinase_child,
    "profile.kinase_child",
    "phosphosite_sphinks",
    GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    errors,
  );

  const limits = objectAt(profile, ["limits"]);
  if (!limits) {
    errors.push("profile.limits must be an object.");
  } else {
    exactFields(limits, PROFILE_LIMIT_FIELDS, "profile.limits", errors);
    const expectedLimits: Record<string, number> = {
      minimum_time_points_per_child: 2,
      maximum_time_points_per_child: GBM_FACTOR_GRAPH_MAX_TIME_POINTS,
      maximum_request_bytes: 4_194_304,
      maximum_result_bytes: 8_388_608,
      maximum_replay_bytes: 16_777_216,
      maximum_numerical_cross_block_edges: 0,
    };
    if (Object.entries(expectedLimits).some(([field, value]) => limits[field] !== value)) {
      errors.push("profile.limits does not match the version-locked factor-graph transport boundary.");
    }
  }
  const counts = objectAt(profile, ["counts"]);
  if (!counts) {
    errors.push("profile.counts must be an object.");
  } else {
    exactFields(counts, PROFILE_COUNT_FIELDS, "profile.counts", errors);
    const expectedCounts: Record<string, number> = {
      computation_blocks: 2,
      reactome_global_factors: 1,
      reactome_pathway_factors: 10,
      kinase_signature_factors: 24,
      subtype_signature_factors: 4,
      nodes: GBM_FACTOR_GRAPH_NODE_COUNT,
      annotation_only_containment_edges: GBM_FACTOR_GRAPH_EDGE_COUNT,
      numerical_cross_block_edges: 0,
    };
    if (Object.entries(expectedCounts).some(([field, value]) => counts[field] !== value)) {
      errors.push("profile.counts does not match the version-locked factor inventory.");
    }
  }
  if (profile.numpy_version !== "2.5.2") {
    errors.push("profile.numpy_version must equal the locked 2.5.2 runtime.");
  }
  if (profile.demo_id !== GBM_FACTOR_GRAPH_DEMO_ID) {
    errors.push(`profile.demo_id must equal ${GBM_FACTOR_GRAPH_DEMO_ID}.`);
  }
  if (profile.source_attestation_state !== "verified_exact_child_snapshots") {
    errors.push("profile.source_attestation_state must affirm the exact child snapshots.");
  }
  if (
    profile.safety_class !== "research_use_only"
    || profile.claim_ceiling !== "independent_source_cohort_concordance_coordinates_only"
  ) errors.push("profile exceeds or differs from the admitted source-cohort claim ceiling.");
  if (
    profile.research_use_only !== true
    || profile.non_prescriptive !== true
    || profile.independent_parallel_blocks !== true
    || profile.cross_modal_fusion_performed !== false
    || profile.no_numerical_cross_block_edges !== true
  ) errors.push("profile must preserve the research-only independent no-fusion boundary.");
  return errors;
}

function validateDigestHeader(
  headers: HeaderReader,
  name: string,
  expected: JsonValue | undefined,
  errors: string[],
): void {
  const value = headers.get(name);
  if (!isDigest(value ?? undefined)) {
    errors.push(`${name} response header must be a lowercase sha256 digest.`);
  } else if (value !== expected) {
    errors.push(`${name} response header must match the admitted payload.`);
  }
}

export function validateFactorGraphProfileHeaders(
  headers: HeaderReader,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(
    headers,
    "X-GLIO-Profile-Digest",
    factorGraphProfileDigest(profile),
    errors,
  );
  return errors;
}

export function validateFactorGraphDemo(
  request: JsonObject,
  headers: HeaderReader,
  profile: JsonObject,
): string[] {
  const errors = [
    ...validateFactorGraphProfile(profile),
    ...validateFactorGraphRequest(request),
  ];
  if (request.analysis_id !== profile.demo_id) {
    errors.push("demo request.analysis_id must match the admitted profile.demo_id.");
  }
  const requestProfileId = request.profile_id ?? GBM_FACTOR_GRAPH_PROFILE_ID;
  if (requestProfileId !== profile.profile_id) {
    errors.push("demo request.profile_id must match the admitted profile.profile_id.");
  }
  const relationship = request.relationship ?? GBM_FACTOR_GRAPH_RELATIONSHIP;
  if (relationship !== profile.relationship) {
    errors.push("demo request.relationship must match the admitted profile.relationship.");
  }
  const profileDigest = factorGraphProfileDigest(profile);
  const requestDigest = factorGraphRequestDigest(request);
  if (profile.demo_request_digest !== requestDigest) {
    errors.push("profile.demo_request_digest must match canonical demo request content.");
  }
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profileDigest, errors);
  validateDigestHeader(headers, "X-GLIO-Request-Digest", requestDigest, errors);
  return errors;
}

function normalizeUncertainty(value: JsonObject | null): KinaseTransitionUncertainty | null {
  if (!value || !exactShape(value, KINASE_UNCERTAINTY_FIELDS)) return null;
  const state = textAt(value, ["state"]);
  const lower = numberAt(value, ["lower_bound"]);
  const upper = numberAt(value, ["upper_bound"]);
  const standardError = numberAt(value, ["standard_error"]);
  const bootstrapReplicates = numberAt(value, ["bootstrap_replicates_used"]);
  const reason = textAt(value, ["reason"]);
  if (state === "estimated") {
    if (
      lower === null
      || upper === null
      || lower > upper
      || standardError === null
      || standardError < 0
      || bootstrapReplicates === null
      || !Number.isInteger(bootstrapReplicates)
      || bootstrapReplicates < 32
      || bootstrapReplicates > 64
      || value.reason !== null
    ) return null;
    return { state, lower, upper, standardError, bootstrapReplicates, reason: "" };
  }
  if (
    state !== "not_estimable"
    || value.lower_bound !== null
    || value.upper_bound !== null
    || value.standard_error !== null
    || value.bootstrap_replicates_used !== 0
    || !nonEmptyText(value.reason)
  ) return null;
  return {
    state,
    lower: null,
    upper: null,
    standardError: null,
    bootstrapReplicates: 0,
    reason,
  };
}

function normalizeFamilyDriver(value: JsonValue): KinaseFamilyDriver | null {
  if (!isJsonObject(value) || !exactShape(value, KINASE_DRIVER_FIELDS)) return null;
  const sourceSiteLabel = textAt(value, ["source_site_label"]);
  const sourcePhosphositeIds = stringValues(value.source_phosphosite_ids);
  const stratum = textAt(value, ["stratum"]);
  const standardizedRank = numberAt(value, ["standardized_rank"]);
  const inverseMultiplicity = numberAt(value, ["inverse_multiplicity"]);
  const adjustedSourceWeight = numberAt(value, ["adjusted_source_weight"]);
  const contribution = numberAt(value, ["signed_contribution"]);
  const pairedSourceSupport = integerAt(value, "paired_source_support", 53, 88);
  if (
    typeof value.source_site_label !== "string"
    || sourceSiteLabel.length < 3
    || sourceSiteLabel.length > 160
    || !exactStringArray(value.source_phosphosite_ids, 1, 16, nonEmptyText)
    || !nonEmptyText(value.stratum)
    || typeof value.contains_composite_source_group !== "boolean"
    || standardizedRank === null
    || standardizedRank < -1
    || standardizedRank > 1
    || inverseMultiplicity === null
    || inverseMultiplicity <= 0
    || inverseMultiplicity > 1
    || adjustedSourceWeight === null
    || adjustedSourceWeight <= 0
    || contribution === null
    || pairedSourceSupport === null
    || !exactStringArray(value.paired_observation_ids, 2, 32, (item) => IDENTIFIER.test(item))
    || !exactStringArray(value.observation_provenance_digests, 2, 32, (item) => DIGEST.test(item))
  ) return null;
  return {
    sourceSiteLabel,
    sourcePhosphositeIds,
    stratum,
    composite: value.contains_composite_source_group === true,
    standardizedRank,
    adjustedSourceWeight,
    contribution,
    pairedSourceSupport,
  };
}

function normalizeKinaseSignature(value: JsonValue): KinaseSignatureTransition | null {
  if (!isJsonObject(value) || !exactShape(value, KINASE_SIGNATURE_FIELDS)) return null;
  const kinase = textAt(value, ["kinase"]);
  const subtype = textAt(value, ["subtype"]);
  const selectionState = textAt(value, ["selection_state"]);
  const support = textAt(value, ["support"]);
  const classification = textAt(value, ["classification"]);
  const score = numberAt(value, ["score"]);
  const uncertainty = normalizeUncertainty(objectAt(value, ["uncertainty"]));
  const sourcePValue = numberAt(value, ["source_p_value"]);
  const sourceQValue = numberAt(value, ["source_q_value"]);
  const coverage = numberAt(value, ["source_weight_coverage"]);
  const outerFrequency = numberAt(value, ["outer_selection_frequency"]);
  const bootstrapFrequency = numberAt(value, ["bootstrap_selection_frequency"]);
  const mappedFamilies = integerAt(value, "mapped_source_family_count", 0, 572);
  const observedFamilies = integerAt(value, "observed_family_count", 0, 572);
  const reasons = stringValues(value.reasons);
  const sourceDirection = textAt(value, ["source_direction"]);
  const sourceEnrichment = numberAt(value, ["source_enrichment"]);
  if (
    typeof value.kinase !== "string"
    || !KINASE.test(kinase)
    || typeof value.subtype !== "string"
    || !validKinaseSubtype(subtype)
    || typeof value.selection_state !== "string"
    || !KINASE_SELECTION.has(selectionState)
    || typeof value.support !== "string"
    || !validKinaseSupport(support)
    || typeof value.classification !== "string"
    || !KINASE_CLASSIFICATIONS.has(classification)
    || typeof value.source_direction !== "string"
    || !KINASE_DIRECTIONS.has(sourceDirection)
    || (value.source_enrichment !== null && sourceEnrichment === null)
    || !uncertainty
    || !validProbability(sourcePValue)
    || !validProbability(sourceQValue)
    || !validProbability(coverage)
    || !validProbability(outerFrequency)
    || !validProbability(bootstrapFrequency)
    || mappedFamilies === null
    || observedFamilies === null
    || (value.score !== null && score === null)
    || !exactStringArray(value.reasons, 0, 8, nonEmptyText)
  ) return null;
  const abstained = support === "abstained";
  if (
    (selectionState === "not_selected" && !abstained)
    || (abstained && (score !== null || classification !== "not_estimable" || uncertainty.state !== "not_estimable" || !reasons.length))
    || (!abstained && (score === null || classification === "not_estimable" || uncertainty.state !== "estimated" || !reasons.length))
  ) return null;
  const directionConsistency = numberAt(value, ["bootstrap_direction_consistency"]);
  if (
    (value.bootstrap_direction_consistency !== null && directionConsistency === null)
    || (directionConsistency !== null && !validProbability(directionConsistency))
  ) return null;
  const rawDrivers = arrayAt(value, ["top_family_drivers"]);
  if (!Array.isArray(value.top_family_drivers) || rawDrivers.length > 8) return null;
  const drivers = rawDrivers.flatMap((item) => normalizeFamilyDriver(item) ?? []);
  if (drivers.length !== rawDrivers.length) return null;
  return {
    kinase,
    subtype,
    selectionState: selectionState as KinaseSignatureTransition["selectionState"],
    support,
    sourceDirection,
    sourceEnrichment,
    sourcePValue,
    sourceQValue,
    mappedFamilies,
    observedFamilies,
    sourceWeightCoverage: coverage,
    outerSelectionFrequency: outerFrequency,
    bootstrapSelectionFrequency: bootstrapFrequency,
    bootstrapDirectionConsistency: directionConsistency,
    score,
    classification,
    uncertainty,
    drivers,
    reasons,
  };
}

function normalizeSubtypeSignature(value: JsonValue): KinaseSubtypeTransition | null {
  if (!isJsonObject(value) || !exactShape(value, KINASE_SUBTYPE_FIELDS)) return null;
  const subtype = textAt(value, ["subtype"]);
  const support = textAt(value, ["support"]);
  const score = numberAt(value, ["score"]);
  const classification = textAt(value, ["classification"]);
  const uncertainty = normalizeUncertainty(objectAt(value, ["uncertainty"]));
  const selectedKinases = integerAt(value, "selected_kinase_count", 0, 9);
  const estimableKinases = integerAt(value, "estimable_kinase_count", 0, 9);
  const reasons = stringValues(value.reasons);
  if (
    typeof value.subtype !== "string"
    || !validKinaseSubtype(subtype)
    || typeof value.support !== "string"
    || !validKinaseSupport(support)
    || typeof value.classification !== "string"
    || !KINASE_CLASSIFICATIONS.has(classification)
    || !uncertainty
    || selectedKinases === null
    || estimableKinases === null
    || (value.score !== null && score === null)
    || !exactStringArray(value.reasons, 0, 8, nonEmptyText)
  ) return null;
  const abstained = support === "abstained";
  if (
    (abstained && (score !== null || classification !== "not_estimable" || uncertainty.state !== "not_estimable" || !reasons.length))
    || (!abstained && (score === null || classification === "not_estimable" || uncertainty.state !== "estimated" || !reasons.length))
  ) return null;
  return {
    subtype,
    selectedKinases,
    estimableKinases,
    support,
    score,
    classification,
    uncertainty,
    reasons,
  };
}

function normalizeSignatureAblation(value: JsonValue): KinaseSignatureAblation | null {
  if (!isJsonObject(value) || !exactShape(value, KINASE_SIGNATURE_ABLATION_FIELDS)) {
    return null;
  }
  const kind = textAt(value, ["ablation"]);
  const support = textAt(value, ["support"]);
  const score = numberAt(value, ["score"]);
  const scoreDelta = numberAt(value, ["score_delta"]);
  const classification = textAt(value, ["classification"]);
  const reason = textAt(value, ["reason"]);
  if (
    typeof value.ablation !== "string"
    || !KINASE_ABLATIONS.has(kind as KinaseSignatureAblation["kind"])
    || typeof value.support !== "string"
    || !validKinaseSupport(support)
    || typeof value.classification !== "string"
    || !KINASE_CLASSIFICATIONS.has(classification)
    || !nonEmptyText(value.reason)
    || (value.score !== null && score === null)
    || (value.score_delta !== null && scoreDelta === null)
  ) return null;
  if (
    (support === "abstained" && (score !== null || scoreDelta !== null || classification !== "not_estimable"))
    || (support === "limited" && (score === null || scoreDelta === null))
  ) return null;
  return {
    kind: kind as KinaseSignatureAblation["kind"],
    support,
    score,
    scoreDelta,
    classification,
    reason,
  };
}

function normalizeKinaseTransition(value: JsonValue): KinaseTransition | null {
  if (!isJsonObject(value) || !exactShape(value, KINASE_TRANSITION_FIELDS)) return null;
  const id = textAt(value, ["transition_id"]);
  const index = numberAt(value, ["transition_index"]);
  const fromTimePointId = textAt(value, ["from_time_point_id"]);
  const toTimePointId = textAt(value, ["to_time_point_id"]);
  const support = textAt(value, ["support"]);
  const classification = textAt(value, ["classification"]);
  const score = numberAt(value, ["score"]);
  const uncertainty = normalizeUncertainty(objectAt(value, ["uncertainty"]));
  const exactSourceRows = integerAt(value, "exact_source_row_count", 0, 4_096);
  const exactFamilies = integerAt(value, "exact_family_count", 0, 2_457);
  const censoredFamilies = integerAt(value, "censored_family_count", 0, 2_457);
  const selectedKinases = integerAt(value, "selected_kinase_count", 0, 24);
  const estimableKinases = integerAt(value, "estimable_kinase_count", 0, 24);
  const reasons = stringValues(value.reasons);
  if (
    typeof value.transition_id !== "string"
    || !IDENTIFIER.test(id)
    || index === null
    || !Number.isInteger(index)
    || index < 0
    || index >= GBM_FACTOR_GRAPH_MAX_TIME_POINTS - 1
    || typeof value.from_time_point_id !== "string"
    || !IDENTIFIER.test(fromTimePointId)
    || typeof value.to_time_point_id !== "string"
    || !IDENTIFIER.test(toTimePointId)
    || typeof value.support !== "string"
    || !validKinaseSupport(support)
    || typeof value.classification !== "string"
    || !KINASE_CLASSIFICATIONS.has(classification)
    || !uncertainty
    || exactSourceRows === null
    || exactFamilies === null
    || censoredFamilies === null
    || selectedKinases === null
    || estimableKinases === null
    || (value.score !== null && score === null)
    || !exactStringArray(value.reasons, 0, 12, nonEmptyText)
  ) return null;
  const abstained = support === "abstained";
  if (
    (abstained && (score !== null || classification !== "not_estimable" || uncertainty.state !== "not_estimable" || !reasons.length))
    || (!abstained && (score === null || classification === "not_estimable" || uncertainty.state !== "estimated" || !reasons.length))
  ) return null;
  const rawKinases = arrayAt(value, ["kinase_signatures"]);
  const rawSubtypes = arrayAt(value, ["subtype_signatures"]);
  const rawAblations = arrayAt(value, ["ablations"]);
  if (rawKinases.length !== 24 || rawSubtypes.length !== 4 || rawAblations.length !== 3) return null;
  const kinaseSignatures = rawKinases.flatMap((item) => normalizeKinaseSignature(item) ?? []);
  const subtypeSignatures = rawSubtypes.flatMap((item) => normalizeSubtypeSignature(item) ?? []);
  const ablations = rawAblations.flatMap((item) => normalizeSignatureAblation(item) ?? []);
  if (kinaseSignatures.length !== 24 || subtypeSignatures.length !== 4 || ablations.length !== 3) return null;
  if (!unique(kinaseSignatures.map((item) => item.kinase))) return null;
  if (kinaseSignatures.map((item) => item.kinase).join("|") !== [...kinaseSignatures].sort((left, right) => left.kinase.localeCompare(right.kinase)).map((item) => item.kinase).join("|")) return null;
  if (subtypeSignatures.map((item) => item.subtype).join("|") !== "GPM|MTC|NEU|PPR") return null;
  if (new Set(ablations.map((item) => item.kind)).size !== 3) return null;
  return {
    id,
    index,
    fromTimePointId,
    toTimePointId,
    support,
    classification,
    score,
    uncertainty,
    exactSourceRows,
    exactFamilies,
    censoredFamilies,
    selectedKinases,
    estimableKinases,
    kinaseSignatures,
    subtypeSignatures,
    ablations,
    reasons,
    raw: value,
  };
}

export function normalizeFactorGraphKinaseTransitions(result: JsonObject): KinaseTransition[] {
  return arrayAt(result, ["transitions"]).flatMap((item) => normalizeKinaseTransition(item) ?? []);
}

function finiteOrNull(value: JsonValue | undefined): boolean {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function boundedIntegerValue(value: JsonValue | undefined, minimum: number, maximum: number): boolean {
  return typeof value === "number"
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum;
}

function validReactomeUncertainty(value: JsonValue | undefined): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_UNCERTAINTY_FIELDS)) return false;
  const components = [
    value.measurement_standard_error,
    value.fitted_model_standard_error,
    value.measurement_model_covariance,
    value.combined_standard_error,
    value.variance_closure_residual,
  ];
  if (!components.every(finiteOrNull)) return false;
  if (value.state === "estimated") {
    return components.every((item) => typeof item === "number")
      && typeof value.bootstrap_replicates_used === "number"
      && Number.isInteger(value.bootstrap_replicates_used)
      && value.bootstrap_replicates_used >= 1
      && value.bootstrap_replicates_used <= 256
      && value.reason === null;
  }
  return value.state === "not_estimable"
    && components.every((item) => item === null)
    && value.bootstrap_replicates_used === 0
    && nonEmptyText(value.reason);
}

function validReactomeContribution(value: JsonValue): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_CONTRIBUTION_FIELDS)) return false;
  return typeof value.gene_symbol === "string"
    && /^[A-Z0-9][A-Z0-9._/-]*$/.test(value.gene_symbol)
    && typeof value.from_observation_id === "string"
    && IDENTIFIER.test(value.from_observation_id)
    && typeof value.to_observation_id === "string"
    && IDENTIFIER.test(value.to_observation_id)
    && typeof value.from_provenance_digest === "string"
    && DIGEST.test(value.from_provenance_digest)
    && typeof value.to_provenance_digest === "string"
    && DIGEST.test(value.to_provenance_digest)
    && value.from_state === "observed"
    && value.to_state === "observed"
    && value.value_semantics === "exact_delta"
    && [
      value.standardized_delta,
      value.pathway_loading,
      value.global_loading,
      value.unadjusted_contribution,
      value.global_adjustment_contribution,
      value.conditional_contribution,
      value.reliability_weight,
    ].every((item) => typeof item === "number" && Number.isFinite(item))
    && typeof value.reliability_weight === "number"
    && value.reliability_weight > 0
    && value.reliability_weight <= 1
    && (
      value.direction === "conditional_source_recurrence_aligned"
      || value.direction === "conditional_source_primary_aligned"
    );
}

function validReactomeAblation(value: JsonValue): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_ABLATION_FIELDS)) return false;
  const kinds = new Set([
    "global_axis",
    "source_processing",
    "degree_normalization",
    "unique_members",
    "leave_pathway_out",
    "overlapping_pathway",
    "top_contribution",
  ]);
  const classifications = new Set([
    "conditional_source_recurrence_aligned",
    "conditional_source_primary_aligned",
    "conditionally_stable",
    "indeterminate",
    "not_estimable",
  ]);
  if (
    typeof value.component_kind !== "string"
    || !kinds.has(value.component_kind)
    || !nonEmptyText(value.component_id)
    || typeof value.support !== "string"
    || !new Set(["supported", "limited", "abstained"]).has(value.support)
    || !finiteOrNull(value.conditional_score_without_component)
    || !finiteOrNull(value.score_delta)
    || typeof value.classification_without_component !== "string"
    || !classifications.has(value.classification_without_component)
    || !boundedIntegerValue(value.removed_feature_count, 0, 4_096)
  ) return false;
  if (value.support === "abstained") {
    return value.conditional_score_without_component === null
      && value.score_delta === null
      && value.classification_without_component === "not_estimable"
      && nonEmptyText(value.reason);
  }
  return typeof value.conditional_score_without_component === "number"
    && typeof value.score_delta === "number"
    && value.classification_without_component !== "not_estimable"
    && (value.support === "limited" ? nonEmptyText(value.reason) : value.reason === null);
}

function validReactomeAblations(value: JsonValue | undefined): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_ABLATIONS_FIELDS)) return false;
  const scalarKeys = [
    "global_axis",
    "degree_normalization",
    "unique_members",
    "leave_pathway_out",
  ] as const;
  if (scalarKeys.some((key) => value[key] !== null && !validReactomeAblation(value[key]))) {
    return false;
  }
  const arrays = [
    [value.source_processing, 4],
    [value.overlap, 9],
    [value.top_contributions, 10],
  ] as const;
  return arrays.every(([items, maximum]) => (
    Array.isArray(items)
    && items.length <= maximum
    && items.every(validReactomeAblation)
  ));
}

function validReactomeGlobal(value: JsonValue | undefined): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_GLOBAL_FIELDS)) return false;
  const supports = new Set(["supported", "limited", "abstained"]);
  const classifications = new Set([
    "source_recurrence_aligned",
    "source_primary_aligned",
    "stable",
    "indeterminate",
    "not_estimable",
  ]);
  if (
    value.output_semantics !== "global_recurrence_concordance"
    || typeof value.support !== "string"
    || !supports.has(value.support)
    || typeof value.classification !== "string"
    || !classifications.has(value.classification)
    || !finiteOrNull(value.score)
    || !finiteOrNull(value.lower_bound)
    || !finiteOrNull(value.upper_bound)
    || value.interval_level !== 0.9
    || !boundedIntegerValue(value.shared_active_gene_count, 0, 4_096)
    || typeof value.coefficient_mass_coverage !== "number"
    || value.coefficient_mass_coverage < 0
    || value.coefficient_mass_coverage > 1
    || typeof value.effective_sample_size !== "number"
    || !Number.isFinite(value.effective_sample_size)
    || value.effective_sample_size < 0
    || !boundedIntegerValue(value.bootstrap_replicates_used, 0, 256)
    || !exactStringArray(value.abstention_reasons, 0, 8, nonEmptyText)
  ) return false;
  if (value.support === "abstained") {
    return value.score === null
      && value.lower_bound === null
      && value.upper_bound === null
      && value.classification === "not_estimable"
      && value.bootstrap_replicates_used === 0
      && (value.abstention_reasons as JsonValue[]).length > 0;
  }
  return typeof value.score === "number"
    && typeof value.lower_bound === "number"
    && typeof value.upper_bound === "number"
    && value.lower_bound <= value.score
    && value.score <= value.upper_bound
    && value.classification !== "not_estimable"
    && typeof value.bootstrap_replicates_used === "number"
    && value.bootstrap_replicates_used > 0;
}

function validReactomePathway(value: JsonValue, panelIndex: number): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_PATHWAY_FIELDS)) return false;
  const supports = new Set(["supported", "limited", "abstained"]);
  const classifications = new Set([
    "conditional_source_recurrence_aligned",
    "conditional_source_primary_aligned",
    "conditionally_stable",
    "indeterminate",
    "not_estimable",
  ]);
  const optionalNumbers = [
    value.score,
    value.lower_bound,
    value.upper_bound,
    value.unadjusted_pathway_coordinate,
    value.global_adjustment,
    value.request_reconstruction_median_relative_gain,
    value.stability,
    value.discordance,
  ];
  const integerRanges = [
    [value.source_member_count, 5, 1_500],
    [value.mapped_feature_count, 5, 4_096],
    [value.fitted_feature_count, 1, 4_096],
    [value.active_feature_count, 0, 4_096],
    [value.observed_count, 0, 4_096],
    [value.left_censored_count, 0, 4_096],
    [value.unique_active_gene_count, 0, 4_096],
    [value.request_reconstruction_evaluable_fold_count, 0, 5],
    [value.request_reconstruction_improved_fold_count, 0, 5],
  ] as const;
  if (
    value.panel_index !== panelIndex
    || typeof value.domain_id !== "string"
    || !IDENTIFIER.test(value.domain_id)
    || typeof value.reactome_id !== "string"
    || !REACTOME_ID.test(value.reactome_id)
    || !nonEmptyText(value.pathway_name)
    || value.output_semantics !== "conditional_pathway_concordance"
    || typeof value.support !== "string"
    || !supports.has(value.support)
    || typeof value.classification !== "string"
    || !classifications.has(value.classification)
    || !optionalNumbers.every(finiteOrNull)
    || value.interval_level !== 0.9
    || integerRanges.some(([item, minimum, maximum]) => (
      !boundedIntegerValue(item, minimum, maximum)
    ))
    || typeof value.coefficient_mass_coverage !== "number"
    || value.coefficient_mass_coverage < 0
    || value.coefficient_mass_coverage > 1
    || typeof value.unique_coefficient_mass !== "number"
    || value.unique_coefficient_mass < 0
    || value.unique_coefficient_mass > 1
    || typeof value.effective_sample_size !== "number"
    || !Number.isFinite(value.effective_sample_size)
    || value.effective_sample_size < 0
    || typeof value.overlap_confounded !== "boolean"
    || !validReactomeUncertainty(value.uncertainty)
    || !Array.isArray(value.top_contributions)
    || value.top_contributions.length > 10
    || !value.top_contributions.every(validReactomeContribution)
    || !validReactomeAblations(value.ablations)
    || !exactStringArray(value.abstention_reasons, 0, 12, nonEmptyText)
  ) return false;
  if (
    value.active_feature_count !== (
      Number(value.observed_count) + Number(value.left_censored_count)
    )
    || Number(value.unique_active_gene_count) > Number(value.active_feature_count)
    || Number(value.request_reconstruction_improved_fold_count)
      > Number(value.request_reconstruction_evaluable_fold_count)
  ) return false;
  if (value.support === "abstained") {
    return [
      value.score,
      value.lower_bound,
      value.upper_bound,
      value.unadjusted_pathway_coordinate,
      value.global_adjustment,
      value.stability,
      value.discordance,
      value.request_reconstruction_median_relative_gain,
    ].every((item) => item === null)
      && value.classification === "not_estimable"
      && (value.abstention_reasons as JsonValue[]).length > 0;
  }
  return [
    value.score,
    value.lower_bound,
    value.upper_bound,
    value.unadjusted_pathway_coordinate,
    value.global_adjustment,
    value.stability,
    value.discordance,
    value.request_reconstruction_median_relative_gain,
  ].every((item) => typeof item === "number")
    && value.classification !== "not_estimable";
}

function validReactomeTransition(value: JsonValue, transitionIndex: number): boolean {
  if (!isJsonObject(value) || !exactShape(value, REACTOME_TRANSITION_FIELDS)) return false;
  return value.transition_index === transitionIndex
    && validReactomeGlobal(value.global_recurrence)
    && Array.isArray(value.pathways)
    && value.pathways.length === 10
    && value.pathways.every((pathway, panelIndex) => validReactomePathway(pathway, panelIndex));
}

function validateChildResultContract(
  result: JsonObject,
  child: "reactome" | "kinase",
  path: string,
  errors: string[],
): void {
  const reactome = child === "reactome";
  exactFields(
    result,
    reactome ? REACTOME_RESULT_FIELDS : KINASE_RESULT_FIELDS,
    path,
    errors,
  );
  const expectedAlgorithmId = reactome
    ? "kncc-reactome-conditional-transition"
    : "kncc-gbm-longitudinal-kinase-transition";
  if (result.algorithm_id !== expectedAlgorithmId) {
    errors.push(`${path}.algorithm_id must equal ${expectedAlgorithmId}.`);
  }
  if (result.algorithm_version !== "1.0.0") {
    errors.push(`${path}.algorithm_version must equal 1.0.0.`);
  }
  if (typeof result.series_id !== "string" || !IDENTIFIER.test(result.series_id)) {
    errors.push(`${path}.series_id must be a valid identifier.`);
  }
  if (!isJsonObject(result.assay_compatibility)) {
    errors.push(`${path}.assay_compatibility must be an object.`);
  }
  if (!isJsonObject(result.normalization_reference)) {
    errors.push(`${path}.normalization_reference must be an object.`);
  }
  if (!isJsonObject(result.provenance)) {
    errors.push(`${path}.provenance must be an object.`);
  }
  const minimumLimitations = reactome ? 6 : 1;
  const maximumLimitations = reactome ? 20 : 16;
  if (
    !exactStringArray(
      result.limitations,
      minimumLimitations,
      maximumLimitations,
      nonEmptyText,
    )
  ) {
    errors.push(
      `${path}.limitations must contain ${minimumLimitations} through ${maximumLimitations} non-empty strings.`,
    );
  }
  if (result.research_use_only !== true || result.non_prescriptive !== true) {
    errors.push(`${path} must remain research-use-only and non-prescriptive.`);
  }
  if (reactome) {
    if (
      result.output_semantics
      !== "global_recurrence_concordance_and_conditional_pathway_concordance_only"
    ) {
      errors.push(`${path}.output_semantics exceeds the Reactome concordance-only boundary.`);
    }
    if (
      result.validation_scope
      !== "same_cohort_patient_grouped_evaluation_not_external_validation"
    ) {
      errors.push(`${path}.validation_scope must remain same-cohort and non-external.`);
    }
  } else {
    if (result.output_semantics !== "SPHINKS_signature_transition_concordance_only") {
      errors.push(`${path}.output_semantics exceeds the SPHINKS concordance-only boundary.`);
    }
    for (const field of [
      "infers_kinase_activity",
      "infers_biochemical_activity",
      "makes_causal_claim",
      "independent_evidence",
    ] as const) {
      if (result[field] !== false) errors.push(`${path}.${field} must remain false.`);
    }
  }
  if (
    isDigest(result.result_digest)
    && result.result_digest !== factorGraphChildResultDigest(result)
  ) {
    errors.push(`${path}.result_digest must match canonical nested child content.`);
  }
}

function validateChildResultTopology(
  result: JsonObject,
  child: "reactome" | "kinase",
  expectedProfileId: string,
  transitionNormalizer: (result: JsonObject) => unknown[],
  path: string,
  errors: string[],
): void {
  validateChildResultContract(result, child, path, errors);
  if (result.profile_id !== expectedProfileId) errors.push(`${path}.profile_id must equal ${expectedProfileId}.`);
  for (const digestField of ["profile_digest", "request_digest", "result_digest"] as const) {
    if (typeof result[digestField] !== "string" || !DIGEST.test(result[digestField] as string)) {
      errors.push(`${path}.${digestField} must be a lowercase sha256 digest.`);
    }
  }
  const timePointIds = stringValues(result.time_point_ids);
  const transitions = arrayAt(result, ["transitions"]);
  if (timePointIds.length < 2 || timePointIds.length > GBM_FACTOR_GRAPH_MAX_TIME_POINTS || !unique(timePointIds)) {
    errors.push(`${path}.time_point_ids must contain 2 through 5 unique identifiers.`);
  }
  if (transitions.length !== Math.max(0, timePointIds.length - 1)) {
    errors.push(`${path}.transitions must contain one entry per consecutive time-point pair.`);
  }
  transitions.forEach((transition, index) => {
    const transitionPath = `${path}.transitions[${index}]`;
    if (!isJsonObject(transition)) {
      errors.push(`${transitionPath} must be an object.`);
      return;
    }
    if (
      typeof transition.transition_id !== "string"
      || !IDENTIFIER.test(transition.transition_id)
    ) {
      errors.push(`${transitionPath}.transition_id must be a valid identifier.`);
    }
    if (transition.transition_index !== index) {
      errors.push(`${transitionPath}.transition_index must equal ${index}.`);
    }
    if (
      transition.from_time_point_id !== timePointIds[index]
      || transition.to_time_point_id !== timePointIds[index + 1]
    ) {
      errors.push(`${transitionPath} endpoints must match consecutive result time points.`);
    }
    if (
      child === "reactome"
      && (
        typeof transition.duration_days !== "number"
        || !Number.isFinite(transition.duration_days)
        || transition.duration_days <= 0
      )
    ) {
      errors.push(`${transitionPath}.duration_days must be a finite positive number.`);
    }
  });
  if (
    child === "reactome"
    && transitions.some((transition, index) => !validReactomeTransition(transition, index))
  ) {
    errors.push(`${path}.transitions contains malformed or incomplete Reactome child results.`);
  }
  const normalized = transitionNormalizer(result);
  if (normalized.length !== transitions.length) errors.push(`${path}.transitions contains malformed or incomplete child results.`);
}

function validateChildBinding(
  value: JsonValue | undefined,
  path: string,
  block: FactorGraphBlock,
  childProfileId: string,
  childResult: JsonObject | null,
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, CHILD_BINDING_FIELDS, path, errors);
  if (value.block !== block) errors.push(`${path}.block must equal ${block}.`);
  if (value.child_profile_id !== childProfileId) errors.push(`${path}.child_profile_id must equal ${childProfileId}.`);
  for (const field of ["child_profile_digest", "child_request_digest", "child_result_digest"] as const) {
    if (typeof value[field] !== "string" || !DIGEST.test(value[field] as string)) {
      errors.push(`${path}.${field} must be a lowercase sha256 digest.`);
    }
  }
  if (value.independently_computed !== true) errors.push(`${path}.independently_computed must be true.`);
  if (childResult) {
    const comparisons = [
      ["child_profile_digest", "profile_digest"],
      ["child_request_digest", "request_digest"],
      ["child_result_digest", "result_digest"],
    ] as const;
    for (const [bindingField, resultField] of comparisons) {
      if (value[bindingField] !== childResult[resultField]) errors.push(`${path}.${bindingField} must match ${resultField} on the nested child result.`);
    }
  }
}

export function validateFactorGraphResult(result: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (result.algorithm_id !== "glio-ecgi-kncc-gbm-transition") errors.push("result.algorithm_id is invalid.");
  if (result.algorithm_version !== "1.0.0") errors.push("result.algorithm_version must equal 1.0.0.");
  if (result.profile_id !== GBM_FACTOR_GRAPH_PROFILE_ID) errors.push(`result.profile_id must equal ${GBM_FACTOR_GRAPH_PROFILE_ID}.`);
  if (typeof result.analysis_id !== "string" || !IDENTIFIER.test(result.analysis_id)) errors.push("result.analysis_id must be a valid identifier.");
  if (result.relationship !== GBM_FACTOR_GRAPH_RELATIONSHIP) errors.push(`result.relationship must equal ${GBM_FACTOR_GRAPH_RELATIONSHIP}.`);
  for (const field of ["profile_digest", "topology_digest", "request_digest", "result_digest"] as const) {
    if (typeof result[field] !== "string" || !DIGEST.test(result[field] as string)) errors.push(`result.${field} must be a lowercase sha256 digest.`);
  }
  if (
    isDigest(result.result_digest)
    && result.result_digest !== factorGraphResultDigest(result)
  ) {
    errors.push("result.result_digest must match canonical result content.");
  }
  if (result.topology_digest !== GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST) {
    errors.push("result.topology_digest must equal the version-locked factor topology digest.");
  }
  if (result.research_use_only !== true || result.non_prescriptive !== true || result.independent_parallel_blocks !== true) {
    errors.push("result must remain research-only, non-prescriptive, and independently parallel.");
  }
  if (result.cross_modal_fusion_performed !== false || result.numerical_cross_block_edge_count !== 0) {
    errors.push("result must report no cross-modal fusion and zero numerical cross-block edges.");
  }
  const limitations = stringValues(result.limitations);
  if (limitations.length < 6 || limitations.length > 20 || limitations.length !== arrayAt(result, ["limitations"]).length) {
    errors.push("result.limitations must contain 6 through 20 non-empty strings.");
  }

  const reactomeResult = objectAt(result, ["reactome_result"]);
  const kinaseResult = objectAt(result, ["kinase_result"]);
  if (!reactomeResult) errors.push("result.reactome_result must be an object.");
  else validateChildResultTopology(
    reactomeResult,
    "reactome",
    LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
    (child) => {
      const normalized = normalizeReactomeTransitions(child);
      return normalized.filter((transition) => transition.pathways.length === 10);
    },
    "result.reactome_result",
    errors,
  );
  if (!kinaseResult) errors.push("result.kinase_result must be an object.");
  else validateChildResultTopology(
    kinaseResult,
    "kinase",
    GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    normalizeFactorGraphKinaseTransitions,
    "result.kinase_result",
    errors,
  );

  const provenance = objectAt(result, ["provenance"]);
  if (!provenance) {
    errors.push("result.provenance must be an object.");
  } else {
    exactFields(provenance, PROVENANCE_FIELDS, "result.provenance", errors);
    if (provenance.engine !== GBM_FACTOR_GRAPH_PROFILE_ID) errors.push("result.provenance.engine is invalid.");
    if (provenance.relationship !== GBM_FACTOR_GRAPH_RELATIONSHIP) errors.push("result.provenance.relationship is invalid.");
    for (const field of ["request_digest", "profile_digest", "topology_digest", "source_inventory_digest"] as const) {
      if (typeof provenance[field] !== "string" || !DIGEST.test(provenance[field] as string)) errors.push(`result.provenance.${field} must be a lowercase sha256 digest.`);
    }
    if (
      provenance.request_digest !== result.request_digest
      || provenance.profile_digest !== result.profile_digest
      || provenance.topology_digest !== result.topology_digest
    ) errors.push("result outer digests must match provenance.");
    if (
      provenance.independent_parallel_blocks !== true
      || provenance.cross_modal_fusion_performed !== false
      || provenance.no_numerical_cross_block_edges !== true
    ) errors.push("result.provenance must preserve the independent no-fusion composition boundary.");
    validateChildBinding(
      provenance.reactome_child,
      "result.provenance.reactome_child",
      "protein_reactome",
      LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
      reactomeResult,
      errors,
    );
    validateChildBinding(
      provenance.kinase_child,
      "result.provenance.kinase_child",
      "phosphosite_sphinks",
      GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
      kinaseResult,
      errors,
    );
  }
  return errors;
}

function validateChildResultRequestBinding(
  result: JsonObject | null,
  request: JsonObject | null,
  path: string,
  modality: "reactome" | "kinase",
  expectedProfileId: string,
  errors: string[],
): void {
  if (!result || !request) return;
  const normalizedRequest = normalizedFactorGraphChildRequest(request, modality);
  if (!isJsonObject(normalizedRequest)) {
    errors.push(`${path} cannot be bound to a malformed child request.`);
    return;
  }
  if (result.series_id !== normalizedRequest.series_id) {
    errors.push(`${path}.series_id must match the submitted child request.`);
  }
  const requestProfileId = normalizedRequest.profile_id ?? expectedProfileId;
  if (result.profile_id !== requestProfileId) {
    errors.push(`${path}.profile_id must match the submitted child request.`);
  }
  if (!sameJson(result.assay_compatibility, normalizedRequest.assay_compatibility)) {
    errors.push(`${path}.assay_compatibility must exactly match the submitted child request.`);
  }
  if (!sameJson(result.normalization_reference, normalizedRequest.normalization_reference)) {
    errors.push(`${path}.normalization_reference must exactly match the submitted child request.`);
  }
  const requestPoints = Array.isArray(normalizedRequest.time_points)
    ? normalizedRequest.time_points
    : [];
  const requestIds = requestPoints.flatMap((item) =>
    isJsonObject(item) && typeof item.time_point_id === "string"
      ? [item.time_point_id]
      : []);
  if (!sameJson(result.time_point_ids, requestIds)) {
    errors.push(`${path}.time_point_ids must exactly match the submitted child request order.`);
  }
}

export function validateFactorGraphResultRequestBinding(
  result: JsonObject,
  request: JsonObject,
): string[] {
  const errors: string[] = [];
  if (result.request_digest !== factorGraphRequestDigest(request)) {
    errors.push("result.request_digest must match the canonical submitted request.");
  }
  if (result.analysis_id !== request.analysis_id) {
    errors.push("result.analysis_id must match the submitted request.");
  }
  const requestProfileId = request.profile_id ?? GBM_FACTOR_GRAPH_PROFILE_ID;
  if (result.profile_id !== requestProfileId) {
    errors.push("result.profile_id must match the submitted request.");
  }
  const relationship = request.relationship ?? GBM_FACTOR_GRAPH_RELATIONSHIP;
  if (result.relationship !== relationship) {
    errors.push("result.relationship must match the submitted request.");
  }
  validateChildResultRequestBinding(
    objectAt(result, ["reactome_result"]),
    objectAt(request, ["reactome_request"]),
    "result.reactome_result",
    "reactome",
    LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
    errors,
  );
  validateChildResultRequestBinding(
    objectAt(result, ["kinase_result"]),
    objectAt(request, ["kinase_request"]),
    "result.kinase_result",
    "kinase",
    GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    errors,
  );
  return errors;
}

export function validateFactorGraphResultProfileBinding(
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors = validateFactorGraphProfile(profile);
  const profileDigest = factorGraphProfileDigest(profile);
  if (!isDigest(profile.profile_digest)) {
    errors.push("loaded profile.profile_digest must be a lowercase sha256 digest.");
  } else if (
    profile.profile_digest !== profileDigest
    || result.profile_digest !== profileDigest
  ) {
    errors.push("result.profile_digest must match the loaded profile.profile_digest.");
  }
  const topology = normalizeFactorGraphTopology(profile);
  if (!topology) {
    errors.push("loaded profile topology was not admitted by the version-locked factor topology validator.");
  } else if (result.topology_digest !== topology.digest) {
    errors.push("result.topology_digest must match the admitted loaded profile topology digest.");
  }
  const provenance = objectAt(result, ["provenance"]);
  if (provenance) {
    if (provenance.source_inventory_digest !== profile.source_inventory_digest) {
      errors.push("result.provenance.source_inventory_digest must match the admitted loaded profile.");
    }
    for (const [name, resultBinding, profileBinding] of [
      ["reactome", objectAt(provenance, ["reactome_child"]), objectAt(profile, ["reactome_child"])],
      ["kinase", objectAt(provenance, ["kinase_child"]), objectAt(profile, ["kinase_child"])],
    ] as const) {
      if (
        resultBinding
        && profileBinding
        && (
          resultBinding.child_profile_id !== profileBinding.child_profile_id
          || resultBinding.child_profile_digest !== profileBinding.child_profile_digest
        )
      ) errors.push(`result.provenance.${name}_child must match the admitted child profile binding.`);
    }
  }
  return errors;
}

export function validateFactorGraphResultHeaders(
  headers: HeaderReader,
  result: JsonObject,
  request: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(
    headers,
    "X-GLIO-Profile-Digest",
    factorGraphProfileDigest(profile),
    errors,
  );
  validateDigestHeader(
    headers,
    "X-GLIO-Request-Digest",
    factorGraphRequestDigest(request),
    errors,
  );
  validateDigestHeader(
    headers,
    "X-GLIO-Result-Digest",
    factorGraphResultDigest(result),
    errors,
  );
  return errors;
}

export function validateFactorGraphVerification(
  verification: JsonObject,
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors = validateFactorGraphProfile(profile);
  exactFields(verification, VERIFICATION_FIELDS, "verification", errors);
  const semanticFields = [
    "reactome_child_verified",
    "kinase_child_verified",
    "independent_parallel_blocks_match",
    "no_cross_modal_fusion_match",
    "no_numerical_cross_block_edges_match",
    "provenance_match",
    "document_semantic_match",
  ] as const;
  const digestFields = [
    "request_digest_match",
    "profile_digest_match",
    "topology_digest_match",
    "source_inventory_digest_match",
    "result_digest_match",
  ] as const;
  for (const field of [
    ...semanticFields,
    ...digestFields,
    "semantic_match",
    "verified",
  ] as const) {
    if (typeof verification[field] !== "boolean") {
      errors.push(`verification.${field} must be Boolean.`);
    }
  }
  const semantic = semanticFields.every((field) => verification[field] === true);
  if (verification.semantic_match !== semantic) {
    errors.push("verification.semantic_match does not close its semantic checks.");
  }
  const verified = digestFields.every((field) => verification[field] === true) && semantic;
  if (verification.verified !== verified) {
    errors.push("verification.verified does not close all digest and semantic checks.");
  }
  for (const field of ["recomputed_request_digest", "recomputed_result_digest"] as const) {
    if (!isDigest(verification[field])) {
      errors.push(`verification.${field} must be a lowercase sha256 digest.`);
    }
  }
  if (
    verification.request_digest_match === true
    && verification.recomputed_request_digest !== result.request_digest
  ) errors.push("verification recomputed request digest does not match the admitted result binding.");
  if (
    verification.result_digest_match === true
    && verification.recomputed_result_digest !== result.result_digest
  ) errors.push("verification recomputed result digest does not match the admitted result.");
  if (
    verification.profile_digest_match === true
    && result.profile_digest !== profile.profile_digest
  ) errors.push("verification profile match does not close the admitted result/profile binding.");
  if (
    verification.topology_digest_match === true
    && (
      result.topology_digest !== profile.topology_digest
      || result.topology_digest !== GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST
    )
  ) errors.push("verification topology match does not close the admitted result/profile binding.");
  const provenance = objectAt(result, ["provenance"]);
  if (
    verification.source_inventory_digest_match === true
    && (!provenance || provenance.source_inventory_digest !== profile.source_inventory_digest)
  ) errors.push("verification source-inventory match does not close the admitted result/profile binding.");
  if (typeof verification.message !== "string" || !verification.message.trim()) {
    errors.push("verification.message must be non-empty.");
  }
  return errors;
}

export function validateFactorGraphVerificationHeaders(
  headers: HeaderReader,
  verification: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(
    headers,
    "X-GLIO-Profile-Digest",
    factorGraphProfileDigest(profile),
    errors,
  );
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

export function normalizeFactorGraphResult(result: JsonObject): NormalizedFactorGraphResult | null {
  if (validateFactorGraphResult(result).length) return null;
  const reactomeResult = objectAt(result, ["reactome_result"]);
  const kinaseResult = objectAt(result, ["kinase_result"]);
  if (!reactomeResult || !kinaseResult) return null;
  return {
    reactomeResult,
    kinaseResult,
    reactomeTransitions: normalizeReactomeTransitions(reactomeResult),
    kinaseTransitions: normalizeFactorGraphKinaseTransitions(kinaseResult),
  };
}
