import {
  isJsonObject,
  validateResearchRequest,
  type JsonObject,
  type JsonValue,
} from "./research-state";
import { graphTopologyDigest, sha256Hex } from "./topology-provenance";

export const ECGI_PROFILE_ID = "glio-ecgi/1.0.0";
export const ECGI_CLAIM_CEILING = "limited_unvalidated_caller_graph";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const IDENTIFIER = /^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$/;
const RESULT_SUPPORT = new Set(["limited", "abstained"]);
const NODE_KINDS = new Set([
  "protein",
  "proteoform",
  "phosphosite",
  "complex",
  "pathway",
  "kinase",
]);
const STATE_CLASSIFICATIONS = new Set([
  "activated",
  "suppressed",
  "neutral",
  "indeterminate",
  "not_estimable",
]);
const DRIVER_TYPES = new Set(["observation", "edge", "kinase_feedback"]);
const ABLATION_KINDS = new Set(["edge_family", "modality"]);

const PROFILE_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "numpy_version",
  "constants",
  "limits",
  "relation_weights",
  "demo_graph_digest",
  "demo_topology_provenance_digest",
  "profile_digest",
  "claim_ceiling",
  "safety_class",
  "interpretation",
]);

const RESULT_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "profile_digest",
  "request_digest",
  "result_digest",
  "sample_id",
  "solver",
  "node_states",
  "kinase_states",
  "external_kinase_comparison",
  "provenance",
  "limitations",
  "research_use_only",
  "non_prescriptive",
]);

const NODE_STATE_FIELDS = new Set([
  "node_id",
  "kind",
  "activity",
  "lower_bound",
  "upper_bound",
  "classification",
  "support",
  "evidence_count",
  "observed_count",
  "censored_count",
  "stability",
  "discordance",
  "top_drivers",
  "ablation_effects",
  "abstention_reason",
]);

const KINASE_STATE_FIELDS = new Set([
  ...NODE_STATE_FIELDS,
  "mapped_substrates",
  "rank_statistic",
  "enrichment_score",
  "null_standard_deviation",
  "p_value",
  "q_value",
]);

const DRIVER_FIELDS = new Set([
  "driver_id",
  "driver_type",
  "signed_contribution",
  "strength",
]);

const ABLATION_FIELDS = new Set([
  "kind",
  "omitted",
  "activity_delta",
]);

const EXTERNAL_COMPARISON_FIELDS = new Set([
  "profile_id",
  "source_digest",
  "matches",
  "unmatched_local_ids",
  "external_ids_with_abstained_local_estimates",
  "rank_correlation",
  "note",
]);

const EXTERNAL_MATCH_FIELDS = new Set([
  "kinase_id",
  "local_activity",
  "external_activity",
  "interval_overlap",
  "direction_agreement",
  "activity_difference",
]);

const SOLVER_FIELDS = new Set(["first_pass", "second_pass"]);
const SOLVER_PASS_FIELDS = new Set([
  "pass_name",
  "solver_kind",
  "objective_trace_semantics",
  "convergence_measure",
  "converged",
  "iterations",
  "final_objective",
  "max_update",
  "objective_trace",
  "trace_digest",
]);

const PROVENANCE_FIELDS = new Set([
  "engine",
  "numpy_version",
  "profile_digest",
  "request_digest",
  "computational_digest",
  "deterministic_seed",
  "observation_source_digests",
  "topology",
  "demo_graph_digest",
]);

const VERIFICATION_FIELDS = new Set([
  "verified",
  "request_digest_match",
  "profile_digest_match",
  "solver_trace_match",
  "result_digest_match",
  "semantic_match",
  "provided_result_digest",
  "recomputed_result_digest",
  "recomputed_request_digest",
  "message",
]);

const VERIFICATION_FLAGS = [
  "request_digest_match",
  "profile_digest_match",
  "solver_trace_match",
  "result_digest_match",
  "semantic_match",
] as const;

// Pydantic emits these fields as Python floats even when their numerical value is
// integral. JavaScript loses that lexical distinction after JSON.parse, so the
// canonical encoder restores it before hashing the backend-compatible projection.
const FLOAT_FIELDS = new Set([
  "weight",
  "standardized_effect",
  "standard_error",
  "quality_weight",
  "activity",
  "lower_bound",
  "upper_bound",
  "final_objective",
  "max_update",
  "objective_trace",
  "signed_contribution",
  "strength",
  "activity_delta",
  "stability",
  "discordance",
  "rank_statistic",
  "enrichment_score",
  "null_standard_deviation",
  "p_value",
  "q_value",
  "local_activity",
  "external_activity",
  "activity_difference",
  "rank_correlation",
  "huber_delta",
  "ridge_penalty",
  "complex_coherence_weight",
  "essential_bottleneck_weight",
  "damping",
  "tolerance",
  "relaxed_tolerance",
  "objective_increase_tolerance",
  "backtracking_factor",
  "activation_threshold",
  "kinase_q_threshold",
  "kinase_null_sd_floor",
  "kinase_score_clip",
  "kinase_feedback_standard_error",
  "kinase_feedback_weight",
  "empirical_p_pseudocount",
  "rank_center",
  "reliability_stratum_q1",
  "reliability_stratum_q2",
  "reliability_stratum_q3",
  "bootstrap_perturbation_scale",
  "interval_lower_quantile",
  "interval_upper_quantile",
  "discordance_scale",
]);

export type HeaderReader = { get(name: string): string | null };

function exactFields(
  source: JsonObject,
  expected: ReadonlySet<string>,
  path: string,
  errors: string[],
): void {
  const missing = [...expected].filter((field) => !Object.prototype.hasOwnProperty.call(source, field));
  const unknown = Object.keys(source).filter((field) => !expected.has(field));
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function isDigest(value: JsonValue | undefined): value is string {
  return typeof value === "string" && DIGEST.test(value);
}

function isFiniteNumber(value: JsonValue | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isIdentifier(value: JsonValue | undefined): value is string {
  return typeof value === "string" && IDENTIFIER.test(value);
}

function isNonEmptyText(value: JsonValue | undefined): value is string {
  return typeof value === "string"
    && [...value].length >= 1
    && [...value].length <= 512
    && value.trim() === value
    && value.trim().length > 0;
}

function isBoundedInteger(
  value: JsonValue | undefined,
  minimum: number,
  maximum: number,
): value is number {
  return typeof value === "number"
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum;
}

function isNullableBoundedNumber(
  value: JsonValue | undefined,
  minimum: number,
  maximum: number,
  exclusiveMinimum = false,
): boolean {
  if (value === null) return true;
  if (!isFiniteNumber(value)) return false;
  return (exclusiveMinimum ? value > minimum : value >= minimum) && value <= maximum;
}

function pythonFloat(value: number): string {
  if (!Number.isFinite(value)) throw new Error("Non-finite values cannot be canonicalized.");
  if (Object.is(value, -0)) return "-0.0";
  const negative = value < 0;
  const source = Math.abs(value).toString().toLowerCase();
  const [coefficient, exponentText] = source.split("e");
  const [integerPart, fractionPart = ""] = coefficient.split(".");
  const combined = `${integerPart}${fractionPart}`;
  const firstNonzero = combined.search(/[1-9]/);
  if (firstNonzero < 0) return negative ? "-0.0" : "0.0";
  let exponent: number;
  if (exponentText !== undefined) {
    exponent = Number(exponentText) + integerPart.length - firstNonzero - 1;
  } else {
    exponent = integerPart.length - firstNonzero - 1;
  }
  const digits = combined.slice(firstNonzero).replace(/0+$/, "") || "0";
  const prefix = negative ? "-" : "";
  if (exponent < -4 || exponent >= 16) {
    const mantissa = digits.length === 1 ? digits : `${digits[0]}.${digits.slice(1)}`;
    const exponentSign = exponent < 0 ? "-" : "+";
    return `${prefix}${mantissa}e${exponentSign}${Math.abs(exponent).toString().padStart(2, "0")}`;
  }
  if (exponent >= 0) {
    const split = exponent + 1;
    const fixed = digits.length <= split
      ? `${digits}${"0".repeat(split - digits.length)}`
      : `${digits.slice(0, split)}.${digits.slice(split)}`;
    return `${prefix}${fixed.includes(".") ? fixed : `${fixed}.0`}`;
  }
  return `${prefix}0.${"0".repeat(-exponent - 1)}${digits}`;
}

function backendCanonicalJson(value: JsonValue, parentKey = ""): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    return FLOAT_FIELDS.has(parentKey) ? pythonFloat(value) : JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => backendCanonicalJson(item, parentKey)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${backendCanonicalJson(value[key], key)}`)
    .join(",")}}`;
}

function digestValue(value: JsonValue): string {
  return `sha256:${sha256Hex(backendCanonicalJson(value))}`;
}

function compareText(left: JsonValue | undefined, right: JsonValue | undefined): number {
  const leftText = String(left);
  const rightText = String(right);
  return leftText < rightText ? -1 : leftText > rightText ? 1 : 0;
}

function sortedObjects(value: JsonValue | undefined, key: string): JsonObject[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isJsonObject)
    .map((item) => ({ ...item }))
    .sort((left, right) => compareText(left[key], right[key]));
}

function canonicalTopologySource(source: JsonObject): JsonObject {
  return {
    source_id: source.source_id,
    resource_name: source.resource_name,
    resource_release: source.resource_release,
    record_id: source.record_id,
    record_title: source.record_title,
    source_uri: source.source_uri,
    source_format: source.source_format,
    source_digest: source.source_digest,
    source_size_bytes: source.source_size_bytes,
    license_id: source.license_id,
    license_uri: source.license_uri,
    retrieved_on: source.retrieved_on,
    scope_node_ids: Array.isArray(source.scope_node_ids) ? [...source.scope_node_ids].sort() : [],
    role: source.role ?? "biological_context",
  };
}

function canonicalTopology(
  topology: JsonObject,
  sortCollections: boolean,
): JsonObject {
  const sources = (Array.isArray(topology.sources) ? topology.sources : [])
    .filter(isJsonObject)
    .map(canonicalTopologySource);
  if (sortCollections) sources.sort((left, right) => compareText(left.source_id, right.source_id));
  return {
    topology_digest: topology.topology_digest,
    derivation: topology.derivation,
    sources,
    curation_note: topology.curation_note,
  };
}

function canonicalRequest(request: JsonObject): JsonObject {
  const nodes = sortedObjects(request.nodes, "node_id").map((node) => ({
    node_id: node.node_id,
    kind: node.kind,
    display_name: node.display_name ?? null,
  }));
  const edges = sortedObjects(request.edges ?? [], "edge_id").map((edge) => ({
    edge_id: edge.edge_id,
    source_id: edge.source_id,
    target_id: edge.target_id,
    kind: edge.kind,
    sign: edge.sign,
    weight: edge.weight,
    essential: edge.essential ?? false,
  }));
  const observations = sortedObjects(request.observations ?? [], "observation_id").map((observation) => ({
    observation_id: observation.observation_id,
    node_id: observation.node_id,
    modality: observation.modality,
    state: observation.state,
    standardized_effect: observation.standardized_effect ?? null,
    standard_error: observation.standard_error ?? null,
    quality_weight: observation.quality_weight ?? 1,
    provenance_digest: observation.provenance_digest,
  }));
  const external = isJsonObject(request.external_kinase_profile)
    ? {
      profile_id: request.external_kinase_profile.profile_id,
      source_digest: request.external_kinase_profile.source_digest,
      estimates: sortedObjects(request.external_kinase_profile.estimates, "kinase_id").map((estimate) => ({
        kinase_id: estimate.kinase_id,
        activity: estimate.activity,
        lower_bound: estimate.lower_bound,
        upper_bound: estimate.upper_bound,
      })),
    }
    : null;
  const document: JsonObject = {
    profile_id: request.profile_id ?? ECGI_PROFILE_ID,
    sample_id: request.sample_id,
    nodes,
    edges,
    observations,
    bootstrap_replicates: request.bootstrap_replicates ?? 64,
    permutation_replicates: request.permutation_replicates ?? 256,
    external_kinase_profile: external,
  };
  if (isJsonObject(request.topology_provenance)) {
    document.topology_provenance = canonicalTopology(request.topology_provenance, true);
  }
  return document;
}

export function ecgiRequestDigest(request: JsonObject): string | null {
  return validateResearchRequest(request).length === 0
    ? digestValue(canonicalRequest(request))
    : null;
}

export function ecgiProfileDigest(profile: JsonObject): string | null {
  if (!Object.prototype.hasOwnProperty.call(profile, "profile_digest")) return null;
  const payload: JsonObject = { ...profile };
  delete payload.profile_digest;
  return digestValue(payload);
}

export function ecgiResultDigest(result: JsonObject): string | null {
  if (!Object.prototype.hasOwnProperty.call(result, "result_digest")) return null;
  const payload: JsonObject = { ...result };
  delete payload.result_digest;
  return digestValue(payload);
}

function validateHeader(
  headers: HeaderReader,
  name: string,
  expected: JsonValue | undefined,
  errors: string[],
): void {
  const value = headers.get(name);
  if (value === null) {
    errors.push(`${name} response header is required.`);
  } else if (!DIGEST.test(value)) {
    errors.push(`${name} response header must be a lowercase sha256 digest.`);
  } else if (typeof expected !== "string" || value !== expected) {
    errors.push(`${name} response header does not match the admitted receipt body.`);
  }
}

export function validateEcgiProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (
    profile.algorithm_id !== "glio-ecgi"
    || profile.algorithm_version !== "1.0.0"
    || profile.profile_id !== ECGI_PROFILE_ID
  ) errors.push("profile algorithm identity is invalid.");
  if (profile.numpy_version !== "2.5.2") errors.push("profile.numpy_version must equal the pinned 2.5.2 runtime.");
  if (profile.claim_ceiling !== ECGI_CLAIM_CEILING) {
    errors.push(`profile.claim_ceiling must equal ${ECGI_CLAIM_CEILING}.`);
  }
  if (profile.safety_class !== "research_use_only" || profile.interpretation !== "non_prescriptive") {
    errors.push("profile must remain research-use-only and non-prescriptive.");
  }
  for (const field of ["demo_graph_digest", "demo_topology_provenance_digest", "profile_digest"] as const) {
    if (!isDigest(profile[field])) errors.push(`profile.${field} must be a lowercase sha256 digest.`);
  }
  if (!isJsonObject(profile.constants)) errors.push("profile.constants must be an object.");
  if (!isJsonObject(profile.limits)) errors.push("profile.limits must be an object.");
  if (!Array.isArray(profile.relation_weights)) errors.push("profile.relation_weights must be an array.");
  const computed = ecgiProfileDigest(profile);
  if (computed !== null && isDigest(profile.profile_digest) && computed !== profile.profile_digest) {
    errors.push("profile.profile_digest does not match the canonical profile content.");
  }
  return errors;
}

export function validateEcgiProfileHeaders(headers: HeaderReader, profile: JsonObject): string[] {
  const errors: string[] = [];
  validateHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  return errors;
}

export function validateEcgiDemo(
  request: JsonObject,
  headers: HeaderReader,
  profile: JsonObject,
): string[] {
  const errors = validateResearchRequest(request);
  const requestDigest = ecgiRequestDigest(request);
  if (request.profile_id !== ECGI_PROFILE_ID) errors.push(`demo.profile_id must equal ${ECGI_PROFILE_ID}.`);
  if (graphTopologyDigest(request) !== profile.demo_graph_digest) {
    errors.push("demo graph topology does not match profile.demo_graph_digest.");
  }
  if (!isJsonObject(request.topology_provenance)) {
    errors.push("demo.topology_provenance is required for profile binding.");
  } else {
    const provenanceDigest = digestValue(canonicalTopology(request.topology_provenance, false));
    if (provenanceDigest !== profile.demo_topology_provenance_digest) {
      errors.push("demo topology provenance does not match profile.demo_topology_provenance_digest.");
    }
  }
  validateHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  validateHeader(headers, "X-GLIO-Request-Digest", requestDigest ?? undefined, errors);
  return errors;
}

function validateSolverPass(
  value: JsonValue | undefined,
  path: string,
  expectedPassName: "evidence_graph" | "kinase_feedback",
  errors: string[],
): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, SOLVER_PASS_FIELDS, path, errors);
  if (value.pass_name !== expectedPassName) {
    errors.push(`${path}.pass_name must equal ${expectedPassName}.`);
  }
  if (value.solver_kind !== "directed_conditional_irls") {
    errors.push(`${path}.solver_kind must equal directed_conditional_irls.`);
  }
  if (value.objective_trace_semantics !== "paired_frozen_parent_baseline_candidate") {
    errors.push(
      `${path}.objective_trace_semantics must equal paired_frozen_parent_baseline_candidate.`,
    );
  }
  if (value.convergence_measure !== "maximum_undamped_fixed_point_residual") {
    errors.push(
      `${path}.convergence_measure must equal maximum_undamped_fixed_point_residual.`,
    );
  }
  if (typeof value.converged !== "boolean") errors.push(`${path}.converged must be a boolean.`);
  if (!isBoundedInteger(value.iterations, 0, 2_000)) {
    errors.push(`${path}.iterations must be an integer from 0 through 2000.`);
  }
  if (!isFiniteNumber(value.final_objective) || value.final_objective < 0) {
    errors.push(`${path}.final_objective must be a finite non-negative number.`);
  }
  if (!isFiniteNumber(value.max_update) || value.max_update < 0) {
    errors.push(`${path}.max_update must be a finite non-negative number.`);
  }
  if (
    !Array.isArray(value.objective_trace)
    || value.objective_trace.length < 1
    || value.objective_trace.length > 2_001
    || !value.objective_trace.every(isFiniteNumber)
  ) {
    errors.push(`${path}.objective_trace must contain 1 through 2001 finite values.`);
  } else if (isDigest(value.trace_digest) && digestValue(value.objective_trace) !== value.trace_digest) {
    errors.push(`${path}.trace_digest does not match the canonical objective trace.`);
  }
  if (!isDigest(value.trace_digest)) errors.push(`${path}.trace_digest must be a lowercase sha256 digest.`);
}

function validateDriver(value: JsonValue, path: string, errors: string[]): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, DRIVER_FIELDS, path, errors);
  if (!isIdentifier(value.driver_id)) errors.push(`${path}.driver_id must be a valid identifier.`);
  if (typeof value.driver_type !== "string" || !DRIVER_TYPES.has(value.driver_type)) {
    errors.push(`${path}.driver_type is invalid.`);
  }
  if (!isFiniteNumber(value.signed_contribution)) {
    errors.push(`${path}.signed_contribution must be finite.`);
  }
  if (!isFiniteNumber(value.strength) || value.strength < 0) {
    errors.push(`${path}.strength must be a finite non-negative number.`);
  }
}

function validateAblation(value: JsonValue, path: string, errors: string[]): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, ABLATION_FIELDS, path, errors);
  if (typeof value.kind !== "string" || !ABLATION_KINDS.has(value.kind)) {
    errors.push(`${path}.kind must be exactly edge_family or modality.`);
  }
  if (!isIdentifier(value.omitted)) errors.push(`${path}.omitted must be a valid identifier.`);
  if (!isFiniteNumber(value.activity_delta)) {
    errors.push(`${path}.activity_delta must be finite.`);
  }
}

function validateKinaseFields(value: JsonObject, path: string, errors: string[]): void {
  const mappedSubstrates = isBoundedInteger(value.mapped_substrates, 0, 256)
    ? value.mapped_substrates
    : null;
  if (mappedSubstrates === null) {
    errors.push(`${path}.mapped_substrates must be an integer from 0 through 256.`);
  }
  if (!isNullableBoundedNumber(value.rank_statistic, -1, 1)) {
    errors.push(`${path}.rank_statistic must be null or a finite number from -1 through 1.`);
  }
  if (value.enrichment_score !== null && !isFiniteNumber(value.enrichment_score)) {
    errors.push(`${path}.enrichment_score must be null or finite.`);
  }
  if (
    value.null_standard_deviation !== null
    && (!isFiniteNumber(value.null_standard_deviation) || value.null_standard_deviation <= 0)
  ) {
    errors.push(`${path}.null_standard_deviation must be null or a finite positive number.`);
  }
  if (!isNullableBoundedNumber(value.p_value, 0, 1)) {
    errors.push(`${path}.p_value must be null or a finite number from 0 through 1.`);
  }
  if (!isNullableBoundedNumber(value.q_value, 0, 1)) {
    errors.push(`${path}.q_value must be null or a finite number from 0 through 1.`);
  }
  const enrichmentFields = [
    value.rank_statistic,
    value.enrichment_score,
    value.null_standard_deviation,
    value.p_value,
    value.q_value,
  ];
  if (mappedSubstrates !== null && mappedSubstrates < 3) {
    if (enrichmentFields.some((field) => field !== null)) {
      errors.push(`${path} kinases with fewer than three mapped substrates must not carry enrichment statistics.`);
    }
  } else if (
    mappedSubstrates !== null
    && enrichmentFields.some((field) => field === null || field === undefined)
  ) {
    errors.push(`${path} kinases with at least three mapped substrates require complete enrichment statistics.`);
  }
}

function validateState(value: JsonValue, path: string, kinase: boolean, errors: string[]): string | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  exactFields(value, kinase ? KINASE_STATE_FIELDS : NODE_STATE_FIELDS, path, errors);
  if (!isIdentifier(value.node_id)) errors.push(`${path}.node_id must be a valid identifier.`);
  if (typeof value.kind !== "string" || !NODE_KINDS.has(value.kind)) {
    errors.push(`${path}.kind is not a recognized graph-node kind.`);
  }
  if (kinase && value.kind !== "kinase") errors.push(`${path}.kind must equal kinase.`);
  if (
    typeof value.classification !== "string"
    || !STATE_CLASSIFICATIONS.has(value.classification)
  ) {
    errors.push(`${path}.classification is invalid.`);
  }
  if (value.support === "supported") {
    errors.push(`${path}.support exceeds the ${ECGI_CLAIM_CEILING} claim ceiling.`);
  } else if (typeof value.support !== "string" || !RESULT_SUPPORT.has(value.support)) {
    errors.push(`${path}.support must be exactly limited or abstained.`);
  }
  for (const field of ["evidence_count", "observed_count", "censored_count"] as const) {
    if (!isBoundedInteger(value[field], 0, 4_096)) {
      errors.push(`${path}.${field} must be an integer from 0 through 4096.`);
    }
  }
  for (const field of ["stability", "discordance"] as const) {
    if (!isNullableBoundedNumber(value[field], 0, 1)) {
      errors.push(`${path}.${field} must be null or a finite number from 0 through 1.`);
    }
  }
  if (!Array.isArray(value.top_drivers) || value.top_drivers.length > 5) {
    errors.push(`${path}.top_drivers must be an array containing at most five entries.`);
  } else {
    value.top_drivers.forEach((driver, index) => {
      validateDriver(driver, `${path}.top_drivers[${index}]`, errors);
    });
  }
  if (!Array.isArray(value.ablation_effects) || value.ablation_effects.length > 16) {
    errors.push(`${path}.ablation_effects must be an array containing at most 16 entries.`);
  } else {
    value.ablation_effects.forEach((ablation, index) => {
      validateAblation(ablation, `${path}.ablation_effects[${index}]`, errors);
    });
  }
  if (value.support === "abstained") {
    if (value.activity !== null || value.lower_bound !== null || value.upper_bound !== null) {
      errors.push(`${path} abstained estimates must be null.`);
    }
    if (value.classification !== "not_estimable") {
      errors.push(`${path} abstained estimates must be classified not_estimable.`);
    }
    if (!isNonEmptyText(value.abstention_reason)) {
      errors.push(`${path} abstention requires a reason.`);
    }
  } else if (value.support === "limited") {
    if (
      !isFiniteNumber(value.activity)
      || !isFiniteNumber(value.lower_bound)
      || !isFiniteNumber(value.upper_bound)
      || value.lower_bound > value.activity
      || value.activity > value.upper_bound
    ) errors.push(`${path} limited estimates require a finite ordered interval.`);
    if (value.classification === "not_estimable") {
      errors.push(`${path} limited estimates cannot be classified not_estimable.`);
    }
    if (value.abstention_reason !== null) errors.push(`${path} limited estimates cannot carry an abstention reason.`);
  }
  if (kinase) validateKinaseFields(value, path, errors);
  return isIdentifier(value.node_id) ? value.node_id : null;
}

function validateIdentifierArray(
  value: JsonValue | undefined,
  path: string,
  maximum: number,
  errors: string[],
): void {
  if (!Array.isArray(value) || value.length > maximum) {
    errors.push(`${path} must be an array containing at most ${maximum} identifiers.`);
    return;
  }
  value.forEach((identifier, index) => {
    if (!isIdentifier(identifier)) errors.push(`${path}[${index}] must be a valid identifier.`);
  });
}

function validateExternalComparison(
  value: JsonValue | undefined,
  path: string,
  errors: string[],
): void {
  if (value === null) return;
  if (!isJsonObject(value)) {
    errors.push(`${path} must be null or an object.`);
    return;
  }
  exactFields(value, EXTERNAL_COMPARISON_FIELDS, path, errors);
  if (!isIdentifier(value.profile_id)) errors.push(`${path}.profile_id must be a valid identifier.`);
  if (!isDigest(value.source_digest)) {
    errors.push(`${path}.source_digest must be a lowercase sha256 digest.`);
  }
  if (!Array.isArray(value.matches) || value.matches.length > 128) {
    errors.push(`${path}.matches must be an array containing at most 128 entries.`);
  } else {
    value.matches.forEach((match, index) => {
      const matchPath = `${path}.matches[${index}]`;
      if (!isJsonObject(match)) {
        errors.push(`${matchPath} must be an object.`);
        return;
      }
      exactFields(match, EXTERNAL_MATCH_FIELDS, matchPath, errors);
      if (!isIdentifier(match.kinase_id)) {
        errors.push(`${matchPath}.kinase_id must be a valid identifier.`);
      }
      for (const field of [
        "local_activity",
        "external_activity",
        "activity_difference",
      ] as const) {
        if (!isFiniteNumber(match[field])) errors.push(`${matchPath}.${field} must be finite.`);
      }
      if (typeof match.interval_overlap !== "boolean") {
        errors.push(`${matchPath}.interval_overlap must be a boolean.`);
      }
      if (typeof match.direction_agreement !== "boolean") {
        errors.push(`${matchPath}.direction_agreement must be a boolean.`);
      }
    });
  }
  validateIdentifierArray(value.unmatched_local_ids, `${path}.unmatched_local_ids`, 128, errors);
  validateIdentifierArray(
    value.external_ids_with_abstained_local_estimates,
    `${path}.external_ids_with_abstained_local_estimates`,
    128,
    errors,
  );
  if (!isNullableBoundedNumber(value.rank_correlation, -1, 1)) {
    errors.push(`${path}.rank_correlation must be null or a finite number from -1 through 1.`);
  }
  if (!isNonEmptyText(value.note)) errors.push(`${path}.note must be non-empty text.`);
}

export function validateEcgiResult(result: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (
    result.algorithm_id !== "glio-ecgi"
    || result.algorithm_version !== "1.0.0"
    || result.profile_id !== ECGI_PROFILE_ID
  ) errors.push("result algorithm identity is invalid.");
  for (const field of ["profile_digest", "request_digest", "result_digest"] as const) {
    if (!isDigest(result[field])) errors.push(`result.${field} must be a lowercase sha256 digest.`);
  }
  if (result.research_use_only !== true || result.non_prescriptive !== true) {
    errors.push("result must remain research-use-only and non-prescriptive.");
  }
  if (!isIdentifier(result.sample_id)) errors.push("result.sample_id must be a valid identifier.");
  if (
    !Array.isArray(result.limitations)
    || result.limitations.length < 1
    || result.limitations.length > 16
    || !result.limitations.every(isNonEmptyText)
  ) {
    errors.push("result.limitations must contain 1 through 16 non-empty text entries.");
  }
  if (!isJsonObject(result.solver)) {
    errors.push("result.solver must be an object.");
  } else {
    exactFields(result.solver, SOLVER_FIELDS, "result.solver", errors);
    validateSolverPass(
      result.solver.first_pass,
      "result.solver.first_pass",
      "evidence_graph",
      errors,
    );
    validateSolverPass(
      result.solver.second_pass,
      "result.solver.second_pass",
      "kinase_feedback",
      errors,
    );
  }
  const identifiers: string[] = [];
  if (!Array.isArray(result.node_states)) errors.push("result.node_states must be an array.");
  else {
    if (result.node_states.length > 256) {
      errors.push("result.node_states must contain at most 256 entries.");
    }
    result.node_states.forEach((state, index) => {
      const identifier = validateState(state, `result.node_states[${index}]`, false, errors);
      if (identifier) identifiers.push(identifier);
    });
  }
  if (!Array.isArray(result.kinase_states)) errors.push("result.kinase_states must be an array.");
  else {
    if (result.kinase_states.length > 128) {
      errors.push("result.kinase_states must contain at most 128 entries.");
    }
    result.kinase_states.forEach((state, index) => {
      const identifier = validateState(state, `result.kinase_states[${index}]`, true, errors);
      if (identifier) identifiers.push(identifier);
    });
  }
  if (new Set(identifiers).size !== identifiers.length) errors.push("result state identifiers must be unique.");
  validateExternalComparison(
    result.external_kinase_comparison,
    "result.external_kinase_comparison",
    errors,
  );
  if (!isJsonObject(result.provenance)) {
    errors.push("result.provenance must be an object.");
  } else {
    exactFields(result.provenance, PROVENANCE_FIELDS, "result.provenance", errors);
    if (result.provenance.engine !== ECGI_PROFILE_ID) errors.push("result.provenance.engine is invalid.");
    if (result.provenance.profile_digest !== result.profile_digest) errors.push("result provenance profile digest does not match result.");
    if (result.provenance.request_digest !== result.request_digest) errors.push("result provenance request digest does not match result.");
    for (const field of ["profile_digest", "request_digest", "computational_digest", "demo_graph_digest"] as const) {
      if (!isDigest(result.provenance[field])) errors.push(`result.provenance.${field} must be a lowercase sha256 digest.`);
    }
  }
  const computed = ecgiResultDigest(result);
  if (computed !== null && isDigest(result.result_digest) && computed !== result.result_digest) {
    errors.push("result.result_digest does not match the canonical result content.");
  }
  return errors;
}

export function validateEcgiResultRequestBinding(result: JsonObject, request: JsonObject): string[] {
  const errors: string[] = [];
  const digest = ecgiRequestDigest(request);
  if (digest === null) errors.push("The executed request cannot be canonically digested.");
  else if (result.request_digest !== digest) errors.push("result.request_digest does not match the executed request.");
  if (result.sample_id !== request.sample_id) errors.push("result.sample_id does not match the executed request.");
  if (isJsonObject(result.provenance)) {
    const expectedTopology = isJsonObject(request.topology_provenance)
      ? canonicalTopology(request.topology_provenance, false)
      : null;
    const actualTopology = isJsonObject(result.provenance.topology)
      ? canonicalTopology(result.provenance.topology, false)
      : result.provenance.topology ?? null;
    if (backendCanonicalJson(actualTopology) !== backendCanonicalJson(expectedTopology)) {
      errors.push("result.provenance.topology does not match the executed request.");
    }
  }
  return errors;
}

export function validateEcgiResultProfileBinding(result: JsonObject, profile: JsonObject): string[] {
  const errors: string[] = [];
  if (result.profile_id !== profile.profile_id) errors.push("result.profile_id does not match the admitted profile.");
  if (result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest does not match the admitted profile.");
  if (isJsonObject(result.provenance) && result.provenance.demo_graph_digest !== profile.demo_graph_digest) {
    errors.push("result.provenance.demo_graph_digest does not match the admitted profile.");
  }
  return errors;
}

export function validateEcgiResultHeaders(headers: HeaderReader, result: JsonObject): string[] {
  const errors: string[] = [];
  validateHeader(headers, "X-GLIO-Profile-Digest", result.profile_digest, errors);
  validateHeader(headers, "X-GLIO-Request-Digest", result.request_digest, errors);
  validateHeader(headers, "X-GLIO-Result-Digest", result.result_digest, errors);
  return errors;
}

export function validateEcgiVerification(
  verification: JsonObject,
  result: JsonObject,
  request: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  exactFields(verification, VERIFICATION_FIELDS, "verification", errors);
  if (typeof verification.verified !== "boolean") errors.push("verification.verified must be a boolean.");
  for (const field of VERIFICATION_FLAGS) {
    if (typeof verification[field] !== "boolean") errors.push(`verification.${field} must be a boolean.`);
  }
  const allChecksPass = VERIFICATION_FLAGS.every((field) => verification[field] === true);
  if (typeof verification.verified === "boolean" && verification.verified !== allChecksPass) {
    errors.push("verification.verified must be true if and only if every replay equality check is true.");
  }
  for (const field of ["provided_result_digest", "recomputed_result_digest", "recomputed_request_digest"] as const) {
    if (!isDigest(verification[field])) errors.push(`verification.${field} must be a lowercase sha256 digest.`);
  }
  if (typeof verification.message !== "string" || !verification.message.trim()) errors.push("verification.message must be non-empty.");
  const requestDigest = ecgiRequestDigest(request);
  if (verification.provided_result_digest !== result.result_digest) {
    errors.push("verification.provided_result_digest does not match the admitted result.");
  }
  if (requestDigest === null || verification.recomputed_request_digest !== requestDigest) {
    errors.push("verification.recomputed_request_digest does not match the executed request.");
  }
  if (verification.verified === true && verification.recomputed_result_digest !== result.result_digest) {
    errors.push("verified replay result digest does not match the admitted result.");
  }
  if (result.profile_digest !== profile.profile_digest) {
    errors.push("the admitted result and profile are not digest-bound.");
  }
  return errors;
}

export function validateEcgiVerificationHeaders(
  headers: HeaderReader,
  verification: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  validateHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  validateHeader(headers, "X-GLIO-Request-Digest", verification.recomputed_request_digest, errors);
  validateHeader(headers, "X-GLIO-Result-Digest", verification.recomputed_result_digest, errors);
  return errors;
}
