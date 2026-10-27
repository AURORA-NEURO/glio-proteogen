import { readBoundedJsonObject } from "./http";

export const REPLICATION_API = "/backend/v1/research/cohort-replication";
export const REPLICATION_INPUT_LIMIT = 2 * 1024 * 1024;
export const REPLICATION_RESPONSE_LIMIT = 4 * 1024 * 1024;
export const REPLICATION_PROFILE_ID = "glioma-cohort-replication/1.0.0";
export const REPLICATION_NETWORK_TIMEOUT_MS = 45_000;

export type ReplicationEffect = {
  cohort_id: string;
  state: string;
  estimate?: number | null;
  standard_error?: number | null;
  reason?: string | null;
};

export type ReplicationCohort = {
  cohort_id: string;
  label?: string;
  [key: string]: unknown;
};

export type PooledEffect = {
  estimate: number;
  standard_error: number;
  lower: number;
  upper: number;
  p_value: number;
};

export type ReplicationFeature = {
  feature_id: string;
  label: string;
  effects: ReplicationEffect[];
  observed_count: number;
  total_count: number;
  support: "limited" | "abstained";
  fixed_effect: PooledEffect | null;
  random_effect: PooledEffect | null;
  heterogeneity: {
    q: number;
    degrees_of_freedom: number;
    i_squared_percent: number;
    tau_squared: number;
  } | null;
  prediction_interval: { lower: number; upper: number; method: string } | null;
  p_value: number | null;
  adjusted_p_value: number;
  dependence_robust_adjusted_p_value: number;
  leave_one_out: {
    omitted_cohort_id: string;
    observed_count: number;
    random_effect: PooledEffect | null;
    delta_estimate: number | null;
  }[];
  direction_agreement: {
    positive_count: number;
    negative_count: number;
    zero_count: number;
    majority_fraction: number | null;
    classification: string;
  };
  reasons: string[];
};

export type ReplicationResult = {
  schema_version: string;
  profile_id: string;
  profile_digest: string;
  analysis_id: string;
  request_digest: string;
  result_digest: string;
  disease_context: string;
  estimand_id: string;
  effect_scale: string;
  contrast: unknown;
  independence_basis: unknown;
  cohorts: ReplicationCohort[];
  features: ReplicationFeature[];
  limitations: string[];
  family_size: number;
  contains_participant_data: false;
};

export type ReplicationRequest = Record<string, unknown>;
export type ReplicationProfile = Record<string, unknown> & { profile_id: string; profile_digest: string };
export type ReplicationVerification = { valid: boolean; request_digest: string; result_digest: string };

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function string(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 8192;
}

function count(value: unknown, maximum = 16): value is number {
  return finite(value) && Number.isInteger(value) && value >= 0 && value <= maximum;
}

function probability(value: unknown): value is number {
  return finite(value) && value >= 0 && value <= 1;
}

function digest(value: unknown): value is string {
  return typeof value === "string" && /^sha256:[a-f0-9]{64}$/.test(value);
}

function pooled(value: unknown): value is PooledEffect | null {
  return value === null || (object(value) && finite(value.estimate) && finite(value.standard_error) && finite(value.lower) && finite(value.upper) && finite(value.p_value)
    && [value.estimate, value.standard_error, value.lower, value.upper].every((number) => Math.abs(number) <= 1e9)
    && value.standard_error > 0 && value.lower <= value.estimate && value.estimate <= value.upper && value.p_value >= 0 && value.p_value <= 1);
}

/** Admit only the display contract; the service remains the scientific validator. */
export function parseReplicationResult(value: unknown): ReplicationResult {
  const invalid = () => { throw new Error("The service returned an incompatible cross-cohort result. No charts were admitted."); };
  if (!object(value)) return invalid();
  if (![value.schema_version, value.profile_id, value.profile_digest, value.analysis_id, value.request_digest, value.result_digest,
    value.disease_context, value.estimand_id, value.effect_scale].every(string)
    || value.schema_version !== "1.0.0" || value.profile_id !== REPLICATION_PROFILE_ID
    || ![value.profile_digest, value.request_digest, value.result_digest].every(digest)
    || !Array.isArray(value.cohorts) || !Array.isArray(value.features) || !Array.isArray(value.limitations)
    || value.cohorts.length < 2 || value.cohorts.length > 16 || value.features.length > 256
    || !value.limitations.every(string) || !count(value.family_size, 256) || value.contains_participant_data !== false
    || !string(value.contrast) || value.independence_basis !== "caller_declared_disjoint_participants") return invalid();
  const ids = new Set<string>();
  for (const cohort of value.cohorts) {
    if (!object(cohort) || !string(cohort.cohort_id) || !string(cohort.label) || !digest(cohort.source_sha256)
      || !string(cohort.independence_group) || !count(cohort.sample_size, 1_000_000) || cohort.sample_size < 2 || ids.has(cohort.cohort_id)) return invalid();
    ids.add(cohort.cohort_id);
  }
  const featureIds = new Set<string>();
  for (const feature of value.features) {
    if (!object(feature) || !string(feature.feature_id) || !string(feature.label) || featureIds.has(feature.feature_id)
      || !Array.isArray(feature.effects) || !count(feature.observed_count) || !count(feature.total_count)
      || !["limited", "abstained"].includes(String(feature.support)) || !pooled(feature.fixed_effect) || !pooled(feature.random_effect)
      || !(feature.p_value === null || probability(feature.p_value))
      || !probability(feature.adjusted_p_value) || !probability(feature.dependence_robust_adjusted_p_value)
      || !Array.isArray(feature.reasons) || !feature.reasons.every(string) || !Array.isArray(feature.leave_one_out)) return invalid();
    featureIds.add(feature.feature_id);
    const effectIds = new Set<string>();
    for (const effect of feature.effects) {
      if (!object(effect) || !string(effect.cohort_id) || !ids.has(effect.cohort_id) || effectIds.has(effect.cohort_id)
        || !["observed", "missing", "unsupported"].includes(String(effect.state))) return invalid();
      effectIds.add(effect.cohort_id);
      if (effect.state === "observed" && (!finite(effect.estimate) || Math.abs(effect.estimate) > 100 || !finite(effect.standard_error) || effect.standard_error < .000001 || effect.standard_error > 100)) return invalid();
      if (effect.state !== "observed" && (effect.estimate !== null || effect.standard_error !== null)) return invalid();
    }
    const observed = feature.effects.filter((effect) => object(effect) && effect.state === "observed").length;
    if (effectIds.size !== ids.size || feature.observed_count !== observed || feature.total_count !== ids.size) return invalid();
    if (observed < 2 && (feature.support !== "abstained" || feature.fixed_effect !== null || feature.random_effect !== null || feature.heterogeneity !== null || feature.p_value !== null || feature.adjusted_p_value !== 1 || feature.dependence_robust_adjusted_p_value !== 1)) return invalid();
    if (observed >= 2 && (feature.support !== "limited" || feature.fixed_effect === null || feature.random_effect === null || feature.heterogeneity === null || feature.p_value === null)) return invalid();
    if (observed < 3 && (feature.prediction_interval !== null || feature.leave_one_out.length !== 0)) return invalid();
    if (feature.heterogeneity !== null && (!object(feature.heterogeneity)
      || !finite(feature.heterogeneity.q) || feature.heterogeneity.q < 0
      || !count(feature.heterogeneity.degrees_of_freedom, 15) || feature.heterogeneity.degrees_of_freedom !== observed - 1
      || !finite(feature.heterogeneity.i_squared_percent) || feature.heterogeneity.i_squared_percent < 0 || feature.heterogeneity.i_squared_percent > 100
      || !finite(feature.heterogeneity.tau_squared) || feature.heterogeneity.tau_squared < 0)) return invalid();
    if (feature.prediction_interval !== null && (!object(feature.prediction_interval)
      || !finite(feature.prediction_interval.lower) || !finite(feature.prediction_interval.upper)
      || Math.abs(feature.prediction_interval.lower) > 1e9 || Math.abs(feature.prediction_interval.upper) > 1e9
      || feature.prediction_interval.lower > feature.prediction_interval.upper
      || feature.prediction_interval.method !== "approximate_normal_random_effects")) return invalid();
    const direction = feature.direction_agreement;
    if (!object(direction) || !count(direction.positive_count) || !count(direction.negative_count) || !count(direction.zero_count)
      || direction.positive_count + direction.negative_count + direction.zero_count !== observed
      || !["all_nominal_intervals_positive", "all_nominal_intervals_negative", "mixed_directions", "direction_indeterminate"].includes(String(direction.classification))
      || !(direction.majority_fraction === null || probability(direction.majority_fraction))) return invalid();
    const omissionIds = new Set<string>();
    for (const omitted of feature.leave_one_out) {
      if (!object(omitted) || !string(omitted.omitted_cohort_id) || !ids.has(omitted.omitted_cohort_id)
        || omissionIds.has(omitted.omitted_cohort_id) || omitted.observed_count !== observed - 1 || !pooled(omitted.random_effect)
        || omitted.random_effect === null || !finite(omitted.delta_estimate)) return invalid();
      omissionIds.add(omitted.omitted_cohort_id);
    }
  }
  if (value.family_size !== value.features.length || value.features.length === 0 || value.cohorts.length === 0) return invalid();
  return value as unknown as ReplicationResult;
}

export function parseReplicationRequest(text: string): ReplicationRequest {
  if (new TextEncoder().encode(text).byteLength > REPLICATION_INPUT_LIMIT) throw new Error("The request exceeds the 2 MiB browser import limit.");
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new Error("Enter a valid JSON object before analyzing."); }
  if (!object(value)) throw new Error("The request must be a JSON object.");
  if (!Array.isArray(value.cohorts) || !Array.isArray(value.features)) throw new Error("The request must include cohort and feature arrays. Load the synthetic demonstration for the contract.");
  return value;
}

export async function replicationFetch(path: string, signal?: AbortSignal, body?: unknown): Promise<Record<string, unknown>> {
  signal?.throwIfAborted();
  const boundedController = new AbortController();
  const cancelFromCaller = () => boundedController.abort(signal?.reason);
  signal?.addEventListener("abort", cancelFromCaller, { once: true });
  let timedOut = false;
  const deadline = setTimeout(() => {
    timedOut = true;
    boundedController.abort();
  }, REPLICATION_NETWORK_TIMEOUT_MS);
  try {
    return await readBoundedJsonObject(await fetch(`${REPLICATION_API}/${path}`, {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store",
      signal: boundedController.signal,
      ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    }), REPLICATION_RESPONSE_LIMIT);
  } catch (cause) {
    if (timedOut && !signal?.aborted) throw new Error("The research service did not finish responding within 45 seconds. Check the service connection, then retry.");
    throw cause;
  } finally {
    clearTimeout(deadline);
    signal?.removeEventListener("abort", cancelFromCaller);
  }
}

export function parseReplicationProfile(value: unknown): ReplicationProfile {
  if (!object(value) || value.profile_id !== REPLICATION_PROFILE_ID || value.schema_version !== "1.0.0" || !digest(value.profile_digest)
    || !digest(value.engine_semantic_digest) || !Array.isArray(value.methods) || !value.methods.every(string)
    || !Array.isArray(value.assumptions) || !value.assumptions.every(string) || value.synthetic_demo_only !== true) {
    throw new Error("The service profile is incompatible with this observatory.");
  }
  return value as ReplicationProfile;
}

export function parseReplicationVerification(value: unknown, result: ReplicationResult): ReplicationVerification {
  if (!object(value) || typeof value.valid !== "boolean" || value.request_digest !== result.request_digest || value.result_digest !== result.result_digest) {
    throw new Error("Replay returned an incompatible verification receipt.");
  }
  return value as ReplicationVerification;
}

export function assertReplicationBinding(request: ReplicationRequest, profile: ReplicationProfile, result: ReplicationResult): void {
  const mismatch = () => { throw new Error("The result does not match the frozen request and active scientific profile. No charts were admitted."); };
  if (result.profile_id !== profile.profile_id || result.profile_digest !== profile.profile_digest) return mismatch();
  for (const field of ["analysis_id", "disease_context", "estimand_id", "effect_scale", "contrast"] as const) {
    if (request[field] !== result[field]) return mismatch();
  }
  if ((request.independence_basis ?? "caller_declared_disjoint_participants") !== result.independence_basis
    || !Array.isArray(request.cohorts) || !Array.isArray(request.features)
    || request.cohorts.length !== result.cohorts.length || request.features.length !== result.features.length) return mismatch();
  for (const submitted of request.cohorts) {
    if (!object(submitted)) return mismatch();
    const admitted = result.cohorts.find((cohort) => cohort.cohort_id === submitted.cohort_id);
    if (!admitted) return mismatch();
    for (const field of ["cohort_id", "label", "source_sha256", "independence_group", "sample_size"]) {
      if (submitted[field] !== admitted[field]) return mismatch();
    }
  }
  for (const submitted of request.features) {
    if (!object(submitted)) return mismatch();
    const admitted = result.features.find((feature) => feature.feature_id === submitted.feature_id);
    if (!admitted || submitted.label !== admitted.label || !Array.isArray(submitted.effects) || submitted.effects.length !== admitted.effects.length) return mismatch();
    for (const effect of submitted.effects) {
      if (!object(effect)) return mismatch();
      const admittedEffect = admitted.effects.find((entry) => entry.cohort_id === effect.cohort_id);
      if (!admittedEffect || effect.state !== admittedEffect.state || (effect.estimate ?? null) !== admittedEffect.estimate
        || (effect.standard_error ?? null) !== admittedEffect.standard_error) return mismatch();
    }
  }
}

export function cohortLabel(cohort: ReplicationCohort): string {
  return typeof cohort.label === "string" && cohort.label ? cohort.label : cohort.cohort_id;
}

export function formatEffect(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const rounded = value.toFixed(digits);
  return Number(rounded) === 0 ? (0).toFixed(digits) : `${value > 0 ? "+" : ""}${rounded}`;
}

export function formatProbability(value: number | null): string {
  if (value === null) return "—";
  if (value === 0) return "< 1e−300";
  return value < 0.001 ? value.toExponential(1) : value.toFixed(3);
}

export function effectFor(feature: ReplicationFeature, cohortId: string): ReplicationEffect | undefined {
  return feature.effects.find((effect) => effect.cohort_id === cohortId);
}

export function forestDomain(feature: ReplicationFeature): [number, number] {
  const values = [0];
  for (const effect of feature.effects) {
    if (effect.state === "observed" && finite(effect.estimate) && finite(effect.standard_error)) {
      values.push(effect.estimate - 1.959963984540054 * effect.standard_error, effect.estimate + 1.959963984540054 * effect.standard_error);
    }
  }
  for (const estimate of [feature.fixed_effect, feature.random_effect, ...feature.leave_one_out.map((entry) => entry.random_effect)]) {
    if (estimate) values.push(estimate.lower, estimate.upper);
  }
  if (feature.prediction_interval) values.push(feature.prediction_interval.lower, feature.prediction_interval.upper);
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.12, 0.1);
  return [minimum - padding, maximum + padding];
}

export function shortReceipt(value: string): string {
  return value.length > 20 ? `${value.slice(0, 12)}…${value.slice(-6)}` : value;
}

/** The strict HTTP /verify and CLI replay contract has exactly these two keys. */
export function replicationReplayEnvelope(request: ReplicationRequest, result: ReplicationResult): { request: ReplicationRequest; result: ReplicationResult } {
  return { request, result };
}
