import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
} from "./research-state";

export const IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID =
  "glioma-immunopeptidomic-presentation/0.1.0";
export const IMMUNOPEPTIDOMIC_PRESENTATION_API_BASE =
  "/backend/v1/research/immunopeptidomic-presentation";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const HLA = /^HLA-[A-Z0-9]+\*[0-9]{2,3}:[0-9]{2,3}$/;
const AMINO_ACIDS = /^[ACDEFGHIKLMNPQRSTVWY]+$/;
const PROFILE_FIELDS = new Set([
  "profile_id",
  "algorithm_id",
  "algorithm_version",
  "numpy_version",
  "execution_scope",
  "score_model",
  "max_peptides",
  "max_alleles",
  "default_bootstrap_replicates",
  "clinical_use_permitted",
  "treatment_recommendation_permitted",
  "profile_digest",
]);
const REQUEST_FIELDS = new Set([
  "profile_id",
  "sample_id",
  "hla_alleles",
  "peptides",
  "models",
  "bootstrap_replicates",
  "source_digests",
  "provenance_note",
]);
const RESULT_FIELDS = new Set([
  "result_id",
  "profile_id",
  "profile_digest",
  "request_digest",
  "result_digest",
  "sample_id",
  "support",
  "candidates",
  "supported_peptide_count",
  "supported_allele_count",
  "model_digests",
  "bootstrap_replicates",
  "abstention_reason",
  "limitations",
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

function nonEmpty(value: unknown, path: string, errors: string[]): void {
  if (typeof value !== "string" || value.trim() === "") errors.push(`${path} must be non-empty text.`);
}

function validatePeptides(request: JsonObject, errors: string[]): void {
  const peptides = arrayAt(request, ["peptides"]);
  if (peptides.length < 1 || peptides.length > 256) {
    errors.push("request.peptides must contain 1-256 peptide observations.");
    return;
  }
  const ids = new Set<string>();
  peptides.forEach((value, index) => {
    if (!isJsonObject(value)) {
      errors.push(`request.peptides[${index}] must be an object.`);
      return;
    }
    const id = textAt(value, ["peptide_id"]);
    if (!id || ids.has(id)) errors.push(`request.peptides[${index}].peptide_id must be unique non-empty text.`);
    if (id) ids.add(id);
    const sequence = textAt(value, ["sequence"]);
    if (!sequence || sequence.length < 8 || sequence.length > 14 || sequence !== sequence.toUpperCase() || !AMINO_ACIDS.test(sequence)) {
      errors.push(`request.peptides[${index}].sequence must be uppercase amino acids of length 8-14.`);
    }
    nonEmpty(value.source_gene, `request.peptides[${index}].source_gene`, errors);
    const state = textAt(value, ["state"], "observed");
    if (!["observed", "left_censored", "missing", "unsupported"].includes(state)) errors.push(`request.peptides[${index}].state is invalid.`);
    if (state === "observed" && value.detection_limit !== undefined && value.detection_limit !== null) errors.push(`request.peptides[${index}] observed evidence cannot carry detection_limit.`);
    if (state === "left_censored" && (typeof value.detection_limit !== "number" || value.expression_effect !== undefined && value.expression_effect !== null)) errors.push(`request.peptides[${index}] left_censored evidence requires only detection_limit.`);
    if (["missing", "unsupported"].includes(state) && ["expression_effect", "expression_standard_error", "detection_limit"].some((field) => value[field] !== undefined && value[field] !== null)) errors.push(`request.peptides[${index}] ${state} evidence cannot carry numeric values.`);
  });
}

export function validatePresentationProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (profile.profile_id !== IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID || profile.algorithm_id !== "glioma-immunopeptidomic-presentation" || profile.algorithm_version !== "0.1.0") errors.push("profile algorithm identity is invalid.");
  if (profile.numpy_version !== "2.5.2" || profile.execution_scope !== "caller_supplied_hla_model_only" || profile.score_model !== "allele_pssm_processing_logit") errors.push("profile must bind the caller-supplied PSSM/logit model and NumPy 2.5.2.");
  if (profile.max_peptides !== 256 || profile.max_alleles !== 16 || profile.default_bootstrap_replicates !== 64) errors.push("profile limits or bootstrap default are invalid.");
  if (profile.clinical_use_permitted !== false || profile.treatment_recommendation_permitted !== false) errors.push("profile must forbid clinical and treatment recommendations.");
  digest(profile.profile_digest, "profile.profile_digest", errors);
  return errors;
}

export function validatePresentationRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(request, REQUEST_FIELDS, "request", errors);
  if (request.profile_id !== IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID) errors.push(`request.profile_id must equal ${IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID}.`);
  nonEmpty(request.sample_id, "request.sample_id", errors);
  const alleles = arrayAt(request, ["hla_alleles"]);
  if (alleles.length < 1 || alleles.length > 16 || alleles.some((allele) => typeof allele !== "string" || !HLA.test(allele))) errors.push("request.hla_alleles must contain 1-16 canonical HLA alleles.");
  if (new Set(alleles.filter((allele): allele is string => typeof allele === "string")).size !== alleles.length) errors.push("request.hla_alleles must be unique.");
  validatePeptides(request, errors);
  const models = arrayAt(request, ["models"]);
  if (models.length < 1 || models.length > 16) errors.push("request.models must contain 1-16 caller-supplied models.");
  const modelAlleles = models.flatMap((model) => isJsonObject(model) ? [textAt(model, ["allele"])] : [null]);
  if (modelAlleles.some((allele) => !allele || !HLA.test(allele))) errors.push("request.models must bind canonical HLA alleles.");
  if (new Set(modelAlleles.filter((allele): allele is string => allele !== null)).size !== modelAlleles.length) errors.push("request.models must contain one model per allele.");
  if (modelAlleles.some((allele) => allele !== null && !alleles.includes(allele))) errors.push("request.models cannot include an unrequested allele.");
  const sourceDigests = arrayAt(request, ["source_digests"]);
  if (sourceDigests.length < 1 || sourceDigests.some((value) => typeof value !== "string" || !DIGEST.test(value))) errors.push("request.source_digests must contain lowercase sha256 digests.");
  nonEmpty(request.provenance_note, "request.provenance_note", errors);
  const replicates = numberAt(request, ["bootstrap_replicates"]);
  if (replicates !== null && (!Number.isInteger(replicates) || replicates < 0 || replicates > 256)) errors.push("request.bootstrap_replicates must be an integer from 0 to 256.");
  return errors;
}

export function validatePresentationDemo(request: JsonObject, profile: JsonObject | null): string[] {
  const errors = validatePresentationRequest(request);
  if (profile && request.profile_id !== profile.profile_id) errors.push("demo.profile_id does not match the admitted presentation profile.");
  return errors;
}

export function validatePresentationResult(result: JsonObject, request: JsonObject | null, profile: JsonObject | null): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (result.profile_id !== IMMUNOPEPTIDOMIC_PRESENTATION_PROFILE_ID) errors.push("result.profile_id is invalid.");
  for (const field of ["profile_digest", "request_digest", "result_digest"]) digest(result[field], `result.${field}`, errors);
  nonEmpty(result.sample_id, "result.sample_id", errors);
  if (!["supported", "limited", "abstained"].includes(textAt(result, ["support"]))) errors.push("result.support is invalid.");
  if (!Array.isArray(result.candidates)) errors.push("result.candidates must be an array.");
  if (!Array.isArray(result.limitations) || result.limitations.length < 1) errors.push("result.limitations must be non-empty.");
  if (profile && result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest does not match the admitted profile.");
  if (request && result.sample_id !== request.sample_id) errors.push("result.sample_id does not match the executed request.");
  return errors;
}

export function validatePresentationResultHeaders(headers: HeaderReader, result: JsonObject): string[] {
  const errors: string[] = [];
  for (const [name, field] of [["X-GLIO-Profile-Digest", "profile_digest"], ["X-GLIO-Request-Digest", "request_digest"], ["X-GLIO-Result-Digest", "result_digest"]] as const) {
    if (headers.get(name) !== result[field]) errors.push(`${name} response header does not match the presentation receipt.`);
  }
  return errors;
}

export function validatePresentationVerification(verification: JsonObject, result: JsonObject, request: JsonObject, profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(verification, REPLAY_FIELDS, "verification", errors);
  if (verification.verified !== true) errors.push("verification.verified must be true.");
  if (verification.request_digest !== request.request_digest && verification.request_digest !== result.request_digest) errors.push("verification.request_digest does not match the request receipt.");
  if (verification.result_digest !== result.result_digest) errors.push("verification.result_digest does not match the result receipt.");
  if (result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest does not match the admitted profile.");
  return errors;
}

export function presentationRequestStats(request: JsonObject): { peptides: number; informative: number; alleles: number; models: number } {
  const peptides = arrayAt(request, ["peptides"]);
  return {
    peptides: peptides.length,
    informative: peptides.filter((value) => isJsonObject(value) && ["observed", "left_censored"].includes(textAt(value, ["state"], "observed"))).length,
    alleles: arrayAt(request, ["hla_alleles"]).length,
    models: arrayAt(request, ["models"]).length,
  };
}

export type PresentationCandidate = {
  id: string;
  sequence: string;
  gene: string;
  support: string;
  probability: number | null;
  low: number | null;
  high: number | null;
  rank: number | null;
  alleles: number;
  drivers: string[];
  ablations: { component: string; delta: number | null }[];
  reason: string | null;
};

export function normalizePresentationCandidates(result: JsonObject): PresentationCandidate[] {
  return arrayAt(result, ["candidates"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    return [{
      id: textAt(value, ["peptide_id"], "unknown"),
      sequence: textAt(value, ["sequence"], "—"),
      gene: textAt(value, ["source_gene"], "—"),
      support: textAt(value, ["support"], "unsupported"),
      probability: numberAt(value, ["presentation_probability"]),
      low: numberAt(value, ["interval_low"]),
      high: numberAt(value, ["interval_high"]),
      rank: numberAt(value, ["rank"]),
      alleles: arrayAt(value, ["supported_alleles"]).length,
      drivers: arrayAt(value, ["top_drivers"]).filter((item): item is string => typeof item === "string"),
      ablations: arrayAt(value, ["ablations"]).flatMap((item) => isJsonObject(item) ? [{ component: textAt(item, ["component"], "—"), delta: numberAt(item, ["probability_delta"]) }] : []),
      reason: textAt(value, ["abstention_reason"], "") || null,
    }];
  });
}

export function presentationProvenance(result: JsonObject): JsonObject | null {
  const first = objectAt(result, ["provenance"]);
  return first;
}
