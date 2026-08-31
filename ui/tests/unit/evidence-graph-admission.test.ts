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
});
