import { describe, expect, it, vi, afterEach } from "vitest";
import resultFixture from "../fixtures/cohort-replication-result.json";
import requestFixture from "../fixtures/cohort-replication-request.json";
import {
  assertReplicationBinding, cohortLabel, effectFor, forestDomain, formatEffect,
  parseReplicationProfile, parseReplicationRequest, parseReplicationResult,
  parseReplicationVerification, replicationFetch, replicationReplayEnvelope, REPLICATION_INPUT_LIMIT, REPLICATION_NETWORK_TIMEOUT_MS,
} from "../../src/lib/cohort-replication";

const fresh = () => structuredClone(resultFixture);
const profile = () => ({
  schema_version: "1.0.0", profile_id: resultFixture.profile_id,
  profile_digest: resultFixture.profile_digest, engine_semantic_digest: `sha256:${"a".repeat(64)}`,
  methods: ["Inverse-variance fixed effects"], assumptions: ["Independent cohorts"], synthetic_demo_only: true,
});

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("cross-cohort result admission", () => {
  it("admits the actual service demonstration, binds its frozen request and profile, and preserves missing vs zero", () => {
    const result = parseReplicationResult(resultFixture);
    const request = parseReplicationRequest(JSON.stringify(requestFixture));
    const admittedProfile = parseReplicationProfile(profile());
    expect(() => assertReplicationBinding(request, admittedProfile, result)).not.toThrow();
    const unavailable = result.features.find((feature) => feature.observed_count === 0)!;
    expect(unavailable.random_effect).toBeNull();
    expect(unavailable.effects.every((effect) => effect.estimate === null)).toBe(true);
    expect(effectFor(unavailable, result.cohorts[0].cohort_id)?.state).not.toBe("observed");
  });

  it.each([
    ["unrecognized profile", (v: ReturnType<typeof fresh>) => { v.profile_id = "other/1"; }],
    ["bad digest", (v: ReturnType<typeof fresh>) => { v.result_digest = "not-a-receipt"; }],
    ["inconsistent coverage", (v: ReturnType<typeof fresh>) => { v.features[0].observed_count = 5; }],
    ["missing state with numerical zero", (v: ReturnType<typeof fresh>) => { v.features[0].effects[0].estimate = 0; }],
    ["out-of-range heterogeneity", (v: ReturnType<typeof fresh>) => { v.features[1].heterogeneity!.i_squared_percent = 101; }],
    ["invalid probability", (v: ReturnType<typeof fresh>) => { v.features[1].adjusted_p_value = -1; }],
    ["invalid BY probability", (v: ReturnType<typeof fresh>) => { v.features[1].dependence_robust_adjusted_p_value = 2; }],
    ["duplicate cohorts", (v: ReturnType<typeof fresh>) => { v.cohorts[1].cohort_id = v.cohorts[0].cohort_id; }],
    ["duplicate feature effects", (v: ReturnType<typeof fresh>) => { v.features[0].effects[1].cohort_id = v.features[0].effects[0].cohort_id; }],
    ["incomplete family", (v: ReturnType<typeof fresh>) => { v.family_size += 1; }],
    ["participant data flag", (v: ReturnType<typeof fresh>) => { v.contains_participant_data = true; }],
    ["infinite pooled SE", (v: ReturnType<typeof fresh>) => { v.features[1].random_effect!.standard_error = Infinity; }],
    ["reversed prediction interval", (v: ReturnType<typeof fresh>) => { v.features[1].prediction_interval!.lower = 1000; }],
  ])("withholds charts for %s", (_, mutate) => {
    const value = fresh(); mutate(value); expect(() => parseReplicationResult(value)).toThrow("No charts were admitted");
  });

  it("rejects another request or changed scientific profile before rendering", () => {
    const result = parseReplicationResult(resultFixture);
    const p = parseReplicationProfile(profile());
    const request = structuredClone(requestFixture);
    request.analysis_id = "another-analysis";
    expect(() => assertReplicationBinding(request, p, result)).toThrow("frozen request");
    const alteredProfile = { ...p, profile_digest: `sha256:${"b".repeat(64)}` };
    expect(() => assertReplicationBinding(requestFixture, alteredProfile, result)).toThrow("active scientific profile");
    const alteredEffect = structuredClone(requestFixture);
    alteredEffect.features[1].effects[0].estimate = 42;
    expect(() => assertReplicationBinding(alteredEffect, p, result)).toThrow("frozen request");
  });

  it("requires well-formed profile identities and a matching replay receipt", () => {
    expect(() => parseReplicationProfile({ ...profile(), engine_semantic_digest: "unknown" })).toThrow("incompatible");
    const result = parseReplicationResult(resultFixture);
    const receipt = { valid: true, request_digest: result.request_digest, result_digest: result.result_digest };
    expect(parseReplicationVerification(receipt, result).valid).toBe(true);
    expect(parseReplicationVerification({ ...receipt, valid: false }, result).valid).toBe(false);
    expect(() => parseReplicationVerification({ ...receipt, request_digest: "another-request" }, result)).toThrow("incompatible verification");
  });

  it("exports a replay envelope with exactly the strict CLI and HTTP contract keys", () => {
    const result = parseReplicationResult(resultFixture);
    const envelope = replicationReplayEnvelope(requestFixture, result);
    expect(Object.keys(envelope).sort()).toEqual(["request", "result"]);
    expect(JSON.parse(JSON.stringify(envelope))).toEqual({ request: requestFixture, result: resultFixture });
  });
});

describe("bounded request import and display transforms", () => {
  it("rejects malformed, non-object, shapeless and oversized imports before sending", () => {
    expect(() => parseReplicationRequest("{")).toThrow("valid JSON");
    expect(() => parseReplicationRequest("[]")).toThrow("JSON object");
    expect(() => parseReplicationRequest("{}")).toThrow("cohort and feature");
    expect(() => parseReplicationRequest(" ".repeat(REPLICATION_INPUT_LIMIT + 1))).toThrow("2 MiB");
  });

  it("keeps zero distinct from absent values and includes all intervals in chart bounds", () => {
    expect(formatEffect(null)).toBe("—"); expect(formatEffect(0)).toBe("0.00"); expect(formatEffect(.5)).toBe("+0.50");
    expect(formatEffect(-.00001)).toBe("0.00"); expect(formatEffect(.00001)).toBe("0.00");
    expect(cohortLabel({ cohort_id: "id", label: "Cohort A" })).toBe("Cohort A");
    expect(cohortLabel({ cohort_id: "id" })).toBe("id");
    const result = parseReplicationResult(resultFixture);
    for (const feature of result.features) {
      const [lower, upper] = forestDomain(feature);
      expect(lower).toBeLessThan(0); expect(upper).toBeGreaterThan(0);
      if (feature.prediction_interval) { expect(lower).toBeLessThan(feature.prediction_interval.lower); expect(upper).toBeGreaterThan(feature.prediction_interval.upper); }
    }
  });

  it("sends actual service requests through the backend rewrite with cancellation and bounded response reads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ready: true }), { headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await expect(replicationFetch("analyze", controller.signal, requestFixture)).resolves.toEqual({ ready: true });
    expect(fetchMock).toHaveBeenCalledWith("/backend/v1/research/cohort-replication/analyze", expect.objectContaining({ method: "POST", signal: expect.any(AbortSignal), cache: "no-store", body: JSON.stringify(requestFixture) }));
  });

  it("aborts an unresponsive request at the network deadline with an explanatory timeout and clears its timer", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    let networkSignal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      networkSignal = init.signal as AbortSignal;
      networkSignal.addEventListener("abort", () => reject(networkSignal!.reason), { once: true });
    })));
    const pending = replicationFetch("analyze", caller.signal, requestFixture);
    const failure = expect(pending).rejects.toThrow("within 45 seconds");
    await vi.advanceTimersByTimeAsync(REPLICATION_NETWORK_TIMEOUT_MS);
    await failure;
    expect(networkSignal?.aborted).toBe(true);
    expect(caller.signal.aborted).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("propagates caller cancellation separately from timeout and does not leave a deadline timer", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    let networkSignal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      networkSignal = init.signal as AbortSignal;
      networkSignal.addEventListener("abort", () => reject(networkSignal!.reason), { once: true });
    })));
    const pending = replicationFetch("demo", caller.signal);
    const failure = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    caller.abort();
    await failure;
    expect(networkSignal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
