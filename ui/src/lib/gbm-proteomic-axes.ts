import {
  arrayAt,
  isJsonObject,
  numberAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";

export const GBM_PROFILE_ID = "gbm-proteomic-axes/1.0.0";
export const GBM_SIGNATURE_IDS = [
  "SWEET_KRAS_TARGETS_UP",
  "HALLMARK_MYC_TARGETS_V1",
  "WINTER_HYPOXIA_UP",
  "VERHAAK_GLIOBLASTOMA_MESENCHYMAL",
  "VERHAAK_GLIOBLASTOMA_NEURAL",
  "VERHAAK_GLIOBLASTOMA_PRONEURAL",
  "EGFR_UP.V1_UP",
] as const;

export type GbmEvidenceState = "observed" | "left_censored" | "missing" | "unsupported";
export type GbmSignatureSupport = "supported" | "limited" | "abstained";

export type GbmFeatureDriver = {
  geneSymbol: string;
  signedContribution: number;
  absoluteContribution: number;
  declaredState: GbmEvidenceState | null;
  inputSource: "observed_lfq" | "published_zero_fill";
};

export type GbmSignature = {
  id: string;
  displayName: string;
  support: GbmSignatureSupport;
  score: number | null;
  lower: number | null;
  upper: number | null;
  modelFeatureCount: number;
  observedFeatureCount: number;
  observedFeatureFraction: number;
  missingFeatureCount: number;
  missingFeatureRatio: number;
  bootstrapReplicates: number;
  abstentionReason: string;
  drivers: GbmFeatureDriver[];
  raw: JsonObject;
};

export type GbmRequestStats = {
  measurements: number;
  observed: number;
  signatures: number;
};

const IDENTIFIER_PATTERN = /^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$/;
const GENE_PATTERN = /^[A-Za-z][A-Za-z0-9.-]{0,31}$/;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const ROOT_FIELDS = new Set(["profile_id", "sample_id", "measurements", "signature_ids", "bootstrap_replicates"]);
const MEASUREMENT_FIELDS = new Set([
  "gene_symbol",
  "state",
  "lfq_intensity",
  "lfq_upper_limit",
  "log2_standard_error",
  "provenance_digest",
]);
const EVIDENCE_STATES = new Set<GbmEvidenceState>(["observed", "left_censored", "missing", "unsupported"]);
const SIGNATURE_IDS = new Set<string>(GBM_SIGNATURE_IDS);

function hasOwn(source: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

function rejectUnknownFields(source: JsonObject, allowed: ReadonlySet<string>, path: string, errors: string[]): void {
  const unknown = Object.keys(source).filter((key) => !allowed.has(key));
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function optionalFiniteNumber(source: JsonObject, key: string, path: string, errors: string[]): number | null {
  const value = source[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    errors.push(`${path} must be a finite number or null.`);
    return null;
  }
  return value;
}

function requirePositiveBounded(
  source: JsonObject,
  key: string,
  path: string,
  maximum: number,
  errors: string[],
): number | null {
  const value = optionalFiniteNumber(source, key, path, errors);
  if (value !== null && (value <= 0 || value > maximum)) {
    errors.push(`${path} must be within (0, ${maximum}].`);
  }
  return value;
}

export function gbmRequestStats(request: JsonObject): GbmRequestStats {
  const measurements = arrayAt(request, ["measurements"]);
  const signatureIds = arrayAt(request, ["signature_ids"]);
  return {
    measurements: measurements.length,
    observed: measurements.filter((value) => isJsonObject(value) && value.state === "observed").length,
    signatures: signatureIds.length || GBM_SIGNATURE_IDS.length,
  };
}

export function validateGbmRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_FIELDS, "request", errors);

  if (hasOwn(request, "profile_id") && request.profile_id !== GBM_PROFILE_ID) {
    errors.push(`profile_id must equal ${GBM_PROFILE_ID}.`);
  }
  if (typeof request.sample_id !== "string" || !IDENTIFIER_PATTERN.test(request.sample_id)) {
    errors.push("sample_id must be a valid identifier (1–128 characters, beginning with a letter).");
  }

  const measurementsValue = request.measurements;
  const measurements = Array.isArray(measurementsValue) ? measurementsValue : [];
  if (!Array.isArray(measurementsValue)) errors.push("measurements must be an array.");
  if (measurements.length < 1) errors.push("At least one protein measurement is required.");
  if (measurements.length > 8_192) errors.push("The request exceeds the 8,192-measurement limit.");

  const symbols: string[] = [];
  measurements.forEach((value, index) => {
    const path = `measurements[${index}]`;
    if (!isJsonObject(value)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    rejectUnknownFields(value, MEASUREMENT_FIELDS, path, errors);
    const gene = value.gene_symbol;
    if (typeof gene !== "string" || !GENE_PATTERN.test(gene)) {
      errors.push(`${path}.gene_symbol must be a canonical gene symbol of 1–32 characters.`);
    } else {
      symbols.push(gene);
    }
    const state = value.state;
    if (typeof state !== "string" || !EVIDENCE_STATES.has(state as GbmEvidenceState)) {
      errors.push(`${path}.state must be one of: observed, left_censored, missing, unsupported.`);
    }
    if (typeof value.provenance_digest !== "string" || !SHA256_PATTERN.test(value.provenance_digest)) {
      errors.push(`${path}.provenance_digest must be a lowercase sha256 digest.`);
    }

    const intensity = requirePositiveBounded(value, "lfq_intensity", `${path}.lfq_intensity`, 1e18, errors);
    const upper = requirePositiveBounded(value, "lfq_upper_limit", `${path}.lfq_upper_limit`, 1e18, errors);
    const standardError = requirePositiveBounded(value, "log2_standard_error", `${path}.log2_standard_error`, 4, errors);
    if (state === "observed" && (intensity === null || upper !== null)) {
      errors.push(`${path} observed evidence requires LFQ intensity and no upper limit.`);
    } else if (state === "left_censored" && (upper === null || intensity !== null || standardError !== null)) {
      errors.push(`${path} left-censored evidence requires an LFQ upper limit only.`);
    } else if ((state === "missing" || state === "unsupported") && (intensity !== null || upper !== null || standardError !== null)) {
      errors.push(`${path} missing/unsupported evidence cannot carry numeric LFQ values.`);
    }
  });
  const duplicates = [...new Set(symbols.filter((symbol, index) => symbols.indexOf(symbol) !== index))];
  if (duplicates.length) errors.push(`Duplicate gene symbols: ${duplicates.join(", ")}.`);

  if (hasOwn(request, "signature_ids")) {
    if (!Array.isArray(request.signature_ids)) {
      errors.push("signature_ids must be an array.");
    } else {
      if (request.signature_ids.length > 7) errors.push("The request exceeds the seven-signature limit.");
      const valid: string[] = [];
      request.signature_ids.forEach((value, index) => {
        if (typeof value !== "string" || !IDENTIFIER_PATTERN.test(value)) {
          errors.push(`signature_ids[${index}] must be a valid identifier.`);
        } else if (!SIGNATURE_IDS.has(value)) {
          errors.push(`signature_ids[${index}] is not a supported GBM signature.`);
        } else {
          valid.push(value);
        }
      });
      const duplicateSignatures = [...new Set(valid.filter((value, index) => valid.indexOf(value) !== index))];
      if (duplicateSignatures.length) errors.push(`Duplicate signature identifiers: ${duplicateSignatures.join(", ")}.`);
    }
  }

  if (hasOwn(request, "bootstrap_replicates")) {
    const bootstrap = request.bootstrap_replicates;
    if (typeof bootstrap !== "number" || !Number.isInteger(bootstrap) || bootstrap < 0 || bootstrap > 256 || (bootstrap > 0 && bootstrap < 8)) {
      errors.push("bootstrap_replicates must be zero or an integer from 8 through 256.");
    }
  }
  return errors;
}

function normalizeDriver(value: JsonValue): GbmFeatureDriver | null {
  if (!isJsonObject(value)) return null;
  const geneSymbol = textAt(value, ["gene_symbol"]);
  const signedContribution = numberAt(value, ["signed_contribution"]);
  const absoluteContribution = numberAt(value, ["absolute_contribution"]);
  const inputSource = textAt(value, ["model_input_source"]);
  if (!geneSymbol || signedContribution === null || absoluteContribution === null || (inputSource !== "observed_lfq" && inputSource !== "published_zero_fill")) return null;
  const declared = textAt(value, ["declared_state"]);
  return {
    geneSymbol,
    signedContribution,
    absoluteContribution,
    declaredState: EVIDENCE_STATES.has(declared as GbmEvidenceState) ? declared as GbmEvidenceState : null,
    inputSource,
  };
}

export function normalizeGbmSignatures(result: JsonObject): GbmSignature[] {
  return arrayAt(result, ["signatures"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const support = textAt(value, ["support"]);
    if (support !== "supported" && support !== "limited" && support !== "abstained") return [];
    return [{
      id: textAt(value, ["signature_id"], "unnamed-signature"),
      displayName: textAt(value, ["display_name"], textAt(value, ["signature_id"], "Unnamed signature")),
      support,
      score: numberAt(value, ["published_score"]),
      lower: numberAt(value, ["lower_bound"]),
      upper: numberAt(value, ["upper_bound"]),
      modelFeatureCount: numberAt(value, ["model_feature_count"]) ?? 0,
      observedFeatureCount: numberAt(value, ["observed_feature_count"]) ?? 0,
      observedFeatureFraction: numberAt(value, ["observed_feature_fraction"]) ?? 0,
      missingFeatureCount: numberAt(value, ["missing_feature_count"]) ?? 0,
      missingFeatureRatio: numberAt(value, ["missing_feature_ratio"]) ?? 0,
      bootstrapReplicates: numberAt(value, ["bootstrap_replicates_used"]) ?? 0,
      abstentionReason: textAt(value, ["abstention_reason"]),
      drivers: arrayAt(value, ["top_feature_drivers"]).flatMap((driver) => {
        const normalized = normalizeDriver(driver);
        return normalized ? [normalized] : [];
      }),
      raw: value,
    } satisfies GbmSignature];
  });
}
