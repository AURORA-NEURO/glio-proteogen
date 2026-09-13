import {
  arrayAt,
  isJsonObject,
  objectAt,
  type JsonObject,
} from "./research-state";
import {
  ecgiRequestDigest,
  validateEcgiResult,
  validateEcgiResultRequestBinding,
} from "./evidence-graph-admission";
import {
  neftelRequestStats,
  normalizeNeftelPrograms,
  validateNeftelRequest,
} from "./neftel-programs";
import { normalizeGbmSignatures, validateGbmRequest } from "./gbm-proteomic-axes";

export const GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID =
  "gbm-microenvironment-graph/1.0.0";
export const GBM_MICROENVIRONMENT_GRAPH_API_BASE =
  "/backend/v1/research/gbm-microenvironment-graph";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const PROFILE_FIELDS = new Set([
  "profile_id",
  "algorithm_id",
  "algorithm_version",
  "source_engine",
  "graph_engine",
  "auxiliary_source_engine",
  "source_profile_digest",
  "graph_profile_digest",
  "topology_digest",
  "projection_policy",
  "auxiliary_projection_policy",
  "projected_axis_signatures",
  "auxiliary_standard_error_floor",
  "source_location_standard_error_floor",
  "source_rank_standard_error_floor",
  "source_location_quality_supported",
  "source_location_quality_limited",
  "source_rank_quality_supported",
  "source_rank_quality_limited",
  "supported_source_families",
  "missing_families_are_not_negative",
  "cell_fraction_claim_permitted",
  "clinical_use_permitted",
  "profile_digest",
]);
const REQUEST_FIELDS = new Set(["profile_id", "sample_id", "source_request"]);
const REQUEST_OPTIONAL_FIELDS = new Set(["axis_request"]);
const RESULT_FIELDS = new Set([
  "profile_id",
  "profile_digest",
  "request_digest",
  "result_digest",
  "sample_id",
  "source_result",
  "graph_request",
  "graph_result",
  "limitations",
  "research_use_only",
  "non_prescriptive",
]);
const RESULT_OPTIONAL_FIELDS = new Set(["axis_result"]);
const REPLAY_FIELDS = new Set([
  "verified",
  "request_digest_match",
  "source_replay_match",
  "axis_replay_match",
  "graph_replay_match",
  "result_digest_match",
  "semantic_match",
  "recomputed_request_digest",
  "recomputed_result_digest",
  "message",
]);
export type HeaderReader = { get(name: string): string | null };

function exactFields(
  source: JsonObject,
  expected: ReadonlySet<string>,
  path: string,
  errors: string[],
  optional: ReadonlySet<string> = new Set(),
): void {
  const missing = [...expected].filter((field) => !Object.prototype.hasOwnProperty.call(source, field));
  const unknown = Object.keys(source).filter((field) => !expected.has(field) && !optional.has(field));
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function requireDigest(value: unknown, path: string, errors: string[]): void {
  if (typeof value !== "string" || !DIGEST.test(value)) errors.push(`${path} must be a lowercase sha256 digest.`);
}

function requireText(value: unknown, path: string, errors: string[]): void {
  if (typeof value !== "string" || value.trim() === "") errors.push(`${path} must be non-empty text.`);
}

function nestedSourceRequest(request: JsonObject): JsonObject | null {
  return isJsonObject(request.source_request) ? request.source_request : null;
}

function nestedAxisRequest(request: JsonObject): JsonObject | null {
  return isJsonObject(request.axis_request) ? request.axis_request : null;
}

export type MicroenvironmentGraphRequestStats = {
  observations: number;
  active: number;
  programs: number;
};

const GRAPH_PROGRAM_COUNT = 14;
const PROJECTED_SOURCE_FAMILIES = [
  "mesenchymal_like",
  "oligodendrocyte_progenitor_like",
  "neural_progenitor_like",
  "astrocyte_like",
  "cell_cycle",
] as const;
const PROJECTED_SOURCE_FAMILY_SET = new Set<string>(PROJECTED_SOURCE_FAMILIES);

export function microenvironmentGraphRequestStats(request: JsonObject): MicroenvironmentGraphRequestStats {
  const source = nestedSourceRequest(request);
  if (!source) return { observations: 0, active: 0, programs: GRAPH_PROGRAM_COUNT };
  const stats = neftelRequestStats(source);
  return { observations: stats.observations, active: stats.active, programs: GRAPH_PROGRAM_COUNT };
}

export function validateMicroenvironmentGraphProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (
    profile.profile_id !== GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID
    || profile.algorithm_id !== "gbm-microenvironment-graph"
    || profile.algorithm_version !== "1.0.0"
  ) errors.push("profile algorithm identity is invalid.");
  if (profile.source_engine !== "neftel-bulk-protein-programs/1.0.0") errors.push("profile.source_engine is invalid.");
  if (profile.graph_engine !== "glio-ecgi/1.0.0") errors.push("profile.graph_engine is invalid.");
  if (profile.auxiliary_source_engine !== "gbm-proteomic-axes/1.0.0") errors.push("profile.auxiliary_source_engine is invalid.");
  if (profile.projection_policy !== "bulk_program_location_and_rank_to_signed_gbm_state_graph_v3") errors.push("profile.projection_policy is invalid.");
  if (profile.auxiliary_projection_policy !== "independent_published_gbm_axes_as_external_observations_v2") errors.push("profile.auxiliary_projection_policy is invalid.");
  const expectedAxisMappings = [
    ["SWEET_KRAS_TARGETS_UP", "kras_targets"],
    ["HALLMARK_MYC_TARGETS_V1", "myc_targets"],
    ["WINTER_HYPOXIA_UP", "hypoxia"],
    ["VERHAAK_GLIOBLASTOMA_MESENCHYMAL", "mesenchymal"],
    ["VERHAAK_GLIOBLASTOMA_NEURAL", "neural"],
    ["VERHAAK_GLIOBLASTOMA_PRONEURAL", "proneural"],
    ["EGFR_UP.V1_UP", "egfr_targets"],
  ];
  if (JSON.stringify(profile.projected_axis_signatures) !== JSON.stringify(expectedAxisMappings)) errors.push("profile.projected_axis_signatures must preserve the seven published GBM axis mappings.");
  if (profile.auxiliary_standard_error_floor !== 0.35) errors.push("profile.auxiliary_standard_error_floor must equal 0.35.");
  if (profile.source_location_standard_error_floor !== 0.05) errors.push("profile.source_location_standard_error_floor must equal 0.05.");
  if (profile.source_rank_standard_error_floor !== 0.10) errors.push("profile.source_rank_standard_error_floor must equal 0.10.");
  if (profile.source_location_quality_supported !== 1.0 || profile.source_location_quality_limited !== 0.5) errors.push("profile source location quality weights are invalid.");
  if (profile.source_rank_quality_supported !== 0.85 || profile.source_rank_quality_limited !== 0.40) errors.push("profile source rank quality weights are invalid.");
  if (!Array.isArray(profile.supported_source_families) || JSON.stringify(profile.supported_source_families) !== JSON.stringify(PROJECTED_SOURCE_FAMILIES)) {
    errors.push("profile.supported_source_families must contain the five supported GBM families in profile order.");
  }
  if (profile.missing_families_are_not_negative !== true || profile.cell_fraction_claim_permitted !== false || profile.clinical_use_permitted !== false) {
    errors.push("profile must preserve missingness and forbid cell-fraction and clinical claims.");
  }
  for (const field of ["source_profile_digest", "graph_profile_digest", "topology_digest", "profile_digest"]) requireDigest(profile[field], `profile.${field}`, errors);
  return errors;
}

export function validateMicroenvironmentGraphRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(request, REQUEST_FIELDS, "request", errors, REQUEST_OPTIONAL_FIELDS);
  if (request.profile_id !== GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID) errors.push(`request.profile_id must equal ${GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID}.`);
  if (typeof request.sample_id !== "string" || request.sample_id.trim() === "") errors.push("request.sample_id must be non-empty text.");
  const source = nestedSourceRequest(request);
  if (!source) {
    errors.push("request.source_request must be an object.");
  } else {
    errors.push(...validateNeftelRequest(source).map((error) => `request.source_request: ${error}`));
    if (source.sample_id !== request.sample_id) errors.push("request.sample_id must match request.source_request.sample_id.");
  }
  const axis = nestedAxisRequest(request);
  if (request.axis_request !== undefined && request.axis_request !== null && !axis) errors.push("request.axis_request must be an object when supplied.");
  if (axis) {
    errors.push(...validateGbmRequest(axis).map((error) => `request.axis_request: ${error}`));
    if (axis.sample_id !== request.sample_id) errors.push("request.sample_id must match request.axis_request.sample_id.");
  }
  return errors;
}

export function validateMicroenvironmentGraphDemo(
  request: JsonObject,
  profile: JsonObject | null,
): string[] {
  const errors = validateMicroenvironmentGraphRequest(request);
  if (profile && request.profile_id !== profile.profile_id) errors.push("demo.profile_id does not match the admitted bridge profile.");
  if (profile) requireDigest(profile.profile_digest, "profile.profile_digest", errors);
  return errors;
}

export function validateMicroenvironmentGraphResult(
  result: JsonObject,
  request?: JsonObject,
  profile?: JsonObject | null,
): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors, RESULT_OPTIONAL_FIELDS);
  if (result.profile_id !== GBM_MICROENVIRONMENT_GRAPH_PROFILE_ID) errors.push("result.profile_id is invalid.");
  for (const field of ["profile_digest", "request_digest", "result_digest"]) requireDigest(result[field], `result.${field}`, errors);
  if (typeof result.sample_id !== "string" || result.sample_id.trim() === "") errors.push("result.sample_id must be non-empty text.");
  if (!Array.isArray(result.limitations) || result.limitations.length < 1 || !result.limitations.every((item) => typeof item === "string" && item.trim() !== "")) errors.push("result.limitations must contain non-empty text entries.");
  if (result.research_use_only !== true || result.non_prescriptive !== true) errors.push("result must remain research-use-only and non-prescriptive.");
  if (profile && result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest does not match the admitted bridge profile.");
  const graphRequest = isJsonObject(result.graph_request) ? result.graph_request : null;
  const graphResult = isJsonObject(result.graph_result) ? result.graph_result : null;
  const axisResult = isJsonObject(result.axis_result) ? result.axis_result : null;
  if (!graphRequest) errors.push("result.graph_request must be an object.");
  if (!graphResult) errors.push("result.graph_result must be an object.");
  if (result.axis_result !== undefined && result.axis_result !== null && !axisResult) errors.push("result.axis_result must be an object when supplied.");
  if (graphRequest) errors.push(...validateEcgiResultRequestBinding(graphResult ?? {}, graphRequest));
  if (graphResult) {
    errors.push(...validateEcgiResult(graphResult).map((error) => `result.graph_result: ${error}`));
    if (profile && graphResult.profile_digest !== profile.graph_profile_digest) {
      errors.push("result.graph_result.profile_digest does not match profile.graph_profile_digest.");
    }
  }
  if (axisResult) {
    if (axisResult.profile_id !== "gbm-proteomic-axes/1.0.0") errors.push("result.axis_result.profile_id is invalid.");
    for (const field of ["profile_digest", "request_digest", "result_digest"]) requireDigest(axisResult[field], `result.axis_result.${field}`, errors);
    if (typeof axisResult.sample_id !== "string" || axisResult.sample_id !== result.sample_id) errors.push("result.axis_result.sample_id does not match the bridge sample.");
    if (!Array.isArray(axisResult.signatures) || axisResult.signatures.length < 1) errors.push("result.axis_result.signatures must be a non-empty array.");
  }
  if (request) {
    if (result.sample_id !== request.sample_id) errors.push("result.sample_id does not match the executed request.");
  }
  return errors;
}

export function validateMicroenvironmentGraphResultHeaders(
  headers: HeaderReader,
  result: JsonObject,
): string[] {
  const errors: string[] = [];
  for (const [name, value] of [["X-GLIO-Profile-Digest", result.profile_digest], ["X-GLIO-Request-Digest", result.request_digest], ["X-GLIO-Result-Digest", result.result_digest]] as const) {
    if (headers.get(name) !== value) errors.push(`${name} response header does not match the bridge receipt.`);
  }
  return errors;
}

export function validateMicroenvironmentGraphVerification(
  verification: JsonObject,
  result: JsonObject,
  request: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  exactFields(verification, REPLAY_FIELDS, "verification", errors);
  if (typeof verification.verified !== "boolean") errors.push("verification.verified must be a boolean.");
  for (const field of ["request_digest_match", "source_replay_match", "graph_replay_match", "result_digest_match", "semantic_match"] as const) {
    if (typeof verification[field] !== "boolean") errors.push(`verification.${field} must be a boolean.`);
  }
  if (typeof verification.axis_replay_match !== "boolean") errors.push("verification.axis_replay_match must be a boolean.");
  for (const field of ["recomputed_request_digest", "recomputed_result_digest"]) requireDigest(verification[field], `verification.${field}`, errors);
  requireText(verification.message, "verification.message", errors);
  if (verification.verified === true && ["request_digest_match", "source_replay_match", "axis_replay_match", "graph_replay_match", "result_digest_match", "semantic_match"].some((field) => verification[field] !== true)) errors.push("verification.verified requires every replay check to pass.");
  if (result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest does not match the admitted bridge profile.");
  if (result.sample_id !== request.sample_id) errors.push("result.sample_id does not match the executed request.");
  return errors;
}

export function normalizeMicroenvironmentGraphResult(result: JsonObject): {
  graphResult: JsonObject | null;
  graphRequest: JsonObject | null;
  sourceResult: JsonObject | null;
  axisResult: JsonObject | null;
  sourcePrograms: ReturnType<typeof normalizeNeftelPrograms>;
  axisSignatures: ReturnType<typeof normalizeGbmSignatures>;
} {
  const graphResult = objectAt(result, ["graph_result"]);
  const graphRequest = objectAt(result, ["graph_request"]);
  const sourceResult = objectAt(result, ["source_result"]);
  const axisResult = objectAt(result, ["axis_result"]);
  return {
    graphResult,
    graphRequest,
    sourceResult,
    axisResult,
    sourcePrograms: sourceResult ? normalizeNeftelPrograms(sourceResult) : [],
    axisSignatures: axisResult ? normalizeGbmSignatures(axisResult) : [],
  };
}

export function microenvironmentStateCount(result: JsonObject | null): number {
  return result ? arrayAt(result, ["node_states"]).filter(isJsonObject).length : 0;
}

export function microenvironmentSupportedFamilyCount(result: JsonObject | null): number {
  if (!result) return 0;
  return normalizeNeftelPrograms(result).filter(
    (program) => PROJECTED_SOURCE_FAMILY_SET.has(program.id) && program.support !== "abstained",
  ).length;
}

export function microenvironmentGraphRequestDigest(request: JsonObject): string | null {
  return isJsonObject(request.graph_request) ? ecgiRequestDigest(request.graph_request) : null;
}
