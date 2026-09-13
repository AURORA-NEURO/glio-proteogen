import { describe, expect, it } from "vitest";

import {
  ecgiProfileDigest,
  ecgiRequestDigest,
  ecgiResultDigest,
  validateEcgiDemo,
  validateEcgiProfile,
  validateEcgiProfileHeaders,
  validateEcgiResult,
  validateEcgiResultHeaders,
  validateEcgiResultProfileBinding,
  validateEcgiResultRequestBinding,
  validateEcgiVerification,
  validateEcgiVerificationHeaders,
  type HeaderReader,
} from "../../src/lib/evidence-graph-admission";
import type { JsonObject } from "../../src/lib/research-state";
import {
  algorithmProfile,
  analysisResult,
  demoRequest,
  verificationResult,
} from "../fixtures/proteogenomic-state";

function copy(value: unknown): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

function headers(values: Record<string, string>): HeaderReader {
  const normalized = Object.fromEntries(
    Object.entries(values).map(([name, value]) => [name.toLowerCase(), value]),
  );
  return { get: (name) => normalized[name.toLowerCase()] ?? null };
}

function resealResult(value: JsonObject): void {
  value.result_digest = ecgiResultDigest(value) as string;
}

const profile = algorithmProfile as JsonObject;
const request = demoRequest as JsonObject;
const result = analysisResult as JsonObject;
const verification = verificationResult as JsonObject;

const profileHeaders = headers({
  "X-GLIO-Profile-Digest": String(profile.profile_digest),
});
const requestHeaders = headers({
  "X-GLIO-Profile-Digest": String(profile.profile_digest),
  "X-GLIO-Request-Digest": String(result.request_digest),
});
const resultHeaders = headers({
  "X-GLIO-Profile-Digest": String(result.profile_digest),
  "X-GLIO-Request-Digest": String(result.request_digest),
  "X-GLIO-Result-Digest": String(result.result_digest),
});

describe("ECGI fail-closed UI receipt admission", () => {
  it("recomputes and admits the locked profile, demo, analysis, and replay receipts", () => {
    expect(ecgiProfileDigest(profile)).toBe(profile.profile_digest);
    expect(ecgiRequestDigest(request)).toBe(result.request_digest);
    expect(ecgiResultDigest(result)).toBe(result.result_digest);
    expect(validateEcgiProfile(profile)).toEqual([]);
    expect(validateEcgiProfileHeaders(profileHeaders, profile)).toEqual([]);
    expect(validateEcgiDemo(request, requestHeaders, profile)).toEqual([]);
    expect(validateEcgiResult(result)).toEqual([]);
    expect(validateEcgiResultRequestBinding(result, request)).toEqual([]);
    expect(validateEcgiResultProfileBinding(result, profile)).toEqual([]);
    expect(validateEcgiResultHeaders(resultHeaders, result)).toEqual([]);
    expect(validateEcgiVerification(verification, result, request, profile)).toEqual([]);
    expect(validateEcgiVerificationHeaders(resultHeaders, verification, profile)).toEqual([]);
  });

  it("rejects profile or demo body mutations hidden behind unchanged digest headers", () => {
    const changedProfile = copy(profile);
    (changedProfile.constants as JsonObject).activation_threshold = 0.5;
    expect(validateEcgiProfile(changedProfile)).toContain(
      "profile.profile_digest does not match the canonical profile content.",
    );

    const changedRequest = copy(request);
    (changedRequest.observations as JsonObject[])[0].standardized_effect = -9;
    expect(validateEcgiDemo(changedRequest, requestHeaders, profile)).toContain(
      "X-GLIO-Request-Digest response header does not match the admitted receipt body.",
    );
  });

  it("rejects a result body mutation or forged response-header digest", () => {
    const changed = copy(result);
    (changed.node_states as JsonObject[])[0].activity = 0.123456;
    expect(validateEcgiResult(changed)).toContain(
      "result.result_digest does not match the canonical result content.",
    );

    const forgedHeaders = headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": `sha256:${"f".repeat(64)}`,
    });
    expect(validateEcgiResultHeaders(forgedHeaders, result)).toContain(
      "X-GLIO-Result-Digest response header does not match the admitted receipt body.",
    );
  });

  it("binds a valid result when topology scope identifiers use caller order", () => {
    const reorderedRequest = copy(request);
    const nodes = reorderedRequest.nodes as JsonObject[];
    const topology = reorderedRequest.topology_provenance as JsonObject;
    const sources = topology.sources as JsonObject[];
    sources[0].scope_node_ids = [nodes[1].node_id, nodes[0].node_id];
    const requestDigest = ecgiRequestDigest(reorderedRequest) as string;

    const reorderedResult = copy(result);
    reorderedResult.request_digest = requestDigest;
    const provenance = reorderedResult.provenance as JsonObject;
    provenance.request_digest = requestDigest;
    provenance.topology = copy(topology);
    resealResult(reorderedResult);

    expect(validateEcgiResult(reorderedResult)).toEqual([]);
    expect(validateEcgiResultRequestBinding(reorderedResult, reorderedRequest)).toEqual([]);
  });

  it("rejects backend-invalid nested receipts after an attacker recomputes the outer digest", () => {
    const rejects = (
      mutate: (changed: JsonObject) => void,
      expectedError: string,
    ): void => {
      const changed = copy(result);
      mutate(changed);
      resealResult(changed);
      expect(validateEcgiResult(changed)).toContain(expectedError);
    };

    rejects(
      (changed) => {
        ((changed.solver as JsonObject).second_pass as JsonObject).pass_name = "evidence_graph";
      },
      "result.solver.second_pass.pass_name must equal kinase_feedback.",
    );
    rejects(
      (changed) => {
        ((changed.solver as JsonObject).first_pass as JsonObject).final_objective = -1;
      },
      "result.solver.first_pass.final_objective must be a finite non-negative number.",
    );
    rejects(
      (changed) => {
        (changed.node_states as JsonObject[])[0].classification = "not_estimable";
      },
      "result.node_states[0] limited estimates cannot be classified not_estimable.",
    );
    rejects(
      (changed) => {
        const state = (changed.node_states as JsonObject[])[0];
        (state.top_drivers as JsonObject[])[0].strength = -1;
      },
      "result.node_states[0].top_drivers[0].strength must be a finite non-negative number.",
    );
    rejects(
      (changed) => {
        const state = (changed.node_states as JsonObject[])[0];
        (state.ablation_effects as JsonObject[])[0].kind = "source";
      },
      "result.node_states[0].ablation_effects[0].kind must be exactly edge_family or modality.",
    );
    rejects(
      (changed) => {
        const kinase = (changed.kinase_states as JsonObject[])[0];
        kinase.mapped_substrates = 0;
      },
      "result.kinase_states[0] kinases with fewer than three mapped substrates must not carry enrichment statistics.",
    );
    rejects(
      (changed) => {
        const kinase = (changed.kinase_states as JsonObject[])[0];
        kinase.q_value = -1;
      },
      "result.kinase_states[0].q_value must be null or a finite number from 0 through 1.",
    );
    rejects(
      (changed) => {
        const comparison = changed.external_kinase_comparison as JsonObject;
        (comparison.matches as JsonObject[])[0].interval_overlap = "yes";
      },
      "result.external_kinase_comparison.matches[0].interval_overlap must be a boolean.",
    );
  });

  it.each([
    ["missing", undefined],
    ["unknown", "provisional"],
    ["forbidden full support", "supported"],
  ])("rejects %s support even when an attacker recomputes the result digest", (_label, support) => {
    const changed = copy(result);
    const state = (changed.node_states as JsonObject[])[0];
    if (support === undefined) delete state.support;
    else state.support = support;
    changed.result_digest = ecgiResultDigest(changed) as string;
    const errors = validateEcgiResult(changed);
    expect(errors.some((error) => error.includes("support"))).toBe(true);
  });

  it("rejects bare and internally contradictory replay claims", () => {
    expect(validateEcgiVerification({ verified: true }, result, request, profile)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("missing required fields"),
        expect.stringContaining("true if and only if"),
      ]),
    );

    const contradictory = copy(verification);
    contradictory.semantic_match = false;
    expect(validateEcgiVerification(contradictory, result, request, profile)).toContain(
      "verification.verified must be true if and only if every replay equality check is true.",
    );
  });

  it("binds replay digests and all three verification response headers", () => {
    const forged = copy(verification);
    forged.recomputed_request_digest = `sha256:${"a".repeat(64)}`;
    expect(validateEcgiVerification(forged, result, request, profile)).toContain(
      "verification.recomputed_request_digest does not match the executed request.",
    );
    expect(validateEcgiVerificationHeaders(headers({}), verification, profile)).toEqual(
      expect.arrayContaining([
        "X-GLIO-Profile-Digest response header is required.",
        "X-GLIO-Request-Digest response header is required.",
        "X-GLIO-Result-Digest response header is required.",
      ]),
    );
  });

  it("rejects every malformed profile and demo binding family", () => {
    const profileMutations: Array<(value: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.numpy_version = "latest"; },
      (value) => { value.claim_ceiling = "supported"; },
      (value) => { value.safety_class = "clinical"; },
      (value) => { value.interpretation = "prescriptive"; },
      (value) => { value.demo_graph_digest = "bad"; },
      (value) => { value.demo_topology_provenance_digest = "bad"; },
      (value) => { value.profile_digest = "bad"; },
      (value) => { value.constants = null; },
      (value) => { value.limits = null; },
      (value) => { value.relation_weights = null; },
    ];
    for (const mutate of profileMutations) {
      const value = copy(profile);
      mutate(value);
      expect(validateEcgiProfile(value).length).toBeGreaterThan(0);
    }
    const noDigest = copy(profile);
    delete noDigest.profile_digest;
    expect(ecgiProfileDigest(noDigest)).toBeNull();

    const invalidHeader = headers({ "X-GLIO-Profile-Digest": "SHA256:BAD" });
    expect(validateEcgiProfileHeaders(invalidHeader, profile)).toContain(
      "X-GLIO-Profile-Digest response header must be a lowercase sha256 digest.",
    );

    const wrongProfile = copy(request);
    wrongProfile.profile_id = "foreign";
    expect(validateEcgiDemo(wrongProfile, requestHeaders, profile).length).toBeGreaterThan(0);
    const wrongTopology = copy(request);
    (wrongTopology.edges as JsonObject[])[0].weight = 0.5;
    expect(validateEcgiDemo(wrongTopology, requestHeaders, profile)).toContain(
      "demo graph topology does not match profile.demo_graph_digest.",
    );
    const noProvenance = copy(request);
    delete noProvenance.topology_provenance;
    expect(validateEcgiDemo(noProvenance, requestHeaders, profile)).toContain(
      "demo.topology_provenance is required for profile binding.",
    );
    const changedProvenance = copy(request);
    (changedProvenance.topology_provenance as JsonObject).curation_note = "changed";
    expect(validateEcgiDemo(changedProvenance, requestHeaders, profile)).toContain(
      "demo topology provenance does not match profile.demo_topology_provenance_digest.",
    );
  });

  it("rejects the complete solver, state, kinase, and external-comparison error surface", () => {
    const firstPass = (value: JsonObject): JsonObject =>
      ((value.solver as JsonObject).first_pass as JsonObject);
    const firstNode = (value: JsonObject): JsonObject =>
      ((value.node_states as JsonObject[])[0]);
    const firstKinase = (value: JsonObject): JsonObject =>
      ((value.kinase_states as JsonObject[])[0]);
    const comparison = (value: JsonObject): JsonObject =>
      (value.external_kinase_comparison as JsonObject);
    const match = (value: JsonObject): JsonObject =>
      ((comparison(value).matches as JsonObject[])[0]);
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { value.algorithm_id = "foreign"; },
      (value) => { value.algorithm_version = "2.0.0"; },
      (value) => { value.profile_id = "foreign"; },
      (value) => { value.profile_digest = "bad"; },
      (value) => { value.request_digest = "bad"; },
      (value) => { value.result_digest = "bad"; },
      (value) => { value.research_use_only = false; },
      (value) => { value.non_prescriptive = false; },
      (value) => { value.sample_id = ""; },
      (value) => { value.limitations = null; },
      (value) => { value.limitations = []; },
      (value) => { value.limitations = Array.from({ length: 17 }, () => "limit"); },
      (value) => { value.limitations = [""]; },
      (value) => { value.solver = null; },
      (value) => { (value.solver as JsonObject).extra = true; },
      (value) => { (value.solver as JsonObject).first_pass = null; },
      (value) => { firstPass(value).extra = true; },
      (value) => { firstPass(value).pass_name = "kinase_feedback"; },
      (value) => { firstPass(value).solver_kind = "weighted_average"; },
      (value) => { firstPass(value).objective_trace_semantics = "unpaired"; },
      (value) => { firstPass(value).convergence_measure = "damped_update"; },
      (value) => { firstPass(value).converged = "yes"; },
      (value) => { firstPass(value).iterations = -1; },
      (value) => { firstPass(value).iterations = 2_001; },
      (value) => { firstPass(value).final_objective = "bad"; },
      (value) => { firstPass(value).max_update = -1; },
      (value) => { firstPass(value).objective_trace = null; },
      (value) => { firstPass(value).objective_trace = []; },
      (value) => { firstPass(value).objective_trace = Array.from({ length: 2_002 }, () => 0); },
      (value) => { firstPass(value).objective_trace = ["bad"]; },
      (value) => { firstPass(value).trace_digest = `sha256:${"a".repeat(64)}`; },
      (value) => { firstPass(value).trace_digest = "bad"; },
      (value) => { value.node_states = null; },
      (value) => { value.node_states = Array.from({ length: 257 }, () => firstNode(value)); },
      (value) => { (value.node_states as unknown[])[0] = null; },
      (value) => { firstNode(value).extra = true; },
      (value) => { firstNode(value).node_id = ""; },
      (value) => { firstNode(value).kind = "unknown"; },
      (value) => { firstNode(value).classification = "unknown"; },
      (value) => { firstNode(value).evidence_count = -1; },
      (value) => { firstNode(value).observed_count = 4_097; },
      (value) => { firstNode(value).censored_count = 0.5; },
      (value) => { firstNode(value).stability = 2; },
      (value) => { firstNode(value).discordance = -1; },
      (value) => { firstNode(value).top_drivers = null; },
      (value) => { firstNode(value).top_drivers = Array.from({ length: 6 }, () => null); },
      (value) => { (firstNode(value).top_drivers as unknown[])[0] = null; },
      (value) => { ((firstNode(value).top_drivers as JsonObject[])[0]).extra = true; },
      (value) => { ((firstNode(value).top_drivers as JsonObject[])[0]).driver_id = ""; },
      (value) => { ((firstNode(value).top_drivers as JsonObject[])[0]).driver_type = "unknown"; },
      (value) => { ((firstNode(value).top_drivers as JsonObject[])[0]).signed_contribution = "bad"; },
      (value) => { ((firstNode(value).top_drivers as JsonObject[])[0]).strength = -1; },
      (value) => { firstNode(value).ablation_effects = null; },
      (value) => { firstNode(value).ablation_effects = Array.from({ length: 17 }, () => null); },
      (value) => { (firstNode(value).ablation_effects as unknown[])[0] = null; },
      (value) => { ((firstNode(value).ablation_effects as JsonObject[])[0]).extra = true; },
      (value) => { ((firstNode(value).ablation_effects as JsonObject[])[0]).kind = "unknown"; },
      (value) => { ((firstNode(value).ablation_effects as JsonObject[])[0]).omitted = ""; },
      (value) => { ((firstNode(value).ablation_effects as JsonObject[])[0]).activity_delta = "bad"; },
      (value) => { firstNode(value).activity = null; },
      (value) => { firstNode(value).lower_bound = 2; },
      (value) => { firstNode(value).upper_bound = -2; },
      (value) => { firstNode(value).classification = "not_estimable"; },
      (value) => { firstNode(value).abstention_reason = "unexpected"; },
      (value) => { value.kinase_states = null; },
      (value) => { value.kinase_states = Array.from({ length: 129 }, () => firstKinase(value)); },
      (value) => { firstKinase(value).kind = "protein"; },
      (value) => { firstKinase(value).activity = 0; },
      (value) => { firstKinase(value).classification = "neutral"; },
      (value) => { firstKinase(value).abstention_reason = ""; },
      (value) => { firstKinase(value).mapped_substrates = -1; },
      (value) => { firstKinase(value).rank_statistic = 2; },
      (value) => { firstKinase(value).enrichment_score = "bad"; },
      (value) => { firstKinase(value).null_standard_deviation = 0; },
      (value) => { firstKinase(value).p_value = 2; },
      (value) => { firstKinase(value).q_value = -1; },
      (value) => { firstKinase(value).mapped_substrates = 2; },
      (value) => { firstKinase(value).rank_statistic = null; },
      (value) => { firstKinase(value).node_id = firstNode(value).node_id; },
      (value) => { value.external_kinase_comparison = "bad"; },
      (value) => { comparison(value).extra = true; },
      (value) => { comparison(value).profile_id = ""; },
      (value) => { comparison(value).source_digest = "bad"; },
      (value) => { comparison(value).matches = null; },
      (value) => { comparison(value).matches = Array.from({ length: 129 }, () => null); },
      (value) => { (comparison(value).matches as unknown[])[0] = null; },
      (value) => { match(value).extra = true; },
      (value) => { match(value).kinase_id = ""; },
      (value) => { match(value).local_activity = "bad"; },
      (value) => { match(value).external_activity = "bad"; },
      (value) => { match(value).activity_difference = "bad"; },
      (value) => { match(value).interval_overlap = "yes"; },
      (value) => { match(value).direction_agreement = "yes"; },
      (value) => { comparison(value).unmatched_local_ids = null; },
      (value) => { comparison(value).unmatched_local_ids = [""]; },
      (value) => { comparison(value).external_ids_with_abstained_local_estimates = null; },
      (value) => { comparison(value).external_ids_with_abstained_local_estimates = [""]; },
      (value) => { comparison(value).rank_correlation = 2; },
      (value) => { comparison(value).note = ""; },
    ];
    for (const mutate of mutations) {
      const value = copy(result);
      mutate(value);
      expect(validateEcgiResult(value).length).toBeGreaterThan(0);
    }

    const noComparison = copy(result);
    noComparison.external_kinase_comparison = null;
    resealResult(noComparison);
    expect(validateEcgiResult(noComparison)).toEqual([]);
  }, 20_000);

  it("rejects result provenance and cross-receipt binding mutations", () => {
    const provenanceMutations: Array<(value: JsonObject) => void> = [
      (value) => { value.provenance = null; },
      (value) => { (value.provenance as JsonObject).extra = true; },
      (value) => { (value.provenance as JsonObject).engine = "foreign"; },
      (value) => { (value.provenance as JsonObject).profile_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).request_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).computational_digest = "bad"; },
      (value) => { (value.provenance as JsonObject).demo_graph_digest = "bad"; },
    ];
    for (const mutate of provenanceMutations) {
      const value = copy(result);
      mutate(value);
      expect(validateEcgiResult(value).length).toBeGreaterThan(0);
    }

    const invalidRequest = copy(request);
    invalidRequest.nodes = null;
    expect(validateEcgiResultRequestBinding(result, invalidRequest)).toContain(
      "The executed request cannot be canonically digested.",
    );
    const foreignRequest = copy(request);
    foreignRequest.sample_id = "foreign.sample";
    expect(validateEcgiResultRequestBinding(result, foreignRequest).length).toBeGreaterThan(0);
    const foreignTopology = copy(result);
    ((foreignTopology.provenance as JsonObject).topology as JsonObject).curation_note = "foreign";
    expect(validateEcgiResultRequestBinding(foreignTopology, request)).toContain(
      "result.provenance.topology does not match the executed request.",
    );
    const foreignProfile = copy(profile);
    foreignProfile.profile_id = "foreign";
    foreignProfile.profile_digest = `sha256:${"a".repeat(64)}`;
    foreignProfile.demo_graph_digest = `sha256:${"b".repeat(64)}`;
    expect(validateEcgiResultProfileBinding(result, foreignProfile)).toHaveLength(3);
  });

  it("rejects every replay field type and receipt-binding contradiction", () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { value.extra = true; },
      (value) => { value.verified = "yes"; },
      (value) => { value.request_digest_match = "yes"; },
      (value) => { value.profile_digest_match = "yes"; },
      (value) => { value.result_digest_match = "yes"; },
      (value) => { value.solver_trace_match = "yes"; },
      (value) => { value.semantic_match = "yes"; },
      (value) => { value.provided_result_digest = "bad"; },
      (value) => { value.recomputed_result_digest = "bad"; },
      (value) => { value.recomputed_request_digest = "bad"; },
      (value) => { value.message = ""; },
      (value) => { value.provided_result_digest = `sha256:${"a".repeat(64)}`; },
      (value) => { value.recomputed_request_digest = `sha256:${"a".repeat(64)}`; },
      (value) => { value.recomputed_result_digest = `sha256:${"a".repeat(64)}`; },
    ];
    for (const mutate of mutations) {
      const value = copy(verification);
      mutate(value);
      expect(validateEcgiVerification(value, result, request, profile).length).toBeGreaterThan(0);
    }
    const foreignProfile = copy(profile);
    foreignProfile.profile_digest = `sha256:${"a".repeat(64)}`;
    expect(validateEcgiVerification(verification, result, request, foreignProfile)).toContain(
      "the admitted result and profile are not digest-bound.",
    );
  });
});
