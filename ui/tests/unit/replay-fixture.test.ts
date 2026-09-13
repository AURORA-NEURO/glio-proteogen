import { describe, expect, it } from "vitest";

import {
  algorithmProfile,
  analysisResult,
  demoRequest,
  verificationResult,
} from "../fixtures/proteogenomic-state";

describe("engine-generated replay fixture", () => {
  it("binds the request, result, profile, traces, and JSON-safe seed", () => {
    expect(verificationResult).toMatchObject({
      verified: true,
      request_digest_match: true,
      profile_digest_match: true,
      solver_trace_match: true,
      result_digest_match: true,
      semantic_match: true,
    });
    expect(verificationResult.recomputed_request_digest).toBe(analysisResult.request_digest);
    expect(verificationResult.provided_result_digest).toBe(analysisResult.result_digest);
    expect(verificationResult.recomputed_result_digest).toBe(analysisResult.result_digest);
    expect(analysisResult.profile_digest).toBe(algorithmProfile.profile_digest);
    expect(analysisResult.provenance.profile_digest).toBe(algorithmProfile.profile_digest);
    expect(analysisResult.provenance.request_digest).toBe(analysisResult.request_digest);
    expect(analysisResult.sample_id).toBe(demoRequest.sample_id);
    expect(analysisResult.solver.first_pass.pass_name).toBe("evidence_graph");
    expect(analysisResult.solver.second_pass.pass_name).toBe("kinase_feedback");
    expect(Number.isSafeInteger(analysisResult.provenance.deterministic_seed)).toBe(true);
  });
});
