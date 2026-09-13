import {
  arrayAt,
  isJsonObject,
  numberAt,
  objectAt,
  textAt,
  type JsonObject,
  type JsonValue,
} from "./research-state";

export const GBM_RNA_PURITY_PROFILE_ID = "gbm-rna-tumor-purity/1.0.0";
export const GBM_RNA_PURITY_MODEL_FEATURE_COUNT = 5_829;
export const GBM_RNA_PURITY_MAX_INPUT_GENES = 40_000;

export const GBM_RNA_PURITY_CONTEXT = {
  schema_version: "glio-proteogen.gbm-rna-context-attestation/1.0.0",
  organism: "Homo sapiens",
  disease_context: "primary_IDH_wildtype_glioblastoma",
  specimen: "bulk_tumor_tissue",
  assay: "bulk_RNA_sequencing",
  value_semantics: "raw_nonnegative_gene_counts",
  batch_corrected: false,
  caller_authorizes_missing_gene_zero_fill: true,
  research_use_only: true,
} as const;

export type GbmRnaPuritySupport = "supported" | "limited" | "abstained";
export type GbmRnaPurityClipping = "none" | "lower_bound" | "upper_bound" | "not_applicable";
export type GbmRnaPurityAttributionDirection =
  | "raises_raw_estimate"
  | "lowers_raw_estimate"
  | "zero_local_contribution";

export type GbmRnaPurityRequestStats = {
  suppliedGenes: number;
  uniqueGenes: number;
  nonzeroGenes: number;
  totalRawCount: number;
};

export type GbmRnaPurityCoverage = {
  modelFeatureCount: number;
  suppliedGeneCount: number;
  recognizedModelGeneCount: number;
  missingModelGeneCount: number;
  ignoredNonModelGeneCount: number;
  nonzeroModelGeneCount: number;
  coverageFraction: number;
  recognizedRawCountSum: number;
  missingGenePolicy: string;
};

export type GbmRnaPurityEstimate = {
  malignantCellFraction: number;
  rawUnclippedOutput: number;
  clippingState: GbmRnaPurityClipping;
  outputSemantics: string;
};

export type GbmRnaPurityAttribution = {
  rank: number;
  geneSymbol: string;
  transformedExpression: number;
  localGradient: number;
  rawOutputContribution: number;
  direction: GbmRnaPurityAttributionDirection;
};

export type GbmRnaPurityExplanation = {
  method: string;
  attributions: GbmRnaPurityAttribution[];
  allGeneContributionSum: number;
  activePathBiasContribution: number;
  reconstructedRawOutput: number;
  reconstructionAbsoluteError: number;
  clippingChangesLocalInterpretation: boolean;
  interpretation: string;
};

export type GbmRnaPurityDiagnostics = {
  preprocessing: string;
  network: string;
  dropoutActive: boolean;
  inferenceDtype: string;
  finiteInference: boolean;
  transformedInputSum: number;
  transformedInputMaximum: number;
  firstLayerActiveNodes: number | null;
  secondLayerActiveNodes: number | null;
  activationPatternDigest: string;
};

export type GbmRnaPurityEvidence = {
  support: GbmRnaPuritySupport;
  coverage: GbmRnaPurityCoverage;
  estimate: GbmRnaPurityEstimate | null;
  diagnostics: GbmRnaPurityDiagnostics;
  explanation: GbmRnaPurityExplanation | null;
  uncertaintyStatus: string;
  uncertaintyReason: string;
  abstentionReasons: string[];
  provenance: JsonObject | null;
  raw: JsonObject;
};

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const GENE_SYMBOL = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ROOT_FIELDS = new Set([
  "schema_version",
  "sample_id",
  "profile_id",
  "context",
  "counts_provenance_digest",
  "counts",
]);
const CONTEXT_FIELDS = new Set(Object.keys(GBM_RNA_PURITY_CONTEXT));
const COUNT_FIELDS = new Set(["gene_symbol", "raw_count"]);
const SUPPORT_VALUES = new Set<string>(["supported", "limited", "abstained"]);
const CLIPPING_VALUES = new Set<string>(["none", "lower_bound", "upper_bound", "not_applicable"]);
const DIRECTION_VALUES = new Set<string>([
  "raises_raw_estimate",
  "lowers_raw_estimate",
  "zero_local_contribution",
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

function duplicateValues(values: string[]): string[] {
  return [...new Set(values.filter((value, index) => values.indexOf(value) !== index))];
}

function stringValues(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function isSupport(value: string): value is GbmRnaPuritySupport {
  return SUPPORT_VALUES.has(value);
}

function isClipping(value: string): value is GbmRnaPurityClipping {
  return CLIPPING_VALUES.has(value);
}

function isAttributionDirection(value: string): value is GbmRnaPurityAttributionDirection {
  return DIRECTION_VALUES.has(value);
}

export function gbmRnaPurityRequestStats(request: JsonObject): GbmRnaPurityRequestStats {
  const counts = arrayAt(request, ["counts"]);
  const genes = counts.flatMap((value) => isJsonObject(value) && typeof value.gene_symbol === "string"
    ? [value.gene_symbol]
    : []);
  const rawCounts = counts.flatMap((value) => {
    if (!isJsonObject(value) || typeof value.raw_count !== "number" || !Number.isFinite(value.raw_count)) return [];
    return [value.raw_count];
  });
  return {
    suppliedGenes: counts.length,
    uniqueGenes: new Set(genes).size,
    nonzeroGenes: rawCounts.filter((value) => value > 0).length,
    totalRawCount: rawCounts.reduce((sum, value) => sum + value, 0),
  };
}

export function validateGbmRnaPurityRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, ROOT_FIELDS, "request", errors);

  if (
    hasOwn(request, "schema_version") &&
    request.schema_version !== "glio-proteogen.gbm-rna-purity-request/1.0.0"
  ) {
    errors.push("schema_version must equal glio-proteogen.gbm-rna-purity-request/1.0.0.");
  }
  if (typeof request.sample_id !== "string" || !IDENTIFIER.test(request.sample_id)) {
    errors.push("sample_id must be a valid identifier.");
  }
  if (hasOwn(request, "profile_id") && request.profile_id !== GBM_RNA_PURITY_PROFILE_ID) {
    errors.push(`profile_id must equal ${GBM_RNA_PURITY_PROFILE_ID}.`);
  }
  if (
    typeof request.counts_provenance_digest !== "string" ||
    !DIGEST.test(request.counts_provenance_digest)
  ) {
    errors.push("counts_provenance_digest must be a lowercase sha256 digest.");
  }

  if (!isJsonObject(request.context)) {
    errors.push("context must be the exact primary IDH-wildtype GBM bulk-RNA attestation object.");
  } else {
    rejectUnknownFields(request.context, CONTEXT_FIELDS, "context", errors);
    for (const [key, expected] of Object.entries(GBM_RNA_PURITY_CONTEXT)) {
      if (request.context[key] !== expected) {
        errors.push(`context.${key} must equal ${JSON.stringify(expected)}.`);
      }
    }
  }

  const values = request.counts;
  const counts = Array.isArray(values) ? values : [];
  if (!Array.isArray(values)) errors.push("counts must be an array.");
  if (!counts.length) errors.push("At least one raw gene count is required.");
  if (counts.length > GBM_RNA_PURITY_MAX_INPUT_GENES) {
    errors.push(`The request exceeds the ${GBM_RNA_PURITY_MAX_INPUT_GENES.toLocaleString("en-US")}-gene limit.`);
  }

  const genes: string[] = [];
  counts.forEach((value, index) => {
    const path = `counts[${index}]`;
    if (!isJsonObject(value)) {
      errors.push(`${path} must be an object.`);
      return;
    }
    rejectUnknownFields(value, COUNT_FIELDS, path, errors);
    if (typeof value.gene_symbol !== "string" || !GENE_SYMBOL.test(value.gene_symbol)) {
      errors.push(`${path}.gene_symbol must use the source-compatible gene-symbol syntax.`);
    } else {
      genes.push(value.gene_symbol);
    }
    if (
      typeof value.raw_count !== "number" ||
      !Number.isFinite(value.raw_count) ||
      value.raw_count < 0 ||
      value.raw_count > 1.0e15
    ) {
      errors.push(`${path}.raw_count must be a finite number within [0, 1e15].`);
    }
  });

  const duplicates = duplicateValues(genes);
  if (duplicates.length) errors.push(`Duplicate gene symbols: ${duplicates.join(", ")}. Counts are never summed implicitly.`);
  return errors;
}

function normalizeAttribution(value: JsonValue): GbmRnaPurityAttribution | null {
  if (!isJsonObject(value)) return null;
  const geneSymbol = textAt(value, ["gene_symbol"]);
  const direction = textAt(value, ["direction"]);
  const rank = numberAt(value, ["rank"]);
  const transformedExpression = numberAt(value, ["transformed_expression"]);
  const localGradient = numberAt(value, ["local_gradient"]);
  const rawOutputContribution = numberAt(value, ["raw_output_contribution"]);
  if (
    !geneSymbol ||
    !isAttributionDirection(direction) ||
    rank === null ||
    transformedExpression === null ||
    localGradient === null ||
    rawOutputContribution === null
  ) return null;
  return {
    rank,
    geneSymbol,
    transformedExpression,
    localGradient,
    rawOutputContribution,
    direction,
  };
}

function normalizeCoverage(value: JsonObject): GbmRnaPurityCoverage {
  return {
    modelFeatureCount: numberAt(value, ["model_feature_count"]) ?? GBM_RNA_PURITY_MODEL_FEATURE_COUNT,
    suppliedGeneCount: numberAt(value, ["supplied_gene_count"]) ?? 0,
    recognizedModelGeneCount: numberAt(value, ["recognized_model_gene_count"]) ?? 0,
    missingModelGeneCount: numberAt(value, ["missing_model_gene_count"]) ?? 0,
    ignoredNonModelGeneCount: numberAt(value, ["ignored_non_model_gene_count"]) ?? 0,
    nonzeroModelGeneCount: numberAt(value, ["nonzero_model_gene_count"]) ?? 0,
    coverageFraction: numberAt(value, ["coverage_fraction"]) ?? 0,
    recognizedRawCountSum: numberAt(value, ["recognized_raw_count_sum"]) ?? 0,
    missingGenePolicy: textAt(value, ["missing_gene_policy"], "not reported"),
  };
}

function normalizeEstimate(value: JsonObject | null): GbmRnaPurityEstimate | null {
  if (!value) return null;
  const malignantCellFraction = numberAt(value, ["malignant_cell_fraction"]);
  const rawUnclippedOutput = numberAt(value, ["raw_unclipped_output"]);
  const clippingState = textAt(value, ["clipping_state"]);
  if (malignantCellFraction === null || rawUnclippedOutput === null || !isClipping(clippingState)) return null;
  return {
    malignantCellFraction,
    rawUnclippedOutput,
    clippingState,
    outputSemantics: textAt(value, ["model_output_semantics"], "not reported"),
  };
}

function normalizeDiagnostics(value: JsonObject): GbmRnaPurityDiagnostics {
  const hiddenTrace = objectAt(value, ["hidden_trace"]);
  return {
    preprocessing: textAt(value, ["preprocessing"], "not reported"),
    network: textAt(value, ["network"], "not reported"),
    dropoutActive: value.dropout_active === true,
    inferenceDtype: textAt(value, ["inference_dtype"], "not reported"),
    finiteInference: value.finite_inference === true,
    transformedInputSum: numberAt(value, ["transformed_input_sum"]) ?? 0,
    transformedInputMaximum: numberAt(value, ["transformed_input_maximum"]) ?? 0,
    firstLayerActiveNodes: hiddenTrace ? numberAt(hiddenTrace, ["first_layer_active_nodes"]) : null,
    secondLayerActiveNodes: hiddenTrace ? numberAt(hiddenTrace, ["second_layer_active_nodes"]) : null,
    activationPatternDigest: hiddenTrace ? textAt(hiddenTrace, ["activation_pattern_digest"]) : "",
  };
}

function normalizeExplanation(value: JsonObject | null): GbmRnaPurityExplanation | null {
  if (!value) return null;
  return {
    method: textAt(value, ["method"], "not reported"),
    attributions: arrayAt(value, ["top_gene_attributions"]).flatMap((item) => {
      const attribution = normalizeAttribution(item);
      return attribution ? [attribution] : [];
    }),
    allGeneContributionSum: numberAt(value, ["all_gene_contribution_sum"]) ?? 0,
    activePathBiasContribution: numberAt(value, ["active_path_bias_contribution"]) ?? 0,
    reconstructedRawOutput: numberAt(value, ["reconstructed_raw_output"]) ?? 0,
    reconstructionAbsoluteError: numberAt(value, ["reconstruction_absolute_error"]) ?? 0,
    clippingChangesLocalInterpretation: value.clipping_changes_local_interpretation === true,
    interpretation: textAt(value, ["interpretation"], "not reported"),
  };
}

export function normalizeGbmRnaPurityResult(result: JsonObject): GbmRnaPurityEvidence | null {
  const support = textAt(result, ["support"]);
  const coverage = objectAt(result, ["coverage"]);
  const diagnostics = objectAt(result, ["diagnostics"]);
  if (!isSupport(support) || !coverage || !diagnostics) return null;
  return {
    support,
    coverage: normalizeCoverage(coverage),
    estimate: normalizeEstimate(objectAt(result, ["estimate"])),
    diagnostics: normalizeDiagnostics(diagnostics),
    explanation: normalizeExplanation(objectAt(result, ["explanation"])),
    uncertaintyStatus: textAt(result, ["uncertainty_status"], "not reported"),
    uncertaintyReason: textAt(result, ["uncertainty_reason"], "No uncertainty statement was returned."),
    abstentionReasons: stringValues(result.abstention_reasons),
    provenance: objectAt(result, ["provenance"]),
    raw: result,
  };
}
