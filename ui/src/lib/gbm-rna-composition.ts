import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
} from "./research-state";

export const GBM_RNA_COMPOSITION_PROFILE_ID = "gbm-rna-composition/0.1.0";
export const GBM_RNA_COMPOSITION_API_BASE = "/backend/v1/research/gbm-rna-composition";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const PROFILE_FIELDS = new Set([
  "profile_id", "algorithm_id", "algorithm_version", "numpy_version", "execution_scope",
  "output_semantics", "histologic_fraction_claim_permitted", "clinical_use_permitted",
  "solver", "max_features", "max_lineages", "max_iterations", "kkt_tolerance",
  "l1_step_tolerance", "relative_objective_tolerance", "profile_digest",
]);
const REQUEST_FIELDS = new Set([
  "profile_id", "sample_id", "feature_ids", "counts", "references", "unknown_background",
  "concentration", "lambda_mass", "lambda_shape", "initial_unknown_mass", "max_iterations",
  "source_digests", "provenance_note",
]);
const RESULT_FIELDS = new Set([
  "result_id", "profile_id", "profile_digest", "request_digest", "result_digest", "sample_id",
  "feature_ids", "support", "known_weights", "unknown_gene_mass", "fitted_probabilities",
  "unknown_mass", "objective", "initial_objective", "iterations", "kkt_residual",
  "signature_condition_number", "objective_trace", "trace_digest", "ood", "abstention_reason",
  "source_digests", "limitations",
]);
const REPLAY_FIELDS = new Set(["verified", "request_digest", "result_digest"]);

export type HeaderReader = { get(name: string): string | null };

function exactFields(source: JsonObject, expected: ReadonlySet<string>, path: string, errors: string[]): void {
  const missing = [...expected].filter((field) => !Object.prototype.hasOwnProperty.call(source, field));
  const unknown = Object.keys(source).filter((field) => !expected.has(field));
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function digest(value: unknown, path: string, errors: string[]): void {
  if (typeof value !== "string" || !DIGEST.test(value)) errors.push(`${path} must be a lowercase sha256 digest.`);
}

function identifier(value: unknown, path: string, errors: string[]): void {
  if (typeof value !== "string" || !IDENTIFIER.test(value)) errors.push(`${path} must be a valid identifier.`);
}

function finite(value: unknown, path: string, errors: string[], minimum?: number): void {
  if (typeof value !== "number" || !Number.isFinite(value) || (minimum !== undefined && value < minimum)) {
    errors.push(`${path} must be finite${minimum === undefined ? "" : ` and >= ${minimum}`}.`);
  }
}

function uniqueStrings(values: unknown[], path: string, errors: string[]): void {
  const strings = values.filter((value): value is string => typeof value === "string");
  if (new Set(strings).size !== strings.length) errors.push(`${path} must contain unique identifiers.`);
}

function numericSum(values: unknown[]): number {
  return values.reduce<number>((sum, value) => sum + (typeof value === "number" && Number.isFinite(value) ? value : 0), 0);
}

export function validateGbmMixtureProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (profile.profile_id !== GBM_RNA_COMPOSITION_PROFILE_ID || profile.algorithm_id !== "gbm-rna-composition" || profile.algorithm_version !== "0.1.0") errors.push("profile algorithm identity is invalid.");
  if (profile.numpy_version !== "2.5.2" || profile.execution_scope !== "caller_supplied_reference_only" || profile.output_semantics !== "rna_mixture_weights_with_unknown_mass") errors.push("profile must bind NumPy 2.5.2 and caller-supplied RNA mixture semantics.");
  if (profile.histologic_fraction_claim_permitted !== false || profile.clinical_use_permitted !== false) errors.push("profile must forbid histologic-fraction and clinical claims.");
  if (profile.solver !== "dirichlet_multinomial_adaptive_unknown_simplex" || profile.max_features !== 512 || profile.max_lineages !== 32 || profile.max_iterations !== 500) errors.push("profile solver or limits are invalid.");
  for (const field of ["kkt_tolerance", "l1_step_tolerance", "relative_objective_tolerance"]) finite(profile[field], `profile.${field}`, errors, 0);
  digest(profile.profile_digest, "profile.profile_digest", errors);
  return errors;
}

export function validateGbmMixtureRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(request, REQUEST_FIELDS, "request", errors);
  if (request.profile_id !== GBM_RNA_COMPOSITION_PROFILE_ID) errors.push(`request.profile_id must equal ${GBM_RNA_COMPOSITION_PROFILE_ID}.`);
  identifier(request.sample_id, "request.sample_id", errors);
  const features = arrayAt(request, ["feature_ids"]);
  const counts = arrayAt(request, ["counts"]);
  const background = arrayAt(request, ["unknown_background"]);
  if (features.length < 2 || features.length > 512) errors.push("request.feature_ids must contain 2-512 features.");
  if (counts.length !== features.length) errors.push("request.counts must share the feature axis.");
  if (background.length !== features.length) errors.push("request.unknown_background must share the feature axis.");
  features.forEach((value, index) => identifier(value, `request.feature_ids[${index}]`, errors));
  uniqueStrings(features, "request.feature_ids", errors);
  counts.forEach((value, index) => {
    if (!Number.isInteger(value) || typeof value !== "number" || value < 0) errors.push(`request.counts[${index}] must be a non-negative integer.`);
  });
  if (numericSum(counts) <= 0) errors.push("request.counts must have positive depth.");
  background.forEach((value, index) => {
    finite(value, `request.unknown_background[${index}]`, errors, 0);
    if (typeof value === "number" && value <= 0) errors.push(`request.unknown_background[${index}] must be strictly positive.`);
  });
  if (background.length && Math.abs(numericSum(background) - 1) > 1e-10) errors.push("request.unknown_background must sum to one.");
  const references = arrayAt(request, ["references"]);
  if (references.length < 1 || references.length > 32) errors.push("request.references must contain 1-32 lineage signatures.");
  const referenceIds: unknown[] = [];
  references.forEach((value, index) => {
    if (!isJsonObject(value)) { errors.push(`request.references[${index}] must be an object.`); return; }
    referenceIds.push(value.reference_id);
    identifier(value.reference_id, `request.references[${index}].reference_id`, errors);
    const signature = arrayAt(value, ["signature"]);
    if (signature.length !== features.length) errors.push(`request.references[${index}].signature must share the feature axis.`);
    signature.forEach((item, itemIndex) => {
      finite(item, `request.references[${index}].signature[${itemIndex}]`, errors, 0);
      if (typeof item === "number" && item <= 0) errors.push(`request.references[${index}].signature[${itemIndex}] must be strictly positive.`);
    });
    if (signature.length && Math.abs(numericSum(signature) - 1) > 1e-10) errors.push(`request.references[${index}].signature must sum to one.`);
  });
  uniqueStrings(referenceIds, "request.references.reference_id", errors);
  for (const field of ["concentration", "lambda_mass", "lambda_shape", "initial_unknown_mass"]) finite(request[field], `request.${field}`, errors, 0);
  if (typeof request.concentration === "number" && request.concentration <= 0) errors.push("request.concentration must be strictly positive.");
  if (typeof request.initial_unknown_mass === "number" && request.initial_unknown_mass >= 1) errors.push("request.initial_unknown_mass must be below one.");
  if (!Number.isInteger(request.max_iterations) || typeof request.max_iterations !== "number" || request.max_iterations < 1 || request.max_iterations > 500) errors.push("request.max_iterations must be an integer from 1 to 500.");
  const sources = arrayAt(request, ["source_digests"]);
  if (sources.length < 1 || sources.length > 32 || sources.some((value) => typeof value !== "string" || !DIGEST.test(value))) errors.push("request.source_digests must contain lowercase sha256 digests.");
  if (typeof request.provenance_note !== "string" || request.provenance_note.trim() === "") errors.push("request.provenance_note must be non-empty text.");
  return errors;
}

export function validateGbmMixtureDemo(request: JsonObject, profile: JsonObject | null, headers?: HeaderReader): string[] {
  const errors = validateGbmMixtureRequest(request);
  if (profile && request.profile_id !== profile.profile_id) errors.push("demo.profile_id does not match the admitted mixture profile.");
  if (headers && !DIGEST.test(headers.get("X-GLIO-Request-Digest") ?? "")) errors.push("demo response must expose a canonical request digest header.");
  return errors;
}

export function validateGbmMixtureResult(result: JsonObject, request: JsonObject | null, profile: JsonObject | null): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (result.profile_id !== GBM_RNA_COMPOSITION_PROFILE_ID) errors.push("result.profile_id is invalid.");
  for (const field of ["profile_digest", "request_digest", "result_digest", "trace_digest"]) digest(result[field], `result.${field}`, errors);
  identifier(result.result_id, "result.result_id", errors);
  identifier(result.sample_id, "result.sample_id", errors);
  if (!["limited", "abstained"].includes(textAt(result, ["support"]))) errors.push("result.support must be limited or abstained.");
  if (!Array.isArray(result.limitations) || result.limitations.length < 1) errors.push("result.limitations must be non-empty.");
  if (profile && result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest does not match the admitted profile.");
  if (request && result.sample_id !== request.sample_id) errors.push("result.sample_id does not match the executed request.");
  const features = arrayAt(result, ["feature_ids"]);
  const weights = arrayAt(result, ["known_weights"]);
  if (result.support === "limited") {
    if (!weights.length) errors.push("limited result must carry known lineage weights.");
    if (features.length !== arrayAt(result, ["unknown_gene_mass"]).length || features.length !== arrayAt(result, ["fitted_probabilities"]).length) errors.push("limited composition vectors must share one feature axis.");
    finite(result.unknown_mass, "result.unknown_mass", errors, 0);
    if (typeof result.unknown_mass === "number" && result.unknown_mass > 1) errors.push("result.unknown_mass must be <= 1.");
  }
  return errors;
}

export function validateGbmMixtureResultHeaders(headers: HeaderReader, result: JsonObject): string[] {
  const errors: string[] = [];
  for (const [name, field] of [["X-GLIO-Profile-Digest", "profile_digest"], ["X-GLIO-Request-Digest", "request_digest"], ["X-GLIO-Result-Digest", "result_digest"]] as const) {
    if (headers.get(name) !== result[field]) errors.push(`${name} response header does not match the mixture receipt.`);
  }
  return errors;
}

export function validateGbmMixtureVerification(verification: JsonObject, result: JsonObject, request: JsonObject, profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(verification, REPLAY_FIELDS, "verification", errors);
  if (verification.verified !== true) errors.push("verification.verified must be true.");
  if (verification.request_digest !== result.request_digest || verification.result_digest !== result.result_digest) errors.push("verification digests do not match the result receipt.");
  if (result.profile_digest !== profile.profile_digest || request.profile_id !== profile.profile_id) errors.push("verification profile binding is invalid.");
  return errors;
}

export function gbmRnaCompositionRequestStats(request: JsonObject): { features: number; nonzero: number; references: number; depth: number } {
  const counts = arrayAt(request, ["counts"]);
  return { features: arrayAt(request, ["feature_ids"]).length, nonzero: counts.filter((value) => typeof value === "number" && value > 0).length, references: arrayAt(request, ["references"]).length, depth: numericSum(counts) };
}

export type GbmMixtureWeight = { id: string; weight: number | null; rank: number | null };
export type GbmMixtureEvidence = {
  support: string;
  weights: GbmMixtureWeight[];
  unknownMass: number | null;
  objective: number | null;
  initialObjective: number | null;
  iterations: number | null;
  kktResidual: number | null;
  conditionNumber: number | null;
  trace: number[];
  ood: JsonObject | null;
  abstentionReason: string | null;
  unknownGeneMass: number[];
  fittedProbabilities: number[];
};

export function normalizeGbmMixtureResult(result: JsonObject): GbmMixtureEvidence {
  return {
    support: textAt(result, ["support"], "abstained"),
    weights: arrayAt(result, ["known_weights"]).flatMap((value) => isJsonObject(value) ? [{ id: textAt(value, ["reference_id"], "unknown"), weight: numberAt(value, ["rna_weight"]), rank: numberAt(value, ["rank"]) }] : []),
    unknownMass: numberAt(result, ["unknown_mass"]),
    objective: numberAt(result, ["objective"]),
    initialObjective: numberAt(result, ["initial_objective"]),
    iterations: numberAt(result, ["iterations"]),
    kktResidual: numberAt(result, ["kkt_residual"]),
    conditionNumber: numberAt(result, ["signature_condition_number"]),
    trace: arrayAt(result, ["objective_trace"]).filter((value): value is number => typeof value === "number"),
    ood: objectAt(result, ["ood"]),
    abstentionReason: textAt(result, ["abstention_reason"], "") || null,
    unknownGeneMass: arrayAt(result, ["unknown_gene_mass"]).filter((value): value is number => typeof value === "number"),
    fittedProbabilities: arrayAt(result, ["fitted_probabilities"]).filter((value): value is number => typeof value === "number"),
  };
}

export function mixtureProvenance(result: JsonObject): JsonObject | null {
  return objectAt(result, ["provenance"]);
}
