import { graphTopologyDigest } from "./topology-provenance";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type StateKind = "protein" | "proteoform" | "phosphosite" | "complex" | "pathway" | "kinase" | "other";

export type NormalizedState = {
  id: string;
  label: string;
  kind: StateKind;
  estimate: number | null;
  lower: number | null;
  upper: number | null;
  classification: string;
  evidenceCount: number | null;
  stability: number | null;
  discordance: number | null;
  qValue: number | null;
  support: string;
  abstentionReason: string;
  drivers: string[];
  raw: JsonObject;
};

export type NormalizedAblation = {
  target: string;
  family: string;
  delta: number | null;
  detail: string;
};

export function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rejectDuplicateJsonKeys(source: string): void {
  let cursor = 0;

  const skipWhitespace = () => {
    while (/\s/.test(source[cursor] ?? "")) cursor += 1;
  };
  const readString = (): string => {
    const start = cursor;
    cursor += 1;
    while (cursor < source.length) {
      if (source[cursor] === "\\") cursor += 2;
      else if (source[cursor] === '"') {
        cursor += 1;
        return JSON.parse(source.slice(start, cursor)) as string;
      } else cursor += 1;
    }
    return "";
  };
  const scanValue = (path: string): void => {
    skipWhitespace();
    if (source[cursor] === "{") {
      cursor += 1;
      const keys = new Set<string>();
      skipWhitespace();
      while (source[cursor] !== "}") {
        const key = readString();
        if (keys.has(key)) throw new Error(`Duplicate JSON key ${path}.${key}.`);
        keys.add(key);
        skipWhitespace();
        cursor += 1; // colon; JSON.parse already established valid syntax.
        scanValue(`${path}.${key}`);
        skipWhitespace();
        if (source[cursor] === ",") {
          cursor += 1;
          skipWhitespace();
        }
      }
      cursor += 1;
      return;
    }
    if (source[cursor] === "[") {
      cursor += 1;
      let index = 0;
      skipWhitespace();
      while (source[cursor] !== "]") {
        scanValue(`${path}[${index}]`);
        index += 1;
        skipWhitespace();
        if (source[cursor] === ",") {
          cursor += 1;
          skipWhitespace();
        }
      }
      cursor += 1;
      return;
    }
    if (source[cursor] === '"') {
      readString();
      return;
    }
    while (cursor < source.length && !/[\s,}\]]/.test(source[cursor] ?? "")) {
      cursor += 1;
    }
  };

  scanValue("request");
}

export function parseJsonObject(source: string): JsonObject {
  const parsed: unknown = JSON.parse(source);
  rejectDuplicateJsonKeys(source);
  if (!isJsonObject(parsed)) throw new Error("The request must be a JSON object.");
  return parsed;
}

export function textAt(source: JsonObject, keys: string[], fallback = ""): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
  }
  return fallback;
}

export function numberAt(source: JsonObject, keys: string[]): number | null {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function objectAt(source: JsonObject, keys: string[]): JsonObject | null {
  for (const key of keys) {
    const value = source[key];
    if (isJsonObject(value)) return value;
  }
  return null;
}

export function arrayAt(source: JsonObject, keys: string[]): JsonValue[] {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) return value;
  }
  return [];
}

function canonicalKind(value: string): StateKind {
  const normalized = value.toLowerCase().replaceAll("_", "").replaceAll("-", "");
  if (normalized.includes("phosphosite") || normalized === "site") return "phosphosite";
  if (normalized.includes("proteoform")) return "proteoform";
  if (normalized.includes("protein")) return "protein";
  if (normalized.includes("complex")) return "complex";
  if (normalized.includes("pathway")) return "pathway";
  if (normalized.includes("kinase")) return "kinase";
  return "other";
}

function intervalFromState(state: JsonObject): { lower: number | null; upper: number | null } {
  const interval = objectAt(state, ["interval", "confidence_interval", "bootstrap_interval", "uncertainty"]);
  return {
    lower: numberAt(state, ["lower", "lower_bound", "ci_lower", "interval_low"]) ??
      (interval ? numberAt(interval, ["lower", "low", "minimum", "p05"]) : null),
    upper: numberAt(state, ["upper", "upper_bound", "ci_upper", "interval_high"]) ??
      (interval ? numberAt(interval, ["upper", "high", "maximum", "p95"]) : null),
  };
}

function textList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string" || typeof item === "number") return [String(item)];
    if (!isJsonObject(item)) return [];
    const label = textAt(item, ["label", "driver_id", "id", "node_id", "source_id", "evidence_id", "family"]);
    const contribution = numberAt(item, ["signed_contribution", "contribution", "weight", "delta", "effect"]);
    return label ? [`${label}${contribution === null ? "" : ` (${formatSigned(contribution)})`}`] : [];
  });
}

function normalizeOne(raw: JsonObject, hintedKind?: string): NormalizedState {
  const interval = intervalFromState(raw);
  const id = textAt(raw, ["node_id", "entity_id", "kinase_id", "complex_id", "pathway_id", "id"], "unnamed");
  const kind = canonicalKind(textAt(raw, ["node_type", "entity_type", "kind", "type"], hintedKind ?? "other"));
  return {
    id,
    label: textAt(raw, ["label", "name", "display_name"], id),
    kind,
    estimate: numberAt(raw, ["estimate", "activity", "score", "latent_activity", "effect"]),
    lower: interval.lower,
    upper: interval.upper,
    classification: textAt(raw, ["classification", "state", "activity_state", "direction"], "indeterminate"),
    evidenceCount: numberAt(raw, ["evidence_count", "observation_count", "n_evidence", "support_count"]),
    stability: numberAt(raw, ["stability", "bootstrap_stability", "selection_frequency"]),
    discordance: numberAt(raw, ["discordance", "discordance_score"]),
    qValue: numberAt(raw, ["q_value", "qvalue", "adjusted_p_value", "fdr"]),
    // Missing support metadata must never be promoted into a full-support claim.
    // Authoritative ECGI receipts are validated before normalization, but this
    // fail-closed fallback also protects generic/partial rendering call sites.
    support: textAt(raw, ["support", "support_state", "status"], "abstained"),
    abstentionReason: textAt(raw, ["abstention_reason", "abstain_reason", "unsupported_reason"]),
    drivers: textList(raw.top_drivers ?? raw.drivers ?? raw.evidence_drivers),
    raw,
  };
}

const STATE_COLLECTIONS: Array<[StateKind, string[]]> = [
  ["protein", ["protein_states", "proteins"]],
  ["proteoform", ["proteoform_states", "proteoforms"]],
  ["phosphosite", ["phosphosite_states", "phosphosites"]],
  ["complex", ["complex_states", "complexes"]],
  ["pathway", ["pathway_states", "pathways"]],
  ["kinase", ["kinase_states", "kinases"]],
];

export function normalizeStates(result: JsonObject): NormalizedState[] {
  const found: NormalizedState[] = [];
  const generic = arrayAt(result, ["node_states", "states", "entities"]);
  for (const raw of generic) if (isJsonObject(raw)) found.push(normalizeOne(raw));
  for (const [kind, aliases] of STATE_COLLECTIONS) {
    for (const raw of arrayAt(result, aliases)) if (isJsonObject(raw)) found.push(normalizeOne(raw, kind));
  }
  const unique = new Map<string, NormalizedState>();
  for (const state of found) unique.set(`${state.kind}:${state.id}`, state);
  return [...unique.values()];
}

export function normalizeAblations(result: JsonObject, states: NormalizedState[]): NormalizedAblation[] {
  const rows: NormalizedAblation[] = [];
  for (const item of arrayAt(result, ["ablations", "ablation_effects", "sensitivity_analyses"])) {
    if (!isJsonObject(item)) continue;
    const kind = textAt(item, ["kind"]);
    const omitted = textAt(item, ["omitted"]);
    rows.push({
      target: textAt(item, ["target", "node_id", "entity_id"], "global"),
      family: kind && omitted ? `${kind} · ${omitted}` : textAt(item, ["omitted", "family", "edge_family", "modality", "source"], "unspecified"),
      delta: numberAt(item, ["activity_delta", "delta", "effect", "score_change", "estimate_change"]),
      detail: textAt(item, ["detail", "interpretation", "description"]),
    });
  }
  for (const state of states) {
    for (const item of arrayAt(state.raw, ["ablation_effects", "ablations"])) {
      if (!isJsonObject(item)) continue;
      const kind = textAt(item, ["kind"]);
      const omitted = textAt(item, ["omitted"]);
      rows.push({
        target: state.label,
        family: kind && omitted ? `${kind} · ${omitted}` : textAt(item, ["omitted", "family", "edge_family", "modality", "source"], "unspecified"),
        delta: numberAt(item, ["activity_delta", "delta", "effect", "score_change", "estimate_change"]),
        detail: textAt(item, ["detail", "interpretation", "description"]),
      });
    }
  }
  return rows;
}

const IDENTIFIER_PATTERN = /^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$/;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const PROFILE_ID = "glio-ecgi/1.0.0";
const NODE_KINDS = new Set(["protein", "proteoform", "phosphosite", "complex", "pathway", "kinase"]);
const EDGE_KINDS = new Set(["regulates", "member_of", "kinase_substrate", "participates_in", "proteoform_of", "site_of"]);
const EVIDENCE_MODALITIES = new Set(["proteomics", "phosphoproteomics", "transcriptomics", "copy_number", "external"]);
const EVIDENCE_STATES = new Set(["observed", "left_censored", "missing", "unsupported"]);
const TOPOLOGY_DERIVATIONS = new Set(["caller_curated", "synthetic_abstraction"]);
const HTTPS_PATTERN = /^https:\/\/[^\s]+$/;
const ISO_DATE_PATTERN = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/;

function hasOwn(source: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

function rejectUnknownFields(source: JsonObject, allowed: ReadonlySet<string>, path: string, errors: string[]): void {
  const unknown = Object.keys(source).filter((key) => !allowed.has(key));
  if (unknown.length) errors.push(`${path} contains unsupported fields: ${unknown.join(", ")}.`);
}

function requireObject(value: JsonValue | undefined, path: string, errors: string[]): JsonObject | null {
  if (!isJsonObject(value)) {
    errors.push(`${path} must be an object.`);
    return null;
  }
  return value;
}

function requireArray(source: JsonObject, key: string, path: string, errors: string[], required: boolean): JsonValue[] {
  if (!hasOwn(source, key)) {
    if (required) errors.push(`${path} is required.`);
    return [];
  }
  const value = source[key];
  if (!Array.isArray(value)) {
    errors.push(`${path} must be an array.`);
    return [];
  }
  return value;
}

function requireString(source: JsonObject, key: string, path: string, errors: string[]): string | null {
  const value = source[key];
  if (typeof value !== "string") {
    errors.push(`${path} must be a string.`);
    return null;
  }
  return value;
}

function requireIdentifier(source: JsonObject, key: string, path: string, errors: string[]): string | null {
  const value = requireString(source, key, path, errors);
  if (value !== null && !IDENTIFIER_PATTERN.test(value)) {
    errors.push(`${path} must be a valid identifier (1–128 characters, beginning with a letter).`);
    return null;
  }
  return value;
}

function requireEnum(source: JsonObject, key: string, path: string, allowed: ReadonlySet<string>, errors: string[]): string | null {
  const value = requireString(source, key, path, errors);
  if (value !== null && !allowed.has(value)) {
    errors.push(`${path} must be one of: ${[...allowed].join(", ")}.`);
    return null;
  }
  return value;
}

function boundedNumber(
  source: JsonObject,
  key: string,
  path: string,
  errors: string[],
  options: { required: boolean; nullable?: boolean; minimum: number; maximum: number; exclusiveMinimum?: boolean },
): number | null {
  if (!hasOwn(source, key)) {
    if (options.required) errors.push(`${path} is required.`);
    return null;
  }
  const value = source[key];
  if (value === null && options.nullable) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    errors.push(`${path} must be a finite number${options.nullable ? " or null" : ""}.`);
    return null;
  }
  const below = options.exclusiveMinimum ? value <= options.minimum : value < options.minimum;
  if (below || value > options.maximum) {
    const opening = options.exclusiveMinimum ? "(" : "[";
    errors.push(`${path} must be within ${opening}${options.minimum}, ${options.maximum}].`);
    return null;
  }
  return value;
}

function boundedInteger(source: JsonObject, key: string, path: string, minimum: number, maximum: number, errors: string[]): void {
  if (!hasOwn(source, key)) return;
  const value = source[key];
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum || value > maximum) {
    errors.push(`${path} must be an integer from ${minimum} through ${maximum}.`);
  }
}

function duplicateValues(values: string[]): string[] {
  return [...new Set(values.filter((value, index) => values.indexOf(value) !== index))];
}

function displayName(source: JsonObject, key: string, path: string, errors: string[]): string | null {
  const value = requireString(source, key, path, errors);
  if (value !== null && (value.length < 1 || value.length > 160)) errors.push(`${path} must contain 1–160 characters.`);
  return value;
}

function httpsUrl(source: JsonObject, key: string, path: string, errors: string[]): string | null {
  const value = requireString(source, key, path, errors);
  if (value !== null && (value.length > 512 || !HTTPS_PATTERN.test(value))) errors.push(`${path} must be an HTTPS URL of at most 512 characters.`);
  return value;
}

export function validateResearchRequest(request: JsonObject): string[] {
  const errors: string[] = [];
  rejectUnknownFields(request, new Set([
    "profile_id", "sample_id", "nodes", "edges", "observations", "bootstrap_replicates",
    "permutation_replicates", "external_kinase_profile", "topology_provenance",
  ]), "request", errors);

  if (hasOwn(request, "profile_id")) {
    const profileId = requireString(request, "profile_id", "profile_id", errors);
    if (profileId !== null && profileId !== PROFILE_ID) errors.push(`profile_id must equal ${PROFILE_ID}.`);
  }
  requireIdentifier(request, "sample_id", "sample_id", errors);
  boundedInteger(request, "bootstrap_replicates", "bootstrap_replicates", 8, 256, errors);
  boundedInteger(request, "permutation_replicates", "permutation_replicates", 32, 2048, errors);

  const nodes = requireArray(request, "nodes", "nodes", errors, true);
  if (nodes.length === 0) errors.push("At least one graph node is required.");
  if (nodes.length > 256) errors.push("The graph exceeds the 256-node limit.");
  const edges = requireArray(request, "edges", "edges", errors, false);
  if (edges.length > 2048) errors.push("The graph exceeds the 2,048-edge limit.");
  const observations = requireArray(request, "observations", "observations", errors, false);
  if (observations.length > 4096) errors.push("The request exceeds the 4,096-observation limit.");

  const nodeIds: string[] = [];
  const nodeKinds = new Map<string, string>();
  nodes.forEach((value, index) => {
    const path = `nodes[${index}]`;
    const node = requireObject(value, path, errors);
    if (!node) return;
    rejectUnknownFields(node, new Set(["node_id", "kind", "display_name"]), path, errors);
    const nodeId = requireIdentifier(node, "node_id", `${path}.node_id`, errors);
    const kind = requireEnum(node, "kind", `${path}.kind`, NODE_KINDS, errors);
    if (hasOwn(node, "display_name") && node.display_name !== null) {
      const displayName = requireString(node, "display_name", `${path}.display_name`, errors);
      if (displayName !== null && (displayName.length < 1 || displayName.length > 160)) {
        errors.push(`${path}.display_name must contain 1–160 characters.`);
      }
    }
    if (nodeId !== null) nodeIds.push(nodeId);
    if (nodeId !== null && kind !== null) nodeKinds.set(nodeId, kind);
  });
  const duplicateNodes = duplicateValues(nodeIds);
  if (duplicateNodes.length) errors.push(`Duplicate node identifiers: ${duplicateNodes.join(", ")}.`);
  const kinaseCount = [...nodeKinds.values()].filter((kind) => kind === "kinase").length;
  if (kinaseCount > 128) errors.push("The graph exceeds the 128-kinase limit.");

  const edgeIds: string[] = [];
  const semanticRelations: string[] = [];
  edges.forEach((value, index) => {
    const path = `edges[${index}]`;
    const edge = requireObject(value, path, errors);
    if (!edge) return;
    rejectUnknownFields(edge, new Set(["edge_id", "source_id", "target_id", "kind", "sign", "weight", "essential"]), path, errors);
    const edgeId = requireIdentifier(edge, "edge_id", `${path}.edge_id`, errors);
    const sourceId = requireIdentifier(edge, "source_id", `${path}.source_id`, errors);
    const targetId = requireIdentifier(edge, "target_id", `${path}.target_id`, errors);
    const kind = requireEnum(edge, "kind", `${path}.kind`, EDGE_KINDS, errors);
    const sign = boundedNumber(edge, "sign", `${path}.sign`, errors, { required: true, minimum: -1, maximum: 1 });
    if (sign !== null && sign !== -1 && sign !== 1) errors.push(`${path}.sign must be exactly -1 or 1.`);
    boundedNumber(edge, "weight", `${path}.weight`, errors, { required: true, minimum: 0.01, maximum: 10 });
    let essential = false;
    if (hasOwn(edge, "essential")) {
      if (typeof edge.essential !== "boolean") errors.push(`${path}.essential must be a boolean.`);
      else essential = edge.essential;
    }
    if (edgeId !== null) edgeIds.push(edgeId);
    if (sourceId !== null && targetId !== null && kind !== null) {
      semanticRelations.push(`${sourceId}\u0000${targetId}\u0000${kind}`);
    }
    if (sourceId !== null && !nodeKinds.has(sourceId)) errors.push(`${path}.source_id references an unresolved node.`);
    if (targetId !== null && !nodeKinds.has(targetId)) errors.push(`${path}.target_id references an unresolved node.`);
    if (sourceId !== null && targetId !== null && sourceId === targetId) errors.push(`${path} cannot be a self edge.`);
    if (essential && kind !== null && kind !== "member_of") errors.push(`${path}.essential is only valid for member_of edges.`);
    if (kind !== null && sign !== null && ["member_of", "proteoform_of", "site_of"].includes(kind) && sign !== 1) {
      errors.push(`${path}.${kind} edges must have positive sign.`);
    }
    if (sourceId === null || targetId === null || kind === null) return;
    const sourceKind = nodeKinds.get(sourceId);
    const targetKind = nodeKinds.get(targetId);
    if (!sourceKind || !targetKind) return;
    if (kind === "member_of" && (!(["protein", "proteoform"].includes(sourceKind)) || targetKind !== "complex")) {
      errors.push(`${path}.member_of requires a protein/proteoform source and complex target.`);
    }
    if (kind === "kinase_substrate" && (sourceKind !== "kinase" || targetKind !== "phosphosite")) {
      errors.push(`${path}.kinase_substrate requires a kinase source and phosphosite target.`);
    }
    if (kind === "participates_in" && targetKind !== "pathway") {
      errors.push(`${path}.participates_in must target a pathway.`);
    }
    if (kind === "proteoform_of" && (sourceKind !== "proteoform" || targetKind !== "protein")) {
      errors.push(`${path}.proteoform_of requires a proteoform source and protein target.`);
    }
    if (kind === "site_of" && (sourceKind !== "phosphosite" || !["proteoform", "protein"].includes(targetKind))) {
      errors.push(`${path}.site_of requires a phosphosite source and proteoform/protein target.`);
    }
  });
  const duplicateEdges = duplicateValues(edgeIds);
  if (duplicateEdges.length) errors.push(`Duplicate edge identifiers: ${duplicateEdges.join(", ")}.`);
  if (duplicateValues(semanticRelations).length) errors.push("Parallel semantic relations are not supported.");

  const observationIds: string[] = [];
  observations.forEach((value, index) => {
    const path = `observations[${index}]`;
    const observation = requireObject(value, path, errors);
    if (!observation) return;
    rejectUnknownFields(observation, new Set([
      "observation_id", "node_id", "modality", "state", "standardized_effect", "standard_error",
      "quality_weight", "provenance_digest",
    ]), path, errors);
    const observationId = requireIdentifier(observation, "observation_id", `${path}.observation_id`, errors);
    const nodeId = requireIdentifier(observation, "node_id", `${path}.node_id`, errors);
    requireEnum(observation, "modality", `${path}.modality`, EVIDENCE_MODALITIES, errors);
    const state = requireEnum(observation, "state", `${path}.state`, EVIDENCE_STATES, errors);
    const effect = boundedNumber(observation, "standardized_effect", `${path}.standardized_effect`, errors, {
      required: false, nullable: true, minimum: -20, maximum: 20,
    });
    const standardError = boundedNumber(observation, "standard_error", `${path}.standard_error`, errors, {
      required: false, nullable: true, minimum: 0, maximum: 20, exclusiveMinimum: true,
    });
    const qualityWeight = hasOwn(observation, "quality_weight")
      ? boundedNumber(observation, "quality_weight", `${path}.quality_weight`, errors, { required: true, minimum: 0, maximum: 1 })
      : 1;
    const provenance = requireString(observation, "provenance_digest", `${path}.provenance_digest`, errors);
    if (provenance !== null && !SHA256_PATTERN.test(provenance)) errors.push(`${path}.provenance_digest must be a lowercase sha256 digest.`);
    if (observationId !== null) observationIds.push(observationId);
    if (nodeId !== null && !nodeKinds.has(nodeId)) errors.push(`${path}.node_id references an unresolved node.`);
    if (state === "observed" || state === "left_censored") {
      if (effect === null || standardError === null) errors.push(`${path} active evidence requires an effect and standard error.`);
      if (qualityWeight !== null && qualityWeight <= 0) errors.push(`${path} active evidence requires a positive quality weight.`);
    } else if ((state === "missing" || state === "unsupported") && (effect !== null || standardError !== null)) {
      errors.push(`${path} missing/unsupported evidence cannot carry numeric effects.`);
    }
  });
  const duplicateObservations = duplicateValues(observationIds);
  if (duplicateObservations.length) errors.push(`Duplicate observation identifiers: ${duplicateObservations.join(", ")}.`);

  if (hasOwn(request, "external_kinase_profile") && request.external_kinase_profile !== null) {
    const profile = requireObject(request.external_kinase_profile, "external_kinase_profile", errors);
    if (profile) {
      rejectUnknownFields(profile, new Set(["profile_id", "source_digest", "estimates"]), "external_kinase_profile", errors);
      requireIdentifier(profile, "profile_id", "external_kinase_profile.profile_id", errors);
      const sourceDigest = requireString(profile, "source_digest", "external_kinase_profile.source_digest", errors);
      if (sourceDigest !== null && !SHA256_PATTERN.test(sourceDigest)) errors.push("external_kinase_profile.source_digest must be a lowercase sha256 digest.");
      const estimates = requireArray(profile, "estimates", "external_kinase_profile.estimates", errors, true);
      if (estimates.length < 1 || estimates.length > 128) errors.push("external_kinase_profile.estimates must contain 1–128 entries.");
      const externalIds: string[] = [];
      estimates.forEach((value, index) => {
        const path = `external_kinase_profile.estimates[${index}]`;
        const estimate = requireObject(value, path, errors);
        if (!estimate) return;
        rejectUnknownFields(estimate, new Set(["kinase_id", "activity", "lower_bound", "upper_bound"]), path, errors);
        const kinaseId = requireIdentifier(estimate, "kinase_id", `${path}.kinase_id`, errors);
        const activity = boundedNumber(estimate, "activity", `${path}.activity`, errors, { required: true, minimum: -20, maximum: 20 });
        const lower = boundedNumber(estimate, "lower_bound", `${path}.lower_bound`, errors, { required: true, minimum: -20, maximum: 20 });
        const upper = boundedNumber(estimate, "upper_bound", `${path}.upper_bound`, errors, { required: true, minimum: -20, maximum: 20 });
        if (kinaseId !== null) {
          externalIds.push(kinaseId);
          if (nodeKinds.get(kinaseId) !== "kinase") errors.push(`${path}.kinase_id must exactly match a kinase node ID.`);
        }
        if (activity !== null && lower !== null && upper !== null && !(lower <= activity && activity <= upper)) {
          errors.push(`${path} interval must contain its activity.`);
        }
      });
      const duplicateExternal = duplicateValues(externalIds);
      if (duplicateExternal.length) errors.push(`Duplicate external kinase identifiers: ${duplicateExternal.join(", ")}.`);
    }
  }

  if (hasOwn(request, "topology_provenance") && request.topology_provenance !== null) {
    const topology = requireObject(request.topology_provenance, "topology_provenance", errors);
    if (topology) {
      rejectUnknownFields(topology, new Set([
        "topology_digest", "derivation", "sources", "curation_note",
      ]), "topology_provenance", errors);
      const topologyDigest = requireString(topology, "topology_digest", "topology_provenance.topology_digest", errors);
      if (topologyDigest !== null && !SHA256_PATTERN.test(topologyDigest)) {
        errors.push("topology_provenance.topology_digest must be a lowercase sha256 digest.");
      }
      requireEnum(topology, "derivation", "topology_provenance.derivation", TOPOLOGY_DERIVATIONS, errors);
      const curationNote = requireString(topology, "curation_note", "topology_provenance.curation_note", errors);
      if (curationNote !== null && (
        curationNote.length < 1 || curationNote.length > 512 || curationNote.trim() !== curationNote
      )) {
        errors.push("topology_provenance.curation_note must contain 1–512 non-blank, unpadded characters.");
      }
      const sources = requireArray(topology, "sources", "topology_provenance.sources", errors, true);
      if (sources.length < 1 || sources.length > 32) {
        errors.push("topology_provenance.sources must contain 1–32 entries.");
      }
      const sourceIds: string[] = [];
      sources.forEach((value, index) => {
        const path = `topology_provenance.sources[${index}]`;
        const source = requireObject(value, path, errors);
        if (!source) return;
        rejectUnknownFields(source, new Set([
          "source_id", "resource_name", "resource_release", "record_id", "record_title",
          "source_uri", "source_format", "source_digest", "source_size_bytes", "license_id",
          "license_uri", "retrieved_on", "scope_node_ids", "role",
        ]), path, errors);
        const sourceId = requireIdentifier(source, "source_id", `${path}.source_id`, errors);
        if (sourceId !== null) sourceIds.push(sourceId);
        displayName(source, "resource_name", `${path}.resource_name`, errors);
        displayName(source, "resource_release", `${path}.resource_release`, errors);
        requireIdentifier(source, "record_id", `${path}.record_id`, errors);
        displayName(source, "record_title", `${path}.record_title`, errors);
        httpsUrl(source, "source_uri", `${path}.source_uri`, errors);
        displayName(source, "source_format", `${path}.source_format`, errors);
        const sourceDigest = requireString(source, "source_digest", `${path}.source_digest`, errors);
        if (sourceDigest !== null && !SHA256_PATTERN.test(sourceDigest)) {
          errors.push(`${path}.source_digest must be a lowercase sha256 digest.`);
        }
        const sourceSize = boundedNumber(source, "source_size_bytes", `${path}.source_size_bytes`, errors, {
          required: true, minimum: 1, maximum: 64 * 1_024 * 1_024,
        });
        if (sourceSize !== null && !Number.isInteger(sourceSize)) errors.push(`${path}.source_size_bytes must be an integer.`);
        requireIdentifier(source, "license_id", `${path}.license_id`, errors);
        httpsUrl(source, "license_uri", `${path}.license_uri`, errors);
        const retrievedOn = requireString(source, "retrieved_on", `${path}.retrieved_on`, errors);
        if (retrievedOn !== null && !ISO_DATE_PATTERN.test(retrievedOn)) {
          errors.push(`${path}.retrieved_on must use YYYY-MM-DD format.`);
        }
        const scope = requireArray(source, "scope_node_ids", `${path}.scope_node_ids`, errors, true);
        if (scope.length < 1 || scope.length > 256) errors.push(`${path}.scope_node_ids must contain 1–256 node identifiers.`);
        const scopeIds: string[] = [];
        scope.forEach((scopeValue, scopeIndex) => {
          if (typeof scopeValue !== "string" || !IDENTIFIER_PATTERN.test(scopeValue)) {
            errors.push(`${path}.scope_node_ids[${scopeIndex}] must be a valid identifier.`);
            return;
          }
          scopeIds.push(scopeValue);
          if (!nodeKinds.has(scopeValue)) errors.push(`${path}.scope_node_ids[${scopeIndex}] references an unresolved node.`);
        });
        const duplicateScope = duplicateValues(scopeIds);
        if (duplicateScope.length) errors.push(`${path}.scope_node_ids contains duplicate node identifiers: ${duplicateScope.join(", ")}.`);
        if (hasOwn(source, "role")) requireEnum(source, "role", `${path}.role`, new Set(["biological_context"]), errors);
      });
      const duplicateSources = duplicateValues(sourceIds);
      if (duplicateSources.length) errors.push(`Duplicate topology source identifiers: ${duplicateSources.join(", ")}.`);
      const calculatedTopologyDigest = graphTopologyDigest(request);
      if (
        topologyDigest !== null &&
        SHA256_PATTERN.test(topologyDigest) &&
        calculatedTopologyDigest !== null &&
        topologyDigest !== calculatedTopologyDigest
      ) {
        errors.push("topology_provenance.topology_digest does not match the canonical nodes and edges.");
      }
    }
  }
  return errors;
}

export function formatNumber(value: number | null, digits = 3): string {
  if (value === null) return "—";
  return value.toFixed(digits).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
}

export function formatSigned(value: number | null, digits = 3): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${formatNumber(value, digits)}`;
}

export function shortDigest(value: string): string {
  return value.replace(/^sha256:/, "").slice(0, 12) || "—";
}

export function requestStats(request: JsonObject): { nodes: number; edges: number; observations: number } {
  return {
    nodes: arrayAt(request, ["nodes", "entities"]).length,
    edges: arrayAt(request, ["relations", "edges"]).length,
    observations: arrayAt(request, ["observations", "evidence"]).length,
  };
}
