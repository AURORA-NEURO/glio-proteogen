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

export const LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID =
  "kncc-reactome-complex-transition/1.0.0";
export const LONGITUDINAL_GBM_COMPLEX_TRANSITION_MODEL_ID =
  "kncc-reactome-complex-transition-factor-model/1.0.0";
export const LONGITUDINAL_GBM_COMPLEX_COUNT = 28;
export const LONGITUDINAL_GBM_COMPLEX_DOMAIN_COUNT = 11;

export type ComplexTransitionSupport = "supported" | "limited" | "abstained";

export type ComplexTransitionRequestStats = {
  timePoints: number;
  transitions: number;
  observations: number;
  active: number;
  genes: number;
};

export type ComplexTransitionUncertainty = {
  state: string;
  measurementStandardError: number | null;
  fittedModelStandardError: number | null;
  measurementModelCovariance: number | null;
  combinedStandardError: number | null;
  varianceClosureResidual: number | null;
  bootstrapReplicates: number;
  reason: string;
};

export type ComplexMemberContribution = {
  geneSymbol: string;
  standardizedDelta: number | null;
  memberLoading: number | null;
  reliabilityWeight: number | null;
  contribution: number | null;
  direction: string;
};

export type ComplexAblation = {
  kind: string;
  componentId: string;
  support: ComplexTransitionSupport;
  scoreWithout: number | null;
  scoreDelta: number | null;
  classificationWithout: string;
  removedMemberCount: number;
  reason: string;
};

export type ComplexMemberConcordance = {
  complexIndex: number;
  domainId: string;
  reactomeId: string;
  complexName: string;
  familyId: string;
  support: ComplexTransitionSupport;
  classification: string;
  score: number | null;
  lower: number | null;
  upper: number | null;
  activeMemberCount: number;
  observedMemberCount: number;
  leftCensoredMemberCount: number;
  coefficientMassCoverage: number;
  effectiveSampleSize: number | null;
  coherence: number | null;
  discordance: number | null;
  stability: number | null;
  sourceHeldMemberRelativeGain: number | null;
  sourceDirectionAccuracy: number | null;
  sourceMinimumOuterLoadingCosine: number | null;
  uncertainty: ComplexTransitionUncertainty;
  contributions: ComplexMemberContribution[];
  ablations: ComplexAblation[];
  reasons: string[];
  raw: JsonObject;
};

export type ComplexTransition = {
  id: string;
  index: number;
  fromTimePointId: string;
  toTimePointId: string;
  durationDays: number | null;
  complexes: ComplexMemberConcordance[];
  raw: JsonObject;
};

export type ComplexEvaluationSummary = {
  validationScope: string;
  patientCount: number;
  evaluationCount: number;
  zeroTransitionMeanMae: number | null;
  trainingCenterMeanMae: number | null;
  factorModelMeanMae: number | null;
  meanRelativeGain: number | null;
  patientClusterInterval: [number | null, number | null];
  directionAccuracy: number | null;
  minimumOuterLoadingCosine: number | null;
  nonconvergedReferenceFitCount: number;
  nonconvergedOuterFitCount: number;
  externalValidationPerformed: boolean;
};

const SUPPORT_VALUES = new Set<ComplexTransitionSupport>([
  "supported",
  "limited",
  "abstained",
]);
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const REACTOME_ID = /^R-HSA-[1-9][0-9]*$/;
const RESULT_FIELDS = new Set([
  "profile_id",
  "model_id",
  "request_digest",
  "result_digest",
  "profile_digest",
  "source_catalog_digest",
  "fitted_model_digest",
  "computational_seed",
  "series_id",
  "assay_compatibility",
  "normalization_reference",
  "time_point_ids",
  "transitions",
  "output_semantics",
  "provenance",
  "limitations",
  "research_use_only",
  "non_prescriptive",
  "infers_complex_assembly",
  "infers_complex_activity",
  "infers_stoichiometry",
  "infers_essential_subunits",
  "infers_causality",
]);
const TRANSITION_FIELDS = new Set([
  "transition_id",
  "transition_index",
  "from_time_point_id",
  "to_time_point_id",
  "duration_days",
  "complexes",
]);
const COMPLEX_FIELDS = new Set([
  "complex_index",
  "domain_id",
  "reactome_id",
  "complex_name",
  "family_id",
  "output_semantics",
  "support",
  "classification",
  "score",
  "lower_bound",
  "upper_bound",
  "interval_level",
  "active_member_count",
  "observed_member_count",
  "left_censored_member_count",
  "coefficient_mass_coverage",
  "effective_sample_size",
  "coherence",
  "discordance",
  "stability",
  "solver_converged",
  "solver_iterations",
  "solver_initial_objective",
  "solver_final_objective",
  "solver_objective_monotone",
  "bootstrap_failed_replicates",
  "least_source_aligned_observed_member",
  "source_held_member_relative_gain",
  "source_panel_patient_cluster_gain_90_interval",
  "source_direction_accuracy",
  "source_minimum_outer_loading_cosine",
  "uncertainty",
  "top_contributions",
  "ablations",
  "limitations",
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
  "value_semantics",
  "standardized_delta",
  "member_loading",
  "reliability_weight",
  "contribution",
  "direction",
]);
const ABLATIONS_FIELDS = new Set([
  "source_processing",
  "uniform_member_loading",
  "top_member",
  "nested_family",
]);
const ABLATION_FIELDS = new Set([
  "component_kind",
  "component_id",
  "support",
  "score_without_component",
  "score_delta",
  "classification_without_component",
  "removed_member_count",
  "reason",
]);
const PROVENANCE_FIELDS = new Set([
  "source_study_id",
  "source_patient_pair_count",
  "reactome_release",
  "source_catalog_digest",
  "fitted_model_digest",
  "training_recipe_digest",
  "panel_selection_digest",
  "participant_membership_digest",
  "source_licenses",
  "source_attribution",
  "validation_scope",
  "patient_level_data_packaged",
  "external_validation_performed",
]);
const PROFILE_FIELDS = new Set([
  "algorithm_id",
  "algorithm_version",
  "profile_id",
  "model_id",
  "profile_digest",
  "required_assay_compatibility",
  "numpy_version",
  "constants",
  "limits",
  "counts",
  "digests",
  "evaluation",
  "complexes",
  "source_licenses",
  "source_attribution",
  "claim_ceiling",
  "limitations",
  "research_use_only",
  "non_prescriptive",
]);
const PROFILE_COMPLEX_FIELDS = new Set([
  "complex_index",
  "domain_id",
  "reactome_id",
  "complex_name",
  "family_id",
  "selection_tier",
  "mapped_member_count",
  "fitted_member_count",
  "source_held_member_relative_gain",
  "source_panel_patient_cluster_gain_90_interval",
  "source_direction_accuracy",
  "minimum_outer_loading_cosine",
]);
const VERIFICATION_FIELDS = new Set([
  "verified",
  "request_digest_match",
  "profile_digest_match",
  "result_digest_match",
  "transition_topology_match",
  "complex_semantic_match",
  "uncertainty_semantic_match",
  "ablation_semantic_match",
  "provenance_match",
  "document_semantic_match",
  "semantic_match",
  "recomputed_request_digest",
  "recomputed_result_digest",
  "authoritative_profile_digest",
  "message",
]);

type HeaderReader = Pick<Headers, "get">;

function exactFields(
  value: JsonObject,
  expected: ReadonlySet<string>,
  path: string,
  errors: string[],
): void {
  const actual = Object.keys(value);
  const unknown = actual.filter((key) => !expected.has(key));
  const missing = [...expected].filter((key) => !Object.prototype.hasOwnProperty.call(value, key));
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
  if (missing.length) errors.push(`${path} is missing required fields: ${missing.join(", ")}.`);
}

function strings(value: JsonValue | undefined): string[] | null {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) return null;
  return value as string[];
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

function canonicalJson(value: JsonValue): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isJsonObject(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sameJson(left: JsonValue | undefined, right: JsonValue | undefined): boolean {
  return left !== undefined && right !== undefined && canonicalJson(left) === canonicalJson(right);
}

function validateUncertainty(value: JsonValue | undefined, path: string, errors: string[]): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, UNCERTAINTY_FIELDS, path, errors);
  if (value.state === "estimated") {
    for (const field of [
      "measurement_standard_error",
      "fitted_model_standard_error",
      "measurement_model_covariance",
      "combined_standard_error",
      "variance_closure_residual",
    ]) if (!finite(value[field])) errors.push(`${path}.${field} must be finite for estimated uncertainty.`);
    if (!integer(value.bootstrap_replicates_used, 1, 256)) errors.push(`${path}.bootstrap_replicates_used must be 1 through 256.`);
    if (value.reason !== null) errors.push(`${path}.reason must be null when uncertainty is estimated.`);
  } else if (value.state === "not_estimable") {
    for (const field of [
      "measurement_standard_error",
      "fitted_model_standard_error",
      "measurement_model_covariance",
      "combined_standard_error",
      "variance_closure_residual",
    ]) if (value[field] !== null) errors.push(`${path}.${field} must be null when uncertainty is not estimable.`);
    if (value.bootstrap_replicates_used !== 0 || typeof value.reason !== "string" || !value.reason.trim()) {
      errors.push(`${path} must carry zero replicates and a reason when uncertainty is not estimable.`);
    }
  } else errors.push(`${path}.state is invalid.`);
}

function validateAblation(value: JsonValue, path: string, errors: string[]): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object or null.`);
    return;
  }
  exactFields(value, ABLATION_FIELDS, path, errors);
  if (!["source_processing", "uniform_member_loading", "top_member", "nested_family"].includes(String(value.component_kind))) {
    errors.push(`${path}.component_kind is invalid.`);
  }
  const support = supportValue(typeof value.support === "string" ? value.support : "");
  if (!support) errors.push(`${path}.support is invalid.`);
  if (!integer(value.removed_member_count, 0, 32)) errors.push(`${path}.removed_member_count must be 0 through 32.`);
  if (support === "abstained") {
    if (value.score_without_component !== null || value.score_delta !== null || value.classification_without_component !== "not_estimable") {
      errors.push(`${path} abstention fields are inconsistent.`);
    }
  } else if (support && (!finite(value.score_without_component) || !finite(value.score_delta))) {
    errors.push(`${path} requires finite ablation estimates.`);
  }
}

function validateComplexDocument(value: JsonValue, expectedIndex: number, path: string, errors: string[]): void {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return;
  }
  exactFields(value, COMPLEX_FIELDS, path, errors);
  if (value.complex_index !== expectedIndex) errors.push(`${path}.complex_index must preserve contiguous panel order.`);
  if (typeof value.reactome_id !== "string" || !REACTOME_ID.test(value.reactome_id)) errors.push(`${path}.reactome_id is invalid.`);
  if (value.output_semantics !== "source_cohort_complex_member_transition_concordance") errors.push(`${path}.output_semantics is invalid.`);
  const support = supportValue(typeof value.support === "string" ? value.support : "");
  if (!support) errors.push(`${path}.support is invalid.`);
  for (const field of ["active_member_count", "observed_member_count", "left_censored_member_count"] as const) {
    if (!integer(value[field], 0, 32)) errors.push(`${path}.${field} must be an integer from 0 through 32.`);
  }
  if (
    integer(value.active_member_count, 0, 32)
    && integer(value.observed_member_count, 0, 32)
    && integer(value.left_censored_member_count, 0, 32)
    && value.observed_member_count + value.left_censored_member_count !== value.active_member_count
  ) errors.push(`${path} active member counts do not close.`);
  if (!finite(value.coefficient_mass_coverage) || value.coefficient_mass_coverage < 0 || value.coefficient_mass_coverage > 1) {
    errors.push(`${path}.coefficient_mass_coverage must be in [0,1].`);
  }
  validateUncertainty(value.uncertainty, `${path}.uncertainty`, errors);
  const ablations = value.ablations;
  if (!isJsonObject(ablations)) errors.push(`${path}.ablations must be an object.`);
  else {
    exactFields(ablations, ABLATIONS_FIELDS, `${path}.ablations`, errors);
    for (const field of ABLATIONS_FIELDS) {
      const item = ablations[field];
      if (item !== null) validateAblation(item, `${path}.ablations.${field}`, errors);
    }
  }
  const contributions = Array.isArray(value.top_contributions) ? value.top_contributions : null;
  if (!contributions || contributions.length > 8) errors.push(`${path}.top_contributions must contain at most 8 entries.`);
  else contributions.forEach((item, index) => {
    if (!isJsonObject(item)) {
      errors.push(`${path}.top_contributions[${index}] must be an object.`);
      return;
    }
    exactFields(item, CONTRIBUTION_FIELDS, `${path}.top_contributions[${index}]`, errors);
    if (item.value_semantics !== "exact_delta") errors.push(`${path}.top_contributions[${index}].value_semantics is invalid.`);
    for (const field of ["from_provenance_digest", "to_provenance_digest"] as const) {
      if (!digest(item[field])) errors.push(`${path}.top_contributions[${index}].${field} must be a sha256 digest.`);
    }
    if (!finite(item.reliability_weight) || item.reliability_weight <= 0 || item.reliability_weight > 1) {
      errors.push(`${path}.top_contributions[${index}].reliability_weight must be in (0,1].`);
    }
  });
  const limitations = strings(value.limitations);
  if (!limitations || limitations.length > 12) errors.push(`${path}.limitations must contain at most 12 non-empty strings.`);
  if (support === "abstained") {
    if (value.classification !== "not_estimable" || value.score !== null || value.lower_bound !== null || value.upper_bound !== null || !limitations?.length) {
      errors.push(`${path} abstention fields are inconsistent.`);
    }
  } else if (support) {
    if (!finite(value.score) || !finite(value.lower_bound) || !finite(value.upper_bound) || value.lower_bound > value.score || value.score > value.upper_bound) {
      errors.push(`${path} requires a finite ordered estimate interval.`);
    }
    if (value.interval_level !== 0.9 || value.solver_converged !== true || value.solver_objective_monotone !== true) {
      errors.push(`${path} estimated diagnostics are incomplete.`);
    }
    if (!isJsonObject(ablations) || !isJsonObject(ablations.source_processing) || !isJsonObject(ablations.uniform_member_loading)) {
      errors.push(`${path} requires source-processing and loading ablations.`);
    }
  }
}

function supportValue(value: string): ComplexTransitionSupport | null {
  return SUPPORT_VALUES.has(value as ComplexTransitionSupport)
    ? (value as ComplexTransitionSupport)
    : null;
}

function stringValues(value: JsonValue | undefined): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function complexTransitionRequestStats(
  request: JsonObject,
): ComplexTransitionRequestStats {
  const stats = longitudinalRequestStats(request);
  return {
    ...stats,
    transitions: Math.max(0, stats.timePoints - 1),
  };
}

export function validateComplexTransitionRequest(request: JsonObject): string[] {
  const profileErrors = request.profile_id === undefined
    || request.profile_id === LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID
    ? []
    : [
      `profile_id must equal ${LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID}.`,
    ];
  const parentCompatibleRequest: JsonObject = {
    ...request,
    profile_id: LONGITUDINAL_GBM_PROFILE_ID,
  };
  return [...profileErrors, ...validateLongitudinalRequest(parentCompatibleRequest)];
}

export function validateComplexTransitionProfile(profile: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(profile, PROFILE_FIELDS, "profile", errors);
  if (profile.algorithm_id !== "kncc-reactome-complex-transition" || profile.algorithm_version !== "1.0.0") {
    errors.push("profile algorithm identity is invalid.");
  }
  if (profile.profile_id !== LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID) {
    errors.push(`profile.profile_id must equal ${LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID}.`);
  }
  if (profile.model_id !== LONGITUDINAL_GBM_COMPLEX_TRANSITION_MODEL_ID) {
    errors.push(`profile.model_id must equal ${LONGITUDINAL_GBM_COMPLEX_TRANSITION_MODEL_ID}.`);
  }
  if (!digest(profile.profile_digest)) errors.push("profile.profile_digest must be a lowercase sha256 digest.");
  if (profile.numpy_version !== "2.5.2") errors.push("profile.numpy_version must equal the locked 2.5.2 runtime.");
  if (profile.claim_ceiling !== "source_cohort_reactome_participant_set_transition_concordance_only") {
    errors.push("profile.claim_ceiling exceeds or differs from the admitted participant-set concordance claim.");
  }
  if (profile.research_use_only !== true || profile.non_prescriptive !== true) {
    errors.push("profile must remain research-only and non-prescriptive.");
  }
  for (const field of ["required_assay_compatibility", "constants", "limits", "counts", "digests", "evaluation"] as const) {
    if (!isJsonObject(profile[field])) errors.push(`profile.${field} must be an object.`);
  }
  const counts = objectAt(profile, ["counts"]);
  if (counts && (
    counts.strict_patient_pair_count !== 104
    || counts.complex_count !== LONGITUDINAL_GBM_COMPLEX_COUNT
    || counts.nested_family_count !== LONGITUDINAL_GBM_COMPLEX_DOMAIN_COUNT
    || counts.fitted_bootstrap_replicate_count !== 128
  )) errors.push("profile source counts do not match the locked 104-pair, 28-set, 11-domain fitted model.");
  const evaluation = objectAt(profile, ["evaluation"]);
  if (evaluation && (
    evaluation.validation_scope !== "internal_patient_grouped_held_member_reconstruction"
    || evaluation.patient_count !== 104
    || evaluation.external_validation_performed !== false
  )) errors.push("profile evaluation must remain internal patient-grouped held-member reconstruction, not external validation.");
  const profileComplexes = Array.isArray(profile.complexes) ? profile.complexes : null;
  if (!profileComplexes || profileComplexes.length !== LONGITUDINAL_GBM_COMPLEX_COUNT) {
    errors.push(`profile.complexes must contain the ${LONGITUDINAL_GBM_COMPLEX_COUNT} locked participant sets.`);
  } else {
    const seen = new Set<string>();
    profileComplexes.forEach((item, index) => {
      const path = `profile.complexes[${index}]`;
      if (!isJsonObject(item)) {
        errors.push(`${path} must be an object.`);
        return;
      }
      exactFields(item, PROFILE_COMPLEX_FIELDS, path, errors);
      if (item.complex_index !== index) errors.push(`${path}.complex_index must preserve contiguous source order.`);
      if (typeof item.reactome_id !== "string" || !REACTOME_ID.test(item.reactome_id) || seen.has(item.reactome_id)) {
        errors.push(`${path}.reactome_id must be a unique exact Reactome identifier.`);
      } else seen.add(item.reactome_id);
      for (const field of ["mapped_member_count", "fitted_member_count"] as const) {
        if (!integer(item[field], 3, 32)) errors.push(`${path}.${field} must be an integer from 3 through 32.`);
      }
    });
  }
  const licenses = strings(profile.source_licenses);
  const limitations = strings(profile.limitations);
  if (!licenses || licenses.length < 2 || licenses.length > 4) errors.push("profile.source_licenses must contain 2 through 4 non-empty entries.");
  if (!limitations || limitations.length < 1 || limitations.length > 24) errors.push("profile.limitations must contain 1 through 24 non-empty entries.");
  return errors;
}

export function validateComplexTransitionResult(result: JsonObject): string[] {
  const errors: string[] = [];
  exactFields(result, RESULT_FIELDS, "result", errors);
  if (result.profile_id !== LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID) errors.push("result.profile_id is invalid.");
  if (result.model_id !== LONGITUDINAL_GBM_COMPLEX_TRANSITION_MODEL_ID) errors.push("result.model_id is invalid.");
  for (const field of ["request_digest", "result_digest", "profile_digest", "source_catalog_digest", "fitted_model_digest"] as const) {
    if (!digest(result[field])) errors.push(`result.${field} must be a lowercase sha256 digest.`);
  }
  if (!integer(result.computational_seed, 0, 2 ** 53 - 1)) errors.push("result.computational_seed must be a safe non-negative integer.");
  if (result.output_semantics !== "reactome_participant_set_transition_concordance") errors.push("result.output_semantics is invalid.");
  if (result.research_use_only !== true || result.non_prescriptive !== true) errors.push("result must remain research-only and non-prescriptive.");
  for (const field of [
    "infers_complex_assembly",
    "infers_complex_activity",
    "infers_stoichiometry",
    "infers_essential_subunits",
    "infers_causality",
  ] as const) if (result[field] !== false) errors.push(`result.${field} must be false.`);
  if (!isJsonObject(result.assay_compatibility)) errors.push("result.assay_compatibility must be an object.");
  if (!isJsonObject(result.normalization_reference)) errors.push("result.normalization_reference must be an object.");
  const timePointIds = strings(result.time_point_ids);
  if (!timePointIds || timePointIds.length < 2 || timePointIds.length > 16 || new Set(timePointIds).size !== timePointIds.length) {
    errors.push("result.time_point_ids must contain 2 through 16 unique identifiers.");
  }
  const transitions = Array.isArray(result.transitions) ? result.transitions : null;
  if (!transitions || !timePointIds || transitions.length !== timePointIds.length - 1) {
    errors.push("result.transitions must contain one entry per adjacent time-point pair.");
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
    const complexes = Array.isArray(item.complexes) ? item.complexes : null;
    if (!complexes || complexes.length < 1 || complexes.length > 64) errors.push(`${path}.complexes must contain 1 through 64 entries.`);
    else complexes.forEach((complex, complexIndex) => validateComplexDocument(complex, complexIndex, `${path}.complexes[${complexIndex}]`, errors));
  });
  const provenance = objectAt(result, ["provenance"]);
  if (!provenance) errors.push("result.provenance must be an object.");
  else {
    exactFields(provenance, PROVENANCE_FIELDS, "result.provenance", errors);
    if (
      provenance.source_study_id !== "PDC000514"
      || provenance.source_patient_pair_count !== 104
      || provenance.reactome_release !== 97
      || provenance.validation_scope !== "internal_patient_grouped_held_member_reconstruction"
      || provenance.patient_level_data_packaged !== false
      || provenance.external_validation_performed !== false
    ) errors.push("result.provenance is not the admitted PDC000514 / Reactome V97 internal-validation source.");
    for (const field of ["source_catalog_digest", "fitted_model_digest", "training_recipe_digest", "panel_selection_digest", "participant_membership_digest"] as const) {
      if (!digest(provenance[field])) errors.push(`result.provenance.${field} must be a sha256 digest.`);
    }
    if (provenance.source_catalog_digest !== result.source_catalog_digest || provenance.fitted_model_digest !== result.fitted_model_digest) {
      errors.push("result source/model digests must close with provenance.");
    }
  }
  const limitations = strings(result.limitations);
  if (!limitations || limitations.length < 1 || limitations.length > 24) errors.push("result.limitations must contain 1 through 24 non-empty entries.");
  return errors;
}

export function validateComplexTransitionResultRequestBinding(
  result: JsonObject,
  request: JsonObject,
): string[] {
  const errors: string[] = [];
  if (result.series_id !== request.series_id) errors.push("result.series_id must match the submitted request.");
  if (request.profile_id !== undefined && result.profile_id !== request.profile_id) errors.push("result.profile_id must match the submitted request.");
  if (!sameJson(result.assay_compatibility, request.assay_compatibility)) errors.push("result.assay_compatibility must exactly match the submitted request.");
  if (!sameJson(result.normalization_reference, request.normalization_reference)) errors.push("result.normalization_reference must exactly match the submitted request.");
  const requestPoints = Array.isArray(request.time_points) ? request.time_points : [];
  const requestIds = requestPoints.flatMap((item) => isJsonObject(item) && typeof item.time_point_id === "string" ? [item.time_point_id] : []);
  if (!sameJson(result.time_point_ids, requestIds)) errors.push("result.time_point_ids must exactly match the submitted request order.");
  return errors;
}

export function validateComplexTransitionResultProfileBinding(
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors = validateComplexTransitionProfile(profile);
  if (result.profile_digest !== profile.profile_digest) errors.push("result.profile_digest must match the admitted loaded profile.");
  const digests = objectAt(profile, ["digests"]);
  if (digests && (
    result.source_catalog_digest !== digests.source_catalog_content_digest
    || result.fitted_model_digest !== digests.fitted_content_digest
  )) errors.push("result source/model digests must match the admitted loaded profile.");
  const profileComplexes = Array.isArray(profile.complexes) ? profile.complexes : [];
  const transitions = Array.isArray(result.transitions) ? result.transitions : [];
  transitions.forEach((transition, transitionIndex) => {
    if (!isJsonObject(transition) || !Array.isArray(transition.complexes)) return;
    if (transition.complexes.length !== profileComplexes.length) {
      errors.push(`result.transitions[${transitionIndex}] must contain every loaded profile participant set.`);
      return;
    }
    transition.complexes.forEach((item, index) => {
      const expected = profileComplexes[index];
      if (!isJsonObject(item) || !isJsonObject(expected)) return;
      if (
        item.reactome_id !== expected.reactome_id
        || item.domain_id !== expected.domain_id
        || item.family_id !== expected.family_id
        || item.complex_name !== expected.complex_name
      ) errors.push(`result.transitions[${transitionIndex}].complexes[${index}] does not match the loaded profile identity.`);
    });
  });
  return errors;
}

function validateDigestHeader(headers: HeaderReader, name: string, expected: JsonValue | undefined, errors: string[]): void {
  const value = headers.get(name);
  if (!digest(value ?? undefined)) errors.push(`${name} response header must be a lowercase sha256 digest.`);
  else if (value !== expected) errors.push(`${name} response header must match the admitted payload.`);
}

export function validateComplexTransitionProfileHeaders(headers: HeaderReader, profile: JsonObject): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", profile.profile_digest, errors);
  return errors;
}

export function validateComplexTransitionResultHeaders(headers: HeaderReader, result: JsonObject): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", result.profile_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Request-Digest", result.request_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Result-Digest", result.result_digest, errors);
  return errors;
}

export function validateComplexTransitionVerification(
  verification: JsonObject,
  result: JsonObject,
  profile: JsonObject,
): string[] {
  const errors: string[] = [];
  exactFields(verification, VERIFICATION_FIELDS, "verification", errors);
  const semanticFields = [
    "transition_topology_match",
    "complex_semantic_match",
    "uncertainty_semantic_match",
    "ablation_semantic_match",
    "provenance_match",
    "document_semantic_match",
  ] as const;
  const digestFields = ["request_digest_match", "profile_digest_match", "result_digest_match"] as const;
  for (const field of [...semanticFields, ...digestFields, "semantic_match", "verified"] as const) {
    if (typeof verification[field] !== "boolean") errors.push(`verification.${field} must be Boolean.`);
  }
  const semantic = semanticFields.every((field) => verification[field] === true);
  if (verification.semantic_match !== semantic) errors.push("verification.semantic_match does not close its semantic checks.");
  const verified = digestFields.every((field) => verification[field] === true) && semantic;
  if (verification.verified !== verified) errors.push("verification.verified does not close all digest and semantic checks.");
  for (const field of ["recomputed_request_digest", "recomputed_result_digest", "authoritative_profile_digest"] as const) {
    if (!digest(verification[field])) errors.push(`verification.${field} must be a lowercase sha256 digest.`);
  }
  if (verification.request_digest_match === true && verification.recomputed_request_digest !== result.request_digest) {
    errors.push("verification recomputed request digest does not match the admitted result binding.");
  }
  if (verification.result_digest_match === true && verification.recomputed_result_digest !== result.result_digest) {
    errors.push("verification recomputed result digest does not match the admitted result.");
  }
  if (
    verification.authoritative_profile_digest !== profile.profile_digest
    || (verification.profile_digest_match === true && verification.authoritative_profile_digest !== result.profile_digest)
  ) errors.push("verification authoritative profile digest does not match the admitted profile/result binding.");
  if (typeof verification.message !== "string" || !verification.message.trim()) errors.push("verification.message must be non-empty.");
  return errors;
}

export function validateComplexTransitionVerificationHeaders(
  headers: HeaderReader,
  verification: JsonObject,
): string[] {
  const errors: string[] = [];
  validateDigestHeader(headers, "X-GLIO-Profile-Digest", verification.authoritative_profile_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Request-Digest", verification.recomputed_request_digest, errors);
  validateDigestHeader(headers, "X-GLIO-Result-Digest", verification.recomputed_result_digest, errors);
  return errors;
}

function normalizeUncertainty(
  value: JsonObject | null,
): ComplexTransitionUncertainty {
  return {
    state: value ? textAt(value, ["state"], "not_estimable") : "not_estimable",
    measurementStandardError: value
      ? numberAt(value, ["measurement_standard_error"])
      : null,
    fittedModelStandardError: value
      ? numberAt(value, ["fitted_model_standard_error"])
      : null,
    measurementModelCovariance: value
      ? numberAt(value, ["measurement_model_covariance"])
      : null,
    combinedStandardError: value
      ? numberAt(value, ["combined_standard_error"])
      : null,
    varianceClosureResidual: value
      ? numberAt(value, ["variance_closure_residual"])
      : null,
    bootstrapReplicates: value
      ? numberAt(value, ["bootstrap_replicates_used"]) ?? 0
      : 0,
    reason: value ? textAt(value, ["reason"]) : "",
  };
}

function normalizeContribution(value: JsonValue): ComplexMemberContribution | null {
  if (!isJsonObject(value)) return null;
  const geneSymbol = textAt(value, ["gene_symbol"]);
  if (!geneSymbol) return null;
  return {
    geneSymbol,
    standardizedDelta: numberAt(value, ["standardized_delta"]),
    memberLoading: numberAt(value, ["member_loading"]),
    reliabilityWeight: numberAt(value, ["reliability_weight"]),
    contribution: numberAt(value, ["contribution"]),
    direction: textAt(value, ["direction"], "indeterminate"),
  };
}

function normalizeAblation(value: JsonValue): ComplexAblation | null {
  if (!isJsonObject(value)) return null;
  const support = supportValue(textAt(value, ["support"]));
  const kind = textAt(value, ["component_kind"]);
  if (!support || !kind) return null;
  return {
    kind,
    componentId: textAt(value, ["component_id"], "unspecified-component"),
    support,
    scoreWithout: numberAt(value, ["score_without_component"]),
    scoreDelta: numberAt(value, ["score_delta"]),
    classificationWithout: textAt(
      value,
      ["classification_without_component"],
      "not_estimable",
    ),
    removedMemberCount: numberAt(value, ["removed_member_count"]) ?? 0,
    reason: textAt(value, ["reason"]),
  };
}

function normalizeComplex(value: JsonValue): ComplexMemberConcordance | null {
  if (!isJsonObject(value)) return null;
  const support = supportValue(textAt(value, ["support"]));
  const reactomeId = textAt(value, ["reactome_id"]);
  if (!support || !reactomeId) return null;
  const ablations = objectAt(value, ["ablations"]);
  const ablationValues = ablations
    ? [
      ablations.source_processing,
      ablations.uniform_member_loading,
      ablations.top_member,
      ablations.nested_family,
    ]
    : [];
  return {
    complexIndex: numberAt(value, ["complex_index"]) ?? 0,
    domainId: textAt(value, ["domain_id"], reactomeId),
    reactomeId,
    complexName: textAt(value, ["complex_name"], reactomeId),
    familyId: textAt(value, ["family_id"], reactomeId),
    support,
    classification: textAt(value, ["classification"], "not_estimable"),
    score: numberAt(value, ["score"]),
    lower: numberAt(value, ["lower_bound"]),
    upper: numberAt(value, ["upper_bound"]),
    activeMemberCount: numberAt(value, ["active_member_count"]) ?? 0,
    observedMemberCount: numberAt(value, ["observed_member_count"]) ?? 0,
    leftCensoredMemberCount: numberAt(value, ["left_censored_member_count"]) ?? 0,
    coefficientMassCoverage: numberAt(value, ["coefficient_mass_coverage"]) ?? 0,
    effectiveSampleSize: numberAt(value, ["effective_sample_size"]),
    coherence: numberAt(value, ["coherence"]),
    discordance: numberAt(value, ["discordance"]),
    stability: numberAt(value, ["stability"]),
    sourceHeldMemberRelativeGain: numberAt(
      value,
      ["source_held_member_relative_gain"],
    ),
    sourceDirectionAccuracy: numberAt(value, ["source_direction_accuracy"]),
    sourceMinimumOuterLoadingCosine: numberAt(
      value,
      ["source_minimum_outer_loading_cosine"],
    ),
    uncertainty: normalizeUncertainty(objectAt(value, ["uncertainty"])),
    contributions: arrayAt(value, ["top_contributions"])
      .flatMap((item) => normalizeContribution(item) ?? []),
    ablations: ablationValues.flatMap(
      (item) => normalizeAblation(item as JsonValue) ?? [],
    ),
    reasons: stringValues(value.limitations),
    raw: value,
  };
}

export function normalizeComplexTransitions(result: JsonObject): ComplexTransition[] {
  return arrayAt(result, ["transitions"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const complexes = arrayAt(value, ["complexes"])
      .flatMap((item) => normalizeComplex(item) ?? [])
      .sort((left, right) => left.complexIndex - right.complexIndex);
    return [{
      id: textAt(value, ["transition_id"], "unnamed-transition"),
      index: numberAt(value, ["transition_index"]) ?? 0,
      fromTimePointId: textAt(value, ["from_time_point_id"], "unknown-from"),
      toTimePointId: textAt(value, ["to_time_point_id"], "unknown-to"),
      durationDays: numberAt(value, ["duration_days"]),
      complexes,
      raw: value,
    }];
  });
}

export function normalizeComplexEvaluation(
  profile: JsonObject | null,
): ComplexEvaluationSummary | null {
  const value = profile ? objectAt(profile, ["evaluation"]) : null;
  if (!value) return null;
  const interval = arrayAt(value, ["patient_cluster_median_gain_90_interval"]);
  return {
    validationScope: textAt(value, ["validation_scope"], "not reported"),
    patientCount: numberAt(value, ["patient_count"]) ?? 0,
    evaluationCount: numberAt(value, ["evaluation_count"]) ?? 0,
    zeroTransitionMeanMae: numberAt(
      value,
      ["zero_transition_mean_standardized_mae"],
    ),
    trainingCenterMeanMae: numberAt(
      value,
      ["training_center_mean_standardized_mae"],
    ),
    factorModelMeanMae: numberAt(value, ["factor_model_mean_standardized_mae"]),
    meanRelativeGain: numberAt(
      value,
      ["mean_relative_gain_over_training_center"],
    ),
    patientClusterInterval: [
      typeof interval[0] === "number" && Number.isFinite(interval[0])
        ? interval[0]
        : null,
      typeof interval[1] === "number" && Number.isFinite(interval[1])
        ? interval[1]
        : null,
    ],
    directionAccuracy: numberAt(value, ["held_member_direction_accuracy"]),
    minimumOuterLoadingCosine: numberAt(
      value,
      ["minimum_outer_loading_cosine"],
    ),
    nonconvergedReferenceFitCount:
      numberAt(value, ["nonconverged_reference_fit_count"]) ?? 0,
    nonconvergedOuterFitCount:
      numberAt(value, ["nonconverged_outer_fit_count"]) ?? 0,
    externalValidationPerformed: value.external_validation_performed === true,
  };
}

export function complexResultCount(transitions: ComplexTransition[]): number {
  return transitions.reduce(
    (count, transition) => count + transition.complexes.length,
    0,
  );
}

export function complexEstimatedCount(transitions: ComplexTransition[]): number {
  return transitions.reduce(
    (count, transition) =>
      count + transition.complexes.filter((item) => item.score !== null).length,
    0,
  );
}

export function complexSupportedCount(transitions: ComplexTransition[]): number {
  return transitions.reduce(
    (count, transition) =>
      count
      + transition.complexes.filter((item) => item.support === "supported").length,
    0,
  );
}
